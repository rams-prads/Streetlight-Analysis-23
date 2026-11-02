import { Component, Input, Output, EventEmitter, OnChanges, SimpleChanges, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';
import { IconComponent } from '../../../../../shared/components/icon/icon.component';
import { DialogService } from '../../../../../core/services/dialog.service';
import { LoadingService } from '../../../../../core/services/loading.service';
import { TenantManagementService } from '../../../../../core/services/tenant-management.service';
import { UlbManagementService } from '../../../../../core/services/ulb-management.service';
import { MasterState, District } from '../../../../../core/models/state-tenant.model';
import {
  UlbTenant,
  UlbTenantCreatePayload,
  UlbTenantUpdatePayload,
} from '../../../../../core/models/ulb-tenant.model';

@Component({
  selector: 'app-ulb-form-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './ulb-form-dialog.component.html',
  styleUrl: './ulb-form-dialog.component.scss',
})
export class UlbFormDialogComponent implements OnChanges {
  private ulbService = inject(UlbManagementService);
  private tenantService = inject(TenantManagementService);
  private dialogs = inject(DialogService);
  private loadingService = inject(LoadingService);

  @Input() isOpen = false;
  @Input() isEditing = false;
  @Input() selectedUlb: UlbTenant | null = null;
  @Input() masterStates: MasterState[] = [];

  @Output() close = new EventEmitter<void>();
  @Output() saveSuccess = new EventEmitter<UlbTenant>();

  readonly districts = signal<District[]>([]);

  readonly ulbTypeOptions = [
    'Municipal Corporation',
    'Municipality',
    'Nagar Panchayat',
    'Town Panchayat',
    'Cantonment Board',
    'Urban Development Authority',
  ];
  readonly gradeOptions = [
    'Selection Grade',
    'Special Grade',
    'Grade I',
    'Grade II',
    'Grade III',
    'Not Applicable',
  ];
  readonly timeZoneOptions = ['Asia/Kolkata', 'UTC'];
  readonly languageOptions = [
    'English',
    'Hindi',
    'Telugu',
    'Marathi',
    'Kannada',
    'Tamil',
    'Bengali',
    'Gujarati',
    'Odia',
    'Malayalam',
    'Punjabi',
    'Urdu',
  ];

  formData: UlbTenantCreatePayload = this.getInitialFormData();
  validationErrors: { [key: string]: string } = {};

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['isOpen'] && this.isOpen) {
      this.initForm();
    }
  }

  getInitialFormData(): UlbTenantCreatePayload {
    return {
      tenantId: '',
      name: '',
      parentStateTenantId: '',
      stateCode: 'TG',
      ulbCode: '',
      tenantSlug: '',
      ulbType: 'Municipal Corporation',
      administrativeGrade: 'Special Grade',
      district: '',
      officialWebsite: '',
      officialEmail: '',
      contactPhone: '',
      officeAddress: '',
      timeZone: 'Asia/Kolkata',
      primaryLanguage: 'English',
      status: 'Active',
      enableZones: false,
      enableWards: true,
      effectiveDate: new Date().toISOString().split('T')[0],
    };
  }

  initForm(): void {
    this.validationErrors = {};
    if (this.isEditing && this.selectedUlb) {
      this.formData = {
        tenantId: this.selectedUlb.tenantId,
        name: this.selectedUlb.name,
        parentStateTenantId: this.selectedUlb.parentStateTenantId || '',
        stateCode: this.selectedUlb.stateCode,
        ulbCode: this.selectedUlb.ulbCode,
        tenantSlug: this.selectedUlb.tenantSlug,
        ulbType: this.selectedUlb.ulbType,
        administrativeGrade: this.selectedUlb.administrativeGrade || '',
        district: this.selectedUlb.district,
        officialWebsite: this.selectedUlb.officialWebsite || '',
        officialEmail: this.selectedUlb.officialEmail || '',
        contactPhone: this.selectedUlb.contactPhone || '',
        officeAddress: this.selectedUlb.officeAddress || '',
        timeZone: this.selectedUlb.timeZone,
        primaryLanguage: this.selectedUlb.primaryLanguage,
        status: this.selectedUlb.status,
        enableZones: this.selectedUlb.enableZones,
        enableWards: this.selectedUlb.enableWards,
        effectiveDate: this.selectedUlb.effectiveDate || '',
      };
    } else {
      this.formData = this.getInitialFormData();
    }

    if (this.formData.stateCode) {
      this.loadDistricts(this.formData.stateCode);
    }
  }

  loadDistricts(stateCode: string): void {
    this.tenantService.getDistricts(stateCode).subscribe({
      next: (d) => this.districts.set(d),
      error: () => this.districts.set([]),
    });
  }

  onStateSelected(stateCode: string): void {
    this.formData.stateCode = stateCode;
    this.loadDistricts(stateCode);
  }

  onNameChange(name: string): void {
    this.formData.name = name;
    if (!this.isEditing) {
      const codeSuggestion = name
        .split(' ')
        .map((w) => w[0])
        .join('')
        .toUpperCase()
        .slice(0, 6);
      if (!this.formData.ulbCode || this.formData.ulbCode.length < 3) {
        this.formData.ulbCode = codeSuggestion;
      }
      const slugSuggestion = name
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-|-$/g, '');
      if (!this.formData.tenantSlug) {
        this.formData.tenantSlug = slugSuggestion;
      }
    }
  }

  validateForm(): boolean {
    this.validationErrors = {};

    if (!this.formData.name || !this.formData.name.trim()) {
      this.validationErrors['name'] = 'ULB Name is mandatory.';
    }
    if (!this.formData.ulbCode || !this.formData.ulbCode.trim()) {
      this.validationErrors['ulbCode'] = 'ULB Code is required.';
    }
    if (!this.formData.tenantSlug || !this.formData.tenantSlug.trim()) {
      this.validationErrors['tenantSlug'] = 'Tenant Slug is required.';
    }
    if (!this.formData.district || !this.formData.district.trim()) {
      this.validationErrors['district'] = 'District is mandatory.';
    }
    if (!this.formData.officialEmail || !this.formData.officialEmail.trim()) {
      this.validationErrors['officialEmail'] = 'Official email is required.';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(this.formData.officialEmail)) {
      this.validationErrors['officialEmail'] = 'Invalid email address format.';
    }

    return Object.keys(this.validationErrors).length === 0;
  }

  onSave(): void {
    if (!this.validateForm()) {
      this.dialogs.showToast('Please resolve the errors highlighted below.', 'error', 3000);
      return;
    }

    this.loadingService.setMessage(
      this.isEditing ? 'Updating ULB configuration...' : 'Provisioning new ULB...'
    );
    this.loadingService.show();

    if (this.isEditing && this.selectedUlb) {
      const updatePayload: UlbTenantUpdatePayload = {
        name: this.formData.name,
        parentStateTenantId: this.formData.parentStateTenantId,
        stateCode: this.formData.stateCode,
        ulbCode: this.formData.ulbCode,
        tenantSlug: this.formData.tenantSlug,
        ulbType: this.formData.ulbType,
        administrativeGrade: this.formData.administrativeGrade,
        district: this.formData.district,
        officialWebsite: this.formData.officialWebsite,
        officialEmail: this.formData.officialEmail,
        contactPhone: this.formData.contactPhone,
        officeAddress: this.formData.officeAddress,
        timeZone: this.formData.timeZone,
        primaryLanguage: this.formData.primaryLanguage,
        status: this.formData.status,
        enableZones: this.formData.enableZones,
        enableWards: this.formData.enableWards,
        effectiveDate: this.formData.effectiveDate,
      };

      this.ulbService
        .updateUlb(this.selectedUlb.tenantId, updatePayload)
        .pipe(finalize(() => this.loadingService.hide()))
        .subscribe({
          next: (updated) => {
            this.dialogs.showToast(`ULB ${updated.name} updated successfully.`, 'success', 2500);
            this.saveSuccess.emit(updated);
            this.close.emit();
          },
          error: (err) => {
            this.dialogs.showToast(
              err.error?.detail || 'Failed to update ULB configuration.',
              'error',
              3500
            );
          },
        });
    } else {
      this.ulbService
        .createUlb(this.formData)
        .pipe(finalize(() => this.loadingService.hide()))
        .subscribe({
          next: (created) => {
            this.dialogs.showToast(
              `ULB ${created.name} (${created.ulbCode}) created successfully!`,
              'success',
              3000
            );
            this.saveSuccess.emit(created);
            this.close.emit();
          },
          error: (err) => {
            this.dialogs.showToast(
              err.error?.detail || 'Failed to create ULB tenant.',
              'error',
              3500
            );
          },
        });
    }
  }

  onCancel(): void {
    this.close.emit();
  }
}
