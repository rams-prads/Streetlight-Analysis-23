import { ChangeDetectorRef, Component, Input, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Floor, OfflineItem, PtxAccess, Survey, WardSheet } from '../../../core/models/ptx.model';
import { PtxService } from '../../../core/services/ptx.service';
import { PtxI18nService } from '../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../core/services/dialog.service';
import { PtxFloorsEditorComponent } from '../shared/ptx-floors-editor.component';
import { OfflineQueue, compressPhoto, currentPosition, dataUrlToBlob, dmy, errorText, newKey } from '../ptx-utils';

type Tab = 'work' | 'review';

/**
 * Field work for inspectors and bill collectors (PT-06, PT-43). Download a ward sheet before going out; surveys and
 * notice service are saved on the phone, even with no signal, and sent when back online. Nothing is deleted from the
 * phone until the server confirms it. The Revenue Officer reviews submitted surveys on the "Review" tab.
 */
@Component({
  selector: 'app-ptx-field',
  standalone: true,
  imports: [CommonModule, FormsModule, PtxFloorsEditorComponent],
  template: `
    @if (tab() === 'work') {
      <div class="ptx-alert" [ngClass]="online() ? 'ok' : 'warn'">
        {{ online() ? 'You are online.' : 'You are offline. Everything you save stays on this phone until you are back online.' }}
        {{ queue().length }} item(s) waiting to be sent.
        <button class="ptx-btn sm primary" (click)="sync()" [disabled]="!online() || !queue().length || busy()">Send now</button>
      </div>

      <div class="ptx-card">
        <h3>1. Download your ward sheet (before going out)</h3>
        <div class="ptx-row">
          <label>{{ i18n.t('ward') }}
            <select [(ngModel)]="wardId"><option value="">Choose…</option>@for (w of access.wards; track w.wardId) { <option [value]="w.wardId">{{ w.wardNumber }} · {{ w.wardName }}</option> }</select>
          </label>
          <button class="ptx-btn teal" (click)="download()" [disabled]="!wardId || busy()">Download</button>
        </div>
        @if (sheet(); as s) {
          <p class="ptx-muted">Ward {{ s.ward.wardNumber }} · downloaded {{ dmy(s.downloadedAt) }} · {{ s.properties.length }} properties · {{ s.buildingsToVerify.length }} building(s) to verify · {{ s.noticesToServe.length }} notice(s) to serve</p>
        }
      </div>

      @if (sheet(); as s) {
        @if (can('survey.capture')) {
          <div class="ptx-card">
            <h3>2. Survey a property or building</h3>
            <div class="ptx-form">
              <label>What are you checking?
                <select [(ngModel)]="sv.target" (change)="pick()">
                  <option value="">Choose…</option>
                  <optgroup label="Properties on the register">@for (p of s.properties; track p.upin) { <option [value]="'P:' + p.upin">{{ p.doorNo }} · {{ p.ownerNames }}</option> }</optgroup>
                  <optgroup label="Buildings with no property number">@for (b of s.buildingsToVerify; track b.footprintId) { <option [value]="'B:' + b.footprintId">{{ b.ref }} · about {{ b.mapBuiltupSqft }} sq ft</option> }</optgroup>
                </select>
              </label>
            </div>
            @if (sv.target) {
              @if (sv.target.startsWith('B:')) {
                <div class="ptx-form">
                  <label>Occupant / owner name * <input [(ngModel)]="sv.occupantName" /></label>
                  <label>Door no. <input [(ngModel)]="sv.doorNo" /></label>
                  <label style="grid-column: 1 / -1">Address * <input [(ngModel)]="sv.address" /></label>
                </div>
              }
              <div class="ptx-form"><label>{{ i18n.t('siteArea') }} <input type="number" min="0" [(ngModel)]="sv.siteAreaSqyd" /></label>
                <label>Remarks <input [(ngModel)]="sv.remarks" /></label></div>
              <app-ptx-floors-editor [access]="access" [(floors)]="sv.floors"></app-ptx-floors-editor>
              <div class="ptx-row">
                <button class="ptx-btn sm" (click)="gps()">Capture GPS</button>
                @if (sv.lat !== null) { <span class="ptx-muted">{{ sv.lat }}, {{ sv.lng }}</span> }
                <label>Photo (required) <input type="file" accept="image/*" capture="environment" (change)="photo($event)" /></label>
                <span class="ptx-muted">{{ sv.photos.length }} photo(s)</span>
              </div>
              <button class="ptx-btn primary big" (click)="saveSurvey()" [disabled]="busy()">Save survey on this phone</button>
            }
          </div>
        }
        @if (can('notice.serve') && s.noticesToServe.length) {
          <div class="ptx-card">
            <h3>{{ noticeStepNo() }}. Serve notices</h3>
            @for (n of s.noticesToServe; track n.noticeNo) {
              <div class="ptx-row" style="align-items: center">
                <div style="flex: 1; min-width: 200px"><span class="ptx-mono">{{ n.noticeNo }}</span> {{ n.noticeType.toLowerCase() }} · ₹{{ n.amount | number: '1.0-0' }}<br /><small class="ptx-muted">{{ n.upin }} · {{ n.address }}</small></div>
                <button class="ptx-btn sm primary" (click)="serve(n, true)">Served</button>
                <button class="ptx-btn sm" (click)="serve(n, false)">Could not serve</button>
              </div>
            }
          </div>
        }
      }

      @if (sheet(); as s2) {
        @if (can('notice.serve') && s2.billsToDeliver?.length) {
          <div class="ptx-card">
            <h3>{{ deliverStepNo() }}. Deliver bills ({{ s2.billsToDeliver!.length }} left)</h3>
            <p class="ptx-muted">In door-number order. Hand the printed bill to the owner or occupier.</p>
            @for (b of s2.billsToDeliver!; track b.demandNo) {
              <div class="ptx-row" style="align-items: center">
                <div style="flex: 1; min-width: 200px"><b>{{ b.doorNo || b.upin }}</b> · {{ b.ownerNames }} · ₹{{ b.amount | number: '1.0-0' }}<br /><small class="ptx-muted">{{ b.address }}</small></div>
                <button class="ptx-btn sm primary" (click)="deliver(b, true)">Delivered</button>
                <button class="ptx-btn sm" (click)="deliver(b, false)">Could not</button>
              </div>
            }
          </div>
        }
      }

      <div class="ptx-card">
        <h3>Waiting on this phone</h3>
        @for (q of queue(); track q.clientRef) {
          <p>{{ q.kind === 'SURVEY' ? 'Survey' : q.kind === 'BILL_DELIVERY' ? 'Bill' : 'Notice' }}: {{ q.label }} <small class="ptx-muted">saved {{ dmy(q.savedAt) }}</small>
            @if (q.lastError) { <br /><span class="ptx-chip ARREARS">{{ q.lastError }}</span> }
            <button class="ptx-btn sm ghost" (click)="discard(q)">Delete</button></p>
        } @empty { <p class="ptx-muted">Nothing waiting. Everything has been sent.</p> }
      </div>
    }

    @if (tab() === 'review') {
      <div class="ptx-card">
        <h2>Submitted surveys</h2>
        @for (s of surveys(); track s.id) {
          <div class="ptx-card" style="margin-top: 0.6rem">
            <p><b>{{ s.surveyType === 'VERIFY' ? 'Verification of ' + s.upin : 'Building with no property number' }}</b> · ward {{ s.wardNumber }} · {{ s.capturedBy }} · {{ dmy(s.capturedAt) }}</p>
            @if (s.data?.occupantName) { <p>{{ s.data.occupantName }} — {{ s.data.address }}</p> }
            <p class="ptx-muted">Surveyed: @for (f of s.data?.floors || []; track $index) { floor {{ f.floorNo }} {{ f.usageCode.toLowerCase() }} {{ f.builtupSqft }} sq ft; }
              @if (s.recordedFloors.length) { · On record: @for (f of s.recordedFloors; track $index) { floor {{ f.floorNo }} {{ f.usageCode.toLowerCase() }} {{ f.builtupSqft }} sq ft; } }</p>
            @if (s.data?.remarks) { <p class="ptx-muted">"{{ s.data.remarks }}"</p> }
            <div class="ptx-row">
              <button class="ptx-btn sm" (click)="decide(s, 'MATCHES_RECORD')">Matches the record</button>
              <button class="ptx-btn sm primary" (click)="decide(s, 'OPEN_CASE')">Open an application</button>
              <button class="ptx-btn sm" (click)="decide(s, 'CLOSE')">Close (not a building / no action)</button>
            </div>
          </div>
        } @empty { <p class="ptx-muted">No surveys waiting for review.</p> }
      </div>
    }
  `,
})
export class PtxFieldComponent implements OnInit, OnDestroy {
  @Input({ required: true }) access!: PtxAccess;
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  private cdr = inject(ChangeDetectorRef);
  i18n = inject(PtxI18nService);
  dmy = dmy;

  /** The part to show, chosen in the sidebar. */
  @Input() view = '';
  tab = signal<Tab>('work');
  online = signal(navigator.onLine);
  wardId = '';
  sheet = signal<WardSheet | null>(null);
  queue = signal<OfflineItem[]>([]);
  surveys = signal<Survey[]>([]);
  reviewTotal = signal(0);
  busy = signal(false);
  sv: { target: string; occupantName: string; doorNo: string; address: string; siteAreaSqyd: number | null; remarks: string; floors: Floor[];
    lat: number | null; lng: number | null; photos: string[] } = this.blankSurvey();

  private onOnline = () => { this.online.set(true); this.sync(); };
  private onOffline = () => this.online.set(false);

  ngOnInit(): void {
    window.addEventListener('online', this.onOnline);
    window.addEventListener('offline', this.onOffline);
    this.tab.set(this.view === 'review' || !(this.can('survey.capture') || this.can('notice.serve')) ? 'review' : 'work');
    this.refreshQueue();
    OfflineQueue.sheets().then((s) => {
      if (s.length) { this.sheet.set(s[0]); this.wardId = s[0].wardId; this.cdr.markForCheck(); }
    }).catch(() => undefined);
    if (this.can('survey.review')) this.loadReview();
  }

  ngOnDestroy(): void {
    window.removeEventListener('online', this.onOnline);
    window.removeEventListener('offline', this.onOffline);
  }

  can(p: string): boolean {
    return this.access.permissions.includes(p);
  }

  /** Step numbers shift up when a role (e.g. a bill collector) has no survey step, so none is skipped. */
  noticeStepNo(): number {
    return this.can('survey.capture') ? 3 : 2;
  }

  deliverStepNo(): number {
    return this.can('survey.capture') ? 4 : 3;
  }

  private blankSurvey() {
    return { target: '', occupantName: '', doorNo: '', address: '', siteAreaSqyd: null as number | null, remarks: '', floors: [] as Floor[],
      lat: null as number | null, lng: null as number | null, photos: [] as string[] };
  }

  setTab(t: Tab): void {
    this.tab.set(t);
    if (t === 'review') this.loadReview();
  }

  refreshQueue(): void {
    OfflineQueue.all().then((q) => { this.queue.set(q); this.cdr.markForCheck(); }).catch(() => this.queue.set([]));
  }

  download(): void {
    this.busy.set(true);
    this.ptx.get<WardSheet>('/field/sheet', { wardId: this.wardId }).subscribe({
      next: async (s) => {
        this.sheet.set(s);
        try { await OfflineQueue.saveSheet(s); } catch { this.dialog.showToast('Could not keep the sheet on this phone for offline use.', 'warning'); }
        this.busy.set(false);
        this.dialog.showToast('Ward sheet downloaded. You can work offline now.', 'success');
      },
      error: (e) => { this.busy.set(false); this.dialog.showToast(errorText(e), 'error'); },
    });
  }

  pick(): void {
    const t = this.sv.target;
    const s = this.sheet();
    if (!t || !s) return;
    this.sv.floors = [];
    if (t.startsWith('P:')) {
      const p = s.properties.find((x) => x.upin === t.slice(2));
      if (p) { this.sv.floors = p.floors.map((f) => ({ ...f })); this.sv.siteAreaSqyd = p.siteAreaSqyd; }
    } else {
      this.sv.floors = [{ floorNo: 0, usageCode: this.access.codes.USAGE?.[0]?.code || '', constructionCode: this.access.codes.CONSTRUCTION?.[0]?.code || '', builtupSqft: 0, occupancy: 'OWNER' }];
    }
  }

  async gps(): Promise<void> {
    try {
      const p = await currentPosition();
      this.sv.lat = p.lat; this.sv.lng = p.lng;
      this.cdr.markForCheck();
    } catch (e: any) {
      this.dialog.showToast(e.message, 'warning');
    }
  }

  /** Photos are shrunk and kept on the phone as data until synced; they are uploaded just before the record is sent. */
  async photo(ev: Event): Promise<void> {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    try {
      this.sv.photos.push(await compressPhoto(file));
      this.cdr.markForCheck();
    } catch (e: any) {
      this.dialog.showToast(e.message, 'error');
    }
    input.value = '';
  }

  async saveSurvey(): Promise<void> {
    const t = this.sv.target;
    const s = this.sv;
    if (s.lat === null) { this.dialog.showToast('Capture the GPS location first.', 'warning'); return; }
    if (!s.photos.length) { this.dialog.showToast('Add at least one photo.', 'warning'); return; }
    const isBuilding = t.startsWith('B:');
    if (isBuilding && (!s.occupantName.trim() || !s.address.trim())) { this.dialog.showToast('Enter the occupant name and address.', 'warning'); return; }
    const payload: any = { clientRef: newKey(), surveyType: isBuilding ? 'NEW_BUILDING' : 'VERIFY', latitude: s.lat, longitude: s.lng, capturedAt: new Date().toISOString(),
      floors: s.floors.map((f) => ({ ...f, floorNo: Number(f.floorNo), builtupSqft: Number(f.builtupSqft) })), siteAreaSqyd: s.siteAreaSqyd === null ? null : Number(s.siteAreaSqyd),
      remarks: s.remarks || null };
    if (isBuilding) Object.assign(payload, { footprintId: t.slice(2), occupantName: s.occupantName, address: s.address, doorNo: s.doorNo || null, wardId: this.wardId });
    else payload.upin = t.slice(2);
    await OfflineQueue.put({ clientRef: payload.clientRef, kind: 'SURVEY', savedAt: new Date().toISOString(), label: isBuilding ? s.address : t.slice(2), payload, photos: s.photos });
    this.sv = this.blankSurvey();
    this.refreshQueue();
    this.dialog.showToast('Saved on this phone.', 'success');
    if (this.online()) this.sync();
  }

  async serve(n: { noticeNo: string; upin: string }, served: boolean): Promise<void> {
    let reason: string | null = null;
    if (!served) {
      reason = await this.dialog.prompt({ title: 'Why could it not be served?', inputLabel: 'Reason', required: true });
      if (!reason) return;
    }
    let pos: { lat: number; lng: number } | null = null;
    try { pos = await currentPosition(); } catch { /* service is still recorded; GPS is optional here */ }
    const payload = { noticeNo: n.noticeNo, served, servedAt: new Date().toISOString(), latitude: pos?.lat ?? null, longitude: pos?.lng ?? null, reason, clientRef: newKey() };
    await OfflineQueue.put({ clientRef: payload.clientRef, kind: 'NOTICE_SERVICE', savedAt: new Date().toISOString(), label: `${n.noticeNo} (${served ? 'served' : 'not served'})`, payload, photos: [] });
    this.sheet.update((s) => (s ? { ...s, noticesToServe: s.noticesToServe.filter((x) => x.noticeNo !== n.noticeNo) } : s));
    this.refreshQueue();
    if (this.online()) this.sync();
  }

  /** A bill handed over, or why not, saved on the phone and sent when there is signal (PT-20). */
  async deliver(b: { demandNo: string; upin: string }, delivered: boolean): Promise<void> {
    let note: string | null = null;
    if (!delivered) {
      note = await this.dialog.prompt({ title: 'Why could the bill not be delivered?', inputLabel: 'Reason', placeholder: 'e.g. House locked, owner away', required: true });
      if (!note) return;
    }
    let pos: { lat: number; lng: number } | null = null;
    try { pos = await currentPosition(); } catch { /* the delivery is still recorded without the location */ }
    const payload = { demandNo: b.demandNo, delivered, note, deliveredAt: new Date().toISOString(), latitude: pos?.lat ?? null, longitude: pos?.lng ?? null };
    await OfflineQueue.put({ clientRef: newKey(), kind: 'BILL_DELIVERY', savedAt: new Date().toISOString(), label: `${b.upin} (${delivered ? 'delivered' : 'not delivered'})`, payload, photos: [] });
    this.sheet.update((s) => (s ? { ...s, billsToDeliver: (s.billsToDeliver || []).filter((x) => x.demandNo !== b.demandNo) } : s));
    this.refreshQueue();
    if (this.online()) this.sync();
  }

  async discard(q: OfflineItem): Promise<void> {
    if (!(await this.dialog.confirm({ title: 'Delete from this phone?', message: 'It has not been sent. This cannot be undone.', confirmText: 'Delete', variant: 'destructive' }))) return;
    await OfflineQueue.remove(q.clientRef);
    this.refreshQueue();
  }

  /** Sends waiting items one by one; an item leaves the phone only after the server confirms it. Repeats are ignored by the server. */
  async sync(): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true);
    let sent = 0;
    for (const item of await OfflineQueue.all()) {
      try {
        if (item.kind === 'SURVEY') {
          const refs: string[] = [];
          for (const p of item.photos) refs.push((await this.ptx.upload(dataUrlToBlob(p), 'survey.jpg').toPromise())!.ref);
          const r = await this.ptx.post('/field/surveys', { surveys: [{ ...item.payload, photoRefs: refs }] }).toPromise();
          const res = r.results[0];
          if (res.result === 'ERROR') throw new Error(res.error);
        } else if (item.kind === 'BILL_DELIVERY') {
          const r = await this.ptx.post('/demands/delivery', { items: [item.payload] }).toPromise();
          if (r.results[0].result === 'ERROR') throw new Error(r.results[0].error);
        } else {
          const r = await this.ptx.post('/field/notice-service', { items: [item.payload] }).toPromise();
          if (r.results[0].result === 'ERROR') throw new Error(r.results[0].error);
        }
        await OfflineQueue.remove(item.clientRef);
        sent++;
      } catch (e: any) {
        await OfflineQueue.put({ ...item, lastError: e?.message && !e.status ? e.message : errorText(e) });
      }
    }
    this.busy.set(false);
    this.refreshQueue();
    if (sent) this.dialog.showToast(`${sent} item(s) sent.`, 'success');
    this.cdr.markForCheck();
  }

  loadReview(): void {
    this.ptx.get('/surveys', { status: 'SUBMITTED', limit: 50 }).subscribe({
      next: (r) => { this.surveys.set(r.items); this.reviewTotal.set(r.total); },
      error: (e) => { this.surveys.set([]); this.dialog.showToast(errorText(e), 'error'); },
    });
  }

  async decide(s: Survey, outcome: 'MATCHES_RECORD' | 'OPEN_CASE' | 'CLOSE'): Promise<void> {
    const remark = await this.dialog.prompt({ title: 'Your remark', inputLabel: 'Remark', required: true });
    if (!remark) return;
    this.ptx.post(`/surveys/${s.id}/decision`, { outcome, remark }).subscribe({
      next: (r) => {
        this.dialog.showToast(r.applicationNo ? `Application ${r.applicationNo} opened.` : 'Survey reviewed.', 'success');
        this.loadReview();
      },
      error: (e) => this.dialog.showToast(errorText(e), 'error'),
    });
  }
}
