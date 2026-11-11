"""
Shared plumbing for the Water & Utility Billing API: request context (tenant, user, ward/zone scope),
permissions, versioned settings, number series, ledger, audit trail, events and notifications.
"""
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
from sqlalchemy import and_, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_tenant, get_current_user
from app.core.permission_overrides import get_overrides
from app.core.water_calc import DUES_BUCKETS, money
from app.db.models import User, Ward, Zone
from app.db.session import AsyncWriteSessionLocal, get_read_db
from app.db.water_models import (
    WaterApiLog, WaterAuditLog, WaterConnection, WaterCounter, WaterEvent, WaterLedger,
    WaterNotification, WaterSetting, WaterTimeline, utcnow,
)

logger = logging.getLogger("urban-water")

# ------------------------------------------------------------------------------------------------
# Roles and permissions (WB-NF-10)
# ------------------------------------------------------------------------------------------------

ADMIN = {"super_admin", "system_admin"}
COMMISSIONER = {"commissioner"}
OFFICER = {"water_officer", "revenue_officer"}  # revenue officers carry WTR in ROLE_DEFAULT_MODULES
CASHIER = {"cashier"}
READER = {"meter_reader"}
FIELD = {"water_field_staff"}
CSC = {"csc_operator"}
CITIZEN = {"citizen"}
STAFF = ADMIN | COMMISSIONER | OFFICER | CASHIER | READER | FIELD | CSC
UNSCOPED_ROLES = ADMIN | COMMISSIONER

PERMISSIONS: Dict[str, Set[str]] = {
    "connection.view": STAFF,
    "connection.edit": OFFICER,
    "application.create": OFFICER | CSC | CITIZEN,
    "application.view": STAFF,
    "meter.manage": OFFICER | FIELD,
    "route.manage": OFFICER,
    "reading.capture": READER | FIELD | OFFICER,
    "reading.self": CITIZEN | CSC,
    "reading.review": OFFICER,
    "tariff.view": STAFF,
    "tariff.propose": ADMIN | OFFICER,
    "tariff.approve": COMMISSIONER,
    "billing.run": OFFICER,
    "billing.view": STAFF,
    "payment.collect": CASHIER | FIELD | CSC | OFFICER,
    "payment.online": STAFF | CITIZEN,
    "payment.cheque_return": CASHIER,
    "payment.reconcile": CASHIER,
    "dayclose.submit": CASHIER | FIELD | CSC | OFFICER,
    "dayclose.verify": CASHIER,
    "approval.request": OFFICER | CASHIER,
    "approval.decide": OFFICER | COMMISSIONER,
    "arrears.manage": OFFICER,
    "field.execute": FIELD | OFFICER,
    "complaint.create": STAFF | CITIZEN,
    "complaint.work": FIELD | OFFICER,
    "illegal.report": STAFF | CITIZEN,
    "illegal.process": FIELD | OFFICER,
    "reports.view": OFFICER | COMMISSIONER | CASHIER,
    "settings.manage": ADMIN,
    "audit.view": ADMIN | COMMISSIONER,
    "migration.run": ADMIN,
}


@dataclass
class WaterContext:
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
        if self.roles & ADMIN:  # the platform admin bypass is absolute and never overridable
            return True
        overrides = self.extra.get("overrides", {}).get(permission, {})
        defaults = PERMISSIONS.get(permission, set())
        for role in self.roles:
            if role in overrides:
                if overrides[role]:
                    return True
            elif role in defaults:
                return True
        return False

    def require(self, permission: str) -> None:
        if not self.can(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Your role does not allow this action ({permission}). Ask the water section administrator for access.",
            )

    def in_scope(self, ward_id: Optional[str]) -> bool:
        return self.allowed_ward_ids is None or (ward_id is not None and ward_id in self.allowed_ward_ids)

    def ensure_scope(self, ward_id: Optional[str]) -> None:
        if not self.in_scope(ward_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This record is outside your assigned area ({self.scope_label}).",
            )

    def ward_filter(self, column):
        """SQL condition limiting a ward_id column to the user's area (WB-NF-10)."""
        if self.allowed_ward_ids is None:
            return true()
        return column.in_(list(self.allowed_ward_ids) or ["__none__"])


def _parse_number(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    digits = "".join(ch for ch in str(text) if ch.isdigit())
    return int(digits) if digits else None


async def water_context(
    request: Request,
    tenant_id: str = Depends(get_current_tenant),
    user: Dict = Depends(get_current_user),
    x_sub_tenant_id: Optional[str] = Header(None, alias="X-Sub-Tenant-ID"),
    db: AsyncSession = Depends(get_read_db),
) -> WaterContext:
    roles = set(user.get("realm_access", {}).get("roles", []) or [])
    if user.get("role"):
        roles.add(user["role"])
    username = user.get("preferred_username") or user.get("email") or user.get("sub") or "unknown"
    ip = request.client.host if request.client else None
    ctx = WaterContext(
        tenant_id=tenant_id,
        sub_tenant_id=(x_sub_tenant_id or "").strip().upper() or None,
        user=user,
        username=username,
        roles=roles,
        ip=ip,
    )
    ctx.extra["overrides"] = await get_overrides(db, tenant_id, "WTR")
    request.state.water_caller = username
    request.state.water_tenant = tenant_id

    if not (roles & UNSCOPED_ROLES) and not (roles <= CITIZEN):
        ward_ref = user.get("assigned_ward")
        zone_ref = user.get("assigned_zone")
        if not ward_ref and not zone_ref:
            # platform tokens do not carry the area; read it from the user record
            account = (await db.execute(
                select(User.assigned_ward, User.assigned_zone).where(User.username == username)
            )).first()
            if account:
                ward_ref, zone_ref = account
        if ward_ref or zone_ref:
            wards = (await db.execute(
                select(Ward.id, Ward.ward_number, Zone.code, Zone.name)
                .join(Zone, Zone.id == Ward.zone_id)
                .where(Ward.tenant_id == tenant_id)
            )).all()
            allowed: Set[str] = set()
            ward_no = _parse_number(ward_ref)
            zone_key = (zone_ref or "").strip().lower()
            zone_no = _parse_number(zone_ref)
            for ward_id, number, zone_code, zone_name in wards:
                if ward_ref and ward_no is not None and number == ward_no:
                    allowed.add(ward_id)
                elif not ward_ref and zone_ref and (
                    zone_key in {(zone_code or "").lower(), (zone_name or "").lower()}
                    or (zone_no is not None and _parse_number(zone_code) == zone_no)
                ):
                    allowed.add(ward_id)
            ctx.allowed_ward_ids = allowed
            ctx.scope_label = ward_ref or zone_ref
    return ctx


class WaterAPIRoute(APIRoute):
    """Logs every Water API call with time, caller and result (WB-IR-11)."""

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
                caller = getattr(request.state, "water_caller", None)
                tenant = getattr(request.state, "water_tenant", None) or request.headers.get("X-Tenant-ID")
                logger.info("WTR-API %s %s caller=%s status=%s %sms", request.method, request.url.path, caller, status_code, duration)
                try:
                    async with AsyncWriteSessionLocal() as log_db:
                        log_db.add(WaterApiLog(
                            tenant_id=tenant, caller=caller, method=request.method,
                            path=request.url.path[:300], status_code=status_code, duration_ms=duration,
                        ))
                        await log_db.commit()
                except Exception as exc:  # logging must never break the call itself
                    logger.warning("Could not write water API log: %s", exc)

        return handler


# ------------------------------------------------------------------------------------------------
# Versioned settings (SRS 2.5, 3.4, WB-NF-50)
# ------------------------------------------------------------------------------------------------

_OFFICER_ROLES = sorted(OFFICER)
_FIELD_ROLES = sorted(FIELD | OFFICER)

DEFAULT_SETTINGS: Dict[str, Any] = {
    # Placeholder values pending GWMC's written rates (SRS Appendix A, items 2-5, 9, 10).
    "billing.cycleMonths": 1,
    "billing.dueDays": 15,
    "billing.averageMethod": {"type": "LAST_N_ACTUAL", "n": 3},
    "reading.checks": {"highPercent": 100, "lowPercent": 50, "minHistory": 1, "n": 3, "zeroBaseHighKl": 10},
    "reading.noReadingReasons": ["DOOR_LOCKED", "METER_FAULTY", "METER_MISSING", "METER_NOT_ACCESSIBLE", "READING_NOT_VISIBLE"],
    "payment.allocationOrder": ["PENALTY", "FEE", "ARREAR", "CURRENT"],
    "penalty": {"percent": 2.0, "graceDays": 0},
    "disconnection": {"thresholdAmount": 5000, "thresholdDays": 90, "noticeDays": 15},
    "reconnection": {"fee": 500, "slaHours": 48},
    "fees.connection": {
        "byPipeSizeMm": {"15": 3000, "20": 5000, "25": 8000, "40": 15000, "50": 25000},
        "roadCuttingPerMetre": 1200,
        "depositByCategory": {"DOMESTIC": 2000, "NON_DOMESTIC": 5000, "INDUSTRIAL": 15000, "BULK": 25000},
    },
    "fees.chequeReturnCharge": 300,
    "fees.regularisationPenalty": {"DOMESTIC": 5000, "NON_DOMESTIC": 10000, "INDUSTRIAL": 25000, "BULK": 25000},
    "connection.duplicateRadiusM": 15,
    "complaint.slaHours": {"LEAK": 24, "NO_SUPPLY": 12, "DIRTY_WATER": 24, "METER": 72, "BILLING": 72, "OTHER": 72},
    "complaint.assignment": {"default": "water.fieldstaff@gwmc.gov.in", "byWardNumber": {}},
    "complaint.escalation": ["water.officer@gwmc.gov.in", "commissioner@gwmc.gov.in"],
    "approval.limits": {"water_officer": 10000, "revenue_officer": 10000, "commissioner": None},
    "accountHeads": {
        "WATER_CHARGE": "AH-WTR-1101", "FIXED_CHARGE": "AH-WTR-1102", "CESS": "AH-WTR-1103",
        "ARREAR": "AH-WTR-1104", "PENALTY": "AH-WTR-1201", "FEES": "AH-WTR-1300", "CONNECTION_FEE": "AH-WTR-1301",
        "ROAD_CUTTING": "AH-WTR-1302", "RECONNECTION_FEE": "AH-WTR-1303", "CHEQUE_RETURN_CHARGE": "AH-WTR-1304",
        "REGULARISATION_PENALTY": "AH-WTR-1305", "DEPOSIT": "AH-WTR-3401", "ADVANCE": "AH-WTR-3402",
        "WAIVER": "AH-WTR-2101", "WRITE_OFF": "AH-WTR-2102", "ADJUSTMENT": "AH-WTR-2103", "REFUND": "AH-WTR-3403",
    },
    "reminders": {"daysBeforeDue": 3, "daysAfterDue": [1, 7]},
    "analysis": {"zeroCycles": 3, "suddenChangePercent": 100, "outlierFactor": 2.0},
    "collection.annualTarget": 2500000,
    "upi": {"vpa": "gwmc.water@placeholder", "payeeName": "GWMC Water Supply"},
    "integrationLinks": {
        "I-05": {"module": "Property Tax & Revenue (Module 1)", "direction": "To Module 2", "enabled": False},
        "I-09": {"module": "Finance & Accounting (Module 4)", "direction": "From Module 2", "enabled": False},
        "GRV": {"module": "Citizen Grievance (Module 3)", "direction": "From Module 2", "enabled": False},
        "INV": {"module": "Inventory & Stores (Module 17)", "direction": "To Module 2", "enabled": False},
        "HRM": {"module": "Payroll & HR (Module 8)", "direction": "To Module 2", "enabled": False},
        "DMS": {"module": "Document Management (Module 9)", "direction": "From Module 2", "enabled": False},
        "LGL": {"module": "Legal Case Management (Module 16)", "direction": "From Module 2", "enabled": False},
    },
    "reports.schedule": [
        {"report": "DCB", "frequency": "MONTHLY", "format": "PDF", "recipients": ["accounts@gwmc.gov.in"]},
        {"report": "ACCOUNT_HEADS", "frequency": "DAILY", "format": "EXCEL", "recipients": ["accounts@gwmc.gov.in"]},
    ],
    "session.staffTimeoutMinutes": 15,
    "workflow": {
        "NEW_CONNECTION": [
            {"code": "PTAX_DUES_CHECK", "label": "Property tax dues check (link I-05)", "slaHours": 24, "roles": _OFFICER_ROLES, "enabled": False},
            {"code": "DOC_CHECK", "label": "Document and duplicate check", "slaHours": 48, "roles": _OFFICER_ROLES, "enabled": True},
            {"code": "SITE_INSPECTION", "label": "Site inspection", "slaHours": 72, "roles": _FIELD_ROLES, "enabled": True},
            {"code": "ESTIMATE_PAYMENT", "label": "Estimate and payment", "slaHours": 168, "roles": _OFFICER_ROLES, "enabled": True},
            {"code": "WORK_ORDER", "label": "Work order: lay connection, fix meter", "slaHours": 168, "roles": _FIELD_ROLES, "enabled": True},
            {"code": "ACTIVATION", "label": "Activation", "slaHours": 24, "roles": _OFFICER_ROLES, "enabled": True},
        ],
        "OWNER_CHANGE": [
            {"code": "DOC_CHECK", "label": "Ownership document check", "slaHours": 72, "roles": _OFFICER_ROLES, "enabled": True},
            {"code": "APPROVAL", "label": "Approval", "slaHours": 48, "roles": _OFFICER_ROLES, "enabled": True},
        ],
        "CATEGORY_CHANGE": [
            {"code": "SITE_INSPECTION", "label": "Site inspection", "slaHours": 72, "roles": _FIELD_ROLES, "enabled": True},
            {"code": "APPROVAL", "label": "Approval", "slaHours": 48, "roles": _OFFICER_ROLES, "enabled": True},
        ],
        "PIPE_SIZE_CHANGE": [
            {"code": "SITE_INSPECTION", "label": "Site inspection", "slaHours": 72, "roles": _FIELD_ROLES, "enabled": True},
            {"code": "ESTIMATE_PAYMENT", "label": "Estimate and payment", "slaHours": 168, "roles": _OFFICER_ROLES, "enabled": True},
            {"code": "APPROVAL", "label": "Approval and work completion", "slaHours": 72, "roles": _OFFICER_ROLES, "enabled": True},
        ],
        "TEMP_DISCONNECTION": [
            {"code": "APPROVAL", "label": "Approval", "slaHours": 48, "roles": _OFFICER_ROLES, "enabled": True},
            {"code": "FIELD_EXECUTION", "label": "Field disconnection", "slaHours": 72, "roles": _FIELD_ROLES, "enabled": True},
        ],
        "TEMP_RECONNECTION": [
            {"code": "APPROVAL", "label": "Approval", "slaHours": 24, "roles": _OFFICER_ROLES, "enabled": True},
            {"code": "FIELD_EXECUTION", "label": "Field reconnection", "slaHours": 48, "roles": _FIELD_ROLES, "enabled": True},
        ],
        "PERM_DISCONNECTION": [
            {"code": "APPROVAL", "label": "Dues clearance and approval", "slaHours": 72, "roles": _OFFICER_ROLES, "enabled": True},
            {"code": "FIELD_EXECUTION", "label": "Field disconnection and meter removal", "slaHours": 72, "roles": _FIELD_ROLES, "enabled": True},
        ],
    },
}

SETTING_DESCRIPTIONS: Dict[str, str] = {
    "billing.cycleMonths": "Billing cycle length in months (must divide 12)",
    "billing.dueDays": "Days from bill date to due date",
    "billing.averageMethod": "Average billing method when no reading (WB-16)",
    "reading.checks": "Reading checks: flag if consumption is above/below usual by these percentages (WB-15)",
    "reading.noReadingReasons": "Reasons a reader can pick when no reading is taken (WB-14)",
    "payment.allocationOrder": "Order in which a payment clears dues (WB-32)",
    "penalty": "Late payment penalty, percent of the unpaid bill amount (WB-40)",
    "disconnection": "Disconnection notice threshold and notice period (WB-43)",
    "reconnection": "Reconnection fee and work order SLA (WB-45)",
    "fees.connection": "Connection charges by pipe size, road cutting rate and deposit by category (WB-05)",
    "fees.chequeReturnCharge": "Charge added when a cheque is returned (WB-36)",
    "fees.regularisationPenalty": "Penalty for regularising an illegal connection, by category (WB-53)",
    "connection.duplicateRadiusM": "Warn if another connection lies within this distance (WB-04)",
    "complaint.slaHours": "Complaint SLA in hours by type (WB-51)",
    "complaint.assignment": "Who complaints go to, by ward number (WB-51)",
    "complaint.escalation": "Escalation chain when a complaint or application step passes its SLA",
    "approval.limits": "Highest amount each role may approve; null means no limit (WB-46)",
    "accountHeads": "Account head codes (WB-65, WB-IR-05) - GWMC chart of accounts pending",
    "reminders": "Reminder days before and after due date (WB-42)",
    "analysis": "Consumption analysis thresholds (WB-54, WB-55)",
    "collection.annualTarget": "Year collection target shown on the Commissioner dashboard (WB-64)",
    "upi": "UPI payee printed in the bill QR code (WB-24)",
    "integrationLinks": "Planned links to other modules; all switched off in Release 1 (WB-IR-08)",
    "reports.schedule": "Reports emailed on a schedule (WB-66)",
    "session.staffTimeoutMinutes": "Staff session inactivity timeout (WB-NF-15)",
    "workflow": "Steps, SLAs and roles for each application type (WB-05, WB-06, WB-IR-06)",
}


# Business dates (receipt date, day-end closing, billing cycle of a reading) follow GWMC's local time, IST by default.
# Timestamps themselves are stored in UTC.
BUSINESS_UTC_OFFSET = datetime.timedelta(minutes=int(os.getenv("WATER_TZ_OFFSET_MINUTES", "330")))


def local_date(utc_naive: datetime.datetime) -> datetime.date:
    return (utc_naive + BUSINESS_UTC_OFFSET).date()


def local_day_start_utc(day: datetime.date) -> datetime.datetime:
    """UTC instant at which the given local (IST) day starts."""
    return datetime.datetime.combine(day, datetime.time.min) - BUSINESS_UTC_OFFSET


def today() -> datetime.date:
    return local_date(utcnow())


def to_utc_naive(value: datetime.datetime) -> datetime.datetime:
    """Timestamps are stored as naive UTC; a time sent with an offset (e.g. +05:30 from a phone) is converted, not truncated."""
    if value.tzinfo is not None:
        value = value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return value


async def get_setting(db: AsyncSession, tenant_id: str, key: str, as_of: Optional[datetime.date] = None) -> Any:
    """Value in force on `as_of` (default today); falls back to the shipped default."""
    as_of = as_of or today()
    row = await db.scalar(
        select(WaterSetting)
        .where(WaterSetting.tenant_id == tenant_id, WaterSetting.key == key, WaterSetting.effective_from <= as_of)
        .order_by(WaterSetting.effective_from.desc(), WaterSetting.created_at.desc())
        .limit(1)
    )
    if row is not None:
        return json.loads(row.value_json)
    if key not in DEFAULT_SETTINGS:
        raise KeyError(key)
    return json.loads(json.dumps(DEFAULT_SETTINGS[key]))


async def account_head(db: AsyncSession, tenant_id: str, component: str) -> str:
    heads = await get_setting(db, tenant_id, "accountHeads")
    return heads.get(component) or heads.get("ADJUSTMENT") or "AH-WTR-UNMAPPED"


# ------------------------------------------------------------------------------------------------
# Number series (WB-01: consumer numbers never change and are never reused)
# ------------------------------------------------------------------------------------------------

async def next_number(db: AsyncSession, tenant_id: str, name: str) -> int:
    row = await db.scalar(
        select(WaterCounter).where(WaterCounter.tenant_id == tenant_id, WaterCounter.name == name).with_for_update()
    )
    if row is None:
        row = WaterCounter(tenant_id=tenant_id, name=name, value=0)
        db.add(row)
        await db.flush()
    row.value = (row.value or 0) + 1
    await db.flush()
    return row.value


async def new_consumer_no(db: AsyncSession, tenant_id: str) -> str:
    return f"{tenant_id}-W-{await next_number(db, tenant_id, 'consumer'):07d}"


async def new_doc_no(db: AsyncSession, tenant_id: str, prefix: str, counter: str) -> str:
    stamp = today().strftime("%Y%m")
    return f"{prefix}-{tenant_id}-{stamp}-{await next_number(db, tenant_id, counter):06d}"


# ------------------------------------------------------------------------------------------------
# Audit, events, notifications, timeline
# ------------------------------------------------------------------------------------------------

def _json(value: Any) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, default=str, ensure_ascii=False)


def audit(db: AsyncSession, ctx: WaterContext, action: str, entity_type: str, entity_id: Optional[str],
          old: Any = None, new: Any = None) -> None:
    """Append-only audit record (WB-NF-13)."""
    db.add(WaterAuditLog(
        tenant_id=ctx.tenant_id, actor=ctx.username, ip_address=ctx.ip, action=action,
        entity_type=entity_type, entity_id=entity_id, old_json=_json(old), new_json=_json(new),
    ))


EVENT_TYPES = {
    "connection.created", "connection.changed", "connection.owner_changed", "meter.fixed", "meter.replaced",
    "bill.raised", "payment.received", "receipt.cancelled", "connection.disconnected", "connection.reconnected",
    "complaint.raised", "complaint.closed", "illegal_case.opened", "illegal_case.closed",
}


def emit_event(db: AsyncSession, tenant_id: str, event_type: str, aggregate_id: Optional[str], payload: Dict) -> None:
    """Writes to the event outbox (WB-IR-02). Payload carries only the fields a consumer module needs (WB-NF-23)."""
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unknown water event type {event_type}")
    db.add(WaterEvent(
        tenant_id=tenant_id, event_type=event_type, aggregate_id=aggregate_id,
        payload_json=json.dumps({"eventType": event_type, "tenantId": tenant_id, "occurredAt": utcnow().isoformat(), **payload}, default=str),
    ))


async def notify(db: AsyncSession, tenant_id: str, *, recipient: Optional[str], template: str, message_en: str,
                 message_te: str, connection_id: Optional[str] = None, ref_no: Optional[str] = None,
                 dedupe_key: Optional[str] = None, channel: str = "SMS") -> bool:
    """Queues an SMS/WhatsApp message through the stand-in sender. Returns False if already sent (dedupe)."""
    if dedupe_key:
        exists = await db.scalar(select(WaterNotification.id).where(
            WaterNotification.tenant_id == tenant_id, WaterNotification.dedupe_key == dedupe_key))
        if exists:
            return False
    db.add(WaterNotification(
        tenant_id=tenant_id, channel=channel, recipient=recipient, template=template,
        message_en=message_en, message_te=message_te, connection_id=connection_id, ref_no=ref_no,
        dedupe_key=dedupe_key, status="LOGGED_STAND_IN" if recipient else "NO_RECIPIENT",
    ))
    return True


def timeline(db: AsyncSession, ctx_or_tenant, entity_type: str, entity_id: str, action: str,
             remark: Optional[str] = None, actor: Optional[str] = None) -> None:
    tenant_id = ctx_or_tenant.tenant_id if isinstance(ctx_or_tenant, WaterContext) else ctx_or_tenant
    who = actor or (ctx_or_tenant.username if isinstance(ctx_or_tenant, WaterContext) else "system")
    db.add(WaterTimeline(tenant_id=tenant_id, entity_type=entity_type, entity_id=entity_id,
                         action=action, remark=remark, actor=who))


# ------------------------------------------------------------------------------------------------
# Ledger (WB-IR-05)
# ------------------------------------------------------------------------------------------------

async def post_ledger(db: AsyncSession, ctx_or_user, *, tenant_id: str, connection_id: Optional[str],
                      txn_type: str, component: str, bucket: str, amount, ward_id: Optional[str],
                      application_id: Optional[str] = None, payment_mode: Optional[str] = None,
                      reference_no: Optional[str] = None, bill_id: Optional[str] = None,
                      receipt_id: Optional[str] = None, approval_id: Optional[str] = None,
                      narration: Optional[str] = None, entry_date: Optional[datetime.date] = None,
                      is_reversal: bool = False, reversal_of_id: Optional[str] = None) -> WaterLedger:
    value = money(amount)
    if value == 0:
        raise ValueError("Ledger entries cannot be zero.")
    actor = ctx_or_user.username if isinstance(ctx_or_user, WaterContext) else str(ctx_or_user)
    entry = WaterLedger(
        tenant_id=tenant_id, connection_id=connection_id, application_id=application_id, ward_id=ward_id,
        entry_date=entry_date or today(), txn_type=txn_type, component=component, bucket=bucket,
        account_head=await account_head(db, tenant_id, component), amount=value, payment_mode=payment_mode,
        reference_no=reference_no, bill_id=bill_id, receipt_id=receipt_id, approval_id=approval_id,
        is_reversal=is_reversal, reversal_of_id=reversal_of_id, narration=narration, created_by=actor,
    )
    db.add(entry)
    return entry


async def balances(db: AsyncSession, tenant_id: str, *, connection_id: Optional[str] = None,
                   application_id: Optional[str] = None) -> Dict[str, Decimal]:
    cond = [WaterLedger.tenant_id == tenant_id]
    if connection_id:
        cond.append(WaterLedger.connection_id == connection_id)
    elif application_id:
        cond.append(and_(WaterLedger.application_id == application_id, WaterLedger.connection_id.is_(None)))
    else:
        raise ValueError("connection_id or application_id is required")
    rows = (await db.execute(
        select(WaterLedger.bucket, func.coalesce(func.sum(WaterLedger.amount), 0)).where(*cond).group_by(WaterLedger.bucket)
    )).all()
    result = {b: Decimal("0.00") for b in ("PENALTY", "FEE", "ARREAR", "CURRENT", "ADVANCE", "DEPOSIT")}
    for bucket, total in rows:
        result[bucket] = money(total)
    return result


def dues_total(bal: Dict[str, Decimal]) -> Decimal:
    return money(sum((bal.get(b, Decimal("0")) for b in DUES_BUCKETS), Decimal("0")))


def dues_summary(bal: Dict[str, Decimal]) -> Dict[str, float]:
    """Dues as shown to users: what is owed, advance held and deposit held (all positive numbers)."""
    total = dues_total(bal)
    advance = money(-bal.get("ADVANCE", 0)) if bal.get("ADVANCE", 0) < 0 else Decimal("0.00")
    deposit = money(-bal.get("DEPOSIT", 0)) if bal.get("DEPOSIT", 0) < 0 else Decimal("0.00")
    return {
        "penalty": float(max(bal.get("PENALTY", 0), 0)),
        "fees": float(max(bal.get("FEE", 0), 0)),
        "arrears": float(max(bal.get("ARREAR", 0), 0)),
        "current": float(max(bal.get("CURRENT", 0), 0)),
        "totalDue": float(max(total, Decimal("0"))),
        "advanceHeld": float(advance),
        "depositHeld": float(deposit),
        "netPayable": float(max(money(total - advance), Decimal("0"))),
    }


async def apply_advance_credit(db: AsyncSession, ctx_or_user, conn: WaterConnection, order: List[str],
                               narration: str) -> Decimal:
    """Uses advance credit held for a connection against its dues, in allocation order. Returns amount used."""
    bal = await balances(db, conn.tenant_id, connection_id=conn.id)
    credit = money(-bal["ADVANCE"]) if bal["ADVANCE"] < 0 else Decimal("0.00")
    used = Decimal("0.00")
    for bucket in order:
        due = bal.get(bucket, Decimal("0"))
        if credit <= 0:
            break
        if due <= 0:
            continue
        take = min(credit, due)
        await post_ledger(db, ctx_or_user, tenant_id=conn.tenant_id, connection_id=conn.id, txn_type="TRANSFER",
                          component="ADVANCE", bucket="ADVANCE", amount=take, ward_id=conn.ward_id, narration=narration)
        await post_ledger(db, ctx_or_user, tenant_id=conn.tenant_id, connection_id=conn.id, txn_type="TRANSFER",
                          component=_bucket_component(bucket), bucket=bucket, amount=-take, ward_id=conn.ward_id, narration=narration)
        credit = money(credit - take)
        used = money(used + take)
    return used


def _bucket_component(bucket: str) -> str:
    """Account-head component used when money moves in or out of a bucket (collections are booked by bucket)."""
    return {"PENALTY": "PENALTY", "FEE": "FEES", "ARREAR": "ARREAR", "CURRENT": "WATER_CHARGE",
            "ADVANCE": "ADVANCE", "DEPOSIT": "DEPOSIT"}[bucket]


bucket_component = _bucket_component


# ------------------------------------------------------------------------------------------------
# Lookups
# ------------------------------------------------------------------------------------------------

async def load_connection(db: AsyncSession, ctx: WaterContext, *, consumer_no: Optional[str] = None,
                          connection_id: Optional[str] = None, for_update: bool = False) -> WaterConnection:
    stmt = select(WaterConnection).where(WaterConnection.tenant_id == ctx.tenant_id)
    if ctx.sub_tenant_id:
        stmt = stmt.where(or_(WaterConnection.sub_tenant_id == ctx.sub_tenant_id, WaterConnection.sub_tenant_id.is_(None)))
    if consumer_no:
        stmt = stmt.where(WaterConnection.consumer_no == consumer_no.strip().upper())
    elif connection_id:
        stmt = stmt.where(WaterConnection.id == connection_id)
    else:
        raise HTTPException(status_code=400, detail="Consumer number is required.")
    if for_update:
        stmt = stmt.with_for_update()
    conn = await db.scalar(stmt)
    if conn is None:
        raise HTTPException(
            status_code=404,
            detail=f"No water connection found with consumer number '{consumer_no or connection_id}'. Check the number on the bill and try again.",
        )
    ctx.ensure_scope(conn.ward_id)
    return conn


async def ward_maps(db: AsyncSession, tenant_id: str):
    """Returns ({ward_id: {...}}, {zone_id: {...}}) for labelling reports."""
    rows = (await db.execute(
        select(Ward.id, Ward.ward_number, Ward.ward_name, Ward.zone_id, Zone.code, Zone.name)
        .join(Zone, Zone.id == Ward.zone_id)
        .where(Ward.tenant_id == tenant_id)
    )).all()
    wards = {r[0]: {"wardId": r[0], "wardNumber": r[1], "wardName": r[2], "zoneId": r[3], "zoneCode": r[4], "zoneName": r[5]} for r in rows}
    zones = {}
    for w in wards.values():
        zones.setdefault(w["zoneId"], {"zoneId": w["zoneId"], "zoneCode": w["zoneCode"], "zoneName": w["zoneName"]})
    return wards, zones


def bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def conflict(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def not_found(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


def dumps(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)


def loads(text: Optional[str], default: Any = None) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except ValueError:
        return default
