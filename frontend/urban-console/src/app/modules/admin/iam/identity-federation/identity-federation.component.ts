import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { IconComponent } from '../../../../shared/components/icon/icon.component';
import { IamSsoService } from '../../../../core/services/iam-sso.service';
import { DialogService } from '../../../../core/services/dialog.service';
import { LoadingService } from '../../../../core/services/loading.service';
import { IdentityProvider } from '../../../../core/models/iam-sso.model';
import { IdpFormDialogComponent } from '../dialogs/idp-form-dialog/idp-form-dialog.component';

@Component({
  selector: 'app-identity-federation',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent, IdpFormDialogComponent],
  templateUrl: './identity-federation.component.html',
  styleUrl: './identity-federation.component.scss'
})
export class IdentityFederationComponent implements OnInit {
  private ssoService = inject(IamSsoService);
  private dialogs = inject(DialogService);
  private loading = inject(LoadingService);

  readonly idps = signal<IdentityProvider[]>([]);
  readonly searchQuery = signal<string>('');
  readonly protocolFilter = signal<string>('ALL');
  readonly isTestingAll = signal<boolean>(false);

  // Dialog state
  readonly isFormDialogOpen = signal<boolean>(false);
  readonly selectedIdp = signal<IdentityProvider | null>(null);

  ngOnInit(): void {
    this.loadIdps();
  }

  loadIdps(): void {
    this.loading.show('Loading Federated Identity Providers...');
    this.ssoService.getIdentityProviders().subscribe({
      next: (data) => {
        this.loading.hide();
        this.idps.set(data);
      },
      error: () => {
        this.loading.hide();
        this.dialogs.showToast('Failed to load identity providers', 'error');
      }
    });
  }

  get filteredIdps(): IdentityProvider[] {
    const q = this.searchQuery().toLowerCase().trim();
    const proto = this.protocolFilter();
    return this.idps().filter(idp => {
      const matchQ = !q || idp.name.toLowerCase().includes(q) || idp.issuerUrl.toLowerCase().includes(q);
      const matchProto = proto === 'ALL' || idp.protocol === proto;
      return matchQ && matchProto;
    });
  }

  // Pagination
  readonly page = signal<number>(1);
  readonly pageSize = signal<number>(10);
  readonly pageSizeOptions = [5, 10, 25];

  readonly paginatedIdps = computed(() => {
    const list = this.filteredIdps;
    const start = (this.page() - 1) * this.pageSize();
    return list.slice(start, start + this.pageSize());
  });

  readonly totalPages = computed(() => {
    const total = Math.ceil(this.filteredIdps.length / this.pageSize());
    return total > 0 ? total : 1;
  });

  readonly startIndex = computed(() => {
    if (this.filteredIdps.length === 0) return 0;
    return (this.page() - 1) * this.pageSize() + 1;
  });

  readonly endIndex = computed(() => {
    const end = this.page() * this.pageSize();
    return Math.min(end, this.filteredIdps.length);
  });

  readonly pagesArray = computed(() => {
    const pages: number[] = [];
    const total = this.totalPages();
    const curr = this.page();
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

  prevPage(): void {
    if (this.page() > 1) {
      this.page.update(p => p - 1);
    }
  }

  nextPage(): void {
    if (this.page() < this.totalPages()) {
      this.page.update(p => p + 1);
    }
  }

  goToPage(page: number): void {
    if (page >= 1 && page <= this.totalPages()) {
      this.page.set(page);
    }
  }

  onPageSizeChange(size: number): void {
    this.pageSize.set(Number(size));
    this.page.set(1);
  }

  openCreateDialog(): void {
    this.selectedIdp.set(null);
    this.isFormDialogOpen.set(true);
  }

  openEditDialog(idp: IdentityProvider): void {
    this.selectedIdp.set(idp);
    this.isFormDialogOpen.set(true);
  }

  closeFormDialog(): void {
    this.isFormDialogOpen.set(false);
    this.selectedIdp.set(null);
  }

  onFormSaved(): void {
    this.closeFormDialog();
    this.loadIdps();
  }

  toggleActive(idp: IdentityProvider): void {
    this.loading.show(`Updating ${idp.name}...`);
    this.ssoService.toggleIdentityProvider(idp.id).subscribe({
      next: (updated) => {
        this.loading.hide();
        this.dialogs.showToast(`${updated.name} is now ${updated.isActive ? 'Active' : 'Inactive'}`, 'success');
        this.loadIdps();
      },
      error: () => {
        this.loading.hide();
        this.dialogs.showToast('Failed to update provider status', 'error');
      }
    });
  }

  async deleteIdp(idp: IdentityProvider): Promise<void> {
    const confirmed = await this.dialogs.confirm({
      title: 'Remove Identity Provider',
      message: `Are you sure you want to remove '${idp.name}'? Users linked to this IDP will not be able to log in via federation.`,
      confirmText: 'Remove Provider',
      variant: 'destructive'
    });

    if (confirmed) {
      this.loading.show(`Removing ${idp.name}...`);
      this.ssoService.deleteIdentityProvider(idp.id).subscribe({
        next: () => {
          this.loading.hide();
          this.dialogs.showToast(`Provider '${idp.name}' removed`, 'success');
          this.loadIdps();
        },
        error: () => {
          this.loading.hide();
          this.dialogs.showToast('Failed to remove provider', 'error');
        }
      });
    }
  }

  testAllBrokers(): void {
    this.isTestingAll.set(true);
    this.ssoService.testConnection().subscribe({
      next: (res) => {
        this.isTestingAll.set(false);
        if (res.success) {
          this.dialogs.showToast(
            `Keycloak SSO broker connection verified (Status: ${res.status})`,
            'success',
            3000
          );
        } else {
          this.dialogs.showToast(
            res.message || 'Federation broker connection test failed',
            'error',
            3500
          );
        }
      },
      error: (err) => {
        this.isTestingAll.set(false);
        this.dialogs.showToast(
          err.error?.detail || 'Failed to connect to federation broker endpoint',
          'error',
          3500
        );
      }
    });
  }
}
