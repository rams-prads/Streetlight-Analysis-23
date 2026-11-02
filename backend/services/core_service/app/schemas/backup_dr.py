import datetime
from typing import List, Optional, Any, Dict
from app.schemas.tenant import CamelModel, ApiResponse


# 1. System-Generated KPI Metrics
class BackupDrOverviewStats(CamelModel):
    totalBackups: int = 0
    successfulBackups: int = 0
    failedBackups: int = 0
    totalStoredDataTb: float = 0.0
    lastBackupTime: Optional[str] = None
    currentRpoMinutes: float = 0.0
    currentRtoMinutes: float = 0.0
    activePoliciesCount: int = 0
    drDrillReadinessPct: float = 100.0


# 2. Backup Policy Schemas
class BackupPolicyPayload(CamelModel):
    policyName: str
    policyCode: str
    backupType: str = "Full Backup"
    backupScope: str = "Platform Full Database"
    environment: str = "Production"
    databaseCluster: str = "pg-aurora-cluster-prod"
    databaseName: str = "urban_core_prod"
    tenantScope: str = "All State Tenants"
    backupDestination: str = "AWS S3 (Immutable Glacier Lock)"
    storageBucketPath: str
    backupFrequency: str = "Daily"
    backupSchedule: str = "0 2 * * * (02:00 AM IST)"
    timeZone: str = "Asia/Kolkata (IST)"
    retentionPeriod: int = 90
    retentionUnit: str = "Days"
    encryptionEnabled: bool = True
    compressionEnabled: bool = True
    backupVerification: bool = True
    notificationRecipients: List[str] = []
    policyStatus: str = "Active"


class BackupPolicyResponse(CamelModel):
    id: str
    policyName: str
    policyCode: str
    backupType: str
    backupScope: str
    environment: str
    databaseCluster: str
    databaseName: str
    tenantScope: str
    backupDestination: str
    storageBucketPath: str
    backupFrequency: str
    backupSchedule: str
    timeZone: str
    retentionPeriod: int
    retentionUnit: str
    encryptionEnabled: bool
    compressionEnabled: bool
    backupVerification: bool
    notificationRecipients: List[str] = []
    policyStatus: str
    createdAt: datetime.datetime
    updatedAt: Optional[datetime.datetime] = None


# 3. Backup History / Job Schemas
class BackupJobResponse(CamelModel):
    id: str
    jobId: str
    policyCode: str
    policyName: str
    environment: str
    databaseCluster: str
    databaseName: str
    backupType: str
    executionStatus: str
    startTime: datetime.datetime
    completionTime: datetime.datetime
    durationSeconds: int
    fileSizeBytes: int
    fileSizeFormatted: str
    storageLocation: str
    checksumSha256: str
    verificationStatus: str
    verificationResult: str
    createdAt: datetime.datetime


# 4. Restore Operations Schemas
class RestoreJobPayload(CamelModel):
    restoreJobName: str
    sourceBackupId: str
    sourceDatabase: str
    targetEnvironment: str
    targetDatabase: str
    restoreType: str = "Full Database Restore"
    restoreDestination: str
    restoreTimestamp: Optional[datetime.datetime] = None
    includeTransactionLogs: bool = True
    validationRequired: bool = True
    approvalAuthority: str
    changeReference: str
    restoreReason: str
    finalConfirmation: bool = True


class RestoreJobResponse(CamelModel):
    id: str
    restoreJobName: str
    sourceBackupId: str
    sourceDatabase: str
    targetEnvironment: str
    targetDatabase: str
    restoreType: str
    restoreDestination: str
    restoreTimestamp: Optional[datetime.datetime] = None
    includeTransactionLogs: bool
    validationRequired: bool
    approvalAuthority: str
    changeReference: str
    restoreReason: str
    executionStatus: str
    durationSeconds: int
    initiatedBy: str
    createdAt: datetime.datetime


# 5. PITR Window Status
class PitrWindowStatus(CamelModel):
    databaseCluster: str
    databaseName: str
    earliestRestoreTime: datetime.datetime
    latestRestoreTime: datetime.datetime
    currentWalLsn: str
    walArchiveLocation: str
    recoveryWindowDays: int
    streamingReplicationStatus: str


# 6. Disaster Recovery Drill Schemas
class DrillExecutionPayload(CamelModel):
    drillName: str
    drillCode: str
    drillType: str = "Cross-Region Failover"
    environment: str = "Production Simulation"
    primaryRegion: str = "ap-south-1 (Mumbai Primary)"
    secondaryRegion: str = "ap-south-2 (Hyderabad Secondary)"
    servicesInScope: List[str] = []
    databasesInScope: List[str] = []
    plannedStartDate: datetime.datetime
    plannedEndDate: datetime.datetime
    expectedRpoMinutes: int = 5
    expectedRtoMinutes: int = 15
    drillCoordinator: str
    approvalAuthority: str
    notificationRecipients: List[str] = []
    drillObjective: str
    rollbackPlan: str


class DrillExecutionResponse(CamelModel):
    id: str
    drillName: str
    drillCode: str
    drillType: str
    environment: str
    primaryRegion: str
    secondaryRegion: str
    servicesInScope: List[str] = []
    databasesInScope: List[str] = []
    plannedStartDate: datetime.datetime
    plannedEndDate: datetime.datetime
    expectedRpoMinutes: int
    expectedRtoMinutes: int
    actualRpoMinutes: float
    actualRtoMinutes: float
    recoverySuccessRatePct: float
    serviceAvailabilityPct: float
    dataIntegrityResult: str
    completionStatus: str
    drillCoordinator: str
    approvalAuthority: str
    notificationRecipients: List[str] = []
    drillObjective: str
    rollbackPlan: str
    findings: str
    createdAt: datetime.datetime

