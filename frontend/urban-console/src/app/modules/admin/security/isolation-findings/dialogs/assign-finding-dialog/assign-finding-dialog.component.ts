import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { IsolationFinding, IsolationFindingUpdatePayload } from '../../../../../../core/models/tenant-security.model';

@Component({
  selector: 'app-assign-finding-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './assign-finding-dialog.component.html',
  styleUrls: ['./assign-finding-dialog.component.scss']
})
export class AssignFindingDialogComponent {
  @Input({ required: true }) finding!: IsolationFinding;
  @Output() save = new EventEmitter<{ id: string; payload: IsolationFindingUpdatePayload }>();
  @Output() cancel = new EventEmitter<void>();

  severity = 'HIGH';
  remediationOwner = '';
  remediationDueDate = '';
  retestStatus = 'OPEN';
  resolutionNotes = '';

  availableOwners = [
    'Database Engineering Lead',
    'Backend Infrastructure Lead',
    'Security Operations (SecOps)',
    'Chief Information Security Officer (CISO)',
    'DevOps & Cloud Architect',
    'State IT Nodal Officer'
  ];

  ngOnInit() {
    if (this.finding) {
      this.severity = this.finding.severity;
      this.remediationOwner = this.finding.remediationOwner;
      this.remediationDueDate = this.finding.remediationDueDate;
      this.retestStatus = this.finding.retestStatus;
      this.resolutionNotes = this.finding.resolutionNotes || '';
    }
  }

  onSubmit() {
    this.save.emit({
      id: this.finding.id,
      payload: {
        severity: this.severity,
        remediationOwner: this.remediationOwner,
        remediationDueDate: this.remediationDueDate,
        retestStatus: this.retestStatus,
        resolutionNotes: this.resolutionNotes.trim()
      }
    });
  }

  onCancel() {
    this.cancel.emit();
  }
}

