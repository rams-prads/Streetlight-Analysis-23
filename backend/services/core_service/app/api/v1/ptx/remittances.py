"""
Remittance (PT-23): what the cashier has verified from collectors (day-end closings) is banked, with the challan number,
and then confirmed by a different officer against the bank credit. Nothing is banked twice: each closing joins one
remittance only. A difference at either stage must be explained.
"""
from decimal import Decimal
from typing import Dict, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ptx_calc import money
from app.db.ptx_models import PtxDayClose, PtxRemittance, utcnow
from app.db.session import get_read_db, get_write_db
from app.schemas.ptx import RemittanceConfirm, RemittanceCreate
from .common import PtxAPIRoute, PtxContext, audit, bad_request, conflict, dumps, loads, new_doc_no, not_found, page, paginate, ptx_context
from .payments import close_dict

router = APIRouter(route_class=PtxAPIRoute)


def remittance_dict(r: PtxRemittance) -> Dict:
    expected = money(r.expected_cash + r.expected_instruments)
    return {"id": r.id, "remittanceNo": r.remittance_no, "depositDate": r.deposit_date, "bankName": r.bank_name, "challanNo": r.challan_no,
            "closeIds": loads(r.close_ids_json, []), "expectedCash": float(r.expected_cash), "expectedInstruments": float(r.expected_instruments),
            "expectedTotal": float(expected), "depositedCash": float(r.deposited_cash), "depositedInstruments": float(r.deposited_instruments),
            "depositedTotal": float(money(r.deposited_cash + r.deposited_instruments)), "depositVariance": float(r.deposit_variance), "status": r.status,
            "preparedBy": r.prepared_by, "preparedAt": r.prepared_at, "creditDate": r.credit_date,
            "creditedAmount": float(r.credited_amount) if r.credited_amount is not None else None, "confirmedBy": r.confirmed_by,
            "confirmedAt": r.confirmed_at, "remark": r.remark}


def _can_see(ctx: PtxContext) -> None:
    if not (ctx.can("remittance.prepare") or ctx.can("remittance.confirm")):
        ctx.require("remittance.prepare")


@router.get("/remittances/pending-closes")
async def pending_closes(ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    """Verified day-end closings that have not been banked yet."""
    _can_see(ctx)
    rows = (await db.execute(select(PtxDayClose).where(PtxDayClose.tenant_id == ctx.tenant_id, PtxDayClose.status == "VERIFIED",
                                                       PtxDayClose.remittance_id.is_(None)).order_by(PtxDayClose.close_date))).scalars().all()
    items = [{**close_dict(c), "expectedCash": float(c.received_cash or 0), "expectedInstruments": float(c.system_non_cash)} for c in rows]
    return {"items": items, "totalCash": float(sum((c.received_cash or 0 for c in rows), Decimal("0"))),
            "totalInstruments": float(sum((c.system_non_cash for c in rows), Decimal("0")))}


@router.post("/remittances", status_code=201)
async def create_remittance(payload: RemittanceCreate, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    ctx.require("remittance.prepare")
    ids = list(dict.fromkeys(payload.close_ids))
    closes = (await db.execute(select(PtxDayClose).where(PtxDayClose.tenant_id == ctx.tenant_id, PtxDayClose.id.in_(ids)).with_for_update())).scalars().all()
    if len(closes) != len(ids):
        raise not_found("One of the day-end closings was not found.")
    for c in closes:
        if c.status != "VERIFIED":
            raise bad_request(f"The closing of {c.collector} on {c.close_date.strftime('%d-%m-%Y')} has not been verified by the cashier yet.")
        if c.remittance_id:
            raise conflict(f"The closing of {c.collector} on {c.close_date.strftime('%d-%m-%Y')} is already in a remittance.")
    if await db.scalar(select(PtxRemittance.id).where(PtxRemittance.tenant_id == ctx.tenant_id, PtxRemittance.challan_no == payload.challan_no.strip())):
        raise conflict("This challan number has already been used.")
    expected_cash = money(sum((c.received_cash or 0 for c in closes), Decimal("0")))
    expected_inst = money(sum((c.system_non_cash for c in closes), Decimal("0")))
    cash, inst = money(payload.deposited_cash), money(payload.deposited_instruments)
    variance = money(cash + inst - expected_cash - expected_inst)
    if variance != 0 and not (payload.remark or "").strip():
        raise bad_request(f"The amount banked differs from the verified amounts by Rs {variance}. Say why in the remark.")
    r = PtxRemittance(tenant_id=ctx.tenant_id, remittance_no=await new_doc_no(db, ctx.tenant_id, "PRM", "remittance"), deposit_date=payload.deposit_date,
                      bank_name=payload.bank_name.strip(), challan_no=payload.challan_no.strip(), close_ids_json=dumps(ids), expected_cash=expected_cash,
                      expected_instruments=expected_inst, deposited_cash=cash, deposited_instruments=inst, deposit_variance=variance,
                      prepared_by=ctx.username, remark=payload.remark)
    db.add(r)
    await db.flush()
    for c in closes:
        c.remittance_id = r.id
    audit(db, ctx, "REMITTANCE_PREPARED", "remittance", r.id, None, {"remittanceNo": r.remittance_no, "challanNo": r.challan_no, "cash": float(cash),
                                                                    "instruments": float(inst), "variance": float(variance)})
    await db.commit()
    return remittance_dict(r)


@router.get("/remittances")
async def list_remittances(search: Optional[str] = Query(None), status: Optional[str] = Query(None), skip: int = Query(0, ge=0),
                           limit: int = Query(50, ge=1, le=100), ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    _can_see(ctx)
    stmt = select(PtxRemittance).where(PtxRemittance.tenant_id == ctx.tenant_id)
    if status:
        stmt = stmt.where(PtxRemittance.status == status.upper())
    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(PtxRemittance.remittance_no.ilike(like), PtxRemittance.challan_no.ilike(like), PtxRemittance.bank_name.ilike(like)))
    rows, total = await paginate(db, stmt.order_by(PtxRemittance.prepared_at.desc()), skip, limit)
    return page([remittance_dict(r) for (r,) in rows], total, skip, limit)


@router.post("/remittances/{remittance_no}/confirm")
async def confirm_remittance(remittance_no: str, payload: RemittanceConfirm, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """A different officer checks the bank credit against what the cashier banked."""
    ctx.require("remittance.confirm")
    r = await db.scalar(select(PtxRemittance).where(PtxRemittance.tenant_id == ctx.tenant_id, PtxRemittance.remittance_no == remittance_no).with_for_update())
    if r is None:
        raise not_found(f"Remittance {remittance_no} not found.")
    if r.status != "SUBMITTED":
        raise conflict(f"This remittance is already {r.status.lower()}.")
    if r.prepared_by == ctx.username:
        raise bad_request("You prepared this remittance; another officer must confirm it.")
    if payload.credit_date < r.deposit_date:
        raise bad_request("The bank cannot have credited the money before it was deposited.")
    credited = money(payload.credited_amount)
    banked = money(r.deposited_cash + r.deposited_instruments)
    if credited != banked and not (payload.remark or "").strip():
        raise bad_request(f"The bank credited Rs {credited} but Rs {banked} was banked. Say what is being done about the difference.")
    r.status = "CONFIRMED" if credited == banked else "MISMATCH"
    r.credit_date, r.credited_amount, r.confirmed_by, r.confirmed_at = payload.credit_date, credited, ctx.username, utcnow()
    if payload.remark:
        r.remark = ((r.remark + " | ") if r.remark else "") + payload.remark
    audit(db, ctx, "REMITTANCE_CONFIRMED", "remittance", r.id, {"status": "SUBMITTED"}, {"status": r.status, "credited": float(credited), "banked": float(banked)})
    await db.commit()
    return remittance_dict(r)
