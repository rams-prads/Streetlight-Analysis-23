import { Component, EventEmitter, Input, OnInit, Output, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import { Ageing, Defaulter, PtxAccess } from '../../../core/models/ptx.model';
import { PtxService } from '../../../core/services/ptx.service';
import { PtxI18nService } from '../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { IconComponent } from '../../../shared/components/icon/icon.component';
import { dmy, errorText } from '../ptx-utils';

interface MyDay {
  total: number;
  receipts: number;
}

interface MyEfficiency {
  collection: number;
  target: number | null;
  achievementPercent: number | null;
}

interface Task {
  key: string;
  icon: string;
  label: string;
  detail: string;
  count: number;
  urgent: boolean;
  go: string;
}

interface Action {
  label: string;
  icon: string;
  go: string;
  primary?: boolean;
}

/**
 * Home for staff: the few things this person should do next, then (for those who see reports) how collection is going.
 * What appears depends on the role's permissions (PT-NF-10); the Commissioner's figures come from the dashboard (PT-48).
 */
@Component({
  selector: 'app-ptx-overview',
  standalone: true,
  imports: [CommonModule, IconComponent],
  templateUrl: './ptx-overview.component.html',
})
export class PtxOverviewComponent implements OnInit {
  @Input({ required: true }) access!: PtxAccess;
  /** Counts the shell already loaded for the sidebar. */
  @Input() badges: { [k: string]: number } = {};
  @Output() navigate = new EventEmitter<string>();
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  private router = inject(Router);
  i18n = inject(PtxI18nService);
  dmy = dmy;

  dash = signal<any | null>(null);
  pending = signal<{ [step: string]: number }>({});
  overdueComplaints = signal(0);
  loaded = signal(false);
  myToday = signal<MyDay | null>(null);
  myEff = signal<MyEfficiency | null>(null);
  myDefaulters = signal<Defaulter[]>([]);

  readonly stepLabels: { [code: string]: { label: string; detail: string; icon: string } } = {
    DOC_CHECK: { label: 'Documents to check', detail: 'Applications waiting for their papers to be checked', icon: 'ri-file-search-line' },
    FIELD_INSPECTION: { label: 'Site visits to make', detail: 'Applications waiting for an inspector to visit', icon: 'ri-walk-line' },
    APPROVAL: { label: 'Applications to approve', detail: 'Checked and visited, waiting for the officer’s decision', icon: 'ri-checkbox-circle-line' },
    NOTICE: { label: 'Objection period running', detail: 'Owners have been told the new tax and may object', icon: 'ri-time-line' },
  };

  ngOnInit(): void {
    this.load();
  }

  can(p: string): boolean {
    return this.access.permissions.includes(p);
  }

  /** Officers and inspectors move applications along; counter staff and the Commissioner only look them up. */
  actsOnCases(): boolean {
    return this.can('case.view') && this.can('property.edit');
  }

  /** Whether this person has a to-do list at all (counter staff start from the actions instead). */
  hasWork(): boolean {
    return this.actsOnCases() || ['complaint.work', 'approval.decide', 'rates.approve', 'petition.decide', 'survey.review', 'integration.run'].some((p) => this.can(p));
  }

  /** A field collector sees their own numbers here, not the full Reports section (PT-NF-10). */
  collectorOnly(): boolean {
    return this.can('reports.view.own') && !this.can('reports.view');
  }

  load(): void {
    const fail = (e: unknown) => this.dialog.showToast(errorText(e), 'error');
    if (this.can('reports.view')) this.ptx.get('/dashboard/commissioner').subscribe({ next: (d) => this.dash.set(d), error: fail });
    if (this.actsOnCases()) {
      this.ptx.get('/cases-summary/pending').subscribe({ next: (p) => { this.pending.set(p); this.loaded.set(true); }, error: fail });
    } else {
      this.loaded.set(true);
    }
    if (this.can('complaint.work')) this.ptx.get('/complaints', { overdue: 'true', limit: 1 }).subscribe({ next: (r) => this.overdueComplaints.set(r.total), error: fail });
    if (this.collectorOnly()) {
      this.ptx.get('/reports/daily-collection').subscribe({ next: (d) => this.myToday.set({ total: d.total, receipts: d.receipts }), error: fail });
      this.ptx.get('/reports/efficiency', { by: 'collector', view: 'YTD' }).subscribe({ next: (r) => this.myEff.set(r.rows[0] || null), error: fail });
      this.ptx.get<Ageing>('/arrears/ageing', { limit: 5 }).subscribe({ next: (a) => this.myDefaulters.set(a.defaulters.items), error: fail });
    }
  }

  /** Jumps straight to this property's record, where the dues and a "Take payment" button are waiting. */
  openProperty(upin: string): void {
    this.router.navigate(['/modules/ptx', 'properties'], { queryParams: { upin } });
  }

  /** The two or three things this role starts most of its work from. */
  actions(): Action[] {
    const list: Action[] = [];
    // inspectors start their day in the field; everyone else who collects starts at the counter
    const fieldFirst = this.can('survey.capture') && !this.can('approval.decide');
    if (fieldFirst) list.push({ label: 'Start field work', icon: 'ri-walk-line', go: 'field/work', primary: true });
    if (this.can('payment.collect')) list.push({ label: 'Take a payment', icon: 'ri-hand-coin-line', go: 'collection/pay', primary: !list.length });
    // a bill collector has no survey step, only notice.serve - this still gets them to the field screen
    if (this.can('notice.serve') && !fieldFirst) list.push({ label: 'Start field work', icon: 'ri-walk-line', go: 'field/work' });
    if (this.can('property.view')) list.push({ label: 'Find a property', icon: 'ri-search-line', go: 'properties', primary: !list.length });
    if (this.can('case.create') && this.can('case.view')) list.push({ label: 'New application', icon: 'ri-add-line', go: 'cases/cases' });
    if (!this.can('payment.collect') && this.can('reports.view')) list.push({ label: 'Open reports', icon: 'ri-bar-chart-box-line', go: 'reports/dcb' });
    return list.slice(0, 3);
  }

  /** Work waiting for this person, most urgent first; nothing waiting is not listed. */
  tasks(): Task[] {
    const b = this.badges || {};
    const list: Task[] = [];
    // checking papers and visiting sites is for inspectors and officers; deciding, and the objection period, for officers
    const officer = this.can('approval.decide');
    for (const [code, n] of Object.entries(this.pending())) {
      const s = this.stepLabels[code];
      if ((code === 'APPROVAL' || code === 'NOTICE') && !officer) continue;
      if (n > 0) list.push({ key: code, icon: s?.icon || 'ri-file-list-3-line', label: s?.label || code, detail: s?.detail || '', count: n, urgent: code === 'APPROVAL', go: 'cases/cases' });
    }
    if ((b['approvals'] || 0) > 0) {
      list.push({ key: 'approvals', icon: 'ri-shield-check-line', label: 'Approvals waiting for you', detail: 'Waivers, refunds and rate changes that need a second person', count: b['approvals'], urgent: true, go: 'approvals' });
    }
    if ((b['complaints'] || 0) > 0) {
      const late = this.overdueComplaints();
      list.push({ key: 'complaints', icon: 'ri-feedback-line', label: 'Complaints to answer', detail: late ? `${late} past their time limit` : 'All within their time limit', count: b['complaints'], urgent: late > 0, go: 'cases/complaints' });
    }
    if ((b['petitions'] || 0) > 0) {
      list.push({ key: 'petitions', icon: 'ri-scales-3-line', label: 'Petitions and appeals to decide', detail: 'Owners asking for the tax to be revised', count: b['petitions'], urgent: true, go: 'cases/petitions' });
    }
    if ((b['surveys'] || 0) > 0) {
      list.push({ key: 'surveys', icon: 'ri-survey-line', label: 'Field surveys to review', detail: 'Compare what inspectors found with the record', count: b['surveys'], urgent: false, go: 'field/review' });
    }
    if ((b['deeds'] || 0) > 0) {
      list.push({ key: 'deeds', icon: 'ri-contract-line', label: 'Registered deeds to check', detail: 'Deeds the system could not match on its own', count: b['deeds'], urgent: false, go: 'connections/deeds' });
    }
    return list.sort((x, y) => Number(y.urgent) - Number(x.urgent));
  }

  /** Whether this role is responsible for collection across wards (officers, Commissioner), not a single counter. */
  showWards(): boolean {
    return this.can('arrears.manage') || this.can('petition.decide') || this.can('approval.decide');
  }

  pct(n: number | null | undefined): number {
    const v = Number(n || 0);
    return v > 100 ? 100 : v < 0 ? 0 : v;
  }
}
