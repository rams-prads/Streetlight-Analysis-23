import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Approval, PtxAccess } from '../../../core/models/ptx.model';
import { PtxService } from '../../../core/services/ptx.service';
import { PtxI18nService } from '../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { IconComponent } from '../../../shared/components/icon/icon.component';
import { PtxPagerComponent } from '../shared/ptx-pager.component';
import { Pager, dmy, errorText } from '../ptx-utils';

const TYPE_NAME: { [k: string]: string } = {
  RATE_TABLE: 'New rate table', RECEIPT_CANCEL: 'Receipt cancellation', REFUND: 'Refund', WAIVER: 'Waiver', WRITE_OFF: 'Write-off',
  DEMAND_CORRECTION: 'Bill correction',
};

/** Maker-checker approvals: rate tables, receipt cancellations, refunds, waivers and write-offs, within each officer's limit (PT-34, PT-40, PT-41). */
@Component({
  selector: 'app-ptx-approvals',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent, PtxPagerComponent],
  template: `
    <div class="ptx-card flush">
      <div class="ptx-card-head">
        <div><p class="ptx-muted">Nobody approves their own request. Amounts above an officer's limit go to the Commissioner.</p></div>
        <button class="ptx-btn" (click)="load()"><app-icon name="refresh" [size]="16"></app-icon> {{ i18n.t('refresh') }}</button>
      </div>
      <div class="ptx-filter-bar">
        <div class="ptx-search">
          <app-icon name="search" [size]="16"></app-icon>
          <input [(ngModel)]="search" (input)="onSearch()" placeholder="Reference, reason or requested by" aria-label="Search approvals" />
        </div>
        <div class="ptx-filters">
          <select [(ngModel)]="status" (change)="pager.reset(); load()" aria-label="Status">
            <option value="PENDING">Waiting</option><option value="APPROVED">Approved</option><option value="REJECTED">Rejected</option><option value="">{{ i18n.t('all') }}</option>
          </select>
          <select [(ngModel)]="type" (change)="pager.reset(); load()" aria-label="Type">
            <option value="">Type: {{ i18n.t('all') }}</option>
            @for (t of typeNames; track t.k) { <option [value]="t.k">{{ t.v }}</option> }
          </select>
        </div>
      </div>
      <div class="ptx-table-wrap">
        <table class="ptx-table">
          <thead><tr><th>Request</th><th>{{ i18n.t('upin') }} / ref</th><th class="num">{{ i18n.t('amount') }}</th><th>{{ i18n.t('reason') }}</th><th>Requested by</th><th>{{ i18n.t('status') }}</th><th></th></tr></thead>
          <tbody>
            @for (a of rows(); track a.id) {
              <tr>
                <td>{{ name(a.approvalType) }}</td>
                <td>{{ a.upin || a.refNo }}@if (a.details?.effectiveFrom) {<br /><small class="ptx-muted">from {{ dmy(a.details.effectiveFrom) }} {{ a.details.orderReference || '' }}</small>}
                  @if (a.details?.billAfter !== undefined) {<br /><small class="ptx-muted">{{ a.details.periodLabel }}: bill ₹{{ a.details.billNow | number: '1.2-2' }} → ₹{{ a.details.billAfter | number: '1.2-2' }}</small>}</td>
                <td class="num">{{ a.amount === null ? '-' : '₹' + (a.amount | number: '1.2-2') }}</td>
                <td>{{ a.reason }}</td>
                <td>{{ a.requestedBy }}<br /><small class="ptx-muted">{{ dmy(a.requestedAt) }}</small></td>
                <td><span class="ptx-chip" [ngClass]="a.status">{{ a.status.toLowerCase() }}</span>
                  @if (a.decidedBy) {<br /><small class="ptx-muted">{{ a.decidedBy }}: {{ a.decisionRemark }}</small>}</td>
                <td>
                  @if (a.status === 'PENDING' && a.canDecide && a.requestedBy !== access.username) {
                    <button class="ptx-btn sm primary" (click)="decide(a, 'APPROVE')">Approve</button>
                    <button class="ptx-btn sm danger" (click)="decide(a, 'REJECT')">Reject</button>
                  } @else if (a.status === 'PENDING') {
                    <small class="ptx-muted">{{ a.requestedBy === access.username ? 'Your request' : 'Above your limit' }}</small>
                  }
                </td>
              </tr>
            } @empty { <tr><td colspan="7" class="ptx-muted">{{ i18n.t('noRecords') }}</td></tr> }
          </tbody>
        </table>
      </div>
      <app-ptx-pager [pager]="pager" (changed)="load()"></app-ptx-pager>
    </div>
  `,
})
export class PtxApprovalsComponent implements OnInit {
  @Input({ required: true }) access!: PtxAccess;
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  i18n = inject(PtxI18nService);
  dmy = dmy;
  typeNames = Object.keys(TYPE_NAME).map((k) => ({ k, v: TYPE_NAME[k] }));
  rows = signal<Approval[]>([]);
  pager = new Pager(10);
  status = 'PENDING';
  type = '';
  search = '';
  private timer?: ReturnType<typeof setTimeout>;

  ngOnInit(): void {
    this.load();
  }

  name(t: string): string {
    return TYPE_NAME[t] || t;
  }

  onSearch(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.pager.reset();
      this.load();
    }, 350);
  }

  load(): void {
    this.ptx.get('/approvals', { status: this.status, type: this.type, search: this.search, ...this.pager.query() }).subscribe({
      next: (r) => {
        this.rows.set(r.items);
        this.pager.total.set(r.total);
      },
      error: (e) => {
        this.rows.set([]);
        this.pager.total.set(0);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  async decide(a: Approval, decision: 'APPROVE' | 'REJECT'): Promise<void> {
    const remark = await this.dialog.prompt({
      title: `${decision === 'APPROVE' ? 'Approve' : 'Reject'}: ${this.name(a.approvalType)} ${a.upin || a.refNo || ''}`,
      message: `${a.amount !== null ? '₹' + a.amount + ' · ' : ''}${a.reason || ''}`, inputLabel: 'Your remark', required: true,
      confirmText: decision === 'APPROVE' ? 'Approve' : 'Reject',
    });
    if (!remark) return;
    this.ptx.post(`/approvals/${a.id}/decide`, { decision, remark }).subscribe({
      next: (r) => {
        this.dialog.showToast(r.message, 'success');
        this.load();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }
}
