import { Component, EventEmitter, Input, Output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { RLSPolicy, RLSPolicyCreatePayload } from '../../../../../../core/models/tenant-security.model';

@Component({
  selector: 'app-create-policy-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './create-policy-dialog.component.html',
  styleUrls: ['./create-policy-dialog.component.scss']
})
export class CreatePolicyDialogComponent {
  @Input() policy?: RLSPolicy | null = null;
  @Output() save = new EventEmitter<RLSPolicyCreatePayload>();
  @Output() cancel = new EventEmitter<void>();

  policyName = '';
  policyCode = '';
  databaseService = 'PostgreSQL 16 (Core Service)';
  schemaName = 'public';
  tableName = 'properties';
  tenantKeyColumn = 'tenant_id';
  policyType = 'ALL';
  selectedCommands: string[] = ['SELECT', 'INSERT', 'UPDATE', 'DELETE'];
  selectedLevels: string[] = ['State (Level 1)', 'ULB / City (Level 2)'];
  policyDefinition = '';
  policyStatus = 'ACTIVE';
  enforcementNotes = '';

  availableServices = [
    'PostgreSQL 16 (Core Service)',
    'PostgreSQL TimescaleDB (IoT/Telemetry)',
    'Redis Scoped Cache Engine'
  ];

  availableTables = [
    'properties',
    'property_units',
    'water_connections',
    'water_meter_readings',
    'trade_licences',
    'financial_ledgers',
    'global_user_profiles',
    'building_plans',
    'citizen_grievances'
  ];

  availableCommands = ['SELECT', 'INSERT', 'UPDATE', 'DELETE'];
  availableLevels = ['Platform Super Admin (Level 0)', 'State (Level 1)', 'ULB / City (Level 2)', 'Department / Ward'];

  ngOnInit() {
    if (this.policy) {
      this.policyName = this.policy.policyName;
      this.policyCode = this.policy.policyCode;
      this.databaseService = this.policy.databaseService;
      this.schemaName = this.policy.schemaName;
      this.tableName = this.policy.tableName;
      this.tenantKeyColumn = this.policy.tenantKeyColumn;
      this.policyType = this.policy.policyType;
      this.selectedCommands = [...(this.policy.databaseCommands || [])];
      this.selectedLevels = [...(this.policy.applicableTenantLevels || [])];
      this.policyDefinition = this.policy.policyDefinition;
      this.policyStatus = this.policy.policyStatus;
      this.enforcementNotes = this.policy.enforcementNotes || '';
    } else {
      this.generateDefaultSql();
    }
  }

  generateDefaultSql() {
    this.policyDefinition = `CREATE POLICY ${this.tableName}_tenant_isolation ON ${this.tableName}
FOR ${this.policyType}
USING (
  ${this.tenantKeyColumn} = current_setting('app.current_tenant_id', true)::uuid
  AND (sub_tenant_id IS NULL OR sub_tenant_id = current_setting('app.current_sub_tenant_id', true)::uuid)
);`;
  }

  onTableChange() {
    if (!this.policy) {
      if (!this.policyCode || this.policyCode.startsWith('RLS-')) {
        this.policyCode = `RLS-${this.tableName.substring(0, 4).toUpperCase()}-01`;
      }
      this.generateDefaultSql();
    }
  }

  toggleCommand(cmd: string) {
    if (this.selectedCommands.includes(cmd)) {
      this.selectedCommands = this.selectedCommands.filter(c => c !== cmd);
    } else {
      this.selectedCommands.push(cmd);
    }
  }

  toggleLevel(lvl: string) {
    if (this.selectedLevels.includes(lvl)) {
      this.selectedLevels = this.selectedLevels.filter(l => l !== lvl);
    } else {
      this.selectedLevels.push(lvl);
    }
  }

  onSubmit() {
    if (!this.policyName.trim() || !this.policyCode.trim() || !this.policyDefinition.trim()) return;

    this.save.emit({
      policyName: this.policyName.trim(),
      policyCode: this.policyCode.trim().toUpperCase(),
      databaseService: this.databaseService,
      schemaName: this.schemaName.trim(),
      tableName: this.tableName,
      tenantKeyColumn: this.tenantKeyColumn.trim(),
      policyType: this.policyType,
      databaseCommands: this.selectedCommands,
      applicableTenantLevels: this.selectedLevels,
      policyDefinition: this.policyDefinition.trim(),
      policyStatus: this.policyStatus,
      enforcementNotes: this.enforcementNotes.trim()
    });
  }

  onCancel() {
    this.cancel.emit();
  }
}

