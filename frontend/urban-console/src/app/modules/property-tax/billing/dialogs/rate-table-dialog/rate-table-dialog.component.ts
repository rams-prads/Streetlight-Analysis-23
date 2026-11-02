import { Component, EventEmitter, Input, OnInit, Output, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { PtxAccess, RateTable } from '../../../../../core/models/ptx.model';
import { PtxService } from '../../../../../core/services/ptx.service';
import { PtxI18nService } from '../../../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../../../core/services/dialog.service';
import { errorText, todayIso } from '../../../ptx-utils';

/**
 * Proposes a new rate table version, starting from a copy of the one in force (PT-10). It takes effect only after the
 * Commissioner approves it, and never from a past date.
 */
@Component({
  selector: 'app-rate-table-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './rate-table-dialog.component.html',
})
export class RateTableDialogComponent implements OnInit {
  @Input({ required: true }) access!: PtxAccess;
  @Input({ required: true }) base!: RateTable;
  @Output() closed = new EventEmitter<boolean>();
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  i18n = inject(PtxI18nService);

  rules: any = {};
  zones: string[] = [];
  effectiveFrom = '';
  orderReference = '';
  reason = '';
  busy = signal(false);
  readonly today = todayIso();

  ngOnInit(): void {
    this.rules = JSON.parse(JSON.stringify(this.base.rules));
    this.rules.rateZones.byWardNumber = this.rules.rateZones.byWardNumber || {};
    this.access.wards.forEach((w) => {
      if (!this.rules.rateZones.byWardNumber[w.wardNumber]) this.rules.rateZones.byWardNumber[w.wardNumber] = this.rules.rateZones.default;
    });
    this.zones = Object.keys(this.rules.monthlyRentalValuePerSqft || {});
    // rules added later are filled in with neutral values so older tables can be copied and extended
    this.rules.roadClassFactorPercent = this.rules.roadClassFactorPercent || {};
    (this.access.codes.ROAD_CLASS || []).forEach((c) => (this.rules.roadClassFactorPercent[c.code] ??= 100));
    this.rules.rooftopInstallations = this.rules.rooftopInstallations || {};
    (this.access.codes.ROOFTOP_TYPE || []).forEach((c) => (this.rules.rooftopInstallations[c.code] ??= { labelEn: c.nameEn, monthlyRatePerSqft: 0, usageCode: 'COMMERCIAL' }));
    this.rules.accommodation = this.rules.accommodation || { usageCode: 'COMMERCIAL', rateFactorPercent: 100 };
    this.rules.setbackPenalty = this.rules.setbackPenalty || { toleranceFt: 0, percentOfTax: 0 };
    const d = new Date();
    const nextFy = new Date(d.getMonth() >= 3 ? d.getFullYear() + 1 : d.getFullYear(), 3, 1);
    this.effectiveFrom = `${nextFy.getFullYear()}-04-01`;
  }

  usages() {
    return this.access.codes.USAGE || [];
  }

  constructions() {
    return this.access.codes.CONSTRUCTION || [];
  }

  addBand(): void {
    const bands = this.rules.depreciation;
    const last = bands[bands.length - 1];
    const from = last ? (last.toAge ?? last.fromAge) + 1 : 0;
    if (last && last.toAge === null) last.toAge = from - 1;
    bands.push({ fromAge: from, toAge: null, percent: 0 });
  }

  /** Numbers typed into inputs arrive as strings: turn them back into numbers before sending. */
  private numeric(value: any): any {
    if (Array.isArray(value)) return value.map((v) => this.numeric(v));
    if (value && typeof value === 'object') {
      const out: any = {};
      Object.keys(value).forEach((k) => (out[k] = this.numeric(value[k])));
      return out;
    }
    if (typeof value === 'string' && value.trim() !== '' && !isNaN(Number(value))) return Number(value);
    return value;
  }

  submit(): void {
    const rules = this.numeric(this.rules);
    // zone letters and codes stay text
    rules.rateZones.default = String(this.rules.rateZones.default);
    Object.keys(rules.rateZones.byWardNumber).forEach((k) => (rules.rateZones.byWardNumber[k] = String(this.rules.rateZones.byWardNumber[k])));
    Object.keys(rules.rooftopInstallations || {}).forEach((k) => {
      rules.rooftopInstallations[k].labelEn = String(this.rules.rooftopInstallations[k].labelEn);
      rules.rooftopInstallations[k].usageCode = String(this.rules.rooftopInstallations[k].usageCode);
    });
    rules.accommodation.usageCode = String(this.rules.accommodation.usageCode);
    (rules.cess || []).forEach((c: any, i: number) => {
      c.code = String(this.rules.cess[i].code);
      c.labelEn = String(this.rules.cess[i].labelEn);
      c.labelTe = String(this.rules.cess[i].labelTe ?? '');
    });
    rules.depreciation.forEach((b: any) => {
      if (b.toAge === '' || b.toAge === undefined) b.toAge = null;
    });
    this.busy.set(true);
    this.ptx.post('/rate-tables', { effectiveFrom: this.effectiveFrom, rules, orderReference: this.orderReference || null, reason: this.reason }).subscribe({
      next: (t) => {
        this.busy.set(false);
        this.dialog.showToast(`Rate table v${t.version} proposed. It waits for the Commissioner's approval under Approvals.`, 'success');
        this.closed.emit(true);
      },
      error: (e) => {
        this.busy.set(false);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }
}
