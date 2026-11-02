/** Module 1 (PTX) Property Tax & Revenue Management - shapes returned by /api/v1/ptx (camelCase). */

export interface Page<T> {
  items: T[];
  total: number;
  skip: number;
  limit: number;
}

export interface PtxCode {
  code: string;
  nameEn: string;
  nameTe: string;
  extra: { percent?: number; documents?: string[] } & { [key: string]: any };
}

export interface PtxWard {
  wardId: string;
  wardNumber: number;
  wardName: string;
  zoneId: string;
  zoneCode: string;
  zoneName: string;
}

export interface PtxLocality {
  localityId: string;
  code: string;
  name: string;
  wardId: string;
  pincode: string;
}

export interface PtxAccess {
  username: string;
  displayName?: string;
  roles: string[];
  tenantId: string;
  scope: string;
  permissions: string[];
  wards: PtxWard[];
  localities: PtxLocality[];
  codes: { USAGE?: PtxCode[]; CONSTRUCTION?: PtxCode[]; EXEMPTION?: PtxCode[]; TRANSFER_REASON?: PtxCode[]; ROAD_CLASS?: PtxCode[]; ROOFTOP_TYPE?: PtxCode[]; COMPLAINT_CATEGORY?: PtxCode[] };
  frequency: string;
  currentPeriod: string;
  currentPeriodLabel: string;
  staffTimeoutMinutes: number;
  fees: { mutationByReason: { [reason: string]: number }; subdivision: number; amalgamation: number };
  objectionDays: number;
}

export type PaymentState = 'PAID' | 'DUE' | 'ARREARS';

export interface PropertySummary {
  complexName?: string | null;
  unitNo?: string | null;
  id: string;
  upin: string;
  oldAssessmentNo: string | null;
  propertyType: 'BUILT' | 'VACANT_LAND';
  status: 'ACTIVE' | 'RETIRED';
  doorNo: string | null;
  address: string;
  wardId: string;
  wardNumber: number;
  wardName: string;
  zoneName: string;
  ownerNames: string;
  latitude: number | null;
  longitude: number | null;
  locationPending: boolean;
  totalDue: number;
  paymentStatus: PaymentState;
}

export type FloorPortion = 'FULL' | 'PART' | 'COMMON' | 'ROOFTOP';

export interface Floor {
  floorNo: number;
  usageCode: string;
  constructionCode: string;
  builtupSqft: number;
  occupancy: 'OWNER' | 'TENANT';
  /** FULL floor, PART of a floor used differently, COMMON-area share (apartments) or ROOFTOP installation. */
  portion?: FloorPortion;
  rooftopType?: string | null;
  /** Owner-declared guest / paying-guest / lodging use of this area (PT-33). */
  declaredAccommodation?: boolean;
}

export interface Party {
  id: string;
  role: 'OWNER' | 'OCCUPIER';
  fullName: string;
  sharePercent: number | null;
  fromDate: string | null;
  toDate: string | null;
  isCurrent: boolean;
  viaApplication: string | null;
  mobileMasked?: string | null;
  email?: string | null;
  aadhaarMasked?: string | null;
}

export interface Dues {
  upin?: string;
  status?: string;
  interest: number;
  fees: number;
  arrears: number;
  current: number;
  totalDue: number;
  advanceHeld: number;
  netPayable: number;
  paymentStatus?: PaymentState;
  lastDemandNo?: string | null;
  lastPeriod?: string | null;
  lastPeriodLabel?: string | null;
  lastDueDate?: string | null;
}

export interface CalcLine {
  kind: 'FLOOR' | 'CESS' | 'VACANT_LAND' | string;
  [key: string]: any;
}

export interface CalcSheet {
  lines: CalcLine[];
  steps: string[];
  rateZone?: string;
  annualTax: number;
  components: { [code: string]: number };
  rateTableId?: string;
  rateTableVersion?: number;
  rateTableEffectiveFrom?: string;
  effectiveFrom?: string;
  frequency?: string;
  firstPeriod?: string;
  firstPeriodLabel?: string;
  instalment?: number;
  orderReference?: string | null;
  parts?: CalcSheet[];
  unitNo?: string;
}

export interface Assessment {
  id: string;
  assessmentNo: string;
  kind: string;
  effectiveFrom: string;
  annualTax: number;
  components: { [code: string]: number };
  calculation: CalcSheet;
  status: 'PROVISIONAL' | 'NOTICE_ISSUED' | 'FINAL' | 'SUPERSEDED' | 'REPLACED';
  noticeNo: string | null;
  objectionUntil: string | null;
  approvedBy: string | null;
  createdAt: string;
}

export interface PropertyDetail extends PropertySummary {
  localityId: string | null;
  localityName: string | null;
  pincode: string | null;
  siteAreaSqyd: number;
  constructionYear: number | null;
  exemptionCode: string | null;
  roadClass?: string | null;
  approvedSetbackFt?: number | null;
  measuredSetbackFt?: number | null;
  complexName?: string | null;
  unitNo?: string | null;
  floors: Floor[];
  owners: Party[];
  occupiers: Party[];
  assessment: Assessment | null;
  dues: Dues;
  retiredReason: string | null;
  related: { parents?: RelatedProperty[]; children?: RelatedProperty[] };
  ownerHistory?: Party[];
  footprintId?: string | null;
  buildingPermissionNo?: string | null;
  occupancyCertificateNo?: string | null;
  photos?: string[];
  documents?: string[];
  source?: string;
  createdAt?: string;
  exemptionDocument?: string | null;
}

export interface RelatedProperty {
  upin: string;
  kind: string;
  status: string;
  applicationNo: string | null;
}

export interface PropertyDemand {
  demandNo: string;
  period: string;
  periodLabel: string;
  dueDate: string;
  amount: number;
  revised: number;
  components: { [code: string]: number };
}

export interface LedgerEntry {
  id: string;
  entryDate: string;
  txnType: string;
  component: string;
  bucket: string;
  accountHead: string;
  amount: number;
  paymentMode: string | null;
  referenceNo: string | null;
  isReversal: boolean;
  narration: string | null;
  netBalance: number;
  createdBy: string;
}

export interface HistoryEntry {
  field: string;
  oldValue: string | null;
  newValue: string | null;
  reason: string | null;
  changedBy: string;
  changedAt: string;
}

export interface CaseStep {
  code: 'DOC_CHECK' | 'FIELD_INSPECTION' | 'APPROVAL' | 'NOTICE' | string;
  label: string;
  slaHours: number;
  roles: string[];
  enabled: boolean;
  status: 'PENDING' | 'CURRENT' | 'DONE' | 'SKIPPED' | 'REJECTED';
  startedAt?: string;
  dueAt?: string;
  doneAt?: string;
  doneBy?: string;
  remark?: string;
}

export type CaseType =
  | 'NEW_ASSESSMENT'
  | 'SELF_ASSESSMENT'
  | 'REASSESSMENT'
  | 'USE_CHANGE'
  | 'EXEMPTION'
  | 'MUTATION'
  | 'SUBDIVISION'
  | 'AMALGAMATION'
  | 'APARTMENT'
  | 'DEMOLITION'
  | 'BACK_ASSESSMENT';

export interface PtxCase {
  id: string;
  applicationNo: string;
  appType: CaseType;
  typeLabel: string;
  channel: string;
  upin: string | null;
  applicantName: string | null;
  wardNumber: number | null;
  wardName: string | null;
  details: any;
  documents: string[];
  calculation: CalcSheet | null;
  proposedAnnualTax: number | null;
  effectiveFrom: string | null;
  noticeNo: string | null;
  objectionUntil: string | null;
  objectionText: string | null;
  objectionFiledAt: string | null;
  objectionDecision: string | null;
  result: any;
  steps: CaseStep[];
  currentStep: string | null;
  status: 'IN_PROGRESS' | 'COMPLETED' | 'REJECTED';
  statusText: string;
  escalationLevel: number;
  createdAt: string;
  completedAt: string | null;
  mobileMasked: string | null;
  createdBy: string;
  startedByStaff: boolean;
  timeline?: { action: string; remark: string | null; actor: string; at: string }[];
  feeDue?: number;
  petitions?: Petition[];
  petitionOptions?: PetitionOptions;
}

export interface Petition {
  id: string;
  petitionNo: string;
  applicationNo: string | null;
  upin: string | null;
  wardNumber?: number | null;
  level: 'REVISION_PETITION' | 'APPEAL';
  levelName: string;
  grounds: string;
  filedBy: string;
  filedAt: string;
  status: 'FILED' | 'ALLOWED' | 'PARTLY_ALLOWED' | 'REJECTED' | 'WITHDRAWN';
  orderReference: string | null;
  decision: string | null;
  decidedBy: string | null;
  decidedAt: string | null;
  newAssessmentNo: string | null;
}

export interface PetitionOptions {
  canFile: 'REVISION_PETITION' | 'APPEAL' | null;
  until: string | null;
  message: string | null;
}

export interface RateTable {
  id: string;
  version: number;
  effectiveFrom: string;
  rules: any;
  status: 'PENDING_APPROVAL' | 'APPROVED' | 'REJECTED';
  orderReference: string | null;
  reason: string | null;
  requestedBy: string;
  approvedBy: string | null;
  approvedAt: string | null;
  inForce: boolean;
}

export interface DemandRow {
  demandNo: string;
  upin: string;
  address: string;
  period: string;
  periodLabel: string;
  dueDate: string;
  amount: number;
  components: { [code: string]: number };
  deliveryStatus?: 'PENDING' | 'DELIVERED' | 'NOT_DELIVERED';
  deliveredAt?: string | null;
  deliveredBy?: string | null;
  deliveryNote?: string | null;
}

export interface DemandNotice extends DemandRow {
  oldAssessmentNo: string | null;
  ownerNames: string[];
  doorNo: string | null;
  wardNumber: number;
  wardName: string;
  zoneName: string;
  periodFrom: string;
  periodTo: string;
  revised: number;
  arrearsAtRaise: number;
  interestAtRaise: number;
  dues: Dues;
  verificationCode: string;
  upiUri: string;
  verifyPath: string;
}

export interface Receipt {
  id: string;
  receiptNo: string;
  upin: string | null;
  amount: number;
  schemeBenefit: number;
  paymentMode: string;
  channel: string;
  instrumentNo: string | null;
  instrumentBank: string | null;
  gatewayTxnId: string | null;
  payerName: string | null;
  payerMobileMasked: string | null;
  allocation: { [bucket: string]: number };
  status: 'VALID' | 'CANCELLED' | 'CHEQUE_RETURNED' | string;
  statusReason: string | null;
  verificationCode: string;
  collectedBy: string;
  receiptDate: string;
  createdAt: string;
  dayCloseId: string | null;
  verifyPath: string;
  ownerNames?: string[];
  address?: string;
  wardNumber?: number;
}

export interface SchemeOffer {
  code: string;
  type: 'REBATE' | 'OTS';
  nameEn: string;
  nameTe: string;
  until: string;
  benefit: number;
  bucket: string;
}

export interface Payable {
  upin?: string;
  totalDue: number;
  advanceHeld: number;
  schemes: SchemeOffer[];
  saving: number;
  payToClearAll: number;
}

export interface DayClose {
  id: string;
  collector: string;
  closeDate: string;
  receiptCount: number;
  systemCash: number;
  systemNonCash: number;
  declaredCash: number;
  receivedCash: number | null;
  variance: number | null;
  status: 'SUBMITTED' | 'VERIFIED';
  verifiedBy: string | null;
  verifiedAt: string | null;
  remark: string | null;
}

export interface Mismatch {
  type: string;
  reference: string | null;
  receiptNo?: string;
  statementAmount?: number;
  systemAmount?: number;
  status?: string;
  action?: string;
}

export interface Notice {
  id: string;
  noticeNo: string;
  noticeType: 'ASSESSMENT' | 'DEMAND' | 'REMINDER' | 'RECOVERY';
  upin: string;
  address: string;
  wardNumber: number;
  amount: number;
  content: any;
  batchId: string | null;
  serviceStatus: 'PENDING' | 'SERVED' | 'NOT_SERVED';
  servedAt: string | null;
  servedBy: string | null;
  serviceLatitude: number | null;
  serviceLongitude: number | null;
  servicePhotoRef: string | null;
  notServedReason: string | null;
  issuedBy: string;
  issuedAt: string;
  verificationCode: string;
  verifyPath: string;
  doorNo?: string | null;
  wardName?: string;
}

export interface RecoveryCase {
  id: string;
  caseNo: string;
  upin: string;
  wardNumber: number;
  stage: string;
  status: 'OPEN' | 'CLOSED';
  duesAtOpen: number;
  currentDue: number;
  stages: { stage: string; at: string; by: string; remark: string }[];
  closureReason: string | null;
  openedBy: string;
  openedAt: string;
  closedAt: string | null;
}

export interface Approval {
  id: string;
  approvalType: 'RATE_TABLE' | 'RECEIPT_CANCEL' | 'REFUND' | 'WAIVER' | 'WRITE_OFF' | string;
  upin: string | null;
  refNo: string | null;
  amount: number | null;
  details: any;
  reason: string | null;
  status: 'PENDING' | 'APPROVED' | 'REJECTED';
  requestedBy: string;
  requestedAt: string;
  decidedBy: string | null;
  decidedAt: string | null;
  decisionRemark: string | null;
  canDecide: boolean;
}

export interface Defaulter {
  upin: string;
  ownerNames: string;
  address: string;
  wardNumber: number;
  interest: number;
  fees: number;
  arrears: number;
  current: number;
  totalDue: number;
  oldestAgeDays: number;
  ageBand: string;
}

export interface Ageing {
  asOf: string;
  bands: string[];
  totals: { [band: string]: number };
  byWard: any[];
  defaulters: Page<Defaulter>;
  note: string;
}

export interface CitizenAccount {
  property: PropertyDetail;
  dues: Dues;
  explanation: { key: string; en: string; te: string; amount: number }[];
  payNow: number;
  saving: number;
  schemes: SchemeOffer[];
  noDues: boolean;
  complaints?: { complaintNo: string; category: string; status: string; dueAt: string; createdAt: string }[];
  demands: { demandNo: string; periodLabel: string; dueDate: string; amount: number }[];
  receipts: { receiptNo: string; date: string; amount: number; mode: string; status: string }[];
  certificates: { certificateNo: string; issuedOn: string; validUntil: string }[];
  cases: { applicationNo: string; type: string; status: string; statusText: string; createdAt: string }[];
}

export interface Complaint {
  id: string;
  complaintNo: string;
  upin: string | null;
  wardNumber?: number | null;
  category: string;
  categoryName: string;
  categoryNameTe: string;
  hint: string | null;
  description: string;
  refNo: string | null;
  filedBy: string;
  channel: string;
  status: 'OPEN' | 'IN_PROGRESS' | 'RESOLVED';
  statusText: string;
  dueAt: string;
  overdue: boolean;
  escalationLevel: number;
  outcome: string | null;
  resolution: string | null;
  applicationNo: string | null;
  resolvedBy: string | null;
  resolvedAt: string | null;
  createdAt: string;
  timeline?: { action: string; remark: string | null; actor: string; at: string }[];
}

export interface Remittance {
  id: string;
  remittanceNo: string;
  depositDate: string;
  bankName: string;
  challanNo: string;
  closeIds: string[];
  expectedCash: number;
  expectedInstruments: number;
  expectedTotal: number;
  depositedCash: number;
  depositedInstruments: number;
  depositedTotal: number;
  depositVariance: number;
  status: 'SUBMITTED' | 'CONFIRMED' | 'MISMATCH';
  preparedBy: string;
  preparedAt: string;
  creditDate: string | null;
  creditedAmount: number | null;
  confirmedBy: string | null;
  confirmedAt: string | null;
  remark: string | null;
}

export interface Certificate {
  certType?: 'NO_DUES' | 'TAX_PAID' | 'ASSESSMENT_EXTRACT' | 'NOC';
  purpose?: string | null;
  content?: any;
  certificateNo: string;
  upin: string;
  oldAssessmentNo: string | null;
  address: string;
  ownerNames?: string[];
  issuedOn: string;
  validUntil: string;
  paidUpTo?: string | null;
  verificationCode: string;
  verifyPath: string;
  [key: string]: any;
}

export interface Survey {
  id: string;
  surveyType: 'VERIFY' | 'NEW_BUILDING';
  upin: string | null;
  footprintId: string | null;
  wardNumber: number | null;
  data: any;
  photos: string[];
  recordedFloors: Floor[];
  latitude: number | null;
  longitude: number | null;
  capturedAt: string;
  capturedBy: string;
  status: string;
  outcome: string | null;
}

export interface WardSheet {
  ward: PtxWard;
  downloadedAt: string;
  properties: { upin: string; doorNo: string | null; address: string; latitude: number | null; longitude: number | null; ownerNames: string;
    siteAreaSqyd: number; floors: Floor[]; propertyType: string }[];
  buildingsToVerify: { footprintId: string; ref: string; latitude: number; longitude: number; mapBuiltupSqft: number; status: string }[];
  noticesToServe: { noticeNo: string; noticeType: string; upin: string; address: string; amount: number }[];
  billsToDeliver?: { demandNo: string; upin: string; doorNo: string | null; address: string; amount: number; dueDate: string; ownerNames: string }[];
}

/** A survey or notice-service record waiting on the device until it is synced (PT-06, PT-43, PT-NF-33). */
export interface OfflineItem {
  clientRef: string;
  kind: 'SURVEY' | 'NOTICE_SERVICE' | 'BILL_DELIVERY';
  savedAt: string;
  label: string;
  payload: any;
  photos: string[];
  lastError?: string;
}
