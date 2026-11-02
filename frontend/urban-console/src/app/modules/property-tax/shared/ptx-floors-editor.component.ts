import { Component, EventEmitter, Input, Output, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Floor, PtxAccess } from '../../../core/models/ptx.model';
import { PtxI18nService } from '../../../core/services/ptx-i18n.service';

/**
 * Floor-by-floor entry (use, construction, area, owner or tenant), used by applications, inspections and surveys.
 * A floor can have more than one row: a part used differently, such as a shop in a house (PT-31), an installation on
 * the roof (PT-31) and a declared guest-accommodation area (PT-33). Apartment common areas are added for you (PT-07).
 */
@Component({
  selector: 'app-ptx-floors-editor',
  standalone: true,
  imports: [FormsModule],
  template: `
    <div class="ptx-floors">
      @for (f of floors; track $index) {
        <div class="ptx-floor-row">
          <label>{{ i18n.t('floor') }}
            <select [(ngModel)]="f.floorNo" (ngModelChange)="emit()">
              @for (n of floorNumbers; track n) { <option [ngValue]="n">{{ floorName(n) }}</option> }
            </select>
          </label>
          @if (allowExtras) {
            <label>This row is
              <select [ngModel]="f.portion || 'FULL'" (ngModelChange)="setPortion(f, $event)">
                <option value="FULL">The whole floor</option>
                <option value="PART">Part of the floor, used differently</option>
                <option value="ROOFTOP">Installation on the roof</option>
              </select>
            </label>
          }
          @if (f.portion === 'ROOFTOP') {
            <label>Installation
              <select [(ngModel)]="f.rooftopType" (ngModelChange)="emit()">
                <option [ngValue]="null">Choose…</option>
                @for (c of access.codes.ROOFTOP_TYPE || []; track c.code) { <option [value]="c.code">{{ i18n.name(c) }}</option> }
              </select>
            </label>
            <label>Area it covers (sq ft)
              <input type="number" min="1" step="1" inputmode="decimal" [(ngModel)]="f.builtupSqft" (ngModelChange)="emit()" />
            </label>
          } @else {
            <label>{{ i18n.t('usage') }}
              <select [(ngModel)]="f.usageCode" (ngModelChange)="emit()">
                @for (c of access.codes.USAGE || []; track c.code) { <option [value]="c.code">{{ i18n.name(c) }}</option> }
              </select>
            </label>
            <label>{{ i18n.t('construction') }}
              <select [(ngModel)]="f.constructionCode" (ngModelChange)="emit()">
                @for (c of access.codes.CONSTRUCTION || []; track c.code) { <option [value]="c.code">{{ i18n.name(c) }}</option> }
              </select>
            </label>
            <label>{{ i18n.t('builtup') }}
              <input type="number" min="1" step="1" inputmode="decimal" [(ngModel)]="f.builtupSqft" (ngModelChange)="emit()" />
            </label>
            <label>{{ i18n.t('occupancy') }}
              <select [(ngModel)]="f.occupancy" (ngModelChange)="emit()">
                <option value="OWNER">{{ i18n.t('OWNER') }}</option>
                <option value="TENANT">{{ i18n.t('TENANT') }}</option>
              </select>
            </label>
            @if (allowExtras) {
              <label class="inline" title="Tick if this area is let to paying guests (homestay, guest house, PG, lodging). It is charged at the notified guest-accommodation rate and checked by the inspector.">
                <input type="checkbox" [(ngModel)]="f.declaredAccommodation" (ngModelChange)="emit()" /> Guest accommodation
              </label>
            }
          }
          @if (floors.length > 1) {
            <button type="button" class="ptx-btn sm ghost" (click)="remove($index)" aria-label="Remove row">Remove</button>
          }
        </div>
      }
      <div class="ptx-row" style="margin: 0">
        <button type="button" class="ptx-btn sm" (click)="add('FULL')">+ Add a floor</button>
        @if (allowExtras) { <button type="button" class="ptx-btn sm" (click)="add('PART')">+ Part of a floor used differently</button>
          <button type="button" class="ptx-btn sm" (click)="add('ROOFTOP')">+ Roof installation</button> }
      </div>
    </div>
  `,
})
export class PtxFloorsEditorComponent {
  @Input({ required: true }) access!: PtxAccess;
  @Input() floors: Floor[] = [];
  /** Part-of-floor, rooftop and guest-accommodation rows. Off where they make no sense (e.g. flats, which add them later). */
  @Input() allowExtras = true;
  @Output() floorsChange = new EventEmitter<Floor[]>();
  i18n = inject(PtxI18nService);
  readonly floorNumbers = [-2, -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

  floorName(n: number): string {
    if (n === 0) return 'Ground';
    if (n < 0) return `Cellar ${-n}`;
    return `Floor ${n}`;
  }

  add(portion: 'FULL' | 'PART' | 'ROOFTOP'): void {
    const last = this.floors[this.floors.length - 1];
    const residential = this.access.codes.USAGE?.find((c) => c.code === 'RESIDENTIAL')?.code || this.access.codes.USAGE?.[0]?.code || '';
    this.floors.push({
      floorNo: portion === 'FULL' ? (last ? last.floorNo + 1 : 0) : (last?.floorNo ?? 0),
      usageCode: portion === 'ROOFTOP' ? '' : last?.usageCode || residential,
      constructionCode: portion === 'ROOFTOP' ? '' : last?.constructionCode || (this.access.codes.CONSTRUCTION?.find((c) => c.code === 'RCC')?.code || this.access.codes.CONSTRUCTION?.[0]?.code) || '',
      builtupSqft: portion === 'FULL' ? last?.builtupSqft || 0 : 0,
      occupancy: 'OWNER', portion, rooftopType: portion === 'ROOFTOP' ? null : undefined, declaredAccommodation: false,
    });
    this.emit();
  }

  setPortion(f: Floor, portion: 'FULL' | 'PART' | 'ROOFTOP'): void {
    f.portion = portion;
    if (portion === 'ROOFTOP') {
      f.usageCode = '';
      f.constructionCode = '';
      f.declaredAccommodation = false;
    } else {
      f.rooftopType = undefined;
      f.usageCode = f.usageCode || this.access.codes.USAGE?.[0]?.code || '';
      f.constructionCode = f.constructionCode || (this.access.codes.CONSTRUCTION?.find((c) => c.code === 'RCC')?.code || this.access.codes.CONSTRUCTION?.[0]?.code) || '';
    }
    this.emit();
  }

  remove(i: number): void {
    this.floors.splice(i, 1);
    this.emit();
  }

  emit(): void {
    this.floorsChange.emit(this.floors);
  }
}
