import { Component, OnInit, Input, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { IconComponent } from '../../../../shared/components/icon/icon.component';
import { IamRbacService } from '../../../../core/services/iam-rbac.service';
import { IamPermissionMatrixService } from '../../../../core/services/iam-permission-matrix.service';
import { DialogService } from '../../../../core/services/dialog.service';
import { LoadingService } from '../../../../core/services/loading.service';
import { RoleItem, RolePermissionItem } from '../../../../core/models/iam-rbac.model';
import { LIVE_MATRIX_MODULES, OverrideChange, PermissionMatrix, PermissionRow, roleLabel } from '../../../../core/models/iam-permission-matrix.model';
import { CreateRoleDialogComponent } from './dialogs/create-role-dialog/create-role-dialog.component';
import { CompareRolesDialogComponent } from './dialogs/compare-roles-dialog/compare-roles-dialog.component';
import { CopyPermissionsDialogComponent } from './dialogs/copy-permissions-dialog/copy-permissions-dialog.component';

@Component({
  selector: 'app-roles-matrix',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    IconComponent,
    CreateRoleDialogComponent,
    CompareRolesDialogComponent,
    CopyPermissionsDialogComponent
  ],
  templateUrl: './roles-matrix.component.html',
  styleUrl: './roles-matrix.component.scss'
})
export class RolesMatrixComponent implements OnInit {
  private rbacService = inject(IamRbacService);
  private permissionMatrixService = inject(IamPermissionMatrixService);
  private dialogs = inject(DialogService);
  private loading = inject(LoadingService);
  private router = inject(Router);
  readonly roleLabel = roleLabel;

  readonly activeTab = signal<'matrix' | 'templates' | 'directory'>('matrix');

  // Live matrix: the module's actual PERMISSIONS dict (PTX/WTR only - the only modules with a real backend).
  readonly liveModules = LIVE_MATRIX_MODULES;
  readonly selectedModule = signal<string>('PTX');
  readonly matrix = signal<PermissionMatrix | null>(null);
  readonly isLoadingMatrix = signal<boolean>(false);
  readonly matrixSearch = signal<string>('');
  /** Keyed by "permissionKey::role"; cleared on load and after a successful save. */
  readonly pendingChanges = signal<Record<string, OverrideChange>>({});

  readonly hasMatrixChanges = computed(() => Object.keys(this.pendingChanges()).length > 0);

  readonly groupedPermissions = computed(() => {
    const m = this.matrix();
    if (!m) return [];
    const q = this.matrixSearch().toLowerCase().trim();
    const rows = q
      ? m.permissions.filter((p) => p.key.toLowerCase().includes(q) || p.group.toLowerCase().includes(q) || (p.label || '').toLowerCase().includes(q))
      : m.permissions;
    const groups: { group: string; permissions: PermissionRow[] }[] = [];
    const byGroup = new Map<string, PermissionRow[]>();
    for (const row of rows) {
      let bucket = byGroup.get(row.group);
      if (!bucket) {
        bucket = [];
        byGroup.set(row.group, bucket);
        groups.push({ group: row.group, permissions: bucket });
      }
      bucket.push(row);
    }
    return groups;
  });

  @Input() set defaultTab(tab: 'matrix' | 'templates' | 'directory' | undefined) {
    if (tab) {
      this.activeTab.set(tab);
    }
  }
  readonly roles = signal<RoleItem[]>([]);
  readonly roleTemplates = signal<RoleItem[]>([]);
  readonly selectedRoleId = signal<string>('');
  readonly permissions = signal<RolePermissionItem[]>([]);
  readonly searchQuery = signal<string>('');
  readonly moduleFilter = signal<string>('ALL');

  readonly isSavingMatrix = signal<boolean>(false);
  readonly isLoading = signal<boolean>(false);
  readonly hasPendingChanges = signal<boolean>(false);

  // Dialog signals
  readonly isCreateDialogOpen = signal<boolean>(false);
  readonly roleToEdit = signal<RoleItem | null>(null);
  readonly isCompareDialogOpen = signal<boolean>(false);
  readonly isCopyDialogOpen = signal<boolean>(false);

  readonly dataScopes = [
    'Own Records',
    'Assigned Department',
    'Ward',
    'ULB',
    'State',
    'Platform'
  ];

  readonly modulesList = [
    { code: 'ALL', name: 'All Modules' },
    { code: 'PTX', name: 'Property Tax (PTX)' },
    { code: 'WTR', name: 'Water & Sewerage (WTR)' },
    { code: 'TRL', name: 'Trade Licences (TRL)' },
    { code: 'UCH', name: 'User Charges (UCH)' },
    { code: 'MPM', name: 'Municipal Property (MPM)' },
    { code: 'FIN', name: 'Finance & Accounting (FIN)' },
    { code: 'HRM', name: 'Payroll & HR (HRM)' },
    { code: 'DMS', name: 'Document Management (DMS)' },
    { code: 'INV', name: 'Inventory & Stores (INV)' },
    { code: 'BPM', name: 'Building Permissions (BPM)' },
    { code: 'TPL', name: 'Town Planning (TPL)' },
    { code: 'LGL', name: 'Legal Cases (LGL)' },
    { code: 'FNC', name: 'Fire NOC (FNC)' },
    { code: 'SWM', name: 'Solid Waste (SWM)' },
    { code: 'ENG', name: 'Engineering Projects (ENG)' },
    { code: 'SLM', name: 'Street Lights (SLM)' },
    { code: 'PRK', name: 'Parks & Horticulture (PRK)' },
    { code: 'GRV', name: 'Citizen Grievance & RTI (GRV)' },
    { code: 'GSC', name: 'Government Schemes (GSC)' },
  ];

  ngOnInit(): void {
    this.loadRoles();
    this.loadTemplates();
    this.loadMatrix();
  }

  // ---- Live matrix (the module's real PERMISSIONS dict) ------------------------------------------------

  loadMatrix(): void {
    this.isLoadingMatrix.set(true);
    this.pendingChanges.set({});
    this.permissionMatrixService.getMatrix(this.selectedModule()).subscribe({
      next: (m) => {
        this.isLoadingMatrix.set(false);
        this.matrix.set(m);
      },
      error: () => {
        this.isLoadingMatrix.set(false);
        this.matrix.set(null);
        this.dialogs.showToast('Failed to load the permission matrix', 'error');
      },
    });
  }

  onModuleChange(code: string): void {
    this.selectedModule.set(code);
    this.loadMatrix();
  }

  /** The header's one Refresh button, aware of which tab is actually showing. */
  refresh(): void {
    if (this.activeTab() === 'matrix') {
      this.loadMatrix();
    } else {
      this.loadRoles();
      this.onRoleChange(this.selectedRoleId());
    }
  }

  /** What the checkbox for this role should show right now: a pending edit if there is one, else the saved state. */
  isEffective(row: PermissionRow, role: string): boolean {
    const pending = this.pendingChanges()[`${row.key}::${role}`];
    if (pending) return pending.granted === null ? row.defaultRoles.includes(role) : !!pending.granted;
    return row.effectiveRoles.includes(role);
  }

  /** Whether this cell differs from the role's hardcoded default right now (saved override, or a pending one). */
  isOverridden(row: PermissionRow, role: string): boolean {
    const pending = this.pendingChanges()[`${row.key}::${role}`];
    if (pending) return pending.granted !== null;
    return row.overrides.some((o) => o.role === role);
  }

  isAdminRole(role: string): boolean {
    return role === 'super_admin' || role === 'system_admin';
  }

  toggleCell(row: PermissionRow, role: string): void {
    if (this.isAdminRole(role)) return; // the platform bypass is absolute and never overridable
    const key = `${row.key}::${role}`;
    const newValue = !this.isEffective(row, role);
    const isDefault = row.defaultRoles.includes(role);
    this.pendingChanges.update((changes) => {
      const next = { ...changes };
      if (newValue === isDefault) {
        // back to the hardcoded default: only a real change if there was a saved override to clear
        if (row.overrides.some((o) => o.role === role)) next[key] = { permissionKey: row.key, role, granted: null };
        else delete next[key];
      } else {
        next[key] = { permissionKey: row.key, role, granted: newValue };
      }
      return next;
    });
  }

  /** Explicitly clears an override back to the default, whatever the checkbox is currently showing. */
  revertCell(row: PermissionRow, role: string): void {
    const key = `${row.key}::${role}`;
    this.pendingChanges.update((changes) => ({ ...changes, [key]: { permissionKey: row.key, role, granted: null } }));
  }

  saveLiveMatrix(): void {
    const changes = Object.values(this.pendingChanges());
    if (!changes.length) return;
    this.isSavingMatrix.set(true);
    this.loading.show('Publishing permission changes...');
    this.permissionMatrixService.saveOverrides(this.selectedModule(), changes).subscribe({
      next: (m) => {
        this.isSavingMatrix.set(false);
        this.loading.hide();
        this.matrix.set(m);
        this.pendingChanges.set({});
        this.dialogs.showToast(`Permissions updated for ${this.selectedModule()}.`, 'success');
      },
      error: (err) => {
        this.isSavingMatrix.set(false);
        this.loading.hide();
        this.dialogs.showToast(err?.error?.detail || 'Failed to save permission changes', 'error');
      },
    });
  }

  loadRoles(): void {
    this.isLoading.set(true);
    this.loading.show('Loading municipal roles & policies...');
    this.rbacService.getRoles().subscribe({
      next: (res) => {
        this.isLoading.set(false);
        this.loading.hide();
        if (res.success && res.data) {
          this.roles.set(res.data);
          if (!this.selectedRoleId() && res.data.length > 0) {
            this.selectedRoleId.set(res.data[0].id);
            this.loadPermissionsForRole(res.data[0].id);
          }
        }
      },
      error: () => {
        this.isLoading.set(false);
        this.loading.hide();
        this.dialogs.showToast('Failed to load roles', 'error');
      }
    });
  }

  loadTemplates(): void {
    this.rbacService.getRoleTemplates().subscribe({
      next: (res) => {
        if (res.success && res.data) {
          this.roleTemplates.set(res.data);
        }
      }
    });
  }

  loadPermissionsForRole(roleId: string): void {
    if (!roleId) return;
    this.loading.show('Loading permission matrix...');
    this.rbacService.getRolePermissions(roleId, this.moduleFilter()).subscribe({
      next: (res) => {
        this.loading.hide();
        if (res.success && res.data) {
          this.permissions.set(res.data);
          this.hasPendingChanges.set(false);
        }
      },
      error: () => {
        this.loading.hide();
        this.dialogs.showToast('Failed to load permission matrix', 'error');
      }
    });
  }

  onRoleChange(roleId: string): void {
    this.selectedRoleId.set(roleId);
    this.loadPermissionsForRole(roleId);
  }

  viewPermissionMatrix(roleId: string): void {
    this.onRoleChange(roleId);
    this.activeTab.set('matrix');
    this.router.navigate(['/admin'], {
      queryParams: { section: 'iam-rbac', item: 'IAM-04' }
    });
  }

  onModuleFilterChange(mod: string): void {
    this.moduleFilter.set(mod);
    this.loadPermissionsForRole(this.selectedRoleId());
  }

  get currentRole(): RoleItem | undefined {
    return this.roles().find(r => r.id === this.selectedRoleId());
  }

  get filteredPermissions(): RolePermissionItem[] {
    const q = this.searchQuery().toLowerCase().trim();
    return this.permissions().filter(p => {
      if (!q) return true;
      return (
        p.componentCode.toLowerCase().includes(q) ||
        p.moduleCode.toLowerCase().includes(q) ||
        p.dataScope.toLowerCase().includes(q)
      );
    });
  }

  // Pagination - Matrix Tab
  readonly matrixPage = signal<number>(1);
  readonly matrixPageSize = signal<number>(25);
  readonly matrixPageSizeOptions = [10, 25, 50, 100];

  readonly paginatedPermissions = computed(() => {
    const list = this.filteredPermissions;
    const start = (this.matrixPage() - 1) * this.matrixPageSize();
    return list.slice(start, start + this.matrixPageSize());
  });

  readonly matrixTotalPages = computed(() => {
    const total = Math.ceil(this.filteredPermissions.length / this.matrixPageSize());
    return total > 0 ? total : 1;
  });

  readonly matrixStartIndex = computed(() => {
    if (this.filteredPermissions.length === 0) return 0;
    return (this.matrixPage() - 1) * this.matrixPageSize() + 1;
  });

  readonly matrixEndIndex = computed(() => {
    const end = this.matrixPage() * this.matrixPageSize();
    return Math.min(end, this.filteredPermissions.length);
  });

  readonly matrixPagesArray = computed(() => {
    const pages: number[] = [];
    const total = this.matrixTotalPages();
    const curr = this.matrixPage();
    let start = Math.max(1, curr - 2);
    let end = Math.min(total, start + 4);
    if (end - start < 4) {
      start = Math.max(1, end - 4);
    }
    for (let i = start; i <= end; i++) {
      pages.push(i);
    }
    return pages;
  });

  prevMatrixPage(): void {
    if (this.matrixPage() > 1) {
      this.matrixPage.update(p => p - 1);
    }
  }

  nextMatrixPage(): void {
    if (this.matrixPage() < this.matrixTotalPages()) {
      this.matrixPage.update(p => p + 1);
    }
  }

  goToMatrixPage(page: number): void {
    if (page >= 1 && page <= this.matrixTotalPages()) {
      this.matrixPage.set(page);
    }
  }

  onMatrixPageSizeChange(size: number): void {
    this.matrixPageSize.set(Number(size));
    this.matrixPage.set(1);
  }

  // Pagination - Directory Tab
  readonly directorySearchQuery = signal<string>('');
  readonly directoryLevelFilter = signal<string>('ALL');
  readonly directoryPage = signal<number>(1);
  readonly directoryPageSize = signal<number>(10);
  readonly directoryPageSizeOptions = [10, 25, 50];

  readonly filteredRoles = computed(() => {
    const q = this.directorySearchQuery().toLowerCase().trim();
    const lvl = this.directoryLevelFilter();
    return this.roles().filter(r => {
      const matchQ = !q ||
        r.roleName.toLowerCase().includes(q) ||
        r.roleCode.toLowerCase().includes(q) ||
        r.scopeType.toLowerCase().includes(q) ||
        (r.description && r.description.toLowerCase().includes(q));
      const matchLvl = lvl === 'ALL' || r.roleLevel === lvl;
      return matchQ && matchLvl;
    });
  });

  readonly paginatedRoles = computed(() => {
    const list = this.filteredRoles();
    const start = (this.directoryPage() - 1) * this.directoryPageSize();
    return list.slice(start, start + this.directoryPageSize());
  });

  readonly directoryTotalPages = computed(() => {
    const total = Math.ceil(this.filteredRoles().length / this.directoryPageSize());
    return total > 0 ? total : 1;
  });

  readonly directoryStartIndex = computed(() => {
    if (this.filteredRoles().length === 0) return 0;
    return (this.directoryPage() - 1) * this.directoryPageSize() + 1;
  });

  readonly directoryEndIndex = computed(() => {
    const end = this.directoryPage() * this.directoryPageSize();
    return Math.min(end, this.filteredRoles().length);
  });

  readonly directoryPagesArray = computed(() => {
    const pages: number[] = [];
    const total = this.directoryTotalPages();
    const curr = this.directoryPage();
    let start = Math.max(1, curr - 2);
    let end = Math.min(total, start + 4);
    if (end - start < 4) {
      start = Math.max(1, end - 4);
    }
    for (let i = start; i <= end; i++) {
      pages.push(i);
    }
    return pages;
  });

  prevDirectoryPage(): void {
    if (this.directoryPage() > 1) {
      this.directoryPage.update(p => p - 1);
    }
  }

  nextDirectoryPage(): void {
    if (this.directoryPage() < this.directoryTotalPages()) {
      this.directoryPage.update(p => p + 1);
    }
  }

  goToDirectoryPage(page: number): void {
    if (page >= 1 && page <= this.directoryTotalPages()) {
      this.directoryPage.set(page);
    }
  }

  onDirectoryPageSizeChange(size: number): void {
    this.directoryPageSize.set(Number(size));
    this.directoryPage.set(1);
  }

  markPermissionChanged(): void {
    this.hasPendingChanges.set(true);
  }

  saveMatrix(): void {
    const roleId = this.selectedRoleId();
    if (!roleId) return;

    this.isSavingMatrix.set(true);
    this.loading.show('Enforcing & publishing RBAC matrix changes...');
    this.rbacService.updateRolePermissions(roleId, { permissions: this.permissions() }).subscribe({
      next: (res) => {
        this.isSavingMatrix.set(false);
        this.loading.hide();
        if (res.success) {
          this.hasPendingChanges.set(false);
          this.dialogs.showToast(`RBAC matrix published for '${this.currentRole?.roleName}'`, 'success');
        }
      },
      error: () => {
        this.isSavingMatrix.set(false);
        this.loading.hide();
        this.dialogs.showToast('Failed to save matrix permissions', 'error');
      }
    });
  }

  // Dialog Handlers
  openCreateRoleDialog(): void {
    this.roleToEdit.set(null);
    this.isCreateDialogOpen.set(true);
  }

  openEditRoleDialog(role: RoleItem): void {
    this.roleToEdit.set(role);
    this.isCreateDialogOpen.set(true);
  }

  closeCreateDialog(): void {
    this.isCreateDialogOpen.set(false);
    this.roleToEdit.set(null);
  }

  onRoleSaved(): void {
    this.closeCreateDialog();
    this.loadRoles();
  }

  openCompareDialog(): void {
    this.isCompareDialogOpen.set(true);
  }

  closeCompareDialog(): void {
    this.isCompareDialogOpen.set(false);
  }

  openCopyDialog(): void {
    this.isCopyDialogOpen.set(true);
  }

  closeCopyDialog(): void {
    this.isCopyDialogOpen.set(false);
  }

  onPermissionsCopied(): void {
    this.closeCopyDialog();
    this.loadPermissionsForRole(this.selectedRoleId());
  }

  async deleteRole(role: RoleItem): Promise<void> {
    const confirmed = await this.dialogs.confirm({
      title: 'Delete Role',
      message: `Are you sure you want to delete role '${role.roleName}'? This will revoke access for any assigned users.`,
      confirmText: 'Delete Role',
      variant: 'destructive'
    });

    if (confirmed) {
      this.loading.show(`Deleting ${role.roleName}...`);
      this.rbacService.deleteRole(role.id).subscribe({
        next: (res) => {
          this.loading.hide();
          if (res.success) {
            this.dialogs.showToast(`Role '${role.roleName}' deleted`, 'success');
            this.loadRoles();
          }
        },
        error: (err) => {
          this.loading.hide();
          this.dialogs.showToast(err?.error?.detail || 'Failed to delete role', 'error');
        }
      });
    }
  }

  cloneTemplate(template: RoleItem): void {
    this.roleToEdit.set({
      ...template,
      id: '',
      roleName: `${template.roleName} (Copy)`,
      roleCode: `${template.roleCode}_COPY`,
      isSystem: false,
      isTemplate: false
    });
    this.isCreateDialogOpen.set(true);
  }
}
