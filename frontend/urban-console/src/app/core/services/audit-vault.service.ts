import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Observable, map } from 'rxjs';
import { KeycloakAuthService } from './keycloak.service';
import { environment } from '../../../environments/environment';
import {
  ImmutableAuditEvent,
  AuditDashboardStats,
  HashVerificationJob,
  HashVerificationCreatePayload,
  RetentionPolicy,
  RetentionPolicyCreatePayload,
  AuditExportJob,
  AuditExportCreatePayload,
} from '../models/audit-vault.model';

export interface ApiResponse<T> {
  success: boolean;
  code?: number;
  message?: string;
  data: T;
}

function unwrapResponse<T>(res: ApiResponse<T> | T): T {
  if (res && typeof res === 'object' && 'data' in res && 'success' in res) {
    return (res as ApiResponse<T>).data;
  }
  return res as T;
}

@Injectable({
  providedIn: 'root',
})
export class AuditVaultService {
  private http = inject(HttpClient);
  private authService = inject(KeycloakAuthService);
  private baseUrl = `${environment.apiUrl}/compliance/audit`;

  private getHeaders(): HttpHeaders {
    const token = this.authService.getToken();
    const tenantId = this.authService.getTenantId();
    return new HttpHeaders({
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      'X-Tenant-ID': tenantId,
    });
  }

  getDashboardStats(): Observable<AuditDashboardStats> {
    return this.http
      .get<ApiResponse<AuditDashboardStats>>(`${this.baseUrl}/stats`, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  getAuditEvents(filters?: {
    search?: string;
    tenantId?: string;
    subTenantId?: string;
    moduleCode?: string;
    componentCode?: string;
    eventCategory?: string;
    action?: string;
    severity?: string;
    result?: string;
    userId?: string;
    ipAddress?: string;
    correlationId?: string;
    dateFrom?: string;
    dateTo?: string;
    skip?: number;
    limit?: number;
  }): Observable<ImmutableAuditEvent[]> {
    let params = new HttpParams();
    if (filters) {
      if (filters.search) params = params.set('search', filters.search);
      if (filters.tenantId && filters.tenantId !== 'ALL') params = params.set('tenant_id', filters.tenantId);
      if (filters.subTenantId && filters.subTenantId !== 'ALL') params = params.set('sub_tenant_id', filters.subTenantId);
      if (filters.moduleCode && filters.moduleCode !== 'ALL') params = params.set('module_code', filters.moduleCode);
      if (filters.componentCode && filters.componentCode !== 'ALL') params = params.set('component_code', filters.componentCode);
      if (filters.eventCategory && filters.eventCategory !== 'ALL') params = params.set('event_category', filters.eventCategory);
      if (filters.action && filters.action !== 'ALL') params = params.set('action', filters.action);
      if (filters.severity && filters.severity !== 'ALL') params = params.set('severity', filters.severity);
      if (filters.result && filters.result !== 'ALL') params = params.set('result', filters.result);
      if (filters.userId) params = params.set('user_id', filters.userId);
      if (filters.ipAddress) params = params.set('ip_address', filters.ipAddress);
      if (filters.correlationId) params = params.set('correlation_id', filters.correlationId);
      if (filters.dateFrom) params = params.set('date_from', filters.dateFrom);
      if (filters.dateTo) params = params.set('date_to', filters.dateTo);
      if (filters.skip !== undefined) params = params.set('skip', filters.skip.toString());
      if (filters.limit !== undefined) params = params.set('limit', filters.limit.toString());
    }

    return this.http
      .get<ApiResponse<ImmutableAuditEvent[]>>(`${this.baseUrl}/events`, {
        headers: this.getHeaders(),
        params,
      })
      .pipe(map(unwrapResponse));
  }

  getEventDetails(eventId: string): Observable<ImmutableAuditEvent> {
    return this.http
      .get<ApiResponse<ImmutableAuditEvent>>(`${this.baseUrl}/events/${eventId}`, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  runHashVerification(payload: HashVerificationCreatePayload): Observable<HashVerificationJob> {
    return this.http
      .post<ApiResponse<HashVerificationJob>>(`${this.baseUrl}/verify`, payload, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  getVerificationJobs(): Observable<HashVerificationJob[]> {
    return this.http
      .get<ApiResponse<HashVerificationJob[]>>(`${this.baseUrl}/verifications`, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  getRetentionPolicies(): Observable<RetentionPolicy[]> {
    return this.http
      .get<ApiResponse<RetentionPolicy[]>>(`${this.baseUrl}/retention-policies`, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  createRetentionPolicy(payload: RetentionPolicyCreatePayload): Observable<RetentionPolicy> {
    return this.http
      .post<ApiResponse<RetentionPolicy>>(`${this.baseUrl}/retention-policies`, payload, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  createAuditExport(payload: AuditExportCreatePayload): Observable<AuditExportJob> {
    return this.http
      .post<ApiResponse<AuditExportJob>>(`${this.baseUrl}/export`, payload, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  getAuditExports(): Observable<AuditExportJob[]> {
    return this.http
      .get<ApiResponse<AuditExportJob[]>>(`${this.baseUrl}/exports`, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }
}

