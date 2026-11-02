import { Component, EventEmitter, Input, OnInit, Output, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { PtxAccess, RateTable } from '../../../../../core/models/ptx.model';
import { PtxService } from '../../../../../core/services/ptx.service';
import { PtxI18nService } from '../../../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../../../core/services/dialog.service';
import { dmy, errorText, periodName } from '../../../ptx-utils';

/**
 * Raises the bills for a period (PT-30) or runs a general revision with an approved rate table (PT-15), for all wards
 * or chosen wards. Both are safe to repeat: a ward already done is skipped.
 */
@Component({
  selector: 'app-billing-run-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './billing-run-dialog.component.html',
})
export class BillingRunDialogComponent implements OnInit {
  @Input({ required: true }) access!: PtxAccess;
  @Input({ required: true }) kind!: 'DEMAND' | 'REVISION';
  @Input() periods: string[] = [];
  @Input() tables: RateTable[] = [];
  @Output() closed = new EventEmitter<boolean>();
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  i18n = inject(PtxI18nService);
  dmy = dmy;
  periodName = periodName;

  period = '';
  rateTableId = '';
  chosen: { [wardId: string]: boolean } = {};
  busy = signal(false);
  result = signal<any | null>(null);
  private ran = false;

  ngOnInit(): void {
    this.period = this.access.currentPeriod;
    const candidates = this.revisable();
    this.rateTableId = candidates[0]?.id || '';
  }

  revisable(): RateTable[] {
    return this.tables.filter((t) => t.status === 'APPROVED');
  }

  wardIds(): string[] {
    return Object.keys(this.chosen).filter((k) => this.chosen[k]);
  }

  async run(): Promise<void> {
    const wards = this.wardIds();
    const where = wards.length ? `${wards.length} ward(s)` : 'all wards';
    const ok = await this.dialog.confirm({
      title: this.kind === 'DEMAND' ? `Raise bills for ${periodName(this.period)}?` : 'Run the general revision?',
      message: this.kind === 'DEMAND'
        ? `Bills are raised for ${where}. Properties already billed for this period are not billed again. Owners get an SMS.`
        : `Every property in ${where} is reassessed with the chosen rates from their start date, and owners get an assessment notice.`,
      confirmText: 'Start',
    });
    if (!ok) return;
    this.busy.set(true);
    const req = this.kind === 'DEMAND'
      ? this.ptx.post('/demand/run', { period: this.period, wardIds: wards })
      : this.ptx.post('/revision/run', { rateTableId: this.rateTableId, wardIds: wards });
    req.subscribe({
      next: (r) => {
        this.busy.set(false);
        this.ran = true;
        this.result.set(r);
      },
      error: (e) => {
        this.busy.set(false);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  close(): void {
    this.closed.emit(this.ran);
  }
}
