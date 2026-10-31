import { Component, OnInit, Output, EventEmitter, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { DelegationService } from '../../../../../../core/services/delegation.service';
import { UlbManagementService } from '../../../../../../core/services/ulb-management.service';
import { UlbTenant } from '../../../../../../core/models/ulb-tenant.model';
import { EffectivePermissionCheckResult } from '../../../../../../core/models/delegation.model';

@Component({
  selector: 'app-verify-access-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './verify-access-dialog.component.html',
  styleUrl: './verify-access-dialog.component.scss'
})
export class VerifyAccessDialogComponent implements OnInit {
  @Output() closed = new EventEmitter<void>();

  private delegationService = inject(DelegationService);
  private ulbService = inject(UlbManagementService);

  readonly ulbTenants = signal<UlbTenant[]>([]);
  readonly isChecking = signal<boolean>(false);
  readonly verificationResult = signal<EffectivePermissionCheckResult | null>(null);

  selectedUlbId: string = '';
  moduleCode: string = 'PTX';
  componentCode: string = 'PTX-P01';
  action: string = 'APPROVE';

  readonly commonModules = ['PTX', 'WTR', 'TRL', 'UCH', 'FIN', 'GRV', 'BPM', 'SWM'];
  readonly commonActions = ['VIEW', 'CREATE', 'UPDATE', 'DELETE', 'APPROVE', 'EXPORT', 'MANAGE'];

  ngOnInit(): void {
    this.ulbService.getUlbs().subscribe({
      next: (ulbs) => {
        this.ulbTenants.set(ulbs || []);
        if (ulbs && ulbs.length > 0) {
          this.selectedUlbId = ulbs[0].tenantId;
        }
      },
      error: () => this.ulbTenants.set([])
    });
  }

  onCancel(): void {
    this.closed.emit();
  }

  executeVerification(): void {
    if (!this.selectedUlbId || !this.moduleCode || !this.componentCode || !this.action) return;

    this.isChecking.set(true);
    this.verificationResult.set(null);

    this.delegationService.verifyHierarchyAccess(
      this.selectedUlbId,
      this.moduleCode.trim(),
      this.componentCode.trim(),
      this.action.trim()
    ).subscribe({
      next: (res) => {
        this.isChecking.set(false);
        if (res.success && res.data) {
          this.verificationResult.set(res.data);
        }
      },
      error: () => {
        this.isChecking.set(false);
      }
    });
  }
}
