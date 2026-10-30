import { Routes } from '@angular/router';
import { DashboardComponent } from './modules/dashboard/dashboard.component';
import { AuthComponent } from './modules/auth/auth.component';
import { AdminDashboardComponent } from './modules/admin/admin-dashboard.component';

export const routes: Routes = [
  { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
  { path: 'login', component: AuthComponent },
  { path: 'dashboard', component: DashboardComponent },
  { path: 'admin', component: AdminDashboardComponent },
  { path: 'admin/:section', component: AdminDashboardComponent },
  // Module 2 - Water & Utility Billing (lazy loaded)
  { path: 'modules/wtr', redirectTo: 'modules/wtr/overview', pathMatch: 'full' },
  {
    path: 'modules/wtr/:section',
    loadComponent: () => import('./modules/water/water-shell.component').then((m) => m.WaterShellComponent),
  },
  { path: '**', redirectTo: 'dashboard' }
];
