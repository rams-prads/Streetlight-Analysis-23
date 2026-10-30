"""Connection register: lookup, search, dues, history and officer corrections (WB-01..WB-08, WB-IR-01)."""
import math
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.water_calc import haversine_m, mask_mobile, money, normalise_address, payment_status
from app.db.models import Ward
from app.db.session import get_read_db, get_write_db
from app.db.water_models import (
    WaterBill, WaterCategory, WaterConnection, WaterConnectionHistory, WaterLedger, WaterMeter,
    WaterReading, WaterRoute,
)
from app.schemas.water import (
    ConnectionDetail, ConnectionSummary, ConnectionUpdate, DuesStatus, DuplicateCheckRequest,
)
from .common import (
    DEFAULT_SETTINGS, PERMISSIONS, WaterAPIRoute, WaterContext, audit, bad_request, balances,
    dues_summary, emit_event, get_setting, load_connection, ward_maps, water_context,
)

router = APIRouter(route_class=WaterAPIRoute)


async def bulk_balances(db: AsyncSession, tenant_id: str, ids: List[str]) -> Dict[str, Dict[str, Decimal]]:
    result: Dict[str, Dict[str, Decimal]] = {
        i: {b: Decimal("0.00") for b in ("PENALTY", "FEE", "ARREAR", "CURRENT", "ADVANCE", "DEPOSIT")} for i in ids
    }
    if not ids:
        return result
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        rows = (await db.execute(
            select(WaterLedger.connection_id, WaterLedger.bucket, func.coalesce(func.sum(WaterLedger.amount), 0))
            .where(WaterLedger.tenant_id == tenant_id, WaterLedger.connection_id.in_(chunk))
            .group_by(WaterLedger.connection_id, WaterLedger.bucket)
        )).all()
        for conn_id, bucket, total in rows:
            result[conn_id][bucket] = money(total)
    return result


def summary_of(conn: WaterConnection, wards: Dict, bal: Dict[str, Decimal]) -> ConnectionSummary:
    ward = wards.get(conn.ward_id, {})
    dues = dues_summary(bal)
    return ConnectionSummary(
        id=conn.id, consumer_no=conn.consumer_no, old_consumer_no=conn.old_consumer_no,
        consumer_name=conn.consumer_name, mobile_masked=mask_mobile(conn.mobile_number),
        address=conn.address, door_no=conn.door_no, ward_id=conn.ward_id,
        ward_number=ward.get("wardNumber"), ward_name=ward.get("wardName"), zone_name=ward.get("zoneName"),
        category_code=conn.category_code, pipe_size_mm=conn.pipe_size_mm, is_metered=conn.is_metered,
        status=conn.status, latitude=conn.latitude, longitude=conn.longitude,
        location_pending=conn.location_pending, total_due=dues["totalDue"], payment_status=payment_status(bal),
    )


async def dues_status_of(db: AsyncSession, conn: WaterConnection) -> DuesStatus:
    bal = await balances(db, conn.tenant_id, connection_id=conn.id)
    dues = dues_summary(bal)
    last_bill = await db.scalar(
        select(WaterBill).where(WaterBill.connection_id == conn.id).order_by(WaterBill.period_from.desc()).limit(1)
    )
    return DuesStatus(
        consumer_no=conn.consumer_no, status=conn.status, penalty=dues["penalty"], fees=dues["fees"],
        arrears=dues["arrears"], current=dues["current"], total_due=dues["totalDue"],
        advance_held=dues["advanceHeld"], deposit_held=dues["depositHeld"], net_payable=dues["netPayable"],
        payment_status=payment_status(bal), last_bill_no=last_bill.bill_no if last_bill else None,
        last_bill_due_date=last_bill.due_date if last_bill else None,
    )


async def find_duplicates(db: AsyncSession, tenant_id: str, *, address: Optional[str], door_no: Optional[str],
                          latitude: Optional[float], longitude: Optional[float],
                          exclude_connection_id: Optional[str] = None) -> List[Dict]:
    """Existing connections at the same address or within the configured distance on the map (WB-04)."""
    radius = float(await get_setting(db, tenant_id, "connection.duplicateRadiusM"))
    warnings: Dict[str, Dict] = {}
    base = select(WaterConnection).where(WaterConnection.tenant_id == tenant_id, WaterConnection.status != "CLOSED")
    if exclude_connection_id:
        base = base.where(WaterConnection.id != exclude_connection_id)

    if latitude is not None and longitude is not None:
        dlat = radius / 111320.0
        dlng = radius / (111320.0 * max(math.cos(math.radians(latitude)), 0.01))
        near = (await db.execute(base.where(
            WaterConnection.latitude.between(latitude - dlat, latitude + dlat),
            WaterConnection.longitude.between(longitude - dlng, longitude + dlng),
        ))).scalars().all()
        for c in near:
            distance = haversine_m(latitude, longitude, c.latitude, c.longitude)
            if distance <= radius:
                warnings[c.id] = {"consumerNo": c.consumer_no, "consumerName": c.consumer_name, "address": c.address,
                                  "reason": "NEARBY", "distanceM": round(distance, 1)}

    norm = normalise_address(address)
    if norm:
        tokens = [t for t in norm.split(" ") if len(t) > 2][:3]
        stmt = base
        for token in tokens:
            stmt = stmt.where(WaterConnection.address.ilike(f"%{token}%"))
        candidates = (await db.execute(stmt.limit(200))).scalars().all() if tokens else []
        door = normalise_address(door_no)
        for c in candidates:
            same_address = normalise_address(c.address) == norm
            same_door = bool(door) and normalise_address(c.door_no) == door and tokens and all(t in normalise_address(c.address) for t in tokens)
            if same_address or same_door:
                entry = warnings.setdefault(c.id, {"consumerNo": c.consumer_no, "consumerName": c.consumer_name,
                                                   "address": c.address, "reason": "SAME_ADDRESS", "distanceM": None})
                if entry["reason"] == "NEARBY":
                    entry["reason"] = "SAME_ADDRESS_AND_NEARBY"
    return list(warnings.values())


@router.get("/me")
async def my_water_access(ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    """What the signed-in user may do in the Water module, and the code lists the screens need."""
    categories = (await db.execute(
        select(WaterCategory).where(WaterCategory.tenant_id == ctx.tenant_id, WaterCategory.is_active.is_(True))
        .order_by(WaterCategory.code)
    )).scalars().all()
    wards, _ = await ward_maps(db, ctx.tenant_id)
    ward_list = sorted(
        [w for w in wards.values() if ctx.in_scope(w["wardId"])], key=lambda w: w["wardNumber"]
    )
    return {
        "username": ctx.username,
        "roles": sorted(ctx.roles),
        "tenantId": ctx.tenant_id,
        "scope": ctx.scope_label,
        "permissions": sorted(p for p in PERMISSIONS if ctx.can(p)),
        "categories": [{"code": c.code, "nameEn": c.name_en, "nameTe": c.name_te} for c in categories],
        "wards": ward_list,
        "noReadingReasons": await get_setting(db, ctx.tenant_id, "reading.noReadingReasons"),
        "cycleMonths": await get_setting(db, ctx.tenant_id, "billing.cycleMonths"),
        "upi": await get_setting(db, ctx.tenant_id, "upi"),
        "staffTimeoutMinutes": await get_setting(db, ctx.tenant_id, "session.staffTimeoutMinutes"),
        "settingKeys": sorted(DEFAULT_SETTINGS.keys()),
    }


@router.get("/connections", response_model=List[ConnectionSummary])
async def search_connections(
    q: Optional[str] = Query(None, description="Consumer no, old consumer no, name, mobile or address"),
    ward_id: Optional[str] = Query(None, alias="wardId"),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    payment_state: Optional[str] = Query(None, alias="paymentStatus", description="PAID, DUE or ARREARS"),
    location_pending: Optional[bool] = Query(None, alias="locationPending"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    ctx: WaterContext = Depends(water_context),
    db: AsyncSession = Depends(get_read_db),
):
    """Connection search by consumer number, old number, name, mobile or address (WB-07, WB-IR-01)."""
    ctx.require("connection.view")
    stmt = select(WaterConnection).where(WaterConnection.tenant_id == ctx.tenant_id, ctx.ward_filter(WaterConnection.ward_id))
    if ctx.sub_tenant_id:
        stmt = stmt.where(or_(WaterConnection.sub_tenant_id == ctx.sub_tenant_id, WaterConnection.sub_tenant_id.is_(None)))
    if q and q.strip():
        term = q.strip()
        like = f"%{term}%"
        digits = "".join(ch for ch in term if ch.isdigit())
        conds = [
            WaterConnection.consumer_no.ilike(like), WaterConnection.old_consumer_no.ilike(like),
            WaterConnection.consumer_name.ilike(like), WaterConnection.address.ilike(like),
            WaterConnection.door_no.ilike(like), WaterConnection.upin.ilike(like),
            WaterConnection.old_assessment_no.ilike(like),
        ]
        if len(digits) >= 4:
            conds.append(WaterConnection.mobile_number.ilike(f"%{digits}%"))
        stmt = stmt.where(or_(*conds))
    if ward_id:
        stmt = stmt.where(WaterConnection.ward_id == ward_id)
    if status:
        stmt = stmt.where(WaterConnection.status == status.upper())
    if category:
        stmt = stmt.where(WaterConnection.category_code == category.upper())
    if location_pending is not None:
        stmt = stmt.where(WaterConnection.location_pending.is_(location_pending))
    stmt = stmt.order_by(WaterConnection.consumer_no)
    if not payment_state:
        stmt = stmt.limit(limit).offset(offset)
    conns = (await db.execute(stmt)).scalars().all()
    wards, _ = await ward_maps(db, ctx.tenant_id)
    bal = await bulk_balances(db, ctx.tenant_id, [c.id for c in conns])
    rows = [summary_of(c, wards, bal[c.id]) for c in conns]
    if payment_state:
        rows = [r for r in rows if r.payment_status == payment_state.upper()][offset:offset + limit]
    return rows


@router.post("/connections/duplicate-check")
async def duplicate_check(payload: DuplicateCheckRequest, ctx: WaterContext = Depends(water_context),
                          db: AsyncSession = Depends(get_read_db)):
    ctx.require("connection.view")
    return await find_duplicates(db, ctx.tenant_id, address=payload.address, door_no=payload.door_no,
                                 latitude=payload.latitude, longitude=payload.longitude,
                                 exclude_connection_id=payload.exclude_connection_id)


@router.get("/connections/{consumer_no}", response_model=ConnectionDetail)
async def get_connection(consumer_no: str, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    """Connection lookup by consumer number (WB-IR-01)."""
    ctx.require("connection.view")
    conn = await load_connection(db, ctx, consumer_no=consumer_no)
    wards, _ = await ward_maps(db, ctx.tenant_id)
    bal = await balances(db, ctx.tenant_id, connection_id=conn.id)
    base = summary_of(conn, wards, bal)
    meter = await db.scalar(select(WaterMeter).where(WaterMeter.connection_id == conn.id, WaterMeter.status.in_(["ACTIVE", "FAULTY"])))
    route = await db.get(WaterRoute, conn.route_id) if conn.route_id else None
    return ConnectionDetail(
        **base.model_dump(),
        email=conn.email, aadhaar_masked=f"XXXX-XXXX-{conn.aadhaar_last4}" if conn.aadhaar_last4 else None,
        citizen_id=conn.citizen_id, locality=conn.locality, pincode=conn.pincode,
        old_assessment_no=conn.old_assessment_no, upin=conn.upin, upin_source=conn.upin_source,
        zone_id=conn.zone_id, supply_area=conn.supply_area, connection_date=conn.connection_date,
        route_id=conn.route_id, route_code=route.code if route else None, route_sequence=conn.route_sequence,
        source=conn.source, dues=await dues_status_of(db, conn),
        meter=None if meter is None else {
            "id": meter.id, "serialNo": meter.serial_no, "make": meter.make, "sizeMm": meter.size_mm,
            "sealNo": meter.seal_no, "initialReading": float(meter.initial_reading), "fixedOn": meter.fixed_on,
            "status": meter.status,
        },
        created_at=conn.created_at,
    )


@router.get("/connections/{consumer_no}/dues", response_model=DuesStatus)
async def get_dues(consumer_no: str, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    """Dues status (WB-IR-01)."""
    ctx.require("connection.view")
    conn = await load_connection(db, ctx, consumer_no=consumer_no)
    return await dues_status_of(db, conn)


def bill_dict(b: WaterBill, adjustments: Decimal = Decimal("0")) -> Dict:
    import json
    return {
        "id": b.id, "billNo": b.bill_no, "cycle": b.cycle, "periodFrom": b.period_from, "periodTo": b.period_to,
        "billDate": b.bill_date, "dueDate": b.due_date, "basis": b.basis, "categoryCode": b.category_code,
        "previousReading": float(b.previous_reading) if b.previous_reading is not None else None,
        "currentReading": float(b.current_reading) if b.current_reading is not None else None,
        "consumptionKl": float(b.consumption_kl), "slabBreakup": json.loads(b.slab_breakup_json or "[]"),
        "waterCharge": float(b.water_charge), "fixedCharge": float(b.fixed_charge), "cess": float(b.cess),
        "currentDemand": float(b.current_demand), "arrears": float(b.arrears), "penalty": float(b.penalty),
        "otherDues": float(b.other_dues), "advanceAdjusted": float(b.advance_adjusted),
        "totalPayable": float(b.total_payable), "approvedAdjustments": float(adjustments),
        "verificationCode": b.verification_code, "tariffId": b.tariff_id,
    }


@router.get("/connections/{consumer_no}/bills")
async def bill_history(consumer_no: str, limit: int = Query(24, ge=1, le=240),
                       ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    """Bill history (WB-IR-01)."""
    ctx.require("connection.view")
    conn = await load_connection(db, ctx, consumer_no=consumer_no)
    bills = (await db.execute(
        select(WaterBill).where(WaterBill.connection_id == conn.id).order_by(WaterBill.period_from.desc()).limit(limit)
    )).scalars().all()
    adj_rows = (await db.execute(
        select(WaterLedger.bill_id, func.sum(WaterLedger.amount))
        .where(WaterLedger.connection_id == conn.id, WaterLedger.txn_type == "ADJUSTMENT", WaterLedger.bill_id.isnot(None))
        .group_by(WaterLedger.bill_id)
    )).all()
    adjustments = {bill_id: money(total) for bill_id, total in adj_rows}
    return [bill_dict(b, adjustments.get(b.id, Decimal("0"))) for b in bills]


@router.get("/connections/{consumer_no}/ledger")
async def ledger_statement(consumer_no: str, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("connection.view")
    conn = await load_connection(db, ctx, consumer_no=consumer_no)
    rows = (await db.execute(
        select(WaterLedger).where(WaterLedger.connection_id == conn.id).order_by(WaterLedger.created_at, WaterLedger.id)
    )).scalars().all()
    running = Decimal("0.00")
    out = []
    for r in rows:
        if r.bucket in ("PENALTY", "FEE", "ARREAR", "CURRENT", "ADVANCE"):
            running = money(running + r.amount)
        out.append({
            "id": r.id, "entryDate": r.entry_date, "txnType": r.txn_type, "component": r.component,
            "bucket": r.bucket, "accountHead": r.account_head, "amount": float(r.amount),
            "paymentMode": r.payment_mode, "referenceNo": r.reference_no, "billId": r.bill_id,
            "receiptId": r.receipt_id, "isReversal": r.is_reversal, "narration": r.narration,
            "createdBy": r.created_by, "netBalance": float(running),
        })
    return out


@router.get("/connections/{consumer_no}/history")
async def change_history(consumer_no: str, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    """Every change to the record: old value, new value, who, when and why (WB-08)."""
    ctx.require("connection.view")
    conn = await load_connection(db, ctx, consumer_no=consumer_no)
    rows = (await db.execute(
        select(WaterConnectionHistory).where(WaterConnectionHistory.connection_id == conn.id)
        .order_by(WaterConnectionHistory.changed_at.desc())
    )).scalars().all()
    return [{"field": r.field, "oldValue": r.old_value, "newValue": r.new_value, "reason": r.reason,
             "changedBy": r.changed_by, "changedAt": r.changed_at} for r in rows]


@router.get("/connections/{consumer_no}/readings")
async def reading_history(consumer_no: str, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("connection.view")
    conn = await load_connection(db, ctx, consumer_no=consumer_no)
    rows = (await db.execute(
        select(WaterReading).where(WaterReading.connection_id == conn.id).order_by(WaterReading.reading_at.desc()).limit(60)
    )).scalars().all()
    from .meters import reading_dict
    return [reading_dict(r, conn) for r in rows]


def record_change(db: AsyncSession, ctx: WaterContext, conn: WaterConnection, field: str, new_value, reason: str) -> bool:
    """Sets a field and writes a history row if the value really changed (WB-08)."""
    old_value = getattr(conn, field)
    if (old_value if old_value != "" else None) == (new_value if new_value != "" else None):
        return False
    setattr(conn, field, new_value)
    db.add(WaterConnectionHistory(
        tenant_id=conn.tenant_id, connection_id=conn.id, field=field,
        old_value=None if old_value is None else str(old_value),
        new_value=None if new_value is None else str(new_value),
        reason=reason, changed_by=ctx.username,
    ))
    return True


@router.patch("/connections/{consumer_no}")
async def update_connection(consumer_no: str, payload: ConnectionUpdate, ctx: WaterContext = Depends(water_context),
                            db: AsyncSession = Depends(get_write_db)):
    ctx.require("connection.edit")
    conn = await load_connection(db, ctx, consumer_no=consumer_no, for_update=True)
    if conn.status == "CLOSED":
        raise bad_request("This connection is permanently closed and cannot be changed.")
    changes = payload.model_dump(exclude_unset=True, exclude={"reason"})
    if ("latitude" in changes) != ("longitude" in changes):
        raise bad_request("Send latitude and longitude together.")
    if "ward_id" in changes:
        ward = await db.scalar(select(Ward).where(Ward.id == changes["ward_id"], Ward.tenant_id == ctx.tenant_id))
        if ward is None:
            raise bad_request("Ward not found.")
        ctx.ensure_scope(ward.id)
        changes["zone_id"] = ward.zone_id
    if changes.get("route_id"):
        route = await db.scalar(select(WaterRoute).where(WaterRoute.id == changes["route_id"], WaterRoute.tenant_id == ctx.tenant_id))
        if route is None:
            raise bad_request("Route not found.")
    if "upin" in changes and changes.get("upin") and not changes.get("upin_source"):
        changes["upin_source"] = "STAFF"
    old = {}
    for field, value in changes.items():
        before = getattr(conn, field)
        if record_change(db, ctx, conn, field, value, payload.reason):
            old[field] = before
    if conn.latitude is not None and conn.longitude is not None and conn.location_pending:
        record_change(db, ctx, conn, "location_pending", False, payload.reason)
    if not old:
        raise bad_request("Nothing changed: the values sent are the same as the current record.")
    audit(db, ctx, "CONNECTION_UPDATED", "connection", conn.id, old, {k: changes[k] for k in old})
    emit_event(db, ctx.tenant_id, "connection.changed", conn.id,
               {"consumerNo": conn.consumer_no, "fields": sorted(old.keys())})
    await db.commit()
    return {"message": "Connection updated", "consumerNo": conn.consumer_no, "changedFields": sorted(old.keys())}
