import { ChangeDetectorRef, Component, Input, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { WaterAccess, WaterOrder } from '../../../core/models/water.model';
import { WaterService } from '../../../core/services/water.service';
import { WaterI18nService } from '../../../core/services/water-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { currentPosition, downloadCsv, dmy, errorText, todayIso } from '../water-utils';

/** Arrears ageing and defaulters (WB-41), penalty (WB-40), reminders (WB-42), disconnection / reconnection (WB-43..45), waivers (WB-46). */
@Component({
  selector: 'app-water-arrears',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './water-arrears.component.html',
})
export class WaterArrearsComponent implements OnInit {
  @Input() access!: WaterAccess;
  private water = inject(WaterService);
  private dialog = inject(DialogService);
  private cdr = inject(ChangeDetectorRef);
  i18n = inject(WaterI18nService);
  dmy = dmy;

  view = signal<'ageing' | 'orders'>('ageing');
  ageing = signal<any>(null);
  wardId = '';
  minDue = 0;
  orderType = 'DISCONNECTION';
  orderStatus = 'PENDING';
  orders = signal<WaterOrder[]>([]);
  proof: any = { orderNo: '', photoRef: '', latitude: null, longitude: null, remark: '' };
  reconNo = '';
  lastRun = signal<any>(null);

  ngOnInit(): void {
    if (!this.can('arrears.manage') && !this.can('reports.view')) this.view.set('orders');
    if (this.view() === 'ageing') this.loadAgeing();
    this.loadOrders();
  }

  can(p: string): boolean {
    return this.access.permissions.includes(p);
  }

  loadAgeing(): void {
    this.water.get('/arrears/ageing', { wardId: this.wardId, minDue: this.minDue }).subscribe({
      next: (a) => this.ageing.set(a),
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  exportDefaulters(): void {
    downloadCsv(`water-defaulters-${todayIso()}`, this.ageing()?.defaulters || [], [
      { key: 'consumerNo', label: 'Consumer no' }, { key: 'consumerName', label: 'Name' }, { key: 'wardNumber', label: 'Ward' },
      { key: 'status', label: 'Status' }, { key: 'penalty', label: 'Penalty' }, { key: 'fees', label: 'Fees' }, { key: 'arrears', label: 'Arrears' },
      { key: 'current', label: 'Current' }, { key: 'totalDue', label: 'Total due' }, { key: 'oldestAgeDays', label: 'Oldest (days)' },
    ]);
  }

  async runJob(path: string, label: string): Promise<void> {
    const ok = await this.dialog.confirm({ title: label, message: `Run "${label}" now? It is safe to run more than once a day: nothing is charged or sent twice.`,
      confirmText: 'Run' });
    if (!ok) return;
    this.water.post(path, {}).subscribe({
      next: (r) => {
        this.lastRun.set({ label, result: r });
        this.dialog.showToast(`${label} done`, 'success');
        this.loadAgeing();
        this.loadOrders();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  json(v: any): string {
    return JSON.stringify(v, null, 1);
  }

  loadOrders(): void {
    this.water.orders({ type: this.orderType, status: this.orderStatus }).subscribe({
      next: (o) => this.orders.set(o),
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  startProof(o: WaterOrder): void {
    this.proof = { orderNo: o.orderNo, photoRef: '', latitude: null, longitude: null, remark: '' };
  }

  async locate(): Promise<void> {
    try {
      const p = await currentPosition();
      this.proof.latitude = p.lat;
      this.proof.longitude = p.lng;
      this.cdr.markForCheck();
    } catch (e: any) {
      this.dialog.showToast(e.message, 'warning');
    }
  }

  photo(ev: Event): void {
    const file = (ev.target as HTMLInputElement).files?.[0];
    if (!file) return;
    this.water.upload(file, file.name).subscribe({
      next: (r) => {
        this.proof.photoRef = r.ref;
        this.cdr.markForCheck();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  execute(): void {
    const p = this.proof;
    this.water.post(`/orders/${encodeURIComponent(p.orderNo)}/execute`, { photoRef: p.photoRef, latitude: p.latitude, longitude: p.longitude,
      remark: p.remark || null, executedAt: new Date().toISOString() }).subscribe({
      next: (r) => {
        this.dialog.showToast(`${r.message} - connection is now ${r.connectionStatus}`, 'success');
        this.proof.orderNo = '';
        this.loadOrders();
      },
      error: (e) => {
        this.dialog.showToast(errorText(e), 'error');
        this.loadOrders();
      },
    });
  }

  requestReconnection(): void {
    this.water.post(`/connections/${encodeURIComponent(this.reconNo.trim().toUpperCase())}/reconnection`, {}).subscribe({
      next: (r) => {
        this.dialog.showToast(r.status === 'PENDING' ? `Work order ${r.orderNo} released` : `Order ${r.orderNo}: collect ₹${r.amountToPay} (dues + reconnection fee)`, 'success');
        this.reconNo = '';
        this.orderType = 'RECONNECTION';
        this.orderStatus = '';
        this.loadOrders();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  async waiver(d: any): Promise<void> {
    const kind = await this.dialog.prompt({ title: `Waiver / write-off for ${d.consumerNo}`, inputLabel: 'Type WAIVER or WRITE_OFF', initialValue: 'WAIVER', required: true });
    if (!kind) return;
    const bucket = await this.dialog.prompt({ title: 'Which dues?', inputLabel: 'PENALTY, FEE, ARREAR or CURRENT', initialValue: 'PENALTY', required: true });
    if (!bucket) return;
    const amount = await this.dialog.prompt({ title: 'Amount', inputLabel: 'Amount (₹)', required: true });
    if (!amount) return;
    const reason = await this.dialog.prompt({ title: 'Reason', inputLabel: 'Reason (recorded with the approval)', required: true });
    if (!reason) return;
    this.water.post(`/connections/${encodeURIComponent(d.consumerNo)}/waivers`, { kind: kind.trim().toUpperCase(), bucket: bucket.trim().toUpperCase(),
      amount: Number(amount), reason }).subscribe({
      next: (r) => this.dialog.showToast(r.message, 'success'),
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  async refund(): Promise<void> {
    const no = await this.dialog.prompt({ title: 'Refund', inputLabel: 'Consumer number', required: true });
    if (!no) return;
    const type = await this.dialog.prompt({ title: 'Refund type', inputLabel: 'EXCESS_PAYMENT or DEPOSIT', initialValue: 'EXCESS_PAYMENT', required: true });
    if (!type) return;
    const mode = type.trim().toUpperCase() === 'DEPOSIT'
      ? await this.dialog.prompt({ title: 'Deposit', inputLabel: 'PAY (refund) or ADJUST (against dues)', initialValue: 'PAY', required: true })
      : 'PAY';
    if (!mode) return;
    const amount = await this.dialog.prompt({ title: 'Amount', inputLabel: 'Amount (₹)', required: true });
    if (!amount) return;
    const reason = await this.dialog.prompt({ title: 'Reason', inputLabel: 'Reason', required: true });
    if (!reason) return;
    this.water.post(`/connections/${encodeURIComponent(no.trim().toUpperCase())}/refunds`, { refundType: type.trim().toUpperCase(),
      mode: mode.trim().toUpperCase(), amount: Number(amount), reason }).subscribe({
      next: (r) => this.dialog.showToast(r.message, 'success'),
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }
}
