import { Component, Input, Output, EventEmitter, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { DelegationService } from '../../../../../../core/services/delegation.service';
import { TenantManagementService } from '../../../../../../core/services/tenant-management.service';
import { DialogService } from '../../../../../../core/services/dialog.service';
import { LoadingService } from '../../../../../../core/services/loading.service';
import { StateTenant } from '../../../../../../core/models/state-tenant.model';
import { StateDelegationScope, UlbAllocationCreatePayload } from '../../../../../../core/models/delegation.model';

@Component({
  selector: 'app-ulb-allocation-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './ulb-allocation-dialog.component.html',
  styleUrl: './ulb-allocation-dialog.component.scss'
})
export class UlbAllocationDialogComponent implements OnInit {
  @Input() preselectedStateId: string = '';
  @Output() saved = new EventEmitter<void>();
  @Output() closed = new EventEmitter<void>();

  private delegationService = inject(DelegationService);
  private tenantService = inject(TenantManagementService);
  private dialogs = inject(DialogService);
  private loading = inject(LoadingService);

  readonly stateTenants = signal<StateTenant[]>([]);
  readonly stateScope = signal<StateDelegationScope | null>(null);
  readonly isLoadingScope = signal<boolean>(false);
  readonly isSubmitting = signal<boolean>(false);

  // Form selections
  selectedStateTenantId: string = '';
  readonly selectedUlbIds = signal<Set<string>>(new Set());
  readonly selectedModuleCodes = signal<Set<string>>(new Set());
  readonly selectedActions = signal<Set<string>>(new Set(['VIEW', 'CREATE', 'UPDATE', 'APPROVE']));

  startDate: string = new Date().toISOString().substring(0, 10);
  endDate: string = '';
  allocationStatus: string = 'Active';
  approvalReference: string = '';
  remarks: string = '';

  readonly availableActions = ['VIEW', 'CREATE', 'UPDATE', 'DELETE', 'APPROVE', 'EXPORT', 'MANAGE'];

  ngOnInit(): void {
    this.tenantService.getStateTenants().subscribe({
      next: (states) => {
        const actives = (states || []).filter((s: StateTenant) => s.status === 'Active');
        this.stateTenants.set(actives);
        if (this.preselectedStateId) {
          this.selectedStateTenantId = this.preselectedStateId;
          this.loadStateScope(this.selectedStateTenantId);
        } else if (actives.length > 0) {
          this.selectedStateTenantId = actives[0].tenantId;
          this.loadStateScope(this.selectedStateTenantId);
        }
      },
      error: () => this.stateTenants.set([])
    });
  }

  onStateChange(): void {
    this.selectedUlbIds.set(new Set());
    this.selectedModuleCodes.set(new Set());
    this.loadStateScope(this.selectedStateTenantId);
  }

  loadStateScope(stateTenantId: string): void {
    if (!stateTenantId) return;
    this.isLoadingScope.set(true);
    this.delegationService.getStateScope(stateTenantId).subscribe({
      next: (res) => {
        this.isLoadingScope.set(false);
        if (res.success && res.data) {
          this.stateScope.set(res.data);
          // Auto select first ULB if only one
          if (res.data.childUlbs.length === 1) {
            this.selectedUlbIds.set(new Set([res.data.childUlbs[0].tenantId]));
          }
        }
      },
      error: () => {
        this.isLoadingScope.set(false);
      }
    });
  }

  // ULB multi-select helpers
  toggleUlb(tenantId: string): void {
    const current = new Set(this.selectedUlbIds());
    if (current.has(tenantId)) current.delete(tenantId);
    else current.add(tenantId);
    this.selectedUlbIds.set(current);
  }

  selectAllUlbs(): void {
    const scope = this.stateScope();
    if (!scope) return;
    this.selectedUlbIds.set(new Set(scope.childUlbs.map(u => u.tenantId)));
  }

  clearUlbs(): void {
    this.selectedUlbIds.set(new Set());
  }

  // Module multi-select helpers
  toggleModule(code: string): void {
    const current = new Set(this.selectedModuleCodes());
    if (current.has(code)) current.delete(code);
    else current.add(code);
    this.selectedModuleCodes.set(current);
  }

  selectAllModules(): void {
    const scope = this.stateScope();
    if (!scope) return;
    this.selectedModuleCodes.set(new Set(scope.activeSubscribedModules.map(m => m.code)));
  }

  clearModules(): void {
    this.selectedModuleCodes.set(new Set());
  }

  // Actions multi-select helpers
  toggleAction(act: string): void {
    const current = new Set(this.selectedActions());
    if (current.has(act)) current.delete(act);
    else current.add(act);
    this.selectedActions.set(current);
  }

  onCancel(): void {
    this.closed.emit();
  }

  onSubmit(): void {
    if (!this.selectedStateTenantId) {
      this.dialogs.showToast('Please select a parent State Tenant', 'error');
      return;
    }
    if (this.selectedUlbIds().size === 0) {
      this.dialogs.showToast('Please select at least one target ULB tenant', 'error');
      return;
    }
    if (this.selectedModuleCodes().size === 0) {
      this.dialogs.showToast('Please select at least one module from state subscription', 'error');
      return;
    }
    if (this.selectedActions().size === 0) {
      this.dialogs.showToast('Please select at least one allowed action permission', 'error');
      return;
    }

    const payload: UlbAllocationCreatePayload = {
      stateTenantId: this.selectedStateTenantId,
      ulbTenantIds: Array.from(this.selectedUlbIds()),
      moduleCodes: Array.from(this.selectedModuleCodes()),
      allocatedComponents: [], // empty delegates all components for the module
      allowedActions: Array.from(this.selectedActions()),
      startDate: new Date(this.startDate).toISOString(),
      endDate: this.endDate ? new Date(this.endDate).toISOString() : null,
      status: this.allocationStatus,
      approvalReference: this.approvalReference.trim() || null,
      remarks: this.remarks.trim() || null,
    };

    this.isSubmitting.set(true);
    this.loading.show('Validating state subscription & delegating to ULB(s)...');
    this.delegationService.createAllocations(payload).subscribe({
      next: (res) => {
        this.isSubmitting.set(false);
        this.loading.hide();
        if (res.success) {
          this.dialogs.showToast(res.message || 'Module allocations successfully created', 'success');
          this.saved.emit();
        } else {
          this.dialogs.showToast(res.message || 'Failed to allocate modules', 'error');
        }
      },
      error: (err) => {
        this.isSubmitting.set(false);
        this.loading.hide();
        this.dialogs.showToast(err.error?.detail || err.error?.message || 'Hierarchy check failed', 'error');
      }
    });
  }
}
