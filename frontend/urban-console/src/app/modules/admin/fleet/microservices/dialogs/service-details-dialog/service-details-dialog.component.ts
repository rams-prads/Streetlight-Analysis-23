import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { MicroserviceRegistryItem } from '../../../../../../core/models/fleet.model';

@Component({
  selector: 'app-service-details-dialog',
  standalone: true,
  imports: [CommonModule, IconComponent],
  templateUrl: './service-details-dialog.component.html',
  styleUrls: ['./service-details-dialog.component.scss'],
})
export class ServiceDetailsDialogComponent {
  @Input() service: MicroserviceRegistryItem | null = null;
  @Output() close = new EventEmitter<void>();

  onClose(): void {
    this.close.emit();
  }
}

