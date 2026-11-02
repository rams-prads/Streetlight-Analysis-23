"""Reports, Commissioner dashboard and GIS analytics (PT-50..PT-54, PT-60..PT-66)."""
import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ptx_calc import DUES_BUCKETS, financial_year_start, money, payment_status
from app.db.ptx_models import PtxApplication, PtxAssessment, PtxFloor, PtxFootprint, PtxLedger, PtxProperty, PtxReceipt
from app.db.session import get_read_db, get_write_db
from .common import (
    PtxAPIRoute, PtxContext, audit, bad_request, bulk_balances, get_setting, locality_map, page, ptx_context, today,
    ward_maps,
)

router = APIRouter(route_class=PtxAPIRoute)
DEMAND_TYPES = ("DEMAND", "DEMAND_REVISION", "INTEREST", "FEE", "OPENING_ARREAR")


def _f(v) -> float:
    return float(money(v or 0))


def _period(date_from: Optional[datetime.date], date_to: Optional[datetime.date]):
    date_to = date_to or today()
    date_from = date_from or financial_year_start(date_to)
    if date_from > date_to:
        raise bad_request("'From' date must be on or before 'to' date.")
    return date_from, date_to


def _eff(collection: Decimal, due: Decimal) -> Optional[float]:
    return round(float(collection / due * 100), 2) if due > 0 else None


async def dcb_rows(db: AsyncSession, ctx: PtxContext, date_from: datetime.date, date_to: datetime.date, key, extra_where=None) -> Dict:
    """Opening, demand, collection and closing per key (property / ward) for a period (PT-60)."""
    base = and_(PtxLedger.tenant_id == ctx.tenant_id, PtxLedger.bucket.in_(DUES_BUCKETS), ctx.ward_filter(PtxLedger.ward_id))
    if extra_where is not None:
        base = and_(base, extra_where)
    in_period = and_(PtxLedger.entry_date >= date_from, PtxLedger.entry_date <= date_to)
    rows = (await db.execute(select(
        key,
        func.coalesce(func.sum(case((PtxLedger.entry_date < date_from, PtxLedger.amount), else_=0)), 0),
        func.coalesce(func.sum(case((and_(in_period, PtxLedger.txn_type.in_(DEMAND_TYPES)), PtxLedger.amount), else_=0)), 0),
        func.coalesce(func.sum(case((and_(in_period, PtxLedger.txn_type == "PAYMENT"), PtxLedger.amount), else_=0)), 0),
        func.coalesce(func.sum(case((in_period, PtxLedger.amount), else_=0)), 0),
    ).where(base, PtxLedger.entry_date <= date_to).group_by(key))).all()
    out = {}
    for k, opening, demand, payments, movement in rows:
        opening, demand, collection = money(opening), money(demand), money(-payments)
        closing = money(opening + money(movement))
        out[k] = {"opening": opening, "demand": demand, "collection": collection, "adjustments": money(closing - opening - demand + collection), "closing": closing}
    return out


@router.get("/reports/dcb")
async def dcb_register(level: str = Query("ward", description="property, ward, zone or city"),
                       date_from: Optional[datetime.date] = Query(None, alias="from"), date_to: Optional[datetime.date] = Query(None, alias="to"),
                       ward_id: Optional[str] = Query(None, alias="wardId"), search: Optional[str] = Query(None),
                       skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                       ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    """DCB register by property, ward, zone or the whole city, for any period (PT-60)."""
    ctx.require("reports.view")
    date_from, date_to = _period(date_from, date_to)
    keys = ("opening", "demand", "collection", "adjustments", "closing")
    note = ("Opening = balance before 'from'. Demand = tax, revisions, interest, fees and migrated arrears raised in the period. "
            "Collection = payments net of cancelled or returned receipts. Adjustments = rebates, waivers, write-offs and advance used. "
            "Efficiency = collection / (opening + demand).")
    if level == "property":
        where = PtxLedger.ward_id == ward_id if ward_id else None
        data = await dcb_rows(db, ctx, date_from, date_to, PtxLedger.property_id, where)
        ids = sorted(data.keys())
        props = {p.id: p for p in (await db.execute(select(PtxProperty).where(PtxProperty.id.in_(ids or ["__none__"])))).scalars().all()}
        rows = [{"upin": props[i].upin, "address": props[i].address, **{k: _f(data[i][k]) for k in keys},
                 "efficiencyPercent": _eff(data[i]["collection"], data[i]["opening"] + data[i]["demand"])} for i in ids if i in props]
        if search and search.strip():
            s = search.strip().lower()
            rows = [r for r in rows if s in r["upin"].lower() or s in (r["address"] or "").lower()]
        rows.sort(key=lambda r: r["upin"])
        totals = {k: _f(sum((data[i][k] for i in ids), Decimal("0"))) for k in keys}
        return {"from": date_from, "to": date_to, "level": level, "rows": page(rows[skip:skip + limit], len(rows), skip, limit), "totals": totals, "note": note}
    data = await dcb_rows(db, ctx, date_from, date_to, PtxLedger.ward_id)
    wards, _ = await ward_maps(db, ctx.tenant_id)
    groups: Dict[str, Dict] = {}
    for wid, row in data.items():
        w = wards.get(wid, {})
        if level == "zone":
            gkey, label = w.get("zoneId") or "UNKNOWN", {"name": w.get("zoneName"), "code": w.get("zoneCode")}
        elif level == "city":
            gkey, label = "CITY", {"name": ctx.tenant_id, "code": ctx.tenant_id}
        else:
            gkey, label = wid, {"name": f"Ward {w.get('wardNumber')} - {w.get('wardName')}", "code": str(w.get("wardNumber")), "wardNumber": w.get("wardNumber")}
        g = groups.setdefault(gkey, {**label, **{k: Decimal("0") for k in keys}})
        for k in keys:
            g[k] += row[k]
    out = [{**{k: v for k, v in g.items() if k not in keys}, **{k: _f(g[k]) for k in keys}, "efficiencyPercent": _eff(g["collection"], g["opening"] + g["demand"])}
           for g in groups.values()]
    out.sort(key=lambda r: (r.get("wardNumber") or 0, r.get("code") or ""))
    totals = {k: sum((g[k] for g in groups.values()), Decimal("0")) for k in keys}
    return {"from": date_from, "to": date_to, "level": level, "rows": page(out[skip:skip + limit], len(out), skip, limit),
            "totals": {**{k: _f(v) for k, v in totals.items()}, "efficiencyPercent": _eff(totals["collection"], totals["opening"] + totals["demand"])}, "note": note}


def _window(view: str, on: datetime.date):
    if view == "DAY":
        return on, on, 1 / 365
    if view == "MONTH":
        return on.replace(day=1), on, 1 / 12
    start = financial_year_start(on)
    return start, on, 1.0


@router.get("/reports/efficiency")
async def collection_efficiency(by: str = Query("ward", description="ward, zone or collector"), view: str = Query("YTD", description="DAY, MONTH or YTD"),
                                on: Optional[datetime.date] = Query(None, alias="date"), ctx: PtxContext = Depends(ptx_context),
                                db: AsyncSession = Depends(get_read_db)):
    """Collection efficiency by ward, zone or collector, daily, monthly and year-to-date, against targets (PT-61)."""
    ctx.require("reports.view")
    on = on or today()
    start, end, fraction = _window(view.upper(), on)
    targets = await get_setting(db, ctx.tenant_id, "collection.targets")
    if by == "collector":
        rows = (await db.execute(select(PtxReceipt.collected_by, func.count(PtxReceipt.id), func.coalesce(func.sum(PtxReceipt.amount), 0)).where(
            PtxReceipt.tenant_id == ctx.tenant_id, PtxReceipt.status == "VALID", PtxReceipt.receipt_date >= start, PtxReceipt.receipt_date <= end,
            ctx.ward_filter(PtxReceipt.ward_id)).group_by(PtxReceipt.collected_by))).all()
        out = []
        for collector, count, amount in rows:
            annual = targets.get("byCollector", {}).get(collector)
            target = money(Decimal(str(annual)) * Decimal(str(fraction))) if annual else None
            out.append({"name": collector, "receipts": count, "collection": _f(amount), "target": float(target) if target else None,
                        "achievementPercent": round(float(money(amount) / target * 100), 1) if target else None})
        return {"by": by, "view": view.upper(), "from": start, "to": end, "rows": sorted(out, key=lambda r: -r["collection"])}
    data = await dcb_rows(db, ctx, start, end, PtxLedger.ward_id)
    wards, _ = await ward_maps(db, ctx.tenant_id)
    groups: Dict[str, Dict] = {}
    for wid, row in data.items():
        w = wards.get(wid, {})
        key = (w.get("zoneId") or "UNKNOWN") if by == "zone" else wid
        g = groups.setdefault(key, {"name": w.get("zoneName") if by == "zone" else f"Ward {w.get('wardNumber')} - {w.get('wardName')}",
                                    "wardNumbers": [], "due": Decimal("0"), "collection": Decimal("0")})
        g["wardNumbers"].append(w.get("wardNumber"))
        g["due"] += row["opening"] + row["demand"]
        g["collection"] += row["collection"]
    out = []
    for g in groups.values():
        annual = sum((Decimal(str(targets.get("byWardNumber", {}).get(str(n), 0) or 0)) for n in g["wardNumbers"]), Decimal("0"))
        target = money(annual * Decimal(str(fraction))) if annual > 0 else None
        out.append({"name": g["name"], "due": _f(g["due"]), "collection": _f(g["collection"]), "efficiencyPercent": _eff(g["collection"], g["due"]),
                    "target": float(target) if target else None,
                    "achievementPercent": round(float(g["collection"] / target * 100), 1) if target else None})
    return {"by": by, "view": view.upper(), "from": start, "to": end, "rows": sorted(out, key=lambda r: (r["efficiencyPercent"] is None, r["efficiencyPercent"] or 0))}


@router.get("/reports/daily-collection")
async def daily_collection(on: Optional[datetime.date] = Query(None, alias="date"), ctx: PtxContext = Depends(ptx_context),
                           db: AsyncSession = Depends(get_read_db)):
    """Daily collection by payment channel, mode and collector (PT-62)."""
    ctx.require("reports.view")
    on = on or today()
    receipts = (await db.execute(select(PtxReceipt).where(PtxReceipt.tenant_id == ctx.tenant_id, PtxReceipt.receipt_date == on,
                                                          ctx.ward_filter(PtxReceipt.ward_id)))).scalars().all()

    def group(attr: str) -> List[Dict]:
        g: Dict[str, Dict] = {}
        for r in receipts:
            row = g.setdefault(getattr(r, attr), {"name": getattr(r, attr), "receipts": 0, "amount": Decimal("0"), "cancelled": 0})
            if r.status == "VALID":
                row["receipts"] += 1
                row["amount"] += r.amount
            else:
                row["cancelled"] += 1
        return sorted([{**v, "amount": _f(v["amount"])} for v in g.values()], key=lambda x: -x["amount"])

    valid = [r for r in receipts if r.status == "VALID"]
    return {"date": on, "total": _f(sum((r.amount for r in valid), Decimal("0"))), "receipts": len(valid),
            "cancelledOrReturned": len(receipts) - len(valid), "byChannel": group("channel"), "byMode": group("payment_mode"), "byCollector": group("collected_by")}


@router.get("/reports/account-heads")
async def account_heads(day: Optional[datetime.date] = Query(None), month: Optional[str] = Query(None), ctx: PtxContext = Depends(ptx_context),
                        db: AsyncSession = Depends(get_read_db)):
    """Daily or monthly summary of demand, collection, refunds and write-offs by account head (PT-66)."""
    ctx.require("reports.view")
    if month:
        try:
            y, m = (int(x) for x in month.split("-"))
            date_from = datetime.date(y, m, 1)
        except ValueError:
            raise bad_request("Month must be YYYY-MM.")
        date_to = (date_from.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)
        label = date_from.strftime("%B %Y")
    else:
        date_from = date_to = day or today()
        label = date_from.strftime("%d-%m-%Y")
    rows = (await db.execute(select(PtxLedger.account_head, PtxLedger.component, PtxLedger.txn_type, func.coalesce(func.sum(PtxLedger.amount), 0)).where(
        PtxLedger.tenant_id == ctx.tenant_id, ctx.ward_filter(PtxLedger.ward_id), PtxLedger.entry_date >= date_from, PtxLedger.entry_date <= date_to,
        PtxLedger.txn_type.notin_(["ROLLOVER", "TRANSFER", "TRANSFER_IN", "TRANSFER_OUT"]))
        .group_by(PtxLedger.account_head, PtxLedger.component, PtxLedger.txn_type))).all()
    keys = ("demand", "collection", "rebates", "refunds", "waivers", "writeOffs", "adjustments", "openingArrears")
    heads: Dict[str, Dict] = {}
    for head, component, txn, amount in rows:
        h = heads.setdefault(head, {"accountHead": head, "components": set(), **{k: Decimal("0") for k in keys}})
        h["components"].add(component)
        amount = money(amount)
        if txn in ("DEMAND", "DEMAND_REVISION", "INTEREST", "FEE"):
            h["demand"] += amount
        elif txn == "OPENING_ARREAR":
            h["openingArrears"] += amount
        elif txn == "PAYMENT":
            h["collection"] -= amount
        elif txn in ("REBATE", "OTS_WAIVER"):
            h["rebates"] -= amount
        elif txn == "REFUND":
            h["refunds"] += amount
        elif txn == "WAIVER":
            h["waivers"] -= amount
        elif txn == "WRITE_OFF":
            h["writeOffs"] -= amount
        elif txn == "ADJUSTMENT":
            h["adjustments"] += amount
    out = [{"accountHead": h["accountHead"], "components": sorted(h["components"]), **{k: _f(h[k]) for k in keys}} for h in sorted(heads.values(), key=lambda x: x["accountHead"])]
    return {"period": label, "from": date_from, "to": date_to, "rows": out, "totals": {k: _f(sum((Decimal(str(r[k])) for r in out), Decimal("0"))) for k in keys},
            "note": "Account head codes are placeholders until GWMC provides its chart of accounts (SRS Appendix A, item 9)."}


@router.get("/dashboard/commissioner")
async def commissioner_dashboard(ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    """Today's collection, year-to-date collection against target and the weakest wards (PT-64)."""
    ctx.require("reports.view")
    now = today()
    fy = financial_year_start(now)
    paid = lambda s, e: select(func.coalesce(func.sum(PtxLedger.amount), 0)).where(  # noqa: E731
        PtxLedger.tenant_id == ctx.tenant_id, PtxLedger.txn_type == "PAYMENT", ctx.ward_filter(PtxLedger.ward_id), PtxLedger.entry_date >= s, PtxLedger.entry_date <= e)
    today_c = money(-(await db.scalar(paid(now, now)) or 0))
    ytd = money(-(await db.scalar(paid(fy, now)) or 0))
    target = money((await get_setting(db, ctx.tenant_id, "collection.targets"))["annual"])
    data = await dcb_rows(db, ctx, fy, now, PtxLedger.ward_id)
    wards, _ = await ward_maps(db, ctx.tenant_id)
    ward_rows = [{"wardNumber": wards.get(w, {}).get("wardNumber"), "wardName": wards.get(w, {}).get("wardName"),
                  "due": _f(r["opening"] + r["demand"]), "collection": _f(r["collection"]), "balance": _f(r["closing"]),
                  "efficiencyPercent": _eff(r["collection"], r["opening"] + r["demand"])} for w, r in data.items()]
    totals = {k: sum((r[k] for r in data.values()), Decimal("0")) for k in ("opening", "demand", "collection", "closing")}
    counts = dict((await db.execute(select(PtxProperty.status, func.count()).where(PtxProperty.tenant_id == ctx.tenant_id, ctx.ward_filter(PtxProperty.ward_id))
                                    .group_by(PtxProperty.status))).all())
    open_cases = await db.scalar(select(func.count()).select_from(PtxApplication).where(PtxApplication.tenant_id == ctx.tenant_id, PtxApplication.status == "IN_PROGRESS",
                                                                                      ctx.ward_filter(PtxApplication.ward_id)))
    return {"asOf": now, "financialYearStart": fy, "todayCollection": _f(today_c), "ytdCollection": _f(ytd), "annualTarget": _f(target),
            "targetAchievedPercent": round(float(ytd / target * 100), 2) if target > 0 else None,
            "ytdDue": _f(totals["opening"] + totals["demand"]), "ytdBalance": _f(totals["closing"]),
            "ytdEfficiencyPercent": _eff(totals["collection"], totals["opening"] + totals["demand"]),
            "weakestWards": sorted([w for w in ward_rows if w["efficiencyPercent"] is not None], key=lambda w: w["efficiencyPercent"])[:5],
            "allWards": sorted(ward_rows, key=lambda w: w["wardNumber"] or 0), "propertiesByStatus": counts, "openCases": open_cases}


# ------------------------------------------------------------------------------------------------
# GIS analytics (PT-50..PT-54)
# ------------------------------------------------------------------------------------------------

async def _recorded_area(db: AsyncSession, ids: List[str]) -> Dict[str, Decimal]:
    if not ids:
        return {}
    rows = (await db.execute(select(PtxFloor.property_id, func.coalesce(func.sum(PtxFloor.builtup_sqft), 0)).where(
        PtxFloor.property_id.in_(ids), PtxFloor.is_current.is_(True)).group_by(PtxFloor.property_id))).all()
    return {pid: Decimal(str(total)) for pid, total in rows}


@router.get("/gis/layers")
async def gis_layers(ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    """Properties coloured by payment status, buildings with no UPIN, and buildings bigger on the map than on record (PT-50, PT-51, PT-54)."""
    ctx.require("gis.view")
    props = (await db.execute(select(PtxProperty).where(PtxProperty.tenant_id == ctx.tenant_id, PtxProperty.status == "ACTIVE", PtxProperty.latitude.isnot(None),
                                                        ctx.ward_filter(PtxProperty.ward_id)))).scalars().all()
    bal = await bulk_balances(db, ctx.tenant_id, [p.id for p in props])
    wards, _ = await ward_maps(db, ctx.tenant_id)
    fps_stmt = select(PtxFootprint).where(PtxFootprint.tenant_id == ctx.tenant_id)
    if ctx.allowed_ward_ids is not None:
        fps_stmt = fps_stmt.where(ctx.ward_filter(PtxFootprint.ward_id))
    fps = (await db.execute(fps_stmt)).scalars().all()
    area = await _recorded_area(db, [f.property_id for f in fps if f.property_id])
    margin = Decimal(str((await get_setting(db, ctx.tenant_id, "gis"))["areaMismatchPercent"]))
    by_id = {p.id: p for p in props}
    mismatch = []
    for f in fps:
        rec = area.get(f.property_id) if f.property_id else None
        if rec and rec > 0 and Decimal(str(f.map_builtup_sqft)) > rec * (1 + margin / 100):
            prop = by_id.get(f.property_id)
            mismatch.append({"footprintId": f.id, "upin": prop.upin if prop else None, "lat": f.latitude, "lng": f.longitude,
                             "mapSqft": float(f.map_builtup_sqft), "recordedSqft": float(rec),
                             "differencePercent": round(float((Decimal(str(f.map_builtup_sqft)) - rec) / rec * 100), 1)})
    no_location = await db.scalar(select(func.count()).select_from(PtxProperty).where(PtxProperty.tenant_id == ctx.tenant_id, PtxProperty.status == "ACTIVE",
                                                                                     PtxProperty.latitude.is_(None), ctx.ward_filter(PtxProperty.ward_id)))
    return {
        "properties": [{"upin": p.upin, "lat": p.latitude, "lng": p.longitude, "wardNumber": wards.get(p.ward_id, {}).get("wardNumber"),
                        "zoneId": wards.get(p.ward_id, {}).get("zoneId"), "paymentStatus": payment_status(bal[p.id]),
                        "totalDue": _f(sum((max(bal[p.id][b], Decimal("0")) for b in DUES_BUCKETS), Decimal("0"))),
                        "address": p.address} for p in props],
        "unassessed": [{"footprintId": f.id, "ref": f.footprint_ref, "lat": f.latitude, "lng": f.longitude, "mapSqft": float(f.map_builtup_sqft),
                        "wardNumber": wards.get(f.ward_id, {}).get("wardNumber"), "status": f.verification_status}
                       for f in fps if not f.property_id and f.verification_status != "NOT_A_BUILDING"],
        "areaMismatch": mismatch, "mismatchMarginPercent": float(margin), "propertiesWithoutLocation": no_location,
    }


@router.get("/gis/heat")
async def revenue_heat(level: str = Query("ward", description="zone, ward or locality"), ctx: PtxContext = Depends(ptx_context),
                       db: AsyncSession = Depends(get_read_db)):
    """Demand, collection and arrears this year by zone, ward or locality, placed at the centre of their properties (PT-52, PT-54)."""
    ctx.require("gis.view")
    now = today()
    fy = financial_year_start(now)
    data = await dcb_rows(db, ctx, fy, now, PtxLedger.property_id)
    props = (await db.execute(select(PtxProperty).where(PtxProperty.tenant_id == ctx.tenant_id, ctx.ward_filter(PtxProperty.ward_id)))).scalars().all()
    wards, _ = await ward_maps(db, ctx.tenant_id)
    locs = await locality_map(db, ctx.tenant_id)
    groups: Dict[str, Dict] = {}
    for p in props:
        if level == "zone":
            gid = wards.get(p.ward_id, {}).get("zoneId")
            name = wards.get(p.ward_id, {}).get("zoneName")
        elif level == "locality":
            gid = p.locality_id
            name = locs.get(p.locality_id or "", {}).get("name")
        else:
            gid = p.ward_id
            w = wards.get(p.ward_id, {})
            name = f"Ward {w.get('wardNumber')} - {w.get('wardName')}"
        if not gid:
            continue
        g = groups.setdefault(gid, {"id": gid, "name": name, "lat": 0.0, "lng": 0.0, "points": 0, "properties": 0,
                                    "due": Decimal("0"), "collection": Decimal("0"), "arrears": Decimal("0"),
                                    "wardId": p.ward_id if level != "zone" else None, "zoneId": wards.get(p.ward_id, {}).get("zoneId")})
        g["properties"] += 1
        if p.latitude is not None:
            g["lat"] += p.latitude
            g["lng"] += p.longitude
            g["points"] += 1
        row = data.get(p.id)
        if row:
            g["due"] += row["opening"] + row["demand"]
            g["collection"] += row["collection"]
            g["arrears"] += max(row["closing"], Decimal("0"))
    out = []
    for g in groups.values():
        if g["points"] == 0:
            continue
        out.append({"id": g["id"], "name": g["name"], "lat": g["lat"] / g["points"], "lng": g["lng"] / g["points"], "properties": g["properties"],
                    "due": _f(g["due"]), "collection": _f(g["collection"]), "arrears": _f(g["arrears"]), "efficiencyPercent": _eff(g["collection"], g["due"]),
                    "wardId": g["wardId"], "zoneId": g["zoneId"]})
    return {"level": level, "from": fy, "to": now, "areas": out}


@router.get("/gis/tax-gap")
async def tax_gap(ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    """
    Estimated tax gap by ward (PT-53): buildings on the map with no UPIN, and buildings bigger on the map than on record,
    valued at the ward's average tax per sq ft of assessed buildings.
    """
    ctx.require("gis.view")
    props = (await db.execute(select(PtxProperty).where(PtxProperty.tenant_id == ctx.tenant_id, PtxProperty.status == "ACTIVE",
                                                        ctx.ward_filter(PtxProperty.ward_id)))).scalars().all()
    area = await _recorded_area(db, [p.id for p in props])
    tax_rows = (await db.execute(select(PtxAssessment.property_id, PtxAssessment.annual_tax).where(
        PtxAssessment.property_id.in_([p.id for p in props] or ["__none__"]), PtxAssessment.status == "FINAL"))).all()
    tax = {pid: Decimal(str(t)) for pid, t in tax_rows}
    fps_stmt = select(PtxFootprint).where(PtxFootprint.tenant_id == ctx.tenant_id)
    if ctx.allowed_ward_ids is not None:
        fps_stmt = fps_stmt.where(ctx.ward_filter(PtxFootprint.ward_id))
    fps = (await db.execute(fps_stmt)).scalars().all()
    wards, _ = await ward_maps(db, ctx.tenant_id)
    out: Dict[str, Dict] = {}
    for p in props:
        w = out.setdefault(p.ward_id, {"wardNumber": wards.get(p.ward_id, {}).get("wardNumber"), "wardName": wards.get(p.ward_id, {}).get("wardName"),
                                       "assessedProperties": 0, "actualDemand": Decimal("0"), "assessedSqft": Decimal("0"),
                                       "unassessedBuildings": 0, "unassessedSqft": Decimal("0"), "underAssessedSqft": Decimal("0")})
        w["assessedProperties"] += 1
        w["actualDemand"] += tax.get(p.id, Decimal("0"))
        if tax.get(p.id) and area.get(p.id):
            w["assessedSqft"] += area[p.id]
    for f in fps:
        if f.ward_id not in out:
            continue
        w = out[f.ward_id]
        if not f.property_id and f.verification_status != "NOT_A_BUILDING":
            w["unassessedBuildings"] += 1
            w["unassessedSqft"] += Decimal(str(f.map_builtup_sqft))
        elif f.property_id and area.get(f.property_id) and Decimal(str(f.map_builtup_sqft)) > area[f.property_id]:
            w["underAssessedSqft"] += Decimal(str(f.map_builtup_sqft)) - area[f.property_id]
    rows = []
    for w in out.values():
        rate = (w["actualDemand"] / w["assessedSqft"]) if w["assessedSqft"] > 0 else Decimal("0")
        gap = money((w["unassessedSqft"] + w["underAssessedSqft"]) * rate)
        rows.append({"wardNumber": w["wardNumber"], "wardName": w["wardName"], "assessedProperties": w["assessedProperties"],
                     "actualDemand": _f(w["actualDemand"]), "avgTaxPerSqft": round(float(rate), 2), "unassessedBuildings": w["unassessedBuildings"],
                     "unassessedSqft": float(w["unassessedSqft"]), "underAssessedSqft": float(w["underAssessedSqft"]), "estimatedGap": float(gap),
                     "potentialDemand": _f(w["actualDemand"] + gap),
                     "gapPercent": round(float(gap / (w["actualDemand"] + gap) * 100), 1) if (w["actualDemand"] + gap) > 0 else None})
    rows.sort(key=lambda r: -r["estimatedGap"])
    return {"rows": rows, "totals": {"actualDemand": round(sum(r["actualDemand"] for r in rows), 2), "estimatedGap": round(sum(r["estimatedGap"] for r in rows), 2)},
            "note": "Estimate only: annual tax at the ward's average tax per sq ft. Field verification decides the actual tax."}


@router.post("/gis/footprints/{footprint_id}/verify")
async def send_for_verification(footprint_id: str, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """Sends a building with no UPIN to field staff for verification (PT-50)."""
    ctx.require("property.edit")
    fp = await db.get(PtxFootprint, footprint_id)
    if fp is None or fp.tenant_id != ctx.tenant_id:
        raise bad_request("Map footprint not found.")
    ctx.ensure_scope(fp.ward_id)
    if fp.property_id:
        raise bad_request("This building already has a property number.")
    fp.verification_status = "SENT_FOR_VERIFICATION"
    audit(db, ctx, "FOOTPRINT_SENT_FOR_VERIFICATION", "footprint", fp.id, None, {"ref": fp.footprint_ref})
    await db.commit()
    return {"message": "Sent to field staff for verification", "footprintId": fp.id}
