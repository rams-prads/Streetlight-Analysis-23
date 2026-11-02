import { ChangeDetectorRef, Component, EventEmitter, Input, Output, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Notice } from '../../../../../core/models/ptx.model';
import { PtxService } from '../../../../../core/services/ptx.service';
import { PtxI18nService } from '../../../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../../../core/services/dialog.service';
import { compressPhoto, currentPosition, dataUrlToBlob, errorText, newKey } from '../../../ptx-utils';

/** Records that a notice was served (with GPS and a photo) or why it could not be (PT-43). */
@Component({
  selector: 'app-notice-service-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="ptx-modal-backdrop" (click)="closed.emit(false)"></div>
    <section class="ptx-modal" role="dialog" aria-modal="true" aria-label="Record notice service">
      <div class="ptx-modal-head">
        <h2>Record service · {{ notice.noticeNo }}</h2>
        <button class="ptx-btn" (click)="closed.emit(false)">{{ i18n.t('cancel') }}</button>
      </div>
      <div class="ptx-modal-body">
        <p>{{ notice.upin }} · {{ notice.address }}</p>
        <div class="ptx-form">
          <label class="inline"><input type="radio" name="served" [value]="true" [(ngModel)]="served" /> Served (handed over or pasted)</label>
          <label class="inline"><input type="radio" name="served" [value]="false" [(ngModel)]="served" /> Could not serve</label>
        </div>
        @if (!served) { <label>Why not? * <input [(ngModel)]="reason" placeholder="e.g. House locked, owner not traceable" /></label> }
        <div class="ptx-row">
          <button class="ptx-btn sm" (click)="gps()">Capture GPS</button>
          @if (lat !== null) { <span class="ptx-muted">{{ lat }}, {{ lng }}</span> }
          <label>Photo <input type="file" accept="image/*" capture="environment" (change)="photo($event)" /></label>
          @if (photoRef()) { <span class="ptx-muted">Photo attached</span> }
        </div>
      </div>
      <div class="ptx-modal-foot">
        <button class="ptx-btn" (click)="closed.emit(false)">{{ i18n.t('cancel') }}</button>
        <button class="ptx-btn primary" (click)="save()" [disabled]="busy() || (!served && reason.trim().length < 3)">{{ i18n.t('save') }}</button>
      </div>
    </section>
  `,
})
export class NoticeServiceDialogComponent {
  @Input({ required: true }) notice!: Notice;
  @Output() closed = new EventEmitter<boolean>();
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  private cdr = inject(ChangeDetectorRef);
  i18n = inject(PtxI18nService);
  served = true;
  reason = '';
  lat: number | null = null;
  lng: number | null = null;
  photoRef = signal<string>('');
  busy = signal(false);

  async gps(): Promise<void> {
    try {
      const p = await currentPosition();
      this.lat = p.lat;
      this.lng = p.lng;
      this.cdr.markForCheck();
    } catch (e: any) {
      this.dialog.showToast(e.message, 'warning');
    }
  }

  async photo(ev: Event): Promise<void> {
    const file = (ev.target as HTMLInputElement).files?.[0];
    if (!file) return;
    try {
      const data = await compressPhoto(file);
      this.ptx.upload(dataUrlToBlob(data), 'service.jpg').subscribe({
        next: (r) => this.photoRef.set(r.ref),
        error: (e) => this.dialog.showToast(errorText(e), 'error'),
      });
    } catch (e: any) {
      this.dialog.showToast(e.message, 'error');
    }
  }

  save(): void {
    this.busy.set(true);
    this.ptx.post(`/notices/${encodeURIComponent(this.notice.noticeNo)}/service`, {
      served: this.served, servedAt: new Date().toISOString(), latitude: this.lat, longitude: this.lng, photoRef: this.photoRef() || null,
      reason: this.served ? null : this.reason, clientRef: newKey(),
    }).subscribe({
      next: () => {
        this.busy.set(false);
        this.dialog.showToast('Service recorded.', 'success');
        this.closed.emit(true);
      },
      error: (e) => {
        this.busy.set(false);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }
}
