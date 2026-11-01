import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../shared/components/icon/icon.component';
import { IamSsoService } from '../../../../core/services/iam-sso.service';
import { DialogService } from '../../../../core/services/dialog.service';
import { LoadingService } from '../../../../core/services/loading.service';
import { SSOConfiguration, SSOPolicyPayload } from '../../../../core/models/iam-sso.model';
import { AuthLogsDialogComponent } from '../dialogs/auth-logs-dialog/auth-logs-dialog.component';

@Component({
  selector: 'app-mfa-session-policy',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent, AuthLogsDialogComponent],
  templateUrl: './mfa-session-policy.component.html',
  styleUrl: './mfa-session-policy.component.scss'
})
export class MfaSessionPolicyComponent implements OnInit {
  private ssoService = inject(IamSsoService);
  private dialogs = inject(DialogService);
  private loading = inject(LoadingService);

  readonly config = signal<SSOConfiguration | null>(null);
  readonly isSaving = signal<boolean>(false);
  readonly isLogsDialogOpen = signal<boolean>(false);

  // Policy Form State
  mfaRequired: boolean = true;
  mfaPolicy: string = 'Admins Only';
  sessionIdleTimeoutMins: number = 30;
  maxSessionLifetimeMins: number = 480;
  rememberMe: boolean = true;
  bruteForceProtection: boolean = true;
  maxFailedAttempts: number = 5;
  passwordMinLength: number = 8;
  passwordRequireUppercase: boolean = true;
  passwordRequireLowercase: boolean = true;
  passwordRequireDigits: boolean = true;
  passwordRequireSpecial: boolean = true;
  passwordExpiryDays: number = 90;
  allowedEmailDomainsStr: string = 'gov.in, nic.in, urban.gov.in';
  requireVerifiedEmail: boolean = true;

  ngOnInit(): void {
    this.loadPolicy();
  }

  loadPolicy(): void {
    this.loading.show('Loading MFA & Session Policy...');
    this.ssoService.getSSOConfiguration().subscribe({
      next: (d) => {
        this.loading.hide();
        this.config.set(d);
        this.mfaRequired = d.mfaRequired;
        this.mfaPolicy = d.mfaPolicy || 'Admins Only';
        this.sessionIdleTimeoutMins = d.sessionIdleTimeoutMins || 30;
        this.maxSessionLifetimeMins = d.maxSessionLifetimeMins || 480;
        this.rememberMe = d.rememberMe;
        this.bruteForceProtection = d.bruteForceProtection;
        this.maxFailedAttempts = d.maxFailedAttempts || 5;
        this.passwordMinLength = d.passwordMinLength || 8;
        this.passwordRequireUppercase = d.passwordRequireUppercase;
        this.passwordRequireLowercase = d.passwordRequireLowercase;
        this.passwordRequireDigits = d.passwordRequireDigits;
        this.passwordRequireSpecial = d.passwordRequireSpecial;
        this.passwordExpiryDays = d.passwordExpiryDays || 90;
        this.allowedEmailDomainsStr = (d.allowedEmailDomains || []).join(', ');
        this.requireVerifiedEmail = d.requireVerifiedEmail;
      },
      error: () => {
        this.loading.hide();
        this.dialogs.showToast('Failed to load session policy', 'error');
      }
    });
  }

  savePolicy(): void {
    const domains = this.allowedEmailDomainsStr
      .split(',')
      .map(s => s.trim().toLowerCase())
      .filter(s => s.length > 0);

    const payload: SSOPolicyPayload = {
      enableSso: this.config()?.enableSso ?? true,
      loginMethods: this.config()?.loginMethods ?? ['Password', 'SSO', 'OTP'],
      mfaRequired: this.mfaRequired,
      mfaPolicy: this.mfaPolicy,
      allowedIdentityProviders: this.config()?.allowedIdentityProviders ?? [],
      sessionIdleTimeoutMins: Number(this.sessionIdleTimeoutMins),
      maxSessionLifetimeMins: Number(this.maxSessionLifetimeMins),
      rememberMe: this.rememberMe,
      bruteForceProtection: this.bruteForceProtection,
      maxFailedAttempts: Number(this.maxFailedAttempts),
      passwordMinLength: Number(this.passwordMinLength),
      passwordRequireUppercase: this.passwordRequireUppercase,
      passwordRequireLowercase: this.passwordRequireLowercase,
      passwordRequireDigits: this.passwordRequireDigits,
      passwordRequireSpecial: this.passwordRequireSpecial,
      passwordExpiryDays: Number(this.passwordExpiryDays),
      allowedEmailDomains: domains,
      requireVerifiedEmail: this.requireVerifiedEmail
    };

    this.isSaving.set(true);
    this.loading.show('Saving MFA & Session Policy...');
    this.ssoService.updatePolicies(payload).subscribe({
      next: (d) => {
        this.isSaving.set(false);
        this.loading.hide();
        this.config.set(d);
        this.dialogs.showToast('MFA & Session Policies applied to Keycloak realm', 'success');
      },
      error: () => {
        this.isSaving.set(false);
        this.loading.hide();
        this.dialogs.showToast('Failed to save security policies', 'error');
      }
    });
  }

  resetToDefaults(): void {
    this.mfaRequired = true;
    this.mfaPolicy = 'Admins Only';
    this.sessionIdleTimeoutMins = 30;
    this.maxSessionLifetimeMins = 480;
    this.rememberMe = true;
    this.bruteForceProtection = true;
    this.maxFailedAttempts = 5;
    this.passwordMinLength = 8;
    this.passwordRequireUppercase = true;
    this.passwordRequireLowercase = true;
    this.passwordRequireDigits = true;
    this.passwordRequireSpecial = true;
    this.passwordExpiryDays = 90;
    this.allowedEmailDomainsStr = 'gov.in, nic.in, urban.gov.in';
    this.requireVerifiedEmail = true;
    this.dialogs.showToast('Form reset to standard municipal baseline', 'info');
  }

  openLogsDialog(): void {
    this.isLogsDialogOpen.set(true);
  }

  closeLogsDialog(): void {
    this.isLogsDialogOpen.set(false);
  }
}
