import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { PtxAccess } from '../../../core/models/ptx.model';
import { PtxService } from '../../../core/services/ptx.service';
import { PtxI18nService } from '../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { IconComponent } from '../../../shared/components/icon/icon.component';
import { PtxPagerComponent } from '../shared/ptx-pager.component';
import { CASE_TYPES } from '../cases/case-types';
import { Pager, dmy, errorText, todayIso } from '../ptx-utils';

/** A role allowed to do a workflow step. Administrators can always act on any step, so they are not listed here. */
const WORKFLOW_ROLES = [
  { code: 'revenue_officer', label: 'Revenue officer' },
  { code: 'revenue_inspector', label: 'Revenue inspector' },
  { code: 'bill_collector', label: 'Bill collector' },
  { code: 'cashier', label: 'Cashier' },
  { code: 'csc_operator', label: 'Meeseva / CSC operator' },
  { code: 'commissioner', label: 'Commissioner' },
];

type Tab = 'settings' | 'codes' | 'audit' | 'sms' | 'migration';

/** Settings with version history (PT-NF-60), code lists, audit trail (PT-NF-13), SMS log and data migration. */
@Component({
  selector: 'app-ptx-admin',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent, PtxPagerComponent],
  template: `
    @if (tab() === 'settings') {
      <div class="ptx-card">
        <p class="ptx-muted">Every rule GWMC may change lives here. A change applies from a future date and the old value is kept. The values shipped are placeholders until GWMC confirms them.</p>

        @if (workflowValue()) {
          <div class="ptx-card" style="margin-top: 0.6rem">
            <div class="ptx-row" style="margin: 0 0 0.25rem"><b>Application workflow</b><span class="ptx-muted">Steps, SLAs and who may do each one, for every kind of application (PT-18)</span></div>
            <div class="ptx-row" style="flex-wrap: wrap; gap: 0.4rem; margin: 0.5rem 0 0.75rem">
              @for (t of workflowTypes; track t.code) {
                <button type="button" class="ptx-btn sm" [class.teal]="workflowType() === t.code" (click)="selectWorkflowType(t.code)">{{ t.label }}</button>
              }
            </div>
            <div style="display: flex; flex-direction: column; gap: 0.6rem">
              @for (s of workflowDraft(); track s.code) {
                <div class="ptx-card" style="margin: 0; padding: 0.75rem 1rem">
                  <div class="ptx-row" style="flex-wrap: wrap; gap: 0.6rem; margin: 0 0 0.5rem">
                    <span class="ptx-mono">{{ s.code }}</span>
                    <input [(ngModel)]="s.label" (ngModelChange)="workflowDirty.set(true)" [disabled]="!can('settings.manage')" aria-label="Step label" style="flex: 1; min-width: 180px" />
                    <label class="inline">SLA <input type="number" min="1" [(ngModel)]="s.slaHours" (ngModelChange)="workflowDirty.set(true)" [disabled]="!can('settings.manage')" aria-label="SLA hours" style="width: 70px" /> hrs (~{{ roundDays(s.slaHours) }} d)</label>
                    <label class="inline"><input type="checkbox" [(ngModel)]="s.enabled" (ngModelChange)="workflowDirty.set(true)" [disabled]="!can('settings.manage')" /> step runs</label>
                  </div>
                  <div style="display: flex; flex-wrap: wrap; gap: 0.6rem">
                    @for (r of WORKFLOW_ROLES; track r.code) {
                      <label class="inline"><input type="checkbox" [checked]="hasRole(s, r.code)" (change)="toggleRole(s, r.code)" [disabled]="!can('settings.manage')" /> {{ r.label }}</label>
                    }
                  </div>
                  @if (!s.roles?.length) { <small class="ptx-muted">Administrators only, until a role is picked.</small> }
                  @if (s.code === 'APPROVAL') { <small class="ptx-muted">The Commissioner can always approve, even if not picked here.</small> }
                </div>
              }
            </div>
            @if (can('settings.manage')) {
              <div class="ptx-row" style="margin-top: 0.75rem">
                <button class="ptx-btn teal" (click)="saveWorkflow()" [disabled]="!workflowDirty()">Save this application type's steps</button>
                <button class="ptx-btn" (click)="revertWorkflow()" [disabled]="!workflowDirty()">Undo changes</button>
              </div>
            }
          </div>
        }

        @for (s of settings(); track s.key) {
          @if (s.key !== 'workflow') {
          <div class="ptx-card" style="margin-top: 0.6rem">
            <div class="ptx-row" style="margin: 0"><b>{{ s.key }}</b><span class="ptx-muted">{{ s.description }}</span><span class="ptx-spacer"></span>
              @if (can('settings.manage')) { <button class="ptx-btn sm" (click)="edit(s)">Change</button> }</div>
            <pre class="ptx-mono" style="white-space: pre-wrap; overflow-x: auto; margin: 0.4rem 0">{{ pretty(s.value) }}</pre>
            @if (s.versions.length > 1) {
              <details><summary class="ptx-muted">{{ s.versions.length }} versions</summary>
                @for (v of s.versions; track $index) { <p class="ptx-muted">From {{ dmy(v.effectiveFrom) }} · {{ v.createdBy }} · {{ v.reason }}</p> }
              </details>
            }
          </div>
          }
        }
      </div>
    }

    @if (tab() === 'codes') {
      <div class="ptx-card">
        <div class="ptx-table-wrap">
          <table class="ptx-table compact">
            <thead><tr><th>List</th><th>Code</th><th>English</th><th>Telugu</th><th>Extra</th></tr></thead>
            <tbody>@for (c of codes(); track c.listName + c.code) {
              <tr><td>{{ c.listName }}</td><td><span class="ptx-mono">{{ c.code }}</span></td><td>{{ c.nameEn }}</td><td>{{ c.nameTe }}</td><td><small>{{ pretty(c.extra) }}</small></td></tr>
            }</tbody>
          </table>
        </div>
        @if (can('settings.manage')) {
          <h3 style="margin-top: 1rem">Add a code</h3>
          <div class="ptx-form">
            <label>List <select [(ngModel)]="newCode.listName"><option value="USAGE">Usage</option><option value="CONSTRUCTION">Construction</option><option value="EXEMPTION">Exemption</option><option value="TRANSFER_REASON">Transfer reason</option><option value="ROAD_CLASS">Road class</option><option value="ROOFTOP_TYPE">Rooftop installation</option></select></label>
            <label>Code <input [(ngModel)]="newCode.code" /></label>
            <label>English name <input [(ngModel)]="newCode.nameEn" /></label>
            <label>Telugu name <input [(ngModel)]="newCode.nameTe" /></label>
          </div>
          <button class="ptx-btn teal" (click)="addCode()" [disabled]="!newCode.code || !newCode.nameEn || !newCode.nameTe">Add</button>
        }
      </div>
    }

    @if (tab() === 'audit' || tab() === 'sms') {
      <div class="ptx-card flush">
        <div class="ptx-card-head"><h2>{{ tab() === 'audit' ? 'Audit trail' : 'SMS log (stand-in: messages are logged, not sent)' }}</h2>
          <button class="ptx-btn" (click)="loadLog()"><app-icon name="refresh" [size]="16"></app-icon> {{ i18n.t('refresh') }}</button></div>
        <div class="ptx-filter-bar"><div class="ptx-search"><app-icon name="search" [size]="16"></app-icon>
          <input [(ngModel)]="logSearch" (input)="onLogSearch()" placeholder="Search" aria-label="Search log" /></div></div>
        <div class="ptx-table-wrap">
          <table class="ptx-table compact">
            @if (tab() === 'audit') {
              <thead><tr><th>When</th><th>Who</th><th>Action</th><th>Before</th><th>After</th><th>IP</th></tr></thead>
              <tbody>@for (r of log(); track $index) {
                <tr><td>{{ dmy(r.at) }}</td><td>{{ r.actor }}</td><td>{{ r.action }}</td><td><small>{{ pretty(r.old) }}</small></td><td><small>{{ pretty(r.new) }}</small></td><td>{{ r.ipAddress }}</td></tr>
              } @empty { <tr><td colspan="6" class="ptx-muted">{{ i18n.t('noRecords') }}</td></tr> }</tbody>
            } @else {
              <thead><tr><th>When</th><th>To</th><th>Template</th><th>Message</th><th>Status</th></tr></thead>
              <tbody>@for (r of log(); track $index) {
                <tr><td>{{ dmy(r.at) }}</td><td>{{ r.recipient }}</td><td>{{ r.template }}</td><td><small>{{ r.messageEn }}</small></td><td>{{ r.status }}</td></tr>
              } @empty { <tr><td colspan="5" class="ptx-muted">{{ i18n.t('noRecords') }}</td></tr> }</tbody>
            }
          </table>
        </div>
        <app-ptx-pager [pager]="logPager" (changed)="loadLog()"></app-ptx-pager>
      </div>
    }

    @if (tab() === 'migration') {
      <div class="ptx-card">
        <h2>Data migration</h2>
        <p class="ptx-muted">Loads records from the old system. Each gets a UPIN and keeps its old number; records that cannot be loaded are listed below, never dropped. Paste JSON: {{ '{' }}"arrearsAsOf": "2025-04-01", "records": [...]{{ '}' }}.</p>
        <textarea [(ngModel)]="migrationJson" rows="6" style="width: 100%" placeholder='{"arrearsAsOf":"2025-04-01","records":[{"oldAssessmentNo":"...","ownerName":"...","address":"...","wardNumber":14,"siteAreaSqyd":120,"usageCode":"RESIDENTIAL","constructionCode":"RCC","builtupSqft":900,"openingArrears":0}]}'></textarea>
        <button class="ptx-btn teal" (click)="migrate()" [disabled]="!migrationJson.trim()">Load records</button>
        @if (migrationResult()) { <div class="ptx-alert info" style="margin-top: 0.6rem">{{ migrationResult() }}</div> }
        <h3 style="margin-top: 1rem">Records that could not be loaded</h3>
        @for (x of exceptions(); track x.id) { <p><b>{{ x.oldAssessmentNo }}</b>: {{ x.reason }}</p> } @empty { <p class="ptx-muted">None.</p> }
      </div>
    }

  `,
})
export class PtxAdminComponent implements OnInit {
  @Input({ required: true }) access!: PtxAccess;
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  i18n = inject(PtxI18nService);
  dmy = dmy;

  /** The part to show, chosen in the sidebar. */
  @Input() view = '';
  tab = signal<Tab>('settings');
  settings = signal<any[]>([]);
  codes = signal<any[]>([]);
  log = signal<any[]>([]);
  logPager = new Pager(10);
  logSearch = '';
  exceptions = signal<any[]>([]);
  migrationJson = '';
  migrationResult = signal('');
  newCode: any = { listName: 'USAGE', code: '', nameEn: '', nameTe: '', extra: {} };
  private timer?: ReturnType<typeof setTimeout>;

  readonly workflowTypes = CASE_TYPES;
  readonly WORKFLOW_ROLES = WORKFLOW_ROLES;
  workflowType = signal<string>('NEW_ASSESSMENT');
  workflowDraft = signal<any[]>([]);
  workflowDirty = signal(false);

  ngOnInit(): void {
    const parts: Tab[] = ['settings', 'codes', 'audit', 'sms', 'migration'];
    this.setTab(parts.includes(this.view as Tab) ? (this.view as Tab) : this.can('audit.view') && !this.can('rates.view') ? 'audit' : 'settings');
  }

  can(p: string): boolean {
    return this.access.permissions.includes(p);
  }

  pretty(v: any): string {
    return v === null || v === undefined ? '-' : JSON.stringify(v, null, 1).replace(/\n\s*/g, ' ');
  }

  private fail = (e: unknown) => this.dialog.showToast(errorText(e), 'error');

  setTab(t: Tab): void {
    this.tab.set(t);
    this.logPager.reset();
    if (t === 'settings') this.ptx.get('/admin/settings').subscribe({ next: (r) => { this.settings.set(r); this.loadWorkflowDraft(); }, error: this.fail });
    if (t === 'codes') this.loadCodes();
    if (t === 'audit' || t === 'sms') this.loadLog();
    if (t === 'migration') this.ptx.get('/migration/exceptions', { limit: 100 }).subscribe({ next: (r) => this.exceptions.set(r.items), error: this.fail });
  }

  loadCodes(): void {
    this.ptx.get('/admin/codes').subscribe({ next: (r) => this.codes.set(r), error: this.fail });
  }

  loadLog(): void {
    this.ptx.get(this.tab() === 'audit' ? '/admin/audit' : '/admin/notifications', { search: this.logSearch, ...this.logPager.query() }).subscribe({
      next: (r) => {
        this.log.set(r.items);
        this.logPager.total.set(r.total);
      },
      error: (e) => {
        this.log.set([]);
        this.fail(e);
      },
    });
  }

  onLogSearch(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.logPager.reset();
      this.loadLog();
    }, 350);
  }

  /** The full `workflow` setting value (every application type), straight from the settings list. */
  workflowValue(): any {
    return this.settings().find((s) => s.key === 'workflow')?.value ?? null;
  }

  private loadWorkflowDraft(): void {
    const steps = this.workflowValue()?.[this.workflowType()];
    this.workflowDraft.set(steps ? JSON.parse(JSON.stringify(steps)) : []);
    this.workflowDirty.set(false);
  }

  async selectWorkflowType(code: string): Promise<void> {
    if (this.workflowDirty() && !(await this.dialog.confirm("Discard the unsaved changes to this application type's steps?"))) return;
    this.workflowType.set(code);
    this.loadWorkflowDraft();
  }

  hasRole(step: any, role: string): boolean {
    return (step.roles || []).includes(role);
  }

  toggleRole(step: any, role: string): void {
    const roles: string[] = step.roles || (step.roles = []);
    const i = roles.indexOf(role);
    if (i >= 0) roles.splice(i, 1);
    else roles.push(role);
    this.workflowDirty.set(true);
  }

  roundDays(hours: number): number {
    return Math.round(((hours || 0) / 24) * 10) / 10;
  }

  revertWorkflow(): void {
    this.loadWorkflowDraft();
  }

  async saveWorkflow(): Promise<void> {
    for (const s of this.workflowDraft()) {
      if (!s.label?.trim()) {
        this.dialog.showToast('Every step needs a label.', 'error');
        return;
      }
      if (!s.slaHours || s.slaHours <= 0) {
        this.dialog.showToast('Every step needs an SLA of at least 1 hour.', 'error');
        return;
      }
    }
    const from = await this.dialog.prompt({ title: 'From which date?', inputLabel: 'Effective from (YYYY-MM-DD, today or later)', initialValue: todayIso(), required: true });
    if (!from) return;
    const reason = await this.dialog.prompt({ title: 'Why?', inputLabel: 'Reason / order no.', required: true });
    if (!reason) return;
    const full = { ...this.workflowValue(), [this.workflowType()]: this.workflowDraft() };
    this.ptx.post('/admin/settings', { key: 'workflow', value: full, effectiveFrom: from, reason }).subscribe({
      next: (r) => {
        this.dialog.showToast(r.message, 'success');
        this.setTab('settings');
      },
      error: this.fail,
    });
  }

  async edit(s: any): Promise<void> {
    const text = await this.dialog.prompt({ title: `Change ${s.key}`, message: s.description + ' Enter the new value as JSON.', inputLabel: 'New value (JSON)', initialValue: JSON.stringify(s.value), required: true });
    if (text === null) return;
    let value: any;
    try {
      value = JSON.parse(text);
    } catch {
      this.dialog.showToast('That is not valid JSON. Check the brackets and quotes.', 'error');
      return;
    }
    const from = await this.dialog.prompt({ title: 'From which date?', inputLabel: 'Effective from (YYYY-MM-DD, today or later)', initialValue: todayIso(), required: true });
    if (!from) return;
    const reason = await this.dialog.prompt({ title: 'Why?', inputLabel: 'Reason / order no.', required: true });
    if (!reason) return;
    this.ptx.post('/admin/settings', { key: s.key, value, effectiveFrom: from, reason }).subscribe({
      next: (r) => {
        this.dialog.showToast(r.message, 'success');
        this.setTab('settings');
      },
      error: this.fail,
    });
  }

  addCode(): void {
    this.ptx.post('/admin/codes', this.newCode).subscribe({
      next: (r) => {
        this.dialog.showToast(r.message, 'success');
        this.newCode = { listName: this.newCode.listName, code: '', nameEn: '', nameTe: '', extra: {} };
        this.loadCodes();
      },
      error: this.fail,
    });
  }

  migrate(): void {
    let body: any;
    try {
      body = JSON.parse(this.migrationJson);
    } catch {
      this.dialog.showToast('That is not valid JSON.', 'error');
      return;
    }
    this.ptx.post('/migration/properties', body).subscribe({
      next: (r) => {
        this.migrationResult.set(`${r.created.length} loaded, ${r.exceptions.length} could not be loaded, ${r.locationPending} still need a map location.`);
        this.setTab('migration');
      },
      error: this.fail,
    });
  }
}
