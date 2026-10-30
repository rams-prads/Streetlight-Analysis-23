import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { WaterAccess, WaterApproval } from '../../../core/models/water.model';
import { WaterService } from '../../../core/services/water.service';
import { WaterI18nService } from '../../../core/services/water-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { dmy, errorText } from '../water-utils';

/** Maker-checker approvals: tariffs, bill corrections, receipt cancellations, refunds, waivers and write-offs. */
@Component({
  selector: 'app-water-approvals',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="wtr-card">
      <div class="wtr-row">
        <label>{{ i18n.t('status') }}
          <select [(ngModel)]="status" (change)="load()"><option value="PENDING">Waiting</option><option value="APPROVED">Approved</option><option value="REJECTED">Rejected</option></select>
        </label>
        <span class="wtr-spacer"></span>
        <button class="wtr-btn" (click)="load()">{{ i18n.t('refresh') }}</button>
      </div>
      <p class="wtr-muted">The person who raised a request can never decide it. Each role approves only up to its configured amount; larger amounts need the Commissioner (WB-46). Tariffs always need the Commissioner (WB-21).</p>
      <div class="wtr-table-wrap">
        <table class="wtr-table">
          <thead><tr><th>Type</th><th>Reference</th><th class="num">{{ i18n.t('amount') }}</th><th>{{ i18n.t('reason') }}</th><th>{{ i18n.t('requestedBy') }}</th><th>{{ i18n.t('status') }}</th><th></th></tr></thead>
          <tbody>
            @for (a of rows(); track a.id) {
              <tr>
                <td><b>{{ a.approvalType }}</b></td>
                <td>{{ a.refNo }}{{ a.consumerNo && a.consumerNo !== a.refNo ? ' · ' + a.consumerNo : '' }}<br /><small class="wtr-muted">{{ summary(a) }}</small></td>
                <td class="num">{{ a.amount !== null && a.amount !== undefined ? '₹' + (a.amount | number: '1.2-2') : '-' }}</td>
                <td>{{ a.reason }}</td>
                <td>{{ a.requestedBy }}<br /><small class="wtr-muted">{{ dmy(a.requestedAt) }}</small></td>
                <td><span class="wtr-chip" [ngClass]="a.status">{{ a.status }}</span>@if (a.decidedBy) {<br /><small>{{ a.decidedBy }}: {{ a.decisionRemark }}</small>}</td>
                <td>
                  @if (a.canDecide) {
                    <button class="wtr-btn sm teal" (click)="decide(a, 'APPROVE')">{{ i18n.t('approve') }}</button>
                    <button class="wtr-btn sm danger" (click)="decide(a, 'REJECT')">{{ i18n.t('reject') }}</button>
                  } @else if (a.status === 'PENDING') {
                    <small class="wtr-muted">{{ a.requestedBy === access.username ? 'Your request' : 'Needs another authority' }}</small>
                  }
                </td>
              </tr>
            } @empty { <tr><td colspan="7" class="wtr-muted">{{ i18n.t('noRecords') }}</td></tr> }
          </tbody>
        </table>
      </div>
    </div>
  `,
})
export class WaterApprovalsComponent implements OnInit {
  @Input() access!: WaterAccess;
  private water = inject(WaterService);
  private dialog = inject(DialogService);
  i18n = inject(WaterI18nService);
  dmy = dmy;
  status = 'PENDING';
  rows = signal<WaterApproval[]>([]);

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.water.approvals(this.status).subscribe({ next: (r) => this.rows.set(r), error: (e) => this.dialog.showToast(errorText(e), 'error') });
  }

  summary(a: WaterApproval): string {
    const d = a.details || {};
    if (a.approvalType === 'TARIFF') return `${d.categoryCode} v${d.version} from ${dmy(d.effectiveFrom)}: ${(d.slabs || []).map((s: any) => `≤${s.uptoKl ?? '∞'}@${s.ratePerKl}`).join(', ')}`;
    if (a.approvalType === 'REFUND') return `${d.refundType} · ${d.mode}`;
    if (a.approvalType === 'WAIVER' || a.approvalType === 'WRITE_OFF') return `on ${d.bucket}`;
    if (a.approvalType === 'BILL_ADJUSTMENT') return `bill ${d.billNo}`;
    return '';
  }

  async decide(a: WaterApproval, decision: 'APPROVE' | 'REJECT'): Promise<void> {
    const remark = await this.dialog.prompt({ title: `${decision === 'APPROVE' ? 'Approve' : 'Reject'} ${a.approvalType} ${a.refNo || ''}`,
      inputLabel: 'Remark (recorded)', required: true });
    if (!remark) return;
    this.water.post(`/approvals/${a.id}/decide`, { decision, remark }).subscribe({
      next: (r) => {
        this.dialog.showToast(r.message, 'success');
        this.load();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }
}
