import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';
import { IconComponent } from '../../../../shared/components/icon/icon.component';
import { DialogService } from '../../../../core/services/dialog.service';
import { LoadingService } from '../../../../core/services/loading.service';
import { IamSsoService } from '../../../../core/services/iam-sso.service';
import {
  SSOConfiguration,
  SSOConnectionPayload,
  SSOPolicyPayload,
  ConnectionTestResult
} from '../../../../core/models/iam-sso.model';
import { AuthLogsDialogComponent } from '../dialogs/auth-logs-dialog/auth-logs-dialog.component';

@Component({
  selector: 'app-sso-config',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    IconComponent,
    AuthLogsDialogComponent
  ],
  templateUrl: './sso-config.component.html',
  styleUrl: './sso-config.component.scss'
})
export class SsoConfigComponent implements OnInit {
  private iamService = inject(IamSsoService);
  private dialogs = inject(DialogService);
  public loadingService = inject(LoadingService);

  readonly isLoading = signal(false);
  readonly isTestingConnection = signal(false);
  readonly isSaving = signal(false);

  // Configuration signal
  readonly ssoConfig = signal<SSOConfiguration | null>(null);

  // Connection form state
  connectionForm: SSOConnectionPayload = {
    providerName: 'SUVIDHA Central Keycloak Identity',
    providerType: 'Keycloak',
    keycloakBaseUrl: 'http://localhost:8080',
    keycloakRealm: 'urban-suvidha',
    clientId: 'urban-console',
    clientSecret: '',
    redirectUri: 'http://localhost:4200/auth/callback',
    postLogoutRedirectUri: 'http://localhost:4200/login',
    oidcScopes: ['openid', 'profile', 'email', 'roles']
  };

  // Policy form state
  policyForm: SSOPolicyPayload = {
    enableSso: true,
    loginMethods: ['Password', 'SSO', 'OTP'],
    mfaRequired: false,
    mfaPolicy: 'Admins Only',
    allowedIdentityProviders: [],
    sessionIdleTimeoutMins: 30,
    maxSessionLifetimeMins: 480,
    rememberMe: true,
    bruteForceProtection: true,
    maxFailedAttempts: 5,
    passwordMinLength: 8,
    passwordRequireUppercase: true,
    passwordRequireLowercase: true,
    passwordRequireDigits: true,
    passwordRequireSpecial: true,
    passwordExpiryDays: 90,
    allowedEmailDomains: ['gov.in', 'nic.in', 'urban.gov.in'],
    requireVerifiedEmail: true
  };

  newScopeInput = '';
  newDomainInput = '';

  readonly availableLoginMethods = ['Password', 'SSO', 'OTP', 'Passwordless (WebAuthn)'];
  readonly providerTypeOptions = ['Keycloak', 'Generic OIDC', 'SAML 2.0'];

  // Dialog signals
  readonly isLogsDialogOpen = signal(false);

  ngOnInit(): void {
    this.loadAll();
  }

  loadAll(): void {
    this.isLoading.set(true);
    this.loadingService.setMessage('Loading SSO & Identity Configuration...');
    this.loadingService.show();

    this.iamService.getSSOConfiguration().pipe(
      finalize(() => {
        this.isLoading.set(false);
        this.loadingService.hide();
      })
    ).subscribe({
      next: (cfg) => {
        this.ssoConfig.set(cfg);
        this.connectionForm = {
          providerName: cfg.providerName,
          providerType: cfg.providerType,
          keycloakBaseUrl: cfg.keycloakBaseUrl,
          keycloakRealm: cfg.keycloakRealm,
          clientId: cfg.clientId,
          clientSecret: '',
          redirectUri: cfg.redirectUri,
          postLogoutRedirectUri: cfg.postLogoutRedirectUri || '',
          oidcScopes: [...cfg.oidcScopes]
        };
        this.policyForm = {
          enableSso: cfg.enableSso,
          loginMethods: [...cfg.loginMethods],
          mfaRequired: cfg.mfaRequired,
          mfaPolicy: cfg.mfaPolicy,
          allowedIdentityProviders: [...(cfg.allowedIdentityProviders || [])],
          sessionIdleTimeoutMins: cfg.sessionIdleTimeoutMins,
          maxSessionLifetimeMins: cfg.maxSessionLifetimeMins,
          rememberMe: cfg.rememberMe,
          bruteForceProtection: cfg.bruteForceProtection,
          maxFailedAttempts: cfg.maxFailedAttempts,
          passwordMinLength: cfg.passwordMinLength,
          passwordRequireUppercase: cfg.passwordRequireUppercase,
          passwordRequireLowercase: cfg.passwordRequireLowercase,
          passwordRequireDigits: cfg.passwordRequireDigits,
          passwordRequireSpecial: cfg.passwordRequireSpecial,
          passwordExpiryDays: cfg.passwordExpiryDays,
          allowedEmailDomains: [...cfg.allowedEmailDomains],
          requireVerifiedEmail: cfg.requireVerifiedEmail
        };
      },
      error: (err: any) => {
        this.dialogs.showToast(err.error?.detail || 'Failed to load SSO configuration', 'error', 3000);
      }
    });
  }

  // --- Scope Tag Management ---
  addScope(): void {
    const s = this.newScopeInput.trim().toLowerCase();
    if (s && !this.connectionForm.oidcScopes.includes(s)) {
      this.connectionForm.oidcScopes.push(s);
      this.newScopeInput = '';
    }
  }

  removeScope(s: string): void {
    this.connectionForm.oidcScopes = this.connectionForm.oidcScopes.filter(item => item !== s);
  }

  // --- Domain Tag Management ---
  addDomain(): void {
    let d = this.newDomainInput.trim().toLowerCase();
    if (d.startsWith('@')) d = d.substring(1);
    if (d && !this.policyForm.allowedEmailDomains.includes(d)) {
      this.policyForm.allowedEmailDomains.push(d);
      this.newDomainInput = '';
    }
  }

  removeDomain(d: string): void {
    this.policyForm.allowedEmailDomains = this.policyForm.allowedEmailDomains.filter(item => item !== d);
  }

  toggleLoginMethod(m: string): void {
    const idx = this.policyForm.loginMethods.indexOf(m);
    if (idx > -1) {
      if (this.policyForm.loginMethods.length > 1) {
        this.policyForm.loginMethods.splice(idx, 1);
      } else {
        this.dialogs.showToast('At least one authentication method must remain enabled', 'warning', 2500);
      }
    } else {
      this.policyForm.loginMethods.push(m);
    }
  }

  // --- Test Connection ---
  testConnection(): void {
    this.isTestingConnection.set(true);
    this.loadingService.setMessage('Probing Keycloak Discovery Endpoint...');
    this.loadingService.show();

    this.iamService.testConnection().pipe(
      finalize(() => {
        this.isTestingConnection.set(false);
        this.loadingService.hide();
      })
    ).subscribe({
      next: (res: ConnectionTestResult) => {
        if (res.success) {
          this.dialogs.showToast(`Connection Verified: ${res.message}`, 'success', 3500);
        } else {
          this.dialogs.showToast(`Connection Warning: ${res.message}`, 'warning', 4000);
        }
        if (this.ssoConfig()) {
          this.ssoConfig.set({
            ...this.ssoConfig()!,
            connectionStatus: res.status as any,
            lastConnectionTest: res.testedAt
          });
        }
      },
      error: (err: any) => {
        this.dialogs.showToast(`Connection Test Failed: ${err.error?.detail || err.message}`, 'error', 4000);
      }
    });
  }

  // --- Save All Configuration ---
  saveAll(): void {
    this.isSaving.set(true);
    this.loadingService.setMessage('Saving Keycloak parameters and SSO policies...');
    this.loadingService.show();

    this.iamService.updateConnection(this.connectionForm).subscribe({
      next: (cfg) => {
        this.iamService.updatePolicies(this.policyForm).pipe(
          finalize(() => {
            this.isSaving.set(false);
            this.loadingService.hide();
          })
        ).subscribe({
          next: (updatedCfg) => {
            this.ssoConfig.set(updatedCfg);
            this.dialogs.showToast('SSO & Keycloak configuration saved successfully', 'success', 3000);
          },
          error: (err: any) => {
            this.dialogs.showToast(err.error?.detail || 'Failed to save policies', 'error', 3000);
          }
        });
      },
      error: (err: any) => {
        this.isSaving.set(false);
        this.loadingService.hide();
        this.dialogs.showToast(err.error?.detail || 'Failed to save connection parameters', 'error', 3000);
      }
    });
  }

  // --- Auth Logs Dialog ---
  openLogsDialog(): void {
    this.isLogsDialogOpen.set(true);
  }

  closeLogsDialog(): void {
    this.isLogsDialogOpen.set(false);
  }
}
