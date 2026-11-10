"""
Shared plumbing for the Property Tax API (Module 1): request context (tenant, user, ward/zone scope), permissions,
versioned settings, number series, ledger, audit trail, events, notifications and pagination.
"""
import copy
import datetime
import json
import logging
import os
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Set

from fastapi import Depends, Header, HTTPException, Request, Response, status
from fastapi.routing import APIRoute
from sqlalchemy import func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_tenant, get_current_user
from app.core.ptx_calc import DUES_BUCKETS, money
from app.db.models import Locality, User, Ward, Zone
from app.db.ptx_models import (
    PtxApiLog, PtxAuditLog, PtxCounter, PtxEvent, PtxLedger, PtxNotification, PtxProperty, PtxSetting, PtxTimeline,
    utcnow,
)
from app.db.session import AsyncWriteSessionLocal, get_read_db

logger = logging.getLogger("urban-ptx")

# ------------------------------------------------------------------------------------------------
# Roles and permissions (PT-NF-10). User classes from SRS 2.3.
# ------------------------------------------------------------------------------------------------

ADMIN = {"super_admin", "system_admin"}
COMMISSIONER = {"commissioner"}
OFFICER = {"revenue_officer"}
INSPECTOR = {"revenue_inspector"}
COLLECTOR = {"bill_collector"}
CASHIER = {"cashier"}
CSC = {"csc_operator"}
CITIZEN = {"citizen"}
STAFF = ADMIN | COMMISSIONER | OFFICER | INSPECTOR | COLLECTOR | CASHIER | CSC
UNSCOPED_ROLES = ADMIN | COMMISSIONER

PERMISSIONS: Dict[str, Set[str]] = {
    "property.view": STAFF,
    "property.edit": OFFICER | INSPECTOR,
    "case.create": OFFICER | INSPECTOR | CSC | CITIZEN,
    "case.view": STAFF,
    "survey.capture": INSPECTOR | OFFICER,
    # the checker on a captured survey is the Officer only (PT-NF-10); decide_survey() also blocks deciding your own
    "survey.review": OFFICER,
    "rates.view": STAFF,
    "rates.propose": ADMIN | OFFICER,
    "rates.approve": COMMISSIONER,
    "demand.run": OFFICER,
    "billing.view": STAFF,
    "payment.collect": CASHIER | COLLECTOR | CSC | OFFICER,
    "payment.online": STAFF | CITIZEN,
    "payment.cheque_return": CASHIER,
    "payment.reconcile": CASHIER,
    "dayclose.submit": CASHIER | COLLECTOR | CSC | OFFICER,
    "dayclose.verify": CASHIER | OFFICER,
    "approval.request": OFFICER | CASHIER,
    "petition.decide": COMMISSIONER,
    "integration.run": OFFICER,
    "complaint.work": OFFICER | INSPECTOR,
    "remittance.prepare": CASHIER,
    "remittance.confirm": OFFICER | COMMISSIONER,
    "approval.decide": OFFICER | COMMISSIONER,
    "arrears.manage": OFFICER,
    "notice.serve": INSPECTOR | COLLECTOR | OFFICER,
    "reports.view": OFFICER | COMMISSIONER | CASHIER,
    # a collector's own numbers only (PT-61, PT-62), not the full Reports section (PT-NF-10)
    "reports.view.own": COLLECTOR,
    "gis.view": STAFF,
    "settings.manage": ADMIN,
    "audit.view": ADMIN | COMMISSIONER,
    "migration.run": ADMIN,
}


@dataclass
class PtxContext:
    tenant_id: str
    sub_tenant_id: Optional[str]
    user: Dict[str, Any]
    username: str
    roles: Set[str]
    ip: Optional[str]
    allowed_ward_ids: Optional[Set[str]] = None  # None = whole city
    scope_label: str = "All wards"
    extra: Dict[str, Any] = field(default_factory=dict)

    def can(self, permission: str) -> bool:
        if self.roles & ADMIN:
            return True
        return bool(self.roles & PERMISSIONS.get(permission, set()))

    def require(self, permission: str) -> None:
        if not self.can(permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"Your role does not allow this action ({permission}). Ask the revenue section administrator for access.")

    def require_any(self, permissions: List[str]) -> None:
        """Passes if any one of these permissions is held; otherwise raises with the first one named."""
        if not any(self.can(p) for p in permissions):
            self.require(permissions[0])

    def is_only(self, roles: Set[str]) -> bool:
        """True when every role this user holds is in the given set (and they hold at least one)."""
        return bool(self.roles) and self.roles <= roles

    def in_scope(self, ward_id: Optional[str]) -> bool:
        return self.allowed_ward_ids is None or (ward_id is not None and ward_id in self.allowed_ward_ids)

    def ensure_scope(self, ward_id: Optional[str]) -> None:
        if not self.in_scope(ward_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f"This property is outside your assigned area ({self.scope_label}).")

    def ward_filter(self, column):
        if self.allowed_ward_ids is None:
            return true()
        return column.in_(list(self.allowed_ward_ids) or ["__none__"])


def _number(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    digits = "".join(ch for ch in str(text) if ch.isdigit())
    return int(digits) if digits else None


async def ptx_context(
    request: Request,
    tenant_id: str = Depends(get_current_tenant),
    user: Dict = Depends(get_current_user),
    x_sub_tenant_id: Optional[str] = Header(None, alias="X-Sub-Tenant-ID"),
    db: AsyncSession = Depends(get_read_db),
) -> PtxContext:
    roles = set(user.get("realm_access", {}).get("roles", []) or [])
    if user.get("role"):
        roles.add(user["role"])
    username = user.get("preferred_username") or user.get("email") or user.get("sub") or "unknown"
    ctx = PtxContext(tenant_id=tenant_id, sub_tenant_id=(x_sub_tenant_id or "").strip().upper() or None, user=user,
                     username=username, roles=roles, ip=request.client.host if request.client else None)
    request.state.ptx_caller = username
    request.state.ptx_tenant = tenant_id
    if not (roles & UNSCOPED_ROLES) and not (roles <= CITIZEN):
        ward_ref, zone_ref = user.get("assigned_ward"), user.get("assigned_zone")
        if not ward_ref and not zone_ref:
            account = (await db.execute(select(User.assigned_ward, User.assigned_zone).where(User.username == username))).first()
            if account:
                ward_ref, zone_ref = account
        if ward_ref or zone_ref:
            rows = (await db.execute(select(Ward.id, Ward.ward_number, Zone.code, Zone.name).join(Zone, Zone.id == Ward.zone_id)
                                     .where(Ward.tenant_id == tenant_id))).all()
            ward_no, zone_key, zone_no = _number(ward_ref), (zone_ref or "").strip().lower(), _number(zone_ref)
            allowed: Set[str] = set()
            for ward_id, number, zone_code, zone_name in rows:
                if ward_ref and ward_no is not None and number == ward_no:
                    allowed.add(ward_id)
                elif not ward_ref and zone_ref and (zone_key in {(zone_code or "").lower(), (zone_name or "").lower()}
                                                    or (zone_no is not None and _number(zone_code) == zone_no)):
                    allowed.add(ward_id)
            ctx.allowed_ward_ids = allowed
            ctx.scope_label = ward_ref or zone_ref
    return ctx


class PtxAPIRoute(APIRoute):
    """Logs every Property Tax API call with time, caller and result (PT-IR-09)."""

    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            started = time.perf_counter()
            status_code = 500
            try:
                response = await original(request)
                status_code = response.status_code
                return response
            except HTTPException as exc:
                status_code = exc.status_code
                raise
            finally:
                duration = int((time.perf_counter() - started) * 1000)
                caller = getattr(request.state, "ptx_caller", None)
                tenant = getattr(request.state, "ptx_tenant", None) or request.headers.get("X-Tenant-ID")
                logger.info("PTX-API %s %s caller=%s status=%s %sms", request.method, request.url.path, caller, status_code, duration)
                try:
                    async with AsyncWriteSessionLocal() as log_db:
                        log_db.add(PtxApiLog(tenant_id=tenant, caller=caller, method=request.method,
                                             path=request.url.path[:300], status_code=status_code, duration_ms=duration))
                        await log_db.commit()
                except Exception as exc:  # logging must never break the call itself
                    logger.warning("Could not write property tax API log: %s", exc)

        return handler


# ------------------------------------------------------------------------------------------------
# Versioned settings (SRS 2.5, 3.4, PT-NF-50). Placeholders until GWMC confirms (SRS Appendix A).
# ------------------------------------------------------------------------------------------------

_OFFICER = sorted(OFFICER)
_INSPECTOR = sorted({"revenue_inspector"} | OFFICER)
_WF = lambda code, label, hours, roles: {"code": code, "label": label, "slaHours": hours, "roles": roles, "enabled": True}  # noqa: E731

DEFAULT_SETTINGS: Dict[str, Any] = {
    "demand.frequency": "HALF_YEARLY",
    "demand.dueDaysFromPeriodStart": 90,
    "payment.allocationOrder": ["PENALTY", "FEE", "ARREAR", "CURRENT"],
    "interest": {"percentPerMonth": 2.0, "graceDays": 0},
    "schemes": [],
    "mutation": {"allowWithDues": False, "feeByReason": {"SALE": 1000, "GIFT": 500, "INHERITANCE": 250, "PARTITION": 500, "COURT_ORDER": 250}},
    "subdivision": {"duesRule": "SPLIT_BY_AREA", "fee": 500},
    "amalgamation": {"duesRule": "CLEAR_FIRST", "fee": 500},
    "assessment": {"objectionDays": 15, "commissionerApprovalAboveAnnualTax": 50000, "petitionDays": 30, "appealDays": 60},
    "backAssessment": {"lookBackYears": 3, "commissionerApproval": True},
    "certificates": {"nocValidDays": 30, "extractValidDays": 90, "taxPaidValidDays": 90, "taxPaidYears": 3},
    "complaints": {"defaultSlaHours": 120},
    "fees.chequeReturnCharge": 300,
    "approval.limits": {"revenue_officer": 25000, "commissioner": None},
    "accountHeads": {
        "PROPERTY_TAX": "AH-PTX-1101", "VACANT_LAND_TAX": "AH-PTX-1102", "LIBRARY_CESS": "AH-PTX-1103",
        "ARREAR": "AH-PTX-1104", "INTEREST": "AH-PTX-1201", "FEES": "AH-PTX-1300", "MUTATION_FEE": "AH-PTX-1301",
        "SUBDIVISION_FEE": "AH-PTX-1302", "AMALGAMATION_FEE": "AH-PTX-1303", "CHEQUE_RETURN_CHARGE": "AH-PTX-1304",
        "SETBACK_PENALTY": "AH-PTX-1105", "ADVANCE": "AH-PTX-3402", "REBATE": "AH-PTX-2104", "OTS_WAIVER": "AH-PTX-2105", "WAIVER": "AH-PTX-2101",
        "WRITE_OFF": "AH-PTX-2102", "ADJUSTMENT": "AH-PTX-2103", "REFUND": "AH-PTX-3403",
    },
    "reminders": {"daysBeforeDue": 15, "daysAfterDue": [7, 30]},
    "recovery": {
        "stages": ["DEMAND_NOTICE", "REMINDER_NOTICE", "RECOVERY_NOTICE", "FINAL_NOTICE", "DISTRAINT_WARRANT", "ATTACHMENT"],
        "openAboveAmount": 10000, "openAfterDaysOverdue": 180,
    },
    "arrearsBands": [{"label": "Under 1 year", "maxDays": 365}, {"label": "1 to 3 years", "maxDays": 1095},
                     {"label": "Over 3 years", "maxDays": None}],
    "gis": {"areaMismatchPercent": 10, "matchRadiusM": 25},
    "collection.targets": {"annual": 5000000, "byWardNumber": {}, "byCollector": {}},
    "noDues": {"validDays": 90},
    "upi": {"vpa": "gwmc.ptax@placeholder", "payeeName": "GWMC Property Tax"},
    "integrationLinks": {
        "I-05": {"module": "Water & Utility Billing (Module 2)", "direction": "From Module 1", "enabled": False},
        "I-03": {"module": "Building Permission (Module 11)", "direction": "To Module 1", "enabled": False},
        "I-09": {"module": "Finance & Accounting (Module 4)", "direction": "From Module 1", "enabled": False},
        "LOOKUP": {"module": "Trade Licence, User Charges, Building Permission, Municipal Property, Fire NOC", "direction": "From Module 1", "enabled": False},
        "DMS": {"module": "Document Management (Module 9)", "direction": "From Module 1", "enabled": False},
        "LGL": {"module": "Legal Case Management (Module 16)", "direction": "From Module 1", "enabled": False},
        "HRM": {"module": "Payroll & HR (Module 8)", "direction": "To Module 1", "enabled": False},
        # stand-ins that work today with the same data the real systems will send (PT-02, PT-14, PT-21)
        "REGISTRATION": {"module": "Registration Department (registered deeds)", "direction": "To Module 1", "enabled": False, "standIn": True},
        "STATE_PLATFORM": {"module": "State property platform", "direction": "Both ways", "enabled": False, "standIn": True},
        "BBPS": {"module": "Bharat Bill Payment System (BBPS)", "direction": "Both ways", "enabled": False, "standIn": True},
    },
    "reports.schedule": [
        {"report": "DCB", "frequency": "MONTHLY", "format": "PDF", "recipients": ["accounts@gwmc.gov.in"]},
        {"report": "DAILY_COLLECTION", "frequency": "DAILY", "format": "EXCEL", "recipients": ["revenue@gwmc.gov.in"]},
    ],
    "session.staffTimeoutMinutes": 15,
    "workflow": {
        "NEW_ASSESSMENT": [_WF("DOC_CHECK", "Document check", 48, _INSPECTOR), _WF("FIELD_INSPECTION", "Field inspection and measurement", 120, _INSPECTOR),
                           _WF("APPROVAL", "Approval", 72, _OFFICER), _WF("NOTICE", "Assessment notice and objection period", 24, _OFFICER)],
        "SELF_ASSESSMENT": [_WF("DOC_CHECK", "Document check", 48, _INSPECTOR), _WF("FIELD_INSPECTION", "Field verification", 120, _INSPECTOR),
                            _WF("APPROVAL", "Approval", 72, _OFFICER), _WF("NOTICE", "Assessment notice and objection period", 24, _OFFICER)],
        "REASSESSMENT": [_WF("DOC_CHECK", "Document check", 48, _INSPECTOR), _WF("FIELD_INSPECTION", "Field inspection and measurement", 120, _INSPECTOR),
                         _WF("APPROVAL", "Approval", 72, _OFFICER), _WF("NOTICE", "Assessment notice and objection period", 24, _OFFICER)],
        "USE_CHANGE": [_WF("DOC_CHECK", "Document check", 48, _INSPECTOR), _WF("FIELD_INSPECTION", "Field inspection", 120, _INSPECTOR),
                       _WF("APPROVAL", "Approval", 72, _OFFICER), _WF("NOTICE", "Assessment notice and objection period", 24, _OFFICER)],
        "EXEMPTION": [_WF("DOC_CHECK", "Document check", 48, _INSPECTOR), _WF("APPROVAL", "Approval", 72, _OFFICER),
                      _WF("NOTICE", "Assessment notice and objection period", 24, _OFFICER)],
        "MUTATION": [_WF("DOC_CHECK", "Ownership document check", 72, _INSPECTOR), _WF("APPROVAL", "Approval", 72, _OFFICER)],
        "SUBDIVISION": [_WF("DOC_CHECK", "Document check", 48, _INSPECTOR), _WF("FIELD_INSPECTION", "Field inspection and measurement", 120, _INSPECTOR),
                        _WF("APPROVAL", "Approval", 72, _OFFICER), _WF("NOTICE", "Assessment notice and objection period", 24, _OFFICER)],
        "AMALGAMATION": [_WF("DOC_CHECK", "Document check", 48, _INSPECTOR), _WF("FIELD_INSPECTION", "Field inspection and measurement", 120, _INSPECTOR),
                         _WF("APPROVAL", "Approval", 72, _OFFICER), _WF("NOTICE", "Assessment notice and objection period", 24, _OFFICER)],
        # each unit gets its own assessment notice when the building is approved, so there is no separate notice step
        "DEMOLITION": [_WF("DOC_CHECK", "Document check", 48, _INSPECTOR), _WF("FIELD_INSPECTION", "Site inspection: confirm the building is gone", 120, _INSPECTOR),
                       _WF("APPROVAL", "Approval", 72, _OFFICER)],
        "BACK_ASSESSMENT": [_WF("DOC_CHECK", "Document check", 48, _INSPECTOR), _WF("FIELD_INSPECTION", "Field inspection and measurement", 120, _INSPECTOR),
                            _WF("APPROVAL", "Approval (Commissioner)", 72, _OFFICER), _WF("NOTICE", "Assessment notice and objection period", 24, _OFFICER)],
        "APARTMENT": [_WF("DOC_CHECK", "Document check", 48, _INSPECTOR), _WF("FIELD_INSPECTION", "Field inspection and measurement of all units", 168, _INSPECTOR),
                      _WF("APPROVAL", "Approval", 72, _OFFICER)],
    },
    "escalation": ["revenue.officer@gwmc.gov.in", "commissioner@gwmc.gov.in"],
}

SETTING_DESCRIPTIONS: Dict[str, str] = {
    "demand.frequency": "Demand raised HALF_YEARLY or YEARLY (PT-30, Appendix A #3)",
    "demand.dueDaysFromPeriodStart": "Days from the start of a period to its due date",
    "payment.allocationOrder": "Order in which a payment clears dues (PT-33)",
    "interest": "Interest on overdue tax, percent per month (PT-41)",
    "schemes": "Rebate and one-time settlement schemes with their dates (PT-39)",
    "mutation": "Mutation fee by reason, and whether mutation is allowed with dues pending (PT-13, PT-14)",
    "subdivision": "How pending dues are handled on subdivision: SPLIT_BY_AREA or MUST_CLEAR (PT-15)",
    "amalgamation": "How dues of merged properties are handled: CLEAR_FIRST or CARRY_FORWARD (PT-16)",
    "assessment": "Objection days, petition and appeal days, and annual tax above which the Commissioner approves (PT-19, PT-24)",
    "certificates": "How long NOC, assessment extract and tax-paid certificates stay valid, and how many years of payments the tax-paid certificate lists (PT-28)",
    "complaints": "Default time limit in hours to resolve a complaint when its category has none (PT-29)",
    "backAssessment": "How far back an assessment may reach (years) and whether the Commissioner must approve back-assessments (PT-11)",
    "fees.chequeReturnCharge": "Charge added when a cheque is returned (PT-37)",
    "approval.limits": "Highest amount each role may approve; null means no limit (PT-40, PT-45)",
    "accountHeads": "Account head codes (PT-66, PT-IR-04) - GWMC chart of accounts pending",
    "reminders": "Reminder days before and after the due date (PT-46)",
    "recovery": "Recovery stages, and when a recovery case is opened (PT-44)",
    "arrearsBands": "Arrears age bands for reports (PT-63)",
    "gis": "Map checks: area mismatch percent (PT-51) and match radius",
    "collection.targets": "Collection targets for the year, by ward and collector (PT-61, PT-64)",
    "noDues": "How long a no-dues certificate stays valid (PT-47)",
    "upi": "UPI payee printed in demand notice QR codes",
    "integrationLinks": "Planned links to other modules; all switched off in Release 1 (PT-IR-06)",
    "reports.schedule": "Reports emailed on a schedule (PT-65)",
    "session.staffTimeoutMinutes": "Staff session inactivity timeout (PT-NF-15)",
    "workflow": "Steps, SLAs and roles for each application type (PT-18)",
    "escalation": "Who is told when a step passes its SLA (PT-18)",
}

BUSINESS_UTC_OFFSET = datetime.timedelta(minutes=int(os.getenv("PTX_TZ_OFFSET_MINUTES", "330")))


async def get_links(db: AsyncSession, tenant_id: str) -> Dict[str, Any]:
    """The link switches as set, with any link added since the setting was saved shown as off."""
    stored = await get_setting(db, tenant_id, "integrationLinks")
    return {**copy.deepcopy(DEFAULT_SETTINGS["integrationLinks"]), **stored}


async def require_link(db: AsyncSession, tenant_id: str, key: str) -> None:
    """A link works only while it is switched on in the settings; switching is by configuration, never by code (PT-IR-06)."""
    link = (await get_links(db, tenant_id)).get(key)
    if not link or not link.get("enabled"):
        name = link["module"] if link else key
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=f"The link with {name} is switched off. An administrator can switch it on under Administration, Connections.")


def local_date(utc_naive: datetime.datetime) -> datetime.date:
    return (utc_naive + BUSINESS_UTC_OFFSET).date()


def local_day_start_utc(day: datetime.date) -> datetime.datetime:
    return datetime.datetime.combine(day, datetime.time.min) - BUSINESS_UTC_OFFSET


def today() -> datetime.date:
    """Business date in GWMC local time (IST); timestamps are stored in UTC."""
    return local_date(utcnow())


def to_utc_naive(value: datetime.datetime) -> datetime.datetime:
    if value.tzinfo is not None:
        value = value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return value


async def get_setting(db: AsyncSession, tenant_id: str, key: str, as_of: Optional[datetime.date] = None) -> Any:
    as_of = as_of or today()
    row = await db.scalar(select(PtxSetting).where(PtxSetting.tenant_id == tenant_id, PtxSetting.key == key,
                                                   PtxSetting.effective_from <= as_of)
                          .order_by(PtxSetting.effective_from.desc(), PtxSetting.created_at.desc()).limit(1))
    if row is not None:
        return json.loads(row.value_json)
    if key not in DEFAULT_SETTINGS:
        raise KeyError(key)
    return json.loads(json.dumps(DEFAULT_SETTINGS[key]))


async def account_head(db: AsyncSession, tenant_id: str, component: str) -> str:
    heads = await get_setting(db, tenant_id, "accountHeads")
    return heads.get(component) or heads.get("ADJUSTMENT") or "AH-PTX-UNMAPPED"


# ------------------------------------------------------------------------------------------------
# Number series (PT-01: UPINs never change and are never reused)
# ------------------------------------------------------------------------------------------------

async def next_number(db: AsyncSession, tenant_id: str, name: str) -> int:
    row = await db.scalar(select(PtxCounter).where(PtxCounter.tenant_id == tenant_id, PtxCounter.name == name).with_for_update())
    if row is None:
        row = PtxCounter(tenant_id=tenant_id, name=name, value=0)
        db.add(row)
        await db.flush()
    row.value = (row.value or 0) + 1
    await db.flush()
    return row.value


async def new_upin(db: AsyncSession, tenant_id: str) -> str:
    return f"{tenant_id}-P-{await next_number(db, tenant_id, 'upin'):08d}"


async def new_doc_no(db: AsyncSession, tenant_id: str, prefix: str, counter: str) -> str:
    return f"{prefix}-{tenant_id}-{today().strftime('%Y%m')}-{await next_number(db, tenant_id, counter):06d}"


# ------------------------------------------------------------------------------------------------
# Audit, events, notifications, timeline
# ------------------------------------------------------------------------------------------------

def dumps(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)


def loads(text: Optional[str], default: Any = None) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except ValueError:
        return default


def audit(db: AsyncSession, ctx: PtxContext, action: str, entity_type: str, entity_id: Optional[str], old: Any = None, new: Any = None) -> None:
    """Append-only audit record (PT-NF-13)."""
    db.add(PtxAuditLog(tenant_id=ctx.tenant_id, actor=ctx.username, ip_address=ctx.ip, action=action, entity_type=entity_type,
                       entity_id=entity_id, old_json=None if old is None else dumps(old), new_json=None if new is None else dumps(new)))


EVENT_TYPES = {
    "property.created", "property.changed", "assessment.approved", "mutation.approved", "subdivision.approved",
    "amalgamation.approved", "demand.raised", "payment.received", "receipt.cancelled", "refund.approved", "writeoff.approved",
}


def emit_event(db: AsyncSession, tenant_id: str, event_type: str, aggregate_id: Optional[str], payload: Dict) -> None:
    """Event outbox (PT-IR-02). Payload carries only the fields a consumer module needs (PT-NF-23)."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unknown property tax event type {event_type}")
    db.add(PtxEvent(tenant_id=tenant_id, event_type=event_type, aggregate_id=aggregate_id,
                    payload_json=dumps({"eventType": event_type, "tenantId": tenant_id, "occurredAt": utcnow().isoformat(), **payload})))


async def notify(db: AsyncSession, tenant_id: str, *, recipient: Optional[str], template: str, message_en: str, message_te: str,
                 property_id: Optional[str] = None, ref_no: Optional[str] = None, dedupe_key: Optional[str] = None,
                 channel: str = "SMS") -> bool:
    """Queues an SMS / WhatsApp / email through the stand-in sender. False if already sent (dedupe)."""
    if dedupe_key and await db.scalar(select(PtxNotification.id).where(PtxNotification.tenant_id == tenant_id,
                                                                       PtxNotification.dedupe_key == dedupe_key)):
        return False
    db.add(PtxNotification(tenant_id=tenant_id, channel=channel, recipient=recipient, template=template, message_en=message_en,
                           message_te=message_te, property_id=property_id, ref_no=ref_no, dedupe_key=dedupe_key,
                           status="LOGGED_STAND_IN" if recipient else "NO_RECIPIENT"))
    return True


def timeline(db: AsyncSession, ctx_or_tenant, entity_type: str, entity_id: str, action: str, remark: Optional[str] = None,
             actor: Optional[str] = None) -> None:
    tenant_id = ctx_or_tenant.tenant_id if isinstance(ctx_or_tenant, PtxContext) else ctx_or_tenant
    who = actor or (ctx_or_tenant.username if isinstance(ctx_or_tenant, PtxContext) else "system")
    db.add(PtxTimeline(tenant_id=tenant_id, entity_type=entity_type, entity_id=entity_id, action=action, remark=remark, actor=who))


# ------------------------------------------------------------------------------------------------
# Ledger (PT-IR-04)
# ------------------------------------------------------------------------------------------------

BUCKET_COMPONENT = {"PENALTY": "INTEREST", "FEE": "FEES", "ARREAR": "ARREAR", "CURRENT": "PROPERTY_TAX", "ADVANCE": "ADVANCE"}


async def post_ledger(db: AsyncSession, actor, *, prop: PtxProperty, txn_type: str, component: str, bucket: str, amount,
                      payment_mode: Optional[str] = None, reference_no: Optional[str] = None, demand_id: Optional[str] = None,
                      receipt_id: Optional[str] = None, approval_id: Optional[str] = None, narration: Optional[str] = None,
                      entry_date: Optional[datetime.date] = None, dedupe_key: Optional[str] = None,
                      is_reversal: bool = False, reversal_of_id: Optional[str] = None) -> PtxLedger:
    value = money(amount)
    if value == 0:
        raise ValueError("Ledger entries cannot be zero.")
    entry = PtxLedger(
        tenant_id=prop.tenant_id, property_id=prop.id, ward_id=prop.ward_id, entry_date=entry_date or today(),
        txn_type=txn_type, component=component, bucket=bucket, account_head=await account_head(db, prop.tenant_id, component),
        amount=value, payment_mode=payment_mode, reference_no=reference_no, demand_id=demand_id, receipt_id=receipt_id,
        approval_id=approval_id, dedupe_key=dedupe_key, is_reversal=is_reversal, reversal_of_id=reversal_of_id,
        narration=narration, created_by=actor.username if isinstance(actor, PtxContext) else str(actor),
    )
    db.add(entry)
    return entry


async def balances(db: AsyncSession, tenant_id: str, property_id: str) -> Dict[str, Decimal]:
    rows = (await db.execute(select(PtxLedger.bucket, func.coalesce(func.sum(PtxLedger.amount), 0))
                             .where(PtxLedger.tenant_id == tenant_id, PtxLedger.property_id == property_id)
                             .group_by(PtxLedger.bucket))).all()
    result = {b: Decimal("0.00") for b in ("PENALTY", "FEE", "ARREAR", "CURRENT", "ADVANCE")}
    for bucket, total in rows:
        result[bucket] = money(total)
    return result


async def bulk_balances(db: AsyncSession, tenant_id: str, ids: List[str]) -> Dict[str, Dict[str, Decimal]]:
    out = {i: {b: Decimal("0.00") for b in ("PENALTY", "FEE", "ARREAR", "CURRENT", "ADVANCE")} for i in ids}
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        rows = (await db.execute(select(PtxLedger.property_id, PtxLedger.bucket, func.coalesce(func.sum(PtxLedger.amount), 0))
                                 .where(PtxLedger.tenant_id == tenant_id, PtxLedger.property_id.in_(chunk))
                                 .group_by(PtxLedger.property_id, PtxLedger.bucket))).all()
        for pid, bucket, total in rows:
            out[pid][bucket] = money(total)
    return out


def dues_total(bal: Dict[str, Decimal]) -> Decimal:
    return money(sum((bal.get(b, Decimal("0")) for b in DUES_BUCKETS), Decimal("0")))


def dues_summary(bal: Dict[str, Decimal]) -> Dict[str, float]:
    total = dues_total(bal)
    advance = money(-bal.get("ADVANCE", 0)) if bal.get("ADVANCE", 0) < 0 else Decimal("0.00")
    return {
        "interest": float(max(bal.get("PENALTY", 0), 0)), "fees": float(max(bal.get("FEE", 0), 0)),
        "arrears": float(max(bal.get("ARREAR", 0), 0)), "current": float(max(bal.get("CURRENT", 0), 0)),
        "totalDue": float(max(total, Decimal("0"))), "advanceHeld": float(advance),
        "netPayable": float(max(money(total - advance), Decimal("0"))),
    }


async def apply_advance_credit(db: AsyncSession, actor, prop: PtxProperty, order: List[str], narration: str) -> Decimal:
    """Uses advance credit held on a property against its dues, in allocation order."""
    bal = await balances(db, prop.tenant_id, prop.id)
    credit = money(-bal["ADVANCE"]) if bal["ADVANCE"] < 0 else Decimal("0.00")
    used = Decimal("0.00")
    for bucket in order:
        due = bal.get(bucket, Decimal("0"))
        if credit <= 0:
            break
        if due <= 0:
            continue
        take = min(credit, due)
        await post_ledger(db, actor, prop=prop, txn_type="TRANSFER", component="ADVANCE", bucket="ADVANCE", amount=take, narration=narration)
        await post_ledger(db, actor, prop=prop, txn_type="TRANSFER", component=BUCKET_COMPONENT[bucket], bucket=bucket, amount=-take, narration=narration)
        credit, used = money(credit - take), money(used + take)
    return used


# ------------------------------------------------------------------------------------------------
# Lookups and pagination
# ------------------------------------------------------------------------------------------------

async def load_property(db: AsyncSession, ctx: PtxContext, *, upin: Optional[str] = None, property_id: Optional[str] = None,
                        for_update: bool = False) -> PtxProperty:
    stmt = select(PtxProperty).where(PtxProperty.tenant_id == ctx.tenant_id)
    if ctx.sub_tenant_id:
        stmt = stmt.where(or_(PtxProperty.sub_tenant_id == ctx.sub_tenant_id, PtxProperty.sub_tenant_id.is_(None)))
    if upin:
        stmt = stmt.where(PtxProperty.upin == upin.strip().upper())
    elif property_id:
        stmt = stmt.where(PtxProperty.id == property_id)
    else:
        raise HTTPException(status_code=400, detail="Property number (UPIN) is required.")
    if for_update:
        stmt = stmt.with_for_update()
    prop = await db.scalar(stmt)
    if prop is None:
        raise HTTPException(status_code=404, detail=f"No property found with number '{upin or property_id}'. Check the number on your tax bill and try again.")
    ctx.ensure_scope(prop.ward_id)
    return prop


async def ward_maps(db: AsyncSession, tenant_id: str):
    rows = (await db.execute(select(Ward.id, Ward.ward_number, Ward.ward_name, Ward.zone_id, Zone.code, Zone.name)
                             .join(Zone, Zone.id == Ward.zone_id).where(Ward.tenant_id == tenant_id))).all()
    wards = {r[0]: {"wardId": r[0], "wardNumber": r[1], "wardName": r[2], "zoneId": r[3], "zoneCode": r[4], "zoneName": r[5]} for r in rows}
    zones: Dict[str, Dict] = {}
    for w in wards.values():
        zones.setdefault(w["zoneId"], {"zoneId": w["zoneId"], "zoneCode": w["zoneCode"], "zoneName": w["zoneName"]})
    return wards, zones


async def locality_map(db: AsyncSession, tenant_id: str) -> Dict[str, Dict]:
    rows = (await db.execute(select(Locality).where(Locality.tenant_id == tenant_id))).scalars().all()
    return {r.id: {"localityId": r.id, "code": r.locality_code, "name": r.locality_name, "wardId": r.ward_id, "pincode": r.pincode} for r in rows}


async def paginate(db: AsyncSession, stmt, skip: int, limit: int):
    """Returns (rows, total) for list endpoints with search, skip and limit (AGENTS.md 3.1)."""
    total = await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = (await db.execute(stmt.offset(skip).limit(limit))).all()
    return rows, total


def page(items: List[Any], total: int, skip: int, limit: int) -> Dict:
    return {"items": items, "total": total, "skip": skip, "limit": limit}


def bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def conflict(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def not_found(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)
