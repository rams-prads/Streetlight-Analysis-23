"""
Property tax complaints (PT-29): wrong area or owner, bill not received, wrong amount, payment not credited ... Each
category has a time limit; the owner is told by SMS at each step; complaints past their limit move up the escalation
chain. A complaint that needs a change to the register points to the right application (hint on the category), and the
application number can be recorded when it is resolved.
"""
import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.ptx_models import PtxComplaint, PtxParty, PtxProperty, PtxTimeline, utcnow
from app.db.session import get_read_db, get_write_db
from app.schemas.ptx import ComplaintAction, ComplaintIn
from .assess import codes
from .citizen import _digits, owned_property
from .common import (
    CITIZEN, PtxAPIRoute, PtxContext, audit, bad_request, conflict, get_setting, load_property, loads, new_doc_no, not_found, notify, page, paginate,
    ptx_context, timeline, ward_maps,
)

router = APIRouter(route_class=PtxAPIRoute)

STATUS_TEXT = {"OPEN": "Received", "IN_PROGRESS": "Being looked into", "RESOLVED": "Resolved"}


def _fmt(d) -> str:
    return d.strftime("%d-%m-%Y")


def plain_status(c: PtxComplaint) -> str:
    """One sentence an owner understands: where the complaint is and when to expect an answer."""
    if c.status == "RESOLVED":
        return f"Resolved. {c.resolution or ''}".strip()
    if c.status == "IN_PROGRESS":
        return f"A revenue officer is looking into it. You should hear back by {_fmt(c.due_at)}."
    return f"Received. A revenue officer will look into it, and you should hear back by {_fmt(c.due_at)}."


def complaint_dict(c: PtxComplaint, upin: Optional[str], ward: Optional[Dict], categories: Dict, public: bool = False) -> Dict:
    cat = categories.get(c.category)
    extra = loads(cat.extra_json, {}) if cat else {}
    return {"id": c.id, "complaintNo": c.complaint_no, "upin": upin, "wardNumber": (ward or {}).get("wardNumber"), "category": c.category,
            "categoryName": cat.name_en if cat else c.category, "categoryNameTe": cat.name_te if cat else c.category, "hint": extra.get("hint"),
            "description": c.description, "refNo": c.ref_no, "filedBy": "Owner" if public and c.filed_by == "citizen" else c.filed_by, "channel": c.channel,
            "status": c.status, "statusText": plain_status(c), "dueAt": c.due_at, "overdue": c.status != "RESOLVED" and c.due_at < utcnow(),
            "escalationLevel": c.escalation_level, "outcome": c.outcome, "resolution": c.resolution, "applicationNo": c.application_no,
            "resolvedBy": None if public else c.resolved_by, "resolvedAt": c.resolved_at, "createdAt": c.created_at}


async def _tell(db: AsyncSession, c: PtxComplaint, prop: PtxProperty, template: str, en: str, te: str, key: str) -> None:
    mobile = c.mobile_number or await db.scalar(select(PtxParty.mobile_number).where(
        PtxParty.property_id == prop.id, PtxParty.role == "OWNER", PtxParty.is_current.is_(True), PtxParty.mobile_number.isnot(None)).limit(1))
    await notify(db, c.tenant_id, recipient=mobile, template=template, property_id=prop.id, ref_no=c.complaint_no, dedupe_key=key,
                 message_en=f"GWMC Property Tax: {en}", message_te=f"జీడబ్ల్యూఎంసీ ఆస్తి పన్ను: {te}")


@router.post("/complaints", status_code=201)
async def file_complaint(payload: ComplaintIn, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """Staff record a complaint at the counter or by phone; owners file it themselves with the property number and registered mobile."""
    ctx.require("case.create")
    citizen = bool(ctx.roles) and ctx.roles <= CITIZEN
    prop = await owned_property(db, ctx, payload.upin, payload.mobile_number or "") if citizen else await load_property(db, ctx, upin=payload.upin)
    categories = await codes(db, ctx.tenant_id, "COMPLAINT_CATEGORY")
    cat = categories.get(payload.category)
    if cat is None:
        raise bad_request("Choose what the complaint is about.")
    if await db.scalar(select(PtxComplaint.complaint_no).where(PtxComplaint.property_id == prop.id, PtxComplaint.category == payload.category,
                                                                PtxComplaint.status != "RESOLVED")):
        raise conflict("There is already an open complaint of this kind for this property. Please wait for its reply, or add details to it by calling the ward office.")
    hours = int(loads(cat.extra_json, {}).get("slaHours") or (await get_setting(db, ctx.tenant_id, "complaints")).get("defaultSlaHours", 120))
    who = "citizen" if citizen else ctx.username
    c = PtxComplaint(tenant_id=ctx.tenant_id, complaint_no=await new_doc_no(db, ctx.tenant_id, "PCM", "complaint"), property_id=prop.id, ward_id=prop.ward_id,
                     category=payload.category, description=payload.description.strip(), ref_no=payload.ref_no, filed_by=who,
                     mobile_number=_digits(payload.mobile_number or "") or None, channel="PORTAL" if citizen else payload.channel,
                     due_at=utcnow() + datetime.timedelta(hours=hours))
    db.add(c)
    await db.flush()
    timeline(db, ctx, "complaint", c.id, "FILED", c.description, actor=who)
    audit(db, ctx, "COMPLAINT_FILED", "complaint", c.id, None, {"complaintNo": c.complaint_no, "upin": prop.upin, "category": c.category})
    await _tell(db, c, prop, "COMPLAINT_FILED", f"complaint {c.complaint_no} received. You will hear back by {_fmt(c.due_at)}.",
                f"ఫిర్యాదు {c.complaint_no} అందింది. {_fmt(c.due_at)} లోపు సమాధానం వస్తుంది.", f"complaint-filed:{c.id}")
    await db.commit()
    wards, _ = await ward_maps(db, ctx.tenant_id)
    return complaint_dict(c, prop.upin, wards.get(prop.ward_id), categories, public=citizen)


@router.get("/complaints")
async def list_complaints(search: Optional[str] = Query(None), status: Optional[str] = Query(None), category: Optional[str] = Query(None),
                          overdue: Optional[bool] = Query(None), skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                          ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("case.view")
    stmt = select(PtxComplaint, PtxProperty.upin).join(PtxProperty, PtxProperty.id == PtxComplaint.property_id).where(
        PtxComplaint.tenant_id == ctx.tenant_id, ctx.ward_filter(PtxComplaint.ward_id))
    if status and status.upper() == "UNRESOLVED":
        stmt = stmt.where(PtxComplaint.status != "RESOLVED")
    elif status:
        stmt = stmt.where(PtxComplaint.status == status.upper())
    if category:
        stmt = stmt.where(PtxComplaint.category == category.upper())
    if overdue:
        stmt = stmt.where(PtxComplaint.status != "RESOLVED", PtxComplaint.due_at < utcnow())
    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(PtxComplaint.complaint_no.ilike(like), PtxProperty.upin.ilike(like), PtxComplaint.description.ilike(like), PtxComplaint.ref_no.ilike(like)))
    rows, total = await paginate(db, stmt.order_by(PtxComplaint.due_at), skip, limit)
    wards, _ = await ward_maps(db, ctx.tenant_id)
    categories = await codes(db, ctx.tenant_id, "COMPLAINT_CATEGORY", active_only=False)
    return page([complaint_dict(c, upin, wards.get(c.ward_id), categories) for c, upin in rows], total, skip, limit)


async def _detail(db: AsyncSession, ctx: PtxContext, c: PtxComplaint, public: bool) -> Dict:
    prop = await db.get(PtxProperty, c.property_id)
    wards, _ = await ward_maps(db, ctx.tenant_id)
    data = complaint_dict(c, prop.upin, wards.get(prop.ward_id), await codes(db, ctx.tenant_id, "COMPLAINT_CATEGORY", active_only=False), public)
    events = (await db.execute(select(PtxTimeline).where(PtxTimeline.entity_id == c.id).order_by(PtxTimeline.at))).scalars().all()
    data["timeline"] = [{"action": e.action, "remark": e.remark, "actor": "GWMC staff" if public and e.actor != "citizen" else e.actor, "at": e.at} for e in events]
    return data


async def _load(db: AsyncSession, ctx: PtxContext, complaint_no: str, for_update: bool = False) -> PtxComplaint:
    stmt = select(PtxComplaint).where(PtxComplaint.tenant_id == ctx.tenant_id, PtxComplaint.complaint_no == complaint_no)
    c = await db.scalar(stmt.with_for_update() if for_update else stmt)
    if c is None:
        raise not_found(f"Complaint {complaint_no} not found.")
    return c


@router.get("/complaints/{complaint_no}")
async def get_complaint(complaint_no: str, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("case.view")
    c = await _load(db, ctx, complaint_no)
    ctx.ensure_scope(c.ward_id)
    return await _detail(db, ctx, c, False)


@router.get("/citizen/complaints/{complaint_no}")
async def track_complaint(complaint_no: str, mobile: str = Query(...), ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    """The owner follows a complaint with its number and the mobile used."""
    ctx.require("payment.online")
    c = await _load(db, ctx, complaint_no)
    digits = _digits(mobile)
    owner_ok = bool(await db.scalar(select(PtxParty.id).where(PtxParty.property_id == c.property_id, PtxParty.role == "OWNER", PtxParty.is_current.is_(True),
                                                              PtxParty.mobile_number == digits)))
    if not (c.mobile_number == digits or owner_ok):
        raise not_found("No complaint found with that number and mobile.")
    return await _detail(db, ctx, c, True)


@router.post("/complaints/{complaint_no}/actions")
async def act_on_complaint(complaint_no: str, payload: ComplaintAction, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    ctx.require("complaint.work")
    c = await _load(db, ctx, complaint_no, for_update=True)
    ctx.ensure_scope(c.ward_id)
    prop = await db.get(PtxProperty, c.property_id)
    if payload.action == "START":
        if c.status != "OPEN":
            raise conflict(f"This complaint is already {STATUS_TEXT[c.status].lower()}.")
        c.status = "IN_PROGRESS"
        await _tell(db, c, prop, "COMPLAINT_STARTED", f"complaint {c.complaint_no} is being looked into.", f"ఫిర్యాదు {c.complaint_no} పరిశీలనలో ఉంది.", f"complaint-start:{c.id}")
    elif payload.action == "RESOLVE":
        if c.status == "RESOLVED":
            raise conflict("This complaint is already resolved.")
        if payload.outcome is None:
            raise bad_request("Say whether action was taken or no change was needed.")
        if len(payload.remark.strip()) < 10:
            raise bad_request("Write the reply the owner will read (a sentence or two).")
        c.status, c.outcome, c.resolution = "RESOLVED", payload.outcome, payload.remark.strip()
        c.resolved_by, c.resolved_at, c.application_no = ctx.username, utcnow(), payload.application_no
        await _tell(db, c, prop, "COMPLAINT_RESOLVED", f"complaint {c.complaint_no} resolved: {c.resolution}", f"ఫిర్యాదు {c.complaint_no} పరిష్కరించబడింది.", f"complaint-done:{c.id}")
    else:  # REOPEN
        if c.status != "RESOLVED":
            raise conflict("Only a resolved complaint can be reopened.")
        c.status, c.outcome, c.resolution, c.resolved_by, c.resolved_at = "OPEN", None, None, None, None
        hours = int((await get_setting(db, ctx.tenant_id, "complaints")).get("defaultSlaHours", 120))
        c.due_at, c.escalation_level = utcnow() + datetime.timedelta(hours=hours), 0
    timeline(db, ctx, "complaint", c.id, payload.action, payload.remark)
    audit(db, ctx, f"COMPLAINT_{payload.action}", "complaint", c.id, None, {"remark": payload.remark, "outcome": payload.outcome})
    await db.commit()
    return {"message": f"Complaint {STATUS_TEXT[c.status].lower()}", "complaintNo": c.complaint_no, "status": c.status}


async def escalate_complaints(db: AsyncSession, tenant_id: str) -> int:
    """Complaints past their time limit move up the escalation chain, one level for each further limit missed."""
    chain: List[str] = await get_setting(db, tenant_id, "escalation")
    now, count = utcnow(), 0
    rows = (await db.execute(select(PtxComplaint).where(PtxComplaint.tenant_id == tenant_id, PtxComplaint.status != "RESOLVED"))).scalars().all()
    for c in rows:
        if now > c.due_at and c.escalation_level < len(chain):
            target = chain[c.escalation_level]
            c.escalation_level += 1
            timeline(db, tenant_id, "complaint", c.id, "ESCALATED", f"Past its time limit; escalated to {target}", actor="system")
            await notify(db, tenant_id, recipient=target, channel="EMAIL", template="COMPLAINT_ESCALATION", ref_no=c.complaint_no,
                         dedupe_key=f"complaint-esc:{c.id}:{c.escalation_level}", message_en=f"Complaint {c.complaint_no} is past its time limit.",
                         message_te=f"ఫిర్యాదు {c.complaint_no} గడువు దాటింది.")
            count += 1
    return count
