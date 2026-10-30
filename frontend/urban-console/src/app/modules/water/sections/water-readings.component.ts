import { ChangeDetectorRef, Component, Input, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouteProgress, WaterAccess, WaterReading } from '../../../core/models/water.model';
import { WaterService } from '../../../core/services/water.service';
import { WaterI18nService } from '../../../core/services/water-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { dmy, errorText, newKey } from '../water-utils';

/** Reading routes and progress (WB-12), flagged-reading review (WB-15), bulk / AMR intake (WB-19), meter register (WB-10). */
@Component({
  selector: 'app-water-readings',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './water-readings.component.html',
})
export class WaterReadingsComponent implements OnInit {
  @Input() access!: WaterAccess;
  private water = inject(WaterService);
  private dialog = inject(DialogService);
  private cdr = inject(ChangeDetectorRef);
  i18n = inject(WaterI18nService);
  dmy = dmy;

  cycle = '';
  routes = signal<RouteProgress[]>([]);
  queue = signal<WaterReading[]>([]);
  meters = signal<any[]>([]);
  meterStatus = '';
  routeForm = { code: '', name: '', wardId: '', readerUsername: '' };
  assign = { routeId: '', consumerNos: '' };
  bulkText = 'consumerNo,readingValue,noReadingReason,readingAt\n';
  bulkSource: 'BULK' | 'AMR' | 'OFFICE' = 'BULK';
  bulkResult = signal<any>(null);
  photoUrl = signal<string>('');

  ngOnInit(): void {
    this.water.get('/cycles/current').subscribe({
      next: (c) => {
        this.cycle = c.cycle;
        this.cdr.markForCheck();
        this.loadRoutes();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
    this.loadQueue();
    this.loadMeters();
  }

  can(p: string): boolean {
    return this.access.permissions.includes(p);
  }

  loadRoutes(): void {
    this.water.routes(this.cycle).subscribe({ next: (r) => this.routes.set(r), error: (e) => this.dialog.showToast(errorText(e), 'error') });
  }

  loadQueue(): void {
    this.water.readings({ status: 'PENDING_REVIEW' }).subscribe({ next: (r) => this.queue.set(r), error: (e) => this.dialog.showToast(errorText(e), 'error') });
  }

  loadMeters(): void {
    this.water.get('/meters', { status: this.meterStatus }).subscribe({ next: (r) => this.meters.set(r), error: () => this.meters.set([]) });
  }

  createRoute(): void {
    this.water.post('/routes', { ...this.routeForm, wardId: this.routeForm.wardId || null, readerUsername: this.routeForm.readerUsername || null }).subscribe({
      next: (r) => {
        this.dialog.showToast(`Route ${r.code} created`, 'success');
        this.routeForm = { code: '', name: '', wardId: '', readerUsername: '' };
        this.loadRoutes();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  assignConnections(): void {
    const nos = this.assign.consumerNos.split(/[\s,]+/).map((s) => s.trim()).filter((s) => s);
    this.water.post(`/routes/${this.assign.routeId}/assign`, { consumerNos: nos }).subscribe({
      next: (r) => {
        this.dialog.showToast(r.message, 'success');
        this.assign.consumerNos = '';
        this.loadRoutes();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  async review(r: WaterReading, decision: 'ACCEPT' | 'REJECT'): Promise<void> {
    const remark = await this.dialog.prompt({
      title: `${decision === 'ACCEPT' ? 'Accept' : 'Reject'} reading of ${r.consumerNo}`,
      message: decision === 'REJECT' ? 'A rejected reading is billed on average consumption.' : 'The reading will be used for the bill.',
      inputLabel: 'Remark', required: true,
    });
    if (!remark) return;
    this.water.post(`/readings/${r.id}/review`, { decision, remark }).subscribe({
      next: (x) => {
        this.dialog.showToast(x.message, 'success');
        this.loadQueue();
        this.loadRoutes();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  viewPhoto(ref?: string | null): void {
    if (!ref) return;
    this.water.getBlob(`/uploads/${ref}`).subscribe({
      next: (b) => this.photoUrl.set(URL.createObjectURL(b)),
      error: () => this.dialog.showToast('Photo not available in storage.', 'warning'),
    });
  }

  loadFile(ev: Event): void {
    const file = (ev.target as HTMLInputElement).files?.[0];
    if (!file) return;
    file.text().then((t) => {
      this.bulkText = t;
      this.cdr.markForCheck();
    });
  }

  submitBulk(): void {
    const lines = this.bulkText.split(/\r?\n/).map((l) => l.trim()).filter((l) => l);
    if (lines.length < 2) {
      this.dialog.showToast('Add at least one data row under the header.', 'warning');
      return;
    }
    const head = lines[0].split(',').map((h) => h.trim());
    const idx = (n: string) => head.indexOf(n);
    if (idx('consumerNo') < 0) {
      this.dialog.showToast('The first line must be a header with a consumerNo column.', 'warning');
      return;
    }
    const readings = lines.slice(1).map((line) => {
      const c = line.split(',').map((x) => x.trim());
      const value = idx('readingValue') >= 0 ? c[idx('readingValue')] : '';
      const reason = idx('noReadingReason') >= 0 ? c[idx('noReadingReason')] : '';
      const at = idx('readingAt') >= 0 ? c[idx('readingAt')] : '';
      return { consumerNo: c[idx('consumerNo')], readingValue: value === '' ? null : Number(value), noReadingReason: reason || null,
        readingAt: at || null, clientRef: `bulk-${newKey()}` };
    });
    this.water.post('/readings/intake', { source: this.bulkSource, readings }).subscribe({
      next: (r) => {
        this.bulkResult.set(r);
        this.dialog.showToast(`${r.stored} stored, ${r.flagged} flagged, ${r.errors} errors`, r.errors ? 'warning' : 'success');
        this.loadQueue();
        this.loadRoutes();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }
}
