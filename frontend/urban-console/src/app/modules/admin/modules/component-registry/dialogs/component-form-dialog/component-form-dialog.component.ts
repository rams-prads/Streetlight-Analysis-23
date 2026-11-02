import { Component, Input, Output, EventEmitter, OnChanges, SimpleChanges, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { DialogService } from '../../../../../../core/services/dialog.service';
import { LoadingService } from '../../../../../../core/services/loading.service';
import { ModuleCatalogueService } from '../../../../../../core/services/module-catalogue.service';
import {
  ComponentCatalogueItem,
  ComponentCreatePayload,
  ModuleCatalogueItem
} from '../../../../../../core/models/module-catalogue.model';

@Component({
  selector: 'app-component-form-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './component-form-dialog.component.html',
  styleUrl: './component-form-dialog.component.scss'
})
export class ComponentFormDialogComponent implements OnChanges {
  private moduleService = inject(ModuleCatalogueService);
  private dialogs = inject(DialogService);
  private loadingService = inject(LoadingService);

  @Input() isOpen = false;
  @Input() isEditing = false;
  @Input() selectedComponent: ComponentCatalogueItem | null = null;
  @Input() defaultModuleCode = '';
  @Input() modules: ModuleCatalogueItem[] = [];
  @Input() existingComponents: ComponentCatalogueItem[] = [];

  @Output() close = new EventEmitter<void>();
  @Output() saveSuccess = new EventEmitter<ComponentCatalogueItem>();

  readonly typeOptions = ['Process', 'Service', 'UI View', 'Report', 'Workflow'];
  readonly statusOptions = ['Draft', 'Published', 'Deprecated'];
  readonly actionOptions = ['VIEW', 'CREATE', 'UPDATE', 'DELETE', 'APPROVE', 'EXPORT', 'MANAGE'];

  formData: ComponentCreatePayload = this.getInitialForm();
  selectedActions = new Set<string>(['VIEW', 'CREATE', 'UPDATE', 'DELETE']);
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
    if (this.isEditing && this.selectedComponent) {
      const c = this.selectedComponent;
      this.formData = {
        componentId: c.componentId,
        parentModuleCode: c.parentModuleCode,
        name: c.name,
        code: c.code,
        description: c.description,
        componentType: c.componentType,
        routePath: c.routePath || '',
        frontendPermissionKey: c.frontendPermissionKey,
        backendApiPermissionKey: c.backendApiPermissionKey,
        supportedActions: c.supportedActions || [],
        dependencies: c.dependencies || [],
        status: c.status || 'Published',
        displayOrder: c.displayOrder || 1
      };
      this.selectedActions = new Set(c.supportedActions || ['VIEW']);
      this.selectedDependencies = new Set(c.dependencies || []);
    } else {
      this.formData = this.getInitialForm();
      this.selectedActions = new Set(['VIEW', 'CREATE', 'UPDATE']);
      this.selectedDependencies = new Set();
      this.updatePermissionKeys();
    }
  }

  private getInitialForm(): ComponentCreatePayload {
    const parent = this.defaultModuleCode || (this.modules[0]?.code ?? 'PTX');
    return {
      componentId: '',
      parentModuleCode: parent,
      name: '',
      code: '',
      description: '',
      componentType: 'Process',
      routePath: '',
      frontendPermissionKey: '',
      backendApiPermissionKey: '',
      supportedActions: ['VIEW', 'CREATE', 'UPDATE'],
      dependencies: [],
      status: 'Published',
      displayOrder: 1
    };
  }

  onCodeChange(val: string): void {
    this.formData.code = val.toUpperCase().trim();
    if (this.validationErrors['code']) delete this.validationErrors['code'];
    this.updatePermissionKeys();
  }

  onParentModuleChange(): void {
    this.updatePermissionKeys();
  }

  toggleAction(action: string): void {
    if (this.selectedActions.has(action)) {
      if (this.selectedActions.size > 1) {
        this.selectedActions.delete(action);
      } else {
        this.dialogs.showToast('At least one supported action is required', 'warning', 2000);
      }
    } else {
      this.selectedActions.add(action);
    }
    this.formData.supportedActions = Array.from(this.selectedActions);
    this.updatePermissionKeys();
  }

  toggleDependency(code: string): void {
    if (this.selectedDependencies.has(code)) {
      this.selectedDependencies.delete(code);
    } else {
      this.selectedDependencies.add(code);
    }
    this.formData.dependencies = Array.from(this.selectedDependencies);
  }

  updatePermissionKeys(): void {
    if (this.isEditing) return;
    const mod = this.formData.parentModuleCode || 'MOD';
    const comp = this.formData.code || 'COMP';
    const firstAction = Array.from(this.selectedActions)[0] || 'VIEW';
    this.formData.frontendPermissionKey = `${comp}:${firstAction}`;
    this.formData.backendApiPermissionKey = `${mod}:${comp}:EXECUTE`;
  }

  validate(): boolean {
    this.validationErrors = {};
    if (!this.formData.parentModuleCode) {
      this.validationErrors['parentModuleCode'] = 'Parent module is required';
    }
    if (!this.formData.name?.trim()) {
      this.validationErrors['name'] = 'Component name is required';
    }
    if (!this.formData.code?.trim()) {
      this.validationErrors['code'] = 'Component code is required (e.g. PTX-P01)';
    } else if (!this.isEditing) {
      const dup = this.existingComponents.some(c => c.code === this.formData.code.trim());
      if (dup) {
        this.validationErrors['code'] = `Component code '${this.formData.code}' already exists`;
      }
    }
    if (!this.formData.description?.trim()) {
      this.validationErrors['description'] = 'Component description is required';
    }
    if (this.selectedActions.size === 0) {
      this.validationErrors['supportedActions'] = 'Select at least one supported action';
    }

    return Object.keys(this.validationErrors).length === 0;
  }

  save(): void {
    if (!this.validate()) {
      this.dialogs.showToast('Please correct form errors before saving', 'warning', 3000);
      return;
    }

    this.isSaving.set(true);
    this.loadingService.setMessage(this.isEditing ? 'Updating component...' : 'Creating component...');
    this.loadingService.show();

    this.formData.code = this.formData.code.toUpperCase().trim();
    this.formData.supportedActions = Array.from(this.selectedActions);
    this.formData.dependencies = Array.from(this.selectedDependencies);

    if (this.isEditing && this.selectedComponent) {
      this.moduleService.updateComponent(this.selectedComponent.code, this.formData).pipe(
        finalize(() => {
          this.isSaving.set(false);
          this.loadingService.hide();
        })
      ).subscribe({
        next: (updated) => {
          this.dialogs.showToast(`Component '${updated.name}' updated successfully`, 'success', 3000);
          this.saveSuccess.emit(updated);
        },
        error: (err: any) => {
          this.dialogs.showToast(err.error?.detail || 'Failed to update component', 'error', 3500);
        }
      });
    } else {
      this.moduleService.createComponent(this.formData).pipe(
        finalize(() => {
          this.isSaving.set(false);
          this.loadingService.hide();
        })
      ).subscribe({
        next: (created) => {
          this.dialogs.showToast(`Component '${created.name}' created successfully`, 'success', 3000);
          this.saveSuccess.emit(created);
        },
        error: (err: any) => {
          this.dialogs.showToast(err.error?.detail || 'Failed to create component', 'error', 3500);
        }
      });
    }
  }

  onCancel(): void {
    this.close.emit();
  }
}
