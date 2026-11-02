import { Component, OnInit, inject, signal, computed, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';
import { IconComponent } from '../../../../shared/components/icon/icon.component';
import { DialogService } from '../../../../core/services/dialog.service';
import { LoadingService } from '../../../../core/services/loading.service';
import { ModuleCatalogueService } from '../../../../core/services/module-catalogue.service';
import {
  ComponentCatalogueItem,
  ModuleCatalogueItem
} from '../../../../core/models/module-catalogue.model';
import { ComponentFormDialogComponent } from './dialogs/component-form-dialog/component-form-dialog.component';

@Component({
  selector: 'app-component-registry',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    IconComponent,
    ComponentFormDialogComponent
  ],
  templateUrl: './component-registry.component.html',
  styleUrl: './component-registry.component.scss'
})
export class ComponentRegistryComponent implements OnInit {
  private catalogueService = inject(ModuleCatalogueService);
  private dialogs = inject(DialogService);
  public loadingService = inject(LoadingService);

  @Input() set preselectedModule(val: string | undefined) {
    if (val && val !== 'ALL') {
      this.selectedParentModuleFilter.set(val);
    }
  }

  readonly isLoading = signal(false);

  // Data
  readonly modules = signal<ModuleCatalogueItem[]>([]);
  readonly components = signal<ComponentCatalogueItem[]>([]);

  // Dialog signals
  readonly isComponentDialogOpen = signal(false);
  readonly isEditingComponent = signal(false);
  readonly selectedComponent = signal<ComponentCatalogueItem | null>(null);
  readonly defaultComponentParent = signal<string>('');

  // Filters
  readonly searchQuery = signal<string>('');
  readonly selectedParentModuleFilter = signal<string>('ALL');
  readonly selectedTypeFilter = signal<string>('ALL');
  readonly selectedStatusFilter = signal<string>('ALL');

  readonly typeOptions = ['Process', 'Service', 'UI View', 'Report', 'Workflow'];

  // Pagination
  readonly currentPage = signal<number>(1);
  readonly pageSize = signal<number>(10);
  readonly pageSizeOptions = [5, 10, 20, 50];

  // Filtered Components
  readonly filteredComponents = computed(() => {
    const q = this.searchQuery().toLowerCase().trim();
    const parent = this.selectedParentModuleFilter();
    const type = this.selectedTypeFilter();
    const st = this.selectedStatusFilter();

    return this.components().filter(c => {
      const matchQ =
        !q ||
        c.name.toLowerCase().includes(q) ||
        c.code.toLowerCase().includes(q) ||
        c.frontendPermissionKey.toLowerCase().includes(q) ||
        (c.routePath && c.routePath.toLowerCase().includes(q));
      const matchParent = parent === 'ALL' || c.parentModuleCode === parent;
      const matchType = type === 'ALL' || c.componentType === type;
      const matchSt = st === 'ALL' || c.status === st;
      return matchQ && matchParent && matchType && matchSt;
    });
  });

  readonly totalPages = computed(() => {
    return Math.max(1, Math.ceil(this.filteredComponents().length / this.pageSize()));
  });

  readonly paginatedComponents = computed(() => {
    const start = (this.currentPage() - 1) * this.pageSize();
    return this.filteredComponents().slice(start, start + this.pageSize());
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
  readonly totalCount = computed(() => this.components().length);
  readonly processCount = computed(
    () => this.components().filter(c => c.componentType === 'Process').length
  );
  readonly serviceCount = computed(
    () => this.components().filter(c => c.componentType === 'Service').length
  );
  readonly activeCount = computed(
    () => this.components().filter(c => c.status === 'Published').length
  );

  ngOnInit(): void {
    this.loadData();
  }

  loadData(silent = false): void {
    if (!silent) {
      this.isLoading.set(true);
      this.loadingService.show('Loading Component Registry...');
    }

    this.catalogueService
      .getAllComponents()
      .pipe(
        finalize(() => {
          this.isLoading.set(false);
          if (!silent) this.loadingService.hide();
        })
      )
      .subscribe({
        next: comps => {
          this.components.set(comps);
          if (silent) {
            this.dialogs.showToast(`Refreshed ${comps.length} components`, 'success', 2500);
          }
        },
        error: () => this.dialogs.showToast('Failed to load component registry', 'error', 3000)
      });

    this.catalogueService.getModules().subscribe({
      next: mods => this.modules.set(mods),
      error: () => {}
    });
  }

  onRefreshClick(): void {
    this.loadData(true);
  }

  onSearchChange(term: string): void {
    this.searchQuery.set(term);
    this.currentPage.set(1);
  }

  onParentModuleFilterChange(val: string): void {
    this.selectedParentModuleFilter.set(val);
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
    this.selectedParentModuleFilter.set('ALL');
    this.selectedTypeFilter.set('ALL');
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

  openCreateComponentDialog(parentModuleCode?: string): void {
    this.selectedComponent.set(null);
    this.isEditingComponent.set(false);
    this.defaultComponentParent.set(parentModuleCode || (this.modules()[0]?.code ?? 'PTX'));
    this.isComponentDialogOpen.set(true);
  }

  openEditComponentDialog(comp: ComponentCatalogueItem): void {
    this.selectedComponent.set(comp);
    this.isEditingComponent.set(true);
    this.defaultComponentParent.set(comp.parentModuleCode);
    this.isComponentDialogOpen.set(true);
  }

  closeComponentDialog(): void {
    this.isComponentDialogOpen.set(false);
    this.selectedComponent.set(null);
  }

  onComponentSaved(savedComp: ComponentCatalogueItem): void {
    this.closeComponentDialog();
    const current = this.components();
    const idx = current.findIndex(c => c.code === savedComp.code);
    if (idx >= 0) {
      const updated = [...current];
      updated[idx] = savedComp;
      this.components.set(updated);
      this.dialogs.showToast(`Updated component ${savedComp.code}`, 'success', 2500);
    } else {
      this.components.set([savedComp, ...current]);
      this.dialogs.showToast(`Created component ${savedComp.code}`, 'success', 2500);
    }
  }

  async deprecateComponent(comp: ComponentCatalogueItem): Promise<void> {
    const ok = await this.dialogs.confirm({
      title: 'Deprecate Component',
      message: `Are you sure you want to deprecate "${comp.name}" (${comp.code})? It will be marked as deprecated across permission policies.`,
      confirmText: 'Deprecate',
      variant: 'destructive'
    });
    if (!ok) return;

    this.loadingService.show(`Deprecating ${comp.code}...`);
    this.catalogueService
      .deprecateComponent(comp.code)
      .pipe(finalize(() => this.loadingService.hide()))
      .subscribe({
        next: updated => {
          this.onComponentSaved(updated);
        },
        error: err => {
          const msg = err.error?.detail || err.error?.message || 'Failed to deprecate component';
          this.dialogs.showToast(msg, 'error', 3500);
        }
      });
  }
}
