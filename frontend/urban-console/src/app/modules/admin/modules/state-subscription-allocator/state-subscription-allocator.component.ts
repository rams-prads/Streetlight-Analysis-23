import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../shared/components/icon/icon.component';
import { SubscriptionService } from '../../../../core/services/subscription.service';
import { TenantManagementService } from '../../../../core/services/tenant-management.service';
import { DialogService } from '../../../../core/services/dialog.service';
import { LoadingService } from '../../../../core/services/loading.service';
import { StateTenant } from '../../../../core/models/state-tenant.model';
import {
  StateSubscription,
  StateSubscriptionHistoryItem,
  StateSubscriptionStats,
} from '../../../../core/models/subscription.model';
import { AssignModulesDialogComponent } from './dialogs/assign-modules-dialog/assign-modules-dialog.component';
import { RenewalExpiryDialogComponent } from './dialogs/renewal-expiry-dialog/renewal-expiry-dialog.component';
import { RevokeSubscriptionDialogComponent } from './dialogs/revoke-subscription-dialog/revoke-subscription-dialog.component';

@Component({
  selector: 'app-state-subscription-allocator',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    IconComponent,
    AssignModulesDialogComponent,
    RenewalExpiryDialogComponent,
    RevokeSubscriptionDialogComponent
  ],
  templateUrl: './state-subscription-allocator.component.html',
  styleUrl: './state-subscription-allocator.component.scss'
})
export class StateSubscriptionAllocatorComponent implements OnInit {
  private subscriptionService = inject(SubscriptionService);
  private tenantService = inject(TenantManagementService);
  private dialogs = inject(DialogService);
  private loading = inject(LoadingService);

  readonly subscriptions = signal<StateSubscription[]>([]);
  readonly masterStates = signal<StateTenant[]>([]);
  readonly stats = signal<StateSubscriptionStats | null>(null);
  readonly historyLogs = signal<StateSubscriptionHistoryItem[]>([]);
  readonly isLoading = signal<boolean>(false);

  // Filters
  readonly searchQuery = signal<string>('');
  readonly selectedStateFilter = signal<string>('ALL');
  readonly selectedStatusFilter = signal<string>('ALL');
  readonly selectedTypeFilter = signal<string>('ALL');

  // Pagination - Directory
  readonly currentPage = signal<number>(1);
  readonly pageSize = signal<number>(10);
  readonly pageSizeOptions = [5, 10, 20, 50];

  // Pagination - History Modal
  readonly isHistoryOpen = signal<boolean>(false);
  readonly histPage = signal<number>(1);
  readonly histPageSize = signal<number>(10);

  // Dialog Controls
  readonly isAssignDialogOpen = signal<boolean>(false);
  readonly preselectedStateIdForAssign = signal<string>('');
  readonly isRenewalDialogOpen = signal<boolean>(false);
  readonly selectedSubForRenewal = signal<StateSubscription | null>(null);
  readonly isRevokeDialogOpen = signal<boolean>(false);
  readonly selectedSubForRevoke = signal<StateSubscription | null>(null);

  // Filtered List
  readonly filteredSubscriptions = computed(() => {
    const q = this.searchQuery().toLowerCase().trim();
    const st = this.selectedStateFilter();
    const stat = this.selectedStatusFilter();
    const typ = this.selectedTypeFilter();

    return this.subscriptions().filter(sub => {
      const matchQ =
        !q ||
        sub.subscriptionId.toLowerCase().includes(q) ||
        sub.subscriptionName.toLowerCase().includes(q) ||
        (sub.stateName && sub.stateName.toLowerCase().includes(q)) ||
        (sub.stateCode && sub.stateCode.toLowerCase().includes(q));

      const matchState = st === 'ALL' || sub.stateTenantId === st;
      const matchStat = stat === 'ALL' || sub.status === stat;
      const matchTyp = typ === 'ALL' || sub.subscriptionType === typ;

      return matchQ && matchState && matchStat && matchTyp;
    });
  });

  // Paginated Slice
  readonly paginatedSubscriptions = computed(() => {
    const list = this.filteredSubscriptions();
    const start = (this.currentPage() - 1) * this.pageSize();
    return list.slice(start, start + this.pageSize());
  });

  readonly totalPages = computed(() => {
    const total = Math.ceil(this.filteredSubscriptions().length / this.pageSize());
    return total > 0 ? total : 1;
  });

  readonly startIndex = computed(() => {
    if (this.filteredSubscriptions().length === 0) return 0;
    return (this.currentPage() - 1) * this.pageSize() + 1;
  });

  readonly endIndex = computed(() => {
    const end = this.currentPage() * this.pageSize();
    return Math.min(end, this.filteredSubscriptions().length);
  });

  readonly pagesArray = computed(() => {
    const pages: number[] = [];
    const total = this.totalPages();
    const curr = this.currentPage();
    let start = Math.max(1, curr - 2);
    let end = Math.min(total, start + 4);
    if (end - start < 4) {
      start = Math.max(1, end - 4);
    }
    for (let i = start; i <= end; i++) {
      pages.push(i);
    }
    return pages;
  });

  // Paginated History
  readonly paginatedHistory = computed(() => {
    const list = this.historyLogs();
    const start = (this.histPage() - 1) * this.histPageSize();
    return list.slice(start, start + this.histPageSize());
  });

  readonly histTotalPages = computed(() => {
    const total = Math.ceil(this.historyLogs().length / this.histPageSize());
    return total > 0 ? total : 1;
  });

  ngOnInit(): void {
    this.loadMasterStates();
    this.loadSubscriptions();
    this.loadStats();
    this.loadHistory();
  }

  loadMasterStates(): void {
    this.tenantService.getStateTenants().subscribe({
      next: (states) => this.masterStates.set(states || []),
      error: () => this.masterStates.set([])
    });
  }

  loadSubscriptions(): void {
    this.isLoading.set(true);
    this.subscriptionService.getSubscriptions().subscribe({
      next: (res) => {
        this.isLoading.set(false);
        if (res.success && res.data) {
          this.subscriptions.set(res.data);
        }
      },
      error: () => {
        this.isLoading.set(false);
        this.dialogs.showToast('Failed to load state module subscriptions', 'error');
      }
    });
  }

  loadStats(): void {
    this.subscriptionService.getStats().subscribe({
      next: (res) => {
        if (res.success && res.data) {
          this.stats.set(res.data);
        }
      },
      error: () => this.stats.set(null)
    });
  }

  loadHistory(): void {
    this.subscriptionService.getHistory().subscribe({
      next: (res) => {
        if (res.success && res.data) {
          this.historyLogs.set(res.data);
        }
      },
      error: () => this.historyLogs.set([])
    });
  }

  // Filter handlers
  onSearchChange(val: string): void {
    this.searchQuery.set(val);
    this.currentPage.set(1);
  }

  onStateFilterChange(val: string): void {
    this.selectedStateFilter.set(val);
    this.currentPage.set(1);
  }

  onStatusFilterChange(val: string): void {
    this.selectedStatusFilter.set(val);
    this.currentPage.set(1);
  }

  onTypeFilterChange(val: string): void {
    this.selectedTypeFilter.set(val);
    this.currentPage.set(1);
  }

  clearFilters(): void {
    this.searchQuery.set('');
    this.selectedStateFilter.set('ALL');
    this.selectedStatusFilter.set('ALL');
    this.selectedTypeFilter.set('ALL');
    this.currentPage.set(1);
  }

  // Directory Pagination controls
  prevPage(): void {
    if (this.currentPage() > 1) {
      this.currentPage.update(p => p - 1);
    }
  }

  nextPage(): void {
    if (this.currentPage() < this.totalPages()) {
      this.currentPage.update(p => p + 1);
    }
  }

  goToPage(page: number): void {
    if (page >= 1 && page <= this.totalPages()) {
      this.currentPage.set(page);
    }
  }

  onPageSizeChange(size: number): void {
    this.pageSize.set(Number(size));
    this.currentPage.set(1);
  }

  // History Pagination
  prevHistPage(): void {
    if (this.histPage() > 1) {
      this.histPage.update(p => p - 1);
    }
  }

  nextHistPage(): void {
    if (this.histPage() < this.histTotalPages()) {
      this.histPage.update(p => p + 1);
    }
  }

  // Dialog Controls
  openAssignDialog(stateId?: string): void {
    this.preselectedStateIdForAssign.set(stateId || '');
    this.isAssignDialogOpen.set(true);
  }

  closeAssignDialog(): void {
    this.isAssignDialogOpen.set(false);
    this.preselectedStateIdForAssign.set('');
  }

  onAssignSaved(): void {
    this.closeAssignDialog();
    this.loadSubscriptions();
    this.loadStats();
    this.loadHistory();
  }

  openRenewalDialog(sub: StateSubscription): void {
    this.selectedSubForRenewal.set(sub);
    this.isRenewalDialogOpen.set(true);
  }

  closeRenewalDialog(): void {
    this.isRenewalDialogOpen.set(false);
    this.selectedSubForRenewal.set(null);
  }

  onRenewalSaved(): void {
    this.closeRenewalDialog();
    this.loadSubscriptions();
    this.loadStats();
    this.loadHistory();
  }

  revokeSubscription(sub: StateSubscription): void {
    this.openRevokeDialog(sub);
  }

  openRevokeDialog(sub: StateSubscription): void {
    this.selectedSubForRevoke.set(sub);
    this.isRevokeDialogOpen.set(true);
  }

  closeRevokeDialog(): void {
    this.selectedSubForRevoke.set(null);
    this.isRevokeDialogOpen.set(false);
  }

  onRevokeConfirmed(event: { reason: string; approvalReference?: string }): void {
    const sub = this.selectedSubForRevoke();
    if (!sub) return;

    this.loading.show(`Revoking subscription ${sub.subscriptionId}...`);
    this.subscriptionService.revokeSubscription(sub.subscriptionId, event.reason, event.approvalReference).subscribe({
      next: (res) => {
        this.loading.hide();
        this.closeRevokeDialog();
        if (res.success) {
          this.dialogs.showToast(res.message || 'Subscription revoked', 'warning');
          this.loadSubscriptions();
          this.loadStats();
          this.loadHistory();
        } else {
          this.dialogs.showToast(res.message || 'Failed to revoke subscription', 'error');
        }
      },
      error: (err) => {
        this.loading.hide();
        this.closeRevokeDialog();
        this.dialogs.showToast(err.error?.detail || 'Failed to revoke subscription', 'error');
      }
    });
  }

  openHistoryModal(): void {
    this.isHistoryOpen.set(true);
  }

  closeHistoryModal(): void {
    this.isHistoryOpen.set(false);
  }

  copySubscriptionId(id: string): void {
    navigator.clipboard.writeText(id).then(() => {
      this.dialogs.showToast(`Subscription ID '${id}' copied to clipboard`, 'info', 1800);
    });
  }

  isExpiringSoon(endDateStr?: string | null): boolean {
    if (!endDateStr) return false;
    const end = new Date(endDateStr).getTime();
    const now = new Date().getTime();
    const diffDays = (end - now) / (1000 * 3600 * 24);
    return diffDays > 0 && diffDays <= 30;
  }
}
