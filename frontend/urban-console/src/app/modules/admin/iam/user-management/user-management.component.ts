import { Component, OnInit, Input, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../shared/components/icon/icon.component';
import { IamUserService } from '../../../../core/services/iam-user.service';
import { IamRbacService } from '../../../../core/services/iam-rbac.service';
import { IamSsoService } from '../../../../core/services/iam-sso.service';
import { DialogService } from '../../../../core/services/dialog.service';
import { LoadingService } from '../../../../core/services/loading.service';
import { GlobalUserItem, UserInvitationItem } from '../../../../core/models/iam-user.model';
import { RoleItem } from '../../../../core/models/iam-rbac.model';
import { AuthenticationAuditLog } from '../../../../core/models/iam-sso.model';
import { CreateUserDialogComponent } from './dialogs/create-user-dialog/create-user-dialog.component';
import { InviteUserDialogComponent } from './dialogs/invite-user-dialog/invite-user-dialog.component';
import { AssignScopeDialogComponent } from './dialogs/assign-scope-dialog/assign-scope-dialog.component';
import { ResetPasswordDialogComponent } from './dialogs/reset-password-dialog/reset-password-dialog.component';

@Component({
  selector: 'app-user-management',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    IconComponent,
    CreateUserDialogComponent,
    InviteUserDialogComponent,
    AssignScopeDialogComponent,
    ResetPasswordDialogComponent
  ],
  templateUrl: './user-management.component.html',
  styleUrl: './user-management.component.scss'
})
export class UserManagementComponent implements OnInit {
  private userService = inject(IamUserService);
  private rbacService = inject(IamRbacService);
  private ssoService = inject(IamSsoService);
  private dialogs = inject(DialogService);
  private loading = inject(LoadingService);

  readonly activeTab = signal<'directory' | 'invitations' | 'scopes' | 'history'>('directory');

  @Input() set defaultTab(tab: 'directory' | 'invitations' | 'scopes' | 'history' | undefined) {
    if (tab) {
      this.activeTab.set(tab);
    }
  }
  readonly users = signal<GlobalUserItem[]>([]);
  readonly invitations = signal<UserInvitationItem[]>([]);
  readonly roles = signal<RoleItem[]>([]);
  readonly auditLogs = signal<AuthenticationAuditLog[]>([]);

  // Filters
  readonly searchQuery = signal<string>('');
  readonly userTypeFilter = signal<string>('ALL');
  readonly statusFilter = signal<string>('ALL');
  readonly tenantFilter = signal<string>('ALL');

  // Dialog Controls
  readonly isCreateUserOpen = signal<boolean>(false);
  readonly selectedUserForEdit = signal<GlobalUserItem | null>(null);
  readonly isInviteUserOpen = signal<boolean>(false);
  readonly isAssignScopeOpen = signal<boolean>(false);
  readonly selectedUserForScope = signal<GlobalUserItem | null>(null);
  readonly isResetPasswordOpen = signal<boolean>(false);
  readonly selectedUserForPassword = signal<GlobalUserItem | null>(null);

  ngOnInit(): void {
    this.loadUsers();
    this.loadInvitations();
    this.loadRoles();
    this.loadAuditLogs();
  }

  loadAuditLogs(): void {
    this.ssoService.getAuditLogs().subscribe({
      next: (logs) => {
        if (logs) {
          this.auditLogs.set(logs);
        }
      },
      error: () => this.auditLogs.set([])
    });
  }

  loadUsers(): void {
    this.loading.show('Loading user directory...');
    this.userService.getUsers().subscribe({
      next: (res) => {
        this.loading.hide();
        if (res.success && res.data) {
          this.users.set(res.data);
        }
      },
      error: () => {
        this.loading.hide();
        this.dialogs.showToast('Failed to load user directory', 'error');
      }
    });
  }

  loadInvitations(): void {
    this.userService.getInvitations().subscribe({
      next: (res) => {
        if (res.success && res.data) {
          this.invitations.set(res.data);
        }
      }
    });
  }

  loadRoles(): void {
    this.rbacService.getRoles().subscribe({
      next: (res) => {
        if (res.success && res.data) {
          this.roles.set(res.data);
        }
      }
    });
  }

  get filteredUsers(): GlobalUserItem[] {
    const q = this.searchQuery().toLowerCase().trim();
    const type = this.userTypeFilter();
    const stat = this.statusFilter();
    const tenant = this.tenantFilter();

    return this.users().filter(u => {
      const matchQ = !q ||
        u.fullName.toLowerCase().includes(q) ||
        u.email.toLowerCase().includes(q) ||
        (u.designation && u.designation.toLowerCase().includes(q)) ||
        (u.employeeId && u.employeeId.toLowerCase().includes(q));

      const matchType = type === 'ALL' || u.userType === type;
      const matchStat = stat === 'ALL' || u.accountStatus === stat;
      const matchTenant = tenant === 'ALL' || u.stateTenantId === tenant || u.ulbTenantId === tenant;

      return matchQ && matchType && matchStat && matchTenant;
    });
  }

  // Pagination - Users Directory & Scope Tabs
  readonly userPage = signal<number>(1);
  readonly userPageSize = signal<number>(10);
  readonly userPageSizeOptions = [10, 25, 50];

  readonly paginatedUsers = computed(() => {
    const list = this.filteredUsers;
    const start = (this.userPage() - 1) * this.userPageSize();
    return list.slice(start, start + this.userPageSize());
  });

  readonly userTotalPages = computed(() => {
    const total = Math.ceil(this.filteredUsers.length / this.userPageSize());
    return total > 0 ? total : 1;
  });

  readonly userStartIndex = computed(() => {
    if (this.filteredUsers.length === 0) return 0;
    return (this.userPage() - 1) * this.userPageSize() + 1;
  });

  readonly userEndIndex = computed(() => {
    const end = this.userPage() * this.userPageSize();
    return Math.min(end, this.filteredUsers.length);
  });

  readonly userPagesArray = computed(() => {
    const pages: number[] = [];
    const total = this.userTotalPages();
    const curr = this.userPage();
    let start = Math.max(1, curr - 2);
    let end = Math.min(total, start + 4);
    if (end - start < 4) {
      start = Math.max(1, end - 4);
    }
    for (let i = start; i <= end; i++) {
      pages.push(i);
    }
    return pages;
  });

  prevUserPage(): void {
    if (this.userPage() > 1) {
      this.userPage.update(p => p - 1);
    }
  }

  nextUserPage(): void {
    if (this.userPage() < this.userTotalPages()) {
      this.userPage.update(p => p + 1);
    }
  }

  goToUserPage(page: number): void {
    if (page >= 1 && page <= this.userTotalPages()) {
      this.userPage.set(page);
    }
  }

  onUserPageSizeChange(size: number): void {
    this.userPageSize.set(Number(size));
    this.userPage.set(1);
  }

  // Pagination & Search - Invitations Tab
  readonly invitationSearchQuery = signal<string>('');
  readonly invitationStatusFilter = signal<string>('ALL');
  readonly invitationPage = signal<number>(1);
  readonly invitationPageSize = signal<number>(10);
  readonly invitationPageSizeOptions = [10, 25, 50];

  readonly filteredInvitations = computed(() => {
    const q = this.invitationSearchQuery().toLowerCase().trim();
    const stat = this.invitationStatusFilter();
    return this.invitations().filter(inv => {
      const matchQ = !q ||
        inv.email.toLowerCase().includes(q) ||
        inv.assignedRole.toLowerCase().includes(q) ||
        (inv.targetTenantId && inv.targetTenantId.toLowerCase().includes(q)) ||
        (inv.userType && inv.userType.toLowerCase().includes(q));
      const matchStat = stat === 'ALL' || inv.status === stat;
      return matchQ && matchStat;
    });
  });

  readonly paginatedInvitations = computed(() => {
    const list = this.filteredInvitations();
    const start = (this.invitationPage() - 1) * this.invitationPageSize();
    return list.slice(start, start + this.invitationPageSize());
  });

  readonly invitationTotalPages = computed(() => {
    const total = Math.ceil(this.filteredInvitations().length / this.invitationPageSize());
    return total > 0 ? total : 1;
  });

  readonly invitationStartIndex = computed(() => {
    if (this.filteredInvitations().length === 0) return 0;
    return (this.invitationPage() - 1) * this.invitationPageSize() + 1;
  });

  readonly invitationEndIndex = computed(() => {
    const end = this.invitationPage() * this.invitationPageSize();
    return Math.min(end, this.filteredInvitations().length);
  });

  readonly invitationPagesArray = computed(() => {
    const pages: number[] = [];
    const total = this.invitationTotalPages();
    const curr = this.invitationPage();
    let start = Math.max(1, curr - 2);
    let end = Math.min(total, start + 4);
    if (end - start < 4) {
      start = Math.max(1, end - 4);
    }
    for (let i = start; i <= end; i++) {
      pages.push(i);
    }
    return pages;
  });

  prevInvitationPage(): void {
    if (this.invitationPage() > 1) {
      this.invitationPage.update(p => p - 1);
    }
  }

  nextInvitationPage(): void {
    if (this.invitationPage() < this.invitationTotalPages()) {
      this.invitationPage.update(p => p + 1);
    }
  }

  goToInvitationPage(page: number): void {
    if (page >= 1 && page <= this.invitationTotalPages()) {
      this.invitationPage.set(page);
    }
  }

  onInvitationPageSizeChange(size: number): void {
    this.invitationPageSize.set(Number(size));
    this.invitationPage.set(1);
  }

  // Dialog actions
  openCreateUserDialog(): void {
    this.selectedUserForEdit.set(null);
    this.isCreateUserOpen.set(true);
  }

  openEditUserDialog(user: GlobalUserItem): void {
    this.selectedUserForEdit.set(user);
    this.isCreateUserOpen.set(true);
  }

  closeCreateUserDialog(): void {
    this.isCreateUserOpen.set(false);
    this.selectedUserForEdit.set(null);
  }

  onUserSaved(newUser?: GlobalUserItem | void): void {
    this.closeCreateUserDialog();
    this.loadUsers();
    if (newUser && typeof newUser === 'object' && newUser.id) {
      this.openAssignScopeDialog(newUser);
    }
  }

  openInviteDialog(): void {
    this.isInviteUserOpen.set(true);
  }

  closeInviteDialog(): void {
    this.isInviteUserOpen.set(false);
  }

  onInvitationSent(): void {
    this.closeInviteDialog();
    this.loadInvitations();
  }

  openAssignScopeDialog(user: GlobalUserItem): void {
    this.selectedUserForScope.set(user);
    this.isAssignScopeOpen.set(true);
  }

  closeAssignScopeDialog(): void {
    this.isAssignScopeOpen.set(false);
    this.selectedUserForScope.set(null);
  }

  onScopeSaved(): void {
    this.closeAssignScopeDialog();
    this.loadUsers();
  }

  openResetPasswordDialog(user: GlobalUserItem): void {
    this.selectedUserForPassword.set(user);
    this.isResetPasswordOpen.set(true);
  }

  closeResetPasswordDialog(): void {
    this.isResetPasswordOpen.set(false);
    this.selectedUserForPassword.set(null);
  }

  onPasswordSaved(): void {
    this.closeResetPasswordDialog();
    this.loadUsers();
  }

  toggleAccountStatus(user: GlobalUserItem): void {
    const nextStatus = user.accountStatus === 'Active' ? 'Suspended' : 'Active';
    this.loading.show(`Setting account status to ${nextStatus}...`);
    this.userService.setUserStatus(user.id, nextStatus).subscribe({
      next: (res) => {
        this.loading.hide();
        if (res.success) {
          this.dialogs.showToast(`User '${user.fullName}' is now ${nextStatus}`, 'success');
          this.loadUsers();
        }
      },
      error: () => {
        this.loading.hide();
        this.dialogs.showToast('Failed to update user status', 'error');
      }
    });
  }

  async revokeSessions(user: GlobalUserItem): Promise<void> {
    const confirmed = await this.dialogs.confirm({
      title: 'Revoke Active Sessions',
      message: `Immediately revoke all active Keycloak sessions and tokens for '${user.fullName}' (${user.email})?`,
      confirmText: 'Revoke Sessions',
      variant: 'destructive'
    });

    if (confirmed) {
      this.loading.show(`Revoking sessions for ${user.email}...`);
      this.userService.revokeUserSessions(user.id).subscribe({
        next: (res) => {
          this.loading.hide();
          if (res.success) {
            this.dialogs.showToast(`Sessions revoked for '${user.email}'`, 'success');
          }
        },
        error: () => {
          this.loading.hide();
          this.dialogs.showToast('Failed to revoke sessions', 'error');
        }
      });
    }
  }

  resendInvitation(inv: UserInvitationItem): void {
    this.loading.show(`Regenerating token for ${inv.email}...`);
    this.userService.resendInvitation(inv.id).subscribe({
      next: (res) => {
        this.loading.hide();
        if (res.success) {
          this.dialogs.showToast(`Invitation resent to ${inv.email}`, 'success');
          this.loadInvitations();
        }
      },
      error: () => {
        this.loading.hide();
        this.dialogs.showToast('Failed to resend invitation', 'error');
      }
    });
  }

  async revokeInvitation(inv: UserInvitationItem): Promise<void> {
    const confirmed = await this.dialogs.confirm({
      title: 'Revoke Invitation',
      message: `Revoke onboarding token for '${inv.email}'?`,
      confirmText: 'Revoke',
      variant: 'destructive'
    });

    if (confirmed) {
      this.userService.revokeInvitation(inv.id).subscribe({
        next: (res) => {
          if (res.success) {
            this.dialogs.showToast(`Invitation for ${inv.email} revoked`, 'success');
            this.loadInvitations();
          }
        }
      });
    }
  }
}
