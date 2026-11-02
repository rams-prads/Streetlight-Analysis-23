"""
Field app support (PT-06, PT-43, SRS 3.1.1): a ward sheet downloaded before going offline, survey / verification
records synced later with GPS and photos, and notice service recorded in the field. Every sync is idempotent, so data
re-sent by a device is stored once (PT-NF-33).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ptx_calc import period_for_date
from app.db.ptx_models import PtxDemand, PtxFootprint, PtxNotice, PtxParty, PtxProperty, PtxSurvey, utcnow
from app.db.session import get_read_db, get_write_db
from app.schemas.ptx import ApplicationCreate, FloorIn, NoticeServiceBatch, PropertyDetailsIn, PartyIn, SurveyBatch, SurveyDecision
from .arrears import record_service
from .assess import current_floors
from .cases import file_case
from .common import (
    PtxAPIRoute, PtxContext, audit, bad_request, dumps, get_setting, loads, not_found, page, paginate, ptx_context, timeline, to_utc_naive, today, ward_maps,
)

router = APIRouter(route_class=PtxAPIRoute)


@router.get("/field/sheet")
async def ward_sheet(ward_id: str = Query(..., alias="wardId"), ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    """Everything a field officer needs offline for one ward: properties, buildings to verify and notices to serve."""
    ctx.require("survey.capture")
    ctx.ensure_scope(ward_id)
    props = (await db.execute(select(PtxProperty).where(PtxProperty.tenant_id == ctx.tenant_id, PtxProperty.ward_id == ward_id,
                                                        PtxProperty.status == "ACTIVE").order_by(PtxProperty.door_no, PtxProperty.upin))).scalars().all()
    owners = {}
    for p in (await db.execute(select(PtxParty).where(PtxParty.property_id.in_([x.id for x in props] or ["__none__"]), PtxParty.role == "OWNER",
                                                      PtxParty.is_current.is_(True)))).scalars().all():
        owners.setdefault(p.property_id, []).append(p.full_name)
    fps = (await db.execute(select(PtxFootprint).where(PtxFootprint.tenant_id == ctx.tenant_id, PtxFootprint.ward_id == ward_id,
                                                       PtxFootprint.property_id.is_(None),
                                                       PtxFootprint.verification_status.in_(["NONE", "SENT_FOR_VERIFICATION"])))).scalars().all()
    notices = (await db.execute(select(PtxNotice, PtxProperty.upin, PtxProperty.address).join(PtxProperty, PtxProperty.id == PtxNotice.property_id).where(
        PtxNotice.tenant_id == ctx.tenant_id, PtxNotice.ward_id == ward_id, PtxNotice.service_status == "PENDING").order_by(PtxNotice.issued_at))).all()
    period = period_for_date(today(), await get_setting(db, ctx.tenant_id, "demand.frequency"))
    bills = (await db.execute(select(PtxDemand, PtxProperty.upin, PtxProperty.address, PtxProperty.door_no).join(PtxProperty, PtxProperty.id == PtxDemand.property_id).where(
        PtxDemand.tenant_id == ctx.tenant_id, PtxDemand.ward_id == ward_id, PtxDemand.period == period, PtxDemand.delivery_status == "PENDING")
        .order_by(PtxProperty.door_no, PtxProperty.upin).limit(500))).all()
    wards, _ = await ward_maps(db, ctx.tenant_id)
    return {
        "billsToDeliver": [{"demandNo": d.demand_no, "upin": upin, "doorNo": door, "address": address, "amount": float(d.amount), "dueDate": d.due_date.isoformat(),
                            "ownerNames": ", ".join(owners.get(d.property_id, []))} for d, upin, address, door in bills],
        "ward": wards.get(ward_id), "downloadedAt": utcnow(),
        "properties": [{"upin": p.upin, "doorNo": p.door_no, "address": p.address, "latitude": p.latitude, "longitude": p.longitude,
                        "ownerNames": ", ".join(owners.get(p.id, [])), "siteAreaSqyd": float(p.site_area_sqyd or 0),
                        "floors": await current_floors(db, p.id), "propertyType": p.property_type} for p in props],
        "buildingsToVerify": [{"footprintId": f.id, "ref": f.footprint_ref, "latitude": f.latitude, "longitude": f.longitude,
                               "mapBuiltupSqft": float(f.map_builtup_sqft), "status": f.verification_status} for f in fps],
        "noticesToServe": [{"noticeNo": n.notice_no, "noticeType": n.notice_type, "upin": upin, "address": address, "amount": float(n.amount or 0)}
                           for n, upin, address in notices],
    }


@router.post("/field/surveys")
async def sync_surveys(payload: SurveyBatch, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """Survey / verification records from the field app (PT-06). Each row is checked on its own; repeats are ignored."""
    ctx.require("survey.capture")
    results = []
    for s in payload.surveys:
        if await db.scalar(select(PtxSurvey.id).where(PtxSurvey.tenant_id == ctx.tenant_id, PtxSurvey.client_ref == s.client_ref)):
            results.append({"clientRef": s.client_ref, "result": "DUPLICATE_IGNORED"})
            continue
        prop = fp = None
        if s.upin:
            prop = await db.scalar(select(PtxProperty).where(PtxProperty.tenant_id == ctx.tenant_id, PtxProperty.upin == s.upin.strip().upper()))
        if s.footprint_id:
            fp = await db.get(PtxFootprint, s.footprint_id)
        ward_id = prop.ward_id if prop else (fp.ward_id if fp else s.ward_id)
        error = None
        if s.survey_type == "VERIFY" and prop is None:
            error = "Property number not found."
        elif s.survey_type == "NEW_BUILDING" and not (fp or ward_id):
            error = "Pick the building on the map or the ward."
        elif s.latitude is None or s.longitude is None:
            error = "GPS location is required. Turn on location and save again."
        elif not s.photo_refs:
            error = "Add at least one photo of the property."
        elif ward_id and not ctx.in_scope(ward_id):
            error = "This property is outside your assigned area."
        if error:
            results.append({"clientRef": s.client_ref, "result": "ERROR", "error": error})
            continue
        row = PtxSurvey(tenant_id=ctx.tenant_id, client_ref=s.client_ref, property_id=prop.id if prop else None, footprint_id=fp.id if fp else None,
                        ward_id=ward_id, survey_type=s.survey_type,
                        data_json=dumps({"floors": [f.model_dump(by_alias=True) for f in s.floors], "siteAreaSqyd": s.site_area_sqyd,
                                         "remarks": s.remarks, "occupantName": s.occupant_name, "address": s.address, "doorNo": s.door_no}),
                        photos_json=dumps(s.photo_refs), latitude=s.latitude, longitude=s.longitude,
                        captured_at=to_utc_naive(s.captured_at) if s.captured_at else utcnow(), captured_by=ctx.username)
        db.add(row)
        await db.flush()
        audit(db, ctx, "SURVEY_SYNCED", "survey", row.id, None, {"type": s.survey_type, "upin": s.upin, "footprint": s.footprint_id})
        results.append({"clientRef": s.client_ref, "result": "STORED", "surveyId": row.id})
    await db.commit()
    return {"stored": sum(1 for r in results if r["result"] == "STORED"), "duplicates": sum(1 for r in results if r["result"] == "DUPLICATE_IGNORED"),
            "errors": sum(1 for r in results if r["result"] == "ERROR"), "results": results}


@router.post("/field/notice-service")
async def sync_notice_service(payload: NoticeServiceBatch, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """Notice service recorded offline and synced later (PT-43)."""
    ctx.require("notice.serve")
    results = []
    for item in payload.items:
        try:
            results.append(await record_service(db, ctx, item.notice_no, item))
        except HTTPException as exc:
            results.append({"noticeNo": item.notice_no, "result": "ERROR", "error": exc.detail})
    await db.commit()
    return {"recorded": sum(1 for r in results if r["result"] in ("RECORDED", "ALREADY_RECORDED")),
            "errors": sum(1 for r in results if r["result"] == "ERROR"), "results": results}


@router.get("/surveys")
async def list_surveys(search: Optional[str] = Query(None), status: Optional[str] = Query("SUBMITTED"), skip: int = Query(0, ge=0),
                       limit: int = Query(50, ge=1, le=100), ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    ctx.require("survey.review")
    stmt = select(PtxSurvey, PtxProperty.upin).outerjoin(PtxProperty, PtxProperty.id == PtxSurvey.property_id).where(
        PtxSurvey.tenant_id == ctx.tenant_id, ctx.ward_filter(PtxSurvey.ward_id))
    if status:
        stmt = stmt.where(PtxSurvey.status == status.upper())
    if search and search.strip():
        like = f"%{search.strip()}%"
        stmt = stmt.where(or_(PtxProperty.upin.ilike(like), PtxSurvey.captured_by.ilike(like), PtxSurvey.data_json.ilike(like)))
    rows, total = await paginate(db, stmt.order_by(PtxSurvey.captured_at.desc()), skip, limit)
    wards, _ = await ward_maps(db, ctx.tenant_id)
    items = []
    for s, upin in rows:
        recorded = await current_floors(db, s.property_id) if s.property_id else []
        items.append({"id": s.id, "surveyType": s.survey_type, "upin": upin, "footprintId": s.footprint_id,
                      "wardNumber": wards.get(s.ward_id, {}).get("wardNumber"), "data": loads(s.data_json, {}), "photos": loads(s.photos_json, []),
                      "recordedFloors": recorded, "latitude": s.latitude, "longitude": s.longitude, "capturedAt": s.captured_at,
                      "capturedBy": s.captured_by, "status": s.status, "outcome": s.outcome})
    return page(items, total, skip, limit)


@router.post("/surveys/{survey_id}/decision")
async def decide_survey(survey_id: str, payload: SurveyDecision, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """The officer reviews a survey: it matches the record, or a case is opened with the surveyed details (PT-06, PT-50)."""
    ctx.require("survey.review")
    s = await db.scalar(select(PtxSurvey).where(PtxSurvey.id == survey_id, PtxSurvey.tenant_id == ctx.tenant_id).with_for_update())
    if s is None:
        raise not_found("Survey not found.")
    ctx.ensure_scope(s.ward_id)
    if s.status != "SUBMITTED":
        raise bad_request("This survey has already been reviewed.")
    data = loads(s.data_json, {})
    outcome_no = None
    if payload.outcome == "OPEN_CASE":
        floors = [FloorIn.model_validate(f) for f in data.get("floors", [])]
        if s.survey_type == "VERIFY":
            prop = await db.get(PtxProperty, s.property_id)
            request = ApplicationCreate(app_type="REASSESSMENT", channel="FIELD", upin=prop.upin, consent=True, floors=floors,
                                        property=PropertyDetailsIn(site_area_sqyd=data.get("siteAreaSqyd")) if data.get("siteAreaSqyd") else None,
                                        reason=f"Field survey: {payload.remark}", documents=loads(s.photos_json, []))
        else:
            if not data.get("occupantName") or not data.get("address"):
                raise bad_request("The survey has no occupant name or address; ask the field officer to resurvey.")
            request = ApplicationCreate(app_type="NEW_ASSESSMENT", channel="FIELD", consent=True, floors=floors,
                                        property=PropertyDetailsIn(ward_id=s.ward_id, address=data["address"], door_no=data.get("doorNo"),
                                                                   latitude=s.latitude, longitude=s.longitude, footprint_id=s.footprint_id,
                                                                   site_area_sqyd=data.get("siteAreaSqyd")),
                                        owners=[PartyIn(full_name=data["occupantName"])], applicant_name=data["occupantName"],
                                        reason=f"Unassessed building found in field survey: {payload.remark}", documents=loads(s.photos_json, []))
        result = await file_case(request, ctx, db)  # commits the case
        outcome_no = result["applicationNo"]
        s = await db.get(PtxSurvey, survey_id)
        s.status, s.outcome = "CASE_OPENED", f"Case {outcome_no}: {payload.remark}"
    else:
        s.status = "MATCHES_RECORD" if payload.outcome == "MATCHES_RECORD" else "CLOSED"
        s.outcome = payload.remark
        if s.footprint_id and payload.outcome == "CLOSE":
            fp = await db.get(PtxFootprint, s.footprint_id)
            if fp is not None and not fp.property_id:
                fp.verification_status = "NOT_A_BUILDING"
    timeline(db, ctx, "survey", s.id, s.status, payload.remark)
    audit(db, ctx, "SURVEY_DECIDED", "survey", s.id, None, {"outcome": payload.outcome, "case": outcome_no})
    await db.commit()
    return {"message": "Survey reviewed", "status": s.status, "applicationNo": outcome_no}
