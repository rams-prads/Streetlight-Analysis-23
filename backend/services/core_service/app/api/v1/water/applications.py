"""
New connection and change-request workflow (WB-05, WB-06, WB-IR-06).

Each application carries a snapshot of the configured steps, each with an SLA and the roles that may
complete it. Steps switched off in configuration (for example the property tax dues check, which needs
link I-05) are skipped. Overdue steps are escalated by the daily job.
"""
import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.water_calc import hash_aadhaar, mask_mobile, money
from app.db.models import Ward
from app.db.session import get_read_db, get_write_db
from app.db.water_models import (
    WaterApplication, WaterCategory, WaterConnection, WaterLedger, WaterMeter, WaterTimeline, utcnow,
)
from app.schemas.water import ApplicationAction, ApplicationCreate
from .common import (
    ADMIN, WaterAPIRoute, WaterContext, audit, bad_request, balances, conflict, dues_total, dumps,
    emit_event, get_setting, load_connection, loads, new_consumer_no, new_doc_no, not_found, notify,
    post_ledger, timeline, today, ward_maps, water_context,
)
from .connections import find_duplicates, record_change

router = APIRouter(route_class=WaterAPIRoute)

CHANGE_TYPES_REQUIRING_ACTIVE = {"OWNER_CHANGE", "CATEGORY_CHANGE", "PIPE_SIZE_CHANGE", "TEMP_DISCONNECTION"}


def _now() -> datetime.datetime:
    return utcnow()


def _activate_next(app: WaterApplication, steps: List[Dict]) -> Optional[Dict]:
    for step in steps:
        if step["status"] == "PENDING":
            step["status"] = "CURRENT"
            step["startedAt"] = _now().isoformat()
            step["dueAt"] = (_now() + datetime.timedelta(hours=float(step.get("slaHours", 48)))).isoformat()
            app.current_step = step["code"]
            return step
    app.current_step = None
    return None


async def _validate_category(db: AsyncSession, tenant_id: str, code: Optional[str]) -> str:
    if not code:
        raise bad_request("Connection category is required.")
    found = await db.scalar(select(WaterCategory).where(
        WaterCategory.tenant_id == tenant_id, WaterCategory.code == code.upper(), WaterCategory.is_active.is_(True)))
    if not found:
        raise bad_request(f"Category '{code}' is not in the category list.")
    return found.code


def application_dict(app: WaterApplication, wards: Dict, consumer_no: Optional[str] = None) -> Dict:
    ward = wards.get(app.ward_id, {}) if app.ward_id else {}
    return {
        "id": app.id, "applicationNo": app.application_no, "appType": app.app_type, "channel": app.channel,
        "consumerNo": consumer_no, "applicantName": app.applicant_name, "mobileMasked": mask_mobile(app.mobile_number),
        "aadhaarMasked": f"XXXX-XXXX-{app.aadhaar_last4}" if app.aadhaar_last4 else None,
        "wardId": app.ward_id, "wardNumber": ward.get("wardNumber"), "wardName": ward.get("wardName"),
        "address": app.address, "doorNo": app.door_no, "latitude": app.latitude, "longitude": app.longitude,
        "details": loads(app.details_json, {}), "documents": loads(app.documents_json, []),
        "warnings": loads(app.warnings_json, []), "estimate": loads(app.estimate_json, None),
        "estimateTotal": float(app.estimate_total) if app.estimate_total is not None else None,
        "amountPaid": float(app.amount_paid or 0), "steps": loads(app.steps_json, []),
        "currentStep": app.current_step, "status": app.status, "escalationLevel": app.escalation_level,
        "createdBy": app.created_by, "createdAt": app.created_at, "completedAt": app.completed_at,
    }


@router.post("/applications", status_code=201)
async def create_application(payload: ApplicationCreate, ctx: WaterContext = Depends(water_context),
                             db: AsyncSession = Depends(get_write_db)):
    ctx.require("application.create")
    if not payload.consent:
        raise bad_request("Consent to use personal data for this application must be recorded (DPDP Act 2023).")
    details: Dict = {}
    conn: Optional[WaterConnection] = None
    warnings: List[Dict] = []

    if payload.app_type == "NEW_CONNECTION":
        missing = [name for name, value in (
            ("applicant name", payload.applicant_name), ("mobile number", payload.mobile_number),
            ("ward", payload.ward_id), ("address", payload.address), ("pipe size", payload.pipe_size_mm),
            ("metered / non-metered", payload.is_metered),
        ) if value in (None, "")]
        if missing:
            raise bad_request("Please fill in: " + ", ".join(missing) + ".")
        ward = await db.scalar(select(Ward).where(Ward.id == payload.ward_id, Ward.tenant_id == ctx.tenant_id))
        if not ward:
            raise bad_request("Ward not found.")
        ctx.ensure_scope(ward.id)
        fees = await get_setting(db, ctx.tenant_id, "fees.connection")
        if str(payload.pipe_size_mm) not in fees.get("byPipeSizeMm", {}):
            raise bad_request(f"Pipe size {payload.pipe_size_mm} mm is not in the fee table. Allowed: {', '.join(sorted(fees['byPipeSizeMm'], key=int))} mm.")
        details = {
            "categoryCode": await _validate_category(db, ctx.tenant_id, payload.category_code),
            "pipeSizeMm": payload.pipe_size_mm, "isMetered": payload.is_metered, "locality": payload.locality,
            "pincode": payload.pincode, "oldAssessmentNo": payload.old_assessment_no, "upin": payload.upin,
            "supplyArea": payload.supply_area, "zoneId": ward.zone_id,
        }
        warnings = await find_duplicates(db, ctx.tenant_id, address=payload.address, door_no=payload.door_no,
                                         latitude=payload.latitude, longitude=payload.longitude)
        ward_id, address, door_no = ward.id, payload.address, payload.door_no
        lat, lng = payload.latitude, payload.longitude
    else:
        if not payload.consumer_no:
            raise bad_request("Consumer number is required for a change request.")
        conn = await load_connection(db, ctx, consumer_no=payload.consumer_no)
        if payload.app_type in CHANGE_TYPES_REQUIRING_ACTIVE and conn.status != "ACTIVE":
            raise bad_request(f"This request needs an active connection; the connection is {conn.status}.")
        if payload.app_type == "TEMP_RECONNECTION" and conn.status != "TEMP_DISCONNECTED":
            raise bad_request("Only a connection that was temporarily disconnected on request can be restored this way. "
                              "Connections cut for arrears are reconnected from the Arrears screen after dues are paid.")
        if payload.app_type == "PERM_DISCONNECTION" and conn.status not in ("ACTIVE", "TEMP_DISCONNECTED"):
            raise bad_request(f"The connection is {conn.status}; permanent disconnection is not possible.")
        if payload.app_type == "OWNER_CHANGE":
            if not payload.applicant_name or not payload.mobile_number:
                raise bad_request("New owner's name and mobile number are required.")
            if not payload.documents:
                raise bad_request("Upload the ownership documents (sale deed, mutation order or similar).")
            details = {"newOwnerName": payload.applicant_name, "newMobile": payload.mobile_number, "newEmail": payload.email}
        elif payload.app_type == "CATEGORY_CHANGE":
            code = await _validate_category(db, ctx.tenant_id, payload.category_code)
            if code == conn.category_code:
                raise bad_request("The connection is already in this category.")
            details = {"fromCategory": conn.category_code, "toCategory": code}
        elif payload.app_type == "PIPE_SIZE_CHANGE":
            fees = await get_setting(db, ctx.tenant_id, "fees.connection")
            if not payload.pipe_size_mm or str(payload.pipe_size_mm) not in fees.get("byPipeSizeMm", {}):
                raise bad_request("Choose a pipe size from the fee table.")
            if payload.pipe_size_mm == conn.pipe_size_mm:
                raise bad_request("The connection already has this pipe size.")
            details = {"fromPipeSizeMm": conn.pipe_size_mm, "toPipeSizeMm": payload.pipe_size_mm}
        else:
            details = {}
        open_same = await db.scalar(select(WaterApplication.application_no).where(
            WaterApplication.tenant_id == ctx.tenant_id, WaterApplication.connection_id == conn.id,
            WaterApplication.app_type == payload.app_type, WaterApplication.status == "IN_PROGRESS"))
        if open_same:
            raise conflict(f"Application {open_same} of the same type is already in progress for this connection.")
        ward_id, address, door_no, lat, lng = conn.ward_id, conn.address, conn.door_no, conn.latitude, conn.longitude
        details["reason"] = payload.reason

    aadhaar_hash = aadhaar_last4 = None
    if payload.aadhaar_number:
        try:
            aadhaar_hash, aadhaar_last4 = hash_aadhaar(payload.aadhaar_number)
        except ValueError as exc:
            raise bad_request(str(exc))

    workflow = await get_setting(db, ctx.tenant_id, "workflow")
    template = workflow.get(payload.app_type)
    if not template:
        raise bad_request(f"No workflow is configured for {payload.app_type}.")
    steps = [{**s, "status": "PENDING" if s.get("enabled", True) else "SKIPPED"} for s in template]

    app = WaterApplication(
        tenant_id=ctx.tenant_id, sub_tenant_id=ctx.sub_tenant_id,
        application_no=await new_doc_no(db, ctx.tenant_id, "WAP", "application"),
        app_type=payload.app_type, connection_id=conn.id if conn else None, channel=payload.channel,
        applicant_name=payload.applicant_name, mobile_number=payload.mobile_number, email=payload.email,
        aadhaar_hash=aadhaar_hash, aadhaar_last4=aadhaar_last4, consent_recorded=True,
        ward_id=ward_id, address=address, door_no=door_no, latitude=lat, longitude=lng,
        details_json=dumps(details), documents_json=dumps(payload.documents), warnings_json=dumps(warnings),
        created_by=ctx.username,
    )
    _activate_next(app, steps)
    app.steps_json = dumps(steps)
    db.add(app)
    await db.flush()
    timeline(db, ctx, "application", app.id, "FILED", f"{payload.app_type} via {payload.channel}")
    audit(db, ctx, "APPLICATION_FILED", "application", app.id, None,
          {"applicationNo": app.application_no, "type": app.app_type, "consumerNo": conn.consumer_no if conn else None})
    await notify(db, ctx.tenant_id, recipient=payload.mobile_number or (conn.mobile_number if conn else None),
                 template="APPLICATION_FILED", connection_id=conn.id if conn else None, ref_no=app.application_no,
                 message_en=f"GWMC Water: your application {app.application_no} has been received.",
                 message_te=f"జీడబ్ల్యూఎంసీ నీటి సరఫరా: మీ దరఖాస్తు {app.application_no} స్వీకరించబడింది.")
    await db.commit()
    wards, _ = await ward_maps(db, ctx.tenant_id)
    return application_dict(app, wards, conn.consumer_no if conn else None)


@router.get("/applications")
async def list_applications(
    status: Optional[str] = Query(None), app_type: Optional[str] = Query(None, alias="appType"),
    q: Optional[str] = Query(None), limit: int = Query(100, ge=1, le=500),
    ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db),
):
    ctx.require("application.view")
    stmt = select(WaterApplication, WaterConnection.consumer_no).outerjoin(
        WaterConnection, WaterConnection.id == WaterApplication.connection_id
    ).where(WaterApplication.tenant_id == ctx.tenant_id, ctx.ward_filter(WaterApplication.ward_id))
    if status:
        stmt = stmt.where(WaterApplication.status == status.upper())
    if app_type:
        stmt = stmt.where(WaterApplication.app_type == app_type.upper())
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(WaterApplication.application_no.ilike(like), WaterApplication.applicant_name.ilike(like),
                              WaterConnection.consumer_no.ilike(like)))
    rows = (await db.execute(stmt.order_by(WaterApplication.created_at.desc()).limit(limit))).all()
    wards, _ = await ward_maps(db, ctx.tenant_id)
    return [application_dict(a, wards, consumer_no) for a, consumer_no in rows]


async def _load_app(db: AsyncSession, ctx: WaterContext, application_no: str, for_update: bool = False) -> WaterApplication:
    stmt = select(WaterApplication).where(WaterApplication.tenant_id == ctx.tenant_id,
                                          WaterApplication.application_no == application_no)
    if for_update:
        stmt = stmt.with_for_update()
    app = await db.scalar(stmt)
    if not app:
        raise not_found(f"Application {application_no} not found.")
    ctx.ensure_scope(app.ward_id)
    return app


@router.get("/applications/{application_no}")
async def get_application(application_no: str, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("application.view")
    app = await _load_app(db, ctx, application_no)
    conn = await db.get(WaterConnection, app.connection_id) if app.connection_id else None
    wards, _ = await ward_maps(db, ctx.tenant_id)
    result = application_dict(app, wards, conn.consumer_no if conn else None)
    events = (await db.execute(select(WaterTimeline).where(WaterTimeline.entity_id == app.id).order_by(WaterTimeline.at))).scalars().all()
    result["timeline"] = [{"action": e.action, "remark": e.remark, "actor": e.actor, "at": e.at} for e in events]
    bal = await balances(db, ctx.tenant_id, application_id=app.id)
    result["amountOutstanding"] = float(max(dues_total(bal), Decimal("0")))
    return result


async def _post_estimate(db: AsyncSession, ctx: WaterContext, app: WaterApplication) -> None:
    """Works out charges from the fee table and raises them against the application (WB-05)."""
    details = loads(app.details_json, {})
    fees = await get_setting(db, ctx.tenant_id, "fees.connection")
    metres = Decimal(str(details.get("roadCuttingMetres", 0) or 0))
    pipe = details.get("pipeSizeMm") if app.app_type == "NEW_CONNECTION" else details.get("toPipeSizeMm")
    lines = [
        {"component": "CONNECTION_FEE", "label": f"Connection charge ({pipe} mm)", "amount": money(fees["byPipeSizeMm"][str(pipe)])},
        {"component": "ROAD_CUTTING", "label": f"Road cutting ({metres} m)", "amount": money(metres * Decimal(str(fees.get("roadCuttingPerMetre", 0))))},
    ]
    if app.app_type == "NEW_CONNECTION":
        deposit = fees.get("depositByCategory", {}).get(details["categoryCode"])
        if deposit is None:
            raise bad_request(f"No deposit is set for category {details['categoryCode']} in the fee table.")
        lines.append({"component": "DEPOSIT", "label": "Security deposit", "amount": money(deposit)})
    lines = [line for line in lines if line["amount"] > 0]
    total = money(sum((line["amount"] for line in lines), Decimal("0")))
    for line in lines:
        await post_ledger(db, ctx, tenant_id=ctx.tenant_id, connection_id=None, application_id=app.id,
                          txn_type="FEE", component=line["component"], bucket="FEE", amount=line["amount"],
                          ward_id=app.ward_id, reference_no=app.application_no, narration=line["label"])
    app.estimate_json = dumps([{**line, "amount": float(line["amount"])} for line in lines])
    app.estimate_total = total
    timeline(db, ctx, "application", app.id, "ESTIMATE_RAISED", f"Total ₹{total}")
    await notify(db, ctx.tenant_id, recipient=app.mobile_number, template="ESTIMATE", ref_no=app.application_no,
                 connection_id=app.connection_id,
                 message_en=f"GWMC Water: estimate for application {app.application_no} is Rs {total}. Please pay to proceed.",
                 message_te=f"జీడబ్ల్యూఎంసీ నీటి సరఫరా: దరఖాస్తు {app.application_no} అంచనా రూ. {total}. కొనసాగడానికి చెల్లించండి.")


async def _activate_connection(db: AsyncSession, ctx: WaterContext, app: WaterApplication) -> WaterConnection:
    details = loads(app.details_json, {})
    warnings = await find_duplicates(db, ctx.tenant_id, address=app.address, door_no=app.door_no,
                                     latitude=app.latitude, longitude=app.longitude)
    app.warnings_json = dumps(warnings)
    conn = WaterConnection(
        tenant_id=ctx.tenant_id, sub_tenant_id=app.sub_tenant_id,
        consumer_no=await new_consumer_no(db, ctx.tenant_id),
        consumer_name=app.applicant_name, mobile_number=app.mobile_number, email=app.email,
        aadhaar_hash=app.aadhaar_hash, aadhaar_last4=app.aadhaar_last4,
        door_no=app.door_no, address=app.address, locality=details.get("locality"), pincode=details.get("pincode"),
        old_assessment_no=details.get("oldAssessmentNo"), upin=details.get("upin"),
        upin_source="APPLICANT" if details.get("upin") else None,
        ward_id=app.ward_id, zone_id=details.get("zoneId"), supply_area=details.get("supplyArea"),
        latitude=app.latitude, longitude=app.longitude,
        location_pending=app.latitude is None or app.longitude is None,
        category_code=details["categoryCode"], pipe_size_mm=int(details["pipeSizeMm"]),
        is_metered=bool(details["isMetered"]), connection_date=today(), status="ACTIVE",
        application_id=app.id, source="APPLICATION", created_by=ctx.username,
    )
    db.add(conn)
    await db.flush()
    app.connection_id = conn.id

    # application charges stay on the application; the deposit is now held against the connection
    deposit_paid = Decimal("0.00")
    for row in (await db.execute(select(WaterLedger).where(
            WaterLedger.application_id == app.id, WaterLedger.component == "DEPOSIT",
            WaterLedger.txn_type == "PAYMENT"))).scalars().all():
        deposit_paid = money(deposit_paid - row.amount)
    if deposit_paid > 0:
        await post_ledger(db, ctx, tenant_id=ctx.tenant_id, connection_id=conn.id, application_id=app.id,
                          txn_type="DEPOSIT_HELD", component="DEPOSIT", bucket="DEPOSIT", amount=-deposit_paid,
                          ward_id=conn.ward_id, reference_no=app.application_no, narration="Security deposit held")

    meter_data = details.get("meter")
    if conn.is_metered and meter_data:
        db.add(WaterMeter(
            tenant_id=ctx.tenant_id, connection_id=conn.id, serial_no=meter_data["serialNo"], make=meter_data["make"],
            size_mm=int(meter_data["sizeMm"]), seal_no=meter_data.get("sealNo"),
            initial_reading=Decimal(str(meter_data.get("initialReading", 0))),
            fixed_on=datetime.date.fromisoformat(str(meter_data["fixedOn"])), status="ACTIVE", created_by=ctx.username,
        ))
        emit_event(db, ctx.tenant_id, "meter.fixed", conn.id, {"consumerNo": conn.consumer_no, "serialNo": meter_data["serialNo"],
                                                              "make": meter_data["make"], "sizeMm": meter_data["sizeMm"]})
    emit_event(db, ctx.tenant_id, "connection.created", conn.id, {
        "consumerNo": conn.consumer_no, "wardId": conn.ward_id, "category": conn.category_code,
        "upin": conn.upin, "latitude": conn.latitude, "longitude": conn.longitude,
    })
    audit(db, ctx, "CONNECTION_CREATED", "connection", conn.id, None,
          {"consumerNo": conn.consumer_no, "applicationNo": app.application_no})
    await notify(db, ctx.tenant_id, recipient=conn.mobile_number, template="CONNECTION_ACTIVATED", connection_id=conn.id,
                 ref_no=conn.consumer_no,
                 message_en=f"GWMC Water: your connection is active. Consumer number {conn.consumer_no}.",
                 message_te=f"జీడబ్ల్యూఎంసీ నీటి సరఫరా: మీ కనెక్షన్ ప్రారంభమైంది. వినియోగదారు సంఖ్య {conn.consumer_no}.")
    return conn


async def _apply_step(db: AsyncSession, ctx: WaterContext, app: WaterApplication, step: Dict, payload: ApplicationAction) -> None:
    details = loads(app.details_json, {})
    code = step["code"]
    conn = await db.get(WaterConnection, app.connection_id) if app.connection_id else None
    data = payload.data or {}

    if code == "SITE_INSPECTION":
        if data.get("feasible") is False:
            raise bad_request("Site marked not feasible: reject the application instead, giving the reason.")
        metres = data.get("roadCuttingMetres", 0) or 0
        try:
            metres = float(metres)
        except (TypeError, ValueError):
            raise bad_request("Road cutting length must be a number of metres.")
        if metres < 0:
            raise bad_request("Road cutting length cannot be negative.")
        details["roadCuttingMetres"] = metres
        details["inspection"] = {"remark": payload.remark, "photoRef": payload.photo_ref, "by": ctx.username,
                                 "latitude": payload.latitude, "longitude": payload.longitude}
        if app.app_type == "NEW_CONNECTION" and payload.latitude is not None and payload.longitude is not None:
            app.latitude, app.longitude = payload.latitude, payload.longitude
    elif code == "ESTIMATE_PAYMENT":
        bal = await balances(db, ctx.tenant_id, application_id=app.id)
        if dues_total(bal) > 0:
            raise bad_request(f"Estimate not fully paid yet: ₹{dues_total(bal)} outstanding.")
    elif code == "WORK_ORDER":
        if details.get("isMetered"):
            meter = data.get("meter") or {}
            required = [k for k in ("serialNo", "make", "sizeMm", "fixedOn") if not meter.get(k)]
            if required:
                raise bad_request("Meter details missing: " + ", ".join(required) + ".")
            exists = await db.scalar(select(WaterMeter.id).where(WaterMeter.tenant_id == ctx.tenant_id,
                                                                 WaterMeter.serial_no == str(meter["serialNo"]).strip()))
            if exists:
                raise conflict(f"Meter serial {meter['serialNo']} is already registered.")
            try:
                datetime.date.fromisoformat(str(meter["fixedOn"]))
                float(meter.get("initialReading", 0))
                int(meter["sizeMm"])
            except (TypeError, ValueError):
                raise bad_request("Meter fixed date must be YYYY-MM-DD, size and initial reading must be numbers.")
            meter["serialNo"] = str(meter["serialNo"]).strip()
            details["meter"] = meter
        details["workOrder"] = {"remark": payload.remark, "photoRef": payload.photo_ref, "by": ctx.username}
    elif code == "ACTIVATION":
        app.details_json = dumps(details)
        await _activate_connection(db, ctx, app)
        return
    elif code == "APPROVAL":
        if conn is None:
            raise bad_request("Connection missing for this request.")
        if app.app_type == "OWNER_CHANGE":
            old_owner = {"name": conn.consumer_name, "mobile": mask_mobile(conn.mobile_number)}
            reason = f"Owner change {app.application_no}: {payload.remark}"
            record_change(db, ctx, conn, "consumer_name", details["newOwnerName"], reason)
            record_change(db, ctx, conn, "mobile_number", details["newMobile"], reason)
            if details.get("newEmail"):
                record_change(db, ctx, conn, "email", details["newEmail"], reason)
            if app.aadhaar_hash:
                record_change(db, ctx, conn, "aadhaar_hash", app.aadhaar_hash, reason)
                record_change(db, ctx, conn, "aadhaar_last4", app.aadhaar_last4, reason)
            emit_event(db, ctx.tenant_id, "connection.owner_changed", conn.id,
                       {"consumerNo": conn.consumer_no, "applicationNo": app.application_no})
            audit(db, ctx, "OWNER_CHANGED", "connection", conn.id, old_owner, {"name": conn.consumer_name})
        elif app.app_type == "CATEGORY_CHANGE":
            await _validate_category(db, ctx.tenant_id, details["toCategory"])
            record_change(db, ctx, conn, "category_code", details["toCategory"], f"{app.application_no}: {payload.remark}")
            emit_event(db, ctx.tenant_id, "connection.changed", conn.id, {"consumerNo": conn.consumer_no, "fields": ["category_code"]})
        elif app.app_type == "PIPE_SIZE_CHANGE":
            record_change(db, ctx, conn, "pipe_size_mm", int(details["toPipeSizeMm"]), f"{app.application_no}: {payload.remark}")
            emit_event(db, ctx.tenant_id, "connection.changed", conn.id, {"consumerNo": conn.consumer_no, "fields": ["pipe_size_mm"]})
        elif app.app_type == "PERM_DISCONNECTION":
            bal = await balances(db, ctx.tenant_id, connection_id=conn.id)
            if dues_total(bal) > 0:
                raise bad_request(f"Dues of ₹{dues_total(bal)} must be cleared before permanent disconnection.")
    elif code == "FIELD_EXECUTION":
        if conn is None:
            raise bad_request("Connection missing for this request.")
        if not payload.photo_ref or payload.latitude is None or payload.longitude is None:
            raise bad_request("Field proof is required: photo, GPS location and time.")
        proof = {"photoRef": payload.photo_ref, "latitude": payload.latitude, "longitude": payload.longitude,
                 "at": _now().isoformat(), "by": ctx.username}
        details["fieldProof"] = proof
        reason = f"{app.application_no}: {payload.remark}"
        if app.app_type == "TEMP_DISCONNECTION":
            record_change(db, ctx, conn, "status", "TEMP_DISCONNECTED", reason)
            emit_event(db, ctx.tenant_id, "connection.disconnected", conn.id, {"consumerNo": conn.consumer_no, "kind": "TEMPORARY_ON_REQUEST"})
        elif app.app_type == "TEMP_RECONNECTION":
            record_change(db, ctx, conn, "status", "ACTIVE", reason)
            emit_event(db, ctx.tenant_id, "connection.reconnected", conn.id, {"consumerNo": conn.consumer_no, "kind": "AFTER_TEMPORARY"})
        elif app.app_type == "PERM_DISCONNECTION":
            bal = await balances(db, ctx.tenant_id, connection_id=conn.id)
            if dues_total(bal) > 0:
                raise bad_request(f"Dues of ₹{dues_total(bal)} must be cleared before permanent disconnection.")
            record_change(db, ctx, conn, "status", "CLOSED", reason)
            meter = await db.scalar(select(WaterMeter).where(WaterMeter.connection_id == conn.id, WaterMeter.status.in_(["ACTIVE", "FAULTY"])))
            if meter:
                final = data.get("finalReading")
                meter.status = "REMOVED"
                meter.removed_on = today()
                if final is not None:
                    meter.final_reading = Decimal(str(final))
            emit_event(db, ctx.tenant_id, "connection.disconnected", conn.id, {"consumerNo": conn.consumer_no, "kind": "PERMANENT"})
    app.details_json = dumps(details)


@router.post("/applications/{application_no}/actions")
async def act_on_application(application_no: str, payload: ApplicationAction, ctx: WaterContext = Depends(water_context),
                             db: AsyncSession = Depends(get_write_db)):
    app = await _load_app(db, ctx, application_no, for_update=True)
    if app.status != "IN_PROGRESS":
        raise bad_request(f"Application is already {app.status}.")
    steps = loads(app.steps_json, [])
    step = next((s for s in steps if s["status"] == "CURRENT"), None)
    if step is None:
        raise bad_request("Application has no open step.")
    allowed = set(step.get("roles", [])) | ADMIN
    if not (ctx.roles & allowed):
        raise bad_request(f"Step '{step['label']}' can only be completed by: {', '.join(sorted(step.get('roles', [])))}.")

    if payload.action == "REJECT":
        step["status"] = "REJECTED"
        step["doneAt"], step["doneBy"], step["remark"] = _now().isoformat(), ctx.username, payload.remark
        app.status = "REJECTED"
        app.current_step = None
        app.completed_at = _now()
        app.steps_json = dumps(steps)
        timeline(db, ctx, "application", app.id, "REJECTED", payload.remark)
        audit(db, ctx, "APPLICATION_REJECTED", "application", app.id, None, {"step": step["code"], "remark": payload.remark})
        await notify(db, ctx.tenant_id, recipient=app.mobile_number, template="APPLICATION_REJECTED", ref_no=app.application_no,
                     connection_id=app.connection_id,
                     message_en=f"GWMC Water: application {app.application_no} was rejected. Reason: {payload.remark}",
                     message_te=f"జీడబ్ల్యూఎంసీ నీటి సరఫరా: దరఖాస్తు {app.application_no} తిరస్కరించబడింది. కారణం: {payload.remark}")
        await db.commit()
        return {"message": "Application rejected", "applicationNo": app.application_no, "status": app.status}

    await _apply_step(db, ctx, app, step, payload)
    step["status"] = "DONE"
    step["doneAt"], step["doneBy"], step["remark"] = _now().isoformat(), ctx.username, payload.remark
    timeline(db, ctx, "application", app.id, f"STEP_DONE:{step['code']}", payload.remark)
    nxt = _activate_next(app, steps)
    if nxt and nxt["code"] == "ESTIMATE_PAYMENT" and app.estimate_total is None:
        await _post_estimate(db, ctx, app)
    if nxt is None:
        app.status = "COMPLETED"
        app.completed_at = _now()
        timeline(db, ctx, "application", app.id, "COMPLETED", None)
    app.steps_json = dumps(steps)
    audit(db, ctx, "APPLICATION_STEP", "application", app.id, None, {"step": step["code"], "remark": payload.remark})
    if nxt is not None:
        await notify(db, ctx.tenant_id, recipient=app.mobile_number, template="APPLICATION_PROGRESS", ref_no=app.application_no,
                     connection_id=app.connection_id,
                     message_en=f"GWMC Water: application {app.application_no} moved to '{nxt['label']}'.",
                     message_te=f"జీడబ్ల్యూఎంసీ నీటి సరఫరా: దరఖాస్తు {app.application_no} తదుపరి దశకు చేరింది: {nxt['label']}.")
    await db.commit()
    conn = await db.get(WaterConnection, app.connection_id) if app.connection_id else None
    return {"message": "Step completed", "applicationNo": app.application_no, "status": app.status,
            "currentStep": app.current_step, "consumerNo": conn.consumer_no if conn else None}


async def escalate_overdue_applications(db: AsyncSession, ctx: WaterContext) -> int:
    """Moves overdue steps up the escalation chain (WB-05). Called by the daily job."""
    chain = await get_setting(db, ctx.tenant_id, "complaint.escalation")
    now = _now()
    count = 0
    apps = (await db.execute(select(WaterApplication).where(
        WaterApplication.tenant_id == ctx.tenant_id, WaterApplication.status == "IN_PROGRESS"))).scalars().all()
    for app in apps:
        steps = loads(app.steps_json, [])
        step = next((s for s in steps if s["status"] == "CURRENT"), None)
        if not step or not step.get("dueAt"):
            continue
        due = datetime.datetime.fromisoformat(step["dueAt"])
        level_due = due + datetime.timedelta(hours=float(step.get("slaHours", 48)) * app.escalation_level)
        if now > level_due and app.escalation_level < len(chain):
            target = chain[app.escalation_level]
            app.escalation_level += 1
            step["escalatedTo"] = target
            app.steps_json = dumps(steps)
            timeline(db, ctx, "application", app.id, "ESCALATED", f"Step '{step['label']}' past SLA; escalated to {target}", actor="system")
            await notify(db, ctx.tenant_id, recipient=target, channel="EMAIL", template="SLA_ESCALATION", ref_no=app.application_no,
                         dedupe_key=f"app-esc:{app.id}:{app.escalation_level}",
                         message_en=f"Application {app.application_no} step '{step['label']}' is past its SLA.",
                         message_te=f"దరఖాస్తు {app.application_no} దశ '{step['label']}' గడువు దాటింది.")
            count += 1
    return count
