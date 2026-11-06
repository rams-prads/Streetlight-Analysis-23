import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { PtxAccess } from '../../../core/models/ptx.model';
import { PtxService } from '../../../core/services/ptx.service';
import { PtxI18nService } from '../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { PtxPagerComponent } from '../shared/ptx-pager.component';
import { Pager, dmy, downloadCsv, errorText, todayIso } from '../ptx-utils';

type Tab = 'dcb' | 'efficiency' | 'daily' | 'heads';

/** DCB register (PT-60), collection efficiency against targets (PT-61), daily collection (PT-62) and account heads (PT-66). */
@Component({
  selector: 'app-ptx-reports',
  standalone: true,
  imports: [CommonModule, FormsModule, PtxPagerComponent],
  template: `
    @if (tab() === 'dcb') {
      <div class="ptx-card flush">
        <div class="ptx-card-head">
          <div><h2>Demand, collection and balance (DCB)</h2><p class="ptx-muted">Opening balance + demand − collection = closing balance, for any period.</p></div>
          <button class="ptx-btn" (click)="exportDcb()" [disabled]="!dcbRows().length">{{ i18n.t('exportCsv') }}</button>
        </div>
        <div class="ptx-filter-bar">
          <div class="ptx-filters">
            <select [(ngModel)]="dcb.level" (change)="dcbPager.reset(); loadDcb()" aria-label="Level">
              <option value="city">Whole city</option><option value="zone">By zone</option><option value="ward">By ward</option><option value="property">By property</option>
            </select>
            <input type="date" [(ngModel)]="dcb.from" (change)="loadDcb()" aria-label="From" />
            <input type="date" [(ngModel)]="dcb.to" (change)="loadDcb()" aria-label="To" />
            <select [(ngModel)]="dcb.wardId" (change)="dcbPager.reset(); loadDcb()" aria-label="Ward">
              <option value="">{{ i18n.t('ward') }}: {{ i18n.t('all') }}</option>
              @for (w of access.wards; track w.wardId) { <option [value]="w.wardId">{{ w.wardNumber }} · {{ w.wardName }}</option> }
            </select>
          </div>
        </div>
        <div class="ptx-table-wrap">
          <table class="ptx-table">
            <thead><tr><th>Name</th><th class="num">Opening</th><th class="num">Demand</th><th class="num">Collection</th><th class="num">Adjustments</th><th class="num">Closing</th><th class="num">Efficiency</th></tr></thead>
            <tbody>
              @for (r of dcbRows(); track $index) {
                <tr><td>{{ r.name }}</td><td class="num">{{ r.opening | number: '1.2-2' }}</td><td class="num">{{ r.demand | number: '1.2-2' }}</td>
                  <td class="num">{{ r.collection | number: '1.2-2' }}</td><td class="num">{{ r.adjustments | number: '1.2-2' }}</td>
                  <td class="num"><b>{{ r.closing | number: '1.2-2' }}</b></td><td class="num">{{ r.efficiencyPercent ?? '-' }}{{ r.efficiencyPercent !== null && r.efficiencyPercent !== undefined ? '%' : '' }}</td></tr>
              } @empty { <tr><td colspan="7" class="ptx-muted">{{ i18n.t('noRecords') }}</td></tr> }
            </tbody>
            @if (dcbTotals(); as t) {
              <tfoot><tr><td>Total</td><td class="num">{{ t.opening | number: '1.2-2' }}</td><td class="num">{{ t.demand | number: '1.2-2' }}</td><td class="num">{{ t.collection | number: '1.2-2' }}</td>
                <td class="num">{{ t.adjustments | number: '1.2-2' }}</td><td class="num">{{ t.closing | number: '1.2-2' }}</td><td class="num">{{ t.efficiencyPercent ?? '-' }}%</td></tr></tfoot>
            }
          </table>
        </div>
        <app-ptx-pager [pager]="dcbPager" (changed)="loadDcb()"></app-ptx-pager>
        <p class="ptx-muted" style="padding: 0 1rem 1rem">{{ dcbNote() }}</p>
      </div>
    }

    @if (tab() === 'efficiency') {
      <div class="ptx-card">
        <div class="ptx-row">
          @if (hasFullReports()) {
            <label>By <select [(ngModel)]="eff.by" (change)="loadEff()"><option value="ward">Ward</option><option value="zone">Zone</option><option value="collector">Collector</option></select></label>
          }
          <label>Period <select [(ngModel)]="eff.view" (change)="loadEff()"><option value="DAY">Day</option><option value="MONTH">Month</option><option value="YTD">Year to date</option></select></label>
          <label>Date <input type="date" [(ngModel)]="eff.date" (change)="loadEff()" /></label>
        </div>
        <div class="ptx-table-wrap">
          <table class="ptx-table">
            <thead><tr><th>Name</th><th class="num">Due</th><th class="num">Collected</th><th>Efficiency</th><th class="num">Target</th><th>Target achieved</th></tr></thead>
            <tbody>
              @for (r of effRows(); track $index) {
                <tr><td>{{ r.name }}</td><td class="num">₹{{ r.due | number: '1.0-0' }}</td><td class="num">₹{{ r.collection | number: '1.0-0' }}</td>
                  <td style="min-width: 130px">{{ r.efficiencyPercent ?? 0 }}%<div class="ptx-bar"><i [style.width.%]="(r.efficiencyPercent || 0) > 100 ? 100 : (r.efficiencyPercent || 0)"></i></div></td>
                  <td class="num">{{ r.target ? '₹' + (r.target | number: '1.0-0') : '-' }}</td>
                  <td style="min-width: 130px">@if (r.achievementPercent !== null && r.achievementPercent !== undefined) { {{ r.achievementPercent }}%<div class="ptx-bar"><i [style.width.%]="r.achievementPercent > 100 ? 100 : r.achievementPercent"></i></div> } @else { - }</td></tr>
              } @empty { <tr><td colspan="6" class="ptx-muted">{{ i18n.t('noRecords') }}</td></tr> }
            </tbody>
          </table>
        </div>
      </div>
    }

    @if (tab() === 'daily') {
      <div class="ptx-card">
        <div class="ptx-row"><label>Date <input type="date" [(ngModel)]="dailyDate" (change)="loadDaily()" /></label></div>
        @if (daily(); as d) {
          <div class="ptx-kpis">
            <div class="ptx-kpi good"><span>Collected</span><b>₹{{ d.total | number: '1.2-2' }}</b></div>
            <div class="ptx-kpi"><span>Receipts</span><b>{{ d.receipts }}</b></div>
            <div class="ptx-kpi" [class.warn]="d.cancelledOrReturned"><span>Cancelled / returned</span><b>{{ d.cancelledOrReturned }}</b></div>
          </div>
          <div class="ptx-grid three" style="margin-top: 0.8rem">
            @for (g of groups(d); track g.title) {
              <div class="ptx-card"><h3>{{ g.title }}</h3>
                @for (r of g.rows; track r.name) { <p>{{ r.name }}: <b>₹{{ r.amount | number: '1.2-2' }}</b> <small class="ptx-muted">({{ r.receipts }} receipts)</small></p> } @empty { <p class="ptx-muted">-</p> }
              </div>
            }
          </div>
        }
      </div>
    }

    @if (tab() === 'heads') {
      <div class="ptx-card">
        <div class="ptx-row"><label>Month <input type="month" [(ngModel)]="headsMonth" (change)="loadHeads()" /></label>
          <button class="ptx-btn" (click)="exportHeads()" [disabled]="!(heads()?.rows?.length)">{{ i18n.t('exportCsv') }}</button></div>
        @if (heads(); as h) {
          <p class="ptx-muted">{{ h.period }} · {{ h.note }}</p>
          <div class="ptx-table-wrap">
            <table class="ptx-table compact">
              <thead><tr><th>Account head</th><th>Covers</th><th class="num">Demand</th><th class="num">Collection</th><th class="num">Rebates</th><th class="num">Refunds</th><th class="num">Waivers</th><th class="num">Write-offs</th><th class="num">Adjustments</th><th class="num">Opening arrears</th></tr></thead>
              <tbody>
                @for (r of h.rows; track r.accountHead) {
                  <tr><td><span class="ptx-mono">{{ r.accountHead }}</span></td><td>{{ r.components.join(', ') }}</td>
                    <td class="num">{{ r.demand | number: '1.2-2' }}</td><td class="num">{{ r.collection | number: '1.2-2' }}</td><td class="num">{{ r.rebates | number: '1.2-2' }}</td>
                    <td class="num">{{ r.refunds | number: '1.2-2' }}</td><td class="num">{{ r.waivers | number: '1.2-2' }}</td><td class="num">{{ r.writeOffs | number: '1.2-2' }}</td>
                    <td class="num">{{ r.adjustments | number: '1.2-2' }}</td><td class="num">{{ r.openingArrears | number: '1.2-2' }}</td></tr>
                } @empty { <tr><td colspan="10" class="ptx-muted">{{ i18n.t('noRecords') }}</td></tr> }
              </tbody>
            </table>
          </div>
        }
      </div>
    }
  `,
})
export class PtxReportsComponent implements OnInit {
  @Input({ required: true }) access!: PtxAccess;
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  i18n = inject(PtxI18nService);
  dmy = dmy;

  /** The part to show, chosen in the sidebar. */
  @Input() view = '';
  tab = signal<Tab>('dcb');
  dcb = { level: 'ward', from: '', to: todayIso(), wardId: '' };
  dcbRows = signal<any[]>([]);
  dcbTotals = signal<any | null>(null);
  dcbNote = signal('');
  dcbPager = new Pager(10);
  eff = { by: 'ward', view: 'YTD', date: todayIso() };
  effRows = signal<any[]>([]);
  dailyDate = todayIso();
  daily = signal<any | null>(null);
  headsMonth = todayIso().slice(0, 7);
  heads = signal<any | null>(null);

  ngOnInit(): void {
    const d = new Date();
    this.dcb.from = `${d.getMonth() >= 3 ? d.getFullYear() : d.getFullYear() - 1}-04-01`;
    if (!this.hasFullReports()) this.eff.by = 'collector';
    this.setTab((['dcb', 'efficiency', 'daily', 'heads'] as Tab[]).includes(this.view as Tab) ? (this.view as Tab) : (this.hasFullReports() ? 'dcb' : 'efficiency'));
  }

  /** The full Reports section (DCB, account heads, every ward/zone/collector) vs. a collector's own numbers only. */
  hasFullReports(): boolean {
    return this.access.permissions.includes('reports.view');
  }

  setTab(t: Tab): void {
    this.tab.set(t);
    if (t === 'dcb') this.loadDcb();
    if (t === 'efficiency') this.loadEff();
    if (t === 'daily') this.loadDaily();
    if (t === 'heads') this.loadHeads();
  }

  private fail = (e: unknown) => this.dialog.showToast(errorText(e), 'error');

  loadDcb(): void {
    this.ptx.get('/reports/dcb', { ...this.dcb, ...this.dcbPager.query() }).subscribe({
      next: (r) => {
        const rows = r.rows?.items ?? r.rows ?? [];
        this.dcbRows.set(rows);
        this.dcbPager.total.set(r.rows?.total ?? rows.length);
        this.dcbTotals.set(r.totals);
        this.dcbNote.set(r.note || '');
      },
      error: (e) => {
        this.dcbRows.set([]);
        this.fail(e);
      },
    });
  }

  exportDcb(): void {
    downloadCsv(`ptx-dcb-${this.dcb.level}-${todayIso()}`, this.dcbRows(), [
      { key: 'name', label: 'Name' }, { key: 'opening', label: 'Opening' }, { key: 'demand', label: 'Demand' }, { key: 'collection', label: 'Collection' },
      { key: 'adjustments', label: 'Adjustments' }, { key: 'closing', label: 'Closing' }, { key: 'efficiencyPercent', label: 'Efficiency %' },
    ]);
  }

  loadEff(): void {
    this.ptx.get('/reports/efficiency', this.eff).subscribe({ next: (r) => this.effRows.set(r.rows), error: (e) => { this.effRows.set([]); this.fail(e); } });
  }

  loadDaily(): void {
    this.ptx.get('/reports/daily-collection', { date: this.dailyDate }).subscribe({ next: (r) => this.daily.set(r), error: (e) => { this.daily.set(null); this.fail(e); } });
  }

  groups(d: any): { title: string; rows: any[] }[] {
    return [{ title: 'By channel', rows: d.byChannel }, { title: 'By payment mode', rows: d.byMode }, { title: 'By collector', rows: d.byCollector }];
  }

  loadHeads(): void {
    this.ptx.get('/reports/account-heads', { month: this.headsMonth }).subscribe({ next: (r) => this.heads.set(r), error: (e) => { this.heads.set(null); this.fail(e); } });
  }

  exportHeads(): void {
    downloadCsv(`ptx-account-heads-${this.headsMonth}`, this.heads().rows, [
      { key: 'accountHead', label: 'Account head' }, { key: 'demand', label: 'Demand' }, { key: 'collection', label: 'Collection' }, { key: 'rebates', label: 'Rebates' },
      { key: 'refunds', label: 'Refunds' }, { key: 'waivers', label: 'Waivers' }, { key: 'writeOffs', label: 'Write-offs' }, { key: 'adjustments', label: 'Adjustments' },
      { key: 'openingArrears', label: 'Opening arrears' },
    ]);
  }
}
