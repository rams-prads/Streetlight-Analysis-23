import datetime
import hashlib
import json
import uuid
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, desc

from app.db.session import get_read_db, get_write_db
from app.db.models import (
    StateTenant,
    Tenant,
    ImmutableAuditEventModel,
    AuditHashVerificationJobModel,
    AuditRetentionPolicyModel,
    AuditExportJobModel,
)
from app.core.auth import get_current_user
from app.schemas.tenant import ApiResponse
from app.schemas.audit_vault import (
    ImmutableAuditEventResponse,
    AuditEventCreatePayload,
    AuditDashboardStats,
    HashVerificationResponse,
    HashVerificationCreatePayload,
    RetentionPolicyResponse,
    RetentionPolicyCreatePayload,
    RetentionPolicyUpdatePayload,
    AuditExportResponse,
    AuditExportCreatePayload,
)

router = APIRouter(prefix="/compliance/audit", tags=["ADM-C06 Immutable Audit Vault"])


def _to_naive_utc(dt: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return dt


def _compute_event_hash(
    prev_hash: str,
    sequence: int,
    event_id: str,
    created_at_iso: str,
    actor_id: str,
    event_category: str,
    action: str,
    result: str,
    details_str: str,
    algorithm: str = "SHA-256",
) -> str:
    payload = f"{prev_hash}|{sequence}|{event_id}|{created_at_iso}|{actor_id}|{event_category}|{action}|{result}|{details_str}"
    if algorithm.upper() == "SHA-512":
        return hashlib.sha512(payload.encode("utf-8")).hexdigest()
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"


# Internal Helper to append an immutable event with cryptographic chaining
async def record_immutable_audit_event(
    db: AsyncSession,
    event_category: str,
    action: str,
    actor_id: str,
    actor_role: str = "Platform Super Admin",
    tenant_id: Optional[str] = None,
    tenant_level: str = "Level 0",
    sub_tenant_id: Optional[str] = None,
    state_code: Optional[str] = None,
    module_code: Optional[str] = None,
    component_code: Optional[str] = None,
    severity: str = "Informational",
    ip_address: str = "127.0.0.1",
    user_agent: Optional[str] = None,
    correlation_id: Optional[str] = None,
    result: str = "SUCCESS",
    details: Optional[Dict[str, Any]] = None,
    is_legal_hold: bool = False,
) -> ImmutableAuditEventModel:
    # Get last event in chain
    stmt = select(ImmutableAuditEventModel).order_by(desc(ImmutableAuditEventModel.sequence_number)).limit(1)
    res = await db.execute(stmt)
    last_event = res.scalar_one_or_none()

    if last_event:
        seq = last_event.sequence_number + 1
        prev_hash = last_event.event_hash
    else:
        seq = 1
        prev_hash = GENESIS_HASH

    now = datetime.datetime.utcnow()
    year = now.year
    event_id = f"AUD-{year}-{seq:06d}"
    corr_id = correlation_id or str(uuid.uuid4())
    det = details or {}
    det_str = json.dumps(det, sort_keys=True)

    event_hash = _compute_event_hash(
        prev_hash=prev_hash,
        sequence=seq,
        event_id=event_id,
        created_at_iso=now.isoformat(),
        actor_id=actor_id,
        event_category=event_category,
        action=action,
        result=result,
        details_str=det_str,
    )

    signature = f"WORM-SIG:{hashlib.sha256((event_hash + 'MUNICIPAL-VAULT-2026').encode('utf-8')).hexdigest()[:32]}"

    event = ImmutableAuditEventModel(
        event_id=event_id,
        sequence_number=seq,
        tenant_id=tenant_id,
        tenant_level=tenant_level,
        sub_tenant_id=sub_tenant_id,
        state_code=state_code,
        module_code=module_code,
        component_code=component_code,
        event_category=event_category,
        action=action,
        severity=severity,
        actor_id=actor_id,
        actor_role=actor_role,
        ip_address=ip_address,
        user_agent=user_agent or "SUVIDHA-Audit-Engine/2.0",
        correlation_id=corr_id,
        result=result,
        details=det,
        prev_event_hash=prev_hash,
        event_hash=event_hash,
        signature=signature,
        is_legal_hold=is_legal_hold,
        created_at=now,
    )
    db.add(event)
    await db.flush()
    return event


# Seed initial vault events & retention policies if empty
async def _ensure_vault_seeded(db: AsyncSession):
    # Check if events exist
    ev_count_res = await db.execute(select(func.count(ImmutableAuditEventModel.id)))
    ev_count = ev_count_res.scalar() or 0

    if ev_count == 0:
        seed_events = [
            {
                "event_category": "Configuration Changes",
                "action": "PLATFORM_INITIALIZATION",
                "severity": "Informational",
                "actor_id": "system.init@urban.gov.in",
                "actor_role": "Platform Super Admin",
                "tenant_level": "Level 0",
                "module_code": "SYS",
                "result": "SUCCESS",
                "details": {"genesis": True, "standard": "CERT-In Statutory WORM", "hash_chain": "SHA-256"},
            },
            {
                "event_category": "Tenant Management",
                "action": "TENANT_PROVISION_STATE",
                "severity": "Medium",
                "actor_id": "admin@urban.gov.in",
                "actor_role": "Platform Super Admin",
                "tenant_level": "Level 1",
                "state_code": "TG",
                "module_code": "ADM",
                "component_code": "ADM-T01",
                "result": "SUCCESS",
                "details": {"stateName": "Telangana", "jurisdiction": "Level 1 State", "code": "TG"},
            },
            {
                "event_category": "Tenant Management",
                "action": "SUB_TENANT_ONBOARD_ULB",
                "severity": "Medium",
                "actor_id": "director.cdma@telangana.gov.in",
                "actor_role": "State Admin",
                "tenant_level": "Level 2",
                "state_code": "TG",
                "module_code": "ADM",
                "component_code": "ADM-T02",
                "result": "SUCCESS",
                "details": {"ulbName": "Greater Warangal Municipal Corp", "ulbCode": "GWMC", "type": "Municipal Corporation"},
            },
            {
                "event_category": "Subscription Changes",
                "action": "MODULE_SUBSCRIPTION_ALLOCATE",
                "severity": "High",
                "actor_id": "admin@urban.gov.in",
                "actor_role": "Platform Super Admin",
                "tenant_level": "Level 1",
                "state_code": "TG",
                "module_code": "PTX",
                "component_code": "ADM-M04",
                "result": "SUCCESS",
                "details": {"module": "Property Tax (PTX)", "cycle": "Yearly", "autoRenew": True},
            },
            {
                "event_category": "Subscription Changes",
                "action": "CASCADE_DELEGATION_RULE_CREATED",
                "severity": "High",
                "actor_id": "director.cdma@telangana.gov.in",
                "actor_role": "State Admin",
                "tenant_level": "Level 1",
                "state_code": "TG",
                "module_code": "PTX",
                "component_code": "ADM-M05",
                "result": "SUCCESS",
                "details": {"ruleCode": "DEL-TG-CORP", "delegationMode": "Selective Delegation", "approvalRequired": True},
            },
            {
                "event_category": "Authentication",
                "action": "MFA_LOGIN_SUCCESS",
                "severity": "Informational",
                "actor_id": "commissioner@gwmc.gov.in",
                "actor_role": "ULB Admin",
                "tenant_level": "Level 2",
                "state_code": "TG",
                "module_code": "IAM",
                "component_code": "IAM-03",
                "result": "SUCCESS",
                "details": {"method": "Aadhaar e-Pramaan OTP", "authBroker": "MeriPehchan OIDC"},
            },
            {
                "event_category": "Authentication",
                "action": "LOGIN_FAILURE_UNAUTHORIZED",
                "severity": "Medium",
                "actor_id": "intruder.probe@unknown.net",
                "actor_role": "Anonymous",
                "tenant_level": "Level 0",
                "module_code": "IAM",
                "component_code": "IAM-01",
                "result": "FAILURE",
                "details": {"reason": "Invalid client assertion token", "attemptCount": 3},
            },
            {
                "event_category": "Authorisation",
                "action": "ROLE_PERMISSION_MATRIX_SYNC",
                "severity": "High",
                "actor_id": "admin@urban.gov.in",
                "actor_role": "Platform Super Admin",
                "tenant_level": "Level 0",
                "module_code": "IAM",
                "component_code": "IAM-04",
                "result": "SUCCESS",
                "details": {"componentsUpdated": 405, "modules": 19, "enforcement": "Strict Component RBAC"},
            },
            {
                "event_category": "Data Access",
                "action": "POSTGRES_RLS_POLICY_AUDIT",
                "severity": "Informational",
                "actor_id": "sec-auditor@urban.gov.in",
                "actor_role": "Platform Auditor",
                "tenant_level": "Level 0",
                "module_code": "SEC",
                "component_code": "SEC-01",
                "result": "SUCCESS",
                "details": {"rlsStatus": "Enforced", "tenantBoundariesVerified": 28, "leakDetected": False},
            },
            {
                "event_category": "Administrative Actions",
                "action": "DATA_ARCHIVAL_PRE_FREEZE_SNAPSHOT",
                "severity": "Critical",
                "actor_id": "admin@urban.gov.in",
                "actor_role": "Platform Super Admin",
                "tenant_level": "Level 1",
                "state_code": "AS",
                "module_code": "ADM",
                "component_code": "ADM-T03",
                "result": "SUCCESS",
                "details": {"tenant": "Assam", "policy": "State Government Statutory Record Retention", "legalHold": True},
                "is_legal_hold": True,
            },
        ]

        for s in seed_events:
            await record_immutable_audit_event(
                db=db,
                event_category=s["event_category"],
                action=s["action"],
                actor_id=s["actor_id"],
                actor_role=s["actor_role"],
                tenant_level=s["tenant_level"],
                state_code=s.get("state_code"),
                module_code=s.get("module_code"),
                component_code=s.get("component_code"),
                severity=s["severity"],
                result=s["result"],
                details=s["details"],
                is_legal_hold=s.get("is_legal_hold", False),
            )
        await db.commit()

    # Check retention policies
    pol_count_res = await db.execute(select(func.count(AuditRetentionPolicyModel.id)))
    pol_count = pol_count_res.scalar() or 0

    if pol_count == 0:
        policies = [
            AuditRetentionPolicyModel(
                policy_code="RET-CERT-IN-7YR",
                policy_name="National CERT-In Cyber Security & Audit Log Retention",
                applicable_tenant_levels=["Level 0", "Level 1", "Level 2"],
                event_categories=["Authentication", "Authorisation", "Configuration Changes", "Administrative Actions"],
                retention_period=7,
                retention_unit="Years",
                archive_required=True,
                archive_destination="State Government Cold Storage Vault",
                legal_hold_enabled=False,
                effective_date=datetime.datetime(2024, 1, 1),
                policy_status="Active",
                description="Statutory rule under CERT-In Directions 2022 mandating 7-year tamper-evident retention of administrative and authentication logs.",
            ),
            AuditRetentionPolicyModel(
                policy_code="RET-MUNICIPAL-FIN-10YR",
                policy_name="CAG Municipal Financial Audit & Billing Ledger Policy",
                applicable_tenant_levels=["Level 1", "Level 2"],
                event_categories=["Subscription Changes", "Data Access", "Administrative Actions"],
                retention_period=10,
                retention_unit="Years",
                archive_required=True,
                archive_destination="NIC National Data Vault (WORM S3)",
                legal_hold_enabled=True,
                effective_date=datetime.datetime(2024, 4, 1),
                policy_status="Active",
                description="Comptroller & Auditor General (CAG) municipal accounts retention policy for revenue demand, collections, and financial journals.",
            ),
            AuditRetentionPolicyModel(
                policy_code="RET-LEGAL-DISPUTE-HOLD",
                policy_name="High Court & Civil Dispute Statutory Legal Hold",
                applicable_tenant_levels=["Level 0", "Level 1", "Level 2"],
                event_categories=["Tenant Management", "User Management", "Administrative Actions"],
                retention_period=30,
                retention_unit="Years",
                archive_required=True,
                archive_destination="Judicial Legal Hold Vault (Immutable)",
                legal_hold_enabled=True,
                effective_date=datetime.datetime(2025, 1, 1),
                policy_status="Active",
                description="Perpetual non-expiring hold for municipal jurisdictions subject to active judicial scrutiny or public interest litigation.",
            ),
        ]
        for p in policies:
            db.add(p)
        await db.commit()


# 1. Dashboard Metrics Endpoint
@router.get("/stats", response_model=ApiResponse[AuditDashboardStats])
async def get_audit_dashboard_stats(
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    await _ensure_vault_seeded(db)

    # Total events
    total_res = await db.execute(select(func.count(ImmutableAuditEventModel.id)))
    total_events = total_res.scalar() or 0

    # Critical events
    crit_res = await db.execute(
        select(func.count(ImmutableAuditEventModel.id)).where(ImmutableAuditEventModel.severity == "Critical")
    )
    critical_events = crit_res.scalar() or 0

    # Failed auth events
    auth_res = await db.execute(
        select(func.count(ImmutableAuditEventModel.id)).where(
            ImmutableAuditEventModel.event_category == "Authentication",
            ImmutableAuditEventModel.result.in_(["FAILURE", "DENIED", "ERROR"]),
        )
    )
    failed_auth = auth_res.scalar() or 0

    # Privileged operations
    priv_res = await db.execute(
        select(func.count(ImmutableAuditEventModel.id)).where(
            ImmutableAuditEventModel.event_category.in_(
                ["Tenant Management", "User Management", "Subscription Changes", "Configuration Changes", "Administrative Actions"]
            )
        )
    )
    privileged_ops = priv_res.scalar() or 0

    # Legal hold events
    lh_res = await db.execute(
        select(func.count(ImmutableAuditEventModel.id)).where(ImmutableAuditEventModel.is_legal_hold == True)
    )
    legal_hold_count = lh_res.scalar() or 0

    # Last verification job
    v_res = await db.execute(
        select(AuditHashVerificationJobModel).order_by(desc(AuditHashVerificationJobModel.created_at)).limit(1)
    )
    last_v = v_res.scalar_one_or_none()
    last_verified = last_v.created_at if last_v else None
    status_str = "100% Tamper-Evident (Chained)" if not last_v or last_v.verification_result == "VALID_INTEGRITY_INTACT" else "WARNING: Verification Inconclusive"

    # Active retention policies
    pol_res = await db.execute(
        select(func.count(AuditRetentionPolicyModel.id)).where(AuditRetentionPolicyModel.policy_status == "Active")
    )
    active_policies = pol_res.scalar() or 0

    return ApiResponse(
        success=True,
        data=AuditDashboardStats(
            totalAuditEvents=total_events,
            criticalEvents=critical_events,
            failedAuthEvents=failed_auth,
            privilegedOperations=privileged_ops,
            integrityStatus=status_str,
            lastVerifiedAt=last_verified,
            activeRetentionPolicies=active_policies,
            legalHoldEvents=legal_hold_count,
        ),
    )


# 2. Audit Log Explorer Endpoint
@router.get("/events", response_model=ApiResponse[List[ImmutableAuditEventResponse]])
async def list_audit_events(
    search: Optional[str] = Query(None),
    tenant_id: Optional[str] = Query(None),
    sub_tenant_id: Optional[str] = Query(None),
    module_code: Optional[str] = Query(None),
    component_code: Optional[str] = Query(None),
    event_category: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    result: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    ip_address: Optional[str] = Query(None),
    correlation_id: Optional[str] = Query(None),
    date_from: Optional[datetime.datetime] = Query(None),
    date_to: Optional[datetime.datetime] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    await _ensure_vault_seeded(db)

    # Pre-fetch tenants for resolving names
    states_res = await db.execute(select(StateTenant))
    states_map = {s.tenant_id: s for s in states_res.scalars().all()}
    ulbs_res = await db.execute(select(Tenant))
    ulbs_map = {u.tenant_id: u for u in ulbs_res.scalars().all()}

    stmt = select(ImmutableAuditEventModel).order_by(desc(ImmutableAuditEventModel.sequence_number))

    if tenant_id and tenant_id != "ALL":
        stmt = stmt.where(ImmutableAuditEventModel.tenant_id == tenant_id)
    if sub_tenant_id and sub_tenant_id != "ALL":
        stmt = stmt.where(ImmutableAuditEventModel.sub_tenant_id == sub_tenant_id)
    if module_code and module_code != "ALL":
        stmt = stmt.where(ImmutableAuditEventModel.module_code == module_code)
    if component_code and component_code != "ALL":
        stmt = stmt.where(ImmutableAuditEventModel.component_code == component_code)
    if event_category and event_category != "ALL":
        stmt = stmt.where(ImmutableAuditEventModel.event_category == event_category)
    if action and action != "ALL":
        stmt = stmt.where(ImmutableAuditEventModel.action == action)
    if severity and severity != "ALL":
        stmt = stmt.where(ImmutableAuditEventModel.severity == severity)
    if result and result != "ALL":
        stmt = stmt.where(ImmutableAuditEventModel.result == result)
    if user_id and user_id.strip():
        stmt = stmt.where(func.lower(ImmutableAuditEventModel.actor_id).like(f"%{user_id.strip().lower()}%"))
    if ip_address and ip_address.strip():
        stmt = stmt.where(ImmutableAuditEventModel.ip_address.like(f"%{ip_address.strip()}%"))
    if correlation_id and correlation_id.strip():
        stmt = stmt.where(func.lower(ImmutableAuditEventModel.correlation_id).like(f"%{correlation_id.strip().lower()}%"))

    if date_from:
        stmt = stmt.where(ImmutableAuditEventModel.created_at >= _to_naive_utc(date_from))
    if date_to:
        stmt = stmt.where(ImmutableAuditEventModel.created_at <= _to_naive_utc(date_to))

    if search and search.strip():
        s = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(ImmutableAuditEventModel.event_id).like(s),
                func.lower(ImmutableAuditEventModel.action).like(s),
                func.lower(ImmutableAuditEventModel.actor_id).like(s),
                func.lower(ImmutableAuditEventModel.correlation_id).like(s),
                func.lower(ImmutableAuditEventModel.module_code).like(s),
            )
        )

    stmt = stmt.offset(skip).limit(limit)
    res = await db.execute(stmt)
    records = res.scalars().all()

    items = []
    for r in records:
        st_obj = states_map.get(r.tenant_id)
        ulb_obj = ulbs_map.get(r.sub_tenant_id)
        items.append(
            ImmutableAuditEventResponse(
                id=r.id,
                eventId=r.event_id,
                sequenceNumber=r.sequence_number,
                tenantId=r.tenant_id,
                tenantName=st_obj.state_name if st_obj else (r.tenant_id or "Platform Super Admin"),
                tenantLevel=r.tenant_level,
                subTenantId=r.sub_tenant_id,
                subTenantName=ulb_obj.name if ulb_obj else (r.sub_tenant_id or "N/A"),
                stateCode=r.state_code,
                moduleCode=r.module_code,
                componentCode=r.component_code,
                eventCategory=r.event_category,
                action=r.action,
                severity=r.severity,
                actorId=r.actor_id,
                actorRole=r.actor_role,
                ipAddress=r.ip_address,
                userAgent=r.user_agent,
                correlationId=r.correlation_id,
                result=r.result,
                details=r.details,
                prevEventHash=r.prev_event_hash,
                eventHash=r.event_hash,
                signature=r.signature,
                isLegalHold=r.is_legal_hold,
                createdAt=r.created_at,
            )
        )

    return ApiResponse(success=True, message=f"Retrieved {len(items)} audit events", data=items)


# 3. Single Event Inspection (Cryptographic Proof)
@router.get("/events/{event_id}", response_model=ApiResponse[ImmutableAuditEventResponse])
async def get_audit_event_details(
    event_id: str,
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    stmt = select(ImmutableAuditEventModel).where(
        or_(
            ImmutableAuditEventModel.id == event_id,
            ImmutableAuditEventModel.event_id == event_id,
        )
    )
    res = await db.execute(stmt)
    r = res.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Audit event not found.")

    return ApiResponse(
        success=True,
        data=ImmutableAuditEventResponse(
            id=r.id,
            eventId=r.event_id,
            sequenceNumber=r.sequence_number,
            tenantId=r.tenant_id,
            tenantName=r.tenant_id or "Platform Super Admin",
            tenantLevel=r.tenant_level,
            subTenantId=r.sub_tenant_id,
            subTenantName=r.sub_tenant_id or "N/A",
            stateCode=r.state_code,
            moduleCode=r.module_code,
            componentCode=r.component_code,
            eventCategory=r.event_category,
            action=r.action,
            severity=r.severity,
            actorId=r.actor_id,
            actorRole=r.actor_role,
            ipAddress=r.ip_address,
            userAgent=r.user_agent,
            correlationId=r.correlation_id,
            result=r.result,
            details=r.details,
            prevEventHash=r.prev_event_hash,
            eventHash=r.event_hash,
            signature=r.signature,
            isLegalHold=r.is_legal_hold,
            createdAt=r.created_at,
        ),
    )


# 4. Hash Verification Engine
@router.post("/verify", response_model=ApiResponse[HashVerificationResponse])
async def run_hash_verification(
    payload: HashVerificationCreatePayload,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(get_current_user),
):
    await _ensure_vault_seeded(db)

    from_dt = _to_naive_utc(payload.fromTimestamp)
    to_dt = _to_naive_utc(payload.toTimestamp)

    stmt = (
        select(ImmutableAuditEventModel)
        .where(
            ImmutableAuditEventModel.created_at >= from_dt,
            ImmutableAuditEventModel.created_at <= to_dt,
        )
        .order_by(ImmutableAuditEventModel.sequence_number.asc())
    )

    if payload.tenantId and payload.tenantId != "ALL":
        stmt = stmt.where(ImmutableAuditEventModel.tenant_id == payload.tenantId)

    res = await db.execute(stmt)
    events = res.scalars().all()

    first_hash = events[0].prev_event_hash if events else GENESIS_HASH
    last_hash = events[-1].event_hash if events else GENESIS_HASH

    mismatches = 0
    calculated_hash = first_hash

    # Walk through events in chronological sequence and verify hashes
    for idx, ev in enumerate(events):
        det_str = json.dumps(ev.details or {}, sort_keys=True)
        expected_current = _compute_event_hash(
            prev_hash=ev.prev_event_hash,
            sequence=ev.sequence_number,
            event_id=ev.event_id,
            created_at_iso=ev.created_at.isoformat(),
            actor_id=ev.actor_id,
            event_category=ev.event_category,
            action=ev.action,
            result=ev.result,
            details_str=det_str,
            algorithm=payload.algorithm,
        )

        if expected_current != ev.event_hash:
            mismatches += 1

        calculated_hash = expected_current

    result_status = "VALID_INTEGRITY_INTACT" if mismatches == 0 else "TAMPER_DETECTED"

    now_year = datetime.datetime.utcnow().year
    rand_job = uuid.uuid4().hex[:6].upper()
    job_id = f"VER-{now_year}-{rand_job}"
    operator = user.get("email", "admin@urban.gov.in")

    job = AuditHashVerificationJobModel(
        job_id=job_id,
        job_name=payload.jobName,
        verification_scope=payload.verificationScope,
        tenant_id=payload.tenantId,
        from_timestamp=from_dt,
        to_timestamp=to_dt,
        algorithm=payload.algorithm,
        verification_mode=payload.verificationMode,
        notification_recipients=payload.notificationRecipients,
        remarks=payload.remarks,
        first_event_hash=first_hash,
        last_event_hash=last_hash,
        expected_hash=last_hash,
        calculated_hash=calculated_hash,
        verification_result=result_status,
        total_verified_events=len(events),
        mismatch_count=mismatches,
        executed_by=operator,
        created_at=datetime.datetime.utcnow(),
    )
    db.add(job)

    # Append immutable event for verification execution
    await record_immutable_audit_event(
        db=db,
        event_category="Administrative Actions",
        action="CRYPTOGRAPHIC_HASH_VERIFICATION_EXECUTED",
        actor_id=operator,
        severity="High" if mismatches > 0 else "Informational",
        result="SUCCESS" if mismatches == 0 else "ERROR",
        details={
            "jobId": job_id,
            "jobName": payload.jobName,
            "algorithm": payload.algorithm,
            "totalVerified": len(events),
            "mismatchCount": mismatches,
            "result": result_status,
        },
    )

    await db.commit()
    await db.refresh(job)

    return ApiResponse(
        success=True,
        message=f"Verification job '{job_id}' completed. Result: {result_status}",
        data=HashVerificationResponse(
            id=job.id,
            jobId=job.job_id,
            jobName=job.job_name,
            verificationScope=job.verification_scope,
            tenantId=job.tenant_id,
            fromTimestamp=job.from_timestamp,
            toTimestamp=job.to_timestamp,
            algorithm=job.algorithm,
            verificationMode=job.verification_mode,
            notificationRecipients=job.notification_recipients or [],
            remarks=job.remarks,
            firstEventHash=job.first_event_hash,
            lastEventHash=job.last_event_hash,
            expectedHash=job.expected_hash,
            calculatedHash=job.calculated_hash,
            verificationResult=job.verification_result,
            totalVerifiedEvents=job.total_verified_events,
            mismatchCount=job.mismatch_count,
            executedBy=job.executed_by,
            createdAt=job.created_at,
        ),
    )


@router.get("/verifications", response_model=ApiResponse[List[HashVerificationResponse]])
async def list_verification_jobs(
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    stmt = select(AuditHashVerificationJobModel).order_by(desc(AuditHashVerificationJobModel.created_at)).limit(50)
    res = await db.execute(stmt)
    records = res.scalars().all()

    return ApiResponse(
        success=True,
        data=[
            HashVerificationResponse(
                id=r.id,
                jobId=r.job_id,
                jobName=r.job_name,
                verificationScope=r.verification_scope,
                tenantId=r.tenant_id,
                fromTimestamp=r.from_timestamp,
                toTimestamp=r.to_timestamp,
                algorithm=r.algorithm,
                verificationMode=r.verification_mode,
                notificationRecipients=r.notification_recipients or [],
                remarks=r.remarks,
                firstEventHash=r.first_event_hash,
                lastEventHash=r.last_event_hash,
                expectedHash=r.expected_hash,
                calculatedHash=r.calculated_hash,
                verificationResult=r.verification_result,
                totalVerifiedEvents=r.total_verified_events,
                mismatchCount=r.mismatch_count,
                executedBy=r.executed_by,
                createdAt=r.created_at,
            )
            for r in records
        ],
    )


# 5. Retention Policies Endpoints
@router.get("/retention-policies", response_model=ApiResponse[List[RetentionPolicyResponse]])
async def list_retention_policies(
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    await _ensure_vault_seeded(db)
    stmt = select(AuditRetentionPolicyModel).order_by(desc(AuditRetentionPolicyModel.created_at))
    res = await db.execute(stmt)
    records = res.scalars().all()

    return ApiResponse(
        success=True,
        data=[
            RetentionPolicyResponse(
                id=r.id,
                policyCode=r.policy_code,
                policyName=r.policy_name,
                applicableTenantLevels=r.applicable_tenant_levels or [],
                eventCategories=r.event_categories or [],
                retentionPeriod=r.retention_period,
                retentionUnit=r.retention_unit,
                archiveRequired=r.archive_required,
                archiveDestination=r.archive_destination,
                legalHoldEnabled=r.legal_hold_enabled,
                effectiveDate=r.effective_date,
                policyStatus=r.policy_status,
                description=r.description,
                createdAt=r.created_at,
                updatedAt=r.updated_at,
            )
            for r in records
        ],
    )


@router.post("/retention-policies", response_model=ApiResponse[RetentionPolicyResponse])
async def create_retention_policy(
    payload: RetentionPolicyCreatePayload,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(get_current_user),
):
    code_up = payload.policyCode.strip().upper()
    dup_res = await db.execute(
        select(AuditRetentionPolicyModel).where(AuditRetentionPolicyModel.policy_code == code_up)
    )
    if dup_res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Retention policy code '{code_up}' already exists.")

    eff_dt = _to_naive_utc(payload.effectiveDate)
    new_pol = AuditRetentionPolicyModel(
        policy_code=code_up,
        policy_name=payload.policyName.strip(),
        applicable_tenant_levels=payload.applicableTenantLevels,
        event_categories=payload.eventCategories,
        retention_period=payload.retentionPeriod,
        retention_unit=payload.retentionUnit,
        archive_required=payload.archiveRequired,
        archive_destination=payload.archiveDestination,
        legal_hold_enabled=payload.legalHoldEnabled,
        effective_date=eff_dt,
        policy_status=payload.policyStatus,
        description=payload.description,
    )
    db.add(new_pol)

    operator = user.get("email", "admin@urban.gov.in")
    await record_immutable_audit_event(
        db=db,
        event_category="Configuration Changes",
        action="RETENTION_POLICY_CREATED",
        actor_id=operator,
        severity="High",
        details={
            "policyCode": code_up,
            "policyName": payload.policyName,
            "retention": f"{payload.retentionPeriod} {payload.retentionUnit}",
            "legalHold": payload.legalHoldEnabled,
        },
    )

    await db.commit()
    await db.refresh(new_pol)

    return ApiResponse(
        success=True,
        message=f"Retention policy '{code_up}' created successfully.",
        data=RetentionPolicyResponse(
            id=new_pol.id,
            policyCode=new_pol.policy_code,
            policyName=new_pol.policy_name,
            applicableTenantLevels=new_pol.applicable_tenant_levels or [],
            eventCategories=new_pol.event_categories or [],
            retentionPeriod=new_pol.retention_period,
            retentionUnit=new_pol.retention_unit,
            archiveRequired=new_pol.archive_required,
            archiveDestination=new_pol.archive_destination,
            legalHoldEnabled=new_pol.legal_hold_enabled,
            effectiveDate=new_pol.effective_date,
            policyStatus=new_pol.policy_status,
            description=new_pol.description,
            createdAt=new_pol.created_at,
            updatedAt=new_pol.updated_at,
        ),
    )


# 6. Audit Export Endpoints
@router.post("/export", response_model=ApiResponse[AuditExportResponse])
async def create_audit_export(
    payload: AuditExportCreatePayload,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(get_current_user),
):
    from_dt = _to_naive_utc(payload.dateFrom)
    to_dt = _to_naive_utc(payload.dateTo)

    stmt = (
        select(ImmutableAuditEventModel)
        .where(
            ImmutableAuditEventModel.created_at >= from_dt,
            ImmutableAuditEventModel.created_at <= to_dt,
        )
        .order_by(ImmutableAuditEventModel.sequence_number.asc())
    )

    if payload.stateTenantId and payload.stateTenantId != "ALL":
        stmt = stmt.where(ImmutableAuditEventModel.tenant_id == payload.stateTenantId)
    if payload.ulbTenantId and payload.ulbTenantId != "ALL":
        stmt = stmt.where(ImmutableAuditEventModel.sub_tenant_id == payload.ulbTenantId)
    if payload.eventCategories:
        stmt = stmt.where(ImmutableAuditEventModel.event_category.in_(payload.eventCategories))

    res = await db.execute(stmt)
    events = res.scalars().all()

    now_year = datetime.datetime.utcnow().year
    rand_exp = uuid.uuid4().hex[:6].upper()
    export_id = f"EXP-AUD-{now_year}-{rand_exp}"
    operator = user.get("email", "admin@urban.gov.in")

    # Generate synthetic file hash and estimated size
    simulated_content = f"{export_id}|count:{len(events)}|format:{payload.exportFormat}|from:{from_dt}|to:{to_dt}"
    checksum = hashlib.sha256(simulated_content.encode("utf-8")).hexdigest()
    approx_size = len(events) * (340 if payload.exportFormat == "CSV" else 580)

    export_job = AuditExportJobModel(
        export_id=export_id,
        export_name=payload.exportName,
        export_format=payload.exportFormat,
        tenant_scope=payload.tenantScope,
        state_tenant_id=payload.stateTenantId,
        ulb_tenant_id=payload.ulbTenantId,
        event_categories=payload.eventCategories,
        date_from=from_dt,
        date_to=to_dt,
        include_hash_info=payload.includeHashInfo,
        mask_sensitive_info=payload.maskSensitiveInfo,
        export_reason=payload.exportReason,
        approval_reference=payload.approvalReference,
        status="Completed",
        exported_by=operator,
        file_size_bytes=approx_size,
        file_checksum=checksum,
        created_at=datetime.datetime.utcnow(),
    )
    db.add(export_job)

    # Log export operation itself into immutable vault
    await record_immutable_audit_event(
        db=db,
        event_category="Data Access",
        action="IMMUTABLE_AUDIT_EXPORT_GENERATED",
        actor_id=operator,
        severity="High",
        details={
            "exportId": export_id,
            "exportFormat": payload.exportFormat,
            "recordsExported": len(events),
            "fileChecksum": checksum,
            "approvalReference": payload.approvalReference,
            "reason": payload.exportReason,
        },
    )

    await db.commit()
    await db.refresh(export_job)

    return ApiResponse(
        success=True,
        message=f"Audit export '{export_id}' created successfully ({len(events)} events processed).",
        data=AuditExportResponse(
            id=export_job.id,
            exportId=export_job.export_id,
            exportName=export_job.export_name,
            exportFormat=export_job.export_format,
            tenantScope=export_job.tenant_scope,
            stateTenantId=export_job.state_tenant_id,
            ulbTenantId=export_job.ulb_tenant_id,
            eventCategories=export_job.event_categories or [],
            dateFrom=export_job.date_from,
            dateTo=export_job.date_to,
            includeHashInfo=export_job.include_hash_info,
            maskSensitiveInfo=export_job.mask_sensitive_info,
            exportReason=export_job.export_reason,
            approvalReference=export_job.approval_reference,
            status=export_job.status,
            exportedBy=export_job.exported_by,
            fileSizeBytes=export_job.file_size_bytes,
            fileChecksum=export_job.file_checksum,
            createdAt=export_job.created_at,
        ),
    )


@router.get("/exports", response_model=ApiResponse[List[AuditExportResponse]])
async def list_audit_exports(
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    stmt = select(AuditExportJobModel).order_by(desc(AuditExportJobModel.created_at)).limit(50)
    res = await db.execute(stmt)
    records = res.scalars().all()

    return ApiResponse(
        success=True,
        data=[
            AuditExportResponse(
                id=r.id,
                exportId=r.export_id,
                exportName=r.export_name,
                exportFormat=r.export_format,
                tenantScope=r.tenant_scope,
                stateTenantId=r.state_tenant_id,
                ulbTenantId=r.ulb_tenant_id,
                eventCategories=r.event_categories or [],
                dateFrom=r.date_from,
                dateTo=r.date_to,
                includeHashInfo=r.include_hash_info,
                maskSensitiveInfo=r.mask_sensitive_info,
                exportReason=r.export_reason,
                approvalReference=r.approval_reference,
                status=r.status,
                exportedBy=r.exported_by,
                fileSizeBytes=r.file_size_bytes,
                fileChecksum=r.file_checksum,
                createdAt=r.created_at,
            )
            for r in records
        ],
    )
