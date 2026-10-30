import { Component, OnDestroy, OnInit, ViewEncapsulation, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router, RouterModule } from '@angular/router';
import { Subscription } from 'rxjs';
import { KeycloakAuthService } from '../../core/services/keycloak.service';
import { WaterService } from '../../core/services/water.service';
import { WaterI18nService } from '../../core/services/water-i18n.service';
import { DialogService } from '../../core/services/dialog.service';
import { WaterAccess } from '../../core/models/water.model';
import { IconComponent } from '../../shared/components/icon/icon.component';
import { errorText } from './water-utils';
import { WaterOverviewComponent } from './sections/water-overview.component';
import { WaterConnectionsComponent } from './sections/water-connections.component';
import { WaterApplicationsComponent } from './sections/water-applications.component';
import { WaterReadingsComponent } from './sections/water-readings.component';
import { WaterBillingComponent } from './sections/water-billing.component';
import { WaterCollectionComponent } from './sections/water-collection.component';
import { WaterArrearsComponent } from './sections/water-arrears.component';
import { WaterComplaintsComponent } from './sections/water-complaints.component';
import { WaterMapComponent } from './sections/water-map.component';
import { WaterReportsComponent } from './sections/water-reports.component';
import { WaterApprovalsComponent } from './sections/water-approvals.component';
import { WaterAdminComponent } from './sections/water-admin.component';
import { WaterCitizenComponent } from './sections/water-citizen.component';
import { WaterFieldComponent } from './sections/water-field.component';

interface Section {
  key: string;
  icon: string;
  anyOf: string[];
}

/** Module 2 shell: section tabs filtered by the user's water permissions (WB-NF-10), and the Telugu / English switch. */
@Component({
  selector: 'app-water-shell',
  standalone: true,
  encapsulation: ViewEncapsulation.None,
  imports: [
    CommonModule, RouterModule, IconComponent, WaterOverviewComponent, WaterConnectionsComponent, WaterApplicationsComponent,
    WaterReadingsComponent, WaterBillingComponent, WaterCollectionComponent, WaterArrearsComponent, WaterComplaintsComponent,
    WaterMapComponent, WaterReportsComponent, WaterApprovalsComponent, WaterAdminComponent, WaterCitizenComponent, WaterFieldComponent,
  ],
  templateUrl: './water-shell.component.html',
  styleUrl: './water.scss',
})
export class WaterShellComponent implements OnInit, OnDestroy {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private auth = inject(KeycloakAuthService);
  private water = inject(WaterService);
  private dialog = inject(DialogService);
  i18n = inject(WaterI18nService);

  readonly sections: Section[] = [
    { key: 'overview', icon: 'chart', anyOf: ['reports.view'] },
    { key: 'connections', icon: 'wtr', anyOf: ['connection.view'] },
    { key: 'applications', icon: 'dms', anyOf: ['application.view', 'application.create'] },
    { key: 'readings', icon: 'efficiency', anyOf: ['reading.capture', 'reading.review'] },
    { key: 'billing', icon: 'ptx', anyOf: ['billing.view'] },
    { key: 'collection', icon: 'fin', anyOf: ['payment.collect', 'payment.reconcile'] },
    { key: 'arrears', icon: 'lgl', anyOf: ['arrears.manage', 'field.execute'] },
    { key: 'complaints', icon: 'grv', anyOf: ['complaint.work', 'reports.view'] },
    { key: 'map', icon: 'tpl', anyOf: ['connection.view'] },
    { key: 'reports', icon: 'chart', anyOf: ['reports.view'] },
    { key: 'approvals', icon: 'gsc', anyOf: ['approval.decide', 'approval.request', 'tariff.approve'] },
    { key: 'admin', icon: 'hrm', anyOf: ['settings.manage', 'audit.view'] },
    { key: 'citizen', icon: 'units', anyOf: ['payment.online'] },
    { key: 'field', icon: 'eng', anyOf: ['reading.capture', 'field.execute'] },
  ];

  access = signal<WaterAccess | null>(null);
  section = signal<string>('overview');
  loadError = signal<string>('');
  visible = computed(() => {
    const perms = new Set(this.access()?.permissions ?? []);
    return this.sections.filter((s) => s.anyOf.some((p) => perms.has(p)));
  });

  private sub?: Subscription;
  private tenantHandler = () => this.load();

  ngOnInit(): void {
    // a page reload lands here directly: make WTR the active module in the shared header
    const wtr = this.auth.userModules().find((m) => m.code === 'WTR');
    if (this.auth.activeModule().code !== 'WTR') {
      this.auth.activeModule.set(
        wtr ?? {
          code: 'WTR', name: 'Water, Sewerage & Utility Billing', domain: 'Revenue & Billing', phase: 1, icon: 'wtr',
          description: 'Consumer connections, meter readings, water tariffs, billing and collection', has_access: true,
          route: '/modules/wtr',
        },
      );
    }
    this.sub = this.route.paramMap.subscribe((p) => this.section.set(p.get('section') || ''));
    window.addEventListener('urban:tenant-changed', this.tenantHandler);
    this.load();
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
    window.removeEventListener('urban:tenant-changed', this.tenantHandler);
  }

  load(): void {
    this.loadError.set('');
    this.water.me().subscribe({
      next: (a) => {
        this.access.set(a);
        const allowed = this.visible().map((s) => s.key);
        if (!allowed.includes(this.section())) this.go(allowed[0] || 'citizen');
      },
      error: (e) => {
        this.loadError.set(errorText(e));
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  go(key: string): void {
    this.router.navigate(['/modules/wtr', key]);
  }
}
