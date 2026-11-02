import { Component, EventEmitter, Input, OnInit, Output, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DemandNotice, PtxAccess } from '../../../../../core/models/ptx.model';
import { PtxService } from '../../../../../core/services/ptx.service';
import { PtxI18nService } from '../../../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../../../core/services/dialog.service';
import { PtxDocumentComponent } from '../../../shared/ptx-document.component';
import { PtxPagerComponent } from '../../../shared/ptx-pager.component';
import { Pager, errorText, periodName, printArea } from '../../../ptx-utils';

/**
 * Prints a ward's bills a page at a time, in door-number order so they can be handed out street by street (PT-20). Each bill
 * is the same bilingual bill with its payment QR code, one to a printed page.
 */
@Component({
  selector: 'app-bill-batch-dialog',
  standalone: true,
  imports: [CommonModule, PtxDocumentComponent, PtxPagerComponent],
  template: `
    <div class="ptx-modal-backdrop" (click)="closed.emit()"></div>
    <section class="ptx-modal" role="dialog" aria-modal="true" aria-label="Print bills">
      <div class="ptx-modal-head">
        <h2>Print bills · {{ periodName(period) }}{{ wardLabel ? ' · ward ' + wardLabel : '' }}</h2>
        <button class="ptx-btn" (click)="closed.emit()">{{ i18n.t('close') }}</button>
      </div>
      <div class="ptx-modal-body">
        <div class="ptx-alert info">
          {{ pager.total() }} bill(s). Choose "Print these" for the bills on this page, then move to the next page. Use "Save as PDF" in the print window to keep a copy.
          Bills are in door-number order. Bill collectors record each delivery in the field app.
        </div>
        <div class="ptx-row no-print">
          <button class="ptx-btn primary" (click)="print()" [disabled]="!items().length">Print these {{ items().length }} bills</button>
        </div>
        <div class="ptx-print-area ptx-batch">
          @for (b of items(); track b.demandNo) { <app-ptx-document kind="DEMAND" [demand]="b" [batch]="true"></app-ptx-document> }
        </div>
        <app-ptx-pager [pager]="pager" (changed)="load()"></app-ptx-pager>
      </div>
    </section>
  `,
})
export class BillBatchDialogComponent implements OnInit {
  @Input({ required: true }) access!: PtxAccess;
  @Input({ required: true }) period!: string;
  @Input() wardId = '';
  @Input() delivery = '';
  @Output() closed = new EventEmitter<void>();
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  i18n = inject(PtxI18nService);
  periodName = periodName;
  pager = new Pager(10);
  items = signal<DemandNotice[]>([]);
  wardLabel = '';

  ngOnInit(): void {
    this.wardLabel = this.access.wards.find((w) => w.wardId === this.wardId)?.wardNumber?.toString() || '';
    this.load();
  }

  load(): void {
    this.ptx.get('/demands/batch', { period: this.period, wardId: this.wardId, delivery: this.delivery, ...this.pager.query() }).subscribe({
      next: (r) => {
        this.items.set(r.items);
        this.pager.total.set(r.total);
      },
      error: (e) => {
        this.items.set([]);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  print(): void {
    printArea();
  }
}
