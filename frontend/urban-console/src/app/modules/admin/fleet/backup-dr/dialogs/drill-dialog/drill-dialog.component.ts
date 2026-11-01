import { Component, EventEmitter, Output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { DrillExecutionPayload } from '../../../../../../core/models/backup-dr.model';

@Component({
  selector: 'app-drill-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './drill-dialog.component.html',
  styleUrls: ['./drill-dialog.component.scss'],
})
export class DrillDialogComponent {
  @Output() cancel = new EventEmitter<void>();
  @Output() scheduled = new EventEmitter<DrillExecutionPayload>();

  drillName = '';
  drillCode = '';
  drillType = 'Cross-Region Failover';
  environment = 'Production Simulation';
  primaryRegion = 'ap-south-1 (Mumbai Primary)';
  secondaryRegion = 'ap-south-2 (Hyderabad Secondary)';
  selectedServices: string[] = ['Core API', 'Billing Engine', 'Citizen Auth Realm'];
  selectedDatabases: string[] = ['pg-aurora-cluster-prod', 'redis-cluster-ha'];
  plannedStartDate = '';
  plannedEndDate = '';
  expectedRpoMinutes = 5;
  expectedRtoMinutes = 15;
  drillCoordinator = 'Anand Verma (Lead SRE)';
  approvalAuthority = 'Director General (State IT)';
  notificationRecipientsText = 'sre-dr-team@urban.gov.in, cert-in-liaison@urban.gov.in';
  drillObjective = '';
  rollbackPlan = '';

  isSubmitting = signal(false);

  readonly availableDrillTypes = [
    'Cross-Region Failover',
    'Simulated Ransomware Recovery',
    'Database Corruption Playbook',
    'Split-Brain Isolation',
  ];

  readonly availableServices = [
    'Core API',
    'Billing Engine',
    'Citizen Auth Realm',
    'Audit Vault',
    'GIS Spatial Server',
    'BBPS Gateway',
  ];

  readonly availableDatabases = [
    'pg-aurora-cluster-prod',
    'pg-gis-postgis-cluster',
    'urban_audit_vault',
    'redis-cluster-ha',
  ];

  readonly availableCoordinators = [
    'Anand Verma (Lead SRE)',
    'Priya Nair (Principal Security Architect)',
    'Ramesh Rao (Cluster Architect)',
  ];

  readonly availableAuthorities = [
    'Director General (State IT)',
    'Chief Information Security Officer (CISO)',
    'State Principal Secretary (MA&UD)',
  ];

  toggleService(svc: string): void {
    const idx = this.selectedServices.indexOf(svc);
    if (idx >= 0) {
      if (this.selectedServices.length > 1) this.selectedServices.splice(idx, 1);
    } else {
      this.selectedServices.push(svc);
    }
  }

  isServiceSelected(svc: string): boolean {
    return this.selectedServices.includes(svc);
  }

  toggleDatabase(db: string): void {
    const idx = this.selectedDatabases.indexOf(db);
    if (idx >= 0) {
      if (this.selectedDatabases.length > 1) this.selectedDatabases.splice(idx, 1);
    } else {
      this.selectedDatabases.push(db);
    }
  }

  isDatabaseSelected(db: string): boolean {
    return this.selectedDatabases.includes(db);
  }

  onCancel(): void {
    this.cancel.emit();
  }

  onSubmit(): void {
    if (
      !this.drillName.trim() ||
      !this.drillCode.trim() ||
      !this.plannedStartDate ||
      !this.plannedEndDate ||
      !this.drillObjective.trim() ||
      !this.rollbackPlan.trim() ||
      this.selectedServices.length === 0 ||
      this.selectedDatabases.length === 0
    ) {
      return;
    }

    const recipients = this.notificationRecipientsText
      .split(',')
      .map((e) => e.trim())
      .filter((e) => !!e);

    const payload: DrillExecutionPayload = {
      drillName: this.drillName.trim(),
      drillCode: this.drillCode.trim().toUpperCase(),
      drillType: this.drillType,
      environment: this.environment,
      primaryRegion: this.primaryRegion,
      secondaryRegion: this.secondaryRegion,
      servicesInScope: [...this.selectedServices],
      databasesInScope: [...this.selectedDatabases],
      plannedStartDate: new Date(this.plannedStartDate).toISOString(),
      plannedEndDate: new Date(this.plannedEndDate).toISOString(),
      expectedRpoMinutes: Number(this.expectedRpoMinutes) || 5,
      expectedRtoMinutes: Number(this.expectedRtoMinutes) || 15,
      drillCoordinator: this.drillCoordinator,
      approvalAuthority: this.approvalAuthority,
      notificationRecipients: recipients,
      drillObjective: this.drillObjective.trim(),
      rollbackPlan: this.rollbackPlan.trim(),
    };

    this.isSubmitting.set(true);
    this.scheduled.emit(payload);
  }
}

