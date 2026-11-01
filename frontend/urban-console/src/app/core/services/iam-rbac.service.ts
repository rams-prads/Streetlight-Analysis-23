import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { ApiResponse } from '../models/iam-sso.model';
import {
  RoleItem,
  RoleCreatePayload,
  RolePermissionItem,
  RolePermissionsUpdate,
  RoleComparisonResult
} from '../models/iam-rbac.model';

@Injectable({
  providedIn: 'root'
})
export class IamRbacService {
  private http = inject(HttpClient);
  private baseUrl = `${environment.apiUrl}/iam/roles`;

  getRoles(filters?: { roleLevel?: string; scopeType?: string; status?: string; search?: string }): Observable<ApiResponse<RoleItem[]>> {
    let params = new HttpParams();
    if (filters?.roleLevel && filters.roleLevel !== 'ALL') params = params.set('role_level', filters.roleLevel);
    if (filters?.scopeType && filters.scopeType !== 'ALL') params = params.set('scope_type', filters.scopeType);
    if (filters?.status && filters.status !== 'ALL') params = params.set('status', filters.status);
    if (filters?.search?.trim()) params = params.set('search', filters.search.trim());

    return this.http.get<ApiResponse<RoleItem[]>>(this.baseUrl, { params });
  }

  getRoleTemplates(): Observable<ApiResponse<RoleItem[]>> {
    return this.http.get<ApiResponse<RoleItem[]>>(`${this.baseUrl}/templates`);
  }

  getRoleById(roleId: string): Observable<ApiResponse<RoleItem>> {
    return this.http.get<ApiResponse<RoleItem>>(`${this.baseUrl}/${roleId}`);
  }

  createRole(payload: RoleCreatePayload): Observable<ApiResponse<RoleItem>> {
    return this.http.post<ApiResponse<RoleItem>>(this.baseUrl, payload);
  }

  updateRole(roleId: string, payload: Partial<RoleCreatePayload>): Observable<ApiResponse<RoleItem>> {
    return this.http.put<ApiResponse<RoleItem>>(`${this.baseUrl}/${roleId}`, payload);
  }

  deleteRole(roleId: string): Observable<ApiResponse<{ id: string }>> {
    return this.http.delete<ApiResponse<{ id: string }>>(`${this.baseUrl}/${roleId}`);
  }

  getRolePermissions(roleId: string, moduleCode?: string, search?: string): Observable<ApiResponse<RolePermissionItem[]>> {
    let params = new HttpParams();
    if (moduleCode && moduleCode !== 'ALL') params = params.set('module_code', moduleCode);
    if (search && search.trim()) params = params.set('search', search.trim());
    return this.http.get<ApiResponse<RolePermissionItem[]>>(`${this.baseUrl}/${roleId}/permissions`, { params });
  }

  updateRolePermissions(roleId: string, payload: RolePermissionsUpdate): Observable<ApiResponse<RolePermissionItem[]>> {
    return this.http.put<ApiResponse<RolePermissionItem[]>>(`${this.baseUrl}/${roleId}/permissions`, payload);
  }

  copyPermissions(targetRoleId: string, sourceRoleId: string): Observable<ApiResponse<{ copiedCount: number }>> {
    return this.http.post<ApiResponse<{ copiedCount: number }>>(`${this.baseUrl}/${targetRoleId}/copy-from/${sourceRoleId}`, {});
  }

  compareRoles(roleAId: string, roleBId: string): Observable<ApiResponse<RoleComparisonResult>> {
    const params = new HttpParams().set('role_a_id', roleAId).set('role_b_id', roleBId);
    return this.http.get<ApiResponse<RoleComparisonResult>>(`${this.baseUrl}/compare/diff`, { params });
  }
}
