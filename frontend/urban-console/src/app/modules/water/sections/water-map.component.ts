import { AfterViewInit, Component, ElementRef, Input, OnDestroy, ViewChild, ViewEncapsulation, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import * as L from 'leaflet';
import { WaterAccess } from '../../../core/models/water.model';
import { WaterService } from '../../../core/services/water.service';
import { WaterI18nService } from '../../../core/services/water-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { errorText } from '../water-utils';

type ColourBy = 'paymentStatus' | 'category' | 'status';

const PALETTE: { [by: string]: { [value: string]: string } } = {
  paymentStatus: { PAID: '#3D8D51', DUE: '#D98A2B', ARREARS: '#B23A2E' },
  category: { DOMESTIC: '#1B8C77', NON_DOMESTIC: '#D98A2B', INDUSTRIAL: '#0E3A52', BULK: '#82683C' },
  status: { ACTIVE: '#3D8D51', TEMP_DISCONNECTED: '#D98A2B', DISCONNECTED: '#B23A2E', CLOSED: '#80A0AF' },
};

/**
 * GIS water revenue map (WB-60, WB-61): connections coloured by payment status, category or connection status;
 * complaint / leak hotspots and illegal connection cases. Clicking a connection opens its record (WB-07).
 * Base map: OpenStreetMap as a stand-in until GWMC's GIS base map (Bhuvan / Survey of India) is connected (WB-IR-10).
 */
@Component({
  selector: 'app-water-map',
  standalone: true,
  encapsulation: ViewEncapsulation.None,
  imports: [CommonModule, FormsModule],
  styleUrl: './water-map.scss',
  template: `
    <div class="wtr-card">
      <div class="wtr-row">
        <label>Colour connections by
          <select [(ngModel)]="colourBy" (change)="draw()">
            <option value="paymentStatus">Payment status</option>
            <option value="category">{{ i18n.t('category') }}</option>
            <option value="status">Connection status</option>
          </select>
        </label>
        <label style="flex-direction: row; align-items: center; gap: 0.3rem"><input type="checkbox" [(ngModel)]="show.connections" (change)="draw()" /> {{ i18n.t('connections') }}</label>
        <label style="flex-direction: row; align-items: center; gap: 0.3rem"><input type="checkbox" [(ngModel)]="show.hotspots" (change)="draw()" /> Complaint / leak hotspots</label>
        <label style="flex-direction: row; align-items: center; gap: 0.3rem"><input type="checkbox" [(ngModel)]="show.complaints" (change)="draw()" /> {{ i18n.t('complaints') }}</label>
        <label style="flex-direction: row; align-items: center; gap: 0.3rem"><input type="checkbox" [(ngModel)]="show.illegal" (change)="draw()" /> {{ i18n.t('illegalConnections') }}</label>
        <span class="wtr-spacer"></span>
        <button class="wtr-btn" (click)="load()">{{ i18n.t('refresh') }}</button>
      </div>
      <div class="wtr-legend">
        @for (k of legend(); track k.label) { <span><i [style.background]="k.colour"></i>{{ k.label }}</span> }
        <span><i style="background: #6f42c1"></i>Complaint</span>
        <span><i style="background: #000"></i>Illegal case</span>
        @if (missing()) { <span class="wtr-chip DUE">{{ missing() }} connection(s) have no location yet</span> }
      </div>
    </div>
    <div #mapEl class="wtr-map"></div>
    <p class="wtr-muted">Base map © OpenStreetMap contributors (stand-in until the GWMC GIS base map with ward boundaries and water network layers is provided).</p>
  `,
})
export class WaterMapComponent implements AfterViewInit, OnDestroy {
  @Input() access!: WaterAccess;
  @ViewChild('mapEl') mapEl!: ElementRef<HTMLDivElement>;
  private water = inject(WaterService);
  private dialog = inject(DialogService);
  private router = inject(Router);
  i18n = inject(WaterI18nService);

  colourBy: ColourBy = 'paymentStatus';
  show = { connections: true, hotspots: true, complaints: true, illegal: true };
  legend = signal<{ label: string; colour: string }[]>([]);
  missing = signal(0);

  private map?: L.Map;
  private layer = L.layerGroup();
  private data: any = null;

  ngAfterViewInit(): void {
    this.map = L.map(this.mapEl.nativeElement, { center: [17.985, 79.59], zoom: 13 });
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; OpenStreetMap contributors',
    }).addTo(this.map);
    this.layer.addTo(this.map);
    this.load();
  }

  ngOnDestroy(): void {
    this.map?.remove();
  }

  load(): void {
    this.water.get('/gis/layers').subscribe({
      next: (d) => {
        this.data = d;
        this.missing.set(d.connectionsWithoutLocation);
        this.draw(true);
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  draw(fit = false): void {
    if (!this.map || !this.data) return;
    this.layer.clearLayers();
    const palette = PALETTE[this.colourBy];
    this.legend.set(Object.keys(palette).map((k) => ({ label: k, colour: palette[k] })));
    const bounds: L.LatLngTuple[] = [];

    if (this.show.connections) {
      for (const c of this.data.connections) {
        const colour = palette[c[this.colourBy]] || '#80A0AF';
        const marker = L.circleMarker([c.lat, c.lng], { radius: 7, color: '#fff', weight: 1.5, fillColor: colour, fillOpacity: 0.95 });
        const popup = document.createElement('div');
        popup.innerHTML = `<b>${c.consumerNo}</b><br>${this.escape(c.consumerName)}<br>${c.category} · ${c.status}<br>` +
          `Due: ₹${Number(c.totalDue).toFixed(2)} (${c.paymentStatus})<br>`;
        const link = document.createElement('a');
        link.textContent = 'Open record';
        link.style.cursor = 'pointer';
        link.onclick = () => this.router.navigate(['/modules/wtr', 'connections'], { queryParams: { consumerNo: c.consumerNo } });
        popup.appendChild(link);
        marker.bindPopup(popup);
        marker.addTo(this.layer);
        bounds.push([c.lat, c.lng]);
      }
    }

    if (this.show.hotspots) {
      // complaints in the last 90 days (and all open ones) grouped on a ~500 m grid
      const cells: { [key: string]: { lat: number; lng: number; n: number; leaks: number } } = {};
      for (const c of this.data.complaints) {
        const key = `${(c.lat / 0.005).toFixed(0)}:${(c.lng / 0.005).toFixed(0)}`;
        const cell = (cells[key] ||= { lat: 0, lng: 0, n: 0, leaks: 0 });
        cell.lat += c.lat;
        cell.lng += c.lng;
        cell.n += 1;
        cell.leaks += c.type === 'LEAK' ? 1 : 0;
      }
      Object.values(cells).forEach((cell) => {
        L.circle([cell.lat / cell.n, cell.lng / cell.n], { radius: 120 + 80 * cell.n, color: '#B23A2E', weight: 1, fillColor: '#B23A2E', fillOpacity: 0.18 })
          .bindTooltip(`${cell.n} complaint(s), ${cell.leaks} leak(s)`)
          .addTo(this.layer);
      });
    }

    if (this.show.complaints) {
      for (const c of this.data.complaints) {
        L.circleMarker([c.lat, c.lng], { radius: 5, color: '#fff', weight: 1, fillColor: c.status === 'CLOSED' ? '#b9a6d9' : '#6f42c1', fillOpacity: 1 })
          .bindPopup(`<b>${c.complaintNo}</b><br>${c.type} · ${c.status}${c.overdue ? ' · past SLA' : ''}`)
          .addTo(this.layer);
        bounds.push([c.lat, c.lng]);
      }
    }

    if (this.show.illegal) {
      for (const c of this.data.illegalCases) {
        L.circleMarker([c.lat, c.lng], { radius: 6, color: '#fff', weight: 1.5, fillColor: '#000', fillOpacity: 1 })
          .bindPopup(`<b>${c.caseNo}</b><br>Illegal connection case · ${c.status}`)
          .addTo(this.layer);
        bounds.push([c.lat, c.lng]);
      }
    }
    if (fit && bounds.length) this.map.fitBounds(bounds, { padding: [30, 30], maxZoom: 15 });
  }

  private escape(text: string): string {
    const div = document.createElement('div');
    div.textContent = text ?? '';
    return div.innerHTML;
  }
}
