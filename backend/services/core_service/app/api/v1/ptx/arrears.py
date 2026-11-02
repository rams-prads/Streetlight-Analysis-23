"""Arrears, interest, reminders, notices, recovery cases, waivers and write-offs (PT-41..PT-46, PT-63)."""
import datetime
import uuid
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ptx_calc import add_months, age_outstanding, band_for, document_code, money, period_label
from app.db.ptx_models import (
    PtxApproval, PtxDemand, PtxLedger, PtxNotice, PtxParty, PtxProperty, PtxRecoveryCase, utcnow,
)
from app.db.session import get_read_db, get_write_db
from app.schemas.ptx import NoticeRequest, NoticeService, RecoveryAdvance, WaiverRequest
from .common import (
    PtxAPIRoute, PtxContext, audit, bad_request, balances, bulk_balances, conflict, dues_summary, dues_total, dumps, emit_event,
    get_setting, load_property, loads, new_doc_no, not_found, notify, page, paginate, post_ledger, ptx_context, timeline, to_utc_naive,
    today, ward_maps,
)

router = APIRouter(route_class=PtxAPIRoute)


async def _demands_newest_first(db: AsyncSession, property_id: str) -> List[Dict]:
    rows = (await db.execute(select(PtxDemand).where(PtxDemand.property_id == property_id).order_by(PtxDemand.period_from.desc()))).scalars().all()
    revisions = dict((await db.execute(select(PtxLedger.demand_id, func.sum(PtxLedger.amount)).where(
        PtxLedger.property_id == property_id, PtxLedger.txn_type == "DEMAND_REVISION").group_by(PtxLedger.demand_id))).all())
    return [{"id": d.id, "demandNo": d.demand_no, "period": d.period, "dueDate": d.due_date,
             "amount": max(money(d.amount + money(revisions.get(d.id, 0))), Decimal("0"))} for d in rows]


async def ageing_rows(db: AsyncSession, prop: PtxProperty, bal: Dict[str, Decimal], as_of: datetime.date) -> List[Dict]:
    principal = money(max(bal["ARREAR"] + bal["CURRENT"], Decimal("0")))
    opening = await db.scalar(select(func.min(PtxLedger.entry_date)).where(PtxLedger.property_id == prop.id, PtxLedger.txn_type == "OPENING_ARREAR"))
    return age_outstanding(principal, await _demands_newest_first(db, prop.id), opening, as_of)


async def owner_mobile(db: AsyncSession, property_id: str) -> Optional[str]:
    return await db.scalar(select(PtxParty.mobile_number).where(PtxParty.property_id == property_id, PtxParty.role == "OWNER",
                                                                PtxParty.is_current.is_(True), PtxParty.mobile_number.isnot(None)).limit(1))


# ------------------------------------------------------------------------------------------------
# Interest on overdue tax (PT-41)
# ------------------------------------------------------------------------------------------------

async def run_interest(db: AsyncSession, actor, tenant_id: str, as_of: datetime.date, ward_filter=None) -> Dict:
    """
    Adds the notified interest for each month (or part month) a demand stays unpaid after its due date, on the part
    of that demand still unpaid. Each demand-month is charged once, so the job can run any number of times.
    """
    rule = await get_setting(db, tenant_id, "interest", as_of)
    pct = Decimal(str(rule.get("percentPerMonth", 0)))
    grace = int(rule.get("graceDays", 0))
    if pct <= 0:
        return {"properties": 0, "charges": 0, "amount": 0.0}
    stmt = select(PtxDemand.property_id).where(PtxDemand.tenant_id == tenant_id, PtxDemand.due_date < as_of - datetime.timedelta(days=grace))
    if ward_filter is not None:
        stmt = stmt.where(ward_filter(PtxDemand.ward_id))
    prop_ids = sorted(set((await db.execute(stmt)).scalars().all()))
    charges, total = 0, Decimal("0.00")
    for pid in prop_ids:
        prop = await db.get(PtxProperty, pid)
        bal = await balances(db, tenant_id, pid)
        for row in await ageing_rows(db, prop, bal, as_of):
            if not row["demandId"] or row["unpaid"] <= 0:
                continue
            start = row["dueDate"] + datetime.timedelta(days=grace)
            k = 1
            while add_months(start, k - 1) < as_of:
                key = f"int:{row['demandId']}:{k}"
                if not await db.scalar(select(PtxLedger.id).where(PtxLedger.property_id == pid, PtxLedger.dedupe_key == key)):
                    amount = money(row["unpaid"] * pct / Decimal("100"))
                    if amount > 0:
                        await post_ledger(db, actor, prop=prop, txn_type="INTEREST", component="INTEREST", bucket="PENALTY", amount=amount,
                                          demand_id=row["demandId"], reference_no=row["demandNo"], dedupe_key=key, entry_date=as_of,
                                          narration=f"Interest {pct}% for month {k} on unpaid Rs {row['unpaid']} of {period_label(row['period'])}")
                        charges += 1
                        total = money(total + amount)
                k += 1
        await db.flush()
    return {"properties": len(prop_ids), "charges": charges, "amount": float(total)}


@router.post("/arrears/interest-run")
async def interest_run(as_of: Optional[datetime.date] = Query(None, alias="asOf"), ctx: PtxContext = Depends(ptx_context),
                       db: AsyncSession = Depends(get_write_db)):
    ctx.require("arrears.manage")
    as_of = as_of or today()
    if as_of > today():
        raise bad_request("Interest cannot be added for a future date.")
    result = await run_interest(db, ctx, ctx.tenant_id, as_of, ctx.ward_filter)
    if result["charges"]:
        audit(db, ctx, "INTEREST_RUN", "interest", None, None, {"asOf": as_of, **result})
    await db.commit()
    return result


# ------------------------------------------------------------------------------------------------
# Reminders (PT-46)
# ------------------------------------------------------------------------------------------------

async def run_reminders(db: AsyncSession, tenant_id: str, as_of: datetime.date, ward_filter=None) -> Dict:
    rule = await get_setting(db, tenant_id, "reminders", as_of)
    before, after_days = int(rule.get("daysBeforeDue", 15)), [int(d) for d in rule.get("daysAfterDue", [])]
    latest = select(PtxDemand.property_id, func.max(PtxDemand.period_from).label("pf")).where(PtxDemand.tenant_id == tenant_id).group_by(PtxDemand.property_id).subquery()
    stmt = select(PtxDemand).join(latest, (latest.c.property_id == PtxDemand.property_id) & (latest.c.pf == PtxDemand.period_from))
    if ward_filter is not None:
        stmt = stmt.where(ward_filter(PtxDemand.ward_id))
    sent = 0
    for d in (await db.execute(stmt)).scalars().all():
        prop = await db.get(PtxProperty, d.property_id)
        mobile = await owner_mobile(db, prop.id)
        due = dues_total(await balances(db, tenant_id, prop.id))
        if prop.status != "ACTIVE" or not mobile or due <= 0:
            continue
        due_text = d.due_date.strftime("%d-%m-%Y")
        if d.due_date - datetime.timedelta(days=before) <= as_of < d.due_date:
            if await notify(db, tenant_id, recipient=mobile, channel="WHATSAPP", template="REMINDER_BEFORE_DUE", property_id=prop.id, ref_no=d.demand_no,
                            dedupe_key=f"rem:before:{d.id}",
                            message_en=f"GWMC Property Tax: Rs {due} for {prop.upin} is due on {due_text}. Pay on time to avoid interest.",
                            message_te=f"జీడబ్ల్యూఎంసీ ఆస్తి పన్ను: {prop.upin} కోసం రూ. {due} గడువు {due_text}. వడ్డీ పడకుండా సకాలంలో చెల్లించండి."):
                sent += 1
        for n in after_days:
            if as_of >= d.due_date + datetime.timedelta(days=n):
                if await notify(db, tenant_id, recipient=mobile, channel="WHATSAPP", template="REMINDER_AFTER_DUE", property_id=prop.id, ref_no=d.demand_no,
                                dedupe_key=f"rem:after{n}:{d.id}",
                                message_en=f"GWMC Property Tax: Rs {due} for {prop.upin} was due on {due_text} and is unpaid. Interest is being added.",
                                message_te=f"జీడబ్ల్యూఎంసీ ఆస్తి పన్ను: {prop.upin} కోసం రూ. {due} గడువు {due_text} దాటింది. వడ్డీ జతవుతోంది."):
                    sent += 1
    return {"remindersQueued": sent}


@router.post("/arrears/reminders-run")
async def reminders_run(ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    ctx.require("arrears.manage")
    result = await run_reminders(db, ctx.tenant_id, today(), ctx.ward_filter)
    await db.commit()
    return result


# ------------------------------------------------------------------------------------------------
# Ageing and defaulters (PT-63)
# ------------------------------------------------------------------------------------------------

@router.get("/arrears/ageing")
async def arrears_ageing(ward_id: Optional[str] = Query(None, alias="wardId"), search: Optional[str] = Query(None),
                         min_due: float = Query(0, alias="minDue"), skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                         ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    """Arrears by age band and ward, and defaulters by amount (largest first)."""
    if not ctx.can("arrears.manage"):
        ctx.require("reports.view")
    bands = await get_setting(db, ctx.tenant_id, "arrearsBands")
    stmt = select(PtxProperty).where(PtxProperty.tenant_id == ctx.tenant_id, ctx.ward_filter(PtxProperty.ward_id))
    if ward_id:
        stmt = stmt.where(PtxProperty.ward_id == ward_id)
    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(PtxProperty.upin.ilike(like), PtxProperty.address.ilike(like), PtxProperty.old_assessment_no.ilike(like)))
    props = (await db.execute(stmt)).scalars().all()
    bal = await bulk_balances(db, ctx.tenant_id, [p.id for p in props])
    wards, _ = await ward_maps(db, ctx.tenant_id)
    as_of = today()
    labels = [b["label"] for b in bands]
    totals = {label: Decimal("0") for label in labels}
    by_ward: Dict[str, Dict] = {}
    defaulters = []
    owners = {}
    if props:
        for p in (await db.execute(select(PtxParty).where(PtxParty.property_id.in_([x.id for x in props]), PtxParty.role == "OWNER",
                                                          PtxParty.is_current.is_(True)))).scalars().all():
            owners.setdefault(p.property_id, []).append(p.full_name)
    for prop in props:
        b = bal[prop.id]
        due = dues_total(b)
        if due <= 0 or due < Decimal(str(min_due)):
            continue
        rows = await ageing_rows(db, prop, b, as_of)
        ward = wards.get(prop.ward_id, {})
        w = by_ward.setdefault(prop.ward_id, {"wardId": prop.ward_id, "wardNumber": ward.get("wardNumber"), "wardName": ward.get("wardName"),
                                              "defaulters": 0, "totalDue": Decimal("0"), **{label: Decimal("0") for label in labels}})
        w["defaulters"] += 1
        w["totalDue"] += due
        for r in rows:
            label = band_for(r["ageDays"], bands)
            totals[label] += r["unpaid"]
            w[label] += r["unpaid"]
        oldest = max((r["ageDays"] for r in rows), default=0)
        defaulters.append({"upin": prop.upin, "ownerNames": ", ".join(owners.get(prop.id, [])) or "-", "address": prop.address,
                           "wardNumber": ward.get("wardNumber"), "interest": float(max(b["PENALTY"], 0)), "fees": float(max(b["FEE"], 0)),
                           "arrears": float(max(b["ARREAR"], 0)), "current": float(max(b["CURRENT"], 0)), "totalDue": float(due),
                           "oldestAgeDays": oldest, "ageBand": band_for(oldest, bands)})
    defaulters.sort(key=lambda d: (-d["totalDue"], -d["oldestAgeDays"]))
    return {"asOf": as_of, "bands": labels, "totals": {k: float(v) for k, v in totals.items()},
            "byWard": sorted([{k: (float(v) if isinstance(v, Decimal) else v) for k, v in w.items()} for w in by_ward.values()],
                             key=lambda w: w["wardNumber"] or 0),
            "defaulters": page(defaulters[skip:skip + limit], len(defaulters), skip, limit),
            "note": "Unpaid tax (arrears + current) is aged by the due date of each demand; interest and fees are shown separately."}


# ------------------------------------------------------------------------------------------------
# Notices (PT-42) and their service (PT-43)
# ------------------------------------------------------------------------------------------------

def notice_dict(n: PtxNotice, upin: Optional[str] = None, address: Optional[str] = None, wards: Optional[Dict] = None) -> Dict:
    ward = (wards or {}).get(n.ward_id, {})
    return {"id": n.id, "noticeNo": n.notice_no, "noticeType": n.notice_type, "upin": upin, "address": address,
            "wardNumber": ward.get("wardNumber"), "amount": float(n.amount) if n.amount is not None else None,
            "content": loads(n.content_json, {}), "batchId": n.batch_id, "serviceStatus": n.service_status, "servedAt": n.served_at,
            "servedBy": n.served_by, "serviceLatitude": n.service_latitude, "serviceLongitude": n.service_longitude,
            "servicePhotoRef": n.service_photo_ref, "notServedReason": n.not_served_reason, "issuedBy": n.issued_by, "issuedAt": n.issued_at,
            "verificationCode": n.verification_code,
            "verifyPath": f"/api/v1/ptx/public/verify?type=NOTICE&no={n.notice_no}&code={n.verification_code}&tenant={n.tenant_id}"}


async def issue_notice(db: AsyncSession, actor, prop: PtxProperty, notice_type: str, batch_id: Optional[str] = None,
                       recovery_case_id: Optional[str] = None, stage: Optional[str] = None) -> Optional[PtxNotice]:
    """Demand, reminder or recovery notice with the dues as of today; bilingual when printed (PT-42)."""
    bal = await balances(db, prop.tenant_id, prop.id)
    dues = dues_summary(bal)
    latest = await db.scalar(select(PtxDemand).where(PtxDemand.property_id == prop.id).order_by(PtxDemand.period_from.desc()).limit(1))
    if notice_type == "DEMAND" and latest is None:
        return None
    if notice_type in ("REMINDER", "RECOVERY") and dues["totalDue"] <= 0:
        return None
    start = datetime.datetime.combine(today(), datetime.time.min) - datetime.timedelta(hours=6)
    if recovery_case_id is None and await db.scalar(select(PtxNotice.id).where(PtxNotice.property_id == prop.id, PtxNotice.notice_type == notice_type,
                                                                               PtxNotice.issued_at >= start)):
        return None  # one notice of a kind per property per day
    owners = (await db.execute(select(PtxParty.full_name).where(PtxParty.property_id == prop.id, PtxParty.role == "OWNER", PtxParty.is_current.is_(True)))).scalars().all()
    content = {"ownerNames": list(owners), "dues": dues, "stage": stage,
               "period": latest.period if latest else None, "periodLabel": period_label(latest.period) if latest else None,
               "demandNo": latest.demand_no if latest else None, "dueDate": latest.due_date if latest else None,
               "components": loads(latest.components_json, {}) if latest else {}}
    n = PtxNotice(tenant_id=prop.tenant_id, notice_no=await new_doc_no(db, prop.tenant_id, {"DEMAND": "PDN", "REMINDER": "PRN", "RECOVERY": "PVN"}[notice_type], "notice"),
                  notice_type=notice_type, property_id=prop.id, ward_id=prop.ward_id, amount=money(dues["totalDue"]), content_json=dumps(content),
                  batch_id=batch_id, recovery_case_id=recovery_case_id, verification_code="PENDING",
                  issued_by=actor.username if isinstance(actor, PtxContext) else str(actor))
    db.add(n)
    await db.flush()
    n.verification_code = document_code("NOTICE", n.notice_no, n.amount)
    mobile = await owner_mobile(db, prop.id)
    await notify(db, prop.tenant_id, recipient=mobile, template=f"NOTICE_{notice_type}", property_id=prop.id, ref_no=n.notice_no, dedupe_key=f"notice:{n.id}",
                 message_en=f"GWMC Property Tax: {notice_type.lower()} notice {n.notice_no} for {prop.upin}. Amount due Rs {dues['totalDue']}.",
                 message_te=f"జీడబ్ల్యూఎంసీ ఆస్తి పన్ను: {prop.upin} కోసం నోటీసు {n.notice_no}. బకాయి రూ. {dues['totalDue']}.")
    return n


@router.post("/notices", status_code=201)
async def generate_notices(payload: NoticeRequest, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """Notices one at a time (list of UPINs) or in bulk for a ward (PT-42)."""
    ctx.require("arrears.manage")
    if bool(payload.upins) == bool(payload.ward_id):
        raise bad_request("Give either property numbers, or a ward for bulk notices.")
    props: List[PtxProperty] = []
    if payload.upins:
        props = [await load_property(db, ctx, upin=u) for u in dict.fromkeys(payload.upins)]
    else:
        ctx.ensure_scope(payload.ward_id)
        props = (await db.execute(select(PtxProperty).where(PtxProperty.tenant_id == ctx.tenant_id, PtxProperty.ward_id == payload.ward_id,
                                                            PtxProperty.status == "ACTIVE").order_by(PtxProperty.upin))).scalars().all()
    batch_id = str(uuid.uuid4())
    issued, skipped = [], 0
    for prop in props:
        if payload.min_due and dues_total(await balances(db, ctx.tenant_id, prop.id)) < Decimal(str(payload.min_due)):
            skipped += 1
            continue
        n = await issue_notice(db, ctx, prop, payload.notice_type, batch_id=batch_id)
        if n is None:
            skipped += 1
        else:
            issued.append(n.notice_no)
    audit(db, ctx, "NOTICES_ISSUED", "notice", batch_id, None, {"type": payload.notice_type, "issued": len(issued), "skipped": skipped})
    await db.commit()
    return {"batchId": batch_id, "issued": issued, "skipped": skipped}


@router.get("/notices")
async def list_notices(search: Optional[str] = Query(None), notice_type: Optional[str] = Query(None, alias="type"),
                       service_status: Optional[str] = Query(None, alias="serviceStatus"), ward_id: Optional[str] = Query(None, alias="wardId"),
                       batch_id: Optional[str] = Query(None, alias="batchId"), skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                       ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("property.view")
    stmt = select(PtxNotice, PtxProperty.upin, PtxProperty.address).join(PtxProperty, PtxProperty.id == PtxNotice.property_id).where(
        PtxNotice.tenant_id == ctx.tenant_id, ctx.ward_filter(PtxNotice.ward_id))
    if notice_type:
        stmt = stmt.where(PtxNotice.notice_type == notice_type.upper())
    if service_status:
        stmt = stmt.where(PtxNotice.service_status == service_status.upper())
    if ward_id:
        stmt = stmt.where(PtxNotice.ward_id == ward_id)
    if batch_id:
        stmt = stmt.where(PtxNotice.batch_id == batch_id)
    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(PtxNotice.notice_no.ilike(like), PtxProperty.upin.ilike(like), PtxProperty.address.ilike(like)))
    rows, total = await paginate(db, stmt.order_by(PtxNotice.issued_at.desc()), skip, limit)
    wards, _ = await ward_maps(db, ctx.tenant_id)
    return page([notice_dict(n, upin, address, wards) for n, upin, address in rows], total, skip, limit)


@router.get("/notices/{notice_no}")
async def get_notice(notice_no: str, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("property.view")
    n = await db.scalar(select(PtxNotice).where(PtxNotice.tenant_id == ctx.tenant_id, PtxNotice.notice_no == notice_no))
    if n is None:
        raise not_found(f"Notice {notice_no} not found.")
    prop = await db.get(PtxProperty, n.property_id)
    ctx.ensure_scope(prop.ward_id)
    wards, _ = await ward_maps(db, ctx.tenant_id)
    return {**notice_dict(n, prop.upin, prop.address, wards), "doorNo": prop.door_no, "wardName": wards.get(prop.ward_id, {}).get("wardName")}


async def record_service(db: AsyncSession, ctx: PtxContext, notice_no: str, payload: NoticeService) -> Dict:
    n = await db.scalar(select(PtxNotice).where(PtxNotice.tenant_id == ctx.tenant_id, PtxNotice.notice_no == notice_no).with_for_update())
    if n is None:
        raise not_found(f"Notice {notice_no} not found.")
    ctx.ensure_scope(n.ward_id)
    if n.service_status != "PENDING":
        return {"noticeNo": n.notice_no, "result": "ALREADY_RECORDED", "serviceStatus": n.service_status}
    if payload.served:
        if not payload.photo_ref or payload.latitude is None or payload.longitude is None:
            raise bad_request("To record a notice as served, add a photo and the GPS location.")
        n.service_status = "SERVED"
    else:
        if not payload.reason or len(payload.reason.strip()) < 3:
            raise bad_request("Say why the notice could not be served (for example: house locked, owner refused).")
        n.service_status, n.not_served_reason = "NOT_SERVED", payload.reason
    n.served_at = to_utc_naive(payload.served_at) if payload.served_at else utcnow()
    n.served_by = ctx.username
    n.service_latitude, n.service_longitude, n.service_photo_ref = payload.latitude, payload.longitude, payload.photo_ref
    audit(db, ctx, "NOTICE_SERVICE", "notice", n.id, {"serviceStatus": "PENDING"}, {"serviceStatus": n.service_status, "reason": payload.reason})
    return {"noticeNo": n.notice_no, "result": "RECORDED", "serviceStatus": n.service_status}


@router.post("/notices/{notice_no}/service")
async def notice_service(notice_no: str, payload: NoticeService, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """Field staff record that a notice was served (date, GPS, photo) or why it could not be (PT-43)."""
    ctx.require("notice.serve")
    result = await record_service(db, ctx, notice_no, payload)
    await db.commit()
    return result


# ------------------------------------------------------------------------------------------------
# Recovery cases (PT-44)
# ------------------------------------------------------------------------------------------------

def recovery_dict(c: PtxRecoveryCase, upin: Optional[str], wards: Dict, due: Optional[float] = None) -> Dict:
    return {"id": c.id, "caseNo": c.case_no, "upin": upin, "wardNumber": wards.get(c.ward_id, {}).get("wardNumber"), "stage": c.stage,
            "status": c.status, "duesAtOpen": float(c.dues_at_open), "currentDue": due, "stages": loads(c.stages_json, []),
            "closureReason": c.closure_reason, "openedBy": c.opened_by, "openedAt": c.opened_at, "closedAt": c.closed_at}


async def run_recovery(db: AsyncSession, actor, tenant_id: str, as_of: datetime.date, ward_filter=None) -> Dict:
    """Opens recovery cases for large or long-unpaid dues and closes cases whose dues are cleared (PT-44)."""
    rule = await get_setting(db, tenant_id, "recovery", as_of)
    stages = rule["stages"]
    opened, closed = [], []
    open_cases = (await db.execute(select(PtxRecoveryCase).where(PtxRecoveryCase.tenant_id == tenant_id, PtxRecoveryCase.status == "OPEN"))).scalars().all()
    with_case = {c.property_id for c in open_cases}
    for c in open_cases:
        if dues_total(await balances(db, tenant_id, c.property_id)) <= 0:
            c.status, c.closed_at, c.closure_reason = "CLOSED", utcnow(), "Dues paid in full"
            timeline(db, tenant_id, "recovery", c.id, "CLOSED", "Dues paid in full", actor=str(actor) if not isinstance(actor, PtxContext) else actor.username)
            closed.append(c.case_no)
    stmt = select(PtxProperty).where(PtxProperty.tenant_id == tenant_id, PtxProperty.status == "ACTIVE")
    if ward_filter is not None:
        stmt = stmt.where(ward_filter(PtxProperty.ward_id))
    props = (await db.execute(stmt)).scalars().all()
    bal = await bulk_balances(db, tenant_id, [p.id for p in props])
    for prop in props:
        if prop.id in with_case:
            continue
        due = dues_total(bal[prop.id])
        if due <= 0:
            continue
        oldest = max((r["ageDays"] for r in await ageing_rows(db, prop, bal[prop.id], as_of)), default=0)
        if due >= Decimal(str(rule["openAboveAmount"])) and oldest >= int(rule["openAfterDaysOverdue"]):
            case = PtxRecoveryCase(tenant_id=tenant_id, case_no=await new_doc_no(db, tenant_id, "PRV", "recovery"), property_id=prop.id,
                                   ward_id=prop.ward_id, stage=stages[0], dues_at_open=due,
                                   stages_json=dumps([{"stage": stages[0], "at": utcnow().isoformat(), "by": "system", "remark": f"Opened: Rs {due} unpaid for {oldest} days"}]),
                                   opened_by=actor.username if isinstance(actor, PtxContext) else str(actor))
            db.add(case)
            await db.flush()
            await issue_notice(db, actor, prop, "RECOVERY", recovery_case_id=case.id, stage=stages[0])
            opened.append(case.case_no)
    return {"opened": opened, "closed": closed}


@router.post("/recovery/run")
async def recovery_run(ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    ctx.require("arrears.manage")
    result = await run_recovery(db, ctx, ctx.tenant_id, today(), ctx.ward_filter)
    await db.commit()
    return result


@router.get("/recovery")
async def list_recovery(search: Optional[str] = Query(None), status: Optional[str] = Query("OPEN"), skip: int = Query(0, ge=0),
                        limit: int = Query(50, ge=1, le=100), ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    if not ctx.can("arrears.manage"):
        ctx.require("reports.view")
    stmt = select(PtxRecoveryCase, PtxProperty.upin).join(PtxProperty, PtxProperty.id == PtxRecoveryCase.property_id).where(
        PtxRecoveryCase.tenant_id == ctx.tenant_id, ctx.ward_filter(PtxRecoveryCase.ward_id))
    if status:
        stmt = stmt.where(PtxRecoveryCase.status == status.upper())
    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(PtxRecoveryCase.case_no.ilike(like), PtxProperty.upin.ilike(like)))
    rows, total = await paginate(db, stmt.order_by(PtxRecoveryCase.opened_at.desc()), skip, limit)
    wards, _ = await ward_maps(db, ctx.tenant_id)
    bal = await bulk_balances(db, ctx.tenant_id, [c.property_id for c, _ in rows])
    return page([recovery_dict(c, upin, wards, float(max(dues_total(bal[c.property_id]), Decimal("0")))) for c, upin in rows], total, skip, limit)


@router.post("/recovery/{case_no}/advance")
async def advance_recovery(case_no: str, payload: RecoveryAdvance, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """Moves a recovery case to its next stage, or closes it, recording who and why (PT-44)."""
    ctx.require("arrears.manage")
    c = await db.scalar(select(PtxRecoveryCase).where(PtxRecoveryCase.tenant_id == ctx.tenant_id, PtxRecoveryCase.case_no == case_no).with_for_update())
    if c is None:
        raise not_found(f"Recovery case {case_no} not found.")
    ctx.ensure_scope(c.ward_id)
    if c.status != "OPEN":
        raise bad_request("This recovery case is already closed.")
    history = loads(c.stages_json, [])
    if payload.close:
        c.status, c.closed_at, c.closure_reason = "CLOSED", utcnow(), payload.remark
        history.append({"stage": "CLOSED", "at": utcnow().isoformat(), "by": ctx.username, "remark": payload.remark})
    else:
        stages = (await get_setting(db, ctx.tenant_id, "recovery"))["stages"]
        idx = stages.index(c.stage) if c.stage in stages else -1
        if idx + 1 >= len(stages):
            raise bad_request("This case is at the final stage. Close it with the outcome.")
        c.stage = stages[idx + 1]
        history.append({"stage": c.stage, "at": utcnow().isoformat(), "by": ctx.username, "remark": payload.remark})
        if c.stage.endswith("_NOTICE") or c.stage == "DISTRAINT_WARRANT":
            prop = await db.get(PtxProperty, c.property_id)
            await issue_notice(db, ctx, prop, "RECOVERY", recovery_case_id=c.id, stage=c.stage)
    c.stages_json = dumps(history)
    audit(db, ctx, "RECOVERY_STAGE", "recovery", c.id, None, {"stage": c.stage, "status": c.status, "remark": payload.remark})
    await db.commit()
    return {"message": "Recovery case updated", "caseNo": c.case_no, "stage": c.stage, "status": c.status}


# ------------------------------------------------------------------------------------------------
# Waivers and write-offs (PT-45)
# ------------------------------------------------------------------------------------------------

@router.post("/properties/{upin}/waivers", status_code=201)
async def request_waiver(upin: str, payload: WaiverRequest, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    ctx.require("approval.request")
    prop = await load_property(db, ctx, upin=upin)
    bal = await balances(db, ctx.tenant_id, prop.id)
    amount = money(payload.amount)
    if amount > bal[payload.bucket]:
        raise bad_request(f"Only Rs {max(bal[payload.bucket], Decimal('0'))} is due under {payload.bucket.lower()}.")
    if await db.scalar(select(PtxApproval.id).where(PtxApproval.property_id == prop.id, PtxApproval.status == "PENDING",
                                                    PtxApproval.approval_type.in_(["WAIVER", "WRITE_OFF"]))):
        raise conflict("A waiver or write-off for this property is already waiting for approval.")
    a = PtxApproval(tenant_id=ctx.tenant_id, approval_type=payload.kind, property_id=prop.id, ref_no=prop.upin, amount=amount, reason=payload.reason,
                    requested_by=ctx.username, payload_json=dumps({"bucket": payload.bucket, "upin": prop.upin}))
    db.add(a)
    audit(db, ctx, f"{payload.kind}_REQUESTED", "property", prop.id, None, payload.model_dump(mode="json"))
    await db.commit()
    return {"message": f"{'Waiver' if payload.kind == 'WAIVER' else 'Write-off'} sent for approval", "approvalId": a.id}


async def post_waiver(db: AsyncSession, ctx: PtxContext, a: PtxApproval) -> None:
    prop = await db.get(PtxProperty, a.property_id)
    bucket = loads(a.payload_json, {})["bucket"]
    bal = await balances(db, ctx.tenant_id, prop.id)
    amount = money(a.amount)
    if amount > bal[bucket]:
        raise bad_request(f"Only Rs {max(bal[bucket], Decimal('0'))} is now due under {bucket.lower()}; reject and raise a new request.")
    await post_ledger(db, ctx, prop=prop, txn_type=a.approval_type, component=a.approval_type, bucket=bucket, amount=-amount, approval_id=a.id,
                      reference_no=prop.upin, narration=a.reason)
    if a.approval_type == "WRITE_OFF":
        emit_event(db, ctx.tenant_id, "writeoff.approved", prop.id, {"upin": prop.upin, "amount": float(amount), "bucket": bucket})
