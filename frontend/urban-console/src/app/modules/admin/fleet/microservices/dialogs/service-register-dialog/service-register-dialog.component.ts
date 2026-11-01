import { Component, EventEmitter, Output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { MicroserviceRegisterPayload } from '../../../../../../core/models/fleet.model';

@Component({
  selector: 'app-service-register-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './service-register-dialog.component.html',
  styleUrls: ['./service-register-dialog.component.scss'],
})
export class ServiceRegisterDialogComponent {
  @Output() cancel = new EventEmitter<void>();
  @Output() registered = new EventEmitter<MicroserviceRegisterPayload>();

  serviceName = '';
  serviceCode = '';
  serviceDescription = '';
  serviceCategory = 'Domain Microservice';
  serviceType = 'Stateless HTTP';
  selectedEnvironments: string[] = ['Production', 'Staging'];
  baseUrl = 'http://microservice.suvidha-cluster.local:8080';
  healthCheckEndpoint = '/healthz';
  healthCheckMethod = 'GET';
  healthCheckIntervalSeconds = 15;
  timeoutSeconds = 5;
  retryCount = 3;
  criticalityLevel = 'P1 - High';
  monitoringEnabled = true;
  alertPolicy = 'Default P0 Escalation';
  version = 'v1.0.0';
  region = 'ap-south-1';

  isSubmitting = signal(false);

  readonly availableCategories = [
    'Core Platform',
    'Domain Microservice',
    'Worker Daemon',
    'Integration Gateway',
    'Data & Analytics',
  ];

  readonly availableTypes = [
    'Stateless HTTP',
    'Async Worker',
    'Event Streamer',
    'Stateful Cache',
  ];

  readonly availableEnvironments = ['Production', 'Staging', 'Development', 'DR-Site'];

  readonly availableMethods = ['GET', 'POST', 'HEAD'];

  readonly availableCriticalities = [
    'P0 - Critical',
    'P1 - High',
    'P2 - Normal',
    'P3 - Low',
  ];

  readonly availableAlertPolicies = [
    'Default P0 Escalation',
    'Infrastructure SRE On-Call',
    'Ops Slack & PagerDuty',
    'Low Priority Daily Digest',
    'None',
  ];

  toggleEnvironment(env: string): void {
    const idx = this.selectedEnvironments.indexOf(env);
    if (idx >= 0) {
      if (this.selectedEnvironments.length > 1) {
        this.selectedEnvironments.splice(idx, 1);
      }
    } else {
      this.selectedEnvironments.push(env);
    }
  }

  isEnvSelected(env: string): boolean {
    return this.selectedEnvironments.includes(env);
  }

  onCancel(): void {
    this.cancel.emit();
  }

  onSubmit(): void {
    if (
      !this.serviceName.trim() ||
      !this.serviceCode.trim() ||
      !this.serviceDescription.trim() ||
      !this.baseUrl.trim() ||
      !this.healthCheckEndpoint.trim() ||
      this.selectedEnvironments.length === 0
    ) {
      return;
    }

    const payload: MicroserviceRegisterPayload = {
      serviceCode: this.serviceCode.trim().toUpperCase(),
      serviceName: this.serviceName.trim(),
      serviceDescription: this.serviceDescription.trim(),
      serviceCategory: this.serviceCategory,
      serviceType: this.serviceType,
      environments: [...this.selectedEnvironments],
      baseUrl: this.baseUrl.trim(),
      healthCheckEndpoint: this.healthCheckEndpoint.trim(),
      healthCheckMethod: this.healthCheckMethod,
      healthCheckIntervalSeconds: Number(this.healthCheckIntervalSeconds) || 15,
      timeoutSeconds: Number(this.timeoutSeconds) || 5,
      retryCount: Number(this.retryCount) || 3,
      criticalityLevel: this.criticalityLevel,
      monitoringEnabled: this.monitoringEnabled,
      alertPolicy: this.alertPolicy === 'None' ? null : this.alertPolicy,
      version: this.version.trim() || 'v1.0.0',
      region: this.region.trim() || 'ap-south-1',
    };

    this.isSubmitting.set(true);
    this.registered.emit(payload);
  }
}

