import { HttpErrorResponse } from '@angular/common/http';
import { OfflineReading } from '../../core/models/water.model';

/** Unique key for idempotent requests (a payment is never recorded twice - WB-NF-32). */
export function newKey(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

/** Plain-words error message: what went wrong and what to do next (WB-NF-42). */
export function errorText(err: unknown): string {
  const e = err as HttpErrorResponse;
  if (e && e.status === 0) {
    return 'Cannot reach the water billing server. Check the connection and try again.';
  }
  const detail = e?.error?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: any) => `${(d.loc || []).filter((p: any) => p !== 'body').join(' › ')}: ${d.msg}`)
      .join('; ');
  }
  if (e?.status === 403) return 'Your role does not allow this action.';
  return e?.message || 'Something went wrong. Please try again.';
}

export function todayIso(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/**
 * Dates are shown as DD-MM-YYYY (SRS 3.4). Timestamps come from the server in UTC and are shown in the
 * viewer's local time (IST for GWMC users); plain dates are shown as they are.
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

export interface CsvColumn {
  key: string;
  label: string;
}

/** Excel-ready CSV (UTF-8 with BOM so Telugu and ₹ open correctly) (WB-66). */
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

/** Prints only the element marked .wtr-print-area (browser "Save as PDF" gives the PDF export). */
export function printArea(): void {
  document.body.classList.add('wtr-printing');
  const done = () => {
    document.body.classList.remove('wtr-printing');
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

/** Shrinks a camera photo to at most 1280 px so it stores offline and syncs quickly on 4G (WB-NF-05). */
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
 * Offline store for field readings and photos (WB-13, WB-NF-33). Records stay on the device in IndexedDB
 * until the server confirms them; a record is deleted only after a successful sync.
 */
export class FieldQueue {
  private static DB = 'urban-water-field';
  private static STORE = 'readings';

  private static open(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      const req = indexedDB.open(FieldQueue.DB, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(FieldQueue.STORE, { keyPath: 'clientRef' });
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  private static async run<T>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest): Promise<T> {
    const db = await FieldQueue.open();
    return new Promise<T>((resolve, reject) => {
      const tx = db.transaction(FieldQueue.STORE, mode);
      const req = fn(tx.objectStore(FieldQueue.STORE));
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

  static all(): Promise<OfflineReading[]> {
    return FieldQueue.run<OfflineReading[]>('readonly', (s) => s.getAll());
  }

  static put(item: OfflineReading): Promise<unknown> {
    return FieldQueue.run('readwrite', (s) => s.put(item));
  }

  static remove(clientRef: string): Promise<unknown> {
    return FieldQueue.run('readwrite', (s) => s.delete(clientRef));
  }
}
