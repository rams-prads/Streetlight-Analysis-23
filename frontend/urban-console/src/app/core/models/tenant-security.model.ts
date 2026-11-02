// -------------------------------------------------------------
// Data Security & Tenant Isolation (ADM-C05) Models
// -------------------------------------------------------------

export interface RLSPolicy {
  id: string;
  policyName: string;
  policyCode: string;
  databaseService: string;
  schemaName: string;
  tableName: string;
  tenantKeyColumn: string;
  policyType: 'SELECT' | 'INSERT' | 'UPDATE' | 'DELETE' | 'ALL';
  databaseCommands: string[];
  applicableTenantLevels: string[];
  policyDefinition: string;
  policyStatus: 'ACTIVE' | 'DISABLED' | 'PENDING_VERIFICATION';
  lastVerifiedAt?: string;
  lastVerificationResult: 'VERIFIED' | 'FAILED' | 'UNTESTED';
  verificationLatencyMs: number;
  enforcementNotes?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface RLSPolicyCreatePayload {
  policyName: string;
  policyCode: string;
  databaseService: string;
  schemaName: string;
  tableName: string;
  tenantKeyColumn: string;
  policyType: string;
  databaseCommands: string[];
  applicableTenantLevels: string[];
  policyDefinition: string;
  policyStatus: string;
  enforcementNotes?: string;
}

export interface RLSPolicyUpdatePayload {
  policyName?: string;
  databaseService?: string;
  schemaName?: string;
  tableName?: string;
  tenantKeyColumn?: string;
  policyType?: string;
  databaseCommands?: string[];
  applicableTenantLevels?: string[];
  policyDefinition?: string;
  policyStatus?: string;
  enforcementNotes?: string;
}

export interface RLSPolicyValidationResult {
  policyId: string;
  policyCode: string;
  status: 'VERIFIED' | 'FAILED';
  latencyMs: number;
  verifiedAt: string;
  details: string;
  enforcedQuerySample: string;
}

export interface TenantIsolationTestRun {
  id: string;
  testRunName: string;
  environment: 'Staging' | 'Isolated Sandbox' | 'Production-Mirror';
  sourceTenant: string;
  targetTenant: string;
  testScenarios: string[];
  databaseServices: string[];
  tablesInScope: string[];
  testType: string;
  executionMode: string;
  schedule?: string;
  notificationRecipients: string[];
  stopOnCriticalFailure: boolean;
  status: 'PASSED' | 'FAILED' | 'RUNNING' | 'SCHEDULED';
  startTime?: string;
  endTime?: string;
  totalTests: number;
  passedCount: number;
  failedCount: number;
  executionLatencyMs: number;
  createdAt?: string;
}

export interface TenantIsolationTestCreatePayload {
  testRunName: string;
  environment: string;
  sourceTenant: string;
  targetTenant: string;
  testScenarios: string[];
  databaseServices: string[];
  tablesInScope: string[];
  testType: string;
  executionMode: string;
  schedule?: string;
  notificationRecipients?: string[];
  stopOnCriticalFailure: boolean;
}

export interface ScenarioResult {
  scenario: string;
  status: 'PASSED' | 'FAILED';
  assertion: string;
  latencyMs: number;
}

export interface TenantIsolationTestRunResult {
  testRunId: string;
  status: 'PASSED' | 'FAILED';
  totalTests: number;
  passedCount: number;
  failedCount: number;
  latencyMs: number;
  scenarioResults: ScenarioResult[];
}

export interface IsolationFinding {
  id: string;
  testRunId?: string;
  severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  findingTitle: string;
  findingDescription: string;
  affectedTenant: string;
  affectedResource: string;
  remediationOwner: string;
  remediationDueDate: string;
  resolutionNotes?: string;
  retestStatus: 'OPEN' | 'IN_REMEDIATION' | 'RESOLVED' | 'VERIFIED';
  detectedAt?: string;
  resolvedAt?: string;
}

export interface IsolationFindingCreatePayload {
  testRunId?: string;
  severity: string;
  findingTitle: string;
  findingDescription: string;
  affectedTenant: string;
  affectedResource: string;
  remediationOwner: string;
  remediationDueDate: string;
  resolutionNotes?: string;
  retestStatus: string;
}

export interface IsolationFindingUpdatePayload {
  severity?: string;
  findingTitle?: string;
  findingDescription?: string;
  affectedTenant?: string;
  affectedResource?: string;
  remediationOwner?: string;
  remediationDueDate?: string;
  resolutionNotes?: string;
  retestStatus?: string;
}

export interface IsolationFindingRetestResult {
  findingId: string;
  retestStatus: string;
  verificationResult: string;
  testedAt: string;
  details: string;
}

export interface SecuritySummaryStats {
  totalRlsPolicies: number;
  activeRlsPolicies: number;
  policyCoverageRate: number;
  totalTestRuns: number;
  passedTestRuns: number;
  isolationPassRate: number;
  openFindingsCount: number;
  criticalFindingsCount: number;
  remediatedFindingsCount: number;
}
