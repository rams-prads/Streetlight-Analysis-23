export interface ApiResponse<T = any> {
  success: boolean;
  message: string;
  data: T;
  timestamp?: string;
  error?: string;
}

export interface TenantDirectoryItem {
  tenantId: string;
  name: string;
  code: string;
  tenantLevel: 'State' | 'ULB';
  parentStateTenantId?: string | null;
  parentStateName?: string;
  tenantType: string;
  currentStatus: 'Draft' | 'Active' | 'Suspended' | 'Locked' | 'Maintenance' | 'Archived' | string;
  createdAt: string;
  updatedAt?: string | null;
  isMaintenanceActive: boolean;
  activeChildUlbsCount?: number;
}

export interface TenantStatusChangePayload {
  tenantId: string;
  tenantLevel: 'State' | 'ULB';
  newStatus: string;
  reason: string;
  effectiveFrom: string;
  effectiveUntil?: string | null;
  supportingDocument?: string | null;
  approvalReference?: string | null;
  confirmation: boolean;
}

export interface TenantMaintenancePayload {
  tenantId: string;
  tenantLevel: 'State' | 'ULB';
  isMaintenanceActive: boolean;
  maintenanceTitle?: string | null;
  maintenanceMessage?: string | null;
  startTime?: string | null;
  endTime?: string | null;
  allowedIps: string[];
  allowAdminAccess: boolean;
  notificationRequired: boolean;
  notificationRecipients: string[];
  reason: string;
}

export interface TenantArchivePayload {
  tenantId: string;
  tenantLevel: 'State' | 'ULB';
  archiveReason: string;
  archiveEffectiveDate: string;
  dataRetentionPolicy: string;
  retentionPeriodYears: number;
  dataExportRequired: boolean;
  exportDestination?: string | null;
  supportingDocument?: string | null;
  approvalAuthority: string;
  finalConfirmation: boolean;
}

export interface TenantLifecycleEventItem {
  id: string;
  tenantId: string;
  tenantName?: string;
  tenantLevel: string;
  previousStatus?: string | null;
  newStatus: string;
  eventType: string;
  reason: string;
  approvalReference?: string | null;
  effectiveFrom?: string | null;
  effectiveUntil?: string | null;
  dataRetentionPolicy?: string | null;
  retentionPeriodYears?: number | null;
  dataExportDestination?: string | null;
  approvalAuthority?: string | null;
  performedBy: string;
  ipAddress?: string | null;
  createdAt: string;
}

export interface TenantMaintenanceConfigItem {
  tenantId: string;
  isActive: boolean;
  title?: string;
  message?: string;
  startTime?: string | null;
  endTime?: string | null;
  allowedIps: string[];
  allowAdminAccess: boolean;
  notificationRequired: boolean;
  notificationRecipients: string[];
  reason?: string;
  updatedBy?: string;
  updatedAt?: string | null;
}
