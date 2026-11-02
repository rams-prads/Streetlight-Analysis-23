"""
Assessment and property-change cases (SRS 3.2.2, PT-10..PT-21). Every case type follows the same path:
application (citizen, CSC, counter or staff) -> document check -> field inspection -> tax calculated by the system
-> approval -> assessment notice with an objection period -> record updated and demand raised from the effective date.
Mutation skips the notice: ownership changes on approval once the fee is paid (PT-13, PT-14).
"""
import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ptx_calc import document_code, mask_mobile, money
from app.db.ptx_models import (
    PtxApplication, PtxAssessment, PtxDemand, PtxFootprint, PtxNotice, PtxParty, PtxProperty, PtxPropertyLink, PtxTimeline, utcnow,
)
from app.db.session import get_read_db, get_write_db
from app.schemas.ptx import ApplicationAction, ApplicationCreate, ObjectionIn
from .assess import (
    _post_by_bucket, apply_details, calculate, check_owner_shares, codes, create_property, current_floors, effective_period_start,
    new_assessment, property_details, raise_missing_demands, revise_raised_demands, secure_parties, set_floors, set_parties,
    transfer_balance, validate_details,
)
from .common import (
    ADMIN, DEFAULT_SETTINGS, CITIZEN, COMMISSIONER, PtxAPIRoute, PtxContext, audit, bad_request, balances, conflict, dues_total, dumps, emit_event, get_setting,
    load_property, loads, new_doc_no, not_found, notify, page, paginate, post_ledger, ptx_context, timeline, today, ward_maps,
)

router = APIRouter(route_class=PtxAPIRoute)

SINGLE_PROPERTY_TYPES = {"REASSESSMENT", "USE_CHANGE", "EXEMPTION", "MUTATION", "SUBDIVISION"}
ASSESSMENT_KIND = {"NEW_ASSESSMENT": "NEW", "SELF_ASSESSMENT": "NEW", "REASSESSMENT": "REASSESSMENT", "USE_CHANGE": "USE_CHANGE",
                   "EXEMPTION": "EXEMPTION", "BACK_ASSESSMENT": "BACK_ASSESSMENT"}
TYPE_LABEL = {"NEW_ASSESSMENT": "New assessment", "SELF_ASSESSMENT": "Self-assessment", "REASSESSMENT": "Reassessment",
              "USE_CHANGE": "Change of use", "EXEMPTION": "Exemption / concession", "MUTATION": "Change of ownership (mutation)",
              "SUBDIVISION": "Split into parts (subdivision)", "AMALGAMATION": "Merge properties (amalgamation)",
              "APARTMENT": "Apartment building (units)", "DEMOLITION": "Demolition (close the property)",
              "BACK_ASSESSMENT": "Back-assessment (correct under-assessed years)"}


def _now() -> datetime.datetime:
    return utcnow()


def _fmt(d) -> str:
    if isinstance(d, str):
        d = datetime.datetime.fromisoformat(d)
    return d.strftime("%d-%m-%Y")


def plain_status(app: PtxApplication) -> str:
    """One sentence a citizen can understand: where the case is and what happens next (ease of use)."""
    if app.status == "COMPLETED":
        return "Completed. The property record and tax have been updated."
    if app.status == "REJECTED":
        steps = loads(app.steps_json, [])
        last = next((s for s in steps if s["status"] == "REJECTED"), None)
        return f"Not approved. Reason: {last.get('remark') if last else 'see the remarks'}."
    step = next((s for s in loads(app.steps_json, []) if s["status"] == "CURRENT"), None)
    if step is None:
        return "Being processed."
    if step["code"] == "NOTICE":
        if app.objection_text and not app.objection_decision:
            return "Your objection has been received and is being looked into by the Revenue Officer."
        if app.objection_until and today() <= app.objection_until:
            return (f"Assessment notice {app.notice_no} issued. If you disagree with the tax, you can file an objection "
                    f"until {_fmt(app.objection_until)}. After that the new tax applies.")
        return "Objection period is over. The new tax will be applied shortly."
    due = f" (expected by {_fmt(step['dueAt'])})" if step.get("dueAt") else ""
    return {"DOC_CHECK": "Documents are being checked by the Revenue Inspector",
            "FIELD_INSPECTION": "A Revenue Inspector will visit the property to verify and measure it",
            "APPROVAL": "Waiting for the Revenue Officer's approval"}.get(step["code"], step["label"]) + due + "."


def case_dict(app: PtxApplication, wards: Dict, upin: Optional[str] = None, public: bool = False) -> Dict:
    ward = wards.get(app.ward_id, {}) if app.ward_id else {}
    data = {
        "id": app.id, "applicationNo": app.application_no, "appType": app.app_type, "typeLabel": TYPE_LABEL.get(app.app_type, app.app_type),
        "channel": app.channel, "upin": upin, "applicantName": app.applicant_name, "wardNumber": ward.get("wardNumber"),
        "wardName": ward.get("wardName"), "details": loads(app.details_json, {}), "documents": loads(app.documents_json, []),
        "calculation": loads(app.calculation_json, None),
        "proposedAnnualTax": float(app.proposed_annual_tax) if app.proposed_annual_tax is not None else None,
        "effectiveFrom": app.effective_from, "noticeNo": app.notice_no, "objectionUntil": app.objection_until,
        "objectionText": app.objection_text, "objectionFiledAt": app.objection_filed_at, "objectionDecision": app.objection_decision,
        "result": loads(app.result_json, None), "steps": loads(app.steps_json, []), "currentStep": app.current_step,
        "status": app.status, "statusText": plain_status(app), "escalationLevel": app.escalation_level,
        "createdAt": app.created_at, "completedAt": app.completed_at,
    }
    if not public:
        data.update({"mobileMasked": mask_mobile(app.mobile_number), "createdBy": app.created_by, "startedByStaff": app.started_by_staff})
    else:
        details = data["details"]
        for party_list in ("owners", "occupiers"):
            for p in details.get(party_list, []):
                p.pop("mobileNumber", None), p.pop("aadhaarHash", None), p.pop("email", None)
    return data


def _activate_next(app: PtxApplication, steps: List[Dict]) -> Optional[Dict]:
    for step in steps:
        if step["status"] == "PENDING":
            step["status"] = "CURRENT"
            step["startedAt"] = _now().isoformat()
            step["dueAt"] = (_now() + datetime.timedelta(hours=float(step.get("slaHours", 48)))).isoformat()
            app.current_step = step["code"]
            return step
    app.current_step = None
    return None


async def _owner_mobile(db: AsyncSession, prop_id: Optional[str]) -> Optional[str]:
    if not prop_id:
        return None
    return await db.scalar(select(PtxParty.mobile_number).where(PtxParty.property_id == prop_id, PtxParty.role == "OWNER",
                                                                PtxParty.is_current.is_(True), PtxParty.mobile_number.isnot(None)).limit(1))


async def _tell(db: AsyncSession, app: PtxApplication, template: str, en: str, te: str) -> None:
    mobile = app.mobile_number or await _owner_mobile(db, app.property_id)
    await notify(db, app.tenant_id, recipient=mobile, template=template, property_id=app.property_id, ref_no=app.application_no,
                 message_en=f"GWMC Property Tax: {en}", message_te=f"జీడబ్ల్యూఎంసీ ఆస్తి పన్ను: {te}")


async def _fee_for(db: AsyncSession, tenant_id: str, app_type: str, transfer_reason: Optional[str]) -> Decimal:
    if app_type == "MUTATION":
        return money((await get_setting(db, tenant_id, "mutation"))["feeByReason"].get(transfer_reason or "", 0))
    if app_type in ("SUBDIVISION", "AMALGAMATION"):
        return money((await get_setting(db, tenant_id, app_type.lower())).get("fee", 0))
    return Decimal("0.00")


async def _duplicates(db: AsyncSession, ctx: PtxContext, details: Dict) -> List[Dict]:
    """Existing properties with the same door number in the ward (helps avoid two UPINs for one building)."""
    if not details.get("doorNo"):
        return []
    rows = (await db.execute(select(PtxProperty).where(PtxProperty.tenant_id == ctx.tenant_id, PtxProperty.status == "ACTIVE",
                                                       PtxProperty.ward_id == details.get("wardId"),
                                                       func.lower(PtxProperty.door_no) == details["doorNo"].strip().lower()))).scalars().all()
    return [{"upin": p.upin, "address": p.address} for p in rows]


# ------------------------------------------------------------------------------------------------
# Filing
# ------------------------------------------------------------------------------------------------

@router.post("/cases", status_code=201)
async def file_case(payload: ApplicationCreate, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    ctx.require("case.create")
    if not payload.consent:
        raise bad_request("Please confirm consent to use these personal details for the application (DPDP Act 2023).")
    staff = bool(ctx.roles - {"citizen"})
    t = payload.app_type
    details: Dict = {"reason": payload.reason}
    prop: Optional[PtxProperty] = None
    inputs: List[PtxProperty] = []
    warnings: List[Dict] = []

    if t in ("NEW_ASSESSMENT", "SELF_ASSESSMENT"):
        if payload.property is None:
            raise bad_request("Enter the property details.")
        d = payload.property.model_dump(by_alias=True)
        floors = [f.model_dump(by_alias=True) for f in payload.floors]
        await validate_details(db, ctx, d, floors)
        owners = secure_parties([o.model_dump(by_alias=True) for o in payload.owners])
        check_owner_shares(owners)
        if d.get("footprintId"):
            fp = await db.get(PtxFootprint, d["footprintId"])
            if fp is None or fp.tenant_id != ctx.tenant_id:
                raise bad_request("Map footprint not found.")
            if fp.property_id:
                raise conflict("That building on the map already has a property number.")
        warnings = await _duplicates(db, ctx, d)
        details.update({"property": d, "floors": floors, "owners": owners,
                        "occupiers": secure_parties([o.model_dump(by_alias=True) for o in payload.occupiers]), "warnings": warnings})
        ward_id = d["wardId"]
    elif t == "APARTMENT":
        if payload.property is None:
            raise bad_request("Enter the building details.")
        if len(payload.units) < 2:
            raise bad_request("An apartment building needs at least two units.")
        if not (payload.complex_name or "").strip():
            raise bad_request("Enter the name of the apartment building.")
        d = {**payload.property.model_dump(by_alias=True), "propertyType": "BUILT", "complexName": payload.complex_name.strip()}
        unit_nos = [u.unit_no.strip().upper() for u in payload.units]
        if len(unit_nos) != len(set(unit_nos)):
            raise bad_request("Each unit number can appear only once.")
        units = await _apartment_units(db, ctx, d, payload, [u.model_dump(by_alias=True) for u in payload.units])
        details.update({"building": d, "units": units, "commonAreaSqft": payload.common_area_sqft or 0,
                        "owners": units[0]["owners"], "warnings": await _duplicates(db, ctx, d)})
        ward_id = d["wardId"]
    else:
        if t == "AMALGAMATION":
            if len(set(u.strip().upper() for u in payload.upins)) < 2:
                raise bad_request("Give at least two property numbers (UPINs) to merge.")
            for u in dict.fromkeys(x.strip().upper() for x in payload.upins):
                p = await load_property(db, ctx, upin=u)
                if p.status != "ACTIVE":
                    raise bad_request(f"{p.upin} is {p.status.lower()} and cannot be merged.")
                inputs.append(p)
            if len({p.ward_id for p in inputs}) > 1:
                raise bad_request("Properties in different wards cannot be merged.")
            prop = inputs[0]
        else:
            if not payload.upin:
                raise bad_request("Give the property number (UPIN).")
            prop = await load_property(db, ctx, upin=payload.upin)
            if prop.status != "ACTIVE":
                raise bad_request(f"This property is {prop.status.lower()}.")
        ward_id = prop.ward_id
        base = property_details(prop)
        if t in ("REASSESSMENT", "USE_CHANGE", "EXEMPTION", "BACK_ASSESSMENT"):
            changes = payload.property.model_dump(by_alias=True, exclude_unset=True) if payload.property else {}
            changes.pop("wardId", None)
            d = {**base, **changes}
            floors = [f.model_dump(by_alias=True) for f in payload.floors] or await current_floors(db, prop.id)
            if t == "EXEMPTION":
                if not d.get("exemptionCode"):
                    raise bad_request("Choose the exemption or concession being claimed.")
                if not (d.get("exemptionDocument") or payload.documents):
                    raise bad_request("Attach the supporting document for the exemption (PT-20).")
                if not d.get("exemptionDocument"):
                    d["exemptionDocument"] = payload.documents[0]
            if t == "BACK_ASSESSMENT":
                if not payload.effective_from:
                    raise bad_request("Give the date from which the correct details apply (the year the property was first under-assessed).")
                if len((payload.reason or "").strip()) < 10:
                    raise bad_request("Say why the earlier assessment was wrong (at least a short sentence); the owner is shown this.")
            if t == "USE_CHANGE":
                if not payload.floors:
                    raise bad_request("Show the floors with their new use.")
                if not payload.effective_from:
                    raise bad_request("Give the date from which the use changed.")
            await validate_details(db, ctx, d, floors)
            details.update({"property": d, "floors": floors})
        elif t == "DEMOLITION":
            if not payload.effective_from:
                raise bad_request("Give the date the building was demolished.")
            if not payload.documents:
                raise bad_request("Attach proof of the demolition (demolition permission or certificate, or photos of the cleared site).")
            details.update({"demolishedOn": payload.effective_from.isoformat()})
        elif t == "MUTATION":
            reasons = await codes(db, ctx.tenant_id, "TRANSFER_REASON")
            if payload.transfer_reason not in reasons:
                raise bad_request("Choose why the ownership is changing (sale, gift, inheritance, partition or court order).")
            required = loads(reasons[payload.transfer_reason].extra_json, {}).get("documents", [])
            if payload.channel != "REGISTRATION" and len(payload.documents) < len(required):  # a registered deed already proves the transfer
                raise bad_request("Attach these documents: " + ", ".join(required) + ".")
            owners = secure_parties([o.model_dump(by_alias=True) for o in payload.owners])
            check_owner_shares(owners)
            details.update({"owners": owners, "transfer": {"reason": payload.transfer_reason, "deedNo": payload.transfer_deed_no,
                                                           "date": payload.transfer_date.isoformat() if payload.transfer_date else None,
                                                           "requiredDocuments": required},
                            "previousOwners": [o.full_name for o in (await db.execute(select(PtxParty).where(
                                PtxParty.property_id == prop.id, PtxParty.role == "OWNER", PtxParty.is_current.is_(True)))).scalars().all()]})
        elif t == "SUBDIVISION":
            if len(payload.parts) < 2:
                raise bad_request("A subdivision needs at least two parts.")
            parent_owners = [{"fullName": o.full_name, "mobileNumber": o.mobile_number, "sharePercent": float(o.share_percent) if o.share_percent is not None else None}
                             for o in (await db.execute(select(PtxParty).where(PtxParty.property_id == prop.id, PtxParty.role == "OWNER",
                                                                               PtxParty.is_current.is_(True)))).scalars().all()]
            parts, total_area = [], Decimal("0")
            for i, part in enumerate(payload.parts, start=1):
                pd = {**base, "footprintId": None, **part.property.model_dump(by_alias=True, exclude_unset=True), "wardId": prop.ward_id}
                pf = [f.model_dump(by_alias=True) for f in part.floors]
                await validate_details(db, ctx, pd, pf)
                po = secure_parties([o.model_dump(by_alias=True) for o in part.owners]) or parent_owners
                check_owner_shares(po)
                total_area += Decimal(str(pd.get("siteAreaSqyd") or 0))
                parts.append({"property": pd, "floors": pf, "owners": po})
            if prop.site_area_sqyd and total_area > Decimal(str(prop.site_area_sqyd)) * Decimal("1.01"):
                raise bad_request(f"The parts add up to {total_area} sq yd, more than the property's {prop.site_area_sqyd} sq yd.")
            details.update({"parts": parts})
        elif t == "AMALGAMATION":
            if payload.property is None:
                raise bad_request("Enter the details of the merged property.")
            d = {**base, "footprintId": None, **payload.property.model_dump(by_alias=True, exclude_unset=True), "wardId": prop.ward_id}
            floors = [f.model_dump(by_alias=True) for f in payload.floors]
            await validate_details(db, ctx, d, floors)
            owners = secure_parties([o.model_dump(by_alias=True) for o in payload.owners])
            check_owner_shares(owners)
            details.update({"property": d, "floors": floors, "owners": owners, "inputs": [p.upin for p in inputs]})
        for p in inputs or [prop]:
            open_case = await db.scalar(select(PtxApplication.application_no).where(
                PtxApplication.tenant_id == ctx.tenant_id, PtxApplication.status == "IN_PROGRESS",
                or_(PtxApplication.property_id == p.id, PtxApplication.related_property_ids_json.contains(p.id))))
            if open_case:
                raise conflict(f"Case {open_case} is already in progress for {p.upin}. Please wait for it to finish.")
        if ctx.roles and ctx.roles <= CITIZEN and t != "MUTATION":
            # a citizen changes only their own property: the mobile must be a current owner's (mutation is applied by the buyer)
            for p in inputs or [prop]:
                if not payload.mobile_number or not await db.scalar(select(PtxParty.id).where(
                        PtxParty.property_id == p.id, PtxParty.role == "OWNER", PtxParty.is_current.is_(True),
                        PtxParty.mobile_number == payload.mobile_number)):
                    raise not_found(f"Enter the mobile number registered with {p.upin} to apply for a change to it.")

    if payload.effective_from and payload.effective_from > today():
        raise bad_request("The effective date cannot be in the future.")
    if payload.effective_from:
        years = int((await get_setting(db, ctx.tenant_id, "backAssessment")).get("lookBackYears", 3))
        earliest = _years_back(today(), years)
        if payload.effective_from < earliest:
            raise bad_request(f"A change can reach back only {years} years, to {_fmt(earliest)}. This limit is set by GWMC; "
                              f"for earlier years, ask the Commissioner.")
    effective = await effective_period_start(db, ctx.tenant_id, payload.effective_from)
    workflow = (await get_setting(db, ctx.tenant_id, "workflow")).get(t) or DEFAULT_SETTINGS["workflow"].get(t)
    if not workflow:
        raise bad_request(f"No workflow is configured for {t}.")
    steps = [{**s, "status": "PENDING" if s.get("enabled", True) else "SKIPPED"} for s in workflow]
    app = PtxApplication(
        tenant_id=ctx.tenant_id, sub_tenant_id=ctx.sub_tenant_id, application_no=await new_doc_no(db, ctx.tenant_id, "PTA", "application"),
        app_type=t, property_id=prop.id if prop else None, related_property_ids_json=dumps([p.id for p in inputs]),
        channel=payload.channel, started_by_staff=staff and payload.channel in ("COUNTER", "FIELD"),
        applicant_name=payload.applicant_name or (details.get("owners") or [{}])[0].get("fullName"),
        mobile_number=payload.mobile_number, email=payload.email, consent_recorded=True, ward_id=ward_id,
        details_json=dumps(details), documents_json=dumps(payload.documents), effective_from=effective, created_by=ctx.username,
    )
    db.add(app)
    await db.flush()
    await _recalculate(db, ctx, app)
    _activate_next(app, steps)
    app.steps_json = dumps(steps)
    fee = await _fee_for(db, ctx.tenant_id, t, payload.transfer_reason)
    if fee > 0 and prop is not None:
        component = {"MUTATION": "MUTATION_FEE", "SUBDIVISION": "SUBDIVISION_FEE", "AMALGAMATION": "AMALGAMATION_FEE"}[t]
        await post_ledger(db, ctx, prop=prop, txn_type="FEE", component=component, bucket="FEE", amount=fee, reference_no=app.application_no,
                          narration=f"{TYPE_LABEL[t]} fee for {app.application_no}")
        details["fee"] = float(fee)
        app.details_json = dumps(details)
    timeline(db, ctx, "case", app.id, "FILED", f"{TYPE_LABEL[t]} via {payload.channel}")
    audit(db, ctx, "CASE_FILED", "case", app.id, None, {"applicationNo": app.application_no, "type": t, "upin": prop.upin if prop else None})
    await _tell(db, app, "CASE_FILED", f"application {app.application_no} ({TYPE_LABEL[t]}) received." + (f" Fee Rs {fee} is payable." if fee > 0 else ""),
                f"మీ దరఖాస్తు {app.application_no} స్వీకరించబడింది." + (f" రుసుము రూ. {fee} చెల్లించాలి." if fee > 0 else ""))
    await db.commit()
    wards, _ = await ward_maps(db, ctx.tenant_id)
    return case_dict(app, wards, prop.upin if prop else None)


async def _recalculate(db: AsyncSession, ctx: PtxContext, app: PtxApplication) -> None:
    """Calculation sheet for the case with the rate table in force on the effective date (PT-10, PT-11)."""
    details = loads(app.details_json, {})
    if app.app_type in ("NEW_ASSESSMENT", "SELF_ASSESSMENT", "REASSESSMENT", "USE_CHANGE", "EXEMPTION", "AMALGAMATION", "BACK_ASSESSMENT"):
        calc = await calculate(db, ctx.tenant_id, details["property"], details.get("floors", []), app.effective_from)
        app.calculation_json = dumps(calc["sheet"])
        app.proposed_annual_tax = calc["annualTax"]
    elif app.app_type == "APARTMENT":
        sheets, total = [], Decimal("0")
        for u in details["units"]:
            calc = await calculate(db, ctx.tenant_id, u["property"], u["floors"], app.effective_from)
            sheets.append({**calc["sheet"], "unitNo": u["unitNo"]})
            total += calc["annualTax"]
        app.calculation_json = dumps({"parts": sheets, "annualTax": float(money(total))})
        app.proposed_annual_tax = money(total)
    elif app.app_type == "SUBDIVISION":
        sheets, total = [], Decimal("0")
        for part in details["parts"]:
            calc = await calculate(db, ctx.tenant_id, part["property"], part["floors"], app.effective_from)
            sheets.append(calc["sheet"])
            total += calc["annualTax"]
        app.calculation_json = dumps({"parts": sheets, "annualTax": float(money(total))})
        app.proposed_annual_tax = money(total)


# ------------------------------------------------------------------------------------------------
# Listing and detail
# ------------------------------------------------------------------------------------------------

@router.get("/cases")
async def list_cases(search: Optional[str] = Query(None), status: Optional[str] = Query(None),
                     app_type: Optional[str] = Query(None, alias="appType"), ward_id: Optional[str] = Query(None, alias="wardId"),
                     skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                     ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("case.view")
    stmt = select(PtxApplication, PtxProperty.upin).outerjoin(PtxProperty, PtxProperty.id == PtxApplication.property_id).where(
        PtxApplication.tenant_id == ctx.tenant_id, ctx.ward_filter(PtxApplication.ward_id))
    if status:
        stmt = stmt.where(PtxApplication.status == status.upper())
    if app_type:
        stmt = stmt.where(PtxApplication.app_type == app_type.upper())
    if ward_id:
        stmt = stmt.where(PtxApplication.ward_id == ward_id)
    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(PtxApplication.application_no.ilike(like), PtxApplication.applicant_name.ilike(like), PtxProperty.upin.ilike(like)))
    rows, total = await paginate(db, stmt.order_by(PtxApplication.created_at.desc()), skip, limit)
    wards, _ = await ward_maps(db, ctx.tenant_id)
    return page([case_dict(a, wards, upin) for a, upin in rows], total, skip, limit)


async def load_case(db: AsyncSession, ctx: PtxContext, application_no: str, for_update: bool = False) -> PtxApplication:
    stmt = select(PtxApplication).where(PtxApplication.tenant_id == ctx.tenant_id, PtxApplication.application_no == application_no)
    if for_update:
        stmt = stmt.with_for_update()
    app = await db.scalar(stmt)
    if app is None:
        raise not_found(f"Application {application_no} not found. Check the number on your acknowledgement.")
    return app


async def case_detail(db: AsyncSession, ctx: PtxContext, app: PtxApplication, public: bool = False) -> Dict:
    prop = await db.get(PtxProperty, app.property_id) if app.property_id else None
    wards, _ = await ward_maps(db, ctx.tenant_id)
    data = case_dict(app, wards, prop.upin if prop else None, public)
    events = (await db.execute(select(PtxTimeline).where(PtxTimeline.entity_id == app.id).order_by(PtxTimeline.at))).scalars().all()
    data["timeline"] = [{"action": e.action, "remark": e.remark, "actor": "GWMC staff" if public and e.actor != "citizen" else e.actor, "at": e.at}
                        for e in events]
    if prop is not None:
        data["feeDue"] = float(max((await balances(db, ctx.tenant_id, prop.id))["FEE"], Decimal("0")))
    from .petitions import petitions_for_case  # imported here: petitions builds on this module
    data.update(await petitions_for_case(db, ctx, app, public))
    return data


@router.get("/cases/{application_no}")
async def get_case(application_no: str, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("case.view")
    app = await load_case(db, ctx, application_no)
    ctx.ensure_scope(app.ward_id)
    return await case_detail(db, ctx, app)


# ------------------------------------------------------------------------------------------------
# Workflow actions
# ------------------------------------------------------------------------------------------------

async def _issue_notice(db: AsyncSession, ctx, app: PtxApplication, prop: PtxProperty) -> None:
    """Assessment notice with the time allowed for objections (PT-19)."""
    days = int((await get_setting(db, app.tenant_id, "assessment"))["objectionDays"])
    calc = loads(app.calculation_json, {})
    notice = PtxNotice(tenant_id=app.tenant_id, notice_no=await new_doc_no(db, app.tenant_id, "PAN", "notice"), notice_type="ASSESSMENT",
                       property_id=prop.id, ward_id=prop.ward_id, amount=app.proposed_annual_tax,
                       content_json=dumps({"applicationNo": app.application_no, "type": app.app_type, "typeLabel": TYPE_LABEL[app.app_type],
                                           "effectiveFrom": app.effective_from, "annualTax": float(app.proposed_annual_tax or 0),
                                           "calculation": calc, "objectionDays": days}),
                       verification_code="PENDING", issued_by=ctx.username if isinstance(ctx, PtxContext) else str(ctx))
    db.add(notice)
    await db.flush()
    notice.verification_code = document_code("NOTICE", notice.notice_no, notice.amount or 0)
    app.notice_no = notice.notice_no
    app.objection_until = today() + datetime.timedelta(days=days)
    await _tell(db, app, "ASSESSMENT_NOTICE",
                f"assessment notice {notice.notice_no}: annual tax Rs {app.proposed_annual_tax} from {_fmt(app.effective_from)}. "
                f"Objections accepted until {_fmt(app.objection_until)}.",
                f"అసెస్‌మెంట్ నోటీసు {notice.notice_no}: వార్షిక పన్ను రూ. {app.proposed_annual_tax}. "
                f"అభ్యంతరాలు {_fmt(app.objection_until)} వరకు స్వీకరిస్తాము.")


async def _approve(db: AsyncSession, ctx: PtxContext, app: PtxApplication) -> Optional[str]:
    """Approval effects. Returns 'COMPLETED' when the case finishes at approval (mutation, apartment)."""
    details = loads(app.details_json, {})
    t = app.app_type
    prop = await db.get(PtxProperty, app.property_id) if app.property_id else None
    if t == "APARTMENT":
        return await _approve_apartment(db, ctx, app, details)
    if t == "DEMOLITION":
        return await _approve_demolition(db, ctx, app, prop, details)
    if t == "MUTATION":
        bal = await balances(db, ctx.tenant_id, prop.id)
        if bal["FEE"] > 0:
            raise bad_request(f"The mutation fee of Rs {bal['FEE']} has not been paid yet.")
        rule = await get_setting(db, ctx.tenant_id, "mutation")
        if not rule.get("allowWithDues", False) and dues_total(bal) > 0:
            raise bad_request(f"Property tax dues of Rs {dues_total(bal)} must be paid before the ownership can change (PT-14).")
        reason = f"Mutation {app.application_no} ({details['transfer']['reason'].lower()})"
        await set_parties(db, ctx.username, prop, details["owners"], "OWNER",
                          datetime.date.fromisoformat(details["transfer"]["date"]) if details["transfer"].get("date") else today(),
                          reason, app.application_no)
        emit_event(db, ctx.tenant_id, "mutation.approved", prop.id, {"upin": prop.upin, "applicationNo": app.application_no,
                                                                     "reason": details["transfer"]["reason"],
                                                                     "newOwners": [o["fullName"] for o in details["owners"]]})
        audit(db, ctx, "MUTATION_APPROVED", "property", prop.id, {"owners": details.get("previousOwners")},
              {"owners": [o["fullName"] for o in details["owners"]]})
        app.result_json = dumps({"upin": prop.upin, "newOwners": [o["fullName"] for o in details["owners"]]})
        return "COMPLETED"
    if t == "SUBDIVISION":
        if (await get_setting(db, ctx.tenant_id, "subdivision"))["duesRule"] == "MUST_CLEAR":
            due = dues_total(await balances(db, ctx.tenant_id, prop.id))
            if due > 0:
                raise bad_request(f"Dues of Rs {due} must be cleared before the property can be split.")
    if t == "AMALGAMATION" and (await get_setting(db, ctx.tenant_id, "amalgamation"))["duesRule"] == "CLEAR_FIRST":
        for pid in loads(app.related_property_ids_json, []):
            p = await db.get(PtxProperty, pid)
            due = dues_total(await balances(db, ctx.tenant_id, pid))
            if due > 0:
                raise bad_request(f"Dues of Rs {due} on {p.upin} must be cleared before merging.")
    await _recalculate(db, ctx, app)
    if t in ("NEW_ASSESSMENT", "SELF_ASSESSMENT"):
        prop = await create_property(db, ctx.username, app.tenant_id, app.sub_tenant_id, details["property"], details.get("floors", []),
                                     details["owners"], details.get("occupiers", []), "ASSESSMENT", app.effective_from, app.application_no)
        app.property_id = prop.id
    if t in ASSESSMENT_KIND:
        calc = await calculate(db, ctx.tenant_id, details["property"], details.get("floors", []), app.effective_from)
        await new_assessment(db, ctx.username, prop, ASSESSMENT_KIND[t], calc, app.effective_from, "NOTICE_ISSUED", app.id)
    await _issue_notice(db, ctx, app, prop)
    pending = await db.scalar(select(PtxAssessment).where(PtxAssessment.application_id == app.id, PtxAssessment.status == "NOTICE_ISSUED"))
    if pending is not None:
        pending.notice_no, pending.objection_until = app.notice_no, app.objection_until
    return None


async def finalise_case(db: AsyncSession, actor, app: PtxApplication) -> Dict:
    """After the objection period: update the record and raise demand from the effective date (SRS 3.2.2 last step)."""
    actor_name = actor.username if isinstance(actor, PtxContext) else str(actor)
    tenant = app.tenant_id
    details = loads(app.details_json, {})
    t = app.app_type
    prop = await db.get(PtxProperty, app.property_id) if app.property_id else None
    result: Dict = {}
    if t in ASSESSMENT_KIND:
        pending = await db.scalar(select(PtxAssessment).where(PtxAssessment.application_id == app.id, PtxAssessment.status == "NOTICE_ISSUED")
                                  .order_by(PtxAssessment.created_at.desc()).limit(1))
        if t not in ("NEW_ASSESSMENT", "SELF_ASSESSMENT"):
            reason = f"{TYPE_LABEL[t]} {app.application_no}"
            await apply_details(db, actor_name, prop, {k: v for k, v in details["property"].items() if k != "wardId"}, reason)
            if prop.property_type != "VACANT_LAND":
                await set_floors(db, actor_name, prop, details.get("floors", []), app.effective_from, reason)
        for other in (await db.execute(select(PtxAssessment).where(PtxAssessment.property_id == prop.id, PtxAssessment.status == "FINAL"))).scalars().all():
            other.status = "SUPERSEDED" if other.effective_from < app.effective_from else "REPLACED"
        pending.status, pending.approved_by = "FINAL", actor_name
        await db.flush()
        revised = await revise_raised_demands(db, actor, prop, app.effective_from, f"{TYPE_LABEL[t]} {app.application_no}")
        raised = await raise_missing_demands(db, actor, prop)
        emit_event(db, tenant, "assessment.approved", prop.id, {"upin": prop.upin, "assessmentNo": pending.assessment_no, "kind": pending.kind,
                                                               "annualTax": float(pending.annual_tax), "effectiveFrom": app.effective_from.isoformat()})
        if t not in ("NEW_ASSESSMENT", "SELF_ASSESSMENT"):
            emit_event(db, tenant, "property.changed", prop.id, {"upin": prop.upin, "fields": ["floors", "assessment"]})
        result = {"upin": prop.upin, "assessmentNo": pending.assessment_no, "annualTax": float(pending.annual_tax),
                  "demandsRaised": len(raised), "revisionAmount": float(revised)}
    elif t == "SUBDIVISION":
        latest = await db.scalar(select(func.max(PtxDemand.period_to)).where(PtxDemand.property_id == prop.id))
        start = max(app.effective_from, (latest + datetime.timedelta(days=1)) if latest else app.effective_from)
        children = []
        for part in details["parts"]:
            child = await create_property(db, actor_name, tenant, prop.sub_tenant_id, part["property"], part["floors"], part["owners"], [],
                                          "SUBDIVISION", start, app.application_no)
            calc = await calculate(db, tenant, part["property"], part["floors"], start)
            await new_assessment(db, actor_name, child, "SUBDIVISION", calc, start, "FINAL", app.id)
            db.add(PtxPropertyLink(tenant_id=tenant, parent_id=prop.id, child_id=child.id, kind="SUBDIVISION", application_no=app.application_no))
            children.append((child, Decimal(str(part["property"].get("siteAreaSqyd") or 0))))
        await db.flush()
        if (await get_setting(db, tenant, "subdivision"))["duesRule"] == "SPLIT_BY_AREA":
            total_area = sum((a for _, a in children), Decimal("0"))
            remaining = Decimal("1")
            for i, (child, area) in enumerate(children):
                last = i == len(children) - 1
                share = Decimal("1") if last else (area / total_area if total_area > 0 else Decimal(1) / len(children))
                # each transfer works on what is left, so convert the original share to a share of the remainder
                await transfer_balance(db, actor, prop, child, Decimal("1") if last else (share / remaining),
                                       f"Dues split on subdivision {app.application_no}")
                remaining -= share
        for child, _ in children:
            await raise_missing_demands(db, actor, child)
        record_retire(db, actor_name, prop, "SUBDIVIDED", app.application_no)
        emit_event(db, tenant, "subdivision.approved", prop.id, {"parentUpin": prop.upin, "childUpins": [c.upin for c, _ in children],
                                                                "applicationNo": app.application_no})
        result = {"retiredUpin": prop.upin, "newUpins": [c.upin for c, _ in children]}
    elif t == "AMALGAMATION":
        inputs = [await db.get(PtxProperty, pid) for pid in loads(app.related_property_ids_json, [])]
        latest = await db.scalar(select(func.max(PtxDemand.period_to)).where(PtxDemand.property_id.in_([p.id for p in inputs])))
        start = max(app.effective_from, (latest + datetime.timedelta(days=1)) if latest else app.effective_from)
        merged = await create_property(db, actor_name, tenant, inputs[0].sub_tenant_id, details["property"], details["floors"], details["owners"],
                                       [], "AMALGAMATION", start, app.application_no)
        calc = await calculate(db, tenant, details["property"], details["floors"], start)
        await new_assessment(db, actor_name, merged, "AMALGAMATION", calc, start, "FINAL", app.id)
        for p in inputs:
            db.add(PtxPropertyLink(tenant_id=tenant, parent_id=p.id, child_id=merged.id, kind="AMALGAMATION", application_no=app.application_no))
            if (await get_setting(db, tenant, "amalgamation"))["duesRule"] == "CARRY_FORWARD":
                await transfer_balance(db, actor, p, merged, Decimal("1"), f"Dues carried forward on amalgamation {app.application_no}")
            record_retire(db, actor_name, p, "AMALGAMATED", app.application_no)
        await db.flush()
        await raise_missing_demands(db, actor, merged)
        emit_event(db, tenant, "amalgamation.approved", merged.id, {"newUpin": merged.upin, "retiredUpins": [p.upin for p in inputs],
                                                                    "applicationNo": app.application_no})
        app.property_id = merged.id
        result = {"newUpin": merged.upin, "retiredUpins": [p.upin for p in inputs]}
    app.result_json = dumps(result)
    return result


def _years_back(day: datetime.date, years: int) -> datetime.date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:  # 29 February
        return day.replace(year=day.year - years, day=28)


async def _approve_demolition(db: AsyncSession, ctx: PtxContext, app: PtxApplication, prop: PtxProperty, details: Dict) -> str:
    """
    The building is gone (PT-17): a final nil assessment starts from the billing period of the demolition, bills already
    raised for later periods are reversed (money already paid is kept as advance), and the property number is closed.
    Dues up to that period stay payable and keep being followed up.
    """
    if prop.status != "ACTIVE":
        raise bad_request(f"This property is {prop.status.lower()}.")
    start = app.effective_from
    on = datetime.date.fromisoformat(details["demolishedOn"])
    sheet = {"lines": [{"kind": "DEMOLISHED", "demolishedOn": on.isoformat()}], "annualTax": 0.0, "components": {},
             "effectiveFrom": start.isoformat(), "rateZone": None,
             "steps": [f"The building was demolished on {_fmt(on)}. No property tax is charged from {_fmt(start)}, the start of that billing period."]}
    calc = {"annualTax": Decimal("0.00"), "components": {}, "sheet": sheet, "rateTable": None}
    await new_assessment(db, ctx.username, prop, "DEMOLITION", calc, start, "FINAL", app.id)
    revised = await revise_raised_demands(db, ctx, prop, start, f"Demolition {app.application_no}")
    record_retire(db, ctx.username, prop, "DEMOLISHED", app.application_no)
    emit_event(db, app.tenant_id, "property.changed", prop.id, {"upin": prop.upin, "fields": ["status"]})
    await db.flush()
    due = dues_total(await balances(db, app.tenant_id, prop.id))
    audit(db, ctx, "DEMOLITION_APPROVED", "property", prop.id, {"status": "ACTIVE"}, {"status": "RETIRED", "from": start})
    app.result_json = dumps({"upin": prop.upin, "demolishedOn": on.isoformat(), "taxStopsFrom": start.isoformat(),
                             "revisionAmount": float(revised), "duesRemaining": float(max(due, Decimal("0")))})
    return "COMPLETED"


async def _apartment_units(db: AsyncSession, ctx: PtxContext, building: Dict, payload: ApplicationCreate, raw_units: List[Dict]) -> List[Dict]:
    """
    Works out each unit's own property record (PT-07): its own floor rows, its share of the site area and of the common areas
    (stairs, lift, parking) in proportion to its built-up area, so the tax of every flat can be checked by hand.
    """
    common = Decimal(str(payload.common_area_sqft or 0))
    site = Decimal(str(building.get("siteAreaSqyd") or 0))
    own_area = []
    for u in raw_units:
        for f in u["floors"]:
            if (f.get("portion") or "FULL") in ("COMMON", "ROOFTOP"):
                raise bad_request(f"Unit {u['unitNo']}: list only the unit's own area; the share of common areas is added for you.")
        own_area.append(sum((Decimal(str(f["builtupSqft"])) for f in u["floors"]), Decimal("0")))
    total = sum(own_area, Decimal("0"))
    units = []
    for u, area in zip(raw_units, own_area):
        floors = [dict(f) for f in u["floors"]]
        share = area / total
        await validate_details(db, ctx, {**building, "siteAreaSqyd": float(money(site * share))}, floors)
        if common > 0:
            main = max(floors, key=lambda f: f["builtupSqft"])
            floors.append({"floorNo": main["floorNo"], "usageCode": main["usageCode"], "constructionCode": main["constructionCode"],
                           "builtupSqft": float(money(common * share)), "occupancy": main.get("occupancy", "OWNER"), "portion": "COMMON"})
        unit_no = u["unitNo"].strip()
        prop = {**building, "siteAreaSqyd": float(money(site * share)), "unitNo": unit_no,
                "doorNo": f"{building.get('doorNo') or ''}/{unit_no}".lstrip("/"), "address": f"Unit {unit_no}, {building.get('address') or ''}",
                "footprintId": None}
        owners = secure_parties(u.get("owners") or [])
        check_owner_shares(owners)
        units.append({"unitNo": unit_no, "property": prop, "floors": floors, "owners": owners, "sharePercent": float(money(share * 100))})
    return units


async def _approve_apartment(db: AsyncSession, ctx: PtxContext, app: PtxApplication, details: Dict) -> str:
    """Each unit becomes its own property with its own UPIN, final assessment, bills and assessment notice (PT-07)."""
    await _recalculate(db, ctx, app)
    created = []
    for u in details["units"]:
        unit = await create_property(db, ctx.username, app.tenant_id, app.sub_tenant_id, u["property"], u["floors"], u["owners"], [],
                                     "APARTMENT", app.effective_from, app.application_no)
        calc = await calculate(db, app.tenant_id, u["property"], u["floors"], app.effective_from)
        assessment = await new_assessment(db, ctx.username, unit, "NEW", calc, app.effective_from, "FINAL", app.id)
        days = int((await get_setting(db, app.tenant_id, "assessment"))["objectionDays"])
        notice = PtxNotice(tenant_id=app.tenant_id, notice_no=await new_doc_no(db, app.tenant_id, "PAN", "notice"), notice_type="ASSESSMENT",
                           property_id=unit.id, ward_id=unit.ward_id, amount=calc["annualTax"],
                           content_json=dumps({"applicationNo": app.application_no, "type": app.app_type, "typeLabel": TYPE_LABEL[app.app_type],
                                               "effectiveFrom": app.effective_from, "annualTax": float(calc["annualTax"]), "calculation": calc["sheet"],
                                               "objectionDays": days, "unitNo": u["unitNo"]}),
                           verification_code="PENDING", issued_by=ctx.username)
        db.add(notice)
        await db.flush()
        notice.verification_code = document_code("NOTICE", notice.notice_no, notice.amount or 0)
        assessment.notice_no = notice.notice_no
        emit_event(db, app.tenant_id, "assessment.approved", unit.id, {"upin": unit.upin, "assessmentNo": assessment.assessment_no, "kind": "NEW",
                                                                      "annualTax": float(calc["annualTax"]), "effectiveFrom": app.effective_from.isoformat()})
        created.append(unit)
    await db.flush()
    for unit in created:
        await raise_missing_demands(db, ctx, unit)
    app.property_id = created[0].id
    audit(db, ctx, "APARTMENT_APPROVED", "case", app.id, None, {"complex": details["building"].get("complexName"), "units": [u.upin for u in created]})
    app.result_json = dumps({"newUpins": [u.upin for u in created], "complex": details["building"].get("complexName")})
    return "COMPLETED"


def record_retire(db: AsyncSession, actor: str, prop: PtxProperty, reason: str, application_no: str) -> None:
    """A retired UPIN stays in the register with its history and is never reused (PT-01)."""
    from .assess import record_change
    record_change(db, actor, prop, "status", "RETIRED", f"{reason.title()} by {application_no}")
    record_change(db, actor, prop, "retired_reason", reason, f"{reason.title()} by {application_no}")


def _complete(app: PtxApplication, steps: List[Dict]) -> None:
    for s in steps:
        if s["status"] == "CURRENT":
            s["status"] = "DONE"
    app.status = "COMPLETED"
    app.current_step = None
    app.completed_at = _now()


@router.post("/cases/{application_no}/actions")
async def act_on_case(application_no: str, payload: ApplicationAction, ctx: PtxContext = Depends(ptx_context),
                      db: AsyncSession = Depends(get_write_db)):
    app = await load_case(db, ctx, application_no, for_update=True)
    ctx.ensure_scope(app.ward_id)
    if app.status != "IN_PROGRESS":
        raise bad_request(f"This application is already {app.status.lower()}.")
    steps = loads(app.steps_json, [])
    step = next((s for s in steps if s["status"] == "CURRENT"), None)
    if step is None:
        raise bad_request("This application has no open step.")
    allowed = set(step.get("roles", [])) | ADMIN | (COMMISSIONER if step["code"] == "APPROVAL" else set())
    if not (ctx.roles & allowed):
        raise bad_request(f"'{step['label']}' is done by: {', '.join(sorted(step.get('roles', [])))}.")
    details = loads(app.details_json, {})

    if payload.action == "REJECT":
        if step["code"] == "NOTICE":
            raise bad_request("After the notice is issued, record the objection decision instead of rejecting.")
        step.update({"status": "REJECTED", "doneAt": _now().isoformat(), "doneBy": ctx.username, "remark": payload.remark})
        app.status, app.current_step, app.completed_at = "REJECTED", None, _now()
        app.steps_json = dumps(steps)
        if details.get("fee") and app.property_id:
            prop = await db.get(PtxProperty, app.property_id)
            await _post_by_bucket(db, ctx, prop, "FEE", "FEES", -Decimal(str(details["fee"])), txn_type="ADJUSTMENT", demand_id=None,
                                  reference_no=app.application_no, narration=f"Fee withdrawn: {app.application_no} not approved", entry_date=today())
        timeline(db, ctx, "case", app.id, "REJECTED", payload.remark)
        audit(db, ctx, "CASE_REJECTED", "case", app.id, None, {"step": step["code"], "remark": payload.remark})
        await _tell(db, app, "CASE_REJECTED", f"application {app.application_no} was not approved. Reason: {payload.remark}",
                    f"దరఖాస్తు {app.application_no} ఆమోదించబడలేదు. కారణం: {payload.remark}")
        await db.commit()
        return {"message": "Application rejected", "applicationNo": app.application_no, "status": app.status}

    if payload.action == "DECIDE_OBJECTION":
        if step["code"] != "NOTICE" or not app.objection_text:
            raise bad_request("There is no objection to decide.")
        if app.objection_decision:
            raise bad_request("The objection has already been decided.")
        if payload.objection_upheld is None:
            raise bad_request("Say whether the objection is upheld or rejected.")
        if payload.objection_upheld and (payload.property or payload.floors):
            if payload.property:
                key = "property" if "property" in details else None
                if key:
                    details[key].update({k: v for k, v in payload.property.model_dump(by_alias=True, exclude_unset=True).items() if k != "wardId"})
            if payload.floors is not None and "floors" in details:
                details["floors"] = [f.model_dump(by_alias=True) for f in payload.floors]
            app.details_json = dumps(details)
            await _recalculate(db, ctx, app)
            old = await db.scalar(select(PtxAssessment).where(PtxAssessment.application_id == app.id, PtxAssessment.status == "NOTICE_ISSUED"))
            if old is not None:
                old.status = "REPLACED"
                prop = await db.get(PtxProperty, app.property_id)
                calc = await calculate(db, ctx.tenant_id, details["property"], details.get("floors", []), app.effective_from)
                await new_assessment(db, ctx.username, prop, ASSESSMENT_KIND[app.app_type], calc, app.effective_from, "NOTICE_ISSUED", app.id,
                                     app.notice_no, app.objection_until)
        app.objection_decision = f"{'Upheld' if payload.objection_upheld else 'Rejected'}: {payload.remark}"
        timeline(db, ctx, "case", app.id, "OBJECTION_DECIDED", app.objection_decision)
        audit(db, ctx, "OBJECTION_DECIDED", "case", app.id, None, {"upheld": payload.objection_upheld, "remark": payload.remark})
        await _tell(db, app, "OBJECTION_DECIDED", f"your objection on {app.application_no} was {app.objection_decision}. Annual tax: Rs {app.proposed_annual_tax}.",
                    f"{app.application_no} పై మీ అభ్యంతరం: {app.objection_decision}. వార్షిక పన్ను రూ. {app.proposed_annual_tax}.")
        await db.commit()
        return {"message": "Objection decision recorded", "applicationNo": app.application_no}

    if payload.action == "FINALISE":
        if step["code"] != "NOTICE":
            raise bad_request("Only a case in the notice stage can be finalised.")
        if app.objection_text and not app.objection_decision:
            raise bad_request("An objection is pending. Decide it first.")
        if not app.objection_text and today() <= app.objection_until:
            raise bad_request(f"The owner can still object until {_fmt(app.objection_until)}. Finalise after that date.")
        result = await finalise_case(db, ctx, app)
        step.update({"doneAt": _now().isoformat(), "doneBy": ctx.username, "remark": payload.remark})
        _complete(app, steps)
        app.steps_json = dumps(steps)
        timeline(db, ctx, "case", app.id, "COMPLETED", payload.remark)
        audit(db, ctx, "CASE_FINALISED", "case", app.id, None, result)
        await _tell(db, app, "CASE_COMPLETED", f"application {app.application_no} is complete. {_result_text(result)}",
                    f"దరఖాస్తు {app.application_no} పూర్తయింది.")
        await db.commit()
        return {"message": "Case completed", "applicationNo": app.application_no, "status": app.status, "result": result}

    # COMPLETE_STEP
    if step["code"] == "NOTICE":
        raise bad_request("Use 'Finalise' once the objection period is over.")
    if step["code"] == "FIELD_INSPECTION":
        if payload.property and "property" in details:
            details["property"].update({k: v for k, v in payload.property.model_dump(by_alias=True, exclude_unset=True).items() if k != "wardId"})
        if payload.floors is not None and "floors" in details:
            details["floors"] = [f.model_dump(by_alias=True) for f in payload.floors]
        if "property" in details:
            await validate_details(db, ctx, details["property"], details.get("floors", []))
        details["inspection"] = {"remark": payload.remark, "photos": payload.photo_refs, "latitude": payload.latitude,
                                 "longitude": payload.longitude, "by": ctx.username, "at": _now().isoformat()}
        if payload.latitude is not None and "property" in details and details["property"].get("latitude") is None:
            details["property"]["latitude"], details["property"]["longitude"] = payload.latitude, payload.longitude
        app.details_json = dumps(details)
        await _recalculate(db, ctx, app)
    finished = None
    if step["code"] == "APPROVAL":
        limit = Decimal(str((await get_setting(db, ctx.tenant_id, "assessment"))["commissionerApprovalAboveAnnualTax"]))
        await _recalculate(db, ctx, app)
        if app.proposed_annual_tax is not None and app.proposed_annual_tax > limit and not (ctx.roles & (COMMISSIONER | ADMIN)):
            raise bad_request(f"Annual tax of Rs {app.proposed_annual_tax} is above Rs {limit}: this case needs the Commissioner's approval.")
        if app.app_type == "BACK_ASSESSMENT" and (await get_setting(db, ctx.tenant_id, "backAssessment")).get("commissionerApproval", True) \
                and not (ctx.roles & (COMMISSIONER | ADMIN)):
            raise bad_request("A back-assessment charges earlier years, so the Commissioner approves it.")
        finished = await _approve(db, ctx, app)
    step.update({"status": "DONE", "doneAt": _now().isoformat(), "doneBy": ctx.username, "remark": payload.remark})
    timeline(db, ctx, "case", app.id, f"STEP_DONE:{step['code']}", payload.remark)
    if finished == "COMPLETED":
        _complete(app, steps)
        timeline(db, ctx, "case", app.id, "COMPLETED", None)
        await _tell(db, app, "CASE_COMPLETED", f"application {app.application_no} is approved. {_result_text(loads(app.result_json, {}))}",
                    f"దరఖాస్తు {app.application_no} ఆమోదించబడింది.")
    else:
        nxt = _activate_next(app, steps)
        if nxt and nxt["code"] == "NOTICE" and app.objection_until:
            nxt["dueAt"] = datetime.datetime.combine(app.objection_until, datetime.time(23, 59)).isoformat()
        if nxt is not None and nxt["code"] != "NOTICE":
            await _tell(db, app, "CASE_PROGRESS", f"application {app.application_no}: {nxt['label']} is next.",
                        f"దరఖాస్తు {app.application_no}: తదుపరి దశ - {nxt['label']}.")
    app.steps_json = dumps(steps)
    audit(db, ctx, "CASE_STEP", "case", app.id, None, {"step": step["code"], "remark": payload.remark})
    await db.commit()
    prop = await db.get(PtxProperty, app.property_id) if app.property_id else None
    return {"message": "Step completed", "applicationNo": app.application_no, "status": app.status, "currentStep": app.current_step,
            "upin": prop.upin if prop else None, "noticeNo": app.notice_no}


def _result_text(result: Dict) -> str:
    if result.get("demolishedOn"):
        return f"{result['upin']} is closed: demolished. No tax from {_fmt(result['taxStopsFrom'])}."
    if result.get("newUpins"):
        return "New property numbers: " + ", ".join(result["newUpins"]) + "."
    if result.get("newUpin"):
        return f"New property number: {result['newUpin']}."
    if result.get("annualTax") is not None:
        return f"Property {result.get('upin')}: annual tax Rs {result['annualTax']}."
    if result.get("newOwners"):
        return "Owner(s) now: " + ", ".join(result["newOwners"]) + "."
    return ""


async def file_objection(db: AsyncSession, ctx: PtxContext, app: PtxApplication, text: str, actor_label: str) -> None:
    steps = loads(app.steps_json, [])
    step = next((s for s in steps if s["status"] == "CURRENT"), None)
    if app.status != "IN_PROGRESS" or step is None or step["code"] != "NOTICE":
        raise bad_request("Objections can be filed only after the assessment notice is issued and before the case is finalised.")
    if today() > app.objection_until:
        raise bad_request(f"The objection period ended on {_fmt(app.objection_until)}.")
    if app.objection_text:
        raise conflict("An objection has already been filed on this case.")
    app.objection_text = text
    app.objection_filed_at = _now()
    timeline(db, ctx, "case", app.id, "OBJECTION_FILED", text, actor=actor_label)
    audit(db, ctx, "OBJECTION_FILED", "case", app.id, None, {"text": text})
    await _tell(db, app, "OBJECTION_FILED", f"objection on {app.application_no} received. The Revenue Officer will decide it.",
                f"{app.application_no} పై మీ అభ్యంతరం అందింది.")


@router.post("/cases/{application_no}/objection")
async def staff_objection(application_no: str, payload: ObjectionIn, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """Objection recorded at a counter or CSC on the owner's behalf (PT-19)."""
    ctx.require("case.create")
    app = await load_case(db, ctx, application_no, for_update=True)
    ctx.ensure_scope(app.ward_id)
    await file_objection(db, ctx, app, payload.text, ctx.username)
    await db.commit()
    return {"message": "Objection recorded", "applicationNo": app.application_no}


async def run_auto_finalise(db: AsyncSession, actor: str, tenant_id: str) -> List[str]:
    """Daily job: cases whose objection period ended with no objection are finalised (PT-19)."""
    done = []
    rows = (await db.execute(select(PtxApplication).where(PtxApplication.tenant_id == tenant_id, PtxApplication.status == "IN_PROGRESS",
                                                          PtxApplication.current_step == "NOTICE", PtxApplication.objection_text.is_(None),
                                                          PtxApplication.objection_until < today()))).scalars().all()
    for app in rows:
        steps = loads(app.steps_json, [])
        await finalise_case(db, actor, app)
        for s in steps:
            if s["status"] == "CURRENT":
                s.update({"doneAt": _now().isoformat(), "doneBy": actor, "remark": "Objection period over, no objection"})
        _complete(app, steps)
        app.steps_json = dumps(steps)
        timeline(db, tenant_id, "case", app.id, "COMPLETED", "Objection period over, no objection", actor=actor)
        done.append(app.application_no)
    return done


async def escalate_cases(db: AsyncSession, tenant_id: str) -> int:
    """Steps past their SLA move up the escalation chain (PT-18)."""
    chain = await get_setting(db, tenant_id, "escalation")
    now, count = _now(), 0
    for app in (await db.execute(select(PtxApplication).where(PtxApplication.tenant_id == tenant_id, PtxApplication.status == "IN_PROGRESS"))).scalars().all():
        steps = loads(app.steps_json, [])
        step = next((s for s in steps if s["status"] == "CURRENT"), None)
        if not step or not step.get("dueAt") or step["code"] == "NOTICE":
            continue
        level_due = datetime.datetime.fromisoformat(step["dueAt"]) + datetime.timedelta(hours=float(step.get("slaHours", 48)) * app.escalation_level)
        if now > level_due and app.escalation_level < len(chain):
            target = chain[app.escalation_level]
            app.escalation_level += 1
            step["escalatedTo"] = target
            app.steps_json = dumps(steps)
            timeline(db, tenant_id, "case", app.id, "ESCALATED", f"'{step['label']}' past its time limit; escalated to {target}", actor="system")
            await notify(db, tenant_id, recipient=target, channel="EMAIL", template="SLA_ESCALATION", ref_no=app.application_no,
                         dedupe_key=f"case-esc:{app.id}:{app.escalation_level}",
                         message_en=f"Case {app.application_no}: '{step['label']}' is past its time limit.",
                         message_te=f"కేసు {app.application_no}: '{step['label']}' గడువు దాటింది.")
            count += 1
    return count


@router.get("/cases-summary/pending")
async def pending_summary(ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    """Counts of open cases by step, for work queues."""
    ctx.require("case.view")
    rows = (await db.execute(select(PtxApplication.current_step, func.count()).where(
        PtxApplication.tenant_id == ctx.tenant_id, PtxApplication.status == "IN_PROGRESS", ctx.ward_filter(PtxApplication.ward_id))
        .group_by(PtxApplication.current_step))).all()
    return {step or "NONE": n for step, n in rows}
