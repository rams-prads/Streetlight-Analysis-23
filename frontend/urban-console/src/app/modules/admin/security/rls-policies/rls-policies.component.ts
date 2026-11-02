import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../shared/components/icon/icon.component';
import { TenantSecurityService } from '../../../../core/services/tenant-security.service';
import {
  RLSPolicy,
  RLSPolicyCreatePayload,
  RLSPolicyValidationResult,
  SecuritySummaryStats
} from '../../../../core/models/tenant-security.model';
import { CreatePolicyDialogComponent } from './dialogs/create-policy-dialog/create-policy-dialog.component';
import { ViewPolicyDialogComponent } from './dialogs/view-policy-dialog/view-policy-dialog.component';

@Component({
  selector: 'app-rls-policies',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    IconComponent,
    CreatePolicyDialogComponent,
    ViewPolicyDialogComponent
  ],
  templateUrl: './rls-policies.component.html',
  styleUrls: ['./rls-policies.component.scss']
})
export class RlsPoliciesComponent implements OnInit {
  private securityService = inject(TenantSecurityService);

  policies = signal<RLSPolicy[]>([]);
  stats = signal<SecuritySummaryStats | null>(null);
  isLoading = signal(false);
  isValidatingAll = signal(false);
  validatingPolicyId = signal<string | null>(null);

  // Filters
  searchQuery = signal('');
  selectedStatus = signal('ALL');
  selectedTable = signal('ALL');

  // Pagination
  readonly page = signal<number>(1);
  readonly pageSize = signal<number>(10);
  readonly pageSizeOptions = [10, 25, 50];

  readonly paginatedPolicies = computed(() => {
    const list = this.policies();
    const start = (this.page() - 1) * this.pageSize();
    return list.slice(start, start + this.pageSize());
  });

  readonly totalPages = computed(() => {
    const total = Math.ceil(this.policies().length / this.pageSize());
    return total > 0 ? total : 1;
  });

  readonly startIndex = computed(() => {
    if (this.policies().length === 0) return 0;
    return (this.page() - 1) * this.pageSize() + 1;
  });

  readonly endIndex = computed(() => {
    const end = this.page() * this.pageSize();
    return Math.min(end, this.policies().length);
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

  // Dialog states
  isCreateDialogOpen = signal(false);
  isViewDialogOpen = signal(false);
  selectedPolicyForEdit = signal<RLSPolicy | null>(null);
  selectedPolicyForView = signal<RLSPolicy | null>(null);
  validationToast = signal<string | null>(null);

  tablesList = [
    'properties',
    'property_units',
    'water_connections',
    'water_meter_readings',
    'trade_licences',
    'financial_ledgers',
    'global_user_profiles',
    'building_plans',
    'citizen_grievances'
  ];

  ngOnInit() {
    this.loadPolicies();
    this.loadStats();
  }

  loadPolicies() {
    this.isLoading.set(true);
    this.securityService.getRlsPolicies({
      search: this.searchQuery(),
      status: this.selectedStatus(),
      table: this.selectedTable()
    }).subscribe({
      next: (res) => {
        this.policies.set(res.data || []);
        this.isLoading.set(false);
      },
      error: (err) => {
        console.error('Failed to load RLS policies:', err);
        this.isLoading.set(false);
      }
    });
  }

  loadStats() {
    this.securityService.getStats().subscribe({
      next: (res) => {
        if (res.data) this.stats.set(res.data);
      },
      error: (err) => console.error('Failed to load stats:', err)
    });
  }

  onFilterChange() {
    this.loadPolicies();
  }

  openCreateDialog() {
    this.selectedPolicyForEdit.set(null);
    this.isCreateDialogOpen.set(true);
  }

  openEditDialog(p: RLSPolicy) {
    this.selectedPolicyForEdit.set(p);
    this.isCreateDialogOpen.set(true);
  }

  openViewDialog(p: RLSPolicy) {
    this.selectedPolicyForView.set(p);
    this.isViewDialogOpen.set(true);
  }

  closeCreateDialog() {
    this.isCreateDialogOpen.set(false);
    this.selectedPolicyForEdit.set(null);
  }

  closeViewDialog() {
    this.isViewDialogOpen.set(false);
    this.selectedPolicyForView.set(null);
  }

  savePolicy(payload: RLSPolicyCreatePayload) {
    const editing = this.selectedPolicyForEdit();
    if (editing) {
      this.securityService.updateRlsPolicy(editing.id, payload).subscribe({
        next: () => {
          this.closeCreateDialog();
          this.loadPolicies();
          this.loadStats();
          this.showToast(`Policy '${payload.policyCode}' updated successfully`);
        },
        error: (err) => alert(err?.error?.detail || 'Failed to update policy')
      });
    } else {
      this.securityService.createRlsPolicy(payload).subscribe({
        next: () => {
          this.closeCreateDialog();
          this.loadPolicies();
          this.loadStats();
          this.showToast(`Policy '${payload.policyCode}' registered successfully`);
        },
        error: (err) => alert(err?.error?.detail || 'Failed to create policy')
      });
    }
  }

  deletePolicy(p: RLSPolicy) {
    if (!confirm(`Are you sure you want to remove policy '${p.policyCode}' from the RLS registry?`)) return;
    this.securityService.deleteRlsPolicy(p.id).subscribe({
      next: () => {
        this.loadPolicies();
        this.loadStats();
        this.showToast(`Policy '${p.policyCode}' removed`);
      },
      error: (err) => alert(err?.error?.detail || 'Failed to delete policy')
    });
  }

  validatePolicy(p: RLSPolicy) {
    this.validatingPolicyId.set(p.id);
    this.securityService.validateRlsPolicy(p.id).subscribe({
      next: (res) => {
        this.validatingPolicyId.set(null);
        this.loadPolicies();
        this.showToast(`Policy '${p.policyCode}' verified: ${res.data.status} (${res.data.latencyMs}ms)`);
      },
      error: (err) => {
        this.validatingPolicyId.set(null);
        alert(err?.error?.detail || 'Validation failed');
      }
    });
  }

  validateAll() {
    this.isValidatingAll.set(true);
    const list = this.policies();
    let completed = 0;
    list.forEach(p => {
      this.securityService.validateRlsPolicy(p.id).subscribe({
        next: () => {
          completed++;
          if (completed >= list.length) {
            this.isValidatingAll.set(false);
            this.loadPolicies();
            this.showToast('All RLS policies verified against active PostgreSQL catalog');
          }
        },
        error: () => {
          completed++;
          if (completed >= list.length) {
            this.isValidatingAll.set(false);
            this.loadPolicies();
          }
        }
      });
    });
  }

  togglePolicyStatus(p: RLSPolicy) {
    const nextStatus = p.policyStatus === 'ACTIVE' ? 'DISABLED' : 'ACTIVE';
    this.securityService.updateRlsPolicy(p.id, { policyStatus: nextStatus }).subscribe({
      next: () => {
        this.loadPolicies();
        this.loadStats();
        this.showToast(`Policy '${p.policyCode}' status set to ${nextStatus}`);
      },
      error: (err) => alert(err?.error?.detail || 'Failed to toggle policy status')
    });
  }

  private showToast(msg: string) {
    this.validationToast.set(msg);
    setTimeout(() => this.validationToast.set(null), 3500);
  }
}

