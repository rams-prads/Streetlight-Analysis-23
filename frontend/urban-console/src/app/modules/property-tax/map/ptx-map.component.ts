import { AfterViewInit, Component, ElementRef, Input, OnDestroy, ViewChild, ViewEncapsulation, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import * as L from 'leaflet';
import { PtxAccess } from '../../../core/models/ptx.model';
import { PtxService } from '../../../core/services/ptx.service';
import { PtxI18nService } from '../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { downloadCsv, errorText, todayIso } from '../ptx-utils';

type View = 'properties' | 'heat';

const STATUS_COLOUR: { [k: string]: string } = { PAID: '#3D8D51', DUE: '#D98A2B', ARREARS: '#B23A2E' };

/**
 * GIS revenue map (PT-50..PT-54): properties coloured by payment status, buildings on the map with no property number,
 * buildings bigger on the map than on record, collection heat by zone / ward / locality and the estimated tax gap.
 * Base map: OpenStreetMap as a stand-in until GWMC's GIS base map is connected (PT-IR-10).
 */
@Component({
  selector: 'app-ptx-map',
  standalone: true,
  encapsulation: ViewEncapsulation.None,
  imports: [CommonModule, FormsModule],
  templateUrl: './ptx-map.component.html',
  styleUrl: './ptx-map.component.scss',
})
export class PtxMapComponent implements AfterViewInit, OnDestroy {
  @Input({ required: true }) access!: PtxAccess;
  @ViewChild('mapEl') mapEl!: ElementRef<HTMLDivElement>;
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  private router = inject(Router);
  i18n = inject(PtxI18nService);

  view: View = 'properties';
  heatLevel: 'zone' | 'ward' | 'locality' = 'ward';
  show = { properties: true, unassessed: true, mismatch: true };
  counts = signal({ properties: 0, unassessed: 0, mismatch: 0, noLocation: 0, margin: 10 });
  heat = signal<any[]>([]);
  gap = signal<any | null>(null);

  private map?: L.Map;
  private layer = L.layerGroup();
  private layers: any = null;

  ngAfterViewInit(): void {
    this.map = L.map(this.mapEl.nativeElement, { center: [17.985, 79.59], zoom: 13 });
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OpenStreetMap contributors' }).addTo(this.map);
    this.layer.addTo(this.map);
    this.load();
    this.loadGap();
  }

  ngOnDestroy(): void {
    this.map?.remove();
  }

  can(p: string): boolean {
    return this.access.permissions.includes(p);
  }

  load(): void {
    this.ptx.get('/gis/layers').subscribe({
      next: (d) => {
        this.layers = d;
        this.counts.set({ properties: d.properties.length, unassessed: d.unassessed.length, mismatch: d.areaMismatch.length,
          noLocation: d.propertiesWithoutLocation, margin: d.mismatchMarginPercent });
        if (this.view === 'properties') this.draw(true);
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  loadHeat(): void {
    this.ptx.get('/gis/heat', { level: this.heatLevel }).subscribe({
      next: (d) => {
        this.heat.set(d.areas);
        if (this.view === 'heat') this.draw(true);
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  loadGap(): void {
    this.ptx.get('/gis/tax-gap').subscribe({ next: (g) => this.gap.set(g), error: () => this.gap.set(null) });
  }

  setView(v: View): void {
    this.view = v;
    if (v === 'heat') this.loadHeat();
    else this.draw(true);
  }

  draw(fit = false): void {
    if (!this.map) return;
    this.layer.clearLayers();
    const bounds: L.LatLngTuple[] = [];
    if (this.view === 'heat') {
      const areas = this.heat();
      const maxArrears = Math.max(1, ...areas.map((a) => a.arrears || 0));
      for (const a of areas) {
        if (a.lat == null || a.lng == null) continue;
        const eff = a.efficiencyPercent ?? 0;
        const colour = eff >= 75 ? '#3D8D51' : eff >= 50 ? '#D98A2B' : '#B23A2E';
        L.circle([a.lat, a.lng], { radius: 250 + 900 * ((a.arrears || 0) / maxArrears), color: colour, weight: 2, fillColor: colour, fillOpacity: 0.3 })
          .bindPopup(`<b>${this.escape(a.name)}</b><br>${a.properties} properties<br>Due ₹${this.money(a.due)} · collected ₹${this.money(a.collection)}<br>` +
            `Collection efficiency <b>${eff}%</b><br>Still unpaid ₹${this.money(a.arrears)}`)
          .addTo(this.layer);
        bounds.push([a.lat, a.lng]);
      }
    } else if (this.layers) {
      if (this.show.properties) {
        for (const p of this.layers.properties) {
          const m = L.circleMarker([p.lat, p.lng], { radius: 7, color: '#fff', weight: 1.5, fillColor: STATUS_COLOUR[p.paymentStatus] || '#80A0AF', fillOpacity: 0.95 });
          const box = document.createElement('div');
          box.innerHTML = `<b>${p.upin}</b><br>${this.escape(p.address)}<br>Ward ${p.wardNumber}<br>Due ₹${this.money(p.totalDue)} (${p.paymentStatus.toLowerCase()})<br>`;
          box.appendChild(this.link('Open record', () => this.router.navigate(['/modules/ptx', 'properties'], { queryParams: { upin: p.upin } })));
          m.bindPopup(box).addTo(this.layer);
          bounds.push([p.lat, p.lng]);
        }
      }
      if (this.show.unassessed) {
        for (const f of this.layers.unassessed) {
          const m = L.circleMarker([f.lat, f.lng], { radius: 8, color: '#6f42c1', weight: 2, fillColor: '#fff', fillOpacity: 0.9, dashArray: '3' });
          const box = document.createElement('div');
          box.innerHTML = `<b>Building with no property number</b><br>${f.ref} · about ${f.mapSqft} sq ft · ward ${f.wardNumber}<br>` +
            `Status: ${f.status === 'SENT_FOR_VERIFICATION' ? 'sent for field verification' : 'not yet checked'}<br>`;
          if (f.status === 'NONE' && this.can('property.edit')) {
            box.appendChild(this.link('Send for field verification', () => this.verify(f.footprintId)));
          }
          m.bindPopup(box).addTo(this.layer);
          bounds.push([f.lat, f.lng]);
        }
      }
      if (this.show.mismatch) {
        for (const x of this.layers.areaMismatch) {
          const m = L.circleMarker([x.lat, x.lng], { radius: 11, color: '#0E3A52', weight: 3, fill: false });
          const box = document.createElement('div');
          box.innerHTML = `<b>${x.upin}</b><br>On the map: ${x.mapSqft} sq ft<br>On record: ${x.recordedSqft} sq ft<br><b>${x.differencePercent}% bigger</b> than recorded<br>`;
          box.appendChild(this.link('Open record', () => this.router.navigate(['/modules/ptx', 'properties'], { queryParams: { upin: x.upin } })));
          m.bindPopup(box).addTo(this.layer);
        }
      }
    }
    if (fit && bounds.length) this.map.fitBounds(bounds, { padding: [30, 30], maxZoom: 16 });
  }

  verify(footprintId: string): void {
    this.ptx.post(`/gis/footprints/${encodeURIComponent(footprintId)}/verify`).subscribe({
      next: () => {
        this.dialog.showToast('Sent to the field team. It appears on their ward sheet as a building to verify.', 'success');
        this.map?.closePopup();
        this.load();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  exportGap(): void {
    const g = this.gap();
    if (!g) return;
    downloadCsv(`ptx-tax-gap-${todayIso()}`, g.rows, [
      { key: 'wardNumber', label: 'Ward' }, { key: 'wardName', label: 'Ward name' }, { key: 'assessedProperties', label: 'Assessed properties' },
      { key: 'actualDemand', label: 'Annual demand' }, { key: 'unassessedBuildings', label: 'Buildings with no UPIN' },
      { key: 'unassessedSqft', label: 'Their area (sq ft)' }, { key: 'underAssessedSqft', label: 'Extra area not on record (sq ft)' },
      { key: 'estimatedGap', label: 'Estimated gap' }, { key: 'gapPercent', label: 'Gap %' },
    ]);
  }

  private link(text: string, onClick: () => void): HTMLAnchorElement {
    const a = document.createElement('a');
    a.textContent = text;
    a.style.cursor = 'pointer';
    a.style.display = 'inline-block';
    a.style.padding = '6px 0';
    a.onclick = onClick;
    return a;
  }

  private money(v: number): string {
    return Number(v || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });
  }

  private escape(text: string): string {
    const div = document.createElement('div');
    div.textContent = text ?? '';
    return div.innerHTML;
  }
}
