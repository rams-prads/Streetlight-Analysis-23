import { Component, ElementRef, Input, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { APP_VERSION } from '../../../core/constants/version';
import { Certificate, CitizenAccount, DemandNotice, PtxAccess, PtxCase, Receipt } from '../../../core/models/ptx.model';
import { PtxService } from '../../../core/services/ptx.service';
import { PtxI18nService } from '../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { IconComponent } from '../../../shared/components/icon/icon.component';
import { PtxCalcSheetComponent } from '../shared/ptx-calc-sheet.component';
import { PtxDocumentComponent } from '../shared/ptx-document.component';
import { CaseFormDialogComponent } from '../cases/dialogs/case-form-dialog/case-form-dialog.component';
import { PtxEmblemComponent } from '../shared/ptx-emblem.component';
import { PtxCitizenMapDialogComponent } from './ptx-citizen-map-dialog.component';
import { DashOpen, PtxCitizenDashboardComponent } from './ptx-citizen-dashboard.component';
import { dmy, errorText, todayIso } from '../ptx-utils';

/** Pages of the portal. 'home' lists the citizen's properties; the rest belong to the property that is open. */
type Page = 'home' | 'find' | 'track' | 'property' | 'paid' | 'bills' | 'tax' | 'certs' | 'complaint' | 'requests' | 'doc' | 'utility';

type UtilityKind = 'ELECTRICITY' | 'WATER';

/** A preview of the other house bills (PT-IR-06: Water & Utility Billing is Module 2, not yet linked). Made up from the UPIN, so it looks the same each visit. */
interface UtilityBill {
  kind: UtilityKind;
  consumerNo: string;
  billNo: string;
  period: string;
  units: number;
  amount: number;
  dueDate: string;
  paid: boolean;
  history: { period: string; units: number; amount: number; paidOn: string }[];
}

/** Same key as the staff menu, so the collapsed / expanded choice is shared. */
const RAIL_KEY = 'urban_ptx_rail';

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
  latitude: number | null;
  longitude: number | null;
  /** OWN: the citizen's own property. OTHER: a family/friend's property they chose to keep after paying for it. */
  relation: 'OWN' | 'OTHER';
}

/**
 * Citizen portal, separate from the staff screens and built for ease of use (SRS 3.1.1): the citizen's properties are listed
 * after they prove each one once (property number and the owner's registered mobile), the amount due is the first thing on
 * the page with one button to pay, and every other service is one tap away (PT-31, PT-40, PT-47, PT-52). Telugu / English.
 */
@Component({
  selector: 'app-ptx-citizen',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent, PtxCalcSheetComponent, PtxDocumentComponent, CaseFormDialogComponent, PtxEmblemComponent,
    PtxCitizenDashboardComponent, PtxCitizenMapDialogComponent],
  templateUrl: './ptx-citizen.component.html',
})
export class PtxCitizenComponent implements OnInit, OnDestroy {
  @Input({ required: true }) access!: PtxAccess;
  @Input() displayName = '';
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  private host = inject(ElementRef<HTMLElement>);
  i18n = inject(PtxI18nService);
  /** Version and build shown at the foot of the menu, as in the platform's admin sidebar. */
  readonly appVersion = APP_VERSION;
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
  /** Which list the home page shows: the citizen's own properties, or ones they kept after paying for someone else. */
  homeTab = signal<'OWN' | 'OTHER'>('OWN');
  /** Set to show one property pinned on the map; null elsewhere. */
  mapProperty = signal<MyProperty | null>(null);
  /** Electricity/water bill preview (page 'utility'); made up locally, not from a server. */
  utilityBill = signal<UtilityBill | null>(null);
  busy = signal(false);
  /** Left menu: a slide-over drawer below 1024px, beside the page above it (where it can shrink to icons). */
  drawerOpen = signal(false);
  rail = signal<boolean>(this.stored(RAIL_KEY) === '1');

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

  // the menu button in the shared top bar asks Property Tax to open its menu
  private drawerHandler = () => this.drawerOpen.update((v) => !v);

  ngOnInit(): void {
    window.addEventListener('urban:ptx-nav', this.drawerHandler);
    this.loadMine();
  }

  ngOnDestroy(): void {
    window.removeEventListener('urban:ptx-nav', this.drawerHandler);
  }

  toggleRail(): void {
    this.rail.update((v) => !v);
    this.store(RAIL_KEY, this.rail() ? '1' : '0');
  }

  /** The menu entry to light up: a bill, receipt or certificate belongs to the page it was opened from, a new receipt to the property. */
  isPage(p: Page): boolean {
    const cur = this.page() === 'doc' ? this.backTo : this.page() === 'paid' ? 'property' : this.page();
    return cur === p;
  }

  openApply(): void {
    this.drawerOpen.set(false);
    this.applyOpen.set(true);
  }

  showOnMap(p: MyProperty): void {
    this.mapProperty.set(p);
  }

  private stored(k: string): string | null {
    try {
      return localStorage.getItem(k);
    } catch {
      return null;
    }
  }

  private store(k: string, v: string): void {
    try {
      localStorage.setItem(k, v);
    } catch {
      /* private mode: the choice is just not remembered */
    }
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

  /** The portal scrolls inside its page area beside the menu, so a new page starts at its top. Also closes the menu drawer. */
  private toTop(): void {
    this.drawerOpen.set(false);
    (this.host.nativeElement as HTMLElement).querySelector('.ptx-main')?.scrollTo({ top: 0 });
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
    return this.mineOwn().reduce((n, p) => n + Math.max(0, p.totalDue), 0);
  }

  mineOwn(): MyProperty[] {
    return (this.mine() || []).filter((p) => p.relation !== 'OTHER');
  }

  mineOther(): MyProperty[] {
    return (this.mine() || []).filter((p) => p.relation === 'OTHER');
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

  openMine(p: MyProperty, then: Page = 'property'): void {
    this.number = p.upin;
    this.mobile = p.mobileNumber;
    this.find(true, then);
  }

  /** A click on the dashboard opens that property at the page it points to. */
  fromDashboard(e: DashOpen): void {
    const p = (this.mine() || []).find((m) => m.upin === e.upin);
    if (p) this.openMine(p, e.page);
  }

  saveThis(): void {
    this.busy.set(true);
    this.ptx.post('/citizen/my-properties', { number: this.acct()!.property.upin, mobileNumber: this.mobile, relation: this.viewingRelation() }).subscribe({
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
  /** Set while looking up a property that is not (yet) saved, so Save, if pressed, saves it as this kind. */
  viewingRelation = signal<'OWN' | 'OTHER'>('OTHER');

  find(isSaved = false, then: Page = 'property', relation: 'OWN' | 'OTHER' = 'OTHER'): void {
    this.viewingRelation.set(relation);
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
        this.page.set(then);
        this.toTop();
      },
      error: this.fail,
    });
  }

  goHome(): void {
    this.acct.set(null);
    this.tracked.set(null);
    this.page.set('home');
    this.toTop();
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

  /** Opens a made-up electricity or water bill for this address, so it looks the same each time without a server. */
  showUtility(kind: UtilityKind): void {
    this.utilityBill.set(this.mockUtilityBill(kind));
    this.show('utility');
  }

  private mockUtilityBill(kind: UtilityKind): UtilityBill {
    const seed = [...(this.acct()?.property.upin || '')].reduce((n, c) => n + c.charCodeAt(0), 0);
    const elec = kind === 'ELECTRICITY';
    const units = (seed % 180) + (elec ? 60 : 8);
    const rate = elec ? 6.5 : 18;
    const months = ['Aug 2026', 'Sep 2026', 'Oct 2026'];
    return {
      kind, consumerNo: `${elec ? 'TSSPDCL' : 'GWMC-WTR'}-${100000 + (seed * 37) % 900000}`, billNo: `${elec ? 'EB' : 'WB'}-${2026000 + seed}`,
      period: months[2], units, amount: Math.round(units * rate + (elec ? 15 : 60)), dueDate: '2026-11-20', paid: false,
      history: months.slice(0, 2).reverse().map((period, i) => {
        const u = Math.max(1, units - (i + 1) * 7);
        return { period, units: u, amount: Math.round(u * rate + (elec ? 15 : 60)), paidOn: i === 0 ? '2026-10-18' : '2026-09-17' };
      }),
    };
  }

  payUtility(): void {
    const b = this.utilityBill();
    if (!b || b.paid || this.busy()) return;
    this.busy.set(true);
    setTimeout(() => {
      this.utilityBill.set({ ...b, paid: true, history: [{ period: b.period, units: b.units, amount: b.amount, paidOn: todayIso() }, ...b.history] });
      this.busy.set(false);
      this.dialog.showToast(this.L(`Paid - demo receipt ${b.billNo}-R. The real ${b.kind === 'ELECTRICITY' ? 'TSSPDCL' : 'Water Board'} payment is coming soon.`,
        `చెల్లించారు - డెమో రసీదు ${b.billNo}-R. నిజమైన చెల్లింపు త్వరలో వస్తుంది.`), 'success');
    }, 700);
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
