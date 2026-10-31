import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  ApiResponse,
  TenantDirectoryItem,
  TenantStatusChangePayload,
  TenantMaintenancePayload,
  TenantMaintenanceConfigItem,
  TenantArchivePayload,
  TenantLifecycleEventItem,
} from '../models/tenant-lifecycle.model';

@Injectable({
  providedIn: 'root',
})
export class TenantLifecycleService {
  private http = inject(HttpClient);
  private baseUrl = `${environment.apiUrl}/tenants/lifecycle`;

  getDirectory(filters?: {
    search?: string;
    tenantLevel?: string;
    parentState?: string;
    tenantType?: string;
    status?: string;
    fromDate?: string;
    toDate?: string;
    skip?: number;
    limit?: number;
  }): Observable<ApiResponse<TenantDirectoryItem[]>> {
    let params = new HttpParams();
    if (filters) {
      if (filters.search) params = params.set('search', filters.search);
      if (filters.tenantLevel && filters.tenantLevel !== 'ALL') params = params.set('tenant_level', filters.tenantLevel);
      if (filters.parentState && filters.parentState !== 'ALL') params = params.set('parent_state', filters.parentState);
      if (filters.tenantType && filters.tenantType !== 'ALL') params = params.set('tenant_type', filters.tenantType);
      if (filters.status && filters.status !== 'ALL') params = params.set('status', filters.status);
      if (filters.fromDate) params = params.set('from_date', filters.fromDate);
      if (filters.toDate) params = params.set('to_date', filters.toDate);
      if (filters.skip !== undefined) params = params.set('skip', filters.skip.toString());
      if (filters.limit !== undefined) params = params.set('limit', filters.limit.toString());
    }
    return this.http.get<ApiResponse<TenantDirectoryItem[]>>(`${this.baseUrl}/directory`, { params });
  }

  updateStatus(payload: TenantStatusChangePayload): Observable<ApiResponse<TenantDirectoryItem>> {
    return this.http.post<ApiResponse<TenantDirectoryItem>>(`${this.baseUrl}/status`, payload);
  }

  getMaintenance(tenantId: string): Observable<ApiResponse<TenantMaintenanceConfigItem>> {
    return this.http.get<ApiResponse<TenantMaintenanceConfigItem>>(`${this.baseUrl}/maintenance/${tenantId}`);
  }

  updateMaintenance(payload: TenantMaintenancePayload): Observable<ApiResponse<TenantMaintenanceConfigItem>> {
    return this.http.post<ApiResponse<TenantMaintenanceConfigItem>>(`${this.baseUrl}/maintenance`, payload);
  }

  getSuspensions(filters?: {
    tenantId?: string;
    suspensionType?: string;
    fromDate?: string;
    toDate?: string;
    skip?: number;
    limit?: number;
  }): Observable<ApiResponse<TenantLifecycleEventItem[]>> {
    let params = new HttpParams();
    if (filters) {
      if (filters.tenantId && filters.tenantId !== 'ALL') params = params.set('tenant_id', filters.tenantId);
      if (filters.suspensionType && filters.suspensionType !== 'ALL') params = params.set('suspension_type', filters.suspensionType);
      if (filters.fromDate) params = params.set('from_date', filters.fromDate);
      if (filters.toDate) params = params.set('to_date', filters.toDate);
      if (filters.skip !== undefined) params = params.set('skip', filters.skip.toString());
      if (filters.limit !== undefined) params = params.set('limit', filters.limit.toString());
    }
    return this.http.get<ApiResponse<TenantLifecycleEventItem[]>>(`${this.baseUrl}/suspensions`, { params });
  }

  archiveTenant(payload: TenantArchivePayload): Observable<ApiResponse<any>> {
    return this.http.post<ApiResponse<any>>(`${this.baseUrl}/archive`, payload);
  }
}
