import { Component, EventEmitter, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { TenantIsolationTestCreatePayload } from '../../../../../../core/models/tenant-security.model';

@Component({
  selector: 'app-create-test-run-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './create-test-run-dialog.component.html',
  styleUrls: ['./create-test-run-dialog.component.scss']
})
export class CreateTestRunDialogComponent {
  @Output() save = new EventEmitter<TenantIsolationTestCreatePayload>();
  @Output() cancel = new EventEmitter<void>();

  testRunName = 'Cross-Tenant Boundary Security Verification';
  environment = 'Isolated Sandbox';
  sourceTenant = 'State of Telangana (TG)';
  targetTenant = 'State of Maharashtra (MH)';
  testType = 'Synthetic Penetration Test';
  executionMode = 'Automated Batch';
  schedule = 'On-Demand';
  newRecipient = '';
  recipients: string[] = ['secops@urban.gov.in'];
  stopOnCriticalFailure = true;

  availableScenarios = [
    "State A cannot read State B's records",
    "ULB A cannot read ULB B's records",
    "A user cannot change a tenant ID in a request to access another tenant",
    "Cross-tenant updates and deletes are rejected",
    "Queries without valid tenant context are denied",
    "Connection-pool reuse does not leak a previous request's tenant context",
    "Background jobs and exports enforce the same tenant restrictions",
    "Privileged support access follows its explicit, audited authorisation path"
  ];

  selectedScenarios: string[] = [
    "State A cannot read State B's records",
    "A user cannot change a tenant ID in a request to access another tenant",
    "Cross-tenant updates and deletes are rejected",
    "Connection-pool reuse does not leak a previous request's tenant context"
  ];

  availableServices = ['PostgreSQL Core', 'Redis Scoped Cache', 'Document Storage (DMS)'];
  selectedServices: string[] = ['PostgreSQL Core', 'Redis Scoped Cache'];

  availableTables = ['properties', 'water_accounts', 'users', 'trade_licences', 'financial_ledgers'];
  selectedTables: string[] = ['properties', 'users', 'financial_ledgers'];

  tenantFixtures = [
    'State of Telangana (TG)',
    'State of Maharashtra (MH)',
    'State of Karnataka (KA)',
    'Greater Hyderabad MC (GHMC)',
    'Greater Warangal MC (GWMC)',
    'Pune Municipal Corporation (PMC)'
  ];

  toggleScenario(sc: string) {
    if (this.selectedScenarios.includes(sc)) {
      this.selectedScenarios = this.selectedScenarios.filter(s => s !== sc);
    } else {
      this.selectedScenarios.push(sc);
    }
  }

  toggleService(svc: string) {
    if (this.selectedServices.includes(svc)) {
      this.selectedServices = this.selectedServices.filter(s => s !== svc);
    } else {
      this.selectedServices.push(svc);
    }
  }

  toggleTable(tbl: string) {
    if (this.selectedTables.includes(tbl)) {
      this.selectedTables = this.selectedTables.filter(t => t !== tbl);
    } else {
      this.selectedTables.push(tbl);
    }
  }

  addRecipient() {
    if (this.newRecipient.trim() && !this.recipients.includes(this.newRecipient.trim())) {
      this.recipients.push(this.newRecipient.trim());
      this.newRecipient = '';
    }
  }

  removeRecipient(r: string) {
    this.recipients = this.recipients.filter(item => item !== r);
  }

  onSubmit() {
    if (!this.testRunName.trim() || this.selectedScenarios.length === 0) return;

    this.save.emit({
      testRunName: this.testRunName.trim(),
      environment: this.environment,
      sourceTenant: this.sourceTenant,
      targetTenant: this.targetTenant,
      testScenarios: this.selectedScenarios,
      databaseServices: this.selectedServices,
      tablesInScope: this.selectedTables,
      testType: this.testType,
      executionMode: this.executionMode,
      schedule: this.schedule,
      notificationRecipients: this.recipients,
      stopOnCriticalFailure: this.stopOnCriticalFailure
    });
  }

  onCancel() {
    this.cancel.emit();
  }
}

