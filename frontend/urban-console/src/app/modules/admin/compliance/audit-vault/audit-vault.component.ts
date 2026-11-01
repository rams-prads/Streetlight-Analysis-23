import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../shared/components/icon/icon.component';
import { AuditVaultService } from '../../../../core/services/audit-vault.service';
import { TenantManagementService } from '../../../../core/services/tenant-management.service';
import { DialogService } from '../../../../core/services/dialog.service';
import { LoadingService } from '../../../../core/services/loading.service';
import { StateTenant } from '../../../../core/models/state-tenant.model';
import {
  ImmutableAuditEvent,
  AuditDashboardStats,
  HashVerificationJob,
  RetentionPolicy,
  AuditExportJob,
} from '../../../../core/models/audit-vault.model';
import { EventDetailsDialogComponent } from './dialogs/event-details-dialog/event-details-dialog.component';
import { HashVerificationDialogComponent } from './dialogs/hash-verification-dialog/hash-verification-dialog.component';
import { RetentionPolicyDialogComponent } from './dialogs/retention-policy-dialog/retention-policy-dialog.component';
import { AuditExportDialogComponent } from './dialogs/audit-export-dialog/audit-export-dialog.component';

@Component({
  selector: 'app-audit-vault',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    IconComponent,
    EventDetailsDialogComponent,
    HashVerificationDialogComponent,
    RetentionPolicyDialogComponent,
    AuditExportDialogComponent,
  ],
  templateUrl: './audit-vault.component.html',
  styleUrl: './audit-vault.component.scss'
})
export class AuditVaultComponent implements OnInit {
  private auditService = inject(AuditVaultService);
  private tenantService = inject(TenantManagementService);
  private dialogs = inject(DialogService);
  private loading = inject(LoadingService);

  readonly activeTab = signal<'dashboard' | 'explorer' | 'verification' | 'retention' | 'export'>('dashboard');

  // Core Data Signals
  readonly stats = signal<AuditDashboardStats | null>(null);
  readonly allEvents = signal<ImmutableAuditEvent[]>([]);
  readonly verificationJobs = signal<HashVerificationJob[]>([]);
  readonly retentionPolicies = signal<RetentionPolicy[]>([]);
  readonly exportJobs = signal<AuditExportJob[]>([]);
  readonly masterStates = signal<StateTenant[]>([]);
  readonly isLoading = signal<boolean>(false);

  // Active Dialog state
  readonly activeDialog = signal<'details' | 'verification' | 'retention' | 'export' | null>(null);
  readonly selectedEventForDetails = signal<ImmutableAuditEvent | null>(null);

  // Explorer Search & Filters
  searchQuery: string = '';
  selectedStateTenantId: string = 'ALL';
  selectedCategory: string = 'ALL';
  selectedSeverity: string = 'ALL';
  selectedResult: string = 'ALL';

  // Dashboard Filters
  dashLevelFilter: string = 'ALL';
  dashStateFilter: string = 'ALL';
  dashCategoryFilter: string = 'ALL';
  dashSeverityFilter: string = 'ALL';
  dashStatusFilter: string = 'ALL';

  // Pagination
  readonly currentPage = signal<number>(1);
  pageSize: number = 20;

  // Filtered Events
  readonly filteredEvents = computed(() => {
    let list = this.allEvents();

    if (this.selectedStateTenantId !== 'ALL') {
      list = list.filter((e) => e.tenantId === this.selectedStateTenantId);
    }
    if (this.selectedCategory !== 'ALL') {
      list = list.filter((e) => e.eventCategory === this.selectedCategory);
    }
    if (this.selectedSeverity !== 'ALL') {
      list = list.filter((e) => e.severity === this.selectedSeverity);
    }
    if (this.selectedResult !== 'ALL') {
      list = list.filter((e) => e.result === this.selectedResult);
    }
    if (this.searchQuery && this.searchQuery.trim()) {
      const q = this.searchQuery.trim().toLowerCase();
      list = list.filter(
        (e) =>
          e.eventId.toLowerCase().includes(q) ||
          e.action.toLowerCase().includes(q) ||
          e.actorId.toLowerCase().includes(q) ||
          e.correlationId.toLowerCase().includes(q) ||
          (e.moduleCode && e.moduleCode.toLowerCase().includes(q))
      );
    }

    return list;
  });

  readonly totalPages = computed(() => {
    const total = this.filteredEvents().length;
    return total > 0 ? Math.ceil(total / this.pageSize) : 1;
  });

  readonly paginatedEvents = computed(() => {
    const start = (this.currentPage() - 1) * this.pageSize;
    return this.filteredEvents().slice(start, start + this.pageSize);
  });

  readonly paginationStart = computed(() => {
    return this.filteredEvents().length === 0 ? 0 : (this.currentPage() - 1) * this.pageSize + 1;
  });

  readonly paginationEnd = computed(() => {
    const end = this.currentPage() * this.pageSize;
    return Math.min(end, this.filteredEvents().length);
  });

  readonly recentCriticalEvents = computed(() => {
    return this.allEvents()
      .filter((e) => e.severity === 'Critical' || e.severity === 'High')
      .slice(0, 5);
  });

  ngOnInit(): void {
    this.loadMasterStates();
    this.refreshAll();
  }

  loadMasterStates(): void {
    this.tenantService.getStateTenants().subscribe({
      next: (states) => {
        this.masterStates.set((states || []).filter((s) => s.status === 'Active'));
      },
      error: () => this.masterStates.set([])
    });
  }

  refreshAll(): void {
    this.isLoading.set(true);
    this.loadStats();
    this.loadEvents();
    this.loadVerifications();
    this.loadPolicies();
    this.loadExports();
    setTimeout(() => this.isLoading.set(false), 400);
  }

  loadStats(): void {
    this.auditService.getDashboardStats().subscribe({
      next: (res) => this.stats.set(res),
      error: () => this.stats.set(null)
    });
  }

  loadEvents(): void {
    this.auditService.getAuditEvents({ limit: 100 }).subscribe({
      next: (res) => this.allEvents.set(res || []),
      error: () => {
        this.allEvents.set([]);
        this.dialogs.showToast('Failed to load audit events', 'error');
      }
    });
  }

  loadVerifications(): void {
    this.auditService.getVerificationJobs().subscribe({
      next: (res) => this.verificationJobs.set(res || []),
      error: () => this.verificationJobs.set([])
    });
  }

  loadPolicies(): void {
    this.auditService.getRetentionPolicies().subscribe({
      next: (res) => this.retentionPolicies.set(res || []),
      error: () => this.retentionPolicies.set([])
    });
  }

  loadExports(): void {
    this.auditService.getAuditExports().subscribe({
      next: (res) => this.exportJobs.set(res || []),
      error: () => this.exportJobs.set([])
    });
  }

  setActiveTab(tab: 'dashboard' | 'explorer' | 'verification' | 'retention' | 'export'): void {
    this.activeTab.set(tab);
  }

  onSearchChange(): void {
    this.currentPage.set(1);
  }

  clearSearch(): void {
    this.searchQuery = '';
    this.currentPage.set(1);
  }

  onFilterChange(): void {
    this.currentPage.set(1);
  }

  onPageSizeChange(): void {
    this.currentPage.set(1);
  }

  goToPage(p: number): void {
    if (p >= 1 && p <= this.totalPages()) {
      this.currentPage.set(p);
    }
  }

  // Dialog open triggers
  inspectEvent(ev: ImmutableAuditEvent): void {
    this.selectedEventForDetails.set(ev);
    this.activeDialog.set('details');
  }

  openVerificationDialog(): void {
    this.activeDialog.set('verification');
  }

  openPolicyDialog(): void {
    this.activeDialog.set('retention');
  }

  openExportDialog(): void {
    this.activeDialog.set('export');
  }

  closeDialog(): void {
    this.activeDialog.set(null);
    this.selectedEventForDetails.set(null);
  }

  onVerificationCompleted(job: HashVerificationJob): void {
    this.loadVerifications();
    this.loadStats();
    this.loadEvents();
  }

  onPolicySaved(pol: RetentionPolicy): void {
    this.closeDialog();
    this.loadPolicies();
    this.loadStats();
    this.loadEvents();
  }

  onExportCompleted(exp: AuditExportJob): void {
    this.closeDialog();
    this.loadExports();
    this.loadEvents();
  }
}

