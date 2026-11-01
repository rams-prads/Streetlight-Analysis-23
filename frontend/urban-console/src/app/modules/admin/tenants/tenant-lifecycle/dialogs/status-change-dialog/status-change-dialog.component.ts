import { Component, Input, Output, EventEmitter, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { TenantLifecycleService } from '../../../../../../core/services/tenant-lifecycle.service';
import { DialogService } from '../../../../../../core/services/dialog.service';
import { LoadingService } from '../../../../../../core/services/loading.service';
import { TenantDirectoryItem, TenantStatusChangePayload } from '../../../../../../core/models/tenant-lifecycle.model';

@Component({
  selector: 'app-status-change-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './status-change-dialog.component.html',
  styleUrl: './status-change-dialog.component.scss'
})
export class StatusChangeDialogComponent implements OnInit {
  @Input() tenant: TenantDirectoryItem | null = null;
  @Input() availableTenants: TenantDirectoryItem[] = [];
  @Output() saved = new EventEmitter<void>();
  @Output() closed = new EventEmitter<void>();

  private lifecycleService = inject(TenantLifecycleService);
  private dialogs = inject(DialogService);
  private loading = inject(LoadingService);

  readonly isSubmitting = signal<boolean>(false);

  // Form Fields
  selectedTenantId: string = '';
  newStatus: string = 'Active';
  reason: string = '';
  effectiveFrom: string = '';
  effectiveUntil: string = '';
  supportingDocument: string = '';
  approvalReference: string = '';
  confirmed: boolean = false;

  readonly statusOptions = ['Draft', 'Active', 'Suspended', 'Locked', 'Maintenance', 'Archived'];

  ngOnInit(): void {
    if (this.tenant) {
      this.selectedTenantId = this.tenant.tenantId;
    } else if (this.availableTenants.length > 0) {
      this.selectedTenantId = this.availableTenants[0].tenantId;
    }

    // Default effectiveFrom to now (YYYY-MM-DDTHH:mm)
    const now = new Date();
    this.effectiveFrom = now.toISOString().slice(0, 16);
  }

  get currentSelectedTenant(): TenantDirectoryItem | undefined {
    return this.tenant || this.availableTenants.find(t => t.tenantId === this.selectedTenantId);
  }

  get isStateWithActiveChildren(): boolean {
    const t = this.currentSelectedTenant;
    return !!(t && t.tenantLevel === 'State' && this.newStatus === 'Archived' && (t.activeChildUlbsCount ?? 0) > 0);
  }

  onSubmit(): void {
    const t = this.currentSelectedTenant;
    if (!t) {
      this.dialogs.showToast('Please select a target tenant', 'warning');
      return;
    }

    if (!this.reason.trim()) {
      this.dialogs.showToast('Status change reason is mandatory for audit logging', 'warning');
      return;
    }

    if (!this.confirmed) {
      this.dialogs.showToast('Please confirm the lifecycle status change', 'warning');
      return;
    }

    if (this.isStateWithActiveChildren) {
      this.dialogs.showToast(`Cannot archive State: ${t.activeChildUlbsCount} active ULBs still depend on it`, 'error', 4000);
      return;
    }

    const payload: TenantStatusChangePayload = {
      tenantId: t.tenantId,
      tenantLevel: t.tenantLevel,
      newStatus: this.newStatus,
      reason: this.reason.trim(),
      effectiveFrom: this.effectiveFrom ? new Date(this.effectiveFrom).toISOString() : new Date().toISOString(),
      effectiveUntil: this.effectiveUntil ? new Date(this.effectiveUntil).toISOString() : null,
      supportingDocument: this.supportingDocument.trim() || null,
      approvalReference: this.approvalReference.trim() || null,
      confirmation: this.confirmed,
    };

    this.isSubmitting.set(true);
    this.loading.show(`Transitioning ${t.name} to ${this.newStatus}...`);
    this.lifecycleService.updateStatus(payload).subscribe({
      next: (res) => {
        this.isSubmitting.set(false);
        this.loading.hide();
        if (res.success) {
          this.dialogs.showToast(`Status updated: ${t.name} is now ${this.newStatus}`, 'success', 3000);
          this.saved.emit();
        }
      },
      error: (err) => {
        this.isSubmitting.set(false);
        this.loading.hide();
        this.dialogs.showToast(err?.error?.detail || 'Failed to update tenant status', 'error', 4000);
      }
    });
  }

  onCancel(): void {
    this.closed.emit();
  }
}

