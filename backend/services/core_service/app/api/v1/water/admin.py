"""
Administration, integration readiness and citizen/public endpoints for the Water module:
versioned settings (WB-NF-50), code lists (WB-NF-64), audit/event/API logs (WB-NF-13, WB-IR-02, WB-IR-11),
link switches (WB-IR-08), connection register export (WB-IR-04), data migration (SRS 3.6.2),
document and photo storage (WB-NF-65), QR verification (SRS 3.1.1) and the daily jobs (WB-40..WB-51).
"""
import csv
import io
import os
import re
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.water_calc import cycle_for_date, document_code, mask_mobile, money, payment_status
from app.db.models import Ward
from app.db.session import get_read_db, get_write_db
from app.db.water_models import (
    WaterApiLog, WaterAuditLog, WaterBill, WaterCategory, WaterComplaint, WaterConnection, WaterEvent, WaterMeter,
    WaterMigrationException, WaterNotification, WaterReceipt, WaterSetting,
)
from app.schemas.water import CategoryCreate, MigrationBatch, MigrationRecord, SettingChange
from .applications import escalate_overdue_applications
from .arrears import run_disconnection, run_penalty, run_reminders
from .billing import printable_bill
from .common import (
    DEFAULT_SETTINGS, DUES_BUCKETS, SETTING_DESCRIPTIONS, WaterAPIRoute, WaterContext, audit, bad_request, balances,
    conflict, dues_summary, dumps, get_setting, loads, new_consumer_no, not_found, post_ledger, today, ward_maps,
    water_context,
)
from .complaints import complaint_dict, escalate_complaints
from .connections import bill_dict, bulk_balances
from .payments import reconcile_pending_intents

router = APIRouter(route_class=WaterAPIRoute)

STORAGE_DIR = Path(os.getenv("WATER_STORAGE_DIR", Path(__file__).resolve().parents[4] / "storage" / "water"))
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf"}
REF_PATTERN = re.compile(r"^[0-9a-f]{32}\.(jpg|png|webp|pdf)$")


# ------------------------------------------------------------------------------------------------
# Settings and code lists (WB-NF-50, WB-NF-64)
# ------------------------------------------------------------------------------------------------

def _validate_setting(key: str, value) -> None:
    default = DEFAULT_SETTINGS[key]
    if default is not None and not isinstance(value, type(default)) and not (isinstance(default, (int, float)) and isinstance(value, (int, float))):
        raise bad_request(f"'{key}' must be a {type(default).__name__}, like the current value.")
    if key == "billing.cycleMonths" and (int(value) < 1 or 12 % int(value) != 0):
        raise bad_request("Billing cycle must be 1, 2, 3, 4, 6 or 12 months.")
    if key == "payment.allocationOrder" and sorted(value) != sorted(DUES_BUCKETS):
        raise bad_request(f"Allocation order must list each of {', '.join(DUES_BUCKETS)} exactly once.")
    if key == "workflow":
        for app_type, steps in value.items():
            if not isinstance(steps, list) or not steps:
                raise bad_request(f"Workflow {app_type} needs at least one step.")
            for step in steps:
                if not {"code", "label", "slaHours", "roles"} <= set(step):
                    raise bad_request(f"Each step of {app_type} needs code, label, slaHours and roles.")
    if key == "billing.averageMethod" and (value.get("type") != "LAST_N_ACTUAL" or int(value.get("n", 0)) < 1):
        raise bad_request("Average method must be LAST_N_ACTUAL with n of 1 or more.")


@router.get("/admin/settings")
async def list_settings(ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("tariff.view")
    out = []
    for key in sorted(DEFAULT_SETTINGS):
        history = (await db.execute(select(WaterSetting).where(WaterSetting.tenant_id == ctx.tenant_id, WaterSetting.key == key)
                                    .order_by(WaterSetting.effective_from.desc(), WaterSetting.created_at.desc()))).scalars().all()
        out.append({"key": key, "description": SETTING_DESCRIPTIONS.get(key, ""), "value": await get_setting(db, ctx.tenant_id, key),
                    "configured": bool(history),
                    "versions": [{"value": loads(h.value_json), "effectiveFrom": h.effective_from, "reason": h.reason,
                                  "createdBy": h.created_by, "createdAt": h.created_at} for h in history]})
    return out


@router.post("/admin/settings", status_code=201)
async def change_setting(payload: SettingChange, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_write_db)):
    """Adds a new version of a setting from an effective date. Old versions are kept so past bills can be recalculated."""
    ctx.require("settings.manage")
    if payload.key not in DEFAULT_SETTINGS:
        raise bad_request(f"Unknown setting '{payload.key}'.")
    if payload.effective_from < today():
        raise bad_request("A setting cannot be changed with a past effective date.")
    _validate_setting(payload.key, payload.value)
    old = await get_setting(db, ctx.tenant_id, payload.key, payload.effective_from)
    row = WaterSetting(tenant_id=ctx.tenant_id, key=payload.key, value_json=dumps(payload.value),
                       effective_from=payload.effective_from, reason=payload.reason, created_by=ctx.username)
    db.add(row)
    audit(db, ctx, "SETTING_CHANGED", "setting", row.id, {"key": payload.key, "value": old},
          {"key": payload.key, "value": payload.value, "effectiveFrom": payload.effective_from, "reason": payload.reason})
    await db.commit()
    return {"message": f"'{payload.key}' will apply from {payload.effective_from.strftime('%d-%m-%Y')}"}


@router.get("/admin/categories")
async def list_categories(ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("tariff.view")
    rows = (await db.execute(select(WaterCategory).where(WaterCategory.tenant_id == ctx.tenant_id).order_by(WaterCategory.code))).scalars().all()
    return [{"code": c.code, "nameEn": c.name_en, "nameTe": c.name_te, "isActive": c.is_active} for c in rows]


@router.post("/admin/categories", status_code=201)
async def add_category(payload: CategoryCreate, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_write_db)):
    ctx.require("settings.manage")
    code = payload.code.strip().upper().replace(" ", "_")
    if await db.scalar(select(WaterCategory.id).where(WaterCategory.tenant_id == ctx.tenant_id, WaterCategory.code == code)):
        raise conflict(f"Category {code} already exists.")
    db.add(WaterCategory(tenant_id=ctx.tenant_id, code=code, name_en=payload.name_en, name_te=payload.name_te))
    audit(db, ctx, "CATEGORY_ADDED", "category", None, None, {"code": code, "nameEn": payload.name_en})
    await db.commit()
    return {"message": f"Category {code} added. Propose a tariff for it before billing."}


# ------------------------------------------------------------------------------------------------
# Logs (WB-NF-13, WB-IR-02, WB-IR-11) and integration links (WB-IR-08)
# ------------------------------------------------------------------------------------------------

@router.get("/admin/audit")
async def audit_log(action: Optional[str] = Query(None), actor: Optional[str] = Query(None), entity_id: Optional[str] = Query(None, alias="entityId"),
                    limit: int = Query(200, ge=1, le=2000), ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("audit.view")
    stmt = select(WaterAuditLog).where(WaterAuditLog.tenant_id == ctx.tenant_id)
    if action:
        stmt = stmt.where(WaterAuditLog.action == action.upper())
    if actor:
        stmt = stmt.where(WaterAuditLog.actor == actor)
    if entity_id:
        stmt = stmt.where(WaterAuditLog.entity_id == entity_id)
    rows = (await db.execute(stmt.order_by(WaterAuditLog.at.desc()).limit(limit))).scalars().all()
    return [{"at": r.at, "actor": r.actor, "ipAddress": r.ip_address, "action": r.action, "entityType": r.entity_type,
             "entityId": r.entity_id, "old": loads(r.old_json), "new": loads(r.new_json)} for r in rows]


@router.get("/admin/events")
async def event_outbox(event_type: Optional[str] = Query(None, alias="type"), limit: int = Query(200, ge=1, le=2000),
                       ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("audit.view")
    stmt = select(WaterEvent).where(WaterEvent.tenant_id == ctx.tenant_id)
    if event_type:
        stmt = stmt.where(WaterEvent.event_type == event_type)
    rows = (await db.execute(stmt.order_by(WaterEvent.created_at.desc()).limit(limit))).scalars().all()
    counts = dict((await db.execute(select(WaterEvent.event_type, func.count(WaterEvent.id)).where(
        WaterEvent.tenant_id == ctx.tenant_id).group_by(WaterEvent.event_type))).all())
    return {"counts": counts, "events": [{"id": r.id, "eventType": r.event_type, "aggregateId": r.aggregate_id,
                                          "payload": loads(r.payload_json), "published": r.published, "createdAt": r.created_at} for r in rows]}


@router.get("/admin/api-log")
async def api_log(limit: int = Query(200, ge=1, le=2000), ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("audit.view")
    rows = (await db.execute(select(WaterApiLog).where(WaterApiLog.tenant_id == ctx.tenant_id)
                             .order_by(WaterApiLog.at.desc()).limit(limit))).scalars().all()
    return [{"at": r.at, "caller": r.caller, "method": r.method, "path": r.path, "statusCode": r.status_code,
             "durationMs": r.duration_ms} for r in rows]


@router.get("/admin/notifications")
async def notifications(template: Optional[str] = Query(None), limit: int = Query(200, ge=1, le=2000),
                        ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("audit.view")
    stmt = select(WaterNotification).where(WaterNotification.tenant_id == ctx.tenant_id)
    if template:
        stmt = stmt.where(WaterNotification.template == template.upper())
    rows = (await db.execute(stmt.order_by(WaterNotification.created_at.desc()).limit(limit))).scalars().all()
    return [{"at": r.created_at, "channel": r.channel, "recipient": mask_mobile(r.recipient) if r.recipient and r.recipient.isdigit() else r.recipient,
             "template": r.template, "messageEn": r.message_en, "messageTe": r.message_te, "refNo": r.ref_no, "status": r.status}
            for r in rows]


@router.get("/integration/links")
async def integration_links(ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    """Planned links to other modules (SRS 3.7.1). All off in Release 1; switched by configuration only (WB-IR-08)."""
    ctx.require("connection.view")
    links = await get_setting(db, ctx.tenant_id, "integrationLinks")
    return [{"link": k, **v} for k, v in links.items()]


# ------------------------------------------------------------------------------------------------
# Connection register export (WB-IR-04)
# ------------------------------------------------------------------------------------------------

EXPORT_COLUMNS = ["consumerNo", "oldConsumerNo", "consumerName", "doorNo", "address", "locality", "pincode", "wardNumber",
                  "wardName", "zoneCode", "supplyArea", "oldAssessmentNo", "upin", "upinSource", "latitude", "longitude",
                  "category", "pipeSizeMm", "metered", "status", "connectionDate", "totalDue", "paymentStatus"]


@router.get("/export/connections")
async def export_connections(fmt: str = Query("csv", alias="format"), ctx: WaterContext = Depends(water_context),
                             db: AsyncSession = Depends(get_read_db)):
    """
    Documented bulk export of the connection register for one-time loading by modules that join later.
    Mobile numbers and identity details are left out (WB-NF-23). Columns: see EXPORT_COLUMNS.
    """
    ctx.require("reports.view")
    conns = (await db.execute(select(WaterConnection).where(WaterConnection.tenant_id == ctx.tenant_id,
                                                            ctx.ward_filter(WaterConnection.ward_id)).order_by(WaterConnection.consumer_no))).scalars().all()
    bal = await bulk_balances(db, ctx.tenant_id, [c.id for c in conns])
    wards, _ = await ward_maps(db, ctx.tenant_id)
    rows = []
    for c in conns:
        ward = wards.get(c.ward_id, {})
        rows.append({
            "consumerNo": c.consumer_no, "oldConsumerNo": c.old_consumer_no, "consumerName": c.consumer_name, "doorNo": c.door_no,
            "address": c.address, "locality": c.locality, "pincode": c.pincode, "wardNumber": ward.get("wardNumber"),
            "wardName": ward.get("wardName"), "zoneCode": ward.get("zoneCode"), "supplyArea": c.supply_area,
            "oldAssessmentNo": c.old_assessment_no, "upin": c.upin, "upinSource": c.upin_source, "latitude": c.latitude,
            "longitude": c.longitude, "category": c.category_code, "pipeSizeMm": c.pipe_size_mm, "metered": c.is_metered,
            "status": c.status, "connectionDate": c.connection_date.isoformat(),
            "totalDue": dues_summary(bal[c.id])["totalDue"], "paymentStatus": payment_status(bal[c.id]),
        })
    audit(db, ctx, "REGISTER_EXPORTED", "export", None, None, {"format": fmt, "rows": len(rows)})
    await db.commit()
    if fmt == "json":
        return {"format": "urban.water.connection-register.v1", "generatedAt": today(), "columns": EXPORT_COLUMNS, "rows": rows}
    buffer = io.StringIO()
    buffer.write("﻿")
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    buffer.seek(0)
    return StreamingResponse(iter([buffer.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="water-connection-register-{today()}.csv"'})


# ------------------------------------------------------------------------------------------------
# Data migration (SRS 3.6.2)
# ------------------------------------------------------------------------------------------------

@router.post("/migration/connections")
async def migrate_connections(payload: MigrationBatch, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_write_db)):
    """
    Loads existing consumers. Old consumer numbers are kept and searchable; records without a location are
    marked for capture on the first reading round; anything that cannot be matched is listed, never dropped.
    """
    ctx.require("migration.run")
    wards = {w.ward_number: w for w in (await db.execute(select(Ward).where(Ward.tenant_id == ctx.tenant_id))).scalars().all()}
    categories = {c.code for c in (await db.execute(select(WaterCategory).where(WaterCategory.tenant_id == ctx.tenant_id))).scalars().all()}
    created, exceptions, location_pending = [], [], 0

    async def exception(raw: Dict, reason: str):
        db.add(WaterMigrationException(tenant_id=ctx.tenant_id, old_consumer_no=str(raw.get("oldConsumerNo") or raw.get("old_consumer_no") or ""),
                                       raw_json=dumps(raw), reason=reason, created_by=ctx.username))
        exceptions.append({"oldConsumerNo": raw.get("oldConsumerNo"), "reason": reason})

    for raw in payload.records:
        try:
            rec = MigrationRecord.model_validate(raw)
        except ValidationError as exc:
            await exception(raw, "Invalid record: " + "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()))
            continue
        if await db.scalar(select(WaterConnection.id).where(WaterConnection.tenant_id == ctx.tenant_id,
                                                            WaterConnection.old_consumer_no == rec.old_consumer_no)):
            await exception(raw, "Old consumer number already migrated")
            continue
        ward = wards.get(rec.ward_number) if rec.ward_number is not None else None
        if ward is None:
            await exception(raw, f"Ward {rec.ward_number} not found: needs field verification")
            continue
        category = rec.category_code.upper()
        if category not in categories:
            await exception(raw, f"Category {rec.category_code} not in the category list")
            continue
        if rec.meter_serial_no and await db.scalar(select(WaterMeter.id).where(WaterMeter.tenant_id == ctx.tenant_id,
                                                                               WaterMeter.serial_no == rec.meter_serial_no)):
            await exception(raw, f"Meter serial {rec.meter_serial_no} already registered")
            continue
        has_location = rec.latitude is not None and rec.longitude is not None
        conn = WaterConnection(
            tenant_id=ctx.tenant_id, sub_tenant_id=ctx.sub_tenant_id, consumer_no=await new_consumer_no(db, ctx.tenant_id),
            old_consumer_no=rec.old_consumer_no, consumer_name=rec.consumer_name, mobile_number=rec.mobile_number,
            door_no=rec.door_no, address=rec.address, old_assessment_no=rec.old_assessment_no, upin=rec.upin,
            upin_source="STAFF" if rec.upin else None, ward_id=ward.id, zone_id=ward.zone_id,
            latitude=rec.latitude, longitude=rec.longitude, location_pending=not has_location,
            category_code=category, pipe_size_mm=rec.pipe_size_mm, is_metered=rec.is_metered,
            connection_date=rec.connection_date or payload.arrears_as_of, status="ACTIVE", source="MIGRATION",
            created_by=ctx.username,
        )
        db.add(conn)
        await db.flush()
        if rec.is_metered and rec.meter_serial_no:
            db.add(WaterMeter(tenant_id=ctx.tenant_id, connection_id=conn.id, serial_no=rec.meter_serial_no,
                              make=rec.meter_make or "UNKNOWN", size_mm=rec.pipe_size_mm,
                              initial_reading=Decimal(str(rec.last_reading or 0)), fixed_on=conn.connection_date,
                              status="ACTIVE", created_by=ctx.username))
        if rec.opening_arrears and money(rec.opening_arrears) > 0:
            await post_ledger(db, ctx, tenant_id=ctx.tenant_id, connection_id=conn.id, txn_type="OPENING_ARREAR", component="ARREAR",
                              bucket="ARREAR", amount=rec.opening_arrears, ward_id=conn.ward_id, entry_date=payload.arrears_as_of,
                              reference_no=rec.old_consumer_no, narration="Opening arrears taken over from the old system")
        location_pending += 0 if has_location else 1
        created.append({"oldConsumerNo": rec.old_consumer_no, "consumerNo": conn.consumer_no})
    audit(db, ctx, "MIGRATION_RUN", "migration", None, None, {"created": len(created), "exceptions": len(exceptions)})
    await db.commit()
    return {"created": created, "exceptions": exceptions, "locationPending": location_pending}


@router.get("/migration/exceptions")
async def migration_exceptions(ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("migration.run")
    rows = (await db.execute(select(WaterMigrationException).where(WaterMigrationException.tenant_id == ctx.tenant_id)
                             .order_by(WaterMigrationException.created_at.desc()))).scalars().all()
    return [{"id": r.id, "oldConsumerNo": r.old_consumer_no, "reason": r.reason, "status": r.status, "record": loads(r.raw_json),
             "createdAt": r.created_at} for r in rows]


# ------------------------------------------------------------------------------------------------
# Photo and document storage (WB-NF-65) - kept outside the database
# ------------------------------------------------------------------------------------------------

@router.post("/uploads", status_code=201)
async def upload(file: UploadFile = File(...), ctx: WaterContext = Depends(water_context)):
    if not (ctx.can("complaint.create") or ctx.can("reading.capture") or ctx.can("application.create")):
        ctx.require("complaint.create")
    ext = ALLOWED_TYPES.get((file.content_type or "").lower())
    if not ext:
        raise bad_request("Only JPG, PNG, WEBP photos or PDF documents can be uploaded.")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise bad_request("File is larger than 5 MB. Please send a smaller photo.")
    if not data:
        raise bad_request("The file is empty.")
    ref = f"{uuid.uuid4().hex}.{ext}"
    folder = STORAGE_DIR / ctx.tenant_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ref).write_bytes(data)
    return {"ref": ref, "sizeBytes": len(data), "contentType": file.content_type}


@router.get("/uploads/{ref}")
async def get_upload(ref: str, ctx: WaterContext = Depends(water_context)):
    if not REF_PATTERN.match(ref):
        raise not_found("File not found.")
    path = STORAGE_DIR / ctx.tenant_id / ref
    if not path.is_file():
        raise not_found("File not found.")
    media = {v: k for k, v in ALLOWED_TYPES.items()}[ref.rsplit(".", 1)[1]]
    return FileResponse(path, media_type=media)


# ------------------------------------------------------------------------------------------------
# Public verification of bills and receipts (SRS 3.1.1) - no login, no personal data (WB-NF-22)
# ------------------------------------------------------------------------------------------------

@router.get("/public/verify")
async def verify_document(doc_type: str = Query(..., alias="type"), number: str = Query(..., alias="no"),
                          code: str = Query(...), tenant: str = Query(...), db: AsyncSession = Depends(get_read_db)):
    tenant = tenant.strip().upper()
    if doc_type.upper() == "BILL":
        doc = await db.scalar(select(WaterBill).where(WaterBill.tenant_id == tenant, WaterBill.bill_no == number))
        amount = doc.total_payable if doc else None
        expected = document_code("BILL", number, amount) if doc else None
        extra = {"billDate": doc.bill_date, "dueDate": doc.due_date, "cycle": doc.cycle} if doc else {}
        status = "ISSUED"
    elif doc_type.upper() == "RECEIPT":
        doc = await db.scalar(select(WaterReceipt).where(WaterReceipt.tenant_id == tenant, WaterReceipt.receipt_no == number))
        amount = doc.amount if doc else None
        expected = document_code("RECEIPT", number, amount) if doc else None
        extra = {"receiptDate": doc.receipt_date, "paymentMode": doc.payment_mode} if doc else {}
        status = doc.status if doc else None
    else:
        raise bad_request("type must be BILL or RECEIPT.")
    if doc is None or expected != code.strip().upper():
        return {"genuine": False, "message": "No matching document. It may be altered or not issued by GWMC Water."}
    conn = await db.get(WaterConnection, doc.connection_id) if doc.connection_id else None
    return {"genuine": True, "documentType": doc_type.upper(), "number": number, "amount": float(money(amount)), "status": status,
            "consumerNo": conn.consumer_no if conn else None, **extra}


# ------------------------------------------------------------------------------------------------
# Citizen self-service (find and pay in three steps - SRS 3.1.1)
# ------------------------------------------------------------------------------------------------

@router.get("/citizen/lookup")
async def citizen_lookup(consumer_no: str = Query(..., alias="consumerNo"), mobile: str = Query(...),
                         ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    """Consumer finds their own connection with consumer number and registered mobile (OTP login is a platform service)."""
    ctx.require("payment.online")
    conn = await db.scalar(select(WaterConnection).where(WaterConnection.tenant_id == ctx.tenant_id,
                                                         WaterConnection.consumer_no == consumer_no.strip().upper()))
    digits = "".join(ch for ch in mobile if ch.isdigit())[-10:]
    if conn is None or not conn.mobile_number or conn.mobile_number[-10:] != digits:
        raise not_found("Consumer number and registered mobile number do not match our records.")
    bal = await balances(db, ctx.tenant_id, connection_id=conn.id)
    bills = (await db.execute(select(WaterBill).where(WaterBill.connection_id == conn.id).order_by(WaterBill.period_from.desc()).limit(6))).scalars().all()
    receipts = (await db.execute(select(WaterReceipt).where(WaterReceipt.connection_id == conn.id).order_by(WaterReceipt.created_at.desc()).limit(6))).scalars().all()
    complaints = (await db.execute(select(WaterComplaint).where(WaterComplaint.connection_id == conn.id).order_by(WaterComplaint.created_at.desc()).limit(5))).scalars().all()
    wards, _ = await ward_maps(db, ctx.tenant_id)
    return {
        "consumerNo": conn.consumer_no, "consumerName": conn.consumer_name, "address": conn.address, "status": conn.status,
        "category": conn.category_code, "isMetered": conn.is_metered, "dues": dues_summary(bal), "paymentStatus": payment_status(bal),
        "bills": [bill_dict(b) for b in bills],
        "receipts": [{"receiptNo": r.receipt_no, "amount": float(r.amount), "date": r.receipt_date, "mode": r.payment_mode,
                      "status": r.status, "verificationCode": r.verification_code} for r in receipts],
        "complaints": [complaint_dict(c, wards, conn.consumer_no, public=True) for c in complaints],
    }


@router.get("/citizen/bill/{bill_no}")
async def citizen_bill(bill_no: str, consumer_no: str = Query(..., alias="consumerNo"), mobile: str = Query(...),
                       ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    """A consumer's own printable bill, after the consumer number and registered mobile are matched."""
    ctx.require("payment.online")
    conn = await db.scalar(select(WaterConnection).where(WaterConnection.tenant_id == ctx.tenant_id,
                                                         WaterConnection.consumer_no == consumer_no.strip().upper()))
    digits = "".join(ch for ch in mobile if ch.isdigit())[-10:]
    if conn is None or not conn.mobile_number or conn.mobile_number[-10:] != digits:
        raise not_found("Consumer number and registered mobile number do not match our records.")
    bill = await db.scalar(select(WaterBill).where(WaterBill.tenant_id == ctx.tenant_id, WaterBill.bill_no == bill_no,
                                                   WaterBill.connection_id == conn.id))
    if bill is None:
        raise not_found(f"Bill {bill_no} not found for {conn.consumer_no}.")
    return await printable_bill(db, ctx.tenant_id, bill, conn)


# ------------------------------------------------------------------------------------------------
# Daily jobs (a scheduler calls this once a day; it can also be run by hand)
# ------------------------------------------------------------------------------------------------

@router.post("/jobs/daily")
async def run_daily_jobs(ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_write_db)):
    ctx.require("arrears.manage")
    as_of = today()
    result: Dict = {"asOf": as_of}
    result["onlinePaymentStatusCheck"] = await reconcile_pending_intents(db, ctx)
    await db.commit()
    result["penalty"] = await run_penalty(db, ctx, as_of)
    await db.commit()
    result["reminders"] = await run_reminders(db, ctx, as_of)
    await db.commit()
    result["disconnection"] = await run_disconnection(db, ctx, as_of)
    await db.commit()
    result["complaintEscalations"] = await escalate_complaints(db, ctx)
    result["applicationEscalations"] = await escalate_overdue_applications(db, ctx)
    audit(db, ctx, "DAILY_JOBS_RUN", "job", None, None, {"asOf": as_of})
    await db.commit()
    return result


@router.get("/cycles/current")
async def current_cycle(ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    months = int(await get_setting(db, ctx.tenant_id, "billing.cycleMonths"))
    return {"cycle": cycle_for_date(today(), months), "cycleMonths": months}
