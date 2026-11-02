from typing import List, Optional, Any, Dict
import datetime
from app.schemas.tenant import CamelModel, ApiResponse

class SSOConnectionUpdate(CamelModel):
    providerName: str
    providerType: str = "Keycloak"
    keycloakBaseUrl: str
    keycloakRealm: str
    clientId: str
    clientSecret: Optional[str] = None
    redirectUri: str
    postLogoutRedirectUri: Optional[str] = None
    oidcScopes: List[str] = ["openid", "profile", "email", "roles"]

class SSOPolicyUpdate(CamelModel):
    enableSso: bool = True
    loginMethods: List[str] = ["Password", "SSO", "OTP"]
    mfaRequired: bool = False
    mfaPolicy: str = "Admins Only"
    allowedIdentityProviders: Optional[List[str]] = []
    sessionIdleTimeoutMins: int = 30
    maxSessionLifetimeMins: int = 480
    rememberMe: bool = True
    bruteForceProtection: bool = True
    maxFailedAttempts: int = 5
    passwordMinLength: int = 8
    passwordRequireUppercase: bool = True
    passwordRequireLowercase: bool = True
    passwordRequireDigits: bool = True
    passwordRequireSpecial: bool = True
    passwordExpiryDays: int = 90
    allowedEmailDomains: List[str] = ["gov.in", "nic.in", "urban.gov.in"]
    requireVerifiedEmail: bool = True

class SSOConfigurationResponse(CamelModel):
    id: str
    providerName: str
    providerType: str
    keycloakBaseUrl: str
    keycloakRealm: str
    clientId: str
    clientSecretMasked: str
    redirectUri: str
    postLogoutRedirectUri: Optional[str] = None
    oidcScopes: List[str]
    discoveryUrl: Optional[str] = None
    connectionStatus: str
    lastConnectionTest: Optional[datetime.datetime] = None

    enableSso: bool
    loginMethods: List[str]
    mfaRequired: bool
    mfaPolicy: str
    allowedIdentityProviders: Optional[List[str]] = []
    sessionIdleTimeoutMins: int
    maxSessionLifetimeMins: int
    rememberMe: bool
    bruteForceProtection: bool
    maxFailedAttempts: int
    passwordMinLength: int
    passwordRequireUppercase: bool
    passwordRequireLowercase: bool
    passwordRequireDigits: bool
    passwordRequireSpecial: bool
    passwordExpiryDays: int
    allowedEmailDomains: List[str]
    requireVerifiedEmail: bool
    createdAt: Optional[datetime.datetime] = None
    updatedAt: Optional[datetime.datetime] = None

class IdentityProviderCreate(CamelModel):
    name: str
    protocol: str = "OIDC"
    issuerUrl: str
    clientId: Optional[str] = None
    clientSecret: Optional[str] = None
    metadataUrl: Optional[str] = None
    claimMapping: Optional[Dict[str, str]] = {"sub": "sub", "email": "email", "name": "name", "roles": "roles"}
    userLinkingPolicy: str = "Auto-link by Email"
    isActive: bool = True

class IdentityProviderUpdate(CamelModel):
    name: Optional[str] = None
    protocol: Optional[str] = None
    issuerUrl: Optional[str] = None
    clientId: Optional[str] = None
    clientSecret: Optional[str] = None
    metadataUrl: Optional[str] = None
    claimMapping: Optional[Dict[str, str]] = None
    userLinkingPolicy: Optional[str] = None
    isActive: Optional[bool] = None

class IdentityProviderResponse(CamelModel):
    id: str
    name: str
    protocol: str
    issuerUrl: str
    clientId: Optional[str] = None
    clientSecretMasked: str = "••••••••"
    metadataUrl: Optional[str] = None
    claimMapping: Dict[str, str]
    userLinkingPolicy: str
    isActive: bool
    createdAt: Optional[datetime.datetime] = None
    updatedAt: Optional[datetime.datetime] = None

class AuthenticationAuditLogResponse(CamelModel):
    id: str
    eventType: str
    username: str
    ipAddress: Optional[str] = None
    userAgent: Optional[str] = None
    idpUsed: Optional[str] = None
    details: Optional[str] = None
    status: str
    timestamp: datetime.datetime

class ConnectionTestResult(CamelModel):
    success: bool
    status: str
    message: str
    testedAt: datetime.datetime
    details: Optional[Dict[str, Any]] = None

# ADM-R03: Roles & Permissions Schemas
class RolePermissionItem(CamelModel):
    id: Optional[str] = None
    roleId: Optional[str] = None
    moduleCode: str
    componentCode: str
    canView: bool = False
    canCreate: bool = False
    canUpdate: bool = False
    canDelete: bool = False
    canApprove: bool = False
    canExport: bool = False
    canManage: bool = False
    dataScope: str = "Own Records"  # Own Records, Assigned Department, Ward, ULB, State, Platform
    conditions: Optional[Dict[str, Any]] = None
    effectiveFrom: Optional[datetime.date] = None
    effectiveUntil: Optional[datetime.date] = None

class RolePermissionsUpdate(CamelModel):
    permissions: List[RolePermissionItem]

class RoleCreate(CamelModel):
    roleName: str
    roleCode: str
    description: str
    roleLevel: str  # Platform Super Admin, State Admin, ULB Admin, Department Admin, Officer, Auditor, Read-only User
    scopeType: str  # Platform, State, ULB, Department, Ward
    parentRoleId: Optional[str] = None
    status: str = "Active"  # Active, Inactive, Deprecated
    effectiveFrom: Optional[datetime.date] = None
    effectiveUntil: Optional[datetime.date] = None
    isTemplate: bool = False

class RoleUpdate(CamelModel):
    roleName: Optional[str] = None
    roleCode: Optional[str] = None
    description: Optional[str] = None
    roleLevel: Optional[str] = None
    scopeType: Optional[str] = None
    parentRoleId: Optional[str] = None
    status: Optional[str] = None
    effectiveFrom: Optional[datetime.date] = None
    effectiveUntil: Optional[datetime.date] = None

class RoleResponse(CamelModel):
    id: str
    roleName: str
    roleCode: str
    description: str
    roleLevel: str
    scopeType: str
    parentRoleId: Optional[str] = None
    status: str
    effectiveFrom: Optional[datetime.date] = None
    effectiveUntil: Optional[datetime.date] = None
    isSystem: bool
    isTemplate: bool
    assignedUsersCount: int = 0
    inheritedPermissionsSummary: Optional[str] = None
    createdAt: Optional[datetime.datetime] = None
    updatedAt: Optional[datetime.datetime] = None

class RoleComparisonDiff(CamelModel):
    moduleCode: str
    componentCode: str
    roleAPermissions: Dict[str, Any]
    roleBPermissions: Dict[str, Any]
    isDifferent: bool
    isConflictOrExcessive: bool

class RoleComparisonResult(CamelModel):
    roleA: RoleResponse
    roleB: RoleResponse
    differences: List[RoleComparisonDiff]
    conflictCount: int

# ADM-R01: Global User Management & Invitations Schemas
class ResetUserPasswordPayload(CamelModel):
    newPassword: str

class GlobalUserCreate(CamelModel):
    firstName: str
    middleName: Optional[str] = None
    lastName: str
    email: str
    password: Optional[str] = "Urban@2026"
    mobileNumber: Optional[str] = None
    idpProvider: str = "Keycloak Suvidha"
    externalIdentityId: Optional[str] = None
    userType: str = "Internal Staff"  # Internal Staff, Government Officer, Support Staff, Auditor, External Partner
    accountStatus: str = "Active"
    preferredLanguage: Optional[str] = "English"
    timeZone: Optional[str] = "Asia/Kolkata"
    employeeId: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    profilePhotoUrl: Optional[str] = None
    accountExpiryDate: Optional[datetime.date] = None
    remarks: Optional[str] = None

class GlobalUserUpdate(CamelModel):
    firstName: Optional[str] = None
    middleName: Optional[str] = None
    lastName: Optional[str] = None
    email: Optional[str] = None
    mobileNumber: Optional[str] = None
    idpProvider: Optional[str] = None
    externalIdentityId: Optional[str] = None
    userType: Optional[str] = None
    accountStatus: Optional[str] = None
    preferredLanguage: Optional[str] = None
    timeZone: Optional[str] = None
    employeeId: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    profilePhotoUrl: Optional[str] = None
    accountExpiryDate: Optional[datetime.date] = None
    remarks: Optional[str] = None

class GlobalUserScopeUpdate(CamelModel):
    platformAccess: bool = False
    stateTenantId: Optional[str] = None
    ulbTenantId: Optional[str] = None
    assignedDepartment: Optional[str] = None
    assignedZone: Optional[str] = None
    assignedWard: Optional[str] = None
    assignedRoles: List[str]
    additionalPermissions: Optional[List[str]] = []
    accessEffectiveFrom: Optional[datetime.date] = None
    accessEffectiveUntil: Optional[datetime.date] = None
    approvalReference: Optional[str] = None

class GlobalUserResponse(CamelModel):
    id: str
    firstName: str
    middleName: Optional[str] = None
    lastName: str
    fullName: str
    email: str
    mobileNumber: Optional[str] = None
    idpProvider: str
    externalIdentityId: Optional[str] = None
    userType: str
    accountStatus: str
    preferredLanguage: str
    timeZone: str
    employeeId: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    profilePhotoUrl: Optional[str] = None
    accountExpiryDate: Optional[datetime.date] = None
    remarks: Optional[str] = None
    platformAccess: bool
    stateTenantId: Optional[str] = None
    ulbTenantId: Optional[str] = None
    assignedDepartment: Optional[str] = None
    assignedZone: Optional[str] = None
    assignedWard: Optional[str] = None
    assignedRoles: List[str]
    additionalPermissions: List[str]
    accessEffectiveFrom: Optional[datetime.date] = None
    accessEffectiveUntil: Optional[datetime.date] = None
    approvalReference: Optional[str] = None
    lastActiveAt: Optional[datetime.datetime] = None
    createdAt: Optional[datetime.datetime] = None
    updatedAt: Optional[datetime.datetime] = None

class UserInvitationCreate(CamelModel):
    email: str
    userType: str = "Internal Staff"
    targetTenantId: str
    targetSubTenantId: Optional[str] = None
    assignedRole: str
    departmentScope: Optional[str] = None
    wardScope: Optional[str] = None
    invitationExpiryDays: int = 7
    requireMfa: bool = True
    invitationMessage: Optional[str] = None

class UserInvitationResponse(CamelModel):
    id: str
    email: str
    userType: str
    targetTenantId: str
    targetSubTenantId: Optional[str] = None
    assignedRole: str
    departmentScope: Optional[str] = None
    wardScope: Optional[str] = None
    invitationTokenMasked: str
    invitationExpiry: datetime.datetime
    isExpired: bool
    requireMfa: bool
    invitationMessage: Optional[str] = None
    status: str
    invitedBy: str
    createdAt: datetime.datetime

