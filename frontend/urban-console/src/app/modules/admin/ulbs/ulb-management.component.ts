import { Component, OnInit, inject, signal, computed, HostListener } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';
import { IconComponent } from '../../../shared/components/icon/icon.component';
import { DialogService } from '../../../core/services/dialog.service';
import { KeycloakAuthService } from '../../../core/services/keycloak.service';
import { LoadingService } from '../../../core/services/loading.service';
import { TenantManagementService } from '../../../core/services/tenant-management.service';
import { UlbManagementService } from '../../../core/services/ulb-management.service';
import { MasterState } from '../../../core/models/state-tenant.model';
import { UlbTenant } from '../../../core/models/ulb-tenant.model';
import { UlbFormDialogComponent } from './dialogs/ulb-form-dialog/ulb-form-dialog.component';
import { UlbStructureDialogComponent } from './dialogs/ulb-structure-dialog/ulb-structure-dialog.component';

@Component({
  selector: 'app-ulb-management',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    IconComponent,
    UlbFormDialogComponent,
    UlbStructureDialogComponent,
  ],
  templateUrl: './ulb-management.component.html',
  styleUrl: './ulb-management.component.scss',
})
export class UlbManagementComponent implements OnInit {
  private ulbService = inject(UlbManagementService);
  private tenantService = inject(TenantManagementService);
  private dialogs = inject(DialogService);
  public authService = inject(KeycloakAuthService);
  public loadingService = inject(LoadingService);

  // State Signals
  readonly ulbs = signal<UlbTenant[]>([]);
  readonly isLoading = signal<boolean>(false);
  readonly masterStates = signal<MasterState[]>([]);

  // Dialog Controls
  readonly isFormDialogOpen = signal<boolean>(false);
  readonly isEditing = signal<boolean>(false);
  readonly selectedUlb = signal<UlbTenant | null>(null);

  readonly isStructureDialogOpen = signal<boolean>(false);
  readonly activeUlbForStructure = signal<UlbTenant | null>(null);

  // Search & Filter Signals
  readonly searchQuery = signal<string>('');
  readonly selectedStateFilter = signal<string>('ALL');
  readonly selectedTypeFilter = signal<string>('ALL');
  readonly selectedStatusFilter = signal<string>('ALL');

  readonly hasActiveFilters = computed(() => {
    return (
      this.selectedStateFilter() !== 'ALL' ||
      this.selectedTypeFilter() !== 'ALL' ||
      this.selectedStatusFilter() !== 'ALL' ||
      this.searchQuery().trim().length > 0
    );
  });

  // Pagination
  readonly currentPage = signal<number>(1);
  readonly pageSize = signal<number>(10);
  readonly pageSizeOptions = [5, 10, 20, 50];

  readonly ulbTypeOptions = [
    'Municipal Corporation',
    'Municipality',
    'Nagar Panchayat',
    'Town Panchayat',
    'Cantonment Board',
    'Urban Development Authority',
  ];

  // Computed Filtered ULB List
  readonly filteredUlbs = computed(() => {
    const q = this.searchQuery().toLowerCase().trim();
    const stateFilter = this.selectedStateFilter();
    const typeFilter = this.selectedTypeFilter();
    const statusFilter = this.selectedStatusFilter();

    return this.ulbs().filter((u) => {
      const matchSearch =
        !q ||
        u.name.toLowerCase().includes(q) ||
        u.ulbCode.toLowerCase().includes(q) ||
        u.tenantId.toLowerCase().includes(q) ||
        (u.district && u.district.toLowerCase().includes(q)) ||
        (u.officialEmail && u.officialEmail.toLowerCase().includes(q));

      const matchState = stateFilter === 'ALL' || u.stateCode === stateFilter;
      const matchType = typeFilter === 'ALL' || u.ulbType === typeFilter;
      const matchStatus = statusFilter === 'ALL' || u.status === statusFilter;

      return matchSearch && matchState && matchType && matchStatus;
    });
  });

  // Computed Pagination
  readonly totalPages = computed(() =>
    Math.max(1, Math.ceil(this.filteredUlbs().length / this.pageSize())),
  );

  readonly paginatedUlbs = computed(() => {
    const start = (this.currentPage() - 1) * this.pageSize();
    return this.filteredUlbs().slice(start, start + this.pageSize());
  });

  readonly startIndex = computed(() => {
    if (this.filteredUlbs().length === 0) return 0;
    return (this.currentPage() - 1) * this.pageSize() + 1;
  });

  readonly endIndex = computed(() =>
    Math.min(this.currentPage() * this.pageSize(), this.filteredUlbs().length),
  );

  readonly pagesArray = computed(() => {
    const total = this.totalPages();
    const cur = this.currentPage();
    const delta = 2;
    const range: number[] = [];
    for (let i = Math.max(1, cur - delta); i <= Math.min(total, cur + delta); i++) {
      range.push(i);
    }
    return range;
  });

  ngOnInit(): void {
    this.loadMasterStates();
    this.loadUlbs();
  }

  @HostListener('document:keydown.escape', ['$event'])
  handleEscape(event: Event): void {
    if (this.isStructureDialogOpen()) {
      this.closeStructureDialog();
    } else if (this.isFormDialogOpen()) {
      this.closeFormDialog();
    }
  }

  // ---------------- Data Loading ----------------

  loadMasterStates(): void {
    this.tenantService.getMasterStates().subscribe({
      next: (states) => this.masterStates.set(states),
      error: () => {
        this.masterStates.set([]);
        this.dialogs.showToast('Failed to load master states reference.', 'error', 3000);
      },
    });
  }

  loadUlbs(): void {
    this.isLoading.set(true);
    this.ulbService
      .getUlbs()
      .pipe(finalize(() => this.isLoading.set(false)))
      .subscribe({
        next: (ulbs) => {
          this.ulbs.set(ulbs);
        },
        error: (err) => {
          this.dialogs.showToast(
            err.error?.detail || 'Unable to connect to Core Service API.',
            'error',
            3500,
          );
        },
      });
  }

  onRefreshClick(): void {
    this.loadingService.setMessage('Refreshing ULB directory...');
    this.loadingService.show();
    this.isLoading.set(true);
    this.ulbService
      .getUlbs()
      .pipe(
        finalize(() => {
          this.isLoading.set(false);
          this.loadingService.hide();
        }),
      )
      .subscribe({
        next: (ulbs) => {
          this.ulbs.set(ulbs);
          this.dialogs.showToast(
            `Refreshed ${ulbs.length} ULB records successfully.`,
            'success',
            2500,
          );
        },
        error: (err) => {
          this.dialogs.showToast(
            err.error?.detail || 'Could not fetch updated ULB records.',
            'error',
            3500,
          );
        },
      });
  }

  // ---------------- Filter & Pagination ----------------

  onSearchChange(q: string): void {
    this.searchQuery.set(q);
    this.currentPage.set(1);
  }

  onStateFilterChange(val: string): void {
    this.selectedStateFilter.set(val);
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

  clearAllFilters(): void {
    this.searchQuery.set('');
    this.selectedStateFilter.set('ALL');
    this.selectedTypeFilter.set('ALL');
    this.selectedStatusFilter.set('ALL');
    this.currentPage.set(1);
    this.dialogs.showToast('All filters cleared.', 'info', 2000);
  }

  onPageSizeChange(newSize: number): void {
    this.pageSize.set(Number(newSize));
    this.currentPage.set(1);
  }

  goToPage(p: number): void {
    if (p >= 1 && p <= this.totalPages()) {
      this.currentPage.set(p);
    }
  }

  prevPage(): void {
    if (this.currentPage() > 1) {
      this.currentPage.update((p) => p - 1);
    }
  }

  nextPage(): void {
    if (this.currentPage() < this.totalPages()) {
      this.currentPage.update((p) => p + 1);
    }
  }

  // ---------------- Form Dialog (Add/Edit) ----------------

  openCreateDialog(): void {
    this.isEditing.set(false);
    this.selectedUlb.set(null);
    this.isFormDialogOpen.set(true);
  }

  openEditDialog(ulb: UlbTenant): void {
    this.isEditing.set(true);
    this.selectedUlb.set(ulb);
    this.isFormDialogOpen.set(true);
  }

  closeFormDialog(): void {
    this.isFormDialogOpen.set(false);
    this.selectedUlb.set(null);
  }

  onUlbSaved(savedUlb: UlbTenant): void {
    this.ulbs.update((list) => {
      const exists = list.some((u) => u.tenantId === savedUlb.tenantId);
      if (exists) {
        return list.map((u) => (u.tenantId === savedUlb.tenantId ? savedUlb : u));
      }
      return [savedUlb, ...list];
    });
  }

  // ---------------- Structure Dialog (Wards & Zones) ----------------

  openWardsZonesModal(ulb: UlbTenant): void {
    this.activeUlbForStructure.set(ulb);
    this.isStructureDialogOpen.set(true);
  }

  closeStructureDialog(): void {
    this.isStructureDialogOpen.set(false);
    this.activeUlbForStructure.set(null);
  }

  onStructureCountsUpdated(event: {
    tenantId: string;
    totalZones: number;
    totalWards: number;
  }): void {
    this.ulbs.update((list) =>
      list.map((u) =>
        u.tenantId === event.tenantId
          ? { ...u, totalZones: event.totalZones, totalWards: event.totalWards }
          : u,
      ),
    );
  }

  // ---------------- Status Transitions & Actions ----------------

  async activateUlb(ulb: UlbTenant): Promise<void> {
    const confirmed = await this.dialogs.confirm({
      title: `Activate ULB: ${ulb.name}?`,
      message: `Enabling "${ulb.name}" (${ulb.ulbCode}) will allow field officers and citizens to access local portals.`,
      confirmText: 'Activate ULB',
      cancelText: 'Cancel',
      variant: 'primary',
    });

    if (confirmed) {
      this.loadingService.setMessage('Activating ULB...');
      this.loadingService.show();
      this.ulbService
        .activateUlb(ulb.tenantId)
        .pipe(finalize(() => this.loadingService.hide()))
        .subscribe({
          next: (updated) => {
            this.ulbs.update((list) =>
              list.map((u) => (u.tenantId === updated.tenantId ? updated : u)),
            );
            this.dialogs.showToast(`${ulb.name} is now Active.`, 'success', 2500);
          },
          error: (err) => {
            this.dialogs.showToast(err.error?.detail || 'Could not activate ULB.', 'error', 3500);
          },
        });
    }
  }

  async suspendUlb(ulb: UlbTenant): Promise<void> {
    const confirmed = await this.dialogs.confirm({
      title: `Suspend ULB: ${ulb.name}?`,
      message: `Suspending "${ulb.name}" will temporarily revoke API access and officer login capabilities.`,
      confirmText: 'Suspend ULB',
      cancelText: 'Cancel',
      variant: 'warning',
    });

    if (confirmed) {
      this.loadingService.setMessage('Suspending ULB...');
      this.loadingService.show();
      this.ulbService
        .suspendUlb(ulb.tenantId)
        .pipe(finalize(() => this.loadingService.hide()))
        .subscribe({
          next: (updated) => {
            this.ulbs.update((list) =>
              list.map((u) => (u.tenantId === updated.tenantId ? updated : u)),
            );
            this.dialogs.showToast(`${ulb.name} suspended.`, 'warning', 2500);
          },
          error: (err) => {
            this.dialogs.showToast(err.error?.detail || 'Could not suspend ULB.', 'error', 3500);
          },
        });
    }
  }

  async deleteUlb(ulb: UlbTenant): Promise<void> {
    const confirmed = await this.dialogs.confirm({
      title: `Delete ULB: ${ulb.name}?`,
      message: `Are you sure you want to permanently remove "${ulb.name}" (${ulb.ulbCode})? This action cannot be undone and will delete child zones and wards.`,
      confirmText: 'Delete Permanently',
      cancelText: 'Cancel',
      variant: 'destructive',
    });

    if (confirmed) {
      this.loadingService.setMessage('Deleting ULB...');
      this.loadingService.show();
      this.ulbService
        .deleteUlb(ulb.tenantId)
        .pipe(finalize(() => this.loadingService.hide()))
        .subscribe({
          next: () => {
            this.ulbs.update((list) => list.filter((u) => u.tenantId !== ulb.tenantId));
            this.dialogs.showToast(`Deleted ${ulb.name} successfully.`, 'info', 2500);
          },
          error: (err) => {
            this.dialogs.showToast(err.error?.detail || 'Could not delete ULB.', 'error', 3500);
          },
        });
    }
  }
}
