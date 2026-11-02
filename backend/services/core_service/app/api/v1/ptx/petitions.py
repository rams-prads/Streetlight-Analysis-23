"""
Revision petition and appeal (PT-24). The first remedy is the objection to the assessment notice, decided by the Revenue
Officer. After the assessment is final the owner can ask the Commissioner to revise it (revision petition) and, if that is
refused, appeal to the appellate authority, each within the number of days GWMC has set. An order that corrects the
assessment becomes a new final assessment from the same date, and bills already raised are revised.
"""
import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.ptx_models import PtxApplication, PtxParty, PtxPetition, PtxProperty, utcnow
from app.db.session import get_read_db, get_write_db
from app.schemas.ptx import PetitionDecision, PetitionIn, ReasonIn
from .assess import apply_details, calculate, current_floors, new_assessment, property_details, raise_missing_demands, revise_raised_demands, set_floors, validate_details
from .cases import ASSESSMENT_KIND, _fmt, _tell, load_case
from .common import (
    CITIZEN, PtxAPIRoute, PtxContext, audit, bad_request, conflict, emit_event, get_setting, local_date, new_doc_no, not_found, page,
    paginate, ptx_context, timeline, today, ward_maps,
)

router = APIRouter(route_class=PtxAPIRoute)

LEVEL_NAME = {"REVISION_PETITION": "Revision petition", "APPEAL": "Appeal"}


def petition_dict(p: PtxPetition, upin: Optional[str] = None, application_no: Optional[str] = None, ward: Optional[Dict] = None, public: bool = False) -> Dict:
    return {"id": p.id, "petitionNo": p.petition_no, "applicationNo": application_no, "upin": upin, "wardNumber": (ward or {}).get("wardNumber"),
            "level": p.level, "levelName": LEVEL_NAME[p.level], "grounds": p.grounds, "filedBy": "Owner" if public else p.filed_by, "filedAt": p.filed_at,
            "status": p.status, "orderReference": p.order_reference, "decision": p.decision, "decidedBy": None if public else p.decided_by,
            "decidedAt": p.decided_at, "newAssessmentNo": p.new_assessment_no}


async def petition_options(db: AsyncSession, tenant_id: str, app: PtxApplication, rows: List[PtxPetition]) -> Dict:
    """What the owner may file now, and until when, in plain words."""
    if app.status != "COMPLETED" or app.app_type not in ASSESSMENT_KIND or not app.property_id:
        return {"canFile": None, "until": None, "message": None}
    rule = await get_setting(db, tenant_id, "assessment")
    live = [p for p in rows if p.status != "WITHDRAWN"]
    if any(p.status == "FILED" for p in live):
        return {"canFile": None, "until": None, "message": "A petition is being considered. You will be told the decision by SMS."}
    revisions = [p for p in live if p.level == "REVISION_PETITION"]
    appeals = [p for p in live if p.level == "APPEAL"]
    if not revisions:
        until = local_date(app.completed_at) + datetime.timedelta(days=int(rule.get("petitionDays", 30)))
        if today() <= until:
            return {"canFile": "REVISION_PETITION", "until": until,
                    "message": f"If you still disagree with the tax, you can ask the Commissioner to revise it, until {_fmt(until)}."}
        return {"canFile": None, "until": None, "message": f"The time to file a revision petition ended on {_fmt(until)}."}
    last = revisions[-1]
    if last.status in ("REJECTED", "PARTLY_ALLOWED") and not appeals:
        until = local_date(last.decided_at) + datetime.timedelta(days=int(rule.get("appealDays", 60)))
        if today() <= until:
            return {"canFile": "APPEAL", "until": until, "message": f"You can appeal to the appellate authority until {_fmt(until)}."}
        return {"canFile": None, "until": None, "message": f"The time to appeal ended on {_fmt(until)}."}
    return {"canFile": None, "until": None, "message": None}


async def petitions_for_case(db: AsyncSession, ctx: PtxContext, app: PtxApplication, public: bool = False) -> Dict:
    rows = (await db.execute(select(PtxPetition).where(PtxPetition.application_id == app.id).order_by(PtxPetition.filed_at))).scalars().all()
    return {"petitions": [petition_dict(p, None, app.application_no, None, public) for p in rows],
            "petitionOptions": await petition_options(db, ctx.tenant_id, app, list(rows))}


def _digits(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())[-10:]


async def _file(db: AsyncSession, ctx: PtxContext, application_no: str, payload: PetitionIn) -> Dict:
    ctx.require("case.create")
    app = await load_case(db, ctx, application_no, for_update=True)
    ctx.ensure_scope(app.ward_id)
    citizen = bool(ctx.roles) and ctx.roles <= CITIZEN
    if citizen:
        mobile = _digits(payload.mobile_number or "")
        owner_ok = bool(app.property_id and await db.scalar(select(PtxParty.id).where(
            PtxParty.property_id == app.property_id, PtxParty.role == "OWNER", PtxParty.mobile_number == mobile)))
        if not (app.mobile_number == mobile or owner_ok):
            raise not_found("No application found with that number and mobile.")
    rows = list((await db.execute(select(PtxPetition).where(PtxPetition.application_id == app.id).order_by(PtxPetition.filed_at))).scalars().all())
    options = await petition_options(db, ctx.tenant_id, app, rows)
    if options["canFile"] != payload.level:
        raise bad_request(options["message"] or f"A {LEVEL_NAME[payload.level].lower()} cannot be filed on this application now.")
    who = "citizen" if citizen else ctx.username
    p = PtxPetition(tenant_id=ctx.tenant_id, petition_no=await new_doc_no(db, ctx.tenant_id, "PPT", "petition"), application_id=app.id,
                    property_id=app.property_id, ward_id=app.ward_id, level=payload.level, grounds=payload.grounds.strip(), filed_by=who)
    db.add(p)
    await db.flush()
    timeline(db, ctx, "case", app.id, f"{payload.level}_FILED", payload.grounds.strip(), actor=who)
    audit(db, ctx, f"{payload.level}_FILED", "petition", p.id, None, {"petitionNo": p.petition_no, "applicationNo": app.application_no})
    await _tell(db, app, "PETITION_FILED", f"your {LEVEL_NAME[payload.level].lower()} {p.petition_no} on {app.application_no} was received.",
                f"{app.application_no} పై మీ {p.petition_no} అందింది.")
    await db.commit()
    return {"message": f"{LEVEL_NAME[payload.level]} received", "petitionNo": p.petition_no}


@router.post("/cases/{application_no}/petitions", status_code=201)
async def file_petition(application_no: str, payload: PetitionIn, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """Filed at a counter on the owner's behalf, or by the owner with the application number and registered mobile."""
    return await _file(db, ctx, application_no, payload)


@router.post("/citizen/cases/{application_no}/petition", status_code=201)
async def citizen_petition(application_no: str, payload: PetitionIn, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    ctx.require("payment.online")
    return await _file(db, ctx, application_no, payload)


@router.get("/petitions")
async def list_petitions(search: Optional[str] = Query(None), status: Optional[str] = Query(None), level: Optional[str] = Query(None),
                         skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                         ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("case.view")
    stmt = select(PtxPetition, PtxProperty.upin, PtxApplication.application_no).join(PtxProperty, PtxProperty.id == PtxPetition.property_id).join(
        PtxApplication, PtxApplication.id == PtxPetition.application_id).where(PtxPetition.tenant_id == ctx.tenant_id, ctx.ward_filter(PtxPetition.ward_id))
    if status:
        stmt = stmt.where(PtxPetition.status == status.upper())
    if level:
        stmt = stmt.where(PtxPetition.level == level.upper())
    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(PtxPetition.petition_no.ilike(like), PtxProperty.upin.ilike(like), PtxApplication.application_no.ilike(like), PtxPetition.grounds.ilike(like)))
    rows, total = await paginate(db, stmt.order_by(PtxPetition.filed_at.desc()), skip, limit)
    wards, _ = await ward_maps(db, ctx.tenant_id)
    return page([petition_dict(p, upin, no, wards.get(p.ward_id)) for p, upin, no in rows], total, skip, limit)


async def _apply_correction(db: AsyncSession, ctx: PtxContext, app: PtxApplication, p: PtxPetition, payload: PetitionDecision) -> str:
    """The order corrects the assessment: new final assessment from the same date, register updated, earlier bills revised."""
    prop = await db.get(PtxProperty, app.property_id)
    if prop.status != "ACTIVE":
        raise bad_request(f"{prop.upin} is {prop.status.lower()}; the correction must be made on its current number.")
    changes = payload.property.model_dump(by_alias=True, exclude_unset=True) if payload.property else {}
    changes.pop("wardId", None)
    merged = {**property_details(prop), **changes}
    floors = [f.model_dump(by_alias=True) for f in payload.floors] if payload.floors else (await current_floors(db, prop.id) if prop.property_type != "VACANT_LAND" else [])
    await validate_details(db, ctx, merged, floors)
    start = app.effective_from
    reason = f"{LEVEL_NAME[p.level]} {p.petition_no}"
    calc = await calculate(db, ctx.tenant_id, merged, floors, start)
    await apply_details(db, ctx.username, prop, {k: v for k, v in merged.items() if k != "wardId"}, reason)
    if prop.property_type != "VACANT_LAND":
        await set_floors(db, ctx.username, prop, floors, start, reason)
    a = await new_assessment(db, ctx.username, prop, p.level, calc, start, "FINAL", app.id)
    await revise_raised_demands(db, ctx, prop, start, reason)
    await db.flush()
    await raise_missing_demands(db, ctx, prop)
    emit_event(db, ctx.tenant_id, "assessment.approved", prop.id, {"upin": prop.upin, "assessmentNo": a.assessment_no, "kind": p.level,
                                                                  "annualTax": float(a.annual_tax), "effectiveFrom": start.isoformat()})
    emit_event(db, ctx.tenant_id, "property.changed", prop.id, {"upin": prop.upin, "fields": ["floors", "assessment"]})
    return a.assessment_no


@router.post("/petitions/{petition_no}/decide")
async def decide_petition(petition_no: str, payload: PetitionDecision, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """The Commissioner decides a revision petition; the order of the appellate authority is recorded for an appeal."""
    ctx.require("petition.decide")
    p = await db.scalar(select(PtxPetition).where(PtxPetition.tenant_id == ctx.tenant_id, PtxPetition.petition_no == petition_no).with_for_update())
    if p is None:
        raise not_found(f"Petition {petition_no} not found.")
    if p.status != "FILED":
        raise conflict(f"This {LEVEL_NAME[p.level].lower()} is already {p.status.replace('_', ' ').lower()}.")
    app = await db.get(PtxApplication, p.application_id)
    ctx.ensure_scope(app.ward_id)
    if p.level == "APPEAL" and not (payload.order_reference or "").strip():
        raise bad_request("Enter the order number of the appellate authority.")
    if payload.outcome != "REJECT":
        if not (payload.property or payload.floors):
            raise bad_request("Give the corrected details (area, floors or use); the tax is worked out again from them.")
        p.new_assessment_no = await _apply_correction(db, ctx, app, p, payload)
    p.status = {"ALLOW": "ALLOWED", "PARTLY_ALLOW": "PARTLY_ALLOWED", "REJECT": "REJECTED"}[payload.outcome]
    p.decision, p.decided_by, p.decided_at, p.order_reference = payload.remark, ctx.username, utcnow(), payload.order_reference
    timeline(db, ctx, "case", app.id, f"{p.level}_{p.status}", payload.remark)
    audit(db, ctx, f"{p.level}_DECIDED", "petition", p.id, {"status": "FILED"}, {"status": p.status, "remark": payload.remark, "assessment": p.new_assessment_no})
    await _tell(db, app, "PETITION_DECIDED", f"{p.petition_no} is {p.status.replace('_', ' ').lower()}. {payload.remark}",
                f"{p.petition_no}: {p.status.replace('_', ' ').lower()}.")
    await db.commit()
    return {"message": f"{LEVEL_NAME[p.level]} {p.status.replace('_', ' ').lower()}", "petitionNo": p.petition_no, "status": p.status, "assessmentNo": p.new_assessment_no}


@router.post("/petitions/{petition_no}/withdraw")
async def withdraw_petition(petition_no: str, payload: ReasonIn, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """Staff record a withdrawal asked for by the owner."""
    ctx.require("petition.decide")
    p = await db.scalar(select(PtxPetition).where(PtxPetition.tenant_id == ctx.tenant_id, PtxPetition.petition_no == petition_no).with_for_update())
    if p is None:
        raise not_found(f"Petition {petition_no} not found.")
    if p.status != "FILED":
        raise conflict(f"This petition is already {p.status.replace('_', ' ').lower()}.")
    p.status, p.decision, p.decided_by, p.decided_at = "WITHDRAWN", payload.reason, ctx.username, utcnow()
    timeline(db, ctx, "case", p.application_id, f"{p.level}_WITHDRAWN", payload.reason)
    audit(db, ctx, f"{p.level}_WITHDRAWN", "petition", p.id, {"status": "FILED"}, {"status": "WITHDRAWN", "reason": payload.reason})
    await db.commit()
    return {"message": "Withdrawn", "petitionNo": p.petition_no}
