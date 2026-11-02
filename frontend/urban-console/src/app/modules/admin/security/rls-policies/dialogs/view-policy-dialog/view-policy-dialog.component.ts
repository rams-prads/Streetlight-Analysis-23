import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { RLSPolicy } from '../../../../../../core/models/tenant-security.model';

@Component({
  selector: 'app-view-policy-dialog',
  standalone: true,
  imports: [CommonModule, IconComponent],
  templateUrl: './view-policy-dialog.component.html',
  styleUrls: ['./view-policy-dialog.component.scss']
})
export class ViewPolicyDialogComponent {
  @Input({ required: true }) policy!: RLSPolicy;
  @Output() close = new EventEmitter<void>();
  @Output() validate = new EventEmitter<RLSPolicy>();

  copied = false;

  copySql() {
    if (this.policy?.policyDefinition) {
      navigator.clipboard.writeText(this.policy.policyDefinition);
      this.copied = true;
      setTimeout(() => (this.copied = false), 2000);
    }
  }

  onValidate() {
    this.validate.emit(this.policy);
  }

  onClose() {
    this.close.emit();
  }
}

