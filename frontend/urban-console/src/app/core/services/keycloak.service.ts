import { Injectable, signal, computed, inject } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable, tap, catchError, of } from 'rxjs';
import { TenantInfo } from '../models/property.model';

export interface UserProfile {
  id?: string;
  username: string;
  email?: string;
  name?: string;
  role: string;
  roles: string[];
  tenantId: string;
  assigned_modules: string[];
  assigned_zone?: string;
  assigned_ward?: string;
  token?: string;
}

export interface AccessibleUlb {
  code: string;
  name: string;
  ulbType: string;
  district?: string;
  stateCode: string;
}

export interface AccessibleTenant {
  stateCode: string;
  stateName: string;
  status: string;
  ulbs: AccessibleUlb[];
}

export interface ModuleMetadata {
  code: string;
  name: string;
  domain: string;
  phase: number;
  icon: string;
  description: string;
  hasAccess?: boolean;
  has_access?: boolean;
  route: string;
}

import { environment } from '../../../environments/environment';

@Injectable({
  providedIn: 'root',
})
export class KeycloakAuthService {
  private http = inject(HttpClient);
  private apiUrl = environment.apiUrl;

  // Signals
  public isAuthenticated = signal<boolean>(false);
  public userProfile = signal<UserProfile | null>(null);

  public isSuperAdmin = computed(() => {
    const role = this.userProfile()?.role;
    const roles = this.userProfile()?.roles || [];
    return role === 'super_admin' || roles.includes('super_admin');
  });

  // Multi-Tenant SaaS State
  // Level 1: State Tenant (e.g. TG, MH, TR)
  public activeTenant = signal<string>('');
  public activeTenantName = signal<string>('');

  // Level 2: Sub-Tenant ULB / City (e.g. GWMC, GHMC, PMC)
  public activeSubTenant = signal<string>('');
  public activeSubTenantName = signal<string>('');

  public accessibleTenants = signal<AccessibleTenant[]>([]);
  public availableTenants = signal<TenantInfo[]>([]);

  // Active module context (like active Google App)
  public activeModule = signal<ModuleMetadata>({
    code: 'PTX',
    name: 'Property Tax & Revenue Management',
    domain: 'Revenue & Billing',
    phase: 1,
    icon: 'ptx',
    description: 'ULPIN property assessment, demand notices, online tax collection, GIS sync',
    has_access: true,
    route: '/modules/ptx',
  });

  public userModules = signal<ModuleMetadata[]>([]);

  init(): void {
    const savedToken = localStorage.getItem('urban_token');
    const savedUser = localStorage.getItem('urban_user');
    const savedTenant = localStorage.getItem('urban_tenant');
    const savedTenantName = localStorage.getItem('urban_tenant_name');
    const savedSubTenant = localStorage.getItem('urban_sub_tenant');
    const savedSubTenantName = localStorage.getItem('urban_sub_tenant_name');

    if (savedTenant) {
      this.activeTenant.set(savedTenant);
    }
    if (savedTenantName) {
      this.activeTenantName.set(savedTenantName);
    }
    if (savedSubTenant) {
      this.activeSubTenant.set(savedSubTenant);
    }
    if (savedSubTenantName) {
      this.activeSubTenantName.set(savedSubTenantName);
    }

    if (savedToken && savedUser) {
      try {
        const parsed = JSON.parse(savedUser);
        this.isAuthenticated.set(true);
        if (parsed.tenantId && !savedTenant) {
          this.activeTenant.set(parsed.tenantId);
        }
        this.userProfile.set({
          ...parsed,
          token: savedToken,
          roles: [parsed.role],
        });
      } catch (e) {
        console.warn('Failed to restore saved session:', e);
      }
    }

    this.refreshModules();
    this.loadTenants();
  }

  getTenantId(): string {
    return this.activeTenant();
  }

  getSubTenantId(): string {
    return this.activeSubTenant();
  }

  setContext(stateCode: string, ulbCode: string, stateName?: string, ulbName?: string): void {
    const cleanState = (stateCode || '').trim().toUpperCase();
    const cleanUlb = (ulbCode || '').trim().toUpperCase();
    this.activeTenant.set(cleanState);
    this.activeSubTenant.set(cleanUlb);
    if (stateName) this.activeTenantName.set(stateName);
    if (ulbName) this.activeSubTenantName.set(ulbName);

    localStorage.setItem('urban_tenant', cleanState);
    localStorage.setItem('urban_sub_tenant', cleanUlb);
    if (stateName) localStorage.setItem('urban_tenant_name', stateName);
    if (ulbName) localStorage.setItem('urban_sub_tenant_name', ulbName);

    this.userProfile.update((u) => (u ? { ...u, tenantId: cleanUlb } : null));
    window.dispatchEvent(
      new CustomEvent('urban:tenant-changed', {
        detail: { tenantId: cleanState, subTenantId: cleanUlb },
      }),
    );
  }

  switchTenant(tenant: TenantInfo | string): void {
    const tId = typeof tenant === 'string' ? tenant : tenant.tenantId;
    const tName = typeof tenant === 'string' ? tenant : tenant.name;
    this.activeSubTenant.set(tId);
    this.activeSubTenantName.set(tName);
    localStorage.setItem('urban_sub_tenant', tId);
    this.userProfile.update((u) => (u ? { ...u, tenantId: tId } : null));
    window.dispatchEvent(new CustomEvent('urban:tenant-changed', { detail: { tenantId: this.activeTenant(), subTenantId: tId } }));
  }

  loadTenants(): void {
    this.http
      .get<TenantInfo[]>(`${this.apiUrl}/tenants`, { headers: this.getHeaders() })
      .pipe(
        catchError(() => of([])),
      )
      .subscribe((tenants) => {
        if (tenants && tenants.length > 0) {
          this.availableTenants.set(tenants);
          const match = tenants.find((t) => t.tenantId === this.activeTenant());
          if (match) {
            this.activeTenantName.set(match.name);
          }
        }
      });
  }

  getToken(): string | undefined {
    return localStorage.getItem('urban_token') || undefined;
  }

  getHeaders(): HttpHeaders {
    let headers = new HttpHeaders({
      'Content-Type': 'application/json',
      'X-Tenant-ID': this.activeTenant(),
      'X-Sub-Tenant-ID': this.activeSubTenant(),
    });
    const token = this.getToken();
    if (token) {
      headers = headers.set('Authorization', `Bearer ${token}`);
    }
    return headers;
  }

  signIn(payload: { userName: string; password: string }): Observable<any> {
    const body = {
      userName: payload.userName,
      password: payload.password,
    };
    return this.http.post<any>(`${this.apiUrl}/auth/signin`, body).pipe(
      tap((res) => {
        const token = res?.accessToken;
        if (token && res?.user) {
          localStorage.setItem('urban_token', token);
          localStorage.setItem('urban_user', JSON.stringify(res.user));

          this.isAuthenticated.set(true);
          this.userProfile.set({
            ...res.user,
            token: token,
            roles: [res.user.role],
            name: res.user.fullName,
          });

          if (res?.accessibleTenants && res.accessibleTenants.length > 0) {
            this.accessibleTenants.set(res.accessibleTenants);
          }

          const tId = res.user.tenantId;
          if (tId) {
            this.activeSubTenant.set(tId);
            localStorage.setItem('urban_sub_tenant', tId);
          }

          this.refreshModules();
        }
      }),
    );
  }

  signUp(payload: {
    fullName: string;
    username: string;
    email: string;
    password: string;
    role?: string;
    tenantId?: string;
    assignedZone?: string;
    assignedWard?: string;
  }): Observable<any> {
    const body = {
      username: payload.username,
      email: payload.email,
      password: payload.password,
      fullName: payload.fullName,
      role: payload.role || 'citizen',
      tenantId: payload.tenantId || this.activeTenant(),
      assignedZone: payload.assignedZone,
      assignedWard: payload.assignedWard,
    };
    return this.http.post<any>(`${this.apiUrl}/auth/signup`, body).pipe(
      tap((res) => {
        const token = res?.accessToken || res?.access_token;
        if (token && res?.user) {
          localStorage.setItem('urban_token', token);
          localStorage.setItem('urban_user', JSON.stringify(res.user));

          this.isAuthenticated.set(true);
          this.userProfile.set({
            ...res.user,
            token: token,
            roles: [res.user.role],
            name: res.user.fullName || res.user.full_name,
          });

          const tId = res.user.tenantId || res.user.tenant_id;
          if (tId) {
            this.activeTenant.set(tId);
            localStorage.setItem('urban_tenant', tId);
          }

          this.refreshModules();
        }
      }),
    );
  }

  logout(): void {
    localStorage.removeItem('urban_token');
    localStorage.removeItem('urban_user');
    this.isAuthenticated.set(false);
    this.userProfile.set(null);
  }

  refreshModules(): void {
    this.http
      .get<ModuleMetadata[]>(`${this.apiUrl}/auth/modules`, { headers: this.getHeaders() })
      .pipe(
        catchError(() => {
          // Fallback default 19 modules
          return of(this.getDefaultModules());
        }),
      )
      .subscribe((modules) => {
        this.userModules.set(modules);
        const current = modules.find((m) => m.code === this.activeModule().code);
        if (current) {
          this.activeModule.set(current);
        }
      });
  }

  switchModule(module: ModuleMetadata): boolean {
    const hasPerm = module.hasAccess ?? module.has_access ?? false;
    if (!hasPerm && !this.hasRole('super_admin')) {
      alert(
        `Access Restricted: You do not have permissions for ${module.name} (${module.code}). Contact your Municipal Administrator.`,
      );
      return false;
    }
    this.activeModule.set(module);
    return true;
  }

  canAccessModule(code: string): boolean {
    if (this.hasRole('super_admin')) return true;
    const modules = this.userProfile()?.assigned_modules || [];
    return modules.includes(code);
  }

  hasRole(role: string): boolean {
    return this.userProfile()?.roles?.includes(role) ?? false;
  }

  private getDefaultModules(): ModuleMetadata[] {
    const assigned = this.userProfile()?.assigned_modules || ['PTX', 'WTR', 'GRV'];
    return [
      {
        code: 'PTX',
        name: 'Property Tax & Revenue',
        domain: 'Revenue & Billing',
        phase: 1,
        icon: 'ptx',
        description: 'ULPIN property assessment & tax',
        has_access: assigned.includes('PTX'),
        route: '/modules/ptx',
      },
      {
        code: 'WTR',
        name: 'Water & Utility Billing',
        domain: 'Revenue & Billing',
        phase: 1,
        icon: 'wtr',
        description: 'Water tap connections & meters',
        has_access: assigned.includes('WTR'),
        route: '/modules/wtr',
      },
      {
        code: 'GRV',
        name: 'Citizen Desk & Grievance',
        domain: 'Citizen Welfare',
        phase: 1,
        icon: 'grv',
        description: 'Grievances & RTI management',
        has_access: assigned.includes('GRV'),
        route: '/modules/grv',
      },
      {
        code: 'FIN',
        name: 'Finance & Accounting',
        domain: 'Finance & Admin',
        phase: 1,
        icon: 'fin',
        description: 'Double-entry municipal ledger',
        has_access: assigned.includes('FIN'),
        route: '/modules/fin',
      },
      {
        code: 'DMS',
        name: 'Document Management',
        domain: 'Finance & Admin',
        phase: 1,
        icon: 'dms',
        description: 'Digital records & OCR dossiers',
        has_access: assigned.includes('DMS'),
        route: '/modules/dms',
      },
      {
        code: 'TRL',
        name: 'Trade Licence',
        domain: 'Revenue & Billing',
        phase: 2,
        icon: 'trl',
        description: 'Trade registrations & renewals',
        has_access: assigned.includes('TRL'),
        route: '/modules/trl',
      },
      {
        code: 'UCH',
        name: 'User Charges',
        domain: 'Revenue & Billing',
        phase: 2,
        icon: 'uch',
        description: 'Sanitation & local fees',
        has_access: assigned.includes('UCH'),
        route: '/modules/uch',
      },
      {
        code: 'BPM',
        name: 'Building Permissions',
        domain: 'Planning & Regulation',
        phase: 2,
        icon: 'bpm',
        description: 'TS-bPASS building permits',
        has_access: assigned.includes('BPM'),
        route: '/modules/bpm',
      },
      {
        code: 'TPL',
        name: 'Town Planning',
        domain: 'Planning & Regulation',
        phase: 2,
        icon: 'tpl',
        description: 'Zoning & layout sanctions',
        has_access: assigned.includes('TPL'),
        route: '/modules/tpl',
      },
      {
        code: 'FNC',
        name: 'Fire NOC',
        domain: 'Planning & Regulation',
        phase: 2,
        icon: 'fnc',
        description: 'Fire safety clearances',
        has_access: assigned.includes('FNC'),
        route: '/modules/fnc',
      },
      {
        code: 'SWM',
        name: 'Solid Waste Management',
        domain: 'Field Ops',
        phase: 3,
        icon: 'swm',
        description: 'Door-to-door RFID sanitation',
        has_access: assigned.includes('SWM'),
        route: '/modules/swm',
      },
      {
        code: 'ENG',
        name: 'Engineering Projects',
        domain: 'Field Ops',
        phase: 3,
        icon: 'eng',
        description: 'e-MB works & civil tenders',
        has_access: assigned.includes('ENG'),
        route: '/modules/eng',
      },
      {
        code: 'SLM',
        name: 'Street Lights',
        domain: 'Field Ops',
        phase: 3,
        icon: 'slm',
        description: 'CCMS pole fault repair',
        has_access: assigned.includes('SLM'),
        route: '/modules/slm',
      },
      {
        code: 'PRK',
        name: 'Parks & Horticulture',
        domain: 'Field Ops',
        phase: 3,
        icon: 'prk',
        description: 'Green budget & tree census',
        has_access: assigned.includes('PRK'),
        route: '/modules/prk',
      },
      {
        code: 'INV',
        name: 'Inventory & Stores',
        domain: 'Finance & Admin',
        phase: 3,
        icon: 'inv',
        description: 'Central stores & GeM indents',
        has_access: assigned.includes('INV'),
        route: '/modules/inv',
      },
      {
        code: 'HRM',
        name: 'Payroll & HR',
        domain: 'Finance & Admin',
        phase: 4,
        icon: 'hrm',
        description: 'Biometric rosters & payroll',
        has_access: assigned.includes('HRM'),
        route: '/modules/hrm',
      },
      {
        code: 'MPM',
        name: 'Municipal Property',
        domain: 'Revenue & Billing',
        phase: 4,
        icon: 'mpm',
        description: 'Land bank leases & auctions',
        has_access: assigned.includes('MPM'),
        route: '/modules/mpm',
      },
      {
        code: 'LGL',
        name: 'Legal Cases',
        domain: 'Planning & Regulation',
        phase: 4,
        icon: 'lgl',
        description: 'eCourts & counter-affidavits',
        has_access: assigned.includes('LGL'),
        route: '/modules/lgl',
      },
      {
        code: 'GSC',
        name: 'Government Schemes',
        domain: 'Citizen Welfare',
        phase: 4,
        icon: 'gsc',
        description: 'PMAY & PM SVANidhi DBT',
        has_access: assigned.includes('GSC'),
        route: '/modules/gsc',
      },
    ];
  }
}
