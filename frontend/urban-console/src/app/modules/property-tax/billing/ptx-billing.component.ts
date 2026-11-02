import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DemandNotice, DemandRow, PtxAccess, RateTable } from '../../../core/models/ptx.model';
import { PtxService } from '../../../core/services/ptx.service';
import { PtxI18nService } from '../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { IconComponent } from '../../../shared/components/icon/icon.component';
import { PtxPagerComponent } from '../shared/ptx-pager.component';
import { PtxDocumentComponent } from '../shared/ptx-document.component';
import { RateTableDialogComponent } from './dialogs/rate-table-dialog/rate-table-dialog.component';
import { BillingRunDialogComponent } from './dialogs/billing-run-dialog/billing-run-dialog.component';
import { BillBatchDialogComponent } from './dialogs/bill-batch-dialog/bill-batch-dialog.component';
import { Pager, dmy, errorText, periodName, periodsBack } from '../ptx-utils';

type Tab = 'bills' | 'rates' | 'jobs';

/** Rate tables with versions (PT-10), raising bills by period (PT-30), general revision (PT-15) and the bills list. */
@Component({
  selector: 'app-ptx-billing',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent, PtxPagerComponent, PtxDocumentComponent, RateTableDialogComponent, BillingRunDialogComponent, BillBatchDialogComponent],
  templateUrl: './ptx-billing.component.html',
})
export class PtxBillingComponent implements OnInit {
  @Input({ required: true }) access!: PtxAccess;
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  i18n = inject(PtxI18nService);
  dmy = dmy;
  periodName = periodName;

  /** The part to show, chosen in the sidebar. */
  @Input() view = '';
  tab = signal<Tab>('bills');
  periods: string[] = [];
  filters = { search: '', period: '', wardId: '', delivery: '' };
  summary = signal<{ PENDING: number; DELIVERED: number; NOT_DELIVERED: number; total: number } | null>(null);
  batchOpen = signal(false);
  bills = signal<DemandRow[]>([]);
  billPager = new Pager(10);
  doc = signal<DemandNotice | null>(null);
  tables = signal<RateTable[]>([]);
  viewTable = signal<RateTable | null>(null);
  jobs = signal<any[]>([]);
  jobPager = new Pager(10);
  rateDialog = signal(false);
  runDialog = signal<'DEMAND' | 'REVISION' | null>(null);
  loading = signal(false);
  private searchTimer?: ReturnType<typeof setTimeout>;

  ngOnInit(): void {
    this.periods = periodsBack(this.access.currentPeriod, 6);
    this.filters.period = this.access.currentPeriod;
    this.setTab((['bills', 'rates', 'jobs'] as Tab[]).includes(this.view as Tab) ? (this.view as Tab) : 'bills');
  }

  can(p: string): boolean {
    return this.access.permissions.includes(p);
  }

  setTab(t: Tab): void {
    this.tab.set(t);
    if (t === 'bills') this.loadBills();
    if (t === 'rates') this.loadTables();
    if (t === 'jobs') this.loadJobs();
  }

  onSearchInput(): void {
    if (this.searchTimer) clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => this.applyFilters(), 350);
  }

  applyFilters(): void {
    this.billPager.reset();
    this.loadBills();
  }

  loadSummary(): void {
    if (!this.filters.period) {
      this.summary.set(null);
      return;
    }
    this.ptx.get('/demands/delivery-summary', { period: this.filters.period, wardId: this.filters.wardId }).subscribe({
      next: (s) => this.summary.set(s),
      error: () => this.summary.set(null),
    });
  }

  loadBills(): void {
    this.loadSummary();
    this.loading.set(true);
    this.ptx.get('/demands', { ...this.filters, ...this.billPager.query() }).subscribe({
      next: (r) => {
        this.bills.set(r.items);
        this.billPager.total.set(r.total);
        this.loading.set(false);
      },
      error: (e) => {
        this.bills.set([]);
        this.billPager.total.set(0);
        this.loading.set(false);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  showBill(no: string): void {
    this.ptx.get<DemandNotice>(`/demands/${encodeURIComponent(no)}`).subscribe({
      next: (d) => this.doc.set(d),
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  async correct(b: { demandNo: string }): Promise<void> {
    const amount = await this.dialog.prompt({ title: `Correct bill ${b.demandNo}`, message: 'A plus raises the bill and a minus lowers it. The bill itself is not edited: the correction is a separate entry that the Commissioner or Revenue Officer approves.',
      inputLabel: 'Amount in ₹ (minus lowers the bill)', placeholder: '-120.50', required: true });
    if (amount === null) return;
    const reason = await this.dialog.prompt({ title: 'Why is the bill being corrected?', inputLabel: 'Reason', required: true });
    if (!reason) return;
    this.ptx.post(`/demands/${encodeURIComponent(b.demandNo)}/corrections`, { amount: Number(amount), reason }).subscribe({
      next: (r) => this.dialog.showToast(`Sent for approval: the bill would go from ₹${r.billNow} to ₹${r.billAfter}.`, 'success'),
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  loadTables(): void {
    this.ptx.get<RateTable[]>('/rate-tables').subscribe({
      next: (t) => this.tables.set(t),
      error: (e) => {
        this.tables.set([]);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  loadJobs(): void {
    this.ptx.get('/jobs', this.jobPager.query()).subscribe({
      next: (r) => {
        this.jobs.set(r.items);
        this.jobPager.total.set(r.total);
      },
      error: (e) => {
        this.jobs.set([]);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  inForce(): RateTable | undefined {
    return this.tables().find((t) => t.inForce);
  }

  taxRates(t: RateTable): { k: string; v: number }[] {
    const r = t.rules?.taxRatePercentOfArv || {};
    return Object.keys(r).map((k) => ({ k, v: r[k] }));
  }

  zoneNames(t: RateTable): string[] {
    return Object.keys(t.rules?.monthlyRentalValuePerSqft || {});
  }

  usageName(code: string): string {
    return this.i18n.name(this.access.codes.USAGE?.find((c) => c.code === code), code);
  }

  onRateClosed(proposed: boolean): void {
    this.rateDialog.set(false);
    if (proposed) this.loadTables();
  }

  onRunClosed(ran: boolean): void {
    this.runDialog.set(null);
    if (ran) {
      if (this.tab() === 'bills') this.loadBills();
      if (this.tab() === 'jobs') this.loadJobs();
    }
  }
}
