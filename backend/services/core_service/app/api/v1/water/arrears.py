"""Arrears, penalty, reminders, disconnection, reconnection, waivers and write-offs (WB-40..WB-46)."""
import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.water_calc import AGE_BANDS, age_band, age_outstanding, money
from app.db.session import get_read_db, get_write_db
from app.db.water_models import WaterApproval, WaterBill, WaterConnection, WaterLedger, WaterOrder, WaterTimeline, utcnow
from app.schemas.water import FieldProof, WaiverRequest
from .common import (
    WaterAPIRoute, WaterContext, apply_advance_credit, audit, bad_request, balances, conflict, dues_total, dumps,
    emit_event, get_setting, load_connection, loads, new_doc_no, not_found, notify, post_ledger, timeline, to_utc_naive, today,
    ward_maps, water_context,
)
from .connections import bulk_balances, record_change

router = APIRouter(route_class=WaterAPIRoute)


async def _bills_newest_first(db: AsyncSession, connection_id: str) -> List[Dict]:
    rows = (await db.execute(select(WaterBill).where(WaterBill.connection_id == connection_id)
                             .order_by(WaterBill.period_from.desc()))).scalars().all()
    return [{"id": b.id, "billNo": b.bill_no, "dueDate": b.due_date, "currentDemand": b.current_demand} for b in rows]


async def _opening_arrear_date(db: AsyncSession, connection_id: str) -> Optional[datetime.date]:
    return await db.scalar(select(func.min(WaterLedger.entry_date)).where(
        WaterLedger.connection_id == connection_id, WaterLedger.txn_type == "OPENING_ARREAR"))


async def ageing_for(db: AsyncSession, conn: WaterConnection, bal: Dict[str, Decimal], as_of: datetime.date) -> Dict:
    principal = money(max(bal["ARREAR"] + bal["CURRENT"], Decimal("0")))
    rows = age_outstanding(principal, await _bills_newest_first(db, conn.id), await _opening_arrear_date(db, conn.id), as_of)
    bands = {label: Decimal("0.00") for label, _, _ in AGE_BANDS}
    for row in rows:
        bands[age_band(row["ageDays"])] += row["unpaid"]
    oldest = max((r["ageDays"] for r in rows), default=0)
    return {"rows": rows, "bands": bands, "oldestAgeDays": oldest}


# ------------------------------------------------------------------------------------------------
# Late payment penalty (WB-40)
# ------------------------------------------------------------------------------------------------

async def run_penalty(db: AsyncSession, ctx: WaterContext, as_of: datetime.date) -> Dict:
    """Adds the notified late payment penalty once per overdue bill, on the part of that bill still unpaid."""
    rule = await get_setting(db, ctx.tenant_id, "penalty", as_of)
    percent = Decimal(str(rule.get("percent", 0)))
    grace = int(rule.get("graceDays", 0))
    if percent <= 0:
        return {"connections": 0, "penalties": 0, "amount": 0.0}
    cutoff = as_of - datetime.timedelta(days=grace)
    penalised = select(WaterLedger.bill_id).where(WaterLedger.tenant_id == ctx.tenant_id, WaterLedger.txn_type == "PENALTY",
                                                  WaterLedger.bill_id.isnot(None))
    overdue = (await db.execute(select(WaterBill).where(
        WaterBill.tenant_id == ctx.tenant_id, WaterBill.due_date < cutoff, WaterBill.id.notin_(penalised),
        ctx.ward_filter(WaterBill.ward_id)))).scalars().all()
    by_conn: Dict[str, List[WaterBill]] = {}
    for bill in overdue:
        by_conn.setdefault(bill.connection_id, []).append(bill)
    count, total = 0, Decimal("0.00")
    for conn_id, bills in by_conn.items():
        conn = await db.get(WaterConnection, conn_id)
        if conn.status == "CLOSED":
            continue
        bal = await balances(db, ctx.tenant_id, connection_id=conn.id)
        unpaid_by_bill = {r["billId"]: r["unpaid"] for r in (await ageing_for(db, conn, bal, as_of))["rows"] if r["billId"]}
        for bill in bills:
            unpaid = unpaid_by_bill.get(bill.id, Decimal("0"))
            penalty = money(unpaid * percent / Decimal("100"))
            if penalty <= 0:
                continue
            await post_ledger(db, ctx, tenant_id=ctx.tenant_id, connection_id=conn.id, txn_type="PENALTY", component="PENALTY",
                              bucket="PENALTY", amount=penalty, ward_id=conn.ward_id, bill_id=bill.id, reference_no=bill.bill_no,
                              entry_date=as_of, narration=f"Late payment penalty {percent}% on unpaid ₹{unpaid} of {bill.bill_no}")
            count += 1
            total = money(total + penalty)
    if count:
        audit(db, ctx, "PENALTY_RUN", "penalty", None, None, {"asOf": as_of, "penalties": count, "amount": float(total)})
    return {"connections": len(by_conn), "penalties": count, "amount": float(total)}


@router.post("/arrears/penalty-run")
async def penalty_run(as_of: Optional[datetime.date] = Query(None, alias="asOf"), ctx: WaterContext = Depends(water_context),
                      db: AsyncSession = Depends(get_write_db)):
    ctx.require("arrears.manage")
    as_of = as_of or today()
    if as_of > today():
        raise bad_request("Penalty cannot be added for a future date.")
    result = await run_penalty(db, ctx, as_of)
    await db.commit()
    return result


# ------------------------------------------------------------------------------------------------
# Reminders (WB-42)
# ------------------------------------------------------------------------------------------------

async def run_reminders(db: AsyncSession, ctx: WaterContext, as_of: datetime.date) -> Dict:
    rule = await get_setting(db, ctx.tenant_id, "reminders", as_of)
    before = int(rule.get("daysBeforeDue", 3))
    after_days = [int(d) for d in rule.get("daysAfterDue", [])]
    latest_cycle = select(WaterBill.connection_id, func.max(WaterBill.period_from).label("pf")).where(
        WaterBill.tenant_id == ctx.tenant_id).group_by(WaterBill.connection_id).subquery()
    bills = (await db.execute(select(WaterBill).join(latest_cycle, (latest_cycle.c.connection_id == WaterBill.connection_id)
                                                     & (latest_cycle.c.pf == WaterBill.period_from))
                              .where(ctx.ward_filter(WaterBill.ward_id)))).scalars().all()
    sent = 0
    for bill in bills:
        conn = await db.get(WaterConnection, bill.connection_id)
        if conn.status == "CLOSED" or not conn.mobile_number:
            continue
        due = dues_total(await balances(db, ctx.tenant_id, connection_id=conn.id))
        if due <= 0:
            continue
        due_text = bill.due_date.strftime("%d-%m-%Y")
        if bill.due_date - datetime.timedelta(days=before) <= as_of < bill.due_date:
            if await notify(db, ctx.tenant_id, recipient=conn.mobile_number, channel="WHATSAPP", template="REMINDER_BEFORE_DUE",
                            connection_id=conn.id, ref_no=bill.bill_no, dedupe_key=f"rem:before:{bill.id}",
                            message_en=f"GWMC Water: Rs {due} for {conn.consumer_no} is due on {due_text}. Please pay to avoid penalty.",
                            message_te=f"జీడబ్ల్యూఎంసీ నీటి సరఫరా: {conn.consumer_no} కోసం రూ. {due} గడువు {due_text}. జరిమానా లేకుండా చెల్లించండి."):
                sent += 1
        for d in after_days:
            if as_of >= bill.due_date + datetime.timedelta(days=d):
                if await notify(db, ctx.tenant_id, recipient=conn.mobile_number, channel="WHATSAPP", template="REMINDER_AFTER_DUE",
                                connection_id=conn.id, ref_no=bill.bill_no, dedupe_key=f"rem:after{d}:{bill.id}",
                                message_en=f"GWMC Water: Rs {due} for {conn.consumer_no} was due on {due_text} and is unpaid. Penalty applies.",
                                message_te=f"జీడబ్ల్యూఎంసీ నీటి సరఫరా: {conn.consumer_no} కోసం రూ. {due} గడువు {due_text} దాటింది. జరిమానా వర్తిస్తుంది."):
                    sent += 1
    return {"remindersQueued": sent}


@router.post("/arrears/reminders-run")
async def reminders_run(ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_write_db)):
    ctx.require("arrears.manage")
    result = await run_reminders(db, ctx, today())
    await db.commit()
    return result


# ------------------------------------------------------------------------------------------------
# Ageing and defaulters (WB-41)
# ------------------------------------------------------------------------------------------------

@router.get("/arrears/ageing")
async def arrears_ageing(ward_id: Optional[str] = Query(None, alias="wardId"), min_due: float = Query(0, alias="minDue"),
                         ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    if not ctx.can("arrears.manage"):
        ctx.require("reports.view")
    stmt = select(WaterConnection).where(WaterConnection.tenant_id == ctx.tenant_id, ctx.ward_filter(WaterConnection.ward_id))
    if ward_id:
        stmt = stmt.where(WaterConnection.ward_id == ward_id)
    conns = (await db.execute(stmt)).scalars().all()
    bal = await bulk_balances(db, ctx.tenant_id, [c.id for c in conns])
    wards, _ = await ward_maps(db, ctx.tenant_id)
    as_of = today()
    totals = {label: Decimal("0.00") for label, _, _ in AGE_BANDS}
    by_ward: Dict[str, Dict] = {}
    defaulters = []
    for conn in conns:
        b = bal[conn.id]
        total_due = dues_total(b)
        if total_due <= 0 or total_due < Decimal(str(min_due)):
            continue
        age = await ageing_for(db, conn, b, as_of)
        ward = wards.get(conn.ward_id, {})
        w = by_ward.setdefault(conn.ward_id, {"wardId": conn.ward_id, "wardNumber": ward.get("wardNumber"),
                                              "wardName": ward.get("wardName"), "defaulters": 0, "totalDue": Decimal("0.00"),
                                              **{label: Decimal("0.00") for label, _, _ in AGE_BANDS}})
        w["defaulters"] += 1
        w["totalDue"] += total_due
        for label, amount in age["bands"].items():
            totals[label] += amount
            w[label] += amount
        defaulters.append({
            "consumerNo": conn.consumer_no, "consumerName": conn.consumer_name, "wardNumber": ward.get("wardNumber"),
            "wardName": ward.get("wardName"), "status": conn.status, "penalty": float(max(b["PENALTY"], 0)),
            "fees": float(max(b["FEE"], 0)), "arrears": float(max(b["ARREAR"], 0)), "current": float(max(b["CURRENT"], 0)),
            "totalDue": float(total_due), "oldestAgeDays": age["oldestAgeDays"], "ageBand": age_band(age["oldestAgeDays"]),
        })
    defaulters.sort(key=lambda d: (-d["totalDue"], -d["oldestAgeDays"]))
    return {
        "asOf": as_of, "bands": [label for label, _, _ in AGE_BANDS],
        "totals": {k: float(v) for k, v in totals.items()},
        "byWard": sorted([{k: (float(v) if isinstance(v, Decimal) else v) for k, v in w.items()} for w in by_ward.values()],
                         key=lambda w: (w["wardNumber"] or 0)),
        "defaulters": defaulters,
        "note": "Principal (arrears + current) is aged by bill due date; penalty and fees are shown separately.",
    }


# ------------------------------------------------------------------------------------------------
# Disconnection notices and orders (WB-43, WB-44)
# ------------------------------------------------------------------------------------------------

def order_dict(o: WaterOrder, conn: Optional[WaterConnection] = None, wards: Optional[Dict] = None) -> Dict:
    ward = (wards or {}).get(o.ward_id, {})
    return {
        "id": o.id, "orderNo": o.order_no, "orderType": o.order_type, "status": o.status,
        "consumerNo": conn.consumer_no if conn else None, "consumerName": conn.consumer_name if conn else None,
        "address": conn.address if conn else None, "latitude": conn.latitude if conn else None,
        "longitude": conn.longitude if conn else None, "wardNumber": ward.get("wardNumber"), "wardName": ward.get("wardName"),
        "duesAtIssue": float(o.dues_at_issue) if o.dues_at_issue is not None else None, "noticeUntil": o.notice_until,
        "slaDueAt": o.sla_due_at, "slaBreached": bool(o.sla_due_at and o.status == "PENDING" and utcnow() > o.sla_due_at),
        "executedAt": o.executed_at, "executedBy": o.executed_by, "photoRef": o.photo_ref, "proofLatitude": o.latitude,
        "proofLongitude": o.longitude, "remark": o.remark, "createdAt": o.created_at,
    }


async def run_disconnection(db: AsyncSession, ctx: WaterContext, as_of: datetime.date) -> Dict:
    rule = await get_setting(db, ctx.tenant_id, "disconnection", as_of)
    threshold_amount = Decimal(str(rule.get("thresholdAmount", 0)))
    threshold_days = int(rule.get("thresholdDays", 0))
    notice_days = int(rule.get("noticeDays", 15))
    issued, listed, withdrawn = [], [], []

    open_notices = (await db.execute(select(WaterOrder).where(
        WaterOrder.tenant_id == ctx.tenant_id, WaterOrder.order_type == "NOTICE", WaterOrder.status.in_(["OPEN", "LISTED"]),
        ctx.ward_filter(WaterOrder.ward_id)))).scalars().all()
    noticed = {n.connection_id for n in open_notices}

    # 1. issue notices where dues cross the amount or age threshold
    conns = (await db.execute(select(WaterConnection).where(
        WaterConnection.tenant_id == ctx.tenant_id, WaterConnection.status == "ACTIVE",
        ctx.ward_filter(WaterConnection.ward_id)))).scalars().all()
    bal = await bulk_balances(db, ctx.tenant_id, [c.id for c in conns])
    for conn in conns:
        if conn.id in noticed:
            continue
        due = dues_total(bal[conn.id])
        if due <= 0:
            continue
        age = (await ageing_for(db, conn, bal[conn.id], as_of))["oldestAgeDays"]
        if (threshold_amount > 0 and due >= threshold_amount) or (threshold_days > 0 and age >= threshold_days):
            notice = WaterOrder(tenant_id=ctx.tenant_id, order_no=await new_doc_no(db, ctx.tenant_id, "WDN", "order_no"),
                                order_type="NOTICE", connection_id=conn.id, ward_id=conn.ward_id, status="OPEN",
                                dues_at_issue=due, notice_until=as_of + datetime.timedelta(days=notice_days),
                                remark=f"Dues ₹{due}, oldest unpaid {age} days", created_by=ctx.username)
            db.add(notice)
            await db.flush()
            timeline(db, ctx, "order", notice.id, "NOTICE_ISSUED", notice.remark)
            await notify(db, ctx.tenant_id, recipient=conn.mobile_number, template="DISCONNECTION_NOTICE", connection_id=conn.id,
                         ref_no=notice.order_no, dedupe_key=f"notice:{notice.id}",
                         message_en=f"GWMC Water: notice {notice.order_no}. Dues of Rs {due} on {conn.consumer_no} must be paid by "
                                    f"{notice.notice_until.strftime('%d-%m-%Y')} or supply will be disconnected.",
                         message_te=f"జీడబ్ల్యూఎంసీ నీటి సరఫరా: నోటీసు {notice.order_no}. {conn.consumer_no} బకాయి రూ. {due} "
                                    f"{notice.notice_until.strftime('%d-%m-%Y')} లోపు చెల్లించకపోతే సరఫరా నిలిపివేయబడుతుంది.")
            issued.append(conn.consumer_no)

    # 2. notices past their period go on the disconnection list; paid ones are withdrawn
    for notice in open_notices:
        conn = await db.get(WaterConnection, notice.connection_id)
        due = dues_total(await balances(db, ctx.tenant_id, connection_id=conn.id))
        if due <= 0 or conn.status != "ACTIVE":
            pending = (await db.execute(select(WaterOrder).where(WaterOrder.parent_order_id == notice.id,
                                                                 WaterOrder.status == "PENDING"))).scalars().all()
            for p in pending:
                p.status = "CANCELLED"
                timeline(db, ctx, "order", p.id, "CANCELLED", "Dues cleared")
            notice.status = "WITHDRAWN"
            timeline(db, ctx, "order", notice.id, "WITHDRAWN", "Dues cleared" if due <= 0 else f"Connection {conn.status}")
            withdrawn.append(conn.consumer_no)
        elif notice.status == "OPEN" and as_of >= notice.notice_until:
            notice.status = "LISTED"
            order = WaterOrder(tenant_id=ctx.tenant_id, order_no=await new_doc_no(db, ctx.tenant_id, "WDO", "order_no"),
                               order_type="DISCONNECTION", connection_id=conn.id, ward_id=conn.ward_id, status="PENDING",
                               dues_at_issue=due, parent_order_id=notice.id, created_by=ctx.username,
                               remark=f"Notice {notice.order_no} expired unpaid")
            db.add(order)
            await db.flush()
            timeline(db, ctx, "order", order.id, "LISTED_FOR_DISCONNECTION", order.remark)
            listed.append(conn.consumer_no)
    if issued or listed or withdrawn:
        audit(db, ctx, "DISCONNECTION_RUN", "order", None, None, {"asOf": as_of, "issued": issued, "listed": listed, "withdrawn": withdrawn})
    return {"noticesIssued": issued, "listedForDisconnection": listed, "withdrawn": withdrawn}


@router.post("/arrears/disconnection-run")
async def disconnection_run(ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_write_db)):
    ctx.require("arrears.manage")
    result = await run_disconnection(db, ctx, today())
    await db.commit()
    return result


@router.get("/orders")
async def list_orders(order_type: Optional[str] = Query(None, alias="type"), status: Optional[str] = Query(None),
                      ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("connection.view")
    stmt = select(WaterOrder, WaterConnection).join(WaterConnection, WaterConnection.id == WaterOrder.connection_id).where(
        WaterOrder.tenant_id == ctx.tenant_id, ctx.ward_filter(WaterOrder.ward_id))
    if order_type:
        stmt = stmt.where(WaterOrder.order_type == order_type.upper())
    if status:
        stmt = stmt.where(WaterOrder.status.in_([s.strip().upper() for s in status.split(",")]))
    rows = (await db.execute(stmt.order_by(WaterOrder.created_at.desc()).limit(500))).all()
    wards, _ = await ward_maps(db, ctx.tenant_id)
    return [order_dict(o, c, wards) for o, c in rows]


@router.post("/orders/{order_no}/execute")
async def execute_order(order_no: str, payload: FieldProof, ctx: WaterContext = Depends(water_context),
                        db: AsyncSession = Depends(get_write_db)):
    """Field staff carry out a disconnection or reconnection with photo, GPS and time (WB-44, WB-45)."""
    ctx.require("field.execute")
    order = await db.scalar(select(WaterOrder).where(WaterOrder.tenant_id == ctx.tenant_id, WaterOrder.order_no == order_no).with_for_update())
    if not order:
        raise not_found(f"Order {order_no} not found.")
    conn = await load_connection(db, ctx, connection_id=order.connection_id, for_update=True)
    if order.order_type not in ("DISCONNECTION", "RECONNECTION") or order.status != "PENDING":
        raise bad_request(f"This order is {order.order_type} / {order.status} and cannot be executed now.")
    executed_at = to_utc_naive(payload.executed_at) if payload.executed_at else utcnow()
    if order.order_type == "DISCONNECTION":
        due = dues_total(await balances(db, ctx.tenant_id, connection_id=conn.id))
        if due <= 0:
            order.status = "CANCELLED"
            timeline(db, ctx, "order", order.id, "CANCELLED", "Dues already cleared; not disconnected")
            await db.commit()
            raise bad_request("Dues have been cleared, so the disconnection was cancelled. Do not cut the supply.")
        if conn.status != "ACTIVE":
            raise bad_request(f"Connection is already {conn.status}.")
        record_change(db, ctx, conn, "status", "DISCONNECTED", f"Disconnected for arrears, order {order.order_no}")
        emit_event(db, ctx.tenant_id, "connection.disconnected", conn.id, {"consumerNo": conn.consumer_no, "kind": "ARREARS",
                                                                            "orderNo": order.order_no, "dues": float(due)})
        message_en = f"GWMC Water: supply to {conn.consumer_no} was disconnected for unpaid dues of Rs {due}."
        message_te = f"జీడబ్ల్యూఎంసీ నీటి సరఫరా: బకాయి రూ. {due} చెల్లించనందున {conn.consumer_no} సరఫరా నిలిపివేయబడింది."
        order.status = "EXECUTED"
    else:
        if conn.status != "DISCONNECTED":
            raise bad_request(f"Connection is {conn.status}; nothing to reconnect.")
        record_change(db, ctx, conn, "status", "ACTIVE", f"Reconnected, order {order.order_no}")
        emit_event(db, ctx.tenant_id, "connection.reconnected", conn.id, {"consumerNo": conn.consumer_no, "orderNo": order.order_no})
        message_en = f"GWMC Water: supply to {conn.consumer_no} has been reconnected."
        message_te = f"జీడబ్ల్యూఎంసీ నీటి సరఫరా: {conn.consumer_no} సరఫరా పునరుద్ధరించబడింది."
        order.status = "COMPLETED"
    order.executed_at = executed_at
    order.executed_by = ctx.username
    order.photo_ref, order.latitude, order.longitude = payload.photo_ref, payload.latitude, payload.longitude
    order.remark = ((order.remark + " | ") if order.remark else "") + (payload.remark or "")
    timeline(db, ctx, "order", order.id, order.status, payload.remark)
    audit(db, ctx, f"ORDER_{order.status}", "order", order.id, None, {"orderNo": order.order_no, "photoRef": payload.photo_ref,
                                                                      "latitude": payload.latitude, "longitude": payload.longitude})
    await notify(db, ctx.tenant_id, recipient=conn.mobile_number, template=f"ORDER_{order.status}", connection_id=conn.id,
                 ref_no=order.order_no, dedupe_key=f"order-done:{order.id}", message_en=message_en, message_te=message_te)
    await db.commit()
    return {"message": f"Order {order.status.lower()}", "orderNo": order.order_no, "connectionStatus": conn.status}


@router.post("/connections/{consumer_no}/reconnection", status_code=201)
async def request_reconnection(consumer_no: str, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_write_db)):
    """Raises the reconnection fee; the work order is released once all dues and the fee are paid (WB-45)."""
    if not ctx.can("payment.collect"):
        ctx.require("connection.edit")
    conn = await load_connection(db, ctx, consumer_no=consumer_no, for_update=True)
    if conn.status != "DISCONNECTED":
        raise bad_request(f"Connection is {conn.status}; reconnection applies only to connections cut for arrears.")
    if await db.scalar(select(WaterOrder.id).where(WaterOrder.connection_id == conn.id, WaterOrder.order_type == "RECONNECTION",
                                                   WaterOrder.status.in_(["AWAITING_PAYMENT", "PENDING"]))):
        raise conflict("A reconnection request is already open for this connection.")
    fee = money((await get_setting(db, ctx.tenant_id, "reconnection")).get("fee", 0))
    order = WaterOrder(tenant_id=ctx.tenant_id, order_no=await new_doc_no(db, ctx.tenant_id, "WRO", "order_no"),
                       order_type="RECONNECTION", connection_id=conn.id, ward_id=conn.ward_id, status="AWAITING_PAYMENT",
                       created_by=ctx.username, remark=f"Reconnection fee ₹{fee}")
    db.add(order)
    await db.flush()
    if fee > 0:
        await post_ledger(db, ctx, tenant_id=ctx.tenant_id, connection_id=conn.id, txn_type="FEE", component="RECONNECTION_FEE",
                          bucket="FEE", amount=fee, ward_id=conn.ward_id, reference_no=order.order_no, narration="Reconnection fee")
    await db.flush()
    await apply_advance_credit(db, ctx, conn, await get_setting(db, ctx.tenant_id, "payment.allocationOrder"),
                               f"Advance used for reconnection {order.order_no}")
    await db.flush()
    due = dues_total(await balances(db, ctx.tenant_id, connection_id=conn.id))
    if due <= 0:
        sla = float((await get_setting(db, ctx.tenant_id, "reconnection")).get("slaHours", 48))
        order.status = "PENDING"
        order.sla_due_at = utcnow() + datetime.timedelta(hours=sla)
    timeline(db, ctx, "order", order.id, "REQUESTED", order.remark)
    audit(db, ctx, "RECONNECTION_REQUESTED", "order", order.id, None, {"consumerNo": conn.consumer_no, "fee": float(fee)})
    await db.commit()
    return {"orderNo": order.order_no, "status": order.status, "amountToPay": float(max(due, Decimal("0")))}


@router.get("/orders/{order_no}/timeline")
async def order_timeline(order_no: str, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("connection.view")
    order = await db.scalar(select(WaterOrder).where(WaterOrder.tenant_id == ctx.tenant_id, WaterOrder.order_no == order_no))
    if not order:
        raise not_found("Order not found.")
    ctx.ensure_scope(order.ward_id)
    rows = (await db.execute(select(WaterTimeline).where(WaterTimeline.entity_id == order.id).order_by(WaterTimeline.at))).scalars().all()
    return [{"action": r.action, "remark": r.remark, "actor": r.actor, "at": r.at} for r in rows]


# ------------------------------------------------------------------------------------------------
# Waivers and write-offs (WB-46)
# ------------------------------------------------------------------------------------------------

@router.post("/connections/{consumer_no}/waivers", status_code=201)
async def request_waiver(consumer_no: str, payload: WaiverRequest, ctx: WaterContext = Depends(water_context),
                         db: AsyncSession = Depends(get_write_db)):
    ctx.require("approval.request")
    conn = await load_connection(db, ctx, consumer_no=consumer_no)
    bal = await balances(db, ctx.tenant_id, connection_id=conn.id)
    amount = money(payload.amount)
    if amount > bal[payload.bucket]:
        raise bad_request(f"Only ₹{max(bal[payload.bucket], Decimal('0'))} is due under {payload.bucket.lower()}.")
    if await db.scalar(select(WaterApproval.id).where(WaterApproval.connection_id == conn.id, WaterApproval.status == "PENDING",
                                                      WaterApproval.approval_type.in_(["WAIVER", "WRITE_OFF"]))):
        raise conflict("A waiver or write-off for this connection is already waiting for approval.")
    approval = WaterApproval(tenant_id=ctx.tenant_id, approval_type=payload.kind, connection_id=conn.id, ref_no=conn.consumer_no,
                             amount=amount, reason=payload.reason, requested_by=ctx.username,
                             payload_json=dumps({"bucket": payload.bucket, "consumerNo": conn.consumer_no}))
    db.add(approval)
    audit(db, ctx, f"{payload.kind}_REQUESTED", "connection", conn.id, None, payload.model_dump(mode="json"))
    await db.commit()
    return {"message": f"{payload.kind.replace('_', '-').title()} sent for approval", "approvalId": approval.id}


async def post_waiver(db: AsyncSession, ctx: WaterContext, approval: WaterApproval) -> None:
    conn = await db.get(WaterConnection, approval.connection_id)
    bucket = loads(approval.payload_json, {})["bucket"]
    bal = await balances(db, ctx.tenant_id, connection_id=conn.id)
    amount = money(approval.amount)
    if amount > bal[bucket]:
        raise bad_request(f"Only ₹{max(bal[bucket], Decimal('0'))} is now due under {bucket.lower()}; reject and raise a new request.")
    await post_ledger(db, ctx, tenant_id=ctx.tenant_id, connection_id=conn.id, txn_type=approval.approval_type,
                      component=approval.approval_type, bucket=bucket, amount=-amount, ward_id=conn.ward_id,
                      approval_id=approval.id, reference_no=conn.consumer_no, narration=approval.reason)
