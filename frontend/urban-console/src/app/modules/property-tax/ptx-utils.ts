import { HttpErrorResponse } from '@angular/common/http';
import { computed, signal } from '@angular/core';
import { OfflineItem } from '../../core/models/ptx.model';

/** Unique key for idempotent requests (a payment is never recorded twice - PT-NF-32). */
export function newKey(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

/** Plain-words error message: what went wrong and what to do next (PT-NF-42). */
export function errorText(err: unknown): string {
  const e = err as HttpErrorResponse;
  if (e && e.status === 0) {
    return 'Cannot reach the property tax server. Check the connection and try again.';
  }
  const detail = e?.error?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: any) => `${(d.loc || []).filter((p: any) => p !== 'body').join(' › ')}: ${d.msg}`)
      .join('; ');
  }
  if (e?.status === 403) return 'Your role does not allow this action.';
  if (e?.status === 404) return 'Not found. Check the number and try again.';
  return e?.message || 'Something went wrong. Please try again.';
}

export function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/**
 * Dates are shown as DD-MM-YYYY. Timestamps come from the server in UTC and are shown in the viewer's local time
 * (IST for GWMC users); plain dates are shown as they are.
 */
export function dmy(value?: string | null): string {
  if (!value) return '-';
  const text = String(value);
  const pad = (n: number) => String(n).padStart(2, '0');
  if (text.includes('T')) {
    const when = new Date(/([zZ]|[+-]\d\d:\d\d)$/.test(text) ? text : `${text}Z`);
    if (!isNaN(when.getTime())) {
      return `${pad(when.getDate())}-${pad(when.getMonth() + 1)}-${when.getFullYear()} ${pad(when.getHours())}:${pad(when.getMinutes())}`;
    }
  }
  const [y, m, d] = text.split('-');
  if (!y || !m || !d) return text;
  return `${d.slice(0, 2)}-${m}-${y}`;
}

/** Ledger transaction types in plain words for the statement screens. */
export const TXN_LABEL: { [code: string]: string } = {
  DEMAND: 'Tax raised',
  DEMAND_REVISION: 'Tax revised',
  ROLLOVER: 'Moved to arrears',
  INTEREST: 'Interest added',
  FEE: 'Fee',
  PAYMENT: 'Payment',
  REBATE: 'Rebate',
  OTS_WAIVER: 'One-time settlement',
  WAIVER: 'Waiver',
  WRITE_OFF: 'Write-off',
  ADJUSTMENT: 'Adjustment',
  REFUND: 'Refund',
  OPENING_ARREAR: 'Opening arrears (old system)',
  TRANSFER: 'Transfer',
  TRANSFER_IN: 'Moved in from another property',
  TRANSFER_OUT: 'Moved to another property',
  CHEQUE_RETURN_CHARGE: 'Cheque return charge',
  ADVANCE_ADJUSTED: 'Advance used',
};

export function txnLabel(code: string): string {
  return TXN_LABEL[code] || code.replace(/_/g, ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase());
}

/** Field names from the change history shown as readable labels (PT-07). */
export function fieldLabel(field: string): string {
  const map: { [key: string]: string } = {
    door_no: 'Door no.', address: 'Address', pincode: 'PIN code', locality_id: 'Locality', latitude: 'Latitude', longitude: 'Longitude',
    footprint_id: 'Map building', old_assessment_no: 'Old assessment no.', building_permission_no: 'Building permission no.',
    occupancy_certificate_no: 'Occupancy certificate no.', site_area_sqyd: 'Site area', construction_year: 'Year built',
    exemption_code: 'Exemption', floors: 'Floors', owners: 'Owners', occupiers: 'Tenants / occupiers', status: 'Status',
    property_type: 'Property type', photos: 'Photos', documents: 'Documents',
  };
  return map[field] || field.replace(/_/g, ' ');
}

export interface CsvColumn {
  key: string;
  label: string;
}

/** Excel-ready CSV (UTF-8 with BOM so Telugu and ₹ open correctly) (PT-49). */
export function downloadCsv(fileName: string, rows: any[], columns: CsvColumn[]): void {
  const esc = (v: any) => {
    if (v === null || v === undefined) return '';
    const s = typeof v === 'object' ? JSON.stringify(v) : String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [columns.map((c) => esc(c.label)).join(',')];
  rows.forEach((r) => lines.push(columns.map((c) => esc(r[c.key])).join(',')));
  const blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
  saveBlob(blob, fileName.endsWith('.csv') ? fileName : `${fileName}.csv`);
}

export function saveBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Prints only the element marked .ptx-print-area (browser "Save as PDF" gives the PDF copy). */
export function printArea(): void {
  document.body.classList.add('ptx-printing');
  const done = () => {
    document.body.classList.remove('ptx-printing');
    window.removeEventListener('afterprint', done);
  };
  window.addEventListener('afterprint', done);
  setTimeout(() => window.print(), 50);
}

export function currentPosition(): Promise<{ lat: number; lng: number }> {
  return new Promise((resolve, reject) => {
    if (!('geolocation' in navigator)) {
      reject(new Error('This device cannot share its location.'));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: +p.coords.latitude.toFixed(6), lng: +p.coords.longitude.toFixed(6) }),
      () => reject(new Error('Location is off or not allowed. Turn on location and try again.')),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 },
    );
  });
}

/** Shrinks a camera photo to at most 1280 px so it stores offline and syncs quickly on 4G (PT-NF-05). */
export function compressPhoto(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('Could not read the photo.'));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error('The file is not a photo.'));
      img.onload = () => {
        const scale = Math.min(1, 1280 / Math.max(img.width, img.height));
        const canvas = document.createElement('canvas');
        canvas.width = Math.round(img.width * scale);
        canvas.height = Math.round(img.height * scale);
        canvas.getContext('2d')!.drawImage(img, 0, 0, canvas.width, canvas.height);
        resolve(canvas.toDataURL('image/jpeg', 0.8));
      };
      img.src = String(reader.result);
    };
    reader.readAsDataURL(file);
  });
}

export function dataUrlToBlob(dataUrl: string): Blob {
  const [head, body] = dataUrl.split(',');
  const mime = head.match(/data:(.*?);/)?.[1] || 'image/jpeg';
  const bin = atob(body);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type: mime });
}

/**
 * Server-side pagination state for a table (mandatory pagination bar): rows per page, current page and the
 * skip / limit sent to the API.
 */
export class Pager {
  readonly sizes = [5, 10, 20, 50];
  page = signal(1);
  size = signal(10);
  total = signal(0);
  skip = computed(() => (this.page() - 1) * this.size());
  pages = computed(() => Math.max(1, Math.ceil(this.total() / this.size())));
  from = computed(() => (this.total() ? this.skip() + 1 : 0));
  to = computed(() => Math.min(this.total(), this.skip() + this.size()));

  constructor(size = 10) {
    this.size.set(size);
  }

  query(): { skip: number; limit: number } {
    return { skip: this.skip(), limit: this.size() };
  }

  reset(): void {
    this.page.set(1);
  }
}

/**
 * Offline store for field surveys and notice service (PT-06, PT-43, PT-NF-33). Records stay on the device in
 * IndexedDB until the server confirms them; a record is deleted only after a successful sync.
 */
export class OfflineQueue {
  private static DB = 'urban-ptx-field';
  private static STORE = 'items';
  private static SHEET = 'sheets';

  private static open(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(OfflineQueue.DB, 1);
      req.onupgradeneeded = () => {
        req.result.createObjectStore(OfflineQueue.STORE, { keyPath: 'clientRef' });
        req.result.createObjectStore(OfflineQueue.SHEET, { keyPath: 'wardId' });
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  private static async run<T>(store: string, mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest): Promise<T> {
    const db = await OfflineQueue.open();
    return new Promise<T>((resolve, reject) => {
      const tx = db.transaction(store, mode);
      const req = fn(tx.objectStore(store));
      tx.oncomplete = () => {
        db.close();
        resolve(req.result as T);
      };
      tx.onerror = () => {
        db.close();
        reject(tx.error);
      };
    });
  }

  static all(): Promise<OfflineItem[]> {
    return OfflineQueue.run<OfflineItem[]>(OfflineQueue.STORE, 'readonly', (s) => s.getAll());
  }

  static put(item: OfflineItem): Promise<unknown> {
    return OfflineQueue.run(OfflineQueue.STORE, 'readwrite', (s) => s.put(item));
  }

  static remove(clientRef: string): Promise<unknown> {
    return OfflineQueue.run(OfflineQueue.STORE, 'readwrite', (s) => s.delete(clientRef));
  }

  /** The ward sheet downloaded before going out, so the officer can work without a signal. */
  static saveSheet(sheet: any): Promise<unknown> {
    return OfflineQueue.run(OfflineQueue.SHEET, 'readwrite', (s) => s.put({ ...sheet, wardId: sheet.ward.wardId }));
  }

  static sheets(): Promise<any[]> {
    return OfflineQueue.run<any[]>(OfflineQueue.SHEET, 'readonly', (s) => s.getAll());
  }
}

/** Billing periods counted back from the current one: "2026-27-H2", "2026-27-H1", "2025-26-H2", ... (or "-Y" when yearly). */
export function periodsBack(current: string, count: number): string[] {
  const m = /^(\d{4})-(\d{2})-(H1|H2|Y)$/.exec(current || '');
  if (!m) return current ? [current] : [];
  let year = Number(m[1]);
  let half = m[3];
  const out: string[] = [];
  const code = (y: number, h: string) => `${y}-${String((y + 1) % 100).padStart(2, '0')}-${h}`;
  for (let i = 0; i < count; i++) {
    out.push(code(year, half));
    if (half === 'Y') year -= 1;
    else if (half === 'H2') half = 'H1';
    else {
      half = 'H2';
      year -= 1;
    }
  }
  return out;
}

export function periodName(code: string): string {
  const m = /^(\d{4})-(\d{2})-(H1|H2|Y)$/.exec(code || '');
  if (!m) return code;
  const fy = `${m[1]}-${m[2]}`;
  return m[3] === 'Y' ? `Year ${fy}` : m[3] === 'H1' ? `First half ${fy} (Apr-Sep)` : `Second half ${fy} (Oct-Mar)`;
}
