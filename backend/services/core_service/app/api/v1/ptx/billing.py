"""Rate tables (PT-10), bulk revision (PT-12), demand generation and demand notices (PT-30, PT-NF-04, PT-NF-63)."""
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ptx_calc import document_code, money, period_bounds, period_label, validate_rules
from app.db.ptx_models import (
    PtxApproval, PtxAssessment, PtxDemand, PtxJob, PtxLedger, PtxNotice, PtxParty, PtxProperty, PtxRateTable, utcnow,
)
from app.db.session import get_read_db, get_write_db
from app.schemas.ptx import CorrectionRequest, DeliveryBatch, DemandRunRequest, RateTableProposal, RevisionRunRequest
from .assess import _post_by_bucket, calculate, current_floors, effective_period_start, new_assessment, property_details, raise_demand, revise_raised_demands
from .common import (
    PtxAPIRoute, PtxContext, audit, bad_request, balances, conflict, dues_summary, dumps, get_setting, loads, new_doc_no, not_found, notify,
    page, paginate, ptx_context, to_utc_naive, today, ward_maps,
)

router = APIRouter(route_class=PtxAPIRoute)


def rate_dict(t: PtxRateTable, in_force_id: Optional[str]) -> Dict:
    return {"id": t.id, "version": t.version, "effectiveFrom": t.effective_from, "rules": loads(t.rules_json, {}), "status": t.status,
            "orderReference": t.order_reference, "reason": t.reason, "requestedBy": t.requested_by, "approvedBy": t.approved_by,
            "approvedAt": t.approved_at, "inForce": t.id == in_force_id}


@router.get("/rate-tables")
async def list_rate_tables(ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("rates.view")
    rows = (await db.execute(select(PtxRateTable).where(PtxRateTable.tenant_id == ctx.tenant_id).order_by(PtxRateTable.version.desc()))).scalars().all()
    current = await db.scalar(select(PtxRateTable.id).where(PtxRateTable.tenant_id == ctx.tenant_id, PtxRateTable.status == "APPROVED",
                                                            PtxRateTable.effective_from <= today())
                              .order_by(PtxRateTable.effective_from.desc(), PtxRateTable.version.desc()).limit(1))
    return [rate_dict(t, current) for t in rows]


@router.post("/rate-tables", status_code=201)
async def propose_rate_table(payload: RateTableProposal, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """A new rate table is a proposal until the Commissioner approves it; old versions are kept (SRS 3.4)."""
    ctx.require("rates.propose")
    try:
        validate_rules(payload.rules)
    except ValueError as exc:
        raise bad_request(str(exc))
    if payload.effective_from < today():
        raise bad_request("A rate table cannot take effect in the past; past bills keep the rates they were raised under.")
    version = (await db.scalar(select(func.max(PtxRateTable.version)).where(PtxRateTable.tenant_id == ctx.tenant_id)) or 0) + 1
    table = PtxRateTable(tenant_id=ctx.tenant_id, version=version, effective_from=payload.effective_from, rules_json=dumps(payload.rules),
                         status="PENDING_APPROVAL", order_reference=payload.order_reference, reason=payload.reason, requested_by=ctx.username)
    db.add(table)
    await db.flush()
    db.add(PtxApproval(tenant_id=ctx.tenant_id, approval_type="RATE_TABLE", ref_id=table.id, ref_no=f"Rate table v{version}",
                       payload_json=dumps({"version": version, "effectiveFrom": payload.effective_from, "orderReference": payload.order_reference}),
                       reason=payload.reason, requested_by=ctx.username))
    audit(db, ctx, "RATE_TABLE_PROPOSED", "rate_table", table.id, None, {"version": version, "effectiveFrom": payload.effective_from})
    await db.commit()
    return rate_dict(table, None)


# ------------------------------------------------------------------------------------------------
# Bulk jobs, ward by ward (PT-NF-63)
# ------------------------------------------------------------------------------------------------

async def _wards_for(db: AsyncSession, ctx: PtxContext, ward_ids: List[str]) -> List[Dict]:
    wards, _ = await ward_maps(db, ctx.tenant_id)
    chosen = [w for w in wards.values() if ctx.in_scope(w["wardId"]) and (not ward_ids or w["wardId"] in ward_ids)]
    if ward_ids and len(chosen) != len(set(ward_ids)):
        raise bad_request("One or more wards were not found or are outside your area.")
    return sorted(chosen, key=lambda w: w["wardNumber"])


async def _job(db: AsyncSession, ctx: PtxContext, job_type: str, key: str, ward_id: str) -> Optional[PtxJob]:
    job = await db.scalar(select(PtxJob).where(PtxJob.tenant_id == ctx.tenant_id, PtxJob.job_type == job_type, PtxJob.job_key == key,
                                               PtxJob.ward_id == ward_id))
    if job is not None and job.status == "DONE" and not loads(job.skipped_json, []):
        return None
    if job is None:
        job = PtxJob(tenant_id=ctx.tenant_id, job_type=job_type, job_key=key, ward_id=ward_id, started_by=ctx.username)
        db.add(job)
        await db.flush()
    job.status = "RUNNING"
    return job


@router.post("/demand/run")
async def run_demand(payload: DemandRunRequest, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """
    Raises demand for a period ward by ward (PT-30). Each ward is committed on its own and recorded, so a stopped run is
    simply started again; the unique (property, period) rule means nobody is billed twice (PT-NF-63).
    """
    ctx.require("demand.run")
    frequency = await get_setting(db, ctx.tenant_id, "demand.frequency")
    try:
        start, _ = period_bounds(payload.period)
    except ValueError as exc:
        raise bad_request(str(exc))
    if (payload.period.endswith("-Y")) != (frequency == "YEARLY"):
        raise bad_request(f"Demand is raised {frequency.replace('_', '-').lower()}; choose a matching period.")
    if start > today():
        raise bad_request("Demand cannot be raised for a period that has not started yet.")
    summary = {"period": payload.period, "periodLabel": period_label(payload.period), "wards": [], "raised": 0, "held": [], "alreadyDone": 0}
    for ward in await _wards_for(db, ctx, payload.ward_ids):
        job = await _job(db, ctx, "DEMAND", payload.period, ward["wardId"])
        if job is None:
            summary["alreadyDone"] += 1
            summary["wards"].append({"wardNumber": ward["wardNumber"], "status": "ALREADY_DONE", "raised": 0})
            continue
        props = (await db.execute(select(PtxProperty).where(PtxProperty.tenant_id == ctx.tenant_id, PtxProperty.ward_id == ward["wardId"],
                                                            PtxProperty.status == "ACTIVE").order_by(PtxProperty.upin))).scalars().all()
        raised, held = 0, []
        for prop in props:
            r = await raise_demand(db, ctx, prop, payload.period, run_id=job.id)
            if r["result"] == "RAISED":
                raised += 1
            elif r["result"] == "HELD":
                held.append({"upin": prop.upin, "reason": r["reason"]})
        job.processed += raised
        job.skipped_json = dumps(held)
        job.status, job.finished_at = "DONE", utcnow()
        audit(db, ctx, "DEMAND_RUN", "job", job.id, None, {"period": payload.period, "ward": ward["wardNumber"], "raised": raised, "held": len(held)})
        await db.commit()
        summary["wards"].append({"wardNumber": ward["wardNumber"], "status": "DONE", "raised": raised, "held": len(held)})
        summary["raised"] += raised
        summary["held"].extend(held)
    return summary


@router.post("/revision/run")
async def run_revision(payload: RevisionRunRequest, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """
    General revision after new rates are approved (PT-12): every active property is reassessed with the new rate table
    from its effective date, ward by ward, resumable. Owners get an assessment notice; bills already raised for those
    periods are revised by ledger entries, never edited.
    """
    ctx.require("demand.run")
    table = await db.scalar(select(PtxRateTable).where(PtxRateTable.id == payload.rate_table_id, PtxRateTable.tenant_id == ctx.tenant_id))
    if table is None or table.status != "APPROVED":
        raise bad_request("Choose an approved rate table.")
    effective = await effective_period_start(db, ctx.tenant_id, table.effective_from)
    summary = {"rateTableVersion": table.version, "effectiveFrom": effective, "wards": [], "reassessed": 0, "skipped": []}
    for ward in await _wards_for(db, ctx, payload.ward_ids):
        job = await _job(db, ctx, "REVISION", table.id, ward["wardId"])
        if job is None:
            summary["wards"].append({"wardNumber": ward["wardNumber"], "status": "ALREADY_DONE"})
            continue
        props = (await db.execute(select(PtxProperty).where(PtxProperty.tenant_id == ctx.tenant_id, PtxProperty.ward_id == ward["wardId"],
                                                            PtxProperty.status == "ACTIVE").order_by(PtxProperty.upin))).scalars().all()
        done, skipped = 0, []
        for prop in props:
            exists = await db.scalar(select(PtxAssessment.id).where(PtxAssessment.property_id == prop.id, PtxAssessment.rate_table_id == table.id,
                                                                    PtxAssessment.kind == "GENERAL_REVISION"))
            current = await db.scalar(select(PtxAssessment.id).where(PtxAssessment.property_id == prop.id, PtxAssessment.status == "FINAL"))
            if exists or not current:
                continue
            try:
                calc = await calculate(db, ctx.tenant_id, property_details(prop), await current_floors(db, prop.id), effective, table.id)
            except Exception as exc:  # one property with a missing rate must not stop the ward
                skipped.append({"upin": prop.upin, "reason": getattr(exc, "detail", str(exc))})
                continue
            assessment = await new_assessment(db, ctx.username, prop, "GENERAL_REVISION", calc, effective, "FINAL")
            await revise_raised_demands(db, ctx, prop, effective, f"General revision to rate table v{table.version}")
            notice = PtxNotice(tenant_id=ctx.tenant_id, notice_no=await new_doc_no(db, ctx.tenant_id, "PAN", "notice"), notice_type="ASSESSMENT",
                               property_id=prop.id, ward_id=prop.ward_id, amount=assessment.annual_tax,
                               content_json=dumps({"type": "GENERAL_REVISION", "typeLabel": "General revision of rates", "assessmentNo": assessment.assessment_no,
                                                   "effectiveFrom": effective, "annualTax": float(assessment.annual_tax), "calculation": calc["sheet"],
                                                   "orderReference": table.order_reference}),
                               verification_code=document_code("NOTICE", f"rev-{assessment.assessment_no}", assessment.annual_tax), issued_by=ctx.username)
            db.add(notice)
            await db.flush()
            notice.verification_code = document_code("NOTICE", notice.notice_no, notice.amount)
            assessment.notice_no = notice.notice_no
            done += 1
        job.processed += done
        job.skipped_json = dumps(skipped)
        job.status, job.finished_at = "DONE", utcnow()
        audit(db, ctx, "REVISION_RUN", "job", job.id, None, {"rateTable": table.version, "ward": ward["wardNumber"], "reassessed": done})
        await db.commit()
        summary["wards"].append({"wardNumber": ward["wardNumber"], "status": "DONE", "reassessed": done, "skipped": len(skipped)})
        summary["reassessed"] += done
        summary["skipped"].extend(skipped)
    return summary


@router.get("/jobs")
async def list_jobs(job_type: Optional[str] = Query(None, alias="type"), skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                    ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("billing.view")
    stmt = select(PtxJob).where(PtxJob.tenant_id == ctx.tenant_id)
    if job_type:
        stmt = stmt.where(PtxJob.job_type == job_type.upper())
    rows, total = await paginate(db, stmt.order_by(PtxJob.started_at.desc()), skip, limit)
    wards, _ = await ward_maps(db, ctx.tenant_id)
    return page([{"id": j.id, "jobType": j.job_type, "jobKey": j.job_key, "wardNumber": wards.get(j.ward_id, {}).get("wardNumber"),
                  "status": j.status, "processed": j.processed, "skipped": loads(j.skipped_json, []), "startedBy": j.started_by,
                  "startedAt": j.started_at, "finishedAt": j.finished_at} for (j,) in rows], total, skip, limit)


# ------------------------------------------------------------------------------------------------
# Demands and the printable demand notice
# ------------------------------------------------------------------------------------------------

@router.get("/demands")
async def list_demands(search: Optional[str] = Query(None), period: Optional[str] = Query(None), ward_id: Optional[str] = Query(None, alias="wardId"),
                       delivery: Optional[str] = Query(None), skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                       ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("billing.view")
    stmt = select(PtxDemand, PtxProperty.upin, PtxProperty.address).join(PtxProperty, PtxProperty.id == PtxDemand.property_id).where(
        PtxDemand.tenant_id == ctx.tenant_id, ctx.ward_filter(PtxDemand.ward_id))
    if period:
        stmt = stmt.where(PtxDemand.period == period)
    if ward_id:
        stmt = stmt.where(PtxDemand.ward_id == ward_id)
    if delivery:
        stmt = stmt.where(PtxDemand.delivery_status == delivery.upper())
    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(PtxDemand.demand_no.ilike(like), PtxProperty.upin.ilike(like), PtxProperty.address.ilike(like)))
    rows, total = await paginate(db, stmt.order_by(PtxDemand.period_from.desc(), PtxDemand.demand_no.desc()), skip, limit)
    return page([{"demandNo": d.demand_no, "upin": upin, "address": address, "period": d.period, "periodLabel": period_label(d.period),
                  "dueDate": d.due_date, "amount": float(d.amount), "components": loads(d.components_json, {}), "deliveryStatus": d.delivery_status,
                  "deliveredAt": d.delivered_at, "deliveredBy": d.delivered_by, "deliveryNote": d.delivery_note} for d, upin, address in rows],
                total, skip, limit)


@router.get("/demands/batch")
async def print_batch(period: str = Query(...), ward_id: Optional[str] = Query(None, alias="wardId"), delivery: Optional[str] = Query(None),
                      skip: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=50), ctx: PtxContext = Depends(ptx_context),
                      db: AsyncSession = Depends(get_read_db)):
    """Full bills for printing, a page of them at a time, in door-number order so they can be handed out street by street (PT-20)."""
    ctx.require("billing.view")
    stmt = select(PtxDemand, PtxProperty).join(PtxProperty, PtxProperty.id == PtxDemand.property_id).where(
        PtxDemand.tenant_id == ctx.tenant_id, PtxDemand.period == period, ctx.ward_filter(PtxDemand.ward_id))
    if ward_id:
        stmt = stmt.where(PtxDemand.ward_id == ward_id)
    if delivery:
        stmt = stmt.where(PtxDemand.delivery_status == delivery.upper())
    rows, total = await paginate(db, stmt.order_by(PtxProperty.door_no, PtxProperty.upin), skip, limit)
    items = []
    for d, prop in rows:
        items.append({**await demand_notice(db, ctx.tenant_id, d, prop), "deliveryStatus": d.delivery_status})
    return page(items, total, skip, limit)


@router.get("/demands/delivery-summary")
async def delivery_summary(period: str = Query(...), ward_id: Optional[str] = Query(None, alias="wardId"), ctx: PtxContext = Depends(ptx_context),
                           db: AsyncSession = Depends(get_read_db)):
    """How many bills of a period are delivered, not delivered or still to go (PT-20)."""
    ctx.require("billing.view")
    stmt = select(PtxDemand.delivery_status, func.count()).where(PtxDemand.tenant_id == ctx.tenant_id, PtxDemand.period == period,
                                                                 ctx.ward_filter(PtxDemand.ward_id)).group_by(PtxDemand.delivery_status)
    if ward_id:
        stmt = stmt.where(PtxDemand.ward_id == ward_id)
    counts = {s: n for s, n in (await db.execute(stmt)).all()}
    out = {"PENDING": counts.get("PENDING", 0), "DELIVERED": counts.get("DELIVERED", 0), "NOT_DELIVERED": counts.get("NOT_DELIVERED", 0)}
    return {"period": period, "periodLabel": period_label(period), **out, "total": sum(out.values())}


@router.post("/demands/delivery")
async def record_delivery(payload: DeliveryBatch, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """Bill collectors record bills handed over or why not, one by one or synced from the field app; repeats are ignored (PT-20)."""
    ctx.require("notice.serve")
    results = []
    for it in payload.items:
        d = await db.scalar(select(PtxDemand).where(PtxDemand.tenant_id == ctx.tenant_id, PtxDemand.demand_no == it.demand_no).with_for_update())
        if d is None:
            results.append({"demandNo": it.demand_no, "result": "ERROR", "error": "Bill not found."})
            continue
        if not ctx.in_scope(d.ward_id):
            results.append({"demandNo": it.demand_no, "result": "ERROR", "error": "This bill is outside your assigned area."})
            continue
        if not it.delivered and not (it.note or "").strip():
            results.append({"demandNo": it.demand_no, "result": "ERROR", "error": "Say why the bill could not be delivered."})
            continue
        status = "DELIVERED" if it.delivered else "NOT_DELIVERED"
        if d.delivery_status == status and d.delivered_by == ctx.username:
            results.append({"demandNo": it.demand_no, "result": "ALREADY_RECORDED"})
            continue
        old = d.delivery_status
        d.delivery_status, d.delivered_by, d.delivered_at = status, ctx.username, to_utc_naive(it.delivered_at) if it.delivered_at else utcnow()
        d.delivery_note, d.delivery_lat, d.delivery_lng = (it.note or None), it.latitude, it.longitude
        audit(db, ctx, "BILL_DELIVERY", "demand", d.id, {"deliveryStatus": old}, {"deliveryStatus": status, "note": it.note})
        results.append({"demandNo": it.demand_no, "result": "RECORDED"})
    await db.commit()
    return {"recorded": sum(1 for r in results if r["result"] in ("RECORDED", "ALREADY_RECORDED")), "errors": sum(1 for r in results if r["result"] == "ERROR"),
            "results": results}


async def demand_notice(db: AsyncSession, tenant_id: str, demand: PtxDemand, prop: PtxProperty, public: bool = False) -> Dict:
    """Everything printed on a demand notice / bill (PT-30, PT-42): each tax and cess separately, dues, due date, QR codes."""
    wards, _ = await ward_maps(db, tenant_id)
    ward = wards.get(prop.ward_id, {})
    owners = (await db.execute(select(PtxParty.full_name).where(PtxParty.property_id == prop.id, PtxParty.role == "OWNER",
                                                                PtxParty.is_current.is_(True)))).scalars().all()
    revised = money(await db.scalar(select(func.coalesce(func.sum(PtxLedger.amount), 0)).where(
        PtxLedger.demand_id == demand.id, PtxLedger.txn_type.in_(["DEMAND_REVISION", "ADJUSTMENT"]))) or 0)
    dues = dues_summary(await balances(db, tenant_id, prop.id))
    upi = await get_setting(db, tenant_id, "upi")
    pay = Decimal(str(dues["netPayable"]))
    return {
        "demandNo": demand.demand_no, "upin": prop.upin, "oldAssessmentNo": prop.old_assessment_no, "ownerNames": list(owners),
        "address": prop.address, "doorNo": prop.door_no, "wardNumber": ward.get("wardNumber"), "wardName": ward.get("wardName"),
        "zoneName": ward.get("zoneName"), "period": demand.period, "periodLabel": period_label(demand.period),
        "periodFrom": demand.period_from, "periodTo": demand.period_to, "dueDate": demand.due_date,
        "components": loads(demand.components_json, {}), "amount": float(demand.amount), "revised": float(revised),
        "arrearsAtRaise": float(demand.arrears_at_raise), "interestAtRaise": float(demand.penalty_at_raise),
        "dues": dues, "verificationCode": demand.verification_code,
        "upiUri": f"upi://pay?pa={upi['vpa']}&pn={upi['payeeName'].replace(' ', '%20')}&am={pay}&cu=INR&tn={prop.upin}" if pay > 0 else None,
        "verifyPath": f"/api/v1/ptx/public/verify?type=DEMAND&no={demand.demand_no}&code={demand.verification_code}&tenant={tenant_id}",
    }


async def _demand_total(db: AsyncSession, d: PtxDemand) -> Decimal:
    """What the bill stands at now: raised amount plus revisions and approved corrections."""
    changes = await db.scalar(select(func.coalesce(func.sum(PtxLedger.amount), 0)).where(
        PtxLedger.demand_id == d.id, PtxLedger.txn_type.in_(["DEMAND_REVISION", "ADJUSTMENT"])))
    return money(d.amount + money(changes or 0))


@router.post("/demands/{demand_no}/corrections", status_code=201)
async def request_correction(demand_no: str, payload: CorrectionRequest, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """
    Corrects one raised bill, for example a clerical error (PT-19). The bill itself is never edited: an approved
    correction is a new entry on the account, with who asked, who approved and why.
    """
    ctx.require("approval.request")
    d = await db.scalar(select(PtxDemand).where(PtxDemand.tenant_id == ctx.tenant_id, PtxDemand.demand_no == demand_no))
    if d is None:
        raise not_found(f"Bill {demand_no} not found.")
    prop = await db.get(PtxProperty, d.property_id)
    ctx.ensure_scope(prop.ward_id)
    if await db.scalar(select(PtxApproval.id).where(PtxApproval.ref_id == d.id, PtxApproval.approval_type == "DEMAND_CORRECTION", PtxApproval.status == "PENDING")):
        raise conflict("A correction for this bill is already waiting for approval.")
    amount = money(payload.amount)
    now = await _demand_total(db, d)
    if now + amount < 0:
        raise bad_request(f"This bill now stands at Rs {now}; it cannot be lowered by Rs {abs(amount)}.")
    a = PtxApproval(tenant_id=ctx.tenant_id, approval_type="DEMAND_CORRECTION", property_id=prop.id, ref_id=d.id, ref_no=d.demand_no, amount=amount,
                    reason=payload.reason, requested_by=ctx.username,
                    payload_json=dumps({"demandNo": d.demand_no, "period": d.period, "periodLabel": period_label(d.period), "billNow": float(now),
                                        "billAfter": float(now + amount), "upin": prop.upin}))
    db.add(a)
    audit(db, ctx, "DEMAND_CORRECTION_REQUESTED", "demand", d.id, None, {"demandNo": d.demand_no, "amount": float(amount), "reason": payload.reason})
    await db.commit()
    return {"message": "Correction sent for approval", "approvalId": a.id, "billNow": float(now), "billAfter": float(now + amount)}


async def post_correction(db: AsyncSession, ctx: PtxContext, a: PtxApproval) -> None:
    """Approved correction: posted against the bill's own bucket (current or arrears); anything already paid becomes advance."""
    d = await db.get(PtxDemand, a.ref_id)
    prop = await db.get(PtxProperty, d.property_id)
    now = await _demand_total(db, d)
    if now + money(a.amount) < 0:
        raise bad_request(f"The bill now stands at Rs {now}; the correction would take it below zero.")
    latest = await db.scalar(select(func.max(PtxDemand.period_from)).where(PtxDemand.property_id == prop.id))
    bucket = "CURRENT" if d.period_from == latest else "ARREAR"
    await _post_by_bucket(db, ctx, prop, bucket, "ADJUSTMENT", money(a.amount), txn_type="ADJUSTMENT", demand_id=d.id, reference_no=d.demand_no,
                          narration=f"Bill correction approved: {a.reason}", entry_date=today())
    owner = await db.scalar(select(PtxParty).where(PtxParty.property_id == prop.id, PtxParty.role == "OWNER", PtxParty.is_current.is_(True),
                                                   PtxParty.mobile_number.isnot(None)).limit(1))
    if owner is not None:
        verb = "increased" if a.amount > 0 else "reduced"
        await notify(db, ctx.tenant_id, recipient=owner.mobile_number, template="BILL_CORRECTED", property_id=prop.id, ref_no=d.demand_no,
                     dedupe_key=f"correction:{a.id}",
                     message_en=f"GWMC Property Tax: bill {d.demand_no} for {prop.upin} was {verb} by Rs {abs(money(a.amount))}. Reason: {a.reason}",
                     message_te=f"జీడబ్ల్యూఎంసీ ఆస్తి పన్ను: {prop.upin} బిల్లు {d.demand_no} రూ. {abs(money(a.amount))} మేర సవరించబడింది.")


@router.get("/demands/{demand_no}")
async def get_demand(demand_no: str, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("billing.view")
    demand = await db.scalar(select(PtxDemand).where(PtxDemand.tenant_id == ctx.tenant_id, PtxDemand.demand_no == demand_no))
    if demand is None:
        raise not_found(f"Demand {demand_no} not found.")
    prop = await db.get(PtxProperty, demand.property_id)
    ctx.ensure_scope(prop.ward_id)
    return await demand_notice(db, ctx.tenant_id, demand, prop)
