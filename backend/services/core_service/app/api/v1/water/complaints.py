"""Leak and service complaints, field-logged leaks and illegal connection cases (WB-50..WB-53)."""
import datetime
from typing import Dict, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.water_calc import mask_mobile, money
from app.db.models import Ward
from app.db.session import get_read_db, get_write_db
from app.db.water_models import WaterCategory, WaterComplaint, WaterConnection, WaterIllegalCase, WaterTimeline, utcnow
from app.schemas.water import ComplaintAction, ComplaintCreate, IllegalDecision, IllegalInspection, IllegalReport
from .common import (
    OFFICER, WaterAPIRoute, WaterContext, audit, bad_request, dumps, emit_event, get_setting, loads,
    new_consumer_no, new_doc_no, not_found, notify, post_ledger, timeline, today, ward_maps, water_context,
)

router = APIRouter(route_class=WaterAPIRoute)

IST = datetime.timedelta(hours=5, minutes=30)


def ist_text(utc_naive: datetime.datetime) -> str:
    """Messages to citizens state times in Indian Standard Time; the database keeps UTC."""
    return (utc_naive + IST).strftime("%d-%m-%Y %H:%M") + " IST"


COMPLAINT_TYPE_TE = {"LEAK": "లీకేజీ", "NO_SUPPLY": "నీటి సరఫరా లేదు", "DIRTY_WATER": "మురికి నీరు",
                     "METER": "మీటర్ సమస్య", "BILLING": "బిల్లు సమస్య", "OTHER": "ఇతర"}


def complaint_dict(c: WaterComplaint, wards: Dict, consumer_no: Optional[str] = None, public: bool = False) -> Dict:
    ward = wards.get(c.ward_id, {})
    now = utcnow()
    data = {
        "id": c.id, "complaintNo": c.complaint_no, "complaintType": c.complaint_type, "source": c.source,
        "consumerNo": consumer_no, "wardId": c.ward_id, "wardNumber": ward.get("wardNumber"), "wardName": ward.get("wardName"),
        "description": c.description, "address": c.address, "latitude": c.latitude, "longitude": c.longitude,
        "photoRef": c.photo_ref, "status": c.status, "slaDueAt": c.sla_due_at, "escalationLevel": c.escalation_level,
        "overdue": c.status != "CLOSED" and now > c.sla_due_at,
        "closedWithinSla": (c.closed_at <= c.sla_due_at) if c.closed_at else None,
        "closingPhotoRef": c.closing_photo_ref, "closingRemark": c.closing_remark, "closedAt": c.closed_at,
        "createdAt": c.created_at,
    }
    if not public:
        data.update({"complainantName": c.complainant_name, "complainantMobileMasked": mask_mobile(c.complainant_mobile),
                     "assignedTo": c.assigned_to, "closedBy": c.closed_by, "createdBy": c.created_by})
    return data


async def _assignee(db: AsyncSession, tenant_id: str, ward_number: Optional[int]) -> str:
    rule = await get_setting(db, tenant_id, "complaint.assignment")
    return (rule.get("byWardNumber") or {}).get(str(ward_number)) or rule.get("default") or "water.officer"


@router.post("/complaints", status_code=201)
async def raise_complaint(payload: ComplaintCreate, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_write_db)):
    """Complaint with photo and location, auto-assigned to the area's staff with an SLA (WB-50, WB-51, WB-52)."""
    ctx.require("complaint.create")
    conn = None
    if payload.consumer_no:
        conn = await db.scalar(select(WaterConnection).where(WaterConnection.tenant_id == ctx.tenant_id,
                                                             WaterConnection.consumer_no == payload.consumer_no.strip().upper()))
        if conn is None:
            raise not_found("Consumer number not found. Leave it blank if the complaint is not about a connection.")
    ward_id = conn.ward_id if conn else payload.ward_id
    if not ward_id:
        raise bad_request("Choose the ward where the problem is.")
    ward = await db.scalar(select(Ward).where(Ward.id == ward_id, Ward.tenant_id == ctx.tenant_id))
    if ward is None:
        raise bad_request("Ward not found.")
    if payload.complaint_type == "LEAK" and (payload.latitude is None or payload.longitude is None) and not conn:
        raise bad_request("Share the location of the leak (GPS) so the team can find it.")
    sla_hours = float((await get_setting(db, ctx.tenant_id, "complaint.slaHours")).get(payload.complaint_type, 72))
    assignee = await _assignee(db, ctx.tenant_id, ward.ward_number)
    complaint = WaterComplaint(
        tenant_id=ctx.tenant_id, complaint_no=await new_doc_no(db, ctx.tenant_id, "WCP", "complaint"),
        complaint_type=payload.complaint_type, source=payload.source, connection_id=conn.id if conn else None,
        ward_id=ward_id, complainant_name=payload.complainant_name or (conn.consumer_name if conn else None),
        complainant_mobile=payload.complainant_mobile or (conn.mobile_number if conn else None),
        description=payload.description, address=payload.address or (conn.address if conn else None),
        latitude=payload.latitude if payload.latitude is not None else (conn.latitude if conn else None),
        longitude=payload.longitude if payload.longitude is not None else (conn.longitude if conn else None),
        photo_ref=payload.photo_ref, assigned_to=assignee, status="OPEN",
        sla_due_at=utcnow() + datetime.timedelta(hours=sla_hours), created_by=ctx.username,
    )
    db.add(complaint)
    await db.flush()
    timeline(db, ctx, "complaint", complaint.id, "RAISED", f"{payload.complaint_type} via {payload.source}")
    timeline(db, ctx, "complaint", complaint.id, "ASSIGNED", f"Auto-assigned to {assignee}; SLA {sla_hours:g} h", actor="system")
    emit_event(db, ctx.tenant_id, "complaint.raised", complaint.id, {
        "complaintNo": complaint.complaint_no, "type": complaint.complaint_type, "wardId": ward_id,
        "consumerNo": conn.consumer_no if conn else None, "slaDueAt": complaint.sla_due_at.isoformat(),
    })
    audit(db, ctx, "COMPLAINT_RAISED", "complaint", complaint.id, None, {"complaintNo": complaint.complaint_no, "type": complaint.complaint_type})
    await notify(db, ctx.tenant_id, recipient=complaint.complainant_mobile, template="COMPLAINT_RAISED", ref_no=complaint.complaint_no,
                 connection_id=complaint.connection_id, dedupe_key=f"cmp:{complaint.id}:raised",
                 message_en=f"GWMC Water: complaint {complaint.complaint_no} registered. It will be attended by "
                            f"{ist_text(complaint.sla_due_at)}.",
                 message_te=f"జీడబ్ల్యూఎంసీ నీటి సరఫరా: ఫిర్యాదు {complaint.complaint_no} నమోదైంది "
                            f"({COMPLAINT_TYPE_TE[complaint.complaint_type]}). పరిష్కార గడువు {ist_text(complaint.sla_due_at)}.")
    await db.commit()
    wards, _ = await ward_maps(db, ctx.tenant_id)
    return complaint_dict(complaint, wards, conn.consumer_no if conn else None)


@router.get("/complaints")
async def list_complaints(status: Optional[str] = Query(None), complaint_type: Optional[str] = Query(None, alias="type"),
                          mine: bool = Query(False), overdue: bool = Query(False), q: Optional[str] = Query(None),
                          ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    if not ctx.can("reports.view"):
        ctx.require("complaint.work")
    stmt = select(WaterComplaint, WaterConnection.consumer_no).outerjoin(
        WaterConnection, WaterConnection.id == WaterComplaint.connection_id).where(
        WaterComplaint.tenant_id == ctx.tenant_id, ctx.ward_filter(WaterComplaint.ward_id))
    if status:
        stmt = stmt.where(WaterComplaint.status.in_([s.strip().upper() for s in status.split(",")]))
    if complaint_type:
        stmt = stmt.where(WaterComplaint.complaint_type == complaint_type.upper())
    if mine:
        stmt = stmt.where(WaterComplaint.assigned_to == ctx.username)
    if overdue:
        stmt = stmt.where(WaterComplaint.status != "CLOSED", WaterComplaint.sla_due_at < utcnow())
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(WaterComplaint.complaint_no.ilike(like), WaterComplaint.description.ilike(like),
                              WaterConnection.consumer_no.ilike(like)))
    rows = (await db.execute(stmt.order_by(WaterComplaint.created_at.desc()).limit(500))).all()
    wards, _ = await ward_maps(db, ctx.tenant_id)
    return [complaint_dict(c, wards, consumer_no) for c, consumer_no in rows]


async def _timeline_of(db: AsyncSession, entity_id: str):
    rows = (await db.execute(select(WaterTimeline).where(WaterTimeline.entity_id == entity_id).order_by(WaterTimeline.at))).scalars().all()
    return [{"action": r.action, "remark": r.remark, "actor": r.actor, "at": r.at} for r in rows]


@router.get("/complaints/{complaint_no}")
async def get_complaint(complaint_no: str, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("complaint.create")
    c = await db.scalar(select(WaterComplaint).where(WaterComplaint.tenant_id == ctx.tenant_id, WaterComplaint.complaint_no == complaint_no))
    if not c:
        raise not_found(f"Complaint {complaint_no} not found.")
    public = not (ctx.can("complaint.work") or ctx.can("reports.view"))
    if not public:
        ctx.ensure_scope(c.ward_id)
    conn = await db.get(WaterConnection, c.connection_id) if c.connection_id else None
    wards, _ = await ward_maps(db, ctx.tenant_id)
    data = complaint_dict(c, wards, conn.consumer_no if conn else None, public=public)
    data["timeline"] = await _timeline_of(db, c.id)
    return data


@router.post("/complaints/{complaint_no}/actions")
async def act_on_complaint(complaint_no: str, payload: ComplaintAction, ctx: WaterContext = Depends(water_context),
                           db: AsyncSession = Depends(get_write_db)):
    """Closing needs a closing photo and remark; the citizen is told at every step (WB-51)."""
    ctx.require("complaint.work")
    c = await db.scalar(select(WaterComplaint).where(WaterComplaint.tenant_id == ctx.tenant_id,
                                                     WaterComplaint.complaint_no == complaint_no).with_for_update())
    if not c:
        raise not_found(f"Complaint {complaint_no} not found.")
    ctx.ensure_scope(c.ward_id)
    if c.status == "CLOSED":
        raise bad_request("Complaint is already closed.")
    if payload.action == "START":
        c.status = "IN_PROGRESS"
        msg_en, msg_te = "work has started", "పని ప్రారంభమైంది"
    elif payload.action == "REASSIGN":
        if not (ctx.roles & (OFFICER | {"super_admin", "system_admin"})):
            raise bad_request("Only the water section officer can reassign a complaint.")
        if not payload.assign_to:
            raise bad_request("Choose who to assign the complaint to.")
        c.assigned_to = payload.assign_to
        msg_en, msg_te = "has been assigned to a new officer", "కొత్త అధికారికి అప్పగించబడింది"
    else:
        if not payload.photo_ref:
            raise bad_request("A closing photo is required to close the complaint.")
        c.status = "CLOSED"
        c.closing_photo_ref = payload.photo_ref
        c.closing_remark = payload.remark
        c.closed_at = utcnow()
        c.closed_by = ctx.username
        emit_event(db, ctx.tenant_id, "complaint.closed", c.id, {"complaintNo": c.complaint_no, "withinSla": c.closed_at <= c.sla_due_at})
        msg_en, msg_te = "is resolved and closed", "పరిష్కరించబడి మూసివేయబడింది"
    timeline(db, ctx, "complaint", c.id, payload.action, payload.remark)
    audit(db, ctx, f"COMPLAINT_{payload.action}", "complaint", c.id, None, payload.model_dump())
    await notify(db, ctx.tenant_id, recipient=c.complainant_mobile, template=f"COMPLAINT_{payload.action}", ref_no=c.complaint_no,
                 connection_id=c.connection_id,
                 message_en=f"GWMC Water: complaint {c.complaint_no} {msg_en}. {payload.remark}",
                 message_te=f"జీడబ్ల్యూఎంసీ నీటి సరఫరా: ఫిర్యాదు {c.complaint_no} {msg_te}. {payload.remark}")
    await db.commit()
    return {"message": f"Complaint {c.status.lower().replace('_', ' ')}", "complaintNo": c.complaint_no, "status": c.status}


async def escalate_complaints(db: AsyncSession, ctx: WaterContext) -> int:
    """Complaints past their SLA move up the escalation chain, one level per further SLA period (WB-51)."""
    chain = await get_setting(db, ctx.tenant_id, "complaint.escalation")
    sla_hours = await get_setting(db, ctx.tenant_id, "complaint.slaHours")
    now = utcnow()
    rows = (await db.execute(select(WaterComplaint).where(WaterComplaint.tenant_id == ctx.tenant_id,
                                                          WaterComplaint.status != "CLOSED", WaterComplaint.sla_due_at < now))).scalars().all()
    count = 0
    for c in rows:
        period = datetime.timedelta(hours=float(sla_hours.get(c.complaint_type, 72)))
        if c.escalation_level < len(chain) and now > c.sla_due_at + period * c.escalation_level:
            target = chain[c.escalation_level]
            c.escalation_level += 1
            timeline(db, ctx, "complaint", c.id, "ESCALATED", f"Past SLA; escalated to {target}", actor="system")
            await notify(db, ctx.tenant_id, recipient=target, channel="EMAIL", template="SLA_ESCALATION", ref_no=c.complaint_no,
                         dedupe_key=f"cmp-esc:{c.id}:{c.escalation_level}",
                         message_en=f"Complaint {c.complaint_no} ({c.complaint_type}) is past its SLA and escalated to you.",
                         message_te=f"ఫిర్యాదు {c.complaint_no} గడువు దాటింది, మీకు పంపబడింది.")
            count += 1
    return count


# ------------------------------------------------------------------------------------------------
# Illegal connections (WB-53)
# ------------------------------------------------------------------------------------------------

def case_dict(c: WaterIllegalCase, wards: Dict, consumer_no: Optional[str] = None) -> Dict:
    ward = wards.get(c.ward_id, {})
    return {
        "id": c.id, "caseNo": c.case_no, "source": c.source, "wardId": c.ward_id, "wardNumber": ward.get("wardNumber"),
        "wardName": ward.get("wardName"), "address": c.address, "description": c.description, "latitude": c.latitude,
        "longitude": c.longitude, "photoRef": c.photo_ref, "status": c.status, "inspection": loads(c.inspection_json, None),
        "penaltyAmount": float(c.penalty_amount) if c.penalty_amount is not None else None,
        "regularisedConsumerNo": consumer_no, "closureRemark": c.closure_remark, "reportedBy": c.reported_by,
        "createdAt": c.created_at, "closedAt": c.closed_at,
    }


@router.post("/illegal-cases", status_code=201)
async def report_illegal(payload: IllegalReport, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_write_db)):
    ctx.require("illegal.report")
    if payload.ward_id and not await db.scalar(select(Ward.id).where(Ward.id == payload.ward_id, Ward.tenant_id == ctx.tenant_id)):
        raise bad_request("Ward not found.")
    case = WaterIllegalCase(tenant_id=ctx.tenant_id, case_no=await new_doc_no(db, ctx.tenant_id, "WIC", "illegal"),
                            source=payload.source, ward_id=payload.ward_id, address=payload.address,
                            description=payload.description, latitude=payload.latitude, longitude=payload.longitude,
                            photo_ref=payload.photo_ref, status="REPORTED", reported_by=ctx.username)
    db.add(case)
    await db.flush()
    timeline(db, ctx, "illegal_case", case.id, "REPORTED", payload.description)
    emit_event(db, ctx.tenant_id, "illegal_case.opened", case.id, {"caseNo": case.case_no, "wardId": case.ward_id,
                                                                     "latitude": case.latitude, "longitude": case.longitude})
    audit(db, ctx, "ILLEGAL_CASE_REPORTED", "illegal_case", case.id, None, {"caseNo": case.case_no})
    await db.commit()
    wards, _ = await ward_maps(db, ctx.tenant_id)
    return case_dict(case, wards)


@router.get("/illegal-cases")
async def list_illegal(status: Optional[str] = Query(None), ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    if not ctx.can("reports.view"):
        ctx.require("illegal.process")
    stmt = select(WaterIllegalCase).where(WaterIllegalCase.tenant_id == ctx.tenant_id)
    if ctx.allowed_ward_ids is not None:
        stmt = stmt.where(ctx.ward_filter(WaterIllegalCase.ward_id))
    if status:
        stmt = stmt.where(WaterIllegalCase.status.in_([s.strip().upper() for s in status.split(",")]))
    rows = (await db.execute(stmt.order_by(WaterIllegalCase.created_at.desc()).limit(500))).scalars().all()
    wards, _ = await ward_maps(db, ctx.tenant_id)
    numbers = {}
    for c in rows:
        if c.connection_id:
            conn = await db.get(WaterConnection, c.connection_id)
            numbers[c.id] = conn.consumer_no if conn else None
    return [case_dict(c, wards, numbers.get(c.id)) for c in rows]


async def _load_case(db: AsyncSession, ctx: WaterContext, case_no: str) -> WaterIllegalCase:
    case = await db.scalar(select(WaterIllegalCase).where(WaterIllegalCase.tenant_id == ctx.tenant_id,
                                                          WaterIllegalCase.case_no == case_no).with_for_update())
    if not case:
        raise not_found(f"Case {case_no} not found.")
    if case.ward_id:
        ctx.ensure_scope(case.ward_id)
    return case


@router.get("/illegal-cases/{case_no}")
async def get_illegal(case_no: str, ctx: WaterContext = Depends(water_context), db: AsyncSession = Depends(get_read_db)):
    if not ctx.can("reports.view"):
        ctx.require("illegal.process")
    case = await db.scalar(select(WaterIllegalCase).where(WaterIllegalCase.tenant_id == ctx.tenant_id, WaterIllegalCase.case_no == case_no))
    if not case:
        raise not_found(f"Case {case_no} not found.")
    wards, _ = await ward_maps(db, ctx.tenant_id)
    conn = await db.get(WaterConnection, case.connection_id) if case.connection_id else None
    data = case_dict(case, wards, conn.consumer_no if conn else None)
    data["timeline"] = await _timeline_of(db, case.id)
    return data


@router.post("/illegal-cases/{case_no}/inspection")
async def inspect_illegal(case_no: str, payload: IllegalInspection, ctx: WaterContext = Depends(water_context),
                          db: AsyncSession = Depends(get_write_db)):
    ctx.require("illegal.process")
    case = await _load_case(db, ctx, case_no)
    if case.status != "REPORTED":
        raise bad_request(f"Case is {case.status}; it has already been inspected.")
    case.inspection_json = dumps({**payload.model_dump(mode="json", by_alias=True), "by": ctx.username, "at": utcnow().isoformat()})
    case.status = "INSPECTED"
    timeline(db, ctx, "illegal_case", case.id, "INSPECTED", ("Confirmed illegal: " if payload.confirmed_illegal else "Not illegal: ") + payload.findings)
    audit(db, ctx, "ILLEGAL_CASE_INSPECTED", "illegal_case", case.id, None, payload.model_dump(mode="json"))
    await db.commit()
    return {"message": "Inspection recorded", "caseNo": case.case_no, "status": case.status}


@router.post("/illegal-cases/{case_no}/decision")
async def decide_illegal(case_no: str, payload: IllegalDecision, ctx: WaterContext = Depends(water_context),
                         db: AsyncSession = Depends(get_write_db)):
    """After inspection, the case is regularised with penalty, disconnected, or closed (WB-53)."""
    ctx.require("illegal.process")
    case = await _load_case(db, ctx, case_no)
    if case.status != "INSPECTED":
        raise bad_request("Record the site inspection first.")
    inspection = loads(case.inspection_json, {})
    consumer_no = None
    if payload.decision == "CLOSE_NO_ISSUE":
        case.status = "CLOSED_NO_ISSUE"
    elif not inspection.get("confirmedIllegal"):
        raise bad_request("The inspection did not confirm an illegal connection; close the case with no issue instead.")
    elif payload.decision == "DISCONNECT":
        if not payload.photo_ref or payload.latitude is None or payload.longitude is None:
            raise bad_request("Field proof is required: photo and GPS location.")
        case.status = "DISCONNECTED"
        inspection["disconnection"] = {"photoRef": payload.photo_ref, "latitude": payload.latitude,
                                       "longitude": payload.longitude, "at": utcnow().isoformat(), "by": ctx.username}
        case.inspection_json = dumps(inspection)
    else:
        missing = [n for n, v in (("consumer name", payload.consumer_name), ("category", payload.category_code),
                                  ("pipe size", payload.pipe_size_mm), ("metered / non-metered", payload.is_metered),
                                  ("ward", case.ward_id)) if v in (None, "")]
        if missing:
            raise bad_request("Please fill in: " + ", ".join(missing) + ".")
        category = await db.scalar(select(WaterCategory).where(WaterCategory.tenant_id == ctx.tenant_id,
                                                               WaterCategory.code == payload.category_code.upper()))
        if not category:
            raise bad_request("Category not found.")
        penalties = await get_setting(db, ctx.tenant_id, "fees.regularisationPenalty")
        penalty = money(penalties.get(category.code, 0))
        ward = await db.get(Ward, case.ward_id)
        conn = WaterConnection(
            tenant_id=ctx.tenant_id, sub_tenant_id=ctx.sub_tenant_id, consumer_no=await new_consumer_no(db, ctx.tenant_id),
            consumer_name=payload.consumer_name, mobile_number=payload.mobile_number, door_no=payload.door_no,
            address=case.address or "Address to be confirmed", ward_id=case.ward_id, zone_id=ward.zone_id if ward else None,
            latitude=case.latitude, longitude=case.longitude, category_code=category.code, pipe_size_mm=payload.pipe_size_mm,
            is_metered=payload.is_metered, connection_date=today(), status="ACTIVE", source="REGULARISATION",
            created_by=ctx.username,
        )
        db.add(conn)
        await db.flush()
        if penalty > 0:
            await post_ledger(db, ctx, tenant_id=ctx.tenant_id, connection_id=conn.id, txn_type="FEE",
                              component="REGULARISATION_PENALTY", bucket="FEE", amount=penalty, ward_id=conn.ward_id,
                              reference_no=case.case_no, narration=f"Regularisation penalty, case {case.case_no}")
        case.connection_id = conn.id
        case.penalty_amount = penalty
        case.status = "REGULARISED"
        consumer_no = conn.consumer_no
        emit_event(db, ctx.tenant_id, "connection.created", conn.id, {"consumerNo": conn.consumer_no, "wardId": conn.ward_id,
                                                                       "category": conn.category_code, "source": "REGULARISATION"})
        await notify(db, ctx.tenant_id, recipient=conn.mobile_number, template="REGULARISED", connection_id=conn.id,
                     ref_no=conn.consumer_no,
                     message_en=f"GWMC Water: your connection is regularised as {conn.consumer_no}. Penalty Rs {penalty} is due.",
                     message_te=f"జీడబ్ల్యూఎంసీ నీటి సరఫరా: మీ కనెక్షన్ {conn.consumer_no}గా క్రమబద్ధీకరించబడింది. జరిమానా రూ. {penalty} చెల్లించాలి.")
    case.closure_remark = payload.remark
    case.closed_at = utcnow()
    timeline(db, ctx, "illegal_case", case.id, case.status, payload.remark)
    emit_event(db, ctx.tenant_id, "illegal_case.closed", case.id, {"caseNo": case.case_no, "outcome": case.status,
                                                                     "consumerNo": consumer_no})
    audit(db, ctx, "ILLEGAL_CASE_CLOSED", "illegal_case", case.id, None, {"outcome": case.status, "consumerNo": consumer_no})
    await db.commit()
    return {"message": f"Case {case.status.lower().replace('_', ' ')}", "caseNo": case.case_no, "status": case.status,
            "consumerNo": consumer_no}
