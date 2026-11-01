import datetime
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, or_, and_

from app.db.session import get_read_db, get_write_db
from app.db.models import (
    Tenant,
    StateTenant,
    TenantAuditLog,
    TenantLifecycleEvent,
    TenantMaintenanceConfig
)
from app.core.auth import get_current_user, require_roles
from app.schemas.tenant import (
    ApiResponse,
    TenantDirectoryItem,
    TenantStatusChangePayload,
    TenantMaintenancePayload,
    TenantMaintenanceResponse,
    TenantArchivePayload,
    TenantLifecycleEventResponse,
)

router = APIRouter(prefix="/tenants/lifecycle", tags=["ADM-T03 Tenant Lifecycle Management"])

@router.get("/directory", response_model=ApiResponse[List[TenantDirectoryItem]])
async def list_lifecycle_directory(
    search: Optional[str] = Query(None),
    tenant_level: Optional[str] = Query(None),
    parent_state: Optional[str] = Query(None),
    tenant_type: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    items: List[TenantDirectoryItem] = []

    # 1. State Tenants (Level 1)
    if not tenant_level or tenant_level.upper() in ["ALL", "STATE"]:
        state_stmt = select(StateTenant)
        if search:
            q = f"%{search.strip().lower()}%"
            state_stmt = state_stmt.where(
                or_(
                    func.lower(StateTenant.state_name).like(q),
                    func.lower(StateTenant.state_code).like(q),
                    func.lower(StateTenant.tenant_id).like(q),
                )
            )
        if status_filter and status_filter.upper() != "ALL":
            state_stmt = state_stmt.where(StateTenant.status == status_filter)
        if tenant_type and tenant_type.upper() not in ["ALL", "STATE GOV", "STATE"]:
            # If filtered by a specific ULB type, exclude states
            state_stmt = state_stmt.where(StateTenant.id == "NONE")

        state_res = await db.execute(state_stmt)
        state_rows = state_res.scalars().all()

        for st in state_rows:
            # Count active child ULBs
            child_count_res = await db.execute(
                select(func.count(Tenant.tenant_id)).where(
                    Tenant.parent_state_tenant_id == st.tenant_id,
                    Tenant.status != "Archived"
                )
            )
            child_count = child_count_res.scalar() or 0

            # Check maintenance
            maint_res = await db.execute(
                select(TenantMaintenanceConfig).where(
                    TenantMaintenanceConfig.tenant_id == st.tenant_id,
                    TenantMaintenanceConfig.is_active == True
                )
            )
            is_maint = maint_res.scalar_one_or_none() is not None

            items.append(
                TenantDirectoryItem(
                    tenantId=st.tenant_id,
                    name=st.state_name,
                    code=st.state_code,
                    tenantLevel="State",
                    parentStateTenantId=None,
                    parentStateName="Government of India (National)",
                    tenantType="State Government",
                    currentStatus=st.status,
                    createdAt=st.created_at,
                    updatedAt=st.updated_at,
                    isMaintenanceActive=is_maint,
                    activeChildUlbsCount=child_count,
                )
            )

    # 2. ULB Tenants (Level 2)
    if not tenant_level or tenant_level.upper() in ["ALL", "ULB"]:
        ulb_stmt = select(Tenant)
        if search:
            q = f"%{search.strip().lower()}%"
            ulb_stmt = ulb_stmt.where(
                or_(
                    func.lower(Tenant.name).like(q),
                    func.lower(Tenant.ulb_code).like(q),
                    func.lower(Tenant.tenant_id).like(q),
                    func.lower(Tenant.district).like(q),
                )
            )
        if parent_state and parent_state.upper() != "ALL":
            ulb_stmt = ulb_stmt.where(
                or_(
                    Tenant.parent_state_tenant_id == parent_state,
                    Tenant.state_code == parent_state
                )
            )
        if tenant_type and tenant_type.upper() != "ALL":
            ulb_stmt = ulb_stmt.where(Tenant.ulb_type == tenant_type)
        if status_filter and status_filter.upper() != "ALL":
            ulb_stmt = ulb_stmt.where(Tenant.status == status_filter)

        ulb_res = await db.execute(ulb_stmt)
        ulb_rows = ulb_res.scalars().all()

        # Preload parent state names
        states_res = await db.execute(select(StateTenant.tenant_id, StateTenant.state_name))
        state_map = {row[0]: row[1] for row in states_res.all()}

        for u in ulb_rows:
            p_name = state_map.get(u.parent_state_tenant_id, u.state_code)

            maint_res = await db.execute(
                select(TenantMaintenanceConfig).where(
                    TenantMaintenanceConfig.tenant_id == u.tenant_id,
                    TenantMaintenanceConfig.is_active == True
                )
            )
            is_maint = maint_res.scalar_one_or_none() is not None

            items.append(
                TenantDirectoryItem(
                    tenantId=u.tenant_id,
                    name=u.name,
                    code=u.ulb_code or u.tenant_id,
                    tenantLevel="ULB",
                    parentStateTenantId=u.parent_state_tenant_id,
                    parentStateName=p_name,
                    tenantType=u.ulb_type,
                    currentStatus=u.status,
                    createdAt=u.created_at,
                    updatedAt=u.updated_at,
                    isMaintenanceActive=is_maint,
                    activeChildUlbsCount=0,
                )
            )

    # Sort and slice
    items.sort(key=lambda x: (0 if x.tenantLevel == "State" else 1, x.name))
    paginated = items[skip : skip + limit]

    return ApiResponse(data=paginated)

@router.post("/status", response_model=ApiResponse[TenantDirectoryItem])
async def update_tenant_status(
    payload: TenantStatusChangePayload,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(require_roles(["super_admin", "state_director"])),
):
    tenant_id = payload.tenantId.strip()
    is_state = payload.tenantLevel.upper() == "STATE"
    operator = user.get("preferred_username") or user.get("email") or "system"

    # Validation: Archiving state with active children
    if is_state and payload.newStatus == "Archived":
        active_children_res = await db.execute(
            select(func.count(Tenant.tenant_id)).where(
                Tenant.parent_state_tenant_id == tenant_id,
                Tenant.status != "Archived"
            )
        )
        active_count = active_children_res.scalar() or 0
        if active_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot archive State Tenant: {active_count} active or operational child ULBs still depend on it. Decommission or archive all child ULBs first."
            )

    old_status = "Unknown"
    tenant_name = ""
    tenant_code = ""
    tenant_type = "State Government" if is_state else "Municipal Corporation"
    parent_state_id = None
    parent_state_name = None

    if is_state:
        st_res = await db.execute(select(StateTenant).where(StateTenant.tenant_id == tenant_id))
        st_obj = st_res.scalar_one_or_none()
        if not st_obj:
            raise HTTPException(status_code=404, detail=f"State Tenant '{tenant_id}' not found")
        old_status = st_obj.status
        st_obj.status = payload.newStatus
        st_obj.updated_at = datetime.datetime.utcnow()
        tenant_name = st_obj.state_name
        tenant_code = st_obj.state_code
    else:
        u_res = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
        u_obj = u_res.scalar_one_or_none()
        if not u_obj:
            raise HTTPException(status_code=404, detail=f"ULB Tenant '{tenant_id}' not found")
        old_status = u_obj.status
        u_obj.status = payload.newStatus
        u_obj.updated_at = datetime.datetime.utcnow()
        tenant_name = u_obj.name
        tenant_code = u_obj.ulb_code or u_obj.tenant_id
        tenant_type = u_obj.ulb_type
        parent_state_id = u_obj.parent_state_tenant_id

        if parent_state_id:
            pst_res = await db.execute(select(StateTenant).where(StateTenant.tenant_id == parent_state_id))
            pst_obj = pst_res.scalar_one_or_none()
            if pst_obj:
                parent_state_name = pst_obj.state_name

    # Record Lifecycle Event
    event_type = "STATUS_CHANGE"
    if payload.newStatus == "Suspended":
        event_type = "SUSPENSION"
    elif payload.newStatus == "Active" and old_status in ["Suspended", "Locked"]:
        event_type = "REACTIVATION"
    elif payload.newStatus == "Locked":
        event_type = "LOCK"
    elif payload.newStatus == "Archived":
        event_type = "ARCHIVE"

    life_event = TenantLifecycleEvent(
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        tenant_level=payload.tenantLevel,
        previous_status=old_status,
        new_status=payload.newStatus,
        event_type=event_type,
        reason=payload.reason.strip(),
        approval_reference=payload.approvalReference,
        effective_from=payload.effectiveFrom or datetime.datetime.utcnow(),
        effective_until=payload.effectiveUntil,
        supporting_document=payload.supportingDocument,
        performed_by=operator,
    )
    db.add(life_event)

    audit = TenantAuditLog(
        tenant_id=tenant_id,
        action=f"LIFECYCLE_{payload.newStatus.upper()}",
        performed_by=operator,
        details=f"Status transitioned from {old_status} to {payload.newStatus}. Reason: {payload.reason.strip()}",
    )
    db.add(audit)

    await db.commit()

    return ApiResponse(
        data=TenantDirectoryItem(
            tenantId=tenant_id,
            name=tenant_name,
            code=tenant_code,
            tenantLevel=payload.tenantLevel,
            parentStateTenantId=parent_state_id,
            parentStateName=parent_state_name or "National Root",
            tenantType=tenant_type,
            currentStatus=payload.newStatus,
            createdAt=datetime.datetime.utcnow(),
            updatedAt=datetime.datetime.utcnow(),
            isMaintenanceActive=(payload.newStatus == "Maintenance"),
            activeChildUlbsCount=0,
        )
    )

@router.get("/maintenance/{tenant_id}", response_model=ApiResponse[TenantMaintenanceResponse])
async def get_tenant_maintenance(
    tenant_id: str,
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    res = await db.execute(
        select(TenantMaintenanceConfig).where(TenantMaintenanceConfig.tenant_id == tenant_id)
    )
    cfg = res.scalar_one_or_none()
    if not cfg:
        return ApiResponse(
            data=TenantMaintenanceResponse(
                tenantId=tenant_id,
                isActive=False,
                title="",
                message="",
                allowedIps=[],
                allowAdminAccess=True,
                notificationRequired=False,
                notificationRecipients=[],
                reason="",
            )
        )

    return ApiResponse(
        data=TenantMaintenanceResponse(
            tenantId=cfg.tenant_id,
            isActive=cfg.is_active,
            title=cfg.title,
            message=cfg.message,
            startTime=cfg.start_time,
            endTime=cfg.end_time,
            allowedIps=cfg.allowed_ips or [],
            allowAdminAccess=cfg.allow_admin_access,
            notificationRequired=cfg.notification_required,
            notificationRecipients=cfg.notification_recipients or [],
            reason=cfg.reason,
            updatedBy=cfg.updated_by,
            updatedAt=cfg.updated_at,
        )
    )

@router.post("/maintenance", response_model=ApiResponse[TenantMaintenanceResponse])
async def update_tenant_maintenance(
    payload: TenantMaintenancePayload,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(require_roles(["super_admin", "state_director"])),
):
    tenant_id = payload.tenantId.strip()
    is_state = payload.tenantLevel.upper() == "STATE"
    operator = user.get("preferred_username") or user.get("email") or "system"

    # Fetch tenant
    tenant_name = ""
    if is_state:
        st_res = await db.execute(select(StateTenant).where(StateTenant.tenant_id == tenant_id))
        st_obj = st_res.scalar_one_or_none()
        if not st_obj:
            raise HTTPException(status_code=404, detail=f"State Tenant '{tenant_id}' not found")
        tenant_name = st_obj.state_name
        if payload.isMaintenanceActive:
            st_obj.status = "Maintenance"
        elif st_obj.status == "Maintenance":
            st_obj.status = "Active"
    else:
        u_res = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
        u_obj = u_res.scalar_one_or_none()
        if not u_obj:
            raise HTTPException(status_code=404, detail=f"ULB Tenant '{tenant_id}' not found")
        tenant_name = u_obj.name
        if payload.isMaintenanceActive:
            u_obj.status = "Maintenance"
        elif u_obj.status == "Maintenance":
            u_obj.status = "Active"

    # Upsert maintenance config
    cfg_res = await db.execute(
        select(TenantMaintenanceConfig).where(TenantMaintenanceConfig.tenant_id == tenant_id)
    )
    cfg = cfg_res.scalar_one_or_none()
    if not cfg:
        cfg = TenantMaintenanceConfig(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
        )
        db.add(cfg)

    cfg.is_active = payload.isMaintenanceActive
    cfg.title = payload.maintenanceTitle
    cfg.message = payload.maintenanceMessage
    cfg.start_time = payload.startTime
    cfg.end_time = payload.endTime
    cfg.allowed_ips = payload.allowedIps
    cfg.allow_admin_access = payload.allowAdminAccess
    cfg.notification_required = payload.notificationRequired
    cfg.notification_recipients = payload.notificationRecipients
    cfg.reason = payload.reason
    cfg.updated_by = operator
    cfg.updated_at = datetime.datetime.utcnow()

    # Log lifecycle event
    life_event = TenantLifecycleEvent(
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        tenant_level=payload.tenantLevel,
        previous_status="Active" if payload.isMaintenanceActive else "Maintenance",
        new_status="Maintenance" if payload.isMaintenanceActive else "Active",
        event_type="MAINTENANCE_START" if payload.isMaintenanceActive else "MAINTENANCE_END",
        reason=payload.reason or "Scheduled maintenance window",
        effective_from=payload.startTime or datetime.datetime.utcnow(),
        effective_until=payload.endTime,
        performed_by=operator,
    )
    db.add(life_event)

    audit = TenantAuditLog(
        tenant_id=tenant_id,
        action="MAINTENANCE_ACTIVE" if payload.isMaintenanceActive else "MAINTENANCE_DEACTIVATED",
        performed_by=operator,
        details=f"Maintenance mode set to {payload.isMaintenanceActive}. Reason: {payload.reason}",
    )
    db.add(audit)

    await db.commit()

    return ApiResponse(
        data=TenantMaintenanceResponse(
            tenantId=cfg.tenant_id,
            isActive=cfg.is_active,
            title=cfg.title,
            message=cfg.message,
            startTime=cfg.start_time,
            endTime=cfg.end_time,
            allowedIps=cfg.allowed_ips or [],
            allowAdminAccess=cfg.allow_admin_access,
            notificationRequired=cfg.notification_required,
            notificationRecipients=cfg.notification_recipients or [],
            reason=cfg.reason,
            updatedBy=cfg.updated_by,
            updatedAt=cfg.updated_at,
        )
    )

@router.get("/suspensions", response_model=ApiResponse[List[TenantLifecycleEventResponse]])
async def list_suspension_history(
    tenant_id: Optional[str] = Query(None),
    suspension_type: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    stmt = select(TenantLifecycleEvent).order_by(desc(TenantLifecycleEvent.created_at))

    if tenant_id and tenant_id.upper() != "ALL":
        stmt = stmt.where(TenantLifecycleEvent.tenant_id == tenant_id)
    if suspension_type and suspension_type.upper() != "ALL":
        stmt = stmt.where(TenantLifecycleEvent.event_type == suspension_type)

    stmt = stmt.offset(skip).limit(limit)
    res = await db.execute(stmt)
    rows = res.scalars().all()

    data = [
        TenantLifecycleEventResponse(
            id=r.id,
            tenantId=r.tenant_id,
            tenantName=r.tenant_name,
            tenantLevel=r.tenant_level,
            previousStatus=r.previous_status,
            newStatus=r.new_status,
            eventType=r.event_type,
            reason=r.reason,
            approvalReference=r.approval_reference,
            effectiveFrom=r.effective_from,
            effectiveUntil=r.effective_until,
            dataRetentionPolicy=r.data_retention_policy,
            retentionPeriodYears=r.retention_period_years,
            dataExportDestination=r.data_export_destination,
            approvalAuthority=r.approval_authority,
            performedBy=r.performed_by,
            ipAddress=r.ip_address,
            createdAt=r.created_at,
        )
        for r in rows
    ]
    return ApiResponse(data=data)

@router.post("/archive", response_model=ApiResponse[dict])
async def archive_tenant(
    payload: TenantArchivePayload,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(require_roles(["super_admin"])),
):
    tenant_id = payload.tenantId.strip()
    is_state = payload.tenantLevel.upper() == "STATE"
    operator = user.get("preferred_username") or user.get("email") or "system"

    # Validation: Do not allow a state tenant to be archived while active child ULBs still depend on it
    if is_state:
        child_res = await db.execute(
            select(func.count(Tenant.tenant_id)).where(
                Tenant.parent_state_tenant_id == tenant_id,
                Tenant.status != "Archived"
            )
        )
        active_children = child_res.scalar() or 0
        if active_children > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot archive State Tenant '{tenant_id}': {active_children} active child ULBs still depend on it. All child ULBs must be archived or migrated first."
            )

    tenant_name = ""
    old_status = ""
    if is_state:
        st_res = await db.execute(select(StateTenant).where(StateTenant.tenant_id == tenant_id))
        st_obj = st_res.scalar_one_or_none()
        if not st_obj:
            raise HTTPException(status_code=404, detail=f"State Tenant '{tenant_id}' not found")
        old_status = st_obj.status
        st_obj.status = "Archived"
        st_obj.updated_at = datetime.datetime.utcnow()
        tenant_name = st_obj.state_name
    else:
        u_res = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
        u_obj = u_res.scalar_one_or_none()
        if not u_obj:
            raise HTTPException(status_code=404, detail=f"ULB Tenant '{tenant_id}' not found")
        old_status = u_obj.status
        u_obj.status = "Archived"
        u_obj.updated_at = datetime.datetime.utcnow()
        tenant_name = u_obj.name

    # Create immutable archive event
    eff_dt = datetime.datetime.combine(payload.archiveEffectiveDate, datetime.time.min)
    life_event = TenantLifecycleEvent(
        tenant_id=tenant_id,
        tenant_name=tenant_name,
        tenant_level=payload.tenantLevel,
        previous_status=old_status,
        new_status="Archived",
        event_type="ARCHIVE",
        reason=payload.archiveReason.strip(),
        effective_from=eff_dt,
        data_retention_policy=payload.dataRetentionPolicy,
        retention_period_years=payload.retentionPeriodYears,
        data_export_destination=payload.exportDestination if payload.dataExportRequired else None,
        approval_authority=payload.approvalAuthority,
        supporting_document=payload.supportingDocument,
        performed_by=operator,
    )
    db.add(life_event)

    audit = TenantAuditLog(
        tenant_id=tenant_id,
        action="ARCHIVED",
        performed_by=operator,
        details=f"Tenant archived under policy '{payload.dataRetentionPolicy}' ({payload.retentionPeriodYears} years). Export: {payload.exportDestination or 'None'}. Reason: {payload.archiveReason}",
    )
    db.add(audit)

    await db.commit()

    return ApiResponse(
        data={
            "archived": True,
            "tenantId": tenant_id,
            "tenantName": tenant_name,
            "dataRetentionPolicy": payload.dataRetentionPolicy,
            "retentionPeriodYears": payload.retentionPeriodYears,
            "message": f"Tenant '{tenant_name}' successfully archived with immutable audit trail.",
        }
    )

