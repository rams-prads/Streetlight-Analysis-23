import { Component, Input, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { PtxAccess } from '../../../core/models/ptx.model';
import { PtxService } from '../../../core/services/ptx.service';
import { DialogService } from '../../../core/services/dialog.service';
import { IconComponent } from '../../../shared/components/icon/icon.component';
import { PtxPagerComponent } from '../shared/ptx-pager.component';
import { Pager, dmy, errorText, todayIso } from '../ptx-utils';

type Part = 'links' | 'deeds' | 'state' | 'bbps';

/**
 * Connections desk: the switches for every link to other systems, and the stand-ins that work today with the same data the real
 * systems will send: registered deeds (PT-14), the state property platform (PT-02) and BBPS (PT-21).
 */
@Component({
  selector: 'app-ptx-connections',
  standalone: true,
  imports: [CommonModule, FormsModule, IconComponent, PtxPagerComponent],
  template: `
    @if (part() === 'links') {
      <div class="ptx-card">
        <h2>Links to other systems</h2>
        <p class="ptx-muted">A link works only while it is switched on. Switching is by configuration, never by code, and every change is kept in the settings history with who made it and why. Links marked <b>stand-in</b> work today with the same data the real system will send.</p>
        @for (l of links(); track l.link) {
          <div class="ptx-row" style="margin: 0.4rem 0">
            <span class="ptx-chip plain" [ngClass]="l.enabled ? 'ACTIVE' : 'muted'">{{ l.enabled ? 'on' : 'off' }}</span>
            <span><b>{{ l.module }}</b> <small class="ptx-muted">{{ l.link }} · {{ l.direction }}@if (l.standIn) { · stand-in }</small></span>
            <span class="ptx-spacer"></span>
            @if (can('settings.manage')) { <button class="ptx-btn sm" (click)="toggle(l)">{{ l.enabled ? 'Switch off' : 'Switch on' }}</button> }
          </div>
        }
        @if (can('reports.view')) { <button class="ptx-btn" style="margin-top: 0.6rem" (click)="exportRegister()">Download property register (for other modules)</button> }
      </div>
    }

    @if (part() === 'deeds') {
      <div class="ptx-card flush">
        <div class="ptx-card-head">
          <button class="ptx-btn" (click)="loadDeeds()"><app-icon name="refresh" [size]="16"></app-icon> Refresh</button></div>
        <p class="ptx-muted" style="padding: 0 1rem">Each deed from the Registration Department starts a change of owner by itself when the property is found and the seller is the owner on record. Anything else waits here for an officer.</p>
        <div class="ptx-filter-bar">
          <div class="ptx-search"><app-icon name="search" [size]="16"></app-icon>
            <input [(ngModel)]="deedSearch" (input)="onDeedSearch()" placeholder="Search deed no., office, buyer, seller" aria-label="Search deeds" /></div>
          <select [(ngModel)]="deedStatus" (change)="deedPager.reset(); loadDeeds()" aria-label="Show deeds">
            <option value="TO_REVIEW">Need an officer</option><option value="">All</option><option value="CASE_OPENED">Case opened</option><option value="DISMISSED">Dismissed</option>
          </select>
        </div>
        <div class="ptx-table-wrap">
          <table class="ptx-table compact">
            <thead><tr><th>Deed</th><th>Date</th><th>Kind</th><th>Seller → Buyer</th><th>Property</th><th>Status</th><th></th></tr></thead>
            <tbody>
              @for (d of deeds(); track d.id) {
                <tr>
                  <td><b>{{ d.deedNo }}</b><br /><small class="ptx-muted">{{ d.registrationOffice }}</small></td>
                  <td>{{ dmy(d.deedDate) }}</td><td>{{ d.deedType }}</td>
                  <td>{{ d.sellers.join(', ') }} → {{ d.buyers.join(', ') }}</td>
                  <td><span class="ptx-mono">{{ d.upin || d.reference.upin || d.reference.oldAssessmentNo || '-' }}</span></td>
                  <td><span class="ptx-chip plain">{{ d.status }}</span>@if (d.message) { <br /><small class="ptx-muted">{{ d.message }}</small> }
                    @if (d.applicationNo) { <br /><small class="ptx-mono">{{ d.applicationNo }}</small> }</td>
                  <td>@if (d.status === 'REVIEW' || d.status === 'NO_MATCH') {
                    <button class="ptx-btn sm teal" (click)="openCase(d)">Open case</button> <button class="ptx-btn sm" (click)="dismiss(d)">Dismiss</button> }</td>
                </tr>
              } @empty { <tr><td colspan="7" class="ptx-muted">Nothing here.</td></tr> }
            </tbody>
          </table>
        </div>
        <app-ptx-pager [pager]="deedPager" (changed)="loadDeeds()"></app-ptx-pager>
      </div>

      <div class="ptx-card">
        <h3>Send a deed (stand-in for the Registration Department)</h3>
        <div class="ptx-form">
          <label>Deed no. * <input [(ngModel)]="deed.deedNo" /></label>
          <label>Registration office * <input [(ngModel)]="deed.registrationOffice" /></label>
          <label>Deed date * <input type="date" [(ngModel)]="deed.deedDate" [max]="today" /></label>
          <label>Kind <select [(ngModel)]="deed.deedType"><option value="SALE">Sale</option><option value="GIFT">Gift</option><option value="PARTITION">Partition</option><option value="WILL">Will</option><option value="LEASE">Lease</option></select></label>
          <label>Property number (UPIN) or old assessment no. * <input [(ngModel)]="deed.property" /></label>
          <label>Seller name * <input [(ngModel)]="deed.seller" /></label>
          <label>Buyer name * <input [(ngModel)]="deed.buyer" /></label>
          <label>Buyer mobile * <input [(ngModel)]="deed.mobile" inputmode="numeric" maxlength="10" /></label>
          <label>Consideration (₹) <input type="number" min="0" [(ngModel)]="deed.amount" inputmode="decimal" /></label>
        </div>
        <button class="ptx-btn teal" (click)="sendDeed()" [disabled]="!deedReady()">Send deed</button>
        @if (deedResult()) { <div class="ptx-alert info" style="margin-top: 0.6rem">{{ deedResult() }}</div> }
      </div>
    }

    @if (part() === 'state') {
      <div class="ptx-card">
        <h2>State property platform</h2>
        <p class="ptx-muted">Send the register out, and bring back the platform's property ids and address corrections. Tax, owners and area are never changed from outside. Mobile numbers and identity details are never sent.</p>
        <button class="ptx-btn" (click)="downloadExport()"><app-icon name="download" [size]="16"></app-icon> Download register for the platform</button>
        <h3 style="margin-top: 1rem">Bring in records from the platform</h3>
        <textarea [(ngModel)]="importJson" rows="5" style="width: 100%" placeholder='{"records":[{"stateRef":"STATE-TG-0001","upin":"GWMC-P-00000001","pincode":"506001"}]}'></textarea>
        <button class="ptx-btn teal" (click)="runImport()" [disabled]="!importJson.trim()">Load records</button>
        @if (importResult()) { <div class="ptx-alert info" style="margin-top: 0.6rem">{{ importResult() }}</div> }
      </div>
      <div class="ptx-card flush">
        <div class="ptx-card-head"><h2>Exchanges so far</h2><button class="ptx-btn" (click)="loadRuns()"><app-icon name="refresh" [size]="16"></app-icon> Refresh</button></div>
        <div class="ptx-table-wrap">
          <table class="ptx-table compact">
            <thead><tr><th>Run</th><th>When</th><th>Direction</th><th>Records</th><th>Matched</th><th>Updated</th><th>Not found</th><th>Problems</th><th>By</th></tr></thead>
            <tbody>@for (r of runs(); track r.id) {
              <tr><td><span class="ptx-mono">{{ r.runNo }}</span></td><td>{{ dmy(r.startedAt) }}</td><td>{{ r.direction === 'PUSH' ? 'Sent' : 'Received' }}</td><td>{{ r.records }}</td><td>{{ r.matched }}</td><td>{{ r.updated }}</td><td>{{ r.unmatched }}</td><td>{{ r.errors }}</td><td>{{ r.startedBy }}</td></tr>
            } @empty { <tr><td colspan="9" class="ptx-muted">No exchanges yet.</td></tr> }</tbody>
          </table>
        </div>
        <app-ptx-pager [pager]="runPager" (changed)="loadRuns()"></app-ptx-pager>
      </div>
    }

    @if (part() === 'bbps') {
      <div class="ptx-card">
        <h2>BBPS test console</h2>
        <p class="ptx-muted">Shows what a BBPS app sees when it asks for a bill, and records a payment it passes on. The same BBPS reference is never recorded twice, and a payment can never be more than what is due.</p>
        <div class="ptx-form">
          <label>Property number (UPIN) * <input [(ngModel)]="bbps.upin" /></label>
          <label>Amount to pay (₹) <input type="number" min="1" step="0.01" [(ngModel)]="bbps.amount" inputmode="decimal" /></label>
          <label>BBPS reference <input [(ngModel)]="bbps.ref" /></label>
        </div>
        <div class="ptx-row">
          <button class="ptx-btn" (click)="bbpsFetch()" [disabled]="!bbps.upin">Fetch bill</button>
          <button class="ptx-btn teal" (click)="bbpsPay()" [disabled]="!bbps.upin || !(bbps.amount > 0) || bbps.ref.length < 6">Record payment</button>
          <button class="ptx-btn" (click)="bbpsStatus()" [disabled]="bbps.ref.length < 6">Check reference</button>
        </div>
        @if (bbpsOut()) { <pre class="ptx-mono" style="white-space: pre-wrap; overflow-x: auto; margin-top: 0.6rem">{{ bbpsOut() }}</pre> }
      </div>
    }
  `,
})
export class PtxConnectionsComponent implements OnInit {
  @Input({ required: true }) access!: PtxAccess;
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  dmy = dmy;
  today = todayIso();

  /** The part to show, chosen in the sidebar. */
  @Input() view = '';
  part = signal<Part>('links');
  links = signal<any[]>([]);
  deeds = signal<any[]>([]);
  deedPager = new Pager(10);
  deedSearch = '';
  deedStatus = 'TO_REVIEW';
  deedResult = signal('');
  deed: any = { deedNo: '', registrationOffice: '', deedDate: todayIso(), deedType: 'SALE', property: '', seller: '', buyer: '', mobile: '', amount: null };
  importJson = '';
  importResult = signal('');
  runs = signal<any[]>([]);
  runPager = new Pager(5);
  bbps: any = { upin: '', amount: null, ref: '' };
  bbpsOut = signal('');
  private timer?: ReturnType<typeof setTimeout>;

  ngOnInit(): void {
    const parts: { [v: string]: Part } = { switches: 'links', deeds: 'deeds', state: 'state', bbps: 'bbps' };
    this.setPart(parts[this.view] || 'links');
  }

  can(p: string): boolean {
    return this.access.permissions.includes(p);
  }

  private fail = (e: unknown) => this.dialog.showToast(errorText(e), 'error');

  setPart(p: Part): void {
    this.part.set(p);
    if (p === 'links') this.loadLinks();
    if (p === 'deeds') this.loadDeeds();
    if (p === 'state') this.loadRuns();
  }

  loadLinks(): void {
    this.ptx.get('/integration/links').subscribe({ next: (r) => this.links.set(r), error: this.fail });
  }

  async toggle(l: any): Promise<void> {
    const reason = await this.dialog.prompt({
      title: `${l.enabled ? 'Switch off' : 'Switch on'}: ${l.module}`,
      message: 'The change applies from today and is kept in the settings history.',
      inputLabel: 'Why? (order no. or short reason)',
      required: true,
    });
    if (!reason) return;
    this.ptx.post(`/integration/links/${l.link}/toggle`, { enabled: !l.enabled, reason }).subscribe({
      next: (r) => {
        this.dialog.showToast(r.message, 'success');
        this.loadLinks();
      },
      error: this.fail,
    });
  }

  // ---- registered deeds ----
  loadDeeds(): void {
    this.ptx.get('/integration/registration/deeds', { search: this.deedSearch, status: this.deedStatus, ...this.deedPager.query() }).subscribe({
      next: (r) => {
        this.deeds.set(r.items);
        this.deedPager.total.set(r.total);
      },
      error: (e) => {
        this.deeds.set([]);
        this.fail(e);
      },
    });
  }

  onDeedSearch(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.deedPager.reset();
      this.loadDeeds();
    }, 350);
  }

  deedReady(): boolean {
    const d = this.deed;
    return !!(d.deedNo && d.registrationOffice && d.deedDate && d.property.trim() && d.seller.trim() && d.buyer.trim() && /^[6-9]\d{9}$/.test(d.mobile));
  }

  sendDeed(): void {
    const d = this.deed;
    const ref = d.property.trim();
    const body: any = {
      deedNo: d.deedNo, registrationOffice: d.registrationOffice, deedDate: d.deedDate, deedType: d.deedType,
      sellers: [d.seller.trim()], buyers: [{ fullName: d.buyer.trim(), mobileNumber: d.mobile }],
      ...(d.amount ? { considerationAmount: Number(d.amount) } : {}),
      ...(/^[A-Z]+-P-\d+$/i.test(ref) ? { upin: ref.toUpperCase() } : { oldAssessmentNo: ref }),
    };
    this.ptx.post('/integration/registration/deeds', { deeds: [body] }).subscribe({
      next: (r) => {
        const x = r.results[0];
        this.deedResult.set(x.result === 'ERROR' ? x.error : x.result === 'DUPLICATE_IGNORED' ? 'This deed was already received.' : x.message || `Deed received: ${x.status}.`);
        if (x.applicationNo && !this.deedResult().includes(x.applicationNo)) this.deedResult.set(`${this.deedResult()} Case ${x.applicationNo} opened.`);
        this.loadDeeds();
      },
      error: this.fail,
    });
  }

  async openCase(d: any): Promise<void> {
    let upin: string | null | undefined = d.upin;
    if (!upin) {
      upin = await this.dialog.prompt({ title: 'Which property?', message: 'The feed could not find the property. Enter its number (UPIN).', inputLabel: 'UPIN', required: true });
      if (!upin) return;
    }
    const remark = await this.dialog.prompt({ title: 'Open the change of owner', message: `Deed ${d.deedNo}: ${d.sellers.join(', ')} to ${d.buyers.join(', ')}.`, inputLabel: 'Your remark (what you checked)', required: true });
    if (!remark) return;
    this.ptx.post(`/integration/registration/deeds/${d.id}/open-case`, { remark, upin: upin.trim().toUpperCase() }).subscribe({
      next: (r) => {
        this.dialog.showToast(`Case ${r.applicationNo} opened.`, 'success');
        this.loadDeeds();
      },
      error: this.fail,
    });
  }

  async dismiss(d: any): Promise<void> {
    const remark = await this.dialog.prompt({ title: `Dismiss deed ${d.deedNo}`, inputLabel: 'Why is no change needed?', required: true });
    if (!remark) return;
    this.ptx.post(`/integration/registration/deeds/${d.id}/dismiss`, { remark }).subscribe({
      next: () => {
        this.dialog.showToast('Deed dismissed.', 'success');
        this.loadDeeds();
      },
      error: this.fail,
    });
  }

  // ---- state platform ----
  downloadExport(): void {
    this.ptx.get('/integration/state/export', { limit: 500 }).subscribe({
      next: (r) => {
        const url = URL.createObjectURL(new Blob([JSON.stringify(r, null, 1)], { type: 'application/json' }));
        const a = document.createElement('a');
        a.href = url;
        a.download = `state-platform-register-${todayIso()}.json`;
        a.click();
        URL.revokeObjectURL(url);
        this.dialog.showToast(`${r.records.length} records ready for the platform.`, 'success');
        this.loadRuns();
      },
      error: this.fail,
    });
  }

  runImport(): void {
    let body: any;
    try {
      body = JSON.parse(this.importJson);
    } catch {
      this.dialog.showToast('That is not valid JSON. Check the brackets and quotes.', 'error');
      return;
    }
    this.ptx.post('/integration/state/import', body).subscribe({
      next: (r) => {
        const problems = r.results.filter((x: any) => x.result === 'ERROR').map((x: any) => `${x.stateRef}: ${x.error}`);
        this.importResult.set(`${r.records} records: ${r.updated} updated, ${r.unmatched} not found, ${r.errors} with problems.${problems.length ? ' ' + problems.join(' · ') : ''}`);
        this.loadRuns();
      },
      error: this.fail,
    });
  }

  loadRuns(): void {
    this.ptx.get('/integration/state/runs', this.runPager.query()).subscribe({
      next: (r) => {
        this.runs.set(r.items);
        this.runPager.total.set(r.total);
      },
      error: (e) => {
        this.runs.set([]);
        this.fail(e);
      },
    });
  }

  // ---- BBPS ----
  private show(r: unknown): void {
    this.bbpsOut.set(JSON.stringify(r, null, 2));
  }

  bbpsFetch(): void {
    this.ptx.post('/integration/bbps/fetch', { requestId: `REQ-${Date.now()}`, upin: this.bbps.upin.trim() }).subscribe({ next: (r) => this.show(r), error: this.fail });
  }

  bbpsPay(): void {
    this.ptx.post('/integration/bbps/pay', { requestId: `REQ-${Date.now()}`, upin: this.bbps.upin.trim(), amount: Number(this.bbps.amount), bbpsTxnRef: this.bbps.ref.trim() }).subscribe({
      next: (r) => this.show(r),
      error: this.fail,
    });
  }

  bbpsStatus(): void {
    this.ptx.get(`/integration/bbps/status/${encodeURIComponent(this.bbps.ref.trim())}`).subscribe({ next: (r) => this.show(r), error: this.fail });
  }

  exportRegister(): void {
    this.ptx.getBlob('/export/register?format=csv').subscribe({
      next: (b) => {
        const url = URL.createObjectURL(b);
        const a = document.createElement('a');
        a.href = url;
        a.download = `property-register-${todayIso()}.csv`;
        a.click();
        URL.revokeObjectURL(url);
      },
      error: this.fail,
    });
  }
}
