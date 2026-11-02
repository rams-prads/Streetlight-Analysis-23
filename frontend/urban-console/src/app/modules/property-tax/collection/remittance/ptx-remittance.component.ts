import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DayClose, PtxAccess, Remittance } from '../../../../core/models/ptx.model';
import { PtxService } from '../../../../core/services/ptx.service';
import { PtxI18nService } from '../../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../../core/services/dialog.service';
import { IconComponent } from '../../../../shared/components/icon/icon.component';
import { PtxPagerComponent } from '../../shared/ptx-pager.component';
import { Pager, dmy, errorText, todayIso } from '../../ptx-utils';

interface PendingClose extends DayClose {
  expectedCash: number;
  expectedInstruments: number;
  picked?: boolean;
}

/**
 * Banking (PT-23): the cashier bundles verified day-end closings into one deposit with the bank challan; a different officer
 * then confirms the bank credit. A closing can be banked only once, and any difference must be explained.
 */
@Component({
  selector: 'app-ptx-remittance',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent, PtxPagerComponent],
  template: `
    @if (can('remittance.prepare')) {
      <div class="ptx-card">
        <h2>Money to deposit</h2>
        <p class="ptx-muted">Day-end closings you have verified and not yet banked. Tick the ones going in this deposit.</p>
        <div class="ptx-table-wrap">
          <table class="ptx-table compact">
            <thead><tr><th></th><th>{{ i18n.t('date') }}</th><th>Collector</th><th class="num">Cash counted</th><th class="num">Cheques, DD, UPI</th></tr></thead>
            <tbody>
              @for (c of pending(); track c.id) {
                <tr><td><input type="checkbox" [(ngModel)]="c.picked" (ngModelChange)="recount()" [attr.aria-label]="'Include ' + c.collector" /></td>
                  <td>{{ dmy(c.closeDate) }}</td><td>{{ c.collector }}</td><td class="num">₹{{ c.expectedCash | number: '1.2-2' }}</td><td class="num">₹{{ c.expectedInstruments | number: '1.2-2' }}</td></tr>
              } @empty { <tr><td colspan="5" class="ptx-muted">Nothing waiting to be banked.</td></tr> }
            </tbody>
          </table>
        </div>
        @if (pickedCount() > 0) {
          <div class="ptx-form" style="margin-top: 0.8rem">
            <label>Bank * <input [(ngModel)]="form.bankName" placeholder="e.g. State Bank of India, Hanamkonda" /></label>
            <label>Challan / deposit slip no. * <input [(ngModel)]="form.challanNo" /></label>
            <label>Date deposited * <input type="date" [max]="today" [(ngModel)]="form.depositDate" /></label>
            <label>Cash deposited (₹) * <input type="number" min="0" step="0.01" [(ngModel)]="form.depositedCash" /></label>
            <label>Cheques, DD, UPI deposited (₹) <input type="number" min="0" step="0.01" [(ngModel)]="form.depositedInstruments" /></label>
            <label style="grid-column: 1 / -1">Remark (needed if the amounts differ) <input [(ngModel)]="form.remark" /></label>
          </div>
          <p class="ptx-muted">Verified: cash ₹{{ expected().cash | number: '1.2-2' }} + cheques etc. ₹{{ expected().inst | number: '1.2-2' }} = ₹{{ expected().cash + expected().inst | number: '1.2-2' }}.
            Being deposited: ₹{{ (+form.depositedCash || 0) + (+form.depositedInstruments || 0) | number: '1.2-2' }}.</p>
          <button class="ptx-btn primary" (click)="create()" [disabled]="busy() || !form.bankName.trim() || !form.challanNo.trim()">Record the deposit</button>
        }
      </div>
    }

    <div class="ptx-card flush">
      <div class="ptx-card-head">
        <div><h2>Deposits</h2><p class="ptx-muted">An officer other than the cashier confirms each deposit against the bank's credit.</p></div>
        <button class="ptx-btn" (click)="load()"><app-icon name="refresh" [size]="16"></app-icon> {{ i18n.t('refresh') }}</button>
      </div>
      <div class="ptx-filter-bar">
        <div class="ptx-search"><app-icon name="search" [size]="16"></app-icon>
          <input [(ngModel)]="search" (input)="onSearch()" placeholder="Deposit no., challan no. or bank" aria-label="Search deposits" /></div>
        <div class="ptx-filters">
          <select [(ngModel)]="status" (change)="pager.reset(); load()" aria-label="Status">
            <option value="">{{ i18n.t('all') }}</option><option value="SUBMITTED">Waiting for bank confirmation</option><option value="CONFIRMED">Confirmed</option><option value="MISMATCH">Difference found</option>
          </select>
        </div>
      </div>
      <div class="ptx-table-wrap">
        <table class="ptx-table">
          <thead><tr><th>Deposit</th><th>Bank / challan</th><th class="num">Verified</th><th class="num">Deposited</th><th class="num">Bank credited</th><th>{{ i18n.t('status') }}</th><th></th></tr></thead>
          <tbody>
            @for (r of rows(); track r.id) {
              <tr>
                <td><span class="ptx-mono">{{ r.remittanceNo }}</span><br /><small class="ptx-muted">{{ dmy(r.depositDate) }} · {{ r.preparedBy }}</small></td>
                <td>{{ r.bankName }}<br /><small class="ptx-muted">{{ r.challanNo }}</small></td>
                <td class="num">₹{{ r.expectedTotal | number: '1.2-2' }}</td>
                <td class="num">₹{{ r.depositedTotal | number: '1.2-2' }}@if (r.depositVariance) {<br /><small class="ptx-chip overdue">{{ r.depositVariance | number: '1.2-2' }}</small>}</td>
                <td class="num">{{ r.creditedAmount === null ? '-' : '₹' + (r.creditedAmount | number: '1.2-2') }}<br /><small class="ptx-muted">{{ dmy(r.creditDate) }}</small></td>
                <td><span class="ptx-chip" [ngClass]="r.status === 'CONFIRMED' ? 'DONE' : r.status === 'MISMATCH' ? 'ARREARS' : 'PENDING'">
                  {{ r.status === 'SUBMITTED' ? 'waiting for bank' : r.status === 'CONFIRMED' ? 'confirmed' : 'difference' }}</span>@if (r.remark) {<br /><small class="ptx-muted">{{ r.remark }}</small>}</td>
                <td>@if (r.status === 'SUBMITTED' && can('remittance.confirm') && r.preparedBy !== access.username) { <button class="ptx-btn sm primary" (click)="confirm(r)">Confirm bank credit</button> }</td>
              </tr>
            } @empty { <tr><td colspan="7" class="ptx-muted">{{ i18n.t('noRecords') }}</td></tr> }
          </tbody>
        </table>
      </div>
      <app-ptx-pager [pager]="pager" (changed)="load()"></app-ptx-pager>
    </div>
  `,
})
export class PtxRemittanceComponent implements OnInit {
  @Input({ required: true }) access!: PtxAccess;
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  i18n = inject(PtxI18nService);
  dmy = dmy;
  readonly today = todayIso();

  pending = signal<PendingClose[]>([]);
  rows = signal<Remittance[]>([]);
  pager = new Pager(10);
  status = '';
  search = '';
  busy = signal(false);
  form = { bankName: '', challanNo: '', depositDate: todayIso(), depositedCash: 0 as number, depositedInstruments: 0 as number, remark: '' };
  private timer?: ReturnType<typeof setTimeout>;

  ngOnInit(): void {
    this.loadPending();
    this.load();
  }

  can(p: string): boolean {
    return this.access.permissions.includes(p);
  }

  expected(): { cash: number; inst: number } {
    const picked = this.pending().filter((c) => c.picked);
    return { cash: picked.reduce((s, c) => s + c.expectedCash, 0), inst: picked.reduce((s, c) => s + c.expectedInstruments, 0) };
  }

  pickedCount(): number {
    return this.pending().filter((c) => c.picked).length;
  }

  /** The deposit boxes start at what was verified, so a clean deposit needs no typing. */
  recount(): void {
    const e = this.expected();
    this.form.depositedCash = +e.cash.toFixed(2);
    this.form.depositedInstruments = +e.inst.toFixed(2);
  }

  loadPending(): void {
    if (!this.can('remittance.prepare')) return;
    this.ptx.get('/remittances/pending-closes').subscribe({
      next: (r) => this.pending.set(r.items),
      error: (e) => {
        this.pending.set([]);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  onSearch(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.pager.reset();
      this.load();
    }, 350);
  }

  load(): void {
    this.ptx.get('/remittances', { search: this.search, status: this.status, ...this.pager.query() }).subscribe({
      next: (r) => {
        this.rows.set(r.items);
        this.pager.total.set(r.total);
      },
      error: (e) => {
        this.rows.set([]);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  create(): void {
    const f = this.form;
    this.busy.set(true);
    this.ptx.post<Remittance>('/remittances', { closeIds: this.pending().filter((c) => c.picked).map((c) => c.id), bankName: f.bankName, challanNo: f.challanNo,
      depositDate: f.depositDate, depositedCash: Number(f.depositedCash), depositedInstruments: Number(f.depositedInstruments), remark: f.remark || null }).subscribe({
      next: (r) => {
        this.busy.set(false);
        this.dialog.showToast(`Deposit ${r.remittanceNo} recorded. Another officer confirms it against the bank credit.`, 'success');
        this.form = { bankName: '', challanNo: '', depositDate: todayIso(), depositedCash: 0, depositedInstruments: 0, remark: '' };
        this.loadPending();
        this.load();
      },
      error: (e) => {
        this.busy.set(false);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  async confirm(r: Remittance): Promise<void> {
    const amount = await this.dialog.prompt({ title: `Confirm ${r.remittanceNo}`, message: `₹${r.depositedTotal} was banked. Enter the amount the bank credited, from the statement.`,
      inputLabel: 'Credited (₹)', initialValue: String(r.depositedTotal), required: true });
    if (amount === null) return;
    const date = await this.dialog.prompt({ title: 'Date the bank credited it', inputLabel: 'Credit date (YYYY-MM-DD)', initialValue: todayIso(), required: true });
    if (!date) return;
    let remark: string | null = null;
    if (Number(amount) !== r.depositedTotal) {
      remark = await this.dialog.prompt({ title: 'The amounts differ', message: 'Say what is being done about the difference.', inputLabel: 'Remark', required: true });
      if (!remark) return;
    }
    this.ptx.post(`/remittances/${encodeURIComponent(r.remittanceNo)}/confirm`, { creditDate: date, creditedAmount: Number(amount), remark }).subscribe({
      next: (res) => {
        this.dialog.showToast(res.status === 'CONFIRMED' ? 'Confirmed: the bank credit matches.' : 'Recorded with a difference to follow up.', res.status === 'CONFIRMED' ? 'success' : 'warning');
        this.load();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }
}
