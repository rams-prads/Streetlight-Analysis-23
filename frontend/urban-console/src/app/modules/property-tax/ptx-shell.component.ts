import { Component, ElementRef, HostListener, OnDestroy, OnInit, ViewEncapsulation, computed, effect, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, Router } from '@angular/router';
import { Subscription, forkJoin, of } from 'rxjs';
import { catchError, map } from 'rxjs/operators';
import { KeycloakAuthService } from '../../core/services/keycloak.service';
import { PtxService } from '../../core/services/ptx.service';
import { PtxI18nService } from '../../core/services/ptx-i18n.service';
import { DialogService } from '../../core/services/dialog.service';
import { PtxAccess } from '../../core/models/ptx.model';
import { IconComponent } from '../../shared/components/icon/icon.component';
import { errorText } from './ptx-utils';
import { HOME, NAV, NavGroup, NavItem, ROLE_LABEL, allowed, mainRole, navKey } from './ptx-nav';
import { PtxOverviewComponent } from './overview/ptx-overview.component';
import { PtxPropertiesComponent } from './properties/ptx-properties.component';
import { PtxCasesComponent } from './cases/ptx-cases.component';
import { PtxBillingComponent } from './billing/ptx-billing.component';
import { PtxCollectionComponent } from './collection/ptx-collection.component';
import { PtxArrearsComponent } from './arrears/ptx-arrears.component';
import { PtxMapComponent } from './map/ptx-map.component';
import { PtxReportsComponent } from './reports/ptx-reports.component';
import { PtxApprovalsComponent } from './approvals/ptx-approvals.component';
import { PtxAdminComponent } from './admin/ptx-admin.component';
import { PtxConnectionsComponent } from './admin/ptx-connections.component';
import { PtxCitizenComponent } from './citizen/ptx-citizen.component';
import { PtxFieldComponent } from './field/ptx-field.component';

const RAIL_KEY = 'urban_ptx_rail';

/**
 * Module 1 shell. Staff get a Property Tax sidebar (grouped by kind of work, filtered by their permissions, PT-NF-10) and one
 * page at a time; citizens get their own simple portal with no staff menus. Telugu / English switch (PT-NF-41) and the staff
 * idle time-out (PT-NF-15). Mobile first: below 1024px the sidebar is a slide-over drawer; on desktop it can shrink to icons.
 */
@Component({
  selector: 'app-ptx-shell',
  standalone: true,
  encapsulation: ViewEncapsulation.None,
  imports: [
    CommonModule, IconComponent, PtxOverviewComponent, PtxPropertiesComponent, PtxCasesComponent, PtxBillingComponent,
    PtxCollectionComponent, PtxArrearsComponent, PtxMapComponent, PtxReportsComponent, PtxApprovalsComponent, PtxAdminComponent,
    PtxConnectionsComponent, PtxCitizenComponent, PtxFieldComponent,
  ],
  templateUrl: './ptx-shell.component.html',
  styleUrl: './ptx.scss',
})
export class PtxShellComponent implements OnInit, OnDestroy {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private auth = inject(KeycloakAuthService);
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  private host = inject(ElementRef<HTMLElement>);
  i18n = inject(PtxI18nService);

  readonly home = HOME;
  /** A request is running somewhere on the page. */
  busy = computed(() => this.ptx.pending() > 0);
  /** The progress bar appears only for requests that take a moment, so quick ones do not flicker. */
  showProgress = signal(false);
  private progressTimer?: ReturnType<typeof setTimeout>;
  access = signal<PtxAccess | null>(null);
  section = signal<string>('');
  view = signal<string>('');
  loadError = signal<string>('');
  rail = signal<boolean>(this.stored(RAIL_KEY) === '1');
  drawerOpen = signal(false);
  badges = signal<{ [k: string]: number }>({});
  /** Groups opened in the sidebar; opening a page keeps just its own group open. */
  private openGroups = signal<Set<string>>(new Set());

  routeKey = computed(() => `${this.section()}/${this.view()}`);
  private perms = computed(() => new Set(this.access()?.permissions ?? []));
  isCitizen = computed(() => {
    const roles = this.access()?.roles ?? [];
    return roles.length > 0 && roles.every((r) => r === 'citizen');
  });
  /** The groups and items this user may open. */
  groups = computed<NavGroup[]>(() =>
    NAV.map((g) => ({ ...g, items: g.items.filter((i) => allowed(i, this.perms())) })).filter((g) => g.items.length > 0),
  );
  private items = computed<NavItem[]>(() => [HOME, ...this.groups().flatMap((g) => g.items)]);
  /** The item for the page on screen; a section opened without a part shows its first allowed part. */
  current = computed<NavItem | null>(() => {
    const list = this.items();
    return list.find((i) => i.section === this.section() && (i.view || '') === this.view()) || null;
  });
  roleLabel = computed(() => {
    const r = ROLE_LABEL[mainRole(this.access()?.roles ?? [])];
    return r ? (this.i18n.lang() === 'te' ? r.te : r.en) : '';
  });
  firstName = computed(() => {
    const raw = this.access()?.displayName || this.auth.userProfile()?.name || '';
    const name = String(raw).replace(/\(.*\)/, '').trim();
    const words = name.split(/[\s,]+/).filter(Boolean);
    return words.find((w) => w.length > 2 && !w.endsWith('.')) || words[0] || '';
  });

  constructor() {
    effect(() => {
      const busy = this.busy();
      if (this.progressTimer) clearTimeout(this.progressTimer);
      if (busy) {
        this.progressTimer = setTimeout(() => this.showProgress.set(true), 180);
      } else {
        this.showProgress.set(false);
        // every pressed button is done once nothing is running
        (this.host.nativeElement as HTMLElement).querySelectorAll('[data-pressed]').forEach((b) => b.removeAttribute('data-pressed'));
      }
    });
  }

  /**
   * Marks the button that was pressed, so it alone shows a spinner while the requests it started run. A press that starts
   * no request (opening a form, for example) is unmarked straight away.
   */
  @HostListener('click', ['$event'])
  onPress(e: MouseEvent): void {
    const button = (e.target as HTMLElement | null)?.closest?.('button.ptx-btn') as HTMLButtonElement | null;
    if (!button || button.disabled) return;
    button.setAttribute('data-pressed', '');
    setTimeout(() => {
      if (!this.busy()) button.removeAttribute('data-pressed');
    }, 60);
  }

  private sub?: Subscription;
  private tenantHandler = () => this.load();
  private drawerHandler = () => this.drawerOpen.update((v) => !v);
  private idleTimer?: ReturnType<typeof setTimeout>;
  private activityEvents = ['mousedown', 'keydown', 'touchstart', 'scroll'];
  private activity = () => this.resetIdle();

  ngOnInit(): void {
    // a page reload lands here directly: make PTX the active module in the shared header
    const ptxModule = this.auth.userModules().find((m) => m.code === 'PTX');
    if (this.auth.activeModule().code !== 'PTX') {
      this.auth.activeModule.set(
        ptxModule ?? {
          code: 'PTX', name: 'Property Tax & Revenue Management', domain: 'Revenue & Billing', phase: 1, icon: 'ptx',
          description: 'Property register, assessment, demand, collection and arrears', has_access: true, route: '/modules/ptx',
        },
      );
    }
    this.sub = this.route.paramMap.subscribe((p) => {
      this.section.set(p.get('section') || '');
      this.view.set(p.get('view') || '');
      this.drawerOpen.set(false);
      document.querySelector('.ptx-main')?.scrollTo({ top: 0 });
      if (this.access()) {
        this.settleRoute();
        this.loadBadges();
      }
    });
    window.addEventListener('urban:tenant-changed', this.tenantHandler);
    window.addEventListener('urban:ptx-nav', this.drawerHandler);
    this.load();
  }

  ngOnDestroy(): void {
    this.sub?.unsubscribe();
    window.removeEventListener('urban:tenant-changed', this.tenantHandler);
    window.removeEventListener('urban:ptx-nav', this.drawerHandler);
    this.stopIdle();
  }

  load(): void {
    this.loadError.set('');
    this.ptx.me().subscribe({
      next: (a) => {
        this.access.set(a);
        if (this.isCitizen()) {
          if (this.section() !== 'home') this.router.navigate(['/modules/ptx', 'home'], { replaceUrl: true });
          return;
        }
        this.settleRoute();
        this.loadBadges();
        this.startIdle();
      },
      error: (e) => {
        this.access.set(null);
        this.loadError.set(errorText(e));
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  /** Refresh button: reload the page on screen (screens load their data when they open) and the counts. */
  reload(): void {
    const s = this.section();
    const v = this.view();
    this.section.set('');
    setTimeout(() => {
      this.section.set(s);
      this.view.set(v);
      this.loadBadges();
    });
  }

  /** Old links and bare sections land on a page this user may see. */
  private settleRoute(): void {
    const s = this.section() === 'overview' ? 'home' : this.section();
    const list = this.items();
    if (list.some((i) => i.section === s && (i.view || '') === this.view())) {
      if (s !== this.section()) this.router.navigate(['/modules/ptx', s], { replaceUrl: true, queryParamsHandling: 'preserve' });
      this.openGroupOf(this.current());
      return;
    }
    const first = list.find((i) => i.section === s);
    const target = first || HOME;
    this.router.navigate(['/modules/ptx', target.section, ...(target.view ? [target.view] : [])], { replaceUrl: true, queryParamsHandling: 'preserve' });
  }

  private loadBadges(): void {
    const p = this.perms();
    const total = (path: string, query: any) => this.ptx.get(path, { ...query, limit: 1 }).pipe(map((r: any) => r.total as number), catchError(() => of(0)));
    const calls: { [k: string]: any } = {};
    // counts only for the people who act on them
    if (p.has('case.view') && p.has('property.edit')) {
      calls['applications'] = this.ptx.get('/cases-summary/pending').pipe(
        map((r: any) => Object.values(r || {}).reduce((a: number, b: any) => a + Number(b || 0), 0)), catchError(() => of(0)));
    }
    if (p.has('complaint.work')) calls['complaints'] = total('/complaints', { status: 'UNRESOLVED' });
    if (p.has('approval.decide') || p.has('rates.approve')) calls['approvals'] = total('/approvals', { status: 'PENDING' });
    if (p.has('petition.decide')) calls['petitions'] = total('/petitions', { status: 'FILED' });
    if (p.has('survey.review')) calls['surveys'] = total('/surveys', { status: 'SUBMITTED' });
    if (p.has('integration.run')) calls['deeds'] = total('/integration/registration/deeds', { status: 'TO_REVIEW' });
    if (!Object.keys(calls).length) return;
    forkJoin(calls).subscribe((r) => this.badges.set(r as { [k: string]: number }));
  }

  // ---- sidebar ----
  label(x: { en: string; te: string }): string {
    return this.i18n.lang() === 'te' ? x.te : x.en;
  }

  key(i: NavItem): string {
    return navKey(i);
  }

  isActive(i: NavItem): boolean {
    const c = this.current();
    return !!c && navKey(c) === navKey(i);
  }

  groupActive(g: NavGroup): boolean {
    return g.items.some((i) => this.isActive(i));
  }

  groupOf(i: NavItem): NavGroup | null {
    return i.section === 'home' ? null : this.groups().find((g) => g.items.some((x) => navKey(x) === navKey(i))) || null;
  }

  badgeFor(i: NavItem): number {
    return i.badge ? this.badges()[i.badge] || 0 : 0;
  }

  groupBadge(g: NavGroup): number {
    return g.items.reduce((n, i) => n + this.badgeFor(i), 0);
  }

  isOpen(key: string): boolean {
    return this.openGroups().has(key);
  }

  toggleGroup(key: string): void {
    if (this.rail()) {
      this.rail.set(false);
      this.store(RAIL_KEY, '0');
      this.setOpen(key, true);
      return;
    }
    this.setOpen(key, !this.openGroups().has(key));
  }

  private setOpen(key: string, open: boolean): void {
    const next = new Set(this.openGroups());
    if (open) next.add(key);
    else next.delete(key);
    this.openGroups.set(next);
  }

  /** Opening a page keeps just its own group open, so the sidebar stays short; with three groups or fewer, all stay open. */
  private openGroupOf(i: NavItem | null): void {
    const groups = this.groups();
    if (groups.length <= 3) {
      this.openGroups.set(new Set(groups.map((g) => g.key)));
      return;
    }
    const g = i ? this.groupOf(i) : null;
    this.openGroups.set(new Set(g ? [g.key] : []));
  }

  toggleRail(): void {
    this.rail.update((v) => !v);
    this.store(RAIL_KEY, this.rail() ? '1' : '0');
  }

  open(i: NavItem): void {
    this.router.navigate(['/modules/ptx', i.section, ...(i.view ? [i.view] : [])]);
  }

  /** Links from the home page and other screens: "section" or "section/view". */
  go(key: string): void {
    const [section, view] = key.split('/');
    this.router.navigate(['/modules/ptx', section, ...(view ? [view] : [])]);
  }

  greeting(): string {
    const h = new Date().getHours();
    const te = this.i18n.lang() === 'te';
    const hello = te ? 'నమస్కారం' : h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
    return this.firstName() ? `${hello}, ${this.firstName()}` : hello;
  }

  homeHint(): string {
    const a = this.access();
    return a ? `${this.roleLabel()}${a.scope ? ' · ' + a.scope : ''}` : '';
  }

  private stored(k: string): string | null {
    try {
      return localStorage.getItem(k);
    } catch {
      return null;
    }
  }

  private store(k: string, v: string): void {
    try {
      localStorage.setItem(k, v);
    } catch {
      /* storage blocked: the choice lasts for this visit */
    }
  }

  /** Staff sessions end after the configured minutes without activity (PT-NF-15). */
  private startIdle(): void {
    this.stopIdle();
    this.activityEvents.forEach((e) => window.addEventListener(e, this.activity, { passive: true }));
    this.resetIdle();
  }

  private stopIdle(): void {
    this.activityEvents.forEach((e) => window.removeEventListener(e, this.activity));
    if (this.idleTimer) clearTimeout(this.idleTimer);
  }

  private resetIdle(): void {
    if (this.idleTimer) clearTimeout(this.idleTimer);
    const minutes = this.access()?.staffTimeoutMinutes || 15;
    this.idleTimer = setTimeout(() => {
      this.stopIdle();
      this.auth.logout();
      this.dialog.showToast(`You were signed out after ${minutes} minutes without activity. Please sign in again.`, 'warning');
      this.router.navigate(['/']);
    }, minutes * 60_000);
  }
}
