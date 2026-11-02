import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { ApiResponse } from '../models/module-catalogue.model';
import {
  DelegationRule,
  DelegationRuleCreatePayload,
  UlbAllocation,
  UlbAllocationCreatePayload,
  ComponentRestriction,
  ComponentRestrictionCreatePayload,
  DelegationHistoryItem,
  EffectivePermissionCheckResult,
  DelegationOverviewStats,
  StateDelegationScope,
} from '../models/delegation.model';

@Injectable({
  providedIn: 'root',
})
export class DelegationService {
  private http = inject(HttpClient);
  private baseUrl = `${environment.apiUrl}/modules/delegation`;

  getStats(): Observable<ApiResponse<DelegationOverviewStats>> {
    return this.http.get<ApiResponse<DelegationOverviewStats>>(`${this.baseUrl}/stats`);
  }

  getStateScope(stateTenantId: string): Observable<ApiResponse<StateDelegationScope>> {
    return this.http.get<ApiResponse<StateDelegationScope>>(`${this.baseUrl}/state-scope/${stateTenantId}`);
  }

  getRules(filters?: {
    search?: string;
    stateTenantId?: string;
    status?: string;
    skip?: number;
    limit?: number;
  }): Observable<ApiResponse<DelegationRule[]>> {
    let params = new HttpParams();
    if (filters) {
      if (filters.search?.trim()) params = params.set('search', filters.search.trim());
      if (filters.stateTenantId && filters.stateTenantId !== 'ALL') params = params.set('state_tenant_id', filters.stateTenantId);
      if (filters.status && filters.status !== 'ALL') params = params.set('status', filters.status);
      if (filters.skip !== undefined) params = params.set('skip', filters.skip.toString());
      if (filters.limit !== undefined) params = params.set('limit', filters.limit.toString());
    }
    return this.http.get<ApiResponse<DelegationRule[]>>(`${this.baseUrl}/rules`, { params });
  }

  createRule(payload: DelegationRuleCreatePayload): Observable<ApiResponse<DelegationRule>> {
    return this.http.post<ApiResponse<DelegationRule>>(`${this.baseUrl}/rules`, payload);
  }

  getAllocations(filters?: {
    search?: string;
    stateTenantId?: string;
    ulbTenantId?: string;
    status?: string;
    skip?: number;
    limit?: number;
  }): Observable<ApiResponse<UlbAllocation[]>> {
    let params = new HttpParams();
    if (filters) {
      if (filters.search?.trim()) params = params.set('search', filters.search.trim());
      if (filters.stateTenantId && filters.stateTenantId !== 'ALL') params = params.set('state_tenant_id', filters.stateTenantId);
      if (filters.ulbTenantId && filters.ulbTenantId !== 'ALL') params = params.set('ulb_tenant_id', filters.ulbTenantId);
      if (filters.status && filters.status !== 'ALL') params = params.set('status', filters.status);
      if (filters.skip !== undefined) params = params.set('skip', filters.skip.toString());
      if (filters.limit !== undefined) params = params.set('limit', filters.limit.toString());
    }
    return this.http.get<ApiResponse<UlbAllocation[]>>(`${this.baseUrl}/allocations`, { params });
  }

  createAllocations(payload: UlbAllocationCreatePayload): Observable<ApiResponse<UlbAllocation[]>> {
    return this.http.post<ApiResponse<UlbAllocation[]>>(`${this.baseUrl}/allocations`, payload);
  }

  revokeAllocation(allocationId: string, reason: string): Observable<ApiResponse<any>> {
    const params = new HttpParams().set('reason', reason);
    return this.http.post<ApiResponse<any>>(`${this.baseUrl}/allocations/${allocationId}/revoke`, {}, { params });
  }

  getRestrictions(filters?: {
    stateTenantId?: string;
    ulbTenantId?: string;
    skip?: number;
    limit?: number;
  }): Observable<ApiResponse<ComponentRestriction[]>> {
    let params = new HttpParams();
    if (filters) {
      if (filters.stateTenantId && filters.stateTenantId !== 'ALL') params = params.set('state_tenant_id', filters.stateTenantId);
      if (filters.ulbTenantId && filters.ulbTenantId !== 'ALL') params = params.set('ulb_tenant_id', filters.ulbTenantId);
      if (filters.skip !== undefined) params = params.set('skip', filters.skip.toString());
      if (filters.limit !== undefined) params = params.set('limit', filters.limit.toString());
    }
    return this.http.get<ApiResponse<ComponentRestriction[]>>(`${this.baseUrl}/restrictions`, { params });
  }

  createRestriction(payload: ComponentRestrictionCreatePayload): Observable<ApiResponse<ComponentRestriction>> {
    return this.http.post<ApiResponse<ComponentRestriction>>(`${this.baseUrl}/restrictions`, payload);
  }

  deleteRestriction(id: string): Observable<ApiResponse<any>> {
    return this.http.delete<ApiResponse<any>>(`${this.baseUrl}/restrictions/${id}`);
  }

  getHistory(filters?: {
    stateTenantId?: string;
    ulbTenantId?: string;
    actionType?: string;
    skip?: number;
    limit?: number;
  }): Observable<ApiResponse<DelegationHistoryItem[]>> {
    let params = new HttpParams();
    if (filters) {
      if (filters.stateTenantId && filters.stateTenantId !== 'ALL') params = params.set('state_tenant_id', filters.stateTenantId);
      if (filters.ulbTenantId && filters.ulbTenantId !== 'ALL') params = params.set('ulb_tenant_id', filters.ulbTenantId);
      if (filters.actionType && filters.actionType !== 'ALL') params = params.set('action_type', filters.actionType);
      if (filters.skip !== undefined) params = params.set('skip', filters.skip.toString());
      if (filters.limit !== undefined) params = params.set('limit', filters.limit.toString());
    }
    return this.http.get<ApiResponse<DelegationHistoryItem[]>>(`${this.baseUrl}/history`, { params });
  }

  verifyHierarchyAccess(
    ulbTenantId: string,
    moduleCode: string,
    componentCode: string,
    action: string
  ): Observable<ApiResponse<EffectivePermissionCheckResult>> {
    return this.http.get<ApiResponse<EffectivePermissionCheckResult>>(
      `${this.baseUrl}/verify-access/${ulbTenantId}/${moduleCode}/${componentCode}/${action}`
    );
  }
}

