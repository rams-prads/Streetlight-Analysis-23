"""Property register: search, record, dues, history, corrections and the tax calculator (PT-01..PT-07, PT-11, PT-IR-01)."""
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ptx_calc import mask_mobile, money, payment_status, period_for_date, period_label
from app.db.models import Locality
from app.db.ptx_models import (
    PtxAssessment, PtxCode, PtxDemand, PtxFloor, PtxFootprint, PtxLedger, PtxParty, PtxProperty, PtxPropertyHistory,
    PtxPropertyLink,
)
from app.db.session import get_read_db, get_write_db
from app.schemas.ptx import CalculatePreview, OccupierUpdate, PropertyUpdate
from .assess import calculate, current_floors, effective_period_start, record_change, secure_parties, set_parties, validate_details
from .common import (
    PERMISSIONS, PtxAPIRoute, PtxContext, audit, bad_request, balances, bulk_balances, dues_summary, dues_total, dumps, emit_event,
    get_setting, load_property, loads, locality_map, page, paginate, ptx_context, today, ward_maps,
)

router = APIRouter(route_class=PtxAPIRoute)


async def owner_names(db: AsyncSession, ids: List[str]) -> Dict[str, List[PtxParty]]:
    out: Dict[str, List[PtxParty]] = {i: [] for i in ids}
    if ids:
        rows = (await db.execute(select(PtxParty).where(PtxParty.property_id.in_(ids), PtxParty.role == "OWNER",
                                                        PtxParty.is_current.is_(True)))).scalars().all()
        for p in rows:
            out[p.property_id].append(p)
    return out


def summary_of(prop: PtxProperty, wards: Dict, owners: List[PtxParty], bal: Dict[str, Decimal]) -> Dict:
    ward = wards.get(prop.ward_id, {})
    return {
        "id": prop.id, "upin": prop.upin, "oldAssessmentNo": prop.old_assessment_no, "propertyType": prop.property_type,
        "status": prop.status, "doorNo": prop.door_no, "address": prop.address, "wardId": prop.ward_id, "complexName": prop.complex_name, "unitNo": prop.unit_no, "stateRef": prop.state_ref,
        "wardNumber": ward.get("wardNumber"), "wardName": ward.get("wardName"), "zoneName": ward.get("zoneName"),
        "ownerNames": ", ".join(o.full_name for o in owners) or "-", "latitude": prop.latitude, "longitude": prop.longitude,
        "locationPending": prop.location_pending, "totalDue": dues_summary(bal)["totalDue"], "paymentStatus": payment_status(bal),
    }


@router.get("/me")
async def my_access(ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    """What the signed-in user may do, plus the code lists every screen needs (loaded from the database)."""
    wards, _ = await ward_maps(db, ctx.tenant_id)
    locs = await locality_map(db, ctx.tenant_id)
    code_rows = (await db.execute(select(PtxCode).where(PtxCode.tenant_id == ctx.tenant_id, PtxCode.is_active.is_(True))
                                  .order_by(PtxCode.list_name, PtxCode.code))).scalars().all()
    lists: Dict[str, List[Dict]] = {}
    for c in code_rows:
        lists.setdefault(c.list_name, []).append({"code": c.code, "nameEn": c.name_en, "nameTe": c.name_te, "extra": loads(c.extra_json, {})})
    frequency = await get_setting(db, ctx.tenant_id, "demand.frequency")
    current = period_for_date(today(), frequency)
    return {
        "username": ctx.username, "displayName": ctx.user.get("name") or ctx.username, "roles": sorted(ctx.roles), "tenantId": ctx.tenant_id, "scope": ctx.scope_label,
        "permissions": sorted(p for p in PERMISSIONS if ctx.can(p)),
        "wards": sorted([w for w in wards.values() if ctx.in_scope(w["wardId"])], key=lambda w: w["wardNumber"]),
        "localities": sorted([l for l in locs.values() if ctx.in_scope(l["wardId"])], key=lambda l: l["name"]),
        "codes": lists, "frequency": frequency, "currentPeriod": current, "currentPeriodLabel": period_label(current),
        "staffTimeoutMinutes": await get_setting(db, ctx.tenant_id, "session.staffTimeoutMinutes"),
        # shown before applying so nobody is surprised by a fee (PT-13, PT-15, PT-16)
        "fees": {"mutationByReason": (await get_setting(db, ctx.tenant_id, "mutation"))["feeByReason"],
                 "subdivision": (await get_setting(db, ctx.tenant_id, "subdivision")).get("fee", 0),
                 "amalgamation": (await get_setting(db, ctx.tenant_id, "amalgamation")).get("fee", 0)},
        "objectionDays": (await get_setting(db, ctx.tenant_id, "assessment"))["objectionDays"],
    }


@router.get("/properties")
async def search_properties(
    search: Optional[str] = Query(None, description="UPIN, old assessment no., owner name, door no. or mobile"),
    ward_id: Optional[str] = Query(None, alias="wardId"), status: Optional[str] = Query(None),
    payment_state: Optional[str] = Query(None, alias="paymentStatus"), location_pending: Optional[bool] = Query(None, alias="locationPending"),
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
    ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db),
):
    """Property search with pagination (PT-04, PT-05, PT-IR-01)."""
    ctx.require("property.view")
    stmt = select(PtxProperty).where(PtxProperty.tenant_id == ctx.tenant_id, ctx.ward_filter(PtxProperty.ward_id))
    if ctx.sub_tenant_id:
        stmt = stmt.where(or_(PtxProperty.sub_tenant_id == ctx.sub_tenant_id, PtxProperty.sub_tenant_id.is_(None)))
    if search and search.strip():
        like = f"%{search.strip()}%"
        digits = "".join(ch for ch in search if ch.isdigit())
        party = select(PtxParty.property_id).where(PtxParty.tenant_id == ctx.tenant_id, PtxParty.is_current.is_(True),
                                                   or_(PtxParty.full_name.ilike(like),
                                                       PtxParty.mobile_number.ilike(f"%{digits}%") if len(digits) >= 4 else false()))
        stmt = stmt.where(or_(PtxProperty.upin.ilike(like), PtxProperty.old_assessment_no.ilike(like), PtxProperty.door_no.ilike(like),
                              PtxProperty.address.ilike(like), PtxProperty.complex_name.ilike(like), PtxProperty.id.in_(party)))
    if ward_id:
        stmt = stmt.where(PtxProperty.ward_id == ward_id)
    if status:
        stmt = stmt.where(PtxProperty.status == status.upper())
    if location_pending is not None:
        stmt = stmt.where(PtxProperty.location_pending.is_(location_pending))
    if payment_state:
        sums = select(PtxLedger.property_id.label("pid"),
                      func.sum(case((PtxLedger.bucket.in_(["ARREAR", "PENALTY", "FEE"]), PtxLedger.amount), else_=0)).label("older"),
                      func.sum(case((PtxLedger.bucket == "CURRENT", PtxLedger.amount), else_=0)).label("cur")) \
            .where(PtxLedger.tenant_id == ctx.tenant_id).group_by(PtxLedger.property_id).subquery()
        stmt = stmt.outerjoin(sums, sums.c.pid == PtxProperty.id)
        older, cur = func.coalesce(sums.c.older, 0), func.coalesce(sums.c.cur, 0)
        state = payment_state.upper()
        if state == "ARREARS":
            stmt = stmt.where(older > 0)
        elif state == "DUE":
            stmt = stmt.where(older <= 0, cur > 0)
        elif state == "PAID":
            stmt = stmt.where(older <= 0, cur <= 0)
        else:
            raise bad_request("Payment status must be ARREARS, DUE or PAID.")
    rows, total = await paginate(db, stmt.order_by(PtxProperty.upin), skip, limit)
    props = [r[0] for r in rows]
    wards, _ = await ward_maps(db, ctx.tenant_id)
    bal = await bulk_balances(db, ctx.tenant_id, [p.id for p in props])
    owners = await owner_names(db, [p.id for p in props])
    return page([summary_of(p, wards, owners[p.id], bal[p.id]) for p in props], total, skip, limit)


def party_dict(p: PtxParty, public: bool = False) -> Dict:
    data = {"id": p.id, "role": p.role, "fullName": p.full_name, "sharePercent": float(p.share_percent) if p.share_percent is not None else None,
            "fromDate": p.from_date, "toDate": p.to_date, "isCurrent": p.is_current, "viaApplication": p.via_application}
    if not public:
        data.update({"mobileMasked": mask_mobile(p.mobile_number), "email": p.email,
                     "aadhaarMasked": f"XXXX-XXXX-{p.aadhaar_last4}" if p.aadhaar_last4 else None})
    return data


async def dues_of(db: AsyncSession, prop: PtxProperty) -> Dict:
    bal = await balances(db, prop.tenant_id, prop.id)
    last = await db.scalar(select(PtxDemand).where(PtxDemand.property_id == prop.id).order_by(PtxDemand.period_from.desc()).limit(1))
    return {"upin": prop.upin, "status": prop.status, **dues_summary(bal), "paymentStatus": payment_status(bal),
            "lastDemandNo": last.demand_no if last else None, "lastPeriod": last.period if last else None,
            "lastPeriodLabel": period_label(last.period) if last else None, "lastDueDate": last.due_date if last else None}


def assessment_dict(a: PtxAssessment) -> Dict:
    return {"id": a.id, "assessmentNo": a.assessment_no, "kind": a.kind, "effectiveFrom": a.effective_from, "annualTax": float(a.annual_tax),
            "components": loads(a.components_json, {}), "calculation": loads(a.calculation_json, {}), "status": a.status,
            "noticeNo": a.notice_no, "objectionUntil": a.objection_until, "approvedBy": a.approved_by, "createdAt": a.created_at}


async def property_detail(db: AsyncSession, ctx: PtxContext, prop: PtxProperty, public: bool = False) -> Dict:
    wards, _ = await ward_maps(db, ctx.tenant_id)
    locs = await locality_map(db, ctx.tenant_id)
    bal = await balances(db, ctx.tenant_id, prop.id)
    parties = (await db.execute(select(PtxParty).where(PtxParty.property_id == prop.id).order_by(PtxParty.from_date.desc()))).scalars().all()
    owners = [p for p in parties if p.role == "OWNER" and p.is_current]
    base = summary_of(prop, wards, owners, bal)
    in_force = await db.scalar(select(PtxAssessment).where(PtxAssessment.property_id == prop.id, PtxAssessment.status == "FINAL")
                               .order_by(PtxAssessment.effective_from.desc()).limit(1))
    links = (await db.execute(select(PtxPropertyLink).where(or_(PtxPropertyLink.parent_id == prop.id, PtxPropertyLink.child_id == prop.id)))).scalars().all()
    related = {}
    for link in links:
        other_id = link.child_id if link.parent_id == prop.id else link.parent_id
        other = await db.get(PtxProperty, other_id)
        related.setdefault("children" if link.parent_id == prop.id else "parents", []).append(
            {"upin": other.upin, "kind": link.kind, "status": other.status, "applicationNo": link.application_no})
    loc = locs.get(prop.locality_id or "", {})
    detail = {
        **base, "localityId": prop.locality_id, "localityName": loc.get("name"), "pincode": prop.pincode,
        "siteAreaSqyd": float(prop.site_area_sqyd or 0), "constructionYear": prop.construction_year, "roadClass": prop.road_class,
        "approvedSetbackFt": prop.approved_setback_ft, "measuredSetbackFt": prop.measured_setback_ft, "complexName": prop.complex_name, "unitNo": prop.unit_no, "stateRef": prop.state_ref,
        "exemptionCode": prop.exemption_code, "floors": await current_floors(db, prop.id),
        "owners": [party_dict(p, public) for p in owners],
        "occupiers": [] if public else [party_dict(p) for p in parties if p.role == "OCCUPIER" and p.is_current],
        "assessment": assessment_dict(in_force) if in_force else None, "dues": await dues_of(db, prop),
        "retiredReason": prop.retired_reason, "related": related,
    }
    if not public:
        detail.update({
            "ownerHistory": [party_dict(p) for p in parties if p.role == "OWNER" and not p.is_current],
            "footprintId": prop.footprint_id, "buildingPermissionNo": prop.building_permission_no,
            "occupancyCertificateNo": prop.occupancy_certificate_no, "photos": loads(prop.photos_json, []),
            "documents": loads(prop.documents_json, []), "source": prop.source, "createdAt": prop.created_at,
            "exemptionDocument": prop.exemption_document,
        })
    return detail


@router.get("/properties/{upin}")
async def get_property(upin: str, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    """Property lookup by UPIN (PT-IR-01)."""
    ctx.require("property.view")
    return await property_detail(db, ctx, await load_property(db, ctx, upin=upin))


@router.get("/properties/{upin}/dues")
async def get_dues(upin: str, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    """Dues status (PT-IR-01)."""
    ctx.require("property.view")
    return await dues_of(db, await load_property(db, ctx, upin=upin))


@router.get("/properties/{upin}/no-dues-check")
async def no_dues_check(upin: str, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    """Yes/no answer other modules will use, e.g. before a sanction (PT-IR-01)."""
    ctx.require("property.view")
    prop = await load_property(db, ctx, upin=upin)
    due = dues_total(await balances(db, ctx.tenant_id, prop.id))
    return {"upin": prop.upin, "noDues": due <= 0, "totalDue": float(max(due, Decimal("0"))), "asOf": today()}


@router.get("/lookup/{upin}")
async def module_lookup(upin: str, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    """Compact lookup for other modules: only address, owner, use and location (PT-NF-23, link LOOKUP)."""
    ctx.require("property.view")
    prop = await load_property(db, ctx, upin=upin)
    owners = (await owner_names(db, [prop.id]))[prop.id]
    floors = await current_floors(db, prop.id)
    wards, _ = await ward_maps(db, ctx.tenant_id)
    return {"upin": prop.upin, "status": prop.status, "address": prop.address, "doorNo": prop.door_no,
            "wardNumber": wards.get(prop.ward_id, {}).get("wardNumber"), "latitude": prop.latitude, "longitude": prop.longitude,
            "ownerNames": [o.full_name for o in owners], "uses": sorted({f["usageCode"] for f in floors}) or [prop.property_type]}


@router.get("/properties/{upin}/assessments")
async def list_assessments(upin: str, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("property.view")
    prop = await load_property(db, ctx, upin=upin)
    rows = (await db.execute(select(PtxAssessment).where(PtxAssessment.property_id == prop.id)
                             .order_by(PtxAssessment.effective_from.desc(), PtxAssessment.created_at.desc()))).scalars().all()
    return [assessment_dict(a) for a in rows]


@router.get("/properties/{upin}/demands")
async def list_property_demands(upin: str, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("property.view")
    prop = await load_property(db, ctx, upin=upin)
    rows = (await db.execute(select(PtxDemand).where(PtxDemand.property_id == prop.id).order_by(PtxDemand.period_from.desc()))).scalars().all()
    revisions = dict((await db.execute(select(PtxLedger.demand_id, func.sum(PtxLedger.amount)).where(
        PtxLedger.property_id == prop.id, PtxLedger.txn_type.in_(["DEMAND_REVISION", "ADJUSTMENT"])).group_by(PtxLedger.demand_id))).all())
    return [{"demandNo": d.demand_no, "period": d.period, "periodLabel": period_label(d.period), "dueDate": d.due_date,
             "amount": float(d.amount), "revised": float(money(revisions.get(d.id, 0))), "components": loads(d.components_json, {})} for d in rows]


@router.get("/properties/{upin}/ledger")
async def ledger_statement(upin: str, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("property.view")
    prop = await load_property(db, ctx, upin=upin)
    rows = (await db.execute(select(PtxLedger).where(PtxLedger.property_id == prop.id).order_by(PtxLedger.created_at, PtxLedger.id))).scalars().all()
    running, out = Decimal("0.00"), []
    for r in rows:
        running = money(running + r.amount)
        out.append({"id": r.id, "entryDate": r.entry_date, "txnType": r.txn_type, "component": r.component, "bucket": r.bucket,
                    "accountHead": r.account_head, "amount": float(r.amount), "paymentMode": r.payment_mode, "referenceNo": r.reference_no,
                    "isReversal": r.is_reversal, "narration": r.narration, "netBalance": float(running), "createdBy": r.created_by})
    return out


@router.get("/properties/{upin}/history")
async def change_history(upin: str, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    """Every change: old value, new value, who, when and why (PT-07)."""
    ctx.require("property.view")
    prop = await load_property(db, ctx, upin=upin)
    rows = (await db.execute(select(PtxPropertyHistory).where(PtxPropertyHistory.property_id == prop.id)
                             .order_by(PtxPropertyHistory.changed_at.desc()))).scalars().all()
    return [{"field": r.field, "oldValue": r.old_value, "newValue": r.new_value, "reason": r.reason, "changedBy": r.changed_by,
             "changedAt": r.changed_at} for r in rows]


@router.patch("/properties/{upin}")
async def update_property(upin: str, payload: PropertyUpdate, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """Corrections that do not change tax; every change is kept in history with the reason (PT-07)."""
    ctx.require("property.edit")
    prop = await load_property(db, ctx, upin=upin, for_update=True)
    if prop.status != "ACTIVE":
        raise bad_request(f"This property is {prop.status.lower()} and cannot be changed.")
    changes = payload.model_dump(exclude_unset=True, exclude={"reason", "add_photos", "add_documents"})
    if ("latitude" in changes) != ("longitude" in changes):
        raise bad_request("Send latitude and longitude together.")
    if changes.get("locality_id"):
        loc = await db.get(Locality, changes["locality_id"])
        if loc is None or loc.ward_id != prop.ward_id:
            raise bad_request("The locality chosen is not in this property's ward.")
    if changes.get("footprint_id"):
        fp = await db.get(PtxFootprint, changes["footprint_id"])
        if fp is None or fp.tenant_id != ctx.tenant_id:
            raise bad_request("Map footprint not found.")
        if fp.property_id and fp.property_id != prop.id:
            raise bad_request("That map footprint is already linked to another property.")
        fp.property_id, fp.verification_status = prop.id, "VERIFIED"
    changed = [field for field, value in changes.items() if record_change(db, ctx.username, prop, field, value, payload.reason)]
    for field, new in (("photos_json", payload.add_photos), ("documents_json", payload.add_documents)):
        if new:
            current = loads(getattr(prop, field), [])
            record_change(db, ctx.username, prop, field, dumps(current + new), payload.reason)
            changed.append(field.replace("_json", ""))
    if prop.latitude is not None and prop.location_pending:
        record_change(db, ctx.username, prop, "location_pending", False, payload.reason)
    if not changed:
        raise bad_request("Nothing changed: the values sent are the same as the current record.")
    audit(db, ctx, "PROPERTY_UPDATED", "property", prop.id, None, {"fields": changed, "reason": payload.reason})
    emit_event(db, ctx.tenant_id, "property.changed", prop.id, {"upin": prop.upin, "fields": changed})
    await db.commit()
    return {"message": "Property record updated", "upin": prop.upin, "changedFields": changed}


@router.put("/properties/{upin}/occupiers")
async def update_occupiers(upin: str, payload: OccupierUpdate, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """Occupiers / tenants (PT-03). Changing tenancy that affects tax is done through a reassessment case."""
    ctx.require("property.edit")
    prop = await load_property(db, ctx, upin=upin, for_update=True)
    parties = secure_parties([p.model_dump(by_alias=True) for p in payload.occupiers])
    await set_parties(db, ctx.username, prop, parties, "OCCUPIER", today(), payload.reason)
    audit(db, ctx, "OCCUPIERS_UPDATED", "property", prop.id, None, {"count": len(parties), "reason": payload.reason})
    emit_event(db, ctx.tenant_id, "property.changed", prop.id, {"upin": prop.upin, "fields": ["occupiers"]})
    await db.commit()
    return {"message": "Occupiers updated", "upin": prop.upin}


@router.post("/calculate")
async def calculate_tax(payload: CalculatePreview, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    """Tax calculator with the full calculation sheet, for officers and citizens (PT-10, PT-11, PT-21)."""
    if not (ctx.can("rates.view") or ctx.can("case.create")):
        ctx.require("rates.view")
    details = payload.property.model_dump(by_alias=True)
    floors = [f.model_dump(by_alias=True) for f in payload.floors]
    await validate_details(db, ctx, details, floors, require_location=False)
    effective = await effective_period_start(db, ctx.tenant_id, payload.effective_from)
    result = await calculate(db, ctx.tenant_id, details, floors, effective, payload.rate_table_id)
    return {"annualTax": float(result["annualTax"]), "components": {k: float(v) for k, v in result["components"].items()},
            "calculation": result["sheet"]}


@router.get("/footprints/{footprint_id}")
async def get_footprint(footprint_id: str, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("gis.view")
    fp = await db.get(PtxFootprint, footprint_id)
    if fp is None or fp.tenant_id != ctx.tenant_id:
        raise bad_request("Map footprint not found.")
    prop = await db.get(PtxProperty, fp.property_id) if fp.property_id else None
    floors = (await db.execute(select(func.coalesce(func.sum(PtxFloor.builtup_sqft), 0)).where(
        PtxFloor.property_id == fp.property_id, PtxFloor.is_current.is_(True)))).scalar() if prop else None
    return {"id": fp.id, "footprintRef": fp.footprint_ref, "latitude": fp.latitude, "longitude": fp.longitude,
            "mapBuiltupSqft": float(fp.map_builtup_sqft), "floorsSeen": fp.floors_seen, "verificationStatus": fp.verification_status,
            "upin": prop.upin if prop else None, "recordedBuiltupSqft": float(floors) if floors is not None else None}
