import { Component, EventEmitter, Input, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../shared/components/icon/icon.component';
import { Pager } from '../ptx-utils';

/** Standard PUROJAS pagination bar: rows per page [5, 10, 20, 50], previous / next, "Showing X to Y of Z entries". */
@Component({
  selector: 'app-ptx-pager',
  standalone: true,
  imports: [FormsModule, IconComponent],
  template: `
    <div class="purojas-pagination-bar">
      <div class="pagination-info">
        Showing <strong>{{ pager.from() }}</strong> to <strong>{{ pager.to() }}</strong> of <strong>{{ pager.total() }}</strong> entries
      </div>
      <div class="pagination-controls">
        <div class="page-size-picker">
          <label for="ptx-rows-{{ id }}">Rows per page:</label>
          <div class="select-picker-wrap">
            <select id="ptx-rows-{{ id }}" [ngModel]="pager.size()" (ngModelChange)="setSize($event)">
              @for (s of pager.sizes; track s) { <option [ngValue]="s">{{ s }}</option> }
            </select>
          </div>
        </div>
        <div class="pagination-buttons">
          <button class="btn-page-nav" [disabled]="pager.page() <= 1" (click)="goTo(pager.page() - 1)" aria-label="Previous page">
            <app-icon name="chevron-left" [size]="16"></app-icon>
          </button>
          <span class="ptx-page-label">Page {{ pager.page() }} of {{ pager.pages() }}</span>
          <button class="btn-page-nav" [disabled]="pager.page() >= pager.pages()" (click)="goTo(pager.page() + 1)" aria-label="Next page">
            <app-icon name="chevron-right" [size]="16"></app-icon>
          </button>
        </div>
      </div>
    </div>
  `,
})
export class PtxPagerComponent {
  private static seq = 0;
  @Input({ required: true }) pager!: Pager;
  @Output() changed = new EventEmitter<void>();
  readonly id = ++PtxPagerComponent.seq;

  setSize(size: number): void {
    this.pager.size.set(Number(size));
    this.pager.page.set(1);
    this.changed.emit();
  }

  goTo(page: number): void {
    if (page < 1 || page > this.pager.pages()) return;
    this.pager.page.set(page);
    this.changed.emit();
  }
}
