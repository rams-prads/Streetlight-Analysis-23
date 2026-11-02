import { Component, Input, Output, EventEmitter, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { IamRbacService } from '../../../../../../core/services/iam-rbac.service';
import { DialogService } from '../../../../../../core/services/dialog.service';
import { LoadingService } from '../../../../../../core/services/loading.service';
import { RoleItem, RoleCreatePayload } from '../../../../../../core/models/iam-rbac.model';

@Component({
  selector: 'app-create-role-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './create-role-dialog.component.html',
  styleUrl: './create-role-dialog.component.scss'
})
export class CreateRoleDialogComponent implements OnInit {
  @Input() role: RoleItem | null = null;
  @Input() availableRoles: RoleItem[] = [];
  @Output() saved = new EventEmitter<void>();
  @Output() closed = new EventEmitter<void>();

  private rbacService = inject(IamRbacService);
  private dialogs = inject(DialogService);
  private loading = inject(LoadingService);

  readonly isSubmitting = signal<boolean>(false);

  // Form Fields
  roleId: string = '';
  roleName: string = '';
  roleCode: string = '';
  description: string = '';
  roleLevel: string = 'Officer';
  scopeType: string = 'Ward';
  parentRoleId: string = '';
  status: string = 'Active';
  effectiveFrom: string = '';
  effectiveUntil: string = '';

  readonly roleLevels = [
    'Platform Super Admin',
    'State Admin',
    'ULB Admin',
    'Department Admin',
    'Officer',
    'Auditor',
    'Read-only User'
  ];

  readonly scopeTypes = [
    'Platform',
    'State',
    'ULB',
    'Department',
    'Ward',
    'Own Records'
  ];

  ngOnInit(): void {
    if (this.role) {
      this.roleId = this.role.id || 'Auto-assigned (UUID v4)';
      this.roleName = this.role.roleName;
      this.roleCode = this.role.roleCode;
      this.description = this.role.description;
      this.roleLevel = this.role.roleLevel;
      this.scopeType = this.role.scopeType;
      this.parentRoleId = this.role.parentRoleId || '';
      this.status = this.role.status;
      this.effectiveFrom = this.role.effectiveFrom || '';
      this.effectiveUntil = this.role.effectiveUntil || '';
    } else {
      this.roleId = 'Auto-assigned (UUID v4)';
    }
  }

  get inheritedPermissionsSummary(): string {
    if (!this.parentRoleId) {
      return `Baseline permissions determined by '${this.roleLevel}' level policies.`;
    }
    const parent = this.availableRoles.find(r => r.id === this.parentRoleId);
    return parent
      ? `Inherits all actions and module scope from parent role '${parent.roleName}' (${parent.roleCode}).`
      : 'No parent delegation inheritance.';
  }

  onSubmit(): void {
    if (!this.roleName.trim() || !this.roleCode.trim() || !this.description.trim()) {
      this.dialogs.showToast('Please fill all mandatory fields (Name, Code, Description)', 'warning');
      return;
    }

    const payload: RoleCreatePayload = {
      roleName: this.roleName.trim(),
      roleCode: this.roleCode.trim().toUpperCase(),
      description: this.description.trim(),
      roleLevel: this.roleLevel,
      scopeType: this.scopeType,
      parentRoleId: this.parentRoleId ? this.parentRoleId : null,
      status: this.status,
      effectiveFrom: this.effectiveFrom || null,
      effectiveUntil: this.effectiveUntil || null
    };

    this.isSubmitting.set(true);
    if (this.role && this.role.id) {
      this.loading.show('Updating role definition...');
      this.rbacService.updateRole(this.role.id, payload).subscribe({
        next: (res) => {
          this.isSubmitting.set(false);
          this.loading.hide();
          if (res.success) {
            this.dialogs.showToast(`Role '${payload.roleName}' updated`, 'success');
            this.saved.emit();
          }
        },
        error: (err) => {
          this.isSubmitting.set(false);
          this.loading.hide();
          this.dialogs.showToast(err?.error?.detail || 'Failed to update role', 'error');
        }
      });
    } else {
      this.loading.show('Creating municipal role...');
      this.rbacService.createRole(payload).subscribe({
        next: (res) => {
          this.isSubmitting.set(false);
          this.loading.hide();
          if (res.success) {
            this.dialogs.showToast(`Role '${payload.roleName}' created`, 'success');
            this.saved.emit();
          }
        },
        error: (err) => {
          this.isSubmitting.set(false);
          this.loading.hide();
          this.dialogs.showToast(err?.error?.detail || 'Failed to create role', 'error');
        }
      });
    }
  }

  onCancel(): void {
    this.closed.emit();
  }
}

