import { ChangeDetectorRef, Component, EventEmitter, Input, OnInit, Output, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { PropertyDetail, PtxAccess } from '../../../../../core/models/ptx.model';
import { PtxService } from '../../../../../core/services/ptx.service';
import { PtxI18nService } from '../../../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../../../core/services/dialog.service';
import { currentPosition, errorText } from '../../../ptx-utils';

/**
 * Corrections that do not change tax (address, location, permission numbers, photos) and the tenant list (PT-07,
 * PT-13). Area, use and ownership change only through an application, so the tax and history stay correct.
 */
@Component({
  selector: 'app-property-correction-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './property-correction-dialog.component.html',
})
export class PropertyCorrectionDialogComponent implements OnInit {
  @Input({ required: true }) property!: PropertyDetail;
  @Input({ required: true }) access!: PtxAccess;
  @Output() closed = new EventEmitter<boolean>();
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  private cdr = inject(ChangeDetectorRef);
  i18n = inject(PtxI18nService);

  form: any = {};
  occupiers: { fullName: string; mobileNumber: string }[] = [];
  occReason = '';
  photos = signal<string[]>([]);
  saving = signal(false);
  private saved = false;

  ngOnInit(): void {
    const p = this.property;
    this.form = { doorNo: p.doorNo || '', address: p.address, pincode: p.pincode || '', localityId: p.localityId || '',
      latitude: p.latitude ?? '', longitude: p.longitude ?? '', oldAssessmentNo: p.oldAssessmentNo || '',
      buildingPermissionNo: p.buildingPermissionNo || '', occupancyCertificateNo: p.occupancyCertificateNo || '', reason: '' };
    this.occupiers = p.occupiers.map((o) => ({ fullName: o.fullName, mobileNumber: '' }));
  }

  localities() {
    return this.access.localities.filter((l) => l.wardId === this.property.wardId);
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
    const file = (ev.target as HTMLInputElement).files?.[0];
    if (!file) return;
    this.ptx.upload(file, file.name).subscribe({
      next: (r) => {
        this.photos.update((list) => [...list, r.ref]);
        this.dialog.showToast('Photo uploaded. Save to attach it to the record.', 'success');
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  save(): void {
    const p = this.property as any;
    const body: any = { reason: this.form.reason };
    ['doorNo', 'address', 'pincode', 'localityId', 'oldAssessmentNo', 'buildingPermissionNo', 'occupancyCertificateNo'].forEach((k) => {
      if ((this.form[k] ?? '') !== (p[k] ?? '')) body[k] = this.form[k] || null;
    });
    if (String(this.form.latitude) !== String(p.latitude ?? '') || String(this.form.longitude) !== String(p.longitude ?? '')) {
      body.latitude = this.form.latitude === '' ? null : Number(this.form.latitude);
      body.longitude = this.form.longitude === '' ? null : Number(this.form.longitude);
    }
    if (this.photos().length) body.addPhotos = this.photos();
    this.saving.set(true);
    this.ptx.patch(`/properties/${encodeURIComponent(p.upin)}`, body).subscribe({
      next: (r) => {
        this.saving.set(false);
        this.saved = true;
        this.dialog.showToast(`${r.message}: ${r.changedFields.join(', ')}`, 'success');
        this.closed.emit(true);
      },
      error: (e) => {
        this.saving.set(false);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  saveOccupiers(): void {
    const list = this.occupiers.filter((o) => o.fullName.trim()).map((o) => ({ fullName: o.fullName.trim(), mobileNumber: o.mobileNumber || null }));
    this.saving.set(true);
    this.ptx.put(`/properties/${encodeURIComponent(this.property.upin)}/occupiers`, { reason: this.occReason, occupiers: list }).subscribe({
      next: () => {
        this.saving.set(false);
        this.saved = true;
        this.dialog.showToast('Tenant / occupier list saved', 'success');
        this.closed.emit(true);
      },
      error: (e) => {
        this.saving.set(false);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  cancel(): void {
    this.closed.emit(this.saved);
  }
}
