import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable, map } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  ApiResponse,
  ModuleCatalogueItem,
  ModuleCreatePayload,
  ComponentCatalogueItem,
  ComponentCreatePayload,
  ModuleChangeHistoryItem,
  CatalogueExportData
} from '../models/module-catalogue.model';

@Injectable({
  providedIn: 'root'
})
export class ModuleCatalogueService {
  private http = inject(HttpClient);
  private baseUrl = `${environment.apiUrl}/modules`;

  getModules(category?: string, status?: string, search?: string): Observable<ModuleCatalogueItem[]> {
    let params = new HttpParams();
    if (category && category !== 'ALL') params = params.set('category', category);
    if (status && status !== 'ALL') params = params.set('status', status);
    if (search && search.trim()) params = params.set('search', search.trim());

    return this.http.get<ApiResponse<ModuleCatalogueItem[]>>(this.baseUrl, { params }).pipe(
      map(res => res.data || [])
    );
  }

  getModule(code: string): Observable<ModuleCatalogueItem> {
    return this.http.get<ApiResponse<ModuleCatalogueItem>>(`${this.baseUrl}/${encodeURIComponent(code)}`).pipe(
      map(res => res.data)
    );
  }

  createModule(payload: ModuleCreatePayload): Observable<ModuleCatalogueItem> {
    return this.http.post<ApiResponse<ModuleCatalogueItem>>(this.baseUrl, payload).pipe(
      map(res => res.data)
    );
  }

  updateModule(code: string, payload: Partial<ModuleCreatePayload>): Observable<ModuleCatalogueItem> {
    return this.http.put<ApiResponse<ModuleCatalogueItem>>(`${this.baseUrl}/${encodeURIComponent(code)}`, payload).pipe(
      map(res => res.data)
    );
  }

  publishModule(code: string): Observable<ModuleCatalogueItem> {
    return this.http.post<ApiResponse<ModuleCatalogueItem>>(`${this.baseUrl}/${encodeURIComponent(code)}/publish`, {}).pipe(
      map(res => res.data)
    );
  }

  deprecateModule(code: string): Observable<ModuleCatalogueItem> {
    return this.http.post<ApiResponse<ModuleCatalogueItem>>(`${this.baseUrl}/${encodeURIComponent(code)}/deprecate`, {}).pipe(
      map(res => res.data)
    );
  }

  getAllComponents(parentModule?: string, type?: string, status?: string, search?: string): Observable<ComponentCatalogueItem[]> {
    let params = new HttpParams();
    if (parentModule && parentModule !== 'ALL') params = params.set('parentModule', parentModule);
    if (type && type !== 'ALL') params = params.set('type', type);
    if (status && status !== 'ALL') params = params.set('status', status);
    if (search && search.trim()) params = params.set('search', search.trim());

    return this.http.get<ApiResponse<ComponentCatalogueItem[]>>(`${this.baseUrl}/components/all`, { params }).pipe(
      map(res => res.data || [])
    );
  }

  createComponent(payload: ComponentCreatePayload): Observable<ComponentCatalogueItem> {
    return this.http.post<ApiResponse<ComponentCatalogueItem>>(`${this.baseUrl}/components`, payload).pipe(
      map(res => res.data)
    );
  }

  updateComponent(code: string, payload: Partial<ComponentCreatePayload>): Observable<ComponentCatalogueItem> {
    return this.http.put<ApiResponse<ComponentCatalogueItem>>(`${this.baseUrl}/components/${encodeURIComponent(code)}`, payload).pipe(
      map(res => res.data)
    );
  }

  deprecateComponent(code: string): Observable<ComponentCatalogueItem> {
    return this.http.post<ApiResponse<ComponentCatalogueItem>>(`${this.baseUrl}/components/${encodeURIComponent(code)}/deprecate`, {}).pipe(
      map(res => res.data)
    );
  }

  getAuditHistory(entityCode?: string): Observable<ModuleChangeHistoryItem[]> {
    let params = new HttpParams();
    if (entityCode) params = params.set('entity_code', entityCode);

    return this.http.get<ApiResponse<ModuleChangeHistoryItem[]>>(`${this.baseUrl}/audit/history`, { params }).pipe(
      map(res => res.data || [])
    );
  }

  exportCatalogue(): Observable<CatalogueExportData> {
    return this.http.get<ApiResponse<CatalogueExportData>>(`${this.baseUrl}/export/catalogue`).pipe(
      map(res => res.data)
    );
  }
}
