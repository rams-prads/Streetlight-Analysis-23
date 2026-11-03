import { Component, EventEmitter, Input, OnChanges, Output, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { forkJoin, of } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { CitizenAccount } from '../../../core/models/ptx.model';
import { PtxService } from '../../../core/services/ptx.service';
import { PtxI18nService } from '../../../core/services/ptx-i18n.service';
import { IconComponent } from '../../../shared/components/icon/icon.component';
import { dmy } from '../ptx-utils';

/** The citizen's saved properties, as the portal lists them. */
export interface DashProperty {
  upin: string;
  doorNo: string | null;
  mobileNumber: string;
  totalDue: number;
  payNow: number;
}

/** Where a click on the dashboard should take the citizen. */
export interface DashOpen {
  upin: string;
  page: 'property' | 'bills' | 'certs' | 'requests';
}

/** One property's share of a half-year. */
interface PeriodLine {
  upin: string;
  door: string;
  demandNo: string;
  billed: number;
  paid: number;
  paidOn: string | null;
  receiptNo: string | null;
  mode: string | null;
}

/** A half-year bill (GWMC bills twice a year: April to September, due 30 June; October to March, due 30 December). */
interface Period {
  label: string;
  months: string;
  fy: string;
  start: Date;
  end: Date;
  dueDate: string;
  billed: number;
  paid: number;
  paidOn: string | null;
  status: 'paid' | 'part' | 'due' | 'overdue';
  isNow: boolean;
  lines: PeriodLine[];
  earlier?: boolean;
}

const DAY = 86_400_000;
/** Key and title of the column for tax owed from before the listed bills. */
const EARLIER = 'Unpaid from earlier years';

/**
 * "Your tax at a glance" on the citizen portal's home page: what is due now, what was paid this financial year, how often it
 * was paid on time, open requests, and every half-year's bill beside its payment. Choosing a half-year (pointer, arrow keys
 * or touch) opens its bill and receipt in the panel beside the chart.
 */
@Component({
  selector: 'app-ptx-citizen-dashboard',
  standalone: true,
  imports: [CommonModule, IconComponent],
  templateUrl: './ptx-citizen-dashboard.component.html',
})
export class PtxCitizenDashboardComponent implements OnChanges {
  @Input({ required: true }) properties: DashProperty[] = [];
  @Output() open = new EventEmitter<DashOpen>();

  private ptx = inject(PtxService);
  i18n = inject(PtxI18nService);
  dmy = dmy;

  readonly props = signal<DashProperty[]>([]);
  accounts = signal<CitizenAccount[] | null>(null);
  /** '' shows every property together. */
  only = signal<string>('');
  selectedKey = signal<string>('');

  private today = startOfDay(new Date());

  ngOnChanges(): void {
    const list = this.properties || [];
    this.props.set(list);
    if (!list.length) {
      this.accounts.set([]);
      return;
    }
    this.accounts.set(null);
    forkJoin(list.map((p) => this.ptx.citizenAccount(p.upin, p.mobileNumber).pipe(catchError(() => of(null))))).subscribe((r) => {
      this.accounts.set(r.filter((a): a is CitizenAccount => !!a));
      if (this.only() && !list.some((p) => p.upin === this.only())) this.only.set('');
      this.selectedKey.set('');
    });
  }

  L(en: string, te: string): string {
    return this.i18n.lang() === 'te' ? te : en;
  }

  /** The accounts in view (one property, or all of them). */
  private inView = computed(() => (this.accounts() || []).filter((a) => !this.only() || a.property.upin === this.only()));

  /** The current financial year, April to March. */
  fy = computed(() => {
    const t = this.today;
    const y = t.getMonth() >= 3 ? t.getFullYear() : t.getFullYear() - 1;
    return { start: new Date(y, 3, 1), end: new Date(y + 1, 2, 31), label: `${y}-${String((y + 1) % 100).padStart(2, '0')}` };
  });

  /**
   * Every half-year with its bills. What is still owed comes from the account's own dues (the ledger is the truth): it is
   * placed on the newest bills first, and anything older than the listed bills becomes an "Earlier years" column. Receipts
   * are then matched, oldest first, to the part of each bill that was paid.
   */
  periods = computed<Period[]>(() => {
    const byLabel = new Map<string, Period>();
    for (const a of this.inView()) {
      const door = a.property.doorNo || a.property.upin;
      const demands = [...a.demands].sort((x, y) => x.dueDate.localeCompare(y.dueDate));
      const receipts = [...a.receipts].filter((r) => r.status === 'VALID').sort((x, y) => x.date.localeCompare(y.date));

      // what is still owed on each bill, newest bill first
      let owed = Math.max(0, a.dues?.netPayable ?? a.dues?.totalDue ?? 0);
      const unpaid = new Map<string, number>();
      for (const d of [...demands].reverse()) {
        const u = Math.min(d.amount, owed);
        unpaid.set(d.demandNo, u);
        owed -= u;
      }
      if (owed > 0.005) {
        const p = byLabel.get(EARLIER) || this.earlierPeriod();
        p.billed += owed;
        p.lines.push({ upin: a.property.upin, door, demandNo: '', billed: owed, paid: 0, paidOn: null, receiptNo: null, mode: null });
        byLabel.set(EARLIER, p);
      }

      // receipts settle the paid part of each bill, oldest first
      let ri = 0;
      let left = receipts.length ? receipts[0].amount : 0;
      for (const d of demands) {
        const paid = d.amount - (unpaid.get(d.demandNo) || 0);
        let need = paid;
        let last: (typeof receipts)[number] | null = null;
        while (need > 0.005 && ri < receipts.length) {
          const take = Math.min(need, left);
          need -= take;
          left -= take;
          last = receipts[ri];
          if (left <= 0.005) {
            ri++;
            left = ri < receipts.length ? receipts[ri].amount : 0;
          }
        }
        const settled = paid >= d.amount - 0.005;
        const p = byLabel.get(d.periodLabel) || this.newPeriod(d.periodLabel, d.dueDate);
        p.billed += d.amount;
        p.paid += paid;
        if (settled && last && (!p.paidOn || last.date > p.paidOn)) p.paidOn = last.date;
        p.lines.push({ upin: a.property.upin, door, demandNo: d.demandNo, billed: d.amount, paid, paidOn: settled && last ? last.date : null,
          receiptNo: settled ? (last?.receiptNo ?? null) : null, mode: settled ? (last?.mode ?? null) : null });
        byLabel.set(d.periodLabel, p);
      }
    }
    const list = [...byLabel.values()].sort((x, y) => x.start.getTime() - y.start.getTime());
    for (const p of list) {
      if (p.earlier) continue;
      if (p.lines.some((l) => !l.paidOn)) p.paidOn = null;
      const due = new Date(p.dueDate);
      p.status = p.paid >= p.billed - 0.005 ? 'paid' : due < this.today ? 'overdue' : p.paid > 0.005 ? 'part' : 'due';
    }
    return list;
  });

  /** Tax owed from before the bills listed here (migrated or older arrears). */
  private earlierPeriod(): Period {
    return { label: EARLIER, months: this.L('Earlier', 'గతంలో'), fy: this.L('arrears', 'బకాయి'), start: new Date(1900, 0, 1), end: new Date(1900, 0, 1),
      dueDate: '', billed: 0, paid: 0, paidOn: null, status: 'overdue', isNow: false, lines: [], earlier: true };
  }

  private newPeriod(label: string, dueDate: string): Period {
    const fy = (label.match(/(\d{4})-(\d{2})/) || [])[0] || '';
    const y = parseInt(fy.slice(0, 4), 10) || new Date(dueDate).getFullYear();
    const second = /second|oct/i.test(label);
    const start = second ? new Date(y, 9, 1) : new Date(y, 3, 1);
    const end = second ? new Date(y + 1, 2, 31) : new Date(y, 8, 30);
    const months = (label.match(/\(([^)]+)\)/) || [])[1]?.replace('-', ' to ') || (second ? 'Oct to Mar' : 'Apr to Sep');
    return { label, months, fy, start, end, dueDate, billed: 0, paid: 0, paidOn: null, status: 'due',
      isNow: this.today >= start && this.today <= end, lines: [] };
  }

  /** Bar heights are relative to the largest half-year bill. */
  private maxBilled = computed(() => Math.max(1, ...this.periods().map((p) => p.billed)));
  barHeight(p: Period): number {
    return Math.max(8, Math.round((p.billed / this.maxBilled()) * 100));
  }
  paidShare(p: Period): number {
    return p.billed > 0 ? Math.min(100, Math.round((p.paid / p.billed) * 100)) : 0;
  }

  selected = computed<Period | null>(() => {
    const list = this.periods();
    return list.find((p) => p.label === this.selectedKey()) || list.find((p) => p.isNow) || list[list.length - 1] || null;
  });

  select(p: Period): void {
    this.selectedKey.set(p.label);
  }

  /** Left and right arrows move between half-years; Home and End jump to the ends. */
  onKey(e: KeyboardEvent): void {
    const list = this.periods();
    const at = list.findIndex((p) => p === this.selected());
    let next = at;
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') next = Math.min(list.length - 1, at + 1);
    else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') next = Math.max(0, at - 1);
    else if (e.key === 'Home') next = 0;
    else if (e.key === 'End') next = list.length - 1;
    else return;
    e.preventDefault();
    this.selectedKey.set(list[next].label);
    const host = (e.currentTarget as HTMLElement).querySelectorAll<HTMLButtonElement>('.ptx-dash-col');
    host[next]?.focus();
  }

  /** Days between paying and the due date: positive is early. */
  /** The due date has passed. */
  isPast(date: string | null): boolean {
    return !!date && startOfDay(new Date(date)) < this.today;
  }

  daysEarly(paidOn: string | null, dueDate: string): number | null {
    if (!paidOn) return null;
    return Math.round((startOfDay(new Date(dueDate)).getTime() - startOfDay(new Date(paidOn)).getTime()) / DAY);
  }
  timing(paidOn: string | null, dueDate: string): string {
    const d = this.daysEarly(paidOn, dueDate);
    if (d === null) return '';
    if (d > 0) return this.L(`${d} days early`, `${d} రోజులు ముందుగా`);
    if (d === 0) return this.L('On the due date', 'గడువు రోజున');
    return this.L(`${-d} days late`, `${-d} రోజులు ఆలస్యంగా`);
  }

  // ---- the four numbers at the top ----
  dueNow = computed(() => this.props().filter((p) => !this.only() || p.upin === this.only()).reduce((n, p) => n + Math.max(0, p.totalDue), 0));
  nextDue = computed(() => this.periods().find((p) => !p.earlier && p.status !== 'paid')?.dueDate || null);
  fyPaid = computed(() => {
    const { start, end } = this.fy();
    return this.inView().reduce((n, a) => n + a.receipts.filter((r) => r.status === 'VALID' && inRange(r.date, start, end)).reduce((s, r) => s + r.amount, 0), 0);
  });
  fyBilled = computed(() => {
    const { start, end } = this.fy();
    return this.periods().filter((p) => !p.earlier && p.start >= start && p.start <= end).reduce((n, p) => n + p.billed, 0);
  });
  fyBills = computed(() => {
    const { start, end } = this.fy();
    const list = this.periods().filter((p) => !p.earlier && p.start >= start && p.start <= end);
    return { paid: list.filter((p) => p.status === 'paid').length, all: list.length };
  });
  /** How much of this year's bills is settled (payments toward older arrears do not count here). */
  fyBillsPaid = computed(() => {
    const { start, end } = this.fy();
    return this.periods().filter((p) => !p.earlier && p.start >= start && p.start <= end).reduce((n, p) => n + p.paid, 0);
  });
  fyShare = computed(() => (this.fyBilled() > 0 ? Math.min(100, Math.floor((this.fyBillsPaid() / this.fyBilled()) * 100)) : 0));
  onTime = computed(() => {
    const settled = this.periods().flatMap((p) => p.lines.filter((l) => l.paidOn).map((l) => this.daysEarly(l.paidOn, p.dueDate) as number));
    const early = settled.filter((d) => d >= 0);
    const avg = early.length ? Math.round(early.reduce((n, d) => n + d, 0) / early.length) : 0;
    return { onTime: early.length, settled: settled.length, avgEarly: avg };
  });
  openRequests = computed(() =>
    this.inView().reduce((n, a) => n + a.cases.filter((c) => !['COMPLETED', 'REJECTED', 'CANCELLED'].includes(c.status)).length
      + (a.complaints || []).filter((c) => c.status !== 'RESOLVED').length, 0));
  certificates = computed(() => this.inView().reduce((n, a) => n + a.certificates.filter((c) => !c.validUntil || c.validUntil >= iso(this.today)).length, 0));

  /** The property a click on a number should open: the chosen one, or the first that has something to show. */
  private target(pick: (a: CitizenAccount) => boolean): string {
    const list = this.inView();
    return (list.find(pick) || list[0])?.property.upin || '';
  }
  go(page: DashOpen['page']): void {
    const upin =
      page === 'property' ? this.target((a) => a.payNow > 0)
      : page === 'requests' ? this.target((a) => a.cases.length > 0 || (a.complaints || []).length > 0)
      : page === 'certs' ? this.target((a) => a.certificates.length > 0)
      : this.target((a) => a.receipts.length > 0);
    if (upin) this.open.emit({ upin, page });
  }
  openLine(l: PeriodLine, page: DashOpen['page']): void {
    this.open.emit({ upin: l.upin, page });
  }

  statusText(p: Period): string {
    return p.status === 'paid' ? this.L('Paid', 'చెల్లించారు') : p.status === 'part' ? this.L('Part paid', 'కొంత చెల్లించారు')
      : p.status === 'overdue' ? this.L('Overdue', 'గడువు దాటింది') : this.L('Due', 'బకాయి');
  }
  chipClass(p: Period): string {
    return p.status === 'paid' ? 'PAID' : p.status === 'overdue' ? 'ARREARS' : 'DUE';
  }
  /** Read out for each half-year column. */
  colLabel(p: Period): string {
    const paid = p.paidOn ? `, ${this.L('paid on', 'చెల్లించిన తేదీ')} ${dmy(p.paidOn)}` : '';
    return `${p.label}: ${this.L('billed', 'బిల్లు')} ₹${p.billed.toFixed(2)}, ${this.statusText(p)}${paid}`;
  }

  door(upin: string): string {
    return this.props().find((p) => p.upin === upin)?.doorNo || upin;
  }
}

function startOfDay(d: Date): Date {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate());
}
function iso(d: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
function inRange(date: string, start: Date, end: Date): boolean {
  const d = startOfDay(new Date(date));
  return d >= start && d <= end;
}
