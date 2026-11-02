import { Component, Input, Output, EventEmitter, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { TenantLifecycleService } from '../../../../../../core/services/tenant-lifecycle.service';
import { DialogService } from '../../../../../../core/services/dialog.service';
import { LoadingService } from '../../../../../../core/services/loading.service';
import { TenantDirectoryItem, TenantArchivePayload } from '../../../../../../core/models/tenant-lifecycle.model';

@Component({
  selector: 'app-archive-tenant-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './archive-tenant-dialog.component.html',
  styleUrl: './archive-tenant-dialog.component.scss'
})
export class ArchiveTenantDialogComponent implements OnInit {
  @Input({ required: true }) tenant!: TenantDirectoryItem;
  @Output() saved = new EventEmitter<void>();
  @Output() closed = new EventEmitter<void>();

  private lifecycleService = inject(TenantLifecycleService);
  private dialogs = inject(DialogService);
  private loading = inject(LoadingService);

  readonly isSubmitting = signal<boolean>(false);

  // Form Fields
  archiveReason: string = '';
  archiveEffectiveDate: string = '';
  dataRetentionPolicy: string = '10 Years - State Gazette Standard';
  retentionPeriodYears: number = 10;
  dataExportRequired: boolean = true;
  exportDestination: string = 'State Government Cold Storage Vault';
  supportingDocument: string = '';
  approvalAuthority: string = 'Director of Municipal Administration';
  finalConfirmation: boolean = false;

  readonly retentionPolicies = [
    { label: '7 Years - Municipal Public Accounts Standard', years: 7 },
    { label: '10 Years - State Gazette Standard', years: 10 },
    { label: '25 Years - Permanent National Heritage Standard', years: 25 },
    { label: 'Indefinite - Legal Dispute Hold', years: 99 },
  ];

  readonly exportDestinations = [
    'State Government Cold Storage Vault',
    'NIC Cloud Long-term Archive Repository',
    'Local Municipal Disaster Recovery Server',
  ];

  readonly approvalAuthorities = [
    'Platform Super Admin',
    'Principal Secretary, Urban Development',
    'Director of Municipal Administration',
    'Municipal Commissioner',
  ];

  ngOnInit(): void {
    const today = new Date().toISOString().slice(0, 10);
    this.archiveEffectiveDate = today;
  }

  get isStateWithActiveChildren(): boolean {
    return this.tenant.tenantLevel === 'State' && (this.tenant.activeChildUlbsCount ?? 0) > 0;
  }

  onPolicyChange(): void {
    const match = this.retentionPolicies.find(p => p.label === this.dataRetentionPolicy);
    if (match) {
      this.retentionPeriodYears = match.years;
    }
  }

  onSubmit(): void {
    if (this.isStateWithActiveChildren) {
      this.dialogs.showToast(`Cannot archive: ${this.tenant.activeChildUlbsCount} active child ULBs depend on this State`, 'error', 4500);
      return;
    }

    if (!this.archiveReason.trim()) {
      this.dialogs.showToast('Please state the formal archival and decommissioning reason', 'warning');
      return;
    }

    if (!this.finalConfirmation) {
      this.dialogs.showToast('Final compliance confirmation checkbox must be checked', 'warning');
      return;
    }

    const payload: TenantArchivePayload = {
      tenantId: this.tenant.tenantId,
      tenantLevel: this.tenant.tenantLevel,
      archiveReason: this.archiveReason.trim(),
      archiveEffectiveDate: this.archiveEffectiveDate,
      dataRetentionPolicy: this.dataRetentionPolicy,
      retentionPeriodYears: Number(this.retentionPeriodYears),
      dataExportRequired: this.dataExportRequired,
      exportDestination: this.dataExportRequired ? this.exportDestination : null,
      supportingDocument: this.supportingDocument.trim() || null,
      approvalAuthority: this.approvalAuthority,
      finalConfirmation: this.finalConfirmation,
    };

    this.isSubmitting.set(true);
    this.loading.show(`Archiving tenant ${this.tenant.name} under statutory retention policy...`);
    this.lifecycleService.archiveTenant(payload).subscribe({
      next: (res) => {
        this.isSubmitting.set(false);
        this.loading.hide();
        if (res.success) {
          this.dialogs.showToast(`Tenant ${this.tenant.name} archived successfully`, 'success', 3500);
          this.saved.emit();
        }
      },
      error: (err) => {
        this.isSubmitting.set(false);
        this.loading.hide();
        this.dialogs.showToast(err?.error?.detail || 'Failed to archive tenant', 'error', 4500);
      }
    });
  }

  onCancel(): void {
    this.closed.emit();
  }
}

