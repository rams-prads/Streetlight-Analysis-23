import { Component, EventEmitter, Input, OnInit, Output, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router } from '@angular/router';
import {
  Assessment, Certificate, DemandNotice, HistoryEntry, LedgerEntry, PropertyDemand, PropertyDetail, PtxAccess,
} from '../../../../../core/models/ptx.model';
import { PtxService } from '../../../../../core/services/ptx.service';
import { PtxI18nService } from '../../../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../../../core/services/dialog.service';
import { PtxCalcSheetComponent } from '../../../shared/ptx-calc-sheet.component';
import { PtxDocumentComponent } from '../../../shared/ptx-document.component';
import { PropertyCorrectionDialogComponent } from '../property-correction-dialog/property-correction-dialog.component';
import { dmy, errorText, fieldLabel, txnLabel } from '../../../ptx-utils';

/** One property: details, dues and bills, statement, how the tax is worked out, change history (PT-04, PT-07, PT-11). */
@Component({
  selector: 'app-property-detail-dialog',
  standalone: true,
  imports: [CommonModule, PtxCalcSheetComponent, PtxDocumentComponent, PropertyCorrectionDialogComponent],
  templateUrl: './property-detail-dialog.component.html',
})
export class PropertyDetailDialogComponent implements OnInit {
  @Input({ required: true }) access!: PtxAccess;
  @Input({ required: true }) upin!: string;
  @Output() closed = new EventEmitter<boolean>();
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  private router = inject(Router);
  i18n = inject(PtxI18nService);
  dmy = dmy;
  txnLabel = txnLabel;
  fieldLabel = fieldLabel;

  p = signal<PropertyDetail | null>(null);
  tab = signal<'details' | 'bills' | 'statement' | 'tax' | 'history'>('details');
  demands = signal<PropertyDemand[]>([]);
  ledger = signal<LedgerEntry[]>([]);
  assessments = signal<Assessment[]>([]);
  history = signal<HistoryEntry[]>([]);
  doc = signal<DemandNotice | null>(null);
  cert = signal<Certificate | null>(null);
  correcting = signal(false);
  private changed = false;

  ngOnInit(): void {
    this.load();
  }

  can(p: string): boolean {
    return this.access.permissions.includes(p);
  }

  load(): void {
    this.ptx.property(this.upin).subscribe({
      next: (p) => {
        this.p.set(p);
        this.setTab(this.tab());
      },
      error: (e) => {
        this.dialog.showToast(errorText(e), 'error');
        this.closed.emit(false);
      },
    });
  }

  setTab(t: 'details' | 'bills' | 'statement' | 'tax' | 'history'): void {
    this.tab.set(t);
    this.doc.set(null);
    const no = encodeURIComponent(this.upin);
    const fail = (e: unknown) => this.dialog.showToast(errorText(e), 'error');
    if (t === 'bills') this.ptx.get<PropertyDemand[]>(`/properties/${no}/demands`).subscribe({ next: (r) => this.demands.set(r), error: fail });
    if (t === 'statement') this.ptx.get<LedgerEntry[]>(`/properties/${no}/ledger`).subscribe({ next: (r) => this.ledger.set([...r].reverse()), error: fail });
    if (t === 'tax') this.ptx.get<Assessment[]>(`/properties/${no}/assessments`).subscribe({ next: (r) => this.assessments.set(r), error: fail });
    if (t === 'history') this.ptx.get<HistoryEntry[]>(`/properties/${no}/history`).subscribe({ next: (r) => this.history.set(r), error: fail });
  }

  async correct(demandNo: string): Promise<void> {
    const amount = await this.dialog.prompt({ title: `Correct bill ${demandNo}`, message: 'A plus raises the bill and a minus lowers it. A separate entry is made and must be approved.',
      inputLabel: 'Amount in ₹ (minus lowers the bill)', placeholder: '-120.50', required: true });
    if (amount === null) return;
    const reason = await this.dialog.prompt({ title: 'Why is the bill being corrected?', inputLabel: 'Reason', required: true });
    if (!reason) return;
    this.ptx.post(`/demands/${encodeURIComponent(demandNo)}/corrections`, { amount: Number(amount), reason }).subscribe({
      next: (r) => this.dialog.showToast(`Sent for approval: the bill would go from ₹${r.billNow} to ₹${r.billAfter}.`, 'success'),
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  showDemand(no: string): void {
    this.ptx.get<DemandNotice>(`/demands/${encodeURIComponent(no)}`).subscribe({
      next: (d) => this.doc.set(d),
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  usage(code: string): string {
    return this.i18n.name(this.access.codes.USAGE?.find((c) => c.code === code), code);
  }

  construction(code: string): string {
    return this.i18n.name(this.access.codes.CONSTRUCTION?.find((c) => c.code === code), code);
  }

  roadName(code?: string | null): string {
    return code ? this.i18n.name(this.access.codes.ROAD_CLASS?.find((c) => c.code === code), code) : '-';
  }

  portionText(f: { portion?: string; rooftopType?: string | null; declaredAccommodation?: boolean }): string {
    if (f.portion === 'ROOFTOP') return `Rooftop ${(f.rooftopType || '').replace('_', ' ').toLowerCase()}`;
    if (f.declaredAccommodation) return 'Guest accommodation';
    return ({ PART: 'Part of floor', COMMON: 'Share of common areas' } as any)[f.portion || ''] || '';
  }

  floorName(n: number): string {
    return n === 0 ? 'Ground' : n < 0 ? `Cellar ${-n}` : `Floor ${n}`;
  }

  goTo(section: 'cases' | 'collection'): void {
    this.closed.emit(this.changed);
    this.router.navigate(['/modules/ptx', section], { queryParams: { upin: this.upin } });
  }

  async noDues(): Promise<void> {
    const ok = await this.dialog.confirm({ title: 'Issue a no-dues certificate?', message: `Nothing is due on ${this.upin}. The certificate is valid for the period set by GWMC.`,
      confirmText: 'Issue certificate' });
    if (!ok) return;
    this.ptx.post<Certificate>('/citizen/no-dues-certificate', { upin: this.upin }).subscribe({
      next: (c) => this.cert.set(c),
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  /** Tax-paid certificate, assessment extract or NOC at the counter (PT-28). A NOC asks what it is for. */
  async other(certType: 'TAX_PAID' | 'ASSESSMENT_EXTRACT' | 'NOC'): Promise<void> {
    let purpose: string | null = null;
    if (certType === 'NOC') {
      purpose = await this.dialog.prompt({ title: 'No Objection Certificate', message: 'Issued when nothing is due and no application is pending on the property.',
        inputLabel: 'What is the NOC for?', placeholder: 'e.g. Sale of the property, bank loan', required: true });
      if (!purpose) return;
    }
    this.ptx.post<Certificate>('/citizen/certificates', { upin: this.upin, certType, purpose }).subscribe({
      next: (c) => this.cert.set(c),
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  onCorrected(saved: boolean): void {
    this.correcting.set(false);
    if (saved) {
      this.changed = true;
      this.load();
    }
  }

  close(): void {
    this.closed.emit(this.changed);
  }
}
