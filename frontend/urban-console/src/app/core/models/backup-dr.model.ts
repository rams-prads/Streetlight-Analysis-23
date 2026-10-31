export interface BackupDrOverviewStats {
  totalBackups: number;
  successfulBackups: number;
  failedBackups: number;
  totalStoredDataTb: number;
  lastBackupTime?: string | null;
  currentRpoMinutes: number;
  currentRtoMinutes: number;
  activePoliciesCount: number;
  drDrillReadinessPct: number;
}

export interface BackupPolicyItem {
  id: string;
  policyName: string;
  policyCode: string;
  backupType: 'Full Backup' | 'Incremental Backup' | 'Differential Backup' | 'WAL / Transaction Log Backup' | string;
  backupScope: 'Platform Full Database' | 'Tenant Scoped' | 'Configuration Only' | 'Audit Vault WORM' | string;
  environment: 'Production' | 'Staging' | 'Development' | string;
  databaseCluster: string;
  databaseName: string;
  tenantScope: string;
  backupDestination: string;
  storageBucketPath: string;
  backupFrequency: 'Hourly' | 'Daily' | 'Weekly' | 'Monthly' | 'Custom' | string;
  backupSchedule: string;
  timeZone: string;
  retentionPeriod: number;
  retentionUnit: 'Days' | 'Months' | 'Years' | string;
  encryptionEnabled: boolean;
  compressionEnabled: boolean;
  backupVerification: boolean;
  notificationRecipients: string[];
  policyStatus: 'Active' | 'Paused' | 'Draft' | string;
  createdAt: string;
  updatedAt?: string | null;
}

export interface BackupPolicyPayload {
  policyName: string;
  policyCode: string;
  backupType: string;
  backupScope: string;
  environment: string;
  databaseCluster: string;
  databaseName: string;
  tenantScope: string;
  backupDestination: string;
  storageBucketPath: string;
  backupFrequency: string;
  backupSchedule: string;
  timeZone: string;
  retentionPeriod: number;
  retentionUnit: string;
  encryptionEnabled: boolean;
  compressionEnabled: boolean;
  backupVerification: boolean;
  notificationRecipients: string[];
  policyStatus: string;
}

export interface BackupJobItem {
  id: string;
  jobId: string;
  policyCode: string;
  policyName: string;
  environment: string;
  databaseCluster: string;
  databaseName: string;
  backupType: string;
  executionStatus: 'Completed' | 'In Progress' | 'Failed' | 'Verified' | string;
  startTime: string;
  completionTime: string;
  durationSeconds: number;
  fileSizeBytes: number;
  fileSizeFormatted: string;
  storageLocation: string;
  checksumSha256: string;
  verificationStatus: 'Verified (Restorable)' | 'Pending Verification' | 'Checksum Mismatch' | string;
  verificationResult: string;
  createdAt: string;
}

export interface RestoreJobItem {
  id: string;
  restoreJobName: string;
  sourceBackupId: string;
  sourceDatabase: string;
  targetEnvironment: 'Staging Recovery Sandbox' | 'Development Sandbox' | 'Production (Requires Dual-Auth)' | string;
  targetDatabase: string;
  restoreType: 'Full Database Restore' | 'Point-in-Time Restore' | 'Selected Tenant Restore' | 'Test Environment Restore' | string;
  restoreDestination: string;
  restoreTimestamp?: string | null;
  includeTransactionLogs: boolean;
  validationRequired: boolean;
  approvalAuthority: string;
  changeReference: string;
  restoreReason: string;
  executionStatus: 'Completed' | 'In Progress' | 'Validating' | 'Failed' | string;
  durationSeconds: number;
  initiatedBy: string;
  createdAt: string;
}

export interface RestoreJobPayload {
  restoreJobName: string;
  sourceBackupId: string;
  sourceDatabase: string;
  targetEnvironment: string;
  targetDatabase: string;
  restoreType: string;
  restoreDestination: string;
  restoreTimestamp?: string | null;
  includeTransactionLogs: boolean;
  validationRequired: boolean;
  approvalAuthority: string;
  changeReference: string;
  restoreReason: string;
  finalConfirmation: boolean;
}

export interface PitrWindowStatus {
  databaseCluster: string;
  databaseName: string;
  earliestRestoreTime: string;
  latestRestoreTime: string;
  currentWalLsn: string;
  walArchiveLocation: string;
  recoveryWindowDays: number;
  streamingReplicationStatus: string;
}

export interface DrillExecutionItem {
  id: string;
  drillName: string;
  drillCode: string;
  drillType: 'Cross-Region Failover' | 'Simulated Ransomware Recovery' | 'Database Corruption Playbook' | 'Split-Brain Isolation' | string;
  environment: 'Production Simulation' | 'Pre-Prod Staging' | string;
  primaryRegion: string;
  secondaryRegion: string;
  servicesInScope: string[];
  databasesInScope: string[];
  plannedStartDate: string;
  plannedEndDate: string;
  expectedRpoMinutes: number;
  expectedRtoMinutes: number;
  actualRpoMinutes: number;
  actualRtoMinutes: number;
  recoverySuccessRatePct: number;
  serviceAvailabilityPct: number;
  dataIntegrityResult: string;
  completionStatus: 'Passed - SLA Compliant' | 'In Progress' | 'Scheduled' | 'Failed' | string;
  drillCoordinator: string;
  approvalAuthority: string;
  notificationRecipients: string[];
  drillObjective: string;
  rollbackPlan: string;
  findings: string;
  createdAt: string;
}

export interface DrillExecutionPayload {
  drillName: string;
  drillCode: string;
  drillType: string;
  environment: string;
  primaryRegion: string;
  secondaryRegion: string;
  servicesInScope: string[];
  databasesInScope: string[];
  plannedStartDate: string;
  plannedEndDate: string;
  expectedRpoMinutes: number;
  expectedRtoMinutes: number;
  drillCoordinator: string;
  approvalAuthority: string;
  notificationRecipients: string[];
  drillObjective: string;
  rollbackPlan: string;
}

