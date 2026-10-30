import { ChangeDetectorRef, Component, Input, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { firstValueFrom } from 'rxjs';
import { OfflineReading, RouteProgress, WaterAccess } from '../../../core/models/water.model';
import { WaterService } from '../../../core/services/water.service';
import { WaterI18nService } from '../../../core/services/water-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { FieldQueue, compressPhoto, currentPosition, dataUrlToBlob, dmy, errorText, newKey } from '../water-utils';

const SHEET_KEY = 'urban_water_route_sheet';

/**
 * Field app for meter readers and field staff (WB-13, WB-14, WB-52). Works offline: the route sheet is kept on the
 * device, readings and photos are queued in IndexedDB with GPS and time, and are deleted only after the server has
 * confirmed them (WB-NF-33). Sync is idempotent, so a reading sent twice is stored once.
 */
@Component({
  selector: 'app-water-field',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './water-field.component.html',
})
export class WaterFieldComponent implements OnInit, OnDestroy {
  @Input() access!: WaterAccess;
  private water = inject(WaterService);
  private dialog = inject(DialogService);
  private cdr = inject(ChangeDetectorRef);
  i18n = inject(WaterI18nService);
  dmy = dmy;

  online = signal<boolean>(navigator.onLine);
  routes = signal<RouteProgress[]>([]);
  sheet = signal<any>(null);
  queue = signal<OfflineReading[]>([]);
  syncing = signal(false);
  current = signal<any>(null);
  entry: any = {};
  leak: any = { wardId: '', description: '', photoRef: '', latitude: null, longitude: null };

  private onOnline = () => {
    this.online.set(true);
    this.sync();
  };
  private onOffline = () => this.online.set(false);

  ngOnInit(): void {
    window.addEventListener('online', this.onOnline);
    window.addEventListener('offline', this.onOffline);
    try {
      const saved = localStorage.getItem(SHEET_KEY);
      if (saved) this.sheet.set(JSON.parse(saved));
    } catch {
      /* no saved sheet */
    }
    this.refreshQueue();
    if (this.online()) {
      this.water.routes().subscribe({ next: (r) => this.routes.set(r), error: () => this.routes.set([]) });
    }
  }

  ngOnDestroy(): void {
    window.removeEventListener('online', this.onOnline);
    window.removeEventListener('offline', this.onOffline);
  }

  can(p: string): boolean {
    return this.access.permissions.includes(p);
  }

  async refreshQueue(): Promise<void> {
    try {
      this.queue.set(await FieldQueue.all());
    } catch {
      this.dialog.showToast('This browser cannot store readings offline. Keep the device online.', 'warning');
    }
  }

  download(routeId: string, quiet = false): void {
    this.water.get(`/routes/${routeId}/sheet`).subscribe({
      next: (s) => {
        this.sheet.set(s);
        try {
          localStorage.setItem(SHEET_KEY, JSON.stringify(s));
        } catch {
          /* storage full: the sheet stays in memory for this visit */
        }
        if (!quiet) this.dialog.showToast(`Route ${s.route.code}: ${s.connections.length} connection(s) ready for offline reading`, 'success');
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  queued(consumerNo: string): boolean {
    return this.queue().some((q) => q.consumerNo === consumerNo);
  }

  start(c: any): void {
    this.current.set(c);
    this.entry = { mode: 'READ', value: null, reason: this.sheet()?.noReadingReasons?.[0] || '', photo: null as string | null };
  }

  async takePhoto(ev: Event): Promise<void> {
    const file = (ev.target as HTMLInputElement).files?.[0];
    if (!file) return;
    try {
      this.entry.photo = await compressPhoto(file);
      this.cdr.markForCheck();
    } catch (e: any) {
      this.dialog.showToast(e.message, 'error');
    }
  }

  async save(): Promise<void> {
    const c = this.current();
    if (this.entry.mode === 'READ') {
      if (this.entry.value === null || this.entry.value === '' || Number(this.entry.value) < 0) {
        this.dialog.showToast('Enter the reading shown on the meter.', 'warning');
        return;
      }
      if (!this.entry.photo) {
        this.dialog.showToast('Take a photo of the meter dial before saving.', 'warning');
        return;
      }
      if (c.lastReading !== null && Number(this.entry.value) < c.lastReading) {
        const ok = await this.dialog.confirm({ title: 'Reading is lower than last time', message: `Last reading was ${c.lastReading}. Save ${this.entry.value} anyway? It will be checked by an officer.`, confirmText: 'Save' });
        if (!ok) return;
      }
    }
    let pos: { lat: number; lng: number } | null = null;
    try {
      pos = await currentPosition();
    } catch (e: any) {
      if (this.entry.mode === 'READ') {
        this.dialog.showToast(e.message, 'error');
        return;
      }
    }
    const item: OfflineReading = {
      clientRef: `field-${newKey()}`, consumerNo: c.consumerNo, consumerName: c.consumerName,
      readingValue: this.entry.mode === 'READ' ? Number(this.entry.value) : null,
      noReadingReason: this.entry.mode === 'READ' ? null : this.entry.reason,
      readingAt: new Date().toISOString(), latitude: pos?.lat ?? null, longitude: pos?.lng ?? null,
      photoDataUrl: this.entry.photo, photoRef: null,
    };
    try {
      await FieldQueue.put(item);
    } catch {
      this.dialog.showToast('Could not save on this device. Check free storage.', 'error');
      return;
    }
    this.current.set(null);
    await this.refreshQueue();
    this.dialog.showToast(this.online() ? 'Saved. Syncing…' : 'Saved on the device. It will sync when online.', 'success');
    if (this.online()) this.sync();
  }

  async sync(): Promise<void> {
    if (this.syncing() || !navigator.onLine) return;
    this.syncing.set(true);
    try {
      const items = await FieldQueue.all();
      const ready: OfflineReading[] = [];
      for (const item of items) {
        if (item.photoDataUrl && !item.photoRef) {
          try {
            const up = await firstValueFrom(this.water.upload(dataUrlToBlob(item.photoDataUrl), `${item.clientRef}.jpg`));
            item.photoRef = up.ref;
            await FieldQueue.put(item);
          } catch (e) {
            item.lastError = errorText(e);
            await FieldQueue.put(item);
            continue;
          }
        }
        ready.push(item);
      }
      if (ready.length) {
        const res = await firstValueFrom(this.water.post('/readings/intake', {
          source: 'FIELD',
          readings: ready.map((r) => ({ consumerNo: r.consumerNo, readingValue: r.readingValue, noReadingReason: r.noReadingReason,
            readingAt: r.readingAt, photoRef: r.photoRef, latitude: r.latitude, longitude: r.longitude, clientRef: r.clientRef })),
        }));
        // the intake answers row by row, in the order the readings were sent
        for (let i = 0; i < res.results.length; i++) {
          const r = res.results[i];
          const item = ready[i];
          if (!item) continue;
          if (r.result === 'STORED' || r.result === 'DUPLICATE_IGNORED') {
            await FieldQueue.remove(item.clientRef);
          } else {
            item.lastError = r.error;
            await FieldQueue.put(item);
          }
        }
        this.dialog.showToast(`Synced: ${res.stored} stored, ${res.flagged} flagged for review, ${res.errors} need attention`, res.errors ? 'warning' : 'success');
        // show the synced readings against the route sheet
        if (this.sheet()) this.download(this.sheet().route.id, true);
      }
    } catch (e) {
      this.dialog.showToast(`Sync stopped: ${errorText(e)} Your readings are still safe on this device.`, 'warning');
    } finally {
      this.syncing.set(false);
      await this.refreshQueue();
    }
  }

  async discard(item: OfflineReading): Promise<void> {
    const ok = await this.dialog.confirm({ title: 'Remove this reading from the device?', message: `${item.consumerNo}: ${item.lastError || ''}`,
      confirmText: 'Remove', variant: 'destructive' });
    if (!ok) return;
    await FieldQueue.remove(item.clientRef);
    this.refreshQueue();
  }

  leakPhoto(ev: Event): void {
    const file = (ev.target as HTMLInputElement).files?.[0];
    if (!file) return;
    this.water.upload(file, file.name).subscribe({ next: (r) => { this.leak.photoRef = r.ref; this.cdr.markForCheck(); }, error: (e) => this.dialog.showToast(errorText(e), 'error') });
  }

  async logLeak(): Promise<void> {
    try {
      const p = await currentPosition();
      this.leak.latitude = p.lat;
      this.leak.longitude = p.lng;
    } catch (e: any) {
      this.dialog.showToast(e.message, 'error');
      return;
    }
    const wardId = this.leak.wardId || this.access.wards[0]?.wardId;
    this.water.post('/complaints', { complaintType: 'LEAK', source: 'FIELD', wardId, description: this.leak.description,
      latitude: this.leak.latitude, longitude: this.leak.longitude, photoRef: this.leak.photoRef || null }).subscribe({
      next: (c) => {
        this.dialog.showToast(`Leak ${c.complaintNo} logged and assigned to ${c.assignedTo}`, 'success');
        this.leak = { wardId: this.leak.wardId, description: '', photoRef: '', latitude: null, longitude: null };
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }
}
