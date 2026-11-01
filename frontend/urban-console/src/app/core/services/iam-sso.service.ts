import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, map } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  ApiResponse,
  SSOConfiguration,
  SSOConnectionPayload,
  SSOPolicyPayload,
  IdentityProvider,
  IdentityProviderPayload,
  AuthenticationAuditLog,
  ConnectionTestResult
} from '../models/iam-sso.model';

@Injectable({
  providedIn: 'root'
})
export class IamSsoService {
  private http = inject(HttpClient);
  private baseUrl = `${environment.apiUrl}/iam`;

  getSSOConfiguration(): Observable<SSOConfiguration> {
    return this.http.get<ApiResponse<SSOConfiguration>>(`${this.baseUrl}/sso`).pipe(
      map(res => res.data)
    );
  }

  updateConnection(payload: SSOConnectionPayload): Observable<SSOConfiguration> {
    return this.http.put<ApiResponse<SSOConfiguration>>(`${this.baseUrl}/sso/connection`, payload).pipe(
      map(res => res.data)
    );
  }

  updatePolicies(payload: SSOPolicyPayload): Observable<SSOConfiguration> {
    return this.http.put<ApiResponse<SSOConfiguration>>(`${this.baseUrl}/sso/policies`, payload).pipe(
      map(res => res.data)
    );
  }

  testConnection(): Observable<ConnectionTestResult> {
    return this.http.post<ApiResponse<ConnectionTestResult>>(`${this.baseUrl}/sso/test-connection`, {}).pipe(
      map(res => res.data)
    );
  }

  getIdentityProviders(search?: string): Observable<IdentityProvider[]> {
    let params = new HttpParams();
    if (search && search.trim()) params = params.set('search', search.trim());
    return this.http.get<ApiResponse<IdentityProvider[]>>(`${this.baseUrl}/idps`, { params }).pipe(
      map(res => res.data || [])
    );
  }

  createIdentityProvider(payload: IdentityProviderPayload): Observable<IdentityProvider> {
    return this.http.post<ApiResponse<IdentityProvider>>(`${this.baseUrl}/idps`, payload).pipe(
      map(res => res.data)
    );
  }

  updateIdentityProvider(id: string, payload: Partial<IdentityProviderPayload>): Observable<IdentityProvider> {
    return this.http.put<ApiResponse<IdentityProvider>>(`${this.baseUrl}/idps/${id}`, payload).pipe(
      map(res => res.data)
    );
  }

  toggleIdentityProvider(id: string): Observable<IdentityProvider> {
    return this.http.patch<ApiResponse<IdentityProvider>>(`${this.baseUrl}/idps/${id}/toggle`, {}).pipe(
      map(res => res.data)
    );
  }

  deleteIdentityProvider(id: string): Observable<any> {
    return this.http.delete<ApiResponse<any>>(`${this.baseUrl}/idps/${id}`).pipe(
      map(res => res.data)
    );
  }

  getAuditLogs(eventType?: string, status?: string, username?: string): Observable<AuthenticationAuditLog[]> {
    let params = new HttpParams();
    if (eventType && eventType !== 'ALL') params = params.set('event_type', eventType);
    if (status && status !== 'ALL') params = params.set('status', status);
    if (username && username.trim()) params = params.set('username', username.trim());

    return this.http.get<ApiResponse<AuthenticationAuditLog[]>>(`${this.baseUrl}/audit/logs`, { params }).pipe(
      map(res => res.data || [])
    );
  }
}
