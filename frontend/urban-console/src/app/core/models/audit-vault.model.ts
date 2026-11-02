export interface ImmutableAuditEvent {
  id: string;
  eventId: string;
  sequenceNumber: number;
  tenantId?: string | null;
  tenantName?: string | null;
  tenantLevel: 'Level 0' | 'Level 1' | 'Level 2' | string;
  subTenantId?: string | null;
  subTenantName?: string | null;
  stateCode?: string | null;
  moduleCode?: string | null;
  componentCode?: string | null;
  eventCategory: string;
  action: string;
  severity: 'Informational' | 'Low' | 'Medium' | 'High' | 'Critical';
  actorId: string;
  actorRole?: string | null;
  ipAddress: string;
  userAgent?: string | null;
  correlationId: string;
  result: 'SUCCESS' | 'FAILURE' | 'DENIED' | 'ERROR';
  details?: Record<string, any> | null;
  prevEventHash: string;
  eventHash: string;
  signature?: string | null;
  isLegalHold: boolean;
  createdAt: string;
}

export interface AuditDashboardStats {
  totalAuditEvents: number;
  criticalEvents: number;
  failedAuthEvents: number;
  privilegedOperations: number;
  integrityStatus: string;
  lastVerifiedAt?: string | null;
  activeRetentionPolicies: number;
  legalHoldEvents: number;
}

export interface HashVerificationJob {
  id: string;
  jobId: string;
  jobName: string;
  verificationScope: string;
  tenantId?: string | null;
  fromTimestamp: string;
  toTimestamp: string;
  algorithm: 'SHA-256' | 'SHA-512' | string;
  verificationMode: string;
  notificationRecipients: string[];
  remarks?: string | null;
  firstEventHash?: string | null;
  lastEventHash?: string | null;
  expectedHash?: string | null;
  calculatedHash?: string | null;
  verificationResult: 'VALID_INTEGRITY_INTACT' | 'TAMPER_DETECTED' | 'CHAIN_BROKEN' | string;
  totalVerifiedEvents: number;
  mismatchCount: number;
  executedBy: string;
  createdAt: string;
}

export interface HashVerificationCreatePayload {
  jobName: string;
  verificationScope: string;
  tenantId?: string | null;
  fromTimestamp: string;
  toTimestamp: string;
  algorithm: string;
  verificationMode: string;
  notificationRecipients: string[];
  remarks?: string | null;
}

export interface RetentionPolicy {
  id: string;
  policyCode: string;
  policyName: string;
  applicableTenantLevels: string[];
  eventCategories: string[];
  retentionPeriod: number;
  retentionUnit: 'Days' | 'Months' | 'Years' | string;
  archiveRequired: boolean;
  archiveDestination?: string | null;
  legalHoldEnabled: boolean;
  effectiveDate: string;
  policyStatus: 'Active' | 'Draft' | 'Inactive' | string;
  description?: string | null;
  createdAt: string;
  updatedAt?: string | null;
}

export interface RetentionPolicyCreatePayload {
  policyCode: string;
  policyName: string;
  applicableTenantLevels: string[];
  eventCategories: string[];
  retentionPeriod: number;
  retentionUnit: string;
  archiveRequired: boolean;
  archiveDestination?: string | null;
  legalHoldEnabled: boolean;
  effectiveDate: string;
  policyStatus: string;
  description?: string | null;
}

export interface AuditExportJob {
  id: string;
  exportId: string;
  exportName: string;
  exportFormat: 'CSV' | 'JSON' | 'PDF' | string;
  tenantScope: string;
  stateTenantId?: string | null;
  ulbTenantId?: string | null;
  eventCategories: string[];
  dateFrom: string;
  dateTo: string;
  includeHashInfo: boolean;
  maskSensitiveInfo: boolean;
  exportReason: string;
  approvalReference?: string | null;
  status: 'Completed' | 'Processing' | 'Archived' | string;
  exportedBy: string;
  fileSizeBytes: number;
  fileChecksum?: string | null;
  createdAt: string;
}

export interface AuditExportCreatePayload {
  exportName: string;
  exportFormat: string;
  tenantScope: string;
  stateTenantId?: string | null;
  ulbTenantId?: string | null;
  eventCategories: string[];
  dateFrom: string;
  dateTo: string;
  includeHashInfo: boolean;
  maskSensitiveInfo: boolean;
  exportReason: string;
  approvalReference?: string | null;
}

