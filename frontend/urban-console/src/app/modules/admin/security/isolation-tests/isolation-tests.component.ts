import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../shared/components/icon/icon.component';
import { TenantSecurityService } from '../../../../core/services/tenant-security.service';
import {
  TenantIsolationTestRun,
  TenantIsolationTestCreatePayload
} from '../../../../core/models/tenant-security.model';
import { CreateTestRunDialogComponent } from './dialogs/create-test-run-dialog/create-test-run-dialog.component';
import { TestDetailsDialogComponent } from './dialogs/test-details-dialog/test-details-dialog.component';

@Component({
  selector: 'app-isolation-tests',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    IconComponent,
    CreateTestRunDialogComponent,
    TestDetailsDialogComponent
  ],
  templateUrl: './isolation-tests.component.html',
  styleUrls: ['./isolation-tests.component.scss']
})
export class IsolationTestsComponent implements OnInit {
  private securityService = inject(TenantSecurityService);

  testRuns = signal<TenantIsolationTestRun[]>([]);
  isLoading = signal(false);
  isRunningAll = signal(false);
  runningTestId = signal<string | null>(null);

  // Filters
  searchQuery = signal('');
  selectedStatus = signal('ALL');
  selectedEnvironment = signal('ALL');

  // Computed Summary Metrics
  readonly overallPassRate = computed(() => {
    const runs = this.testRuns();
    if (runs.length === 0) return '100%';
    let total = 0;
    let passed = 0;
    for (const r of runs) {
      total += r.totalTests || 0;
      passed += r.passedCount || 0;
    }
    if (total === 0) return '100%';
    return `${Math.round((passed / total) * 100)}%`;
  });

  readonly totalScenariosAudited = computed(() => {
    return this.testRuns().reduce((acc, r) => acc + (r.totalTests || 0), 0);
  });

  readonly activeEnvironmentName = computed(() => {
    const env = this.selectedEnvironment();
    return env === 'ALL' ? 'Sandbox & Prod' : env;
  });

  // Pagination
  readonly page = signal<number>(1);
  readonly pageSize = signal<number>(10);
  readonly pageSizeOptions = [10, 25, 50];

  readonly paginatedTestRuns = computed(() => {
    const list = this.testRuns();
    const start = (this.page() - 1) * this.pageSize();
    return list.slice(start, start + this.pageSize());
  });

  readonly totalPages = computed(() => {
    const total = Math.ceil(this.testRuns().length / this.pageSize());
    return total > 0 ? total : 1;
  });

  readonly startIndex = computed(() => {
    if (this.testRuns().length === 0) return 0;
    return (this.page() - 1) * this.pageSize() + 1;
  });

  readonly endIndex = computed(() => {
    const end = this.page() * this.pageSize();
    return Math.min(end, this.testRuns().length);
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

  // Dialogs
  isCreateDialogOpen = signal(false);
  isDetailsDialogOpen = signal(false);
  selectedTestForDetails = signal<TenantIsolationTestRun | null>(null);
  toastMessage = signal<string | null>(null);

  ngOnInit() {
    this.loadTestRuns();
  }

  loadTestRuns(callback?: () => void) {
    this.isLoading.set(true);
    this.securityService.getIsolationTests({
      status: this.selectedStatus(),
      environment: this.selectedEnvironment(),
      search: this.searchQuery()
    }).subscribe({
      next: (res) => {
        this.testRuns.set(res.data || []);
        this.isLoading.set(false);
        if (callback) callback();
      },
      error: (err) => {
        console.error('Failed to load isolation tests:', err);
        this.isLoading.set(false);
        if (callback) callback();
      }
    });
  }

  onFilterChange() {
    this.page.set(1);
    this.loadTestRuns();
  }

  openCreateDialog() {
    this.isCreateDialogOpen.set(true);
  }

  closeCreateDialog() {
    this.isCreateDialogOpen.set(false);
  }

  openDetailsDialog(t: TenantIsolationTestRun) {
    this.selectedTestForDetails.set(t);
    this.isDetailsDialogOpen.set(true);
  }

  closeDetailsDialog() {
    this.isDetailsDialogOpen.set(false);
    this.selectedTestForDetails.set(null);
  }

  saveTestRun(payload: TenantIsolationTestCreatePayload) {
    this.securityService.createIsolationTest(payload).subscribe({
      next: (res) => {
        this.closeCreateDialog();
        this.loadTestRuns();
        this.showToast(`Test run '${res.data.id}' scheduled successfully`);
      },
      error: (err) => alert(err?.error?.detail || 'Failed to schedule test run')
    });
  }

  executeTest(t: TenantIsolationTestRun) {
    this.runningTestId.set(t.id);
    this.securityService.runIsolationTest(t.id).subscribe({
      next: (res) => {
        this.runningTestId.set(null);
        const passPct = res.data.totalTests > 0
          ? Math.round((res.data.passedCount / res.data.totalTests) * 100)
          : 0;
        this.showToast(`Test '${t.id}' executed: ${passPct}% Passed (${res.data.status})`);
        this.loadTestRuns(() => {
          if (this.selectedTestForDetails()?.id === t.id) {
            const updated = this.testRuns().find(item => item.id === t.id);
            if (updated) this.selectedTestForDetails.set(updated);
          }
        });
      },
      error: (err) => {
        this.runningTestId.set(null);
        alert(err?.error?.detail || 'Execution failed');
      }
    });
  }

  runAll() {
    const runs = this.testRuns();
    if (runs.length === 0) return;
    this.isRunningAll.set(true);
    let completed = 0;
    let failed = 0;
    runs.forEach(r => {
      this.securityService.runIsolationTest(r.id).subscribe({
        next: (res) => {
          completed++;
          if (res.data.failedCount > 0 || res.data.status === 'FAILED') {
            failed++;
          }
          if (completed >= runs.length) {
            this.isRunningAll.set(false);
            this.loadTestRuns();
            if (failed === 0) {
              this.showToast('All isolation tests executed with 100% boundary compliance');
            } else {
              this.showToast(`${completed - failed}/${completed} tests passed. ${failed} runs reported leaks.`);
            }
          }
        },
        error: () => {
          completed++;
          failed++;
          if (completed >= runs.length) {
            this.isRunningAll.set(false);
            this.loadTestRuns();
            this.showToast(`${completed - failed}/${completed} tests completed. ${failed} runs encountered execution errors.`);
          }
        }
      });
    });
  }

  private showToast(msg: string) {
    this.toastMessage.set(msg);
    setTimeout(() => this.toastMessage.set(null), 3500);
  }
}

