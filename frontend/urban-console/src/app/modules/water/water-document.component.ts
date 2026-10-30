import { Component, Input, OnChanges, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import * as QRCode from 'qrcode';
import { WaterBill, WaterReceipt } from '../../core/models/water.model';
import { WaterI18nService } from '../../core/services/water-i18n.service';
import { WaterService } from '../../core/services/water.service';
import { dmy, printArea } from './water-utils';

/**
 * Printable bill / receipt (WB-24, WB-31). Always bilingual (Telugu and English), with the GWMC mark,
 * the unique document number, a QR code anyone can scan to check it is genuine and, on bills, a UPI QR code.
 */
@Component({
  selector: 'app-water-document',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="wtr-doc wtr-print-area">
      <header class="wtr-doc-head">
        <div class="wtr-doc-logo" aria-label="GWMC logo">GWMC</div>
        <div>
          <div class="wtr-doc-org">{{ i18n.te('gwmcFull') }}</div>
          <div class="wtr-doc-org">{{ i18n.en('gwmcFull') }}</div>
          <div class="wtr-doc-sub">{{ i18n.both('waterSupply') }}</div>
        </div>
        <div class="wtr-doc-kind">{{ kind === 'BILL' ? i18n.both('waterBill') : i18n.both('paymentReceipt') }}</div>
      </header>

      @if (kind === 'BILL' && bill; as b) {
        <div class="wtr-doc-grid">
          <div><span>{{ i18n.both('billNo') }}</span><b>{{ b.billNo }}</b></div>
          <div><span>{{ i18n.both('consumerNo') }}</span><b>{{ b.consumerNo }}</b></div>
          <div><span>{{ i18n.both('consumerName') }}</span><b>{{ b.consumerName }}</b></div>
          <div><span>{{ i18n.both('address') }}</span><b>{{ b.address }}</b></div>
          <div><span>{{ i18n.both('ward') }}</span><b>{{ b.wardNumber }} - {{ b.wardName }}</b></div>
          <div><span>{{ i18n.both('category') }}</span><b>{{ b.categoryCode }} · {{ b.pipeSizeMm }} mm</b></div>
          <div><span>{{ i18n.both('period') }}</span><b>{{ dmy(b.periodFrom) }} – {{ dmy(b.periodTo) }}</b></div>
          <div><span>{{ i18n.both('billDate') }}</span><b>{{ dmy(b.billDate) }}</b></div>
          <div><span>{{ i18n.both('basis') }}</span><b>{{ b.basis }}</b></div>
          <div><span>{{ i18n.both('previousReading') }}</span><b>{{ b.previousReading ?? '-' }}</b></div>
          <div><span>{{ i18n.both('currentReading') }}</span><b>{{ b.currentReading ?? '-' }}</b></div>
          <div><span>{{ i18n.both('consumption') }}</span><b>{{ b.consumptionKl }}</b></div>
        </div>
        <table class="wtr-table compact">
          <thead><tr><th>{{ i18n.both('slab') }}</th><th class="num">{{ i18n.both('units') }}</th><th class="num">{{ i18n.both('rate') }}</th><th class="num">{{ i18n.both('amount') }}</th></tr></thead>
          <tbody>
            @for (s of b.slabBreakup; track $index) {
              <tr>
                <td>{{ slabLabel(s) }}</td>
                <td class="num">{{ s.units ?? '' }}</td>
                <td class="num">{{ s.rate ?? s.monthlyRate ?? '' }}</td>
                <td class="num">{{ s.amount !== undefined ? (s.amount | number: '1.2-2') : '' }}</td>
              </tr>
            }
          </tbody>
        </table>
        <div class="wtr-doc-sums">
          <div><span>{{ i18n.both('waterCharge') }}</span><b>₹{{ b.waterCharge | number: '1.2-2' }}</b></div>
          <div><span>{{ i18n.both('fixedCharge') }}</span><b>₹{{ b.fixedCharge | number: '1.2-2' }}</b></div>
          <div><span>{{ i18n.both('cess') }}</span><b>₹{{ b.cess | number: '1.2-2' }}</b></div>
          <div class="em"><span>{{ i18n.both('currentDemand') }}</span><b>₹{{ b.currentDemand | number: '1.2-2' }}</b></div>
          <div><span>{{ i18n.both('arrearsLabel') }}</span><b>₹{{ b.arrears | number: '1.2-2' }}</b></div>
          <div><span>{{ i18n.both('penalty') }}</span><b>₹{{ b.penalty | number: '1.2-2' }}</b></div>
          @if (b.otherDues) { <div><span>{{ i18n.both('fees') }}</span><b>₹{{ b.otherDues | number: '1.2-2' }}</b></div> }
          @if (b.advanceAdjusted) { <div><span>{{ i18n.both('advanceHeld') }}</span><b>- ₹{{ b.advanceAdjusted | number: '1.2-2' }}</b></div> }
          @if (b.approvedAdjustments) { <div><span>Approved correction / ఆమోదిత సవరణ</span><b>₹{{ b.approvedAdjustments | number: '1.2-2' }}</b></div> }
          <div class="total"><span>{{ i18n.both('totalPayable') }}</span><b>₹{{ b.totalPayable | number: '1.2-2' }}</b></div>
          <div class="due"><span>{{ i18n.both('dueDate') }}</span><b>{{ dmy(b.dueDate) }}</b></div>
        </div>
      }

      @if (kind === 'RECEIPT' && receipt; as r) {
        <div class="wtr-doc-grid">
          <div><span>{{ i18n.both('receiptNo') }}</span><b>{{ r.receiptNo }}</b></div>
          <div><span>{{ i18n.both('date') }}</span><b>{{ dmy(r.createdAt) }}</b></div>
          <div><span>{{ r.consumerNo ? i18n.both('consumerNo') : i18n.both('applicationNo') }}</span><b>{{ r.consumerNo || r.applicationNo }}</b></div>
          <div><span>{{ i18n.both('consumerName') }}</span><b>{{ r.consumerName || r.payerName || '-' }}</b></div>
          <div><span>{{ i18n.both('paymentMode') }}</span><b>{{ r.paymentMode }} · {{ r.channel }}{{ r.instrumentNo ? ' · ' + r.instrumentNo : '' }}</b></div>
          <div><span>{{ i18n.both('status') }}</span><b [class.bad]="r.status !== 'VALID'">{{ r.status }}</b></div>
        </div>
        <div class="wtr-doc-sums">
          @for (a of allocation(r); track a.k) {
            <div><span>{{ i18n.both('allocation') }}: {{ a.k }}</span><b>₹{{ a.v | number: '1.2-2' }}</b></div>
          }
          <div class="total"><span>{{ i18n.both('receivedWithThanks') }}</span><b>₹{{ r.amount | number: '1.2-2' }}</b></div>
        </div>
      }

      <footer class="wtr-doc-foot">
        <div class="wtr-qr">
          @if (verifyQr()) { <img [src]="verifyQr()" alt="Verification QR code" /> }
          <small>{{ i18n.te('scanToVerify') }}<br />{{ i18n.en('scanToVerify') }}<br />{{ i18n.both('verifyCode') }}: <b>{{ code() }}</b></small>
        </div>
        @if (upiQr()) {
          <div class="wtr-qr">
            <img [src]="upiQr()" alt="UPI payment QR code" />
            <small>{{ i18n.te('scanToPay') }}<br />{{ i18n.en('scanToPay') }}</small>
          </div>
        }
      </footer>
      <p class="wtr-doc-note">{{ i18n.te('computerGenerated') }} {{ i18n.en('computerGenerated') }}</p>
    </div>
    <div class="wtr-row no-print">
      <button class="wtr-btn primary" (click)="print()">{{ i18n.t('printPdf') }}</button>
    </div>
  `,
})
export class WaterDocumentComponent implements OnChanges {
  @Input() kind: 'BILL' | 'RECEIPT' = 'BILL';
  @Input() bill: WaterBill | null = null;
  @Input() receipt: WaterReceipt | null = null;

  i18n = inject(WaterI18nService);
  private water = inject(WaterService);
  verifyQr = signal<string>('');
  upiQr = signal<string>('');
  code = signal<string>('');
  dmy = dmy;

  async ngOnChanges(): Promise<void> {
    const doc = this.kind === 'BILL' ? this.bill : this.receipt;
    this.verifyQr.set('');
    this.upiQr.set('');
    if (!doc) return;
    this.code.set(doc.verificationCode);
    const verifyUrl = this.water.verifyUrl((doc as any).verifyPath);
    if (verifyUrl) this.verifyQr.set(await QRCode.toDataURL(verifyUrl, { margin: 1, width: 132 }));
    const upi = this.kind === 'BILL' ? this.bill?.upiUri : null;
    if (upi && (this.bill?.totalPayable ?? 0) > 0) this.upiQr.set(await QRCode.toDataURL(upi, { margin: 1, width: 132 }));
  }

  slabLabel(s: any): string {
    if (s.label === 'SLAB') return `${s.fromKl}–${s.toKl ?? '∞'} kL`;
    if (s.label === 'FLAT_RATE') return `Flat rate ${s.pipeSizeMm} mm × ${s.months} month(s)`;
    if (s.label === 'AVERAGE_BASIS') return `Average billing (${s.reason || 'no reading'})`;
    if (s.label === 'MINIMUM_CHARGE_TOP_UP') return 'Minimum charge top-up';
    if (s.label === 'FREE_ALLOWANCE') return `Free allowance 0–${s.toKl} kL`;
    return s.label;
  }

  allocation(r: WaterReceipt): { k: string; v: number }[] {
    return Object.keys(r.allocation || {}).map((k) => ({ k, v: r.allocation[k] }));
  }

  print(): void {
    printArea();
  }
}
