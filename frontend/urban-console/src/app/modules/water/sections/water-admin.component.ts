import { ChangeDetectorRef, Component, Input, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { WaterAccess } from '../../../core/models/water.model';
import { WaterService } from '../../../core/services/water.service';
import { WaterI18nService } from '../../../core/services/water-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { dmy, errorText, todayIso } from '../water-utils';

/**
 * Administration: versioned settings (WB-NF-50), categories (WB-NF-64), integration link switches (WB-IR-08),
 * audit trail (WB-NF-13), event outbox (WB-IR-02), API call log (WB-IR-11), notifications and data migration (SRS 3.6.2).
 */
@Component({
  selector: 'app-water-admin',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './water-admin.component.html',
})
export class WaterAdminComponent implements OnInit {
  @Input() access!: WaterAccess;
  private water = inject(WaterService);
  private dialog = inject(DialogService);
  private cdr = inject(ChangeDetectorRef);
  i18n = inject(WaterI18nService);
  dmy = dmy;

  view = signal<string>('settings');
  settings = signal<any[]>([]);
  editKey = '';
  editValue = '';
  editFrom = todayIso();
  editReason = '';
  categories = signal<any[]>([]);
  cat = { code: '', nameEn: '', nameTe: '' };
  links = signal<any[]>([]);
  audit = signal<any[]>([]);
  auditFilter = { action: '', actor: '' };
  events = signal<any>(null);
  apiLog = signal<any[]>([]);
  notes = signal<any[]>([]);
  migrationText = '[\n  {"oldConsumerNo": "OLD-1001", "consumerName": "Example Name", "address": "H.No 1-1-1, Example Street", "wardNumber": 14, "categoryCode": "DOMESTIC", "pipeSizeMm": 15, "isMetered": false, "openingArrears": 0}\n]';
  arrearsAsOf = todayIso();
  migrationResult = signal<any>(null);
  exceptions = signal<any[]>([]);

  ngOnInit(): void {
    this.show(this.can('settings.manage') || this.can('audit.view') ? 'settings' : 'links');
  }

  can(p: string): boolean {
    return this.access.permissions.includes(p);
  }

  show(v: string): void {
    this.view.set(v);
    const fail = (e: unknown) => this.dialog.showToast(errorText(e), 'error');
    if (v === 'settings') this.water.get('/admin/settings').subscribe({ next: (s) => this.settings.set(s), error: fail });
    if (v === 'categories') this.water.get('/admin/categories').subscribe({ next: (c) => this.categories.set(c), error: fail });
    if (v === 'links') this.water.get('/integration/links').subscribe({ next: (l) => this.links.set(l), error: fail });
    if (v === 'audit') this.loadAudit();
    if (v === 'events') this.water.get('/admin/events', { limit: 100 }).subscribe({ next: (e) => this.events.set(e), error: fail });
    if (v === 'api') this.water.get('/admin/api-log', { limit: 200 }).subscribe({ next: (a) => this.apiLog.set(a), error: fail });
    if (v === 'notifications') this.water.get('/admin/notifications', { limit: 200 }).subscribe({ next: (n) => this.notes.set(n), error: fail });
    if (v === 'migration') this.water.get('/migration/exceptions').subscribe({ next: (x) => this.exceptions.set(x), error: () => this.exceptions.set([]) });
  }

  loadAudit(): void {
    this.water.get('/admin/audit', { ...this.auditFilter, limit: 300 }).subscribe({
      next: (a) => this.audit.set(a),
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  edit(s: any): void {
    this.editKey = s.key;
    this.editValue = JSON.stringify(s.value, null, 2);
    this.editFrom = todayIso();
    this.editReason = '';
  }

  saveSetting(): void {
    let value: any;
    try {
      value = JSON.parse(this.editValue);
    } catch {
      this.dialog.showToast('The value is not valid JSON. Check brackets, quotes and commas.', 'error');
      return;
    }
    this.water.post('/admin/settings', { key: this.editKey, value, effectiveFrom: this.editFrom, reason: this.editReason }).subscribe({
      next: (r) => {
        this.dialog.showToast(r.message, 'success');
        this.editKey = '';
        this.show('settings');
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  addCategory(): void {
    this.water.post('/admin/categories', this.cat).subscribe({
      next: (r) => {
        this.dialog.showToast(r.message, 'success');
        this.cat = { code: '', nameEn: '', nameTe: '' };
        this.show('categories');
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  json(v: any): string {
    return v === null || v === undefined ? '' : JSON.stringify(v);
  }

  loadMigrationFile(ev: Event): void {
    const file = (ev.target as HTMLInputElement).files?.[0];
    if (file) {
      file.text().then((t) => {
        this.migrationText = t;
        this.cdr.markForCheck();
      });
    }
  }

  migrate(): void {
    let records: any[];
    try {
      records = JSON.parse(this.migrationText);
      if (!Array.isArray(records)) throw new Error();
    } catch {
      this.dialog.showToast('Paste a JSON list of records: [ {...}, {...} ]', 'error');
      return;
    }
    this.water.post('/migration/connections', { records, arrearsAsOf: this.arrearsAsOf }).subscribe({
      next: (r) => {
        this.migrationResult.set(r);
        this.show('migration');
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  runDaily(): void {
    this.water.post('/jobs/daily', {}).subscribe({
      next: () => this.dialog.showToast('Daily jobs completed', 'success'),
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }
}
