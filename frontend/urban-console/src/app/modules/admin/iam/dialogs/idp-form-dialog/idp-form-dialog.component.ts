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
import { LoadingService } from '../../../../../core/services/loading.service';
import { IamSsoService } from '../../../../../core/services/iam-sso.service';
import {
  IdentityProvider,
  IdentityProviderPayload
} from '../../../../../core/models/iam-sso.model';

@Component({
  selector: 'app-idp-form-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './idp-form-dialog.component.html',
  styleUrl: './idp-form-dialog.component.scss'
})
export class IdpFormDialogComponent implements OnChanges {
  private iamService = inject(IamSsoService);
  private dialogs = inject(DialogService);
  private loadingService = inject(LoadingService);

  @Input() isOpen = false;
  @Input() isEditing = false;
  @Input() selectedIdp: IdentityProvider | null = null;

  @Output() close = new EventEmitter<void>();
  @Output() saveSuccess = new EventEmitter<IdentityProvider>();

  readonly protocolOptions = ['OIDC', 'SAML'];
  readonly linkingPolicyOptions = [
    'Auto-link by Email',
    'Require Manual Verification',
    'Disabled'
  ];

  formData: IdentityProviderPayload = {
    name: '',
    protocol: 'OIDC',
    issuerUrl: '',
    clientId: '',
    clientSecret: '',
    metadataUrl: '',
    claimMapping: { sub: 'sub', email: 'email', name: 'name' },
    userLinkingPolicy: 'Auto-link by Email',
    isActive: true
  };

  claimSub = 'sub';
  claimEmail = 'email';
  claimName = 'name';
  claimPhone = 'mobile';

  readonly isSaving = signal(false);
  validationErrors: Record<string, string> = {};

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['isOpen'] && this.isOpen) {
      this.resetForm();
    }
  }

  private resetForm(): void {
    this.validationErrors = {};
    if (this.isEditing && this.selectedIdp) {
      this.formData = {
        name: this.selectedIdp.name,
        protocol: this.selectedIdp.protocol,
        issuerUrl: this.selectedIdp.issuerUrl,
        clientId: this.selectedIdp.clientId || '',
        clientSecret: '',
        metadataUrl: this.selectedIdp.metadataUrl || '',
        claimMapping: { ...this.selectedIdp.claimMapping },
        userLinkingPolicy: this.selectedIdp.userLinkingPolicy,
        isActive: this.selectedIdp.isActive
      };
      this.claimSub = this.formData.claimMapping?.['sub'] || 'sub';
      this.claimEmail = this.formData.claimMapping?.['email'] || 'email';
      this.claimName = this.formData.claimMapping?.['name'] || 'name';
      this.claimPhone = this.formData.claimMapping?.['phone'] || 'mobile';
    } else {
      this.formData = {
        name: '',
        protocol: 'OIDC',
        issuerUrl: '',
        clientId: '',
        clientSecret: '',
        metadataUrl: '',
        claimMapping: { sub: 'sub', email: 'email', name: 'name' },
        userLinkingPolicy: 'Auto-link by Email',
        isActive: true
      };
      this.claimSub = 'sub';
      this.claimEmail = 'email';
      this.claimName = 'name';
      this.claimPhone = 'mobile';
    }
  }

  validate(): boolean {
    this.validationErrors = {};
    if (!this.formData.name.trim()) {
      this.validationErrors['name'] = 'Identity provider name is required';
    }
    if (!this.formData.issuerUrl.trim()) {
      this.validationErrors['issuerUrl'] = 'Issuer or Entity ID URL is required';
    } else if (!this.formData.issuerUrl.startsWith('http://') && !this.formData.issuerUrl.startsWith('https://')) {
      this.validationErrors['issuerUrl'] = 'Must be a valid HTTP/HTTPS URL';
    }
    if (!this.claimSub.trim()) {
      this.validationErrors['claimSub'] = 'Subject claim mapping is required';
    }
    if (!this.claimEmail.trim()) {
      this.validationErrors['claimEmail'] = 'Email claim mapping is required';
    }
    return Object.keys(this.validationErrors).length === 0;
  }

  save(): void {
    if (!this.validate()) {
      this.dialogs.showToast('Please correct form errors before saving', 'warning', 3000);
      return;
    }

    this.isSaving.set(true);
    this.loadingService.setMessage(this.isEditing ? 'Updating provider...' : 'Registering identity provider...');
    this.loadingService.show();

    this.formData.claimMapping = {
      sub: this.claimSub.trim(),
      email: this.claimEmail.trim(),
      name: this.claimName.trim(),
      phone: this.claimPhone.trim()
    };

    if (this.isEditing && this.selectedIdp) {
      this.iamService.updateIdentityProvider(this.selectedIdp.id, this.formData).pipe(
        finalize(() => {
          this.isSaving.set(false);
          this.loadingService.hide();
        })
      ).subscribe({
        next: (updated) => {
          this.dialogs.showToast(`Provider '${updated.name}' updated successfully`, 'success', 3000);
          this.saveSuccess.emit(updated);
        },
        error: (err: any) => {
          this.dialogs.showToast(err.error?.detail || 'Failed to update provider', 'error', 3500);
        }
      });
    } else {
      this.iamService.createIdentityProvider(this.formData).pipe(
        finalize(() => {
          this.isSaving.set(false);
          this.loadingService.hide();
        })
      ).subscribe({
        next: (created) => {
          this.dialogs.showToast(`Provider '${created.name}' registered successfully`, 'success', 3000);
          this.saveSuccess.emit(created);
        },
        error: (err: any) => {
          this.dialogs.showToast(err.error?.detail || 'Failed to register provider', 'error', 3500);
        }
      });
    }
  }

  onCancel(): void {
    this.close.emit();
  }
}
