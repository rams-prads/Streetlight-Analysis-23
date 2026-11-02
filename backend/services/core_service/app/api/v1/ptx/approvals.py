"""
Maker-checker approvals for rate tables (SRS 3.4), receipt cancellation (PT-34), refunds (PT-40), waivers and write-offs
(PT-45). The person who asks can never decide their own request, and each role decides only up to its configured amount.
"""
from decimal import Decimal
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ptx_calc import money
from app.db.ptx_models import PtxApproval, PtxProperty, PtxRateTable, PtxReceipt, utcnow
from app.db.session import get_read_db, get_write_db
from app.schemas.ptx import ApprovalDecision
from .arrears import post_waiver
from .billing import post_correction
from .common import ADMIN, PtxAPIRoute, PtxContext, audit, bad_request, get_setting, loads, not_found, page, paginate, ptx_context, today
from .payments import post_refund, reverse_receipt

router = APIRouter(route_class=PtxAPIRoute)


async def approval_limit(db: AsyncSession, ctx: PtxContext) -> Optional[Decimal]:
    if ctx.roles & ADMIN:
        return None
    limits: Dict = await get_setting(db, ctx.tenant_id, "approval.limits")
    best = Decimal("-1")
    for role in ctx.roles:
        if role in limits:
            if limits[role] is None:
                return None
            best = max(best, Decimal(str(limits[role])))
    if best < 0:
        raise HTTPException(status_code=403, detail="Your role has no approval authority for amounts.")
    return best


async def can_decide(db: AsyncSession, ctx: PtxContext, a: PtxApproval) -> bool:
    if a.status != "PENDING" or a.requested_by == ctx.username:
        return False
    if a.approval_type == "RATE_TABLE":
        return ctx.can("rates.approve")
    if not ctx.can("approval.decide"):
        return False
    try:
        limit = await approval_limit(db, ctx)
    except HTTPException:
        return False
    return limit is None or abs(money(a.amount or 0)) <= limit


@router.get("/approvals")
async def list_approvals(status: Optional[str] = Query("PENDING"), approval_type: Optional[str] = Query(None, alias="type"),
                         search: Optional[str] = Query(None), skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                         ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    if not (ctx.can("approval.decide") or ctx.can("approval.request") or ctx.can("rates.approve")):
        ctx.require("approval.decide")
    stmt = select(PtxApproval, PtxProperty.upin, PtxProperty.ward_id).outerjoin(PtxProperty, PtxProperty.id == PtxApproval.property_id).where(
        PtxApproval.tenant_id == ctx.tenant_id)
    if ctx.allowed_ward_ids is not None:
        stmt = stmt.where((PtxApproval.property_id.is_(None)) | ctx.ward_filter(PtxProperty.ward_id))
    if status:
        stmt = stmt.where(PtxApproval.status == status.upper())
    if approval_type:
        stmt = stmt.where(PtxApproval.approval_type == approval_type.upper())
    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(PtxApproval.ref_no.ilike(like) | PtxApproval.reason.ilike(like) | PtxApproval.requested_by.ilike(like))
    rows, total = await paginate(db, stmt.order_by(PtxApproval.requested_at.desc()), skip, limit)
    items = []
    for a, upin, _ in rows:
        items.append({"id": a.id, "approvalType": a.approval_type, "upin": upin, "refNo": a.ref_no,
                      "amount": float(a.amount) if a.amount is not None else None, "details": loads(a.payload_json, {}), "reason": a.reason,
                      "status": a.status, "requestedBy": a.requested_by, "requestedAt": a.requested_at, "decidedBy": a.decided_by,
                      "decidedAt": a.decided_at, "decisionRemark": a.decision_remark, "canDecide": await can_decide(db, ctx, a)})
    return page(items, total, skip, limit)


@router.post("/approvals/{approval_id}/decide")
async def decide(approval_id: str, body: ApprovalDecision, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    a = await db.scalar(select(PtxApproval).where(PtxApproval.id == approval_id, PtxApproval.tenant_id == ctx.tenant_id).with_for_update())
    if a is None:
        raise not_found("Approval request not found.")
    if a.status != "PENDING":
        raise bad_request(f"This request is already {a.status.lower()}.")
    if a.requested_by == ctx.username:
        raise bad_request("You cannot decide your own request. Another authorised officer must decide it.")
    if a.property_id:
        prop = await db.get(PtxProperty, a.property_id)
        ctx.ensure_scope(prop.ward_id)
    if a.approval_type == "RATE_TABLE":
        ctx.require("rates.approve")
    else:
        ctx.require("approval.decide")
        limit = await approval_limit(db, ctx)
        if limit is not None and abs(money(a.amount or 0)) > limit:
            raise HTTPException(status_code=403, detail=f"Rs {abs(money(a.amount))} is above your approval limit of Rs {limit}. It needs the Commissioner.")
    if body.decision == "APPROVE":
        if a.approval_type == "RATE_TABLE":
            table = await db.get(PtxRateTable, a.ref_id)
            if table.effective_from < today():
                raise bad_request("The rate table's effective date has passed. Reject it and propose it again with a future date.")
            table.status, table.approved_by, table.approved_at = "APPROVED", ctx.username, utcnow()
        elif a.approval_type == "RECEIPT_CANCEL":
            r = await db.get(PtxReceipt, a.ref_id)
            if r.status != "VALID":
                raise bad_request(f"Receipt is already {r.status.lower()}.")
            await reverse_receipt(db, ctx, r, "CANCELLED", a.reason, approval_id=a.id)
        elif a.approval_type == "REFUND":
            await post_refund(db, ctx, a)
        elif a.approval_type in ("WAIVER", "WRITE_OFF"):
            await post_waiver(db, ctx, a)
        elif a.approval_type == "DEMAND_CORRECTION":
            await post_correction(db, ctx, a)
        else:
            raise bad_request(f"Unknown approval type {a.approval_type}.")
    elif a.approval_type == "RATE_TABLE":
        (await db.get(PtxRateTable, a.ref_id)).status = "REJECTED"
    a.status = "APPROVED" if body.decision == "APPROVE" else "REJECTED"
    a.decided_by, a.decided_at, a.decision_remark = ctx.username, utcnow(), body.remark
    audit(db, ctx, f"APPROVAL_{a.status}", "approval", a.id, {"status": "PENDING"},
          {"status": a.status, "type": a.approval_type, "ref": a.ref_no, "amount": float(a.amount) if a.amount is not None else None, "remark": body.remark})
    await db.commit()
    return {"message": f"Request {a.status.lower()}", "id": a.id, "status": a.status}
