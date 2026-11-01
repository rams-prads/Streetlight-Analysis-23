import { Component, Input, Output, EventEmitter, OnChanges, SimpleChanges, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';
import { IconComponent } from '../../../../../shared/components/icon/icon.component';
import { DialogService } from '../../../../../core/services/dialog.service';
import { LoadingService } from '../../../../../core/services/loading.service';
import { TenantManagementService } from '../../../../../core/services/tenant-management.service';
import {
  StateTenant,
  StateTenantCreatePayload,
  MasterState,
  District,
  City,
} from '../../../../../core/models/state-tenant.model';

@Component({
  selector: 'app-state-tenant-form-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './state-tenant-form-dialog.component.html',
  styleUrl: './state-tenant-form-dialog.component.scss',
})
export class StateTenantFormDialogComponent implements OnChanges {
  private tenantService = inject(TenantManagementService);
  private dialogs = inject(DialogService);
  private loadingService = inject(LoadingService);

  @Input() isOpen = false;
  @Input() isEditing = false;
  @Input() selectedTenant: StateTenant | null = null;
  @Input() masterStates: MasterState[] = [];

  @Output() close = new EventEmitter<void>();
  @Output() saveSuccess = new EventEmitter<StateTenant>();

  readonly districts = signal<District[]>([]);
  readonly cities = signal<City[]>([]);
  readonly selectedDistrictId = signal<string>('');
  readonly selectedCityId = signal<string>('');

  readonly countryOptions = ['India'];
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

  formData: StateTenantCreatePayload = this.getInitialFormData();
  selectedLanguages: Set<string> = new Set(['Hindi']);
  emblemFileName = '';
  validationErrors: { [key: string]: string } = {};

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['isOpen'] && this.isOpen) {
      this.initForm();
    }
  }

  getInitialFormData(): StateTenantCreatePayload {
    return {
      stateName: '',
      stateCode: '',
      tenantSlug: '',
      status: 'Active',
      country: 'India',
      timeZone: 'Asia/Kolkata',
      primaryLanguage: 'English',
      additionalLanguages: ['Hindi'],
      officialStateName: '',
      stateEmblemUrl: '',
      stateWebsite: '',
      administrativeEmail: '',
      administrativePhone: '',
      address: '',
      effectiveDate: new Date().toISOString().split('T')[0],
      notes: '',
    };
  }

  initForm(): void {
    this.validationErrors = {};
    if (this.isEditing && this.selectedTenant) {
      const t = this.selectedTenant;
      this.formData = {
        stateName: t.stateName,
        stateCode: t.stateCode,
        tenantSlug: t.tenantSlug,
        status: t.status,
        country: t.country || 'India',
        timeZone: t.timeZone || 'Asia/Kolkata',
        primaryLanguage: t.primaryLanguage || 'English',
        additionalLanguages: t.additionalLanguages || [],
        officialStateName: t.officialStateName || '',
        stateEmblemUrl: t.stateEmblemUrl || '',
        stateWebsite: t.stateWebsite || '',
        administrativeEmail: t.administrativeEmail,
        administrativePhone: t.administrativePhone || '',
        address: t.address || '',
        effectiveDate: t.effectiveDate || '',
        notes: t.notes || '',
      };
      this.selectedLanguages = new Set(t.additionalLanguages || []);
      this.emblemFileName = t.stateEmblemUrl ? 'Current Emblem' : '';
    } else {
      this.formData = this.getInitialFormData();
      this.selectedLanguages = new Set(['Hindi']);
      this.emblemFileName = '';
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

  onMasterStateSelected(code: string): void {
    const selected = this.masterStates.find((s) => s.code === code);
    if (!selected) return;

    this.formData.stateCode = selected.code;
    this.formData.stateName = selected.name;
    this.formData.tenantSlug = selected.defaultSlug;
    this.formData.officialStateName = selected.officialName;
    this.formData.primaryLanguage = selected.primaryLanguage;
    this.formData.additionalLanguages = [...selected.additionalLanguages];
    this.selectedLanguages = new Set(selected.additionalLanguages);

    this.selectedDistrictId.set('');
    this.selectedCityId.set('');
    this.cities.set([]);
    this.loadDistricts(code);
  }

  onDistrictSelected(districtId: string): void {
    this.selectedDistrictId.set(districtId);
    this.selectedCityId.set('');
    this.cities.set([]);
    if (districtId) {
      this.tenantService.getCities(this.formData.stateCode, districtId).subscribe({
        next: (c) => this.cities.set(c),
        error: () => this.cities.set([]),
      });
    }
  }

  onCitySelected(cityId: string): void {
    this.selectedCityId.set(cityId);
  }

  toggleAdditionalLanguage(lang: string): void {
    if (this.selectedLanguages.has(lang)) {
      this.selectedLanguages.delete(lang);
    } else {
      this.selectedLanguages.add(lang);
    }
    this.formData.additionalLanguages = Array.from(this.selectedLanguages);
  }

  onEmblemSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files[0]) {
      const file = input.files[0];
      if (file.size > 2 * 1024 * 1024) {
        this.dialogs.showToast('Emblem logo must be less than 2MB', 'error', 3000);
        return;
      }
      this.emblemFileName = file.name;
      const reader = new FileReader();
      reader.onload = (e: ProgressEvent<FileReader>) => {
        this.formData.stateEmblemUrl = e.target?.result as string;
      };
      reader.readAsDataURL(file);
    }
  }

  clearEmblem(): void {
    this.emblemFileName = '';
    this.formData.stateEmblemUrl = '';
  }

  validateForm(): boolean {
    this.validationErrors = {};
    if (!this.formData.stateName || !this.formData.stateName.trim()) {
      this.validationErrors['stateName'] = 'State or Union Territory name is required.';
    }
    if (!this.formData.stateCode || !this.formData.stateCode.trim()) {
      this.validationErrors['stateCode'] = 'Official state code is mandatory.';
    }
    if (!this.formData.tenantSlug || !this.formData.tenantSlug.trim()) {
      this.validationErrors['tenantSlug'] = 'Portal URL slug is mandatory.';
    }
    if (!this.formData.administrativeEmail || !this.formData.administrativeEmail.trim()) {
      this.validationErrors['administrativeEmail'] = 'Nodal administrative email is required.';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(this.formData.administrativeEmail)) {
      this.validationErrors['administrativeEmail'] = 'Invalid email address format.';
    }
    return Object.keys(this.validationErrors).length === 0;
  }

  saveDraft(): void {
    this.formData.status = 'Draft';
    this.submitForm();
  }

  submitAction(): void {
    this.submitForm();
  }

  private submitForm(): void {
    if (!this.validateForm()) {
      this.dialogs.showToast('Please correct form validation errors.', 'warning', 3000);
      return;
    }

    this.loadingService.setMessage(
      this.isEditing ? 'Updating state tenant...' : 'Creating state tenant...'
    );
    this.loadingService.show();

    if (this.isEditing && this.selectedTenant) {
      this.tenantService
        .updateStateTenant(this.selectedTenant.tenantId, this.formData)
        .pipe(finalize(() => this.loadingService.hide()))
        .subscribe({
          next: (updated) => {
            this.dialogs.showToast(
              `State tenant ${updated.stateName} updated successfully.`,
              'success',
              3000
            );
            this.saveSuccess.emit(updated);
            this.close.emit();
          },
          error: (err) => {
            this.dialogs.showToast(err.error?.detail || 'Failed to update tenant.', 'error', 3000);
          },
        });
    } else {
      this.tenantService
        .createStateTenant(this.formData)
        .pipe(finalize(() => this.loadingService.hide()))
        .subscribe({
          next: (created) => {
            this.dialogs.showToast(
              `State tenant ${created.stateName} (${created.stateCode}) created successfully!`,
              'success',
              3500
            );
            this.saveSuccess.emit(created);
            this.close.emit();
          },
          error: (err) => {
            this.dialogs.showToast(err.error?.detail || 'Failed to create tenant.', 'error', 4000);
          },
        });
    }
  }

  onCancel(): void {
    this.close.emit();
  }
}
