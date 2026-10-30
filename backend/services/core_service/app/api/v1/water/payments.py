"""Demand, collection and receipts (WB-30..WB-38, WB-NF-03, WB-NF-32)."""
import datetime
import uuid
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.water_calc import allocate_payment, document_code, mask_mobile, money
from app.db.session import get_read_db, get_write_db
from app.db.water_models import (
    WaterApplication, WaterApproval, WaterBill, WaterConnection, WaterDayClose, WaterGatewayStub, WaterLedger, WaterOrder,
    WaterPaymentIntent, WaterReceipt, WaterReconciliation, utcnow,
)
from app.schemas.water import (
    ChequeReturnRequest, DayCloseSubmit, DayCloseVerify, GatewayCallback, OnlineInitiate, PaymentCreate,
    ReceiptCancelRequest, ReconciliationRequest, RefundRequest, StubGatewayPay,
)
from .common import (
    WaterAPIRoute, WaterContext, audit, bad_request, balances, bucket_component, conflict, dues_total, dumps,
    emit_event, get_setting, load_connection, loads, local_day_start_utc, new_doc_no, not_found, notify, post_ledger, timeline,
    today,
    water_context,
)

router = APIRouter(route_class=WaterAPIRoute)

ONLINE_MODES = {"ONLINE", "UPI", "BBPS"}
ONLINE_CHANNELS = {"PORTAL", "APP", "BBPS", "WHATSAPP"}


def receipt_dict(r: WaterReceipt, consumer_no: Optional[str] = None, application_no: Optional[str] = None) -> Dict:
    return {
        "id": r.id, "receiptNo": r.receipt_no, "consumerNo": consumer_no, "applicationNo": application_no,
        "amount": float(r.amount), "paymentMode": r.payment_mode, "channel": r.channel, "instrumentNo": r.instrument_no,
        "instrumentBank": r.instrument_bank, "instrumentDate": r.instrument_date, "gatewayTxnId": r.gateway_txn_id,
        "payerName": r.payer_name, "payerMobileMasked": mask_mobile(r.payer_mobile),
        "allocation": loads(r.allocation_json, {}), "status": r.status, "statusReason": r.status_reason,
        "verificationCode": r.verification_code, "collectedBy": r.collected_by, "receiptDate": r.receipt_date,
        "createdAt": r.created_at, "dayCloseId": r.day_close_id,
        "verifyPath": f"/api/v1/water/public/verify?type=RECEIPT&no={r.receipt_no}&code={r.verification_code}&tenant={r.tenant_id}",
    }


async def _release_reconnection_orders(db: AsyncSession, ctx: WaterContext, conn: WaterConnection) -> None:
    """Once dues and the reconnection fee are paid, the reconnection work order starts its SLA (WB-45)."""
    waiting = (await db.execute(select(WaterOrder).where(
        WaterOrder.connection_id == conn.id, WaterOrder.order_type == "RECONNECTION",
        WaterOrder.status == "AWAITING_PAYMENT"))).scalars().all()
    if not waiting:
        return
    if dues_total(await balances(db, ctx.tenant_id, connection_id=conn.id)) > 0:
        return
    sla_hours = float((await get_setting(db, ctx.tenant_id, "reconnection")).get("slaHours", 48))
    for order in waiting:
        order.status = "PENDING"
        order.sla_due_at = utcnow() + datetime.timedelta(hours=sla_hours)
        timeline(db, ctx, "order", order.id, "DUES_CLEARED", f"Reconnection work order released; SLA {sla_hours:g} h")


async def _current_split(db: AsyncSession, conn: WaterConnection, part: Decimal) -> List[tuple]:
    """
    Splits a payment towards the current bill across its account heads (water charge, fixed charge, cess) in the
    same proportion as the latest bill, so the account-head summary shows collection against each head (WB-65).
    Rounding is kept exact: cess and fixed charge are rounded, the water charge takes the remainder.
    """
    bill = await db.scalar(select(WaterBill).where(WaterBill.connection_id == conn.id).order_by(WaterBill.period_from.desc()).limit(1))
    if bill is None or money(bill.current_demand) <= 0:
        return [("WATER_CHARGE", part)]
    total = money(bill.current_demand)
    cess = money(part * money(bill.cess) / total)
    fixed = money(part * money(bill.fixed_charge) / total)
    water = money(part - cess - fixed)
    if water < 0:  # only possible for a few paise; keep the whole amount on one head
        return [("WATER_CHARGE", part)]
    return [(c, v) for c, v in (("WATER_CHARGE", water), ("FIXED_CHARGE", fixed), ("CESS", cess)) if v > 0]


async def take_payment(db: AsyncSession, ctx: WaterContext, *, conn: Optional[WaterConnection], app: Optional[WaterApplication],
                       amount: Decimal, mode: str, channel: str, idempotency_key: str, instrument_no: Optional[str] = None,
                       instrument_bank: Optional[str] = None, instrument_date: Optional[datetime.date] = None,
                       gateway_txn_id: Optional[str] = None, payer_name: Optional[str] = None,
                       payer_mobile: Optional[str] = None, on_date: Optional[datetime.date] = None) -> WaterReceipt:
    """
    Records a payment and issues its receipt in one transaction. The idempotency key (client request id or
    gateway order id) guarantees a payment is never recorded twice (WB-NF-32).
    """
    existing = await db.scalar(select(WaterReceipt).where(WaterReceipt.tenant_id == ctx.tenant_id,
                                                          WaterReceipt.idempotency_key == idempotency_key))
    if existing:
        return existing
    amount = money(amount)
    if amount <= 0:
        raise bad_request("Amount must be more than zero.")
    if mode in ("CHEQUE", "DD") and not (instrument_no and instrument_bank and instrument_date):
        raise bad_request("Cheque / DD number, bank and date are required.")

    receipt = WaterReceipt(
        tenant_id=ctx.tenant_id, receipt_no=await new_doc_no(db, ctx.tenant_id, "WRC", "receipt"),
        connection_id=conn.id if conn else None, application_id=app.id if app else None,
        ward_id=conn.ward_id if conn else app.ward_id, amount=amount, payment_mode=mode, channel=channel,
        instrument_no=instrument_no, instrument_bank=instrument_bank, instrument_date=instrument_date,
        gateway_txn_id=gateway_txn_id, idempotency_key=idempotency_key, payer_name=payer_name, payer_mobile=payer_mobile,
        collected_by=ctx.username, receipt_date=on_date or today(), verification_code="PENDING",
    )
    db.add(receipt)
    await db.flush()
    receipt.verification_code = document_code("RECEIPT", receipt.receipt_no, amount)
    allocation: Dict[str, float] = {}

    if conn is not None:
        bal = await balances(db, ctx.tenant_id, connection_id=conn.id)
        order = await get_setting(db, ctx.tenant_id, "payment.allocationOrder")
        try:
            applied = allocate_payment(amount, bal, order)
        except ValueError as exc:
            raise bad_request(str(exc))
        for bucket, part in applied.items():
            split = await _current_split(db, conn, part) if bucket == "CURRENT" else [(bucket_component(bucket), part)]
            for component, piece in split:
                await post_ledger(db, ctx, tenant_id=ctx.tenant_id, connection_id=conn.id, txn_type="PAYMENT",
                                  component=component, bucket=bucket, amount=-piece, ward_id=conn.ward_id,
                                  payment_mode=mode, reference_no=receipt.receipt_no, receipt_id=receipt.id,
                                  entry_date=on_date, narration=f"Receipt {receipt.receipt_no}")
            allocation[bucket] = float(part)
        await db.flush()
        await _release_reconnection_orders(db, ctx, conn)
        target_mobile = payer_mobile or conn.mobile_number
        ref_label = conn.consumer_no
        emit_event(db, ctx.tenant_id, "payment.received", receipt.id, {
            "consumerNo": conn.consumer_no, "receiptNo": receipt.receipt_no, "amount": float(amount), "mode": mode,
            "channel": channel, "allocation": allocation, "wardId": conn.ward_id,
        })
    else:
        # application charges are paid in full, component by component, so each lands on its own account head
        rows = (await db.execute(select(WaterLedger.component, func.sum(WaterLedger.amount)).where(
            WaterLedger.application_id == app.id, WaterLedger.connection_id.is_(None), WaterLedger.bucket == "FEE")
            .group_by(WaterLedger.component))).all()
        outstanding = {component: money(total) for component, total in rows if money(total) > 0}
        due = money(sum(outstanding.values(), Decimal("0")))
        if due <= 0:
            raise bad_request("Nothing is due on this application.")
        if amount != due:
            raise bad_request(f"Application charges must be paid in full: ₹{due} is due.")
        for component, part in sorted(outstanding.items()):
            await post_ledger(db, ctx, tenant_id=ctx.tenant_id, connection_id=None, application_id=app.id, txn_type="PAYMENT",
                              component=component, bucket="FEE", amount=-part, ward_id=app.ward_id, payment_mode=mode,
                              reference_no=receipt.receipt_no, receipt_id=receipt.id, entry_date=on_date,
                              narration=f"Receipt {receipt.receipt_no}")
            allocation[component] = float(part)
        app.amount_paid = money((app.amount_paid or 0) + amount)
        timeline(db, ctx, "application", app.id, "PAYMENT_RECEIVED", f"Receipt {receipt.receipt_no} ₹{amount}")
        target_mobile = payer_mobile or app.mobile_number
        ref_label = app.application_no
        emit_event(db, ctx.tenant_id, "payment.received", receipt.id, {
            "applicationNo": app.application_no, "receiptNo": receipt.receipt_no, "amount": float(amount), "mode": mode,
            "channel": channel, "allocation": allocation, "wardId": app.ward_id,
        })

    receipt.allocation_json = dumps(allocation)
    audit(db, ctx, "PAYMENT_RECEIVED", "receipt", receipt.id, None, {
        "receiptNo": receipt.receipt_no, "ref": ref_label, "amount": float(amount), "mode": mode, "channel": channel,
    })
    await notify(db, ctx.tenant_id, recipient=target_mobile, template="RECEIPT", channel="SMS", ref_no=receipt.receipt_no,
                 connection_id=conn.id if conn else None, dedupe_key=f"receipt:{receipt.id}",
                 message_en=f"GWMC Water: received Rs {amount} for {ref_label}. Receipt {receipt.receipt_no}. Verify code {receipt.verification_code}.",
                 message_te=f"జీడబ్ల్యూఎంసీ నీటి సరఫరా: {ref_label} కోసం రూ. {amount} అందింది. రసీదు {receipt.receipt_no}. ధృవీకరణ కోడ్ {receipt.verification_code}.")
    return receipt


async def _target(db: AsyncSession, ctx: WaterContext, consumer_no: Optional[str], application_no: Optional[str]):
    if bool(consumer_no) == bool(application_no):
        raise bad_request("Give either a consumer number or an application number.")
    if consumer_no:
        conn = await load_connection(db, ctx, consumer_no=consumer_no, for_update=True)
        return conn, None
    app = await db.scalar(select(WaterApplication).where(WaterApplication.tenant_id == ctx.tenant_id,
                                                         WaterApplication.application_no == application_no).with_for_update())
    if not app:
        raise not_found(f"Application {application_no} not found.")
    if app.status != "IN_PROGRESS":
        raise bad_request(f"Application is {app.status}; no payment is due.")
    return None, app


@router.post("/payments", status_code=201)
async def collect_payment(payload: PaymentCreate, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_write_db)):
    """Counter, field staff and CSC collection: cash, cheque, demand draft, UPI QR (WB-30). Part payments allowed (WB-32)."""
    ctx.require("payment.collect")
    if payload.payment_mode in ("ONLINE", "BBPS"):
        raise bad_request("Online and BBPS payments are confirmed by the gateway, not entered at a counter.")
    conn, app = await _target(db, ctx, payload.consumer_no, payload.application_no)
    if conn is not None and conn.status == "CLOSED":
        raise bad_request("This connection is permanently closed.")
    receipt = await take_payment(
        db, ctx, conn=conn, app=app, amount=Decimal(str(payload.amount)), mode=payload.payment_mode, channel=payload.channel,
        idempotency_key=f"COUNTER:{payload.idempotency_key}", instrument_no=payload.instrument_no,
        instrument_bank=payload.instrument_bank, instrument_date=payload.instrument_date,
        payer_name=payload.payer_name, payer_mobile=payload.payer_mobile)
    await db.commit()
    return receipt_dict(receipt, conn.consumer_no if conn else None, app.application_no if app else None)


# ------------------------------------------------------------------------------------------------
# Online payment through the gateway stand-in (WB-30, WB-35, WB-IR-10)
# ------------------------------------------------------------------------------------------------

@router.post("/payments/online/initiate", status_code=201)
async def initiate_online(payload: OnlineInitiate, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_write_db)):
    ctx.require("payment.online")
    if bool(payload.consumer_no) == bool(payload.application_no):
        raise bad_request("Give either a consumer number or an application number.")
    if payload.consumer_no:
        conn = await db.scalar(select(WaterConnection).where(WaterConnection.tenant_id == ctx.tenant_id,
                                                             WaterConnection.consumer_no == payload.consumer_no.strip().upper()))
        if conn is None:
            raise not_found("Consumer number not found.")
        if conn.status == "CLOSED":
            raise bad_request("This connection is permanently closed.")
        app = None
    else:
        conn = None
        app = await db.scalar(select(WaterApplication).where(WaterApplication.tenant_id == ctx.tenant_id,
                                                             WaterApplication.application_no == payload.application_no))
        if app is None or app.status != "IN_PROGRESS":
            raise not_found("Application not found or not awaiting payment.")
        due = dues_total(await balances(db, ctx.tenant_id, application_id=app.id))
        if due <= 0:
            raise bad_request("Nothing is due on this application.")
        if money(payload.amount) != due:
            raise bad_request(f"Application charges must be paid in full: ₹{due} is due.")
    intent = WaterPaymentIntent(
        tenant_id=ctx.tenant_id, order_id=await new_doc_no(db, ctx.tenant_id, "WPO", "order"),
        connection_id=conn.id if conn else None, application_id=app.id if app else None,
        amount=money(payload.amount), channel=payload.channel, created_by=ctx.username,
    )
    db.add(intent)
    audit(db, ctx, "ONLINE_PAYMENT_INITIATED", "payment_intent", intent.id, None, {"orderId": intent.order_id, "amount": payload.amount})
    await db.commit()
    return {"orderId": intent.order_id, "amount": float(intent.amount), "status": intent.status,
            "gateway": "STAND_IN", "note": "Local stand-in gateway (WB-IR-10). Replace with the real gateway adapter."}


async def _complete_intent(db: AsyncSession, ctx: WaterContext, intent: WaterPaymentIntent, gateway_txn_id: str, via: str) -> WaterReceipt:
    conn = await db.get(WaterConnection, intent.connection_id) if intent.connection_id else None
    app = await db.get(WaterApplication, intent.application_id) if intent.application_id else None
    receipt = await take_payment(db, ctx, conn=conn, app=app, amount=Decimal(str(intent.amount)),
                                 mode="ONLINE" if intent.channel != "BBPS" else "BBPS", channel=intent.channel,
                                 idempotency_key=f"ORDER:{intent.order_id}", gateway_txn_id=gateway_txn_id)
    intent.status = "SUCCESS"
    intent.gateway_txn_id = gateway_txn_id
    intent.receipt_id = receipt.id
    intent.completed_via = via
    intent.completed_at = utcnow()
    return receipt


@router.post("/payments/online/stub-gateway")
async def stub_gateway(payload: StubGatewayPay, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_write_db)):
    """
    Stand-in for the bank's payment page. SUCCESS sends the confirmation straight back; SUCCESS_NO_CALLBACK
    simulates money taken but confirmation lost, which the status check then completes (WB-35).
    """
    ctx.require("payment.online")
    intent = await db.scalar(select(WaterPaymentIntent).where(WaterPaymentIntent.tenant_id == ctx.tenant_id,
                                                              WaterPaymentIntent.order_id == payload.order_id).with_for_update())
    if intent is None:
        raise not_found("Payment order not found.")
    if await db.get(WaterGatewayStub, payload.order_id):
        raise conflict("This order was already processed by the gateway.")
    captured = payload.outcome != "FAILURE"
    txn = f"STUB{uuid.uuid4().hex[:14].upper()}" if captured else None
    db.add(WaterGatewayStub(order_id=intent.order_id, tenant_id=ctx.tenant_id, gateway_txn_id=txn, amount=intent.amount,
                            status="CAPTURED" if captured else "FAILED"))
    await db.commit()
    if payload.outcome == "SUCCESS_NO_CALLBACK":
        return {"orderId": intent.order_id, "gatewayStatus": "CAPTURED", "callback": "LOST",
                "message": "Money taken at the gateway but the confirmation did not reach the system. Run the status check."}
    return await gateway_callback(GatewayCallback(order_id=intent.order_id, gateway_txn_id=txn,
                                                  status="SUCCESS" if captured else "FAILURE"), ctx, db)


@router.post("/payments/online/callback")
async def gateway_callback(payload: GatewayCallback, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_write_db)):
    """Gateway confirmation. Safe to receive more than once: the receipt is issued only the first time (WB-NF-32)."""
    intent = await db.scalar(select(WaterPaymentIntent).where(WaterPaymentIntent.tenant_id == ctx.tenant_id,
                                                              WaterPaymentIntent.order_id == payload.order_id).with_for_update())
    if intent is None:
        raise not_found("Payment order not found.")
    if intent.status == "SUCCESS":
        receipt = await db.get(WaterReceipt, intent.receipt_id)
        return {"orderId": intent.order_id, "status": "SUCCESS", "receipt": receipt_dict(receipt), "duplicate": True}
    stub = await db.get(WaterGatewayStub, intent.order_id)
    if payload.status == "SUCCESS":
        # never trust the callback alone: confirm with the gateway record
        if stub is None or stub.status != "CAPTURED" or money(stub.amount) != money(intent.amount):
            raise bad_request("Gateway has no matching captured payment for this order.")
        receipt = await _complete_intent(db, ctx, intent, stub.gateway_txn_id, "CALLBACK")
        await db.commit()
        conn_no = (await db.get(WaterConnection, intent.connection_id)).consumer_no if intent.connection_id else None
        return {"orderId": intent.order_id, "status": "SUCCESS", "receipt": receipt_dict(receipt, conn_no)}
    intent.status = "FAILED"
    intent.completed_at = utcnow()
    await db.commit()
    return {"orderId": intent.order_id, "status": "FAILED"}


async def reconcile_pending_intents(db: AsyncSession, ctx: WaterContext) -> Dict:
    """Asks the gateway about orders still waiting for confirmation and completes them (WB-35)."""
    pending = (await db.execute(select(WaterPaymentIntent).where(
        WaterPaymentIntent.tenant_id == ctx.tenant_id, WaterPaymentIntent.status == "INITIATED").with_for_update())).scalars().all()
    completed, failed = [], []
    for intent in pending:
        stub = await db.get(WaterGatewayStub, intent.order_id)
        if stub is None:
            continue
        if stub.status == "CAPTURED" and money(stub.amount) == money(intent.amount):
            receipt = await _complete_intent(db, ctx, intent, stub.gateway_txn_id, "STATUS_CHECK")
            completed.append({"orderId": intent.order_id, "receiptNo": receipt.receipt_no})
        elif stub.status == "FAILED":
            intent.status = "FAILED"
            intent.completed_at = utcnow()
            failed.append(intent.order_id)
    return {"checked": len(pending), "completed": completed, "failed": failed}


@router.post("/payments/online/status-check")
async def run_status_check(ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_write_db)):
    ctx.require("payment.online")
    result = await reconcile_pending_intents(db, ctx)
    await db.commit()
    return result


@router.get("/payments/online/{order_id}")
async def get_intent(order_id: str, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("payment.online")
    intent = await db.scalar(select(WaterPaymentIntent).where(WaterPaymentIntent.tenant_id == ctx.tenant_id,
                                                              WaterPaymentIntent.order_id == order_id))
    if intent is None:
        raise not_found("Payment order not found.")
    receipt = await db.get(WaterReceipt, intent.receipt_id) if intent.receipt_id else None
    return {"orderId": intent.order_id, "amount": float(intent.amount), "status": intent.status,
            "completedVia": intent.completed_via, "receipt": receipt_dict(receipt) if receipt else None}


# ------------------------------------------------------------------------------------------------
# Receipts (WB-31, WB-33, WB-36)
# ------------------------------------------------------------------------------------------------

@router.get("/receipts")
async def list_receipts(date_from: Optional[datetime.date] = Query(None, alias="from"), date_to: Optional[datetime.date] = Query(None, alias="to"),
                        q: Optional[str] = Query(None), mode: Optional[str] = Query(None), collector: Optional[str] = Query(None),
                        limit: int = Query(200, ge=1, le=2000),
                        ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("billing.view")
    stmt = (select(WaterReceipt, WaterConnection.consumer_no, WaterApplication.application_no)
            .outerjoin(WaterConnection, WaterConnection.id == WaterReceipt.connection_id)
            .outerjoin(WaterApplication, WaterApplication.id == WaterReceipt.application_id)
            .where(WaterReceipt.tenant_id == ctx.tenant_id, ctx.ward_filter(WaterReceipt.ward_id)))
    if date_from:
        stmt = stmt.where(WaterReceipt.receipt_date >= date_from)
    if date_to:
        stmt = stmt.where(WaterReceipt.receipt_date <= date_to)
    if mode:
        stmt = stmt.where(WaterReceipt.payment_mode == mode.upper())
    if collector:
        stmt = stmt.where(WaterReceipt.collected_by == collector)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(WaterReceipt.receipt_no.ilike(like), WaterConnection.consumer_no.ilike(like),
                              WaterApplication.application_no.ilike(like), WaterReceipt.gateway_txn_id.ilike(like)))
    rows = (await db.execute(stmt.order_by(WaterReceipt.created_at.desc()).limit(limit))).all()
    return [receipt_dict(r, c, a) for r, c, a in rows]


@router.get("/receipts/{receipt_no}")
async def get_receipt(receipt_no: str, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("billing.view")
    receipt = await db.scalar(select(WaterReceipt).where(WaterReceipt.tenant_id == ctx.tenant_id, WaterReceipt.receipt_no == receipt_no))
    if not receipt:
        raise not_found(f"Receipt {receipt_no} not found.")
    ctx.ensure_scope(receipt.ward_id)
    conn = await db.get(WaterConnection, receipt.connection_id) if receipt.connection_id else None
    app = await db.get(WaterApplication, receipt.application_id) if receipt.application_id else None
    data = receipt_dict(receipt, conn.consumer_no if conn else None, app.application_no if app else None)
    data["consumerName"] = conn.consumer_name if conn else (app.applicant_name if app else None)
    data["address"] = conn.address if conn else (app.address if app else None)
    return data


@router.post("/receipts/{receipt_no}/cancel", status_code=201)
async def request_receipt_cancellation(receipt_no: str, payload: ReceiptCancelRequest, ctx: WaterContext = Depends(water_context),
                                       db: AsyncSession = Depends(get_write_db)):
    """A wrong receipt is never edited; it is cancelled through an approved reversal (WB-33)."""
    ctx.require("approval.request")
    receipt = await db.scalar(select(WaterReceipt).where(WaterReceipt.tenant_id == ctx.tenant_id, WaterReceipt.receipt_no == receipt_no))
    if not receipt:
        raise not_found(f"Receipt {receipt_no} not found.")
    ctx.ensure_scope(receipt.ward_id)
    if receipt.status != "VALID":
        raise bad_request(f"Receipt is already {receipt.status}.")
    if await db.scalar(select(WaterApproval.id).where(WaterApproval.ref_id == receipt.id, WaterApproval.status == "PENDING")):
        raise conflict("A cancellation for this receipt is already waiting for approval.")
    approval = WaterApproval(tenant_id=ctx.tenant_id, approval_type="RECEIPT_CANCEL", connection_id=receipt.connection_id,
                             ref_id=receipt.id, ref_no=receipt.receipt_no, amount=receipt.amount, reason=payload.reason,
                             requested_by=ctx.username, payload_json=dumps({"receiptNo": receipt.receipt_no, "amount": float(receipt.amount)}))
    db.add(approval)
    audit(db, ctx, "RECEIPT_CANCEL_REQUESTED", "receipt", receipt.id, None, {"reason": payload.reason})
    await db.commit()
    return {"message": "Cancellation sent for approval", "approvalId": approval.id}


async def reverse_receipt(db: AsyncSession, ctx: WaterContext, receipt: WaterReceipt, new_status: str, reason: str,
                          approval_id: Optional[str] = None) -> None:
    """Posts the exact opposite of every ledger row of a receipt and marks it CANCELLED or BOUNCED."""
    rows = (await db.execute(select(WaterLedger).where(WaterLedger.receipt_id == receipt.id, WaterLedger.is_reversal.is_(False)))).scalars().all()
    for row in rows:
        await post_ledger(db, ctx, tenant_id=ctx.tenant_id, connection_id=row.connection_id, application_id=row.application_id,
                          txn_type=row.txn_type, component=row.component, bucket=row.bucket, amount=-row.amount,
                          ward_id=row.ward_id, payment_mode=row.payment_mode, reference_no=receipt.receipt_no,
                          receipt_id=receipt.id, approval_id=approval_id, is_reversal=True, reversal_of_id=row.id,
                          narration=f"Reversal ({new_status.lower()}): {reason}")
    receipt.status = new_status
    receipt.status_reason = reason
    if receipt.application_id:
        app = await db.get(WaterApplication, receipt.application_id)
        app.amount_paid = money((app.amount_paid or 0) - receipt.amount)
        timeline(db, ctx, "application", app.id, f"RECEIPT_{new_status}", f"{receipt.receipt_no}: {reason}")
    emit_event(db, ctx.tenant_id, "receipt.cancelled", receipt.id, {
        "receiptNo": receipt.receipt_no, "amount": float(receipt.amount), "status": new_status, "reason": reason,
    })


@router.post("/receipts/{receipt_no}/cheque-return")
async def cheque_return(receipt_no: str, payload: ChequeReturnRequest, ctx: WaterContext = Depends(water_context),
                        db: AsyncSession = Depends(get_write_db)):
    """Cheque/DD returned by the bank: reverse the receipt, add the notified charge, inform the payer (WB-36)."""
    ctx.require("payment.cheque_return")
    receipt = await db.scalar(select(WaterReceipt).where(WaterReceipt.tenant_id == ctx.tenant_id,
                                                         WaterReceipt.receipt_no == receipt_no).with_for_update())
    if not receipt:
        raise not_found(f"Receipt {receipt_no} not found.")
    if receipt.payment_mode not in ("CHEQUE", "DD"):
        raise bad_request("Only cheque or demand draft receipts can be returned.")
    if receipt.status != "VALID":
        raise bad_request(f"Receipt is already {receipt.status}.")
    await reverse_receipt(db, ctx, receipt, "BOUNCED", f"Cheque returned: {payload.reason}")
    charge = money(await get_setting(db, ctx.tenant_id, "fees.chequeReturnCharge"))
    conn = await db.get(WaterConnection, receipt.connection_id) if receipt.connection_id else None
    if conn is not None and charge > 0:
        await post_ledger(db, ctx, tenant_id=ctx.tenant_id, connection_id=conn.id, txn_type="FEE", component="CHEQUE_RETURN_CHARGE",
                          bucket="FEE", amount=charge, ward_id=conn.ward_id, reference_no=receipt.receipt_no,
                          entry_date=payload.return_date or today(), narration=f"Cheque return charge for {receipt.receipt_no}")
    mobile = receipt.payer_mobile or (conn.mobile_number if conn else None)
    await notify(db, ctx.tenant_id, recipient=mobile, template="CHEQUE_RETURNED", ref_no=receipt.receipt_no,
                 connection_id=conn.id if conn else None, dedupe_key=f"cheque-return:{receipt.id}",
                 message_en=f"GWMC Water: cheque {receipt.instrument_no} for receipt {receipt.receipt_no} was returned. "
                            f"Rs {receipt.amount} is due again{f' with a charge of Rs {charge}' if conn and charge > 0 else ''}.",
                 message_te=f"జీడబ్ల్యూఎంసీ నీటి సరఫరా: రసీదు {receipt.receipt_no} చెక్కు {receipt.instrument_no} తిరిగి వచ్చింది. "
                            f"రూ. {receipt.amount} మళ్లీ చెల్లించాలి{f', అదనపు ఛార్జీ రూ. {charge}' if conn and charge > 0 else ''}.")
    audit(db, ctx, "CHEQUE_RETURNED", "receipt", receipt.id, {"status": "VALID"}, {"status": "BOUNCED", "charge": float(charge), "reason": payload.reason})
    await db.commit()
    return {"message": "Receipt reversed and payer informed", "receiptNo": receipt.receipt_no, "chargeAdded": float(charge) if conn else 0.0}


# ------------------------------------------------------------------------------------------------
# Day-end closing (WB-37)
# ------------------------------------------------------------------------------------------------

def day_close_dict(d: WaterDayClose) -> Dict:
    return {"id": d.id, "collector": d.collector, "closeDate": d.close_date, "receiptCount": d.receipt_count,
            "systemCash": float(d.system_cash), "systemNonCash": float(d.system_non_cash),
            "declaredCash": float(d.declared_cash), "receivedCash": float(d.received_cash) if d.received_cash is not None else None,
            "variance": float(d.variance) if d.variance is not None else None, "status": d.status,
            "verifiedBy": d.verified_by, "verifiedAt": d.verified_at, "remark": d.remark}


@router.post("/day-close", status_code=201)
async def submit_day_close(payload: DayCloseSubmit, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_write_db)):
    ctx.require("dayclose.submit")
    if payload.close_date > today():
        raise bad_request("Cannot close a future day.")
    if await db.scalar(select(WaterDayClose.id).where(WaterDayClose.tenant_id == ctx.tenant_id, WaterDayClose.collector == ctx.username,
                                                      WaterDayClose.close_date == payload.close_date)):
        raise conflict("This day is already closed for you.")
    receipts = (await db.execute(select(WaterReceipt).where(
        WaterReceipt.tenant_id == ctx.tenant_id, WaterReceipt.collected_by == ctx.username,
        WaterReceipt.receipt_date == payload.close_date, WaterReceipt.day_close_id.is_(None),
        WaterReceipt.channel.notin_(list(ONLINE_CHANNELS))))).scalars().all()
    valid = [r for r in receipts if r.status != "CANCELLED"]
    cash = money(sum((r.amount for r in valid if r.payment_mode == "CASH"), Decimal("0")))
    non_cash = money(sum((r.amount for r in valid if r.payment_mode != "CASH"), Decimal("0")))
    close = WaterDayClose(tenant_id=ctx.tenant_id, collector=ctx.username, close_date=payload.close_date,
                          receipt_count=len(valid), system_cash=cash, system_non_cash=non_cash,
                          declared_cash=money(payload.declared_cash), remark=payload.remark)
    db.add(close)
    await db.flush()
    for r in receipts:
        r.day_close_id = close.id
    audit(db, ctx, "DAY_CLOSE_SUBMITTED", "day_close", close.id, None, day_close_dict(close))
    await db.commit()
    return day_close_dict(close)


@router.get("/day-close")
async def list_day_closes(status: Optional[str] = Query(None), ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    if not ctx.can("dayclose.verify"):
        ctx.require("dayclose.submit")
    stmt = select(WaterDayClose).where(WaterDayClose.tenant_id == ctx.tenant_id)
    if not ctx.can("dayclose.verify"):
        stmt = stmt.where(WaterDayClose.collector == ctx.username)
    if status:
        stmt = stmt.where(WaterDayClose.status == status.upper())
    rows = (await db.execute(stmt.order_by(WaterDayClose.close_date.desc()).limit(200))).scalars().all()
    return [day_close_dict(d) for d in rows]


@router.post("/day-close/{close_id}/verify")
async def verify_day_close(close_id: str, payload: DayCloseVerify, ctx: WaterContext = Depends(water_context),
                           db: AsyncSession = Depends(get_write_db)):
    """Cashier counts the cash handed over and matches it against receipts issued (WB-37)."""
    ctx.require("dayclose.verify")
    close = await db.scalar(select(WaterDayClose).where(WaterDayClose.id == close_id, WaterDayClose.tenant_id == ctx.tenant_id).with_for_update())
    if not close:
        raise not_found("Day close not found.")
    if close.status == "VERIFIED":
        raise bad_request("Already verified.")
    if close.collector == ctx.username:
        raise bad_request("You cannot verify your own day-end closing.")
    close.received_cash = money(payload.received_cash)
    close.variance = money(close.received_cash - close.system_cash)
    close.status = "VERIFIED"
    close.verified_by = ctx.username
    close.verified_at = utcnow()
    if payload.remark:
        close.remark = ((close.remark + " | ") if close.remark else "") + payload.remark
    audit(db, ctx, "DAY_CLOSE_VERIFIED", "day_close", close.id, None, day_close_dict(close))
    await db.commit()
    return day_close_dict(close)


# ------------------------------------------------------------------------------------------------
# Reconciliation (WB-34)
# ------------------------------------------------------------------------------------------------

@router.get("/reconciliation/stand-in-statement")
async def stand_in_statement(statement_date: datetime.date = Query(..., alias="date"), ctx: WaterContext = Depends(water_context),
                             db: AsyncSession = Depends(get_read_db)):
    """Statement as the stand-in gateway would send it, so daily reconciliation can be exercised locally."""
    ctx.require("payment.reconcile")
    start = local_day_start_utc(statement_date)
    end = start + datetime.timedelta(days=1)
    rows = (await db.execute(select(WaterGatewayStub).where(WaterGatewayStub.tenant_id == ctx.tenant_id,
                                                            WaterGatewayStub.status == "CAPTURED",
                                                            WaterGatewayStub.captured_at >= start, WaterGatewayStub.captured_at < end))).scalars().all()
    return [{"reference": r.gateway_txn_id, "amount": float(r.amount), "txnDate": statement_date} for r in rows]


@router.post("/reconciliation")
async def reconcile(payload: ReconciliationRequest, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_write_db)):
    """Matches the gateway/bank statement with online receipts of the day and lists mismatches (WB-34)."""
    ctx.require("payment.reconcile")
    receipts = (await db.execute(select(WaterReceipt).where(
        WaterReceipt.tenant_id == ctx.tenant_id, WaterReceipt.receipt_date == payload.statement_date,
        WaterReceipt.payment_mode.in_(list(ONLINE_MODES))))).scalars().all()
    by_ref: Dict[str, WaterReceipt] = {}
    for r in receipts:
        if r.gateway_txn_id:
            by_ref[r.gateway_txn_id] = r
        by_ref.setdefault(r.idempotency_key.replace("ORDER:", ""), r)
    seen = set()
    mismatches: List[Dict] = []
    matched = 0
    for row in payload.rows:
        receipt = by_ref.get(row.reference)
        if receipt is None:
            mismatches.append({"type": "NOT_IN_SYSTEM", "reference": row.reference, "statementAmount": row.amount,
                               "action": "Check the order with the gateway; run the online status check."})
            continue
        seen.add(receipt.id)
        if receipt.status != "VALID":
            mismatches.append({"type": "RECEIPT_NOT_VALID", "reference": row.reference, "receiptNo": receipt.receipt_no,
                               "statementAmount": row.amount, "systemAmount": float(receipt.amount), "status": receipt.status})
        elif money(row.amount) != money(receipt.amount):
            mismatches.append({"type": "AMOUNT_MISMATCH", "reference": row.reference, "receiptNo": receipt.receipt_no,
                               "statementAmount": row.amount, "systemAmount": float(receipt.amount)})
        else:
            matched += 1
    for r in receipts:
        if r.id not in seen and r.status == "VALID":
            mismatches.append({"type": "NOT_IN_STATEMENT", "reference": r.gateway_txn_id, "receiptNo": r.receipt_no,
                               "systemAmount": float(r.amount), "action": "Confirm settlement with the bank."})
    rec = WaterReconciliation(tenant_id=ctx.tenant_id, statement_date=payload.statement_date, source=payload.source,
                              matched_count=matched, mismatches_json=dumps(mismatches), run_by=ctx.username)
    db.add(rec)
    audit(db, ctx, "RECONCILIATION_RUN", "reconciliation", rec.id, None, {"date": payload.statement_date, "matched": matched, "mismatches": len(mismatches)})
    await db.commit()
    return {"id": rec.id, "statementDate": payload.statement_date, "matched": matched, "mismatches": mismatches}


@router.get("/reconciliation")
async def list_reconciliations(ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("payment.reconcile")
    rows = (await db.execute(select(WaterReconciliation).where(WaterReconciliation.tenant_id == ctx.tenant_id)
                             .order_by(WaterReconciliation.run_at.desc()).limit(60))).scalars().all()
    return [{"id": r.id, "statementDate": r.statement_date, "source": r.source, "matched": r.matched_count,
             "mismatches": loads(r.mismatches_json, []), "runBy": r.run_by, "runAt": r.run_at} for r in rows]


# ------------------------------------------------------------------------------------------------
# Refunds (WB-38)
# ------------------------------------------------------------------------------------------------

@router.post("/connections/{consumer_no}/refunds", status_code=201)
async def request_refund(consumer_no: str, payload: RefundRequest, ctx: WaterContext = Depends(water_context),
                         db: AsyncSession = Depends(get_write_db)):
    ctx.require("approval.request")
    conn = await load_connection(db, ctx, consumer_no=consumer_no)
    bal = await balances(db, ctx.tenant_id, connection_id=conn.id)
    amount = money(payload.amount)
    if payload.refund_type == "EXCESS_PAYMENT":
        held = money(-bal["ADVANCE"]) if bal["ADVANCE"] < 0 else Decimal("0")
        if payload.mode != "PAY":
            raise bad_request("Excess payment is adjusted against the next bill automatically; choose PAY to refund it.")
        if amount > held:
            raise bad_request(f"Only ₹{held} is held as excess payment.")
    else:
        held = money(-bal["DEPOSIT"]) if bal["DEPOSIT"] < 0 else Decimal("0")
        if conn.status != "CLOSED":
            raise bad_request("The deposit is refunded only after permanent disconnection.")
        if amount > held:
            raise bad_request(f"Only ₹{held} is held as deposit.")
        if payload.mode == "ADJUST" and amount > dues_total(bal):
            raise bad_request(f"Only ₹{dues_total(bal)} is due; adjust at most that much and refund the rest.")
    if await db.scalar(select(WaterApproval.id).where(WaterApproval.connection_id == conn.id, WaterApproval.approval_type == "REFUND",
                                                      WaterApproval.status == "PENDING")):
        raise conflict("A refund for this connection is already waiting for approval.")
    approval = WaterApproval(tenant_id=ctx.tenant_id, approval_type="REFUND", connection_id=conn.id, ref_no=conn.consumer_no,
                             amount=amount, reason=payload.reason, requested_by=ctx.username,
                             payload_json=dumps({"refundType": payload.refund_type, "mode": payload.mode, "consumerNo": conn.consumer_no}))
    db.add(approval)
    audit(db, ctx, "REFUND_REQUESTED", "connection", conn.id, None, {"amount": float(amount), **payload.model_dump(mode="json")})
    await db.commit()
    return {"message": "Refund sent for approval", "approvalId": approval.id}


async def post_refund(db: AsyncSession, ctx: WaterContext, approval: WaterApproval) -> None:
    conn = await db.get(WaterConnection, approval.connection_id)
    details = loads(approval.payload_json, {})
    amount = money(approval.amount)
    bal = await balances(db, ctx.tenant_id, connection_id=conn.id)
    bucket = "ADVANCE" if details["refundType"] == "EXCESS_PAYMENT" else "DEPOSIT"
    held = money(-bal[bucket]) if bal[bucket] < 0 else Decimal("0")
    if amount > held:
        raise bad_request(f"Only ₹{held} is now held; the refund cannot be approved for ₹{amount}.")
    if details["mode"] == "PAY":
        await post_ledger(db, ctx, tenant_id=ctx.tenant_id, connection_id=conn.id, txn_type="REFUND",
                          component="REFUND" if bucket == "ADVANCE" else "DEPOSIT", bucket=bucket, amount=amount,
                          ward_id=conn.ward_id, approval_id=approval.id, reference_no=conn.consumer_no, narration=approval.reason)
        await notify(db, ctx.tenant_id, recipient=conn.mobile_number, template="REFUND_APPROVED", connection_id=conn.id,
                     ref_no=conn.consumer_no, dedupe_key=f"refund:{approval.id}",
                     message_en=f"GWMC Water: refund of Rs {amount} for {conn.consumer_no} is approved.",
                     message_te=f"జీడబ్ల్యూఎంసీ నీటి సరఫరా: {conn.consumer_no} కోసం రూ. {amount} వాపసు ఆమోదించబడింది.")
    else:
        order = await get_setting(db, ctx.tenant_id, "payment.allocationOrder")
        remaining = amount
        for target in order:
            due = bal.get(target, Decimal("0"))
            if remaining <= 0:
                break
            if due <= 0:
                continue
            take = min(due, remaining)
            await post_ledger(db, ctx, tenant_id=ctx.tenant_id, connection_id=conn.id, txn_type="TRANSFER", component="DEPOSIT",
                              bucket="DEPOSIT", amount=take, ward_id=conn.ward_id, approval_id=approval.id,
                              narration=f"Deposit adjusted against dues: {approval.reason}")
            await post_ledger(db, ctx, tenant_id=ctx.tenant_id, connection_id=conn.id, txn_type="TRANSFER",
                              component=bucket_component(target), bucket=target, amount=-take, ward_id=conn.ward_id,
                              approval_id=approval.id, narration=f"Deposit adjusted against dues: {approval.reason}")
            remaining = money(remaining - take)
