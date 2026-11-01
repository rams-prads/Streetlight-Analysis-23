import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../../environments/environment';
import { ApiResponse } from '../models/iam-sso.model';
import {
  GlobalUserItem,
  GlobalUserCreatePayload,
  GlobalUserScopePayload,
  UserInvitationItem,
  UserInvitationCreatePayload
} from '../models/iam-user.model';

@Injectable({
  providedIn: 'root'
})
export class IamUserService {
  private http = inject(HttpClient);
  private usersUrl = `${environment.apiUrl}/iam/users`;
  private invitationsUrl = `${environment.apiUrl}/iam/invitations`;

  getUsers(filters?: { tenantId?: string; userType?: string; status?: string; search?: string }): Observable<ApiResponse<GlobalUserItem[]>> {
    let params = new HttpParams();
    if (filters?.tenantId && filters.tenantId !== 'ALL') params = params.set('tenant_id', filters.tenantId);
    if (filters?.userType && filters.userType !== 'ALL') params = params.set('user_type', filters.userType);
    if (filters?.status && filters.status !== 'ALL') params = params.set('status', filters.status);
    if (filters?.search?.trim()) params = params.set('search', filters.search.trim());

    return this.http.get<ApiResponse<GlobalUserItem[]>>(this.usersUrl, { params });
  }

  getUserById(userId: string): Observable<ApiResponse<GlobalUserItem>> {
    return this.http.get<ApiResponse<GlobalUserItem>>(`${this.usersUrl}/${userId}`);
  }

  createUser(payload: GlobalUserCreatePayload): Observable<ApiResponse<GlobalUserItem>> {
    return this.http.post<ApiResponse<GlobalUserItem>>(this.usersUrl, payload);
  }

  updateUser(userId: string, payload: Partial<GlobalUserCreatePayload>): Observable<ApiResponse<GlobalUserItem>> {
    return this.http.put<ApiResponse<GlobalUserItem>>(`${this.usersUrl}/${userId}`, payload);
  }

  updateUserScope(userId: string, payload: GlobalUserScopePayload): Observable<ApiResponse<GlobalUserItem>> {
    return this.http.put<ApiResponse<GlobalUserItem>>(`${this.usersUrl}/${userId}/scope`, payload);
  }

  setUserStatus(userId: string, status: 'Active' | 'Suspended' | 'Deactivated'): Observable<ApiResponse<GlobalUserItem>> {
    const params = new HttpParams().set('status', status);
    return this.http.patch<ApiResponse<GlobalUserItem>>(`${this.usersUrl}/${userId}/status`, {}, { params });
  }

  resetPassword(userId: string, newPassword: string): Observable<ApiResponse<{ email: string; updated: boolean }>> {
    return this.http.post<ApiResponse<{ email: string; updated: boolean }>>(`${this.usersUrl}/${userId}/reset-password`, {
      newPassword
    });
  }

  revokeUserSessions(userId: string): Observable<ApiResponse<{ userId: string; email: string; revokedAt: string }>> {
    return this.http.post<ApiResponse<{ userId: string; email: string; revokedAt: string }>>(`${this.usersUrl}/${userId}/revoke-sessions`, {});
  }

  getInvitations(status?: string, search?: string): Observable<ApiResponse<UserInvitationItem[]>> {
    let params = new HttpParams();
    if (status && status !== 'ALL') params = params.set('status', status);
    if (search && search.trim()) params = params.set('search', search.trim());
    return this.http.get<ApiResponse<UserInvitationItem[]>>(this.invitationsUrl, { params });
  }

  createInvitation(payload: UserInvitationCreatePayload): Observable<ApiResponse<UserInvitationItem>> {
    return this.http.post<ApiResponse<UserInvitationItem>>(this.invitationsUrl, payload);
  }

  resendInvitation(invitationId: string): Observable<ApiResponse<UserInvitationItem>> {
    return this.http.post<ApiResponse<UserInvitationItem>>(`${this.invitationsUrl}/${invitationId}/resend`, {});
  }

  revokeInvitation(invitationId: string): Observable<ApiResponse<{ id: string; status: string }>> {
    return this.http.delete<ApiResponse<{ id: string; status: string }>>(`${this.invitationsUrl}/${invitationId}`);
  }
}
