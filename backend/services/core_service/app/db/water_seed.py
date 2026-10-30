"""
Module 2 (WTR) start-up data.

Always (any environment): connection categories, the initial versioned settings and an approved tariff per
category, so the module can bill. All rates are PLACEHOLDERS until GWMC supplies its notified rates
(SRS Appendix A, items 2-5); they are changed through the Tariffs and Settings screens, never in code.

Development only: water staff users, reading routes and ~24 demo connections with four months of history,
generated through the module's own engine (readings, bill runs, payments, penalty, notices), so dashboards and
reports show real numbers.
"""
import datetime
import json
import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password
from app.db.models import User, Ward
from app.db.water_models import (
    WaterBill, WaterCategory, WaterComplaint, WaterConnection, WaterCounter, WaterMeter, WaterReading, WaterRoute,
    WaterSetting, WaterTariff, utcnow,
)

logger = logging.getLogger(__name__)

TENANT = "GWMC"
SEED_ACTOR = "system.seed"
PLACEHOLDER = "PLACEHOLDER - awaiting GWMC notified rates (SRS Appendix A, item 2)"

CATEGORIES = [
    ("DOMESTIC", "Domestic", "గృహ వినియోగం"),
    ("NON_DOMESTIC", "Non-domestic (commercial)", "గృహేతర (వాణిజ్య)"),
    ("INDUSTRIAL", "Industrial", "పారిశ్రామిక"),
    ("BULK", "Bulk (apartments / institutions)", "బల్క్ (అపార్ట్‌మెంట్లు / సంస్థలు)"),
]

TARIFFS = {
    "DOMESTIC": {"slabs": [{"uptoKl": 15, "ratePerKl": 7}, {"uptoKl": 30, "ratePerKl": 11}, {"uptoKl": None, "ratePerKl": 20}],
                 "flat": {"15": 150, "20": 300, "25": 500}, "min": 100, "fixed": 30, "cess": 0, "free": 0},
    "NON_DOMESTIC": {"slabs": [{"uptoKl": 25, "ratePerKl": 25}, {"uptoKl": None, "ratePerKl": 35}],
                     "flat": {"15": 600, "20": 1000, "25": 1500}, "min": 500, "fixed": 100, "cess": 2, "free": 0},
    "INDUSTRIAL": {"slabs": [{"uptoKl": None, "ratePerKl": 50}],
                   "flat": {"25": 4000, "40": 8000, "50": 12000}, "min": 2000, "fixed": 300, "cess": 2, "free": 0},
    "BULK": {"slabs": [{"uptoKl": None, "ratePerKl": 40}],
             "flat": {"40": 15000, "50": 25000}, "min": 5000, "fixed": 500, "cess": 0, "free": 0},
}

WATER_USERS = [
    ("water.officer@gwmc.gov.in", "K. Srinivas (Water Section Officer)", "water_officer", None, None),
    ("meter.reader@gwmc.gov.in", "B. Raju (Meter Reader)", "meter_reader", None, "Ward-14"),
    ("water.fieldstaff@gwmc.gov.in", "M. Yadagiri (Water Field Staff)", "water_field_staff", None, None),
    ("cashier@gwmc.gov.in", "S. Lavanya (Cashier)", "cashier", None, None),
    ("commissioner@gwmc.gov.in", "Commissioner, GWMC", "commissioner", None, None),
    ("csc.operator@gwmc.gov.in", "Meeseva Operator, Hanamkonda", "csc_operator", None, None),
]
DEMO_PASSWORD = "Water@123"

# (ward, name, door, address, category, pipe, metered, monthly kL pattern, pay behaviour, mobile)
DEMO_CONNECTIONS = [
    (14, "K. Venkateshwarlu", "2-4-123", "Postal Colony, Subedari, Hanamkonda", "DOMESTIC", 15, True, [14, 15, 13, 16], "FULL", "9000000101"),
    (14, "G. Manjula", "2-4-202", "Postal Colony Extension, Subedari", "DOMESTIC", 15, True, [11, 12, 10, 12], "FULL", "9000000102"),
    (14, "T. Prakash", "2-4-310", "Subedari Main Road, Hanamkonda", "DOMESTIC", 20, True, [22, 24, 21, 23], "PARTIAL", "9000000103"),
    (14, "Sri Sai Tiffins", "2-5-12", "Subedari Main Road, Hanamkonda", "NON_DOMESTIC", 20, True, [38, 41, 40, 43], "FULL", "9000000104"),
    (14, "P. Anjaiah", "2-4-77", "Ambedkar Nagar, Subedari", "DOMESTIC", 15, False, None, "NONE", "9000000105"),
    (22, "Ch. Narayana Rao", "3-8-45", "Judicial Complex Enclave, Balasamudram", "NON_DOMESTIC", 25, True, [60, 58, 63, 61], "LATE", "9000000201"),
    (22, "R. Swapna", "3-8-102", "Balasamudram, Hanamkonda", "DOMESTIC", 15, True, [9, 10, 8, 0], "FULL", "9000000202"),
    (22, "D. Ramulu", "3-9-14", "Balasamudram Road, Hanamkonda", "DOMESTIC", 15, True, [0, 0, 0, 0], "FULL", "9000000203"),
    (22, "Balaji Heights Residents Assn", "3-8-200", "Judicial Complex Enclave, Balasamudram", "BULK", 40, True, [410, 395, 420, 405], "FULL", "9000000204"),
    (22, "V. Padma", "3-7-66", "Excise Colony, Balasamudram", "DOMESTIC", 15, False, None, "PARTIAL", "9000000205"),
    (35, "P. Sudhakar Reddy", "1-12-88", "Green Meadows Avenue, Nakkalagutta", "DOMESTIC", 15, True, [16, 17, 15, 18], "FULL", "9000000301"),
    (35, "A. Lakshmi", "1-12-90", "Green Meadows Avenue, Nakkalagutta", "DOMESTIC", 15, True, [13, 14, 12, 41], "FULL", "9000000302"),
    (35, "Hotel Ashoka Grand", "1-10-5", "Nakkalagutta Main Road", "NON_DOMESTIC", 25, True, [120, 118, 125, 122], "NONE", "9000000303"),
    (35, "S. Bhaskar", "1-11-23", "Nakkalagutta, Hanamkonda", "DOMESTIC", 15, True, [12, 13, 12, 12], "NONE", "9000000304"),
    (35, "N. Kavitha", "1-11-40", "Teachers Colony, Nakkalagutta", "DOMESTIC", 15, True, [14, 15, 14, 15], "FULL", "9000000305"),
    (48, "Kakatiya Infotech Pvt Ltd", "5-2-101", "Main Road, KU Campus Road, Kazipet", "NON_DOMESTIC", 25, True, [95, 99, 92, 97], "LATE", "9000000401"),
    (48, "Warangal Agro Foods", "5-3-9", "Industrial Estate, Kazipet", "INDUSTRIAL", 40, True, [610, 640, 625, 655], "FULL", "9000000402"),
    (48, "M. Rajeshwar", "5-2-140", "KU Campus Road, Kazipet", "DOMESTIC", 15, True, [17, 18, 16, 17], "PARTIAL", "9000000403"),
    (48, "Y. Saritha", "5-2-155", "Vidyanagar, Kazipet", "DOMESTIC", 15, False, None, "FULL", "9000000404"),
    (56, "M. Srinivas", "4-1-12", "Mandi Bazar, Warangal", "NON_DOMESTIC", 20, True, [44, 47, 45, 46], "NONE", "9000000501"),
    (56, "Sri Ganesh Kirana", "4-1-30", "Mandi Bazar, Warangal", "NON_DOMESTIC", 15, False, None, "NONE", "9000000502"),
    (56, "B. Yellamma", "4-2-7", "Chowrasta, Warangal", "DOMESTIC", 15, True, [10, 11, 10, 11], "FULL", "9000000503"),
    (56, "K. Mallesham", "4-2-19", "Chowrasta, Warangal", "DOMESTIC", 15, True, [13, 12, 14, 13], "LATE", "9000000504"),
]
WARD_CENTRES = {14: (17.9812, 79.5982), 22: (17.9891, 79.6015), 35: (17.9945, 79.5872), 48: (18.0125, 79.5714), 56: (17.9700, 79.5940)}


async def _seed_reference(db: AsyncSession) -> bool:
    """Categories, settings and approved placeholder tariffs. Returns False if already seeded."""
    if await db.scalar(select(WaterCategory.id).where(WaterCategory.tenant_id == TENANT)):
        return False
    from app.api.v1.water.common import DEFAULT_SETTINGS
    # effective from the start of the previous financial year so the seeded history is covered
    start = datetime.date(datetime.date.today().year - 1, 4, 1)
    for code, en, te in CATEGORIES:
        db.add(WaterCategory(tenant_id=TENANT, code=code, name_en=en, name_te=te))
    for key, value in DEFAULT_SETTINGS.items():
        db.add(WaterSetting(tenant_id=TENANT, key=key, value_json=json.dumps(value), effective_from=start,
                            reason="Initial configuration - placeholder values pending GWMC confirmation (SRS Appendix A)",
                            created_by=SEED_ACTOR))
    for code, t in TARIFFS.items():
        db.add(WaterTariff(tenant_id=TENANT, category_code=code, version=1, effective_from=start,
                           slabs_json=json.dumps(t["slabs"]), flat_rates_json=json.dumps(t["flat"]),
                           minimum_charge=Decimal(t["min"]), fixed_charge=Decimal(t["fixed"]), cess_percent=Decimal(t["cess"]),
                           free_allowance_kl=Decimal(t["free"]), status="APPROVED", order_reference=PLACEHOLDER,
                           reason="Initial tariff", requested_by=SEED_ACTOR, approved_by=SEED_ACTOR, approved_at=utcnow()))
    await db.commit()
    return True


async def _seed_demo(db: AsyncSession) -> None:
    from app.api.v1.water.arrears import run_disconnection, run_penalty
    from app.api.v1.water.billing import _bill_one
    from app.api.v1.water.common import WaterContext, balances, dues_total, get_setting, new_consumer_no
    from app.api.v1.water.complaints import raise_complaint, report_illegal
    from app.api.v1.water.applications import create_application
    from app.api.v1.water.meters import ingest_reading
    from app.api.v1.water.payments import take_payment
    from app.core.water_calc import cycle_for_date, cycle_period, previous_cycle
    from app.schemas.water import ApplicationCreate, ComplaintCreate, IllegalReport, ReadingIn

    ctx = WaterContext(tenant_id=TENANT, sub_tenant_id=None, user={}, username=SEED_ACTOR, roles={"super_admin"}, ip="127.0.0.1")

    for username, name, role, zone, ward in WATER_USERS:
        if not await db.scalar(select(User.id).where(User.username == username)):
            db.add(User(tenant_id=TENANT, username=username, email=username, password_hash=hash_password(DEMO_PASSWORD),
                        full_name=name, role=role, assigned_modules="WTR", assigned_zone=zone, assigned_ward=ward))
    wards = {}
    for w in (await db.execute(select(Ward).where(Ward.tenant_id == TENANT).order_by(Ward.ward_number))).scalars().all():
        wards.setdefault(w.ward_number, w)
    if not all(n in wards for n in WARD_CENTRES):
        logger.warning("Water demo seed skipped: GWMC wards 14, 22, 35, 48, 56 not found.")
        await db.commit()
        return

    routes = {}
    for number in WARD_CENTRES:
        route = WaterRoute(tenant_id=TENANT, code=f"R-{number:02d}-A", name=f"Ward {number} - {wards[number].ward_name} route A",
                           ward_id=wards[number].id, reader_username="meter.reader@gwmc.gov.in")
        db.add(route)
        routes[number] = route
    await db.flush()

    months = int(await get_setting(db, TENANT, "billing.cycleMonths"))
    current = cycle_for_date(datetime.date.today(), months)
    cycles = []
    c = current
    for _ in range(4):
        c = previous_cycle(c, months)
        cycles.insert(0, c)
    first_from, _ = cycle_period(cycles[0], months)
    connected_on = first_from - datetime.timedelta(days=60)

    conns = []
    for i, (ward_no, name, door, address, category, pipe, metered, pattern, behaviour, mobile) in enumerate(DEMO_CONNECTIONS):
        lat0, lng0 = WARD_CENTRES[ward_no]
        seq = sum(1 for x in conns if x[0].ward_id == wards[ward_no].id) + 1
        lat, lng = round(lat0 + 0.0011 * (seq % 3) - 0.0009 * (seq // 3), 6), round(lng0 + 0.0013 * (seq % 2) + 0.0007 * seq, 6)
        migrated = i == 4
        conn = WaterConnection(
            tenant_id=TENANT, consumer_no=await new_consumer_no(db, TENANT),
            old_consumer_no=f"OLD-W-{ward_no}{seq:03d}" if i % 4 == 0 else None, consumer_name=name, mobile_number=mobile,
            door_no=door, address=f"H.No {door}, {address}", ward_id=wards[ward_no].id, zone_id=wards[ward_no].zone_id,
            supply_area=f"Supply area W{ward_no}", latitude=None if migrated else lat,
            longitude=None if migrated else lng, location_pending=migrated, category_code=category, pipe_size_mm=pipe,
            is_metered=metered, connection_date=connected_on, status="ACTIVE", route_id=routes[ward_no].id, route_sequence=seq,
            source="MIGRATION" if i % 4 == 0 else "APPLICATION", created_by=SEED_ACTOR,
            upin=f"TG-GWMC-50600{ward_no % 10}-{100 + i:05d}" if i % 3 == 0 else None, upin_source="APPLICANT" if i % 3 == 0 else None,
        )
        db.add(conn)
        await db.flush()
        if metered:
            db.add(WaterMeter(tenant_id=TENANT, connection_id=conn.id, serial_no=f"GWM-{ward_no}{seq:03d}-{2025}",
                              make="Kranti" if i % 2 else "Itron", size_mm=pipe, seal_no=f"S{1000 + i}",
                              initial_reading=Decimal(1000 + 37 * i), fixed_on=connected_on, status="ACTIVE", created_by=SEED_ACTOR))
        conns.append((conn, pattern, behaviour))
    await db.commit()

    order = await get_setting(db, TENANT, "payment.allocationOrder")
    avg_method = await get_setting(db, TENANT, "billing.averageMethod")
    due_days = int(await get_setting(db, TENANT, "billing.dueDays"))
    readings_value = {conn.id: Decimal(1000 + 37 * i) for i, (conn, _, _) in enumerate(conns)}
    for index, cycle in enumerate(cycles):
        period_from, period_to = cycle_period(cycle, months)
        read_at = datetime.datetime.combine(period_to - datetime.timedelta(days=4), datetime.time(10, 30))
        for n, (conn, pattern, _) in enumerate(conns):
            if not conn.is_metered:
                continue
            if n == 13 and index == len(cycles) - 1:
                await ingest_reading(db, ctx, ReadingIn(consumer_no=conn.consumer_no, no_reading_reason="DOOR_LOCKED",
                                                        reading_at=read_at, client_ref=f"seed-{cycle}-{n}"), "FIELD", conn=conn)
                continue
            readings_value[conn.id] += Decimal(pattern[index])
            await ingest_reading(db, ctx, ReadingIn(
                consumer_no=conn.consumer_no, reading_value=float(readings_value[conn.id]), reading_at=read_at,
                photo_ref=None, latitude=conn.latitude, longitude=conn.longitude, client_ref=f"seed-{cycle}-{n}"), "OFFICE", conn=conn)
        await db.commit()
        # an officer accepts any flagged reading so the seeded cycle can be billed (the current cycle keeps one flagged)
        for r in (await db.execute(select(WaterReading).where(WaterReading.cycle == cycle, WaterReading.status == "PENDING_REVIEW"))).scalars().all():
            r.status, r.review_remark, r.reviewed_by = "ACCEPTED", "Verified on site (seed)", SEED_ACTOR
        await db.commit()

        bill_date = period_to + datetime.timedelta(days=1)
        for conn, _, _ in conns:
            await _bill_one(db, ctx, conn, cycle, bill_date, months, due_days, order, avg_method, "seed")
        await db.commit()

        for n, (conn, _, behaviour) in enumerate(conns):
            bill = await db.scalar(select(WaterBill).where(WaterBill.connection_id == conn.id, WaterBill.cycle == cycle))
            if bill is None:
                continue
            due = dues_total(await balances(db, TENANT, connection_id=conn.id))
            if due <= 0:
                continue
            if behaviour == "FULL":
                pay, day = due, 5 + n % 7
            elif behaviour == "PARTIAL":
                pay, day = (bill.current_demand * Decimal("0.6")).quantize(Decimal("1")), 9
            elif behaviour == "LATE" and index % 2 == 1:
                pay, day = due, due_days + 6
            else:
                continue
            pay_date = bill_date + datetime.timedelta(days=day)
            if pay_date > datetime.date.today() or pay <= 0:
                continue
            await take_payment(db, ctx, conn=conn, app=None, amount=pay, mode="UPI" if n % 3 == 0 else "CASH",
                               channel="COUNTER", idempotency_key=f"SEED:{cycle}:{conn.consumer_no}", on_date=pay_date)
        await db.commit()
        penalty_day = bill_date + datetime.timedelta(days=due_days + 1)
        if penalty_day <= datetime.date.today():
            await run_penalty(db, ctx, penalty_day)
            await db.commit()

    # current cycle: partial reading progress with one high reading waiting for review
    today = datetime.date.today()
    read_at = datetime.datetime.combine(today - datetime.timedelta(days=1), datetime.time(9, 0))
    for n, (conn, pattern, _) in enumerate(conns):
        if not conn.is_metered or n % 2:
            continue
        step = Decimal(pattern[-1] * (4 if n == 0 else 1))
        readings_value[conn.id] += step
        await ingest_reading(db, ctx, ReadingIn(consumer_no=conn.consumer_no, reading_value=float(readings_value[conn.id]),
                                                reading_at=read_at, latitude=conn.latitude, longitude=conn.longitude,
                                                client_ref=f"seed-{current}-{n}"), "OFFICE", conn=conn)
    await db.commit()

    await run_disconnection(db, ctx, today - datetime.timedelta(days=20))
    await db.commit()
    await run_disconnection(db, ctx, today)
    await db.commit()

    complaints = [
        ("LEAK", 14, "Pipeline leak near the drain on the main road; water flowing since morning.", 0, (17.9819, 79.5990)),
        ("NO_SUPPLY", 35, "No water supply for two days in Green Meadows Avenue.", 10, None),
        ("DIRTY_WATER", 22, "Muddy water coming in the morning supply.", 1, None),
        ("BILLING", 48, "Bill shows more consumption than usual.", 17, None),
        ("LEAK", 56, "Valve chamber overflowing at Chowrasta junction.", None, (17.9708, 79.5951)),
        ("METER", 35, "Meter glass broken, reading not visible.", 14, None),
    ]
    for ctype, ward_no, text, conn_index, point in complaints:
        conn = conns[conn_index][0] if conn_index is not None else None
        result = await raise_complaint(ComplaintCreate(
            complaint_type=ctype, source="FIELD" if ctype == "LEAK" else "PORTAL", consumer_no=conn.consumer_no if conn else None,
            ward_id=wards[ward_no].id, description=text, latitude=point[0] if point else None, longitude=point[1] if point else None,
            complainant_mobile=None), ctx, db)
        if ctype in ("NO_SUPPLY", "DIRTY_WATER"):
            row = await db.scalar(select(WaterComplaint).where(WaterComplaint.complaint_no == result["complaintNo"]))
            row.created_at = utcnow() - datetime.timedelta(days=3)
            row.sla_due_at = utcnow() - datetime.timedelta(hours=30)
            await db.commit()
    await report_illegal(IllegalReport(source="STAFF", ward_id=wards[48].id, address="Behind 5-2-150, KU Campus Road",
                                       description="Direct tap from distribution line without meter", latitude=18.0131,
                                       longitude=79.5726, photo_ref="seed-photo-placeholder"), ctx, db)
    await create_application(ApplicationCreate(
        app_type="NEW_CONNECTION", channel="CSC", applicant_name="E. Ravinder", mobile_number="9000000601", consent=True,
        ward_id=wards[35].id, address="H.No 1-12-95, Green Meadows Avenue, Nakkalagutta", door_no="1-12-95",
        latitude=17.99455, longitude=79.58735, category_code="DOMESTIC", pipe_size_mm=15, is_metered=True), ctx, db)
    db.add(WaterCounter(tenant_id=TENANT, name="seed_done", value=1))
    await db.commit()


async def seed_water_data(db: AsyncSession) -> None:
    created = await _seed_reference(db)
    if not created:
        done = await db.scalar(select(WaterCounter.value).where(WaterCounter.tenant_id == TENANT, WaterCounter.name == "seed_done"))
        if settings.ENVIRONMENT == "development" and not done:
            logger.warning("Water demo data looks incomplete (an earlier start-up stopped part way). "
                           "Reference data is in place; recreate the database to reload the demo.")
        return
    logger.info("Water module reference data (categories, settings, placeholder tariffs) seeded.")
    if settings.ENVIRONMENT == "development":
        await _seed_demo(db)
        logger.info("Water module demo data seeded (development only).")
