import { Component, Output, EventEmitter, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { IamUserService } from '../../../../../../core/services/iam-user.service';
import { IamRbacService } from '../../../../../../core/services/iam-rbac.service';
import { DialogService } from '../../../../../../core/services/dialog.service';
import { LoadingService } from '../../../../../../core/services/loading.service';
import { TenantManagementService } from '../../../../../../core/services/tenant-management.service';
import { UlbManagementService } from '../../../../../../core/services/ulb-management.service';
import { UserInvitationCreatePayload } from '../../../../../../core/models/iam-user.model';
import { RoleItem } from '../../../../../../core/models/iam-rbac.model';
import { StateTenant } from '../../../../../../core/models/state-tenant.model';
import { UlbTenant } from '../../../../../../core/models/ulb-tenant.model';

@Component({
  selector: 'app-invite-user-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './invite-user-dialog.component.html',
  styleUrl: './invite-user-dialog.component.scss'
})
export class InviteUserDialogComponent implements OnInit {
  @Output() saved = new EventEmitter<void>();
  @Output() closed = new EventEmitter<void>();

  private userService = inject(IamUserService);
  private rbacService = inject(IamRbacService);
  private tenantService = inject(TenantManagementService);
  private ulbService = inject(UlbManagementService);
  private dialogs = inject(DialogService);
  private loading = inject(LoadingService);

  readonly roles = signal<RoleItem[]>([]);
  readonly states = signal<StateTenant[]>([]);
  readonly ulbs = signal<UlbTenant[]>([]);
  readonly isSubmitting = signal<boolean>(false);

  // Form Fields
  email: string = '';
  userType: string = 'Government Officer';
  targetTenantId: string = '';
  targetSubTenantId: string = '';
  assignedRole: string = 'STATE_DIRECTOR';
  departmentScope: string = 'Directorate of Municipal Administration';
  wardScope: string = '';
  invitationExpiryDays: number = 7;
  requireMfa: boolean = true;
  invitationMessage: string = 'You are invited to access the SUVIDHA Integrated Municipal ERP Platform. Please verify your identity and set up your multi-factor authentication credentials.';

  readonly userTypes = [
    'Government Officer',
    'Internal Staff',
    'Support Staff',
    'Auditor',
    'External Partner'
  ];

  ngOnInit(): void {
    this.rbacService.getRoles().subscribe({
      next: (res) => {
        if (res.success && res.data) {
          this.roles.set(res.data);
          if (res.data.length > 0 && !this.assignedRole) {
            this.assignedRole = res.data[0].roleCode;
          }
        }
      }
    });

    this.tenantService.getStateTenants().subscribe({
      next: (states) => {
        if (states && states.length > 0) {
          this.states.set(states);
          if (!this.targetTenantId) {
            this.targetTenantId = states[0].tenantId;
            this.loadUlbsForTenant(this.targetTenantId);
          }
        }
      }
    });
  }

  onTenantChange(tenantId: string): void {
    this.targetTenantId = tenantId;
    this.targetSubTenantId = '';
    this.loadUlbsForTenant(tenantId);
  }

  loadUlbsForTenant(tenantId: string): void {
    if (!tenantId) {
      this.ulbs.set([]);
      return;
    }
    this.ulbService.getUlbs({ stateCode: tenantId }).subscribe({
      next: (ulbs) => {
        this.ulbs.set(ulbs || []);
      },
      error: () => this.ulbs.set([])
    });
  }

  onSubmit(): void {
    if (!this.email.trim() || !this.targetTenantId || !this.assignedRole) {
      this.dialogs.showToast('Please provide email address, target tenant, and assigned role', 'warning');
      return;
    }

    const payload: UserInvitationCreatePayload = {
      email: this.email.trim().toLowerCase(),
      userType: this.userType,
      targetTenantId: this.targetTenantId,
      targetSubTenantId: this.targetSubTenantId || null,
      assignedRole: this.assignedRole,
      departmentScope: this.departmentScope.trim() || null,
      wardScope: this.wardScope.trim() || null,
      invitationExpiryDays: Number(this.invitationExpiryDays),
      requireMfa: this.requireMfa,
      invitationMessage: this.invitationMessage.trim() || null
    };

    this.isSubmitting.set(true);
    this.loading.show(`Dispatching single-use invitation token to ${payload.email}...`);
    this.userService.createInvitation(payload).subscribe({
      next: (res) => {
        this.isSubmitting.set(false);
        this.loading.hide();
        if (res.success) {
          this.dialogs.showToast(`Invitation sent to ${res.data.email}`, 'success');
          this.saved.emit();
        }
      },
      error: () => {
        this.isSubmitting.set(false);
        this.loading.hide();
        this.dialogs.showToast('Failed to send invitation', 'error');
      }
    });
  }

  onCancel(): void {
    this.closed.emit();
  }
}
