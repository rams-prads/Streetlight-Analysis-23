"""Collection and receipts (PT-31..PT-40, PT-NF-03, PT-NF-32)."""
import datetime
import uuid
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ptx_calc import allocate_payment, document_code, mask_mobile, money
from app.db.ptx_models import (
    PtxApproval, PtxDayClose, PtxGatewayStub, PtxLedger, PtxParty, PtxPaymentIntent, PtxProperty, PtxReceipt, PtxReconciliation, utcnow,
)
from app.db.session import get_read_db, get_write_db
from app.schemas.ptx import (
    ChequeReturnRequest, DayCloseSubmit, DayCloseVerify, GatewayCallback, OnlineInitiate, PaymentCreate, ReasonIn,
    ReconciliationRequest, RefundRequest, StubGatewayPay,
)
from .common import (
    BUCKET_COMPONENT, COLLECTOR, PtxAPIRoute, PtxContext, audit, bad_request, balances, conflict, dues_total, dumps, emit_event, get_setting,
    load_property, loads, local_day_start_utc, new_doc_no, not_found, notify, page, paginate, post_ledger, ptx_context, timeline, today,
    ward_maps,
)

router = APIRouter(route_class=PtxAPIRoute)

ONLINE_MODES = {"ONLINE", "UPI", "BBPS"}
ONLINE_CHANNELS = {"PORTAL", "APP", "BBPS", "WHATSAPP"}


# ------------------------------------------------------------------------------------------------
# Rebate and one-time settlement schemes (PT-39)
# ------------------------------------------------------------------------------------------------

async def scheme_quote(db: AsyncSession, prop: PtxProperty, on: datetime.date) -> Dict:
    """
    What the owner pays now if they clear everything, including any rebate or one-time settlement running today.
    Schemes apply automatically, once per scheme, when the payment clears all dues (PT-39).
    """
    bal = await balances(db, prop.tenant_id, prop.id)
    due = dues_total(bal)
    advance = money(-bal["ADVANCE"]) if bal["ADVANCE"] < 0 else Decimal("0")
    offers: List[Dict] = []
    for s in await get_setting(db, prop.tenant_id, "schemes", on):
        try:
            active = datetime.date.fromisoformat(s["from"]) <= on <= datetime.date.fromisoformat(s["to"])
        except (KeyError, ValueError):
            continue
        if not active:
            continue
        reversed_ids = select(PtxLedger.reversal_of_id).where(PtxLedger.property_id == prop.id, PtxLedger.reversal_of_id.isnot(None))
        if await db.scalar(select(PtxLedger.id).where(PtxLedger.property_id == prop.id, PtxLedger.dedupe_key == f"scheme:{s['code']}:{prop.id}",
                                                      PtxLedger.is_reversal.is_(False), PtxLedger.id.notin_(reversed_ids))):
            continue  # already given on a receipt that still stands
        if s.get("type") == "REBATE":
            benefit = money(max(bal["CURRENT"], Decimal("0")) * Decimal(str(s.get("percentOfCurrentTax", 0))) / Decimal("100"))
            bucket = "CURRENT"
        elif s.get("type") == "OTS":
            benefit = money(max(bal["PENALTY"], Decimal("0")) * Decimal(str(s.get("percentOfInterest", 0))) / Decimal("100"))
            bucket = "PENALTY"
        else:
            continue
        if benefit > 0:
            offers.append({"code": s["code"], "type": s["type"], "nameEn": s.get("nameEn", s["code"]), "nameTe": s.get("nameTe", s.get("nameEn", s["code"])),
                           "until": s["to"], "benefit": float(benefit), "bucket": bucket})
    saving = money(sum((Decimal(str(o["benefit"])) for o in offers), Decimal("0")))
    pay_all = money(max(due - saving - advance, Decimal("0")))
    return {"totalDue": float(max(due, Decimal("0"))), "advanceHeld": float(advance), "schemes": offers, "saving": float(saving),
            "payToClearAll": float(pay_all)}


async def take_payment(db: AsyncSession, ctx, prop: PtxProperty, *, amount: Decimal, mode: str, channel: str, idempotency_key: str,
                       instrument_no: Optional[str] = None, instrument_bank: Optional[str] = None,
                       instrument_date: Optional[datetime.date] = None, gateway_txn_id: Optional[str] = None,
                       payer_name: Optional[str] = None, payer_mobile: Optional[str] = None,
                       on_date: Optional[datetime.date] = None) -> PtxReceipt:
    """Records a payment and its receipt in one transaction; the idempotency key stops it being recorded twice (PT-NF-32)."""
    existing = await db.scalar(select(PtxReceipt).where(PtxReceipt.tenant_id == prop.tenant_id, PtxReceipt.idempotency_key == idempotency_key))
    if existing:
        return existing
    amount = money(amount)
    if amount <= 0:
        raise bad_request("Amount must be more than zero.")
    if mode == "POS" and not instrument_no:
        raise bad_request("Enter the approval code (RRN) printed by the card machine.")
    if mode in ("CHEQUE", "DD") and not (instrument_no and instrument_bank and instrument_date):
        raise bad_request("Cheque / DD number, bank and date are required.")
    if prop.status != "ACTIVE" and dues_total(await balances(db, prop.tenant_id, prop.id)) <= 0:
        raise bad_request(f"This property number is {prop.status.lower()} and has nothing due. Pay under the new property number.")
    pay_date = on_date or today()
    actor = ctx.username if isinstance(ctx, PtxContext) else str(ctx)
    receipt = PtxReceipt(tenant_id=prop.tenant_id, receipt_no=await new_doc_no(db, prop.tenant_id, "PRC", "receipt"), property_id=prop.id,
                         ward_id=prop.ward_id, amount=amount, payment_mode=mode, channel=channel, instrument_no=instrument_no,
                         instrument_bank=instrument_bank, instrument_date=instrument_date, gateway_txn_id=gateway_txn_id,
                         idempotency_key=idempotency_key, payer_name=payer_name, payer_mobile=payer_mobile, collected_by=actor,
                         receipt_date=pay_date, verification_code="PENDING")
    db.add(receipt)
    await db.flush()
    receipt.verification_code = document_code("RECEIPT", receipt.receipt_no, amount)
    allocation: Dict[str, float] = {}

    quote = await scheme_quote(db, prop, pay_date)
    if quote["schemes"] and amount >= Decimal(str(quote["payToClearAll"])):
        for offer in quote["schemes"]:
            component = "REBATE" if offer["type"] == "REBATE" else "OTS_WAIVER"
            await post_ledger(db, ctx, prop=prop, txn_type=component, component=component, bucket=offer["bucket"], amount=-Decimal(str(offer["benefit"])),
                              receipt_id=receipt.id, reference_no=receipt.receipt_no, dedupe_key=f"scheme:{offer['code']}:{prop.id}",
                              entry_date=pay_date, narration=f"{offer['nameEn']} applied")
            allocation[f"Scheme: {offer['nameEn']}"] = offer["benefit"]
        receipt.scheme_benefit = money(Decimal(str(quote["saving"])))
        await db.flush()

    bal = await balances(db, prop.tenant_id, prop.id)
    order = await get_setting(db, prop.tenant_id, "payment.allocationOrder")
    try:
        applied = allocate_payment(amount, bal, order)
    except ValueError as exc:
        raise bad_request(str(exc))
    for bucket, part in applied.items():
        await post_ledger(db, ctx, prop=prop, txn_type="PAYMENT", component=BUCKET_COMPONENT[bucket], bucket=bucket, amount=-part,
                          payment_mode=mode, reference_no=receipt.receipt_no, receipt_id=receipt.id, entry_date=pay_date,
                          narration=f"Receipt {receipt.receipt_no}")
        allocation[bucket] = float(part)
    receipt.allocation_json = dumps(allocation)
    emit_event(db, prop.tenant_id, "payment.received", receipt.id, {"upin": prop.upin, "receiptNo": receipt.receipt_no, "amount": float(amount),
                                                                    "mode": mode, "channel": channel, "allocation": allocation, "wardId": prop.ward_id})
    if isinstance(ctx, PtxContext):
        audit(db, ctx, "PAYMENT_RECEIVED", "receipt", receipt.id, None, {"receiptNo": receipt.receipt_no, "upin": prop.upin, "amount": float(amount),
                                                                         "mode": mode, "channel": channel})
    mobile = payer_mobile or await db.scalar(select(PtxParty.mobile_number).where(PtxParty.property_id == prop.id, PtxParty.role == "OWNER",
                                                                                  PtxParty.is_current.is_(True), PtxParty.mobile_number.isnot(None)).limit(1))
    await notify(db, prop.tenant_id, recipient=mobile, template="RECEIPT", property_id=prop.id, ref_no=receipt.receipt_no, dedupe_key=f"receipt:{receipt.id}",
                 message_en=f"GWMC Property Tax: received Rs {amount} for {prop.upin}. Receipt {receipt.receipt_no}, verify code {receipt.verification_code}.",
                 message_te=f"జీడబ్ల్యూఎంసీ ఆస్తి పన్ను: {prop.upin} కోసం రూ. {amount} అందింది. రసీదు {receipt.receipt_no}, ధృవీకరణ కోడ్ {receipt.verification_code}.")
    return receipt


def receipt_dict(r: PtxReceipt, upin: Optional[str] = None) -> Dict:
    return {"id": r.id, "receiptNo": r.receipt_no, "upin": upin, "amount": float(r.amount), "schemeBenefit": float(r.scheme_benefit or 0),
            "paymentMode": r.payment_mode, "channel": r.channel, "instrumentNo": r.instrument_no, "instrumentBank": r.instrument_bank,
            "gatewayTxnId": r.gateway_txn_id, "payerName": r.payer_name, "payerMobileMasked": mask_mobile(r.payer_mobile),
            "allocation": loads(r.allocation_json, {}), "status": r.status, "statusReason": r.status_reason,
            "verificationCode": r.verification_code, "collectedBy": r.collected_by, "receiptDate": r.receipt_date, "createdAt": r.created_at,
            "dayCloseId": r.day_close_id,
            "verifyPath": f"/api/v1/ptx/public/verify?type=RECEIPT&no={r.receipt_no}&code={r.verification_code}&tenant={r.tenant_id}"}


@router.get("/properties/{upin}/payable")
async def payable(upin: str, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    """Amount to pay now, with any scheme saving explained (shown before paying)."""
    if not ctx.can("payment.collect"):
        ctx.require("property.view")
    prop = await load_property(db, ctx, upin=upin)
    return {"upin": prop.upin, **await scheme_quote(db, prop, today())}


@router.post("/payments", status_code=201)
async def collect(payload: PaymentCreate, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """Counter, field collector and CSC payments: cash, cheque, DD, UPI QR (PT-31). Part payments allowed (PT-33)."""
    ctx.require("payment.collect")
    prop = await load_property(db, ctx, upin=payload.upin, for_update=True)
    receipt = await take_payment(db, ctx, prop, amount=Decimal(str(payload.amount)), mode=payload.payment_mode, channel=payload.channel,
                                 idempotency_key=f"COUNTER:{payload.idempotency_key}", instrument_no=payload.instrument_no,
                                 instrument_bank=payload.instrument_bank, instrument_date=payload.instrument_date,
                                 payer_name=payload.payer_name, payer_mobile=payload.payer_mobile)
    await db.commit()
    return receipt_dict(receipt, prop.upin)


# ------------------------------------------------------------------------------------------------
# Online payment through the gateway stand-in (PT-31, PT-36, PT-IR-08)
# ------------------------------------------------------------------------------------------------

@router.post("/payments/online/initiate", status_code=201)
async def initiate_online(payload: OnlineInitiate, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    ctx.require("payment.online")
    prop = await db.scalar(select(PtxProperty).where(PtxProperty.tenant_id == ctx.tenant_id, PtxProperty.upin == payload.upin.strip().upper()))
    if prop is None:
        raise not_found("Property number not found. Check the number on your tax bill.")
    intent = PtxPaymentIntent(tenant_id=ctx.tenant_id, order_id=await new_doc_no(db, ctx.tenant_id, "PPO", "order"), property_id=prop.id,
                              amount=money(payload.amount), channel=payload.channel, created_by=ctx.username)
    db.add(intent)
    audit(db, ctx, "ONLINE_PAYMENT_INITIATED", "payment_intent", intent.id, None, {"orderId": intent.order_id, "amount": payload.amount})
    await db.commit()
    return {"orderId": intent.order_id, "amount": float(intent.amount), "status": intent.status, "gateway": "STAND_IN"}


async def _complete_intent(db: AsyncSession, actor, intent: PtxPaymentIntent, txn: str, via: str) -> PtxReceipt:
    prop = await db.get(PtxProperty, intent.property_id)
    receipt = await take_payment(db, actor, prop, amount=Decimal(str(intent.amount)), mode="BBPS" if intent.channel == "BBPS" else "ONLINE",
                                 channel=intent.channel, idempotency_key=f"ORDER:{intent.order_id}", gateway_txn_id=txn)
    intent.status, intent.gateway_txn_id, intent.receipt_id = "SUCCESS", txn, receipt.id
    intent.completed_via, intent.completed_at = via, utcnow()
    return receipt


@router.post("/payments/online/stub-gateway")
async def stub_gateway(payload: StubGatewayPay, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """Stand-in for the bank's payment page. SUCCESS_NO_CALLBACK simulates money taken but confirmation lost (PT-36)."""
    ctx.require("payment.online")
    intent = await db.scalar(select(PtxPaymentIntent).where(PtxPaymentIntent.tenant_id == ctx.tenant_id, PtxPaymentIntent.order_id == payload.order_id).with_for_update())
    if intent is None:
        raise not_found("Payment order not found.")
    if await db.get(PtxGatewayStub, payload.order_id):
        raise conflict("This order was already processed by the gateway.")
    captured = payload.outcome != "FAILURE"
    txn = f"STUB{uuid.uuid4().hex[:14].upper()}" if captured else None
    db.add(PtxGatewayStub(order_id=intent.order_id, tenant_id=ctx.tenant_id, gateway_txn_id=txn, amount=intent.amount,
                          status="CAPTURED" if captured else "FAILED"))
    await db.commit()
    if payload.outcome == "SUCCESS_NO_CALLBACK":
        return {"orderId": intent.order_id, "gatewayStatus": "CAPTURED", "callback": "LOST",
                "message": "Money was taken at the gateway but the confirmation did not reach the system. The status check will complete it."}
    return await gateway_callback(GatewayCallback(order_id=intent.order_id, gateway_txn_id=txn, status="SUCCESS" if captured else "FAILURE"), ctx, db)


@router.post("/payments/online/callback")
async def gateway_callback(payload: GatewayCallback, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """Gateway confirmation; safe to receive more than once (PT-NF-32)."""
    intent = await db.scalar(select(PtxPaymentIntent).where(PtxPaymentIntent.tenant_id == ctx.tenant_id, PtxPaymentIntent.order_id == payload.order_id).with_for_update())
    if intent is None:
        raise not_found("Payment order not found.")
    prop = await db.get(PtxProperty, intent.property_id)
    if intent.status == "SUCCESS":
        return {"orderId": intent.order_id, "status": "SUCCESS", "receipt": receipt_dict(await db.get(PtxReceipt, intent.receipt_id), prop.upin), "duplicate": True}
    stub = await db.get(PtxGatewayStub, intent.order_id)
    if payload.status == "SUCCESS":
        if stub is None or stub.status != "CAPTURED" or money(stub.amount) != money(intent.amount):
            raise bad_request("The gateway has no matching payment for this order.")
        receipt = await _complete_intent(db, ctx, intent, stub.gateway_txn_id, "CALLBACK")
        await db.commit()
        return {"orderId": intent.order_id, "status": "SUCCESS", "receipt": receipt_dict(receipt, prop.upin)}
    intent.status, intent.completed_at = "FAILED", utcnow()
    await db.commit()
    return {"orderId": intent.order_id, "status": "FAILED"}


async def reconcile_pending_intents(db: AsyncSession, actor, tenant_id: str) -> Dict:
    """Asks the gateway about orders still waiting and completes those that were paid (PT-36)."""
    pending = (await db.execute(select(PtxPaymentIntent).where(PtxPaymentIntent.tenant_id == tenant_id, PtxPaymentIntent.status == "INITIATED")
                                .with_for_update())).scalars().all()
    completed, failed = [], []
    for intent in pending:
        stub = await db.get(PtxGatewayStub, intent.order_id)
        if stub is None:
            continue
        if stub.status == "CAPTURED" and money(stub.amount) == money(intent.amount):
            receipt = await _complete_intent(db, actor, intent, stub.gateway_txn_id, "STATUS_CHECK")
            completed.append({"orderId": intent.order_id, "receiptNo": receipt.receipt_no})
        elif stub.status == "FAILED":
            intent.status, intent.completed_at = "FAILED", utcnow()
            failed.append(intent.order_id)
    return {"checked": len(pending), "completed": completed, "failed": failed}


@router.post("/payments/online/status-check")
async def status_check(ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    ctx.require("payment.online")
    result = await reconcile_pending_intents(db, ctx, ctx.tenant_id)
    await db.commit()
    return result


@router.get("/payments/online/{order_id}")
async def get_intent(order_id: str, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("payment.online")
    intent = await db.scalar(select(PtxPaymentIntent).where(PtxPaymentIntent.tenant_id == ctx.tenant_id, PtxPaymentIntent.order_id == order_id))
    if intent is None:
        raise not_found("Payment order not found.")
    receipt = await db.get(PtxReceipt, intent.receipt_id) if intent.receipt_id else None
    return {"orderId": intent.order_id, "amount": float(intent.amount), "status": intent.status, "completedVia": intent.completed_via,
            "receipt": receipt_dict(receipt) if receipt else None}


# ------------------------------------------------------------------------------------------------
# Receipts (PT-32, PT-34, PT-37)
# ------------------------------------------------------------------------------------------------

@router.get("/receipts")
async def list_receipts(search: Optional[str] = Query(None), date_from: Optional[datetime.date] = Query(None, alias="from"),
                        date_to: Optional[datetime.date] = Query(None, alias="to"), mode: Optional[str] = Query(None),
                        collector: Optional[str] = Query(None), skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                        ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("billing.view")
    stmt = select(PtxReceipt, PtxProperty.upin).join(PtxProperty, PtxProperty.id == PtxReceipt.property_id).where(
        PtxReceipt.tenant_id == ctx.tenant_id, ctx.ward_filter(PtxReceipt.ward_id))
    if date_from:
        stmt = stmt.where(PtxReceipt.receipt_date >= date_from)
    if date_to:
        stmt = stmt.where(PtxReceipt.receipt_date <= date_to)
    if mode:
        stmt = stmt.where(PtxReceipt.payment_mode == mode.upper())
    # a bill collector sees only their own receipts here, never another collector's or the whole ward's (PT-NF-10)
    if ctx.is_only(COLLECTOR):
        stmt = stmt.where(PtxReceipt.collected_by == ctx.username)
    elif collector:
        stmt = stmt.where(PtxReceipt.collected_by == collector)
    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(PtxReceipt.receipt_no.ilike(like), PtxProperty.upin.ilike(like), PtxReceipt.gateway_txn_id.ilike(like)))
    rows, total = await paginate(db, stmt.order_by(PtxReceipt.created_at.desc()), skip, limit)
    return page([receipt_dict(r, upin) for r, upin in rows], total, skip, limit)


async def printable_receipt(db: AsyncSession, r: PtxReceipt) -> Dict:
    prop = await db.get(PtxProperty, r.property_id)
    owners = (await db.execute(select(PtxParty.full_name).where(PtxParty.property_id == prop.id, PtxParty.role == "OWNER",
                                                                PtxParty.is_current.is_(True)))).scalars().all()
    wards, _ = await ward_maps(db, r.tenant_id)
    return {**receipt_dict(r, prop.upin), "ownerNames": list(owners), "address": prop.address,
            "wardNumber": wards.get(prop.ward_id, {}).get("wardNumber")}


@router.get("/receipts/{receipt_no}")
async def get_receipt(receipt_no: str, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("billing.view")
    r = await db.scalar(select(PtxReceipt).where(PtxReceipt.tenant_id == ctx.tenant_id, PtxReceipt.receipt_no == receipt_no))
    if r is None:
        raise not_found(f"Receipt {receipt_no} not found.")
    ctx.ensure_scope(r.ward_id)
    return await printable_receipt(db, r)


@router.post("/receipts/{receipt_no}/cancel", status_code=201)
async def request_cancellation(receipt_no: str, payload: ReasonIn, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """A wrong receipt is never edited; it is cancelled only through an approved reversal (PT-34)."""
    ctx.require("approval.request")
    r = await db.scalar(select(PtxReceipt).where(PtxReceipt.tenant_id == ctx.tenant_id, PtxReceipt.receipt_no == receipt_no))
    if r is None:
        raise not_found(f"Receipt {receipt_no} not found.")
    ctx.ensure_scope(r.ward_id)
    if r.status != "VALID":
        raise bad_request(f"Receipt is already {r.status.lower()}.")
    if await db.scalar(select(PtxApproval.id).where(PtxApproval.ref_id == r.id, PtxApproval.status == "PENDING")):
        raise conflict("A cancellation for this receipt is already waiting for approval.")
    a = PtxApproval(tenant_id=ctx.tenant_id, approval_type="RECEIPT_CANCEL", property_id=r.property_id, ref_id=r.id, ref_no=r.receipt_no,
                    amount=r.amount, reason=payload.reason, requested_by=ctx.username, payload_json=dumps({"receiptNo": r.receipt_no}))
    db.add(a)
    audit(db, ctx, "RECEIPT_CANCEL_REQUESTED", "receipt", r.id, None, {"reason": payload.reason})
    await db.commit()
    return {"message": "Cancellation sent for approval", "approvalId": a.id}


async def reverse_receipt(db: AsyncSession, ctx: PtxContext, r: PtxReceipt, new_status: str, reason: str, approval_id: Optional[str] = None) -> None:
    """Posts the exact opposite of every ledger row of a receipt (including any scheme benefit) and marks it."""
    prop = await db.get(PtxProperty, r.property_id)
    rows = (await db.execute(select(PtxLedger).where(PtxLedger.receipt_id == r.id, PtxLedger.is_reversal.is_(False)))).scalars().all()
    for row in rows:
        await post_ledger(db, ctx, prop=prop, txn_type=row.txn_type, component=row.component, bucket=row.bucket, amount=-row.amount,
                          payment_mode=row.payment_mode, reference_no=r.receipt_no, receipt_id=r.id, approval_id=approval_id,
                          is_reversal=True, reversal_of_id=row.id, narration=f"Reversal ({new_status.lower()}): {reason}")
    r.status, r.status_reason = new_status, reason
    emit_event(db, ctx.tenant_id, "receipt.cancelled", r.id, {"receiptNo": r.receipt_no, "upin": prop.upin, "amount": float(r.amount),
                                                             "status": new_status, "reason": reason})


@router.post("/receipts/{receipt_no}/cheque-return")
async def cheque_return(receipt_no: str, payload: ChequeReturnRequest, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """Cheque / DD returned: reverse the receipt, add the notified charge, inform the payer (PT-37)."""
    ctx.require("payment.cheque_return")
    r = await db.scalar(select(PtxReceipt).where(PtxReceipt.tenant_id == ctx.tenant_id, PtxReceipt.receipt_no == receipt_no).with_for_update())
    if r is None:
        raise not_found(f"Receipt {receipt_no} not found.")
    if r.payment_mode not in ("CHEQUE", "DD"):
        raise bad_request("Only cheque or demand draft receipts can be returned.")
    if r.status != "VALID":
        raise bad_request(f"Receipt is already {r.status.lower()}.")
    await reverse_receipt(db, ctx, r, "BOUNCED", f"Cheque returned: {payload.reason}")
    prop = await db.get(PtxProperty, r.property_id)
    charge = money(await get_setting(db, ctx.tenant_id, "fees.chequeReturnCharge"))
    if charge > 0:
        await post_ledger(db, ctx, prop=prop, txn_type="FEE", component="CHEQUE_RETURN_CHARGE", bucket="FEE", amount=charge, reference_no=r.receipt_no,
                          entry_date=payload.return_date or today(), narration=f"Cheque return charge for {r.receipt_no}")
    mobile = r.payer_mobile or await db.scalar(select(PtxParty.mobile_number).where(PtxParty.property_id == prop.id, PtxParty.role == "OWNER",
                                                                                    PtxParty.is_current.is_(True), PtxParty.mobile_number.isnot(None)).limit(1))
    await notify(db, ctx.tenant_id, recipient=mobile, template="CHEQUE_RETURNED", property_id=prop.id, ref_no=r.receipt_no, dedupe_key=f"cheque:{r.id}",
                 message_en=f"GWMC Property Tax: cheque {r.instrument_no} for receipt {r.receipt_no} was returned. Rs {r.amount} is due again with a charge of Rs {charge}.",
                 message_te=f"జీడబ్ల్యూఎంసీ ఆస్తి పన్ను: రసీదు {r.receipt_no} చెక్కు తిరిగి వచ్చింది. రూ. {r.amount} మళ్లీ చెల్లించాలి, అదనపు ఛార్జీ రూ. {charge}.")
    audit(db, ctx, "CHEQUE_RETURNED", "receipt", r.id, {"status": "VALID"}, {"status": "BOUNCED", "charge": float(charge)})
    await db.commit()
    return {"message": "Receipt reversed and payer informed", "receiptNo": r.receipt_no, "chargeAdded": float(charge)}


# ------------------------------------------------------------------------------------------------
# Day-end closing (PT-38) and reconciliation (PT-35)
# ------------------------------------------------------------------------------------------------

def close_dict(d: PtxDayClose) -> Dict:
    return {"id": d.id, "collector": d.collector, "closeDate": d.close_date, "receiptCount": d.receipt_count, "systemCash": float(d.system_cash),
            "systemNonCash": float(d.system_non_cash), "declaredCash": float(d.declared_cash),
            "receivedCash": float(d.received_cash) if d.received_cash is not None else None,
            "variance": float(d.variance) if d.variance is not None else None, "status": d.status, "verifiedBy": d.verified_by,
            "verifiedAt": d.verified_at, "remark": d.remark}


@router.post("/day-close", status_code=201)
async def submit_day_close(payload: DayCloseSubmit, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    ctx.require("dayclose.submit")
    if payload.close_date > today():
        raise bad_request("Cannot close a future day.")
    if await db.scalar(select(PtxDayClose.id).where(PtxDayClose.tenant_id == ctx.tenant_id, PtxDayClose.collector == ctx.username,
                                                    PtxDayClose.close_date == payload.close_date)):
        raise conflict("This day is already closed for you.")
    receipts = (await db.execute(select(PtxReceipt).where(PtxReceipt.tenant_id == ctx.tenant_id, PtxReceipt.collected_by == ctx.username,
                                                          PtxReceipt.receipt_date == payload.close_date, PtxReceipt.day_close_id.is_(None),
                                                          PtxReceipt.channel.notin_(list(ONLINE_CHANNELS))))).scalars().all()
    valid = [r for r in receipts if r.status != "CANCELLED"]
    close = PtxDayClose(tenant_id=ctx.tenant_id, collector=ctx.username, close_date=payload.close_date, receipt_count=len(valid),
                        system_cash=money(sum((r.amount for r in valid if r.payment_mode == "CASH"), Decimal("0"))),
                        system_non_cash=money(sum((r.amount for r in valid if r.payment_mode != "CASH"), Decimal("0"))),
                        declared_cash=money(payload.declared_cash), remark=payload.remark)
    db.add(close)
    await db.flush()
    for r in receipts:
        r.day_close_id = close.id
    audit(db, ctx, "DAY_CLOSE_SUBMITTED", "day_close", close.id, None, close_dict(close))
    await db.commit()
    return close_dict(close)


@router.get("/day-close")
async def list_day_closes(status: Optional[str] = Query(None), skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                          ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    if not ctx.can("dayclose.verify"):
        ctx.require("dayclose.submit")
    stmt = select(PtxDayClose).where(PtxDayClose.tenant_id == ctx.tenant_id)
    if not ctx.can("dayclose.verify"):
        stmt = stmt.where(PtxDayClose.collector == ctx.username)
    if status:
        stmt = stmt.where(PtxDayClose.status == status.upper())
    rows, total = await paginate(db, stmt.order_by(PtxDayClose.close_date.desc()), skip, limit)
    return page([close_dict(d) for (d,) in rows], total, skip, limit)


@router.post("/day-close/{close_id}/verify")
async def verify_day_close(close_id: str, payload: DayCloseVerify, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """The cashier counts the cash handed over and matches it against receipts issued (PT-38)."""
    ctx.require("dayclose.verify")
    close = await db.scalar(select(PtxDayClose).where(PtxDayClose.id == close_id, PtxDayClose.tenant_id == ctx.tenant_id).with_for_update())
    if close is None:
        raise not_found("Day close not found.")
    if close.status == "VERIFIED":
        raise bad_request("Already verified.")
    if close.collector == ctx.username:
        raise bad_request("You cannot verify your own day-end closing.")
    close.received_cash = money(payload.received_cash)
    close.variance = money(close.received_cash - close.system_cash)
    close.status, close.verified_by, close.verified_at = "VERIFIED", ctx.username, utcnow()
    if payload.remark:
        close.remark = ((close.remark + " | ") if close.remark else "") + payload.remark
    audit(db, ctx, "DAY_CLOSE_VERIFIED", "day_close", close.id, None, close_dict(close))
    await db.commit()
    return close_dict(close)


@router.get("/reconciliation/stand-in-statement")
async def stand_in_statement(statement_date: datetime.date = Query(..., alias="date"), ctx: PtxContext = Depends(ptx_context),
                             db: AsyncSession = Depends(get_read_db)):
    ctx.require("payment.reconcile")
    start = local_day_start_utc(statement_date)
    rows = (await db.execute(select(PtxGatewayStub).where(PtxGatewayStub.tenant_id == ctx.tenant_id, PtxGatewayStub.status == "CAPTURED",
                                                          PtxGatewayStub.captured_at >= start,
                                                          PtxGatewayStub.captured_at < start + datetime.timedelta(days=1)))).scalars().all()
    out = [{"reference": r.gateway_txn_id, "amount": float(r.amount)} for r in rows]
    # what the BBPS operating unit would report for the day: every BBPS payment it passed on to us
    bbps = (await db.execute(select(PtxReceipt).where(PtxReceipt.tenant_id == ctx.tenant_id, PtxReceipt.payment_mode == "BBPS",
                                                      PtxReceipt.receipt_date == statement_date, PtxReceipt.status == "VALID"))).scalars().all()
    return out + [{"reference": r.gateway_txn_id, "amount": float(r.amount)} for r in bbps if r.gateway_txn_id]


@router.post("/reconciliation")
async def reconcile(payload: ReconciliationRequest, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """Matches the gateway / bank statement with the day's online receipts and lists mismatches (PT-35)."""
    ctx.require("payment.reconcile")
    receipts = (await db.execute(select(PtxReceipt).where(PtxReceipt.tenant_id == ctx.tenant_id, PtxReceipt.receipt_date == payload.statement_date,
                                                          PtxReceipt.payment_mode.in_(list(ONLINE_MODES))))).scalars().all()
    by_ref: Dict[str, PtxReceipt] = {}
    for r in receipts:
        if r.gateway_txn_id:
            by_ref[r.gateway_txn_id] = r
        by_ref.setdefault(r.idempotency_key.replace("ORDER:", ""), r)
    seen, mismatches, matched = set(), [], 0
    for row in payload.rows:
        r = by_ref.get(row.reference)
        if r is None:
            mismatches.append({"type": "NOT_IN_SYSTEM", "reference": row.reference, "statementAmount": row.amount,
                               "action": "Check the order with the gateway, then run the online status check."})
            continue
        seen.add(r.id)
        if r.status != "VALID":
            mismatches.append({"type": "RECEIPT_NOT_VALID", "reference": row.reference, "receiptNo": r.receipt_no, "statementAmount": row.amount,
                               "systemAmount": float(r.amount), "status": r.status})
        elif money(row.amount) != money(r.amount):
            mismatches.append({"type": "AMOUNT_MISMATCH", "reference": row.reference, "receiptNo": r.receipt_no, "statementAmount": row.amount,
                               "systemAmount": float(r.amount)})
        else:
            matched += 1
    for r in receipts:
        if r.id not in seen and r.status == "VALID":
            mismatches.append({"type": "NOT_IN_STATEMENT", "reference": r.gateway_txn_id, "receiptNo": r.receipt_no, "systemAmount": float(r.amount),
                               "action": "Confirm settlement with the bank."})
    rec = PtxReconciliation(tenant_id=ctx.tenant_id, statement_date=payload.statement_date, source=payload.source, matched_count=matched,
                            mismatches_json=dumps(mismatches), run_by=ctx.username)
    db.add(rec)
    audit(db, ctx, "RECONCILIATION_RUN", "reconciliation", rec.id, None, {"date": payload.statement_date, "matched": matched, "mismatches": len(mismatches)})
    await db.commit()
    return {"id": rec.id, "statementDate": payload.statement_date, "matched": matched, "mismatches": mismatches}


@router.get("/reconciliation")
async def list_reconciliations(skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), ctx: PtxContext = Depends(ptx_context),
                               db: AsyncSession = Depends(get_read_db)):
    ctx.require("payment.reconcile")
    rows, total = await paginate(db, select(PtxReconciliation).where(PtxReconciliation.tenant_id == ctx.tenant_id).order_by(PtxReconciliation.run_at.desc()), skip, limit)
    return page([{"id": r.id, "statementDate": r.statement_date, "source": r.source, "matched": r.matched_count,
                  "mismatches": loads(r.mismatches_json, []), "runBy": r.run_by, "runAt": r.run_at} for (r,) in rows], total, skip, limit)


# ------------------------------------------------------------------------------------------------
# Refunds (PT-40)
# ------------------------------------------------------------------------------------------------

@router.post("/properties/{upin}/refunds", status_code=201)
async def request_refund(upin: str, payload: RefundRequest, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """Refund of excess payment, through approval before it is paid or adjusted (PT-40)."""
    ctx.require("approval.request")
    prop = await load_property(db, ctx, upin=upin)
    bal = await balances(db, ctx.tenant_id, prop.id)
    held = money(-bal["ADVANCE"]) if bal["ADVANCE"] < 0 else Decimal("0")
    amount = money(payload.amount)
    if amount > held:
        raise bad_request(f"Only Rs {held} is held as excess payment on this property.")
    if payload.mode == "ADJUST" and amount > dues_total(bal):
        raise bad_request(f"Only Rs {max(dues_total(bal), Decimal('0'))} is due; adjust at most that much.")
    if await db.scalar(select(PtxApproval.id).where(PtxApproval.property_id == prop.id, PtxApproval.approval_type == "REFUND", PtxApproval.status == "PENDING")):
        raise conflict("A refund for this property is already waiting for approval.")
    a = PtxApproval(tenant_id=ctx.tenant_id, approval_type="REFUND", property_id=prop.id, ref_no=prop.upin, amount=amount, reason=payload.reason,
                    requested_by=ctx.username, payload_json=dumps({"mode": payload.mode, "upin": prop.upin}))
    db.add(a)
    audit(db, ctx, "REFUND_REQUESTED", "property", prop.id, None, {"amount": float(amount), "mode": payload.mode, "reason": payload.reason})
    await db.commit()
    return {"message": "Refund sent for approval", "approvalId": a.id}


async def post_refund(db: AsyncSession, ctx: PtxContext, a: PtxApproval) -> None:
    prop = await db.get(PtxProperty, a.property_id)
    bal = await balances(db, ctx.tenant_id, prop.id)
    held = money(-bal["ADVANCE"]) if bal["ADVANCE"] < 0 else Decimal("0")
    amount = money(a.amount)
    if amount > held:
        raise bad_request(f"Only Rs {held} is now held as excess payment; the refund cannot be approved for Rs {amount}.")
    if loads(a.payload_json, {}).get("mode") == "ADJUST":
        order = await get_setting(db, ctx.tenant_id, "payment.allocationOrder")
        remaining = amount
        for bucket in order:
            take = min(max(bal[bucket], Decimal("0")), remaining)
            if take <= 0:
                continue
            narration = f"Excess payment adjusted against dues: {a.reason}"
            await post_ledger(db, ctx, prop=prop, txn_type="TRANSFER", component="ADVANCE", bucket="ADVANCE", amount=take, approval_id=a.id, narration=narration)
            await post_ledger(db, ctx, prop=prop, txn_type="TRANSFER", component=BUCKET_COMPONENT[bucket], bucket=bucket, amount=-take,
                              approval_id=a.id, narration=narration)
            remaining = money(remaining - take)
    else:
        await post_ledger(db, ctx, prop=prop, txn_type="REFUND", component="REFUND", bucket="ADVANCE", amount=amount, approval_id=a.id,
                          reference_no=prop.upin, narration=a.reason)
        timeline(db, ctx, "property", prop.id, "REFUND_APPROVED", f"Rs {amount}")
    emit_event(db, ctx.tenant_id, "refund.approved", prop.id, {"upin": prop.upin, "amount": float(amount), "mode": loads(a.payload_json, {}).get("mode")})
