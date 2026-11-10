import { Component, EventEmitter, Input, OnInit, Output, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Payable, PropertyDetail, PtxAccess, Receipt } from '../../../../../core/models/ptx.model';
import { PtxService } from '../../../../../core/services/ptx.service';
import { PtxI18nService } from '../../../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../../../core/services/dialog.service';
import { errorText, newKey, todayIso } from '../../../ptx-utils';

/**
 * Takes one payment: shows what is due and any scheme saving first, then records cash, cheque, DD or UPI and returns
 * the receipt (PT-31..PT-33, PT-39). The request key is fixed when the dialog opens, so a double click cannot charge twice.
 */
@Component({
  selector: 'app-payment-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './payment-dialog.component.html',
})
export class PaymentDialogComponent implements OnInit {
  @Input({ required: true }) access!: PtxAccess;
  @Input({ required: true }) upin!: string;
  @Output() closed = new EventEmitter<Receipt | null>();
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  i18n = inject(PtxI18nService);

  property = signal<PropertyDetail | null>(null);
  quote = signal<Payable | null>(null);
  busy = signal(false);
  readonly key = newKey();
  readonly today = todayIso();
  form = { amount: 0, paymentMode: 'CASH', channel: 'COUNTER', instrumentNo: '', instrumentBank: '', instrumentDate: todayIso(), payerName: '', payerMobile: '' };

  ngOnInit(): void {
    const roles = this.access.roles;
    this.form.channel = roles.includes('csc_operator') ? 'CSC' : roles.includes('bill_collector') ? 'FIELD' : 'COUNTER';
    this.ptx.property(this.upin).subscribe({
      next: (p) => {
        this.property.set(p);
        this.upin = p.upin;
        this.ptx.payable(p.upin).subscribe({
          next: (q) => {
            this.quote.set(q);
            this.form.amount = q.payToClearAll;
          },
          error: (e) => this.fail(e),
        });
      },
      error: (e) => this.fail(e),
    });
  }

  private fail(e: unknown): void {
    this.dialog.showToast(errorText(e), 'error');
    this.closed.emit(null);
  }

  needsInstrument(): boolean {
    return this.form.paymentMode === 'CHEQUE' || this.form.paymentMode === 'DD';
  }

  /** How a part payment will be used, in the order GWMC has set: interest and fees, then older tax, then this period. */
  partNote(): string {
    const q = this.quote();
    if (!q) return '';
    if (this.form.amount >= q.payToClearAll) return q.saving > 0 ? `Clears everything, including the scheme saving of ₹${q.saving}.` : 'Clears everything due.';
    const extra = q.saving > 0 ? ' Paying less than the full amount means the scheme saving does not apply.' : '';
    return `Part payment: ₹${(q.totalDue - this.form.amount).toFixed(2)} will still be due.${extra}`;
  }

  async pay(): Promise<void> {
    const q = this.quote()!;
    if (this.form.amount > q.payToClearAll && q.payToClearAll > 0) {
      const ok = await this.dialog.confirm({ title: 'More than what is due', message: `₹${this.form.amount} is more than the ₹${q.payToClearAll} due. The extra is kept as advance for future bills.`,
        confirmText: 'Take it' });
      if (!ok) return;
    }
    const f = this.form;
    const body: any = { upin: this.upin, amount: Number(f.amount), paymentMode: f.paymentMode, channel: f.channel, idempotencyKey: this.key,
      payerName: f.payerName || null, payerMobile: f.payerMobile || null };
    if (this.needsInstrument()) Object.assign(body, { instrumentNo: f.instrumentNo, instrumentBank: f.instrumentBank, instrumentDate: f.instrumentDate });
    if ((f.paymentMode === 'UPI' || f.paymentMode === 'POS') && f.instrumentNo) body.instrumentNo = f.instrumentNo;
    this.busy.set(true);
    this.ptx.post<Receipt>('/payments', body).subscribe({
      next: (r) =>
        this.ptx.get<Receipt>(`/receipts/${encodeURIComponent(r.receiptNo)}`).subscribe({
          next: (full) => {
            this.busy.set(false);
            this.closed.emit(full);
          },
          error: () => {
            this.busy.set(false);
            this.closed.emit(r);
          },
        }),
      error: (e) => {
        this.busy.set(false);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }
}
