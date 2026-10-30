"""
Maker-checker approvals for tariffs (WB-21), bill corrections (WB-26), receipt cancellation (WB-33),
refunds (WB-38), waivers and write-offs (WB-46). The person who asks can never approve their own request,
and each role may approve only up to its configured amount.
"""
from decimal import Decimal
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.water_calc import money
from app.db.session import get_read_db, get_write_db
from app.db.water_models import WaterApproval, WaterConnection, WaterReceipt, WaterTariff, utcnow
from app.schemas.water import ApprovalDecision
from .arrears import post_waiver
from .billing import post_bill_adjustment
from .common import (
    ADMIN, WaterAPIRoute, WaterContext, audit, bad_request, get_setting, loads, not_found, today, water_context,
)
from .payments import post_refund, reverse_receipt

router = APIRouter(route_class=WaterAPIRoute)


async def approval_limit(db: AsyncSession, ctx: WaterContext) -> Optional[Decimal]:
    """Highest amount the user may approve. None = no limit. Raises if the user may not approve money at all."""
    if ctx.roles & ADMIN:
        return None
    limits: Dict = await get_setting(db, ctx.tenant_id, "approval.limits")
    best: Optional[Decimal] = Decimal("-1")
    for role in ctx.roles:
        if role in limits:
            value = limits[role]
            if value is None:
                return None
            best = max(best, Decimal(str(value)))
    if best < 0:
        raise HTTPException(status_code=403, detail="Your role has no approval authority for amounts.")
    return best


def approval_dict(a: WaterApproval, consumer_no: Optional[str], can_decide: bool) -> Dict:
    return {
        "id": a.id, "approvalType": a.approval_type, "consumerNo": consumer_no, "refNo": a.ref_no,
        "amount": float(a.amount) if a.amount is not None else None, "details": loads(a.payload_json, {}),
        "reason": a.reason, "status": a.status, "requestedBy": a.requested_by, "requestedAt": a.requested_at,
        "decidedBy": a.decided_by, "decidedAt": a.decided_at, "decisionRemark": a.decision_remark, "canDecide": can_decide,
    }


async def _can_decide(db: AsyncSession, ctx: WaterContext, a: WaterApproval) -> bool:
    if a.status != "PENDING" or a.requested_by == ctx.username:
        return False
    if a.approval_type == "TARIFF":
        return ctx.can("tariff.approve")
    if not ctx.can("approval.decide"):
        return False
    try:
        limit = await approval_limit(db, ctx)
    except HTTPException:
        return False
    return limit is None or abs(money(a.amount or 0)) <= limit


@router.get("/approvals")
async def list_approvals(status: Optional[str] = Query("PENDING"), approval_type: Optional[str] = Query(None, alias="type"),
                         ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    if not (ctx.can("approval.decide") or ctx.can("approval.request") or ctx.can("tariff.approve")):
        ctx.require("approval.decide")
    stmt = select(WaterApproval, WaterConnection.consumer_no, WaterConnection.ward_id).outerjoin(
        WaterConnection, WaterConnection.id == WaterApproval.connection_id).where(WaterApproval.tenant_id == ctx.tenant_id)
    if status:
        stmt = stmt.where(WaterApproval.status == status.upper())
    if approval_type:
        stmt = stmt.where(WaterApproval.approval_type == approval_type.upper())
    rows = (await db.execute(stmt.order_by(WaterApproval.requested_at.desc()).limit(500))).all()
    out = []
    for a, consumer_no, ward_id in rows:
        if ward_id and not ctx.in_scope(ward_id):
            continue
        out.append(approval_dict(a, consumer_no, await _can_decide(db, ctx, a)))
    return out


@router.post("/approvals/{approval_id}/decide")
async def decide(approval_id: str, body: ApprovalDecision, ctx: WaterContext = Depends(water_context),
                 db: AsyncSession = Depends(get_write_db)):
    a = await db.scalar(select(WaterApproval).where(WaterApproval.id == approval_id, WaterApproval.tenant_id == ctx.tenant_id).with_for_update())
    if not a:
        raise not_found("Approval request not found.")
    if a.status != "PENDING":
        raise bad_request(f"This request is already {a.status}.")
    if a.requested_by == ctx.username:
        raise bad_request("You cannot approve or reject your own request. Another authorised officer must decide.")
    if a.connection_id:
        conn = await db.get(WaterConnection, a.connection_id)
        ctx.ensure_scope(conn.ward_id)
    if a.approval_type == "TARIFF":
        ctx.require("tariff.approve")
    else:
        ctx.require("approval.decide")
        limit = await approval_limit(db, ctx)
        if limit is not None and abs(money(a.amount or 0)) > limit:
            raise HTTPException(status_code=403, detail=f"₹{abs(money(a.amount))} is above your approval limit of ₹{limit}. "
                                                        "It needs a higher authority (Commissioner).")

    if body.decision == "APPROVE":
        if a.approval_type == "TARIFF":
            tariff = await db.get(WaterTariff, a.ref_id)
            if tariff.effective_from < today():
                raise bad_request("The tariff's effective date has passed. Reject it and propose it again with a future date.")
            tariff.status = "APPROVED"
            tariff.approved_by = ctx.username
            tariff.approved_at = utcnow()
        elif a.approval_type == "BILL_ADJUSTMENT":
            await post_bill_adjustment(db, ctx, a)
        elif a.approval_type == "RECEIPT_CANCEL":
            receipt = await db.get(WaterReceipt, a.ref_id)
            if receipt.status != "VALID":
                raise bad_request(f"Receipt is already {receipt.status}.")
            await reverse_receipt(db, ctx, receipt, "CANCELLED", a.reason, approval_id=a.id)
        elif a.approval_type == "REFUND":
            await post_refund(db, ctx, a)
        elif a.approval_type in ("WAIVER", "WRITE_OFF"):
            await post_waiver(db, ctx, a)
        else:
            raise bad_request(f"Unknown approval type {a.approval_type}.")
    elif a.approval_type == "TARIFF":
        tariff = await db.get(WaterTariff, a.ref_id)
        tariff.status = "REJECTED"

    a.status = "APPROVED" if body.decision == "APPROVE" else "REJECTED"
    a.decided_by = ctx.username
    a.decided_at = utcnow()
    a.decision_remark = body.remark
    audit(db, ctx, f"APPROVAL_{a.status}", "approval", a.id, {"status": "PENDING"},
          {"status": a.status, "type": a.approval_type, "ref": a.ref_no, "amount": float(a.amount) if a.amount is not None else None,
           "remark": body.remark})
    await db.commit()
    return {"message": f"Request {a.status.lower()}", "id": a.id, "status": a.status}
