import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { ApiResponse } from '../models/iam-sso.model';
import {
  RLSPolicy,
  RLSPolicyCreatePayload,
  RLSPolicyUpdatePayload,
  RLSPolicyValidationResult,
  TenantIsolationTestRun,
  TenantIsolationTestCreatePayload,
  TenantIsolationTestRunResult,
  IsolationFinding,
  IsolationFindingCreatePayload,
  IsolationFindingUpdatePayload,
  IsolationFindingRetestResult,
  SecuritySummaryStats,
} from '../models/tenant-security.model';

@Injectable({
  providedIn: 'root'
})
export class TenantSecurityService {
  private http = inject(HttpClient);
  private baseUrl = `${environment.apiUrl}/security`;

  // Stats
  getStats(): Observable<ApiResponse<SecuritySummaryStats>> {
    return this.http.get<ApiResponse<SecuritySummaryStats>>(`${this.baseUrl}/stats`);
  }

  // 1. RLS Policies
  getRlsPolicies(filters?: { search?: string; status?: string; table?: string }): Observable<ApiResponse<RLSPolicy[]>> {
    let params = new HttpParams();
    if (filters?.search?.trim()) params = params.set('search', filters.search.trim());
    if (filters?.status && filters.status !== 'ALL') params = params.set('status', filters.status);
    if (filters?.table && filters.table !== 'ALL') params = params.set('table', filters.table);

    return this.http.get<ApiResponse<RLSPolicy[]>>(`${this.baseUrl}/rls-policies`, { params });
  }

  createRlsPolicy(payload: RLSPolicyCreatePayload): Observable<ApiResponse<RLSPolicy>> {
    return this.http.post<ApiResponse<RLSPolicy>>(`${this.baseUrl}/rls-policies`, payload);
  }

  updateRlsPolicy(policyId: string, payload: RLSPolicyUpdatePayload): Observable<ApiResponse<RLSPolicy>> {
    return this.http.put<ApiResponse<RLSPolicy>>(`${this.baseUrl}/rls-policies/${policyId}`, payload);
  }

  deleteRlsPolicy(policyId: string): Observable<ApiResponse<{ id: string; code: string }>> {
    return this.http.delete<ApiResponse<{ id: string; code: string }>>(`${this.baseUrl}/rls-policies/${policyId}`);
  }

  validateRlsPolicy(policyId: string): Observable<ApiResponse<RLSPolicyValidationResult>> {
    return this.http.post<ApiResponse<RLSPolicyValidationResult>>(`${this.baseUrl}/rls-policies/${policyId}/validate`, {});
  }

  // 2. Isolation Test Runs
  getIsolationTests(filters?: { status?: string; environment?: string; search?: string }): Observable<ApiResponse<TenantIsolationTestRun[]>> {
    let params = new HttpParams();
    if (filters?.status && filters.status !== 'ALL') params = params.set('status', filters.status);
    if (filters?.environment && filters.environment !== 'ALL') params = params.set('environment', filters.environment);
    if (filters?.search && filters.search.trim()) params = params.set('search', filters.search.trim());

    return this.http.get<ApiResponse<TenantIsolationTestRun[]>>(`${this.baseUrl}/isolation-tests`, { params });
  }

  createIsolationTest(payload: TenantIsolationTestCreatePayload): Observable<ApiResponse<TenantIsolationTestRun>> {
    return this.http.post<ApiResponse<TenantIsolationTestRun>>(`${this.baseUrl}/isolation-tests`, payload);
  }

  runIsolationTest(testRunId: string): Observable<ApiResponse<TenantIsolationTestRunResult>> {
    return this.http.post<ApiResponse<TenantIsolationTestRunResult>>(`${this.baseUrl}/isolation-tests/${testRunId}/run`, {});
  }

  // 3. Isolation Findings & Reports
  getFindings(filters?: { severity?: string; status?: string; tenant?: string; search?: string }): Observable<ApiResponse<IsolationFinding[]>> {
    let params = new HttpParams();
    if (filters?.severity && filters.severity !== 'ALL') params = params.set('severity', filters.severity);
    if (filters?.status && filters.status !== 'ALL') params = params.set('status', filters.status);
    if (filters?.tenant && filters.tenant !== 'ALL') params = params.set('tenant', filters.tenant);
    if (filters?.search && filters.search.trim()) params = params.set('search', filters.search.trim());

    return this.http.get<ApiResponse<IsolationFinding[]>>(`${this.baseUrl}/findings`, { params });
  }

  createFinding(payload: IsolationFindingCreatePayload): Observable<ApiResponse<IsolationFinding>> {
    return this.http.post<ApiResponse<IsolationFinding>>(`${this.baseUrl}/findings`, payload);
  }

  updateFinding(findingId: string, payload: IsolationFindingUpdatePayload): Observable<ApiResponse<IsolationFinding>> {
    return this.http.put<ApiResponse<IsolationFinding>>(`${this.baseUrl}/findings/${findingId}`, payload);
  }

  retestFinding(findingId: string): Observable<ApiResponse<IsolationFindingRetestResult>> {
    return this.http.post<ApiResponse<IsolationFindingRetestResult>>(`${this.baseUrl}/findings/${findingId}/retest`, {});
  }
}
