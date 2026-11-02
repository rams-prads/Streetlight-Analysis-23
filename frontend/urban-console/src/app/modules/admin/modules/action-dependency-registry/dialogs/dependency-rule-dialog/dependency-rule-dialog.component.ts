import { Component, Input, Output, EventEmitter, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActionDependencyRule, ModuleCatalogueItem, ComponentCatalogueItem } from '../../../../../../core/models/module-catalogue.model';

@Component({
  selector: 'app-dependency-rule-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './dependency-rule-dialog.component.html',
  styleUrl: './dependency-rule-dialog.component.scss'
})
export class DependencyRuleDialogComponent implements OnChanges {
  @Input() isOpen = false;
  @Input() isEditing = false;
  @Input() selectedRule: ActionDependencyRule | null = null;
  @Input() modules: ModuleCatalogueItem[] = [];
  @Input() components: ComponentCatalogueItem[] = [];

  @Output() close = new EventEmitter<void>();
  @Output() saveSuccess = new EventEmitter<ActionDependencyRule>();

  readonly ruleTypeOptions = ['Prerequisite', 'Trigger', 'Cross-Module Gate', 'Audit Chain'] as const;
  readonly enforcementOptions = ['Strict Block', 'Workflow Gate', 'Async Verification'] as const;
  readonly actionOptions = ['VIEW', 'CREATE', 'UPDATE', 'DELETE', 'APPROVE', 'VERIFY', 'EXECUTE', 'DISBURSE', 'SANCTION'];

  formData: Partial<ActionDependencyRule> = this.getInitialForm();
  validationErrors: Record<string, string> = {};

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['isOpen'] && this.isOpen) {
      this.initForm();
    }
  }

  private initForm(): void {
    this.validationErrors = {};
    if (this.isEditing && this.selectedRule) {
      this.formData = { ...this.selectedRule };
    } else {
      this.formData = this.getInitialForm();
    }
  }

  private getInitialForm(): Partial<ActionDependencyRule> {
    return {
      sourceModuleCode: this.modules[0]?.code ?? '',
      sourceComponentCode: '',
      sourceAction: 'APPROVE',
      targetModuleCode: '',
      targetComponentCode: '',
      targetAction: '',
      ruleType: 'Prerequisite',
      enforcementLevel: 'Strict Block',
      description: '',
      status: 'Active'
    };
  }

  onClose(): void {
    this.close.emit();
  }

  onSubmit(): void {
    this.validationErrors = {};
    if (!this.formData.sourceModuleCode) {
      this.validationErrors['sourceModuleCode'] = 'Source module is required';
    }
    if (!this.formData.sourceComponentCode) {
      this.validationErrors['sourceComponentCode'] = 'Source component code is required';
    }
    if (!this.formData.targetModuleCode) {
      this.validationErrors['targetModuleCode'] = 'Target module is required';
    }
    if (!this.formData.targetComponentCode) {
      this.validationErrors['targetComponentCode'] = 'Target component code is required';
    }
    if (!this.formData.targetAction) {
      this.validationErrors['targetAction'] = 'Required target action must be selected';
    }
    if (
      this.formData.sourceComponentCode &&
      this.formData.targetComponentCode &&
      this.formData.sourceComponentCode.trim().toUpperCase() === this.formData.targetComponentCode.trim().toUpperCase()
    ) {
      this.validationErrors['targetComponentCode'] = 'Target component cannot be identical to source component';
    }
    if (!this.formData.description) {
      this.validationErrors['description'] = 'Description rule purpose is required';
    }

    if (Object.keys(this.validationErrors).length > 0) return;

    const savedRule: ActionDependencyRule = {
      id: this.formData.id || `DEP-${Date.now().toString(36).toUpperCase()}`,
      sourceModuleCode: this.formData.sourceModuleCode!,
      sourceComponentCode: this.formData.sourceComponentCode!.toUpperCase().trim(),
      sourceAction: this.formData.sourceAction || 'APPROVE',
      targetModuleCode: this.formData.targetModuleCode!,
      targetComponentCode: this.formData.targetComponentCode!.toUpperCase().trim(),
      targetAction: this.formData.targetAction || 'VERIFY',
      ruleType: (this.formData.ruleType as any) || 'Prerequisite',
      enforcementLevel: (this.formData.enforcementLevel as any) || 'Strict Block',
      description: this.formData.description || '',
      status: (this.formData.status as any) || 'Active'
    };

    this.saveSuccess.emit(savedRule);
  }
}
