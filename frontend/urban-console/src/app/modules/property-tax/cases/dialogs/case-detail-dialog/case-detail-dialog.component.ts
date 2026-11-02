import { ChangeDetectorRef, Component, EventEmitter, Input, OnInit, Output, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { Floor, Notice, PtxAccess, PtxCase } from '../../../../../core/models/ptx.model';
import { PtxService } from '../../../../../core/services/ptx.service';
import { PtxI18nService } from '../../../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../../../core/services/dialog.service';
import { PtxCalcSheetComponent } from '../../../shared/ptx-calc-sheet.component';
import { PtxDocumentComponent } from '../../../shared/ptx-document.component';
import { PtxFloorsEditorComponent } from '../../../shared/ptx-floors-editor.component';
import { compressPhoto, currentPosition, dataUrlToBlob, dmy, errorText, saveBlob } from '../../../ptx-utils';

const ADMIN_ROLES = ['super_admin', 'system_admin'];

/**
 * One application: where it is, what happens next, the tax working, the documents and timeline, and the action the
 * signed-in officer can take at the current step (PT-18, PT-19, PT-20).
 */
@Component({
  selector: 'app-case-detail-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, PtxCalcSheetComponent, PtxDocumentComponent, PtxFloorsEditorComponent],
  templateUrl: './case-detail-dialog.component.html',
})
export class CaseDetailDialogComponent implements OnInit {
  @Input({ required: true }) access!: PtxAccess;
  @Input({ required: true }) applicationNo!: string;
  @Output() closed = new EventEmitter<boolean>();
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  private cdr = inject(ChangeDetectorRef);
  private router = inject(Router);
  i18n = inject(PtxI18nService);
  dmy = dmy;

  c = signal<PtxCase | null>(null);
  notice = signal<Notice | null>(null);
  busy = signal(false);
  photos = signal<string[]>([]);
  remark = '';
  objection = '';
  upheld: 'yes' | 'no' | '' = '';
  measured: { siteAreaSqyd: number | null; floors: Floor[]; lat: number | null; lng: number | null; roadClass: string; approvedSetbackFt: number | null; measuredSetbackFt: number | null } =
    { siteAreaSqyd: null, floors: [], lat: null, lng: null, roadClass: '', approvedSetbackFt: null, measuredSetbackFt: null };
  private changed = false;

  current = computed(() => this.c()?.steps.find((s) => s.status === 'CURRENT') ?? null);
  canAct = computed(() => {
    const step = this.current();
    if (!step) return false;
    const roles = new Set(this.access.roles);
    if (ADMIN_ROLES.some((r) => roles.has(r))) return true;
    if (step.code === 'APPROVAL' && roles.has('commissioner')) return true;
    return step.roles.some((r) => roles.has(r));
  });
  windowOpen = computed(() => {
    const c = this.c();
    if (!c?.objectionUntil) return false;
    return c.objectionUntil >= new Date().toISOString().slice(0, 10);
  });

  ngOnInit(): void {
    this.load();
  }

  can(p: string): boolean {
    return this.access.permissions.includes(p);
  }

  load(): void {
    this.ptx.caseDetail(this.applicationNo).subscribe({
      next: (c) => {
        this.c.set(c);
        this.remark = '';
        const d = c.details || {};
        const prop = d.property || {};
        this.measured = { siteAreaSqyd: prop.siteAreaSqyd ?? null, floors: (d.floors || []).map((f: Floor) => ({ ...f })), lat: null, lng: null,
          roadClass: prop.roadClass || '', approvedSetbackFt: prop.approvedSetbackFt ?? null, measuredSetbackFt: prop.measuredSetbackFt ?? null };
      },
      error: (e) => {
        this.dialog.showToast(errorText(e), 'error');
        this.closed.emit(false);
      },
    });
  }

  ownersText(list: any[] | undefined): string {
    return (list || []).map((o) => o.fullName + (o.sharePercent ? ` (${o.sharePercent}%)` : '')).join(', ') || '-';
  }

  usage(code: string): string {
    return this.i18n.name(this.access.codes.USAGE?.find((c) => c.code === code), code);
  }

  floorText(floors: Floor[] | undefined): string {
    return (floors || []).map((f) => {
      const where = f.floorNo === 0 ? 'Ground' : 'Floor ' + f.floorNo;
      if (f.portion === 'ROOFTOP') return `${where}: rooftop ${f.rooftopType?.replace('_', ' ').toLowerCase()} ${f.builtupSqft} sq ft`;
      const tag = f.declaredAccommodation ? ' guest accommodation' : f.portion === 'PART' ? ' part' : f.portion === 'COMMON' ? ' common-area share' : '';
      return `${where}${tag}: ${this.usage(f.usageCode)} ${f.builtupSqft} sq ft${f.occupancy === 'TENANT' ? ' (tenant)' : ''}`;
    }).join(' · ');
  }

  openDoc(ref: string): void {
    this.ptx.getBlob(`/uploads/${encodeURIComponent(ref)}`).subscribe({
      next: (b) => {
        const url = URL.createObjectURL(b);
        const w = window.open(url, '_blank');
        if (!w) saveBlob(b, ref);
        setTimeout(() => URL.revokeObjectURL(url), 60_000);
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  showNotice(): void {
    const no = this.c()?.noticeNo;
    if (!no) return;
    this.ptx.get<Notice>(`/notices/${encodeURIComponent(no)}`).subscribe({
      next: (n) => this.notice.set(n),
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  async inspectionPhoto(ev: Event): Promise<void> {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    try {
      const data = await compressPhoto(file);
      this.ptx.upload(dataUrlToBlob(data), 'inspection.jpg').subscribe({
        next: (r) => this.photos.update((p) => [...p, r.ref]),
        error: (e) => this.dialog.showToast(errorText(e), 'error'),
      });
    } catch (e: any) {
      this.dialog.showToast(e.message, 'error');
    }
    input.value = '';
  }

  async gps(): Promise<void> {
    try {
      const p = await currentPosition();
      this.measured.lat = p.lat;
      this.measured.lng = p.lng;
      this.cdr.markForCheck();
    } catch (e: any) {
      this.dialog.showToast(e.message, 'warning');
    }
  }

  private act(body: any, done: string): void {
    this.busy.set(true);
    this.ptx.post(`/cases/${encodeURIComponent(this.applicationNo)}/actions`, body).subscribe({
      next: (r) => {
        this.busy.set(false);
        this.changed = true;
        this.dialog.showToast(r.upin && r.noticeNo ? `${done}. Assessment notice ${r.noticeNo} issued for ${r.upin}.` : done, 'success');
        this.load();
      },
      error: (e) => {
        this.busy.set(false);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  completeStep(): void {
    const step = this.current();
    const body: any = { action: 'COMPLETE_STEP', remark: this.remark };
    if (step?.code === 'FIELD_INSPECTION') {
      const c = this.c()!;
      const area = this.measured.siteAreaSqyd as any;
      const m: any = this.measured;
      if (c.details?.property) {
        body.property = {};
        if (area !== null && area !== '') body.property.siteAreaSqyd = Number(area);
        if (m.roadClass) body.property.roadClass = m.roadClass;
        if (m.approvedSetbackFt !== null && m.approvedSetbackFt !== '') body.property.approvedSetbackFt = Number(m.approvedSetbackFt);
        if (m.measuredSetbackFt !== null && m.measuredSetbackFt !== '') body.property.measuredSetbackFt = Number(m.measuredSetbackFt);
      }
      if (c.details?.floors) body.floors = this.measured.floors.map((f) => ({ ...f, floorNo: Number(f.floorNo), builtupSqft: Number(f.builtupSqft) }));
      body.photoRefs = this.photos();
      body.latitude = this.measured.lat;
      body.longitude = this.measured.lng;
    }
    this.act(body, `${step?.label} done`);
  }

  /** Revision petition or appeal filed at the counter on the owner's behalf (PT-24). */
  petitionText = '';
  petForm: any = { outcome: 'REJECT', remark: '', orderReference: '', siteAreaSqyd: null, approvedSetbackFt: null, measuredSetbackFt: null, floors: [] };

  startDecision(): void {
    this.petForm = { outcome: 'REJECT', remark: '', orderReference: '', siteAreaSqyd: this.measured.siteAreaSqyd, approvedSetbackFt: this.measured.approvedSetbackFt,
      measuredSetbackFt: this.measured.measuredSetbackFt, floors: (this.c()?.details?.floors || []).map((f: Floor) => ({ ...f })) };
  }

  filePetition(level: string): void {
    this.busy.set(true);
    this.ptx.post(`/cases/${encodeURIComponent(this.applicationNo)}/petitions`, { level, grounds: this.petitionText }).subscribe({
      next: (r) => {
        this.busy.set(false);
        this.petitionText = '';
        this.changed = true;
        this.dialog.showToast(`${r.message}: ${r.petitionNo}.`, 'success');
        this.load();
      },
      error: (e) => {
        this.busy.set(false);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  decidePetition(petitionNo: string): void {
    const f = this.petForm;
    const body: any = { outcome: f.outcome, remark: f.remark, orderReference: f.orderReference || null };
    if (f.outcome !== 'REJECT') {
      const property: any = {};
      if (f.siteAreaSqyd !== null && f.siteAreaSqyd !== '') property.siteAreaSqyd = Number(f.siteAreaSqyd);
      if (f.approvedSetbackFt !== null && f.approvedSetbackFt !== '') property.approvedSetbackFt = Number(f.approvedSetbackFt);
      if (f.measuredSetbackFt !== null && f.measuredSetbackFt !== '') property.measuredSetbackFt = Number(f.measuredSetbackFt);
      body.property = property;
      if (f.floors.length) body.floors = f.floors.map((x: Floor) => ({ ...x, floorNo: Number(x.floorNo), builtupSqft: Number(x.builtupSqft) }));
    }
    this.busy.set(true);
    this.ptx.post(`/petitions/${encodeURIComponent(petitionNo)}/decide`, body).subscribe({
      next: (r) => {
        this.busy.set(false);
        this.changed = true;
        this.dialog.showToast(r.assessmentNo ? `${r.message}. New assessment ${r.assessmentNo} applied and bills revised.` : r.message, 'success');
        this.load();
      },
      error: (e) => {
        this.busy.set(false);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  async reject(): Promise<void> {
    const ok = await this.dialog.confirm({ title: 'Reject this application?', message: `The applicant is told the reason by SMS: "${this.remark}". Any fee charged is withdrawn.`,
      confirmText: 'Reject', variant: 'destructive' });
    if (ok) this.act({ action: 'REJECT', remark: this.remark }, 'Application rejected');
  }

  fileObjection(): void {
    this.busy.set(true);
    this.ptx.post(`/cases/${encodeURIComponent(this.applicationNo)}/objection`, { text: this.objection }).subscribe({
      next: () => {
        this.busy.set(false);
        this.objection = '';
        this.changed = true;
        this.dialog.showToast('Objection recorded. The Revenue Officer decides it before the tax is finalised.', 'success');
        this.load();
      },
      error: (e) => {
        this.busy.set(false);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  decideObjection(): void {
    const body: any = { action: 'DECIDE_OBJECTION', remark: this.remark, objectionUpheld: this.upheld === 'yes' };
    if (this.upheld === 'yes' && this.c()?.details?.floors) {
      body.floors = this.measured.floors.map((f) => ({ ...f, floorNo: Number(f.floorNo), builtupSqft: Number(f.builtupSqft) }));
      if (this.c()?.details?.property) body.property = { siteAreaSqyd: Number(this.measured.siteAreaSqyd) };
    }
    this.act(body, 'Objection decision recorded');
  }

  async finalise(): Promise<void> {
    const ok = await this.dialog.confirm({ title: 'Finalise this case?', message: 'The property record and tax are updated, and bills are raised or revised from the effective date.',
      confirmText: 'Finalise' });
    if (ok) this.act({ action: 'FINALISE', remark: this.remark || 'Finalised after the objection period' }, 'Case completed');
  }

  openProperty(upin: string): void {
    this.closed.emit(this.changed);
    this.router.navigate(['/modules/ptx/properties'], { queryParams: { upin } });
  }

  close(): void {
    this.closed.emit(this.changed);
  }
}
