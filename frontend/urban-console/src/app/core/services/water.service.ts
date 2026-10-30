import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { KeycloakAuthService } from './keycloak.service';
import {
  ConnectionDetail,
  ConnectionSummary,
  DuesStatus,
  RouteProgress,
  WaterAccess,
  WaterApplication,
  WaterApproval,
  WaterBill,
  WaterComplaint,
  WaterOrder,
  WaterReading,
  WaterReceipt,
} from '../models/water.model';

/** Module 2 (WTR) API client. Every call carries the bearer token, X-Tenant-ID and X-Sub-Tenant-ID. */
@Injectable({ providedIn: 'root' })
export class WaterService {
  private http = inject(HttpClient);
  private authService = inject(KeycloakAuthService);
  readonly apiRoot = 'http://localhost:8000';
  private baseUrl = `${this.apiRoot}/api/v1/water`;

  private headers(json = true): HttpHeaders {
    let h = new HttpHeaders({
      Authorization: `Bearer ${this.authService.getToken()}`,
      'X-Tenant-ID': this.authService.getTenantId(),
      'X-Sub-Tenant-ID': localStorage.getItem('urban_sub_tenant') || '',
    });
    if (json) h = h.set('Content-Type', 'application/json');
    return h;
  }

  private params(values: { [key: string]: any } = {}): HttpParams {
    let p = new HttpParams();
    Object.keys(values).forEach((k) => {
      const v = values[k];
      if (v !== undefined && v !== null && v !== '') p = p.set(k, String(v));
    });
    return p;
  }

  get<T = any>(path: string, query: { [key: string]: any } = {}): Observable<T> {
    return this.http.get<T>(`${this.baseUrl}${path}`, { headers: this.headers(), params: this.params(query) });
  }

  post<T = any>(path: string, body: any = {}, query: { [key: string]: any } = {}): Observable<T> {
    return this.http.post<T>(`${this.baseUrl}${path}`, body, { headers: this.headers(), params: this.params(query) });
  }

  patch<T = any>(path: string, body: any): Observable<T> {
    return this.http.patch<T>(`${this.baseUrl}${path}`, body, { headers: this.headers() });
  }

  getText(path: string, query: { [key: string]: any } = {}): Observable<string> {
    return this.http.get(`${this.baseUrl}${path}`, { headers: this.headers(), params: this.params(query), responseType: 'text' });
  }

  getBlob(path: string): Observable<Blob> {
    return this.http.get(`${this.baseUrl}${path}`, { headers: this.headers(false), responseType: 'blob' });
  }

  // ---- access and code lists ----
  me(): Observable<WaterAccess> {
    return this.get<WaterAccess>('/me');
  }

  // ---- connections (WB-01..WB-08, WB-IR-01) ----
  searchConnections(query: { [key: string]: any }): Observable<ConnectionSummary[]> {
    return this.get<ConnectionSummary[]>('/connections', query);
  }

  connection(consumerNo: string): Observable<ConnectionDetail> {
    return this.get<ConnectionDetail>(`/connections/${encodeURIComponent(consumerNo)}`);
  }

  dues(consumerNo: string): Observable<DuesStatus> {
    return this.get<DuesStatus>(`/connections/${encodeURIComponent(consumerNo)}/dues`);
  }

  bills(consumerNo: string): Observable<WaterBill[]> {
    return this.get<WaterBill[]>(`/connections/${encodeURIComponent(consumerNo)}/bills`);
  }

  bill(billNo: string): Observable<WaterBill> {
    return this.get<WaterBill>(`/bills/${encodeURIComponent(billNo)}`);
  }

  receipt(receiptNo: string): Observable<WaterReceipt> {
    return this.get<WaterReceipt>(`/receipts/${encodeURIComponent(receiptNo)}`);
  }

  readings(query: { [key: string]: any }): Observable<WaterReading[]> {
    return this.get<WaterReading[]>('/readings', query);
  }

  routes(cycle?: string): Observable<RouteProgress[]> {
    return this.get<RouteProgress[]>('/routes', { cycle });
  }

  applications(query: { [key: string]: any } = {}): Observable<WaterApplication[]> {
    return this.get<WaterApplication[]>('/applications', query);
  }

  approvals(status = 'PENDING'): Observable<WaterApproval[]> {
    return this.get<WaterApproval[]>('/approvals', { status });
  }

  complaints(query: { [key: string]: any } = {}): Observable<WaterComplaint[]> {
    return this.get<WaterComplaint[]>('/complaints', query);
  }

  orders(query: { [key: string]: any } = {}): Observable<WaterOrder[]> {
    return this.get<WaterOrder[]>('/orders', query);
  }

  /** Photo / document upload to separate storage (WB-NF-65). Returns the stored reference. */
  upload(file: Blob, fileName: string): Observable<{ ref: string }> {
    const form = new FormData();
    form.append('file', file, fileName);
    return this.http.post<{ ref: string }>(`${this.baseUrl}/uploads`, form, { headers: this.headers(false) });
  }

  /** Full URL anyone can open to check a bill or receipt is genuine (encoded in its QR code). */
  verifyUrl(verifyPath?: string): string {
    return verifyPath ? `${this.apiRoot}${verifyPath}` : '';
  }
}
