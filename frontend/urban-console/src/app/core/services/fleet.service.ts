import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Observable, map } from 'rxjs';
import { KeycloakAuthService } from './keycloak.service';
import { environment } from '../../../environments/environment';
import {
  MicroserviceOverviewStats,
  MicroserviceRegistryItem,
  MicroserviceRegisterPayload,
  PodMonitoringItem,
  WorkerQueueItem,
  DatabaseConnectionPoolItem,
} from '../models/fleet.model';

export interface ApiResponse<T> {
  success: boolean;
  code?: number;
  message?: string;
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
export class FleetService {
  private http = inject(HttpClient);
  private authService = inject(KeycloakAuthService);
  private baseUrl = `${environment.apiUrl}/fleet/cluster`;

  private getHeaders(): HttpHeaders {
    const token = this.authService.getToken();
    const tenantId = this.authService.getTenantId();
    return new HttpHeaders({
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      'X-Tenant-ID': tenantId,
    });
  }

  getClusterStats(): Observable<MicroserviceOverviewStats> {
    return this.http
      .get<ApiResponse<MicroserviceOverviewStats>>(`${this.baseUrl}/stats`, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  getMicroservices(filters?: {
    search?: string;
    environment?: string;
    category?: string;
    status?: string;
    region?: string;
    skip?: number;
    limit?: number;
  }): Observable<MicroserviceRegistryItem[]> {
    let params = new HttpParams();
    if (filters) {
      if (filters.search) params = params.set('search', filters.search);
      if (filters.environment && filters.environment !== 'ALL') params = params.set('environment', filters.environment);
      if (filters.category && filters.category !== 'ALL') params = params.set('category', filters.category);
      if (filters.status && filters.status !== 'ALL') params = params.set('status', filters.status);
      if (filters.region && filters.region !== 'ALL') params = params.set('region', filters.region);
      if (filters.skip !== undefined) params = params.set('skip', filters.skip.toString());
      if (filters.limit !== undefined) params = params.set('limit', filters.limit.toString());
    }

    return this.http
      .get<ApiResponse<MicroserviceRegistryItem[]>>(`${this.baseUrl}/services`, {
        headers: this.getHeaders(),
        params,
      })
      .pipe(map(unwrapResponse));
  }

  registerMicroservice(payload: MicroserviceRegisterPayload): Observable<MicroserviceRegistryItem> {
    return this.http
      .post<ApiResponse<MicroserviceRegistryItem>>(`${this.baseUrl}/services`, payload, {
        headers: this.getHeaders(),
      })
      .pipe(map(unwrapResponse));
  }

  getPods(filters?: {
    cluster?: string;
    namespace?: string;
    deployment?: string;
    podName?: string;
    serviceCode?: string;
    status?: string;
    nodeName?: string;
  }): Observable<PodMonitoringItem[]> {
    let params = new HttpParams();
    if (filters) {
      if (filters.cluster && filters.cluster !== 'ALL') params = params.set('cluster', filters.cluster);
      if (filters.namespace && filters.namespace !== 'ALL') params = params.set('namespace', filters.namespace);
      if (filters.deployment && filters.deployment !== 'ALL') params = params.set('deployment', filters.deployment);
      if (filters.podName) params = params.set('pod_name', filters.podName);
      if (filters.serviceCode && filters.serviceCode !== 'ALL') params = params.set('service_code', filters.serviceCode);
      if (filters.status && filters.status !== 'ALL') params = params.set('status', filters.status);
      if (filters.nodeName && filters.nodeName !== 'ALL') params = params.set('node_name', filters.nodeName);
    }

    return this.http
      .get<ApiResponse<PodMonitoringItem[]>>(`${this.baseUrl}/pods`, {
        headers: this.getHeaders(),
        params,
      })
      .pipe(map(unwrapResponse));
  }

  getWorkerQueues(filters?: {
    queueName?: string;
    workerService?: string;
    queueType?: string;
    queueStatus?: string;
  }): Observable<WorkerQueueItem[]> {
    let params = new HttpParams();
    if (filters) {
      if (filters.queueName && filters.queueName !== 'ALL') params = params.set('queue_name', filters.queueName);
      if (filters.workerService && filters.workerService !== 'ALL') params = params.set('worker_service', filters.workerService);
      if (filters.queueType && filters.queueType !== 'ALL') params = params.set('queue_type', filters.queueType);
      if (filters.queueStatus && filters.queueStatus !== 'ALL') params = params.set('queue_status', filters.queueStatus);
    }

    return this.http
      .get<ApiResponse<WorkerQueueItem[]>>(`${this.baseUrl}/queues`, {
        headers: this.getHeaders(),
        params,
      })
      .pipe(map(unwrapResponse));
  }

  getDatabaseConnectionPools(filters?: {
    databaseCluster?: string;
    databaseName?: string;
    serviceName?: string;
    connectionStatus?: string;
  }): Observable<DatabaseConnectionPoolItem[]> {
    let params = new HttpParams();
    if (filters) {
      if (filters.databaseCluster && filters.databaseCluster !== 'ALL') params = params.set('database_cluster', filters.databaseCluster);
      if (filters.databaseName && filters.databaseName !== 'ALL') params = params.set('database_name', filters.databaseName);
      if (filters.serviceName && filters.serviceName !== 'ALL') params = params.set('service_name', filters.serviceName);
      if (filters.connectionStatus && filters.connectionStatus !== 'ALL') params = params.set('connection_status', filters.connectionStatus);
    }

    return this.http
      .get<ApiResponse<DatabaseConnectionPoolItem[]>>(`${this.baseUrl}/db-pools`, {
        headers: this.getHeaders(),
        params,
      })
      .pipe(map(unwrapResponse));
  }
}

