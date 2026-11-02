import { Component, Input, OnChanges, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import * as QRCode from 'qrcode';
import { Certificate, DemandNotice, Notice, Receipt } from '../../../core/models/ptx.model';
import { PtxI18nService } from '../../../core/services/ptx-i18n.service';
import { PtxService } from '../../../core/services/ptx.service';
import { PtxCalcSheetComponent } from './ptx-calc-sheet.component';
import { dmy, printArea } from '../ptx-utils';

type DocKind = 'RECEIPT' | 'DEMAND' | 'NOTICE' | 'CERTIFICATE';

/**
 * Printable receipt, demand notice, assessment / reminder / recovery notice and no-dues certificate (PT-32, PT-42,
 * PT-47). Always in Telugu and English, with the document number, a QR code anyone can scan to check it is genuine
 * and, on bills, a UPI QR code to pay.
 */
@Component({
  selector: 'app-ptx-document',
  standalone: true,
  imports: [CommonModule, PtxCalcSheetComponent],
  template: `
    <div class="ptx-doc" [class.ptx-print-area]="!batch">
      <header class="ptx-doc-head">
        <div class="ptx-doc-logo" aria-label="GWMC logo">GWMC</div>
        <div>
          <div class="ptx-doc-org">{{ i18n.te('gwmcFull') }}</div>
          <div class="ptx-doc-org">{{ i18n.en('gwmcFull') }}</div>
          <div class="ptx-doc-sub">{{ i18n.both('propertyTaxDept') }}</div>
        </div>
        <div class="ptx-doc-kind">{{ i18n.both(title()) }}</div>
      </header>

      @if (kind === 'RECEIPT' && receipt; as r) {
        <div class="ptx-doc-grid">
          <div><span>{{ i18n.both('receiptNo') }}</span><b>{{ r.receiptNo }}</b></div>
          <div><span>{{ i18n.both('date') }}</span><b>{{ dmy(r.receiptDate) }}</b></div>
          <div><span>{{ i18n.both('upin') }}</span><b>{{ r.upin }}</b></div>
          <div><span>{{ i18n.both('owner') }}</span><b>{{ (r.ownerNames || []).join(', ') || r.payerName || '-' }}</b></div>
          <div class="wide"><span>{{ i18n.both('address') }}</span><b>{{ r.address || '-' }}</b></div>
          <div><span>{{ i18n.both('paymentMode') }}</span><b>{{ r.paymentMode }} · {{ r.channel }}{{ r.instrumentNo ? ' · ' + r.instrumentNo : '' }}</b></div>
          <div><span>{{ i18n.both('status') }}</span><b [class.bad]="r.status !== 'VALID'">{{ r.status === 'VALID' ? 'Valid' : r.status }}</b></div>
        </div>
        <div class="ptx-doc-sums">
          @for (a of allocation(r); track a.k) {
            <div><span>{{ i18n.both('allocation') }}: {{ bucketName(a.k) }}</span><b>₹{{ a.v | number: '1.2-2' }}</b></div>
          }
          @if (r.schemeBenefit) { <div><span>{{ i18n.both('schemeSaving') }}</span><b>₹{{ r.schemeBenefit | number: '1.2-2' }}</b></div> }
          <div class="total"><span>{{ i18n.both('receivedWithThanks') }}</span><b>₹{{ r.amount | number: '1.2-2' }}</b></div>
        </div>
      }

      @if (kind === 'DEMAND' && demand; as d) {
        <div class="ptx-doc-grid">
          <div><span>{{ i18n.both('demandNo') }}</span><b>{{ d.demandNo }}</b></div>
          <div><span>{{ i18n.both('upin') }}</span><b>{{ d.upin }}</b></div>
          <div><span>{{ i18n.both('oldNo') }}</span><b>{{ d.oldAssessmentNo || '-' }}</b></div>
          <div><span>{{ i18n.both('owner') }}</span><b>{{ d.ownerNames.join(', ') }}</b></div>
          <div class="wide"><span>{{ i18n.both('address') }}</span><b>{{ d.address }}</b></div>
          <div><span>{{ i18n.both('ward') }}</span><b>{{ d.wardNumber }} - {{ d.wardName }}</b></div>
          <div><span>{{ i18n.both('period') }}</span><b>{{ d.periodLabel }}</b></div>
        </div>
        <div class="ptx-doc-sums">
          @for (c of components(d.components); track c.k) {
            <div><span>{{ i18n.both(c.k) }}</span><b>₹{{ c.v | number: '1.2-2' }}</b></div>
          }
          @if (d.revised) { <div><span>Revised / సవరణ</span><b>₹{{ d.revised | number: '1.2-2' }}</b></div> }
          <div class="em"><span>{{ i18n.both('current') }}</span><b>₹{{ d.dues.current | number: '1.2-2' }}</b></div>
          <div><span>{{ i18n.both('arrearsLabel') }}</span><b>₹{{ d.dues.arrears | number: '1.2-2' }}</b></div>
          <div><span>{{ i18n.both('interest') }}</span><b>₹{{ d.dues.interest | number: '1.2-2' }}</b></div>
          @if (d.dues.fees) { <div><span>{{ i18n.both('fees') }}</span><b>₹{{ d.dues.fees | number: '1.2-2' }}</b></div> }
          @if (d.dues.advanceHeld) { <div><span>{{ i18n.both('advanceHeld') }}</span><b>- ₹{{ d.dues.advanceHeld | number: '1.2-2' }}</b></div> }
          <div class="total"><span>{{ i18n.both('totalPayable') }}</span><b>₹{{ d.dues.netPayable | number: '1.2-2' }}</b></div>
          <div class="due"><span>{{ i18n.both('dueDate') }}</span><b>{{ dmy(d.dueDate) }}</b></div>
        </div>
        <p class="ptx-doc-note">Interest is added on tax not paid by the due date. / గడువు తేదీలోపు చెల్లించని పన్నుపై వడ్డీ విధించబడుతుంది.</p>
      }

      @if (kind === 'NOTICE' && notice; as n) {
        <div class="ptx-doc-grid">
          <div><span>{{ i18n.both('noticeNo') }}</span><b>{{ n.noticeNo }}</b></div>
          <div><span>{{ i18n.both('date') }}</span><b>{{ dmy(n.issuedAt) }}</b></div>
          <div><span>{{ i18n.both('upin') }}</span><b>{{ n.upin }}</b></div>
          @if (n.content?.ownerNames) { <div><span>{{ i18n.both('owner') }}</span><b>{{ n.content.ownerNames.join(', ') }}</b></div> }
          <div class="wide"><span>{{ i18n.both('address') }}</span><b>{{ n.address }}</b></div>
          <div><span>{{ i18n.both('ward') }}</span><b>{{ n.wardNumber }}{{ n.wardName ? ' - ' + n.wardName : '' }}</b></div>
        </div>
        @if (n.noticeType === 'ASSESSMENT') {
          <p class="ptx-doc-lead">{{ n.content.typeLabel }} · {{ n.content.applicationNo }}</p>
          <app-ptx-calc-sheet [sheet]="n.content.calculation" [detailed]="true"></app-ptx-calc-sheet>
          <p class="ptx-doc-lead">{{ objection('te', n.content.objectionDays) }}<br />{{ objection('en', n.content.objectionDays) }}</p>
        } @else if (n.content?.dues; as dues) {
          <div class="ptx-doc-sums">
            <div><span>{{ i18n.both('current') }}</span><b>₹{{ dues.current | number: '1.2-2' }}</b></div>
            <div><span>{{ i18n.both('arrearsLabel') }}</span><b>₹{{ dues.arrears | number: '1.2-2' }}</b></div>
            <div><span>{{ i18n.both('interest') }}</span><b>₹{{ dues.interest | number: '1.2-2' }}</b></div>
            @if (dues.fees) { <div><span>{{ i18n.both('fees') }}</span><b>₹{{ dues.fees | number: '1.2-2' }}</b></div> }
            <div class="total"><span>{{ i18n.both('totalPayable') }}</span><b>₹{{ dues.netPayable | number: '1.2-2' }}</b></div>
          </div>
          <p class="ptx-doc-lead">
            @if (n.noticeType === 'RECOVERY') {
              ఈ బకాయిని వెంటనే చెల్లించకపోతే చట్ట ప్రకారం వసూలు చర్యలు తీసుకోబడతాయి. / If these dues are not paid at once, recovery action will follow as provided by law.
            } @else {
              దయచేసి ఈ బకాయిని వెంటనే చెల్లించండి. / Please pay these dues at the earliest to avoid further interest.
            }
          </p>
        }
      }

      @if (kind === 'CERTIFICATE' && certificate; as c) {
        <div class="ptx-doc-grid">
          <div><span>{{ i18n.both('certificateNo') }}</span><b>{{ c.certificateNo }}</b></div>
          <div><span>{{ i18n.both('issuedOn') }}</span><b>{{ dmy(c.issuedOn) }}</b></div>
          <div><span>{{ i18n.both('upin') }}</span><b>{{ c.upin }}</b></div>
          <div><span>{{ i18n.both('oldNo') }}</span><b>{{ c.oldAssessmentNo || '-' }}</b></div>
          <div><span>{{ i18n.both('owner') }}</span><b>{{ (c.ownerNames || []).join(', ') }}</b></div>
          <div class="wide"><span>{{ i18n.both('address') }}</span><b>{{ c.address }}</b></div>
          <div><span>{{ i18n.both('paidUpTo') }}</span><b>{{ c['paidUpToLabel'] || '-' }}</b></div>
          <div><span>{{ i18n.both('validUntil') }}</span><b>{{ dmy(c.validUntil) }}</b></div>
          @if (c.purpose) { <div class="wide"><span>{{ i18n.both('purpose') }}</span><b>{{ c.purpose }}</b></div> }
        </div>
        @switch (c.certType) {
          @case ('TAX_PAID') {
            <div class="ptx-table-wrap">
              <table class="ptx-table compact">
                <thead><tr><th>{{ i18n.both('receiptNo') }}</th><th>{{ i18n.both('date') }}</th><th>{{ i18n.both('paymentMode') }}</th><th class="num">{{ i18n.both('amount') }}</th></tr></thead>
                <tbody>
                  @for (r of c.content?.receipts || []; track r.receiptNo) {
                    <tr><td>{{ r.receiptNo }}</td><td>{{ dmy(r.date) }}</td><td>{{ r.mode }}</td><td class="num">₹{{ r.amount | number: '1.2-2' }}</td></tr>
                  }
                </tbody>
              </table>
            </div>
            <div class="ptx-doc-sums">
              <div><span>{{ i18n.both('totalPaid') }}</span><b>₹{{ c.content?.totalPaid | number: '1.2-2' }}</b></div>
              <div class="total"><span>{{ i18n.both('balanceDue') }}</span><b>₹{{ c.content?.balanceDue | number: '1.2-2' }}</b></div>
            </div>
            <p class="ptx-doc-lead">{{ i18n.te('taxPaidText') }}<br />{{ i18n.en('taxPaidText') }}</p>
          }
          @case ('ASSESSMENT_EXTRACT') {
            <div class="ptx-doc-grid">
              <div><span>Assessment no.</span><b>{{ c.content?.assessmentNo }}</b></div>
              <div><span>{{ i18n.both('period') }}</span><b>{{ dmy(c.content?.effectiveFrom) }}</b></div>
              <div><span>{{ i18n.both('siteArea') }}</span><b>{{ c.content?.siteAreaSqyd }}</b></div>
              <div><span>{{ i18n.both('builtYear') }}</span><b>{{ c.content?.constructionYear || '-' }}</b></div>
              <div><span>Exemption</span><b>{{ c.content?.exemptionCode || '-' }}</b></div>
              <div><span>Road class</span><b>{{ c.content?.roadClass || '-' }}</b></div>
            </div>
            <div class="ptx-table-wrap">
              <table class="ptx-table compact">
                <thead><tr><th>{{ i18n.both('floor') }}</th><th>{{ i18n.both('usage') }}</th><th>{{ i18n.both('construction') }}</th><th class="num">Sq ft</th></tr></thead>
                <tbody>
                  @for (f of c.content?.floors || []; track $index) {
                    <tr><td>{{ f.floorNo === 0 ? 'Ground' : f.floorNo }}{{ f.portion && f.portion !== 'FULL' ? ' · ' + f.portion.toLowerCase() : '' }}</td><td>{{ f.usageCode }}</td><td>{{ f.constructionCode }}</td><td class="num">{{ f.builtupSqft }}</td></tr>
                  }
                </tbody>
              </table>
            </div>
            <div class="ptx-doc-sums">
              @for (k of componentList(c.content?.components); track k.k) { <div><span>{{ i18n.both(k.k) }}</span><b>₹{{ k.v | number: '1.2-2' }}</b></div> }
              <div class="total"><span>{{ i18n.both('annualTax') }}</span><b>₹{{ c.content?.annualTax | number: '1.2-2' }}</b></div>
            </div>
            <p class="ptx-doc-lead">{{ i18n.te('extractText') }}<br />{{ i18n.en('extractText') }}</p>
          }
          @case ('NOC') {
            <p class="ptx-doc-lead">{{ i18n.te('nocText') }}<br />{{ i18n.en('nocText') }}</p>
          }
          @default {
            <p class="ptx-doc-lead">{{ i18n.te('noDuesText') }}<br />{{ i18n.en('noDuesText') }}</p>
          }
        }
      }

      <footer class="ptx-doc-foot">
        <div class="ptx-qr">
          @if (verifyQr()) { <img [src]="verifyQr()" alt="Verification QR code" /> }
          <small>{{ i18n.te('scanToVerify') }}<br />{{ i18n.en('scanToVerify') }}<br />{{ i18n.both('verifyCode') }}: <b>{{ code() }}</b></small>
        </div>
        @if (upiQr()) {
          <div class="ptx-qr">
            <img [src]="upiQr()" alt="UPI payment QR code" />
            <small>{{ i18n.te('scanToPay') }}<br />{{ i18n.en('scanToPay') }}</small>
          </div>
        }
      </footer>
      <p class="ptx-doc-note">{{ i18n.te('computerGenerated') }} {{ i18n.en('computerGenerated') }}</p>
    </div>
    @if (!batch) {
      <div class="ptx-row no-print">
        <button class="ptx-btn primary" (click)="print()">{{ i18n.t('printPdf') }}</button>
      </div>
    }
  `,
})
export class PtxDocumentComponent implements OnChanges {
  @Input() kind: DocKind = 'RECEIPT';
  @Input() receipt: Receipt | null = null;
  @Input() demand: DemandNotice | null = null;
  @Input() notice: Notice | null = null;
  @Input() certificate: Certificate | null = null;
  /** Printed together with other bills: no print button and no page of its own; the page that holds the batch prints them (PT-20). */
  @Input() batch = false;

  i18n = inject(PtxI18nService);
  private ptx = inject(PtxService);
  verifyQr = signal<string>('');
  upiQr = signal<string>('');
  code = signal<string>('');
  dmy = dmy;

  title(): string {
    if (this.kind === 'RECEIPT') return 'paymentReceipt';
    if (this.kind === 'DEMAND') return 'demandNotice';
    if (this.kind === 'CERTIFICATE') {
      return ({ TAX_PAID: 'taxPaidCertificate', ASSESSMENT_EXTRACT: 'assessmentExtract', NOC: 'nocCertificate' } as any)[this.certificate?.certType || ''] || 'noDuesCertificate';
    }
    const t = this.notice?.noticeType;
    return t === 'ASSESSMENT' ? 'assessmentNotice' : t === 'REMINDER' ? 'reminderNotice' : t === 'RECOVERY' ? 'recoveryNotice' : 'demandNotice';
  }

  async ngOnChanges(): Promise<void> {
    const doc: any = { RECEIPT: this.receipt, DEMAND: this.demand, NOTICE: this.notice, CERTIFICATE: this.certificate }[this.kind];
    this.verifyQr.set('');
    this.upiQr.set('');
    if (!doc) return;
    this.code.set(doc.verificationCode);
    const verifyUrl = this.ptx.verifyUrl(doc.verifyPath);
    if (verifyUrl) this.verifyQr.set(await QRCode.toDataURL(verifyUrl, { margin: 1, width: 132 }));
    if (this.kind === 'DEMAND' && this.demand?.upiUri && this.demand.dues.netPayable > 0) {
      this.upiQr.set(await QRCode.toDataURL(this.demand.upiUri, { margin: 1, width: 132 }));
    }
  }

  allocation(r: Receipt): { k: string; v: number }[] {
    return Object.keys(r.allocation || {}).map((k) => ({ k, v: r.allocation[k] }));
  }

  componentList(c: { [code: string]: number } | undefined): { k: string; v: number }[] {
    return this.components(c || {});
  }

  components(c: { [code: string]: number }): { k: string; v: number }[] {
    return Object.keys(c || {}).map((k) => ({ k, v: c[k] }));
  }

  bucketName(k: string): string {
    if (k.startsWith('Scheme:')) return k;
    return this.i18n.both(k);
  }

  objection(lang: 'te' | 'en', days: number): string {
    return (lang === 'te' ? this.i18n.te('objectionText') : this.i18n.en('objectionText')).replace('{days}', String(days ?? 15));
  }

  print(): void {
    printArea();
  }
}
