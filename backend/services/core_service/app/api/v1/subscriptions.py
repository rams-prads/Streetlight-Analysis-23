import datetime
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, desc

from app.db.session import get_read_db, get_write_db
from app.db.models import (
    StateTenant,
    ModuleModel,
    StateModuleSubscription,
    StateSubscriptionHistory
)
from app.core.auth import get_current_user
from app.schemas.tenant import ApiResponse
from app.schemas.subscription import (
    StateSubscriptionResponse,
    StateSubscriptionCreatePayload,
    StateSubscriptionRenewPayload,
    StateSubscriptionHistoryResponse,
    StateSubscriptionOverviewStats,
    SubscribedModuleItem
)

router = APIRouter(prefix="/modules/subscriptions", tags=["ADM-M04 State Module Subscription Allocator"])


def _to_naive_utc(dt: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return dt


def _generate_subscription_id(state_code: str) -> str:
    now_year = datetime.datetime.utcnow().year
    rand_suffix = uuid.uuid4().hex[:6].upper()
    return f"SUB-{state_code.upper()}-{now_year}-{rand_suffix}"


async def _check_and_update_expired_subscriptions(db: AsyncSession):
    """Enforce backend subscription expiry."""
    now = datetime.datetime.utcnow()
    stmt = select(StateModuleSubscription).where(
        StateModuleSubscription.status == "Active",
        StateModuleSubscription.end_date.isnot(None),
        StateModuleSubscription.end_date < now
    )
    res = await db.execute(stmt)
    expired_subs = res.scalars().all()
    for sub in expired_subs:
        sub.status = "Expired"
        # Log expiry event
        history_entry = StateSubscriptionHistory(
            subscription_id=sub.subscription_id,
            state_tenant_id=sub.state_tenant_id,
            action_type="Expired",
            previous_status="Active",
            new_status="Expired",
            previous_expiry_date=sub.end_date,
            new_expiry_date=sub.end_date,
            changed_modules=sub.subscribed_modules,
            changed_by="System (Automated Expiry Sentinel)",
            change_reason="Subscription validity window elapsed.",
            created_at=now
        )
        db.add(history_entry)
    if expired_subs:
        await db.commit()


@router.get("", response_model=ApiResponse[List[StateSubscriptionResponse]])
async def list_subscriptions(
    search: Optional[str] = Query(None),
    state_tenant_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    subscription_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(get_current_user),
):
    await _check_and_update_expired_subscriptions(db)

    # Preload state tenants map for names and codes
    states_res = await db.execute(select(StateTenant))
    states = states_res.scalars().all()
    state_map = {s.tenant_id: s for s in states}

    query = select(StateModuleSubscription).order_by(desc(StateModuleSubscription.created_at))

    if state_tenant_id and state_tenant_id.upper() != "ALL":
        query = query.where(StateModuleSubscription.state_tenant_id == state_tenant_id)
    if status_filter and status_filter.upper() != "ALL":
        query = query.where(StateModuleSubscription.status == status_filter)
    if subscription_type and subscription_type.upper() != "ALL":
        query = query.where(StateModuleSubscription.subscription_type == subscription_type)

    if search:
        q = f"%{search.strip().lower()}%"
        # Match subscription_id, name, remarks
        query = query.where(
            or_(
                func.lower(StateModuleSubscription.subscription_id).like(q),
                func.lower(StateModuleSubscription.subscription_name).like(q),
                func.lower(StateModuleSubscription.remarks).like(q),
            )
        )

    res = await db.execute(query.offset(skip).limit(limit))
    rows = res.scalars().all()

    items: List[StateSubscriptionResponse] = []
    for row in rows:
        st = state_map.get(row.state_tenant_id)
        modules_list = [
            SubscribedModuleItem(**m) if isinstance(m, dict) else SubscribedModuleItem(code=m, name=m)
            for m in (row.subscribed_modules or [])
        ]
        items.append(
            StateSubscriptionResponse(
                id=row.id,
                subscriptionId=row.subscription_id,
                stateTenantId=row.state_tenant_id,
                stateName=st.state_name if st else "Unknown State",
                stateCode=st.state_code if st else "N/A",
                subscriptionName=row.subscription_name,
                subscriptionType=row.subscription_type,
                subscribedModules=modules_list,
                totalModules=len(modules_list),
                activeModulesCount=len([m for m in modules_list if m.status == "Active"]) if row.status == "Active" else 0,
                startDate=row.start_date,
                endDate=row.end_date,
                billingCycle=row.billing_cycle,
                status=row.status,
                autoRenewal=row.auto_renewal,
                remarks=row.remarks,
                approvalReference=row.approval_reference,
                createdAt=row.created_at,
                updatedAt=row.updated_at,
            )
        )

    return ApiResponse(
        success=True,
        message=f"Retrieved {len(items)} state module subscriptions",
        data=items
    )


@router.get("/stats", response_model=ApiResponse[StateSubscriptionOverviewStats])
async def get_subscription_stats(
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(get_current_user),
):
    await _check_and_update_expired_subscriptions(db)

    res = await db.execute(select(StateModuleSubscription))
    all_subs = res.scalars().all()

    now = datetime.datetime.utcnow()
    thirty_days_later = now + datetime.timedelta(days=30)

    total_subs = len(all_subs)
    active_subs = 0
    expiring_soon = 0
    expired_or_revoked = 0
    total_allocated_modules = 0

    for s in all_subs:
        if s.status == "Active":
            active_subs += 1
            total_allocated_modules += len(s.subscribed_modules or [])
            if s.end_date and now <= s.end_date <= thirty_days_later:
                expiring_soon += 1
        elif s.status in ["Expired", "Revoked"]:
            expired_or_revoked += 1

    return ApiResponse(
        success=True,
        message="Subscription statistics computed",
        data=StateSubscriptionOverviewStats(
            totalSubscriptions=total_subs,
            activeSubscriptions=active_subs,
            expiringSoonCount=expiring_soon,
            expiredOrRevokedCount=expired_or_revoked,
            totalAllocatedModules=total_allocated_modules
        )
    )


@router.post("", response_model=ApiResponse[StateSubscriptionResponse])
async def create_subscription(
    payload: StateSubscriptionCreatePayload,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(get_current_user),
):
    # 1. Validation: Only active state tenants should receive new subscriptions
    state_res = await db.execute(select(StateTenant).where(StateTenant.tenant_id == payload.stateTenantId))
    state_tenant = state_res.scalar_one_or_none()
    if not state_tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"State tenant '{payload.stateTenantId}' not found."
        )

    if state_tenant.status != "Active":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only active state tenants can receive new module subscriptions. Current tenant status is '{state_tenant.status}'."
        )

    # 2. Validation: State can only allocate modules from published master catalogue
    if not payload.moduleCodes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one module code must be selected for subscription allocation."
        )

    clean_codes = [c.strip().upper() for c in payload.moduleCodes]
    modules_res = await db.execute(
        select(ModuleModel).where(ModuleModel.code.in_(clean_codes))
    )
    published_modules = modules_res.scalars().all()
    published_map = {m.code: m for m in published_modules if m.status == "Published"}

    invalid_or_unpublished = [c for c in clean_codes if c not in published_map]
    if invalid_or_unpublished:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The following module(s) are either invalid or not published in the master catalogue: {', '.join(invalid_or_unpublished)}."
        )

    # 3. Validation: Prevent duplicate active subscriptions for the same module and tenant
    existing_subs_res = await db.execute(
        select(StateModuleSubscription).where(
            StateModuleSubscription.state_tenant_id == payload.stateTenantId,
            StateModuleSubscription.status == "Active"
        )
    )
    existing_subs = existing_subs_res.scalars().all()

    already_allocated_modules = set()
    for es in existing_subs:
        for m in (es.subscribed_modules or []):
            code = m.get("code") if isinstance(m, dict) else m
            if code:
                already_allocated_modules.add(code.upper())

    overlap = set(clean_codes).intersection(already_allocated_modules)
    if overlap:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Duplicate active subscription detected! Tenant already has active subscriptions for module(s): {', '.join(overlap)}."
        )

    # Prepare modules list
    modules_to_assign = []
    for code in clean_codes:
        m_obj = published_map[code]
        modules_to_assign.append({
            "code": m_obj.code,
            "name": m_obj.name,
            "version": m_obj.module_version,
            "category": m_obj.category,
            "status": "Active"
        })

    sub_id = _generate_subscription_id(state_tenant.state_code)
    start_dt = _to_naive_utc(payload.startDate)
    end_dt = _to_naive_utc(payload.endDate)

    new_sub = StateModuleSubscription(
        subscription_id=sub_id,
        state_tenant_id=payload.stateTenantId,
        subscription_name=payload.subscriptionName.strip(),
        subscription_type=payload.subscriptionType,
        subscribed_modules=modules_to_assign,
        start_date=start_dt,
        end_date=end_dt,
        billing_cycle=payload.billingCycle,
        status=payload.status,
        auto_renewal=payload.autoRenewal,
        remarks=payload.remarks,
        approval_reference=payload.approvalReference
    )
    db.add(new_sub)

    # Log history
    operator_email = user.get("email", "admin@urban.gov.in")
    history_entry = StateSubscriptionHistory(
        subscription_id=sub_id,
        state_tenant_id=payload.stateTenantId,
        module_code="ALL",
        action_type="Allocated",
        previous_status=None,
        new_status=payload.status,
        previous_expiry_date=None,
        new_expiry_date=end_dt,
        changed_modules=modules_to_assign,
        changed_by=operator_email,
        change_reason=payload.remarks or "Initial module subscription allocation.",
        approval_reference=payload.approvalReference
    )
    db.add(history_entry)

    await db.commit()
    await db.refresh(new_sub)

    return ApiResponse(
        success=True,
        message=f"Subscription '{sub_id}' allocated successfully with {len(modules_to_assign)} modules.",
        data=StateSubscriptionResponse(
            id=new_sub.id,
            subscriptionId=new_sub.subscription_id,
            stateTenantId=new_sub.state_tenant_id,
            stateName=state_tenant.state_name,
            stateCode=state_tenant.state_code,
            subscriptionName=new_sub.subscription_name,
            subscriptionType=new_sub.subscription_type,
            subscribedModules=[SubscribedModuleItem(**m) for m in modules_to_assign],
            totalModules=len(modules_to_assign),
            activeModulesCount=len(modules_to_assign),
            startDate=new_sub.start_date,
            endDate=new_sub.end_date,
            billingCycle=new_sub.billing_cycle,
            status=new_sub.status,
            autoRenewal=new_sub.auto_renewal,
            remarks=new_sub.remarks,
            approvalReference=new_sub.approval_reference,
            createdAt=new_sub.created_at,
            updatedAt=new_sub.updated_at
        )
    )


@router.post("/{subscription_id}/renew", response_model=ApiResponse[StateSubscriptionResponse])
async def renew_subscription(
    subscription_id: str,
    payload: StateSubscriptionRenewPayload,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(get_current_user),
):
    sub_res = await db.execute(
        select(StateModuleSubscription).where(StateModuleSubscription.subscription_id == subscription_id)
    )
    sub = sub_res.scalar_one_or_none()
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subscription '{subscription_id}' not found."
        )

    state_res = await db.execute(select(StateTenant).where(StateTenant.tenant_id == sub.state_tenant_id))
    state_tenant = state_res.scalar_one_or_none()

    previous_expiry = sub.end_date
    current_modules = list(sub.subscribed_modules or [])

    # Check additional modules if provided
    if payload.additionalModuleCodes:
        add_codes = [c.strip().upper() for c in payload.additionalModuleCodes]
        modules_res = await db.execute(select(ModuleModel).where(ModuleModel.code.in_(add_codes)))
        published_modules = modules_res.scalars().all()
        published_map = {m.code: m for m in published_modules if m.status == "Published"}

        existing_codes = {m.get("code") if isinstance(m, dict) else m for m in current_modules}
        for code in add_codes:
            if code in published_map and code not in existing_codes:
                m_obj = published_map[code]
                current_modules.append({
                    "code": m_obj.code,
                    "name": m_obj.name,
                    "version": m_obj.module_version,
                    "category": m_obj.category,
                    "status": "Active"
                })

    new_start_dt = _to_naive_utc(payload.newStartDate)
    new_end_dt = _to_naive_utc(payload.newEndDate)
    sub.start_date = new_start_dt
    sub.end_date = new_end_dt
    sub.subscribed_modules = current_modules
    sub.status = "Active"
    if payload.approvalReference:
        sub.approval_reference = payload.approvalReference
    sub.updated_at = datetime.datetime.utcnow()

    # Log history
    operator_email = user.get("email", "admin@urban.gov.in")
    history_entry = StateSubscriptionHistory(
        subscription_id=sub.subscription_id,
        state_tenant_id=sub.state_tenant_id,
        action_type=f"Renewed ({payload.renewalType})",
        previous_status="Active" if previous_expiry and previous_expiry > datetime.datetime.utcnow() else "Expired",
        new_status="Active",
        previous_expiry_date=_to_naive_utc(previous_expiry),
        new_expiry_date=new_end_dt,
        changed_modules=current_modules,
        changed_by=operator_email,
        change_reason=payload.renewalRemarks,
        approval_reference=payload.approvalReference
    )
    db.add(history_entry)

    await db.commit()
    await db.refresh(sub)

    return ApiResponse(
        success=True,
        message=f"Subscription '{subscription_id}' successfully renewed until {payload.newEndDate.strftime('%d %b %Y')}.",
        data=StateSubscriptionResponse(
            id=sub.id,
            subscriptionId=sub.subscription_id,
            stateTenantId=sub.state_tenant_id,
            stateName=state_tenant.state_name if state_tenant else "Unknown",
            stateCode=state_tenant.state_code if state_tenant else "N/A",
            subscriptionName=sub.subscription_name,
            subscriptionType=sub.subscription_type,
            subscribedModules=[SubscribedModuleItem(**m) for m in current_modules],
            totalModules=len(current_modules),
            activeModulesCount=len(current_modules),
            startDate=sub.start_date,
            endDate=sub.end_date,
            billingCycle=sub.billing_cycle,
            status=sub.status,
            autoRenewal=sub.auto_renewal,
            remarks=sub.remarks,
            approvalReference=sub.approval_reference,
            createdAt=sub.created_at,
            updatedAt=sub.updated_at
        )
    )


@router.post("/{subscription_id}/revoke", response_model=ApiResponse[StateSubscriptionResponse])
async def revoke_subscription(
    subscription_id: str,
    reason: str = Query(..., min_length=5),
    approval_ref: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(get_current_user),
):
    sub_res = await db.execute(
        select(StateModuleSubscription).where(StateModuleSubscription.subscription_id == subscription_id)
    )
    sub = sub_res.scalar_one_or_none()
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Subscription '{subscription_id}' not found."
        )

    prev_status = sub.status
    sub.status = "Revoked"
    sub.updated_at = datetime.datetime.utcnow()

    operator_email = user.get("email", "admin@urban.gov.in")
    history_entry = StateSubscriptionHistory(
        subscription_id=sub.subscription_id,
        state_tenant_id=sub.state_tenant_id,
        action_type="Revoked",
        previous_status=prev_status,
        new_status="Revoked",
        previous_expiry_date=sub.end_date,
        new_expiry_date=sub.end_date,
        changed_modules=sub.subscribed_modules,
        changed_by=operator_email,
        change_reason=reason,
        approval_reference=approval_ref
    )
    db.add(history_entry)

    await db.commit()
    await db.refresh(sub)

    return ApiResponse(
        success=True,
        message=f"Subscription '{subscription_id}' revoked.",
        data=StateSubscriptionResponse(
            id=sub.id,
            subscriptionId=sub.subscription_id,
            stateTenantId=sub.state_tenant_id,
            subscriptionName=sub.subscription_name,
            subscriptionType=sub.subscription_type,
            subscribedModules=[SubscribedModuleItem(**m) for m in (sub.subscribed_modules or [])],
            totalModules=len(sub.subscribed_modules or []),
            activeModulesCount=0,
            startDate=sub.start_date,
            endDate=sub.end_date,
            billingCycle=sub.billing_cycle,
            status=sub.status,
            autoRenewal=sub.auto_renewal,
            remarks=sub.remarks,
            approvalReference=sub.approval_reference,
            createdAt=sub.created_at,
            updatedAt=sub.updated_at
        )
    )


@router.get("/history", response_model=ApiResponse[List[StateSubscriptionHistoryResponse]])
async def list_subscription_history(
    subscription_id: Optional[str] = Query(None),
    state_tenant_id: Optional[str] = Query(None),
    action_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    states_res = await db.execute(select(StateTenant))
    states = states_res.scalars().all()
    state_map = {s.tenant_id: s.state_name for s in states}

    query = select(StateSubscriptionHistory).order_by(desc(StateSubscriptionHistory.created_at))

    if subscription_id and subscription_id.upper() != "ALL":
        query = query.where(StateSubscriptionHistory.subscription_id == subscription_id)
    if state_tenant_id and state_tenant_id.upper() != "ALL":
        query = query.where(StateSubscriptionHistory.state_tenant_id == state_tenant_id)
    if action_type and action_type.upper() != "ALL":
        query = query.where(StateSubscriptionHistory.action_type.like(f"%{action_type}%"))

    res = await db.execute(query.offset(skip).limit(limit))
    rows = res.scalars().all()

    items = [
        StateSubscriptionHistoryResponse(
            id=row.id,
            subscriptionId=row.subscription_id,
            stateTenantId=row.state_tenant_id,
            stateName=state_map.get(row.state_tenant_id, "Unknown State"),
            moduleCode=row.module_code,
            actionType=row.action_type,
            previousStatus=row.previous_status,
            newStatus=row.new_status,
            previousExpiryDate=row.previous_expiry_date,
            newExpiryDate=row.new_expiry_date,
            changedModules=row.changed_modules or [],
            changedBy=row.changed_by,
            changeReason=row.change_reason,
            approvalReference=row.approval_reference,
            createdAt=row.created_at
        )
        for row in rows
    ]

    return ApiResponse(
        success=True,
        message=f"Retrieved {len(items)} subscription history entries",
        data=items
    )


@router.get("/check/{state_tenant_id}/{module_code}")
async def check_module_active_status(
    state_tenant_id: str,
    module_code: str,
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    """Enforce backend verification of state module subscription validity."""
    now = datetime.datetime.utcnow()
    m_code = module_code.strip().upper()

    subs_res = await db.execute(
        select(StateModuleSubscription).where(
            StateModuleSubscription.state_tenant_id == state_tenant_id,
            StateModuleSubscription.status == "Active",
            or_(
                StateModuleSubscription.end_date.is_(None),
                StateModuleSubscription.end_date >= now
            )
        )
    )
    active_subs = subs_res.scalars().all()

    is_subscribed = False
    sub_id = None
    expiry_date = None

    for sub in active_subs:
        for m in (sub.subscribed_modules or []):
            code = m.get("code") if isinstance(m, dict) else m
            if code and code.upper() == m_code:
                is_subscribed = True
                sub_id = sub.subscription_id
                expiry_date = sub.end_date
                break
        if is_subscribed:
            break

    return {
        "success": True,
        "stateTenantId": state_tenant_id,
        "moduleCode": m_code,
        "isActive": is_subscribed,
        "subscriptionId": sub_id,
        "expiryDate": expiry_date.isoformat() if expiry_date else None,
        "enforcedAt": now.isoformat()
    }

