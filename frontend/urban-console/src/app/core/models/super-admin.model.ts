export interface SuperAdminMenuItem {
  id: string;
  code: string;
  title: string;
  route: string;
  badge?: string;
  count?: string | number;
  icon?: string;
  description: string;
}

export interface SuperAdminSection {
  id: string;
  title: string;
  code?: string;
  icon: string;
  items: SuperAdminMenuItem[];
}

export const SUPER_ADMIN_SECTIONS: SuperAdminSection[] = [
  {
    id: 'tenancy',
    title: 'TENANCY & HIERARCHY',
    icon: 'ri-government-line',
    items: [
      {
        id: 'TH-01',
        code: 'ADM-T01',
        title: 'Tenant Management',
        route: '/admin/tenancy/tenants',
        badge: 'Level 1',
        count: 28,
        icon: 'ri-government-line',
        description: 'State onboarding, regional jurisdictions & Level 1 tenant hierarchy',
      },
      {
        id: 'TH-02',
        code: 'ADM-T02',
        title: 'ULB / City Management',
        route: '/admin/tenancy/cities',
        badge: 'Level 2',
        count: '4.8k',
        icon: 'ri-building-line',
        description: 'Municipal corporations, municipalities, ward zoning & boundaries',
      },
      {
        id: 'TH-03',
        code: 'ADM-T03',
        title: 'Tenant Lifecycle Management',
        route: '/admin/tenancy/lifecycle',
        badge: 'Lifecycle',
        count: 5,
        icon: 'ri-loop-right-line',
        description: 'Manage lifecycle of State & ULB tenants: activation, suspension, locking, maintenance & archival',
      },
    ],
  },
  {
    id: 'modules',
    title: 'MODULE & SUBSCRIPTION',
    icon: 'ri-apps-2-line',
    items: [
      {
        id: 'MS-01',
        code: 'MS-01',
        title: 'Module Catalogue',
        route: '/admin/modules/catalogue',
        badge: '19 Modules',
        count: 19,
        icon: 'ri-apps-2-line',
        description: 'Master 19 municipal service domains and suite subscriptions',
      },
      {
        id: 'MS-02',
        code: 'MS-02',
        title: 'Component Registry',
        route: '/admin/modules/components',
        badge: '405 Comps',
        count: 405,
        icon: 'ri-puzzle-line',
        description: 'Process component decomposition and granular feature registry',
      },
      {
        id: 'MS-03',
        code: 'MS-03',
        title: 'Action & Dependency Registry',
        route: '/admin/modules/dependencies',
        count: 14,
        icon: 'ri-git-branch-line',
        description: 'Component action dependencies, prerequisite chains & triggers',
      },
      {
        id: 'MS-04',
        code: 'ADM-M04',
        title: 'Module Subscription Allocator',
        route: '/admin/modules/subscriptions',
        badge: 'Level 1',
        count: '19 Modules',
        icon: 'ri-checkbox-multiple-line',
        description: 'Allocate, activate, renew, and revoke the 19 standard ERP modules for state tenants',
      },
      {
        id: 'MS-05',
        code: 'ADM-M05',
        title: 'Sub-Tenant Cascade Delegation Guard',
        route: '/admin/modules/delegation',
        badge: 'Level 1→2',
        count: 'Guard',
        icon: 'ri-shield-keyhole-line',
        description: 'Control how a state tenant delegates subscribed modules and component permissions to child ULBs',
      },
    ],
  },
  {
    id: 'iam-sso',
    title: 'SSO & IDENTITY PROVIDERS',
    code: 'ADM-R05',
    icon: 'ri-key-2-line',
    items: [
      {
        id: 'IAM-01',
        code: 'IAM-01',
        title: 'SSO & Identity Provider Configuration',
        route: '/admin/iam/idp-sso',
        count: 2,
        icon: 'ri-fingerprint-line',
        description: 'Keycloak OIDC realm integration & centralized auth server',
      },
      {
        id: 'IAM-02',
        code: 'IAM-02',
        title: 'Identity Federation',
        route: '/admin/iam/federation',
        count: 4,
        icon: 'ri-shield-keyhole-line',
        description: 'MeriPehchan, Aadhaar e-Pramaan, Jan Parichay & SAML brokers',
      },
      {
        id: 'IAM-03',
        code: 'IAM-03',
        title: 'MFA & Session Policy',
        route: '/admin/iam/mfa-policy',
        count: 5,
        icon: 'ri-lock-password-line',
        description: 'Adaptive MFA, session timeouts, brute-force lockout & password policies',
      },
    ],
  },
  {
    id: 'iam-rbac',
    title: 'ROLES & PERMISSION MATRIX',
    code: 'ADM-R03',
    icon: 'ri-shield-check-line',
    items: [
      {
        id: 'IAM-04',
        code: 'IAM-04',
        title: 'Roles & Permission Matrix',
        route: '/admin/iam/roles-matrix',
        count: 7,
        icon: 'ri-shield-user-line',
        description: 'Granular component action permissions across 19 modules and 405 components',
      },
      {
        id: 'IAM-05',
        code: 'IAM-05',
        title: 'Role Templates',
        route: '/admin/iam/role-templates',
        count: 7,
        icon: 'ri-file-copy-2-line',
        description: 'Pre-configured standard municipal roles and delegation baselines',
      },
      {
        id: 'IAM-06',
        code: 'IAM-06',
        title: 'Effective Permissions',
        route: '/admin/iam/effective-permissions',
        count: 'Diff',
        icon: 'ri-scales-3-line',
        description: 'Role comparison, differential audit & excessive privilege detection',
      },
    ],
  },
  {
    id: 'iam-users',
    title: 'GLOBAL USER DIRECTORY',
    code: 'ADM-R01',
    icon: 'ri-team-line',
    items: [
      {
        id: 'IAM-07',
        code: 'IAM-07',
        title: 'Global User Management',
        route: '/admin/iam/users',
        count: '1.4k',
        icon: 'ri-team-line',
        description: 'Pan-state directory of state officers, municipal staff & admins',
      },
      {
        id: 'IAM-08',
        code: 'IAM-08',
        title: 'User Invitations',
        route: '/admin/iam/invitations',
        badge: 'Pending',
        count: 2,
        icon: 'ri-mail-send-line',
        description: 'Expiring onboarding tokens & self-service credential initialization',
      },
      {
        id: 'IAM-09',
        code: 'IAM-09',
        title: 'Access & Scope',
        route: '/admin/iam/access-scope',
        count: 'Multi-tier',
        icon: 'ri-node-tree',
        description: 'Hierarchical Level 0/1/2 tenancy and organizational scope assignments',
      },
    ],
  },
  {
    id: 'security',
    title: 'DATA SECURITY & TENANT ISOLATION',
    code: 'ADM-C05',
    icon: 'ri-shield-keyhole-line',
    items: [
      {
        id: 'SEC-01',
        code: 'SEC-01',
        title: 'RLS Policy Registry',
        route: '/admin/security/rls-policies',
        badge: 'RLS',
        count: 5,
        icon: 'ri-database-2-line',
        description: 'Postgres row-level security policies enforcing tenant_id scoping',
      },
      {
        id: 'SEC-02',
        code: 'SEC-02',
        title: 'Tenant Isolation Test Runs',
        route: '/admin/security/isolation-tests',
        badge: 'Automated',
        count: 100,
        icon: 'ri-test-tube-line',
        description: 'Cross-tenant boundary penetration tests and synthetic injection runs',
      },
      {
        id: 'SEC-03',
        code: 'SEC-03',
        title: 'Isolation Findings & Reports',
        route: '/admin/security/reports',
        badge: 'Audit',
        count: 3,
        icon: 'ri-file-shield-line',
        description: 'Immutable compliance audit findings, leak checks & CERT-In logs',
      },
    ],
  },
  {
    id: 'compliance',
    title: 'INTEGRATIONS & COMPLIANCE',
    code: 'ADM-C06',
    icon: 'ri-shield-check-line',
    items: [
      {
        id: 'COMP-01',
        code: 'ADM-C06',
        title: 'Immutable Audit Vault',
        route: '/admin/compliance/audit-vault',
        badge: 'Tamper-Evident',
        count: 'WORM',
        icon: 'ri-file-shield-line',
        description: 'Central tamper-evident repository: cryptographic hash chaining, retention, and verification',
      },
    ],
  },
  {
    id: 'fleet',
    title: 'PLATFORM FLEET & OPERATIONS',
    code: 'ADM-O01',
    icon: 'ri-server-line',
    items: [
      {
        id: 'FLEET-01',
        code: 'ADM-O01',
        title: 'Microservice Cluster Health',
        route: '/admin/fleet/microservices',
        badge: 'Live K8s',
        count: '8 Svcs',
        icon: 'ri-pulse-line',
        description: 'Monitor health, availability, performance, and resource consumption of all SUVIDHA microservices',
      },
      {
        id: 'FLEET-02',
        code: 'ADM-O02',
        title: 'Backup & Disaster Recovery',
        route: '/admin/fleet/backup-dr',
        badge: 'WORM Vault',
        count: 'PITR',
        icon: 'ri-shield-check-line',
        description: 'Automated backups, PITR recovery replay, and regional disaster recovery drills',
      },
    ],
  },
];
