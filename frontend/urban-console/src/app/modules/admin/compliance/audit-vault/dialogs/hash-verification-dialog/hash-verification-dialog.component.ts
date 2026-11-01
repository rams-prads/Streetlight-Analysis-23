import { Component, OnInit, Output, EventEmitter, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { AuditVaultService } from '../../../../../../core/services/audit-vault.service';
import { TenantManagementService } from '../../../../../../core/services/tenant-management.service';
import { DialogService } from '../../../../../../core/services/dialog.service';
import { StateTenant } from '../../../../../../core/models/state-tenant.model';
import {
  HashVerificationJob,
  HashVerificationCreatePayload,
} from '../../../../../../core/models/audit-vault.model';

@Component({
  selector: 'app-hash-verification-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './hash-verification-dialog.component.html',
  styleUrl: './hash-verification-dialog.component.scss'
})
export class HashVerificationDialogComponent implements OnInit {
  @Output() closed = new EventEmitter<void>();
  @Output() completed = new EventEmitter<HashVerificationJob>();

  private auditService = inject(AuditVaultService);
  private tenantService = inject(TenantManagementService);
  private dialogs = inject(DialogService);

  readonly stateTenants = signal<StateTenant[]>([]);
  readonly isVerifying = signal<boolean>(false);
  readonly verificationJobResult = signal<HashVerificationJob | null>(null);

  jobName: string = 'CERT-In Scheduled Compliance Verification';
  verificationScope: string = 'Global Platform';
  selectedTenantId: string = '';
  algorithm: string = 'SHA-256';
  verificationMode: string = 'On-Demand Scan';
  notificationRecipientsText: string = 'ciso@urban.gov.in, compliance@nic.in';
  remarks: string = 'Verification of mathematical continuity across chained audit ledger.';

  fromTimestamp: string = '';
  toTimestamp: string = '';

  ngOnInit(): void {
    const now = new Date();
    const thirtyDaysAgo = new Date();
    thirtyDaysAgo.setDate(now.getDate() - 30);

    this.fromTimestamp = this.formatDatetimeForInput(thirtyDaysAgo);
    this.toTimestamp = this.formatDatetimeForInput(now);

    this.tenantService.getStateTenants().subscribe({
      next: (states) => {
        this.stateTenants.set((states || []).filter((s) => s.status === 'Active'));
      },
      error: () => this.stateTenants.set([])
    });
  }

  private formatDatetimeForInput(date: Date): string {
    const pad = (n: number) => (n < 10 ? '0' + n : n);
    return (
      date.getFullYear() +
      '-' +
      pad(date.getMonth() + 1) +
      '-' +
      pad(date.getDate()) +
      'T' +
      pad(date.getHours()) +
      ':' +
      pad(date.getMinutes())
    );
  }

  onScopeChange(): void {
    if (this.verificationScope === 'Global Platform') {
      this.selectedTenantId = '';
    }
  }

  onCancel(): void {
    this.closed.emit();
  }

  resetAndRunAnother(): void {
    this.verificationJobResult.set(null);
    this.jobName = 'On-Demand Ledger Integrity Scan';
  }

  onSubmit(): void {
    if (!this.jobName.trim()) {
      this.dialogs.showToast('Verification Job Name is required', 'error');
      return;
    }
    if (this.verificationScope !== 'Global Platform' && !this.selectedTenantId) {
      this.dialogs.showToast('Please select target tenant jurisdiction', 'error');
      return;
    }
    if (!this.fromTimestamp || !this.toTimestamp) {
      this.dialogs.showToast('From and To timestamps are required', 'error');
      return;
    }

    const recipients = this.notificationRecipientsText
      ? this.notificationRecipientsText.split(',').map((e) => e.trim()).filter((e) => e.length > 0)
      : [];

    const payload: HashVerificationCreatePayload = {
      jobName: this.jobName.trim(),
      verificationScope: this.verificationScope,
      tenantId: this.selectedTenantId || null,
      fromTimestamp: new Date(this.fromTimestamp).toISOString(),
      toTimestamp: new Date(this.toTimestamp).toISOString(),
      algorithm: this.algorithm,
      verificationMode: this.verificationMode,
      notificationRecipients: recipients,
      remarks: this.remarks.trim() || null,
    };

    this.isVerifying.set(true);
    this.auditService.runHashVerification(payload).subscribe({
      next: (res) => {
        this.isVerifying.set(false);
        this.verificationJobResult.set(res);
        this.completed.emit(res);
        this.dialogs.showToast('Verification job completed successfully', 'success');
      },
      error: (err) => {
        this.isVerifying.set(false);
        this.dialogs.showToast(err.error?.detail || 'Verification job failed', 'error');
      }
    });
  }
}

