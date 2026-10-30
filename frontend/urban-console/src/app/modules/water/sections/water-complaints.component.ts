import { ChangeDetectorRef, Component, Input, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { WaterAccess, WaterComplaint } from '../../../core/models/water.model';
import { WaterService } from '../../../core/services/water.service';
import { WaterI18nService } from '../../../core/services/water-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { currentPosition, dmy, errorText } from '../water-utils';

/** Complaints with SLA, auto-assignment and closing proof (WB-50..WB-52) and illegal connection cases (WB-53). */
@Component({
  selector: 'app-water-complaints',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './water-complaints.component.html',
})
export class WaterComplaintsComponent implements OnInit {
  @Input() access!: WaterAccess;
  private water = inject(WaterService);
  private dialog = inject(DialogService);
  private cdr = inject(ChangeDetectorRef);
  i18n = inject(WaterI18nService);
  dmy = dmy;
  types = ['LEAK', 'NO_SUPPLY', 'DIRTY_WATER', 'METER', 'BILLING', 'OTHER'];

  view = signal<'complaints' | 'illegal'>('complaints');
  filters = { status: 'OPEN,IN_PROGRESS', type: '', overdue: false, mine: false, q: '' };
  rows = signal<WaterComplaint[]>([]);
  selected = signal<WaterComplaint | null>(null);
  form: any = {};
  act: any = { remark: '', photoRef: '', assignTo: '' };

  cases = signal<any[]>([]);
  caseSel = signal<any>(null);
  caseForm: any = {};
  inspection: any = {};
  decision: any = {};

  ngOnInit(): void {
    this.resetForm();
    this.load();
  }

  can(p: string): boolean {
    return this.access.permissions.includes(p);
  }

  resetForm(): void {
    this.form = { complaintType: 'LEAK', source: 'FIELD', consumerNo: '', wardId: this.access?.wards[0]?.wardId || '', complainantName: '',
      complainantMobile: '', description: '', address: '', latitude: null, longitude: null, photoRef: '' };
    this.caseForm = { source: 'STAFF', wardId: this.access?.wards[0]?.wardId || '', address: '', description: '', latitude: null, longitude: null, photoRef: '' };
  }

  load(): void {
    this.water.complaints(this.filters).subscribe({ next: (r) => this.rows.set(r), error: (e) => this.dialog.showToast(errorText(e), 'error') });
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

  upload(ev: Event, target: any, field = 'photoRef'): void {
    const file = (ev.target as HTMLInputElement).files?.[0];
    if (!file) return;
    this.water.upload(file, file.name).subscribe({
      next: (r) => {
        target[field] = r.ref;
        this.cdr.markForCheck();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  raise(): void {
    const f = this.form;
    const body = { ...f, consumerNo: f.consumerNo || null, complainantMobile: f.complainantMobile || null, photoRef: f.photoRef || null };
    this.water.post<WaterComplaint>('/complaints', body).subscribe({
      next: (c) => {
        this.dialog.showToast(`Complaint ${c.complaintNo} registered and assigned to ${c.assignedTo}`, 'success');
        this.resetForm();
        this.load();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  open(c: WaterComplaint): void {
    this.water.get<WaterComplaint>(`/complaints/${encodeURIComponent(c.complaintNo)}`).subscribe({
      next: (d) => {
        this.selected.set(d);
        this.act = { remark: '', photoRef: '', assignTo: '' };
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  action(kind: 'START' | 'CLOSE' | 'REASSIGN'): void {
    const c = this.selected()!;
    this.water.post(`/complaints/${encodeURIComponent(c.complaintNo)}/actions`, { action: kind, remark: this.act.remark,
      photoRef: this.act.photoRef || null, assignTo: this.act.assignTo || null }).subscribe({
      next: (r) => {
        this.dialog.showToast(r.message, 'success');
        this.open(c);
        this.load();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  loadCases(): void {
    this.water.get('/illegal-cases').subscribe({ next: (r) => this.cases.set(r), error: (e) => this.dialog.showToast(errorText(e), 'error') });
  }

  reportCase(): void {
    this.water.post('/illegal-cases', this.caseForm).subscribe({
      next: (c) => {
        this.dialog.showToast(`Case ${c.caseNo} opened`, 'success');
        this.resetForm();
        this.loadCases();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  openCase(c: any): void {
    this.water.get(`/illegal-cases/${encodeURIComponent(c.caseNo)}`).subscribe({
      next: (d) => {
        this.caseSel.set(d);
        this.inspection = { findings: '', confirmedIllegal: true, photoRef: '' };
        this.decision = { decision: 'REGULARISE', remark: '', consumerName: '', mobileNumber: '', categoryCode: 'DOMESTIC', pipeSizeMm: 15,
          isMetered: false, doorNo: '', photoRef: '', latitude: null, longitude: null };
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  inspect(): void {
    const c = this.caseSel();
    this.water.post(`/illegal-cases/${encodeURIComponent(c.caseNo)}/inspection`, { ...this.inspection, photoRef: this.inspection.photoRef || null }).subscribe({
      next: () => {
        this.openCase(c);
        this.loadCases();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  decide(): void {
    const c = this.caseSel();
    const d = this.decision;
    this.water.post(`/illegal-cases/${encodeURIComponent(c.caseNo)}/decision`, { ...d, pipeSizeMm: Number(d.pipeSizeMm),
      mobileNumber: d.mobileNumber || null, photoRef: d.photoRef || null }).subscribe({
      next: (r) => {
        this.dialog.showToast(r.consumerNo ? `${r.message}: consumer number ${r.consumerNo}` : r.message, 'success');
        this.openCase(c);
        this.loadCases();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }
}
