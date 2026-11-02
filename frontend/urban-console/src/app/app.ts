import { Component, effect, inject, signal, untracked } from '@angular/core';
import { RouterOutlet, RouterModule, Router, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { KeycloakAuthService } from './core/services/keycloak.service';
import { PropertyService } from './core/services/property.service';
import { AppSwitcherComponent } from './shared/components/app-switcher/app-switcher.component';
import { IconComponent } from './shared/components/icon/icon.component';
import { GlobalDialogsComponent } from './shared/components/dialogs/global-dialogs.component';
import { GlobalLoaderComponent } from './shared/components/global-loader/global-loader.component';
import { SuperAdminSidebarComponent } from './shared/components/super-admin-sidebar/super-admin-sidebar.component';
import { TenantInfo } from './core/models/property.model';

@Component({
  imports: [
    RouterOutlet,
    RouterModule,
    CommonModule,
    FormsModule,
    AppSwitcherComponent,
    IconComponent,
    GlobalDialogsComponent,
    GlobalLoaderComponent,
    SuperAdminSidebarComponent,
  ],
  selector: 'app-root',
  styleUrl: './app.scss',
  templateUrl: './app.html',
})
export class App {
  public authService = inject(KeycloakAuthService);
  public propertyService = inject(PropertyService);
  public router = inject(Router);

  public isMobileSidebarOpen = signal<boolean>(false);
  /** Property Tax pages have their own sidebar, so the platform sidebar is left out there. */
  public isPtxRoute = signal<boolean>(false);
  public isSidebarCollapsed = signal<boolean>(false);
  public isTenantDropdownOpen = signal<boolean>(false);
  public isProfileMenuOpen = signal<boolean>(false);
  public isNotificationMenuOpen = signal<boolean>(false);
  public unreadNotificationCount = signal<number>(3);
  public showNewTenantModal = signal<boolean>(false);
  public isSubmittingTenant = signal<boolean>(false);
  public isSuperAdminView = signal<boolean>(false);
  public isWaterRoute = signal<boolean>(false);

  constructor() {
    if (
      this.authService.isSuperAdmin() &&
      (window.location.pathname === '/' || window.location.pathname === '/dashboard')
    ) {
      this.router.navigate(['/admin']);
    }

    this.router.events
      .pipe(filter((e): e is NavigationEnd => e instanceof NavigationEnd))
      .subscribe((e) => {
        this.isWaterRoute.set(e.urlAfterRedirects.startsWith('/modules/wtr') || e.urlAfterRedirects.startsWith('/modules/ptx'));
        this.isPtxRoute.set(e.urlAfterRedirects.startsWith('/modules/ptx'));
      });

    // Module 2 (WTR) has its own screens: open them when WTR is picked in the launcher, leave them when another module is picked
    let previous = this.authService.activeModule().code;
    effect(() => {
      const code = this.authService.activeModule().code;
      if (code === previous) return;
      previous = code;
      untracked(() => {
        const onWater = this.router.url.startsWith('/modules/wtr');
        const onPtx = this.router.url.startsWith('/modules/ptx');
        if (code === 'WTR' && !onWater) this.router.navigate(['/modules/wtr']);
        else if (code === 'PTX' && !onPtx && !this.authService.isSuperAdmin()) this.router.navigate(['/modules/ptx']);
        else if (code !== 'WTR' && onWater) this.router.navigate(['/dashboard']);
        else if (code !== 'PTX' && onPtx) this.router.navigate(['/dashboard']);
      });
    });
  }

  toggleSidebarCollapse(): void {
    this.isSidebarCollapsed.update((v) => !v);
  }

  toggleNotificationMenu(): void {
    this.isNotificationMenuOpen.update((v) => !v);
  }

  closeNotificationMenu(): void {
    this.isNotificationMenuOpen.set(false);
  }

  clearNotifications(): void {
    this.unreadNotificationCount.set(0);
  }

  toggleProfileMenu(): void {
    this.isProfileMenuOpen.update((v) => !v);
  }

  closeProfileMenu(): void {
    this.isProfileMenuOpen.set(false);
  }

  toggleSuperAdminView(): void {
    const next = !this.isSuperAdminView();
    this.isSuperAdminView.set(next);
    if (next) {
      this.router.navigate(['/admin']);
    } else {
      this.router.navigate(['/dashboard']);
    }
  }

  // New SaaS Tenant Onboarding Form Model
  public newTenant = {
    tenantId: '',
    name: '',
    stateCode: 'TG',
    district: '',
  };

  get isAuthPage(): boolean {
    return this.router.url.includes('/login');
  }

  toggleSidebar(): void {
    if (this.isPtxRoute()) {
      window.dispatchEvent(new CustomEvent('urban:ptx-nav'));
      return;
    }
    this.isMobileSidebarOpen.update((v) => !v);
  }

  closeSidebar(): void {
    this.isMobileSidebarOpen.set(false);
  }

  toggleTenantDropdown(): void {
    this.isTenantDropdownOpen.update((v) => !v);
  }

  closeTenantDropdown(): void {
    this.isTenantDropdownOpen.set(false);
  }

  selectTenant(tenant: TenantInfo): void {
    this.authService.switchTenant(tenant);
    this.isTenantDropdownOpen.set(false);
  }

  openNewTenantModal(): void {
    this.isTenantDropdownOpen.set(false);
    this.newTenant = { tenantId: '', name: '', stateCode: 'TG', district: '' };
    this.showNewTenantModal.set(true);
  }

  closeNewTenantModal(): void {
    this.showNewTenantModal.set(false);
  }

  submitNewTenant(): void {
    if (!this.newTenant.tenantId || !this.newTenant.name || !this.newTenant.district) {
      alert('Please fill all required tenant fields.');
      return;
    }

    this.isSubmittingTenant.set(true);
    this.propertyService.createTenant(this.newTenant).subscribe({
      next: (created) => {
        this.isSubmittingTenant.set(false);
        this.showNewTenantModal.set(false);
        this.authService.loadTenants();
        this.authService.switchTenant(created);
      },
      error: (err) => {
        this.isSubmittingTenant.set(false);
        alert(err.error?.detail || 'Failed to provision tenant.');
      },
    });
  }

  logout(): void {
    this.authService.logout();
    this.router.navigate(['/login']);
  }
}
