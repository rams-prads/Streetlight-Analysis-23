import { Component, OnInit, Output, EventEmitter, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { AuditVaultService } from '../../../../../../core/services/audit-vault.service';
import { TenantManagementService } from '../../../../../../core/services/tenant-management.service';
import { DialogService } from '../../../../../../core/services/dialog.service';
import { StateTenant } from '../../../../../../core/models/state-tenant.model';
import {
  AuditExportJob,
  AuditExportCreatePayload,
} from '../../../../../../core/models/audit-vault.model';

@Component({
  selector: 'app-audit-export-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './audit-export-dialog.component.html',
  styleUrl: './audit-export-dialog.component.scss'
})
export class AuditExportDialogComponent implements OnInit {
  @Output() closed = new EventEmitter<void>();
  @Output() exported = new EventEmitter<AuditExportJob>();

  private auditService = inject(AuditVaultService);
  private tenantService = inject(TenantManagementService);
  private dialogs = inject(DialogService);

  readonly stateTenants = signal<StateTenant[]>([]);
  readonly isSubmitting = signal<boolean>(false);

  exportName: string = 'Statutory Compliance Audit Archive';
  exportFormat: string = 'CSV';
  tenantScope: string = 'All Tenants';
  selectedStateTenantId: string = '';
  dateFrom: string = '';
  dateTo: string = '';
  includeHashInfo: boolean = true;
  maskSensitiveInfo: boolean = true;
  exportReason: string = 'Annual CERT-In and CAG statutory audit compliance filing';
  approvalReference: string = 'MUNICIPAL/AUDIT/2026/894';

  readonly availableCategories = [
    'Authentication',
    'Authorisation',
    'Tenant Management',
    'User Management',
    'Subscription Changes',
    'Configuration Changes',
    'Data Access',
    'Administrative Actions',
  ];
  readonly selectedCategories = signal<Set<string>>(new Set());

  ngOnInit(): void {
    const now = new Date();
    const thirtyDaysAgo = new Date();
    thirtyDaysAgo.setDate(now.getDate() - 30);

    this.dateFrom = this.formatDatetimeForInput(thirtyDaysAgo);
    this.dateTo = this.formatDatetimeForInput(now);

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

  toggleCategory(cat: string): void {
    const curr = new Set(this.selectedCategories());
    if (curr.has(cat)) {
      curr.delete(cat);
    } else {
      curr.add(cat);
    }
    this.selectedCategories.set(curr);
  }

  isCategorySelected(cat: string): boolean {
    return this.selectedCategories().has(cat);
  }

  onCancel(): void {
    this.closed.emit();
  }

  onSubmit(): void {
    if (!this.exportName.trim()) {
      this.dialogs.showToast('Export Name is required', 'error');
      return;
    }
    if (this.tenantScope !== 'All Tenants' && !this.selectedStateTenantId) {
      this.dialogs.showToast('Please select State Tenant', 'error');
      return;
    }
    if (!this.dateFrom || !this.dateTo) {
      this.dialogs.showToast('Date From and Date To are required', 'error');
      return;
    }
    if (!this.exportReason.trim()) {
      this.dialogs.showToast('Export Reason is required', 'error');
      return;
    }

    const payload: AuditExportCreatePayload = {
      exportName: this.exportName.trim(),
      exportFormat: this.exportFormat,
      tenantScope: this.tenantScope,
      stateTenantId: this.tenantScope !== 'All Tenants' ? this.selectedStateTenantId : null,
      ulbTenantId: null,
      eventCategories: Array.from(this.selectedCategories()),
      dateFrom: new Date(this.dateFrom).toISOString(),
      dateTo: new Date(this.dateTo).toISOString(),
      includeHashInfo: this.includeHashInfo,
      maskSensitiveInfo: this.maskSensitiveInfo,
      exportReason: this.exportReason.trim(),
      approvalReference: this.approvalReference.trim() || null,
    };

    this.isSubmitting.set(true);
    this.auditService.createAuditExport(payload).subscribe({
      next: (res) => {
        this.isSubmitting.set(false);
        this.exported.emit(res);
        this.dialogs.showToast(`Audit export '${res.exportId}' generated successfully`, 'success');
      },
      error: (err) => {
        this.isSubmitting.set(false);
        this.dialogs.showToast(err.error?.detail || 'Failed to generate audit export', 'error');
      }
    });
  }
}

