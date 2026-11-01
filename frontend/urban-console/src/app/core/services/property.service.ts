import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';
import { DashboardStats, PropertySummary, PropertyDetail, Ward, TenantInfo } from '../models/property.model';
import { KeycloakAuthService } from './keycloak.service';
import { environment } from '../../../environments/environment';

@Injectable({
  providedIn: 'root'
})
export class PropertyService {
  private http = inject(HttpClient);
  private authService = inject(KeycloakAuthService);
  private baseUrl = environment.apiUrl;

  private getHeaders(): HttpHeaders {
    const token = this.authService.getToken();
    const tenantId = this.authService.getTenantId();
    return new HttpHeaders({
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
      'X-Tenant-ID': tenantId
    });
  }

  getDashboardStats(): Observable<DashboardStats> {
    return this.http.get<DashboardStats>(`${this.baseUrl}/properties/stats/summary`, {
      headers: this.getHeaders()
    });
  }

  getProperties(search?: string, wardId?: string, taxStatus?: string): Observable<PropertySummary[]> {
    let params = new HttpParams();
    if (search) params = params.set('q', search);
    if (wardId) params = params.set('ward_id', wardId);
    if (taxStatus) params = params.set('tax_status', taxStatus);

    return this.http.get<PropertySummary[]>(`${this.baseUrl}/properties`, {
      headers: this.getHeaders(),
      params
    });
  }

  getPropertyByUlpin(ulpin: string): Observable<PropertyDetail> {
    return this.http.get<PropertyDetail>(`${this.baseUrl}/properties/${ulpin}`, {
      headers: this.getHeaders()
    });
  }

  getWards(): Observable<Ward[]> {
    return this.http.get<Ward[]>(`${this.baseUrl}/boundaries/wards`, {
      headers: this.getHeaders()
    });
  }

  createProperty(data: any): Observable<any> {
    return this.http.post<any>(`${this.baseUrl}/properties`, data, {
      headers: this.getHeaders()
    });
  }

  // SaaS Tenant Management APIs
  getTenants(): Observable<TenantInfo[]> {
    return this.http.get<TenantInfo[]>(`${this.baseUrl}/tenants`, {
      headers: this.getHeaders()
    });
  }

  getCurrentTenant(): Observable<TenantInfo> {
    return this.http.get<TenantInfo>(`${this.baseUrl}/tenants/current`, {
      headers: this.getHeaders()
    });
  }

  createTenant(payload: { tenantId: string; name: string; stateCode: string; district: string }): Observable<TenantInfo> {
    return this.http.post<TenantInfo>(`${this.baseUrl}/tenants`, payload, {
      headers: this.getHeaders()
    });
  }
}
