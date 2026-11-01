import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../shared/components/icon/icon.component';
import { DialogService } from '../../../../core/services/dialog.service';
import { LoadingService } from '../../../../core/services/loading.service';
import { ModuleCatalogueService } from '../../../../core/services/module-catalogue.service';
import {
  ActionDependencyRule,
  ModuleCatalogueItem,
  ComponentCatalogueItem
} from '../../../../core/models/module-catalogue.model';
import { DependencyRuleDialogComponent } from './dialogs/dependency-rule-dialog/dependency-rule-dialog.component';

@Component({
  selector: 'app-action-dependency-registry',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    IconComponent,
    DependencyRuleDialogComponent
  ],
  templateUrl: './action-dependency-registry.component.html',
  styleUrl: './action-dependency-registry.component.scss'
})
export class ActionDependencyRegistryComponent implements OnInit {
  private catalogueService = inject(ModuleCatalogueService);
  private dialogs = inject(DialogService);
  public loadingService = inject(LoadingService);

  readonly isLoading = signal(false);
  readonly isRunningDagCheck = signal(false);

  // Data
  readonly modules = signal<ModuleCatalogueItem[]>([]);
  readonly components = signal<ComponentCatalogueItem[]>([]);
  readonly rules = signal<ActionDependencyRule[]>([
    {
      id: 'DEP-001',
      sourceModuleCode: 'PTX',
      sourceComponentCode: 'PTX-P10',
      sourceAction: 'APPROVE',
      targetModuleCode: 'FIN',
      targetComponentCode: 'FIN-C01',
      targetAction: 'VALIDATE_LEDGER',
      ruleType: 'Prerequisite',
      enforcementLevel: 'Strict Block',
      description: 'Requires municipal finance ledger account validation before property assessment approval.',
      status: 'Active'
    },
    {
      id: 'DEP-002',
      sourceModuleCode: 'PTX',
      sourceComponentCode: 'PTX-P10',
      sourceAction: 'APPROVE',
      targetModuleCode: 'DMS',
      targetComponentCode: 'DMS-D02',
      targetAction: 'VERIFY_DEED',
      ruleType: 'Prerequisite',
      enforcementLevel: 'Strict Block',
      description: 'Encumbrance certificate and sale deed verification in DMS required prior to assessment issuance.',
      status: 'Active'
    },
    {
      id: 'DEP-003',
      sourceModuleCode: 'BPM',
      sourceComponentCode: 'BPM-P05',
      sourceAction: 'SANCTION',
      targetModuleCode: 'FNC',
      targetComponentCode: 'FNC-F01',
      targetAction: 'VERIFY_NOC',
      ruleType: 'Cross-Module Gate',
      enforcementLevel: 'Strict Block',
      description: 'Statutory Fire NOC certificate clearance required before high-rise building plan approval.',
      status: 'Active'
    },
    {
      id: 'DEP-004',
      sourceModuleCode: 'BPM',
      sourceComponentCode: 'BPM-P05',
      sourceAction: 'SANCTION',
      targetModuleCode: 'TPL',
      targetComponentCode: 'TPL-T02',
      targetAction: 'CHECK_ZONING',
      ruleType: 'Cross-Module Gate',
      enforcementLevel: 'Strict Block',
      description: 'Town Planning master plan zoning and setback validation gate.',
      status: 'Active'
    },
    {
      id: 'DEP-005',
      sourceModuleCode: 'TRL',
      sourceComponentCode: 'TRL-T03',
      sourceAction: 'ISSUE',
      targetModuleCode: 'UCH',
      targetComponentCode: 'UCH-U01',
      targetAction: 'CLEAR_DUES',
      ruleType: 'Prerequisite',
      enforcementLevel: 'Workflow Gate',
      description: 'Verify solid waste and sanitation user charges are cleared before commercial trade licence issue.',
      status: 'Active'
    },
    {
      id: 'DEP-006',
      sourceModuleCode: 'ENG',
      sourceComponentCode: 'ENG-E04',
      sourceAction: 'BILL_PAYMENT',
      targetModuleCode: 'FIN',
      targetComponentCode: 'FIN-C05',
      targetAction: 'BUDGET_CHECK',
      ruleType: 'Prerequisite',
      enforcementLevel: 'Strict Block',
      description: '15th Finance Commission or AMRUT capital expenditure budget headroom check before contractor voucher pass.',
      status: 'Active'
    },
    {
      id: 'DEP-007',
      sourceModuleCode: 'ENG',
      sourceComponentCode: 'ENG-E04',
      sourceAction: 'BILL_PAYMENT',
      targetModuleCode: 'INV',
      targetComponentCode: 'INV-I02',
      targetAction: 'STOCK_VERIFY',
      ruleType: 'Trigger',
      enforcementLevel: 'Workflow Gate',
      description: 'Stores goods receipt note (GRN) inspection and consumption reconciliation before bill release.',
      status: 'Active'
    },
    {
      id: 'DEP-008',
      sourceModuleCode: 'WTR',
      sourceComponentCode: 'WTR-W03',
      sourceAction: 'DISCONNECT',
      targetModuleCode: 'UCH',
      targetComponentCode: 'UCH-U03',
      targetAction: 'LEGAL_NOTICE',
      ruleType: 'Prerequisite',
      enforcementLevel: 'Strict Block',
      description: 'Formal 15-day statutory default notice must be dispatched and logged before water disconnection execution.',
      status: 'Active'
    },
    {
      id: 'DEP-009',
      sourceModuleCode: 'MPM',
      sourceComponentCode: 'MPM-M02',
      sourceAction: 'LEASE_ALLOCATE',
      targetModuleCode: 'FIN',
      targetComponentCode: 'FIN-C02',
      targetAction: 'ESCROW_DEPOSIT',
      ruleType: 'Cross-Module Gate',
      enforcementLevel: 'Strict Block',
      description: 'Earnest money deposit (EMD) or security escrow realization verified before municipal asset lease signing.',
      status: 'Active'
    },
    {
      id: 'DEP-010',
      sourceModuleCode: 'GSC',
      sourceComponentCode: 'GSC-S03',
      sourceAction: 'DBT_DISBURSE',
      targetModuleCode: 'FIN',
      targetComponentCode: 'FIN-C03',
      targetAction: 'PFMS_TREASURY_CLEAR',
      ruleType: 'Trigger',
      enforcementLevel: 'Async Verification',
      description: 'Public Financial Management System (PFMS) treasury queue sync for Direct Benefit Transfer subsidies.',
      status: 'Active'
    }
  ]);

  // Dialog State
  readonly isRuleDialogOpen = signal(false);
  readonly isEditingRule = signal(false);
  readonly selectedRule = signal<ActionDependencyRule | null>(null);

  // Filters
  readonly searchQuery = signal<string>('');
  readonly selectedSourceModuleFilter = signal<string>('ALL');
  readonly selectedRuleTypeFilter = signal<string>('ALL');
  readonly selectedStatusFilter = signal<string>('ALL');

  readonly ruleTypeOptions = ['Prerequisite', 'Trigger', 'Cross-Module Gate', 'Audit Chain'];

  // Filtered Rules
  readonly filteredRules = computed(() => {
    const q = this.searchQuery().toLowerCase().trim();
    const mod = this.selectedSourceModuleFilter();
    const rt = this.selectedRuleTypeFilter();
    const st = this.selectedStatusFilter();

    return this.rules().filter(r => {
      const matchQ =
        !q ||
        r.sourceComponentCode.toLowerCase().includes(q) ||
        r.targetComponentCode.toLowerCase().includes(q) ||
        r.sourceAction.toLowerCase().includes(q) ||
        r.targetAction.toLowerCase().includes(q) ||
        r.description.toLowerCase().includes(q);
      const matchMod = mod === 'ALL' || r.sourceModuleCode === mod || r.targetModuleCode === mod;
      const matchRt = rt === 'ALL' || r.ruleType === rt;
      const matchSt = st === 'ALL' || r.status === st;
      return matchQ && matchMod && matchRt && matchSt;
    });
  });

  // KPI Metrics
  readonly totalRules = computed(() => this.rules().length);

  // Pagination
  readonly page = signal<number>(1);
  readonly pageSize = signal<number>(10);
  readonly pageSizeOptions = [10, 25, 50];

  readonly paginatedRules = computed(() => {
    const list = this.filteredRules();
    const start = (this.page() - 1) * this.pageSize();
    return list.slice(start, start + this.pageSize());
  });

  readonly totalPages = computed(() => {
    const total = Math.ceil(this.filteredRules().length / this.pageSize());
    return total > 0 ? total : 1;
  });

  readonly startIndex = computed(() => {
    if (this.filteredRules().length === 0) return 0;
    return (this.page() - 1) * this.pageSize() + 1;
  });

  readonly endIndex = computed(() => {
    const end = this.page() * this.pageSize();
    return Math.min(end, this.filteredRules().length);
  });

  readonly pagesArray = computed(() => {
    const pages: number[] = [];
    const total = this.totalPages();
    const curr = this.page();
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

  prevPage(): void {
    if (this.page() > 1) {
      this.page.update(p => p - 1);
    }
  }

  nextPage(): void {
    if (this.page() < this.totalPages()) {
      this.page.update(p => p + 1);
    }
  }

  goToPage(page: number): void {
    if (page >= 1 && page <= this.totalPages()) {
      this.page.set(page);
    }
  }

  onPageSizeChange(size: number): void {
    this.pageSize.set(Number(size));
    this.page.set(1);
  }
  readonly interlinkedModulesCount = computed(() => {
    const mods = new Set<string>();
    this.rules().forEach(r => {
      mods.add(r.sourceModuleCode);
      mods.add(r.targetModuleCode);
    });
    return mods.size;
  });
  readonly strictBlockCount = computed(
    () => this.rules().filter(r => r.enforcementLevel === 'Strict Block').length
  );

  readonly isAcyclic = computed(() => {
    const activeRules = this.rules().filter(r => r.status === 'Active');
    const adj = new Map<string, string[]>();
    for (const r of activeRules) {
      const u = r.sourceComponentCode.trim().toUpperCase();
      const v = r.targetComponentCode.trim().toUpperCase();
      if (!adj.has(u)) adj.set(u, []);
      adj.get(u)!.push(v);
    }
    const state = new Map<string, number>();
    const dfs = (node: string): boolean => {
      state.set(node, 1);
      const neighbors = adj.get(node) || [];
      for (const nxt of neighbors) {
        if (state.get(nxt) === 1) return true;
        if (!state.has(nxt) || state.get(nxt) === 0) {
          if (dfs(nxt)) return true;
        }
      }
      state.set(node, 2);
      return false;
    };
    for (const node of adj.keys()) {
      if (!state.has(node) || state.get(node) === 0) {
        if (dfs(node)) return false;
      }
    }
    return true;
  });

  readonly dagStatusLabel = computed(() => {
    return this.isAcyclic() ? '100% Valid' : 'Cycle Detected';
  });

  ngOnInit(): void {
    const savedRules = localStorage.getItem('urban_action_dependencies');
    if (savedRules) {
      try {
        const parsed = JSON.parse(savedRules);
        if (Array.isArray(parsed) && parsed.length > 0) {
          this.rules.set(parsed);
        }
      } catch (e) {
        console.warn('Failed to parse saved dependency rules:', e);
      }
    }
    this.loadMetadata();
  }

  private persistRules(rules: ActionDependencyRule[]): void {
    this.rules.set(rules);
    localStorage.setItem('urban_action_dependencies', JSON.stringify(rules));
  }

  loadMetadata(): void {
    this.isLoading.set(true);
    this.catalogueService.getModules().subscribe({
      next: mods => {
        this.modules.set(mods);
        this.isLoading.set(false);
      },
      error: () => this.isLoading.set(false)
    });

    this.catalogueService.getAllComponents().subscribe({
      next: comps => this.components.set(comps),
      error: () => {}
    });
  }

  onRefreshClick(): void {
    this.loadMetadata();
    const savedRules = localStorage.getItem('urban_action_dependencies');
    if (savedRules) {
      try {
        const parsed = JSON.parse(savedRules);
        if (Array.isArray(parsed)) this.rules.set(parsed);
      } catch {}
    }
    this.dialogs.showToast(`Refreshed ${this.rules().length} action dependency rules`, 'success', 2500);
  }

  onSearchChange(term: string): void {
    this.searchQuery.set(term);
    this.page.set(1);
  }

  onSourceModuleFilterChange(mod: string): void {
    this.selectedSourceModuleFilter.set(mod);
    this.page.set(1);
  }

  onRuleTypeFilterChange(rt: string): void {
    this.selectedRuleTypeFilter.set(rt);
    this.page.set(1);
  }

  onStatusFilterChange(st: string): void {
    this.selectedStatusFilter.set(st);
    this.page.set(1);
  }

  clearFilters(): void {
    this.searchQuery.set('');
    this.selectedSourceModuleFilter.set('ALL');
    this.selectedRuleTypeFilter.set('ALL');
    this.selectedStatusFilter.set('ALL');
    this.page.set(1);
  }

  openCreateRuleDialog(): void {
    this.selectedRule.set(null);
    this.isEditingRule.set(false);
    this.isRuleDialogOpen.set(true);
  }

  openEditRuleDialog(rule: ActionDependencyRule): void {
    this.selectedRule.set(rule);
    this.isEditingRule.set(true);
    this.isRuleDialogOpen.set(true);
  }

  closeRuleDialog(): void {
    this.isRuleDialogOpen.set(false);
    this.selectedRule.set(null);
  }

  onRuleSaved(rule: ActionDependencyRule): void {
    this.closeRuleDialog();
    const current = this.rules();
    const idx = current.findIndex(r => r.id === rule.id);
    let updated: ActionDependencyRule[];
    if (idx >= 0) {
      updated = [...current];
      updated[idx] = rule;
      this.persistRules(updated);
      this.dialogs.showToast(`Updated dependency rule ${rule.id}`, 'success', 2500);
    } else {
      updated = [rule, ...current];
      this.persistRules(updated);
      this.dialogs.showToast(`Registered dependency rule ${rule.id}`, 'success', 2500);
    }
  }

  toggleRuleStatus(rule: ActionDependencyRule): void {
    const newStatus: 'Active' | 'Deprecated' = rule.status === 'Active' ? 'Deprecated' : 'Active';
    const updated: ActionDependencyRule[] = this.rules().map(r =>
      r.id === rule.id ? { ...r, status: newStatus } : r
    );
    this.persistRules(updated);
    this.dialogs.showToast(`Rule ${rule.id} marked as ${newStatus}`, 'info', 2500);
  }

  validateDagGraph(): void {
    this.isRunningDagCheck.set(true);
    const activeRules = this.rules().filter(r => r.status === 'Active');
    const adj = new Map<string, string[]>();
    for (const r of activeRules) {
      const u = r.sourceComponentCode.trim().toUpperCase();
      const v = r.targetComponentCode.trim().toUpperCase();
      if (!adj.has(u)) adj.set(u, []);
      adj.get(u)!.push(v);
    }

    const state = new Map<string, number>();
    let hasCycle = false;
    let cycleNodes: string[] = [];

    const dfs = (node: string, path: string[]): boolean => {
      state.set(node, 1);
      path.push(node);
      const neighbors = adj.get(node) || [];
      for (const nxt of neighbors) {
        if (state.get(nxt) === 1) {
          cycleNodes = [...path, nxt];
          return true;
        }
        if (!state.has(nxt) || state.get(nxt) === 0) {
          if (dfs(nxt, path)) return true;
        }
      }
      path.pop();
      state.set(node, 2);
      return false;
    };

    for (const node of adj.keys()) {
      if (!state.has(node) || state.get(node) === 0) {
        if (dfs(node, [])) {
          hasCycle = true;
          break;
        }
      }
    }

    this.isRunningDagCheck.set(false);
    if (hasCycle) {
      this.dialogs.showToast(
        `Circular Dependency Detected: ${cycleNodes.join(' -> ')}. Prerequisites violate DAG acyclicity rules.`,
        'error',
        5000
      );
    } else {
      this.dialogs.showToast(
        `DAG Integrity Verified: All ${activeRules.length} active rules validated. Zero circular prerequisite chains detected across all components.`,
        'success',
        4000
      );
    }
  }
}
