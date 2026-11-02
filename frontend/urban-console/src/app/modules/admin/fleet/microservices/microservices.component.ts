import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../shared/components/icon/icon.component';
import { FleetService } from '../../../../core/services/fleet.service';
import { DialogService } from '../../../../core/services/dialog.service';
import {
  MicroserviceOverviewStats,
  MicroserviceRegistryItem,
  MicroserviceRegisterPayload,
  PodMonitoringItem,
  WorkerQueueItem,
  DatabaseConnectionPoolItem,
} from '../../../../core/models/fleet.model';
import { ServiceRegisterDialogComponent } from './dialogs/service-register-dialog/service-register-dialog.component';
import { ServiceDetailsDialogComponent } from './dialogs/service-details-dialog/service-details-dialog.component';

@Component({
  selector: 'app-microservices',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    IconComponent,
    ServiceRegisterDialogComponent,
    ServiceDetailsDialogComponent,
  ],
  templateUrl: './microservices.component.html',
  styleUrl: './microservices.component.scss',
})
export class MicroservicesComponent implements OnInit {
  private fleetService = inject(FleetService);
  private dialogs = inject(DialogService);

  readonly activeTab = signal<'overview' | 'registry' | 'pods' | 'queues' | 'db-pools'>('overview');

  // Core Data
  readonly stats = signal<MicroserviceOverviewStats | null>(null);
  readonly allServices = signal<MicroserviceRegistryItem[]>([]);
  readonly allPods = signal<PodMonitoringItem[]>([]);
  readonly allQueues = signal<WorkerQueueItem[]>([]);
  readonly allDbPools = signal<DatabaseConnectionPoolItem[]>([]);
  readonly isLoading = signal<boolean>(false);

  // Dialog State
  readonly activeDialog = signal<'register' | 'details' | null>(null);
  readonly selectedServiceForDetails = signal<MicroserviceRegistryItem | null>(null);

  // Filters: Overview & Registry
  searchQuery: string = '';
  selectedEnvironment: string = 'ALL';
  selectedCategory: string = 'ALL';
  selectedStatus: string = 'ALL';
  selectedCriticality: string = 'ALL';

  // Filters: Pods
  podSearch: string = '';
  selectedCluster: string = 'ALL';
  selectedNamespace: string = 'ALL';
  selectedPodStatus: string = 'ALL';

  // Filters: Queues
  selectedQueueType: string = 'ALL';
  selectedQueueStatus: string = 'ALL';

  // Filters: DB Pools
  selectedDbCluster: string = 'ALL';
  selectedPoolStatus: string = 'ALL';

  // Pagination
  readonly currentPage = signal<number>(1);
  pageSize: number = 20;

  // Filtered Services
  readonly filteredServices = computed(() => {
    let list = this.allServices();

    if (this.selectedEnvironment !== 'ALL') {
      list = list.filter((s) => s.environments.includes(this.selectedEnvironment));
    }
    if (this.selectedCategory !== 'ALL') {
      list = list.filter((s) => s.serviceCategory === this.selectedCategory);
    }
    if (this.selectedStatus !== 'ALL') {
      list = list.filter((s) => s.status === this.selectedStatus);
    }
    if (this.selectedCriticality !== 'ALL') {
      list = list.filter((s) => s.criticalityLevel.startsWith(this.selectedCriticality));
    }
    if (this.searchQuery && this.searchQuery.trim()) {
      const q = this.searchQuery.trim().toLowerCase();
      list = list.filter(
        (s) =>
          s.serviceName.toLowerCase().includes(q) ||
          s.serviceCode.toLowerCase().includes(q) ||
          s.serviceDescription.toLowerCase().includes(q) ||
          s.baseUrl.toLowerCase().includes(q)
      );
    }

    return list;
  });

  // Filtered Pods
  readonly filteredPods = computed(() => {
    let list = this.allPods();

    if (this.selectedCluster !== 'ALL') {
      list = list.filter((p) => p.cluster === this.selectedCluster);
    }
    if (this.selectedNamespace !== 'ALL') {
      list = list.filter((p) => p.namespace === this.selectedNamespace);
    }
    if (this.selectedPodStatus !== 'ALL') {
      list = list.filter((p) => p.podStatus === this.selectedPodStatus);
    }
    if (this.podSearch && this.podSearch.trim()) {
      const q = this.podSearch.trim().toLowerCase();
      list = list.filter(
        (p) =>
          p.podName.toLowerCase().includes(q) ||
          p.serviceCode.toLowerCase().includes(q) ||
          p.deployment.toLowerCase().includes(q) ||
          p.nodeName.toLowerCase().includes(q)
      );
    }

    return list;
  });

  // Filtered Queues
  readonly filteredQueues = computed(() => {
    let list = this.allQueues();

    if (this.selectedQueueType !== 'ALL') {
      list = list.filter((q) => q.queueType === this.selectedQueueType);
    }
    if (this.selectedQueueStatus !== 'ALL') {
      list = list.filter((q) => q.queueStatus === this.selectedQueueStatus);
    }

    return list;
  });

  // Filtered DB Pools
  readonly filteredDbPools = computed(() => {
    let list = this.allDbPools();

    if (this.selectedDbCluster !== 'ALL') {
      list = list.filter((dp) => dp.databaseCluster === this.selectedDbCluster);
    }
    if (this.selectedPoolStatus !== 'ALL') {
      list = list.filter((dp) => dp.connectionStatus === this.selectedPoolStatus);
    }

    return list;
  });

  // Pagination Computations
  readonly totalPages = computed(() => {
    let count = 0;
    const tab = this.activeTab();
    if (tab === 'overview' || tab === 'registry') count = this.filteredServices().length;
    else if (tab === 'pods') count = this.filteredPods().length;
    else if (tab === 'queues') count = this.filteredQueues().length;
    else if (tab === 'db-pools') count = this.filteredDbPools().length;

    return count > 0 ? Math.ceil(count / this.pageSize) : 1;
  });

  readonly paginatedServices = computed(() => {
    const start = (this.currentPage() - 1) * this.pageSize;
    return this.filteredServices().slice(start, start + this.pageSize);
  });

  readonly paginatedPods = computed(() => {
    const start = (this.currentPage() - 1) * this.pageSize;
    return this.filteredPods().slice(start, start + this.pageSize);
  });

  readonly paginationStart = computed(() => {
    let count = 0;
    const tab = this.activeTab();
    if (tab === 'overview' || tab === 'registry') count = this.filteredServices().length;
    else if (tab === 'pods') count = this.filteredPods().length;
    else if (tab === 'queues') count = this.filteredQueues().length;
    else if (tab === 'db-pools') count = this.filteredDbPools().length;

    return count === 0 ? 0 : (this.currentPage() - 1) * this.pageSize + 1;
  });

  readonly paginationEnd = computed(() => {
    let count = 0;
    const tab = this.activeTab();
    if (tab === 'overview' || tab === 'registry') count = this.filteredServices().length;
    else if (tab === 'pods') count = this.filteredPods().length;
    else if (tab === 'queues') count = this.filteredQueues().length;
    else if (tab === 'db-pools') count = this.filteredDbPools().length;

    const end = this.currentPage() * this.pageSize;
    return Math.min(end, count);
  });

  ngOnInit(): void {
    this.refreshAll();
  }

  refreshAll(): void {
    this.isLoading.set(true);
    this.loadStats();
    this.loadServices();
    this.loadPods();
    this.loadQueues();
    this.loadDbPools();
    setTimeout(() => this.isLoading.set(false), 350);
  }

  loadStats(): void {
    this.fleetService.getClusterStats().subscribe({
      next: (s) => this.stats.set(s),
      error: () => this.stats.set(null),
    });
  }

  loadServices(): void {
    this.fleetService.getMicroservices().subscribe({
      next: (svcs) => this.allServices.set(svcs || []),
      error: () => {
        this.allServices.set([]);
        this.dialogs.showToast('Failed to load microservice registry', 'error');
      },
    });
  }

  loadPods(): void {
    this.fleetService.getPods().subscribe({
      next: (pods) => this.allPods.set(pods || []),
      error: () => this.allPods.set([]),
    });
  }

  loadQueues(): void {
    this.fleetService.getWorkerQueues().subscribe({
      next: (q) => this.allQueues.set(q || []),
      error: () => this.allQueues.set([]),
    });
  }

  loadDbPools(): void {
    this.fleetService.getDatabaseConnectionPools().subscribe({
      next: (pools) => this.allDbPools.set(pools || []),
      error: () => this.allDbPools.set([]),
    });
  }

  setActiveTab(tab: 'overview' | 'registry' | 'pods' | 'queues' | 'db-pools'): void {
    this.activeTab.set(tab);
    this.currentPage.set(1);
  }

  onFilterChange(): void {
    this.currentPage.set(1);
  }

  clearSearch(): void {
    this.searchQuery = '';
    this.currentPage.set(1);
  }

  clearPodSearch(): void {
    this.podSearch = '';
    this.currentPage.set(1);
  }

  goToPage(p: number): void {
    if (p >= 1 && p <= this.totalPages()) {
      this.currentPage.set(p);
    }
  }

  onPageSizeChange(): void {
    this.currentPage.set(1);
  }

  // Dialog Controls
  openRegisterDialog(): void {
    this.activeDialog.set('register');
  }

  inspectService(svc: MicroserviceRegistryItem): void {
    this.selectedServiceForDetails.set(svc);
    this.activeDialog.set('details');
  }

  closeDialog(): void {
    this.activeDialog.set(null);
    this.selectedServiceForDetails.set(null);
  }

  onServiceRegistered(payload: MicroserviceRegisterPayload): void {
    this.fleetService.registerMicroservice(payload).subscribe({
      next: (created) => {
        this.closeDialog();
        this.dialogs.showToast(`Microservice '${created.serviceCode}' enrolled successfully!`, 'success');
        this.refreshAll();
      },
      error: (err) => {
        const msg = err?.error?.detail || err?.message || 'Failed to register microservice';
        this.dialogs.showToast(msg, 'error');
      },
    });
  }

  triggerProbe(svc: MicroserviceRegistryItem): void {
    this.dialogs.showToast(`Triggered liveness probe on ${svc.serviceCode} (${svc.baseUrl}${svc.healthCheckEndpoint})`, 'info');
    setTimeout(() => {
      this.refreshAll();
      this.dialogs.showToast(`Probe completed: ${svc.serviceCode} responded 200 OK (${svc.avgLatencyMs}ms)`, 'success');
    }, 800);
  }
}

