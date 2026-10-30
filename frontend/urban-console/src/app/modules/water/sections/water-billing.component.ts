import { ChangeDetectorRef, Component, Input, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouteProgress, WaterAccess, WaterBill } from '../../../core/models/water.model';
import { WaterService } from '../../../core/services/water.service';
import { WaterI18nService } from '../../../core/services/water-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { WaterDocumentComponent } from '../water-document.component';
import { downloadCsv, dmy, errorText } from '../water-utils';

/** Bill generation (WB-23), printable bills (WB-24, WB-25), corrections (WB-26), tariffs (WB-20, WB-21, WB-22). */
@Component({
  selector: 'app-water-billing',
  standalone: true,
  imports: [CommonModule, FormsModule, WaterDocumentComponent],
  templateUrl: './water-billing.component.html',
})
export class WaterBillingComponent implements OnInit {
  @Input() access!: WaterAccess;
  private water = inject(WaterService);
  private dialog = inject(DialogService);
  private cdr = inject(ChangeDetectorRef);
  i18n = inject(WaterI18nService);
  dmy = dmy;

  view = signal<'bills' | 'run' | 'tariffs'>('bills');
  cycle = '';
  billDate = '';
  routes = signal<RouteProgress[]>([]);
  pickedRoutes: { [id: string]: boolean } = {};
  runResult = signal<any>(null);
  runs = signal<any[]>([]);
  running = signal(false);

  billQuery = { cycle: '', q: '' };
  bills = signal<WaterBill[]>([]);
  doc = signal<WaterBill | null>(null);

  tariffs = signal<any[]>([]);
  proposal: any = {};
  calc: any = { categoryCode: 'DOMESTIC', consumptionKl: 20, isMetered: true, pipeSizeMm: 15 };
  calcResult = signal<any>(null);

  ngOnInit(): void {
    this.resetProposal();
    this.water.get('/cycles/current').subscribe((c) => {
      this.cycle = c.cycle;
      this.billQuery.cycle = c.cycle;
      this.cdr.markForCheck();
      this.loadBills();
      this.water.routes(c.cycle).subscribe((r) => this.routes.set(r));
    });
    this.loadRuns();
    this.loadTariffs();
  }

  can(p: string): boolean {
    return this.access.permissions.includes(p);
  }

  loadRuns(): void {
    this.water.get('/billing/runs').subscribe({ next: (r) => this.runs.set(r), error: () => this.runs.set([]) });
  }

  async run(): Promise<void> {
    const routeIds = Object.keys(this.pickedRoutes).filter((k) => this.pickedRoutes[k]);
    const ok = await this.dialog.confirm({
      title: this.i18n.t('runBilling'),
      message: `Generate bills for cycle ${this.cycle} on ${routeIds.length ? routeIds.length + ' route(s)' : 'all routes and unrouted connections'}? ` +
        'Connections already billed for this cycle are skipped; held readings stay held.',
      confirmText: this.i18n.t('runBilling'),
    });
    if (!ok) return;
    this.running.set(true);
    this.water.post('/billing/run', { cycle: this.cycle, routeIds, billDate: this.billDate || null }).subscribe({
      next: (r) => {
        this.running.set(false);
        this.runResult.set(r);
        this.dialog.showToast(`${r.billsRaised} bill(s) raised, ${r.held.length} held`, r.held.length ? 'warning' : 'success');
        this.loadRuns();
        this.loadBills();
      },
      error: (e) => {
        this.running.set(false);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  loadBills(): void {
    this.water.get<WaterBill[]>('/bills', { cycle: this.billQuery.cycle, q: this.billQuery.q, limit: 500 }).subscribe({
      next: (b) => this.bills.set(b),
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  exportBills(): void {
    downloadCsv(`water-bills-${this.billQuery.cycle || 'all'}`, this.bills(), [
      { key: 'billNo', label: 'Bill no' }, { key: 'consumerNo', label: 'Consumer no' }, { key: 'consumerName', label: 'Name' },
      { key: 'cycle', label: 'Cycle' }, { key: 'basis', label: 'Basis' }, { key: 'consumptionKl', label: 'kL' },
      { key: 'currentDemand', label: 'Current demand' }, { key: 'arrears', label: 'Arrears' }, { key: 'penalty', label: 'Penalty' },
      { key: 'totalPayable', label: 'Total payable' }, { key: 'dueDate', label: 'Due date' },
    ]);
  }

  showBill(b: WaterBill): void {
    this.water.bill(b.billNo).subscribe({ next: (full) => this.doc.set(full), error: (e) => this.dialog.showToast(errorText(e), 'error') });
  }

  loadTariffs(): void {
    this.water.get('/tariffs').subscribe({ next: (t) => this.tariffs.set(t), error: (e) => this.dialog.showToast(errorText(e), 'error') });
  }

  resetProposal(): void {
    this.proposal = { categoryCode: 'DOMESTIC', effectiveFrom: '', slabs: [{ uptoKl: 15, ratePerKl: 7 }, { uptoKl: null, ratePerKl: 20 }],
      flat: [{ size: 15, rate: 150 }], minimumCharge: 0, fixedCharge: 0, cessPercent: 0, freeAllowanceKl: 0, orderReference: '', reason: '' };
  }

  copyTariff(t: any): void {
    this.proposal = { categoryCode: t.categoryCode, effectiveFrom: '', slabs: t.slabs.map((s: any) => ({ ...s })),
      flat: Object.keys(t.flatRates).map((k) => ({ size: Number(k), rate: t.flatRates[k] })), minimumCharge: t.minimumCharge,
      fixedCharge: t.fixedCharge, cessPercent: t.cessPercent, freeAllowanceKl: t.freeAllowanceKl, orderReference: '', reason: '' };
  }

  propose(): void {
    const p = this.proposal;
    const flatRates: { [k: string]: number } = {};
    p.flat.filter((f: any) => f.size).forEach((f: any) => (flatRates[String(f.size)] = Number(f.rate)));
    const body = { categoryCode: p.categoryCode, effectiveFrom: p.effectiveFrom, reason: p.reason, orderReference: p.orderReference || null,
      slabs: p.slabs.map((s: any) => ({ uptoKl: s.uptoKl === '' || s.uptoKl === null ? null : Number(s.uptoKl), ratePerKl: Number(s.ratePerKl) })),
      flatRates, minimumCharge: Number(p.minimumCharge), fixedCharge: Number(p.fixedCharge), cessPercent: Number(p.cessPercent),
      freeAllowanceKl: Number(p.freeAllowanceKl) };
    this.water.post('/tariffs', body).subscribe({
      next: (t) => {
        this.dialog.showToast(`${t.categoryCode} v${t.version} sent for the Commissioner's approval`, 'success');
        this.resetProposal();
        this.loadTariffs();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  calculate(): void {
    this.water.post('/tariffs/preview', { ...this.calc, consumptionKl: Number(this.calc.consumptionKl), pipeSizeMm: Number(this.calc.pipeSizeMm) }).subscribe({
      next: (r) => this.calcResult.set(r),
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }
}
