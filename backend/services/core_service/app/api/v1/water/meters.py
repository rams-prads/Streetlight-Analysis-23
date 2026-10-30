"""Meters, reading routes and the single reading intake (WB-10..WB-19)."""
import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.water_calc import classify_reading, cycle_for_date, qty
from app.db.models import Ward
from app.db.session import get_read_db, get_write_db
from app.db.water_models import WaterBill, WaterConnection, WaterMeter, WaterReading, WaterRoute, utcnow
from app.schemas.water import (
    ConsumerReading, MeterFix, MeterStatusChange, ReadingIntake, ReadingIn, ReadingReview, RouteAssign,
    RouteCreate, RouteUpdate,
)
from .common import (
    WaterAPIRoute, WaterContext, audit, bad_request, conflict, emit_event, get_setting, load_connection, local_date, to_utc_naive,
    not_found, today, water_context,
)
from .connections import record_change

router = APIRouter(route_class=WaterAPIRoute)


def reading_dict(r: WaterReading, conn: Optional[WaterConnection] = None) -> Dict:
    return {
        "id": r.id, "consumerNo": conn.consumer_no if conn else None, "consumerName": conn.consumer_name if conn else None,
        "cycle": r.cycle, "readingValue": float(r.reading_value) if r.reading_value is not None else None,
        "previousValue": float(r.previous_value) if r.previous_value is not None else None,
        "consumptionKl": float(r.consumption_kl) if r.consumption_kl is not None else None,
        "noReadingReason": r.no_reading_reason, "readingAt": r.reading_at, "photoRef": r.photo_ref,
        "latitude": r.latitude, "longitude": r.longitude, "source": r.source, "flag": r.flag, "status": r.status,
        "reviewRemark": r.review_remark, "reviewedBy": r.reviewed_by, "capturedBy": r.captured_by,
    }


def meter_dict(m: WaterMeter, consumer_no: Optional[str] = None) -> Dict:
    return {
        "id": m.id, "consumerNo": consumer_no, "serialNo": m.serial_no, "make": m.make, "sizeMm": m.size_mm,
        "sealNo": m.seal_no, "initialReading": float(m.initial_reading), "carryOverKl": float(m.carry_over_kl or 0),
        "fixedOn": m.fixed_on, "status": m.status,
        "finalReading": float(m.final_reading) if m.final_reading is not None else None, "removedOn": m.removed_on,
    }


async def active_meter(db: AsyncSession, connection_id: str) -> Optional[WaterMeter]:
    return await db.scalar(select(WaterMeter).where(
        WaterMeter.connection_id == connection_id, WaterMeter.status.in_(["ACTIVE", "FAULTY"])))


async def last_accepted_value(db: AsyncSession, meter_id: str, before_cycle: str) -> Optional[Decimal]:
    row = await db.scalar(
        select(WaterReading).where(
            WaterReading.meter_id == meter_id, WaterReading.status == "ACCEPTED",
            WaterReading.reading_value.isnot(None), WaterReading.cycle < before_cycle)
        .order_by(WaterReading.cycle.desc(), WaterReading.reading_at.desc()).limit(1))
    return Decimal(str(row.reading_value)) if row else None


async def actual_history(db: AsyncSession, connection_id: str, before_cycle: str, n: int) -> List[Decimal]:
    rows = (await db.execute(
        select(WaterBill.consumption_kl).where(
            WaterBill.connection_id == connection_id, WaterBill.basis == "ACTUAL", WaterBill.cycle < before_cycle)
        .order_by(WaterBill.cycle.desc()).limit(n))).all()
    return [Decimal(str(r[0])) for r in rows]


# ------------------------------------------------------------------------------------------------
# Meter register (WB-10, WB-11)
# ------------------------------------------------------------------------------------------------

@router.get("/meters")
async def list_meters(status: Optional[str] = Query(None), q: Optional[str] = Query(None),
                      ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("connection.view")
    stmt = select(WaterMeter, WaterConnection.consumer_no).join(
        WaterConnection, WaterConnection.id == WaterMeter.connection_id
    ).where(WaterMeter.tenant_id == ctx.tenant_id, ctx.ward_filter(WaterConnection.ward_id))
    if status:
        stmt = stmt.where(WaterMeter.status == status.upper())
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(WaterMeter.serial_no.ilike(like) | WaterConnection.consumer_no.ilike(like))
    rows = (await db.execute(stmt.order_by(WaterMeter.fixed_on.desc()).limit(500))).all()
    return [meter_dict(m, c) for m, c in rows]


@router.get("/connections/{consumer_no}/meters")
async def connection_meters(consumer_no: str, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("connection.view")
    conn = await load_connection(db, ctx, consumer_no=consumer_no)
    rows = (await db.execute(select(WaterMeter).where(WaterMeter.connection_id == conn.id).order_by(WaterMeter.fixed_on.desc()))).scalars().all()
    return [meter_dict(m, conn.consumer_no) for m in rows]


@router.post("/connections/{consumer_no}/meter")
async def fix_or_replace_meter(consumer_no: str, payload: MeterFix, ctx: WaterContext = Depends(water_context),
                               db: AsyncSession = Depends(get_write_db)):
    """Fix a meter, or replace the current one recording its final reading (WB-10, WB-11)."""
    ctx.require("meter.manage")
    conn = await load_connection(db, ctx, consumer_no=consumer_no, for_update=True)
    if conn.status == "CLOSED":
        raise bad_request("The connection is permanently closed.")
    serial = payload.serial_no.strip()
    if await db.scalar(select(WaterMeter.id).where(WaterMeter.tenant_id == ctx.tenant_id, WaterMeter.serial_no == serial)):
        raise conflict(f"Meter serial {serial} is already registered.")
    cycle_months = int(await get_setting(db, ctx.tenant_id, "billing.cycleMonths"))
    old = await active_meter(db, conn.id)
    carry = Decimal("0")
    event = "meter.fixed"
    if old is not None:
        if payload.final_reading_of_old is None:
            raise bad_request("Enter the final reading of the old meter before replacing it.")
        cycle = cycle_for_date(payload.fixed_on, cycle_months)
        last = await last_accepted_value(db, old.id, cycle)
        base = last if last is not None else Decimal(str(old.initial_reading)) - Decimal(str(old.carry_over_kl or 0))
        final = Decimal(str(payload.final_reading_of_old))
        if final < (last if last is not None else Decimal(str(old.initial_reading))):
            raise bad_request(f"Final reading {final} is lower than the old meter's last billed reading "
                              f"{last if last is not None else old.initial_reading}. Check the reading.")
        carry = qty(final - base)
        old.status = "REPLACED"
        old.final_reading = final
        old.removed_on = payload.fixed_on
        event = "meter.replaced"
    meter = WaterMeter(
        tenant_id=ctx.tenant_id, connection_id=conn.id, serial_no=serial, make=payload.make.strip(),
        size_mm=payload.size_mm, seal_no=payload.seal_no, initial_reading=Decimal(str(payload.initial_reading)),
        carry_over_kl=carry, fixed_on=payload.fixed_on, status="ACTIVE", created_by=ctx.username,
    )
    db.add(meter)
    if not conn.is_metered:
        record_change(db, ctx, conn, "is_metered", True, f"Meter {serial} fixed: {payload.reason}")
    audit(db, ctx, "METER_REPLACED" if old else "METER_FIXED", "meter", conn.id,
          {"serialNo": old.serial_no, "finalReading": float(old.final_reading)} if old else None,
          {"serialNo": serial, "initialReading": payload.initial_reading, "carryOverKl": float(carry), "reason": payload.reason})
    emit_event(db, ctx.tenant_id, event, conn.id, {
        "consumerNo": conn.consumer_no, "serialNo": serial, "make": meter.make, "sizeMm": meter.size_mm,
        "oldSerialNo": old.serial_no if old else None,
    })
    await db.commit()
    return {"message": "Meter replaced" if old else "Meter fixed", "meter": meter_dict(meter, conn.consumer_no)}


@router.post("/connections/{consumer_no}/meter/status")
async def change_meter_status(consumer_no: str, payload: MeterStatusChange, ctx: WaterContext = Depends(water_context),
                              db: AsyncSession = Depends(get_write_db)):
    ctx.require("meter.manage")
    conn = await load_connection(db, ctx, consumer_no=consumer_no)
    meter = await active_meter(db, conn.id)
    if meter is None:
        raise not_found("No meter is fixed on this connection.")
    old = meter.status
    if old == payload.status:
        raise bad_request(f"Meter is already {old}.")
    meter.status = payload.status
    audit(db, ctx, "METER_STATUS", "meter", meter.id, {"status": old}, {"status": payload.status, "reason": payload.reason})
    await db.commit()
    return {"message": f"Meter marked {payload.status}", "serialNo": meter.serial_no}


# ------------------------------------------------------------------------------------------------
# Routes (WB-12)
# ------------------------------------------------------------------------------------------------

async def route_progress(db: AsyncSession, tenant_id: str, routes: List[WaterRoute], cycle: str) -> List[Dict]:
    out = []
    for route in routes:
        conns = (await db.execute(select(WaterConnection.id).where(
            WaterConnection.route_id == route.id, WaterConnection.status == "ACTIVE",
            WaterConnection.is_metered.is_(True)))).scalars().all()
        stats = {"read": 0, "noReading": 0, "pendingReview": 0}
        if conns:
            rows = (await db.execute(select(WaterReading.status, WaterReading.reading_value.isnot(None), func.count())
                                     .where(WaterReading.connection_id.in_(conns), WaterReading.cycle == cycle,
                                            WaterReading.status.in_(["ACCEPTED", "PENDING_REVIEW"]))
                                     .group_by(WaterReading.status, WaterReading.reading_value.isnot(None)))).all()
            for status, has_value, count in rows:
                if status == "PENDING_REVIEW":
                    stats["pendingReview"] += count
                elif has_value:
                    stats["read"] += count
                else:
                    stats["noReading"] += count
        total = len(conns)
        done = stats["read"] + stats["noReading"] + stats["pendingReview"]
        out.append({
            "id": route.id, "code": route.code, "name": route.name, "wardId": route.ward_id,
            "readerUsername": route.reader_username, "isActive": route.is_active, "cycle": cycle,
            "totalConnections": total, **stats, "remaining": max(total - done, 0),
            "completionPercent": round(done * 100.0 / total, 1) if total else 0.0,
        })
    return out


@router.get("/routes")
async def list_routes(cycle: Optional[str] = Query(None), ctx: WaterContext = Depends(water_context),
                      db: AsyncSession = Depends(get_read_db)):
    ctx.require("connection.view")
    cycle_months = int(await get_setting(db, ctx.tenant_id, "billing.cycleMonths"))
    cycle = cycle or cycle_for_date(today(), cycle_months)
    stmt = select(WaterRoute).where(WaterRoute.tenant_id == ctx.tenant_id)
    if ctx.allowed_ward_ids is not None:
        stmt = stmt.where(ctx.ward_filter(WaterRoute.ward_id))
    if ctx.roles <= {"meter_reader"} and ctx.roles:
        stmt = stmt.where(WaterRoute.reader_username == ctx.username)
    routes = (await db.execute(stmt.order_by(WaterRoute.code))).scalars().all()
    return await route_progress(db, ctx.tenant_id, routes, cycle)


@router.post("/routes", status_code=201)
async def create_route(payload: RouteCreate, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_write_db)):
    ctx.require("route.manage")
    code = payload.code.strip().upper()
    if await db.scalar(select(WaterRoute.id).where(WaterRoute.tenant_id == ctx.tenant_id, WaterRoute.code == code)):
        raise conflict(f"Route {code} already exists.")
    if payload.ward_id:
        if not await db.scalar(select(Ward.id).where(Ward.id == payload.ward_id, Ward.tenant_id == ctx.tenant_id)):
            raise bad_request("Ward not found.")
        ctx.ensure_scope(payload.ward_id)
    route = WaterRoute(tenant_id=ctx.tenant_id, sub_tenant_id=ctx.sub_tenant_id, code=code, name=payload.name,
                       ward_id=payload.ward_id, reader_username=payload.reader_username)
    db.add(route)
    audit(db, ctx, "ROUTE_CREATED", "route", route.id, None, payload.model_dump())
    await db.commit()
    return {"id": route.id, "code": route.code}


@router.patch("/routes/{route_id}")
async def update_route(route_id: str, payload: RouteUpdate, ctx: WaterContext = Depends(water_context),
                       db: AsyncSession = Depends(get_write_db)):
    ctx.require("route.manage")
    route = await db.scalar(select(WaterRoute).where(WaterRoute.id == route_id, WaterRoute.tenant_id == ctx.tenant_id))
    if not route:
        raise not_found("Route not found.")
    if route.ward_id:
        ctx.ensure_scope(route.ward_id)
    old = {"name": route.name, "readerUsername": route.reader_username, "isActive": route.is_active}
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(route, field, value)
    audit(db, ctx, "ROUTE_UPDATED", "route", route.id, old, payload.model_dump(exclude_unset=True))
    await db.commit()
    return {"message": "Route updated"}


@router.post("/routes/{route_id}/assign")
async def assign_to_route(route_id: str, payload: RouteAssign, ctx: WaterContext = Depends(water_context),
                          db: AsyncSession = Depends(get_write_db)):
    """Adds connections to a route in the order given (sequence continues after the last one)."""
    ctx.require("route.manage")
    route = await db.scalar(select(WaterRoute).where(WaterRoute.id == route_id, WaterRoute.tenant_id == ctx.tenant_id))
    if not route:
        raise not_found("Route not found.")
    seq = await db.scalar(select(func.max(WaterConnection.route_sequence)).where(WaterConnection.route_id == route.id)) or 0
    moved = []
    for consumer_no in payload.consumer_nos:
        conn = await load_connection(db, ctx, consumer_no=consumer_no, for_update=True)
        if conn.route_id == route.id:
            continue
        seq += 1
        record_change(db, ctx, conn, "route_id", route.id, f"Assigned to route {route.code}")
        record_change(db, ctx, conn, "route_sequence", seq, f"Assigned to route {route.code}")
        moved.append(conn.consumer_no)
    audit(db, ctx, "ROUTE_ASSIGNED", "route", route.id, None, {"consumerNos": moved})
    await db.commit()
    return {"message": f"{len(moved)} connection(s) assigned to {route.code}", "assigned": moved}


@router.get("/routes/{route_id}/sheet")
async def route_sheet(route_id: str, cycle: Optional[str] = Query(None), ctx: WaterContext = Depends(water_context),
                      db: AsyncSession = Depends(get_read_db)):
    """Reading sheet for the field app, downloaded before going offline (WB-12, WB-13)."""
    ctx.require("reading.capture")
    route = await db.scalar(select(WaterRoute).where(WaterRoute.id == route_id, WaterRoute.tenant_id == ctx.tenant_id))
    if not route:
        raise not_found("Route not found.")
    cycle_months = int(await get_setting(db, ctx.tenant_id, "billing.cycleMonths"))
    cycle = cycle or cycle_for_date(today(), cycle_months)
    conns = (await db.execute(select(WaterConnection).where(
        WaterConnection.route_id == route.id, WaterConnection.status == "ACTIVE", WaterConnection.is_metered.is_(True),
        ctx.ward_filter(WaterConnection.ward_id)).order_by(WaterConnection.route_sequence, WaterConnection.consumer_no))).scalars().all()
    rows = []
    for c in conns:
        meter = await active_meter(db, c.id)
        last = await last_accepted_value(db, meter.id, cycle) if meter else None
        this_cycle = await db.scalar(select(WaterReading).where(
            WaterReading.connection_id == c.id, WaterReading.cycle == cycle,
            WaterReading.status.in_(["ACCEPTED", "PENDING_REVIEW"])).order_by(WaterReading.reading_at.desc()).limit(1))
        rows.append({
            "consumerNo": c.consumer_no, "consumerName": c.consumer_name, "address": c.address, "doorNo": c.door_no,
            "sequence": c.route_sequence, "latitude": c.latitude, "longitude": c.longitude,
            "meterSerialNo": meter.serial_no if meter else None, "meterStatus": meter.status if meter else "NO_METER",
            "lastReading": float(last) if last is not None else (float(meter.initial_reading) if meter else None),
            "thisCycle": reading_dict(this_cycle) if this_cycle else None,
        })
    return {"route": {"id": route.id, "code": route.code, "name": route.name}, "cycle": cycle,
            "noReadingReasons": await get_setting(db, ctx.tenant_id, "reading.noReadingReasons"), "connections": rows}


# ------------------------------------------------------------------------------------------------
# Reading intake (WB-13..WB-19)
# ------------------------------------------------------------------------------------------------

async def ingest_reading(db: AsyncSession, ctx: WaterContext, item: ReadingIn, source: str,
                         conn: Optional[WaterConnection] = None) -> Dict:
    if item.client_ref:
        existing = await db.scalar(select(WaterReading).where(WaterReading.tenant_id == ctx.tenant_id,
                                                              WaterReading.client_ref == item.client_ref))
        if existing:
            return {"consumerNo": item.consumer_no, "result": "DUPLICATE_IGNORED", "readingId": existing.id,
                    "status": existing.status, "flag": existing.flag}
    conn = conn or await load_connection(db, ctx, consumer_no=item.consumer_no)
    if conn.status != "ACTIVE":
        raise bad_request(f"Connection {conn.consumer_no} is {conn.status}; readings are not taken.")
    if not conn.is_metered:
        raise bad_request(f"Connection {conn.consumer_no} is non-metered and billed at a flat rate.")
    if (item.reading_value is None) == (item.no_reading_reason is None):
        raise bad_request("Give either a meter reading or a reason why it could not be taken, not both.")
    if source in ("FIELD", "CONSUMER") and item.reading_value is not None and not item.photo_ref:
        raise bad_request("A meter photo is required with the reading.")
    if source == "FIELD" and item.reading_value is not None and (item.latitude is None or item.longitude is None):
        raise bad_request("GPS location is required with a field reading. Turn on location and try again.")

    cycle_months = int(await get_setting(db, ctx.tenant_id, "billing.cycleMonths"))
    reading_at = to_utc_naive(item.reading_at) if item.reading_at else utcnow()
    if reading_at > utcnow() + datetime.timedelta(minutes=10):
        raise bad_request("Reading time cannot be in the future.")
    cycle = cycle_for_date(local_date(reading_at), cycle_months)
    if await db.scalar(select(WaterBill.id).where(WaterBill.connection_id == conn.id, WaterBill.cycle == cycle)):
        raise conflict(f"The bill for {cycle} is already raised for {conn.consumer_no}; the reading cannot change it. Use a bill correction instead.")

    meter = await active_meter(db, conn.id)
    if meter is None:
        raise bad_request(f"No meter is registered on {conn.consumer_no}. Fix a meter first.")

    reading = WaterReading(
        tenant_id=ctx.tenant_id, connection_id=conn.id, meter_id=meter.id, route_id=conn.route_id, cycle=cycle,
        reading_at=reading_at, photo_ref=item.photo_ref, latitude=item.latitude, longitude=item.longitude,
        source=source, client_ref=item.client_ref, captured_by=ctx.username,
    )
    if item.no_reading_reason is not None:
        reasons = await get_setting(db, ctx.tenant_id, "reading.noReadingReasons")
        if item.no_reading_reason not in reasons:
            raise bad_request(f"Reason must be one of: {', '.join(reasons)}.")
        reading.no_reading_reason = item.no_reading_reason
        reading.status = "ACCEPTED"
        reading.flag = "NONE"
        if item.no_reading_reason == "METER_FAULTY" and meter.status == "ACTIVE":
            meter.status = "FAULTY"
            audit(db, ctx, "METER_STATUS", "meter", meter.id, {"status": "ACTIVE"}, {"status": "FAULTY", "reason": "Reported by reader"})
    else:
        value = qty(item.reading_value)
        last = await last_accepted_value(db, meter.id, cycle)
        base = last if last is not None else Decimal(str(meter.initial_reading)) - Decimal(str(meter.carry_over_kl or 0))
        rules = await get_setting(db, ctx.tenant_id, "reading.checks")
        history = await actual_history(db, conn.id, cycle, int(rules.get("n", 3)))
        flag, consumption = classify_reading(reading_value=value, previous_value=base, history=history, rules=rules)
        # compare with the real last reading, not the carry-over adjusted base used for consumption
        shown_previous = last if last is not None else Decimal(str(meter.initial_reading))
        if value < shown_previous:
            flag = "LOWER_THAN_LAST"
        reading.reading_value = value
        reading.previous_value = shown_previous
        reading.consumption_kl = consumption
        reading.flag = flag
        reading.status = "ACCEPTED" if flag == "NONE" else "PENDING_REVIEW"

    # a newer reading for the same cycle replaces the earlier one (only before billing)
    earlier = (await db.execute(select(WaterReading).where(
        WaterReading.connection_id == conn.id, WaterReading.cycle == cycle,
        WaterReading.status.in_(["ACCEPTED", "PENDING_REVIEW"])))).scalars().all()
    for e in earlier:
        e.status = "SUPERSEDED"
    db.add(reading)
    await db.flush()
    audit(db, ctx, "READING_CAPTURED", "reading", reading.id, None, {
        "consumerNo": conn.consumer_no, "cycle": cycle, "value": item.reading_value, "reason": item.no_reading_reason,
        "flag": reading.flag, "source": source,
    })
    return {"consumerNo": conn.consumer_no, "result": "STORED", "readingId": reading.id, "cycle": cycle,
            "status": reading.status, "flag": reading.flag,
            "consumptionKl": float(reading.consumption_kl) if reading.consumption_kl is not None else None}


@router.post("/readings/intake")
async def reading_intake(payload: ReadingIntake, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_write_db)):
    """Single intake for field, office, bulk-file and automatic meter readings (WB-19). Each row is handled on its own."""
    ctx.require("reading.capture")
    results = []
    for item in payload.readings:
        # ingest_reading runs every check before it changes anything, so a rejected row leaves no partial
        # writes and the rest of a synced batch is still stored (WB-NF-33)
        try:
            results.append(await ingest_reading(db, ctx, item, payload.source))
        except HTTPException as exc:
            results.append({"consumerNo": item.consumer_no, "result": "ERROR", "error": exc.detail, "clientRef": item.client_ref})
    await db.commit()
    return {
        "stored": sum(1 for r in results if r["result"] == "STORED"),
        "duplicates": sum(1 for r in results if r["result"] == "DUPLICATE_IGNORED"),
        "errors": sum(1 for r in results if r["result"] == "ERROR"),
        "flagged": sum(1 for r in results if r.get("status") == "PENDING_REVIEW"),
        "results": results,
    }


@router.post("/citizen/self-reading")
async def consumer_self_reading(payload: ConsumerReading, ctx: WaterContext = Depends(water_context),
                                db: AsyncSession = Depends(get_write_db)):
    """Consumer submits own reading with a photo; same checks as field readings (WB-18)."""
    if not ctx.can("reading.capture"):
        ctx.require("reading.self")
    conn = await db.scalar(select(WaterConnection).where(WaterConnection.tenant_id == ctx.tenant_id,
                                                         WaterConnection.consumer_no == payload.consumer_no.strip().upper()))
    if conn is None or not conn.mobile_number or conn.mobile_number[-10:] != "".join(ch for ch in payload.mobile_number if ch.isdigit())[-10:]:
        raise not_found("Consumer number and registered mobile number do not match our records.")
    result = await ingest_reading(db, ctx, ReadingIn(
        consumer_no=conn.consumer_no, reading_value=payload.reading_value, photo_ref=payload.photo_ref,
        latitude=payload.latitude, longitude=payload.longitude), "CONSUMER", conn=conn)
    await db.commit()
    return result


@router.get("/readings")
async def list_readings(status: Optional[str] = Query("PENDING_REVIEW"), cycle: Optional[str] = Query(None),
                        route_id: Optional[str] = Query(None, alias="routeId"), limit: int = Query(200, ge=1, le=1000),
                        ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("connection.view")
    stmt = select(WaterReading, WaterConnection).join(WaterConnection, WaterConnection.id == WaterReading.connection_id).where(
        WaterReading.tenant_id == ctx.tenant_id, ctx.ward_filter(WaterConnection.ward_id))
    if status:
        stmt = stmt.where(WaterReading.status == status.upper())
    if cycle:
        stmt = stmt.where(WaterReading.cycle == cycle)
    if route_id:
        stmt = stmt.where(WaterReading.route_id == route_id)
    rows = (await db.execute(stmt.order_by(WaterReading.reading_at.desc()).limit(limit))).all()
    return [reading_dict(r, c) for r, c in rows]


@router.post("/readings/{reading_id}/review")
async def review_reading(reading_id: str, payload: ReadingReview, ctx: WaterContext = Depends(water_context),
                         db: AsyncSession = Depends(get_write_db)):
    """Officer checks a flagged reading before a bill is raised (WB-15). A rejected reading is billed on average."""
    ctx.require("reading.review")
    reading = await db.scalar(select(WaterReading).where(WaterReading.id == reading_id, WaterReading.tenant_id == ctx.tenant_id).with_for_update())
    if not reading:
        raise not_found("Reading not found.")
    conn = await db.get(WaterConnection, reading.connection_id)
    ctx.ensure_scope(conn.ward_id)
    if reading.status != "PENDING_REVIEW":
        raise bad_request(f"Reading is {reading.status}; only readings waiting for review can be decided.")
    if payload.decision == "ACCEPT" and reading.flag == "LOWER_THAN_LAST":
        raise bad_request("A reading lower than the last one gives negative consumption and cannot be accepted. "
                          "Reject it (bill goes on average) or record a meter replacement if the meter was changed.")
    reading.status = "ACCEPTED" if payload.decision == "ACCEPT" else "REJECTED"
    reading.review_remark = payload.remark
    reading.reviewed_by = ctx.username
    audit(db, ctx, "READING_REVIEWED", "reading", reading.id, {"status": "PENDING_REVIEW"},
          {"status": reading.status, "remark": payload.remark})
    await db.commit()
    return {"message": f"Reading {reading.status.lower()}", "readingId": reading.id}
