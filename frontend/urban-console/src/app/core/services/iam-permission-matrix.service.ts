import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { OverrideChange, PermissionMatrix } from '../models/iam-permission-matrix.model';

/** The real Roles & Permission Matrix for the modules that actually have a backend (PTX, WTR) - not the
 * decorative one in iam-rbac.service.ts. Every call needs super_admin/system_admin; the backend 403s otherwise. */
@Injectable({ providedIn: 'root' })
export class IamPermissionMatrixService {
  private http = inject(HttpClient);
  private baseUrl = `${environment.apiUrl}/iam/permissions`;

  getMatrix(moduleCode: string): Observable<PermissionMatrix> {
    return this.http.get<PermissionMatrix>(`${this.baseUrl}/${moduleCode}/matrix`);
  }

  saveOverrides(moduleCode: string, changes: OverrideChange[]): Observable<PermissionMatrix> {
    return this.http.put<PermissionMatrix>(`${this.baseUrl}/${moduleCode}/overrides/bulk`, { changes });
  }

  /** Every real role across the named modules, for assigning a user's actual role (Global User Management, Phase 6). */
  listRoles(moduleCodes: string[]): Observable<{ roles: string[] }> {
    return this.http.get<{ roles: string[] }>(`${this.baseUrl}/roles`, { params: { modules: moduleCodes.join(',') } });
  }
}
