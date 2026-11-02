import { ChangeDetectorRef, Component, EventEmitter, Input, OnInit, Output, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Observable } from 'rxjs';
import { CalcSheet, CaseType, Floor, PropertyDetail, PtxAccess, PtxCase } from '../../../../../core/models/ptx.model';
import { PtxService } from '../../../../../core/services/ptx.service';
import { PtxI18nService } from '../../../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../../../core/services/dialog.service';
import { PtxFloorsEditorComponent } from '../../../shared/ptx-floors-editor.component';
import { PtxCalcSheetComponent } from '../../../shared/ptx-calc-sheet.component';
import { CASE_TYPES, CaseTypeInfo } from '../../case-types';
import { currentPosition, errorText, todayIso } from '../../../ptx-utils';

interface PartyForm {
  fullName: string;
  mobileNumber: string;
  aadhaarNumber: string;
  sharePercent: number | null;
}

interface UnitForm {
  unitNo: string;
  floors: Floor[];
  owners: PartyForm[];
}

interface PartForm {
  doorNo: string;
  address: string;
  siteAreaSqyd: number | null;
  floors: Floor[];
  owners: PartyForm[];
}

/**
 * Guided application form in three steps - choose, fill in, check and submit - used at the counter, by Meeseva and
 * by owners on the portal (PT-12..PT-21). The tax is shown before submitting, with the working (PT-11).
 */
@Component({
  selector: 'app-case-form-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, PtxFloorsEditorComponent, PtxCalcSheetComponent],
  templateUrl: './case-form-dialog.component.html',
})
export class CaseFormDialogComponent implements OnInit {
  @Input({ required: true }) access!: PtxAccess;
  @Input() presetUpin = '';
  @Input() presetType: CaseType | '' = '';
  /** Portal mode: the owner's registered mobile, used to confirm they may apply for this property. */
  @Input() citizenMobile = '';
  @Output() closed = new EventEmitter<string | null>();
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  private cdr = inject(ChangeDetectorRef);
  i18n = inject(PtxI18nService);

  step = signal<1 | 2 | 3>(1);
  type = signal<CaseType | ''>('');
  property = signal<PropertyDetail | null>(null);
  preview = signal<CalcSheet | null>(null);
  partPreviews = signal<CalcSheet[]>([]);
  documents = signal<{ ref: string; name: string }[]>([]);
  busy = signal(false);
  citizen = computed(() => !!this.citizenMobile);

  upin = '';
  upinsText = '';
  form: any = {};
  floors: Floor[] = [];
  owners: PartyForm[] = [];
  transfer = { reason: '', deedNo: '', date: '' };
  parts: PartForm[] = [];
  units: UnitForm[] = [];
  complexName = '';
  commonAreaSqft: number | null = null;
  reason = '';
  effectiveFrom = '';
  applicantName = '';
  mobileNumber = '';
  consent = false;
  readonly today = todayIso();

  ngOnInit(): void {
    this.upin = this.presetUpin;
    this.mobileNumber = this.citizenMobile;
    this.resetDetails();
    if (this.presetType) this.choose(CASE_TYPES.find((t) => t.code === this.presetType)!);
  }

  types(): CaseTypeInfo[] {
    return CASE_TYPES.filter((t) => (this.citizen() ? t.citizen : true)).filter((t) => (this.presetUpin ? t.needsUpin : true));
  }

  info(): CaseTypeInfo | undefined {
    return CASE_TYPES.find((t) => t.code === this.type());
  }

  needsUpin(): boolean {
    return !!this.info()?.needsUpin;
  }

  isNewProperty(): boolean {
    return this.type() === 'NEW_ASSESSMENT' || this.type() === 'SELF_ASSESSMENT';
  }

  hasFloors(): boolean {
    const t = this.type();
    if (this.isNewProperty()) return this.form.propertyType === 'BUILT';
    return t === 'REASSESSMENT' || t === 'USE_CHANGE' || t === 'AMALGAMATION' || t === 'BACK_ASSESSMENT';
  }

  private blankFloor(): Floor {
    return { floorNo: 0, usageCode: this.access.codes.USAGE?.find((c) => c.code === 'RESIDENTIAL')?.code || this.access.codes.USAGE?.[0]?.code || '',
      constructionCode: (this.access.codes.CONSTRUCTION?.find((c) => c.code === 'RCC')?.code || this.access.codes.CONSTRUCTION?.[0]?.code) || '', builtupSqft: 0, occupancy: 'OWNER' };
  }

  private blankParty(): PartyForm {
    return { fullName: '', mobileNumber: '', aadhaarNumber: '', sharePercent: null };
  }

  resetDetails(): void {
    this.form = { propertyType: 'BUILT', wardId: this.access.wards.length === 1 ? this.access.wards[0].wardId : '', localityId: '', doorNo: '',
      address: '', pincode: '', latitude: null, longitude: null, siteAreaSqyd: null, constructionYear: null, buildingPermissionNo: '',
      occupancyCertificateNo: '', exemptionCode: '', roadClass: '', approvedSetbackFt: null, measuredSetbackFt: null };
    this.floors = [this.blankFloor()];
    this.units = [];
    this.owners = [this.blankParty()];
    this.parts = [];
    this.preview.set(null);
    this.partPreviews.set([]);
  }

  choose(t: CaseTypeInfo): void {
    this.type.set(t.code);
    this.resetDetails();
    if (t.code === 'APARTMENT') {
      this.units = [0, 1].map((i) => ({ unitNo: String(101 + i), floors: [{ ...this.blankFloor(), floorNo: 1 }], owners: [this.blankParty()] }));
    }
    if (t.code === 'SUBDIVISION') {
      this.parts = [0, 1].map(() => ({ doorNo: '', address: '', siteAreaSqyd: null, floors: [this.blankFloor()], owners: [] }));
    }
    this.step.set(2);
    if (t.needsUpin && this.upin) this.loadProperty();
  }

  /** Brings in the property's current details so the applicant only changes what is different. */
  loadProperty(): void {
    const upin = this.upin.trim().toUpperCase();
    if (!upin) return;
    this.property.set(null);
    if (this.type() === 'MUTATION' && this.citizen()) return; // the buyer's mobile is not on the record yet
    const req: Observable<PropertyDetail> = this.citizen()
      ? new Observable<PropertyDetail>((obs) => {
          this.ptx.citizenAccount(upin, this.citizenMobile).subscribe({ next: (a) => { obs.next(a.property); obs.complete(); }, error: (e) => obs.error(e) });
        })
      : this.ptx.property(upin);
    req.subscribe({
      next: (p) => {
        this.upin = p.upin;
        this.property.set(p);
        this.floors = p.floors.map((f) => ({ ...f }));
        this.form.siteAreaSqyd = p.siteAreaSqyd;
        this.form.constructionYear = p.constructionYear;
        this.form.exemptionCode = p.exemptionCode || '';
        this.form.roadClass = p.roadClass || '';
        this.form.approvedSetbackFt = p.approvedSetbackFt ?? null;
        this.form.measuredSetbackFt = p.measuredSetbackFt ?? null;
        if (p.status !== 'ACTIVE') this.dialog.showToast(`${p.upin} is closed (${p.retiredReason}). Use the new property number.`, 'warning');
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  localities() {
    return this.access.localities.filter((l) => l.wardId === this.form.wardId);
  }

  transferReason() {
    return this.access.codes.TRANSFER_REASON?.find((c) => c.code === this.transfer.reason);
  }

  exemption() {
    return this.access.codes.EXEMPTION?.find((c) => c.code === this.form.exemptionCode);
  }

  fee(): number {
    const t = this.type();
    if (t === 'MUTATION') return this.access.fees?.mutationByReason?.[this.transfer.reason] || 0;
    if (t === 'SUBDIVISION') return this.access.fees?.subdivision || 0;
    if (t === 'AMALGAMATION') return this.access.fees?.amalgamation || 0;
    return 0;
  }

  async useMyLocation(): Promise<void> {
    try {
      const pos = await currentPosition();
      this.form.latitude = pos.lat;
      this.form.longitude = pos.lng;
      this.cdr.markForCheck();
    } catch (e: any) {
      this.dialog.showToast(e.message, 'warning');
    }
  }

  upload(ev: Event): void {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    this.busy.set(true);
    this.ptx.upload(file, file.name).subscribe({
      next: (r) => {
        this.busy.set(false);
        this.documents.update((d) => [...d, { ref: r.ref, name: file.name }]);
        input.value = '';
      },
      error: (e) => {
        this.busy.set(false);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  removeDoc(i: number): void {
    this.documents.update((d) => d.filter((_, k) => k !== i));
  }

  private parties(list: PartyForm[]) {
    return list
      .filter((o) => o.fullName.trim())
      .map((o) => ({ fullName: o.fullName.trim(), mobileNumber: o.mobileNumber || null, aadhaarNumber: o.aadhaarNumber || null,
        sharePercent: o.sharePercent === null || (o.sharePercent as any) === '' ? null : Number(o.sharePercent) }));
  }

  private cleanFloors(list: Floor[]): Floor[] {
    return list.map((f) => ({ ...f, floorNo: Number(f.floorNo), builtupSqft: Number(f.builtupSqft) }));
  }

  private newPropertyDetails(): any {
    const f = this.form;
    return { propertyType: f.propertyType, wardId: f.wardId || null, localityId: f.localityId || null, doorNo: f.doorNo || null,
      address: f.address || null, pincode: f.pincode || null, latitude: f.latitude === null || f.latitude === '' ? null : Number(f.latitude),
      longitude: f.longitude === null || f.longitude === '' ? null : Number(f.longitude),
      siteAreaSqyd: f.siteAreaSqyd === null || f.siteAreaSqyd === '' ? null : Number(f.siteAreaSqyd),
      constructionYear: f.constructionYear ? Number(f.constructionYear) : null, buildingPermissionNo: f.buildingPermissionNo || null,
      occupancyCertificateNo: f.occupancyCertificateNo || null, ...this.valuationFields() };
  }

  /** Road class and setback measurements, sent only when filled in (setback is measured by staff, never asked from owners). */
  private valuationFields(): any {
    const f = this.form;
    const out: any = {};
    if (f.roadClass) out.roadClass = f.roadClass;
    if (f.approvedSetbackFt !== null && f.approvedSetbackFt !== '') out.approvedSetbackFt = Number(f.approvedSetbackFt);
    if (f.measuredSetbackFt !== null && f.measuredSetbackFt !== '') out.measuredSetbackFt = Number(f.measuredSetbackFt);
    return out;
  }

  /** Property details as they would be after this application (for the tax preview). */
  private resultingDetails(): any | null {
    const t = this.type();
    if (this.isNewProperty()) return this.newPropertyDetails();
    const p = this.property();
    if (!p) return null;
    const base = { propertyType: p.propertyType, wardId: p.wardId, localityId: p.localityId, doorNo: p.doorNo, address: p.address,
      pincode: p.pincode, latitude: p.latitude, longitude: p.longitude, siteAreaSqyd: p.siteAreaSqyd, constructionYear: p.constructionYear,
      exemptionCode: p.exemptionCode };
    if (t === 'REASSESSMENT' || t === 'BACK_ASSESSMENT') return { ...base, siteAreaSqyd: Number(this.form.siteAreaSqyd), constructionYear: this.form.constructionYear ? Number(this.form.constructionYear) : null,
      roadClass: this.form.roadClass || null, ...this.valuationFields() };
    if (t === 'EXEMPTION') return { ...base, exemptionCode: this.form.exemptionCode || null };
    if (t === 'AMALGAMATION') return { ...base, doorNo: this.form.doorNo || base.doorNo, address: this.form.address || base.address,
      siteAreaSqyd: Number(this.form.siteAreaSqyd), footprintId: null };
    return base;
  }

  body(): any {
    const t = this.type() as CaseType;
    const staffChannel = this.access.roles.includes('csc_operator') ? 'CSC' : 'COUNTER';
    const b: any = { appType: t, channel: this.citizen() ? 'PORTAL' : staffChannel, consent: this.consent, reason: this.reason || null,
      effectiveFrom: this.effectiveFrom || null, documents: this.documents().map((d) => d.ref), applicantName: this.applicantName || null,
      mobileNumber: this.mobileNumber || null };
    if (this.needsUpin()) b.upin = this.upin.trim().toUpperCase();
    if (this.isNewProperty()) {
      b.property = this.newPropertyDetails();
      b.floors = this.form.propertyType === 'BUILT' ? this.cleanFloors(this.floors) : [];
      b.owners = this.parties(this.owners);
    }
    if (t === 'REASSESSMENT' || t === 'BACK_ASSESSMENT') {
      b.property = { siteAreaSqyd: Number(this.form.siteAreaSqyd), constructionYear: this.form.constructionYear ? Number(this.form.constructionYear) : null,
        ...this.valuationFields() };
      b.floors = this.cleanFloors(this.floors);
    }
    if (t === 'USE_CHANGE') b.floors = this.cleanFloors(this.floors);
    if (t === 'EXEMPTION') b.property = { exemptionCode: this.form.exemptionCode || null, exemptionDocument: this.documents()[0]?.ref || null };
    if (t === 'MUTATION') {
      Object.assign(b, { transferReason: this.transfer.reason, transferDeedNo: this.transfer.deedNo || null, transferDate: this.transfer.date || null,
        owners: this.parties(this.owners) });
    }
    if (t === 'APARTMENT') {
      b.property = { ...this.newPropertyDetails(), propertyType: 'BUILT' };
      b.complexName = this.complexName;
      b.commonAreaSqft = this.commonAreaSqft === null ? 0 : Number(this.commonAreaSqft);
      b.units = this.units.map((u) => ({ unitNo: u.unitNo, floors: this.cleanFloors(u.floors), owners: this.parties(u.owners) }));
    }
    if (t === 'SUBDIVISION') {
      b.parts = this.parts.map((p) => ({ property: { doorNo: p.doorNo || null, address: p.address || null, siteAreaSqyd: Number(p.siteAreaSqyd) },
        floors: this.cleanFloors(p.floors), owners: this.parties(p.owners) }));
    }
    if (t === 'AMALGAMATION') {
      b.upins = this.upinsText.split(/[\s,;]+/).map((u) => u.trim().toUpperCase()).filter((u) => u);
      b.property = { doorNo: this.form.doorNo || null, address: this.form.address || null, siteAreaSqyd: Number(this.form.siteAreaSqyd) };
      b.floors = this.cleanFloors(this.floors);
      b.owners = this.parties(this.owners);
    }
    return b;
  }

  /** Step 2 -> 3: work out the tax so the applicant sees it before submitting. */
  review(): void {
    const t = this.type();
    this.preview.set(null);
    this.partPreviews.set([]);
    if (t === 'MUTATION' || t === 'DEMOLITION') {
      this.step.set(3);
      return;
    }
    if (t === 'APARTMENT') {
      this.previewApartment();
      return;
    }
    if (t === 'SUBDIVISION') {
      const p = this.property();
      if (!p) {
        this.dialog.showToast('Enter the property number and press "Bring in details" first.', 'warning');
        return;
      }
      const sheets: CalcSheet[] = [];
      let left = this.parts.length;
      this.busy.set(true);
      this.parts.forEach((part, i) => {
        const details = { propertyType: 'BUILT', wardId: p.wardId, localityId: p.localityId, siteAreaSqyd: Number(part.siteAreaSqyd),
          constructionYear: p.constructionYear };
        this.ptx.post('/calculate', { property: details, floors: this.cleanFloors(part.floors), effectiveFrom: this.effectiveFrom || null }).subscribe({
          next: (r) => {
            sheets[i] = { ...r.calculation, annualTax: r.annualTax };
            if (--left === 0) {
              this.partPreviews.set(sheets);
              this.busy.set(false);
              this.step.set(3);
            }
          },
          error: (e) => {
            this.busy.set(false);
            this.dialog.showToast(`Part ${i + 1}: ${errorText(e)}`, 'error');
          },
        });
      });
      return;
    }
    const details = this.resultingDetails();
    if (!details) {
      this.dialog.showToast('Enter the property number and press "Bring in details" first.', 'warning');
      return;
    }
    const floors = this.hasFloors() || (!this.isNewProperty() && details.propertyType === 'BUILT') ? this.cleanFloors(this.floors) : [];
    this.busy.set(true);
    this.ptx.post('/calculate', { property: details, floors, effectiveFrom: this.effectiveFrom || null }).subscribe({
      next: (r) => {
        this.busy.set(false);
        this.preview.set({ ...r.calculation, annualTax: r.annualTax });
        this.step.set(3);
      },
      error: (e) => {
        this.busy.set(false);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  /** Each flat's tax with its share of the common areas, worked out the same way the office will (PT-07). */
  private previewApartment(): void {
    const common = Number(this.commonAreaSqft || 0);
    const own = this.units.map((u) => u.floors.reduce((sum, f) => sum + Number(f.builtupSqft || 0), 0));
    const total = own.reduce((a, b) => a + b, 0);
    if (!total || this.units.some((u, i) => !u.unitNo.trim() || own[i] <= 0)) {
      this.dialog.showToast('Give every unit a number and its area.', 'warning');
      return;
    }
    const site = Number(this.form.siteAreaSqyd || 0);
    const sheets: CalcSheet[] = [];
    let left = this.units.length;
    this.busy.set(true);
    this.units.forEach((u, i) => {
      const share = own[i] / total;
      const floors = this.cleanFloors(u.floors);
      if (common > 0) {
        const main = [...floors].sort((a, b) => b.builtupSqft - a.builtupSqft)[0];
        floors.push({ ...main, builtupSqft: +(common * share).toFixed(2), portion: 'COMMON', declaredAccommodation: false });
      }
      const details = { ...this.newPropertyDetails(), propertyType: 'BUILT', siteAreaSqyd: +(site * share).toFixed(2) };
      this.ptx.post('/calculate', { property: details, floors, effectiveFrom: this.effectiveFrom || null }).subscribe({
        next: (r) => {
          sheets[i] = { ...r.calculation, annualTax: r.annualTax };
          if (--left === 0) {
            this.partPreviews.set(sheets);
            this.busy.set(false);
            this.step.set(3);
          }
        },
        error: (e) => {
          this.busy.set(false);
          this.dialog.showToast(`Unit ${u.unitNo}: ${errorText(e)}`, 'error');
        },
      });
    });
  }

  totalOfUnits(): number {
    return this.partPreviews().reduce((sum, s) => sum + (s.annualTax || 0), 0);
  }

  /** Why the dialog asks for the date, in the words that fit the application. */
  dateLabel(): string {
    const t = this.type();
    if (t === 'USE_CHANGE') return 'Use changed from *';
    if (t === 'DEMOLITION') return 'Date the building was demolished *';
    if (t === 'BACK_ASSESSMENT') return 'The correct details apply from * (the year the property was first under-assessed)';
    return 'Change took effect from (optional)';
  }

  submit(): void {
    if (!this.consent) {
      this.dialog.showToast('Please tick the consent box to continue.', 'warning');
      return;
    }
    this.busy.set(true);
    this.ptx.post<PtxCase>('/cases', this.body()).subscribe({
      next: (c) => {
        this.busy.set(false);
        const fee = c.details?.fee ? ` A fee of ₹${c.details.fee} has been added to the property's dues.` : '';
        this.dialog.showToast(`Application ${c.applicationNo} received. Keep this number to track it.${fee}`, 'success');
        const warnings = c.details?.warnings || [];
        if (warnings.length) {
          this.dialog.alert({ title: 'Possible duplicate', variant: 'warning',
            message: `Properties with the same door number already exist: ${warnings.map((w: any) => w.upin).join(', ')}. The inspector will check this.` });
        }
        this.closed.emit(c.applicationNo);
      },
      error: (e) => {
        this.busy.set(false);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  close(): void {
    this.closed.emit(null);
  }
}
