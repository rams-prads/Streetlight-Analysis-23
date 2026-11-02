import { Component, OnInit, inject, signal, computed, HostListener } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';
import { IconComponent } from '../../../shared/components/icon/icon.component';
import { StateTenantFormDialogComponent } from './dialogs/state-tenant-form-dialog/state-tenant-form-dialog.component';
import { DialogService } from '../../../core/services/dialog.service';
import { KeycloakAuthService } from '../../../core/services/keycloak.service';
import { TenantManagementService } from '../../../core/services/tenant-management.service';
import { LoadingService } from '../../../core/services/loading.service';
import {
  StateTenant,
  TenantAuditLog,
  MasterState,
} from '../../../core/models/state-tenant.model';

export type TenantTab = 'directory' | 'create' | 'audit';

@Component({
  selector: 'app-tenant-management',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent, StateTenantFormDialogComponent],
  templateUrl: './tenant-management.component.html',
  styleUrl: './tenant-management.component.scss',
})
export class TenantManagementComponent implements OnInit {
  private tenantService = inject(TenantManagementService);
  private dialogs = inject(DialogService);
  public authService = inject(KeycloakAuthService);
  public loadingService = inject(LoadingService);

  readonly activeTab = signal<TenantTab>('directory');
  readonly isDialogOpen = signal<boolean>(false);
  readonly isLoading = signal<boolean>(false);
  readonly isEditing = signal<boolean>(false);
  readonly masterStates = signal<MasterState[]>([]);
  readonly tenants = signal<StateTenant[]>([]);
  readonly auditLogs = signal<TenantAuditLog[]>([]);
  readonly selectedTenant = signal<StateTenant | null>(null);

  // Search & Filters
  readonly searchQuery = signal<string>('');
  readonly selectedStateFilter = signal<string>('ALL');
  readonly selectedStatusFilter = signal<string>('ALL');

  readonly hasActiveFilters = computed(() => {
    return (
      this.selectedStateFilter() !== 'ALL' ||
      this.selectedStatusFilter() !== 'ALL' ||
      this.searchQuery().trim().length > 0
    );
  });

  // Pagination
  readonly currentPage = signal<number>(1);
  readonly pageSize = signal<number>(5);
  readonly pageSizeOptions = [5, 10, 20, 50];

  // Computed Filtered List
  readonly filteredTenants = computed(() => {
    const q = this.searchQuery().toLowerCase().trim();
    const stateFilter = this.selectedStateFilter();
    const statusFilter = this.selectedStatusFilter();

    return this.tenants().filter((t) => {
      const matchSearch =
        !q ||
        t.stateName.toLowerCase().includes(q) ||
        t.stateCode.toLowerCase().includes(q) ||
        t.tenantSlug.toLowerCase().includes(q) ||
        t.administrativeEmail.toLowerCase().includes(q) ||
        (t.officialStateName && t.officialStateName.toLowerCase().includes(q));

      const matchState = stateFilter === 'ALL' || t.stateCode === stateFilter;
      const matchStatus =
        statusFilter === 'ALL' || t.status.toLowerCase() === statusFilter.toLowerCase();

      return matchSearch && matchState && matchStatus;
    });
  });

  // Pagination Computations
  readonly totalPages = computed(() =>
    Math.max(1, Math.ceil(this.filteredTenants().length / this.pageSize())),
  );

  readonly paginatedTenants = computed(() => {
    const start = (this.currentPage() - 1) * this.pageSize();
    return this.filteredTenants().slice(start, start + this.pageSize());
  });

  readonly startIndex = computed(() =>
    this.filteredTenants().length === 0 ? 0 : (this.currentPage() - 1) * this.pageSize() + 1,
  );

  readonly endIndex = computed(() =>
    Math.min(this.currentPage() * this.pageSize(), this.filteredTenants().length),
  );

  readonly pagesArray = computed(() => {
    const total = this.totalPages();
    const current = this.currentPage();
    const pages: number[] = [];
    const maxVisible = 5;

    let start = Math.max(1, current - 2);
    let end = Math.min(total, start + maxVisible - 1);

    if (end - start + 1 < maxVisible) {
      start = Math.max(1, end - maxVisible + 1);
    }

    for (let i = start; i <= end; i++) {
      pages.push(i);
    }
    return pages;
  });

  ngOnInit(): void {
    this.loadMasterStates();
    this.loadTenants();
    this.loadAuditLogs();
  }

  loadMasterStates(): void {
    this.tenantService.getMasterStates().subscribe({
      next: (states) => this.masterStates.set(states),
      error: () => {
        this.masterStates.set([]);
        this.dialogs.showToast('Failed to load master states reference.', 'error', 3000);
      },
    });
  }

  loadTenants(showToast = false): void {
    this.isLoading.set(true);
    this.tenantService
      .getStateTenants()
      .pipe(
        finalize(() => {
          this.isLoading.set(false);
          this.loadingService.hide();
        })
      )
      .subscribe({
        next: (data) => {
          this.tenants.set(data || []);
          if (showToast) {
            this.dialogs.showToast('Tenants list refreshed successfully.', 'success', 2500);
          }
        },
        error: () => {
          if (showToast) {
            this.dialogs.showToast('Failed to refresh tenants list.', 'error', 3000);
          }
        },
      });
  }

  onRefreshClick(): void {
    this.loadingService.setMessage('Refreshing tenants list...');
    this.loadTenants(true);
  }

  clearAllFilters(): void {
    this.searchQuery.set('');
    this.selectedStateFilter.set('ALL');
    this.selectedStatusFilter.set('ALL');
    this.currentPage.set(1);
    this.dialogs.showToast('All filters cleared.', 'info', 2000);
  }

  loadAuditLogs(): void {
    this.tenantService.getAuditLogs().subscribe({
      next: (logs) => this.auditLogs.set(logs),
      error: () => {},
    });
  }

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

  goToPage(page: number): void {
    if (page >= 1 && page <= this.totalPages()) {
      this.currentPage.set(page);
    }
  }

  nextPage(): void {
    if (this.currentPage() < this.totalPages()) {
      this.currentPage.set(this.currentPage() + 1);
    }
  }

  prevPage(): void {
    if (this.currentPage() > 1) {
      this.currentPage.set(this.currentPage() - 1);
    }
  }

  onPageSizeChange(newSize: number): void {
    this.pageSize.set(Number(newSize));
    this.currentPage.set(1);
  }

  openCreateTab(): void {
    this.isEditing.set(false);
    this.selectedTenant.set(null);
    this.isDialogOpen.set(true);
  }

  editTenant(tenant: StateTenant): void {
    this.isEditing.set(true);
    this.selectedTenant.set(tenant);
    this.isDialogOpen.set(true);
  }

  closeDialog(): void {
    this.isDialogOpen.set(false);
    this.selectedTenant.set(null);
    if (this.activeTab() === 'create') {
      this.activeTab.set('directory');
    }
  }

  onTenantSaved(savedTenant: StateTenant): void {
    this.loadTenants();
    this.loadAuditLogs();
    this.closeDialog();
  }

  @HostListener('document:keydown.escape')
  onEscapePress(): void {
    if (this.isDialogOpen()) {
      this.closeDialog();
    }
  }

  async deleteTenant(tenant: StateTenant): Promise<void> {
    const confirmed = await this.dialogs.confirm({
      title: `Delete State Tenant: ${tenant.stateName}`,
      message: `Are you sure you want to permanently delete Level 1 Tenant ${tenant.stateName} (${tenant.stateCode})? This will remove its jurisdiction and isolation boundaries.`,
      confirmText: 'Delete Permanently',
      cancelText: 'Cancel',
      variant: 'destructive',
    });

    if (confirmed) {
      this.tenantService.deleteStateTenant(tenant.tenantId).subscribe({
        next: () => {
          this.dialogs.showToast(
            `State Tenant '${tenant.stateName}' deleted successfully.`,
            'success',
            3000,
          );
          this.loadTenants();
          this.loadAuditLogs();
        },
        error: (err) => {
          this.dialogs.showToast(err.error?.detail || 'Failed to delete tenant.', 'error', 3000);
        },
      });
    }
  }

  copyTenantId(tenantId: string): void {
    navigator.clipboard?.writeText(tenantId);
    this.dialogs.showToast(`Tenant ID copied to clipboard.`, 'info', 1800);
  }

  setTab(tab: TenantTab): void {
    this.activeTab.set(tab);
    if (tab === 'create' && !this.isEditing()) {
      this.openCreateTab();
    }
  }

  async activateTenant(tenant: StateTenant): Promise<void> {
    const confirmed = await this.dialogs.confirm({
      title: `Activate State Tenant: ${tenant.stateName}`,
      message: `Authorize Level 1 activation for ${tenant.stateName} (${tenant.stateCode})?`,
      confirmText: 'Activate State Tenant',
      cancelText: 'Cancel',
      variant: 'primary',
    });

    if (confirmed) {
      this.tenantService.activateStateTenant(tenant.tenantId).subscribe({
        next: () => {
          this.dialogs.showToast(
            `State Tenant ${tenant.stateName} is now ACTIVE.`,
            'success',
            3000,
          );
          this.loadTenants();
          this.loadAuditLogs();
        },
        error: (err) => {
          this.dialogs.showToast(err.error?.detail || 'Failed to activate tenant.', 'error', 3000);
        },
      });
    }
  }

  async suspendTenant(tenant: StateTenant): Promise<void> {
    const confirmed = await this.dialogs.confirm({
      title: `Suspend State Tenant: ${tenant.stateName}`,
      message: `Suspend Level 1 tenant ${tenant.stateName}? Child ULBs under this state will lose write access.`,
      confirmText: 'Suspend Tenant',
      cancelText: 'Abort',
      variant: 'destructive',
    });

    if (confirmed) {
      this.tenantService.suspendStateTenant(tenant.tenantId).subscribe({
        next: () => {
          this.dialogs.showToast(
            `State Tenant ${tenant.stateName} has been SUSPENDED.`,
            'warning',
            3500,
          );
          this.loadTenants();
          this.loadAuditLogs();
        },
        error: (err) => {
          this.dialogs.showToast(err.error?.detail || 'Failed to suspend tenant.', 'error', 3000);
        },
      });
    }
  }

  viewTenantAudit(tenant: StateTenant): void {
    this.selectedTenant.set(tenant);
    this.searchQuery.set(tenant.tenantId);
    this.activeTab.set('audit');
  }
}
