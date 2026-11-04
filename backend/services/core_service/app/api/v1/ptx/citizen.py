"""
Citizen self-service, designed for ease of use (SRS 3.1.1): find your property and pay in three steps, see what you owe
in plain words, download receipts, bills and a no-dues certificate (PT-47), and track or object to your cases.
A citizen proves the property is theirs with the property number (or old assessment number) and the owner's
registered mobile; mobile OTP sign-in itself is a platform service (PT-NF-11). No other person's mobile or identity
details are ever shown (PT-NF-22).
"""
import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ptx_calc import document_code, period_label
from app.db.ptx_models import PtxApplication, PtxCertificate, PtxCitizenLink, PtxComplaint, PtxDemand, PtxParty, PtxProperty, PtxReceipt
from app.db.session import get_read_db, get_write_db
from app.schemas.ptx import CertificateRequest, ObjectionIn, PropertyClaim
from .billing import demand_notice
from .cases import TYPE_LABEL, case_detail, file_objection, plain_status
from .common import (
    PtxAPIRoute, PtxContext, audit, bad_request, balances, dues_summary, dues_total, get_setting, loads, new_doc_no, not_found, ptx_context, today,
    ward_maps,
)
from .payments import printable_receipt, scheme_quote
from .properties import assessment_dict, property_detail

router = APIRouter(route_class=PtxAPIRoute)


def _digits(mobile: str) -> str:
    return "".join(ch for ch in (mobile or "") if ch.isdigit())[-10:]


async def owned_property(db: AsyncSession, ctx: PtxContext, number: str, mobile: str) -> PtxProperty:
    """Property by UPIN or old assessment number, only if the mobile belongs to a current owner."""
    ctx.require("payment.online")
    key = (number or "").strip()
    if not key or len(_digits(mobile)) != 10:
        raise bad_request("Enter your property number and the 10-digit mobile number registered with the property.")
    prop = await db.scalar(select(PtxProperty).where(PtxProperty.tenant_id == ctx.tenant_id,
                                                     or_(PtxProperty.upin == key.upper(), PtxProperty.old_assessment_no == key)))
    mobile_ok = prop is not None and await db.scalar(select(PtxParty.id).where(
        PtxParty.property_id == prop.id, PtxParty.role == "OWNER", PtxParty.is_current.is_(True), PtxParty.mobile_number == _digits(mobile)))
    if not mobile_ok:
        raise not_found("We could not find a property with that number and mobile. Check the number on your tax bill, "
                        "or visit a Meeseva centre to update your mobile number.")
    return prop


def explain(dues: Dict, quote: Dict) -> List[Dict]:
    """Dues in plain words, line by line, for the citizen screen (ease of use)."""
    lines = []
    if dues["current"] > 0:
        lines.append({"key": "current", "en": "Tax for the current period", "te": "ప్రస్తుత కాలానికి పన్ను", "amount": dues["current"]})
    if dues["arrears"] > 0:
        lines.append({"key": "arrears", "en": "Unpaid tax from earlier periods", "te": "గత కాలాల బకాయి పన్ను", "amount": dues["arrears"]})
    if dues["interest"] > 0:
        lines.append({"key": "interest", "en": "Interest for late payment", "te": "ఆలస్య చెల్లింపు వడ్డీ", "amount": dues["interest"]})
    if dues["fees"] > 0:
        lines.append({"key": "fees", "en": "Fees and charges (for example a mutation fee)", "te": "రుసుములు, ఛార్జీలు", "amount": dues["fees"]})
    if dues["advanceHeld"] > 0:
        lines.append({"key": "advance", "en": "Extra amount you paid earlier (will be used)", "te": "మీరు ముందుగా చెల్లించిన అదనపు మొత్తం", "amount": -dues["advanceHeld"]})
    for s in quote["schemes"]:
        lines.append({"key": "scheme", "en": f"{s['nameEn']} - you save if you pay in full by {datetime.date.fromisoformat(s['until']).strftime('%d-%m-%Y')}",
                      "te": f"{s['nameTe']} - పూర్తిగా చెల్లిస్తే ఆదా", "amount": -s["benefit"]})
    return lines


@router.get("/citizen/account")
async def my_property(number: str = Query(..., description="UPIN or old assessment number"), mobile: str = Query(...),
                      ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    """Step 1 and 2: find the property and see what is owed, explained line by line."""
    prop = await owned_property(db, ctx, number, mobile)
    detail = await property_detail(db, ctx, prop, public=True)
    dues = dues_summary(await balances(db, ctx.tenant_id, prop.id))
    quote = await scheme_quote(db, prop, today())
    demands = (await db.execute(select(PtxDemand).where(PtxDemand.property_id == prop.id).order_by(PtxDemand.period_from.desc()).limit(8))).scalars().all()
    receipts = (await db.execute(select(PtxReceipt).where(PtxReceipt.property_id == prop.id).order_by(PtxReceipt.created_at.desc()).limit(10))).scalars().all()
    certs = (await db.execute(select(PtxCertificate).where(PtxCertificate.property_id == prop.id).order_by(PtxCertificate.created_at.desc()).limit(10))).scalars().all()
    cases = (await db.execute(select(PtxApplication).where(PtxApplication.property_id == prop.id).order_by(PtxApplication.created_at.desc()).limit(10))).scalars().all()
    complaints = (await db.execute(select(PtxComplaint).where(PtxComplaint.property_id == prop.id).order_by(PtxComplaint.created_at.desc()).limit(5))).scalars().all()
    return {
        "complaints": [{"complaintNo": c.complaint_no, "category": c.category, "status": c.status, "dueAt": c.due_at, "createdAt": c.created_at} for c in complaints],
        "property": detail, "dues": dues, "explanation": explain(dues, quote), "payNow": quote["payToClearAll"], "saving": quote["saving"],
        "schemes": quote["schemes"], "noDues": dues["totalDue"] <= 0,
        "demands": [{"demandNo": d.demand_no, "periodLabel": period_label(d.period), "dueDate": d.due_date, "amount": float(d.amount)} for d in demands],
        "receipts": [{"receiptNo": r.receipt_no, "date": r.receipt_date, "amount": float(r.amount), "mode": r.payment_mode, "status": r.status} for r in receipts],
        "certificates": [{"certificateNo": c.certificate_no, "certType": c.cert_type, "issuedOn": c.issued_on, "validUntil": c.valid_until} for c in certs],
        "cases": [{"applicationNo": a.application_no, "type": TYPE_LABEL.get(a.app_type, a.app_type), "status": a.status, "statusText": plain_status(a),
                   "createdAt": a.created_at} for a in cases],
    }


# ------------------------------------------------------------------------------------------------
# Your properties: a signed-in citizen proves a property once and finds it listed every time after
# ------------------------------------------------------------------------------------------------

async def _link_rows(db: AsyncSession, ctx: PtxContext) -> List:
    return (await db.execute(select(PtxCitizenLink, PtxProperty).join(PtxProperty, PtxProperty.id == PtxCitizenLink.property_id)
                             .where(PtxCitizenLink.tenant_id == ctx.tenant_id, PtxCitizenLink.username == ctx.username)
                             .order_by(PtxCitizenLink.linked_at))).all()


@router.get("/citizen/my-properties")
async def my_properties(ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    """The properties on this sign-in, each with what is due. The mobile is returned only to the person who gave it."""
    ctx.require("payment.online")
    wards, _ = await ward_maps(db, ctx.tenant_id)
    out = []
    for link, prop in await _link_rows(db, ctx):
        owners = (await db.execute(select(PtxParty.full_name).where(PtxParty.property_id == prop.id, PtxParty.role == "OWNER",
                                                                    PtxParty.is_current.is_(True)))).scalars().all()
        w = wards.get(prop.ward_id) or {}
        out.append({"upin": prop.upin, "oldAssessmentNo": prop.old_assessment_no, "doorNo": prop.door_no, "address": prop.address,
                    "wardNumber": w.get("wardNumber"), "wardName": w.get("wardName"), "ownerNames": ", ".join(owners), "status": prop.status,
                    "totalDue": dues_total(await balances(db, ctx.tenant_id, prop.id)), "payNow": (await scheme_quote(db, prop, today()))["payToClearAll"],
                    "mobileNumber": link.mobile_number, "linkedAt": link.linked_at,
                    "latitude": None if prop.location_pending else prop.latitude, "longitude": None if prop.location_pending else prop.longitude})
    return out


@router.post("/citizen/my-properties", status_code=201)
async def add_my_property(payload: PropertyClaim, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    prop = await owned_property(db, ctx, payload.number, payload.mobile_number)
    mobile = _digits(payload.mobile_number)
    link = await db.scalar(select(PtxCitizenLink).where(PtxCitizenLink.tenant_id == ctx.tenant_id, PtxCitizenLink.username == ctx.username,
                                                         PtxCitizenLink.property_id == prop.id))
    if link is None:
        db.add(PtxCitizenLink(tenant_id=ctx.tenant_id, username=ctx.username, property_id=prop.id, mobile_number=mobile))
        audit(db, ctx, "CITIZEN_PROPERTY_LINKED", "property", prop.id, None, {"upin": prop.upin})
    else:
        link.mobile_number = mobile
    await db.commit()
    return {"message": f"{prop.upin} is now listed under your account.", "upin": prop.upin}


@router.delete("/citizen/my-properties/{upin}")
async def remove_my_property(upin: str, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    ctx.require("payment.online")
    for link, prop in await _link_rows(db, ctx):
        if prop.upin == upin.strip().upper():
            await db.delete(link)
            audit(db, ctx, "CITIZEN_PROPERTY_UNLINKED", "property", prop.id, {"upin": prop.upin}, None)
            await db.commit()
            return {"message": f"{prop.upin} is no longer listed under your account."}
    raise not_found("That property is not listed under your account.")


@router.get("/citizen/demand/{demand_no}")
async def my_demand(demand_no: str, number: str = Query(...), mobile: str = Query(...), ctx: PtxContext = Depends(ptx_context),
                    db: AsyncSession = Depends(get_read_db)):
    prop = await owned_property(db, ctx, number, mobile)
    demand = await db.scalar(select(PtxDemand).where(PtxDemand.tenant_id == ctx.tenant_id, PtxDemand.demand_no == demand_no, PtxDemand.property_id == prop.id))
    if demand is None:
        raise not_found("Bill not found for this property.")
    return await demand_notice(db, ctx.tenant_id, demand, prop, public=True)


@router.get("/citizen/receipt/{receipt_no}")
async def my_receipt(receipt_no: str, number: str = Query(...), mobile: str = Query(...), ctx: PtxContext = Depends(ptx_context),
                     db: AsyncSession = Depends(get_read_db)):
    prop = await owned_property(db, ctx, number, mobile)
    r = await db.scalar(select(PtxReceipt).where(PtxReceipt.tenant_id == ctx.tenant_id, PtxReceipt.receipt_no == receipt_no, PtxReceipt.property_id == prop.id))
    if r is None:
        raise not_found("Receipt not found for this property.")
    return await printable_receipt(db, r)


@router.get("/citizen/calculation")
async def my_calculation(number: str = Query(...), mobile: str = Query(...), ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    """How the tax was worked out, shown to the owner (PT-11)."""
    prop = await owned_property(db, ctx, number, mobile)
    from app.db.ptx_models import PtxAssessment
    rows = (await db.execute(select(PtxAssessment).where(PtxAssessment.property_id == prop.id, PtxAssessment.status.in_(["FINAL", "NOTICE_ISSUED"]))
                             .order_by(PtxAssessment.effective_from.desc(), PtxAssessment.created_at.desc()))).scalars().all()
    return [assessment_dict(a) for a in rows]


# ------------------------------------------------------------------------------------------------
# No-dues certificate (PT-47)
# ------------------------------------------------------------------------------------------------

def certificate_dict(c: PtxCertificate, prop: PtxProperty, owners: List[str], ward: Dict) -> Dict:
    return {"certificateNo": c.certificate_no, "upin": prop.upin, "oldAssessmentNo": prop.old_assessment_no, "address": prop.address,
            "wardNumber": ward.get("wardNumber"), "wardName": ward.get("wardName"), "ownerNames": owners, "issuedOn": c.issued_on,
            "validUntil": c.valid_until, "paidUpTo": c.paid_up_to, "paidUpToLabel": period_label(c.paid_up_to) if c.paid_up_to else None,
            "verificationCode": c.verification_code, "certType": c.cert_type, "purpose": c.purpose, "content": loads(c.content_json, {}),
            "verifyPath": f"/api/v1/ptx/public/verify?type=CERTIFICATE&no={c.certificate_no}&code={c.verification_code}&tenant={c.tenant_id}"}


async def _certificate_view(db: AsyncSession, ctx: PtxContext, c: PtxCertificate, prop: PtxProperty) -> Dict:
    owners = (await db.execute(select(PtxParty.full_name).where(PtxParty.property_id == prop.id, PtxParty.role == "OWNER", PtxParty.is_current.is_(True)))).scalars().all()
    wards, _ = await ward_maps(db, ctx.tenant_id)
    return certificate_dict(c, prop, list(owners), wards.get(prop.ward_id, {}))


@router.post("/citizen/no-dues-certificate", status_code=201)
async def no_dues_certificate(payload: CertificateRequest, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """Issues a no-dues certificate when nothing is owed. Staff can issue one at the counter without the mobile."""
    if ctx.can("payment.collect") and not payload.mobile_number:
        from .common import load_property
        prop = await load_property(db, ctx, upin=payload.upin)
    else:
        prop = await owned_property(db, ctx, payload.upin, payload.mobile_number or "")
    due = dues_total(await balances(db, ctx.tenant_id, prop.id))
    if due > 0:
        raise bad_request(f"Rs {due} is still due on this property. Please pay it first; the certificate is issued straight after.")
    if prop.status != "ACTIVE":
        raise bad_request(f"This property number is {prop.status.lower()}. Ask for a certificate on the new property number.")
    valid_days = int((await get_setting(db, ctx.tenant_id, "noDues"))["validDays"])
    last = await db.scalar(select(PtxDemand.period).where(PtxDemand.property_id == prop.id).order_by(PtxDemand.period_from.desc()).limit(1))
    cert = PtxCertificate(tenant_id=ctx.tenant_id, certificate_no=await new_doc_no(db, ctx.tenant_id, "PND", "certificate"), property_id=prop.id,
                          issued_on=today(), valid_until=today() + datetime.timedelta(days=valid_days), paid_up_to=last, verification_code="PENDING",
                          issued_to=payload.mobile_number, created_by=ctx.username)
    db.add(cert)
    await db.flush()
    cert.verification_code = document_code("CERTIFICATE", cert.certificate_no, 0)
    audit(db, ctx, "NO_DUES_ISSUED", "certificate", cert.id, None, {"certificateNo": cert.certificate_no, "upin": prop.upin})
    await db.commit()
    return await _certificate_view(db, ctx, cert, prop)


@router.get("/citizen/certificate/{certificate_no}")
async def get_certificate(certificate_no: str, number: Optional[str] = Query(None), mobile: Optional[str] = Query(None),
                          ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    cert = await db.scalar(select(PtxCertificate).where(PtxCertificate.tenant_id == ctx.tenant_id, PtxCertificate.certificate_no == certificate_no))
    if cert is None:
        raise not_found("Certificate not found.")
    if ctx.can("property.view"):
        prop = await db.get(PtxProperty, cert.property_id)
    else:
        prop = await owned_property(db, ctx, number or "", mobile or "")
        if prop.id != cert.property_id:
            raise not_found("Certificate not found for this property.")
    return await _certificate_view(db, ctx, cert, prop)


# ------------------------------------------------------------------------------------------------
# Tracking cases and objections
# ------------------------------------------------------------------------------------------------

@router.get("/citizen/cases/{application_no}")
async def track_case(application_no: str, mobile: str = Query(...), ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_read_db)):
    """Anyone with the application number and the mobile given on it can track it, in plain words."""
    ctx.require("payment.online")
    app = await db.scalar(select(PtxApplication).where(PtxApplication.tenant_id == ctx.tenant_id, PtxApplication.application_no == application_no))
    owner_ok = False
    if app is not None and app.property_id:
        owner_ok = bool(await db.scalar(select(PtxParty.id).where(PtxParty.property_id == app.property_id, PtxParty.role == "OWNER",
                                                                  PtxParty.mobile_number == _digits(mobile))))
    if app is None or not (app.mobile_number == _digits(mobile) or owner_ok):
        raise not_found("No application found with that number and mobile. Check the acknowledgement you received.")
    return await case_detail(db, ctx, app, public=True)


@router.post("/citizen/cases/{application_no}/objection")
async def citizen_objection(application_no: str, payload: ObjectionIn, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """The owner disagrees with the assessment notice and files an objection within the period (PT-19)."""
    ctx.require("payment.online")
    app = await db.scalar(select(PtxApplication).where(PtxApplication.tenant_id == ctx.tenant_id, PtxApplication.application_no == application_no).with_for_update())
    mobile = _digits(payload.mobile_number or "")
    owner_ok = bool(app and app.property_id and await db.scalar(select(PtxParty.id).where(
        PtxParty.property_id == app.property_id, PtxParty.role == "OWNER", PtxParty.mobile_number == mobile)))
    if app is None or not (app.mobile_number == mobile or owner_ok):
        raise not_found("No application found with that number and mobile.")
    await file_objection(db, ctx, app, payload.text, "citizen")
    await db.commit()
    return {"message": "Your objection has been received. The Revenue Officer will decide it and you will get an SMS.", "applicationNo": app.application_no}
