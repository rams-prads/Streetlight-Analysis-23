import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../shared/components/icon/icon.component';
import { TenantSecurityService } from '../../../../core/services/tenant-security.service';
import {
  IsolationFinding,
  IsolationFindingUpdatePayload,
  SecuritySummaryStats
} from '../../../../core/models/tenant-security.model';
import { AssignFindingDialogComponent } from './dialogs/assign-finding-dialog/assign-finding-dialog.component';
import { ExportReportDialogComponent } from './dialogs/export-report-dialog/export-report-dialog.component';

@Component({
  selector: 'app-isolation-findings',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    IconComponent,
    AssignFindingDialogComponent,
    ExportReportDialogComponent
  ],
  templateUrl: './isolation-findings.component.html',
  styleUrls: ['./isolation-findings.component.scss']
})
export class IsolationFindingsComponent implements OnInit {
  private securityService = inject(TenantSecurityService);

  findings = signal<IsolationFinding[]>([]);
  stats = signal<SecuritySummaryStats | null>(null);
  isLoading = signal(false);
  retestingFindingId = signal<string | null>(null);

  // Filters
  searchQuery = signal('');
  selectedSeverity = signal('ALL');
  selectedStatus = signal('ALL');

  // Pagination
  readonly page = signal<number>(1);
  readonly pageSize = signal<number>(10);
  readonly pageSizeOptions = [10, 25, 50];

  readonly paginatedFindings = computed(() => {
    const list = this.findings();
    const start = (this.page() - 1) * this.pageSize();
    return list.slice(start, start + this.pageSize());
  });

  readonly totalPages = computed(() => {
    const total = Math.ceil(this.findings().length / this.pageSize());
    return total > 0 ? total : 1;
  });

  readonly startIndex = computed(() => {
    if (this.findings().length === 0) return 0;
    return (this.page() - 1) * this.pageSize() + 1;
  });

  readonly endIndex = computed(() => {
    const end = this.page() * this.pageSize();
    return Math.min(end, this.findings().length);
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
  isAssignDialogOpen = signal(false);
  isExportDialogOpen = signal(false);
  selectedFindingForAssign = signal<IsolationFinding | null>(null);
  toastMessage = signal<string | null>(null);

  ngOnInit() {
    this.loadFindings();
    this.loadStats();
  }

  loadFindings() {
    this.isLoading.set(true);
    this.securityService.getFindings({
      severity: this.selectedSeverity(),
      status: this.selectedStatus(),
      search: this.searchQuery()
    }).subscribe({
      next: (res) => {
        this.findings.set(res.data || []);
        this.isLoading.set(false);
      },
      error: (err) => {
        console.error('Failed to load findings:', err);
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
    this.page.set(1);
    this.loadFindings();
  }

  openAssignDialog(f: IsolationFinding) {
    this.selectedFindingForAssign.set(f);
    this.isAssignDialogOpen.set(true);
  }

  closeAssignDialog() {
    this.isAssignDialogOpen.set(false);
    this.selectedFindingForAssign.set(null);
  }

  openExportDialog() {
    this.isExportDialogOpen.set(true);
  }

  closeExportDialog() {
    this.isExportDialogOpen.set(false);
  }

  saveAssignment(event: { id: string; payload: IsolationFindingUpdatePayload }) {
    this.securityService.updateFinding(event.id, event.payload).subscribe({
      next: () => {
        this.closeAssignDialog();
        this.loadFindings();
        this.loadStats();
        this.showToast(`Remediation plan updated for finding '${event.id}'`);
      },
      error: (err) => alert(err?.error?.detail || 'Failed to update finding')
    });
  }

  retestFinding(f: IsolationFinding) {
    this.retestingFindingId.set(f.id);
    this.securityService.retestFinding(f.id).subscribe({
      next: (res) => {
        this.retestingFindingId.set(null);
        this.loadFindings();
        this.loadStats();
        this.showToast(`Finding '${f.id}' re-tested and marked ${res.data.retestStatus}`);
      },
      error: (err) => {
        this.retestingFindingId.set(null);
        alert(err?.error?.detail || 'Retest failed');
      }
    });
  }

  private showToast(msg: string) {
    this.toastMessage.set(msg);
    setTimeout(() => this.toastMessage.set(null), 3500);
  }
}

