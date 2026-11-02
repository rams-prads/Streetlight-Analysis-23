import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { TenantIsolationTestRun } from '../../../../../../core/models/tenant-security.model';

@Component({
  selector: 'app-test-details-dialog',
  standalone: true,
  imports: [CommonModule, IconComponent],
  templateUrl: './test-details-dialog.component.html',
  styleUrls: ['./test-details-dialog.component.scss']
})
export class TestDetailsDialogComponent {
  @Input({ required: true }) testRun!: TenantIsolationTestRun;
  @Output() close = new EventEmitter<void>();
  @Output() runAgain = new EventEmitter<TenantIsolationTestRun>();

  onRunAgain() {
    this.runAgain.emit(this.testRun);
  }

  onClose() {
    this.close.emit();
  }
}

