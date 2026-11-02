import { Component, ElementRef, Input, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Certificate, CitizenAccount, DemandNotice, PtxAccess, PtxCase, Receipt } from '../../../core/models/ptx.model';
import { PtxService } from '../../../core/services/ptx.service';
import { PtxI18nService } from '../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { IconComponent } from '../../../shared/components/icon/icon.component';
import { PtxCalcSheetComponent } from '../shared/ptx-calc-sheet.component';
import { PtxDocumentComponent } from '../shared/ptx-document.component';
import { CaseFormDialogComponent } from '../cases/dialogs/case-form-dialog/case-form-dialog.component';
import { PtxEmblemComponent } from '../shared/ptx-emblem.component';
import { dmy, errorText } from '../ptx-utils';

/** Pages of the portal. 'home' lists the citizen's properties; the rest belong to the property that is open. */
type Page = 'home' | 'find' | 'track' | 'property' | 'paid' | 'bills' | 'tax' | 'certs' | 'complaint' | 'requests' | 'doc';

interface MyProperty {
  upin: string;
  oldAssessmentNo: string | null;
  doorNo: string | null;
  address: string;
  wardNumber: number | null;
  wardName: string | null;
  ownerNames: string;
  status: string;
  totalDue: number;
  payNow: number;
  mobileNumber: string;
}

/**
 * Citizen portal, separate from the staff screens and built for ease of use (SRS 3.1.1): the citizen's properties are listed
 * after they prove each one once (property number and the owner's registered mobile), the amount due is the first thing on
 * the page with one button to pay, and every other service is one tap away (PT-31, PT-40, PT-47, PT-52). Telugu / English.
 */
@Component({
  selector: 'app-ptx-citizen',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent, PtxCalcSheetComponent, PtxDocumentComponent, CaseFormDialogComponent, PtxEmblemComponent],
  templateUrl: './ptx-citizen.component.html',
})
export class PtxCitizenComponent implements OnInit {
  @Input({ required: true }) access!: PtxAccess;
  @Input() displayName = '';
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  private host = inject(ElementRef<HTMLElement>);
  i18n = inject(PtxI18nService);
  dmy = dmy;

  page = signal<Page>('home');
  mine = signal<MyProperty[] | null>(null);
  acct = signal<CitizenAccount | null>(null);
  /** Whether the open property is saved under this sign-in. */
  saved = signal(false);
  receipt = signal<Receipt | null>(null);
  bill = signal<DemandNotice | null>(null);
  cert = signal<Certificate | null>(null);
  docKind = signal<'RECEIPT' | 'DEMAND' | 'CERTIFICATE'>('RECEIPT');
  taxSheets = signal<any[]>([]);
  tracked = signal<PtxCase | null>(null);
  complaintView = signal<any | null>(null);
  addOpen = signal(false);
  otherAmount = signal(false);
  applyOpen = signal(false);
  busy = signal(false);

  number = '';
  mobile = '';
  addNumber = '';
  addMobile = '';
  trackNo = '';
  trackMobile = '';
  custom = 0;
  objectionText = '';
  petitionText = '';
  complaint = { category: '', description: '' };
  private backTo: Page = 'property';

  ngOnInit(): void {
    this.loadMine();
  }

  /** English or Telugu text for the few portal phrases that are not in the shared dictionary. */
  L(en: string, te: string): string {
    return this.i18n.lang() === 'te' ? te : en;
  }

  greeting(): string {
    const h = new Date().getHours();
    const hello = this.L(h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening', 'నమస్కారం');
    return this.displayName ? `${hello}, ${this.displayName}` : hello;
  }

  /** The portal scrolls inside the Property Tax area, so a new page starts at its top. */
  private toTop(): void {
    (this.host.nativeElement as HTMLElement).closest('.ptx')?.scrollTo({ top: 0 });
  }

  private fail = (e: unknown) => {
    this.busy.set(false);
    this.dialog.showToast(errorText(e), 'error');
  };

  private q() {
    return { number: this.acct()?.property.upin || this.number.trim(), mobile: this.mobile };
  }

  // ---- your properties ----
  loadMine(): void {
    this.ptx.get<MyProperty[]>('/citizen/my-properties').subscribe({ next: (r) => this.mine.set(r), error: (e) => { this.mine.set([]); this.fail(e); } });
  }

  totalDue(): number {
    return (this.mine() || []).reduce((n, p) => n + Math.max(0, p.totalDue), 0);
  }

  addProperty(): void {
    this.busy.set(true);
    this.ptx.post('/citizen/my-properties', { number: this.addNumber.trim(), mobileNumber: this.addMobile }).subscribe({
      next: (r) => {
        this.busy.set(false);
        this.dialog.showToast(r.message, 'success');
        this.addOpen.set(false);
        this.addNumber = '';
        this.addMobile = '';
        this.loadMine();
      },
      error: this.fail,
    });
  }

  async removeProperty(p: MyProperty): Promise<void> {
    const ok = await this.dialog.confirm({ title: this.L('Remove from your account?', 'మీ ఖాతా నుండి తొలగించాలా?'),
      message: this.L(`${p.upin} will no longer be listed here. You can add it again any time.`, `${p.upin} ఇక్కడ కనిపించదు. ఎప్పుడైనా మళ్లీ జోడించవచ్చు.`) });
    if (!ok) return;
    this.ptx.delete(`/citizen/my-properties/${encodeURIComponent(p.upin)}`).subscribe({
      next: () => {
        this.goHome();
        this.loadMine();
      },
      error: this.fail,
    });
  }

  openMine(p: MyProperty): void {
    this.number = p.upin;
    this.mobile = p.mobileNumber;
    this.find(true);
  }

  saveThis(): void {
    this.busy.set(true);
    this.ptx.post('/citizen/my-properties', { number: this.acct()!.property.upin, mobileNumber: this.mobile }).subscribe({
      next: (r) => {
        this.busy.set(false);
        this.saved.set(true);
        this.dialog.showToast(r.message, 'success');
        this.loadMine();
      },
      error: this.fail,
    });
  }

  // ---- a property ----
  find(isSaved = false): void {
    this.busy.set(true);
    this.ptx.citizenAccount(this.number.trim(), this.mobile).subscribe({
      next: (a) => {
        this.busy.set(false);
        this.acct.set(a);
        this.saved.set(isSaved || (this.mine() || []).some((m) => m.upin === a.property.upin));
        this.custom = a.payNow;
        this.otherAmount.set(false);
        this.tracked.set(null);
        this.complaintView.set(null);
        this.page.set('property');
        this.toTop();
      },
      error: this.fail,
    });
  }

  goHome(): void {
    this.acct.set(null);
    this.tracked.set(null);
    this.page.set('home');
    this.loadMine();
  }

  show(p: Page): void {
    this.page.set(p);
    this.toTop();
  }

  back(): void {
    this.page.set(this.page() === 'doc' ? this.backTo : 'property');
  }

  refresh(): void {
    this.ptx.citizenAccount(this.q().number, this.mobile).subscribe({ next: (a) => this.acct.set(a), error: this.fail });
  }

  /** Online payment through the gateway stand-in. A fresh order is created per click; the bank page is simulated. */
  pay(amount: number): void {
    const upin = this.acct()!.property.upin;
    this.busy.set(true);
    this.ptx.post('/payments/online/initiate', { upin, amount: Number(amount), channel: 'PORTAL' }).subscribe({
      next: (o) =>
        this.ptx.post('/payments/online/stub-gateway', { orderId: o.orderId, outcome: 'SUCCESS' }).subscribe({
          next: (r) => {
            const no = r.receipt?.receiptNo;
            this.ptx.get<Receipt>(`/citizen/receipt/${encodeURIComponent(no)}`, this.q()).subscribe({
              next: (full) => {
                this.busy.set(false);
                this.receipt.set(full);
                this.show('paid');
                this.otherAmount.set(false);
                this.refresh();
                this.loadMine();
              },
              error: this.fail,
            });
          },
          error: this.fail,
        }),
      error: this.fail,
    });
  }

  private openDoc(kind: 'RECEIPT' | 'DEMAND' | 'CERTIFICATE'): void {
    this.backTo = this.page() === 'doc' ? this.backTo : this.page();
    this.docKind.set(kind);
    this.show('doc');
  }

  showReceipt(no: string): void {
    this.ptx.get<Receipt>(`/citizen/receipt/${encodeURIComponent(no)}`, this.q()).subscribe({ next: (r) => { this.receipt.set(r); this.openDoc('RECEIPT'); }, error: this.fail });
  }

  showBill(no: string): void {
    this.ptx.get<DemandNotice>(`/citizen/demand/${encodeURIComponent(no)}`, this.q()).subscribe({ next: (d) => { this.bill.set(d); this.openDoc('DEMAND'); }, error: this.fail });
  }

  showTax(): void {
    this.ptx.get('/citizen/calculation', this.q()).subscribe({ next: (r) => { this.taxSheets.set(r); this.show('tax'); }, error: this.fail });
  }

  async certificate(certType: 'TAX_PAID' | 'ASSESSMENT_EXTRACT' | 'NOC'): Promise<void> {
    let purpose: string | null = null;
    if (certType === 'NOC') {
      purpose = await this.dialog.prompt({ title: 'No Objection Certificate', message: 'It is issued once nothing is due and no application is pending on the property.',
        inputLabel: 'What is it for?', placeholder: 'e.g. Sale of the property, bank loan', required: true });
      if (!purpose) return;
    }
    this.ptx.post<Certificate>('/citizen/certificates', { upin: this.acct()!.property.upin, certType, purpose, mobileNumber: this.mobile }).subscribe({
      next: (c) => { this.cert.set(c); this.openDoc('CERTIFICATE'); this.refresh(); },
      error: this.fail,
    });
  }

  noDues(): void {
    this.ptx.post<Certificate>('/citizen/no-dues-certificate', { upin: this.acct()!.property.upin, mobileNumber: this.mobile }).subscribe({
      next: (c) => { this.cert.set(c); this.openDoc('CERTIFICATE'); this.refresh(); },
      error: this.fail,
    });
  }

  showCert(no: string): void {
    this.ptx.get<Certificate>(`/citizen/certificate/${encodeURIComponent(no)}`, this.q()).subscribe({ next: (c) => { this.cert.set(c); this.openDoc('CERTIFICATE'); }, error: this.fail });
  }

  // ---- applications, objections, petitions ----
  trackCase(no: string): void {
    this.trackNo = no;
    this.trackMobile = this.mobile;
    this.track();
  }

  track(): void {
    this.ptx.get<PtxCase>(`/citizen/cases/${encodeURIComponent(this.trackNo.trim())}`, { mobile: this.trackMobile }).subscribe({
      next: (c) => this.tracked.set(c),
      error: (e) => { this.tracked.set(null); this.fail(e); },
    });
  }

  objectTo(no: string): void {
    this.busy.set(true);
    this.ptx.post(`/citizen/cases/${encodeURIComponent(no)}/objection`, { mobileNumber: this.trackMobile || this.mobile, text: this.objectionText }).subscribe({
      next: () => {
        this.busy.set(false);
        this.objectionText = '';
        this.dialog.showToast('Your objection was received. The Revenue Officer will decide it.', 'success');
        this.trackMobile = this.trackMobile || this.mobile;
        this.track();
      },
      error: this.fail,
    });
  }

  filePetition(no: string, level: string): void {
    const mobile = this.trackMobile || this.mobile;
    this.busy.set(true);
    this.ptx.post(`/citizen/cases/${encodeURIComponent(no)}/petition`, { level, grounds: this.petitionText, mobileNumber: mobile }).subscribe({
      next: (r) => {
        this.busy.set(false);
        this.petitionText = '';
        this.dialog.showToast(`${r.message}. Keep the number ${r.petitionNo}; you will be told the decision by SMS.`, 'success');
        this.trackNo = no;
        this.trackMobile = mobile;
        this.track();
      },
      error: this.fail,
    });
  }

  onApplied(no: string | null): void {
    this.applyOpen.set(false);
    if (no) {
      this.trackCase(no);
      this.refresh();
      this.show('requests');
    }
  }

  // ---- complaints ----
  complaintHint(): string {
    const c = this.access.codes.COMPLAINT_CATEGORY?.find((x) => x.code === this.complaint.category);
    return (c?.extra as any)?.['hint'] || '';
  }

  fileComplaint(): void {
    this.busy.set(true);
    this.ptx.post('/complaints', { upin: this.acct()!.property.upin, category: this.complaint.category, description: this.complaint.description, mobileNumber: this.mobile, channel: 'PORTAL' }).subscribe({
      next: (c) => {
        this.busy.set(false);
        this.complaint = { category: '', description: '' };
        this.dialog.showToast(`Complaint ${c.complaintNo} received. ${c.statusText}`, 'success');
        this.refresh();
        this.show('requests');
      },
      error: this.fail,
    });
  }

  trackComplaint(no: string): void {
    this.ptx.get(`/citizen/complaints/${encodeURIComponent(no)}`, { mobile: this.mobile }).subscribe({ next: (c) => this.complaintView.set(c), error: this.fail });
  }

  requestCount(a: CitizenAccount): number {
    return (a.cases?.length || 0) + ((a as any).complaints?.length || 0);
  }
}
