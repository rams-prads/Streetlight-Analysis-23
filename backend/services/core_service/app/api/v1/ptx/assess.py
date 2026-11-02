"""
Property register and assessment engine shared by cases, bulk jobs, migration and the seed:
validation against code lists, tax calculation with the rate table in force, property creation with a UPIN,
floors / owners history, assessments, demand raising and revision of already-raised demands (PT-10..PT-17, PT-30).
"""
import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ptx_calc import (
    compute_annual_tax, document_code, hash_aadhaar, money, period_bounds, period_for_date, period_label,
    period_share, period_start_for, periods_between,
)
from app.db.models import Locality, Ward
from app.db.ptx_models import (
    PtxAssessment, PtxCode, PtxDemand, PtxFloor, PtxLedger, PtxParty, PtxProperty, PtxPropertyHistory, PtxRateTable,
)
from .common import (
    BUCKET_COMPONENT, apply_advance_credit, bad_request, balances, dumps, emit_event, get_setting, loads, new_doc_no,
    new_upin, notify, post_ledger, today,
)


# ------------------------------------------------------------------------------------------------
# Code lists and validation
# ------------------------------------------------------------------------------------------------

async def codes(db: AsyncSession, tenant_id: str, list_name: str, active_only: bool = True) -> Dict[str, PtxCode]:
    stmt = select(PtxCode).where(PtxCode.tenant_id == tenant_id, PtxCode.list_name == list_name)
    if active_only:
        stmt = stmt.where(PtxCode.is_active.is_(True))
    return {c.code: c for c in (await db.execute(stmt)).scalars().all()}


async def labels(db: AsyncSession, tenant_id: str) -> Dict[str, str]:
    rows = (await db.execute(select(PtxCode.code, PtxCode.name_en).where(PtxCode.tenant_id == tenant_id))).all()
    return {code: name for code, name in rows}


async def exemption_info(db: AsyncSession, tenant_id: str, code: Optional[str]) -> Optional[Dict]:
    if not code:
        return None
    found = (await codes(db, tenant_id, "EXEMPTION")).get(code)
    if found is None:
        raise bad_request(f"Exemption '{code}' is not in the notified exemption list.")
    extra = loads(found.extra_json, {})
    return {"code": found.code, "nameEn": found.name_en, "percent": extra.get("percent", 0), "documents": extra.get("documents", [])}


async def validate_details(db: AsyncSession, ctx, details: Dict, floors: List[Dict], *, require_location: bool = True) -> Ward:
    """Checks a proposed property against the ward list and code lists before anything is saved."""
    ward = await db.scalar(select(Ward).where(Ward.id == details.get("wardId"), Ward.tenant_id == ctx.tenant_id))
    if ward is None:
        raise bad_request("Choose the ward the property is in.")
    ctx.ensure_scope(ward.id)
    if details.get("localityId"):
        loc = await db.scalar(select(Locality).where(Locality.id == details["localityId"], Locality.tenant_id == ctx.tenant_id))
        if loc is None or loc.ward_id != ward.id:
            raise bad_request("The locality chosen is not in this ward.")
    if require_location and not (details.get("address") or "").strip():
        raise bad_request("Enter the property address.")
    if details.get("propertyType", "BUILT") == "VACANT_LAND":
        if not details.get("siteAreaSqyd"):
            raise bad_request("Enter the site area (sq yd) for vacant land.")
    else:
        if not floors:
            raise bad_request("Add at least one floor with its built-up area and use.")
        usage = await codes(db, ctx.tenant_id, "USAGE")
        construction = await codes(db, ctx.tenant_id, "CONSTRUCTION")
        rooftop = await codes(db, ctx.tenant_id, "ROOFTOP_TYPE")
        seen = set()
        for f in floors:
            portion = f.get("portion") or "FULL"
            if portion == "ROOFTOP":
                if f.get("rooftopType") not in rooftop:
                    raise bad_request(f"Rooftop installation '{f.get('rooftopType')}' is not in the notified list.")
            else:
                if f["usageCode"] not in usage:
                    raise bad_request(f"Use '{f['usageCode']}' is not in the usage list.")
                if f["constructionCode"] not in construction:
                    raise bad_request(f"Construction '{f['constructionCode']}' is not in the construction type list.")
            if f.get("declaredAccommodation") and portion == "ROOFTOP":
                raise bad_request("Guest accommodation cannot be declared on a rooftop installation.")
            key = (f["floorNo"], portion, f.get("usageCode"), f.get("rooftopType"), bool(f.get("declaredAccommodation")))
            if key in seen:
                raise bad_request(f"Floor {f['floorNo']} has the same row twice. Combine them, or use 'part of the floor' for a different use.")
            seen.add(key)
        if all((f.get("portion") or "FULL") in ("ROOFTOP", "COMMON") for f in floors):
            raise bad_request("A building needs at least one floor row of its own (not only a rooftop installation or common-area share).")
    if (details.get("latitude") is None) != (details.get("longitude") is None):
        raise bad_request("Give both latitude and longitude, or neither.")
    if details.get("roadClass") and details["roadClass"] not in await codes(db, ctx.tenant_id, "ROAD_CLASS"):
        raise bad_request(f"Road class '{details['roadClass']}' is not in the road class list.")
    for key, label in (("approvedSetbackFt", "approved"), ("measuredSetbackFt", "measured")):
        if details.get(key) is not None and not (0 <= float(details[key]) <= 500):
            raise bad_request(f"The {label} setback must be between 0 and 500 feet.")
    await exemption_info(db, ctx.tenant_id, details.get("exemptionCode"))
    return ward


def check_owner_shares(owners: List[Dict]) -> None:
    if not owners:
        raise bad_request("Add at least one owner.")
    shares = [o.get("sharePercent") for o in owners]
    if any(s is not None for s in shares):
        if any(s is None for s in shares):
            raise bad_request("Give a share for every owner, or for none.")
        if money(sum(Decimal(str(s)) for s in shares)) != Decimal("100.00"):
            raise bad_request("Owner shares must add up to 100%.")


def secure_parties(parties: List[Dict]) -> List[Dict]:
    """Replaces any Aadhaar number with a salted hash and the last four digits before storing (PT-NF-21)."""
    out = []
    for p in parties:
        p = dict(p)
        number = p.pop("aadhaarNumber", None)
        if number:
            try:
                p["aadhaarHash"], p["aadhaarLast4"] = hash_aadhaar(number)
            except ValueError as exc:
                raise bad_request(str(exc))
        out.append(p)
    return out


# ------------------------------------------------------------------------------------------------
# Rate tables and calculation
# ------------------------------------------------------------------------------------------------

async def rate_table_for(db: AsyncSession, tenant_id: str, on: datetime.date, rate_table_id: Optional[str] = None) -> PtxRateTable:
    if rate_table_id:
        table = await db.scalar(select(PtxRateTable).where(PtxRateTable.id == rate_table_id, PtxRateTable.tenant_id == tenant_id))
    else:
        table = await db.scalar(select(PtxRateTable).where(PtxRateTable.tenant_id == tenant_id, PtxRateTable.status == "APPROVED",
                                                           PtxRateTable.effective_from <= on)
                                .order_by(PtxRateTable.effective_from.desc(), PtxRateTable.version.desc()).limit(1))
    if table is None:
        raise bad_request(f"No approved rate table is in force on {on.strftime('%d-%m-%Y')}.")
    return table


async def effective_period_start(db: AsyncSession, tenant_id: str, effective: Optional[datetime.date]) -> datetime.date:
    frequency = await get_setting(db, tenant_id, "demand.frequency")
    return period_start_for(effective or today(), frequency)


async def calculate(db: AsyncSession, tenant_id: str, details: Dict, floors: List[Dict], effective: datetime.date,
                    rate_table_id: Optional[str] = None) -> Dict:
    """Tax for a proposed property with the rate table in force on the effective date (PT-10, PT-11)."""
    table = await rate_table_for(db, tenant_id, effective, rate_table_id)
    ward = await db.get(Ward, details.get("wardId")) if details.get("wardId") else None
    loc = await db.get(Locality, details.get("localityId")) if details.get("localityId") else None
    try:
        result = compute_annual_tax(
            rules=loads(table.rules_json, {}), property_type=details.get("propertyType", "BUILT"),
            site_area_sqyd=details.get("siteAreaSqyd") or 0, construction_year=details.get("constructionYear"),
            floors=floors, ward_number=ward.ward_number if ward else None, locality_code=loc.locality_code if loc else None,
            as_of=effective, exemption=await exemption_info(db, tenant_id, details.get("exemptionCode")),
            labels=await labels(db, tenant_id), road_class=details.get("roadClass"),
            setback={"approvedFt": details.get("approvedSetbackFt"), "measuredFt": details.get("measuredSetbackFt")})
    except ValueError as exc:
        raise bad_request(str(exc))
    sheet = result["sheet"]
    frequency = await get_setting(db, tenant_id, "demand.frequency")
    first = period_for_date(effective, frequency)
    sheet.update({"rateTableId": table.id, "rateTableVersion": table.version, "rateTableEffectiveFrom": table.effective_from.isoformat(),
                  "effectiveFrom": effective.isoformat(), "frequency": frequency, "firstPeriod": first,
                  "firstPeriodLabel": period_label(first), "instalment": float(period_share(result["annualTax"], first)),
                  "orderReference": table.order_reference})
    return {"annualTax": result["annualTax"], "components": result["components"], "sheet": sheet, "rateTable": table}


async def current_floors(db: AsyncSession, property_id: str) -> List[Dict]:
    rows = (await db.execute(select(PtxFloor).where(PtxFloor.property_id == property_id, PtxFloor.is_current.is_(True))
                             .order_by(PtxFloor.floor_no, PtxFloor.portion, PtxFloor.usage_code))).scalars().all()
    return [{"floorNo": f.floor_no, "usageCode": f.usage_code, "constructionCode": f.construction_code,
             "builtupSqft": float(f.builtup_sqft), "occupancy": f.occupancy, "portion": f.portion, "rooftopType": f.rooftop_type,
             "declaredAccommodation": bool(f.declared_accommodation)} for f in rows]


def property_details(prop: PtxProperty) -> Dict:
    return {"propertyType": prop.property_type, "wardId": prop.ward_id, "localityId": prop.locality_id, "doorNo": prop.door_no,
            "address": prop.address, "pincode": prop.pincode, "latitude": prop.latitude, "longitude": prop.longitude,
            "footprintId": prop.footprint_id, "siteAreaSqyd": float(prop.site_area_sqyd or 0), "constructionYear": prop.construction_year,
            "exemptionCode": prop.exemption_code, "exemptionDocument": prop.exemption_document,
            "buildingPermissionNo": prop.building_permission_no, "occupancyCertificateNo": prop.occupancy_certificate_no,
            "roadClass": prop.road_class, "approvedSetbackFt": prop.approved_setback_ft, "measuredSetbackFt": prop.measured_setback_ft}


# ------------------------------------------------------------------------------------------------
# Register changes
# ------------------------------------------------------------------------------------------------

def record_change(db: AsyncSession, actor: str, prop: PtxProperty, field: str, new_value, reason: str) -> bool:
    """Sets a field and keeps the old value, new value, who, when and why (PT-07)."""
    old_value = getattr(prop, field)
    norm = lambda v: None if v in ("", None) else str(v)  # noqa: E731
    if norm(old_value) == norm(new_value):
        return False
    setattr(prop, field, new_value)
    db.add(PtxPropertyHistory(tenant_id=prop.tenant_id, property_id=prop.id, field=field, old_value=norm(old_value),
                              new_value=norm(new_value), reason=reason, changed_by=actor))
    return True


async def set_floors(db: AsyncSession, actor: str, prop: PtxProperty, floors: List[Dict], valid_from: datetime.date, reason: str) -> None:
    old = (await db.execute(select(PtxFloor).where(PtxFloor.property_id == prop.id, PtxFloor.is_current.is_(True)))).scalars().all()
    tag = lambda portion, rooftop, declared: (f"[{portion.lower()}]" if portion != "FULL" else "") + (f"[{rooftop}]" if rooftop else "") + ("[guest accommodation]" if declared else "")  # noqa: E731
    before = [f"{f.floor_no}{tag(f.portion, f.rooftop_type, f.declared_accommodation)}:{f.usage_code}/{f.construction_code}/{f.builtup_sqft}/{f.occupancy}"
              for f in sorted(old, key=lambda x: (x.floor_no, x.portion, x.usage_code))]
    for f in old:
        f.is_current = False
        f.valid_to = valid_from
    for f in floors:
        db.add(PtxFloor(tenant_id=prop.tenant_id, property_id=prop.id, floor_no=f["floorNo"], usage_code=f.get("usageCode") or "",
                        construction_code=f.get("constructionCode") or "", builtup_sqft=Decimal(str(f["builtupSqft"])),
                        occupancy=f.get("occupancy", "OWNER"), portion=f.get("portion") or "FULL", rooftop_type=f.get("rooftopType"),
                        declared_accommodation=bool(f.get("declaredAccommodation")), valid_from=valid_from))
    after = [f"{f['floorNo']}{tag(f.get('portion') or 'FULL', f.get('rooftopType'), f.get('declaredAccommodation'))}:{f.get('usageCode') or ''}/"
             f"{f.get('constructionCode') or ''}/{f['builtupSqft']}/{f.get('occupancy', 'OWNER')}"
             for f in sorted(floors, key=lambda x: (x["floorNo"], x.get("portion") or "FULL", x.get("usageCode") or ""))]
    if before != after:
        db.add(PtxPropertyHistory(tenant_id=prop.tenant_id, property_id=prop.id, field="floors", old_value="; ".join(before) or None,
                                  new_value="; ".join(after) or None, reason=reason, changed_by=actor))


async def set_parties(db: AsyncSession, actor: str, prop: PtxProperty, parties: List[Dict], role: str, from_date: datetime.date,
                      reason: str, application_no: Optional[str] = None) -> None:
    old = (await db.execute(select(PtxParty).where(PtxParty.property_id == prop.id, PtxParty.role == role,
                                                   PtxParty.is_current.is_(True)))).scalars().all()
    before = [p.full_name for p in old]
    for p in old:
        p.is_current = False
        p.to_date = from_date
    for p in parties:
        db.add(PtxParty(tenant_id=prop.tenant_id, property_id=prop.id, role=role, full_name=p["fullName"], mobile_number=p.get("mobileNumber"),
                        email=p.get("email"), aadhaar_hash=p.get("aadhaarHash"), aadhaar_last4=p.get("aadhaarLast4"),
                        share_percent=Decimal(str(p["sharePercent"])) if p.get("sharePercent") is not None else None,
                        citizen_id=p.get("citizenId"), from_date=from_date, via_application=application_no))
    after = [p["fullName"] for p in parties]
    if before != after:
        db.add(PtxPropertyHistory(tenant_id=prop.tenant_id, property_id=prop.id, field="owners" if role == "OWNER" else "occupiers",
                                  old_value=", ".join(before) or None, new_value=", ".join(after) or None, reason=reason, changed_by=actor))


async def create_property(db: AsyncSession, actor: str, tenant_id: str, sub_tenant_id: Optional[str], details: Dict, floors: List[Dict],
                          owners: List[Dict], occupiers: List[Dict], source: str, valid_from: datetime.date,
                          application_no: Optional[str], old_assessment_no: Optional[str] = None) -> PtxProperty:
    ward = await db.get(Ward, details["wardId"])
    prop = PtxProperty(
        tenant_id=tenant_id, sub_tenant_id=sub_tenant_id, upin=await new_upin(db, tenant_id), old_assessment_no=old_assessment_no,
        property_type=details.get("propertyType", "BUILT"), status="ACTIVE", ward_id=ward.id, zone_id=ward.zone_id,
        locality_id=details.get("localityId"), door_no=details.get("doorNo"), address=details.get("address") or "",
        pincode=details.get("pincode"), latitude=details.get("latitude"), longitude=details.get("longitude"),
        footprint_id=details.get("footprintId"), location_pending=details.get("latitude") is None,
        site_area_sqyd=Decimal(str(details.get("siteAreaSqyd") or 0)), construction_year=details.get("constructionYear"),
        exemption_code=details.get("exemptionCode"), exemption_document=details.get("exemptionDocument"),
        building_permission_no=details.get("buildingPermissionNo"), occupancy_certificate_no=details.get("occupancyCertificateNo"),
        road_class=details.get("roadClass"), approved_setback_ft=details.get("approvedSetbackFt"), measured_setback_ft=details.get("measuredSetbackFt"),
        complex_name=details.get("complexName"), unit_no=details.get("unitNo"),
        source=source, created_by=actor,
    )
    db.add(prop)
    await db.flush()
    reason = f"Created by {application_no}" if application_no else f"Created ({source.lower()})"
    if prop.property_type != "VACANT_LAND":
        await set_floors(db, actor, prop, floors, valid_from, reason)
    await set_parties(db, actor, prop, owners, "OWNER", valid_from, reason, application_no)
    if occupiers:
        await set_parties(db, actor, prop, occupiers, "OCCUPIER", valid_from, reason, application_no)
    if prop.footprint_id:
        from app.db.ptx_models import PtxFootprint
        fp = await db.get(PtxFootprint, prop.footprint_id)
        if fp is not None and fp.tenant_id == tenant_id:
            fp.property_id = prop.id
            fp.verification_status = "VERIFIED"
    emit_event(db, tenant_id, "property.created", prop.id, {"upin": prop.upin, "wardId": prop.ward_id, "address": prop.address,
                                                           "latitude": prop.latitude, "longitude": prop.longitude, "source": source})
    return prop


async def apply_details(db: AsyncSession, actor: str, prop: PtxProperty, details: Dict, reason: str) -> None:
    """Applies changed register fields from an approved case (area, construction year, exemption ...)."""
    mapping = {"siteAreaSqyd": "site_area_sqyd", "constructionYear": "construction_year", "exemptionCode": "exemption_code",
               "exemptionDocument": "exemption_document", "propertyType": "property_type", "doorNo": "door_no", "address": "address",
               "localityId": "locality_id", "latitude": "latitude", "longitude": "longitude", "footprintId": "footprint_id",
               "buildingPermissionNo": "building_permission_no", "occupancyCertificateNo": "occupancy_certificate_no", "pincode": "pincode",
               "roadClass": "road_class", "approvedSetbackFt": "approved_setback_ft", "measuredSetbackFt": "measured_setback_ft"}
    for key, column in mapping.items():
        if key in details:
            value = details[key]
            if column == "site_area_sqyd":
                value = Decimal(str(value or 0))
            record_change(db, actor, prop, column, value, reason)
    if prop.latitude is not None:
        prop.location_pending = False


async def new_assessment(db: AsyncSession, actor: str, prop: PtxProperty, kind: str, calc: Dict, effective_from: datetime.date,
                         status: str, application_id: Optional[str] = None, notice_no: Optional[str] = None,
                         objection_until: Optional[datetime.date] = None) -> PtxAssessment:
    if status == "FINAL":
        older = (await db.execute(select(PtxAssessment).where(PtxAssessment.property_id == prop.id, PtxAssessment.status == "FINAL"))).scalars().all()
        for a in older:
            # an earlier-dated one stays in force until this one starts; a same- or later-dated one is replaced outright,
            # so a back-assessment governs every period it reaches back to (PT-11)
            a.status = "SUPERSEDED" if a.effective_from < effective_from else "REPLACED"
    a = PtxAssessment(
        tenant_id=prop.tenant_id, assessment_no=await new_doc_no(db, prop.tenant_id, "PAS", "assessment"), property_id=prop.id,
        application_id=application_id, kind=kind, rate_table_id=calc["rateTable"].id if calc.get("rateTable") else None,
        effective_from=effective_from, annual_tax=calc["annualTax"], components_json=dumps({k: float(v) for k, v in calc["components"].items()}),
        calculation_json=dumps(calc["sheet"]), status=status, notice_no=notice_no, objection_until=objection_until,
        approved_by=actor if status == "FINAL" else None, created_by=actor,
    )
    db.add(a)
    await db.flush()
    return a


async def assessment_for_period(db: AsyncSession, property_id: str, period_start: datetime.date) -> Optional[PtxAssessment]:
    """Assessment in force at the start of a period: latest final (or since superseded) one effective by then."""
    return await db.scalar(select(PtxAssessment).where(PtxAssessment.property_id == property_id,
                                                       PtxAssessment.status.in_(["FINAL", "SUPERSEDED"]),
                                                       PtxAssessment.effective_from <= period_start)
                           .order_by(PtxAssessment.effective_from.desc(), PtxAssessment.created_at.desc()).limit(1))


# ------------------------------------------------------------------------------------------------
# Demand
# ------------------------------------------------------------------------------------------------

async def _post_by_bucket(db: AsyncSession, actor, prop: PtxProperty, bucket: str, component: str, amount: Decimal, *,
                          txn_type: str, demand_id: Optional[str], reference_no: Optional[str], narration: str,
                          entry_date: datetime.date) -> None:
    """Posts an increase, or a reduction that never takes a dues bucket below zero (the rest becomes advance credit)."""
    amount = money(amount)
    if amount == 0:
        return
    if amount > 0:
        await post_ledger(db, actor, prop=prop, txn_type=txn_type, component=component, bucket=bucket, amount=amount,
                          demand_id=demand_id, reference_no=reference_no, narration=narration, entry_date=entry_date)
        return
    await db.flush()
    held = (await balances(db, prop.tenant_id, prop.id))[bucket]
    within = max(min(-amount, held), Decimal("0"))
    if within > 0:
        await post_ledger(db, actor, prop=prop, txn_type=txn_type, component=component, bucket=bucket, amount=-within,
                          demand_id=demand_id, reference_no=reference_no, narration=narration, entry_date=entry_date)
    rest = money(-amount - within)
    if rest > 0:
        await post_ledger(db, actor, prop=prop, txn_type=txn_type, component=component, bucket="ADVANCE", amount=-rest,
                          demand_id=demand_id, reference_no=reference_no, narration=f"{narration} (already paid; held as advance)",
                          entry_date=entry_date)


async def raise_demand(db: AsyncSession, actor, prop: PtxProperty, period: str, run_id: Optional[str] = None,
                       on_date: Optional[datetime.date] = None) -> Dict:
    """Raises one property's demand for one period, by component (PT-30). Never twice for the same period."""
    if prop.status != "ACTIVE":
        return {"result": "SKIPPED", "reason": f"Property is {prop.status.lower()}"}
    if await db.scalar(select(PtxDemand.id).where(PtxDemand.property_id == prop.id, PtxDemand.period == period)):
        return {"result": "ALREADY_RAISED"}
    period_from, period_to = period_bounds(period)
    assessment = await assessment_for_period(db, prop.id, period_from)
    if assessment is None:
        return {"result": "HELD", "reason": "No final assessment in force for this period"}
    components = {k: period_share(Decimal(str(v)), period) for k, v in loads(assessment.components_json, {}).items()}
    components = {k: v for k, v in components.items() if v > 0}
    amount = money(sum(components.values(), Decimal("0")))
    if amount <= 0:
        return {"result": "SKIPPED", "reason": "No tax payable (fully exempt)"}
    due_days = int(await get_setting(db, prop.tenant_id, "demand.dueDaysFromPeriodStart", period_from))
    latest = await db.scalar(select(func.max(PtxDemand.period_from)).where(PtxDemand.property_id == prop.id))
    back_period = latest is not None and period_from < latest
    raise_date = on_date or (max(today(), period_from) if not back_period else today())

    demand = PtxDemand(
        tenant_id=prop.tenant_id, demand_no=await new_doc_no(db, prop.tenant_id, "PDM", "demand"), property_id=prop.id,
        ward_id=prop.ward_id, period=period, financial_year=period.rsplit("-", 1)[0], period_from=period_from, period_to=period_to,
        due_date=period_from + datetime.timedelta(days=due_days), assessment_id=assessment.id,
        components_json=dumps({k: float(v) for k, v in components.items()}), amount=amount, verification_code="PENDING",
        run_id=run_id, created_by=actor if isinstance(actor, str) else actor.username,
    )
    db.add(demand)
    await db.flush()
    bal = await balances(db, prop.tenant_id, prop.id)
    if not back_period and bal["CURRENT"] != 0:
        # what was current on the last demand becomes arrears
        await post_ledger(db, actor, prop=prop, txn_type="ROLLOVER", component="PROPERTY_TAX", bucket="CURRENT", amount=-bal["CURRENT"],
                          demand_id=demand.id, entry_date=raise_date, narration=f"Unpaid current tax moved to arrears on {demand.demand_no}")
        await post_ledger(db, actor, prop=prop, txn_type="ROLLOVER", component="ARREAR", bucket="ARREAR", amount=bal["CURRENT"],
                          demand_id=demand.id, entry_date=raise_date, narration=f"Unpaid current tax moved to arrears on {demand.demand_no}")
    bucket = "ARREAR" if back_period else "CURRENT"
    for component, value in components.items():
        await post_ledger(db, actor, prop=prop, txn_type="DEMAND", component=component, bucket=bucket, amount=value, demand_id=demand.id,
                          reference_no=demand.demand_no, entry_date=raise_date, narration=f"{period_label(period)} {component.replace('_', ' ').lower()}")
    await db.flush()
    order = await get_setting(db, prop.tenant_id, "payment.allocationOrder")
    await apply_advance_credit(db, actor, prop, order, f"Advance adjusted on {demand.demand_no}")
    await db.flush()
    after = await balances(db, prop.tenant_id, prop.id)
    demand.arrears_at_raise = money(max(after["ARREAR"], Decimal("0")))
    demand.penalty_at_raise = money(max(after["PENALTY"], Decimal("0")))
    demand.verification_code = document_code("DEMAND", demand.demand_no, amount)
    emit_event(db, prop.tenant_id, "demand.raised", demand.id, {"upin": prop.upin, "demandNo": demand.demand_no, "period": period,
                                                                 "amount": float(amount), "dueDate": demand.due_date.isoformat(), "wardId": prop.ward_id})
    owner = await db.scalar(select(PtxParty).where(PtxParty.property_id == prop.id, PtxParty.role == "OWNER", PtxParty.is_current.is_(True),
                                                   PtxParty.mobile_number.isnot(None)).limit(1))
    if owner is not None and not back_period:
        await notify(db, prop.tenant_id, recipient=owner.mobile_number, channel="WHATSAPP", template="DEMAND_RAISED", property_id=prop.id,
                     ref_no=demand.demand_no, dedupe_key=f"demand:{demand.id}",
                     message_en=f"GWMC Property Tax: {period_label(period)} tax of Rs {amount} for {prop.upin} is due by "
                                f"{demand.due_date.strftime('%d-%m-%Y')}. Pay online: MyGWMC portal.",
                     message_te=f"జీడబ్ల్యూఎంసీ ఆస్తి పన్ను: {prop.upin} కోసం రూ. {amount} పన్ను "
                                f"{demand.due_date.strftime('%d-%m-%Y')} లోపు చెల్లించాలి. MyGWMC పోర్టల్‌లో చెల్లించండి.")
    if owner is not None and owner.email and not back_period:
        await notify(db, prop.tenant_id, recipient=owner.email, channel="EMAIL", template="DEMAND_RAISED", property_id=prop.id, ref_no=demand.demand_no,
                     dedupe_key=f"demand-email:{demand.id}",
                     message_en=f"GWMC Property Tax: {period_label(period)} tax of Rs {amount} for {prop.upin} is due by {demand.due_date.strftime('%d-%m-%Y')}. "
                                f"Your bill {demand.demand_no} can be downloaded and paid on the MyGWMC portal.",
                     message_te=f"జీడబ్ల్యూఎంసీ ఆస్తి పన్ను: {prop.upin} కోసం రూ. {amount} పన్ను {demand.due_date.strftime('%d-%m-%Y')} లోపు చెల్లించాలి. బిల్లు {demand.demand_no}.")
    return {"result": "RAISED", "demandNo": demand.demand_no, "amount": float(amount)}


async def raise_missing_demands(db: AsyncSession, actor, prop: PtxProperty, upto: Optional[datetime.date] = None) -> List[Dict]:
    """Raises every period from the first assessment up to the current period that has no demand yet (oldest first)."""
    first = await db.scalar(select(func.min(PtxAssessment.effective_from)).where(PtxAssessment.property_id == prop.id,
                                                                                 PtxAssessment.status.in_(["FINAL", "SUPERSEDED"])))
    if first is None:
        return []
    frequency = await get_setting(db, prop.tenant_id, "demand.frequency")
    out = []
    for p in periods_between(first, upto or today(), frequency):
        result = await raise_demand(db, actor, prop, p)
        if result["result"] == "RAISED":
            out.append(result)
    return out


async def revise_raised_demands(db: AsyncSession, actor, prop: PtxProperty, from_date: datetime.date, reason: str) -> Decimal:
    """
    After a reassessment that applies from an earlier date (use change, area change, revision), the difference for
    periods already billed is posted as revision entries; the original demand rows never change (PT-12, PT-17).
    """
    demands = (await db.execute(select(PtxDemand).where(PtxDemand.property_id == prop.id, PtxDemand.period_from >= from_date)
                                .order_by(PtxDemand.period_from))).scalars().all()
    if not demands:
        return Decimal("0.00")
    latest_from = await db.scalar(select(func.max(PtxDemand.period_from)).where(PtxDemand.property_id == prop.id))
    net = Decimal("0.00")
    for d in demands:
        assessment = await assessment_for_period(db, prop.id, d.period_from)
        target = {k: period_share(Decimal(str(v)), d.period) for k, v in loads(assessment.components_json, {}).items()} if assessment else {}
        billed = {k: money(v) for k, v in loads(d.components_json, {}).items()}
        rows = (await db.execute(select(PtxLedger.component, func.sum(PtxLedger.amount)).where(
            PtxLedger.demand_id == d.id, PtxLedger.txn_type == "DEMAND_REVISION").group_by(PtxLedger.component))).all()
        for component, total in rows:
            billed[component] = money(billed.get(component, 0) + money(total))
        bucket = "CURRENT" if d.period_from == latest_from else "ARREAR"
        for component in sorted(set(target) | set(billed)):
            diff = money(target.get(component, 0) - billed.get(component, 0))
            if diff != 0:
                await _post_by_bucket(db, actor, prop, bucket, component if bucket == "CURRENT" else "ARREAR", diff,
                                      txn_type="DEMAND_REVISION", demand_id=d.id, reference_no=d.demand_no,
                                      narration=f"Revised {period_label(d.period)}: {reason}", entry_date=today())
                net = money(net + diff)
    return net


async def transfer_balance(db: AsyncSession, actor, source: PtxProperty, target: PtxProperty, share: Decimal, narration: str) -> None:
    """Moves a share of every dues bucket from one property to another (subdivision / amalgamation).
    Pass share=1 for the last target so rounding leaves nothing behind."""
    await db.flush()
    bal = await balances(db, source.tenant_id, source.id)
    for bucket in ("PENALTY", "FEE", "ARREAR", "CURRENT", "ADVANCE"):
        amount = money(bal[bucket] * share)
        if amount == 0:
            continue
        component = BUCKET_COMPONENT[bucket] if bucket != "CURRENT" else "ARREAR"
        target_bucket = "ARREAR" if bucket == "CURRENT" else bucket
        await post_ledger(db, actor, prop=source, txn_type="TRANSFER_OUT", component=component, bucket=bucket, amount=-amount,
                          reference_no=target.upin, narration=narration)
        await post_ledger(db, actor, prop=target, txn_type="TRANSFER_IN", component=component, bucket=target_bucket, amount=amount,
                          reference_no=source.upin, narration=narration)
