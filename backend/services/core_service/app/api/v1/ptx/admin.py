"""
Administration and integration readiness: versioned settings (PT-NF-50), code lists (SRS 3.6.3), audit / event / API logs
(PT-NF-13, PT-IR-02, PT-IR-09), link switches (PT-IR-06), register export (PT-IR-03), data migration (SRS 3.6.2),
document and photo storage (PT-NF-65), public QR verification (SRS 3.1.1) and the daily jobs.
"""
import csv
import io
import os
import re
import uuid
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ptx_calc import document_code, mask_mobile, money, payment_status, period_label
from app.db.models import Ward
from app.db.ptx_models import (
    PtxApiLog, PtxAuditLog, PtxCertificate, PtxCode, PtxDemand, PtxEvent, PtxFloor, PtxMigrationException, PtxNotice, PtxNotification,
    PtxParty, PtxProperty, PtxReceipt, PtxSetting,
)
from app.db.session import get_read_db, get_write_db
from app.schemas.ptx import CodeCreate, MigrationBatch, MigrationRecord, SettingChange
from .complaints import escalate_complaints
from .arrears import run_interest, run_recovery, run_reminders
from .assess import calculate, create_property, effective_period_start, new_assessment
from .cases import escalate_cases, run_auto_finalise
from .common import (
    DEFAULT_SETTINGS, DUES_BUCKETS, SETTING_DESCRIPTIONS, PtxAPIRoute, PtxContext, audit, bad_request, bulk_balances, conflict,
    dues_summary, dumps, get_links, get_setting, loads, not_found, page, paginate, post_ledger, ptx_context, today, ward_maps,
)
from .payments import reconcile_pending_intents

router = APIRouter(route_class=PtxAPIRoute)

STORAGE_DIR = Path(os.getenv("PTX_STORAGE_DIR", Path(__file__).resolve().parents[4] / "storage" / "ptx"))
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf"}
REF_PATTERN = re.compile(r"^[0-9a-f]{32}\.(jpg|png|webp|pdf)$")


# ------------------------------------------------------------------------------------------------
# Settings and code lists
# ------------------------------------------------------------------------------------------------

def _validate_setting(key: str, value) -> None:
    default = DEFAULT_SETTINGS[key]
    if not isinstance(value, type(default)) and not (isinstance(default, (int, float)) and isinstance(value, (int, float))):
        raise bad_request(f"'{key}' must be a {type(default).__name__}, like the current value.")
    if key == "demand.frequency" and value not in ("HALF_YEARLY", "YEARLY"):
        raise bad_request("Demand frequency must be HALF_YEARLY or YEARLY.")
    if key == "payment.allocationOrder" and sorted(value) != sorted(DUES_BUCKETS):
        raise bad_request(f"Payment order must list each of {', '.join(DUES_BUCKETS)} exactly once.")
    if key == "schemes":
        for s in value:
            if not {"code", "type", "from", "to"} <= set(s) or s["type"] not in ("REBATE", "OTS"):
                raise bad_request("Each scheme needs code, type (REBATE or OTS), from and to dates.")
    if key == "workflow":
        for t, steps in value.items():
            if not steps or not all({"code", "label", "slaHours", "roles"} <= set(s) for s in steps):
                raise bad_request(f"Each step of {t} needs code, label, slaHours and roles.")


@router.get("/admin/settings")
async def list_settings(ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("rates.view")
    out = []
    for key in sorted(DEFAULT_SETTINGS):
        history = (await db.execute(select(PtxSetting).where(PtxSetting.tenant_id == ctx.tenant_id, PtxSetting.key == key)
                                    .order_by(PtxSetting.effective_from.desc(), PtxSetting.created_at.desc()))).scalars().all()
        out.append({"key": key, "description": SETTING_DESCRIPTIONS.get(key, ""), "value": await get_setting(db, ctx.tenant_id, key), "configured": bool(history),
                    "versions": [{"value": loads(h.value_json), "effectiveFrom": h.effective_from, "reason": h.reason, "createdBy": h.created_by,
                                  "createdAt": h.created_at} for h in history]})
    return out


@router.post("/admin/settings", status_code=201)
async def change_setting(payload: SettingChange, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    ctx.require("settings.manage")
    if payload.key not in DEFAULT_SETTINGS:
        raise bad_request(f"Unknown setting '{payload.key}'.")
    if payload.effective_from < today():
        raise bad_request("A setting cannot be changed with a past effective date.")
    _validate_setting(payload.key, payload.value)
    old = await get_setting(db, ctx.tenant_id, payload.key, payload.effective_from)
    row = PtxSetting(tenant_id=ctx.tenant_id, key=payload.key, value_json=dumps(payload.value), effective_from=payload.effective_from,
                     reason=payload.reason, created_by=ctx.username)
    db.add(row)
    audit(db, ctx, "SETTING_CHANGED", "setting", row.id, {"key": payload.key, "value": old}, {"key": payload.key, "value": payload.value,
                                                                                              "effectiveFrom": payload.effective_from})
    await db.commit()
    return {"message": f"'{payload.key}' will apply from {payload.effective_from.strftime('%d-%m-%Y')}"}


@router.get("/admin/codes")
async def list_codes(list_name: Optional[str] = Query(None, alias="list"), ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("rates.view")
    stmt = select(PtxCode).where(PtxCode.tenant_id == ctx.tenant_id)
    if list_name:
        stmt = stmt.where(PtxCode.list_name == list_name.upper())
    rows = (await db.execute(stmt.order_by(PtxCode.list_name, PtxCode.code))).scalars().all()
    return [{"listName": c.list_name, "code": c.code, "nameEn": c.name_en, "nameTe": c.name_te, "extra": loads(c.extra_json, {}), "isActive": c.is_active} for c in rows]


@router.post("/admin/codes", status_code=201)
async def add_code(payload: CodeCreate, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    ctx.require("settings.manage")
    code = payload.code.strip().upper().replace(" ", "_")
    if await db.scalar(select(PtxCode.id).where(PtxCode.tenant_id == ctx.tenant_id, PtxCode.list_name == payload.list_name, PtxCode.code == code)):
        raise conflict(f"{code} already exists in {payload.list_name}.")
    db.add(PtxCode(tenant_id=ctx.tenant_id, list_name=payload.list_name, code=code, name_en=payload.name_en, name_te=payload.name_te,
                   extra_json=dumps(payload.extra)))
    audit(db, ctx, "CODE_ADDED", "code", None, None, {"list": payload.list_name, "code": code})
    await db.commit()
    hint = " Add its rates in a new rate table before using it." if payload.list_name in ("USAGE", "CONSTRUCTION") else ""
    return {"message": f"{code} added to {payload.list_name.lower()}.{hint}"}


# ------------------------------------------------------------------------------------------------
# Logs and integration links
# ------------------------------------------------------------------------------------------------

@router.get("/admin/audit")
async def audit_log(search: Optional[str] = Query(None), action: Optional[str] = Query(None), skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                    ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("audit.view")
    stmt = select(PtxAuditLog).where(PtxAuditLog.tenant_id == ctx.tenant_id)
    if action:
        stmt = stmt.where(PtxAuditLog.action == action.upper())
    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(PtxAuditLog.actor.ilike(like) | PtxAuditLog.action.ilike(like) | PtxAuditLog.new_json.ilike(like))
    rows, total = await paginate(db, stmt.order_by(PtxAuditLog.at.desc()), skip, limit)
    return page([{"at": r.at, "actor": r.actor, "ipAddress": r.ip_address, "action": r.action, "entityType": r.entity_type, "entityId": r.entity_id,
                  "old": loads(r.old_json), "new": loads(r.new_json)} for (r,) in rows], total, skip, limit)


@router.get("/admin/events")
async def event_outbox(event_type: Optional[str] = Query(None, alias="type"), skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                       ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("audit.view")
    stmt = select(PtxEvent).where(PtxEvent.tenant_id == ctx.tenant_id)
    if event_type:
        stmt = stmt.where(PtxEvent.event_type == event_type)
    rows, total = await paginate(db, stmt.order_by(PtxEvent.created_at.desc()), skip, limit)
    counts = dict((await db.execute(select(PtxEvent.event_type, func.count()).where(PtxEvent.tenant_id == ctx.tenant_id).group_by(PtxEvent.event_type))).all())
    return {"counts": counts, "events": page([{"id": e.id, "eventType": e.event_type, "payload": loads(e.payload_json), "published": e.published,
                                              "createdAt": e.created_at} for (e,) in rows], total, skip, limit)}


@router.get("/admin/api-log")
async def api_log(search: Optional[str] = Query(None), skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                  ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("audit.view")
    stmt = select(PtxApiLog).where(PtxApiLog.tenant_id == ctx.tenant_id)
    if search and search.strip():
        stmt = stmt.where(PtxApiLog.path.ilike(f"%{search.strip()}%") | PtxApiLog.caller.ilike(f"%{search.strip()}%"))
    rows, total = await paginate(db, stmt.order_by(PtxApiLog.at.desc()), skip, limit)
    return page([{"at": r.at, "caller": r.caller, "method": r.method, "path": r.path, "statusCode": r.status_code, "durationMs": r.duration_ms}
                 for (r,) in rows], total, skip, limit)


@router.get("/admin/notifications")
async def notifications(search: Optional[str] = Query(None), skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                        ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("audit.view")
    stmt = select(PtxNotification).where(PtxNotification.tenant_id == ctx.tenant_id)
    if search and search.strip():
        stmt = stmt.where(PtxNotification.template.ilike(f"%{search.strip()}%") | PtxNotification.ref_no.ilike(f"%{search.strip()}%"))
    rows, total = await paginate(db, stmt.order_by(PtxNotification.created_at.desc()), skip, limit)
    return page([{"at": n.created_at, "channel": n.channel, "recipient": mask_mobile(n.recipient) if n.recipient and n.recipient.isdigit() else n.recipient,
                  "template": n.template, "messageEn": n.message_en, "messageTe": n.message_te, "refNo": n.ref_no, "status": n.status}
                 for (n,) in rows], total, skip, limit)


@router.get("/integration/links")
async def integration_links(ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    """Planned links (SRS 3.7.1); all off in Release 1, switched by configuration only (PT-IR-06)."""
    ctx.require("property.view")
    return [{"link": k, **v} for k, v in (await get_links(db, ctx.tenant_id)).items()]


# ------------------------------------------------------------------------------------------------
# Register export (PT-IR-03)
# ------------------------------------------------------------------------------------------------

EXPORT_COLUMNS = ["upin", "oldAssessmentNo", "status", "propertyType", "doorNo", "address", "wardNumber", "wardName", "zoneCode", "latitude", "longitude",
                  "ownerNames", "uses", "siteAreaSqyd", "buildingPermissionNo", "occupancyCertificateNo", "totalDue", "duesStatus"]


@router.get("/export/register")
async def export_register(fmt: str = Query("csv", alias="format"), ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    """
    Documented bulk export of the property register for one-time loading by modules that join later, e.g. matching
    water connections to UPINs. Owner mobiles and identity details are left out (PT-NF-23).
    """
    ctx.require("reports.view")
    props = (await db.execute(select(PtxProperty).where(PtxProperty.tenant_id == ctx.tenant_id, ctx.ward_filter(PtxProperty.ward_id))
                              .order_by(PtxProperty.upin))).scalars().all()
    ids = [p.id for p in props]
    bal = await bulk_balances(db, ctx.tenant_id, ids)
    wards, _ = await ward_maps(db, ctx.tenant_id)
    owners: Dict[str, list] = {}
    for p in (await db.execute(select(PtxParty).where(PtxParty.property_id.in_(ids or ["__none__"]), PtxParty.role == "OWNER", PtxParty.is_current.is_(True)))).scalars().all():
        owners.setdefault(p.property_id, []).append(p.full_name)
    uses: Dict[str, set] = {}
    for f in (await db.execute(select(PtxFloor).where(PtxFloor.property_id.in_(ids or ["__none__"]), PtxFloor.is_current.is_(True)))).scalars().all():
        uses.setdefault(f.property_id, set()).add(f.usage_code)
    rows = [{"upin": p.upin, "oldAssessmentNo": p.old_assessment_no, "status": p.status, "propertyType": p.property_type, "doorNo": p.door_no,
             "address": p.address, "wardNumber": wards.get(p.ward_id, {}).get("wardNumber"), "wardName": wards.get(p.ward_id, {}).get("wardName"),
             "zoneCode": wards.get(p.ward_id, {}).get("zoneCode"), "latitude": p.latitude, "longitude": p.longitude,
             "ownerNames": "; ".join(owners.get(p.id, [])), "uses": "; ".join(sorted(uses.get(p.id, set()))) or p.property_type,
             "siteAreaSqyd": float(p.site_area_sqyd or 0), "buildingPermissionNo": p.building_permission_no,
             "occupancyCertificateNo": p.occupancy_certificate_no, "totalDue": dues_summary(bal[p.id])["totalDue"], "duesStatus": payment_status(bal[p.id])}
            for p in props]
    audit(db, ctx, "REGISTER_EXPORTED", "export", None, None, {"format": fmt, "rows": len(rows)})
    await db.commit()
    if fmt == "json":
        return {"format": "urban.ptx.property-register.v1", "generatedAt": today(), "columns": EXPORT_COLUMNS, "rows": rows}
    buf = io.StringIO()
    buf.write("﻿")
    w = csv.DictWriter(buf, fieldnames=EXPORT_COLUMNS)
    w.writeheader()
    w.writerows(rows)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="property-register-{today()}.csv"'})


# ------------------------------------------------------------------------------------------------
# Data migration (SRS 3.6.2)
# ------------------------------------------------------------------------------------------------

@router.post("/migration/properties")
async def migrate(payload: MigrationBatch, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """
    Loads existing property tax records: each gets a UPIN, keeps its old assessment number (PT-05), is assessed with the
    current rates and carries its signed-off opening arrears. Records with no map location are flagged for field
    verification; records that cannot be matched are listed, never dropped.
    """
    ctx.require("migration.run")
    wards = {}
    for w in (await db.execute(select(Ward).where(Ward.tenant_id == ctx.tenant_id))).scalars().all():
        wards.setdefault(w.ward_number, w)
    usage = {c.code for c in (await db.execute(select(PtxCode).where(PtxCode.tenant_id == ctx.tenant_id, PtxCode.list_name == "USAGE"))).scalars().all()}
    construction = {c.code for c in (await db.execute(select(PtxCode).where(PtxCode.tenant_id == ctx.tenant_id, PtxCode.list_name == "CONSTRUCTION"))).scalars().all()}
    effective = await effective_period_start(db, ctx.tenant_id, payload.arrears_as_of)
    created, exceptions, pending_location = [], [], 0

    def exception(raw: Dict, reason: str):
        db.add(PtxMigrationException(tenant_id=ctx.tenant_id, old_assessment_no=str(raw.get("oldAssessmentNo") or ""), raw_json=dumps(raw),
                                     reason=reason, created_by=ctx.username))
        exceptions.append({"oldAssessmentNo": raw.get("oldAssessmentNo"), "reason": reason})

    for raw in payload.records:
        try:
            rec = MigrationRecord.model_validate(raw)
        except ValidationError as exc:
            exception(raw, "Invalid record: " + "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()))
            continue
        if await db.scalar(select(PtxProperty.id).where(PtxProperty.tenant_id == ctx.tenant_id, PtxProperty.old_assessment_no == rec.old_assessment_no)):
            exception(raw, "Old assessment number already migrated")
            continue
        ward = wards.get(rec.ward_number) if rec.ward_number is not None else None
        if ward is None:
            exception(raw, f"Ward {rec.ward_number} not found: needs field verification")
            continue
        if rec.property_type == "BUILT" and (rec.usage_code not in usage or rec.construction_code not in construction or rec.builtup_sqft <= 0):
            exception(raw, "Use, construction type or built-up area missing or not in the code lists")
            continue
        details = {"propertyType": rec.property_type, "wardId": ward.id, "doorNo": rec.door_no, "address": rec.address, "latitude": rec.latitude,
                   "longitude": rec.longitude, "siteAreaSqyd": rec.site_area_sqyd, "constructionYear": rec.construction_year, "roadClass": rec.road_class or None}
        floors = [] if rec.property_type == "VACANT_LAND" else [{"floorNo": 0, "usageCode": rec.usage_code, "constructionCode": rec.construction_code,
                                                                  "builtupSqft": rec.builtup_sqft, "occupancy": "OWNER"}]
        try:
            calc = await calculate(db, ctx.tenant_id, details, floors, effective)
        except Exception as exc:
            exception(raw, f"Tax could not be worked out: {getattr(exc, 'detail', exc)}")
            continue
        prop = await create_property(db, ctx.username, ctx.tenant_id, ctx.sub_tenant_id, details, floors,
                                     [{"fullName": rec.owner_name, "mobileNumber": rec.owner_mobile}], [], "MIGRATION", effective, None, rec.old_assessment_no)
        await new_assessment(db, ctx.username, prop, "MIGRATION", calc, effective, "FINAL")
        if rec.opening_arrears and money(rec.opening_arrears) > 0:
            await post_ledger(db, ctx, prop=prop, txn_type="OPENING_ARREAR", component="ARREAR", bucket="ARREAR", amount=rec.opening_arrears,
                              entry_date=payload.arrears_as_of, reference_no=rec.old_assessment_no, narration="Opening arrears from the old system (signed off by GWMC)")
        pending_location += 1 if prop.location_pending else 0
        created.append({"oldAssessmentNo": rec.old_assessment_no, "upin": prop.upin})
    audit(db, ctx, "MIGRATION_RUN", "migration", None, None, {"created": len(created), "exceptions": len(exceptions)})
    await db.commit()
    return {"created": created, "exceptions": exceptions, "locationPending": pending_location}


@router.get("/migration/exceptions")
async def migration_exceptions(skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100), ctx: PtxContext = Depends(ptx_context),
                               db: AsyncSession = Depends(get_read_db)):
    ctx.require("migration.run")
    rows, total = await paginate(db, select(PtxMigrationException).where(PtxMigrationException.tenant_id == ctx.tenant_id)
                                 .order_by(PtxMigrationException.created_at.desc()), skip, limit)
    return page([{"id": r.id, "oldAssessmentNo": r.old_assessment_no, "reason": r.reason, "status": r.status, "record": loads(r.raw_json),
                  "createdAt": r.created_at} for (r,) in rows], total, skip, limit)


# ------------------------------------------------------------------------------------------------
# Documents and photos, stored outside the database (PT-NF-65)
# ------------------------------------------------------------------------------------------------

@router.post("/uploads", status_code=201)
async def upload(file: UploadFile = File(...), ctx: PtxContext = Depends(ptx_context)):
    if not (ctx.can("case.create") or ctx.can("survey.capture") or ctx.can("notice.serve")):
        ctx.require("case.create")
    ext = ALLOWED_TYPES.get((file.content_type or "").lower())
    if not ext:
        raise bad_request("Only JPG, PNG or WEBP photos and PDF documents can be uploaded.")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise bad_request("The file is larger than 5 MB. Please send a smaller photo or scan.")
    if not data:
        raise bad_request("The file is empty.")
    ref = f"{uuid.uuid4().hex}.{ext}"
    folder = STORAGE_DIR / ctx.tenant_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / ref).write_bytes(data)
    return {"ref": ref, "sizeBytes": len(data), "contentType": file.content_type, "fileName": file.filename}


@router.get("/uploads/{ref}")
async def get_upload(ref: str, ctx: PtxContext = Depends(ptx_context)):
    if not REF_PATTERN.match(ref):
        raise not_found("File not found.")
    path = STORAGE_DIR / ctx.tenant_id / ref
    if not path.is_file():
        raise not_found("File not found.")
    return FileResponse(path, media_type={v: k for k, v in ALLOWED_TYPES.items()}[ref.rsplit(".", 1)[1]])


# ------------------------------------------------------------------------------------------------
# Public verification by QR code - no login, no personal data (SRS 3.1.1, PT-NF-22)
# ------------------------------------------------------------------------------------------------

@router.get("/public/verify")
async def verify_document(doc_type: str = Query(..., alias="type"), number: str = Query(..., alias="no"), code: str = Query(...),
                          tenant: str = Query(...), db: AsyncSession = Depends(get_read_db)):
    tenant = tenant.strip().upper()
    kind = doc_type.upper()
    model = {"RECEIPT": (PtxReceipt, PtxReceipt.receipt_no), "DEMAND": (PtxDemand, PtxDemand.demand_no), "NOTICE": (PtxNotice, PtxNotice.notice_no),
             "CERTIFICATE": (PtxCertificate, PtxCertificate.certificate_no)}.get(kind)
    if model is None:
        raise bad_request("type must be RECEIPT, DEMAND, NOTICE or CERTIFICATE.")
    cls, column = model
    doc = await db.scalar(select(cls).where(cls.tenant_id == tenant, column == number))
    if doc is None:
        return {"genuine": False, "message": "No matching document. It may be altered or not issued by GWMC."}
    amount = {"RECEIPT": lambda d: d.amount, "DEMAND": lambda d: d.amount, "NOTICE": lambda d: d.amount or 0, "CERTIFICATE": lambda d: 0}[kind](doc)
    if document_code(kind, number, amount) != code.strip().upper():
        return {"genuine": False, "message": "The verification code does not match. The document may be altered."}
    prop = await db.get(PtxProperty, doc.property_id)
    info = {"genuine": True, "documentType": kind, "number": number, "upin": prop.upin if prop else None}
    if kind == "RECEIPT":
        info.update({"amount": float(doc.amount), "date": doc.receipt_date, "status": doc.status, "mode": doc.payment_mode})
    elif kind == "DEMAND":
        info.update({"amount": float(doc.amount), "period": period_label(doc.period), "dueDate": doc.due_date})
    elif kind == "NOTICE":
        info.update({"noticeType": doc.notice_type, "issuedAt": doc.issued_at, "amount": float(doc.amount or 0)})
    else:
        info.update({"certType": doc.cert_type, "purpose": doc.purpose, "issuedOn": doc.issued_on, "validUntil": doc.valid_until,
                     "stillValid": doc.valid_until >= today(), "paidUpTo": doc.paid_up_to})
    return info


# ------------------------------------------------------------------------------------------------
# Daily jobs (a scheduler calls this once a day; it can also be run by hand)
# ------------------------------------------------------------------------------------------------

@router.post("/jobs/daily")
async def daily_jobs(ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    ctx.require("arrears.manage")
    as_of = today()
    result: Dict = {"asOf": as_of}
    result["onlinePaymentStatusCheck"] = await reconcile_pending_intents(db, ctx, ctx.tenant_id)
    await db.commit()
    result["casesFinalised"] = await run_auto_finalise(db, ctx.username, ctx.tenant_id)
    await db.commit()
    result["interest"] = await run_interest(db, ctx, ctx.tenant_id, as_of, ctx.ward_filter)
    await db.commit()
    result["reminders"] = await run_reminders(db, ctx.tenant_id, as_of, ctx.ward_filter)
    await db.commit()
    result["recovery"] = await run_recovery(db, ctx, ctx.tenant_id, as_of, ctx.ward_filter)
    result["escalations"] = await escalate_cases(db, ctx.tenant_id)
    result["complaintEscalations"] = await escalate_complaints(db, ctx.tenant_id)
    audit(db, ctx, "DAILY_JOBS_RUN", "job", None, None, {"asOf": as_of})
    await db.commit()
    return result
