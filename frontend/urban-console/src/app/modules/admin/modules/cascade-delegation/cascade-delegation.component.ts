import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../shared/components/icon/icon.component';
import { DelegationService } from '../../../../core/services/delegation.service';
import { TenantManagementService } from '../../../../core/services/tenant-management.service';
import { DialogService } from '../../../../core/services/dialog.service';
import { LoadingService } from '../../../../core/services/loading.service';
import { StateTenant } from '../../../../core/models/state-tenant.model';
import {
  DelegationRule,
  UlbAllocation,
  ComponentRestriction,
  DelegationHistoryItem,
  DelegationOverviewStats,
} from '../../../../core/models/delegation.model';
import { DelegationRuleDialogComponent } from './dialogs/delegation-rule-dialog/delegation-rule-dialog.component';
import { UlbAllocationDialogComponent } from './dialogs/ulb-allocation-dialog/ulb-allocation-dialog.component';
import { ComponentRestrictionDialogComponent } from './dialogs/component-restriction-dialog/component-restriction-dialog.component';
import { VerifyAccessDialogComponent } from './dialogs/verify-access-dialog/verify-access-dialog.component';

@Component({
  selector: 'app-cascade-delegation',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    IconComponent,
    DelegationRuleDialogComponent,
    UlbAllocationDialogComponent,
    ComponentRestrictionDialogComponent,
    VerifyAccessDialogComponent
  ],
  templateUrl: './cascade-delegation.component.html',
  styleUrl: './cascade-delegation.component.scss'
})
export class CascadeDelegationComponent implements OnInit {
  private delegationService = inject(DelegationService);
  private tenantService = inject(TenantManagementService);
  private dialogs = inject(DialogService);
  private loading = inject(LoadingService);

  readonly activeTab = signal<'rules' | 'allocations' | 'restrictions'>('rules');

  // Data signals
  readonly rules = signal<DelegationRule[]>([]);
  readonly allocations = signal<UlbAllocation[]>([]);
  readonly restrictions = signal<ComponentRestriction[]>([]);
  readonly masterStates = signal<StateTenant[]>([]);
  readonly stats = signal<DelegationOverviewStats | null>(null);
  readonly historyLogs = signal<DelegationHistoryItem[]>([]);
  readonly isLoading = signal<boolean>(false);

  // Filters
  readonly searchQuery = signal<string>('');
  readonly selectedStateFilter = signal<string>('ALL');
  readonly selectedStatusFilter = signal<string>('ALL');

  // Pagination
  readonly currentPage = signal<number>(1);
  readonly pageSize = signal<number>(10);
  readonly pageSizeOptions = [5, 10, 20, 50];

  // History modal pagination
  readonly isHistoryOpen = signal<boolean>(false);
  readonly histPage = signal<number>(1);
  readonly histPageSize = signal<number>(10);

  // Dialog signals
  readonly isRuleDialogOpen = signal<boolean>(false);
  readonly isAllocDialogOpen = signal<boolean>(false);
  readonly isRestrictDialogOpen = signal<boolean>(false);
  readonly isVerifyDialogOpen = signal<boolean>(false);

  // Revoke Allocation state
  readonly allocToRevoke = signal<UlbAllocation | null>(null);
  readonly isRevokeAllocOpen = signal<boolean>(false);
  revokeReason: string = '';

  // Filtered Rules
  readonly filteredRules = computed(() => {
    const q = this.searchQuery().toLowerCase().trim();
    const st = this.selectedStateFilter();
    const stat = this.selectedStatusFilter();

    return this.rules().filter(r => {
      const matchQ =
        !q ||
        r.ruleCode.toLowerCase().includes(q) ||
        r.ruleName.toLowerCase().includes(q) ||
        (r.stateName && r.stateName.toLowerCase().includes(q));
      const matchSt = st === 'ALL' || r.stateTenantId === st;
      const matchStat = stat === 'ALL' || r.ruleStatus === stat;
      return matchQ && matchSt && matchStat;
    });
  });

  // Filtered Allocations
  readonly filteredAllocations = computed(() => {
    const q = this.searchQuery().toLowerCase().trim();
    const st = this.selectedStateFilter();
    const stat = this.selectedStatusFilter();

    return this.allocations().filter(a => {
      const matchQ =
        !q ||
        a.allocationId.toLowerCase().includes(q) ||
        a.moduleCode.toLowerCase().includes(q) ||
        a.moduleName.toLowerCase().includes(q) ||
        (a.ulbName && a.ulbName.toLowerCase().includes(q)) ||
        (a.stateName && a.stateName.toLowerCase().includes(q));
      const matchSt = st === 'ALL' || a.stateTenantId === st;
      const matchStat = stat === 'ALL' || a.status === stat;
      return matchQ && matchSt && matchStat;
    });
  });

  // Filtered Restrictions
  readonly filteredRestrictions = computed(() => {
    const q = this.searchQuery().toLowerCase().trim();
    const st = this.selectedStateFilter();

    return this.restrictions().filter(r => {
      const matchQ =
        !q ||
        r.restrictionId.toLowerCase().includes(q) ||
        r.moduleCode.toLowerCase().includes(q) ||
        r.componentCode.toLowerCase().includes(q) ||
        (r.ulbName && r.ulbName.toLowerCase().includes(q)) ||
        r.reason.toLowerCase().includes(q);
      const matchSt = st === 'ALL' || r.stateTenantId === st;
      return matchQ && matchSt;
    });
  });

  // Paged Data based on active tab
  readonly pagedRules = computed(() => {
    const start = (this.currentPage() - 1) * this.pageSize();
    return this.filteredRules().slice(start, start + this.pageSize());
  });

  readonly pagedAllocations = computed(() => {
    const start = (this.currentPage() - 1) * this.pageSize();
    return this.filteredAllocations().slice(start, start + this.pageSize());
  });

  readonly pagedRestrictions = computed(() => {
    const start = (this.currentPage() - 1) * this.pageSize();
    return this.filteredRestrictions().slice(start, start + this.pageSize());
  });

  readonly totalItems = computed(() => {
    const tab = this.activeTab();
    if (tab === 'rules') return this.filteredRules().length;
    if (tab === 'allocations') return this.filteredAllocations().length;
    return this.filteredRestrictions().length;
  });

  readonly totalPages = computed(() => {
    return Math.max(1, Math.ceil(this.totalItems() / this.pageSize()));
  });

  readonly pagedHistory = computed(() => {
    const start = (this.histPage() - 1) * this.histPageSize();
    return this.historyLogs().slice(start, start + this.histPageSize());
  });

  readonly histTotalPages = computed(() => {
    return Math.max(1, Math.ceil(this.historyLogs().length / this.histPageSize()));
  });

  ngOnInit(): void {
    this.loadStates();
    this.refreshAll();
  }

  loadStates(): void {
    this.tenantService.getStateTenants().subscribe({
      next: (states) => {
        this.masterStates.set((states || []).filter((s: StateTenant) => s.status === 'Active'));
      },
      error: () => this.masterStates.set([])
    });
  }

  refreshAll(): void {
    this.isLoading.set(true);
    this.loadStats();
    this.loadRules();
    this.loadAllocations();
    this.loadRestrictions();
    this.loadHistory();
    setTimeout(() => this.isLoading.set(false), 500);
  }

  loadStats(): void {
    this.delegationService.getStats().subscribe({
      next: (res) => {
        if (res.success && res.data) {
          this.stats.set(res.data);
        }
      }
    });
  }

  loadRules(): void {
    this.delegationService.getRules().subscribe({
      next: (res) => {
        if (res.success && res.data) {
          this.rules.set(res.data);
        }
      }
    });
  }

  loadAllocations(): void {
    this.delegationService.getAllocations().subscribe({
      next: (res) => {
        if (res.success && res.data) {
          this.allocations.set(res.data);
        }
      }
    });
  }

  loadRestrictions(): void {
    this.delegationService.getRestrictions().subscribe({
      next: (res) => {
        if (res.success && res.data) {
          this.restrictions.set(res.data);
        }
      }
    });
  }

  loadHistory(): void {
    this.delegationService.getHistory().subscribe({
      next: (res) => {
        if (res.success && res.data) {
          this.historyLogs.set(res.data);
        }
      }
    });
  }

  setTab(tab: 'rules' | 'allocations' | 'restrictions'): void {
    this.activeTab.set(tab);
    this.currentPage.set(1);
  }

  // Pagination Controls
  onPageChange(page: number): void {
    if (page >= 1 && page <= this.totalPages()) {
      this.currentPage.set(page);
    }
  }

  onPageSizeChange(newSize: number): void {
    this.pageSize.set(newSize);
    this.currentPage.set(1);
  }

  onHistPageChange(page: number): void {
    if (page >= 1 && page <= this.histTotalPages()) {
      this.histPage.set(page);
    }
  }

  // Modals
  openRuleDialog(): void {
    this.isRuleDialogOpen.set(true);
  }

  closeRuleDialog(): void {
    this.isRuleDialogOpen.set(false);
  }

  onRuleSaved(): void {
    this.closeRuleDialog();
    this.refreshAll();
  }

  openAllocDialog(): void {
    this.isAllocDialogOpen.set(true);
  }

  closeAllocDialog(): void {
    this.isAllocDialogOpen.set(false);
  }

  onAllocSaved(): void {
    this.closeAllocDialog();
    this.refreshAll();
  }

  openRestrictDialog(): void {
    this.isRestrictDialogOpen.set(true);
  }

  closeRestrictDialog(): void {
    this.isRestrictDialogOpen.set(false);
  }

  onRestrictSaved(): void {
    this.closeRestrictDialog();
    this.refreshAll();
  }

  openVerifyDialog(): void {
    this.isVerifyDialogOpen.set(true);
  }

  closeVerifyDialog(): void {
    this.isVerifyDialogOpen.set(false);
  }

  openHistoryModal(): void {
    this.isHistoryOpen.set(true);
  }

  closeHistoryModal(): void {
    this.isHistoryOpen.set(false);
  }

  // Revoke Allocation Custom Modal
  openRevokeAllocModal(alloc: UlbAllocation): void {
    this.allocToRevoke.set(alloc);
    this.revokeReason = '';
    this.isRevokeAllocOpen.set(true);
  }

  closeRevokeAllocModal(): void {
    this.allocToRevoke.set(null);
    this.isRevokeAllocOpen.set(false);
  }

  confirmRevokeAlloc(): void {
    const alloc = this.allocToRevoke();
    if (!alloc || !this.revokeReason.trim() || this.revokeReason.trim().length < 5) return;

    this.loading.show(`Revoking allocation ${alloc.allocationId}...`);
    this.delegationService.revokeAllocation(alloc.allocationId, this.revokeReason.trim()).subscribe({
      next: (res) => {
        this.loading.hide();
        this.closeRevokeAllocModal();
        if (res.success) {
          this.dialogs.showToast(res.message || 'Allocation revoked', 'warning');
          this.refreshAll();
        } else {
          this.dialogs.showToast(res.message || 'Failed to revoke allocation', 'error');
        }
      },
      error: (err) => {
        this.loading.hide();
        this.closeRevokeAllocModal();
        this.dialogs.showToast(err.error?.detail || err.error?.message || 'Failed to revoke allocation', 'error');
      }
    });
  }

  // Delete Restriction
  deleteRestriction(r: ComponentRestriction): void {
    this.loading.show(`Lifting restriction on ${r.componentCode}...`);
    this.delegationService.deleteRestriction(r.id).subscribe({
      next: (res) => {
        this.loading.hide();
        if (res.success) {
          this.dialogs.showToast(res.message || 'Restriction removed', 'info');
          this.refreshAll();
        }
      },
      error: (err) => {
        this.loading.hide();
        this.dialogs.showToast(err.error?.detail || 'Failed to remove restriction', 'error');
      }
    });
  }

  copyText(val: string, label: string): void {
    navigator.clipboard.writeText(val).then(() => {
      this.dialogs.showToast(`${label} copied to clipboard`, 'info', 1800);
    });
  }
}
