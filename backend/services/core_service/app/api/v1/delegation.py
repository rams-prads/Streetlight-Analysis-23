import datetime
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, desc

from app.db.session import get_read_db, get_write_db
from app.db.models import (
    StateTenant,
    Tenant,
    ModuleModel,
    ComponentModel,
    StateModuleSubscription,
    DelegationRuleModel,
    UlbModuleAllocationModel,
    UlbComponentRestrictionModel,
    DelegationAuditHistoryModel,
)
from app.core.auth import get_current_user
from app.schemas.tenant import ApiResponse
from app.schemas.delegation import (
    DelegationRuleResponse,
    DelegationRuleCreatePayload,
    DelegationRuleUpdatePayload,
    UlbAllocationResponse,
    UlbAllocationCreatePayload,
    ComponentRestrictionResponse,
    ComponentRestrictionCreatePayload,
    DelegationAuditHistoryResponse,
    DelegationOverviewStats,
    EffectivePermissionCheckResponse,
    HierarchyVerificationTrace,
)

router = APIRouter(prefix="/modules/delegation", tags=["ADM-M05 Sub-Tenant Cascade Delegation Guard"])


def _to_naive_utc(dt: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return dt


# 1. Stats Endpoint
@router.get("/stats", response_model=ApiResponse[DelegationOverviewStats])
async def get_delegation_stats(
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    rules_res = await db.execute(select(DelegationRuleModel))
    rules = rules_res.scalars().all()

    allocs_res = await db.execute(select(UlbModuleAllocationModel))
    allocs = allocs_res.scalars().all()

    rests_res = await db.execute(select(UlbComponentRestrictionModel))
    rests = rests_res.scalars().all()

    active_rules = sum(1 for r in rules if r.rule_status == "Active")
    active_allocs = sum(1 for a in allocs if a.status == "Active")
    active_rests = sum(1 for r in rests if r.is_active)
    unique_ulbs = len(set(a.ulb_tenant_id for a in allocs if a.status == "Active"))

    return ApiResponse(
        success=True,
        message="Delegation guard metrics retrieved",
        data=DelegationOverviewStats(
            totalRules=len(rules),
            activeRules=active_rules,
            totalAllocations=len(allocs),
            activeAllocations=active_allocs,
            totalRestrictions=len(rests),
            activeRestrictions=active_rests,
            delegatedUlbsCount=unique_ulbs,
        ),
    )


# 2. State Scope (Subscribed Modules & Child ULBs for dropdowns)
@router.get("/state-scope/{state_tenant_id}")
async def get_state_delegation_scope(
    state_tenant_id: str,
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    st_res = await db.execute(select(StateTenant).where(StateTenant.tenant_id == state_tenant_id))
    state = st_res.scalar_one_or_none()
    if not state:
        raise HTTPException(status_code=404, detail="State tenant not found")

    # Get active subscriptions for this state
    subs_res = await db.execute(
        select(StateModuleSubscription).where(
            StateModuleSubscription.state_tenant_id == state_tenant_id,
            StateModuleSubscription.status == "Active",
        )
    )
    active_subs = subs_res.scalars().all()

    active_modules = []
    seen_codes = set()
    for s in active_subs:
        for m in (s.subscribed_modules or []):
            code = m.get("code") if isinstance(m, dict) else m
            if code and code not in seen_codes:
                seen_codes.add(code)
                active_modules.append(m)

    # Get child ULBs
    ulbs_res = await db.execute(
        select(Tenant).where(
            Tenant.parent_state_tenant_id == state_tenant_id,
            Tenant.status == "Active",
        ).order_by(Tenant.name)
    )
    child_ulbs = ulbs_res.scalars().all()

    # Get delegation rules
    rules_res = await db.execute(
        select(DelegationRuleModel).where(
            DelegationRuleModel.state_tenant_id == state_tenant_id,
            DelegationRuleModel.rule_status == "Active",
        )
    )
    rules = rules_res.scalars().all()

    return ApiResponse(
        success=True,
        data={
            "stateTenantId": state.tenant_id,
            "stateName": state.state_name,
            "stateCode": state.state_code,
            "activeSubscribedModules": active_modules,
            "childUlbs": [
                {
                    "tenantId": u.tenant_id,
                    "name": u.name,
                    "ulbCode": u.ulb_code,
                    "ulbType": u.ulb_type,
                    "status": u.status,
                }
                for u in child_ulbs
            ],
            "activeRules": [
                {
                    "ruleCode": r.rule_code,
                    "ruleName": r.rule_name,
                    "delegationMode": r.delegation_mode,
                    "allowModuleDelegation": r.allow_module_delegation,
                    "allowComponentDelegation": r.allow_component_delegation,
                }
                for r in rules
            ],
        },
    )


# 3. Delegation Rules Endpoints
@router.get("/rules", response_model=ApiResponse[List[DelegationRuleResponse]])
async def list_delegation_rules(
    search: Optional[str] = Query(None),
    state_tenant_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    states_res = await db.execute(select(StateTenant))
    states_map = {s.tenant_id: s for s in states_res.scalars().all()}

    stmt = select(DelegationRuleModel).order_by(desc(DelegationRuleModel.created_at))

    if state_tenant_id and state_tenant_id != "ALL":
        stmt = stmt.where(DelegationRuleModel.state_tenant_id == state_tenant_id)
    if status_filter and status_filter != "ALL":
        stmt = stmt.where(DelegationRuleModel.rule_status == status_filter)
    if search:
        s = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(DelegationRuleModel.rule_code).like(s),
                func.lower(DelegationRuleModel.rule_name).like(s),
                func.lower(DelegationRuleModel.description).like(s),
            )
        )

    stmt = stmt.offset(skip).limit(limit)
    res = await db.execute(stmt)
    records = res.scalars().all()

    items = []
    for r in records:
        st = states_map.get(r.state_tenant_id)
        items.append(
            DelegationRuleResponse(
                id=r.id,
                ruleCode=r.rule_code,
                ruleName=r.rule_name,
                stateTenantId=r.state_tenant_id,
                stateName=st.state_name if st else "Unknown",
                stateCode=st.state_code if st else "N/A",
                applicableUlbTypes=r.applicable_ulb_types or [],
                delegationMode=r.delegation_mode,
                allowModuleDelegation=r.allow_module_delegation,
                allowComponentDelegation=r.allow_component_delegation,
                allowRoleDelegation=r.allow_role_delegation,
                requireStateApproval=r.require_state_approval,
                effectiveFrom=r.effective_from,
                effectiveUntil=r.effective_until,
                description=r.description,
                ruleStatus=r.rule_status,
                createdAt=r.created_at,
                updatedAt=r.updated_at,
            )
        )

    return ApiResponse(success=True, message=f"Retrieved {len(items)} delegation rules", data=items)


@router.post("/rules", response_model=ApiResponse[DelegationRuleResponse])
async def create_delegation_rule(
    payload: DelegationRuleCreatePayload,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(get_current_user),
):
    st_res = await db.execute(select(StateTenant).where(StateTenant.tenant_id == payload.stateTenantId))
    st = st_res.scalar_one_or_none()
    if not st:
        raise HTTPException(status_code=404, detail="Parent State Tenant not found.")

    # Check duplicate rule code
    dup_res = await db.execute(select(DelegationRuleModel).where(DelegationRuleModel.rule_code == payload.ruleCode.strip()))
    if dup_res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Rule Code '{payload.ruleCode}' already exists.")

    new_rule = DelegationRuleModel(
        rule_code=payload.ruleCode.strip().upper(),
        rule_name=payload.ruleName.strip(),
        state_tenant_id=payload.stateTenantId,
        applicable_ulb_types=payload.applicableUlbTypes,
        delegation_mode=payload.delegationMode,
        allow_module_delegation=payload.allowModuleDelegation,
        allow_component_delegation=payload.allowComponentDelegation,
        allow_role_delegation=payload.allowRoleDelegation,
        require_state_approval=payload.requireStateApproval,
        effective_from=_to_naive_utc(payload.effectiveFrom),
        effective_until=_to_naive_utc(payload.effectiveUntil),
        description=payload.description.strip(),
        rule_status=payload.ruleStatus,
    )
    db.add(new_rule)

    # History log
    history = DelegationAuditHistoryModel(
        state_tenant_id=payload.stateTenantId,
        action_type="Rule Created",
        details={
            "ruleCode": new_rule.rule_code,
            "delegationMode": new_rule.delegation_mode,
            "status": new_rule.rule_status,
        },
        changed_by=user.get("email", "admin@urban.gov.in"),
        change_reason=f"Created delegation rule {new_rule.rule_code}",
    )
    db.add(history)

    await db.commit()
    await db.refresh(new_rule)

    return ApiResponse(
        success=True,
        message=f"Delegation rule '{new_rule.rule_code}' created successfully.",
        data=DelegationRuleResponse(
            id=new_rule.id,
            ruleCode=new_rule.rule_code,
            ruleName=new_rule.rule_name,
            stateTenantId=new_rule.state_tenant_id,
            stateName=st.state_name,
            stateCode=st.state_code,
            applicableUlbTypes=new_rule.applicable_ulb_types or [],
            delegationMode=new_rule.delegation_mode,
            allowModuleDelegation=new_rule.allow_module_delegation,
            allowComponentDelegation=new_rule.allow_component_delegation,
            allowRoleDelegation=new_rule.allow_role_delegation,
            requireStateApproval=new_rule.require_state_approval,
            effectiveFrom=new_rule.effective_from,
            effectiveUntil=new_rule.effective_until,
            description=new_rule.description,
            ruleStatus=new_rule.rule_status,
            createdAt=new_rule.created_at,
            updatedAt=new_rule.updated_at,
        ),
    )


# 4. ULB Allocation Endpoints
@router.get("/allocations", response_model=ApiResponse[List[UlbAllocationResponse]])
async def list_ulb_allocations(
    search: Optional[str] = Query(None),
    state_tenant_id: Optional[str] = Query(None),
    ulb_tenant_id: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    states_res = await db.execute(select(StateTenant))
    states_map = {s.tenant_id: s for s in states_res.scalars().all()}

    ulbs_res = await db.execute(select(Tenant))
    ulbs_map = {u.tenant_id: u for u in ulbs_res.scalars().all()}

    stmt = select(UlbModuleAllocationModel).order_by(desc(UlbModuleAllocationModel.created_at))

    if state_tenant_id and state_tenant_id != "ALL":
        stmt = stmt.where(UlbModuleAllocationModel.state_tenant_id == state_tenant_id)
    if ulb_tenant_id and ulb_tenant_id != "ALL":
        stmt = stmt.where(UlbModuleAllocationModel.ulb_tenant_id == ulb_tenant_id)
    if status_filter and status_filter != "ALL":
        stmt = stmt.where(UlbModuleAllocationModel.status == status_filter)
    if search:
        s = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(UlbModuleAllocationModel.allocation_id).like(s),
                func.lower(UlbModuleAllocationModel.module_code).like(s),
                func.lower(UlbModuleAllocationModel.module_name).like(s),
                func.lower(UlbModuleAllocationModel.approval_reference).like(s),
            )
        )

    stmt = stmt.offset(skip).limit(limit)
    res = await db.execute(stmt)
    records = res.scalars().all()

    items = []
    for r in records:
        st = states_map.get(r.state_tenant_id)
        u = ulbs_map.get(r.ulb_tenant_id)
        items.append(
            UlbAllocationResponse(
                id=r.id,
                allocationId=r.allocation_id,
                stateTenantId=r.state_tenant_id,
                stateName=st.state_name if st else "Unknown",
                ulbTenantId=r.ulb_tenant_id,
                ulbName=u.name if u else "Unknown ULB",
                ulbCode=u.ulb_code if u else "N/A",
                ulbType=u.ulb_type if u else "N/A",
                moduleCode=r.module_code,
                moduleName=r.module_name,
                allocatedComponents=r.allocated_components or [],
                allowedActions=r.allowed_actions or [],
                startDate=r.start_date,
                endDate=r.end_date,
                status=r.status,
                approvalReference=r.approval_reference,
                remarks=r.remarks,
                createdAt=r.created_at,
                updatedAt=r.updated_at,
            )
        )

    return ApiResponse(success=True, message=f"Retrieved {len(items)} allocations", data=items)


@router.post("/allocations", response_model=ApiResponse[List[UlbAllocationResponse]])
async def create_ulb_allocations(
    payload: UlbAllocationCreatePayload,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(get_current_user),
):
    # 1. State Verification
    st_res = await db.execute(select(StateTenant).where(StateTenant.tenant_id == payload.stateTenantId))
    st = st_res.scalar_one_or_none()
    if not st:
        raise HTTPException(status_code=404, detail="Parent State Tenant not found.")
    if st.status != "Active":
        raise HTTPException(status_code=400, detail=f"Parent state tenant status is '{st.status}'. Only active state tenants can delegate modules.")

    # 2. Check State Delegation Rules (Full, Selective, Restricted, No Delegation)
    rule_res = await db.execute(
        select(DelegationRuleModel).where(
            DelegationRuleModel.state_tenant_id == payload.stateTenantId,
            DelegationRuleModel.rule_status == "Active",
        )
    )
    rules = rule_res.scalars().all()
    for r in rules:
        if r.delegation_mode == "No Delegation" or not r.allow_module_delegation:
            raise HTTPException(
                status_code=400,
                detail=f"State delegation policy '{r.rule_name}' explicitly blocks module delegation to child ULBs.",
            )

    # 3. CRITICAL VALIDATION: A ULB cannot receive a module that its parent state has not subscribed to
    subs_res = await db.execute(
        select(StateModuleSubscription).where(
            StateModuleSubscription.state_tenant_id == payload.stateTenantId,
            StateModuleSubscription.status == "Active",
        )
    )
    active_subs = subs_res.scalars().all()

    state_active_modules = {}
    for s in active_subs:
        for m in (s.subscribed_modules or []):
            code = m.get("code") if isinstance(m, dict) else m
            if code:
                state_active_modules[code.upper()] = m.get("name") if isinstance(m, dict) else code

    unsubscribed = [m.upper() for m in payload.moduleCodes if m.upper() not in state_active_modules]
    if unsubscribed:
        raise HTTPException(
            status_code=400,
            detail=f"Hierarchy Violation: State '{st.state_name}' has not subscribed to active module(s): {', '.join(unsubscribed)}. A child ULB cannot receive unallocated state modules.",
        )

    # 4. Target ULBs Verification (Must belong to parent state)
    ulbs_res = await db.execute(
        select(Tenant).where(Tenant.tenant_id.in_(payload.ulbTenantIds))
    )
    target_ulbs = ulbs_res.scalars().all()
    if len(target_ulbs) != len(payload.ulbTenantIds):
        raise HTTPException(status_code=404, detail="One or more target ULB tenants do not exist.")

    for u in target_ulbs:
        if u.parent_state_tenant_id != payload.stateTenantId:
            raise HTTPException(
                status_code=400,
                detail=f"Hierarchy Violation: ULB '{u.name}' ({u.tenant_id}) does not belong to parent state '{st.state_name}'.",
            )
        if u.status != "Active":
            raise HTTPException(
                status_code=400,
                detail=f"ULB '{u.name}' is '{u.status}'. Only active ULB tenants can receive module delegations.",
            )

    # 5. Fetch Module Models for Component names
    modules_res = await db.execute(
        select(ModuleModel).where(ModuleModel.code.in_([m.upper() for m in payload.moduleCodes]))
    )
    mod_map = {m.code.upper(): m for m in modules_res.scalars().all()}

    created_allocations = []
    start_dt = _to_naive_utc(payload.startDate)
    end_dt = _to_naive_utc(payload.endDate)
    operator = user.get("email", "admin@urban.gov.in")

    for u in target_ulbs:
        for m_code in payload.moduleCodes:
            code_up = m_code.strip().upper()
            mod_obj = mod_map.get(code_up)
            mod_name = mod_obj.name if mod_obj else state_active_modules.get(code_up, code_up)

            # Check existing active allocation
            dup_res = await db.execute(
                select(UlbModuleAllocationModel).where(
                    UlbModuleAllocationModel.ulb_tenant_id == u.tenant_id,
                    UlbModuleAllocationModel.module_code == code_up,
                    UlbModuleAllocationModel.status == "Active",
                )
            )
            if dup_res.scalar_one_or_none():
                continue  # Skip duplicate active allocation

            now_year = datetime.datetime.utcnow().year
            rand_suffix = uuid.uuid4().hex[:5].upper()
            u_code = u.ulb_code or u.tenant_id[:4].upper()
            alloc_id = f"ALC-{u_code}-{code_up}-{now_year}-{rand_suffix}"

            new_alloc = UlbModuleAllocationModel(
                allocation_id=alloc_id,
                state_tenant_id=payload.stateTenantId,
                ulb_tenant_id=u.tenant_id,
                module_code=code_up,
                module_name=mod_name,
                allocated_components=payload.allocatedComponents,
                allowed_actions=payload.allowedActions,
                start_date=start_dt,
                end_date=end_dt,
                status=payload.status,
                approval_reference=payload.approvalReference,
                remarks=payload.remarks,
            )
            db.add(new_alloc)
            created_allocations.append(new_alloc)

            # Audit history
            hist = DelegationAuditHistoryModel(
                state_tenant_id=payload.stateTenantId,
                ulb_tenant_id=u.tenant_id,
                module_code=code_up,
                action_type="ULB Allocated",
                details={
                    "allocationId": alloc_id,
                    "ulbName": u.name,
                    "moduleCode": code_up,
                    "actions": payload.allowedActions,
                },
                changed_by=operator,
                change_reason=payload.remarks or f"Delegated {code_up} to {u.name}",
            )
            db.add(hist)

    await db.commit()

    # Re-fetch for response
    response_items = []
    for a in created_allocations:
        await db.refresh(a)
        target_u = next((x for x in target_ulbs if x.tenant_id == a.ulb_tenant_id), None)
        response_items.append(
            UlbAllocationResponse(
                id=a.id,
                allocationId=a.allocation_id,
                stateTenantId=a.state_tenant_id,
                stateName=st.state_name,
                ulbTenantId=a.ulb_tenant_id,
                ulbName=target_u.name if target_u else "ULB",
                ulbCode=target_u.ulb_code if target_u else "N/A",
                ulbType=target_u.ulb_type if target_u else "N/A",
                moduleCode=a.module_code,
                moduleName=a.module_name,
                allocatedComponents=a.allocated_components or [],
                allowedActions=a.allowed_actions or [],
                startDate=a.start_date,
                endDate=a.end_date,
                status=a.status,
                approvalReference=a.approval_reference,
                remarks=a.remarks,
                createdAt=a.created_at,
                updatedAt=a.updated_at,
            )
        )

    return ApiResponse(
        success=True,
        message=f"Successfully allocated {len(response_items)} module delegations to target ULB(s).",
        data=response_items,
    )


@router.post("/allocations/{allocation_id}/revoke")
async def revoke_ulb_allocation(
    allocation_id: str,
    reason: str = Query(..., min_length=5),
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(get_current_user),
):
    res = await db.execute(
        select(UlbModuleAllocationModel).where(UlbModuleAllocationModel.allocation_id == allocation_id)
    )
    alloc = res.scalar_one_or_none()
    if not alloc:
        raise HTTPException(status_code=404, detail="Allocation not found.")

    alloc.status = "Revoked"
    alloc.updated_at = datetime.datetime.utcnow()

    operator = user.get("email", "admin@urban.gov.in")
    hist = DelegationAuditHistoryModel(
        state_tenant_id=alloc.state_tenant_id,
        ulb_tenant_id=alloc.ulb_tenant_id,
        module_code=alloc.module_code,
        action_type="Allocation Revoked",
        details={"allocationId": alloc.allocation_id},
        changed_by=operator,
        change_reason=reason,
    )
    db.add(hist)

    await db.commit()
    return ApiResponse(success=True, message=f"Allocation '{allocation_id}' has been revoked.")


# 5. Component Restrictions Endpoints
@router.get("/restrictions", response_model=ApiResponse[List[ComponentRestrictionResponse]])
async def list_component_restrictions(
    state_tenant_id: Optional[str] = Query(None),
    ulb_tenant_id: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    states_res = await db.execute(select(StateTenant))
    states_map = {s.tenant_id: s for s in states_res.scalars().all()}

    ulbs_res = await db.execute(select(Tenant))
    ulbs_map = {u.tenant_id: u for u in ulbs_res.scalars().all()}

    stmt = select(UlbComponentRestrictionModel).order_by(desc(UlbComponentRestrictionModel.created_at))
    if state_tenant_id and state_tenant_id != "ALL":
        stmt = stmt.where(UlbComponentRestrictionModel.state_tenant_id == state_tenant_id)
    if ulb_tenant_id and ulb_tenant_id != "ALL":
        stmt = stmt.where(UlbComponentRestrictionModel.ulb_tenant_id == ulb_tenant_id)

    stmt = stmt.offset(skip).limit(limit)
    res = await db.execute(stmt)
    records = res.scalars().all()

    items = []
    for r in records:
        st = states_map.get(r.state_tenant_id)
        u = ulbs_map.get(r.ulb_tenant_id)
        items.append(
            ComponentRestrictionResponse(
                id=r.id,
                restrictionId=r.restriction_id,
                stateTenantId=r.state_tenant_id,
                stateName=st.state_name if st else "State",
                ulbTenantId=r.ulb_tenant_id,
                ulbName=u.name if u else "ULB",
                moduleCode=r.module_code,
                componentCode=r.component_code,
                componentName=r.component_name,
                restrictionType=r.restriction_type,
                restrictedActions=r.restricted_actions or [],
                reason=r.reason,
                effectiveFrom=r.effective_from,
                effectiveUntil=r.effective_until,
                isActive=r.is_active,
                createdAt=r.created_at,
                updatedAt=r.updated_at,
            )
        )

    return ApiResponse(success=True, message=f"Retrieved {len(items)} restrictions", data=items)


@router.post("/restrictions", response_model=ApiResponse[ComponentRestrictionResponse])
async def create_component_restriction(
    payload: ComponentRestrictionCreatePayload,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(get_current_user),
):
    rand_suffix = uuid.uuid4().hex[:4].upper()
    rst_id = f"RST-{payload.moduleCode.upper()}-{payload.componentCode.upper()}-{rand_suffix}"

    new_rst = UlbComponentRestrictionModel(
        restriction_id=rst_id,
        state_tenant_id=payload.stateTenantId,
        ulb_tenant_id=payload.ulbTenantId,
        module_code=payload.moduleCode.upper(),
        component_code=payload.componentCode.upper(),
        component_name=payload.componentName or payload.componentCode.upper(),
        restriction_type=payload.restrictionType,
        restricted_actions=payload.restrictedActions,
        reason=payload.reason.strip(),
        effective_from=_to_naive_utc(payload.effectiveFrom),
        effective_until=_to_naive_utc(payload.effectiveUntil),
        is_active=payload.isActive,
    )
    db.add(new_rst)

    hist = DelegationAuditHistoryModel(
        state_tenant_id=payload.stateTenantId,
        ulb_tenant_id=payload.ulbTenantId,
        module_code=payload.moduleCode.upper(),
        action_type="Component Restricted",
        details={
            "restrictionId": rst_id,
            "componentCode": payload.componentCode,
            "type": payload.restrictionType,
        },
        changed_by=user.get("email", "admin@urban.gov.in"),
        change_reason=payload.reason,
    )
    db.add(hist)

    await db.commit()
    await db.refresh(new_rst)

    return ApiResponse(
        success=True,
        message=f"Restriction '{rst_id}' applied on component '{payload.componentCode}'.",
        data=ComponentRestrictionResponse(
            id=new_rst.id,
            restrictionId=new_rst.restriction_id,
            stateTenantId=new_rst.state_tenant_id,
            ulbTenantId=new_rst.ulb_tenant_id,
            moduleCode=new_rst.module_code,
            componentCode=new_rst.component_code,
            componentName=new_rst.component_name,
            restrictionType=new_rst.restriction_type,
            restrictedActions=new_rst.restricted_actions or [],
            reason=new_rst.reason,
            effectiveFrom=new_rst.effective_from,
            effectiveUntil=new_rst.effective_until,
            isActive=new_rst.is_active,
            createdAt=new_rst.created_at,
            updatedAt=new_rst.updated_at,
        ),
    )


@router.delete("/restrictions/{id}")
async def delete_component_restriction(
    id: str,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(get_current_user),
):
    res = await db.execute(
        select(UlbComponentRestrictionModel).where(UlbComponentRestrictionModel.id == id)
    )
    rst = res.scalar_one_or_none()
    if not rst:
        raise HTTPException(status_code=404, detail="Restriction not found.")

    hist = DelegationAuditHistoryModel(
        state_tenant_id=rst.state_tenant_id,
        ulb_tenant_id=rst.ulb_tenant_id,
        module_code=rst.module_code,
        action_type="Restriction Lifted",
        details={"restrictionId": rst.restriction_id, "componentCode": rst.component_code},
        changed_by=user.get("email", "admin@urban.gov.in"),
        change_reason="Administrative restriction lifted.",
    )
    db.add(hist)

    await db.delete(rst)
    await db.commit()
    return ApiResponse(success=True, message=f"Restriction '{rst.restriction_id}' has been removed.")


# 6. Audit History Endpoint
@router.get("/history", response_model=ApiResponse[List[DelegationAuditHistoryResponse]])
async def list_delegation_history(
    state_tenant_id: Optional[str] = Query(None),
    ulb_tenant_id: Optional[str] = Query(None),
    action_type: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    states_res = await db.execute(select(StateTenant))
    states_map = {s.tenant_id: s.state_name for s in states_res.scalars().all()}

    ulbs_res = await db.execute(select(Tenant))
    ulbs_map = {u.tenant_id: u.name for u in ulbs_res.scalars().all()}

    stmt = select(DelegationAuditHistoryModel).order_by(desc(DelegationAuditHistoryModel.created_at))
    if state_tenant_id and state_tenant_id != "ALL":
        stmt = stmt.where(DelegationAuditHistoryModel.state_tenant_id == state_tenant_id)
    if ulb_tenant_id and ulb_tenant_id != "ALL":
        stmt = stmt.where(DelegationAuditHistoryModel.ulb_tenant_id == ulb_tenant_id)
    if action_type and action_type != "ALL":
        stmt = stmt.where(DelegationAuditHistoryModel.action_type == action_type)

    stmt = stmt.offset(skip).limit(limit)
    res = await db.execute(stmt)
    records = res.scalars().all()

    items = []
    for r in records:
        items.append(
            DelegationAuditHistoryResponse(
                id=r.id,
                stateTenantId=r.state_tenant_id,
                stateName=states_map.get(r.state_tenant_id, "State"),
                ulbTenantId=r.ulb_tenant_id,
                ulbName=ulbs_map.get(r.ulb_tenant_id) if r.ulb_tenant_id else None,
                moduleCode=r.module_code,
                actionType=r.action_type,
                details=r.details,
                changedBy=r.changed_by,
                changeReason=r.change_reason,
                createdAt=r.created_at,
            )
        )

    return ApiResponse(success=True, message=f"Retrieved {len(items)} history logs", data=items)


# 7. Comprehensive Hierarchy Access Validator
@router.get("/verify-access/{ulb_tenant_id}/{module_code}/{component_code}/{action}", response_model=ApiResponse[EffectivePermissionCheckResponse])
async def verify_hierarchy_access(
    ulb_tenant_id: str,
    module_code: str,
    component_code: str,
    action: str,
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    m_code = module_code.strip().upper()
    c_code = component_code.strip().upper()
    act = action.strip().upper()
    traces: List[HierarchyVerificationTrace] = []

    # 1. ULB Verification
    u_res = await db.execute(select(Tenant).where(Tenant.tenant_id == ulb_tenant_id))
    ulb = u_res.scalar_one_or_none()
    if not ulb:
        traces.append(HierarchyVerificationTrace(step="Level 2 ULB Existence", status="FAIL", message=f"ULB '{ulb_tenant_id}' not found in registry."))
        return ApiResponse(success=True, data=EffectivePermissionCheckResponse(allowed=False, ulbTenantId=ulb_tenant_id, moduleCode=m_code, componentCode=c_code, action=act, reason="ULB tenant not found", traces=traces))

    if ulb.status != "Active":
        traces.append(HierarchyVerificationTrace(step="Level 2 ULB Status", status="FAIL", message=f"ULB '{ulb.name}' status is '{ulb.status}' (Inactive)."))
        return ApiResponse(success=True, data=EffectivePermissionCheckResponse(allowed=False, ulbTenantId=ulb_tenant_id, moduleCode=m_code, componentCode=c_code, action=act, reason=f"ULB status is {ulb.status}", traces=traces))

    traces.append(HierarchyVerificationTrace(step="Level 2 ULB Status", status="PASS", message=f"ULB '{ulb.name}' ({ulb.ulb_type}) is Active."))

    # 2. Parent State Verification
    st_res = await db.execute(select(StateTenant).where(StateTenant.tenant_id == ulb.parent_state_tenant_id))
    state = st_res.scalar_one_or_none()
    if not state or state.status != "Active":
        traces.append(HierarchyVerificationTrace(step="Level 1 Parent State", status="FAIL", message="Parent state tenant is not Active or missing."))
        return ApiResponse(success=True, data=EffectivePermissionCheckResponse(allowed=False, ulbTenantId=ulb_tenant_id, moduleCode=m_code, componentCode=c_code, action=act, reason="Parent state not active", traces=traces))

    traces.append(HierarchyVerificationTrace(step="Level 1 Parent State", status="PASS", message=f"Parent State '{state.state_name}' is Active."))

    # 3. State Active Subscription Check
    sub_res = await db.execute(
        select(StateModuleSubscription).where(
            StateModuleSubscription.state_tenant_id == state.tenant_id,
            StateModuleSubscription.status == "Active",
        )
    )
    active_subs = sub_res.scalars().all()
    state_has_module = False
    for s in active_subs:
        for m in (s.subscribed_modules or []):
            code = m.get("code") if isinstance(m, dict) else m
            if code and code.upper() == m_code:
                state_has_module = True
                break
        if state_has_module:
            break

    if not state_has_module:
        traces.append(HierarchyVerificationTrace(step="State Module Subscription", status="FAIL", message=f"Parent state '{state.state_name}' does NOT have an active subscription for module '{m_code}'."))
        return ApiResponse(success=True, data=EffectivePermissionCheckResponse(allowed=False, ulbTenantId=ulb_tenant_id, moduleCode=m_code, componentCode=c_code, action=act, reason=f"Module {m_code} not subscribed by parent state", traces=traces))

    traces.append(HierarchyVerificationTrace(step="State Module Subscription", status="PASS", message=f"Parent state has valid active subscription for '{m_code}'."))

    # 4. State Delegation Policy
    rule_res = await db.execute(
        select(DelegationRuleModel).where(
            DelegationRuleModel.state_tenant_id == state.tenant_id,
            DelegationRuleModel.rule_status == "Active",
        )
    )
    rules = rule_res.scalars().all()
    for r in rules:
        if r.delegation_mode == "No Delegation":
            traces.append(HierarchyVerificationTrace(step="State Delegation Policy", status="FAIL", message=f"State policy '{r.rule_name}' sets mode 'No Delegation'."))
            return ApiResponse(success=True, data=EffectivePermissionCheckResponse(allowed=False, ulbTenantId=ulb_tenant_id, moduleCode=m_code, componentCode=c_code, action=act, reason="State policy blocks delegation", traces=traces))

    traces.append(HierarchyVerificationTrace(step="State Delegation Policy", status="PASS", message="State policy allows sub-tenant cascade delegation."))

    # 5. ULB Module Allocation Check
    alloc_res = await db.execute(
        select(UlbModuleAllocationModel).where(
            UlbModuleAllocationModel.ulb_tenant_id == ulb_tenant_id,
            UlbModuleAllocationModel.module_code == m_code,
            UlbModuleAllocationModel.status == "Active",
        )
    )
    alloc = alloc_res.scalar_one_or_none()
    if not alloc:
        traces.append(HierarchyVerificationTrace(step="ULB Allocation", status="FAIL", message=f"ULB '{ulb.name}' has no active allocation for module '{m_code}'."))
        return ApiResponse(success=True, data=EffectivePermissionCheckResponse(allowed=False, ulbTenantId=ulb_tenant_id, moduleCode=m_code, componentCode=c_code, action=act, reason=f"ULB has no allocation for {m_code}", traces=traces))

    if alloc.allocated_components and c_code not in [c.upper() for c in alloc.allocated_components]:
        traces.append(HierarchyVerificationTrace(step="Component Scope", status="FAIL", message=f"Component '{c_code}' is not included in ULB's allocated component list."))
        return ApiResponse(success=True, data=EffectivePermissionCheckResponse(allowed=False, ulbTenantId=ulb_tenant_id, moduleCode=m_code, componentCode=c_code, action=act, reason=f"Component {c_code} not allocated to ULB", traces=traces))

    if alloc.allowed_actions and act not in [a.upper() for a in alloc.allowed_actions]:
        traces.append(HierarchyVerificationTrace(step="Action Permissions", status="FAIL", message=f"Action '{act}' is not permitted under ULB's allocation."))
        return ApiResponse(success=True, data=EffectivePermissionCheckResponse(allowed=False, ulbTenantId=ulb_tenant_id, moduleCode=m_code, componentCode=c_code, action=act, reason=f"Action {act} not permitted", traces=traces))

    traces.append(HierarchyVerificationTrace(step="ULB Allocation", status="PASS", message=f"Active allocation '{alloc.allocation_id}' grants component '{c_code}' action '{act}'."))

    # 6. Component Restriction Check
    rst_res = await db.execute(
        select(UlbComponentRestrictionModel).where(
            UlbComponentRestrictionModel.ulb_tenant_id == ulb_tenant_id,
            UlbComponentRestrictionModel.component_code == c_code,
            UlbComponentRestrictionModel.is_active == True,
        )
    )
    rst = rst_res.scalar_one_or_none()
    if rst:
        if rst.restriction_type == "Block Entire Component":
            traces.append(HierarchyVerificationTrace(step="Component Restriction Guard", status="FAIL", message=f"Active restriction '{rst.restriction_id}' blocks component entirely. Reason: {rst.reason}"))
            return ApiResponse(success=True, data=EffectivePermissionCheckResponse(allowed=False, ulbTenantId=ulb_tenant_id, moduleCode=m_code, componentCode=c_code, action=act, reason=f"Component blocked: {rst.reason}", traces=traces))

        if rst.restriction_type == "Block Selected Actions" and act in [a.upper() for a in (rst.restricted_actions or [])]:
            traces.append(HierarchyVerificationTrace(step="Component Restriction Guard", status="FAIL", message=f"Active restriction blocks action '{act}'. Reason: {rst.reason}"))
            return ApiResponse(success=True, data=EffectivePermissionCheckResponse(allowed=False, ulbTenantId=ulb_tenant_id, moduleCode=m_code, componentCode=c_code, action=act, reason=f"Action blocked: {rst.reason}", traces=traces))

        if rst.restriction_type == "Read Only" and act not in ["VIEW", "EXPORT"]:
            traces.append(HierarchyVerificationTrace(step="Component Restriction Guard", status="FAIL", message=f"Component is under Read-Only restriction. Mutating action '{act}' is blocked."))
            return ApiResponse(success=True, data=EffectivePermissionCheckResponse(allowed=False, ulbTenantId=ulb_tenant_id, moduleCode=m_code, componentCode=c_code, action=act, reason="Component restricted to Read Only", traces=traces))

    traces.append(HierarchyVerificationTrace(step="Component Restriction Guard", status="PASS", message="No active restriction blocks this action."))

    return ApiResponse(
        success=True,
        data=EffectivePermissionCheckResponse(
            allowed=True,
            ulbTenantId=ulb_tenant_id,
            moduleCode=m_code,
            componentCode=c_code,
            action=act,
            reason="Full hierarchy validation passed. Access authorized.",
            traces=traces,
        ),
    )

