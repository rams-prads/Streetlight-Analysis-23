import { ChangeDetectorRef, Component, Input, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DuesStatus, WaterAccess, WaterReceipt } from '../../../core/models/water.model';
import { WaterService } from '../../../core/services/water.service';
import { WaterI18nService } from '../../../core/services/water-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { WaterDocumentComponent } from '../water-document.component';
import { downloadCsv, dmy, errorText, newKey, todayIso } from '../water-utils';

/** Counter / field collection, receipts, cheque returns, day-end closing, online payment and reconciliation (WB-30..WB-37). */
@Component({
  selector: 'app-water-collection',
  standalone: true,
  imports: [CommonModule, FormsModule, WaterDocumentComponent],
  templateUrl: './water-collection.component.html',
})
export class WaterCollectionComponent implements OnInit {
  @Input() access!: WaterAccess;
  private water = inject(WaterService);
  private dialog = inject(DialogService);
  private cdr = inject(ChangeDetectorRef);
  i18n = inject(WaterI18nService);
  dmy = dmy;

  view = signal<'counter' | 'receipts' | 'online' | 'dayclose' | 'reconcile'>('counter');

  pay: any = {};
  dues = signal<DuesStatus | null>(null);
  receiptDoc = signal<WaterReceipt | null>(null);
  busy = signal(false);

  rq = { from: todayIso(), to: todayIso(), q: '', mode: '' };
  receipts = signal<WaterReceipt[]>([]);

  online: any = { consumerNo: '', amount: 0 };
  order = signal<any>(null);

  closeForm = { closeDate: todayIso(), declaredCash: 0, remark: '' };
  closes = signal<any[]>([]);

  recDate = todayIso();
  recRows: { reference: string; amount: number }[] = [];
  recResult = signal<any>(null);
  recHistory = signal<any[]>([]);

  ngOnInit(): void {
    this.resetPay();
    if (this.can('payment.collect')) this.view.set('counter');
    else this.view.set('receipts');
    this.loadReceipts();
  }

  can(p: string): boolean {
    return this.access.permissions.includes(p);
  }

  resetPay(): void {
    this.pay = { consumerNo: '', amount: 0, paymentMode: 'CASH', channel: 'COUNTER', instrumentNo: '', instrumentBank: '', instrumentDate: todayIso(),
      payerName: '', payerMobile: '', idempotencyKey: newKey() };
    this.dues.set(null);
  }

  lookupDues(): void {
    if (!this.pay.consumerNo) return;
    this.water.dues(this.pay.consumerNo.trim().toUpperCase()).subscribe({
      next: (d) => {
        this.dues.set(d);
        this.pay.amount = d.netPayable;
      },
      error: (e) => {
        this.dues.set(null);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  collect(): void {
    const p = this.pay;
    const body: any = { consumerNo: p.consumerNo.trim().toUpperCase(), amount: Number(p.amount), paymentMode: p.paymentMode, channel: p.channel,
      payerName: p.payerName || null, payerMobile: p.payerMobile || null, idempotencyKey: p.idempotencyKey };
    if (['CHEQUE', 'DD'].includes(p.paymentMode)) Object.assign(body, { instrumentNo: p.instrumentNo, instrumentBank: p.instrumentBank, instrumentDate: p.instrumentDate });
    this.busy.set(true);
    this.water.post<WaterReceipt>('/payments', body).subscribe({
      next: (r) => {
        this.busy.set(false);
        this.dialog.showToast(`Receipt ${r.receiptNo} issued`, 'success');
        this.openReceipt(r.receiptNo);
        this.resetPay();
        this.loadReceipts();
      },
      error: (e) => {
        this.busy.set(false);
        // same idempotency key on retry: a payment that did reach the server is never recorded twice
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  loadReceipts(): void {
    this.water.get<WaterReceipt[]>('/receipts', { from: this.rq.from, to: this.rq.to, q: this.rq.q, mode: this.rq.mode }).subscribe({
      next: (r) => this.receipts.set(r),
      error: () => this.receipts.set([]),
    });
  }

  exportReceipts(): void {
    downloadCsv(`water-receipts-${this.rq.from}-${this.rq.to}`, this.receipts(), [
      { key: 'receiptNo', label: 'Receipt no' }, { key: 'receiptDate', label: 'Date' }, { key: 'consumerNo', label: 'Consumer no' },
      { key: 'applicationNo', label: 'Application no' }, { key: 'amount', label: 'Amount' }, { key: 'paymentMode', label: 'Mode' },
      { key: 'channel', label: 'Channel' }, { key: 'status', label: 'Status' }, { key: 'collectedBy', label: 'Collected by' },
    ]);
  }

  openReceipt(no: string): void {
    this.water.receipt(no).subscribe({ next: (r) => this.receiptDoc.set(r), error: (e) => this.dialog.showToast(errorText(e), 'error') });
  }

  async cancelReceipt(r: WaterReceipt): Promise<void> {
    const reason = await this.dialog.prompt({ title: `Cancel receipt ${r.receiptNo}`, message: 'Receipts are never edited. The cancellation is reversed only after approval.',
      inputLabel: 'Reason', required: true });
    if (!reason) return;
    this.water.post(`/receipts/${encodeURIComponent(r.receiptNo)}/cancel`, { reason }).subscribe({
      next: (x) => this.dialog.showToast(x.message, 'success'),
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  async chequeReturn(r: WaterReceipt): Promise<void> {
    const reason = await this.dialog.prompt({ title: `Cheque returned - ${r.receiptNo}`, message: 'The receipt is reversed, the notified charge added and the payer informed.',
      inputLabel: 'Bank return reason', required: true });
    if (!reason) return;
    this.water.post(`/receipts/${encodeURIComponent(r.receiptNo)}/cheque-return`, { reason }).subscribe({
      next: (x) => {
        this.dialog.showToast(`${x.message}. Charge ₹${x.chargeAdded}`, 'success');
        this.loadReceipts();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  startOnline(): void {
    this.water.post('/payments/online/initiate', { consumerNo: this.online.consumerNo.trim().toUpperCase(), amount: Number(this.online.amount) }).subscribe({
      next: (o) => this.order.set(o),
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  gateway(outcome: 'SUCCESS' | 'SUCCESS_NO_CALLBACK' | 'FAILURE'): void {
    const o = this.order();
    this.water.post('/payments/online/stub-gateway', { orderId: o.orderId, outcome }).subscribe({
      next: (r) => {
        this.order.set({ ...o, result: r });
        if (r.receipt) this.openReceipt(r.receipt.receiptNo);
        this.dialog.showToast(r.message || `Payment ${r.status}`, r.status === 'FAILED' ? 'warning' : 'success');
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  statusCheck(): void {
    this.water.post('/payments/online/status-check', {}).subscribe({
      next: (r) => {
        this.dialog.showToast(`Checked ${r.checked}: ${r.completed.length} completed, ${r.failed.length} failed`, 'success');
        if (r.completed.length) this.openReceipt(r.completed[0].receiptNo);
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  loadCloses(): void {
    this.water.get('/day-close').subscribe({ next: (r) => this.closes.set(r), error: () => this.closes.set([]) });
  }

  submitClose(): void {
    this.water.post('/day-close', { ...this.closeForm, declaredCash: Number(this.closeForm.declaredCash) }).subscribe({
      next: (d) => {
        const v = Number(this.closeForm.declaredCash) - d.systemCash;
        this.dialog.showToast(`Day closed: system cash ₹${d.systemCash}${v ? ', difference ₹' + v.toFixed(2) : ''}`, v ? 'warning' : 'success');
        this.loadCloses();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  async verifyClose(d: any): Promise<void> {
    const cash = await this.dialog.prompt({ title: `Cash handed over by ${d.collector}`, message: `System cash for ${dmy(d.closeDate)}: ₹${d.systemCash}`,
      inputLabel: 'Cash counted (₹)', initialValue: String(d.systemCash), required: true });
    if (cash === null) return;
    this.water.post(`/day-close/${d.id}/verify`, { receivedCash: Number(cash) }).subscribe({
      next: (r) => {
        this.dialog.showToast(`Verified. Variance ₹${r.variance}`, r.variance ? 'warning' : 'success');
        this.loadCloses();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  loadStandIn(): void {
    this.water.get('/reconciliation/stand-in-statement', { date: this.recDate }).subscribe({
      next: (rows) => {
        this.recRows = rows.map((r: any) => ({ reference: r.reference, amount: r.amount }));
        this.dialog.showToast(`${rows.length} line(s) loaded from the stand-in gateway statement`, 'info');
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  loadStatementFile(ev: Event): void {
    const file = (ev.target as HTMLInputElement).files?.[0];
    if (!file) return;
    file.text().then((t) => {
      this.recRows = t.split(/\r?\n/).slice(1).map((l) => l.split(',')).filter((c) => c[0]?.trim())
        .map((c) => ({ reference: c[0].trim(), amount: Number(c[1]) }));
      this.cdr.markForCheck();
    });
  }

  reconcile(): void {
    this.water.post('/reconciliation', { statementDate: this.recDate, source: 'GATEWAY', rows: this.recRows }).subscribe({
      next: (r) => {
        this.recResult.set(r);
        this.loadRecHistory();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  loadRecHistory(): void {
    this.water.get('/reconciliation').subscribe({ next: (r) => this.recHistory.set(r), error: () => this.recHistory.set([]) });
  }

  setView(v: 'counter' | 'receipts' | 'online' | 'dayclose' | 'reconcile'): void {
    this.view.set(v);
    this.receiptDoc.set(null);
    if (v === 'dayclose') this.loadCloses();
    if (v === 'reconcile') this.loadRecHistory();
    if (v === 'receipts') this.loadReceipts();
  }
}
