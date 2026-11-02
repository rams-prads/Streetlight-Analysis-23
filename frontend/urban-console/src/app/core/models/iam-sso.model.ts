export interface ApiResponse<T = any> {
  success: boolean;
  code?: number;
  message?: string;
  data: T;
}

export interface SSOConfiguration {
  id: string;
  providerName: string;
  providerType: string;
  keycloakBaseUrl: string;
  keycloakRealm: string;
  clientId: string;
  clientSecretMasked: string;
  redirectUri: string;
  postLogoutRedirectUri?: string;
  oidcScopes: string[];
  discoveryUrl?: string;
  connectionStatus: 'Connected' | 'Degraded' | 'Offline' | string;
  lastConnectionTest?: string;

  // SSO & Auth Policies
  enableSso: boolean;
  loginMethods: string[];
  mfaRequired: boolean;
  mfaPolicy: 'Optional' | 'Admins Only' | 'Mandatory All' | string;
  allowedIdentityProviders?: string[];
  sessionIdleTimeoutMins: number;
  maxSessionLifetimeMins: number;
  rememberMe: boolean;
  bruteForceProtection: boolean;
  maxFailedAttempts: number;
  passwordMinLength: number;
  passwordRequireUppercase: boolean;
  passwordRequireLowercase: boolean;
  passwordRequireDigits: boolean;
  passwordRequireSpecial: boolean;
  passwordExpiryDays: number;
  allowedEmailDomains: string[];
  requireVerifiedEmail: boolean;
  createdAt?: string;
  updatedAt?: string;
}

export interface SSOConnectionPayload {
  providerName: string;
  providerType: string;
  keycloakBaseUrl: string;
  keycloakRealm: string;
  clientId: string;
  clientSecret?: string;
  redirectUri: string;
  postLogoutRedirectUri?: string;
  oidcScopes: string[];
}

export interface SSOPolicyPayload {
  enableSso: boolean;
  loginMethods: string[];
  mfaRequired: boolean;
  mfaPolicy: string;
  allowedIdentityProviders?: string[];
  sessionIdleTimeoutMins: number;
  maxSessionLifetimeMins: number;
  rememberMe: boolean;
  bruteForceProtection: boolean;
  maxFailedAttempts: number;
  passwordMinLength: number;
  passwordRequireUppercase: boolean;
  passwordRequireLowercase: boolean;
  passwordRequireDigits: boolean;
  passwordRequireSpecial: boolean;
  passwordExpiryDays: number;
  allowedEmailDomains: string[];
  requireVerifiedEmail: boolean;
}

export interface IdentityProvider {
  id: string;
  name: string;
  protocol: 'OIDC' | 'SAML' | string;
  issuerUrl: string;
  clientId?: string;
  clientSecretMasked: string;
  metadataUrl?: string;
  claimMapping: Record<string, string>;
  userLinkingPolicy: 'Auto-link by Email' | 'Require Manual Verification' | 'Disabled' | string;
  isActive: boolean;
  createdAt?: string;
  updatedAt?: string;
}

export interface IdentityProviderPayload {
  name: string;
  protocol: string;
  issuerUrl: string;
  clientId?: string;
  clientSecret?: string;
  metadataUrl?: string;
  claimMapping?: Record<string, string>;
  userLinkingPolicy: string;
  isActive: boolean;
}

export interface AuthenticationAuditLog {
  id: string;
  eventType: string;
  username: string;
  ipAddress?: string;
  userAgent?: string;
  idpUsed?: string;
  details?: string;
  status: 'SUCCESS' | 'FAILED' | 'BLOCKED' | string;
  timestamp: string;
}

export interface ConnectionTestResult {
  success: boolean;
  status: string;
  message: string;
  testedAt: string;
  details?: Record<string, any>;
}
