import { inject } from '@angular/core';
import { Router, Routes, UrlMatchResult, UrlSegment } from '@angular/router';
import { KeycloakAuthService } from './core/services/keycloak.service';
import { DashboardComponent } from './modules/dashboard/dashboard.component';
import { AuthComponent } from './modules/auth/auth.component';
import { AdminDashboardComponent } from './modules/admin/admin-dashboard.component';

/** Property Tax (Module 1) has its own screens: the old landing page is shown only while another module is active. */
const ptxHome = () => {
  const auth = inject(KeycloakAuthService);
  return auth.activeModule().code === 'PTX' && !auth.isSuperAdmin() ? inject(Router).createUrlTree(['/modules/ptx']) : true;
};

/** Every workspace route needs a real sign-in for this tab: the session (token) lives per-tab, not shared across the browser. */
const authGuard = () => {
  const auth = inject(KeycloakAuthService);
  return auth.isAuthenticated() ? true : inject(Router).createUrlTree(['/login']);
};

/** The Super Admin console is for super_admin/system_admin only - no other signed-in role may land here. */
const superAdminGuard = () => {
  const auth = inject(KeycloakAuthService);
  return auth.isSuperAdmin() ? true : inject(Router).createUrlTree(['/dashboard']);
};

/** Property Tax pages: modules/ptx/:section with an optional :view (a part of the section chosen in the sidebar). */
export function ptxPage(segments: UrlSegment[]): UrlMatchResult | null {
  if (segments.length < 3 || segments.length > 4 || segments[0].path !== 'modules' || segments[1].path !== 'ptx') return null;
  const posParams: { [name: string]: UrlSegment } = { section: segments[2] };
  if (segments.length === 4) posParams['view'] = segments[3];
  return { consumed: segments, posParams };
}

export const routes: Routes = [
  { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
  { path: 'login', component: AuthComponent },
  { path: 'dashboard', component: DashboardComponent, canActivate: [authGuard, ptxHome] },
  { path: 'admin', component: AdminDashboardComponent, canActivate: [authGuard, superAdminGuard] },
  { path: 'admin/:section', component: AdminDashboardComponent, canActivate: [authGuard, superAdminGuard] },
  { path: 'admin/:section/:sub', component: AdminDashboardComponent, canActivate: [authGuard, superAdminGuard] },
  // Module 1 - Property Tax & Revenue Management (lazy loaded)
  { path: 'modules/ptx', redirectTo: 'modules/ptx/home', pathMatch: 'full' },
  {
    // one route for /modules/ptx/:section and /modules/ptx/:section/:view, so the shell and its sidebar stay put between pages
    matcher: ptxPage,
    canActivate: [authGuard],
    loadComponent: () => import('./modules/property-tax/ptx-shell.component').then((m) => m.PtxShellComponent),
  },
  // Module 2 - Water & Utility Billing (lazy loaded)
  { path: 'modules/wtr', redirectTo: 'modules/wtr/overview', pathMatch: 'full' },
  {
    path: 'modules/wtr/:section',
    canActivate: [authGuard],
    loadComponent: () => import('./modules/water/water-shell.component').then((m) => m.WaterShellComponent),
  },
  { path: '**', redirectTo: 'dashboard' }
];
