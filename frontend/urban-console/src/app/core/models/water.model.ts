// Module 2 (WTR) - Water & Utility Billing view models. Keys match the API (camelCase).

export interface WaterWard {
  wardId: string;
  wardNumber: number;
  wardName: string;
  zoneId: string;
  zoneCode: string;
  zoneName: string;
}

export interface WaterCategory {
  code: string;
  nameEn: string;
  nameTe: string;
}

export interface WaterAccess {
  username: string;
  roles: string[];
  tenantId: string;
  scope: string;
  permissions: string[];
  categories: WaterCategory[];
  wards: WaterWard[];
  noReadingReasons: string[];
  cycleMonths: number;
  upi: { vpa: string; payeeName: string };
  staffTimeoutMinutes: number;
}

export type PaymentState = 'PAID' | 'DUE' | 'ARREARS';

export interface ConnectionSummary {
  id: string;
  consumerNo: string;
  oldConsumerNo?: string;
  consumerName: string;
  mobileMasked?: string;
  address: string;
  doorNo?: string;
  wardId: string;
  wardNumber?: number;
  wardName?: string;
  zoneName?: string;
  categoryCode: string;
  pipeSizeMm: number;
  isMetered: boolean;
  status: string;
  latitude?: number;
  longitude?: number;
  locationPending: boolean;
  totalDue: number;
  paymentStatus: PaymentState;
}

export interface DuesStatus {
  consumerNo: string;
  status: string;
  penalty: number;
  fees: number;
  arrears: number;
  current: number;
  totalDue: number;
  advanceHeld: number;
  depositHeld: number;
  netPayable: number;
  paymentStatus: PaymentState;
  lastBillNo?: string;
  lastBillDueDate?: string;
}

export interface ConnectionDetail extends ConnectionSummary {
  email?: string;
  aadhaarMasked?: string;
  citizenId?: string;
  locality?: string;
  pincode?: string;
  oldAssessmentNo?: string;
  upin?: string;
  upinSource?: string;
  supplyArea?: string;
  connectionDate: string;
  routeId?: string;
  routeCode?: string;
  routeSequence?: number;
  source: string;
  dues: DuesStatus;
  meter?: {
    id: string;
    serialNo: string;
    make: string;
    sizeMm: number;
    sealNo?: string;
    initialReading: number;
    fixedOn: string;
    status: string;
  } | null;
  createdAt: string;
}

export interface SlabLine {
  label: string;
  fromKl?: number;
  toKl?: number | null;
  units?: number;
  rate?: number;
  amount: number;
  pipeSizeMm?: number;
  monthlyRate?: number;
  months?: number;
  reason?: string;
}

export interface WaterBill {
  id: string;
  billNo: string;
  cycle: string;
  periodFrom: string;
  periodTo: string;
  billDate: string;
  dueDate: string;
  basis: 'ACTUAL' | 'AVERAGE' | 'FLAT';
  categoryCode: string;
  previousReading?: number | null;
  currentReading?: number | null;
  consumptionKl: number;
  slabBreakup: SlabLine[];
  waterCharge: number;
  fixedCharge: number;
  cess: number;
  currentDemand: number;
  arrears: number;
  penalty: number;
  otherDues: number;
  advanceAdjusted: number;
  totalPayable: number;
  approvedAdjustments: number;
  verificationCode: string;
  consumerNo?: string;
  consumerName?: string;
  address?: string;
  doorNo?: string;
  wardNumber?: number;
  wardName?: string;
  zoneName?: string;
  pipeSizeMm?: number;
  isMetered?: boolean;
  tariffVersion?: number;
  upiUri?: string;
  verifyPath?: string;
}

export interface WaterReceipt {
  id: string;
  receiptNo: string;
  consumerNo?: string;
  applicationNo?: string;
  consumerName?: string;
  address?: string;
  amount: number;
  paymentMode: string;
  channel: string;
  instrumentNo?: string;
  instrumentBank?: string;
  gatewayTxnId?: string;
  payerName?: string;
  allocation: { [bucket: string]: number };
  status: string;
  statusReason?: string;
  verificationCode: string;
  collectedBy: string;
  receiptDate: string;
  createdAt: string;
  verifyPath: string;
}

export interface WaterReading {
  id: string;
  consumerNo?: string;
  consumerName?: string;
  cycle: string;
  readingValue?: number | null;
  previousValue?: number | null;
  consumptionKl?: number | null;
  noReadingReason?: string | null;
  readingAt: string;
  photoRef?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  source: string;
  flag: string;
  status: string;
  reviewRemark?: string | null;
  capturedBy: string;
}

export interface RouteProgress {
  id: string;
  code: string;
  name: string;
  wardId?: string;
  readerUsername?: string;
  isActive: boolean;
  cycle: string;
  totalConnections: number;
  read: number;
  noReading: number;
  pendingReview: number;
  remaining: number;
  completionPercent: number;
}

export interface WorkflowStep {
  code: string;
  label: string;
  slaHours: number;
  roles: string[];
  enabled: boolean;
  status: 'PENDING' | 'CURRENT' | 'DONE' | 'SKIPPED' | 'REJECTED';
  dueAt?: string;
  doneAt?: string;
  doneBy?: string;
  remark?: string;
  escalatedTo?: string;
}

export interface WaterApplication {
  id: string;
  applicationNo: string;
  appType: string;
  channel: string;
  consumerNo?: string;
  applicantName?: string;
  mobileMasked?: string;
  aadhaarMasked?: string;
  wardNumber?: number;
  wardName?: string;
  address?: string;
  details: any;
  documents: string[];
  warnings: { consumerNo: string; consumerName: string; address: string; reason: string; distanceM?: number }[];
  estimate?: { component: string; label: string; amount: number }[] | null;
  estimateTotal?: number | null;
  amountPaid: number;
  amountOutstanding?: number;
  steps: WorkflowStep[];
  currentStep?: string;
  status: string;
  escalationLevel: number;
  createdAt: string;
  timeline?: TimelineEntry[];
}

export interface TimelineEntry {
  action: string;
  remark?: string;
  actor: string;
  at: string;
}

export interface WaterApproval {
  id: string;
  approvalType: string;
  consumerNo?: string;
  refNo?: string;
  amount?: number | null;
  details: any;
  reason: string;
  status: string;
  requestedBy: string;
  requestedAt: string;
  decidedBy?: string;
  decisionRemark?: string;
  canDecide: boolean;
}

export interface WaterComplaint {
  id: string;
  complaintNo: string;
  complaintType: string;
  source: string;
  consumerNo?: string;
  wardNumber?: number;
  wardName?: string;
  description: string;
  address?: string;
  latitude?: number;
  longitude?: number;
  photoRef?: string;
  status: string;
  slaDueAt: string;
  escalationLevel: number;
  overdue: boolean;
  closingPhotoRef?: string;
  closingRemark?: string;
  closedAt?: string;
  assignedTo?: string;
  complainantName?: string;
  createdAt: string;
  timeline?: TimelineEntry[];
}

export interface WaterOrder {
  id: string;
  orderNo: string;
  orderType: 'NOTICE' | 'DISCONNECTION' | 'RECONNECTION';
  status: string;
  consumerNo: string;
  consumerName: string;
  address: string;
  latitude?: number;
  longitude?: number;
  wardNumber?: number;
  wardName?: string;
  duesAtIssue?: number;
  noticeUntil?: string;
  slaDueAt?: string;
  slaBreached: boolean;
  executedAt?: string;
  executedBy?: string;
  remark?: string;
  createdAt: string;
}

export interface OfflineReading {
  clientRef: string;
  consumerNo: string;
  consumerName: string;
  readingValue: number | null;
  noReadingReason: string | null;
  readingAt: string;
  latitude: number | null;
  longitude: number | null;
  photoDataUrl: string | null;
  photoRef: string | null;
  lastError?: string;
}
