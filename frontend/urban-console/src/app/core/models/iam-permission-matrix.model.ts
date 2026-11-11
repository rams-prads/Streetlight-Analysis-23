/** The real Roles & Permission Matrix: a module's actual PERMISSIONS dict, not the decorative component list. */

export interface OverrideDetail {
  role: string;
  granted: boolean;
  reason?: string;
  createdBy: string;
  effectiveFrom: string;
}

export interface PermissionRow {
  key: string;
  group: string;
  label?: string;
  /** Roles that hold this permission with no override at all (includes the platform admin bypass). */
  defaultRoles: string[];
  /** Roles that hold it right now, after any saved override. What the checkboxes should reflect. */
  effectiveRoles: string[];
  overrides: OverrideDetail[];
}

export interface PermissionMatrix {
  moduleCode: string;
  roles: string[];
  permissions: PermissionRow[];
}

export interface OverrideChange {
  permissionKey: string;
  role: string;
  /** true = grant, false = revoke, null = revert to the hardcoded default. */
  granted: boolean | null;
  reason?: string;
}

export const LIVE_MATRIX_MODULES = [
  { code: 'PTX', name: 'Property Tax (PTX)' },
  { code: 'WTR', name: 'Water & Utility Billing (WTR)' },
];

/** Every role string either module's PERMISSIONS actually use, with a name worth showing in a column header. */
export const ROLE_LABELS: Record<string, string> = {
  super_admin: 'Platform admin',
  system_admin: 'System admin',
  commissioner: 'Commissioner',
  revenue_officer: 'Revenue officer',
  revenue_inspector: 'Revenue inspector',
  bill_collector: 'Bill collector',
  cashier: 'Cashier',
  csc_operator: 'Meeseva / CSC',
  citizen: 'Citizen',
  water_officer: 'Water officer',
  meter_reader: 'Meter reader',
  water_field_staff: 'Water field staff',
};

export function roleLabel(role: string): string {
  return ROLE_LABELS[role] || role;
}
