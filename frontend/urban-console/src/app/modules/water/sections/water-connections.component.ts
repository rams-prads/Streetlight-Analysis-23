import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { ConnectionDetail, ConnectionSummary, WaterAccess, WaterBill } from '../../../core/models/water.model';
import { WaterService } from '../../../core/services/water.service';
import { WaterI18nService } from '../../../core/services/water-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { WaterDocumentComponent } from '../water-document.component';
import { downloadCsv, dmy, errorText, todayIso } from '../water-utils';

/** Connection register: search (WB-07), record, dues, bills, statement, readings, history (WB-08), meters (WB-10, WB-11). */
@Component({
  selector: 'app-water-connections',
  standalone: true,
  imports: [CommonModule, FormsModule, WaterDocumentComponent],
  templateUrl: './water-connections.component.html',
})
export class WaterConnectionsComponent implements OnInit {
  @Input() access!: WaterAccess;
  private water = inject(WaterService);
  private dialog = inject(DialogService);
  private route = inject(ActivatedRoute);
  i18n = inject(WaterI18nService);
  dmy = dmy;

  filters = { q: '', wardId: '', status: '', category: '', paymentStatus: '', locationPending: '' };
  rows = signal<ConnectionSummary[]>([]);
  loading = signal(false);

  selected = signal<ConnectionDetail | null>(null);
  tab = signal<string>('details');
  bills = signal<WaterBill[]>([]);
  ledger = signal<any[]>([]);
  readings = signal<any[]>([]);
  history = signal<any[]>([]);
  meters = signal<any[]>([]);
  doc = signal<WaterBill | null>(null);

  edit: any = {};
  meterForm: any = {};
  change: any = {};

  ngOnInit(): void {
    const q = this.route.snapshot.queryParamMap.get('consumerNo');
    if (q) {
      this.filters.q = q;
      this.open(q);
    }
    this.search();
  }

  can(p: string): boolean {
    return this.access.permissions.includes(p);
  }

  search(): void {
    this.loading.set(true);
    const f = this.filters;
    this.water
      .searchConnections({ q: f.q, wardId: f.wardId, status: f.status, category: f.category, paymentStatus: f.paymentStatus,
        locationPending: f.locationPending, limit: 200 })
      .subscribe({
        next: (r) => {
          this.rows.set(r);
          this.loading.set(false);
        },
        error: (e) => {
          this.loading.set(false);
          this.dialog.showToast(errorText(e), 'error');
        },
      });
  }

  export(): void {
    downloadCsv(`water-connections-${todayIso()}`, this.rows(), [
      { key: 'consumerNo', label: 'Consumer no' }, { key: 'oldConsumerNo', label: 'Old consumer no' },
      { key: 'consumerName', label: 'Name' }, { key: 'address', label: 'Address' }, { key: 'wardNumber', label: 'Ward' },
      { key: 'categoryCode', label: 'Category' }, { key: 'pipeSizeMm', label: 'Pipe mm' }, { key: 'isMetered', label: 'Metered' },
      { key: 'status', label: 'Status' }, { key: 'totalDue', label: 'Total due' }, { key: 'paymentStatus', label: 'Payment status' },
    ]);
  }

  open(consumerNo: string): void {
    this.water.connection(consumerNo).subscribe({
      next: (c) => {
        this.selected.set(c);
        this.doc.set(null);
        this.edit = { mobileNumber: '', email: c.email || '', doorNo: c.doorNo || '', address: c.address, upin: c.upin || '',
          oldAssessmentNo: c.oldAssessmentNo || '', supplyArea: c.supplyArea || '', latitude: c.latitude ?? '', longitude: c.longitude ?? '',
          reason: '' };
        this.meterForm = { serialNo: '', make: '', sizeMm: c.pipeSizeMm, sealNo: '', initialReading: 0, fixedOn: todayIso(),
          finalReadingOfOld: null, reason: '' };
        this.change = { appType: 'OWNER_CHANGE', applicantName: '', mobileNumber: '', categoryCode: c.categoryCode,
          pipeSizeMm: c.pipeSizeMm, reason: '', documents: '' };
        this.setTab(this.tab());
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  close(): void {
    this.selected.set(null);
  }

  setTab(t: string): void {
    this.tab.set(t);
    const c = this.selected();
    if (!c) return;
    const no = encodeURIComponent(c.consumerNo);
    const fail = (e: unknown) => this.dialog.showToast(errorText(e), 'error');
    if (t === 'bills') this.water.bills(c.consumerNo).subscribe({ next: (b) => this.bills.set(b), error: fail });
    if (t === 'ledger') this.water.get(`/connections/${no}/ledger`).subscribe({ next: (r) => this.ledger.set(r), error: fail });
    if (t === 'readings') this.water.get(`/connections/${no}/readings`).subscribe({ next: (r) => this.readings.set(r), error: fail });
    if (t === 'history') this.water.get(`/connections/${no}/history`).subscribe({ next: (r) => this.history.set(r), error: fail });
    if (t === 'meters') this.water.get(`/connections/${no}/meters`).subscribe({ next: (r) => this.meters.set(r), error: fail });
  }

  showBill(b: WaterBill): void {
    this.water.bill(b.billNo).subscribe({ next: (full) => this.doc.set(full), error: (e) => this.dialog.showToast(errorText(e), 'error') });
  }

  async requestAdjustment(b: WaterBill): Promise<void> {
    const amount = await this.dialog.prompt({ title: `Correct bill ${b.billNo}`, inputLabel: 'Amount (negative reduces the bill)',
      placeholder: '-120.50', required: true });
    if (amount === null) return;
    const reason = await this.dialog.prompt({ title: 'Reason for the correction', inputLabel: 'Reason', required: true });
    if (!reason) return;
    this.water.post(`/bills/${encodeURIComponent(b.billNo)}/adjustments`, { amount: Number(amount), reason }).subscribe({
      next: (r) => this.dialog.showToast(r.message, 'success'),
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  saveEdit(): void {
    const c = this.selected()!;
    const body: any = { reason: this.edit.reason };
    ['email', 'doorNo', 'address', 'upin', 'oldAssessmentNo', 'supplyArea'].forEach((k) => {
      if ((this.edit[k] ?? '') !== ((c as any)[k] ?? '')) body[k] = this.edit[k];
    });
    if (this.edit.mobileNumber) body.mobileNumber = this.edit.mobileNumber;
    if (String(this.edit.latitude) !== String(c.latitude ?? '') || String(this.edit.longitude) !== String(c.longitude ?? '')) {
      body.latitude = this.edit.latitude === '' ? null : Number(this.edit.latitude);
      body.longitude = this.edit.longitude === '' ? null : Number(this.edit.longitude);
    }
    this.water.patch(`/connections/${encodeURIComponent(c.consumerNo)}`, body).subscribe({
      next: (r) => {
        this.dialog.showToast(`${r.message}: ${r.changedFields.join(', ')}`, 'success');
        this.open(c.consumerNo);
        this.search();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  saveMeter(): void {
    const c = this.selected()!;
    const body = { ...this.meterForm };
    if (!c.meter) delete body.finalReadingOfOld;
    this.water.post(`/connections/${encodeURIComponent(c.consumerNo)}/meter`, body).subscribe({
      next: (r) => {
        this.dialog.showToast(r.message, 'success');
        this.open(c.consumerNo);
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  async meterStatus(status: 'ACTIVE' | 'FAULTY'): Promise<void> {
    const c = this.selected()!;
    const reason = await this.dialog.prompt({ title: `Mark meter ${status}`, inputLabel: 'Reason', required: true });
    if (!reason) return;
    this.water.post(`/connections/${encodeURIComponent(c.consumerNo)}/meter/status`, { status, reason }).subscribe({
      next: (r) => {
        this.dialog.showToast(r.message, 'success');
        this.open(c.consumerNo);
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  fileChange(): void {
    const c = this.selected()!;
    const ch = this.change;
    const body: any = { appType: ch.appType, consumerNo: c.consumerNo, channel: 'COUNTER', consent: true, reason: ch.reason,
      documents: (ch.documents || '').split(',').map((d: string) => d.trim()).filter((d: string) => d) };
    if (ch.appType === 'OWNER_CHANGE') Object.assign(body, { applicantName: ch.applicantName, mobileNumber: ch.mobileNumber });
    if (ch.appType === 'CATEGORY_CHANGE') body.categoryCode = ch.categoryCode;
    if (ch.appType === 'PIPE_SIZE_CHANGE') body.pipeSizeMm = Number(ch.pipeSizeMm);
    this.water.post('/applications', body).subscribe({
      next: (a) => this.dialog.showToast(`Application ${a.applicationNo} filed. Track it under Applications.`, 'success'),
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  async uploadDoc(ev: Event): Promise<void> {
    const file = (ev.target as HTMLInputElement).files?.[0];
    if (!file) return;
    this.water.upload(file, file.name).subscribe({
      next: (r) => {
        this.change.documents = [this.change.documents, r.ref].filter((x) => x).join(', ');
        this.dialog.showToast('Document uploaded', 'success');
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }
}
