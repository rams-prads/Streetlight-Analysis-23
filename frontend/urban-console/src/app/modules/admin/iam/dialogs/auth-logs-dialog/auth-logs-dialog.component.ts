import {
  Component,
  Input,
  Output,
  EventEmitter,
  OnChanges,
  SimpleChanges,
  inject,
  signal
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';
import { IconComponent } from '../../../../../shared/components/icon/icon.component';
import { DialogService } from '../../../../../core/services/dialog.service';
import { IamSsoService } from '../../../../../core/services/iam-sso.service';
import { AuthenticationAuditLog } from '../../../../../core/models/iam-sso.model';

@Component({
  selector: 'app-auth-logs-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './auth-logs-dialog.component.html',
  styleUrl: './auth-logs-dialog.component.scss'
})
export class AuthLogsDialogComponent implements OnChanges {
  private iamService = inject(IamSsoService);
  private dialogs = inject(DialogService);

  @Input() isOpen = false;
  @Output() close = new EventEmitter<void>();

  readonly logs = signal<AuthenticationAuditLog[]>([]);
  readonly isLoading = signal(false);

  // Filters
  readonly selectedEventFilter = signal('ALL');
  readonly selectedStatusFilter = signal('ALL');
  readonly usernameSearch = signal('');

  readonly eventOptions = [
    'ALL',
    'LOGIN_SUCCESS',
    'LOGIN_FAILURE',
    'MFA_CHALLENGE',
    'SSO_REDIRECT',
    'FEDERATION_TOKEN_EXCHANGED',
    'SSO_CONNECTION_TEST',
    'SSO_CONNECTION_UPDATED',
    'SSO_POLICIES_UPDATED',
    'IDP_FEDERATION_CREATED',
    'IDP_FEDERATION_UPDATED',
    'IDP_STATUS_TOGGLED'
  ];

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['isOpen'] && this.isOpen) {
      this.loadLogs();
    }
  }

  loadLogs(): void {
    this.isLoading.set(true);
    this.iamService.getAuditLogs(
      this.selectedEventFilter(),
      this.selectedStatusFilter(),
      this.usernameSearch()
    ).pipe(
      finalize(() => this.isLoading.set(false))
    ).subscribe({
      next: (data: AuthenticationAuditLog[]) => this.logs.set(data),
      error: () => this.dialogs.showToast('Failed to load authentication audit logs', 'error', 3000)
    });
  }

  onFilterChange(): void {
    this.loadLogs();
  }

  onClose(): void {
    this.close.emit();
  }
}
