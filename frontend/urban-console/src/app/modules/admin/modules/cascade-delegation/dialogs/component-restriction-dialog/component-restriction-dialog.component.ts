import { Component, Input, Output, EventEmitter, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { DelegationService } from '../../../../../../core/services/delegation.service';
import { TenantManagementService } from '../../../../../../core/services/tenant-management.service';
import { DialogService } from '../../../../../../core/services/dialog.service';
import { LoadingService } from '../../../../../../core/services/loading.service';
import { StateTenant } from '../../../../../../core/models/state-tenant.model';
import { ComponentRestrictionCreatePayload, StateDelegationScope } from '../../../../../../core/models/delegation.model';

@Component({
  selector: 'app-component-restriction-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './component-restriction-dialog.component.html',
  styleUrl: './component-restriction-dialog.component.scss'
})
export class ComponentRestrictionDialogComponent implements OnInit {
  @Input() preselectedStateId: string = '';
  @Output() saved = new EventEmitter<void>();
  @Output() closed = new EventEmitter<void>();

  private delegationService = inject(DelegationService);
  private tenantService = inject(TenantManagementService);
  private dialogs = inject(DialogService);
  private loading = inject(LoadingService);

  readonly stateTenants = signal<StateTenant[]>([]);
  readonly stateScope = signal<StateDelegationScope | null>(null);
  readonly isSubmitting = signal<boolean>(false);

  selectedStateTenantId: string = '';
  selectedUlbId: string = '';
  selectedModuleCode: string = 'PTX';
  componentCode: string = '';
  componentName: string = '';
  restrictionType: string = 'Block Selected Actions';
  readonly selectedRestrictedActions = signal<Set<string>>(new Set(['DELETE', 'APPROVE']));

  reason: string = '';
  effectiveFrom: string = new Date().toISOString().substring(0, 10);
  effectiveUntil: string = '';
  isActive: boolean = true;

  readonly restrictionTypes = [
    { value: 'Block Selected Actions', desc: 'Restricts destructive operations like DELETE or APPROVE' },
    { value: 'Block Entire Component', desc: 'Completely disables the process component for this ULB' },
    { value: 'Read Only', desc: 'Limits user access strictly to VIEW and EXPORT' },
    { value: 'Restrict Data Scope', desc: 'Limits transaction limits or ward/zone visibility' }
  ];

  readonly availableActions = ['VIEW', 'CREATE', 'UPDATE', 'DELETE', 'APPROVE', 'EXPORT', 'MANAGE'];

  ngOnInit(): void {
    this.tenantService.getStateTenants().subscribe({
      next: (states) => {
        const actives = (states || []).filter((s: StateTenant) => s.status === 'Active');
        this.stateTenants.set(actives);
        if (this.preselectedStateId) {
          this.selectedStateTenantId = this.preselectedStateId;
        } else if (actives.length > 0) {
          this.selectedStateTenantId = actives[0].tenantId;
        }
        this.loadScope();
      },
      error: () => this.stateTenants.set([])
    });
  }

  onStateChange(): void {
    this.selectedUlbId = '';
    this.loadScope();
  }

  loadScope(): void {
    if (!this.selectedStateTenantId) return;
    this.delegationService.getStateScope(this.selectedStateTenantId).subscribe({
      next: (res) => {
        if (res.success && res.data) {
          this.stateScope.set(res.data);
          if (res.data.childUlbs.length > 0) {
            this.selectedUlbId = res.data.childUlbs[0].tenantId;
          }
          if (res.data.activeSubscribedModules.length > 0) {
            this.selectedModuleCode = res.data.activeSubscribedModules[0].code;
          }
        }
      }
    });
  }

  toggleRestrictedAction(act: string): void {
    const current = new Set(this.selectedRestrictedActions());
    if (current.has(act)) current.delete(act);
    else current.add(act);
    this.selectedRestrictedActions.set(current);
  }

  onCancel(): void {
    this.closed.emit();
  }

  onSubmit(): void {
    if (!this.selectedStateTenantId || !this.selectedUlbId) {
      this.dialogs.showToast('Please select State Tenant and Target ULB', 'error');
      return;
    }
    if (!this.componentCode.trim()) {
      this.dialogs.showToast('Component Code is required (e.g. PTX-P10)', 'error');
      return;
    }
    if (!this.reason.trim()) {
      this.dialogs.showToast('Restriction Reason is required', 'error');
      return;
    }

    const payload: ComponentRestrictionCreatePayload = {
      stateTenantId: this.selectedStateTenantId,
      ulbTenantId: this.selectedUlbId,
      moduleCode: this.selectedModuleCode,
      componentCode: this.componentCode.trim().toUpperCase(),
      componentName: this.componentName.trim() || undefined,
      restrictionType: this.restrictionType,
      restrictedActions: Array.from(this.selectedRestrictedActions()),
      reason: this.reason.trim(),
      effectiveFrom: new Date(this.effectiveFrom).toISOString(),
      effectiveUntil: this.effectiveUntil ? new Date(this.effectiveUntil).toISOString() : null,
      isActive: this.isActive,
    };

    this.isSubmitting.set(true);
    this.loading.show('Applying component restriction...');
    this.delegationService.createRestriction(payload).subscribe({
      next: (res) => {
        this.isSubmitting.set(false);
        this.loading.hide();
        if (res.success) {
          this.dialogs.showToast(res.message || 'Component restriction applied', 'success');
          this.saved.emit();
        } else {
          this.dialogs.showToast(res.message || 'Failed to apply restriction', 'error');
        }
      },
      error: (err) => {
        this.isSubmitting.set(false);
        this.loading.hide();
        this.dialogs.showToast(err.error?.detail || err.error?.message || 'Failed to apply restriction', 'error');
      }
    });
  }
}
