import { Component, EventEmitter, Input, OnInit, Output, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Complaint, PtxAccess } from '../../../../../core/models/ptx.model';
import { PtxService } from '../../../../../core/services/ptx.service';
import { PtxI18nService } from '../../../../../core/services/ptx-i18n.service';
import { DialogService } from '../../../../../core/services/dialog.service';
import { dmy, errorText } from '../../../ptx-utils';

/**
 * Record a complaint (staff, at the counter or by phone) or work on one: start it, resolve it with a reply the owner will
 * read, or reopen it (PT-29). Each category carries its own time limit; the owner is told by SMS at each step.
 */
@Component({
  selector: 'app-complaint-dialog',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="ptx-modal-backdrop" (click)="close()"></div>
    <section class="ptx-modal" role="dialog" aria-modal="true" aria-label="Complaint">
      <div class="ptx-modal-head">
        <h2>{{ complaintNo ? 'Complaint ' + complaintNo : 'Record a complaint' }}</h2>
        <button class="ptx-btn" (click)="close()">{{ i18n.t('close') }}</button>
      </div>
      <div class="ptx-modal-body">
        @if (!complaintNo) {
          <div class="ptx-form">
            <label>{{ i18n.t('upin') }} *
              <input [(ngModel)]="form.upin" placeholder="e.g. GWMC-P-00000006" />
            </label>
            <label>What is it about? *
              <select [(ngModel)]="form.category">
                <option value="">Choose…</option>
                @for (c of access.codes.COMPLAINT_CATEGORY || []; track c.code) { <option [value]="c.code">{{ i18n.name(c) }}</option> }
              </select>
            </label>
            <label>Bill, receipt or application number (if any) <input [(ngModel)]="form.refNo" /></label>
            <label>Caller's mobile (for SMS) <input [(ngModel)]="form.mobileNumber" inputmode="numeric" maxlength="10" /></label>
            <label style="grid-column: 1 / -1">What is the problem? * <textarea [(ngModel)]="form.description" placeholder="At least 10 characters"></textarea></label>
          </div>
          @if (hint()) { <div class="ptx-alert info">{{ hint() }}</div> }
        } @else if (c(); as x) {
          <div class="ptx-alert" [ngClass]="x.status === 'RESOLVED' ? 'ok' : x.overdue ? 'error' : 'info'">
            <b>{{ x.status === 'OPEN' ? 'Received' : x.status === 'IN_PROGRESS' ? 'Being looked into' : 'Resolved' }}.</b> {{ x.statusText }}
            @if (x.overdue) { <b> Past its time limit{{ x.escalationLevel ? ' (escalated, level ' + x.escalationLevel + ')' : '' }}.</b> }
          </div>
          <div class="ptx-card ptx-kv">
            <div><span>{{ i18n.t('upin') }}</span>{{ x.upin }}</div>
            <div><span>About</span>{{ x.categoryName }}</div>
            <div><span>Filed</span>{{ dmy(x.createdAt) }} · {{ x.filedBy }} · {{ x.channel }}</div>
            <div><span>Reply due by</span>{{ dmy(x.dueAt) }}</div>
            @if (x.refNo) { <div><span>Reference</span>{{ x.refNo }}</div> }
          </div>
          <div class="ptx-card"><h3>The problem</h3><p>{{ x.description }}</p>@if (x.hint) { <p class="ptx-muted">{{ x.hint }}</p> }</div>
          @if (x.status === 'RESOLVED') {
            <div class="ptx-card"><h3>Reply sent to the owner</h3><p>{{ x.resolution }}</p>
              <p class="ptx-muted">{{ x.outcome === 'ACTION_TAKEN' ? 'Action taken' : 'No change needed' }} · {{ x.resolvedBy }} · {{ dmy(x.resolvedAt) }}@if (x.applicationNo) { · application {{ x.applicationNo }} }</p></div>
          }
          @if (can('complaint.work')) {
            <div class="ptx-card">
              <h3>What next?</h3>
              @if (x.status === 'RESOLVED') {
                <label>Why is it being reopened? * <input [(ngModel)]="remark" /></label>
                <button class="ptx-btn" (click)="act('REOPEN')" [disabled]="busy() || remark.trim().length < 3">Reopen</button>
              } @else {
                @if (x.status === 'OPEN') {
                  <div class="ptx-row"><label style="flex: 1">Note <input [(ngModel)]="startNote" placeholder="e.g. Checking the delivery record" /></label>
                    <button class="ptx-btn teal" (click)="start()" [disabled]="busy()">Start looking into it</button></div>
                }
                <div class="ptx-form">
                  <label>Result *
                    <select [(ngModel)]="outcome"><option value="">Choose…</option><option value="ACTION_TAKEN">Action taken</option><option value="NO_CHANGE_NEEDED">No change needed</option></select>
                  </label>
                  <label>Application opened to fix it (if any) <input [(ngModel)]="applicationNo" placeholder="PTA-GWMC-..." /></label>
                  <label style="grid-column: 1 / -1">Reply for the owner * <textarea [(ngModel)]="remark" placeholder="A sentence or two the owner will read by SMS and on the portal"></textarea></label>
                </div>
                <button class="ptx-btn primary" (click)="act('RESOLVE')" [disabled]="busy() || !outcome || remark.trim().length < 10">Resolve and tell the owner</button>
              }
            </div>
          }
          @if (x.timeline?.length) {
            <div class="ptx-card"><h3>Timeline</h3>
              @for (t of x.timeline; track $index) { <p><small class="ptx-muted">{{ dmy(t.at) }} · {{ t.actor }}</small> — {{ t.action.toLowerCase() }} {{ t.remark || '' }}</p> }
            </div>
          }
        } @else {
          <p class="ptx-muted">{{ i18n.t('loading') }}</p>
        }
      </div>
      @if (!complaintNo) {
        <div class="ptx-modal-foot">
          <button class="ptx-btn" (click)="close()">{{ i18n.t('cancel') }}</button>
          <button class="ptx-btn primary" (click)="file()" [disabled]="busy() || !form.upin.trim() || !form.category || form.description.trim().length < 10">Record the complaint</button>
        </div>
      }
    </section>
  `,
})
export class ComplaintDialogComponent implements OnInit {
  @Input({ required: true }) access!: PtxAccess;
  @Input() complaintNo = '';
  @Input() presetUpin = '';
  @Output() closed = new EventEmitter<boolean>();
  private ptx = inject(PtxService);
  private dialog = inject(DialogService);
  i18n = inject(PtxI18nService);
  dmy = dmy;

  c = signal<Complaint | null>(null);
  busy = signal(false);
  form = { upin: '', category: '', refNo: '', mobileNumber: '', description: '' };
  remark = '';
  startNote = '';
  outcome = '';
  applicationNo = '';
  private changed = false;

  ngOnInit(): void {
    this.form.upin = this.presetUpin;
    if (this.complaintNo) this.load();
  }

  can(p: string): boolean {
    return this.access.permissions.includes(p);
  }

  hint(): string {
    const c = this.access.codes.COMPLAINT_CATEGORY?.find((x) => x.code === this.form.category);
    return (c?.extra as any)?.['hint'] || '';
  }

  load(): void {
    this.ptx.get<Complaint>(`/complaints/${encodeURIComponent(this.complaintNo)}`).subscribe({
      next: (c) => { this.c.set(c); this.remark = ''; },
      error: (e) => { this.dialog.showToast(errorText(e), 'error'); this.closed.emit(this.changed); },
    });
  }

  file(): void {
    this.busy.set(true);
    this.ptx.post<Complaint>('/complaints', { ...this.form, upin: this.form.upin.trim().toUpperCase(), refNo: this.form.refNo || null,
      mobileNumber: this.form.mobileNumber || null, channel: 'COUNTER' }).subscribe({
      next: (c) => {
        this.busy.set(false);
        this.dialog.showToast(`Complaint ${c.complaintNo} recorded. Reply due by ${dmy(c.dueAt)}.`, 'success');
        this.closed.emit(true);
      },
      error: (e) => { this.busy.set(false); this.dialog.showToast(errorText(e), 'error'); },
    });
  }

  start(): void {
    this.send({ action: 'START', remark: this.startNote.trim() || 'Started' });
  }

  act(action: 'RESOLVE' | 'REOPEN'): void {
    this.send({ action, remark: this.remark, outcome: action === 'RESOLVE' ? this.outcome : null, applicationNo: this.applicationNo || null });
  }

  private send(body: any): void {
    this.busy.set(true);
    this.ptx.post(`/complaints/${encodeURIComponent(this.complaintNo)}/actions`, body).subscribe({
      next: (r) => {
        this.busy.set(false);
        this.changed = true;
        this.dialog.showToast(r.message, 'success');
        this.load();
      },
      error: (e) => { this.busy.set(false); this.dialog.showToast(errorText(e), 'error'); },
    });
  }

  close(): void {
    this.closed.emit(this.changed);
  }
}
