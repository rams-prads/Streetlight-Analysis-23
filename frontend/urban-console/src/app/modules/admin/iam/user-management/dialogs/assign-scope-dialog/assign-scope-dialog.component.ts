import { Component, Input, Output, EventEmitter, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../../../shared/components/icon/icon.component';
import { IamUserService } from '../../../../../../core/services/iam-user.service';
import { DialogService } from '../../../../../../core/services/dialog.service';
import { LoadingService } from '../../../../../../core/services/loading.service';
import { TenantManagementService } from '../../../../../../core/services/tenant-management.service';
import { UlbManagementService } from '../../../../../../core/services/ulb-management.service';
import { GlobalUserItem, GlobalUserScopePayload } from '../../../../../../core/models/iam-user.model';
import { RoleItem } from '../../../../../../core/models/iam-rbac.model';
import { StateTenant } from '../../../../../../core/models/state-tenant.model';
import { UlbTenant, Zone, Ward } from '../../../../../../core/models/ulb-tenant.model';

@Component({
  selector: 'app-assign-scope-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './assign-scope-dialog.component.html',
  styleUrl: './assign-scope-dialog.component.scss'
})
export class AssignScopeDialogComponent implements OnInit {
  @Input() user!: GlobalUserItem;
  @Input() availableRoles: RoleItem[] = [];
  @Output() saved = new EventEmitter<void>();
  @Output() closed = new EventEmitter<void>();

  private userService = inject(IamUserService);
  private tenantService = inject(TenantManagementService);
  private ulbService = inject(UlbManagementService);
  private dialogs = inject(DialogService);
  private loading = inject(LoadingService);

  readonly isSubmitting = signal<boolean>(false);
  readonly loadingStates = signal<boolean>(false);
  readonly loadingUlbs = signal<boolean>(false);
  readonly loadingZones = signal<boolean>(false);
  readonly loadingWards = signal<boolean>(false);

  // Multi-select dropdown popover open states
  readonly isStateDropdownOpen = signal<boolean>(false);
  readonly isUlbDropdownOpen = signal<boolean>(false);

  // Form Fields
  platformAccess: boolean = false;
  readonly selectedStateCodes = signal<string[]>([]);
  readonly selectedUlbCodes = signal<string[]>([]);
  assignedDepartment: string = '';
  assignedZone: string = '';
  assignedWard: string = '';
  selectedRoleCodes: string[] = [];
  accessEffectiveFrom: string = '';
  accessEffectiveUntil: string = '';
  approvalReference: string = '';

  // Dynamic Lists from Database
  readonly states = signal<StateTenant[]>([]);
  readonly ulbs = signal<UlbTenant[]>([]);
  readonly zones = signal<Zone[]>([]);
  readonly wards = signal<Ward[]>([]);

  readonly departments = [
    'Executive Directorate',
    'Revenue & Property Tax',
    'Water & Sewerage Operations',
    'Town Planning & Regulations',
    'Finance & Accounts',
    'Audit & Vigilance'
  ];

  ngOnInit(): void {
    this.platformAccess = this.user.platformAccess;

    if (this.user.stateTenantId) {
      this.selectedStateCodes.set(
        this.user.stateTenantId.split(',').map(s => s.trim()).filter(Boolean)
      );
    }
    if (this.user.ulbTenantId) {
      this.selectedUlbCodes.set(
        this.user.ulbTenantId.split(',').map(u => u.trim()).filter(Boolean)
      );
    }

    this.assignedDepartment = this.user.assignedDepartment || '';
    this.assignedZone = this.user.assignedZone || '';
    this.assignedWard = this.user.assignedWard || '';
    this.selectedRoleCodes = [...(this.user.assignedRoles || [])];
    this.accessEffectiveFrom = this.user.accessEffectiveFrom || new Date().toISOString().split('T')[0];
    this.accessEffectiveUntil = this.user.accessEffectiveUntil || '';
    this.approvalReference = this.user.approvalReference || '';

    this.loadStates();
  }

  loadStates(): void {
    this.loadingStates.set(true);
    this.tenantService.getStateTenants().subscribe({
      next: (res) => {
        const list = res || [];
        this.states.set(list);
        this.loadingStates.set(false);

        // If no state selected, auto-select first active or first state
        if (this.selectedStateCodes().length === 0 && list.length > 0) {
          const firstActive = list.find(s => s.status === 'Active') || list[0];
          this.selectedStateCodes.set([firstActive.stateCode]);
        }

        this.onSelectedStatesChanged();
      },
      error: () => {
        this.states.set([]);
        this.loadingStates.set(false);
        this.dialogs.showToast('Failed to load state tenants', 'error');
      }
    });
  }

  toggleStateDropdown(event: Event): void {
    event.stopPropagation();
    this.isUlbDropdownOpen.set(false);
    this.isStateDropdownOpen.update(v => !v);
  }

  toggleUlbDropdown(event: Event): void {
    event.stopPropagation();
    this.isStateDropdownOpen.set(false);
    this.isUlbDropdownOpen.update(v => !v);
  }

  closeAllDropdowns(): void {
    this.isStateDropdownOpen.set(false);
    this.isUlbDropdownOpen.set(false);
  }

  // State selection methods
  isStateSelected(code: string): boolean {
    return this.selectedStateCodes().includes(code);
  }

  toggleState(code: string): void {
    const current = [...this.selectedStateCodes()];
    const index = current.indexOf(code);
    if (index > -1) {
      current.splice(index, 1);
    } else {
      current.push(code);
    }
    this.selectedStateCodes.set(current);
    this.onSelectedStatesChanged();
  }

  removeState(code: string, event: Event): void {
    event.stopPropagation();
    this.toggleState(code);
  }

  selectAllStates(): void {
    this.selectedStateCodes.set(this.states().map(s => s.stateCode));
    this.onSelectedStatesChanged();
  }

  clearAllStates(): void {
    this.selectedStateCodes.set([]);
    this.onSelectedStatesChanged();
  }

  onSelectedStatesChanged(): void {
    const states = this.selectedStateCodes();
    if (states.length === 0) {
      this.ulbs.set([]);
      this.selectedUlbCodes.set([]);
      this.onSelectedUlbsChanged();
      return;
    }

    this.loadingUlbs.set(true);
    this.ulbService.getUlbs().subscribe({
      next: (allUlbs) => {
        const filtered = (allUlbs || []).filter(u => states.includes(u.stateCode));
        this.ulbs.set(filtered);
        this.loadingUlbs.set(false);

        // Keep only valid selected ULBs
        const validCodes = new Set(filtered.map(u => u.ulbCode));
        const pruned = this.selectedUlbCodes().filter(c => validCodes.has(c));
        this.selectedUlbCodes.set(pruned);
        this.onSelectedUlbsChanged();
      },
      error: () => {
        this.ulbs.set([]);
        this.loadingUlbs.set(false);
      }
    });
  }

  // ULB selection methods
  isUlbSelected(code: string): boolean {
    return this.selectedUlbCodes().includes(code);
  }

  toggleUlb(code: string): void {
    const current = [...this.selectedUlbCodes()];
    const index = current.indexOf(code);
    if (index > -1) {
      current.splice(index, 1);
    } else {
      current.push(code);
    }
    this.selectedUlbCodes.set(current);
    this.onSelectedUlbsChanged();
  }

  removeUlb(code: string, event: Event): void {
    event.stopPropagation();
    this.toggleUlb(code);
  }

  selectAllUlbs(): void {
    this.selectedUlbCodes.set(this.ulbs().map(u => u.ulbCode));
    this.onSelectedUlbsChanged();
  }

  clearAllUlbs(): void {
    this.selectedUlbCodes.set([]);
    this.onSelectedUlbsChanged();
  }

  onSelectedUlbsChanged(): void {
    const sel = this.selectedUlbCodes();
    if (sel.length === 1) {
      this.loadZonesAndWards(sel[0]);
    } else {
      this.zones.set([]);
      this.wards.set([]);
      this.assignedZone = '';
      this.assignedWard = '';
    }
  }

  loadZonesAndWards(ulbCode: string): void {
    this.loadingZones.set(true);
    this.loadingWards.set(true);

    this.ulbService.getZones(ulbCode).subscribe({
      next: (res) => {
        this.zones.set(res || []);
        this.loadingZones.set(false);
      },
      error: () => {
        this.zones.set([]);
        this.loadingZones.set(false);
      }
    });

    this.ulbService.getWards(ulbCode).subscribe({
      next: (res) => {
        this.wards.set(res || []);
        this.loadingWards.set(false);
      },
      error: () => {
        this.wards.set([]);
        this.loadingWards.set(false);
      }
    });
  }

  onZoneChange(newZone: string): void {
    this.assignedZone = newZone;
    if (this.assignedWard) {
      const valid = this.filteredWards.some(w =>
        (w.wardCode && w.wardCode === this.assignedWard) ||
        ('Ward ' + w.wardNumber === this.assignedWard) ||
        (String(w.wardNumber) === this.assignedWard) ||
        (w.wardName === this.assignedWard)
      );
      if (!valid) {
        this.assignedWard = '';
      }
    }
  }

  get filteredWards(): Ward[] {
    const zoneVal = this.assignedZone;
    if (!zoneVal) {
      return this.wards();
    }
    const matchedZone = this.zones().find(z => z.code === zoneVal || z.id === zoneVal || z.name === zoneVal);
    if (!matchedZone) {
      return this.wards();
    }
    return this.wards().filter(w => w.zoneId === matchedZone.id);
  }

  isZoneInList(code: string): boolean {
    if (!code) return true;
    return this.zones().some(z => z.code === code || z.id === code || z.name === code);
  }

  isWardInList(val: string): boolean {
    if (!val) return true;
    return this.filteredWards.some(w =>
      (w.wardCode && w.wardCode === val) ||
      ('Ward ' + w.wardNumber === val) ||
      (String(w.wardNumber) === val) ||
      (w.wardName === val)
    );
  }

  isRoleSelected(code: string): boolean {
    return this.selectedRoleCodes.includes(code);
  }

  toggleRole(code: string): void {
    if (this.selectedRoleCodes.includes(code)) {
      this.selectedRoleCodes = this.selectedRoleCodes.filter(c => c !== code);
    } else {
      this.selectedRoleCodes.push(code);
    }
  }

  onSubmit(): void {
    if (!this.platformAccess && this.selectedStateCodes().length === 0) {
      this.dialogs.showToast('Please select at least one State Tenant', 'warning');
      return;
    }

    if (this.selectedRoleCodes.length === 0) {
      this.dialogs.showToast('Please assign at least one role to the user', 'warning');
      return;
    }

    const stateTenantId = this.selectedStateCodes().join(',');
    const ulbTenantId = this.selectedUlbCodes().join(',');

    const payload: GlobalUserScopePayload = {
      platformAccess: this.platformAccess,
      stateTenantId: this.platformAccess ? null : (stateTenantId || null),
      ulbTenantId: this.platformAccess ? null : (ulbTenantId || null),
      assignedDepartment: this.assignedDepartment || null,
      assignedZone: this.assignedZone || null,
      assignedWard: this.assignedWard || null,
      assignedRoles: this.selectedRoleCodes,
      additionalPermissions: [],
      accessEffectiveFrom: this.accessEffectiveFrom || null,
      accessEffectiveUntil: this.accessEffectiveUntil || null,
      approvalReference: this.approvalReference.trim() || null
    };

    this.isSubmitting.set(true);
    this.loading.show(`Applying scope allocation for ${this.user.fullName}...`);
    this.userService.updateUserScope(this.user.id, payload).subscribe({
      next: (res) => {
        this.isSubmitting.set(false);
        this.loading.hide();
        if (res.success) {
          this.dialogs.showToast(`Tenancy & organizational scope updated for '${this.user.fullName}'`, 'success');
          this.saved.emit();
        }
      },
      error: () => {
        this.isSubmitting.set(false);
        this.loading.hide();
        this.dialogs.showToast('Failed to update scope assignment', 'error');
      }
    });
  }

  onCancel(): void {
    this.closed.emit();
  }
}
