import { Component, Input, Output, EventEmitter, OnChanges, SimpleChanges, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { finalize } from 'rxjs';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { DialogService } from '../../../../../../core/services/dialog.service';
import { LoadingService } from '../../../../../../core/services/loading.service';
import { ModuleCatalogueService } from '../../../../../../core/services/module-catalogue.service';
import { ModuleChangeHistoryItem } from '../../../../../../core/models/module-catalogue.model';

@Component({
  selector: 'app-catalogue-history-dialog',
  standalone: true,
  imports: [CommonModule, IconComponent],
  templateUrl: './catalogue-history-dialog.component.html',
  styleUrl: './catalogue-history-dialog.component.scss'
})
export class CatalogueHistoryDialogComponent implements OnChanges {
  private moduleService = inject(ModuleCatalogueService);
  private dialogs = inject(DialogService);
  private loadingService = inject(LoadingService);

  @Input() isOpen = false;
  @Input() entityCode = '';

  @Output() close = new EventEmitter<void>();

  readonly logs = signal<ModuleChangeHistoryItem[]>([]);
  readonly isLoading = signal(false);

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['isOpen'] && this.isOpen) {
      this.loadHistory();
    }
  }

  loadHistory(): void {
    this.isLoading.set(true);
    this.moduleService.getAuditHistory(this.entityCode).pipe(
      finalize(() => this.isLoading.set(false))
    ).subscribe({
      next: (data: ModuleChangeHistoryItem[]) => this.logs.set(data),
      error: () => this.dialogs.showToast('Failed to load catalogue change history', 'error', 3000)
    });
  }

  exportJson(): void {
    this.moduleService.exportCatalogue().subscribe({
      next: (data: any) => {
        const jsonStr = JSON.stringify(data, null, 2);
        const blob = new Blob([jsonStr], { type: 'application/json' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `suvidha-module-catalogue-${new Date().toISOString().split('T')[0]}.json`;
        a.click();
        window.URL.revokeObjectURL(url);
        this.dialogs.showToast('Catalogue JSON exported successfully', 'success', 2500);
      },
      error: () => this.dialogs.showToast('Export failed', 'error', 3000)
    });
  }

  onClose(): void {
    this.close.emit();
  }
}
