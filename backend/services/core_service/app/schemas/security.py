from typing import List, Optional, Any, Dict
import datetime
from app.schemas.tenant import CamelModel, ApiResponse


# -------------------------------------------------------------
# 1. RLS Policy Registry Schemas (ADM-C05.A)
# -------------------------------------------------------------
class RLSPolicyBase(CamelModel):
    policyName: str
    policyCode: str
    databaseService: str = "PostgreSQL 16 (Core Service)"
    schemaName: str = "public"
    tableName: str
    tenantKeyColumn: str = "tenant_id"
    policyType: str = "ALL"  # SELECT, INSERT, UPDATE, DELETE, ALL
    databaseCommands: List[str] = ["SELECT", "INSERT", "UPDATE", "DELETE"]
    applicableTenantLevels: List[str] = ["State (Level 1)", "ULB / City (Level 2)"]
    policyDefinition: str
    policyStatus: str = "ACTIVE"  # ACTIVE, DISABLED, PENDING_VERIFICATION
    enforcementNotes: Optional[str] = None


class RLSPolicyCreate(RLSPolicyBase):
    pass


class RLSPolicyUpdate(CamelModel):
    policyName: Optional[str] = None
    databaseService: Optional[str] = None
    schemaName: Optional[str] = None
    tableName: Optional[str] = None
    tenantKeyColumn: Optional[str] = None
    policyType: Optional[str] = None
    databaseCommands: Optional[List[str]] = None
    applicableTenantLevels: Optional[List[str]] = None
    policyDefinition: Optional[str] = None
    policyStatus: Optional[str] = None
    enforcementNotes: Optional[str] = None


class RLSPolicyResponse(RLSPolicyBase):
    id: str
    lastVerifiedAt: Optional[datetime.datetime] = None
    lastVerificationResult: str = "VERIFIED"
    verificationLatencyMs: float = 1.2
    createdAt: Optional[datetime.datetime] = None
    updatedAt: Optional[datetime.datetime] = None


class RLSPolicyValidationResult(CamelModel):
    policyId: str
    policyCode: str
    status: str  # VERIFIED, FAILED
    latencyMs: float
    verifiedAt: datetime.datetime
    details: str
    enforcedQuerySample: str


# -------------------------------------------------------------
# 2. Tenant Isolation Test Configuration & Runs (ADM-C05.B)
# -------------------------------------------------------------
class TenantIsolationTestCreate(CamelModel):
    testRunName: str
    environment: str = "Isolated Sandbox"  # Staging, Isolated Sandbox, Production-Mirror
    sourceTenant: str
    targetTenant: str
    testScenarios: List[str]
    databaseServices: List[str] = ["PostgreSQL Core", "Redis Cache"]
    tablesInScope: List[str] = ["properties", "water_accounts", "users"]
    testType: str = "Synthetic Penetration Test"  # Synthetic Penetration Test, Injection Audit, Concurrency Pool Leak
    executionMode: str = "Automated Batch"  # Automated Batch, Step-by-Step Interactive
    schedule: Optional[str] = "On-Demand"
    notificationRecipients: Optional[List[str]] = []
    stopOnCriticalFailure: bool = True


class TenantIsolationTestResponse(CamelModel):
    id: str
    testRunName: str
    environment: str
    sourceTenant: str
    targetTenant: str
    testScenarios: List[str]
    databaseServices: List[str]
    tablesInScope: List[str]
    testType: str
    executionMode: str
    schedule: Optional[str] = None
    notificationRecipients: List[str]
    stopOnCriticalFailure: bool
    status: str  # PASSED, FAILED, RUNNING, SCHEDULED
    startTime: Optional[datetime.datetime] = None
    endTime: Optional[datetime.datetime] = None
    totalTests: int = 8
    passedCount: int = 8
    failedCount: int = 0
    executionLatencyMs: float = 42.5
    createdAt: Optional[datetime.datetime] = None


class TenantIsolationTestRunResult(CamelModel):
    testRunId: str
    status: str
    totalTests: int
    passedCount: int
    failedCount: int
    latencyMs: float
    scenarioResults: List[Dict[str, Any]]


# -------------------------------------------------------------
# 3. Isolation Findings & Reports (ADM-C05.C)
# -------------------------------------------------------------
class IsolationFindingCreate(CamelModel):
    testRunId: Optional[str] = None
    severity: str = "HIGH"  # CRITICAL, HIGH, MEDIUM, LOW
    findingTitle: str
    findingDescription: str
    affectedTenant: str
    affectedResource: str
    remediationOwner: str
    remediationDueDate: str
    resolutionNotes: Optional[str] = None
    retestStatus: str = "OPEN"  # OPEN, IN_REMEDIATION, RESOLVED, VERIFIED


class IsolationFindingUpdate(CamelModel):
    severity: Optional[str] = None
    findingTitle: Optional[str] = None
    findingDescription: Optional[str] = None
    affectedTenant: Optional[str] = None
    affectedResource: Optional[str] = None
    remediationOwner: Optional[str] = None
    remediationDueDate: Optional[str] = None
    resolutionNotes: Optional[str] = None
    retestStatus: Optional[str] = None


class IsolationFindingResponse(CamelModel):
    id: str
    testRunId: Optional[str] = None
    severity: str
    findingTitle: str
    findingDescription: str
    affectedTenant: str
    affectedResource: str
    remediationOwner: str
    remediationDueDate: str
    resolutionNotes: Optional[str] = None
    retestStatus: str
    detectedAt: Optional[datetime.datetime] = None
    resolvedAt: Optional[datetime.datetime] = None


class IsolationFindingRetestResult(CamelModel):
    findingId: str
    retestStatus: str
    verificationResult: str
    testedAt: datetime.datetime
    details: str


# -------------------------------------------------------------
# 4. Security Stats Overview
# -------------------------------------------------------------
class SecuritySummaryStatsResponse(CamelModel):
    totalRlsPolicies: int
    activeRlsPolicies: int
    policyCoverageRate: float
    totalTestRuns: int
    passedTestRuns: int
    isolationPassRate: float
    openFindingsCount: int
    criticalFindingsCount: int
    remediatedFindingsCount: int

