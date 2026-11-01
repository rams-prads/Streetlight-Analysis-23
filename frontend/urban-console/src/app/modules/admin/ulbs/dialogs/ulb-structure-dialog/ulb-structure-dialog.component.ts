import { Component, Input, Output, EventEmitter, OnChanges, SimpleChanges, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';
import { IconComponent } from '../../../../../shared/components/icon/icon.component';
import { DialogService } from '../../../../../core/services/dialog.service';
import { LoadingService } from '../../../../../core/services/loading.service';
import { UlbManagementService } from '../../../../../core/services/ulb-management.service';
import {
  UlbTenant,
  Zone,
  ZoneCreatePayload,
  Ward,
  WardCreatePayload,
} from '../../../../../core/models/ulb-tenant.model';

@Component({
  selector: 'app-ulb-structure-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './ulb-structure-dialog.component.html',
  styleUrl: './ulb-structure-dialog.component.scss',
})
export class UlbStructureDialogComponent implements OnChanges {
  private ulbService = inject(UlbManagementService);
  private dialogs = inject(DialogService);
  private loadingService = inject(LoadingService);

  @Input() isOpen = false;
  @Input() ulb: UlbTenant | null = null;

  @Output() close = new EventEmitter<void>();
  @Output() countsUpdated = new EventEmitter<{ tenantId: string; totalZones: number; totalWards: number }>();

  readonly activeSubTab = signal<'zones' | 'wards'>('zones');
  readonly zones = signal<Zone[]>([]);
  readonly wards = signal<Ward[]>([]);
  readonly isLoading = signal<boolean>(false);

  zoneFormData: ZoneCreatePayload = { code: '', name: '' };
  wardFormData: WardCreatePayload = {
    wardNumber: 1,
    wardCode: '',
    wardName: '',
    councilorName: '',
    zoneId: '',
  };
  zoneValidationErrors: { [key: string]: string } = {};
  wardValidationErrors: { [key: string]: string } = {};

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['isOpen'] && this.isOpen && this.ulb) {
      this.initDialog();
    }
  }

  initDialog(): void {
    if (!this.ulb) return;
    this.activeSubTab.set('zones');
    this.zoneFormData = { code: '', name: '' };
    this.wardFormData = {
      wardNumber: (this.ulb.totalWards || 0) + 1,
      wardCode: `W-${String((this.ulb.totalWards || 0) + 1).padStart(3, '0')}`,
      wardName: '',
      councilorName: '',
      zoneId: '',
    };
    this.zoneValidationErrors = {};
    this.wardValidationErrors = {};
    this.loadData();
  }

  loadData(): void {
    if (!this.ulb) return;
    this.isLoading.set(true);

    this.ulbService.getZones(this.ulb.tenantId).subscribe({
      next: (z) => this.zones.set(z),
      error: () => this.zones.set([]),
    });

    this.ulbService
      .getWards(this.ulb.tenantId)
      .pipe(finalize(() => this.isLoading.set(false)))
      .subscribe({
        next: (w) => this.wards.set(w),
        error: () => this.wards.set([]),
      });
  }

  setSubTab(tab: 'zones' | 'wards'): void {
    this.activeSubTab.set(tab);
  }

  addZone(): void {
    this.zoneValidationErrors = {};
    if (!this.zoneFormData.code.trim()) {
      this.zoneValidationErrors['code'] = 'Zone Code is required (e.g. Z-01).';
    }
    if (!this.zoneFormData.name.trim()) {
      this.zoneValidationErrors['name'] = 'Zone Name is required (e.g. North Zone).';
    }
    if (Object.keys(this.zoneValidationErrors).length > 0 || !this.ulb) return;

    this.loadingService.setMessage('Creating child zone record...');
    this.loadingService.show();
    this.ulbService
      .createZone(this.ulb.tenantId, this.zoneFormData)
      .pipe(finalize(() => this.loadingService.hide()))
      .subscribe({
        next: (created) => {
          this.zones.update((list) => [...list, created]);
          this.zoneFormData = { code: '', name: '' };
          this.dialogs.showToast(`Zone ${created.name} (${created.code}) created.`, 'success', 2500);
          this.emitCounts();
        },
        error: (err) => {
          this.dialogs.showToast(err.error?.detail || 'Could not create zone.', 'error', 3500);
        },
      });
  }

  async deleteZone(zone: Zone): Promise<void> {
    if (!this.ulb) return;

    const confirmed = await this.dialogs.confirm({
      title: `Delete Zone ${zone.name}?`,
      message: `Are you sure you want to delete zone ${zone.code}? Linked wards will have their zone unassigned.`,
      confirmText: 'Delete Zone',
      cancelText: 'Cancel',
      variant: 'destructive',
    });

    if (confirmed) {
      this.loadingService.setMessage('Deleting zone...');
      this.loadingService.show();
      this.ulbService
        .deleteZone(this.ulb.tenantId, zone.id)
        .pipe(finalize(() => this.loadingService.hide()))
        .subscribe({
          next: () => {
            this.zones.update((list) => list.filter((z) => z.id !== zone.id));
            this.dialogs.showToast(`Zone ${zone.name} deleted.`, 'info', 2500);
            this.emitCounts();
          },
          error: (err) => {
            this.dialogs.showToast(err.error?.detail || 'Could not delete zone.', 'error', 3500);
          },
        });
    }
  }

  addWard(): void {
    this.wardValidationErrors = {};
    if (!this.wardFormData.wardNumber || this.wardFormData.wardNumber <= 0) {
      this.wardValidationErrors['wardNumber'] = 'Valid Ward Number is required.';
    }
    if (!this.wardFormData.wardName.trim()) {
      this.wardValidationErrors['wardName'] = 'Ward Name is required.';
    }
    if (Object.keys(this.wardValidationErrors).length > 0 || !this.ulb) return;

    this.loadingService.setMessage('Creating child ward record...');
    this.loadingService.show();
    this.ulbService
      .createWard(this.ulb.tenantId, this.wardFormData)
      .pipe(finalize(() => this.loadingService.hide()))
      .subscribe({
        next: (created) => {
          this.wards.update((list) => [...list, created]);
          const nextNum = created.wardNumber + 1;
          this.wardFormData = {
            wardNumber: nextNum,
            wardCode: `W-${String(nextNum).padStart(3, '0')}`,
            wardName: '',
            councilorName: '',
            zoneId: '',
          };
          this.dialogs.showToast(`Ward ${created.wardName} (#${created.wardNumber}) created.`, 'success', 2500);
          this.emitCounts();
        },
        error: (err) => {
          this.dialogs.showToast(err.error?.detail || 'Could not create ward.', 'error', 3500);
        },
      });
  }

  async deleteWard(ward: Ward): Promise<void> {
    if (!this.ulb) return;

    const confirmed = await this.dialogs.confirm({
      title: `Delete Ward #${ward.wardNumber}?`,
      message: `Are you sure you want to delete ward "${ward.wardName}"?`,
      confirmText: 'Delete Ward',
      cancelText: 'Cancel',
      variant: 'destructive',
    });

    if (confirmed) {
      this.loadingService.setMessage('Deleting ward...');
      this.loadingService.show();
      this.ulbService
        .deleteWard(this.ulb.tenantId, ward.id)
        .pipe(finalize(() => this.loadingService.hide()))
        .subscribe({
          next: () => {
            this.wards.update((list) => list.filter((w) => w.id !== ward.id));
            this.dialogs.showToast(`Ward #${ward.wardNumber} deleted.`, 'info', 2500);
            this.emitCounts();
          },
          error: (err) => {
            this.dialogs.showToast(err.error?.detail || 'Could not delete ward.', 'error', 3500);
          },
        });
    }
  }

  private emitCounts(): void {
    if (!this.ulb) return;
    this.countsUpdated.emit({
      tenantId: this.ulb.tenantId,
      totalZones: this.zones().length,
      totalWards: this.wards().length,
    });
  }

  onClose(): void {
    this.close.emit();
  }
}
