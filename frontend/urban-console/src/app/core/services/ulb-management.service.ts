import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Observable, map } from 'rxjs';
import { KeycloakAuthService } from './keycloak.service';
import { environment } from '../../../environments/environment';
import {
  UlbTenant,
  UlbTenantCreatePayload,
  UlbTenantUpdatePayload,
  Zone,
  ZoneCreatePayload,
  Ward,
  WardCreatePayload,
} from '../models/ulb-tenant.model';

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

@Injectable({
  providedIn: 'root',
})
export class UlbManagementService {
  private http = inject(HttpClient);
  private authService = inject(KeycloakAuthService);
  private baseUrl = `${environment.apiUrl}/ulbs`;

  private getHeaders(): HttpHeaders {
    const token = this.authService.getToken();
    const tenantId = this.authService.getTenantId();
    return new HttpHeaders({
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      'X-Tenant-ID': tenantId,
    });
  }

  getUlbs(filters?: {
    search?: string;
    stateCode?: string;
    ulbType?: string;
    status?: string;
  }): Observable<UlbTenant[]> {
    let params = new HttpParams();
    if (filters?.search) {
      params = params.set('search', filters.search);
    }
    if (filters?.stateCode) {
      params = params.set('state_code', filters.stateCode);
    }
    if (filters?.ulbType) {
      params = params.set('ulb_type', filters.ulbType);
    }
    if (filters?.status) {
      params = params.set('status', filters.status);
    }

    return this.http
      .get<ApiResponse<UlbTenant[]> | UlbTenant[]>(this.baseUrl, {
        headers: this.getHeaders(),
        params,
      })
      .pipe(map(unwrapResponse));
  }

  getUlb(tenantId: string): Observable<UlbTenant> {
    return this.http
      .get<ApiResponse<UlbTenant> | UlbTenant>(`${this.baseUrl}/${tenantId}`, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  createUlb(payload: UlbTenantCreatePayload): Observable<UlbTenant> {
    return this.http
      .post<ApiResponse<UlbTenant> | UlbTenant>(this.baseUrl, payload, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  updateUlb(tenantId: string, payload: UlbTenantUpdatePayload): Observable<UlbTenant> {
    return this.http
      .put<ApiResponse<UlbTenant> | UlbTenant>(`${this.baseUrl}/${tenantId}`, payload, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  activateUlb(tenantId: string): Observable<UlbTenant> {
    return this.http
      .post<ApiResponse<UlbTenant> | UlbTenant>(
        `${this.baseUrl}/${tenantId}/activate`,
        {},
        { headers: this.getHeaders() }
      )
      .pipe(map(unwrapResponse));
  }

  suspendUlb(tenantId: string): Observable<UlbTenant> {
    return this.http
      .post<ApiResponse<UlbTenant> | UlbTenant>(
        `${this.baseUrl}/${tenantId}/suspend`,
        {},
        { headers: this.getHeaders() }
      )
      .pipe(map(unwrapResponse));
  }

  deleteUlb(tenantId: string): Observable<{ deleted: boolean; tenantId: string }> {
    return this.http
      .delete<ApiResponse<{ deleted: boolean; tenantId: string }> | { deleted: boolean; tenantId: string }>(
        `${this.baseUrl}/${tenantId}`,
        { headers: this.getHeaders() }
      )
      .pipe(map(unwrapResponse));
  }

  // Zones
  getZones(tenantId: string): Observable<Zone[]> {
    return this.http
      .get<ApiResponse<Zone[]> | Zone[]>(`${this.baseUrl}/${tenantId}/zones`, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  createZone(tenantId: string, payload: ZoneCreatePayload): Observable<Zone> {
    return this.http
      .post<ApiResponse<Zone> | Zone>(`${this.baseUrl}/${tenantId}/zones`, payload, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  deleteZone(tenantId: string, zoneId: string): Observable<{ deleted: boolean; zoneId: string }> {
    return this.http
      .delete<ApiResponse<{ deleted: boolean; zoneId: string }> | { deleted: boolean; zoneId: string }>(
        `${this.baseUrl}/${tenantId}/zones/${zoneId}`,
        { headers: this.getHeaders() }
      )
      .pipe(map(unwrapResponse));
  }

  // Wards
  getWards(tenantId: string): Observable<Ward[]> {
    return this.http
      .get<ApiResponse<Ward[]> | Ward[]>(`${this.baseUrl}/${tenantId}/wards`, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  createWard(tenantId: string, payload: WardCreatePayload): Observable<Ward> {
    return this.http
      .post<ApiResponse<Ward> | Ward>(`${this.baseUrl}/${tenantId}/wards`, payload, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  deleteWard(tenantId: string, wardId: string): Observable<{ deleted: boolean; wardId: string }> {
    return this.http
      .delete<ApiResponse<{ deleted: boolean; wardId: string }> | { deleted: boolean; wardId: string }>(
        `${this.baseUrl}/${tenantId}/wards/${wardId}`,
        { headers: this.getHeaders() }
      )
      .pipe(map(unwrapResponse));
  }
}
