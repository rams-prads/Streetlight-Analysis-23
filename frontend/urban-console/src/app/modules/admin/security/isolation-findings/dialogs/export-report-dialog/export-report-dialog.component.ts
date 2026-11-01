import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { IsolationFinding } from '../../../../../../core/models/tenant-security.model';

@Component({
  selector: 'app-export-report-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './export-report-dialog.component.html',
  styleUrls: ['./export-report-dialog.component.scss']
})
export class ExportReportDialogComponent {
  @Input({ required: true }) findings: IsolationFinding[] = [];
  @Output() close = new EventEmitter<void>();

  reportFormat = 'PDF';
  includeRemediation = true;
  includeCertInCompliance = true;
  isDownloading = false;

  downloadReport() {
    this.isDownloading = true;
    setTimeout(() => {
      this.isDownloading = false;
      const jsonContent = JSON.stringify({
        reportTitle: 'SUVIDHA Municipal ERP — Tenant Isolation & Security Compliance Audit Report',
        auditStandard: 'CERT-In & Ministry of Housing and Urban Affairs (MoHUA)',
        generatedAt: new Date().toISOString(),
        totalFindings: this.findings.length,
        findings: this.findings
      }, null, 2);

      const blob = new Blob([jsonContent], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `tenant-isolation-audit-report-${new Date().toISOString().split('T')[0]}.json`;
      a.click();
      URL.revokeObjectURL(url);
      this.close.emit();
    }, 800);
  }

  onClose() {
    this.close.emit();
  }
}

