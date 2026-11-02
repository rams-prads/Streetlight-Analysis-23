import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { DayClose, Mismatch, PtxAccess, Receipt } from '../../../core/models/ptx.model';
import { PtxService } from '../../../core/services/ptx.service';
import { PtxI18nService } from '../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { IconComponent } from '../../../shared/components/icon/icon.component';
import { PtxPagerComponent } from '../shared/ptx-pager.component';
import { PtxDocumentComponent } from '../shared/ptx-document.component';
import { PaymentDialogComponent } from './dialogs/payment-dialog/payment-dialog.component';
import { DayCloseDialogComponent } from './dialogs/day-close-dialog/day-close-dialog.component';
import { PtxRemittanceComponent } from './remittance/ptx-remittance.component';
import { Pager, dmy, errorText, todayIso } from '../ptx-utils';

type Tab = 'pay' | 'receipts' | 'dayclose' | 'reconcile' | 'banking';

/** Counter / field collection (PT-31), receipts and reversals (PT-34, PT-35), day-end closing (PT-38), reconciliation (PT-35). */
@Component({
  selector: 'app-ptx-collection',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent, PtxPagerComponent, PtxDocumentComponent, PaymentDialogComponent, DayCloseDialogComponent, PtxRemittanceComponent],
  templateUrl: './ptx-collection.component.html',
})
export class PtxCollectionComponent implements OnInit {
  @Input({ required: true }) access!: PtxAccess;
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  private route = inject(ActivatedRoute);
  i18n = inject(PtxI18nService);
  dmy = dmy;

  /** The part to show, chosen in the sidebar. */
  @Input() view = '';
  tab = signal<Tab>('pay');
  upin = '';
  payUpin = signal<string | null>(null);
  lastReceipt = signal<Receipt | null>(null);

  rf = { search: '', from: todayIso(), to: todayIso(), mode: '' };
  receipts = signal<Receipt[]>([]);
  receiptPager = new Pager(10);
  shown = signal<Receipt | null>(null);

  closes = signal<DayClose[]>([]);
  closePager = new Pager(10);
  closeDialog = signal(false);

  reconDate = todayIso();
  mismatches = signal<Mismatch[] | null>(null);
  reconResult = signal<any | null>(null);
  reconHistory = signal<any[]>([]);
  busy = signal(false);
  private searchTimer?: ReturnType<typeof setTimeout>;

  ngOnInit(): void {
    const upin = this.route.snapshot.queryParamMap.get('upin');
    if (!this.can('payment.collect')) this.tab.set(this.can('dayclose.verify') ? 'dayclose' : 'reconcile');
    if ((['pay', 'receipts', 'dayclose', 'reconcile', 'banking'] as Tab[]).includes(this.view as Tab)) this.tab.set(this.view as Tab);
    if (upin && this.can('payment.collect')) {
      this.upin = upin;
      this.payUpin.set(upin);
    }
    this.setTab(this.tab());
  }

  can(p: string): boolean {
    return this.access.permissions.includes(p);
  }

  setTab(t: Tab): void {
    this.tab.set(t);
    if (t === 'receipts') this.loadReceipts();
    if (t === 'dayclose') this.loadCloses();
    if (t === 'reconcile' && this.can('payment.reconcile')) this.loadRecon();
  }

  startPayment(): void {
    const u = this.upin.trim().toUpperCase();
    if (!u) return;
    this.payUpin.set(u);
  }

  onPaid(r: Receipt | null): void {
    this.payUpin.set(null);
    if (r) this.lastReceipt.set(r);
  }

  onSearchInput(): void {
    if (this.searchTimer) clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => {
      this.receiptPager.reset();
      this.loadReceipts();
    }, 350);
  }

  loadReceipts(): void {
    this.ptx.get('/receipts', { ...this.rf, ...this.receiptPager.query() }).subscribe({
      next: (r) => {
        this.receipts.set(r.items);
        this.receiptPager.total.set(r.total);
      },
      error: (e) => {
        this.receipts.set([]);
        this.receiptPager.total.set(0);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  showReceipt(no: string): void {
    this.ptx.get<Receipt>(`/receipts/${encodeURIComponent(no)}`).subscribe({
      next: (r) => this.shown.set(r),
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  async cancelReceipt(r: Receipt): Promise<void> {
    const reason = await this.dialog.prompt({ title: `Cancel receipt ${r.receiptNo}?`, message: 'A receipt is never edited. Cancelling needs approval; the dues come back on the property.',
      inputLabel: 'Reason', required: true });
    if (!reason) return;
    this.ptx.post(`/receipts/${encodeURIComponent(r.receiptNo)}/cancel`, { reason }).subscribe({
      next: () => this.dialog.showToast('Cancellation sent for approval.', 'success'),
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  async chequeReturn(r: Receipt): Promise<void> {
    const reason = await this.dialog.prompt({ title: `Cheque returned: ${r.receiptNo}`, message: 'The payment is reversed, the return charge is added and the payer is told by SMS.',
      inputLabel: 'Bank reason', placeholder: 'e.g. Insufficient funds', required: true });
    if (!reason) return;
    this.ptx.post(`/receipts/${encodeURIComponent(r.receiptNo)}/cheque-return`, { reason }).subscribe({
      next: () => {
        this.dialog.showToast('Cheque return recorded and the dues restored.', 'success');
        this.loadReceipts();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  loadCloses(): void {
    this.ptx.get('/day-close', this.closePager.query()).subscribe({
      next: (r) => {
        this.closes.set(r.items);
        this.closePager.total.set(r.total);
      },
      error: (e) => {
        this.closes.set([]);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  async verify(c: DayClose): Promise<void> {
    const got = await this.dialog.prompt({ title: `Count the cash from ${c.collector}`, message: `Receipts say ₹${c.systemCash} in cash; they declared ₹${c.declaredCash}.`,
      inputLabel: 'Cash actually received (₹)', initialValue: String(c.declaredCash), required: true });
    if (got === null) return;
    this.ptx.post(`/day-close/${c.id}/verify`, { receivedCash: Number(got) }).subscribe({
      next: (r) => {
        this.dialog.showToast(r.variance ? `Verified with a difference of ₹${r.variance}.` : 'Verified: cash matches the receipts.', r.variance ? 'warning' : 'success');
        this.loadCloses();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  onClosed(done: boolean): void {
    this.closeDialog.set(false);
    if (done) this.loadCloses();
  }

  loadRecon(): void {
    this.ptx.get('/reconciliation', { limit: 10 }).subscribe({
      next: (r) => this.reconHistory.set(r.items),
      error: () => this.reconHistory.set([]),
    });
  }

  /** Uses the gateway stand-in's statement for the day; with the real gateway the bank file is loaded here (PT-35). */
  reconcile(): void {
    this.busy.set(true);
    this.ptx.get<{ reference: string; amount: number }[]>('/reconciliation/stand-in-statement', { date: this.reconDate }).subscribe({
      next: (rows) =>
        this.ptx.post('/reconciliation', { statementDate: this.reconDate, source: 'GATEWAY', rows }).subscribe({
          next: (r) => {
            this.busy.set(false);
            this.reconResult.set(r);
            this.mismatches.set(r.mismatches);
            this.loadRecon();
          },
          error: (e) => {
            this.busy.set(false);
            this.dialog.showToast(errorText(e), 'error');
          },
        }),
      error: (e) => {
        this.busy.set(false);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  statusCheck(): void {
    this.ptx.post('/payments/online/status-check').subscribe({
      next: (r) => this.dialog.showToast(`${r.checked} waiting online payment(s) checked: ${r.completed.length} completed, ${r.failed.length} failed.`, 'info'),
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }
}
