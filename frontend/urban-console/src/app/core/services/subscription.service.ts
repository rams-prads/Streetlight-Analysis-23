import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  ApiResponse,
  StateSubscription,
  StateSubscriptionCreatePayload,
  StateSubscriptionRenewPayload,
  StateSubscriptionHistoryItem,
  StateSubscriptionStats,
} from '../models/subscription.model';
import { ModuleModel } from '../models/module-catalogue.model';

@Injectable({
  providedIn: 'root',
})
export class SubscriptionService {
  private http = inject(HttpClient);
  private baseUrl = `${environment.apiUrl}/modules/subscriptions`;

  getSubscriptions(filters?: {
    search?: string;
    stateTenantId?: string;
    status?: string;
    subscriptionType?: string;
    skip?: number;
    limit?: number;
  }): Observable<ApiResponse<StateSubscription[]>> {
    let params = new HttpParams();
    if (filters) {
      if (filters.search) params = params.set('search', filters.search);
      if (filters.stateTenantId && filters.stateTenantId !== 'ALL') params = params.set('state_tenant_id', filters.stateTenantId);
      if (filters.status && filters.status !== 'ALL') params = params.set('status', filters.status);
      if (filters.subscriptionType && filters.subscriptionType !== 'ALL') params = params.set('subscription_type', filters.subscriptionType);
      if (filters.skip !== undefined) params = params.set('skip', filters.skip.toString());
      if (filters.limit !== undefined) params = params.set('limit', filters.limit.toString());
    }
    return this.http.get<ApiResponse<StateSubscription[]>>(this.baseUrl, { params });
  }

  getStats(): Observable<ApiResponse<StateSubscriptionStats>> {
    return this.http.get<ApiResponse<StateSubscriptionStats>>(`${this.baseUrl}/stats`);
  }

  createSubscription(payload: StateSubscriptionCreatePayload): Observable<ApiResponse<StateSubscription>> {
    return this.http.post<ApiResponse<StateSubscription>>(this.baseUrl, payload);
  }

  renewSubscription(subscriptionId: string, payload: StateSubscriptionRenewPayload): Observable<ApiResponse<StateSubscription>> {
    return this.http.post<ApiResponse<StateSubscription>>(`${this.baseUrl}/${subscriptionId}/renew`, payload);
  }

  revokeSubscription(subscriptionId: string, reason: string, approvalRef?: string): Observable<ApiResponse<StateSubscription>> {
    let params = new HttpParams().set('reason', reason);
    if (approvalRef) params = params.set('approval_ref', approvalRef);
    return this.http.post<ApiResponse<StateSubscription>>(`${this.baseUrl}/${subscriptionId}/revoke`, {}, { params });
  }

  getHistory(filters?: {
    subscriptionId?: string;
    stateTenantId?: string;
    actionType?: string;
    skip?: number;
    limit?: number;
  }): Observable<ApiResponse<StateSubscriptionHistoryItem[]>> {
    let params = new HttpParams();
    if (filters) {
      if (filters.subscriptionId && filters.subscriptionId !== 'ALL') params = params.set('subscription_id', filters.subscriptionId);
      if (filters.stateTenantId && filters.stateTenantId !== 'ALL') params = params.set('state_tenant_id', filters.stateTenantId);
      if (filters.actionType && filters.actionType !== 'ALL') params = params.set('action_type', filters.actionType);
      if (filters.skip !== undefined) params = params.set('skip', filters.skip.toString());
      if (filters.limit !== undefined) params = params.set('limit', filters.limit.toString());
    }
    return this.http.get<ApiResponse<StateSubscriptionHistoryItem[]>>(`${this.baseUrl}/history`, { params });
  }

  getPublishedModules(): Observable<ApiResponse<ModuleModel[]>> {
    const params = new HttpParams().set('status', 'Published').set('limit', '50');
    return this.http.get<ApiResponse<ModuleModel[]>>(`${environment.apiUrl}/modules`, { params });
  }

  checkModuleActiveStatus(stateTenantId: string, moduleCode: string): Observable<any> {
    return this.http.get(`${this.baseUrl}/check/${stateTenantId}/${moduleCode}`);
  }
}

