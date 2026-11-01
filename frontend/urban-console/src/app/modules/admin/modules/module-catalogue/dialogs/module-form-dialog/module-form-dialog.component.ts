import {
  Component,
  Input,
  Output,
  EventEmitter,
  OnChanges,
  SimpleChanges,
  inject,
  signal,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { DialogService } from '../../../../../../core/services/dialog.service';
import { LoadingService } from '../../../../../../core/services/loading.service';
import { ModuleCatalogueService } from '../../../../../../core/services/module-catalogue.service';
import {
  ModuleCatalogueItem,
  ModuleCreatePayload,
} from '../../../../../../core/models/module-catalogue.model';

@Component({
  selector: 'app-module-form-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './module-form-dialog.component.html',
  styleUrl: './module-form-dialog.component.scss',
})
export class ModuleFormDialogComponent implements OnChanges {
  private moduleService = inject(ModuleCatalogueService);
  private dialogs = inject(DialogService);
  private loadingService = inject(LoadingService);

  @Input() isOpen = false;
  @Input() isEditing = false;
  @Input() selectedModule: ModuleCatalogueItem | null = null;
  @Input() existingModules: ModuleCatalogueItem[] = [];

  @Output() close = new EventEmitter<void>();
  @Output() saveSuccess = new EventEmitter<ModuleCatalogueItem>();

  readonly categoryOptions = [
    'Revenue & Billing',
    'Finance & Administration',
    'Planning & Regulation',
    'Infrastructure & Field Operations',
    'Citizen Engagement & Welfare',
  ];

  readonly statusOptions = ['Draft', 'Published', 'Deprecated'];

  readonly iconOptions = [
    'ri-apps-2-line',
    'ri-money-dollar-circle-line',
    'ri-drop-line',
    'ri-customer-service-2-line',
    'ri-bank-line',
    'ri-store-2-line',
    'ri-exchange-dollar-line',
    'ri-delete-bin-line',
    'ri-team-line',
    'ri-folder-open-line',
    'ri-hammer-line',
    'ri-building-4-line',
    'ri-lightbulb-line',
    'ri-compass-3-line',
    'ri-plant-line',
    'ri-hotel-line',
    'ri-scales-3-line',
    'ri-archive-line',
    'ri-fire-line',
    'ri-hand-heart-line',
  ];

  formData: ModuleCreatePayload = this.getInitialForm();
  selectedDependencies = new Set<string>();
  validationErrors: Record<string, string> = {};
  readonly isSaving = signal(false);

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['isOpen'] && this.isOpen) {
      this.initForm();
    }
  }

  private initForm(): void {
    this.validationErrors = {};
    if (this.isEditing && this.selectedModule) {
      const m = this.selectedModule;
      this.formData = {
        moduleId: m.moduleId,
        name: m.name,
        code: m.code,
        description: m.description,
        category: m.category,
        icon: m.icon || 'ri-apps-2-line',
        displayOrder: m.displayOrder || 1,
        moduleVersion: m.moduleVersion || '1.0.0',
        status: m.status || 'Published',
        dependencies: m.dependencies || [],
        minimumPlatformVersion: m.minimumPlatformVersion || '1.0.0',
        documentationUrl: m.documentationUrl || '',
        effectiveFrom: m.effectiveFrom || '',
      };
      this.selectedDependencies = new Set(m.dependencies || []);
    } else {
      this.formData = this.getInitialForm();
      this.selectedDependencies = new Set();
    }
  }

  private getInitialForm(): ModuleCreatePayload {
    return {
      moduleId: '',
      name: '',
      code: '',
      description: '',
      category: 'Revenue & Billing',
      icon: 'ri-apps-2-line',
      displayOrder: this.existingModules.length + 1,
      moduleVersion: '1.0.0',
      status: 'Published',
      dependencies: [],
      minimumPlatformVersion: '1.0.0',
      documentationUrl: '',
      effectiveFrom: new Date().toISOString().split('T')[0],
    };
  }

  onCodeChange(val: string): void {
    this.formData.code = val.toUpperCase().trim();
    if (this.validationErrors['code']) delete this.validationErrors['code'];
  }

  toggleDependency(code: string): void {
    if (this.selectedDependencies.has(code)) {
      this.selectedDependencies.delete(code);
    } else {
      this.selectedDependencies.add(code);
    }
    this.formData.dependencies = Array.from(this.selectedDependencies);
  }

  validate(): boolean {
    this.validationErrors = {};
    if (!this.formData.name?.trim()) {
      this.validationErrors['name'] = 'Module name is required';
    }
    if (!this.formData.code?.trim()) {
      this.validationErrors['code'] = 'Module code is required (e.g. PTX, WTR)';
    } else if (!/^[A-Z0-9_-]{2,10}$/.test(this.formData.code.trim())) {
      this.validationErrors['code'] = 'Code must be 2-10 uppercase alphanumeric chars';
    } else if (!this.isEditing) {
      const dup = this.existingModules.some((m) => m.code === this.formData.code.trim());
      if (dup) {
        this.validationErrors['code'] = `Module code '${this.formData.code}' already exists`;
      }
    }
    if (!this.formData.description?.trim()) {
      this.validationErrors['description'] = 'Description is required';
    }
    if (!this.formData.category) {
      this.validationErrors['category'] = 'Category is required';
    }
    if (!this.formData.moduleVersion?.trim()) {
      this.validationErrors['moduleVersion'] = 'Module version is required (e.g. 1.0.0)';
    }

    return Object.keys(this.validationErrors).length === 0;
  }

  save(): void {
    if (!this.validate()) {
      this.dialogs.showToast('Please correct form errors before saving', 'warning', 3000);
      return;
    }

    this.isSaving.set(true);
    this.loadingService.setMessage(this.isEditing ? 'Updating module...' : 'Creating module...');
    this.loadingService.show();

    this.formData.code = this.formData.code.toUpperCase().trim();
    this.formData.dependencies = Array.from(this.selectedDependencies);

    if (this.isEditing && this.selectedModule) {
      this.moduleService
        .updateModule(this.selectedModule.code, this.formData)
        .pipe(
          finalize(() => {
            this.isSaving.set(false);
            this.loadingService.hide();
          }),
        )
        .subscribe({
          next: (updated) => {
            this.dialogs.showToast(
              `Module '${updated.name}' updated successfully`,
              'success',
              3000,
            );
            this.saveSuccess.emit(updated);
          },
          error: (err: any) => {
            this.dialogs.showToast(err.error?.detail || 'Failed to update module', 'error', 3500);
          },
        });
    } else {
      this.moduleService
        .createModule(this.formData)
        .pipe(
          finalize(() => {
            this.isSaving.set(false);
            this.loadingService.hide();
          }),
        )
        .subscribe({
          next: (created) => {
            this.dialogs.showToast(
              `Module '${created.name}' created successfully`,
              'success',
              3000,
            );
            this.saveSuccess.emit(created);
          },
          error: (err: any) => {
            this.dialogs.showToast(err.error?.detail || 'Failed to create module', 'error', 3500);
          },
        });
    }
  }

  onCancel(): void {
    this.close.emit();
  }
}
