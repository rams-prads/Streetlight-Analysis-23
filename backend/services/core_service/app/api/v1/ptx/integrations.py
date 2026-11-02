"""
Connections to systems outside Module 1 (SRS 3.7). The real systems are not connected in Release 1, so each link works today
as a stand-in that takes exactly the data the real system will send:

  REGISTRATION    registered deeds from the Registration Department start a change of owner (PT-14)
  STATE_PLATFORM  property records exchanged with the state platform (PT-02)
  BBPS            bill fetch and payment confirmation for any BBPS app (PT-21)

Each link works only while it is switched on in the settings. Switching is a configuration change, with a reason on record.
"""
import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ptx_calc import mask_mobile, period_label
from app.db.ptx_models import PtxAssessment, PtxDeedIntake, PtxDemand, PtxFloor, PtxParty, PtxProperty, PtxReceipt, PtxSetting, PtxSyncRun, utcnow
from app.db.session import get_read_db, get_write_db
from app.schemas.ptx import ApplicationCreate, BbpsFetch, BbpsPay, DeedAction, DeedBatch, DeedIn, LinkToggle, StateImport
from .assess import record_change
from .cases import file_case
from .common import (
    PtxAPIRoute, PtxContext, audit, bad_request, balances, conflict, dues_summary, dumps, get_links, loads, local_day_start_utc, new_doc_no,
    not_found, page, paginate, ptx_context, require_link, today, ward_maps,
)
from .payments import take_payment

router = APIRouter(route_class=PtxAPIRoute)

DEED_TYPE_TO_REASON = {"SALE": "SALE", "GIFT": "GIFT", "SETTLEMENT": "GIFT", "PARTITION": "PARTITION", "RELEASE": "PARTITION", "WILL": "INHERITANCE",
                       "SUCCESSION": "INHERITANCE", "COURT_ORDER": "COURT_ORDER"}
TITLES = {"mr", "mrs", "ms", "smt", "sri", "shri", "late", "dr", "kum", "m", "s", "sk"}


# ------------------------------------------------------------------------------------------------
# Link switches
# ------------------------------------------------------------------------------------------------

@router.post("/integration/links/{link}/toggle")
async def toggle_link(link: str, payload: LinkToggle, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """Switches a link on or off from today. The old value stays in the settings history with who changed it and why (PT-IR-06)."""
    ctx.require("settings.manage")
    links = await get_links(db, ctx.tenant_id)
    if link not in links:
        raise not_found(f"There is no link called {link}.")
    old = bool(links[link].get("enabled"))
    links[link]["enabled"] = payload.enabled
    row = PtxSetting(tenant_id=ctx.tenant_id, key="integrationLinks", value_json=dumps(links), effective_from=today(), reason=payload.reason, created_by=ctx.username)
    db.add(row)
    audit(db, ctx, "LINK_SWITCHED", "setting", row.id, {"link": link, "enabled": old}, {"link": link, "enabled": payload.enabled, "reason": payload.reason})
    await db.commit()
    return {"message": f"{links[link]['module']} is now {'on' if payload.enabled else 'off'}.", "link": link, "enabled": payload.enabled}


# ------------------------------------------------------------------------------------------------
# Registered deeds start a mutation (PT-14)
# ------------------------------------------------------------------------------------------------

def _tokens(name: str) -> set:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in name or "")
    return {t for t in cleaned.split() if len(t) > 1 and t not in TITLES}


def _names_match(sellers: List[str], owners: List[str]) -> bool:
    """A seller matches an owner when at least half of the shorter name's words appear in the other (initials and titles are ignored)."""
    for s in sellers:
        ts = _tokens(s)
        for o in owners:
            to = _tokens(o)
            if ts and to and len(ts & to) / min(len(ts), len(to)) >= 0.5:
                return True
    return False


def deed_dict(i: PtxDeedIntake, upin: Optional[str] = None) -> Dict:
    p = loads(i.payload_json, {})
    return {"id": i.id, "deedNo": i.deed_no, "registrationOffice": i.registration_office, "deedDate": i.deed_date, "deedType": i.deed_type,
            "sellers": p.get("sellers", []), "buyers": [b.get("fullName") for b in p.get("buyers", [])], "considerationAmount": p.get("considerationAmount"),
            "reference": {k: p.get(k) for k in ("upin", "oldAssessmentNo", "wardNumber", "doorNo")}, "status": i.status, "message": i.message, "upin": upin,
            "applicationNo": i.application_no, "receivedBy": i.received_by, "receivedAt": i.received_at, "handledBy": i.handled_by, "handledAt": i.handled_at}


async def _find_property(db: AsyncSession, ctx: PtxContext, deed: DeedIn, forced_upin: Optional[str]) -> Optional[PtxProperty]:
    base = select(PtxProperty).where(PtxProperty.tenant_id == ctx.tenant_id)
    if forced_upin:
        return await db.scalar(base.where(PtxProperty.upin == forced_upin.strip().upper()))
    if deed.upin:
        found = await db.scalar(base.where(PtxProperty.upin == deed.upin.strip().upper()))
        if found:
            return found
    if deed.old_assessment_no:
        found = await db.scalar(base.where(PtxProperty.old_assessment_no == deed.old_assessment_no.strip()))
        if found:
            return found
    if deed.ward_number is not None and deed.door_no:
        wards, _ = await ward_maps(db, ctx.tenant_id)
        ids = [w["wardId"] for w in wards.values() if w["wardNumber"] == deed.ward_number]
        rows = (await db.execute(base.where(PtxProperty.ward_id.in_(ids), PtxProperty.door_no == deed.door_no.strip(), PtxProperty.status == "ACTIVE"))).scalars().all()
        if len(rows) == 1:
            return rows[0]
    return None


async def _decide(db: AsyncSession, ctx: PtxContext, deed: DeedIn, forced_upin: Optional[str]):
    """Matches the deed to a property and opens the mutation case, or says why an officer must look at it. Returns (status, message, property id, application no)."""
    prop = await _find_property(db, ctx, deed, forced_upin)
    if prop is None:
        return "NO_MATCH", "No property matched the number or door number given in the deed. An officer can pick the property and open the mutation by hand.", None, None
    prop_id = prop.id
    if prop.status != "ACTIVE":
        return "REVIEW", f"{prop.upin} is {prop.status.lower()}. The mutation belongs on the property that replaced it.", prop_id, None
    reason = DEED_TYPE_TO_REASON.get(deed.deed_type.strip().upper())
    if reason is None:
        return "REVIEW", f"'{deed.deed_type}' is not a kind of transfer handled automatically. An officer should decide how to treat it.", prop_id, None
    owners = (await db.execute(select(PtxParty.full_name).where(PtxParty.property_id == prop.id, PtxParty.role == "OWNER", PtxParty.is_current.is_(True)))).scalars().all()
    if not forced_upin and not _names_match(deed.sellers, list(owners)):
        return ("REVIEW", f"The seller(s) in the deed ({', '.join(deed.sellers)}) do not match the owner(s) on record ({', '.join(owners)}). "
                          "An officer should check the deed, and can then open the mutation by hand.", prop_id, None)
    request = ApplicationCreate(app_type="MUTATION", channel="REGISTRATION", upin=prop.upin, consent=True, applicant_name=deed.buyers[0].full_name,
                                mobile_number=deed.buyers[0].mobile_number, transfer_reason=reason,
                                transfer_deed_no=f"{deed.deed_no} ({deed.registration_office})", transfer_date=deed.deed_date, owners=deed.buyers,
                                reason=f"Registered deed {deed.deed_no} at {deed.registration_office} on {deed.deed_date.strftime('%d-%m-%Y')}")
    try:
        case = await file_case(request, ctx, db)
    except HTTPException as exc:
        await db.rollback()  # nothing of the failed case may stay in this session
        return "REVIEW", str(exc.detail), prop_id, None
    return "CASE_OPENED", f"Mutation {case['applicationNo']} opened from the registered deed. The inspector checks the deed copy and the officer approves.", prop_id, case["applicationNo"]


async def _process(db: AsyncSession, ctx: PtxContext, intake_id: str, deed: DeedIn, forced_upin: Optional[str] = None, handler: Optional[str] = None) -> PtxDeedIntake:
    status, message, prop_id, app_no = await _decide(db, ctx, deed, forced_upin)
    intake = await db.get(PtxDeedIntake, intake_id)
    intake.status, intake.message, intake.property_id, intake.application_no = status, message, prop_id, app_no
    if handler:
        intake.handled_by, intake.handled_at = handler, utcnow()
    audit(db, ctx, "DEED_PROCESSED", "deed", intake.id, None, {"deedNo": intake.deed_no, "status": status, "applicationNo": app_no})
    await db.commit()
    return intake


@router.post("/integration/registration/deeds", status_code=201)
async def receive_deeds(payload: DeedBatch, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """What the Registration Department sends for each registered deed. Each deed is stored once; repeats are ignored (PT-14)."""
    ctx.require("integration.run")
    await require_link(db, ctx.tenant_id, "REGISTRATION")
    results = []
    for deed in payload.deeds:
        if deed.deed_date > today():
            results.append({"deedNo": deed.deed_no, "result": "ERROR", "error": "The deed date is in the future."})
            continue
        existing = await db.scalar(select(PtxDeedIntake).where(PtxDeedIntake.tenant_id == ctx.tenant_id, PtxDeedIntake.registration_office == deed.registration_office,
                                                               PtxDeedIntake.deed_no == deed.deed_no))
        if existing is not None:
            results.append({"deedNo": deed.deed_no, "result": "DUPLICATE_IGNORED", "status": existing.status, "applicationNo": existing.application_no})
            continue
        intake = PtxDeedIntake(tenant_id=ctx.tenant_id, deed_no=deed.deed_no, registration_office=deed.registration_office, deed_date=deed.deed_date,
                               deed_type=deed.deed_type.strip().upper(), payload_json=dumps(deed.model_dump(mode="json", by_alias=True)), received_by=ctx.username)
        db.add(intake)
        await db.commit()
        done = await _process(db, ctx, intake.id, deed)
        results.append({"deedNo": deed.deed_no, "result": "RECEIVED", "status": done.status, "message": done.message, "applicationNo": done.application_no})
    return {"received": sum(1 for r in results if r["result"] == "RECEIVED"), "duplicates": sum(1 for r in results if r["result"] == "DUPLICATE_IGNORED"),
            "errors": sum(1 for r in results if r["result"] == "ERROR"), "results": results}


@router.get("/integration/registration/deeds")
async def list_deeds(search: Optional[str] = Query(None), status: Optional[str] = Query(None), skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                     ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("integration.run")
    stmt = select(PtxDeedIntake, PtxProperty.upin).outerjoin(PtxProperty, PtxProperty.id == PtxDeedIntake.property_id).where(PtxDeedIntake.tenant_id == ctx.tenant_id)
    if status == "TO_REVIEW":
        stmt = stmt.where(PtxDeedIntake.status.in_(["REVIEW", "NO_MATCH"]))
    elif status:
        stmt = stmt.where(PtxDeedIntake.status == status.upper())
    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(PtxDeedIntake.deed_no.ilike(like), PtxDeedIntake.registration_office.ilike(like), PtxProperty.upin.ilike(like), PtxDeedIntake.payload_json.ilike(like)))
    rows, total = await paginate(db, stmt.order_by(PtxDeedIntake.received_at.desc()), skip, limit)
    return page([deed_dict(i, upin) for i, upin in rows], total, skip, limit)


async def _open_intake(db: AsyncSession, ctx: PtxContext, intake_id: str) -> PtxDeedIntake:
    i = await db.scalar(select(PtxDeedIntake).where(PtxDeedIntake.tenant_id == ctx.tenant_id, PtxDeedIntake.id == intake_id).with_for_update())
    if i is None:
        raise not_found("Deed not found.")
    if i.status not in ("REVIEW", "NO_MATCH"):
        raise conflict(f"This deed is already {i.status.replace('_', ' ').lower()}.")
    return i


@router.post("/integration/registration/deeds/{intake_id}/open-case")
async def open_case_from_deed(intake_id: str, payload: DeedAction, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """After checking the deed, the officer opens the mutation by hand, naming the property if the feed could not match it."""
    ctx.require("integration.run")
    i = await _open_intake(db, ctx, intake_id)
    deed = DeedIn.model_validate(loads(i.payload_json, {}))
    forced = payload.upin
    if not forced and i.property_id:
        forced = (await db.get(PtxProperty, i.property_id)).upin
    if not forced:
        raise bad_request("Choose the property this deed is about.")
    done = await _process(db, ctx, i.id, deed, forced_upin=forced, handler=ctx.username)
    if done.status != "CASE_OPENED":
        raise bad_request(done.message or "The mutation could not be opened.")
    return {"message": done.message, "applicationNo": done.application_no}


@router.post("/integration/registration/deeds/{intake_id}/dismiss")
async def dismiss_deed(intake_id: str, payload: DeedAction, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    ctx.require("integration.run")
    i = await _open_intake(db, ctx, intake_id)
    i.status, i.handled_by, i.handled_at = "DISMISSED", ctx.username, utcnow()
    i.message = f"{(i.message or '').strip()} | Dismissed: {payload.remark}".strip(" |")
    audit(db, ctx, "DEED_DISMISSED", "deed", i.id, {"status": "REVIEW"}, {"status": "DISMISSED", "remark": payload.remark})
    await db.commit()
    return {"message": "Deed dismissed", "id": i.id}


# ------------------------------------------------------------------------------------------------
# State property platform (PT-02)
# ------------------------------------------------------------------------------------------------

@router.get("/integration/state/export")
async def state_export(since: Optional[datetime.date] = Query(None), skip: int = Query(0, ge=0), limit: int = Query(200, ge=1, le=500),
                       ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """The register in the shape sent to the state platform: no mobile numbers or identity details, only what the platform needs to match records."""
    ctx.require("integration.run")
    await require_link(db, ctx.tenant_id, "STATE_PLATFORM")
    stmt = select(PtxProperty).where(PtxProperty.tenant_id == ctx.tenant_id, PtxProperty.status == "ACTIVE", ctx.ward_filter(PtxProperty.ward_id))
    if since:
        stmt = stmt.where(PtxProperty.updated_at >= local_day_start_utc(since))
    rows, total = await paginate(db, stmt.order_by(PtxProperty.upin), skip, limit)
    props = [r[0] for r in rows]
    ids = [p.id for p in props] or ["__none__"]
    owners: Dict[str, List[str]] = {}
    for party in (await db.execute(select(PtxParty).where(PtxParty.property_id.in_(ids), PtxParty.role == "OWNER", PtxParty.is_current.is_(True)))).scalars().all():
        owners.setdefault(party.property_id, []).append(party.full_name)
    uses: Dict[str, set] = {}
    for f in (await db.execute(select(PtxFloor).where(PtxFloor.property_id.in_(ids), PtxFloor.is_current.is_(True)))).scalars().all():
        uses.setdefault(f.property_id, set()).add(f.usage_code)
    tax = {a.property_id: float(a.annual_tax) for a in (await db.execute(select(PtxAssessment).where(PtxAssessment.property_id.in_(ids), PtxAssessment.status == "FINAL"))).scalars().all()}
    wards, _ = await ward_maps(db, ctx.tenant_id)
    records = [{"upin": p.upin, "stateRef": p.state_ref, "oldAssessmentNo": p.old_assessment_no, "doorNo": p.door_no, "address": p.address, "pincode": p.pincode,
                "wardNumber": wards.get(p.ward_id, {}).get("wardNumber"), "latitude": p.latitude, "longitude": p.longitude, "ownerNames": owners.get(p.id, []),
                "uses": sorted(uses.get(p.id, set())) or [p.property_type], "siteAreaSqyd": float(p.site_area_sqyd or 0), "annualTax": tax.get(p.id)} for p in props]
    run = PtxSyncRun(tenant_id=ctx.tenant_id, run_no=await new_doc_no(db, ctx.tenant_id, "PSY", "syncrun"), direction="PUSH", records=len(records),
                     matched=len(records), started_by=ctx.username, results_json=dumps({"since": since, "skip": skip, "total": total}))
    db.add(run)
    audit(db, ctx, "STATE_EXPORT", "sync_run", run.id, None, {"runNo": run.run_no, "records": len(records)})
    await db.commit()
    return {"format": "urban.ptx.state-sync.v1", "runNo": run.run_no, "generatedAt": utcnow(), "total": total, "skip": skip, "limit": limit, "records": records}


@router.post("/integration/state/import")
async def state_import(payload: StateImport, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """
    Records from the state platform: each is matched to a property by UPIN, old assessment number or its state reference, then the
    platform's id is stored and address corrections applied. Tax, owners and area are never changed from outside (PT-02).
    """
    ctx.require("integration.run")
    await require_link(db, ctx.tenant_id, "STATE_PLATFORM")
    run_no = await new_doc_no(db, ctx.tenant_id, "PSY", "syncrun")
    reason = f"State platform sync {run_no}"
    results, matched, updated, unmatched, errors = [], 0, 0, 0, 0
    for rec in payload.records:
        prop = None
        base = select(PtxProperty).where(PtxProperty.tenant_id == ctx.tenant_id)
        if rec.upin:
            prop = await db.scalar(base.where(PtxProperty.upin == rec.upin.strip().upper()))
        if prop is None and rec.old_assessment_no:
            prop = await db.scalar(base.where(PtxProperty.old_assessment_no == rec.old_assessment_no.strip()))
        if prop is None:
            prop = await db.scalar(base.where(PtxProperty.state_ref == rec.state_ref))
        if prop is None:
            unmatched += 1
            results.append({"stateRef": rec.state_ref, "result": "UNMATCHED"})
            continue
        matched += 1
        if prop.status != "ACTIVE" or not ctx.in_scope(prop.ward_id):
            errors += 1
            results.append({"stateRef": rec.state_ref, "upin": prop.upin, "result": "ERROR", "error": "The property is closed or outside your area."})
            continue
        if (rec.latitude is None) != (rec.longitude is None):
            errors += 1
            results.append({"stateRef": rec.state_ref, "upin": prop.upin, "result": "ERROR", "error": "Latitude and longitude must come together."})
            continue
        await db.flush()  # earlier records in this batch count when checking for a clash
        clash = await db.scalar(select(PtxProperty.upin).where(PtxProperty.tenant_id == ctx.tenant_id, PtxProperty.state_ref == rec.state_ref, PtxProperty.id != prop.id))
        if clash:
            errors += 1
            results.append({"stateRef": rec.state_ref, "upin": prop.upin, "result": "ERROR", "error": f"That state reference already belongs to {clash}."})
            continue
        fields = []
        for column, value in (("state_ref", rec.state_ref), ("door_no", rec.door_no), ("address", rec.address), ("pincode", rec.pincode),
                              ("latitude", rec.latitude), ("longitude", rec.longitude)):
            if value not in (None, "") and record_change(db, ctx.username, prop, column, value, reason):
                fields.append(column)
        if rec.latitude is not None and prop.location_pending:
            record_change(db, ctx.username, prop, "location_pending", False, reason)
        if fields:
            updated += 1
        results.append({"stateRef": rec.state_ref, "upin": prop.upin, "result": "UPDATED" if fields else "UNCHANGED", "fields": fields})
    db.add(PtxSyncRun(tenant_id=ctx.tenant_id, run_no=run_no, direction="PULL", records=len(payload.records), matched=matched, updated=updated, unmatched=unmatched,
                      errors=errors, results_json=dumps(results[:300]), started_by=ctx.username))
    audit(db, ctx, "STATE_IMPORT", "sync_run", None, None, {"runNo": run_no, "records": len(payload.records), "updated": updated, "unmatched": unmatched, "errors": errors})
    await db.commit()
    return {"runNo": run_no, "records": len(payload.records), "matched": matched, "updated": updated, "unmatched": unmatched, "errors": errors, "results": results}


@router.get("/integration/state/runs")
async def state_runs(skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("integration.run")
    rows, total = await paginate(db, select(PtxSyncRun).where(PtxSyncRun.tenant_id == ctx.tenant_id).order_by(PtxSyncRun.started_at.desc()), skip, limit)
    return page([{"id": r.id, "runNo": r.run_no, "direction": r.direction, "records": r.records, "matched": r.matched, "updated": r.updated, "unmatched": r.unmatched,
                  "errors": r.errors, "startedBy": r.started_by, "startedAt": r.started_at, "results": loads(r.results_json, [])} for (r,) in rows], total, skip, limit)


# ------------------------------------------------------------------------------------------------
# BBPS (PT-21): bill fetch and payment confirmation
# ------------------------------------------------------------------------------------------------

def _first_name_mask(name: str) -> str:
    parts = (name or "").split()
    return " ".join([parts[0][:1] + "*" * max(len(parts[0]) - 1, 2)] + [p[:1] + "." for p in parts[1:]]) if parts else "Owner"


async def _bbps_property(db: AsyncSession, ctx: PtxContext, upin: Optional[str], old_no: Optional[str]) -> Optional[PtxProperty]:
    base = select(PtxProperty).where(PtxProperty.tenant_id == ctx.tenant_id)
    if upin:
        return await db.scalar(base.where(PtxProperty.upin == upin.strip().upper()))
    if old_no:
        return await db.scalar(base.where(PtxProperty.old_assessment_no == old_no.strip()))
    return None


@router.post("/integration/bbps/fetch")
async def bbps_fetch(payload: BbpsFetch, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    """Bill fetch: the customer types the property number in any BBPS app, the app asks us what is due."""
    ctx.require("integration.run")
    await require_link(db, ctx.tenant_id, "BBPS")
    prop = await _bbps_property(db, ctx, payload.upin, payload.old_assessment_no)
    if prop is None:
        return {"requestId": payload.request_id, "status": "BILL_NOT_FOUND", "message": "No property found with that number. Check the number on your tax bill."}
    dues = dues_summary(await balances(db, ctx.tenant_id, prop.id))
    if dues["netPayable"] <= 0:
        return {"requestId": payload.request_id, "status": "NO_DUES", "message": "Nothing is due on this property."}
    latest = await db.scalar(select(PtxDemand).where(PtxDemand.property_id == prop.id).order_by(PtxDemand.period_from.desc()).limit(1))
    owner = await db.scalar(select(PtxParty.full_name).where(PtxParty.property_id == prop.id, PtxParty.role == "OWNER", PtxParty.is_current.is_(True)).limit(1))
    return {"requestId": payload.request_id, "status": "OK", "billerResponse": {
        "upin": prop.upin, "customerName": _first_name_mask(owner or ""), "billNumber": latest.demand_no if latest else None,
        "billPeriod": period_label(latest.period) if latest else None, "billDate": latest.created_at.date() if latest else None,
        "dueDate": latest.due_date if latest else None, "amount": dues["netPayable"],
        "amountBreakup": {"currentTax": dues["current"], "arrears": dues["arrears"], "interest": dues["interest"], "fees": dues["fees"], "advanceAdjusted": dues["advanceHeld"]}}}


@router.post("/integration/bbps/pay")
async def bbps_pay(payload: BbpsPay, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """Payment confirmation from BBPS: recorded as an online receipt. The same BBPS reference is never recorded twice."""
    ctx.require("integration.run")
    await require_link(db, ctx.tenant_id, "BBPS")
    key = f"BBPS:{payload.bbps_txn_ref}"
    existing = await db.scalar(select(PtxReceipt).where(PtxReceipt.tenant_id == ctx.tenant_id, PtxReceipt.idempotency_key == key))
    if existing is not None:
        if Decimal(str(payload.amount)) != existing.amount:
            raise bad_request("This BBPS reference was already used for a different amount.")
        return {"requestId": payload.request_id, "status": "PAID", "duplicate": True, "receiptNo": existing.receipt_no, "receiptDate": existing.receipt_date,
                "amount": float(existing.amount), "bbpsTxnRef": payload.bbps_txn_ref}
    prop = await _bbps_property(db, ctx, payload.upin, None)
    if prop is None:
        return {"requestId": payload.request_id, "status": "BILL_NOT_FOUND", "message": "No property found with that number."}
    due = dues_summary(await balances(db, ctx.tenant_id, prop.id))["netPayable"]
    if due <= 0:
        return {"requestId": payload.request_id, "status": "NO_DUES", "message": "Nothing is due on this property."}
    if payload.amount > due:
        return {"requestId": payload.request_id, "status": "AMOUNT_EXCEEDS_DUE", "message": f"Rs {due} is due; BBPS payments cannot be more than what is due."}
    receipt = await take_payment(db, ctx, prop, amount=Decimal(str(payload.amount)), mode="BBPS", channel="BBPS", idempotency_key=key,
                                 gateway_txn_id=payload.bbps_txn_ref, payer_name="Paid through BBPS")
    audit(db, ctx, "BBPS_PAYMENT", "receipt", receipt.id, None, {"receiptNo": receipt.receipt_no, "bbpsTxnRef": payload.bbps_txn_ref, "amount": payload.amount})
    await db.commit()
    return {"requestId": payload.request_id, "status": "PAID", "duplicate": False, "receiptNo": receipt.receipt_no, "receiptDate": receipt.receipt_date,
            "amount": float(receipt.amount), "bbpsTxnRef": payload.bbps_txn_ref}


@router.get("/integration/bbps/status/{bbps_txn_ref}")
async def bbps_status(bbps_txn_ref: str, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    """BBPS asks whether a payment it passed on was recorded."""
    ctx.require("integration.run")
    await require_link(db, ctx.tenant_id, "BBPS")
    r = await db.scalar(select(PtxReceipt).where(PtxReceipt.tenant_id == ctx.tenant_id, PtxReceipt.idempotency_key == f"BBPS:{bbps_txn_ref}"))
    if r is None:
        return {"bbpsTxnRef": bbps_txn_ref, "status": "NOT_FOUND"}
    return {"bbpsTxnRef": bbps_txn_ref, "status": "PAID" if r.status == "VALID" else r.status, "receiptNo": r.receipt_no, "receiptDate": r.receipt_date, "amount": float(r.amount),
            "payerMobileMasked": mask_mobile(r.payer_mobile)}

