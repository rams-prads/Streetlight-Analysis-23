"""Tariff management and bill generation (WB-20..WB-26, WB-NF-04, WB-NF-63)."""
import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.water_calc import (
    average_consumption, compute_bill_amounts, cycle_period, document_code, money, qty,
    validate_slabs,
)
from app.db.session import get_read_db, get_write_db
from app.db.water_models import (
    WaterApproval, WaterBill, WaterBillRun, WaterCategory, WaterConnection, WaterLedger, WaterReading,
    WaterRoute, WaterTariff, utcnow,
)
from app.schemas.water import BillAdjustmentRequest, BillRunRequest, TariffProposal
from .common import (
    WaterAPIRoute, WaterContext, apply_advance_credit, audit, bad_request, balances, conflict, dumps,
    emit_event, get_setting, loads, new_doc_no, not_found, notify, post_ledger, today,
    ward_maps, water_context,
)
from .connections import bill_dict

router = APIRouter(route_class=WaterAPIRoute)


def tariff_dict(t: WaterTariff) -> Dict:
    return {
        "id": t.id, "categoryCode": t.category_code, "version": t.version, "effectiveFrom": t.effective_from,
        "slabs": loads(t.slabs_json, []), "flatRates": loads(t.flat_rates_json, {}),
        "minimumCharge": float(t.minimum_charge), "fixedCharge": float(t.fixed_charge),
        "cessPercent": float(t.cess_percent), "freeAllowanceKl": float(t.free_allowance_kl),
        "status": t.status, "orderReference": t.order_reference, "reason": t.reason,
        "requestedBy": t.requested_by, "approvedBy": t.approved_by, "approvedAt": t.approved_at, "createdAt": t.created_at,
    }


async def tariff_in_force(db: AsyncSession, tenant_id: str, category: str, on: datetime.date) -> Optional[WaterTariff]:
    return await db.scalar(
        select(WaterTariff).where(
            WaterTariff.tenant_id == tenant_id, WaterTariff.category_code == category,
            WaterTariff.status == "APPROVED", WaterTariff.effective_from <= on)
        .order_by(WaterTariff.effective_from.desc(), WaterTariff.version.desc()).limit(1))


# ------------------------------------------------------------------------------------------------
# Tariffs (WB-20, WB-21, WB-22)
# ------------------------------------------------------------------------------------------------

@router.get("/tariffs")
async def list_tariffs(category: Optional[str] = Query(None), ctx: WaterContext = Depends(water_context),
                       db: AsyncSession = Depends(get_read_db)):
    ctx.require("tariff.view")
    stmt = select(WaterTariff).where(WaterTariff.tenant_id == ctx.tenant_id)
    if category:
        stmt = stmt.where(WaterTariff.category_code == category.upper())
    rows = (await db.execute(stmt.order_by(WaterTariff.category_code, WaterTariff.version.desc()))).scalars().all()
    in_force = {}
    for t in rows:
        current = await tariff_in_force(db, ctx.tenant_id, t.category_code, today())
        in_force[t.category_code] = current.id if current else None
    return [{**tariff_dict(t), "inForce": in_force.get(t.category_code) == t.id} for t in rows]


@router.post("/tariffs", status_code=201)
async def propose_tariff(payload: TariffProposal, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_write_db)):
    """A tariff change is only a proposal until the Commissioner approves it (WB-21)."""
    ctx.require("tariff.propose")
    code = payload.category_code.upper()
    if not await db.scalar(select(WaterCategory.id).where(WaterCategory.tenant_id == ctx.tenant_id, WaterCategory.code == code)):
        raise bad_request(f"Category {code} is not in the category list.")
    slabs = [{"uptoKl": s.upto_kl, "ratePerKl": s.rate_per_kl} for s in payload.slabs]
    try:
        validate_slabs(slabs)
    except ValueError as exc:
        raise bad_request(str(exc))
    for size, rate in payload.flat_rates.items():
        if not str(size).isdigit() or rate < 0:
            raise bad_request("Flat rates need a pipe size in mm and a rate of zero or more.")
    if payload.effective_from < today():
        raise bad_request("A new tariff cannot take effect in the past; past bills keep the tariff they were raised under.")
    version = (await db.scalar(select(func.max(WaterTariff.version)).where(
        WaterTariff.tenant_id == ctx.tenant_id, WaterTariff.category_code == code)) or 0) + 1
    tariff = WaterTariff(
        tenant_id=ctx.tenant_id, category_code=code, version=version, effective_from=payload.effective_from,
        slabs_json=dumps(slabs), flat_rates_json=dumps({str(k): v for k, v in payload.flat_rates.items()}),
        minimum_charge=money(payload.minimum_charge), fixed_charge=money(payload.fixed_charge),
        cess_percent=Decimal(str(payload.cess_percent)), free_allowance_kl=Decimal(str(payload.free_allowance_kl)),
        status="PENDING_APPROVAL", order_reference=payload.order_reference, reason=payload.reason,
        requested_by=ctx.username,
    )
    db.add(tariff)
    await db.flush()
    db.add(WaterApproval(tenant_id=ctx.tenant_id, approval_type="TARIFF", ref_id=tariff.id,
                         ref_no=f"{code} v{version}", payload_json=dumps(tariff_dict(tariff)),
                         reason=payload.reason, requested_by=ctx.username))
    audit(db, ctx, "TARIFF_PROPOSED", "tariff", tariff.id, None, tariff_dict(tariff))
    await db.commit()
    return tariff_dict(tariff)


@router.post("/tariffs/preview")
async def preview_bill(payload: Dict, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    """Bill calculator for a category and consumption, using the tariff in force (or a given tariff id)."""
    ctx.require("tariff.view")
    tariff_id = payload.get("tariffId")
    if tariff_id:
        tariff = await db.scalar(select(WaterTariff).where(WaterTariff.id == tariff_id, WaterTariff.tenant_id == ctx.tenant_id))
    else:
        tariff = await tariff_in_force(db, ctx.tenant_id, str(payload.get("categoryCode", "")).upper(), today())
    if not tariff:
        raise not_found("No approved tariff in force for this category.")
    cycle_months = int(await get_setting(db, ctx.tenant_id, "billing.cycleMonths"))
    try:
        result = compute_bill_amounts(
            basis="FLAT" if payload.get("isMetered") is False else "ACTUAL",
            consumption_kl=Decimal(str(payload.get("consumptionKl", 0))), pipe_size_mm=int(payload.get("pipeSizeMm", 15)),
            slabs=loads(tariff.slabs_json, []), flat_rates=loads(tariff.flat_rates_json, {}),
            minimum_charge=tariff.minimum_charge, fixed_charge=tariff.fixed_charge, cess_percent=tariff.cess_percent,
            free_allowance_kl=tariff.free_allowance_kl, cycle_months=cycle_months)
    except (ValueError, ArithmeticError) as exc:
        raise bad_request(str(exc))
    return {**{k: (float(v) if isinstance(v, Decimal) else v) for k, v in result.items()}, "tariff": tariff_dict(tariff)}


# ------------------------------------------------------------------------------------------------
# Bill generation (WB-16, WB-17, WB-23, WB-24, WB-NF-63)
# ------------------------------------------------------------------------------------------------

async def _bill_one(db: AsyncSession, ctx: WaterContext, conn: WaterConnection, cycle: str, bill_date: datetime.date,
                    cycle_months: int, due_days: int, order: List[str], avg_method: Dict, run_id: str) -> Dict:
    """Raises one bill, or returns why it is held. Never bills a connection twice for a cycle."""
    if await db.scalar(select(WaterBill.id).where(WaterBill.connection_id == conn.id, WaterBill.cycle == cycle)):
        return {"result": "ALREADY_BILLED"}
    period_from, period_to = cycle_period(cycle, cycle_months)
    if conn.connection_date > period_to:
        return {"result": "SKIPPED", "reason": "Connection started after this cycle"}
    tariff = await tariff_in_force(db, ctx.tenant_id, conn.category_code, period_to)
    if tariff is None:
        return {"result": "HELD", "reason": f"No approved tariff for {conn.category_code} on {period_to}"}

    reading = None
    basis = "FLAT"
    consumption = Decimal("0")
    if conn.is_metered:
        reading = await db.scalar(select(WaterReading).where(
            WaterReading.connection_id == conn.id, WaterReading.cycle == cycle,
            WaterReading.status.in_(["ACCEPTED", "PENDING_REVIEW"])).order_by(WaterReading.reading_at.desc()).limit(1))
        if reading is not None and reading.status == "PENDING_REVIEW":
            return {"result": "HELD", "reason": "Reading flagged and waiting for officer review"}
        if reading is not None and reading.reading_value is not None:
            basis = "ACTUAL"
            consumption = qty(reading.consumption_kl)
        else:
            basis = "AVERAGE"
            history = [r[0] for r in (await db.execute(select(WaterBill.consumption_kl).where(
                WaterBill.connection_id == conn.id, WaterBill.basis == "ACTUAL", WaterBill.cycle < cycle)
                .order_by(WaterBill.cycle.desc()).limit(int(avg_method.get("n", 3))))).all()]
            avg = average_consumption(history, avg_method)
            consumption = avg if avg is not None else Decimal("0")
    try:
        amounts = compute_bill_amounts(
            basis=basis, consumption_kl=consumption, pipe_size_mm=conn.pipe_size_mm,
            slabs=loads(tariff.slabs_json, []), flat_rates=loads(tariff.flat_rates_json, {}),
            minimum_charge=tariff.minimum_charge, fixed_charge=tariff.fixed_charge,
            cess_percent=tariff.cess_percent, free_allowance_kl=tariff.free_allowance_kl, cycle_months=cycle_months)
    except ValueError as exc:
        return {"result": "HELD", "reason": str(exc)}
    if basis == "AVERAGE":
        amounts["breakup"].insert(0, {"label": "AVERAGE_BASIS", "method": avg_method,
                                      "reason": reading.no_reading_reason if reading else "NO_READING"})

    bill_no = await new_doc_no(db, ctx.tenant_id, "WBL", "bill")
    bill = WaterBill(
        tenant_id=ctx.tenant_id, bill_no=bill_no, connection_id=conn.id, ward_id=conn.ward_id, cycle=cycle,
        period_from=period_from, period_to=period_to, bill_date=bill_date,
        due_date=bill_date + datetime.timedelta(days=due_days), tariff_id=tariff.id, category_code=conn.category_code,
        basis=basis, reading_id=reading.id if reading is not None and basis == "ACTUAL" else None,
        previous_reading=reading.previous_value if basis == "ACTUAL" else None,
        current_reading=reading.reading_value if basis == "ACTUAL" else None,
        consumption_kl=consumption if basis != "FLAT" else Decimal("0"),
        slab_breakup_json=dumps(amounts["breakup"]), water_charge=amounts["waterCharge"],
        fixed_charge=amounts["fixedCharge"], cess=amounts["cess"], current_demand=amounts["currentDemand"],
        total_payable=Decimal("0"), verification_code="PENDING", run_id=run_id, created_by=ctx.username,
    )
    db.add(bill)
    await db.flush()

    # 1. what was 'current' on the last bill becomes arrears
    bal = await balances(db, ctx.tenant_id, connection_id=conn.id)
    if bal["CURRENT"] != 0:
        await post_ledger(db, ctx, tenant_id=ctx.tenant_id, connection_id=conn.id, txn_type="ROLLOVER", component="WATER_CHARGE",
                          bucket="CURRENT", amount=-bal["CURRENT"], ward_id=conn.ward_id, bill_id=bill.id, entry_date=bill_date,
                          narration=f"Unpaid current dues moved to arrears on bill {bill_no}")
        await post_ledger(db, ctx, tenant_id=ctx.tenant_id, connection_id=conn.id, txn_type="ROLLOVER", component="ARREAR",
                          bucket="ARREAR", amount=bal["CURRENT"], ward_id=conn.ward_id, bill_id=bill.id, entry_date=bill_date,
                          narration=f"Unpaid current dues moved to arrears on bill {bill_no}")
    # 2. this cycle's demand, by account head (WB-IR-05)
    for component, amount in (("WATER_CHARGE", amounts["waterCharge"]), ("FIXED_CHARGE", amounts["fixedCharge"]), ("CESS", amounts["cess"])):
        if amount > 0:
            await post_ledger(db, ctx, tenant_id=ctx.tenant_id, connection_id=conn.id, txn_type="DEMAND", component=component,
                              bucket="CURRENT", amount=amount, ward_id=conn.ward_id, bill_id=bill.id, reference_no=bill_no,
                              entry_date=bill_date, narration=f"{cycle} {component.replace('_', ' ').lower()}")
    await db.flush()
    # 3. any advance paid earlier is used against the dues
    advance_used = await apply_advance_credit(db, ctx, conn, order, f"Advance adjusted on bill {bill_no}")
    await db.flush()
    after = await balances(db, ctx.tenant_id, connection_id=conn.id)
    bill.arrears = money(max(after["ARREAR"], Decimal("0")))
    bill.penalty = money(max(after["PENALTY"], Decimal("0")))
    bill.other_dues = money(max(after["FEE"], Decimal("0")))
    bill.advance_adjusted = advance_used
    bill.total_payable = money(sum((max(after[b], Decimal("0")) for b in ("PENALTY", "FEE", "ARREAR", "CURRENT")), Decimal("0")))
    bill.verification_code = document_code("BILL", bill_no, bill.total_payable)

    emit_event(db, ctx.tenant_id, "bill.raised", bill.id, {
        "consumerNo": conn.consumer_no, "billNo": bill_no, "cycle": cycle, "currentDemand": float(bill.current_demand),
        "totalPayable": float(bill.total_payable), "dueDate": bill.due_date.isoformat(), "wardId": conn.ward_id,
    })
    await notify(db, ctx.tenant_id, recipient=conn.mobile_number, channel="WHATSAPP", template="BILL_RAISED",
                 connection_id=conn.id, ref_no=bill_no, dedupe_key=f"bill:{bill.id}",
                 message_en=(f"GWMC Water bill {bill_no} for {conn.consumer_no}: Rs {bill.total_payable} due by "
                             f"{bill.due_date.strftime('%d-%m-%Y')}. View and pay: /water/bill/{bill_no}"),
                 message_te=(f"జీడబ్ల్యూఎంసీ నీటి బిల్లు {bill_no} ({conn.consumer_no}): రూ. {bill.total_payable}, "
                             f"చెల్లింపు గడువు {bill.due_date.strftime('%d-%m-%Y')}. చూడండి, చెల్లించండి: /water/bill/{bill_no}"))
    return {"result": "BILLED", "billNo": bill_no, "basis": basis, "amount": float(bill.current_demand)}


@router.post("/billing/run")
async def run_billing(payload: BillRunRequest, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_write_db)):
    """
    Generates bills route by route for a cycle (WB-23). Each route commits on its own and is recorded in
    wtr_bill_runs, so a run that stops part way can simply be started again: routes already done are
    skipped and the unique (connection, cycle) rule stops anyone being billed twice (WB-NF-63).
    Disconnected and closed connections are not billed; their arrears stay on record (WB-44).
    """
    ctx.require("billing.run")
    cycle_months = int(await get_setting(db, ctx.tenant_id, "billing.cycleMonths"))
    try:
        period_from, period_to = cycle_period(payload.cycle, cycle_months)
    except ValueError as exc:
        raise bad_request(str(exc))
    bill_date = payload.bill_date or today()
    if bill_date < period_from:
        raise bad_request("Bill date cannot be before the start of the billing cycle.")
    if period_from > today():
        raise bad_request("Cannot bill a cycle that has not started yet.")
    due_days = int(await get_setting(db, ctx.tenant_id, "billing.dueDays"))
    order = await get_setting(db, ctx.tenant_id, "payment.allocationOrder")
    avg_method = await get_setting(db, ctx.tenant_id, "billing.averageMethod")

    route_stmt = select(WaterRoute).where(WaterRoute.tenant_id == ctx.tenant_id, WaterRoute.is_active.is_(True))
    if payload.route_ids:
        route_stmt = route_stmt.where(WaterRoute.id.in_(payload.route_ids))
    route_keys = [r.id for r in (await db.execute(route_stmt.order_by(WaterRoute.code))).scalars().all()]
    if not payload.route_ids:
        route_keys.append("UNROUTED")

    summary = {"cycle": payload.cycle, "routes": [], "billsRaised": 0, "held": [], "alreadyDone": 0}
    for route_key in route_keys:
        run = await db.scalar(select(WaterBillRun).where(WaterBillRun.tenant_id == ctx.tenant_id,
                                                         WaterBillRun.cycle == payload.cycle, WaterBillRun.route_key == route_key))
        if run is not None and run.status == "DONE" and not loads(run.held_json, []):
            summary["alreadyDone"] += 1
            summary["routes"].append({"routeKey": route_key, "status": "ALREADY_DONE", "billsRaised": 0})
            continue
        if run is None:
            run = WaterBillRun(tenant_id=ctx.tenant_id, cycle=payload.cycle, route_key=route_key, started_by=ctx.username)
            db.add(run)
            await db.flush()
        run.status = "RUNNING"
        conn_stmt = select(WaterConnection).where(
            WaterConnection.tenant_id == ctx.tenant_id, WaterConnection.status == "ACTIVE",
            ctx.ward_filter(WaterConnection.ward_id))
        conn_stmt = conn_stmt.where(WaterConnection.route_id.is_(None) if route_key == "UNROUTED" else WaterConnection.route_id == route_key)
        conns = (await db.execute(conn_stmt.order_by(WaterConnection.route_sequence, WaterConnection.consumer_no))).scalars().all()
        raised, held = 0, []
        for conn in conns:
            outcome = await _bill_one(db, ctx, conn, payload.cycle, bill_date, cycle_months, due_days, order, avg_method, run.id)
            if outcome["result"] == "BILLED":
                raised += 1
            elif outcome["result"] == "HELD":
                held.append({"consumerNo": conn.consumer_no, "reason": outcome["reason"]})
        run.bills_raised = (run.bills_raised or 0) + raised
        run.held_json = dumps(held)
        run.status = "DONE"
        run.finished_at = utcnow()
        audit(db, ctx, "BILL_RUN", "bill_run", run.id, None, {"cycle": payload.cycle, "route": route_key, "raised": raised, "held": len(held)})
        await db.commit()  # each route is committed on its own (resumable)
        summary["routes"].append({"routeKey": route_key, "status": "DONE", "billsRaised": raised, "held": len(held)})
        summary["billsRaised"] += raised
        summary["held"].extend(held)
    return summary


@router.get("/billing/runs")
async def list_runs(cycle: Optional[str] = Query(None), ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("billing.view")
    stmt = select(WaterBillRun).where(WaterBillRun.tenant_id == ctx.tenant_id)
    if cycle:
        stmt = stmt.where(WaterBillRun.cycle == cycle)
    rows = (await db.execute(stmt.order_by(WaterBillRun.started_at.desc()).limit(200))).scalars().all()
    routes = {r.id: r.code for r in (await db.execute(select(WaterRoute).where(WaterRoute.tenant_id == ctx.tenant_id))).scalars().all()}
    return [{"id": r.id, "cycle": r.cycle, "routeKey": r.route_key, "routeCode": routes.get(r.route_key, r.route_key),
             "status": r.status, "billsRaised": r.bills_raised, "held": loads(r.held_json, []),
             "startedBy": r.started_by, "startedAt": r.started_at, "finishedAt": r.finished_at} for r in rows]


@router.get("/bills")
async def list_bills(cycle: Optional[str] = Query(None), ward_id: Optional[str] = Query(None, alias="wardId"),
                     q: Optional[str] = Query(None), limit: int = Query(100, ge=1, le=1000),
                     ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("billing.view")
    stmt = select(WaterBill, WaterConnection).join(WaterConnection, WaterConnection.id == WaterBill.connection_id).where(
        WaterBill.tenant_id == ctx.tenant_id, ctx.ward_filter(WaterBill.ward_id))
    if cycle:
        stmt = stmt.where(WaterBill.cycle == cycle)
    if ward_id:
        stmt = stmt.where(WaterBill.ward_id == ward_id)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(WaterBill.bill_no.ilike(like) | WaterConnection.consumer_no.ilike(like) | WaterConnection.consumer_name.ilike(like))
    rows = (await db.execute(stmt.order_by(WaterBill.bill_date.desc(), WaterBill.bill_no.desc()).limit(limit))).all()
    return [{**bill_dict(b), "consumerNo": c.consumer_no, "consumerName": c.consumer_name} for b, c in rows]


async def printable_bill(db: AsyncSession, tenant_id: str, bill: WaterBill, conn: WaterConnection) -> Dict:
    """Everything printed on a bill (WB-24): consumer, readings, slabs, arrears, penalty, due date, UPI QR."""
    wards, _ = await ward_maps(db, tenant_id)
    ward = wards.get(conn.ward_id, {})
    upi = await get_setting(db, tenant_id, "upi", bill.bill_date)
    adjustments = money(await db.scalar(select(func.coalesce(func.sum(WaterLedger.amount), 0)).where(
        WaterLedger.bill_id == bill.id, WaterLedger.txn_type == "ADJUSTMENT")) or 0)
    tariff = await db.get(WaterTariff, bill.tariff_id)
    amount = bill.total_payable
    upi_uri = f"upi://pay?pa={upi['vpa']}&pn={upi['payeeName'].replace(' ', '%20')}&am={amount}&cu=INR&tn={bill.bill_no}"
    return {
        **bill_dict(bill, adjustments),
        "consumerNo": conn.consumer_no, "consumerName": conn.consumer_name, "address": conn.address, "doorNo": conn.door_no,
        "wardNumber": ward.get("wardNumber"), "wardName": ward.get("wardName"), "zoneName": ward.get("zoneName"),
        "pipeSizeMm": conn.pipe_size_mm, "isMetered": conn.is_metered, "tariffVersion": tariff.version if tariff else None,
        "upiUri": upi_uri, "verifyPath": f"/api/v1/water/public/verify?type=BILL&no={bill.bill_no}&code={bill.verification_code}&tenant={tenant_id}",
    }


@router.get("/bills/{bill_no}")
async def get_bill(bill_no: str, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("billing.view")
    bill = await db.scalar(select(WaterBill).where(WaterBill.tenant_id == ctx.tenant_id, WaterBill.bill_no == bill_no))
    if not bill:
        raise not_found(f"Bill {bill_no} not found.")
    conn = await db.get(WaterConnection, bill.connection_id)
    ctx.ensure_scope(conn.ward_id)
    return await printable_bill(db, ctx.tenant_id, bill, conn)


@router.post("/bills/{bill_no}/adjustments", status_code=201)
async def request_bill_adjustment(bill_no: str, payload: BillAdjustmentRequest, ctx: WaterContext = Depends(water_context),
                                  db: AsyncSession = Depends(get_write_db)):
    """A bill correction is an approved adjustment entry with a reason; the bill itself is never changed (WB-26)."""
    ctx.require("approval.request")
    bill = await db.scalar(select(WaterBill).where(WaterBill.tenant_id == ctx.tenant_id, WaterBill.bill_no == bill_no))
    if not bill:
        raise not_found(f"Bill {bill_no} not found.")
    conn = await db.get(WaterConnection, bill.connection_id)
    ctx.ensure_scope(conn.ward_id)
    amount = money(payload.amount)
    if amount == 0:
        raise bad_request("Adjustment amount cannot be zero.")
    already = money(await db.scalar(select(func.coalesce(func.sum(WaterLedger.amount), 0)).where(
        WaterLedger.bill_id == bill.id, WaterLedger.txn_type == "ADJUSTMENT")) or 0)
    if amount < 0 and money(bill.current_demand + already + amount) < 0:
        raise bad_request(f"A reduction of ₹{-amount} would take the bill below zero (bill demand ₹{bill.current_demand}, earlier adjustments ₹{already}).")
    pending = await db.scalar(select(WaterApproval.id).where(WaterApproval.tenant_id == ctx.tenant_id, WaterApproval.ref_id == bill.id,
                                                             WaterApproval.approval_type == "BILL_ADJUSTMENT", WaterApproval.status == "PENDING"))
    if pending:
        raise conflict("A correction for this bill is already waiting for approval.")
    approval = WaterApproval(tenant_id=ctx.tenant_id, approval_type="BILL_ADJUSTMENT", connection_id=conn.id, ref_id=bill.id,
                             ref_no=bill.bill_no, amount=amount, reason=payload.reason, requested_by=ctx.username,
                             payload_json=dumps({"consumerNo": conn.consumer_no, "billNo": bill.bill_no, "amount": float(amount)}))
    db.add(approval)
    audit(db, ctx, "ADJUSTMENT_REQUESTED", "bill", bill.id, None, {"amount": float(amount), "reason": payload.reason})
    await db.commit()
    return {"message": "Correction sent for approval", "approvalId": approval.id}


async def post_bill_adjustment(db: AsyncSession, ctx: WaterContext, approval: WaterApproval) -> None:
    """Called when a bill correction is approved: posts the adjustment against the right dues bucket."""
    bill = await db.get(WaterBill, approval.ref_id)
    conn = await db.get(WaterConnection, bill.connection_id)
    latest = await db.scalar(select(WaterBill.id).where(WaterBill.connection_id == conn.id).order_by(WaterBill.period_from.desc()).limit(1))
    bucket = "CURRENT" if latest == bill.id else "ARREAR"
    amount = money(approval.amount)
    bal = await balances(db, ctx.tenant_id, connection_id=conn.id)
    if amount < 0 and bal[bucket] + amount < 0:
        # the bill was (partly) paid already: the part that was paid becomes advance credit
        within = -bal[bucket] if bal[bucket] > 0 else Decimal("0")
        if within < 0:
            await post_ledger(db, ctx, tenant_id=ctx.tenant_id, connection_id=conn.id, txn_type="ADJUSTMENT", component="ADJUSTMENT",
                              bucket=bucket, amount=within, ward_id=conn.ward_id, bill_id=bill.id, approval_id=approval.id,
                              reference_no=bill.bill_no, narration=approval.reason)
        rest = money(amount - within)
        await post_ledger(db, ctx, tenant_id=ctx.tenant_id, connection_id=conn.id, txn_type="ADJUSTMENT", component="ADJUSTMENT",
                          bucket="ADVANCE", amount=rest, ward_id=conn.ward_id, bill_id=bill.id, approval_id=approval.id,
                          reference_no=bill.bill_no, narration=f"{approval.reason} (already paid; held as advance)")
    else:
        await post_ledger(db, ctx, tenant_id=ctx.tenant_id, connection_id=conn.id, txn_type="ADJUSTMENT", component="ADJUSTMENT",
                          bucket=bucket, amount=amount, ward_id=conn.ward_id, bill_id=bill.id, approval_id=approval.id,
                          reference_no=bill.bill_no, narration=approval.reason)
