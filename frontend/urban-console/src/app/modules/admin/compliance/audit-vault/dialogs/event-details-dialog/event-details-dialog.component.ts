import { Component, Input, Output, EventEmitter, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { ImmutableAuditEvent } from '../../../../../../core/models/audit-vault.model';
import { DialogService } from '../../../../../../core/services/dialog.service';

@Component({
  selector: 'app-event-details-dialog',
  standalone: true,
  imports: [CommonModule, IconComponent],
  templateUrl: './event-details-dialog.component.html',
  styleUrl: './event-details-dialog.component.scss'
})
export class EventDetailsDialogComponent {
  @Input({ required: true }) event!: ImmutableAuditEvent;
  @Output() closed = new EventEmitter<void>();

  private dialogs = inject(DialogService);

  onCancel(): void {
    this.closed.emit();
  }

  copyHash(): void {
    if (this.event && this.event.eventHash) {
      navigator.clipboard.writeText(this.event.eventHash);
      this.dialogs.showToast('Event hash copied to clipboard', 'info');
    }
  }
}

