import { AfterViewInit, Component, ElementRef, EventEmitter, Input, OnDestroy, Output, ViewChild, ViewEncapsulation } from '@angular/core';
import { CommonModule } from '@angular/common';
import * as L from 'leaflet';

export interface MappedProperty {
  upin: string;
  doorNo: string | null;
  address: string;
  wardNumber: number | null;
  latitude: number | null;
  longitude: number | null;
}

/** Where this one property actually is, for the citizen who just wants to see it on the map - not the staff GIS console. */
@Component({
  selector: 'app-ptx-citizen-map-dialog',
  standalone: true,
  encapsulation: ViewEncapsulation.None,
  imports: [CommonModule],
  styleUrl: './ptx-citizen-map-dialog.component.scss',
  template: `
    <div class="ptx-modal-backdrop" (click)="close()"></div>
    <section class="ptx-modal" role="dialog" aria-modal="true" [attr.aria-label]="'Map: ' + (property.doorNo || property.upin)">
      <div class="ptx-modal-head">
        <div style="min-width: 0">
          <h2>{{ property.doorNo || property.upin }}</h2>
          <p class="ptx-muted" style="margin: 0.1rem 0 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis">
            {{ property.address }}@if (property.wardNumber) { · Ward {{ property.wardNumber }} }
          </p>
        </div>
        <button class="ptx-btn" (click)="close()">Close</button>
      </div>
      <div class="ptx-modal-body" style="padding: 0.75rem">
        <div #mapEl class="ptx-map"></div>
      </div>
      <div class="ptx-modal-foot">
        <a class="ptx-btn" [href]="directionsUrl()" target="_blank" rel="noopener">Get directions</a>
      </div>
    </section>
  `,
})
export class PtxCitizenMapDialogComponent implements AfterViewInit, OnDestroy {
  @Input({ required: true }) property!: MappedProperty;
  @Output() closed = new EventEmitter<void>();
  @ViewChild('mapEl') mapEl!: ElementRef<HTMLDivElement>;
  private map?: L.Map;

  ngAfterViewInit(): void {
    const known = this.property.latitude != null && this.property.longitude != null;
    const lat = this.property.latitude ?? 17.985, lng = this.property.longitude ?? 79.59;
    this.map = L.map(this.mapEl.nativeElement, { center: [lat, lng], zoom: known ? 15 : 13 });
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OpenStreetMap contributors' }).addTo(this.map);
    if (known) {
      const marker = L.circleMarker([lat, lng], { radius: 10, color: '#fff', weight: 2, fillColor: '#0E3A52', fillOpacity: 0.95 }).addTo(this.map);
      marker.bindPopup(`<b>${this.escape(this.property.doorNo || this.property.upin)}</b><br>${this.escape(this.property.address)}`).openPopup();
      // a gentle fly-in to the exact spot, rather than snapping straight to the close-up view
      setTimeout(() => this.map?.flyTo([lat, lng], 18, { duration: 1.1 }), 150);
    }
  }

  ngOnDestroy(): void {
    this.map?.remove();
  }

  close(): void {
    this.closed.emit();
  }

  directionsUrl(): string {
    const lat = this.property.latitude, lng = this.property.longitude;
    return lat != null && lng != null ? `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}` : 'https://www.google.com/maps';
  }

  private escape(text: string): string {
    const div = document.createElement('div');
    div.textContent = text ?? '';
    return div.innerHTML;
  }
}
