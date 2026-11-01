export interface GlobalUserItem {
  id: string;
  firstName: string;
  middleName?: string | null;
  lastName: string;
  fullName: string;
  email: string;
  mobileNumber?: string | null;
  idpProvider: string;
  externalIdentityId?: string | null;
  userType: 'Internal Staff' | 'Government Officer' | 'Support Staff' | 'Auditor' | 'External Partner' | string;
  accountStatus: 'Active' | 'Suspended' | 'Pending Invitation' | 'Deactivated';
  preferredLanguage: string;
  timeZone: string;
  employeeId?: string | null;
  designation?: string | null;
  department?: string | null;
  profilePhotoUrl?: string | null;
  accountExpiryDate?: string | null;
  remarks?: string | null;
  platformAccess: boolean;
  stateTenantId?: string | null;
  ulbTenantId?: string | null;
  assignedDepartment?: string | null;
  assignedZone?: string | null;
  assignedWard?: string | null;
  assignedRoles: string[];
  additionalPermissions: string[];
  accessEffectiveFrom?: string | null;
  accessEffectiveUntil?: string | null;
  approvalReference?: string | null;
  lastActiveAt?: string | null;
  createdAt?: string;
  updatedAt?: string;
}

export interface GlobalUserCreatePayload {
  firstName: string;
  middleName?: string | null;
  lastName: string;
  email: string;
  password?: string;
  mobileNumber?: string | null;
  idpProvider: string;
  externalIdentityId?: string | null;
  userType: string;
  accountStatus: string;
  preferredLanguage?: string;
  timeZone?: string;
  employeeId?: string | null;
  designation?: string | null;
  department?: string | null;
  profilePhotoUrl?: string | null;
  accountExpiryDate?: string | null;
  remarks?: string | null;
}

export interface GlobalUserScopePayload {
  platformAccess: boolean;
  stateTenantId?: string | null;
  ulbTenantId?: string | null;
  assignedDepartment?: string | null;
  assignedZone?: string | null;
  assignedWard?: string | null;
  assignedRoles: string[];
  additionalPermissions?: string[];
  accessEffectiveFrom?: string | null;
  accessEffectiveUntil?: string | null;
  approvalReference?: string | null;
}

export interface UserInvitationItem {
  id: string;
  email: string;
  userType: string;
  targetTenantId: string;
  targetSubTenantId?: string | null;
  assignedRole: string;
  departmentScope?: string | null;
  wardScope?: string | null;
  invitationTokenMasked: string;
  invitationExpiry: string;
  isExpired: boolean;
  requireMfa: boolean;
  invitationMessage?: string | null;
  status: 'Pending' | 'Accepted' | 'Expired' | 'Revoked' | string;
  invitedBy: string;
  createdAt: string;
}

export interface UserInvitationCreatePayload {
  email: string;
  userType: string;
  targetTenantId: string;
  targetSubTenantId?: string | null;
  assignedRole: string;
  departmentScope?: string | null;
  wardScope?: string | null;
  invitationExpiryDays: number;
  requireMfa: boolean;
  invitationMessage?: string | null;
}

