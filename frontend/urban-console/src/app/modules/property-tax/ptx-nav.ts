/**
 * The Property Tax sidebar: every screen a member of staff can open, grouped by the kind of work, each shown only to the
 * roles who do that work (by the permission that does it, PT-NF-10), so each person's menu holds only their own job. A screen with parts (for example Collection) lists each part as its own
 * item, so the sidebar is the only navigation. Labels are English and Telugu (PT-NF-41).
 */
export interface NavItem {
  section: string;
  view?: string;
  icon: string;
  en: string;
  te: string;
  /** One line under the page title. */
  hint: string;
  anyOf: string[];
  /** Count shown beside the item, loaded by the shell. */
  badge?: 'applications' | 'approvals' | 'complaints' | 'petitions' | 'surveys' | 'deeds';
}

export interface NavGroup {
  key: string;
  icon: string;
  en: string;
  te: string;
  items: NavItem[];
}

export const HOME: NavItem = {
  section: 'home', icon: 'ri-home-5-line', en: 'Home', te: 'హోమ్', hint: 'What needs you today', anyOf: [],
};

export const NAV: NavGroup[] = [
  {
    key: 'work', icon: 'ri-inbox-2-line', en: 'Work', te: 'పని',
    items: [
      { section: 'cases', view: 'cases', icon: 'ri-file-list-3-line', en: 'Applications', te: 'దరఖాస్తులు', anyOf: ['property.edit', 'approval.decide', 'case.create'], badge: 'applications',
        hint: 'New assessments, changes of owner, splits, merges and exemptions, step by step' },
      { section: 'approvals', icon: 'ri-checkbox-circle-line', en: 'Approvals', te: 'ఆమోదాలు', anyOf: ['approval.decide', 'approval.request', 'rates.approve'],
        badge: 'approvals', hint: 'Waivers, refunds, write-offs and rate changes that need a second person' },
      { section: 'cases', view: 'complaints', icon: 'ri-feedback-line', en: 'Complaints', te: 'ఫిర్యాదులు', anyOf: ['complaint.work', 'case.create', 'petition.decide'], badge: 'complaints',
        hint: 'Complaints from owners, each with a time limit' },
      { section: 'cases', view: 'petitions', icon: 'ri-scales-3-line', en: 'Petitions and appeals', te: 'పిటిషన్లు, అప్పీళ్లు', anyOf: ['petition.decide', 'approval.decide'],
        badge: 'petitions', hint: 'Requests to revise a tax, and appeals against the decision' },
      { section: 'field', view: 'review', icon: 'ri-survey-line', en: 'Survey review', te: 'సర్వే పరిశీలన', anyOf: ['survey.review'], badge: 'surveys',
        hint: 'What inspectors found in the field, next to what is on record' },
      { section: 'connections', view: 'deeds', icon: 'ri-contract-line', en: 'Registered deeds', te: 'రిజిస్టర్డ్ దస్తావేజులు', anyOf: ['integration.run'],
        badge: 'deeds', hint: 'Sale and gift deeds from the Registration Department that start a change of owner' },
    ],
  },
  {
    key: 'field', icon: 'ri-map-pin-2-line', en: 'Field', te: 'క్షేత్రం',
    items: [
      { section: 'field', view: 'work', icon: 'ri-walk-line', en: 'My field work', te: 'నా క్షేత్ర పని', anyOf: ['survey.capture', 'notice.serve'],
        hint: 'Download your ward, then survey, serve notices or deliver bills, even with no signal' },
    ],
  },
  {
    key: 'records', icon: 'ri-building-line', en: 'Records', te: 'రికార్డులు',
    items: [
      { section: 'properties', icon: 'ri-building-line', en: 'Properties', te: 'ఆస్తులు', anyOf: ['property.view'],
        hint: 'Find any property by number, owner, mobile or door number' },
      { section: 'map', icon: 'ri-map-2-line', en: 'Map', te: 'మ్యాప్', anyOf: ['survey.capture', 'notice.serve', 'arrears.manage', 'approval.decide', 'rates.approve'], hint: 'Properties and collection on the city map' },
    ],
  },
  {
    key: 'billing', icon: 'ri-bill-line', en: 'Billing', te: 'బిల్లింగ్',
    items: [
      { section: 'billing', view: 'bills', icon: 'ri-bill-line', en: 'Bills', te: 'బిల్లులు', anyOf: ['billing.view'], hint: 'Every bill raised, and its delivery' },
      { section: 'billing', view: 'jobs', icon: 'ri-play-list-add-line', en: 'Bill runs', te: 'బిల్లు రన్‌లు', anyOf: ['demand.run', 'rates.approve'], hint: 'Raise the bills for a period, ward by ward' },
      { section: 'billing', view: 'rates', icon: 'ri-percent-line', en: 'Rate tables', te: 'రేట్ పట్టికలు', anyOf: ['rates.propose', 'rates.approve'],
        hint: 'Tax rates by zone, use and construction, with their approvals' },
    ],
  },
  {
    key: 'collection', icon: 'ri-wallet-3-line', en: 'Collection', te: 'వసూలు',
    items: [
      { section: 'collection', view: 'pay', icon: 'ri-hand-coin-line', en: 'Take a payment', te: 'చెల్లింపు తీసుకోండి', anyOf: ['payment.collect'],
        hint: 'Cash, cheque, demand draft, UPI or card, with a printed receipt' },
      { section: 'collection', view: 'receipts', icon: 'ri-file-paper-2-line', en: 'Receipts', te: 'రసీదులు', anyOf: ['payment.collect', 'payment.reconcile', 'dayclose.verify'],
        hint: 'Every receipt, with reprints and cancellations' },
      { section: 'collection', view: 'dayclose', icon: 'ri-calendar-check-line', en: 'Day-end closing', te: 'రోజు ముగింపు', anyOf: ['dayclose.submit', 'dayclose.verify'],
        hint: 'Count the cash at the end of the day and hand it over' },
      { section: 'collection', view: 'banking', icon: 'ri-bank-line', en: 'Banking', te: 'బ్యాంకింగ్', anyOf: ['remittance.prepare', 'remittance.confirm'],
        hint: 'Cash and cheques taken to the bank, and the bank’s confirmation' },
      { section: 'collection', view: 'reconcile', icon: 'ri-arrow-left-right-line', en: 'Reconciliation', te: 'సమన్వయం', anyOf: ['payment.reconcile'],
        hint: 'Match online and BBPS payments with the bank statement' },
    ],
  },
  {
    key: 'arrears', icon: 'ri-alarm-warning-line', en: 'Arrears', te: 'బకాయిలు',
    items: [
      { section: 'arrears', view: 'defaulters', icon: 'ri-user-unfollow-line', en: 'Defaulters', te: 'బకాయిదారులు', anyOf: ['arrears.manage', 'reports.view.own'],
        hint: 'Who owes what, and for how long' },
      { section: 'arrears', view: 'notices', icon: 'ri-mail-send-line', en: 'Notices', te: 'నోటీసులు', anyOf: ['arrears.manage'], hint: 'Demand and distraint notices, and their service' },
      { section: 'arrears', view: 'recovery', icon: 'ri-auction-line', en: 'Recovery cases', te: 'వసూలు కేసులు', anyOf: ['arrears.manage'], hint: 'Cases taken further when notices are not paid' },
      { section: 'arrears', view: 'runs', icon: 'ri-timer-line', en: 'Interest and reminders', te: 'వడ్డీ, గుర్తుచేతలు', anyOf: ['arrears.manage'],
        hint: 'Monthly interest and SMS reminders' },
    ],
  },
  {
    key: 'reports', icon: 'ri-bar-chart-box-line', en: 'Reports', te: 'నివేదికలు',
    items: [
      { section: 'reports', view: 'dcb', icon: 'ri-table-line', en: 'Demand, collection, balance', te: 'డిమాండ్, వసూలు, బాకీ', anyOf: ['reports.view'],
        hint: 'Opening balance, demand, collection and closing balance for any period' },
      { section: 'reports', view: 'efficiency', icon: 'ri-line-chart-line', en: 'Collection efficiency', te: 'వసూలు సామర్థ్యం', anyOf: ['reports.view', 'reports.view.own'],
        hint: 'How much of what was due has been collected, by ward and zone' },
      { section: 'reports', view: 'daily', icon: 'ri-calendar-line', en: 'Daily collection', te: 'రోజువారీ వసూలు', anyOf: ['reports.view', 'reports.view.own'],
        hint: 'Collection by day, counter and payment mode' },
      { section: 'reports', view: 'heads', icon: 'ri-book-2-line', en: 'Account heads', te: 'ఖాతా శీర్షికలు', anyOf: ['reports.view'],
        hint: 'Collection split by account head, for Finance' },
    ],
  },
  {
    key: 'admin', icon: 'ri-settings-3-line', en: 'Administration', te: 'పరిపాలన',
    items: [
      { section: 'admin', view: 'settings', icon: 'ri-equalizer-line', en: 'Settings', te: 'సెట్టింగులు', anyOf: ['settings.manage', 'rates.propose', 'audit.view'],
        hint: 'Every rule the city may change, with its history' },
      { section: 'admin', view: 'codes', icon: 'ri-list-check-2', en: 'Code lists', te: 'కోడ్ జాబితాలు', anyOf: ['settings.manage', 'rates.propose', 'audit.view'],
        hint: 'Uses, construction types, exemptions and other lists, in English and Telugu' },
      { section: 'admin', view: 'audit', icon: 'ri-shield-check-line', en: 'Audit trail', te: 'ఆడిట్ ట్రయల్', anyOf: ['audit.view'], hint: 'Who changed what, and when' },
      { section: 'admin', view: 'sms', icon: 'ri-message-2-line', en: 'SMS log', te: 'SMS లాగ్', anyOf: ['audit.view'], hint: 'Every message sent to owners' },
      { section: 'admin', view: 'migration', icon: 'ri-upload-cloud-2-line', en: 'Data migration', te: 'డేటా మైగ్రేషన్', anyOf: ['migration.run'],
        hint: 'Load records from the old system' },
      { section: 'connections', view: 'switches', icon: 'ri-plug-line', en: 'Connections', te: 'అనుసంధానాలు', anyOf: ['settings.manage', 'integration.run'],
        hint: 'Switch the links to other systems on or off' },
      { section: 'connections', view: 'state', icon: 'ri-government-line', en: 'State platform', te: 'రాష్ట్ర వేదిక', anyOf: ['integration.run'],
        hint: 'Exchange the register with the state property platform' },
      { section: 'connections', view: 'bbps', icon: 'ri-smartphone-line', en: 'BBPS', te: 'BBPS', anyOf: ['integration.run'],
        hint: 'Bills fetched and paid through Bharat Bill Payment apps' },
    ],
  },
];

export const ROLE_LABEL: { [role: string]: { en: string; te: string } } = {
  super_admin: { en: 'Platform administrator', te: 'ప్లాట్‌ఫారమ్ నిర్వాహకులు' },
  system_admin: { en: 'Property tax administrator', te: 'ఆస్తి పన్ను నిర్వాహకులు' },
  commissioner: { en: 'Commissioner', te: 'కమిషనర్' },
  revenue_officer: { en: 'Revenue officer', te: 'రెవెన్యూ అధికారి' },
  revenue_inspector: { en: 'Revenue inspector', te: 'రెవెన్యూ ఇన్‌స్పెక్టర్' },
  bill_collector: { en: 'Bill collector', te: 'బిల్ కలెక్టర్' },
  cashier: { en: 'Cashier', te: 'క్యాషియర్' },
  csc_operator: { en: 'Meeseva / CSC operator', te: 'మీసేవ / CSC ఆపరేటర్' },
  citizen: { en: 'Citizen', te: 'పౌరులు' },
};

/** The most senior role decides the label shown under the user's name. */
const ROLE_ORDER = ['super_admin', 'system_admin', 'commissioner', 'revenue_officer', 'revenue_inspector', 'bill_collector', 'cashier', 'csc_operator', 'citizen'];

export function mainRole(roles: string[]): string {
  return ROLE_ORDER.find((r) => roles.includes(r)) || roles[0] || '';
}

export function allowed(item: NavItem, permissions: Set<string>): boolean {
  return item.anyOf.length === 0 || item.anyOf.some((p) => permissions.has(p));
}

export function navKey(item: NavItem): string {
  return item.view ? `${item.section}/${item.view}` : item.section;
}
