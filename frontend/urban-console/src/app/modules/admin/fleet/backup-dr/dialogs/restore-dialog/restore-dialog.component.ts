import { Component, EventEmitter, Input, Output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { BackupJobItem, RestoreJobPayload } from '../../../../../../core/models/backup-dr.model';

@Component({
  selector: 'app-restore-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './restore-dialog.component.html',
  styleUrls: ['./restore-dialog.component.scss'],
})
export class RestoreDialogComponent {
  @Input() availableBackups: BackupJobItem[] = [];
  @Output() cancel = new EventEmitter<void>();
  @Output() initiated = new EventEmitter<RestoreJobPayload>();

  restoreJobName = '';
  selectedBackupId = '';
  sourceDatabase = 'urban_core_prod';
  targetEnvironment = 'Staging Recovery Sandbox';
  targetDatabase = 'urban_core_recovered_staging';
  restoreType = 'Test Environment Restore';
  restoreDestination = 'pg-restore-sandbox.internal:5432/urban_core_recovered_staging';
  restoreTimestamp = '';
  includeTransactionLogs = true;
  validationRequired = true;
  approvalAuthority = 'Dr. Rajesh Rao (Chief SRE Officer)';
  changeReference = 'CR-2026-DR-092';
  restoreReason = '';
  finalConfirmation = false;

  isSubmitting = signal(false);

  readonly availableTargetEnvironments = [
    'Staging Recovery Sandbox',
    'Development Sandbox',
    'Production (Requires Dual-Auth)',
  ];

  readonly availableRestoreTypes = [
    'Test Environment Restore',
    'Full Database Restore',
    'Point-in-Time Restore',
    'Selected Tenant Restore',
  ];

  readonly availableAuthorities = [
    'Dr. Rajesh Rao (Chief SRE Officer)',
    'Sunil Sharma (State IT Secretary)',
    'Anand Verma (Lead SRE)',
    'Priya Nair (Principal Security Architect)',
  ];

  onCancel(): void {
    this.cancel.emit();
  }

  onSubmit(): void {
    if (
      !this.restoreJobName.trim() ||
      !this.selectedBackupId.trim() ||
      !this.sourceDatabase.trim() ||
      !this.targetDatabase.trim() ||
      !this.restoreDestination.trim() ||
      !this.approvalAuthority.trim() ||
      !this.changeReference.trim() ||
      !this.restoreReason.trim() ||
      !this.finalConfirmation
    ) {
      return;
    }

    const payload: RestoreJobPayload = {
      restoreJobName: this.restoreJobName.trim(),
      sourceBackupId: this.selectedBackupId,
      sourceDatabase: this.sourceDatabase,
      targetEnvironment: this.targetEnvironment,
      targetDatabase: this.targetDatabase,
      restoreType: this.restoreType,
      restoreDestination: this.restoreDestination.trim(),
      restoreTimestamp: this.restoreTimestamp ? new Date(this.restoreTimestamp).toISOString() : null,
      includeTransactionLogs: this.includeTransactionLogs,
      validationRequired: this.validationRequired,
      approvalAuthority: this.approvalAuthority,
      changeReference: this.changeReference.trim(),
      restoreReason: this.restoreReason.trim(),
      finalConfirmation: this.finalConfirmation,
    };

    this.isSubmitting.set(true);
    this.initiated.emit(payload);
  }
}

