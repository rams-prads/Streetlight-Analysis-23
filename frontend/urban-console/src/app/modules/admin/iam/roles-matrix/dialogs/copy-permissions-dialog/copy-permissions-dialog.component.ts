import { Component, Input, Output, EventEmitter, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { IamRbacService } from '../../../../../../core/services/iam-rbac.service';
import { DialogService } from '../../../../../../core/services/dialog.service';
import { LoadingService } from '../../../../../../core/services/loading.service';
import { RoleItem } from '../../../../../../core/models/iam-rbac.model';

@Component({
  selector: 'app-copy-permissions-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './copy-permissions-dialog.component.html',
  styleUrl: './copy-permissions-dialog.component.scss'
})
export class CopyPermissionsDialogComponent implements OnInit {
  @Input() targetRole!: RoleItem;
  @Input() availableRoles: RoleItem[] = [];
  @Output() saved = new EventEmitter<void>();
  @Output() closed = new EventEmitter<void>();

  private rbacService = inject(IamRbacService);
  private dialogs = inject(DialogService);
  private loading = inject(LoadingService);

  sourceRoleId: string = '';
  readonly isCopying = signal<boolean>(false);

  ngOnInit(): void {
    const defaultSource = this.availableRoles.find(r => r.id !== this.targetRole.id);
    if (defaultSource) {
      this.sourceRoleId = defaultSource.id;
    }
  }

  onSubmit(): void {
    if (!this.sourceRoleId) {
      this.dialogs.showToast('Please select a source role to copy permissions from', 'warning');
      return;
    }

    const source = this.availableRoles.find(r => r.id === this.sourceRoleId);
    const sourceName = source ? source.roleName : 'Selected Role';

    this.isCopying.set(true);
    this.loading.show(`Cloning matrix from '${sourceName}'...`);
    this.rbacService.copyPermissions(this.targetRole.id, this.sourceRoleId).subscribe({
      next: (res) => {
        this.isCopying.set(false);
        this.loading.hide();
        if (res.success) {
          this.dialogs.showToast(`Successfully copied ${res.data.copiedCount} permission rules to ${this.targetRole.roleName}`, 'success');
          this.saved.emit();
        }
      },
      error: () => {
        this.isCopying.set(false);
        this.loading.hide();
        this.dialogs.showToast('Failed to copy role permissions', 'error');
      }
    });
  }

  onCancel(): void {
    this.closed.emit();
  }
}

