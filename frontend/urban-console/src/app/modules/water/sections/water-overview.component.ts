import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { WaterAccess } from '../../../core/models/water.model';
import { WaterService } from '../../../core/services/water.service';
import { WaterI18nService } from '../../../core/services/water-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { dmy, errorText } from '../water-utils';

/** Commissioner's dashboard: today's collection, year-to-date against target, weakest wards, complaints past SLA (WB-64). */
@Component({
  selector: 'app-water-overview',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './water-overview.component.html',
})
export class WaterOverviewComponent implements OnInit {
  @Input() access!: WaterAccess;
  private water = inject(WaterService);
  private dialog = inject(DialogService);
  i18n = inject(WaterI18nService);
  data = signal<any>(null);
  loading = signal(false);
  dmy = dmy;

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.water.get('/dashboard/commissioner').subscribe({
      next: (d) => {
        this.data.set(d);
        this.loading.set(false);
      },
      error: (e) => {
        this.loading.set(false);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  statusKeys(d: any): string[] {
    return Object.keys(d?.connectionsByStatus || {});
  }
}
