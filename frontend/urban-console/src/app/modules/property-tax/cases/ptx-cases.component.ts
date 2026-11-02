import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { Complaint, Petition, PtxAccess, PtxCase } from '../../../core/models/ptx.model';
import { PtxService } from '../../../core/services/ptx.service';
import { PtxI18nService } from '../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { IconComponent } from '../../../shared/components/icon/icon.component';
import { PtxPagerComponent } from '../shared/ptx-pager.component';
import { CaseFormDialogComponent } from './dialogs/case-form-dialog/case-form-dialog.component';
import { CaseDetailDialogComponent } from './dialogs/case-detail-dialog/case-detail-dialog.component';
import { ComplaintDialogComponent } from './dialogs/complaint-dialog/complaint-dialog.component';
import { CASE_TYPES } from './case-types';
import { Pager, dmy, errorText } from '../ptx-utils';

/** Applications: new and self assessment, reassessment, use change, exemption, mutation, split, merge (PT-12..PT-21). */
@Component({
  selector: 'app-ptx-cases',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent, PtxPagerComponent, CaseFormDialogComponent, CaseDetailDialogComponent, ComplaintDialogComponent],
  templateUrl: './ptx-cases.component.html',
})
export class PtxCasesComponent implements OnInit {
  @Input({ required: true }) access!: PtxAccess;
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  private route = inject(ActivatedRoute);
  i18n = inject(PtxI18nService);
  dmy = dmy;
  types = CASE_TYPES;

  /** The part to show, chosen in the sidebar. */
  @Input() view = '';
  tab = signal<'cases' | 'petitions' | 'complaints'>('cases');
  complaints = signal<Complaint[]>([]);
  compPager = new Pager(10);
  cf = { search: '', status: 'UNRESOLVED', category: '', overdue: false };
  complaintOpen = signal<string | null>(null);
  newComplaint = signal(false);
  petitions = signal<Petition[]>([]);
  petPager = new Pager(10);
  pf = { search: '', status: 'FILED', level: '' };
  filters = { search: '', status: 'IN_PROGRESS', appType: '', wardId: '' };
  rows = signal<PtxCase[]>([]);
  loading = signal(false);
  pager = new Pager(10);
  formOpen = signal(false);
  presetUpin = signal<string>('');
  openNo = signal<string | null>(null);
  private searchTimer?: ReturnType<typeof setTimeout>;

  ngOnInit(): void {
    const upin = this.route.snapshot.queryParamMap.get('upin');
    if (upin && this.can('case.create')) {
      this.presetUpin.set(upin);
      this.formOpen.set(true);
    }
    const no = this.route.snapshot.queryParamMap.get('applicationNo');
    if (no) this.openNo.set(no);
    this.load();
    if (this.view === 'petitions' || this.view === 'complaints') this.setTab(this.view);
  }

  can(p: string): boolean {
    return this.access.permissions.includes(p);
  }

  onSearchInput(): void {
    if (this.searchTimer) clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => this.applyFilters(), 350);
  }

  applyFilters(): void {
    this.pager.reset();
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.ptx.cases({ ...this.filters, ...this.pager.query() }).subscribe({
      next: (r) => {
        this.rows.set(r.items);
        this.pager.total.set(r.total);
        this.loading.set(false);
      },
      error: (e) => {
        this.rows.set([]);
        this.pager.total.set(0);
        this.loading.set(false);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  setTab(t: 'cases' | 'petitions' | 'complaints'): void {
    this.tab.set(t);
    if (t === 'petitions') this.loadPetitions();
    if (t === 'complaints') this.loadComplaints();
  }

  searchComplaints(): void {
    if (this.searchTimer) clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => {
      this.compPager.reset();
      this.loadComplaints();
    }, 350);
  }

  loadComplaints(): void {
    this.ptx.get('/complaints', { search: this.cf.search, status: this.cf.status, category: this.cf.category, overdue: this.cf.overdue ? 'true' : '', ...this.compPager.query() }).subscribe({
      next: (r) => {
        this.complaints.set(r.items);
        this.compPager.total.set(r.total);
      },
      error: (e) => {
        this.complaints.set([]);
        this.compPager.total.set(0);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  onComplaintClosed(changed: boolean): void {
    this.complaintOpen.set(null);
    this.newComplaint.set(false);
    if (changed) this.loadComplaints();
  }

  searchPetitions(): void {
    if (this.searchTimer) clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => {
      this.petPager.reset();
      this.loadPetitions();
    }, 350);
  }

  loadPetitions(): void {
    this.ptx.get('/petitions', { ...this.pf, ...this.petPager.query() }).subscribe({
      next: (r) => {
        this.petitions.set(r.items);
        this.petPager.total.set(r.total);
      },
      error: (e) => {
        this.petitions.set([]);
        this.petPager.total.set(0);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  currentStepLabel(c: PtxCase): string {
    return c.steps.find((s) => s.status === 'CURRENT')?.label || '-';
  }

  overdue(c: PtxCase): boolean {
    const s = c.steps.find((x) => x.status === 'CURRENT');
    return !!s?.dueAt && s.code !== 'NOTICE' && new Date(`${s.dueAt}Z`).getTime() < Date.now();
  }

  newCase(): void {
    this.presetUpin.set('');
    this.formOpen.set(true);
  }

  onFiled(applicationNo: string | null): void {
    this.formOpen.set(false);
    if (applicationNo) {
      this.load();
      this.openNo.set(applicationNo);
    }
  }

  onDetailClosed(changed: boolean): void {
    this.openNo.set(null);
    if (changed) this.load();
  }
}
