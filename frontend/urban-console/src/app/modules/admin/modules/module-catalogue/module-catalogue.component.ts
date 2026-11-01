import { Component, OnInit, inject, signal, computed, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';
import { IconComponent } from '../../../../shared/components/icon/icon.component';
import { DialogService } from '../../../../core/services/dialog.service';
import { LoadingService } from '../../../../core/services/loading.service';
import { ModuleCatalogueService } from '../../../../core/services/module-catalogue.service';
import { ModuleCatalogueItem } from '../../../../core/models/module-catalogue.model';
import { ModuleFormDialogComponent } from './dialogs/module-form-dialog/module-form-dialog.component';
import { CatalogueHistoryDialogComponent } from './dialogs/catalogue-history-dialog/catalogue-history-dialog.component';

@Component({
  selector: 'app-module-catalogue',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    IconComponent,
    ModuleFormDialogComponent,
    CatalogueHistoryDialogComponent
  ],
  templateUrl: './module-catalogue.component.html',
  styleUrl: './module-catalogue.component.scss'
})
export class ModuleCatalogueComponent implements OnInit {
  private catalogueService = inject(ModuleCatalogueService);
  private dialogs = inject(DialogService);
  public loadingService = inject(LoadingService);

  @Output() viewComponents = new EventEmitter<string>();

  readonly isLoading = signal(false);

  // Data signals
  readonly modules = signal<ModuleCatalogueItem[]>([]);

  // Dialog signals
  readonly isModuleDialogOpen = signal(false);
  readonly isEditingModule = signal(false);
  readonly selectedModule = signal<ModuleCatalogueItem | null>(null);

  readonly isHistoryDialogOpen = signal(false);
  readonly historyEntityCode = signal<string>('');

  // Filters
  readonly searchQuery = signal<string>('');
  readonly selectedCategoryFilter = signal<string>('ALL');
  readonly selectedStatusFilter = signal<string>('ALL');

  readonly categoryOptions = [
    'Revenue & Billing',
    'Finance & Administration',
    'Planning & Regulation',
    'Infrastructure & Field Operations',
    'Citizen Engagement & Welfare'
  ];

  // Pagination
  readonly currentPage = signal<number>(1);
  readonly pageSize = signal<number>(10);
  readonly pageSizeOptions = [5, 10, 20, 50];

  // Filtered Modules
  readonly filteredModules = computed(() => {
    const q = this.searchQuery().toLowerCase().trim();
    const cat = this.selectedCategoryFilter();
    const st = this.selectedStatusFilter();

    return this.modules().filter(m => {
      const matchQ =
        !q ||
        m.name.toLowerCase().includes(q) ||
        m.code.toLowerCase().includes(q) ||
        m.description.toLowerCase().includes(q);
      const matchCat = cat === 'ALL' || m.category === cat;
      const matchSt = st === 'ALL' || m.status === st;
      return matchQ && matchCat && matchSt;
    });
  });

  // Total pages
  readonly totalPages = computed(() => {
    return Math.max(1, Math.ceil(this.filteredModules().length / this.pageSize()));
  });

  readonly paginatedModules = computed(() => {
    const start = (this.currentPage() - 1) * this.pageSize();
    return this.filteredModules().slice(start, start + this.pageSize());
  });

  readonly pagesArray = computed(() => {
    const total = this.totalPages();
    const cur = this.currentPage();
    const delta = 2;
    const range: number[] = [];
    for (let i = Math.max(2, cur - delta); i <= Math.min(total - 1, cur + delta); i++) {
      range.push(i);
    }
    if (cur - delta > 2) range.unshift(-1);
    if (cur + delta < total - 1) range.push(-1);
    range.unshift(1);
    if (total > 1) range.push(total);
    return range;
  });

  // KPI Metrics
  readonly totalCount = computed(() => this.modules().length);
  readonly publishedCount = computed(
    () => this.modules().filter(m => m.status === 'Published').length
  );
  readonly totalProcesses = computed(() =>
    this.modules().reduce((acc, m) => acc + (m.totalComponents || 0), 0)
  );

  ngOnInit(): void {
    this.loadData();
  }

  loadData(silent = false): void {
    if (!silent) {
      this.isLoading.set(true);
      this.loadingService.show('Loading Module Catalogue...');
    }

    this.catalogueService
      .getModules()
      .pipe(
        finalize(() => {
          this.isLoading.set(false);
          if (!silent) this.loadingService.hide();
        })
      )
      .subscribe({
        next: data => {
          this.modules.set(data);
          if (silent) {
            this.dialogs.showToast(`Refreshed ${data.length} municipal modules`, 'success', 2500);
          }
        },
        error: () => this.dialogs.showToast('Failed to load modules catalogue', 'error', 3000)
      });
  }

  onRefreshClick(): void {
    this.loadData(true);
  }

  onSearchChange(term: string): void {
    this.searchQuery.set(term);
    this.currentPage.set(1);
  }

  onCategoryFilterChange(val: string): void {
    this.selectedCategoryFilter.set(val);
    this.currentPage.set(1);
  }

  onStatusFilterChange(val: string): void {
    this.selectedStatusFilter.set(val);
    this.currentPage.set(1);
  }

  clearFilters(): void {
    this.searchQuery.set('');
    this.selectedCategoryFilter.set('ALL');
    this.selectedStatusFilter.set('ALL');
    this.currentPage.set(1);
  }

  onPageSizeChange(newSize: number): void {
    this.pageSize.set(Number(newSize));
    this.currentPage.set(1);
  }

  goToPage(p: number): void {
    if (p > 0 && p <= this.totalPages()) {
      this.currentPage.set(p);
    }
  }

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

  openCreateModuleDialog(): void {
    this.selectedModule.set(null);
    this.isEditingModule.set(false);
    this.isModuleDialogOpen.set(true);
  }

  openEditModuleDialog(mod: ModuleCatalogueItem): void {
    this.selectedModule.set(mod);
    this.isEditingModule.set(true);
    this.isModuleDialogOpen.set(true);
  }

  closeModuleDialog(): void {
    this.isModuleDialogOpen.set(false);
    this.selectedModule.set(null);
  }

  onModuleSaved(savedModule: ModuleCatalogueItem): void {
    this.closeModuleDialog();
    const current = this.modules();
    const idx = current.findIndex(m => m.code === savedModule.code);
    if (idx >= 0) {
      const updated = [...current];
      updated[idx] = savedModule;
      this.modules.set(updated);
      this.dialogs.showToast(`Updated module ${savedModule.code}`, 'success', 2500);
    } else {
      this.modules.set([savedModule, ...current]);
      this.dialogs.showToast(`Created module ${savedModule.code}`, 'success', 2500);
    }
  }

  async publishModule(mod: ModuleCatalogueItem): Promise<void> {
    const ok = await this.dialogs.confirm({
      title: 'Publish Module',
      message: `Publish module "${mod.name}" (${mod.code}) to all Level 1 State catalogs?`,
      confirmText: 'Publish',
      variant: 'primary'
    });
    if (!ok) return;

    this.loadingService.show(`Publishing ${mod.code}...`);
    this.catalogueService
      .publishModule(mod.code)
      .pipe(finalize(() => this.loadingService.hide()))
      .subscribe({
        next: updated => {
          this.onModuleSaved(updated);
        },
        error: err => {
          const msg = err.error?.detail || err.error?.message || 'Failed to publish module';
          this.dialogs.showToast(msg, 'error', 3500);
        }
      });
  }

  async deprecateModule(mod: ModuleCatalogueItem): Promise<void> {
    const ok = await this.dialogs.confirm({
      title: 'Deprecate Module',
      message: `Are you sure you want to deprecate "${mod.name}" (${mod.code})? It will become read-only and no new states can subscribe.`,
      confirmText: 'Deprecate',
      variant: 'destructive'
    });
    if (!ok) return;

    this.loadingService.show(`Deprecating ${mod.code}...`);
    this.catalogueService
      .deprecateModule(mod.code)
      .pipe(finalize(() => this.loadingService.hide()))
      .subscribe({
        next: updated => {
          this.onModuleSaved(updated);
        },
        error: err => {
          const msg = err.error?.detail || err.error?.message || 'Failed to deprecate module';
          this.dialogs.showToast(msg, 'error', 3500);
        }
      });
  }

  viewComponentsForModule(mod: ModuleCatalogueItem): void {
    this.viewComponents.emit(mod.code);
  }

  openHistoryDialog(entityCode: string): void {
    this.historyEntityCode.set(entityCode);
    this.isHistoryDialogOpen.set(true);
  }

  closeHistoryDialog(): void {
    this.isHistoryDialogOpen.set(false);
    this.historyEntityCode.set('');
  }

  exportCatalogueJson(): void {
    this.loadingService.show('Exporting Module Catalogue JSON...');
    this.catalogueService
      .exportCatalogue()
      .pipe(finalize(() => this.loadingService.hide()))
      .subscribe({
        next: data => {
          const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `suvidha-module-catalogue-${new Date().toISOString().slice(0, 10)}.json`;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          window.URL.revokeObjectURL(url);
          this.dialogs.showToast('Catalogue JSON exported successfully', 'success', 3000);
        },
        error: () => this.dialogs.showToast('Failed to export catalogue', 'error', 3000)
      });
  }
}
