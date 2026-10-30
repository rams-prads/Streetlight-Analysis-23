import { ChangeDetectorRef, Component, Input, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { WaterAccess, WaterApplication } from '../../../core/models/water.model';
import { WaterService } from '../../../core/services/water.service';
import { WaterI18nService } from '../../../core/services/water-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { currentPosition, dmy, errorText, newKey, todayIso } from '../water-utils';

/** New connection and change-request workflow with SLA per step (WB-04, WB-05, WB-06). */
@Component({
  selector: 'app-water-applications',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './water-applications.component.html',
})
export class WaterApplicationsComponent implements OnInit {
  @Input() access!: WaterAccess;
  private water = inject(WaterService);
  private dialog = inject(DialogService);
  private cdr = inject(ChangeDetectorRef);
  i18n = inject(WaterI18nService);
  dmy = dmy;

  filters = { status: 'IN_PROGRESS', appType: '', q: '' };
  rows = signal<WaterApplication[]>([]);
  selected = signal<WaterApplication | null>(null);
  showNew = signal(false);
  warnings = signal<any[]>([]);
  busy = signal(false);

  form: any = {};
  act: any = {};

  ngOnInit(): void {
    this.resetForm();
    this.load();
  }

  can(p: string): boolean {
    return this.access.permissions.includes(p);
  }

  resetForm(): void {
    this.form = { appType: 'NEW_CONNECTION', channel: 'COUNTER', applicantName: '', mobileNumber: '', email: '', aadhaarNumber: '',
      consent: false, wardId: this.access?.wards[0]?.wardId || '', address: '', doorNo: '', locality: '', pincode: '', latitude: '',
      longitude: '', oldAssessmentNo: '', upin: '', categoryCode: 'DOMESTIC', pipeSizeMm: 15, isMetered: true, supplyArea: '', documents: '' };
    this.warnings.set([]);
  }

  load(): void {
    this.water.applications(this.filters).subscribe({
      next: (r) => this.rows.set(r),
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  open(no: string): void {
    this.water.get<WaterApplication>(`/applications/${encodeURIComponent(no)}`).subscribe({
      next: (a) => {
        this.selected.set(a);
        this.act = { remark: '', roadCuttingMetres: 0, photoRef: '', latitude: null, longitude: null, finalReading: null,
          meter: { serialNo: '', make: '', sizeMm: a.details?.pipeSizeMm || 15, sealNo: '', initialReading: 0, fixedOn: todayIso() } };
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  currentStep(a: WaterApplication) {
    return a.steps.find((s) => s.status === 'CURRENT');
  }

  canAct(a: WaterApplication): boolean {
    const step = this.currentStep(a);
    if (!step) return false;
    return this.access.roles.some((r) => step.roles.includes(r) || r === 'super_admin' || r === 'system_admin');
  }

  async locate(target: any): Promise<void> {
    try {
      const p = await currentPosition();
      target.latitude = p.lat;
      target.longitude = p.lng;
      this.cdr.markForCheck();
    } catch (e: any) {
      this.dialog.showToast(e.message, 'warning');
    }
  }

  checkDuplicates(): void {
    const f = this.form;
    this.water.post('/connections/duplicate-check', { address: f.address, doorNo: f.doorNo,
      latitude: f.latitude === '' ? null : Number(f.latitude), longitude: f.longitude === '' ? null : Number(f.longitude) }).subscribe({
      next: (w) => {
        this.warnings.set(w);
        if (!w.length) this.dialog.showToast('No existing connection at this address or nearby.', 'success');
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  upload(ev: Event, target: any, field: string): void {
    const file = (ev.target as HTMLInputElement).files?.[0];
    if (!file) return;
    this.water.upload(file, file.name).subscribe({
      next: (r) => {
        target[field] = field === 'documents' ? [target[field], r.ref].filter((x: string) => x).join(', ') : r.ref;
        this.cdr.markForCheck();
        this.dialog.showToast('Uploaded', 'success');
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  submitNew(): void {
    const f = this.form;
    const body = { ...f, pipeSizeMm: Number(f.pipeSizeMm), latitude: f.latitude === '' ? null : Number(f.latitude),
      longitude: f.longitude === '' ? null : Number(f.longitude), aadhaarNumber: f.aadhaarNumber || null,
      documents: (f.documents || '').split(',').map((d: string) => d.trim()).filter((d: string) => d) };
    this.busy.set(true);
    this.water.post<WaterApplication>('/applications', body).subscribe({
      next: (a) => {
        this.busy.set(false);
        this.showNew.set(false);
        this.dialog.showToast(`Application ${a.applicationNo} filed${a.warnings.length ? ' - check the duplicate warnings' : ''}.`, 'success');
        this.resetForm();
        this.load();
        this.open(a.applicationNo);
      },
      error: (e) => {
        this.busy.set(false);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  doAction(action: 'COMPLETE_STEP' | 'REJECT'): void {
    const a = this.selected()!;
    const step = this.currentStep(a)!;
    const data: any = {};
    if (step.code === 'SITE_INSPECTION') data.roadCuttingMetres = Number(this.act.roadCuttingMetres || 0);
    if (step.code === 'WORK_ORDER' && a.details?.isMetered) data.meter = { ...this.act.meter, sizeMm: Number(this.act.meter.sizeMm),
      initialReading: Number(this.act.meter.initialReading) };
    if (step.code === 'FIELD_EXECUTION' && this.act.finalReading !== null && this.act.finalReading !== '') data.finalReading = Number(this.act.finalReading);
    const body = { action, remark: this.act.remark, data, photoRef: this.act.photoRef || null,
      latitude: this.act.latitude, longitude: this.act.longitude };
    this.busy.set(true);
    this.water.post(`/applications/${encodeURIComponent(a.applicationNo)}/actions`, body).subscribe({
      next: (r) => {
        this.busy.set(false);
        this.dialog.showToast(r.consumerNo && r.status === 'COMPLETED' ? `Completed. Consumer number ${r.consumerNo}` : r.message, 'success');
        this.load();
        this.open(a.applicationNo);
      },
      error: (e) => {
        this.busy.set(false);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  async collect(a: WaterApplication): Promise<void> {
    const ok = await this.dialog.confirm({ title: 'Collect estimate', message: `Record cash payment of ₹${a.amountOutstanding} for ${a.applicationNo}?`,
      confirmText: 'Record payment' });
    if (!ok) return;
    this.water.post('/payments', { applicationNo: a.applicationNo, amount: a.amountOutstanding, paymentMode: 'CASH', channel: 'COUNTER',
      idempotencyKey: newKey() }).subscribe({
      next: (r) => {
        this.dialog.showToast(`Receipt ${r.receiptNo} issued`, 'success');
        this.open(a.applicationNo);
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }
}
