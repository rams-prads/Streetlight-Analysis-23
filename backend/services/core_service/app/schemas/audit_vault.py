import datetime
from typing import List, Optional, Any, Dict
from pydantic import field_validator
from app.schemas.tenant import CamelModel, ApiResponse


# 1. Audit Event Schemas
class ImmutableAuditEventResponse(CamelModel):
    id: str
    eventId: str
    sequenceNumber: int
    tenantId: Optional[str] = None
    tenantName: Optional[str] = None
    tenantLevel: str  # Level 0, Level 1, Level 2
    subTenantId: Optional[str] = None
    subTenantName: Optional[str] = None
    stateCode: Optional[str] = None
    moduleCode: Optional[str] = None
    componentCode: Optional[str] = None
    eventCategory: str
    action: str
    severity: str  # Informational, Low, Medium, High, Critical
    actorId: str
    actorRole: Optional[str] = None
    ipAddress: str
    userAgent: Optional[str] = None
    correlationId: str
    result: str  # SUCCESS, FAILURE, DENIED, ERROR
    details: Optional[Dict[str, Any]] = None
    prevEventHash: str
    eventHash: str
    signature: Optional[str] = None
    isLegalHold: bool = False
    createdAt: datetime.datetime


class AuditEventCreatePayload(CamelModel):
    tenantId: Optional[str] = None
    tenantLevel: str = "Level 0"
    subTenantId: Optional[str] = None
    stateCode: Optional[str] = None
    moduleCode: Optional[str] = None
    componentCode: Optional[str] = None
    eventCategory: str
    action: str
    severity: str = "Informational"
    actorId: str
    actorRole: Optional[str] = "Platform Super Admin"
    ipAddress: str = "127.0.0.1"
    userAgent: Optional[str] = None
    correlationId: Optional[str] = None
    result: str = "SUCCESS"
    details: Optional[Dict[str, Any]] = None
    isLegalHold: bool = False


# 2. Audit Dashboard Metrics
class AuditDashboardStats(CamelModel):
    totalAuditEvents: int = 0
    criticalEvents: int = 0
    failedAuthEvents: int = 0
    privilegedOperations: int = 0
    integrityStatus: str = "100% Tamper-Evident (Chained)"
    lastVerifiedAt: Optional[datetime.datetime] = None
    activeRetentionPolicies: int = 0
    legalHoldEvents: int = 0


# 3. Hash Verification Schemas
class HashVerificationResponse(CamelModel):
    id: str
    jobId: str
    jobName: str
    verificationScope: str
    tenantId: Optional[str] = None
    fromTimestamp: datetime.datetime
    toTimestamp: datetime.datetime
    algorithm: str
    verificationMode: str
    notificationRecipients: List[str] = []
    remarks: Optional[str] = None
    firstEventHash: Optional[str] = None
    lastEventHash: Optional[str] = None
    expectedHash: Optional[str] = None
    calculatedHash: Optional[str] = None
    verificationResult: str  # VALID_INTEGRITY_INTACT, TAMPER_DETECTED, CHAIN_BROKEN
    totalVerifiedEvents: int = 0
    mismatchCount: int = 0
    executedBy: str
    createdAt: datetime.datetime


class HashVerificationCreatePayload(CamelModel):
    jobName: str
    verificationScope: str = "Global Platform"
    tenantId: Optional[str] = None
    fromTimestamp: datetime.datetime
    toTimestamp: datetime.datetime
    algorithm: str = "SHA-256"
    verificationMode: str = "On-Demand Scan"
    notificationRecipients: List[str] = []
    remarks: Optional[str] = None

    @field_validator("fromTimestamp", "toTimestamp", mode="after")
    @classmethod
    def ensure_naive_utc(cls, v: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
        if v is not None and v.tzinfo is not None:
            return v.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return v


# 4. Retention Policy Schemas
class RetentionPolicyResponse(CamelModel):
    id: str
    policyCode: str
    policyName: str
    applicableTenantLevels: List[str] = []
    eventCategories: List[str] = []
    retentionPeriod: int
    retentionUnit: str
    archiveRequired: bool
    archiveDestination: Optional[str] = None
    legalHoldEnabled: bool
    effectiveDate: datetime.datetime
    policyStatus: str
    description: Optional[str] = None
    createdAt: datetime.datetime
    updatedAt: Optional[datetime.datetime] = None


class RetentionPolicyCreatePayload(CamelModel):
    policyCode: str
    policyName: str
    applicableTenantLevels: List[str] = ["Level 0", "Level 1", "Level 2"]
    eventCategories: List[str] = []
    retentionPeriod: int = 7
    retentionUnit: str = "Years"
    archiveRequired: bool = True
    archiveDestination: Optional[str] = "State Government Cold Storage Vault"
    legalHoldEnabled: bool = False
    effectiveDate: datetime.datetime
    policyStatus: str = "Active"
    description: Optional[str] = None

    @field_validator("effectiveDate", mode="after")
    @classmethod
    def ensure_naive_utc(cls, v: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
        if v is not None and v.tzinfo is not None:
            return v.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return v


class RetentionPolicyUpdatePayload(CamelModel):
    policyName: Optional[str] = None
    applicableTenantLevels: Optional[List[str]] = None
    eventCategories: Optional[List[str]] = None
    retentionPeriod: Optional[int] = None
    retentionUnit: Optional[str] = None
    archiveRequired: Optional[bool] = None
    archiveDestination: Optional[str] = None
    legalHoldEnabled: Optional[bool] = None
    effectiveDate: Optional[datetime.datetime] = None
    policyStatus: Optional[str] = None
    description: Optional[str] = None

    @field_validator("effectiveDate", mode="after")
    @classmethod
    def ensure_naive_utc(cls, v: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
        if v is not None and v.tzinfo is not None:
            return v.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return v


# 5. Audit Export Schemas
class AuditExportResponse(CamelModel):
    id: str
    exportId: str
    exportName: str
    exportFormat: str
    tenantScope: str
    stateTenantId: Optional[str] = None
    ulbTenantId: Optional[str] = None
    eventCategories: List[str] = []
    dateFrom: datetime.datetime
    dateTo: datetime.datetime
    includeHashInfo: bool
    maskSensitiveInfo: bool
    exportReason: str
    approvalReference: Optional[str] = None
    status: str
    exportedBy: str
    fileSizeBytes: int = 0
    fileChecksum: Optional[str] = None
    createdAt: datetime.datetime


class AuditExportCreatePayload(CamelModel):
    exportName: str
    exportFormat: str = "CSV"  # CSV, JSON, PDF
    tenantScope: str = "All Tenants"
    stateTenantId: Optional[str] = None
    ulbTenantId: Optional[str] = None
    eventCategories: List[str] = []
    dateFrom: datetime.datetime
    dateTo: datetime.datetime
    includeHashInfo: bool = True
    maskSensitiveInfo: bool = True
    exportReason: str
    approvalReference: Optional[str] = None

    @field_validator("dateFrom", "dateTo", mode="after")
    @classmethod
    def ensure_naive_utc(cls, v: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
        if v is not None and v.tzinfo is not None:
            return v.astimezone(datetime.timezone.utc).replace(tzinfo=None)
        return v

