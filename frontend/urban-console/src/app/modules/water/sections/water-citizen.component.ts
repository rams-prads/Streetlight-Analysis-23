import { ChangeDetectorRef, Component, Input, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { WaterAccess, WaterBill, WaterReceipt } from '../../../core/models/water.model';
import { WaterService } from '../../../core/services/water.service';
import { WaterI18nService } from '../../../core/services/water-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { WaterDocumentComponent } from '../water-document.component';
import { currentPosition, dmy, errorText } from '../water-utils';

/**
 * Citizen self-service, mobile friendly: find connection and pay in three steps (SRS 3.1.1), own meter reading
 * (WB-18), complaints with photo and location (WB-50) and tracking. Login by mobile OTP is a platform service.
 */
@Component({
  selector: 'app-water-citizen',
  standalone: true,
  imports: [CommonModule, FormsModule, WaterDocumentComponent],
  templateUrl: './water-citizen.component.html',
})
export class WaterCitizenComponent {
  @Input() access!: WaterAccess;
  private water = inject(WaterService);
  private dialog = inject(DialogService);
  private cdr = inject(ChangeDetectorRef);
  i18n = inject(WaterI18nService);
  dmy = dmy;
  types = ['LEAK', 'NO_SUPPLY', 'DIRTY_WATER', 'METER', 'BILLING', 'OTHER'];

  find = { consumerNo: '', mobile: '' };
  account = signal<any>(null);
  step = signal(1);
  amount = 0;
  order = signal<any>(null);
  bill = signal<WaterBill | null>(null);
  receipt = signal<WaterReceipt | null>(null);
  extra = signal<'none' | 'reading' | 'complaint'>('none');
  reading: any = { value: null, photoRef: '', latitude: null, longitude: null };
  complaint: any = { complaintType: 'NO_SUPPLY', description: '', photoRef: '', latitude: null, longitude: null };

  lookup(): void {
    this.water.get('/citizen/lookup', { consumerNo: this.find.consumerNo.trim().toUpperCase(), mobile: this.find.mobile }).subscribe({
      next: (a) => {
        this.account.set(a);
        this.amount = a.dues.netPayable;
        this.step.set(2);
        this.receipt.set(null);
        this.bill.set(null);
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  showBill(b: any): void {
    // the consumer's own bill, with the verification QR and the UPI QR
    this.water.get<WaterBill>(`/citizen/bill/${encodeURIComponent(b.billNo)}`, { consumerNo: this.account().consumerNo, mobile: this.find.mobile })
      .subscribe({ next: (full) => this.bill.set(full), error: (e) => this.dialog.showToast(errorText(e), 'error') });
  }

  pay(): void {
    const a = this.account();
    this.water.post('/payments/online/initiate', { consumerNo: a.consumerNo, amount: Number(this.amount), channel: 'PORTAL' }).subscribe({
      next: (o) => {
        this.order.set(o);
        this.step.set(3);
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  confirm(outcome: 'SUCCESS' | 'FAILURE'): void {
    this.water.post('/payments/online/stub-gateway', { orderId: this.order().orderId, outcome }).subscribe({
      next: (r) => {
        if (r.receipt) {
          this.receipt.set(r.receipt);
          this.dialog.showToast(`Paid. Receipt ${r.receipt.receiptNo} sent by SMS.`, 'success');
          this.refresh();
        } else {
          this.dialog.showToast('Payment did not go through. No money was taken; please try again.', 'warning');
          this.step.set(2);
        }
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  refresh(): void {
    this.water.get('/citizen/lookup', { consumerNo: this.account().consumerNo, mobile: this.find.mobile }).subscribe({
      next: (a) => this.account.set(a),
    });
  }

  photo(ev: Event, target: any): void {
    const file = (ev.target as HTMLInputElement).files?.[0];
    if (!file) return;
    this.water.upload(file, file.name).subscribe({ next: (r) => { target.photoRef = r.ref; this.cdr.markForCheck(); }, error: (e) => this.dialog.showToast(errorText(e), 'error') });
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

  submitReading(): void {
    const a = this.account();
    this.water.post('/citizen/self-reading', { consumerNo: a.consumerNo, mobileNumber: this.find.mobile, readingValue: Number(this.reading.value),
      photoRef: this.reading.photoRef, latitude: this.reading.latitude, longitude: this.reading.longitude }).subscribe({
      next: (r) => {
        this.dialog.showToast(r.status === 'PENDING_REVIEW' ? 'Reading received. It is unusual, so an officer will check it before billing.' : 'Reading received. Thank you.', 'success');
        this.extra.set('none');
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  submitComplaint(): void {
    const a = this.account();
    this.water.post('/complaints', { ...this.complaint, source: 'PORTAL', consumerNo: a.consumerNo, complainantMobile: this.find.mobile,
      photoRef: this.complaint.photoRef || null }).subscribe({
      next: (c) => {
        this.dialog.showToast(`Complaint ${c.complaintNo} registered. You will get SMS updates.`, 'success');
        this.extra.set('none');
        this.refresh();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }
}
