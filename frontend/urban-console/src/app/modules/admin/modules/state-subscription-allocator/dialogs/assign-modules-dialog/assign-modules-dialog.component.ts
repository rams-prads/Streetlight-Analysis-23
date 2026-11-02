import { Component, Input, Output, EventEmitter, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { SubscriptionService } from '../../../../../../core/services/subscription.service';
import { TenantManagementService } from '../../../../../../core/services/tenant-management.service';
import { DialogService } from '../../../../../../core/services/dialog.service';
import { LoadingService } from '../../../../../../core/services/loading.service';
import { StateTenant } from '../../../../../../core/models/state-tenant.model';
import { ModuleModel } from '../../../../../../core/models/module-catalogue.model';
import { StateSubscriptionCreatePayload } from '../../../../../../core/models/subscription.model';

@Component({
  selector: 'app-assign-modules-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './assign-modules-dialog.component.html',
  styleUrl: './assign-modules-dialog.component.scss'
})
export class AssignModulesDialogComponent implements OnInit {
  @Input() preselectedStateId: string = '';
  @Output() saved = new EventEmitter<void>();
  @Output() closed = new EventEmitter<void>();

  private subscriptionService = inject(SubscriptionService);
  private tenantService = inject(TenantManagementService);
  private dialogs = inject(DialogService);
  private loading = inject(LoadingService);

  readonly isSubmitting = signal<boolean>(false);
  readonly activeStates = signal<StateTenant[]>([]);
  readonly publishedModules = signal<ModuleModel[]>([]);

  // Form Fields
  selectedStateTenantId: string = '';
  subscriptionName: string = '';
  subscriptionType: string = 'Standard';
  selectedModuleCodes: Set<string> = new Set<string>();
  startDate: string = '';
  endDate: string = '';
  billingCycle: string = 'Yearly';
  subscriptionStatus: string = 'Active';
  autoRenewal: boolean = false;
  remarks: string = '';
  approvalReference: string = '';

  readonly subscriptionTypes = ['Standard', 'Premium', 'Custom', 'Government Sponsored'];
  readonly billingCycles = ['Monthly', 'Quarterly', 'Half-Yearly', 'Yearly', 'Custom'];
  readonly statusOptions = ['Active', 'Draft', 'Suspended'];

  ngOnInit(): void {
    // Set default dates: Today to 1 year later
    const today = new Date();
    this.startDate = today.toISOString().split('T')[0];
    const nextYear = new Date(today);
    nextYear.setFullYear(today.getFullYear() + 1);
    this.endDate = nextYear.toISOString().split('T')[0];

    this.loadActiveStates();
    this.loadPublishedModules();
  }

  loadActiveStates(): void {
    this.tenantService.getStateTenants().subscribe({
      next: (states) => {
        // Enforce rule: Only active state tenants receive new subscriptions
        const activeOnly = (states || []).filter(s => s.status === 'Active');
        this.activeStates.set(activeOnly);
        if (this.preselectedStateId) {
          this.selectedStateTenantId = this.preselectedStateId;
          this.onStateChange();
        } else if (activeOnly.length > 0) {
          this.selectedStateTenantId = activeOnly[0].tenantId;
          this.onStateChange();
        }
      },
      error: () => this.activeStates.set([])
    });
  }

  loadPublishedModules(): void {
    this.subscriptionService.getPublishedModules().subscribe({
      next: (res) => {
        if (res.success && res.data) {
          this.publishedModules.set(res.data);
        }
      },
      error: () => this.publishedModules.set([])
    });
  }

  onStateChange(): void {
    const st = this.activeStates().find(s => s.tenantId === this.selectedStateTenantId);
    if (st && !this.subscriptionName) {
      const year = new Date().getFullYear();
      this.subscriptionName = `${st.stateName} State Municipal ERP Subscription FY${year}-${year + 1}`;
    }
  }

  toggleModule(code: string): void {
    if (this.selectedModuleCodes.has(code)) {
      this.selectedModuleCodes.delete(code);
    } else {
      this.selectedModuleCodes.add(code);
    }
  }

  isModuleSelected(code: string): boolean {
    return this.selectedModuleCodes.has(code);
  }

  selectAllModules(): void {
    this.publishedModules().forEach(m => this.selectedModuleCodes.add(m.code));
  }

  clearAllModules(): void {
    this.selectedModuleCodes.clear();
  }

  onCancel(): void {
    this.closed.emit();
  }

  onSubmit(): void {
    if (!this.selectedStateTenantId) {
      this.dialogs.showToast('Please select a valid State Tenant', 'error');
      return;
    }
    if (!this.subscriptionName.trim()) {
      this.dialogs.showToast('Subscription Name is required', 'error');
      return;
    }
    if (this.selectedModuleCodes.size === 0) {
      this.dialogs.showToast('Please select at least one module to allocate', 'error');
      return;
    }
    if (!this.startDate) {
      this.dialogs.showToast('Subscription Start Date is required', 'error');
      return;
    }

    const payload: StateSubscriptionCreatePayload = {
      stateTenantId: this.selectedStateTenantId,
      subscriptionName: this.subscriptionName.trim(),
      subscriptionType: this.subscriptionType,
      moduleCodes: Array.from(this.selectedModuleCodes),
      startDate: new Date(this.startDate).toISOString(),
      endDate: this.endDate ? new Date(this.endDate).toISOString() : null,
      billingCycle: this.billingCycle,
      status: this.subscriptionStatus,
      autoRenewal: this.autoRenewal,
      remarks: this.remarks.trim() || null,
      approvalReference: this.approvalReference.trim() || null,
    };

    this.isSubmitting.set(true);
    this.loading.show('Allocating modules & creating subscription...');
    this.subscriptionService.createSubscription(payload).subscribe({
      next: (res) => {
        this.isSubmitting.set(false);
        this.loading.hide();
        if (res.success) {
          this.dialogs.showToast(res.message || 'Subscription created successfully', 'success');
          this.saved.emit();
        } else {
          this.dialogs.showToast(res.message || 'Failed to allocate subscription', 'error');
        }
      },
      error: (err) => {
        this.isSubmitting.set(false);
        this.loading.hide();
        const msg = err.error?.detail || err.error?.message || 'Error creating subscription';
        this.dialogs.showToast(msg, 'error', 4500);
      }
    });
  }
}

