import { Injectable, inject, signal } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Observable, defer } from 'rxjs';
import { finalize } from 'rxjs/operators';
import { KeycloakAuthService } from './keycloak.service';
import { environment } from '../../../environments/environment';
import { CitizenAccount, Page, Payable, PropertyDetail, PropertySummary, PtxAccess, PtxCase } from '../models/ptx.model';

/**
 * Module 1 (PTX) API client. Every call carries the bearer token, X-Tenant-ID and X-Sub-Tenant-ID. Calls skip the platform's
 * full-screen loader (X-Silent-Request); the Property Tax screens show their own progress instead, from `pending`.
 */
@Injectable({ providedIn: 'root' })
export class PtxService {
  private http = inject(HttpClient);
  private authService = inject(KeycloakAuthService);
  readonly apiRoot = environment.apiUrl.replace(/\/api\/v1\/?$/, '');
  private baseUrl = `${environment.apiUrl}/ptx`;
  /** Requests still running; the shell shows a progress bar and a spinner on the button that started them. */
  readonly pending = signal(0);

  private track<T>(request: Observable<T>): Observable<T> {
    return defer(() => {
      this.pending.update((n) => n + 1);
      return request.pipe(finalize(() => this.pending.update((n) => Math.max(0, n - 1))));
    });
  }

  private headers(json = true): HttpHeaders {
    // The console's tenant is the State (e.g. TG) and its sub-tenant the city (e.g. GWMC). Property tax records belong to
    // the city (ULB), so the city is the data tenant whenever one is chosen.
    const city = this.authService.getSubTenantId() || sessionStorage.getItem('urban_sub_tenant') || '';
    let h = new HttpHeaders({
      Authorization: `Bearer ${this.authService.getToken()}`,
      'X-Tenant-ID': city || this.authService.getTenantId(),
      'X-Sub-Tenant-ID': city,
      'X-Silent-Request': 'true',
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
    return this.track(this.http.get<T>(`${this.baseUrl}${path}`, { headers: this.headers(), params: this.params(query) }));
  }

  post<T = any>(path: string, body: any = {}, query: { [key: string]: any } = {}): Observable<T> {
    return this.track(this.http.post<T>(`${this.baseUrl}${path}`, body, { headers: this.headers(), params: this.params(query) }));
  }

  put<T = any>(path: string, body: any): Observable<T> {
    return this.track(this.http.put<T>(`${this.baseUrl}${path}`, body, { headers: this.headers() }));
  }

  patch<T = any>(path: string, body: any): Observable<T> {
    return this.track(this.http.patch<T>(`${this.baseUrl}${path}`, body, { headers: this.headers() }));
  }

  delete<T = any>(path: string): Observable<T> {
    return this.track(this.http.delete<T>(`${this.baseUrl}${path}`, { headers: this.headers() }));
  }

  getText(path: string, query: { [key: string]: any } = {}): Observable<string> {
    return this.track(this.http.get(`${this.baseUrl}${path}`, { headers: this.headers(), params: this.params(query), responseType: 'text' }));
  }

  getBlob(path: string): Observable<Blob> {
    return this.track(this.http.get(`${this.baseUrl}${path}`, { headers: this.headers(false), responseType: 'blob' }));
  }

  // ---- access and code lists ----
  me(): Observable<PtxAccess> {
    return this.get<PtxAccess>('/me');
  }

  // ---- property register (PT-01..PT-07, PT-IR-01) ----
  properties(query: { [key: string]: any }): Observable<Page<PropertySummary>> {
    return this.get<Page<PropertySummary>>('/properties', query);
  }

  property(upin: string): Observable<PropertyDetail> {
    return this.get<PropertyDetail>(`/properties/${encodeURIComponent(upin)}`);
  }

  payable(upin: string): Observable<Payable> {
    return this.get<Payable>(`/properties/${encodeURIComponent(upin)}/payable`);
  }

  // ---- cases (PT-12..PT-21) ----
  cases(query: { [key: string]: any }): Observable<Page<PtxCase>> {
    return this.get<Page<PtxCase>>('/cases', query);
  }

  caseDetail(applicationNo: string): Observable<PtxCase> {
    return this.get<PtxCase>(`/cases/${encodeURIComponent(applicationNo)}`);
  }

  // ---- citizen portal ----
  citizenAccount(number: string, mobile: string): Observable<CitizenAccount> {
    return this.get<CitizenAccount>('/citizen/account', { number, mobile });
  }

  /** Photo / document upload to separate storage (PT-NF-65). Returns the stored reference. */
  upload(file: Blob, fileName: string): Observable<{ ref: string }> {
    const form = new FormData();
    form.append('file', file, fileName);
    return this.track(this.http.post<{ ref: string }>(`${this.baseUrl}/uploads`, form, { headers: this.headers(false) }));
  }

  /** Full URL anyone can open to check a document is genuine (encoded in its QR code). */
  verifyUrl(verifyPath?: string): string {
    return verifyPath ? `${this.apiRoot}${verifyPath}` : '';
  }
}
