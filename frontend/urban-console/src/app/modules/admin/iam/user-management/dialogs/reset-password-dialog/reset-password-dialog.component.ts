import { Component, Input, Output, EventEmitter, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { IamUserService } from '../../../../../../core/services/iam-user.service';
import { DialogService } from '../../../../../../core/services/dialog.service';
import { LoadingService } from '../../../../../../core/services/loading.service';
import { GlobalUserItem } from '../../../../../../core/models/iam-user.model';

@Component({
  selector: 'app-reset-password-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './reset-password-dialog.component.html',
  styleUrl: './reset-password-dialog.component.scss'
})
export class ResetPasswordDialogComponent implements OnInit {
  @Input({ required: true }) user!: GlobalUserItem;
  @Output() saved = new EventEmitter<void>();
  @Output() closed = new EventEmitter<void>();

  private userService = inject(IamUserService);
  private dialogs = inject(DialogService);
  private loading = inject(LoadingService);

  readonly isSubmitting = signal<boolean>(false);
  readonly showPassword = signal<boolean>(true);
  readonly copied = signal<boolean>(false);

  newPassword = '';

  ngOnInit(): void {
    this.generatePassword();
  }

  private getRandomInt(max: number): number {
    const arr = new Uint32Array(1);
    window.crypto.getRandomValues(arr);
    return arr[0] % max;
  }

  generatePassword(): void {
    const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$%';
    let res = 'Urban@';
    for (let i = 0; i < 6; i++) {
      res += chars.charAt(this.getRandomInt(chars.length));
    }
    this.newPassword = res;
    this.copied.set(false);
    this.dialogs.showToast('Generated strong password', 'info');
  }

  copyPassword(): void {
    if (!this.newPassword) return;
    navigator.clipboard.writeText(this.newPassword).then(() => {
      this.copied.set(true);
      this.dialogs.showToast('Password copied to clipboard', 'success');
      setTimeout(() => this.copied.set(false), 2500);
    });
  }

  onSubmit(): void {
    const pwd = this.newPassword.trim();
    if (!pwd || pwd.length < 6) {
      this.dialogs.showToast('Password must be at least 6 characters long', 'warning');
      return;
    }

    this.isSubmitting.set(true);
    this.loading.show(`Updating credentials for ${this.user.fullName}...`);

    this.userService.resetPassword(this.user.id, pwd).subscribe({
      next: (res) => {
        this.isSubmitting.set(false);
        this.loading.hide();
        if (res.success) {
          this.dialogs.showToast(`Password successfully updated for ${this.user.email}`, 'success');
          this.saved.emit();
        }
      },
      error: (err) => {
        this.isSubmitting.set(false);
        this.loading.hide();
        this.dialogs.showToast(err?.error?.detail || 'Failed to reset password', 'error');
      }
    });
  }

  onCancel(): void {
    this.closed.emit();
  }
}

