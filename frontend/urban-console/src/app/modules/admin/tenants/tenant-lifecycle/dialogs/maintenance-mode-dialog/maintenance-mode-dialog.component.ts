import { Component, Input, Output, EventEmitter, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { TenantLifecycleService } from '../../../../../../core/services/tenant-lifecycle.service';
import { DialogService } from '../../../../../../core/services/dialog.service';
import { LoadingService } from '../../../../../../core/services/loading.service';
import { TenantDirectoryItem, TenantMaintenancePayload } from '../../../../../../core/models/tenant-lifecycle.model';

@Component({
  selector: 'app-maintenance-mode-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './maintenance-mode-dialog.component.html',
  styleUrl: './maintenance-mode-dialog.component.scss'
})
export class MaintenanceModeDialogComponent implements OnInit {
  @Input({ required: true }) tenant!: TenantDirectoryItem;
  @Output() saved = new EventEmitter<void>();
  @Output() closed = new EventEmitter<void>();

  private lifecycleService = inject(TenantLifecycleService);
  private dialogs = inject(DialogService);
  private loading = inject(LoadingService);

  readonly isSubmitting = signal<boolean>(false);
  readonly isLoadingConfig = signal<boolean>(true);

  // Form Fields
  isMaintenanceActive: boolean = false;
  maintenanceTitle: string = 'Scheduled Municipal System Maintenance Window';
  maintenanceMessage: string = 'SUVIDHA core billing and registry services are temporarily offline for planned database indexing and security upgrades. Citizen services will resume shortly.';
  startTime: string = '';
  endTime: string = '';
  allowedIpsRaw: string = '';
  allowAdminAccess: boolean = true;
  notificationRequired: boolean = true;
  notificationRecipientsRaw: string = '';
  reason: string = '';

  ngOnInit(): void {
    const now = new Date();
    this.startTime = now.toISOString().slice(0, 16);
    const end = new Date(now.getTime() + 4 * 60 * 60 * 1000); // +4 hours
    this.endTime = end.toISOString().slice(0, 16);

    // Load existing maintenance config if any
    this.lifecycleService.getMaintenance(this.tenant.tenantId).subscribe({
      next: (res) => {
        this.isLoadingConfig.set(false);
        if (res.success && res.data) {
          const cfg = res.data;
          this.isMaintenanceActive = cfg.isActive;
          if (cfg.title) this.maintenanceTitle = cfg.title;
          if (cfg.message) this.maintenanceMessage = cfg.message;
          if (cfg.startTime) this.startTime = new Date(cfg.startTime).toISOString().slice(0, 16);
          if (cfg.endTime) this.endTime = new Date(cfg.endTime).toISOString().slice(0, 16);
          if (cfg.allowedIps && cfg.allowedIps.length > 0) this.allowedIpsRaw = cfg.allowedIps.join(', ');
          this.allowAdminAccess = cfg.allowAdminAccess;
          this.notificationRequired = cfg.notificationRequired;
          if (cfg.notificationRecipients && cfg.notificationRecipients.length > 0) {
            this.notificationRecipientsRaw = cfg.notificationRecipients.join(', ');
          }
          if (cfg.reason) this.reason = cfg.reason;
        }
      },
      error: () => this.isLoadingConfig.set(false)
    });
  }

  onSubmit(): void {
    if (this.isMaintenanceActive && !this.reason.trim()) {
      this.dialogs.showToast('Please provide a maintenance reason for audit ledger', 'warning');
      return;
    }

    const ips = this.allowedIpsRaw
      ? this.allowedIpsRaw.split(',').map(s => s.trim()).filter(Boolean)
      : [];
    const recipients = this.notificationRecipientsRaw
      ? this.notificationRecipientsRaw.split(',').map(s => s.trim()).filter(Boolean)
      : [];

    const payload: TenantMaintenancePayload = {
      tenantId: this.tenant.tenantId,
      tenantLevel: this.tenant.tenantLevel,
      isMaintenanceActive: this.isMaintenanceActive,
      maintenanceTitle: this.maintenanceTitle.trim() || null,
      maintenanceMessage: this.maintenanceMessage.trim() || null,
      startTime: this.startTime ? new Date(this.startTime).toISOString() : null,
      endTime: this.endTime ? new Date(this.endTime).toISOString() : null,
      allowedIps: ips,
      allowAdminAccess: this.allowAdminAccess,
      notificationRequired: this.notificationRequired,
      notificationRecipients: recipients,
      reason: this.reason.trim(),
    };

    this.isSubmitting.set(true);
    this.loading.show(this.isMaintenanceActive ? 'Enabling maintenance window...' : 'Restoring operational service...');
    this.lifecycleService.updateMaintenance(payload).subscribe({
      next: (res) => {
        this.isSubmitting.set(false);
        this.loading.hide();
        if (res.success) {
          const actionWord = this.isMaintenanceActive ? 'enabled' : 'deactivated';
          this.dialogs.showToast(`Maintenance mode ${actionWord} for ${this.tenant.name}`, 'success', 3000);
          this.saved.emit();
        }
      },
      error: (err) => {
        this.isSubmitting.set(false);
        this.loading.hide();
        this.dialogs.showToast(err?.error?.detail || 'Failed to update maintenance configuration', 'error', 4000);
      }
    });
  }

  onCancel(): void {
    this.closed.emit();
  }
}

