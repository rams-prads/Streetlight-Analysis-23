"""Reports, dashboards, consumption analysis and GIS layers (WB-54, WB-55, WB-60..WB-66)."""
import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.water_calc import cycle_for_date, financial_year_start, money, payment_status
from app.db.session import get_read_db
from app.db.water_models import (
    WaterBill, WaterComplaint, WaterConnection, WaterIllegalCase, WaterLedger, WaterMeter, WaterOrder, WaterRoute,
    utcnow,
)
from .common import (
    DUES_BUCKETS, WaterAPIRoute, WaterContext, bad_request, get_setting, local_day_start_utc, today, ward_maps, water_context,
)
from .connections import bulk_balances
from .meters import route_progress

router = APIRouter(route_class=WaterAPIRoute)

DEMAND_TYPES = ("DEMAND", "PENALTY", "FEE", "OPENING_ARREAR")


def _f(value) -> float:
    return float(money(value or 0))


def _require_reports(ctx: WaterContext) -> None:
    ctx.require("reports.view")


def _period(date_from: Optional[datetime.date], date_to: Optional[datetime.date]):
    date_to = date_to or today()
    date_from = date_from or financial_year_start(date_to)
    if date_from > date_to:
        raise bad_request("'From' date must be on or before 'to' date.")
    return date_from, date_to


async def dcb_by_ward(db: AsyncSession, ctx: WaterContext, date_from: datetime.date, date_to: datetime.date) -> Dict[str, Dict]:
    """Demand, collection and balance per ward for a period (WB-62). Covers consumer dues buckets only."""
    base = and_(WaterLedger.tenant_id == ctx.tenant_id, WaterLedger.connection_id.isnot(None),
                WaterLedger.bucket.in_(DUES_BUCKETS), ctx.ward_filter(WaterLedger.ward_id))
    in_period = and_(WaterLedger.entry_date >= date_from, WaterLedger.entry_date <= date_to)
    rows = (await db.execute(select(
        WaterLedger.ward_id,
        func.coalesce(func.sum(case((WaterLedger.entry_date < date_from, WaterLedger.amount), else_=0)), 0),
        func.coalesce(func.sum(case((and_(in_period, WaterLedger.txn_type.in_(DEMAND_TYPES)), WaterLedger.amount), else_=0)), 0),
        func.coalesce(func.sum(case((and_(in_period, WaterLedger.txn_type == "PAYMENT"), WaterLedger.amount), else_=0)), 0),
        func.coalesce(func.sum(case((in_period, WaterLedger.amount), else_=0)), 0),
    ).where(base, WaterLedger.entry_date <= date_to).group_by(WaterLedger.ward_id))).all()
    out = {}
    for ward_id, opening, demand, payments, movement in rows:
        opening, demand, collection = money(opening), money(demand), money(-payments)
        closing = money(opening + money(movement))
        adjustments = money(closing - opening - demand + collection)
        out[ward_id] = {"opening": opening, "demand": demand, "collection": collection,
                        "adjustments": adjustments, "closing": closing}
    return out


def _efficiency(collection: Decimal, opening: Decimal, demand: Decimal) -> Optional[float]:
    due = opening + demand
    return round(float(collection / due * 100), 2) if due > 0 else None


@router.get("/reports/dcb")
async def dcb_register(date_from: Optional[datetime.date] = Query(None, alias="from"),
                       date_to: Optional[datetime.date] = Query(None, alias="to"),
                       group_by: str = Query("ward", alias="groupBy"),
                       ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    """Water DCB register and collection efficiency by ward or zone for any period (WB-62)."""
    _require_reports(ctx)
    date_from, date_to = _period(date_from, date_to)
    data = await dcb_by_ward(db, ctx, date_from, date_to)
    wards, zones = await ward_maps(db, ctx.tenant_id)
    groups: Dict[str, Dict] = {}
    for ward_id, row in data.items():
        ward = wards.get(ward_id, {})
        if group_by == "zone":
            key = ward.get("zoneId") or "UNKNOWN"
            label = {"zoneCode": ward.get("zoneCode"), "zoneName": ward.get("zoneName")}
        else:
            key = ward_id or "UNKNOWN"
            label = {"wardNumber": ward.get("wardNumber"), "wardName": ward.get("wardName"), "zoneName": ward.get("zoneName")}
        g = groups.setdefault(key, {**label, "opening": Decimal("0"), "demand": Decimal("0"), "collection": Decimal("0"),
                                    "adjustments": Decimal("0"), "closing": Decimal("0")})
        for k in ("opening", "demand", "collection", "adjustments", "closing"):
            g[k] += row[k]
    rows = []
    totals = {k: Decimal("0") for k in ("opening", "demand", "collection", "adjustments", "closing")}
    for g in groups.values():
        for k in totals:
            totals[k] += g[k]
        rows.append({**{k: v for k, v in g.items() if not isinstance(v, Decimal)},
                     **{k: _f(g[k]) for k in totals}, "efficiencyPercent": _efficiency(g["collection"], g["opening"], g["demand"])})
    rows.sort(key=lambda r: (r.get("wardNumber") or 0, r.get("zoneCode") or ""))
    return {"from": date_from, "to": date_to, "groupBy": group_by, "rows": rows,
            "totals": {**{k: _f(v) for k, v in totals.items()},
                       "efficiencyPercent": _efficiency(totals["collection"], totals["opening"], totals["demand"])},
            "note": "Opening = balance before 'from'. Demand = bills, penalty, fees and migrated arrears. "
                    "Collection = payments net of cancelled/returned receipts. Adjustments = approved corrections, waivers, "
                    "write-offs and advance/deposit applied. Efficiency = collection / (opening + demand)."}


@router.get("/reports/billing")
async def billing_report(cycle: Optional[str] = Query(None), ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    _require_reports(ctx)
    cycle_months = int(await get_setting(db, ctx.tenant_id, "billing.cycleMonths"))
    cycle = cycle or cycle_for_date(today(), cycle_months)
    rows = (await db.execute(select(
        WaterBill.ward_id, WaterBill.basis, func.count(WaterBill.id), func.coalesce(func.sum(WaterBill.consumption_kl), 0),
        func.coalesce(func.sum(WaterBill.current_demand), 0)).where(
        WaterBill.tenant_id == ctx.tenant_id, WaterBill.cycle == cycle, ctx.ward_filter(WaterBill.ward_id))
        .group_by(WaterBill.ward_id, WaterBill.basis))).all()
    wards, _ = await ward_maps(db, ctx.tenant_id)
    out: Dict[str, Dict] = {}
    for ward_id, basis, count, kl, demand in rows:
        ward = wards.get(ward_id, {})
        r = out.setdefault(ward_id, {"wardNumber": ward.get("wardNumber"), "wardName": ward.get("wardName"), "bills": 0,
                                     "ACTUAL": 0, "AVERAGE": 0, "FLAT": 0, "consumptionKl": 0.0, "demand": 0.0})
        r["bills"] += count
        r[basis] += count
        r["consumptionKl"] = round(r["consumptionKl"] + float(kl), 3)
        r["demand"] = round(r["demand"] + _f(demand), 2)
    active = await db.scalar(select(func.count(WaterConnection.id)).where(
        WaterConnection.tenant_id == ctx.tenant_id, WaterConnection.status == "ACTIVE", ctx.ward_filter(WaterConnection.ward_id)))
    rows_out = sorted(out.values(), key=lambda r: r["wardNumber"] or 0)
    return {"cycle": cycle, "activeConnections": active, "rows": rows_out,
            "totals": {"bills": sum(r["bills"] for r in rows_out), "demand": round(sum(r["demand"] for r in rows_out), 2),
                       "consumptionKl": round(sum(r["consumptionKl"] for r in rows_out), 3)}}


@router.get("/reports/reading-completion")
async def reading_completion(cycle: Optional[str] = Query(None), ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    _require_reports(ctx)
    cycle_months = int(await get_setting(db, ctx.tenant_id, "billing.cycleMonths"))
    cycle = cycle or cycle_for_date(today(), cycle_months)
    routes = (await db.execute(select(WaterRoute).where(WaterRoute.tenant_id == ctx.tenant_id, ctx.ward_filter(WaterRoute.ward_id))
                               .order_by(WaterRoute.code))).scalars().all()
    by_route = await route_progress(db, ctx.tenant_id, routes, cycle)
    by_reader: Dict[str, Dict] = {}
    for r in by_route:
        key = r["readerUsername"] or "Unassigned"
        agg = by_reader.setdefault(key, {"reader": key, "routes": 0, "totalConnections": 0, "read": 0, "noReading": 0,
                                         "pendingReview": 0, "remaining": 0})
        agg["routes"] += 1
        for k in ("totalConnections", "read", "noReading", "pendingReview", "remaining"):
            agg[k] += r[k]
    for agg in by_reader.values():
        done = agg["read"] + agg["noReading"] + agg["pendingReview"]
        agg["completionPercent"] = round(done * 100.0 / agg["totalConnections"], 1) if agg["totalConnections"] else 0.0
    return {"cycle": cycle, "byRoute": by_route, "byReader": sorted(by_reader.values(), key=lambda a: a["reader"])}


@router.get("/reports/meter-status")
async def meter_status(ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    _require_reports(ctx)
    rows = (await db.execute(select(WaterMeter.status, func.count(WaterMeter.id)).join(
        WaterConnection, WaterConnection.id == WaterMeter.connection_id).where(
        WaterMeter.tenant_id == ctx.tenant_id, ctx.ward_filter(WaterConnection.ward_id)).group_by(WaterMeter.status))).all()
    faulty = (await db.execute(select(WaterMeter, WaterConnection).join(WaterConnection, WaterConnection.id == WaterMeter.connection_id)
                               .where(WaterMeter.tenant_id == ctx.tenant_id, WaterMeter.status == "FAULTY",
                                      ctx.ward_filter(WaterConnection.ward_id)))).all()
    metered_without = (await db.execute(select(WaterConnection.consumer_no).where(
        WaterConnection.tenant_id == ctx.tenant_id, WaterConnection.is_metered.is_(True), WaterConnection.status == "ACTIVE",
        ctx.ward_filter(WaterConnection.ward_id),
        ~select(WaterMeter.id).where(WaterMeter.connection_id == WaterConnection.id,
                                     WaterMeter.status.in_(["ACTIVE", "FAULTY"])).exists()))).scalars().all()
    return {"byStatus": {s: c for s, c in rows},
            "faulty": [{"consumerNo": c.consumer_no, "consumerName": c.consumer_name, "serialNo": m.serial_no,
                        "make": m.make, "sizeMm": m.size_mm, "fixedOn": m.fixed_on} for m, c in faulty],
            "meteredWithoutMeter": metered_without}


@router.get("/reports/disconnections")
async def disconnection_report(date_from: Optional[datetime.date] = Query(None, alias="from"),
                               date_to: Optional[datetime.date] = Query(None, alias="to"),
                               ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    _require_reports(ctx)
    date_from, date_to = _period(date_from, date_to)
    start = local_day_start_utc(date_from)
    end = local_day_start_utc(date_to + datetime.timedelta(days=1)) - datetime.timedelta(microseconds=1)
    orders = (await db.execute(select(WaterOrder).where(WaterOrder.tenant_id == ctx.tenant_id, ctx.ward_filter(WaterOrder.ward_id),
                                                        WaterOrder.created_at >= start, WaterOrder.created_at <= end))).scalars().all()
    executed = (await db.execute(select(WaterOrder).where(WaterOrder.tenant_id == ctx.tenant_id, ctx.ward_filter(WaterOrder.ward_id),
                                                          WaterOrder.executed_at >= start, WaterOrder.executed_at <= end))).scalars().all()
    now = utcnow()
    pending_recon = (await db.execute(select(WaterOrder).where(WaterOrder.tenant_id == ctx.tenant_id, WaterOrder.order_type == "RECONNECTION",
                                                               WaterOrder.status == "PENDING", ctx.ward_filter(WaterOrder.ward_id)))).scalars().all()
    completed_recon = [o for o in executed if o.order_type == "RECONNECTION"]
    return {
        "from": date_from, "to": date_to,
        "noticesIssued": sum(1 for o in orders if o.order_type == "NOTICE"),
        "noticesWithdrawn": sum(1 for o in orders if o.order_type == "NOTICE" and o.status == "WITHDRAWN"),
        "listedForDisconnection": sum(1 for o in orders if o.order_type == "DISCONNECTION"),
        "disconnectionsExecuted": sum(1 for o in executed if o.order_type == "DISCONNECTION"),
        "reconnectionsRequested": sum(1 for o in orders if o.order_type == "RECONNECTION"),
        "reconnectionsCompleted": len(completed_recon),
        "reconnectionsWithinSla": sum(1 for o in completed_recon if o.sla_due_at and o.executed_at <= o.sla_due_at),
        "reconnectionsPending": len(pending_recon),
        "reconnectionsPastSla": sum(1 for o in pending_recon if o.sla_due_at and now > o.sla_due_at),
    }


@router.get("/reports/complaint-sla")
async def complaint_sla(date_from: Optional[datetime.date] = Query(None, alias="from"),
                        date_to: Optional[datetime.date] = Query(None, alias="to"),
                        ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    _require_reports(ctx)
    date_from, date_to = _period(date_from, date_to)
    start = local_day_start_utc(date_from)
    end = local_day_start_utc(date_to + datetime.timedelta(days=1)) - datetime.timedelta(microseconds=1)
    rows = (await db.execute(select(WaterComplaint).where(WaterComplaint.tenant_id == ctx.tenant_id, ctx.ward_filter(WaterComplaint.ward_id),
                                                          WaterComplaint.created_at >= start, WaterComplaint.created_at <= end))).scalars().all()
    now = utcnow()
    by_type: Dict[str, Dict] = {}
    for c in rows:
        t = by_type.setdefault(c.complaint_type, {"type": c.complaint_type, "raised": 0, "closed": 0, "closedWithinSla": 0,
                                                  "openWithinSla": 0, "openPastSla": 0, "hours": []})
        t["raised"] += 1
        if c.status == "CLOSED":
            t["closed"] += 1
            t["closedWithinSla"] += 1 if c.closed_at <= c.sla_due_at else 0
            t["hours"].append((c.closed_at - c.created_at).total_seconds() / 3600)
        elif now > c.sla_due_at:
            t["openPastSla"] += 1
        else:
            t["openWithinSla"] += 1
    out = []
    for t in by_type.values():
        hours = t.pop("hours")
        t["avgResolutionHours"] = round(sum(hours) / len(hours), 1) if hours else None
        t["slaCompliancePercent"] = round(t["closedWithinSla"] * 100.0 / t["closed"], 1) if t["closed"] else None
        out.append(t)
    return {"from": date_from, "to": date_to, "rows": sorted(out, key=lambda r: r["type"])}


@router.get("/reports/account-heads")
async def account_head_summary(day: Optional[datetime.date] = Query(None), month: Optional[str] = Query(None),
                               ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    """
    Daily or monthly summary of demand, collection, refunds, deposits and write-offs by account head (WB-65),
    for the accounts section until Finance & Accounting (Module 4) is live. Internal moves (arrears roll-over,
    advance/deposit transfers) are left out because they are not money in or out.
    """
    _require_reports(ctx)
    if month:
        try:
            year, mon = (int(x) for x in month.split("-"))
            date_from = datetime.date(year, mon, 1)
        except ValueError:
            raise bad_request("Month must be YYYY-MM.")
        date_to = (date_from.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)
        label = date_from.strftime("%B %Y")
    else:
        date_from = date_to = day or today()
        label = date_from.strftime("%d-%m-%Y")
    rows = (await db.execute(select(WaterLedger.account_head, WaterLedger.component, WaterLedger.txn_type,
                                    func.coalesce(func.sum(WaterLedger.amount), 0)).where(
        WaterLedger.tenant_id == ctx.tenant_id, ctx.ward_filter(WaterLedger.ward_id),
        WaterLedger.entry_date >= date_from, WaterLedger.entry_date <= date_to,
        WaterLedger.txn_type.notin_(["ROLLOVER", "TRANSFER", "DEPOSIT_HELD"]))
        .group_by(WaterLedger.account_head, WaterLedger.component, WaterLedger.txn_type))).all()
    heads: Dict[str, Dict] = {}
    for head, component, txn_type, amount in rows:
        h = heads.setdefault(head, {"accountHead": head, "components": set(), "demand": Decimal("0"), "collection": Decimal("0"),
                                    "refunds": Decimal("0"), "waivers": Decimal("0"), "writeOffs": Decimal("0"),
                                    "adjustments": Decimal("0"), "openingArrears": Decimal("0")})
        h["components"].add(component)
        amount = money(amount)
        if txn_type in ("DEMAND", "PENALTY", "FEE"):
            h["demand"] += amount
        elif txn_type == "OPENING_ARREAR":
            h["openingArrears"] += amount
        elif txn_type == "PAYMENT":
            h["collection"] -= amount
        elif txn_type == "REFUND":
            h["refunds"] += amount
        elif txn_type == "WAIVER":
            h["waivers"] -= amount
        elif txn_type == "WRITE_OFF":
            h["writeOffs"] -= amount
        elif txn_type == "ADJUSTMENT":
            h["adjustments"] += amount
    out = []
    keys = ("demand", "collection", "refunds", "waivers", "writeOffs", "adjustments", "openingArrears")
    totals = {k: Decimal("0") for k in keys}
    for h in sorted(heads.values(), key=lambda x: x["accountHead"]):
        for k in keys:
            totals[k] += h[k]
        out.append({"accountHead": h["accountHead"], "components": sorted(h["components"]), **{k: _f(h[k]) for k in keys}})
    deposits = next((r["collection"] for r in out if "DEPOSIT" in r["components"]), 0.0)
    return {"period": label, "from": date_from, "to": date_to, "rows": out,
            "totals": {k: _f(v) for k, v in totals.items()}, "depositsReceived": deposits,
            "note": "Account head codes are placeholders until GWMC provides its chart of accounts (SRS Appendix A, item 10)."}


@router.get("/dashboard/commissioner")
async def commissioner_dashboard(ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    """Today's collection, year-to-date against target, weakest wards and complaints past SLA (WB-64)."""
    _require_reports(ctx)
    now_date = today()
    fy_start = financial_year_start(now_date)
    collected = lambda start, end: select(func.coalesce(func.sum(WaterLedger.amount), 0)).where(  # noqa: E731
        WaterLedger.tenant_id == ctx.tenant_id, WaterLedger.txn_type == "PAYMENT", ctx.ward_filter(WaterLedger.ward_id),
        WaterLedger.entry_date >= start, WaterLedger.entry_date <= end)
    today_collection = money(-(await db.scalar(collected(now_date, now_date)) or 0))
    ytd_collection = money(-(await db.scalar(collected(fy_start, now_date)) or 0))
    target = money(await get_setting(db, ctx.tenant_id, "collection.annualTarget"))
    dcb = await dcb_by_ward(db, ctx, fy_start, now_date)
    wards, _ = await ward_maps(db, ctx.tenant_id)
    ward_rows = []
    for ward_id, row in dcb.items():
        eff = _efficiency(row["collection"], row["opening"], row["demand"])
        ward = wards.get(ward_id, {})
        ward_rows.append({"wardNumber": ward.get("wardNumber"), "wardName": ward.get("wardName"), "efficiencyPercent": eff,
                          "demand": _f(row["opening"] + row["demand"]), "collection": _f(row["collection"]), "balance": _f(row["closing"])})
    weakest = sorted([w for w in ward_rows if w["efficiencyPercent"] is not None], key=lambda w: w["efficiencyPercent"])[:5]
    now = utcnow()
    overdue = (await db.execute(select(WaterComplaint).where(WaterComplaint.tenant_id == ctx.tenant_id, WaterComplaint.status != "CLOSED",
                                                             WaterComplaint.sla_due_at < now, ctx.ward_filter(WaterComplaint.ward_id))
                                .order_by(WaterComplaint.sla_due_at))).scalars().all()
    totals = {"opening": sum((r["opening"] for r in dcb.values()), Decimal("0")),
              "demand": sum((r["demand"] for r in dcb.values()), Decimal("0")),
              "collection": sum((r["collection"] for r in dcb.values()), Decimal("0")),
              "closing": sum((r["closing"] for r in dcb.values()), Decimal("0"))}
    status_counts = dict((await db.execute(select(WaterConnection.status, func.count(WaterConnection.id)).where(
        WaterConnection.tenant_id == ctx.tenant_id, ctx.ward_filter(WaterConnection.ward_id)).group_by(WaterConnection.status))).all())
    return {
        "asOf": now_date, "financialYearStart": fy_start,
        "todayCollection": _f(today_collection), "ytdCollection": _f(ytd_collection), "annualTarget": _f(target),
        "targetAchievedPercent": round(float(ytd_collection / target * 100), 2) if target > 0 else None,
        "ytdDemand": _f(totals["opening"] + totals["demand"]), "ytdBalance": _f(totals["closing"]),
        "ytdEfficiencyPercent": _efficiency(totals["collection"], totals["opening"], totals["demand"]),
        "weakestWards": weakest, "allWards": sorted(ward_rows, key=lambda w: w["wardNumber"] or 0),
        "complaintsPastSla": len(overdue),
        "complaintsPastSlaList": [{"complaintNo": c.complaint_no, "type": c.complaint_type, "slaDueAt": c.sla_due_at,
                                   "hoursOverdue": round((now - c.sla_due_at).total_seconds() / 3600, 1),
                                   "assignedTo": c.assigned_to, "escalationLevel": c.escalation_level} for c in overdue[:15]],
        "connectionsByStatus": status_counts,
    }


# ------------------------------------------------------------------------------------------------
# Consumption analysis (WB-54, WB-55)
# ------------------------------------------------------------------------------------------------

@router.get("/analysis/consumption")
async def consumption_analysis(ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    _require_reports(ctx)
    rule = await get_setting(db, ctx.tenant_id, "analysis")
    zero_cycles = int(rule.get("zeroCycles", 3))
    change = Decimal(str(rule.get("suddenChangePercent", 100))) / Decimal("100")
    factor = Decimal(str(rule.get("outlierFactor", 2.0)))
    conns = {c.id: c for c in (await db.execute(select(WaterConnection).where(
        WaterConnection.tenant_id == ctx.tenant_id, WaterConnection.status == "ACTIVE", WaterConnection.is_metered.is_(True),
        ctx.ward_filter(WaterConnection.ward_id)))).scalars().all()}
    bills = (await db.execute(select(WaterBill).where(WaterBill.connection_id.in_(list(conns) or ["__none__"]),
                                                      WaterBill.basis == "ACTUAL").order_by(WaterBill.cycle.desc()))).scalars().all()
    history: Dict[str, List[WaterBill]] = {}
    for b in bills:
        history.setdefault(b.connection_id, []).append(b)
    wards, _ = await ward_maps(db, ctx.tenant_id)

    def row(conn: WaterConnection, **extra) -> Dict:
        ward = wards.get(conn.ward_id, {})
        return {"consumerNo": conn.consumer_no, "consumerName": conn.consumer_name, "category": conn.category_code,
                "wardNumber": ward.get("wardNumber"), "wardName": ward.get("wardName"), **extra}

    zero, sudden = [], []
    latest_by_group: Dict[tuple, List] = {}
    for conn_id, hist in history.items():
        conn = conns[conn_id]
        if len(hist) >= zero_cycles and all(Decimal(str(b.consumption_kl)) == 0 for b in hist[:zero_cycles]):
            zero.append(row(conn, cycles=zero_cycles, lastCycle=hist[0].cycle))
        latest = Decimal(str(hist[0].consumption_kl))
        previous = [Decimal(str(b.consumption_kl)) for b in hist[1:4]]
        if previous:
            avg = sum(previous) / Decimal(len(previous))
            if avg > 0 and (latest >= avg * (1 + change) or latest <= avg / (1 + change)):
                sudden.append(row(conn, cycle=hist[0].cycle, latestKl=float(latest), usualKl=round(float(avg), 3),
                                  direction="RISE" if latest > avg else "DROP",
                                  changePercent=round(float((latest - avg) / avg * 100), 1)))
        latest_by_group.setdefault((conn.category_code, conn.ward_id, hist[0].cycle), []).append((conn, latest))

    outliers = []
    for (category, ward_id, cycle), members in latest_by_group.items():
        if len(members) < 3:
            continue
        for conn, value in members:
            others = [v for c, v in members if c.id != conn.id]
            avg = sum(others) / Decimal(len(others))
            if avg > 0 and (value > avg * factor or value < avg / factor):
                outliers.append(row(conn, cycle=cycle, consumptionKl=float(value), peerAverageKl=round(float(avg), 3),
                                    peers=len(others), ratio=round(float(value / avg), 2)))
    return {"rules": rule, "zeroConsumption": zero, "suddenChange": sudden, "peerOutliers": outliers,
            "note": "Only actual (read) bills are analysed; average and flat bills are left out."}


# ------------------------------------------------------------------------------------------------
# GIS layers (WB-60, WB-61)
# ------------------------------------------------------------------------------------------------

@router.get("/gis/layers")
async def gis_layers(ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("connection.view")
    conns = (await db.execute(select(WaterConnection).where(
        WaterConnection.tenant_id == ctx.tenant_id, WaterConnection.latitude.isnot(None), WaterConnection.longitude.isnot(None),
        ctx.ward_filter(WaterConnection.ward_id)))).scalars().all()
    bal = await bulk_balances(db, ctx.tenant_id, [c.id for c in conns])
    since = utcnow() - datetime.timedelta(days=90)
    complaints = (await db.execute(select(WaterComplaint).where(
        WaterComplaint.tenant_id == ctx.tenant_id, WaterComplaint.latitude.isnot(None), ctx.ward_filter(WaterComplaint.ward_id),
        (WaterComplaint.status != "CLOSED") | (WaterComplaint.created_at >= since)))).scalars().all()
    cases_stmt = select(WaterIllegalCase).where(WaterIllegalCase.tenant_id == ctx.tenant_id)
    if ctx.allowed_ward_ids is not None:
        cases_stmt = cases_stmt.where(ctx.ward_filter(WaterIllegalCase.ward_id))
    cases = (await db.execute(cases_stmt)).scalars().all()
    pending_location = await db.scalar(select(func.count(WaterConnection.id)).where(
        WaterConnection.tenant_id == ctx.tenant_id, WaterConnection.latitude.is_(None), ctx.ward_filter(WaterConnection.ward_id)))
    now = utcnow()
    return {
        "connections": [{"consumerNo": c.consumer_no, "consumerName": c.consumer_name, "lat": c.latitude, "lng": c.longitude,
                         "category": c.category_code, "status": c.status, "paymentStatus": payment_status(bal[c.id]),
                         "totalDue": _f(sum((max(bal[c.id][b], Decimal("0")) for b in DUES_BUCKETS), Decimal("0")))} for c in conns],
        "complaints": [{"complaintNo": c.complaint_no, "type": c.complaint_type, "status": c.status, "lat": c.latitude,
                        "lng": c.longitude, "overdue": c.status != "CLOSED" and now > c.sla_due_at} for c in complaints],
        "illegalCases": [{"caseNo": c.case_no, "status": c.status, "lat": c.latitude, "lng": c.longitude} for c in cases],
        "connectionsWithoutLocation": pending_location,
    }
