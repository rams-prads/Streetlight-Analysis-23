import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable, map } from 'rxjs';
import { KeycloakAuthService } from './keycloak.service';
import {
  StateTenant,
  StateTenantCreatePayload,
  TenantAuditLog,
  MasterState,
} from '../models/state-tenant.model';

export interface ApiResponse<T> {
  success: boolean;
  code: number;
  data: T;
}

function unwrapResponse<T>(res: ApiResponse<T> | T): T {
  if (res && typeof res === 'object' && 'data' in res && 'success' in res) {
    return (res as ApiResponse<T>).data;
  }
  return res as T;
}

import { environment } from '../../../environments/environment';

@Injectable({
  providedIn: 'root',
})
export class TenantManagementService {
  private http = inject(HttpClient);
  private authService = inject(KeycloakAuthService);
  private baseUrl = `${environment.apiUrl}/tenants/states`;

  private getHeaders(): HttpHeaders {
    const token = this.authService.getToken();
    const tenantId = this.authService.getTenantId();
    return new HttpHeaders({
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      'X-Tenant-ID': tenantId,
    });
  }

  getMasterStates(): Observable<MasterState[]> {
    return this.http
      .get<ApiResponse<MasterState[]> | MasterState[]>(
        `${environment.apiUrl}/tenants/master-states`,
        {
          headers: this.getHeaders(),
        },
      )
      .pipe(map(unwrapResponse));
  }

  getDistricts(stateCode?: string): Observable<import('../models/state-tenant.model').District[]> {
    const url = stateCode
      ? `${environment.apiUrl}/tenants/master-states/${stateCode}/districts`
      : `${environment.apiUrl}/tenants/districts`;
    return this.http
      .get<
        | ApiResponse<import('../models/state-tenant.model').District[]>
        | import('../models/state-tenant.model').District[]
      >(url, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  getCities(
    stateCode?: string,
    districtId?: string,
  ): Observable<import('../models/state-tenant.model').City[]> {
    let url = stateCode
      ? `${environment.apiUrl}/tenants/master-states/${stateCode}/cities`
      : `${environment.apiUrl}/tenants/cities`;
    if (districtId) {
      url += `?districtId=${districtId}`;
    }
    return this.http
      .get<
        | ApiResponse<import('../models/state-tenant.model').City[]>
        | import('../models/state-tenant.model').City[]
      >(url, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  getStateTenants(search?: string): Observable<StateTenant[]> {
    let url = this.baseUrl;
    if (search && search.trim()) {
      url += `?search=${encodeURIComponent(search.trim())}`;
    }
    return this.http
      .get<ApiResponse<StateTenant[]> | StateTenant[]>(url, { headers: this.getHeaders() })
      .pipe(map(unwrapResponse));
  }

  getStateTenant(tenantId: string): Observable<StateTenant> {
    return this.http
      .get<ApiResponse<StateTenant> | StateTenant>(`${this.baseUrl}/${tenantId}`, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  createStateTenant(payload: StateTenantCreatePayload): Observable<StateTenant> {
    return this.http
      .post<ApiResponse<StateTenant> | StateTenant>(this.baseUrl, payload, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  updateStateTenant(
    tenantId: string,
    payload: Partial<StateTenantCreatePayload>,
  ): Observable<StateTenant> {
    return this.http
      .put<ApiResponse<StateTenant> | StateTenant>(`${this.baseUrl}/${tenantId}`, payload, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  activateStateTenant(tenantId: string): Observable<StateTenant> {
    return this.http
      .post<ApiResponse<StateTenant> | StateTenant>(
        `${this.baseUrl}/${tenantId}/activate`,
        {},
        { headers: this.getHeaders() },
      )
      .pipe(map(unwrapResponse));
  }

  suspendStateTenant(tenantId: string): Observable<StateTenant> {
    return this.http
      .post<ApiResponse<StateTenant> | StateTenant>(
        `${this.baseUrl}/${tenantId}/suspend`,
        {},
        { headers: this.getHeaders() },
      )
      .pipe(map(unwrapResponse));
  }

  deleteStateTenant(tenantId: string): Observable<{ message: string; tenantId: string }> {
    return this.http
      .delete<
        ApiResponse<{ message: string; tenantId: string }> | { message: string; tenantId: string }
      >(`${this.baseUrl}/${tenantId}`, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  getAuditLogs(): Observable<TenantAuditLog[]> {
    return this.http
      .get<ApiResponse<TenantAuditLog[]> | TenantAuditLog[]>(`${this.baseUrl}/audit-logs`, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }
}
