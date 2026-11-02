"""
Certificates (PT-28, PT-47): no-dues, tax-paid, assessment extract and No Objection Certificate (NOC). Each has a number, a
validity and a QR code anyone can scan to check it is genuine. What was certified is frozen at the moment of issue.
"""
import datetime
from typing import Dict

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ptx_calc import document_code
from app.db.ptx_models import PtxApplication, PtxAssessment, PtxCertificate, PtxDemand, PtxProperty, PtxReceipt
from app.db.session import get_write_db
from app.schemas.ptx import CertificateIssue
from .assess import current_floors
from .citizen import _certificate_view, owned_property
from .common import (
    PtxAPIRoute, PtxContext, audit, bad_request, balances, dues_total, dumps, get_setting, load_property, loads, new_doc_no, ptx_context, today,
)

router = APIRouter(route_class=PtxAPIRoute)

PREFIX = {"NO_DUES": "PND", "TAX_PAID": "PTP", "ASSESSMENT_EXTRACT": "PAE", "NOC": "PNC"}


async def _content(db: AsyncSession, ctx: PtxContext, prop: PtxProperty, cert_type: str, purpose: str, due, cfg: Dict) -> Dict:
    if cert_type == "TAX_PAID":
        since = today() - datetime.timedelta(days=365 * int(cfg.get("taxPaidYears", 3)))
        receipts = (await db.execute(select(PtxReceipt).where(PtxReceipt.property_id == prop.id, PtxReceipt.status == "VALID", PtxReceipt.receipt_date >= since)
                                     .order_by(PtxReceipt.receipt_date.desc()).limit(60))).scalars().all()
        return {"since": since.isoformat(), "balanceDue": float(max(due, 0)), "totalPaid": float(sum((r.amount for r in receipts), 0)),
                "receipts": [{"receiptNo": r.receipt_no, "date": r.receipt_date.isoformat(), "amount": float(r.amount), "mode": r.payment_mode} for r in receipts]}
    if cert_type == "ASSESSMENT_EXTRACT":
        a = await db.scalar(select(PtxAssessment).where(PtxAssessment.property_id == prop.id, PtxAssessment.status == "FINAL")
                            .order_by(PtxAssessment.effective_from.desc(), PtxAssessment.created_at.desc()).limit(1))
        if a is None:
            raise bad_request("This property has no final assessment yet, so there is nothing to extract.")
        sheet = loads(a.calculation_json, {})
        return {"assessmentNo": a.assessment_no, "effectiveFrom": a.effective_from.isoformat(), "annualTax": float(a.annual_tax),
                "components": loads(a.components_json, {}), "rateZone": sheet.get("rateZone"), "floors": await current_floors(db, prop.id),
                "siteAreaSqyd": float(prop.site_area_sqyd or 0), "constructionYear": prop.construction_year, "roadClass": prop.road_class,
                "exemptionCode": prop.exemption_code, "propertyType": prop.property_type}
    if cert_type == "NOC":
        return {"purpose": purpose, "duesCleared": True, "noApplicationInProgress": True}
    return {}


@router.post("/citizen/certificates", status_code=201)
async def issue_certificate(payload: CertificateIssue, ctx: PtxContext = Depends(ptx_context), db: AsyncSession = Depends(get_write_db)):
    """Staff issue at the counter without the mobile; owners confirm with the registered mobile."""
    if ctx.can("payment.collect") and not payload.mobile_number:
        prop = await load_property(db, ctx, upin=payload.upin)
    else:
        prop = await owned_property(db, ctx, payload.upin, payload.mobile_number or "")
    t = payload.cert_type
    due = dues_total(await balances(db, ctx.tenant_id, prop.id))
    if t in ("NO_DUES", "NOC"):
        if due > 0:
            raise bad_request(f"Rs {due} is still due on this property. Please pay it first; the certificate is issued straight after.")
        if prop.status != "ACTIVE":
            raise bad_request(f"This property number is {prop.status.lower()}. Ask for a certificate on the new property number.")
    purpose = (payload.purpose or "").strip()
    if t == "NOC":
        if len(purpose) < 5:
            raise bad_request("Say what the NOC is for (for example: sale of the property, or a bank loan).")
        open_case = await db.scalar(select(PtxApplication.application_no).where(
            PtxApplication.tenant_id == ctx.tenant_id, PtxApplication.status == "IN_PROGRESS",
            (PtxApplication.property_id == prop.id) | PtxApplication.related_property_ids_json.contains(prop.id)).limit(1))
        if open_case:
            raise bad_request(f"Application {open_case} is still in progress on this property. A NOC is issued once it is completed.")
    cfg = await get_setting(db, ctx.tenant_id, "certificates")
    days = {"NO_DUES": int((await get_setting(db, ctx.tenant_id, "noDues"))["validDays"]), "NOC": int(cfg.get("nocValidDays", 30)),
            "ASSESSMENT_EXTRACT": int(cfg.get("extractValidDays", 90)), "TAX_PAID": int(cfg.get("taxPaidValidDays", 90))}[t]
    content = await _content(db, ctx, prop, t, purpose, due, cfg)
    last = await db.scalar(select(PtxDemand.period).where(PtxDemand.property_id == prop.id).order_by(PtxDemand.period_from.desc()).limit(1))
    cert = PtxCertificate(tenant_id=ctx.tenant_id, certificate_no=await new_doc_no(db, ctx.tenant_id, PREFIX[t], f"certificate-{t.lower()}"), property_id=prop.id,
                          issued_on=today(), valid_until=today() + datetime.timedelta(days=days), paid_up_to=last if due <= 0 else None,
                          verification_code="PENDING", issued_to=payload.mobile_number, created_by=ctx.username, cert_type=t,
                          purpose=purpose or None, content_json=dumps(content))
    db.add(cert)
    await db.flush()
    cert.verification_code = document_code("CERTIFICATE", cert.certificate_no, 0)
    audit(db, ctx, f"{t}_CERTIFICATE_ISSUED", "certificate", cert.id, None, {"certificateNo": cert.certificate_no, "upin": prop.upin, "purpose": purpose})
    await db.commit()
    return await _certificate_view(db, ctx, cert, prop)
