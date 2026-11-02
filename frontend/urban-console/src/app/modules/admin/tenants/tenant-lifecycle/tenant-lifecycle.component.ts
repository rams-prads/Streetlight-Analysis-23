import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../shared/components/icon/icon.component';
import { TenantLifecycleService } from '../../../../core/services/tenant-lifecycle.service';
import { TenantManagementService } from '../../../../core/services/tenant-management.service';
import { DialogService } from '../../../../core/services/dialog.service';
import { LoadingService } from '../../../../core/services/loading.service';
import { StateTenant } from '../../../../core/models/state-tenant.model';
import {
  TenantDirectoryItem,
  TenantLifecycleEventItem,
} from '../../../../core/models/tenant-lifecycle.model';
import { StatusChangeDialogComponent } from './dialogs/status-change-dialog/status-change-dialog.component';
import { MaintenanceModeDialogComponent } from './dialogs/maintenance-mode-dialog/maintenance-mode-dialog.component';
import { ArchiveTenantDialogComponent } from './dialogs/archive-tenant-dialog/archive-tenant-dialog.component';

@Component({
  selector: 'app-tenant-lifecycle',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    IconComponent,
    StatusChangeDialogComponent,
    MaintenanceModeDialogComponent,
    ArchiveTenantDialogComponent
  ],
  templateUrl: './tenant-lifecycle.component.html',
  styleUrl: './tenant-lifecycle.component.scss'
})
export class TenantLifecycleComponent implements OnInit {
  private lifecycleService = inject(TenantLifecycleService);
  private tenantService = inject(TenantManagementService);
  private dialogs = inject(DialogService);
  private loading = inject(LoadingService);

  readonly isAuditHistoryOpen = signal<boolean>(false);

  // Master Data
  readonly masterStates = signal<StateTenant[]>([]);
  readonly directoryItems = signal<TenantDirectoryItem[]>([]);
  readonly suspensionLogs = signal<TenantLifecycleEventItem[]>([]);
  readonly isLoading = signal<boolean>(false);

  // Directory Filters
  readonly searchQuery = signal<string>('');
  readonly selectedLevelFilter = signal<string>('ALL');
  readonly selectedParentStateFilter = signal<string>('ALL');
  readonly selectedTypeFilter = signal<string>('ALL');
  readonly selectedStatusFilter = signal<string>('ALL');

  // Suspension History Filters
  readonly suspensionTenantFilter = signal<string>('ALL');
  readonly suspensionTypeFilter = signal<string>('ALL');

  // Pagination - Directory
  readonly currentPage = signal<number>(1);
  readonly pageSize = signal<number>(10);
  readonly pageSizeOptions = [5, 10, 20, 50];

  // Pagination - Suspensions
  readonly suspPage = signal<number>(1);
  readonly suspPageSize = signal<number>(10);

  // Dialog State
  readonly isStatusDialogOpen = signal<boolean>(false);
  readonly selectedTenantForStatus = signal<TenantDirectoryItem | null>(null);

  readonly isMaintenanceDialogOpen = signal<boolean>(false);
  readonly selectedTenantForMaintenance = signal<TenantDirectoryItem | null>(null);

  readonly isArchiveDialogOpen = signal<boolean>(false);
  readonly selectedTenantForArchive = signal<TenantDirectoryItem | null>(null);

  // Filtered Directory Items
  readonly filteredDirectory = computed(() => {
    const q = this.searchQuery().toLowerCase().trim();
    const lvl = this.selectedLevelFilter();
    const st = this.selectedParentStateFilter();
    const typ = this.selectedTypeFilter();
    const stat = this.selectedStatusFilter();

    return this.directoryItems().filter(item => {
      const matchQ =
        !q ||
        item.name.toLowerCase().includes(q) ||
        item.code.toLowerCase().includes(q) ||
        item.tenantId.toLowerCase().includes(q);

      const matchLvl = lvl === 'ALL' || item.tenantLevel === lvl;
      const matchSt =
        st === 'ALL' ||
        item.parentStateTenantId === st ||
        item.parentStateName === st ||
        item.code === st;
      const matchTyp = typ === 'ALL' || item.tenantType === typ;
      const matchStat = stat === 'ALL' || item.currentStatus === stat;

      return matchQ && matchLvl && matchSt && matchTyp && matchStat;
    });
  });

  // KPI Metrics
  readonly activeCount = computed(() => this.directoryItems().filter(t => t.currentStatus === 'Active').length);
  readonly maintenanceCount = computed(() => this.directoryItems().filter(t => t.isMaintenanceActive || t.currentStatus === 'Maintenance').length);
  readonly suspendedCount = computed(() => this.directoryItems().filter(t => t.currentStatus === 'Suspended' || t.currentStatus === 'Locked').length);
  readonly archivedCount = computed(() => this.directoryItems().filter(t => t.currentStatus === 'Archived').length);

  // Paginated Directory Slice
  readonly paginatedDirectory = computed(() => {
    const list = this.filteredDirectory();
    const start = (this.currentPage() - 1) * this.pageSize();
    return list.slice(start, start + this.pageSize());
  });

  readonly totalPages = computed(() => {
    const total = Math.ceil(this.filteredDirectory().length / this.pageSize());
    return total > 0 ? total : 1;
  });

  readonly startIndex = computed(() => {
    if (this.filteredDirectory().length === 0) return 0;
    return (this.currentPage() - 1) * this.pageSize() + 1;
  });

  readonly endIndex = computed(() => {
    const end = this.currentPage() * this.pageSize();
    return Math.min(end, this.filteredDirectory().length);
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

  // Paginated Suspensions Slice
  readonly filteredSuspensions = computed(() => {
    const tId = this.suspensionTenantFilter();
    const sType = this.suspensionTypeFilter();

    return this.suspensionLogs().filter(log => {
      const matchT = tId === 'ALL' || log.tenantId === tId;
      const matchType = sType === 'ALL' || log.eventType === sType;
      return matchT && matchType;
    });
  });

  readonly paginatedSuspensions = computed(() => {
    const list = this.filteredSuspensions();
    const start = (this.suspPage() - 1) * this.suspPageSize();
    return list.slice(start, start + this.suspPageSize());
  });

  readonly suspTotalPages = computed(() => {
    const total = Math.ceil(this.filteredSuspensions().length / this.suspPageSize());
    return total > 0 ? total : 1;
  });

  ngOnInit(): void {
    this.loadMasterStates();
    this.loadDirectory();
    this.loadSuspensionHistory();
  }

  loadMasterStates(): void {
    this.tenantService.getStateTenants().subscribe({
      next: (states) => this.masterStates.set(states || []),
      error: () => this.masterStates.set([])
    });
  }

  loadDirectory(): void {
    this.isLoading.set(true);
    this.lifecycleService.getDirectory().subscribe({
      next: (res) => {
        this.isLoading.set(false);
        if (res.success && res.data) {
          this.directoryItems.set(res.data);
        }
      },
      error: () => {
        this.isLoading.set(false);
        this.dialogs.showToast('Failed to load tenant lifecycle directory', 'error');
      }
    });
  }

  loadSuspensionHistory(): void {
    this.lifecycleService.getSuspensions().subscribe({
      next: (res) => {
        if (res.success && res.data) {
          this.suspensionLogs.set(res.data);
        }
      },
      error: () => this.suspensionLogs.set([])
    });
  }

  // Filter handlers with mandatory page reset
  onSearchChange(val: string): void {
    this.searchQuery.set(val);
    this.currentPage.set(1);
  }

  onLevelFilterChange(val: string): void {
    this.selectedLevelFilter.set(val);
    this.currentPage.set(1);
  }

  onParentStateFilterChange(val: string): void {
    this.selectedParentStateFilter.set(val);
    this.currentPage.set(1);
  }

  onTypeFilterChange(val: string): void {
    this.selectedTypeFilter.set(val);
    this.currentPage.set(1);
  }

  onStatusFilterChange(val: string): void {
    this.selectedStatusFilter.set(val);
    this.currentPage.set(1);
  }

  clearFilters(): void {
    this.searchQuery.set('');
    this.selectedLevelFilter.set('ALL');
    this.selectedParentStateFilter.set('ALL');
    this.selectedTypeFilter.set('ALL');
    this.selectedStatusFilter.set('ALL');
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

  // Suspension Pagination
  prevSuspPage(): void {
    if (this.suspPage() > 1) {
      this.suspPage.update(p => p - 1);
    }
  }

  nextSuspPage(): void {
    if (this.suspPage() < this.suspTotalPages()) {
      this.suspPage.update(p => p + 1);
    }
  }

  // Dialog Openers
  openStatusDialog(tenant?: TenantDirectoryItem): void {
    this.selectedTenantForStatus.set(tenant || null);
    this.isStatusDialogOpen.set(true);
  }

  closeStatusDialog(): void {
    this.isStatusDialogOpen.set(false);
    this.selectedTenantForStatus.set(null);
  }

  onStatusSaved(): void {
    this.closeStatusDialog();
    this.loadDirectory();
    this.loadSuspensionHistory();
  }

  openMaintenanceDialog(tenant: TenantDirectoryItem): void {
    this.selectedTenantForMaintenance.set(tenant);
    this.isMaintenanceDialogOpen.set(true);
  }

  closeMaintenanceDialog(): void {
    this.isMaintenanceDialogOpen.set(false);
    this.selectedTenantForMaintenance.set(null);
  }

  onMaintenanceSaved(): void {
    this.closeMaintenanceDialog();
    this.loadDirectory();
    this.loadSuspensionHistory();
  }

  openArchiveDialog(tenant: TenantDirectoryItem): void {
    this.selectedTenantForArchive.set(tenant);
    this.isArchiveDialogOpen.set(true);
  }

  closeArchiveDialog(): void {
    this.isArchiveDialogOpen.set(false);
    this.selectedTenantForArchive.set(null);
  }

  onArchiveSaved(): void {
    this.closeArchiveDialog();
    this.loadDirectory();
    this.loadSuspensionHistory();
  }

  openAuditHistory(): void {
    this.isAuditHistoryOpen.set(true);
  }

  closeAuditHistory(): void {
    this.isAuditHistoryOpen.set(false);
  }

  copyTenantId(id: string): void {
    navigator.clipboard.writeText(id).then(() => {
      this.dialogs.showToast(`Tenant ID '${id}' copied to clipboard`, 'info', 1800);
    });
  }
}
