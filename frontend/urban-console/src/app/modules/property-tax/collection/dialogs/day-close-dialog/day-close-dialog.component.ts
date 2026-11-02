import { Component, EventEmitter, Output, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { PtxService } from '../../../../../core/services/ptx.service';
import { PtxI18nService } from '../../../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../../../core/services/dialog.service';
import { DayClose } from '../../../../../core/models/ptx.model';
import { errorText, todayIso } from '../../../ptx-utils';

/** A collector or counter closes the day and declares the cash in hand; the cashier then counts and verifies it (PT-38). */
@Component({
  selector: 'app-day-close-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="ptx-modal-backdrop" (click)="closed.emit(false)"></div>
    <section class="ptx-modal" role="dialog" aria-modal="true" aria-label="Close my day">
      <div class="ptx-modal-head">
        <h2>Close my day</h2>
        <button class="ptx-btn" (click)="closed.emit(false)">{{ i18n.t('cancel') }}</button>
      </div>
      <div class="ptx-modal-body">
        @if (done(); as d) {
          <div class="ptx-alert" [ngClass]="d.declaredCash === d.systemCash ? 'ok' : 'warn'">
            {{ d.receiptCount }} receipt(s). Cash by receipts ₹{{ d.systemCash | number: '1.2-2' }}, you declared ₹{{ d.declaredCash | number: '1.2-2' }}.
            Hand the cash to the cashier for counting.
          </div>
        } @else {
          <p class="ptx-muted">All your receipts for the day (not yet closed) are included. Online payments are not part of the cash count.</p>
          <div class="ptx-form">
            <label>{{ i18n.t('date') }} <input type="date" [max]="today" [(ngModel)]="closeDate" /></label>
            <label>Cash in hand (₹) * <input type="number" min="0" step="0.01" inputmode="decimal" [(ngModel)]="declaredCash" /></label>
            <label style="grid-column: 1 / -1">{{ i18n.t('remark') }} <input [(ngModel)]="remark" /></label>
          </div>
        }
      </div>
      <div class="ptx-modal-foot">
        @if (done()) {
          <button class="ptx-btn primary" (click)="closed.emit(true)">Done</button>
        } @else {
          <button class="ptx-btn" (click)="closed.emit(false)">{{ i18n.t('cancel') }}</button>
          <button class="ptx-btn primary" (click)="submit()" [disabled]="busy() || declaredCash === null">Close the day</button>
        }
      </div>
    </section>
  `,
})
export class DayCloseDialogComponent {
  @Output() closed = new EventEmitter<boolean>();
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  i18n = inject(PtxI18nService);
  readonly today = todayIso();
  closeDate = todayIso();
  declaredCash: number | null = null;
  remark = '';
  busy = signal(false);
  done = signal<DayClose | null>(null);

  submit(): void {
    this.busy.set(true);
    this.ptx.post<DayClose>('/day-close', { closeDate: this.closeDate, declaredCash: Number(this.declaredCash), remark: this.remark || null }).subscribe({
      next: (d) => {
        this.busy.set(false);
        this.done.set(d);
      },
      error: (e) => {
        this.busy.set(false);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }
}
