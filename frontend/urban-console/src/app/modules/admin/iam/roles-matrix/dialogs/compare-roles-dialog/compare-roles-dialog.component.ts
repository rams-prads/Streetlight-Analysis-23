import { Component, Input, Output, EventEmitter, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { IamRbacService } from '../../../../../../core/services/iam-rbac.service';
import { DialogService } from '../../../../../../core/services/dialog.service';
import { RoleItem, RoleComparisonResult } from '../../../../../../core/models/iam-rbac.model';

@Component({
  selector: 'app-compare-roles-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './compare-roles-dialog.component.html',
  styleUrl: './compare-roles-dialog.component.scss'
})
export class CompareRolesDialogComponent implements OnInit {
  @Input() availableRoles: RoleItem[] = [];
  @Input() initialRoleAId: string = '';
  @Input() initialRoleBId: string = '';
  @Output() closed = new EventEmitter<void>();

  private rbacService = inject(IamRbacService);
  private dialogs = inject(DialogService);

  roleAId: string = '';
  roleBId: string = '';
  readonly isLoading = signal<boolean>(false);
  readonly comparisonResult = signal<RoleComparisonResult | null>(null);

  ngOnInit(): void {
    if (this.availableRoles.length >= 2) {
      this.roleAId = this.initialRoleAId || this.availableRoles[0].id;
      this.roleBId = this.initialRoleBId || this.availableRoles[1].id;
      this.runComparison();
    }
  }

  runComparison(): void {
    if (!this.roleAId || !this.roleBId) return;
    if (this.roleAId === this.roleBId) {
      this.dialogs.showToast('Please select two distinct roles to compare', 'warning');
      return;
    }

    this.isLoading.set(true);
    this.rbacService.compareRoles(this.roleAId, this.roleBId).subscribe({
      next: (res) => {
        this.isLoading.set(false);
        if (res.success && res.data) {
          this.comparisonResult.set(res.data);
        }
      },
      error: () => {
        this.isLoading.set(false);
        this.dialogs.showToast('Failed to compare roles', 'error');
      }
    });
  }

  onCancel(): void {
    this.closed.emit();
  }
}

