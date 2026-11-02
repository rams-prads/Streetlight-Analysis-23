import { Component, EventEmitter, Output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { BackupPolicyPayload } from '../../../../../../core/models/backup-dr.model';

@Component({
  selector: 'app-policy-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './policy-dialog.component.html',
  styleUrls: ['./policy-dialog.component.scss'],
})
export class PolicyDialogComponent {
  @Output() cancel = new EventEmitter<void>();
  @Output() created = new EventEmitter<BackupPolicyPayload>();

  policyName = '';
  policyCode = '';
  backupType = 'Full Backup';
  backupScope = 'Platform Full Database';
  environment = 'Production';
  databaseCluster = 'pg-aurora-cluster-prod';
  databaseName = 'urban_core_prod';
  tenantScope = 'All State Tenants';
  backupDestination = 'AWS S3 (Immutable Glacier Lock)';
  storageBucketPath = 's3://suvidha-backup-vault-prod/pg-cluster-01/';
  backupFrequency = 'Daily';
  backupSchedule = '0 2 * * * (02:00 AM IST)';
  timeZone = 'Asia/Kolkata (IST)';
  retentionPeriod = 90;
  retentionUnit = 'Days';
  encryptionEnabled = true;
  compressionEnabled = true;
  backupVerification = true;
  notificationRecipientsText = 'sre-dr-team@urban.gov.in, cert-in-alerts@urban.gov.in';
  policyStatus = 'Active';

  isSubmitting = signal(false);

  readonly availableBackupTypes = [
    'Full Backup',
    'Incremental Backup',
    'Differential Backup',
    'WAL / Transaction Log Backup',
  ];

  readonly availableScopes = [
    'Platform Full Database',
    'Tenant Scoped',
    'Configuration Only',
    'Audit Vault WORM',
  ];

  readonly availableEnvironments = ['Production', 'Staging', 'Development'];

  readonly availableClusters = [
    'pg-aurora-cluster-prod',
    'pg-gis-postgis-cluster',
    'redis-cluster-ha',
  ];

  readonly availableDatabases = [
    'urban_core_prod',
    'urban_ptx_billing',
    'urban_gis_spatial',
    'urban_audit_vault',
  ];

  readonly availableDestinations = [
    'AWS S3 (Immutable Glacier Lock)',
    'GCS Coldline (WORM Vault)',
    'State Gov Data Centre NAS',
  ];

  readonly availableFrequencies = ['Hourly', 'Daily', 'Weekly', 'Monthly', 'Custom'];

  onCancel(): void {
    this.cancel.emit();
  }

  onSubmit(): void {
    if (
      !this.policyName.trim() ||
      !this.policyCode.trim() ||
      !this.storageBucketPath.trim() ||
      !this.backupSchedule.trim()
    ) {
      return;
    }

    const recipients = this.notificationRecipientsText
      .split(',')
      .map((e) => e.trim())
      .filter((e) => !!e);

    const payload: BackupPolicyPayload = {
      policyName: this.policyName.trim(),
      policyCode: this.policyCode.trim().toUpperCase(),
      backupType: this.backupType,
      backupScope: this.backupScope,
      environment: this.environment,
      databaseCluster: this.databaseCluster,
      databaseName: this.databaseName,
      tenantScope: this.tenantScope,
      backupDestination: this.backupDestination,
      storageBucketPath: this.storageBucketPath.trim(),
      backupFrequency: this.backupFrequency,
      backupSchedule: this.backupSchedule.trim(),
      timeZone: this.timeZone,
      retentionPeriod: Number(this.retentionPeriod) || 90,
      retentionUnit: this.retentionUnit,
      encryptionEnabled: this.encryptionEnabled,
      compressionEnabled: this.compressionEnabled,
      backupVerification: this.backupVerification,
      notificationRecipients: recipients,
      policyStatus: this.policyStatus,
    };

    this.isSubmitting.set(true);
    this.created.emit(payload);
  }
}

