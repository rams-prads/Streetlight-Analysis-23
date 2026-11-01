export interface ApiResponse<T = any> {
  success: boolean;
  message: string;
  data: T;
  timestamp?: string;
  error?: string;
}

export interface SubscribedModuleItem {
  code: string;
  name: string;
  version: string;
  category?: string;
  status: string;
}

export interface StateSubscription {
  id: string;
  subscriptionId: string;
  stateTenantId: string;
  stateName?: string;
  stateCode?: string;
  subscriptionName: string;
  subscriptionType: 'Standard' | 'Premium' | 'Custom' | 'Government Sponsored' | string;
  subscribedModules: SubscribedModuleItem[];
  totalModules: number;
  activeModulesCount: number;
  startDate: string;
  endDate?: string | null;
  billingCycle: 'Monthly' | 'Quarterly' | 'Half-Yearly' | 'Yearly' | 'Custom' | string;
  status: 'Active' | 'Suspended' | 'Expired' | 'Revoked' | 'Draft' | string;
  autoRenewal: boolean;
  remarks?: string | null;
  approvalReference?: string | null;
  createdAt: string;
  updatedAt?: string | null;
}

export interface StateSubscriptionCreatePayload {
  stateTenantId: string;
  subscriptionName: string;
  subscriptionType: string;
  moduleCodes: string[];
  startDate: string;
  endDate?: string | null;
  billingCycle: string;
  status: string;
  autoRenewal: boolean;
  remarks?: string | null;
  approvalReference?: string | null;
}

export interface StateSubscriptionRenewPayload {
  subscriptionId: string;
  renewalType: string;
  newStartDate: string;
  newEndDate: string;
  additionalModuleCodes: string[];
  renewalRemarks: string;
  approvalReference?: string | null;
  notifyTenant: boolean;
}

export interface StateSubscriptionHistoryItem {
  id: string;
  subscriptionId: string;
  stateTenantId: string;
  stateName?: string;
  moduleCode?: string | null;
  actionType: string;
  previousStatus?: string | null;
  newStatus?: string | null;
  previousExpiryDate?: string | null;
  newExpiryDate?: string | null;
  changedModules: any[];
  changedBy: string;
  changeReason?: string | null;
  approvalReference?: string | null;
  createdAt: string;
}

export interface StateSubscriptionStats {
  totalSubscriptions: number;
  activeSubscriptions: number;
  expiringSoonCount: number;
  expiredOrRevokedCount: number;
  totalAllocatedModules: number;
}

