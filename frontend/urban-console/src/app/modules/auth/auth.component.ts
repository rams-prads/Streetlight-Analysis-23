import { Component, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import {
  KeycloakAuthService,
  AccessibleTenant,
  AccessibleUlb,
} from '../../core/services/keycloak.service';
import { LoadingService } from '../../core/services/loading.service';
import { IconComponent } from '../../shared/components/icon/icon.component';
import { APP_VERSION } from '../../core/constants/version';

export interface DemoPersona {
  title: string;
  username: string;
  role: string;
  badge: string;
  icon: string;
}

@Component({
  selector: 'app-auth',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './auth.component.html',
  styleUrl: './auth.component.scss',
})
export class AuthComponent {
  private authService = inject(KeycloakAuthService);
  private router = inject(Router);
  public loadingService = inject(LoadingService);
  readonly appVersion = APP_VERSION;

  // Authentication Stepper: 'credentials' -> 'tenant-select' -> 'ulb-select'
  readonly authStep = signal<'credentials' | 'tenant-select' | 'ulb-select'>('credentials');

  isSignUp = signal<boolean>(false);
  isLoading = signal<boolean>(false);
  showPassword = signal<boolean>(false);
  rememberMe = signal<boolean>(true);
  errorMessage = signal<string>('');
  successMessage = signal<string>('');

  // Tenancy Hierarchy State
  readonly accessibleTenants = signal<AccessibleTenant[]>([]);
  readonly selectedTenant = signal<AccessibleTenant | null>(null);
  readonly selectedUlb = signal<AccessibleUlb | null>(null);

  // Search Filters
  tenantSearch = signal<string>('');
  ulbSearch = signal<string>('');

  // Quick Demo Personas
  readonly demoPersonas: DemoPersona[] = [
    {
      title: 'Platform Super Admin',
      username: 'admin@urban.gov.in',
      role: 'Platform Super Admin (Level 0)',
      badge: 'All States & ULBs',
      icon: 'ri-shield-user-line',
    },
    {
      title: 'State Municipal Director',
      username: 'suresh.director@telangana.gov.in',
      role: 'State Director (Level 1)',
      badge: 'Telangana Directorate',
      icon: 'ri-government-line',
    },
    {
      title: 'GWMC Revenue Inspector',
      username: 'officer@gwmc.gov.in',
      role: 'Revenue Officer (Level 2)',
      badge: 'Greater Warangal',
      icon: 'ri-file-list-3-line',
    },
    {
      title: 'Town Planning Officer',
      username: 'planner@gwmc.gov.in',
      role: 'Town Planner (TS-bPASS)',
      badge: 'Building Permissions',
      icon: 'ri-community-line',
    },
  ];

  // Production Sign In Form Model
  signInData = {
    userName: '',
    password: '',
  };

  // User Registration Form Model
  signUpData = {
    fullName: '',
    email: '',
    username: '',
    password: '',
    role: 'citizen',
    assignedZone: '',
    assignedWard: '',
  };

  // Filtered State Tenants
  readonly filteredTenants = computed(() => {
    const q = this.tenantSearch().trim().toLowerCase();
    const list = this.accessibleTenants();
    if (!q) return list;
    return list.filter(
      (t) =>
        t.stateName.toLowerCase().includes(q) ||
        t.stateCode.toLowerCase().includes(q) ||
        t.ulbs.some(
          (u) =>
            u.name.toLowerCase().includes(q) ||
            u.code.toLowerCase().includes(q) ||
            (u.district && u.district.toLowerCase().includes(q)),
        ),
    );
  });

  // Filtered ULBs
  readonly filteredUlbs = computed(() => {
    const t = this.selectedTenant();
    if (!t) return [];
    const q = this.ulbSearch().trim().toLowerCase();
    if (!q) return t.ulbs;
    return t.ulbs.filter(
      (u) =>
        u.name.toLowerCase().includes(q) ||
        u.code.toLowerCase().includes(q) ||
        (u.district && u.district.toLowerCase().includes(q)),
    );
  });

  fillPersona(p: DemoPersona): void {
    this.signInData.userName = p.username;
    this.signInData.password = '';
    this.errorMessage.set('');
    this.successMessage.set(`Selected persona ${p.title} (${p.username})`);
  }

  toggleMode(signUp: boolean): void {
    this.isSignUp.set(signUp);
    this.authStep.set('credentials');
    this.errorMessage.set('');
    this.successMessage.set('');
  }

  toggleShowPassword(): void {
    this.showPassword.update((v) => !v);
  }

  private extractErrorMessage(err: any, fallback: string): string {
    if (!err) return fallback;
    const detail = err.error?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d: any) => {
          if (typeof d === 'string') return d;
          if (d?.msg) {
            const loc = Array.isArray(d.loc)
              ? d.loc.filter((l: string) => l !== 'body').join('.')
              : '';
            return loc ? `${loc}: ${d.msg}` : d.msg;
          }
          return JSON.stringify(d);
        })
        .join(', ');
    }
    if (typeof detail === 'object' && detail !== null) {
      return detail.msg || detail.message || JSON.stringify(detail);
    }
    if (typeof err.error === 'string') return err.error;
    if (err.message && typeof err.message === 'string') return err.message;
    return fallback;
  }

  onSignIn(): void {
    const identifier = this.signInData.userName?.trim();
    const password = this.signInData.password?.trim();

    if (!identifier || !password) {
      this.errorMessage.set('Please provide both official email/username and password.');
      return;
    }

    this.isLoading.set(true);
    this.errorMessage.set('');

    this.authService.signIn({ userName: identifier, password }).subscribe({
      next: (res) => {
        this.isLoading.set(false);
        const tenants: AccessibleTenant[] =
          res?.accessibleTenants || this.authService.accessibleTenants() || [];

        // Condition 2: If user has multiple tenants, show tenant selection
        if (tenants.length > 1) {
          this.accessibleTenants.set(tenants);
          this.authStep.set('tenant-select');
          this.successMessage.set('Authentication successful. Select your State Tenant context.');
        } else if (tenants.length === 1) {
          // Exactly 1 State Tenant: advance to check ULBs in that tenant
          this.accessibleTenants.set(tenants);
          this.selectTenant(tenants[0]);
        } else {
          // Fallback if no tenants explicitly returned
          this.navigateToWorkspace();
        }
      },
      error: (err) => {
        this.isLoading.set(false);
        this.errorMessage.set(
          this.extractErrorMessage(err, 'Authentication failed. Please verify credentials.'),
        );
      },
    });
  }

  selectTenant(t: AccessibleTenant): void {
    this.selectedTenant.set(t);
    this.errorMessage.set('');

    // Condition 3: Upon selecting a tenant, if user has multiple ULBs, show ULB selection
    if (t.ulbs && t.ulbs.length > 1) {
      this.authStep.set('ulb-select');
      this.successMessage.set(
        `State: ${t.stateName}. Choose your Municipal Corporation / ULB workspace.`,
      );
    } else if (t.ulbs && t.ulbs.length === 1) {
      this.selectUlb(t.ulbs[0]);
    } else {
      // No child ULBs: enter statewide directorate scope
      this.authService.setContext(t.stateCode, 'ALL', t.stateName, 'Statewide Directorate');
      this.navigateToWorkspace();
    }
  }

  selectUlb(u: AccessibleUlb): void {
    this.selectedUlb.set(u);
    const st = this.selectedTenant() || { stateCode: u.stateCode, stateName: u.stateCode };
    this.authService.setContext(st.stateCode, u.code, st.stateName, u.name);
    this.successMessage.set(`Activating workspace: ${u.name} (${st.stateName})...`);
    setTimeout(() => {
      this.navigateToWorkspace();
    }, 350);
  }

  selectStatewideDirectorate(): void {
    const st = this.selectedTenant() || { stateCode: 'TG', stateName: 'Telangana' };
    this.authService.setContext(st.stateCode, 'ALL', st.stateName, 'Statewide Directorate');
    this.successMessage.set(`Activating Statewide Directorate: ${st.stateName}...`);
    setTimeout(() => {
      this.navigateToWorkspace();
    }, 350);
  }

  navigateToWorkspace(): void {
    if (this.authService.isSuperAdmin()) {
      this.router.navigate(['/admin']);
    } else {
      this.router.navigate(['/dashboard']);
    }
  }

  backToCredentials(): void {
    this.authStep.set('credentials');
    this.errorMessage.set('');
    this.successMessage.set('');
  }

  backToTenants(): void {
    this.authStep.set('tenant-select');
    this.selectedUlb.set(null);
    this.errorMessage.set('');
    this.successMessage.set('');
  }

  onSignUp(): void {
    if (
      !this.signUpData.fullName?.trim() ||
      !this.signUpData.email?.trim() ||
      !this.signUpData.username?.trim() ||
      !this.signUpData.password?.trim()
    ) {
      this.errorMessage.set('Please complete all required fields.');
      return;
    }

    this.isLoading.set(true);
    this.errorMessage.set('');

    this.authService.signUp(this.signUpData).subscribe({
      next: () => {
        this.isLoading.set(false);
        this.successMessage.set('Account provisioned successfully. Redirecting to workspace...');
        setTimeout(() => {
          this.router.navigate(['/dashboard']);
        }, 800);
      },
      error: (err) => {
        this.isLoading.set(false);
        this.errorMessage.set(
          this.extractErrorMessage(err, 'Registration failed. Please review inputs.'),
        );
      },
    });
  }
}
