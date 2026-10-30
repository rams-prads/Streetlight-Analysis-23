"""Module 2 (WTR) request and response schemas. JSON keys are camelCase via CamelModel (AGENTS.md 3.1)."""
import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import Field, field_validator

from app.schemas.property import CamelModel

CategoryCode = str
PaymentMode = Literal["CASH", "CHEQUE", "DD", "UPI", "ONLINE", "BBPS"]
Channel = Literal["COUNTER", "FIELD", "CSC", "PORTAL", "APP", "BBPS", "WHATSAPP"]
ApplicationType = Literal[
    "NEW_CONNECTION", "OWNER_CHANGE", "CATEGORY_CHANGE", "PIPE_SIZE_CHANGE",
    "TEMP_DISCONNECTION", "TEMP_RECONNECTION", "PERM_DISCONNECTION",
]
ComplaintType = Literal["LEAK", "NO_SUPPLY", "DIRTY_WATER", "METER", "BILLING", "OTHER"]


def _mobile(value: Optional[str]) -> Optional[str]:
    if value is None or value == "":
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) != 10 or digits[0] not in "6789":
        raise ValueError("Mobile number must be a 10-digit Indian mobile number starting with 6, 7, 8 or 9.")
    return digits


# ------------------------------------------------------------------------------------------------
# Connections (WB-01..WB-08)
# ------------------------------------------------------------------------------------------------

class ConnectionSummary(CamelModel):
    id: str
    consumer_no: str
    old_consumer_no: Optional[str] = None
    consumer_name: str
    mobile_masked: Optional[str] = None
    address: str
    door_no: Optional[str] = None
    ward_id: str
    ward_number: Optional[int] = None
    ward_name: Optional[str] = None
    zone_name: Optional[str] = None
    category_code: str
    pipe_size_mm: int
    is_metered: bool
    status: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_pending: bool = False
    total_due: float = 0.0
    payment_status: str = "PAID"


class DuesStatus(CamelModel):
    consumer_no: str
    status: str
    penalty: float
    fees: float
    arrears: float
    current: float
    total_due: float
    advance_held: float
    deposit_held: float
    net_payable: float
    payment_status: str
    last_bill_no: Optional[str] = None
    last_bill_due_date: Optional[datetime.date] = None


class ConnectionDetail(ConnectionSummary):
    email: Optional[str] = None
    aadhaar_masked: Optional[str] = None
    citizen_id: Optional[str] = None
    locality: Optional[str] = None
    pincode: Optional[str] = None
    old_assessment_no: Optional[str] = None
    upin: Optional[str] = None
    upin_source: Optional[str] = None
    zone_id: Optional[str] = None
    supply_area: Optional[str] = None
    connection_date: datetime.date
    route_id: Optional[str] = None
    route_code: Optional[str] = None
    route_sequence: Optional[int] = None
    source: str
    dues: DuesStatus
    meter: Optional[Dict[str, Any]] = None
    created_at: datetime.datetime


class ConnectionUpdate(CamelModel):
    """Officer corrections that do not need a workflow. Owner, category and pipe size go through applications (WB-06)."""
    reason: str = Field(min_length=5)
    mobile_number: Optional[str] = None
    email: Optional[str] = None
    door_no: Optional[str] = None
    address: Optional[str] = None
    locality: Optional[str] = None
    pincode: Optional[str] = None
    old_assessment_no: Optional[str] = None
    upin: Optional[str] = None
    upin_source: Optional[Literal["APPLICANT", "STAFF", "LINK"]] = None
    supply_area: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    route_id: Optional[str] = None
    route_sequence: Optional[int] = None
    ward_id: Optional[str] = None

    @field_validator("mobile_number")
    @classmethod
    def check_mobile_number(cls, v):
        return _mobile(v)


class DuplicateCheckRequest(CamelModel):
    address: Optional[str] = None
    door_no: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    exclude_connection_id: Optional[str] = None


# ------------------------------------------------------------------------------------------------
# Applications (WB-05, WB-06)
# ------------------------------------------------------------------------------------------------

class ApplicationCreate(CamelModel):
    app_type: ApplicationType
    channel: Literal["PORTAL", "APP", "CSC", "COUNTER"] = "COUNTER"
    consumer_no: Optional[str] = None  # required for change requests
    applicant_name: Optional[str] = None
    mobile_number: Optional[str] = None
    email: Optional[str] = None
    aadhaar_number: Optional[str] = None
    consent: bool = False
    ward_id: Optional[str] = None
    address: Optional[str] = None
    door_no: Optional[str] = None
    locality: Optional[str] = None
    pincode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    old_assessment_no: Optional[str] = None
    upin: Optional[str] = None
    category_code: Optional[str] = None
    pipe_size_mm: Optional[int] = None
    is_metered: Optional[bool] = None
    supply_area: Optional[str] = None
    reason: Optional[str] = None
    documents: List[str] = Field(default_factory=list)

    @field_validator("mobile_number")
    @classmethod
    def check_mobile_number(cls, v):
        return _mobile(v)


class ApplicationAction(CamelModel):
    action: Literal["COMPLETE_STEP", "REJECT"]
    remark: str = Field(min_length=3)
    data: Dict[str, Any] = Field(default_factory=dict)
    photo_ref: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


# ------------------------------------------------------------------------------------------------
# Meters, routes and readings (WB-10..WB-19)
# ------------------------------------------------------------------------------------------------

class MeterFix(CamelModel):
    serial_no: str = Field(min_length=3)
    make: str = Field(min_length=2)
    size_mm: int = Field(gt=0)
    seal_no: Optional[str] = None
    initial_reading: float = Field(ge=0)
    fixed_on: datetime.date
    final_reading_of_old: Optional[float] = Field(default=None, ge=0)  # required when replacing (WB-11)
    reason: str = Field(min_length=3)


class MeterStatusChange(CamelModel):
    status: Literal["ACTIVE", "FAULTY"]
    reason: str = Field(min_length=3)


class RouteCreate(CamelModel):
    code: str = Field(min_length=2, max_length=30)
    name: str = Field(min_length=2)
    ward_id: Optional[str] = None
    reader_username: Optional[str] = None


class RouteUpdate(CamelModel):
    name: Optional[str] = None
    reader_username: Optional[str] = None
    is_active: Optional[bool] = None


class RouteAssign(CamelModel):
    consumer_nos: List[str] = Field(min_length=1)


class ReadingIn(CamelModel):
    consumer_no: str
    reading_value: Optional[float] = Field(default=None, ge=0)
    no_reading_reason: Optional[str] = None
    reading_at: Optional[datetime.datetime] = None
    photo_ref: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    client_ref: Optional[str] = Field(default=None, max_length=80)


class ReadingIntake(CamelModel):
    """One intake for field app, consumer self-reading, office and bulk/AMR files (WB-19)."""
    source: Literal["FIELD", "CONSUMER", "BULK", "AMR", "OFFICE"] = "FIELD"
    readings: List[ReadingIn] = Field(min_length=1, max_length=5000)


class ReadingReview(CamelModel):
    decision: Literal["ACCEPT", "REJECT"]
    remark: str = Field(min_length=3)


class ConsumerReading(CamelModel):
    consumer_no: str
    mobile_number: str
    reading_value: float = Field(ge=0)
    photo_ref: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None


# ------------------------------------------------------------------------------------------------
# Tariffs and billing (WB-20..WB-26)
# ------------------------------------------------------------------------------------------------

class Slab(CamelModel):
    upto_kl: Optional[float] = None
    rate_per_kl: float = Field(ge=0)


class TariffProposal(CamelModel):
    category_code: str
    effective_from: datetime.date
    slabs: List[Slab] = Field(min_length=1)
    flat_rates: Dict[str, float] = Field(default_factory=dict)
    minimum_charge: float = Field(ge=0, default=0)
    fixed_charge: float = Field(ge=0, default=0)
    cess_percent: float = Field(ge=0, le=100, default=0)
    free_allowance_kl: float = Field(ge=0, default=0)
    order_reference: Optional[str] = None
    reason: str = Field(min_length=5)


class BillRunRequest(CamelModel):
    cycle: str
    route_ids: List[str] = Field(default_factory=list)
    bill_date: Optional[datetime.date] = None


class BillAdjustmentRequest(CamelModel):
    amount: float  # negative reduces the bill, positive increases it
    reason: str = Field(min_length=5)


# ------------------------------------------------------------------------------------------------
# Collection (WB-30..WB-38)
# ------------------------------------------------------------------------------------------------

class PaymentCreate(CamelModel):
    consumer_no: Optional[str] = None
    application_no: Optional[str] = None
    amount: float = Field(gt=0)
    payment_mode: PaymentMode
    channel: Channel = "COUNTER"
    instrument_no: Optional[str] = None
    instrument_bank: Optional[str] = None
    instrument_date: Optional[datetime.date] = None
    payer_name: Optional[str] = None
    payer_mobile: Optional[str] = None
    idempotency_key: str = Field(min_length=8, max_length=80)

    @field_validator("payer_mobile")
    @classmethod
    def check_payer_mobile(cls, v):
        return _mobile(v)


class OnlineInitiate(CamelModel):
    consumer_no: Optional[str] = None
    application_no: Optional[str] = None
    amount: float = Field(gt=0)
    channel: Literal["PORTAL", "APP", "BBPS", "WHATSAPP"] = "PORTAL"


class StubGatewayPay(CamelModel):
    order_id: str
    outcome: Literal["SUCCESS", "SUCCESS_NO_CALLBACK", "FAILURE"]


class GatewayCallback(CamelModel):
    order_id: str
    gateway_txn_id: Optional[str] = None
    status: Literal["SUCCESS", "FAILURE"]


class ReceiptCancelRequest(CamelModel):
    reason: str = Field(min_length=5)


class ChequeReturnRequest(CamelModel):
    reason: str = Field(min_length=3)
    return_date: Optional[datetime.date] = None


class DayCloseSubmit(CamelModel):
    close_date: datetime.date
    declared_cash: float = Field(ge=0)
    remark: Optional[str] = None


class DayCloseVerify(CamelModel):
    received_cash: float = Field(ge=0)
    remark: Optional[str] = None


class StatementRow(CamelModel):
    reference: str
    amount: float
    txn_date: Optional[datetime.date] = None


class ReconciliationRequest(CamelModel):
    statement_date: datetime.date
    source: Literal["GATEWAY", "BANK"] = "GATEWAY"
    rows: List[StatementRow] = Field(default_factory=list)


class RefundRequest(CamelModel):
    refund_type: Literal["EXCESS_PAYMENT", "DEPOSIT"]
    amount: float = Field(gt=0)
    mode: Literal["PAY", "ADJUST"] = "PAY"
    reason: str = Field(min_length=5)


# ------------------------------------------------------------------------------------------------
# Arrears, disconnection, waivers (WB-40..WB-46)
# ------------------------------------------------------------------------------------------------

class WaiverRequest(CamelModel):
    kind: Literal["WAIVER", "WRITE_OFF"]
    bucket: Literal["PENALTY", "FEE", "ARREAR", "CURRENT"]
    amount: float = Field(gt=0)
    reason: str = Field(min_length=5)


class FieldProof(CamelModel):
    photo_ref: str
    latitude: float
    longitude: float
    remark: Optional[str] = None
    executed_at: Optional[datetime.datetime] = None


class ApprovalDecision(CamelModel):
    decision: Literal["APPROVE", "REJECT"]
    remark: str = Field(min_length=3)


# ------------------------------------------------------------------------------------------------
# Complaints and illegal connections (WB-50..WB-53)
# ------------------------------------------------------------------------------------------------

class ComplaintCreate(CamelModel):
    complaint_type: ComplaintType
    source: Literal["PORTAL", "APP", "WHATSAPP", "CALL_CENTRE", "FIELD", "COUNTER"] = "PORTAL"
    consumer_no: Optional[str] = None
    ward_id: Optional[str] = None
    complainant_name: Optional[str] = None
    complainant_mobile: Optional[str] = None
    description: str = Field(min_length=5)
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    photo_ref: Optional[str] = None

    @field_validator("complainant_mobile")
    @classmethod
    def check_complainant_mobile(cls, v):
        return _mobile(v)


class ComplaintAction(CamelModel):
    action: Literal["START", "CLOSE", "REASSIGN"]
    remark: str = Field(min_length=3)
    photo_ref: Optional[str] = None
    assign_to: Optional[str] = None


class IllegalReport(CamelModel):
    source: Literal["STAFF", "CITIZEN"] = "STAFF"
    ward_id: Optional[str] = None
    address: Optional[str] = None
    description: Optional[str] = None
    latitude: float
    longitude: float
    photo_ref: str


class IllegalInspection(CamelModel):
    findings: str = Field(min_length=5)
    confirmed_illegal: bool
    photo_ref: Optional[str] = None
    estimated_since: Optional[datetime.date] = None


class IllegalDecision(CamelModel):
    decision: Literal["REGULARISE", "DISCONNECT", "CLOSE_NO_ISSUE"]
    remark: str = Field(min_length=3)
    # REGULARISE: details for the new connection
    consumer_name: Optional[str] = None
    mobile_number: Optional[str] = None
    category_code: Optional[str] = None
    pipe_size_mm: Optional[int] = None
    is_metered: Optional[bool] = None
    door_no: Optional[str] = None
    # DISCONNECT: field proof
    photo_ref: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    @field_validator("mobile_number")
    @classmethod
    def check_mobile_number(cls, v):
        return _mobile(v)


# ------------------------------------------------------------------------------------------------
# Administration, migration
# ------------------------------------------------------------------------------------------------

class SettingChange(CamelModel):
    key: str
    value: Any
    effective_from: datetime.date
    reason: str = Field(min_length=5)


class CategoryCreate(CamelModel):
    code: str = Field(min_length=2, max_length=30)
    name_en: str
    name_te: str


class MigrationRecord(CamelModel):
    old_consumer_no: str
    consumer_name: str
    mobile_number: Optional[str] = None
    address: str
    door_no: Optional[str] = None
    ward_number: Optional[int] = None
    category_code: str
    pipe_size_mm: int
    is_metered: bool
    connection_date: Optional[datetime.date] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    old_assessment_no: Optional[str] = None
    upin: Optional[str] = None
    meter_serial_no: Optional[str] = None
    meter_make: Optional[str] = None
    last_reading: Optional[float] = None
    opening_arrears: float = 0.0


class MigrationBatch(CamelModel):
    records: List[Dict[str, Any]] = Field(min_length=1, max_length=20000)
    arrears_as_of: datetime.date
