import { Component, inject, signal, Input, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs/operators';
import { IconComponent } from '../icon/icon.component';
import { DialogService } from '../../../core/services/dialog.service';
import {
  SUPER_ADMIN_SECTIONS,
  SuperAdminMenuItem,
  SuperAdminSection,
} from '../../../core/models/super-admin.model';
import { APP_VERSION } from '../../../core/constants/version';

@Component({
  selector: 'app-super-admin-sidebar',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent],
  templateUrl: './super-admin-sidebar.component.html',
  styleUrl: './super-admin-sidebar.component.scss',
})
export class SuperAdminSidebarComponent implements OnInit {
  @Input() collapsed: boolean = false;

  private router = inject(Router);
  private dialogs = inject(DialogService);

  readonly appVersion = APP_VERSION;
  readonly sections: SuperAdminSection[] = SUPER_ADMIN_SECTIONS;
  readonly openSections = signal<Set<string>>(
    new Set(['tenancy', 'modules', 'iam', 'iam-sso', 'iam-rbac', 'iam-users', 'security']),
  );
  readonly activeItemId = signal<string>('TH-01');

  searchQuery = '';

  ngOnInit(): void {
    this.syncActiveItemFromUrl();
    this.router.events
      .pipe(filter((event): event is NavigationEnd => event instanceof NavigationEnd))
      .subscribe(() => {
        this.syncActiveItemFromUrl();
      });
  }

  private syncActiveItemFromUrl(): void {
    try {
      const urlTree = this.router.parseUrl(this.router.url);
      const item = urlTree.queryParams['item'];
      if (item && this.activeItemId() !== item) {
        this.activeItemId.set(item);
      }
    } catch {
      // Ignore URL parse errors
    }
  }

  isSectionOpen(sectionId: string): boolean {
    return this.openSections().has(sectionId);
  }

  toggleSection(sectionId: string): void {
    const next = new Set(this.openSections());
    if (next.has(sectionId)) {
      next.delete(sectionId);
    } else {
      next.add(sectionId);
    }
    this.openSections.set(next);
  }

  get filteredSections(): SuperAdminSection[] {
    if (!this.searchQuery.trim()) {
      return this.sections;
    }
    const q = this.searchQuery.toLowerCase();
    return this.sections
      .map((sec) => ({
        ...sec,
        items: sec.items.filter(
          (item) =>
            item.title.toLowerCase().includes(q) ||
            item.code.toLowerCase().includes(q) ||
            item.description.toLowerCase().includes(q),
        ),
      }))
      .filter((sec) => sec.items.length > 0);
  }

  selectItem(item: SuperAdminMenuItem): void {
    this.activeItemId.set(item.id);
    const parentSection = this.sections.find((s) => s.items.some((i) => i.id === item.id));
    const secId = parentSection ? parentSection.id : 'tenancy';

    this.dialogs.showToast(`Selected: ${item.title}`, 'info', 1500);

    this.router.navigate(['/admin'], { queryParams: { section: secId, item: item.id } });
  }
}
