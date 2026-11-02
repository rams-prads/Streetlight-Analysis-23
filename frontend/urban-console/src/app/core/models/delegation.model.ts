export interface DelegationRule {
  id: string;
  ruleCode: string;
  ruleName: string;
  stateTenantId: string;
  stateName?: string;
  stateCode?: string;
  applicableUlbTypes: string[];
  delegationMode: 'Full Delegation' | 'Selective Delegation' | 'Restricted Delegation' | 'No Delegation';
  allowModuleDelegation: boolean;
  allowComponentDelegation: boolean;
  allowRoleDelegation: boolean;
  requireStateApproval: boolean;
  effectiveFrom: string;
  effectiveUntil?: string | null;
  description: string;
  ruleStatus: 'Active' | 'Draft' | 'Deprecated';
  createdAt: string;
  updatedAt?: string | null;
}

export interface DelegationRuleCreatePayload {
  ruleCode: string;
  ruleName: string;
  stateTenantId: string;
  applicableUlbTypes: string[];
  delegationMode: string;
  allowModuleDelegation: boolean;
  allowComponentDelegation: boolean;
  allowRoleDelegation: boolean;
  requireStateApproval: boolean;
  effectiveFrom: string;
  effectiveUntil?: string | null;
  description: string;
  ruleStatus: string;
}

export interface UlbAllocation {
  id: string;
  allocationId: string;
  stateTenantId: string;
  stateName?: string;
  ulbTenantId: string;
  ulbName?: string;
  ulbCode?: string;
  ulbType?: string;
  moduleCode: string;
  moduleName: string;
  allocatedComponents: string[];
  allowedActions: string[];
  startDate: string;
  endDate?: string | null;
  status: 'Active' | 'Suspended' | 'Revoked' | 'Draft';
  approvalReference?: string | null;
  remarks?: string | null;
  createdAt: string;
  updatedAt?: string | null;
}

export interface UlbAllocationCreatePayload {
  stateTenantId: string;
  ulbTenantIds: string[];
  moduleCodes: string[];
  allocatedComponents: string[];
  allowedActions: string[];
  startDate: string;
  endDate?: string | null;
  status: string;
  approvalReference?: string | null;
  remarks?: string | null;
}

export interface ComponentRestriction {
  id: string;
  restrictionId: string;
  stateTenantId: string;
  stateName?: string;
  ulbTenantId: string;
  ulbName?: string;
  moduleCode: string;
  componentCode: string;
  componentName?: string;
  restrictionType: 'Block Entire Component' | 'Block Selected Actions' | 'Read Only' | 'Restrict Data Scope';
  restrictedActions: string[];
  reason: string;
  effectiveFrom: string;
  effectiveUntil?: string | null;
  isActive: boolean;
  createdAt: string;
  updatedAt?: string | null;
}

export interface ComponentRestrictionCreatePayload {
  stateTenantId: string;
  ulbTenantId: string;
  moduleCode: string;
  componentCode: string;
  componentName?: string;
  restrictionType: string;
  restrictedActions: string[];
  reason: string;
  effectiveFrom: string;
  effectiveUntil?: string | null;
  isActive: boolean;
}

export interface DelegationHistoryItem {
  id: string;
  stateTenantId: string;
  stateName?: string;
  ulbTenantId?: string | null;
  ulbName?: string | null;
  moduleCode?: string | null;
  actionType: string;
  details?: Record<string, any> | null;
  changedBy: string;
  changeReason?: string | null;
  createdAt: string;
}

export interface HierarchyVerificationTrace {
  step: string;
  status: 'PASS' | 'FAIL' | 'WARN';
  message: string;
}

export interface EffectivePermissionCheckResult {
  allowed: boolean;
  ulbTenantId: string;
  moduleCode: string;
  componentCode: string;
  action: string;
  reason: string;
  traces: HierarchyVerificationTrace[];
}

export interface DelegationOverviewStats {
  totalRules: number;
  activeRules: number;
  totalAllocations: number;
  activeAllocations: number;
  totalRestrictions: number;
  activeRestrictions: number;
  delegatedUlbsCount: number;
}

export interface StateDelegationScope {
  stateTenantId: string;
  stateName: string;
  stateCode: string;
  activeSubscribedModules: Array<{
    code: string;
    name: string;
    version?: string;
    category?: string;
  }>;
  childUlbs: Array<{
    tenantId: string;
    name: string;
    ulbCode?: string;
    ulbType?: string;
    status: string;
  }>;
  activeRules: Array<{
    ruleCode: string;
    ruleName: string;
    delegationMode: string;
    allowModuleDelegation: boolean;
    allowComponentDelegation: boolean;
  }>;
}

