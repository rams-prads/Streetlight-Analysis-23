import datetime
from typing import List, Optional, Any, Dict
from pydantic import field_validator
from app.schemas.tenant import CamelModel, ApiResponse


# 1. Delegation Rule Schemas
class DelegationRuleResponse(CamelModel):
    id: str
    ruleCode: str
    ruleName: str
    stateTenantId: str
    stateName: Optional[str] = None
    stateCode: Optional[str] = None
    applicableUlbTypes: List[str] = []
    delegationMode: str  # Full Delegation, Selective Delegation, Restricted Delegation, No Delegation
    allowModuleDelegation: bool = True
    allowComponentDelegation: bool = True
    allowRoleDelegation: bool = True
    requireStateApproval: bool = True
    effectiveFrom: datetime.datetime
    effectiveUntil: Optional[datetime.datetime] = None
    description: str
    ruleStatus: str  # Active, Draft, Deprecated
    createdAt: datetime.datetime
    updatedAt: Optional[datetime.datetime] = None


class DelegationRuleCreatePayload(CamelModel):
    ruleCode: str
    ruleName: str
    stateTenantId: str
    applicableUlbTypes: List[str] = []
    delegationMode: str = "Selective Delegation"
    allowModuleDelegation: bool = True
    allowComponentDelegation: bool = True
    allowRoleDelegation: bool = True
    requireStateApproval: bool = True
    effectiveFrom: datetime.datetime
    effectiveUntil: Optional[datetime.datetime] = None
    description: str
    ruleStatus: str = "Active"

    @field_validator("effectiveFrom", "effectiveUntil", mode="after")
    @classmethod
    def ensure_naive_utc(cls, v: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
        if v is not None and v.tzinfo is not None:
            return v.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return v


class DelegationRuleUpdatePayload(CamelModel):
    ruleName: Optional[str] = None
    applicableUlbTypes: Optional[List[str]] = None
    delegationMode: Optional[str] = None
    allowModuleDelegation: Optional[bool] = None
    allowComponentDelegation: Optional[bool] = None
    allowRoleDelegation: Optional[bool] = None
    requireStateApproval: Optional[bool] = None
    effectiveFrom: Optional[datetime.datetime] = None
    effectiveUntil: Optional[datetime.datetime] = None
    description: Optional[str] = None
    ruleStatus: Optional[str] = None

    @field_validator("effectiveFrom", "effectiveUntil", mode="after")
    @classmethod
    def ensure_naive_utc(cls, v: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
        if v is not None and v.tzinfo is not None:
            return v.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return v


# 2. ULB Module Allocation Schemas
class UlbAllocationResponse(CamelModel):
    id: str
    allocationId: str
    stateTenantId: str
    stateName: Optional[str] = None
    ulbTenantId: str
    ulbName: Optional[str] = None
    ulbCode: Optional[str] = None
    ulbType: Optional[str] = None
    moduleCode: str
    moduleName: str
    allocatedComponents: List[str] = []
    allowedActions: List[str] = []
    startDate: datetime.datetime
    endDate: Optional[datetime.datetime] = None
    status: str  # Active, Suspended, Revoked, Draft
    approvalReference: Optional[str] = None
    remarks: Optional[str] = None
    createdAt: datetime.datetime
    updatedAt: Optional[datetime.datetime] = None


class UlbAllocationCreatePayload(CamelModel):
    stateTenantId: str
    ulbTenantIds: List[str]
    moduleCodes: List[str]
    allocatedComponents: List[str] = []  # Component codes, or empty for all
    allowedActions: List[str] = ["VIEW", "CREATE", "UPDATE", "APPROVE"]
    startDate: datetime.datetime
    endDate: Optional[datetime.datetime] = None
    status: str = "Active"
    approvalReference: Optional[str] = None
    remarks: Optional[str] = None

    @field_validator("startDate", "endDate", mode="after")
    @classmethod
    def ensure_naive_utc(cls, v: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
        if v is not None and v.tzinfo is not None:
            return v.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return v


# 3. Component Restriction Schemas
class ComponentRestrictionResponse(CamelModel):
    id: str
    restrictionId: str
    stateTenantId: str
    stateName: Optional[str] = None
    ulbTenantId: str
    ulbName: Optional[str] = None
    moduleCode: str
    componentCode: str
    componentName: Optional[str] = None
    restrictionType: str  # Block Entire Component, Block Selected Actions, Read Only, Restrict Data Scope
    restrictedActions: List[str] = []
    reason: str
    effectiveFrom: datetime.datetime
    effectiveUntil: Optional[datetime.datetime] = None
    isActive: bool = True
    createdAt: datetime.datetime
    updatedAt: Optional[datetime.datetime] = None


class ComponentRestrictionCreatePayload(CamelModel):
    stateTenantId: str
    ulbTenantId: str
    moduleCode: str
    componentCode: str
    componentName: Optional[str] = None
    restrictionType: str = "Block Selected Actions"
    restrictedActions: List[str] = []
    reason: str
    effectiveFrom: datetime.datetime
    effectiveUntil: Optional[datetime.datetime] = None
    isActive: bool = True

    @field_validator("effectiveFrom", "effectiveUntil", mode="after")
    @classmethod
    def ensure_naive_utc(cls, v: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
        if v is not None and v.tzinfo is not None:
            return v.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return v


# 4. Audit History Schemas
class DelegationAuditHistoryResponse(CamelModel):
    id: str
    stateTenantId: str
    stateName: Optional[str] = None
    ulbTenantId: Optional[str] = None
    ulbName: Optional[str] = None
    moduleCode: Optional[str] = None
    actionType: str
    details: Optional[Dict[str, Any]] = None
    changedBy: str
    changeReason: Optional[str] = None
    createdAt: datetime.datetime


# 5. Hierarchy Verification / Trace
class HierarchyVerificationTrace(CamelModel):
    step: str
    status: str  # PASS, FAIL, WARN
    message: str


class EffectivePermissionCheckResponse(CamelModel):
    allowed: bool
    ulbTenantId: str
    moduleCode: str
    componentCode: str
    action: str
    reason: str
    traces: List[HierarchyVerificationTrace] = []


# 6. Overview KPI Stats
class DelegationOverviewStats(CamelModel):
    totalRules: int = 0
    activeRules: int = 0
    totalAllocations: int = 0
    activeAllocations: int = 0
    totalRestrictions: int = 0
    activeRestrictions: int = 0
    delegatedUlbsCount: int = 0

