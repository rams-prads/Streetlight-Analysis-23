import { Component, Input, Output, EventEmitter, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { StateSubscription } from '../../../../../../core/models/subscription.model';

@Component({
  selector: 'app-revoke-subscription-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './revoke-subscription-dialog.component.html',
  styleUrl: './revoke-subscription-dialog.component.scss'
})
export class RevokeSubscriptionDialogComponent {
  @Input() subscription: StateSubscription | null = null;
  @Output() confirmed = new EventEmitter<{ reason: string; approvalReference?: string }>();
  @Output() closed = new EventEmitter<void>();

  reason: string = '';
  approvalReference: string = '';
  confirmAcknowledge: boolean = false;
  readonly isSubmitting = signal<boolean>(false);

  onCancel(): void {
    this.closed.emit();
  }

  onSubmit(): void {
    if (!this.reason.trim() || this.reason.trim().length < 5) {
      return;
    }
    if (!this.confirmAcknowledge) {
      return;
    }
    this.isSubmitting.set(true);
    this.confirmed.emit({
      reason: this.reason.trim(),
      approvalReference: this.approvalReference.trim() || undefined
    });
  }
}

