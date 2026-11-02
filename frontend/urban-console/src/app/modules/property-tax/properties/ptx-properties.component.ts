import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { PropertySummary, PtxAccess } from '../../../core/models/ptx.model';
import { PtxService } from '../../../core/services/ptx.service';
import { PtxI18nService } from '../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { IconComponent } from '../../../shared/components/icon/icon.component';
import { PtxPagerComponent } from '../shared/ptx-pager.component';
import { PropertyDetailDialogComponent } from './dialogs/property-detail-dialog/property-detail-dialog.component';
import { Pager, errorText, saveBlob, todayIso } from '../ptx-utils';

/** Property register: search by UPIN, old number, owner, mobile or door number (PT-04, PT-05), filters and paging. */
@Component({
  selector: 'app-ptx-properties',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent, PtxPagerComponent, PropertyDetailDialogComponent],
  templateUrl: './ptx-properties.component.html',
})
export class PtxPropertiesComponent implements OnInit {
  @Input({ required: true }) access!: PtxAccess;
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  private route = inject(ActivatedRoute);
  i18n = inject(PtxI18nService);

  filters = { search: '', wardId: '', status: '', paymentStatus: '', locationPending: '' };
  rows = signal<PropertySummary[]>([]);
  loading = signal(false);
  pager = new Pager(10);
  openUpin = signal<string | null>(null);
  private searchTimer?: ReturnType<typeof setTimeout>;

  ngOnInit(): void {
    const upin = this.route.snapshot.queryParamMap.get('upin');
    if (upin) {
      this.filters.search = upin;
      this.openUpin.set(upin);
    }
    this.load();
  }

  can(p: string): boolean {
    return this.access.permissions.includes(p);
  }

  /** Live search: waits for a short pause in typing, then asks the server. */
  onSearchInput(): void {
    if (this.searchTimer) clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => this.applyFilters(), 350);
  }

  applyFilters(): void {
    this.pager.reset();
    this.load();
  }

  load(): void {
    this.loading.set(true);
    const f = this.filters;
    this.ptx
      .properties({ search: f.search, wardId: f.wardId, status: f.status, paymentStatus: f.paymentStatus, locationPending: f.locationPending,
        ...this.pager.query() })
      .subscribe({
        next: (r) => {
          this.rows.set(r.items);
          this.pager.total.set(r.total);
          this.loading.set(false);
        },
        error: (e) => {
          this.rows.set([]);
          this.pager.total.set(0);
          this.loading.set(false);
          this.dialog.showToast(errorText(e), 'error');
        },
      });
  }

  initials(name: string): string {
    return (name || '?').split(/[\s.]+/).filter((p) => p).slice(0, 2).map((p) => p[0].toUpperCase()).join('');
  }

  exportRegister(): void {
    this.ptx.getBlob('/export/register?format=csv').subscribe({
      next: (b) => saveBlob(b, `property-register-${todayIso()}.csv`),
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  onClosed(changed: boolean): void {
    this.openUpin.set(null);
    if (changed) this.load();
  }
}
