import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Observable, map } from 'rxjs';
import { KeycloakAuthService } from './keycloak.service';
import { environment } from '../../../environments/environment';
import {
  BackupDrOverviewStats,
  BackupPolicyItem,
  BackupPolicyPayload,
  BackupJobItem,
  RestoreJobItem,
  RestoreJobPayload,
  PitrWindowStatus,
  DrillExecutionItem,
  DrillExecutionPayload,
} from '../models/backup-dr.model';

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
export class BackupDrService {
  private http = inject(HttpClient);
  private authService = inject(KeycloakAuthService);
  private baseUrl = `${environment.apiUrl}/fleet/backup-dr`;

  private getHeaders(): HttpHeaders {
    const token = this.authService.getToken();
    const tenantId = this.authService.getTenantId();
    return new HttpHeaders({
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      'X-Tenant-ID': tenantId,
    });
  }

  getStats(): Observable<BackupDrOverviewStats> {
    return this.http
      .get<ApiResponse<BackupDrOverviewStats>>(`${this.baseUrl}/stats`, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  getPolicies(filters?: {
    status?: string;
    environment?: string;
    backupType?: string;
  }): Observable<BackupPolicyItem[]> {
    let params = new HttpParams();
    if (filters) {
      if (filters.status && filters.status !== 'ALL') params = params.set('status', filters.status);
      if (filters.environment && filters.environment !== 'ALL') params = params.set('environment', filters.environment);
      if (filters.backupType && filters.backupType !== 'ALL') params = params.set('backup_type', filters.backupType);
    }

    return this.http
      .get<ApiResponse<BackupPolicyItem[]>>(`${this.baseUrl}/policies`, {
        headers: this.getHeaders(),
        params,
      })
      .pipe(map(unwrapResponse));
  }

  createPolicy(payload: BackupPolicyPayload): Observable<BackupPolicyItem> {
    return this.http
      .post<ApiResponse<BackupPolicyItem>>(`${this.baseUrl}/policies`, payload, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  getJobs(filters?: {
    search?: string;
    policyCode?: string;
    environment?: string;
    database?: string;
    backupType?: string;
    status?: string;
    skip?: number;
    limit?: number;
  }): Observable<BackupJobItem[]> {
    let params = new HttpParams();
    if (filters) {
      if (filters.search) params = params.set('search', filters.search);
      if (filters.policyCode && filters.policyCode !== 'ALL') params = params.set('policy_code', filters.policyCode);
      if (filters.environment && filters.environment !== 'ALL') params = params.set('environment', filters.environment);
      if (filters.database && filters.database !== 'ALL') params = params.set('database', filters.database);
      if (filters.backupType && filters.backupType !== 'ALL') params = params.set('backup_type', filters.backupType);
      if (filters.status && filters.status !== 'ALL') params = params.set('status', filters.status);
      if (filters.skip !== undefined) params = params.set('skip', filters.skip.toString());
      if (filters.limit !== undefined) params = params.set('limit', filters.limit.toString());
    }

    return this.http
      .get<ApiResponse<BackupJobItem[]>>(`${this.baseUrl}/jobs`, {
        headers: this.getHeaders(),
        params,
      })
      .pipe(map(unwrapResponse));
  }

  triggerOnDemandBackup(policyCode: string): Observable<BackupJobItem> {
    const params = new HttpParams().set('policy_code', policyCode);
    return this.http
      .post<ApiResponse<BackupJobItem>>(`${this.baseUrl}/jobs/trigger`, {}, {
        headers: this.getHeaders(),
        params,
      })
      .pipe(map(unwrapResponse));
  }

  getRestores(): Observable<RestoreJobItem[]> {
    return this.http
      .get<ApiResponse<RestoreJobItem[]>>(`${this.baseUrl}/restores`, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  initiateRestore(payload: RestoreJobPayload): Observable<RestoreJobItem> {
    return this.http
      .post<ApiResponse<RestoreJobItem>>(`${this.baseUrl}/restores`, payload, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  getPitrStatus(): Observable<PitrWindowStatus> {
    return this.http
      .get<ApiResponse<PitrWindowStatus>>(`${this.baseUrl}/pitr-status`, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  getDrills(): Observable<DrillExecutionItem[]> {
    return this.http
      .get<ApiResponse<DrillExecutionItem[]>>(`${this.baseUrl}/drills`, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  scheduleDrill(payload: DrillExecutionPayload): Observable<DrillExecutionItem> {
    return this.http
      .post<ApiResponse<DrillExecutionItem>>(`${this.baseUrl}/drills`, payload, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }
}

