import { Component, OnInit, Output, EventEmitter, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { AuditVaultService } from '../../../../../../core/services/audit-vault.service';
import { DialogService } from '../../../../../../core/services/dialog.service';
import {
  RetentionPolicy,
  RetentionPolicyCreatePayload,
} from '../../../../../../core/models/audit-vault.model';

@Component({
  selector: 'app-retention-policy-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './retention-policy-dialog.component.html',
  styleUrl: './retention-policy-dialog.component.scss'
})
export class RetentionPolicyDialogComponent implements OnInit {
  @Output() closed = new EventEmitter<void>();
  @Output() saved = new EventEmitter<RetentionPolicy>();

  private auditService = inject(AuditVaultService);
  private dialogs = inject(DialogService);

  readonly isSubmitting = signal<boolean>(false);

  policyCode: string = '';
  policyName: string = '';
  retentionPeriod: number = 7;
  retentionUnit: string = 'Years';
  policyStatus: string = 'Active';
  effectiveDate: string = '';
  archiveRequired: boolean = true;
  archiveDestination: string = 'State Government Cold Storage Vault';
  legalHoldEnabled: boolean = false;
  description: string = '';

  readonly availableLevels = ['Level 0', 'Level 1', 'Level 2'];
  readonly selectedLevels = signal<Set<string>>(new Set(['Level 0', 'Level 1', 'Level 2']));

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
  readonly selectedCategories = signal<Set<string>>(
    new Set(['Authentication', 'Authorisation', 'Administrative Actions'])
  );

  ngOnInit(): void {
    const today = new Date().toISOString().split('T')[0];
    this.effectiveDate = today;
    this.generateDefaultPolicyCode();
  }

  generateDefaultPolicyCode(): void {
    const rand = Math.floor(100 + Math.random() * 900);
    this.policyCode = `RET-MUNICIPAL-${rand}`;
  }

  toggleLevel(lvl: string): void {
    const curr = new Set(this.selectedLevels());
    if (curr.has(lvl)) {
      if (curr.size > 1) curr.delete(lvl);
    } else {
      curr.add(lvl);
    }
    this.selectedLevels.set(curr);
  }

  isLevelSelected(lvl: string): boolean {
    return this.selectedLevels().has(lvl);
  }

  toggleCategory(cat: string): void {
    const curr = new Set(this.selectedCategories());
    if (curr.has(cat)) {
      if (curr.size > 1) curr.delete(cat);
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
    if (!this.policyCode.trim()) {
      this.dialogs.showToast('Policy Code is required', 'error');
      return;
    }
    if (!this.policyName.trim()) {
      this.dialogs.showToast('Policy Name is required', 'error');
      return;
    }
    if (this.selectedCategories().size === 0) {
      this.dialogs.showToast('Please select at least one governed event category', 'error');
      return;
    }
    if (!this.effectiveDate) {
      this.dialogs.showToast('Policy Effective Date is required', 'error');
      return;
    }

    const payload: RetentionPolicyCreatePayload = {
      policyCode: this.policyCode.trim().toUpperCase(),
      policyName: this.policyName.trim(),
      applicableTenantLevels: Array.from(this.selectedLevels()),
      eventCategories: Array.from(this.selectedCategories()),
      retentionPeriod: Number(this.retentionPeriod),
      retentionUnit: this.retentionUnit,
      archiveRequired: this.archiveRequired,
      archiveDestination: this.archiveRequired ? this.archiveDestination : null,
      legalHoldEnabled: this.legalHoldEnabled,
      effectiveDate: new Date(this.effectiveDate).toISOString(),
      policyStatus: this.policyStatus,
      description: this.description.trim() || null,
    };

    this.isSubmitting.set(true);
    this.auditService.createRetentionPolicy(payload).subscribe({
      next: (res) => {
        this.isSubmitting.set(false);
        this.saved.emit(res);
        this.dialogs.showToast(`Retention policy '${res.policyCode}' saved successfully`, 'success');
      },
      error: (err) => {
        this.isSubmitting.set(false);
        this.dialogs.showToast(err.error?.detail || 'Failed to save retention policy', 'error');
      }
    });
  }
}

