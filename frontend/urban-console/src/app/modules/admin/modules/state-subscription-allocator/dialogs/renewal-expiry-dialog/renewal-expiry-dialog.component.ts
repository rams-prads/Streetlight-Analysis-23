import { Component, Input, Output, EventEmitter, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { SubscriptionService } from '../../../../../../core/services/subscription.service';
import { DialogService } from '../../../../../../core/services/dialog.service';
import { LoadingService } from '../../../../../../core/services/loading.service';
import { StateSubscription, StateSubscriptionRenewPayload } from '../../../../../../core/models/subscription.model';
import { ModuleModel } from '../../../../../../core/models/module-catalogue.model';

@Component({
  selector: 'app-renewal-expiry-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './renewal-expiry-dialog.component.html',
  styleUrl: './renewal-expiry-dialog.component.scss'
})
export class RenewalExpiryDialogComponent implements OnInit {
  @Input() subscription: StateSubscription | null = null;
  @Output() saved = new EventEmitter<void>();
  @Output() closed = new EventEmitter<void>();

  private subscriptionService = inject(SubscriptionService);
  private dialogs = inject(DialogService);
  private loading = inject(LoadingService);

  readonly isSubmitting = signal<boolean>(false);
  readonly availableExtraModules = signal<ModuleModel[]>([]);
  readonly selectedAdditionalCodes = signal<Set<string>>(new Set<string>());

  // Form Fields
  renewalType: string = 'Term Extension';
  newStartDate: string = '';
  newEndDate: string = '';
  renewalRemarks: string = '';
  approvalReference: string = '';
  notifyTenant: boolean = true;

  readonly renewalTypes = ['Term Extension', 'Module Addition & Renewal', 'Full Overhaul'];

  ngOnInit(): void {
    if (this.subscription) {
      // Default start date: existing end date or today
      const start = this.subscription.endDate ? new Date(this.subscription.endDate) : new Date();
      this.newStartDate = start.toISOString().split('T')[0];

      // Default end date: 1 year from new start date
      const end = new Date(start);
      end.setFullYear(start.getFullYear() + 1);
      this.newEndDate = end.toISOString().split('T')[0];

      this.loadUnassignedModules();
    }
  }

  loadUnassignedModules(): void {
    if (!this.subscription) return;
    const existingCodes = new Set(this.subscription.subscribedModules.map(m => m.code));

    this.subscriptionService.getPublishedModules().subscribe({
      next: (res) => {
        if (res.success && res.data) {
          const unassigned = res.data.filter(m => !existingCodes.has(m.code));
          this.availableExtraModules.set(unassigned);
        }
      },
      error: () => this.availableExtraModules.set([])
    });
  }

  toggleAdditionalModule(code: string): void {
    const s = new Set(this.selectedAdditionalCodes());
    if (s.has(code)) {
      s.delete(code);
    } else {
      s.add(code);
    }
    this.selectedAdditionalCodes.set(s);
  }

  isAdditionalSelected(code: string): boolean {
    return this.selectedAdditionalCodes().has(code);
  }

  onCancel(): void {
    this.closed.emit();
  }

  onSubmit(): void {
    if (!this.subscription) return;

    if (!this.newStartDate || !this.newEndDate) {
      this.dialogs.showToast('Both New Start Date and New Expiry Date are required', 'error');
      return;
    }
    if (new Date(this.newEndDate) <= new Date(this.newStartDate)) {
      this.dialogs.showToast('New Expiry Date must be after New Start Date', 'error');
      return;
    }
    if (!this.renewalRemarks.trim()) {
      this.dialogs.showToast('Renewal Remarks are required for audit trail compliance', 'error');
      return;
    }

    const payload: StateSubscriptionRenewPayload = {
      subscriptionId: this.subscription.subscriptionId,
      renewalType: this.renewalType,
      newStartDate: new Date(this.newStartDate).toISOString(),
      newEndDate: new Date(this.newEndDate).toISOString(),
      additionalModuleCodes: Array.from(this.selectedAdditionalCodes()),
      renewalRemarks: this.renewalRemarks.trim(),
      approvalReference: this.approvalReference.trim() || null,
      notifyTenant: this.notifyTenant,
    };

    this.isSubmitting.set(true);
    this.loading.show('Renewing subscription and updating validity...');
    this.subscriptionService.renewSubscription(this.subscription.subscriptionId, payload).subscribe({
      next: (res) => {
        this.isSubmitting.set(false);
        this.loading.hide();
        if (res.success) {
          this.dialogs.showToast(res.message || 'Subscription renewed successfully', 'success');
          this.saved.emit();
        } else {
          this.dialogs.showToast(res.message || 'Failed to renew subscription', 'error');
        }
      },
      error: (err) => {
        this.isSubmitting.set(false);
        this.loading.hide();
        const msg = err.error?.detail || err.error?.message || 'Error renewing subscription';
        this.dialogs.showToast(msg, 'error', 4500);
      }
    });
  }
}

