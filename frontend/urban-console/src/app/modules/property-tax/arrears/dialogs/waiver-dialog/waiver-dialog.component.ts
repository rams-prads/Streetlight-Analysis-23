import { Component, EventEmitter, Input, OnInit, Output, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Dues } from '../../../../../core/models/ptx.model';
import { PtxService } from '../../../../../core/services/ptx.service';
import { PtxI18nService } from '../../../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../../../core/services/dialog.service';
import { errorText } from '../../../ptx-utils';

/**
 * Asks for a waiver or write-off of part of a property's dues (PT-41). Nothing changes until an officer within their
 * approval limit - or the Commissioner above it - approves it.
 */
@Component({
  selector: 'app-waiver-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="ptx-modal-backdrop" (click)="closed.emit(false)"></div>
    <section class="ptx-modal" role="dialog" aria-modal="true" aria-label="Waiver or write-off">
      <div class="ptx-modal-head">
        <h2>Waiver / write-off · {{ upin }}</h2>
        <button class="ptx-btn" (click)="closed.emit(false)">{{ i18n.t('cancel') }}</button>
      </div>
      <div class="ptx-modal-body">
        @if (dues(); as d) {
          <div class="ptx-kpis">
            <div class="ptx-kpi"><span>{{ i18n.t('interest') }}</span><b>₹{{ d.interest | number: '1.2-2' }}</b></div>
            <div class="ptx-kpi"><span>{{ i18n.t('fees') }}</span><b>₹{{ d.fees | number: '1.2-2' }}</b></div>
            <div class="ptx-kpi"><span>{{ i18n.t('arrearsLabel') }}</span><b>₹{{ d.arrears | number: '1.2-2' }}</b></div>
            <div class="ptx-kpi"><span>{{ i18n.t('current') }}</span><b>₹{{ d.current | number: '1.2-2' }}</b></div>
          </div>
        }
        <div class="ptx-form">
          <label>Request
            <select [(ngModel)]="kind"><option value="WAIVER">Waiver (by order)</option><option value="WRITE_OFF">Write-off (cannot be recovered)</option></select>
          </label>
          <label>From
            <select [(ngModel)]="bucket">
              <option value="PENALTY">{{ i18n.t('interest') }}</option><option value="FEE">{{ i18n.t('fees') }}</option>
              <option value="ARREAR">{{ i18n.t('arrearsLabel') }}</option><option value="CURRENT">{{ i18n.t('current') }}</option>
            </select>
          </label>
          <label>{{ i18n.t('amount') }} (₹) * <input type="number" min="1" step="0.01" [(ngModel)]="amount" /></label>
          <label style="grid-column: 1 / -1">Order no. / reason * <input [(ngModel)]="reason" placeholder="e.g. Council resolution 4/2026" /></label>
        </div>
        <p class="ptx-muted">The request goes to Approvals. Large amounts need the Commissioner.</p>
      </div>
      <div class="ptx-modal-foot">
        <button class="ptx-btn" (click)="closed.emit(false)">{{ i18n.t('cancel') }}</button>
        <button class="ptx-btn primary" (click)="submit()" [disabled]="busy() || !(amount > 0) || reason.trim().length < 5">Send for approval</button>
      </div>
    </section>
  `,
})
export class WaiverDialogComponent implements OnInit {
  @Input({ required: true }) upin!: string;
  @Output() closed = new EventEmitter<boolean>();
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  i18n = inject(PtxI18nService);
  dues = signal<Dues | null>(null);
  kind = 'WAIVER';
  bucket = 'PENALTY';
  amount = 0;
  reason = '';
  busy = signal(false);

  ngOnInit(): void {
    this.ptx.get<Dues>(`/properties/${encodeURIComponent(this.upin)}/dues`).subscribe({
      next: (d) => this.dues.set(d),
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  submit(): void {
    this.busy.set(true);
    this.ptx.post(`/properties/${encodeURIComponent(this.upin)}/waivers`, { kind: this.kind, bucket: this.bucket, amount: Number(this.amount), reason: this.reason }).subscribe({
      next: (r) => {
        this.busy.set(false);
        this.dialog.showToast(r.message, 'success');
        this.closed.emit(true);
      },
      error: (e) => {
        this.busy.set(false);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }
}
