import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Ageing, Defaulter, Notice, PtxAccess, RecoveryCase } from '../../../core/models/ptx.model';
import { PtxService } from '../../../core/services/ptx.service';
import { PtxI18nService } from '../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { IconComponent } from '../../../shared/components/icon/icon.component';
import { PtxPagerComponent } from '../shared/ptx-pager.component';
import { PtxDocumentComponent } from '../shared/ptx-document.component';
import { NoticeIssueDialogComponent } from './dialogs/notice-issue-dialog/notice-issue-dialog.component';
import { WaiverDialogComponent } from './dialogs/waiver-dialog/waiver-dialog.component';
import { NoticeServiceDialogComponent } from './dialogs/notice-service-dialog/notice-service-dialog.component';
import { Pager, dmy, downloadCsv, errorText, todayIso } from '../ptx-utils';

type Tab = 'defaulters' | 'notices' | 'recovery' | 'runs';

/** Arrears ageing and defaulters (PT-41, PT-63), notices and their service (PT-42, PT-43), recovery cases (PT-44). */
@Component({
  selector: 'app-ptx-arrears',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent, PtxPagerComponent, PtxDocumentComponent, NoticeIssueDialogComponent, WaiverDialogComponent,
    NoticeServiceDialogComponent],
  templateUrl: './ptx-arrears.component.html',
})
export class PtxArrearsComponent implements OnInit {
  @Input({ required: true }) access!: PtxAccess;
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  i18n = inject(PtxI18nService);
  dmy = dmy;

  /** The part to show, chosen in the sidebar. */
  @Input() view = '';
  tab = signal<Tab>('defaulters');
  af = { search: '', wardId: '', minDue: '' };
  ageing = signal<Ageing | null>(null);
  defaulters = signal<Defaulter[]>([]);
  defPager = new Pager(10);

  nf = { search: '', type: '', serviceStatus: '', wardId: '' };
  notices = signal<Notice[]>([]);
  noticePager = new Pager(10);
  shownNotice = signal<Notice | null>(null);

  rf = { search: '', status: 'OPEN' };
  recovery = signal<RecoveryCase[]>([]);
  recPager = new Pager(10);

  issueFor = signal<{ upins: string[] } | null>(null);
  waiverFor = signal<string | null>(null);
  serveNotice = signal<Notice | null>(null);
  runResult = signal<string>('');
  busy = signal(false);
  private searchTimer?: ReturnType<typeof setTimeout>;

  ngOnInit(): void {
    this.setTab((['defaulters', 'notices', 'recovery', 'runs'] as Tab[]).includes(this.view as Tab) ? (this.view as Tab) : 'defaulters');
  }

  can(p: string): boolean {
    return this.access.permissions.includes(p);
  }

  setTab(t: Tab): void {
    this.tab.set(t);
    if (t === 'defaulters') this.loadAgeing();
    if (t === 'notices') this.loadNotices();
    if (t === 'recovery') this.loadRecovery();
  }

  private debounce(fn: () => void): void {
    if (this.searchTimer) clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(fn, 350);
  }

  searchDefaulters(): void {
    this.debounce(() => {
      this.defPager.reset();
      this.loadAgeing();
    });
  }

  searchNotices(): void {
    this.debounce(() => {
      this.noticePager.reset();
      this.loadNotices();
    });
  }

  searchRecovery(): void {
    this.debounce(() => {
      this.recPager.reset();
      this.loadRecovery();
    });
  }

  loadAgeing(): void {
    this.ptx.get<Ageing>('/arrears/ageing', { ...this.af, ...this.defPager.query() }).subscribe({
      next: (a) => {
        this.ageing.set(a);
        this.defaulters.set(a.defaulters.items);
        this.defPager.total.set(a.defaulters.total);
      },
      error: (e) => {
        this.ageing.set(null);
        this.defaulters.set([]);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  exportDefaulters(): void {
    downloadCsv(`ptx-defaulters-${todayIso()}`, this.defaulters(), [
      { key: 'upin', label: 'UPIN' }, { key: 'ownerNames', label: 'Owner' }, { key: 'address', label: 'Address' }, { key: 'wardNumber', label: 'Ward' },
      { key: 'current', label: 'Current' }, { key: 'arrears', label: 'Arrears' }, { key: 'interest', label: 'Interest' }, { key: 'fees', label: 'Fees' },
      { key: 'totalDue', label: 'Total due' }, { key: 'oldestAgeDays', label: 'Oldest (days)' }, { key: 'ageBand', label: 'Age band' },
    ]);
  }

  bandAmount(row: any, band: string): number {
    return row[band] || 0;
  }

  loadNotices(): void {
    this.ptx.get('/notices', { ...this.nf, ...this.noticePager.query() }).subscribe({
      next: (r) => {
        this.notices.set(r.items);
        this.noticePager.total.set(r.total);
      },
      error: (e) => {
        this.notices.set([]);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  showNotice(no: string): void {
    this.ptx.get<Notice>(`/notices/${encodeURIComponent(no)}`).subscribe({
      next: (n) => this.shownNotice.set(n),
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  loadRecovery(): void {
    this.ptx.get('/recovery', { ...this.rf, ...this.recPager.query() }).subscribe({
      next: (r) => {
        this.recovery.set(r.items);
        this.recPager.total.set(r.total);
      },
      error: (e) => {
        this.recovery.set([]);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  async advance(c: RecoveryCase, close: boolean): Promise<void> {
    const remark = await this.dialog.prompt({
      title: close ? `Close recovery case ${c.caseNo}?` : `Move ${c.caseNo} to the next stage?`,
      message: close ? 'Say why it is being closed (e.g. paid in full, court stay).' : `Now at: ${c.stage.replaceAll('_', ' ').toLowerCase()}. Record what was done.`,
      inputLabel: 'Remark', required: true,
    });
    if (!remark) return;
    this.ptx.post(`/recovery/${encodeURIComponent(c.caseNo)}/advance`, { remark, close }).subscribe({
      next: () => {
        this.dialog.showToast(close ? 'Recovery case closed.' : 'Moved to the next stage.', 'success');
        this.loadRecovery();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }

  async run(kind: 'interest' | 'reminders' | 'recovery' | 'daily'): Promise<void> {
    const text = {
      interest: 'Add interest for overdue bills up to today? Each month is charged only once, so running it again adds nothing extra.',
      reminders: 'Send SMS reminders for bills nearing or past their due date (as set by GWMC)?',
      recovery: 'Open recovery cases for large or long-unpaid dues, and close cases that are now paid?',
      daily: 'Run all the daily jobs now (online payment checks, auto-finalise, interest, reminders, recovery, escalations)?',
    }[kind];
    if (!(await this.dialog.confirm({ title: 'Run now?', message: text, confirmText: 'Run' }))) return;
    const path = { interest: '/arrears/interest-run', reminders: '/arrears/reminders-run', recovery: '/recovery/run', daily: '/jobs/daily' }[kind];
    this.busy.set(true);
    this.ptx.post(path).subscribe({
      next: (r) => {
        this.busy.set(false);
        const msg = kind === 'interest' ? `Interest added on ${r.properties} propert(ies): ${r.charges} charge(s), ₹${r.amount}.`
          : kind === 'reminders' ? `${r.remindersQueued} reminder(s) queued.`
          : kind === 'recovery' ? `${r.opened} recovery case(s) opened, ${r.closed} closed.`
          : `Done: ${r.casesFinalised ?? 0} case(s) finalised; interest on ${r.interest?.properties ?? 0} propert(ies); ${r.reminders?.remindersQueued ?? 0} reminder(s); ${r.recovery?.opened ?? 0} recovery case(s) opened.`;
        this.runResult.set(msg);
        this.dialog.showToast(msg, 'success');
      },
      error: (e) => {
        this.busy.set(false);
        this.dialog.showToast(errorText(e), 'error');
      },
    });
  }

  onIssued(done: boolean): void {
    this.issueFor.set(null);
    if (done) this.setTab('notices');
  }

  onWaiverClosed(done: boolean): void {
    this.waiverFor.set(null);
    if (done) this.loadAgeing();
  }

  onServed(done: boolean): void {
    this.serveNotice.set(null);
    if (done) this.loadNotices();
  }
}
