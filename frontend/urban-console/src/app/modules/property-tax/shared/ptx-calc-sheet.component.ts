import { Component, Input, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { CalcSheet } from '../../../core/models/ptx.model';
import { PtxI18nService } from '../../../core/services/ptx-i18n.service';
import { dmy } from '../ptx-utils';

/**
 * The calculation sheet in plain words (PT-11, PT-21): a short summary sentence for everyone, then each floor's
 * working and the rate table used, so an owner or auditor can check the tax by hand.
 */
@Component({
  selector: 'app-ptx-calc-sheet',
  standalone: true,
  imports: [CommonModule],
  template: `
    @if (sheet; as s) {
      <div class="ptx-calc">
        <div class="ptx-calc-head">
          <div>
            <span class="ptx-muted">{{ i18n.t('annualTax') }}</span>
            <b class="ptx-big">₹{{ s.annualTax | number: '1.2-2' }}</b>
          </div>
          @if (s.instalment) {
            <div>
              <span class="ptx-muted">{{ s.frequency === 'HALF_YEARLY' ? 'Each half-year' : 'Each year' }}</span>
              <b>₹{{ s.instalment | number: '1.2-2' }}</b>
            </div>
          }
          @if (s.effectiveFrom) {
            <div><span class="ptx-muted">From</span><b>{{ s.firstPeriodLabel || dmy(s.effectiveFrom) }}</b></div>
          }
          @if (s.rateZone) {
            <div><span class="ptx-muted">Rate zone</span><b>{{ s.rateZone }}</b></div>
          }
        </div>

        @if (s.parts?.length) {
          @for (p of s.parts; track $index) {
            <h4>{{ p.unitNo ? 'Unit ' + p.unitNo : 'Part ' + ($index + 1) }} — ₹{{ p.annualTax | number: '1.2-2' }} a year</h4>
            <ol class="ptx-steps">
              @for (step of p.steps; track $index) { <li>{{ step }}</li> }
            </ol>
          }
        } @else {
          <h4>{{ i18n.t('howCalculated') }}</h4>
          <ol class="ptx-steps">
            @for (step of s.steps; track $index) { <li>{{ step }}</li> }
          </ol>
          @if (detailed && floorLines().length) {
            <div class="ptx-table-wrap">
              <table class="ptx-table compact">
                <thead>
                  <tr>
                    <th>{{ i18n.t('floor') }}</th><th>{{ i18n.t('usage') }}</th><th>{{ i18n.t('construction') }}</th>
                    <th class="num">Sq ft</th><th class="num">₹/sq ft/month</th><th class="num">Factor</th>
                    <th class="num">Rental value</th><th class="num">Less wear</th><th class="num">Tax %</th><th class="num">Tax</th>
                  </tr>
                </thead>
                <tbody>
                  @for (l of floorLines(); track $index) {
                    <tr>
                      <td>{{ l['floorNo'] === 0 ? 'Ground' : l['floorNo'] }}{{ rowTag(l) }}</td><td>{{ l['usage'] }}</td><td>{{ l['kind'] === 'ROOFTOP' ? l['installation'] : l['construction'] }}</td>
                      <td class="num">{{ l['builtupSqft'] }}</td><td class="num">{{ l['monthlyRatePerSqft'] }}</td>
                      <td class="num">{{ l['occupancyFactor'] }}</td><td class="num">{{ l['grossArv'] | number: '1.0-2' }}</td>
                      <td class="num">{{ l['depreciationPercent'] }}%</td><td class="num">{{ l['taxRatePercent'] }}%</td>
                      <td class="num">{{ l['tax'] | number: '1.2-2' }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          }
        }
        @if (s.rateTableVersion) {
          <p class="ptx-muted small">
            Rate table v{{ s.rateTableVersion }} in force from {{ dmy(s.rateTableEffectiveFrom) }}@if (s.orderReference) {; {{ s.orderReference }}}.
          </p>
        }
      </div>
    }
  `,
})
export class PtxCalcSheetComponent {
  @Input() sheet: CalcSheet | null | undefined = null;
  @Input() detailed = true;
  i18n = inject(PtxI18nService);
  dmy = dmy;

  floorLines() {
    return (this.sheet?.lines || []).filter((l) => l.kind === 'FLOOR' || l.kind === 'ROOFTOP');
  }

  /** What kind of row this is, shown beside the floor number. */
  rowTag(l: any): string {
    if (l['kind'] === 'ROOFTOP') return ' · rooftop';
    if (l['declaredAccommodation']) return ' · guest accommodation';
    return ({ PART: ' · part of floor', COMMON: ' · common-area share' } as any)[l['portion']] || '';
  }
}
