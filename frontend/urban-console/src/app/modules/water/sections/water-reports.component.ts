import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { WaterAccess } from '../../../core/models/water.model';
import { WaterService } from '../../../core/services/water.service';
import { WaterI18nService } from '../../../core/services/water-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { CsvColumn, downloadCsv, dmy, errorText, printArea, saveBlob, todayIso } from '../water-utils';

interface ReportDef {
  key: string;
  label: string;
}

/** Reports (WB-62, WB-63, WB-65), consumption analysis (WB-54, WB-55), exports to Excel / PDF (WB-66) and register export (WB-IR-04). */
@Component({
  selector: 'app-water-reports',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './water-reports.component.html',
})
export class WaterReportsComponent implements OnInit {
  @Input() access!: WaterAccess;
  private water = inject(WaterService);
  private dialog = inject(DialogService);
  i18n = inject(WaterI18nService);
  dmy = dmy;

  reports: ReportDef[] = [
    { key: 'dcb', label: 'DCB register' },
    { key: 'billing', label: 'Billing' },
    { key: 'reading', label: 'Reading completion' },
    { key: 'meter', label: 'Meter status' },
    { key: 'disconnections', label: 'Disconnections & reconnections' },
    { key: 'complaints', label: 'Complaint SLA' },
    { key: 'heads', label: 'Account-head summary' },
    { key: 'analysis', label: 'Consumption analysis' },
    { key: 'register', label: 'Register export & schedules' },
  ];
  current = signal<string>('dcb');
  data = signal<any>(null);
  loading = signal(false);
  q = { from: '', to: todayIso(), groupBy: 'ward', cycle: '', day: todayIso(), month: todayIso().slice(0, 7), headsMode: 'day' };
  schedule = signal<any[]>([]);

  ngOnInit(): void {
    const d = new Date();
    const fy = d.getMonth() >= 3 ? d.getFullYear() : d.getFullYear() - 1;
    this.q.from = `${fy}-04-01`;
    this.run();
  }

  pick(key: string): void {
    this.current.set(key);
    this.data.set(null);
    this.run();
  }

  run(): void {
    const k = this.current();
    const paths: { [key: string]: [string, any] } = {
      dcb: ['/reports/dcb', { from: this.q.from, to: this.q.to, groupBy: this.q.groupBy }],
      billing: ['/reports/billing', { cycle: this.q.cycle }],
      reading: ['/reports/reading-completion', { cycle: this.q.cycle }],
      meter: ['/reports/meter-status', {}],
      disconnections: ['/reports/disconnections', { from: this.q.from, to: this.q.to }],
      complaints: ['/reports/complaint-sla', { from: this.q.from, to: this.q.to }],
      heads: ['/reports/account-heads', this.q.headsMode === 'day' ? { day: this.q.day } : { month: this.q.month }],
      analysis: ['/analysis/consumption', {}],
    };
    if (k === 'register') {
      this.water.get('/admin/settings').subscribe({
        next: (s: any[]) => this.schedule.set(s.find((x) => x.key === 'reports.schedule')?.value || []),
        error: () => this.schedule.set([]),
      });
      return;
    }
    const [path, params] = paths[k];
    this.loading.set(true);
    this.water.get(path, params).subscribe({
      next: (d) => {
        this.data.set(d);
        this.loading.set(false);
      },
      error: (e) => {
        this.loading.set(false);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  private table(): { rows: any[]; cols: CsvColumn[] } {
    const d = this.data();
    const k = this.current();
    if (!d) return { rows: [], cols: [] };
    if (k === 'dcb') return { rows: [...d.rows, { wardName: 'TOTAL', ...d.totals }], cols: [
      { key: this.q.groupBy === 'zone' ? 'zoneName' : 'wardNumber', label: this.q.groupBy === 'zone' ? 'Zone' : 'Ward' }, { key: 'wardName', label: 'Name' },
      { key: 'opening', label: 'Opening' }, { key: 'demand', label: 'Demand' }, { key: 'collection', label: 'Collection' },
      { key: 'adjustments', label: 'Adjustments' }, { key: 'closing', label: 'Closing balance' }, { key: 'efficiencyPercent', label: 'Efficiency %' }] };
    if (k === 'billing') return { rows: d.rows, cols: [{ key: 'wardNumber', label: 'Ward' }, { key: 'wardName', label: 'Name' }, { key: 'bills', label: 'Bills' },
      { key: 'ACTUAL', label: 'Actual' }, { key: 'AVERAGE', label: 'Average' }, { key: 'FLAT', label: 'Flat' }, { key: 'consumptionKl', label: 'kL' }, { key: 'demand', label: 'Demand' }] };
    if (k === 'reading') return { rows: d.byRoute, cols: [{ key: 'code', label: 'Route' }, { key: 'readerUsername', label: 'Reader' },
      { key: 'totalConnections', label: 'Connections' }, { key: 'read', label: 'Read' }, { key: 'noReading', label: 'No reading' },
      { key: 'pendingReview', label: 'To review' }, { key: 'remaining', label: 'Remaining' }, { key: 'completionPercent', label: '%' }] };
    if (k === 'meter') return { rows: d.faulty, cols: [{ key: 'consumerNo', label: 'Consumer' }, { key: 'serialNo', label: 'Serial' }, { key: 'make', label: 'Make' }, { key: 'sizeMm', label: 'mm' }] };
    if (k === 'complaints') return { rows: d.rows, cols: [{ key: 'type', label: 'Type' }, { key: 'raised', label: 'Raised' }, { key: 'closed', label: 'Closed' },
      { key: 'closedWithinSla', label: 'Closed within SLA' }, { key: 'openWithinSla', label: 'Open within SLA' }, { key: 'openPastSla', label: 'Open past SLA' },
      { key: 'avgResolutionHours', label: 'Avg hours' }, { key: 'slaCompliancePercent', label: 'SLA %' }] };
    if (k === 'heads') return { rows: [...d.rows, { accountHead: 'TOTAL', ...d.totals }], cols: [{ key: 'accountHead', label: 'Account head' }, { key: 'components', label: 'Components' },
      { key: 'demand', label: 'Demand' }, { key: 'collection', label: 'Collection' }, { key: 'refunds', label: 'Refunds' }, { key: 'waivers', label: 'Waivers' },
      { key: 'writeOffs', label: 'Write-offs' }, { key: 'adjustments', label: 'Adjustments' }, { key: 'openingArrears', label: 'Opening arrears' }] };
    if (k === 'disconnections') return { rows: Object.keys(d).filter((x) => !['from', 'to'].includes(x)).map((x) => ({ measure: x, value: d[x] })),
      cols: [{ key: 'measure', label: 'Measure' }, { key: 'value', label: 'Value' }] };
    if (k === 'analysis') return { rows: [
      ...d.zeroConsumption.map((r: any) => ({ check: 'Zero consumption', ...r })),
      ...d.suddenChange.map((r: any) => ({ check: `Sudden ${r.direction.toLowerCase()}`, ...r })),
      ...d.peerOutliers.map((r: any) => ({ check: 'Peer outlier', ...r }))],
      cols: [{ key: 'check', label: 'Check' }, { key: 'consumerNo', label: 'Consumer' }, { key: 'consumerName', label: 'Name' }, { key: 'category', label: 'Category' },
        { key: 'wardNumber', label: 'Ward' }, { key: 'cycle', label: 'Cycle' }, { key: 'latestKl', label: 'Latest kL' }, { key: 'consumptionKl', label: 'kL' },
        { key: 'usualKl', label: 'Usual kL' }, { key: 'peerAverageKl', label: 'Peer avg kL' }, { key: 'changePercent', label: 'Change %' }] };
    return { rows: [], cols: [] };
  }

  exportCsv(): void {
    const t = this.table();
    downloadCsv(`water-${this.current()}-${todayIso()}`, t.rows, t.cols);
  }

  print(): void {
    printArea();
  }

  exportRegister(fmt: 'csv' | 'json'): void {
    if (fmt === 'csv') {
      this.water.getBlob('/export/connections?format=csv').subscribe({
        next: (b) => saveBlob(b, `water-connection-register-${todayIso()}.csv`),
        error: (e) => this.dialog.showToast(errorText(e), 'error'),
      });
    } else {
      this.water.get('/export/connections', { format: 'json' }).subscribe({
        next: (d) => saveBlob(new Blob([JSON.stringify(d, null, 2)], { type: 'application/json' }), `water-connection-register-${todayIso()}.json`),
        error: (e) => this.dialog.showToast(errorText(e), 'error'),
      });
    }
  }

  keys(o: any): string[] {
    return Object.keys(o || {});
  }

  title(): string {
    return this.reports.find((r) => r.key === this.current())?.label || '';
  }
}
