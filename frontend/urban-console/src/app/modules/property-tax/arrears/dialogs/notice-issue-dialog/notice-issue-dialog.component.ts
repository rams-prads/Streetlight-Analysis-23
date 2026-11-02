import { Component, EventEmitter, Input, OnInit, Output, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { PtxAccess } from '../../../../../core/models/ptx.model';
import { PtxService } from '../../../../../core/services/ptx.service';
import { PtxI18nService } from '../../../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../../../core/services/dialog.service';
import { errorText } from '../../../ptx-utils';

/** Issues demand, reminder or recovery notices one at a time or for a whole ward (PT-42). Owners also get an SMS. */
@Component({
  selector: 'app-notice-issue-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="ptx-modal-backdrop" (click)="closed.emit(done())"></div>
    <section class="ptx-modal" role="dialog" aria-modal="true" aria-label="Issue notices">
      <div class="ptx-modal-head">
        <h2>Issue notices</h2>
        <button class="ptx-btn" (click)="closed.emit(done())">{{ i18n.t('close') }}</button>
      </div>
      <div class="ptx-modal-body">
        @if (result(); as r) {
          <div class="ptx-alert ok">{{ r.issued.length }} notice(s) issued. {{ r.skipped.length }} property(ies) skipped (nothing due or no bill).</div>
          <p class="ptx-muted">Print them from the Notices list, or send them to field staff, who record service in the Field Work screen.</p>
        } @else {
          <div class="ptx-form">
            <label>Notice type
              <select [(ngModel)]="type">
                <option value="DEMAND">Demand notice (the current bill)</option>
                <option value="REMINDER">Reminder</option>
                <option value="RECOVERY">Recovery notice</option>
              </select>
            </label>
            @if (!upins.length) {
              <label>{{ i18n.t('ward') }} *
                <select [(ngModel)]="wardId">
                  <option value="">Choose…</option>
                  @for (w of access.wards; track w.wardId) { <option [value]="w.wardId">{{ w.wardNumber }} · {{ w.wardName }}</option> }
                </select>
              </label>
              <label>Only where dues are at least (₹) <input type="number" min="0" [(ngModel)]="minDue" /></label>
            } @else {
              <p>For: <b>{{ upins.join(', ') }}</b></p>
            }
          </div>
        }
      </div>
      <div class="ptx-modal-foot">
        @if (!result()) {
          <button class="ptx-btn" (click)="closed.emit(false)">{{ i18n.t('cancel') }}</button>
          <button class="ptx-btn primary" (click)="issue()" [disabled]="busy() || (!upins.length && !wardId)">Issue</button>
        } @else {
          <button class="ptx-btn primary" (click)="closed.emit(true)">See notices</button>
        }
      </div>
    </section>
  `,
})
export class NoticeIssueDialogComponent implements OnInit {
  @Input({ required: true }) access!: PtxAccess;
  @Input() upins: string[] = [];
  @Output() closed = new EventEmitter<boolean>();
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  i18n = inject(PtxI18nService);
  type = 'DEMAND';
  wardId = '';
  minDue = 1;
  busy = signal(false);
  result = signal<{ issued: string[]; skipped: any[] } | null>(null);
  done = () => !!this.result();

  ngOnInit(): void {
    if (this.upins.length) this.type = 'REMINDER';
  }

  issue(): void {
    const body: any = { noticeType: this.type, minDue: Number(this.minDue) || 0 };
    if (this.upins.length) body.upins = this.upins;
    else body.wardId = this.wardId;
    this.busy.set(true);
    this.ptx.post('/notices', body).subscribe({
      next: (r) => {
        this.busy.set(false);
        this.result.set(r);
      },
      error: (e) => {
        this.busy.set(false);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }
}
