import datetime
from typing import List, Optional, Any
from pydantic import field_validator
from app.schemas.tenant import CamelModel, ApiResponse


class SubscribedModuleItem(CamelModel):
    code: str
    name: str
    version: str = "1.0.0"
    category: Optional[str] = None
    status: str = "Active"


class StateSubscriptionResponse(CamelModel):
    id: str
    subscriptionId: str
    stateTenantId: str
    stateName: Optional[str] = None
    stateCode: Optional[str] = None
    subscriptionName: str
    subscriptionType: str  # Standard, Premium, Custom, Government Sponsored
    subscribedModules: List[SubscribedModuleItem] = []
    totalModules: int = 0
    activeModulesCount: int = 0
    startDate: datetime.datetime
    endDate: Optional[datetime.datetime] = None
    billingCycle: Optional[str] = "Yearly"  # Monthly, Quarterly, Half-Yearly, Yearly, Custom
    status: str  # Active, Suspended, Expired, Revoked, Draft
    autoRenewal: bool = False
    remarks: Optional[str] = None
    approvalReference: Optional[str] = None
    createdAt: datetime.datetime
    updatedAt: Optional[datetime.datetime] = None


class StateSubscriptionCreatePayload(CamelModel):
    stateTenantId: str
    subscriptionName: str
    subscriptionType: str = "Standard"
    moduleCodes: List[str]
    startDate: datetime.datetime
    endDate: Optional[datetime.datetime] = None
    billingCycle: Optional[str] = "Yearly"
    status: str = "Active"
    autoRenewal: bool = False
    remarks: Optional[str] = None
    approvalReference: Optional[str] = None

    @field_validator("startDate", "endDate", mode="after")
    @classmethod
    def ensure_naive_utc(cls, v: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
        if v is not None and v.tzinfo is not None:
            return v.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return v


class StateSubscriptionRenewPayload(CamelModel):
    subscriptionId: str
    renewalType: str = "Term Extension"  # Term Extension, Module Addition & Renewal, Full Overhaul
    newStartDate: datetime.datetime
    newEndDate: datetime.datetime
    additionalModuleCodes: List[str] = []
    renewalRemarks: str
    approvalReference: Optional[str] = None
    notifyTenant: bool = True

    @field_validator("newStartDate", "newEndDate", mode="after")
    @classmethod
    def ensure_naive_utc(cls, v: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
        if v is not None and v.tzinfo is not None:
            return v.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return v


class StateSubscriptionHistoryResponse(CamelModel):
    id: str
    subscriptionId: str
    stateTenantId: str
    stateName: Optional[str] = None
    moduleCode: Optional[str] = None
    actionType: str
    previousStatus: Optional[str] = None
    newStatus: Optional[str] = None
    previousExpiryDate: Optional[datetime.datetime] = None
    newExpiryDate: Optional[datetime.datetime] = None
    changedModules: List[Any] = []
    changedBy: str
    changeReason: Optional[str] = None
    approvalReference: Optional[str] = None
    createdAt: datetime.datetime


class StateSubscriptionOverviewStats(CamelModel):
    totalSubscriptions: int = 0
    activeSubscriptions: int = 0
    expiringSoonCount: int = 0
    expiredOrRevokedCount: int = 0
    totalAllocatedModules: int = 0

