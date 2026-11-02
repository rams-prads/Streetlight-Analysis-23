export interface RolePermissionItem {
  id?: string;
  roleId?: string;
  moduleCode: string;
  componentCode: string;
  canView: boolean;
  canCreate: boolean;
  canUpdate: boolean;
  canDelete: boolean;
  canApprove: boolean;
  canExport: boolean;
  canManage: boolean;
  dataScope: 'Own Records' | 'Assigned Department' | 'Ward' | 'ULB' | 'State' | 'Platform';
  conditions?: Record<string, any>;
  effectiveFrom?: string;
  effectiveUntil?: string;
}

export interface RolePermissionsUpdate {
  permissions: RolePermissionItem[];
}

export interface RoleItem {
  id: string;
  roleName: string;
  roleCode: string;
  description: string;
  roleLevel: 'Platform Super Admin' | 'State Admin' | 'ULB Admin' | 'Department Admin' | 'Officer' | 'Auditor' | 'Read-only User' | string;
  scopeType: 'Platform' | 'State' | 'ULB' | 'Department' | 'Ward' | 'Own Records' | string;
  parentRoleId?: string | null;
  status: 'Active' | 'Inactive' | 'Deprecated';
  effectiveFrom?: string | null;
  effectiveUntil?: string | null;
  isSystem: boolean;
  isTemplate: boolean;
  assignedUsersCount: number;
  inheritedPermissionsSummary?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface RoleCreatePayload {
  roleName: string;
  roleCode: string;
  description: string;
  roleLevel: string;
  scopeType: string;
  parentRoleId?: string | null;
  status: string;
  effectiveFrom?: string | null;
  effectiveUntil?: string | null;
  isTemplate?: boolean;
}

export interface RoleComparisonDiff {
  moduleCode: string;
  componentCode: string;
  roleAPermissions: {
    view: boolean;
    create: boolean;
    update: boolean;
    delete: boolean;
    approve: boolean;
    manage: boolean;
    scope: string;
  };
  roleBPermissions: {
    view: boolean;
    create: boolean;
    update: boolean;
    delete: boolean;
    approve: boolean;
    manage: boolean;
    scope: string;
  };
  isDifferent: boolean;
  isConflictOrExcessive: boolean;
}

export interface RoleComparisonResult {
  roleA: RoleItem;
  roleB: RoleItem;
  differences: RoleComparisonDiff[];
  conflictCount: number;
}

