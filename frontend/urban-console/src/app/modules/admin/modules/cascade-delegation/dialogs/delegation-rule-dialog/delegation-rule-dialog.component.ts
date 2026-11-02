import { Component, Input, Output, EventEmitter, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { DelegationService } from '../../../../../../core/services/delegation.service';
import { TenantManagementService } from '../../../../../../core/services/tenant-management.service';
import { DialogService } from '../../../../../../core/services/dialog.service';
import { LoadingService } from '../../../../../../core/services/loading.service';
import { StateTenant } from '../../../../../../core/models/state-tenant.model';
import { DelegationRuleCreatePayload } from '../../../../../../core/models/delegation.model';

@Component({
  selector: 'app-delegation-rule-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './delegation-rule-dialog.component.html',
  styleUrl: './delegation-rule-dialog.component.scss'
})
export class DelegationRuleDialogComponent implements OnInit {
  @Input() preselectedStateId: string = '';
  @Output() saved = new EventEmitter<void>();
  @Output() closed = new EventEmitter<void>();

  private delegationService = inject(DelegationService);
  private tenantService = inject(TenantManagementService);
  private dialogs = inject(DialogService);
  private loading = inject(LoadingService);

  readonly stateTenants = signal<StateTenant[]>([]);
  readonly isSubmitting = signal<boolean>(false);

  // Form Model
  selectedStateTenantId: string = '';
  ruleName: string = '';
  ruleCode: string = '';
  delegationMode: string = 'Selective Delegation';
  allowModuleDelegation: boolean = true;
  allowComponentDelegation: boolean = true;
  allowRoleDelegation: boolean = true;
  requireStateApproval: boolean = true;
  effectiveFrom: string = new Date().toISOString().substring(0, 10);
  effectiveUntil: string = '';
  ruleDescription: string = '';
  ruleStatus: string = 'Active';

  readonly ulbTypeOptions = ['Municipal Corporation', 'Municipality', 'Town Panchayat', 'Cantonment Board'];
  readonly selectedUlbTypes = signal<Set<string>>(new Set(['Municipal Corporation', 'Municipality']));

  readonly delegationModes = [
    { value: 'Full Delegation', desc: 'Allows complete cascading of all active modules & actions' },
    { value: 'Selective Delegation', desc: 'State admin explicitly approves each module allocation' },
    { value: 'Restricted Delegation', desc: 'Read-only or capped operational scope delegation' },
    { value: 'No Delegation', desc: 'Blocks all sub-tenant cascading (State Level centralized)' }
  ];

  ngOnInit(): void {
    this.tenantService.getStateTenants().subscribe({
      next: (states) => {
        const actives = (states || []).filter((s: StateTenant) => s.status === 'Active');
        this.stateTenants.set(actives);
        if (this.preselectedStateId) {
          this.selectedStateTenantId = this.preselectedStateId;
          this.generateDefaultRuleCode();
        } else if (actives.length > 0) {
          this.selectedStateTenantId = actives[0].tenantId;
          this.generateDefaultRuleCode();
        }
      },
      error: () => this.stateTenants.set([])
    });
  }

  onStateChange(): void {
    this.generateDefaultRuleCode();
  }

  generateDefaultRuleCode(): void {
    const st = this.stateTenants().find(s => s.tenantId === this.selectedStateTenantId);
    const code = st ? st.stateCode : 'ST';
    const rand = Math.random().toString(36).substring(2, 6).toUpperCase();
    this.ruleCode = `DEL-${code}-${rand}`;
  }

  toggleUlbType(type: string): void {
    const current = new Set(this.selectedUlbTypes());
    if (current.has(type)) {
      current.delete(type);
    } else {
      current.add(type);
    }
    this.selectedUlbTypes.set(current);
  }

  isUlbTypeSelected(type: string): boolean {
    return this.selectedUlbTypes().has(type);
  }

  onCancel(): void {
    this.closed.emit();
  }

  onSubmit(): void {
    if (!this.selectedStateTenantId) {
      this.dialogs.showToast('Please select a parent State Tenant', 'error');
      return;
    }
    if (!this.ruleName.trim()) {
      this.dialogs.showToast('Rule Name is required', 'error');
      return;
    }
    if (!this.ruleCode.trim()) {
      this.dialogs.showToast('Rule Code is required', 'error');
      return;
    }
    if (!this.ruleDescription.trim()) {
      this.dialogs.showToast('Rule Description is required', 'error');
      return;
    }

    const payload: DelegationRuleCreatePayload = {
      ruleCode: this.ruleCode.trim().toUpperCase(),
      ruleName: this.ruleName.trim(),
      stateTenantId: this.selectedStateTenantId,
      applicableUlbTypes: Array.from(this.selectedUlbTypes()),
      delegationMode: this.delegationMode,
      allowModuleDelegation: this.allowModuleDelegation,
      allowComponentDelegation: this.allowComponentDelegation,
      allowRoleDelegation: this.allowRoleDelegation,
      requireStateApproval: this.requireStateApproval,
      effectiveFrom: new Date(this.effectiveFrom).toISOString(),
      effectiveUntil: this.effectiveUntil ? new Date(this.effectiveUntil).toISOString() : null,
      description: this.ruleDescription.trim(),
      ruleStatus: this.ruleStatus,
    };

    this.isSubmitting.set(true);
    this.loading.show('Creating cascade delegation rule...');
    this.delegationService.createRule(payload).subscribe({
      next: (res) => {
        this.isSubmitting.set(false);
        this.loading.hide();
        if (res.success) {
          this.dialogs.showToast(res.message || 'Delegation rule created successfully', 'success');
          this.saved.emit();
        } else {
          this.dialogs.showToast(res.message || 'Failed to create delegation rule', 'error');
        }
      },
      error: (err) => {
        this.isSubmitting.set(false);
        this.loading.hide();
        this.dialogs.showToast(err.error?.detail || err.error?.message || 'Failed to create delegation rule', 'error');
      }
    });
  }
}
