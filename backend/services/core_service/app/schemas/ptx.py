"""Module 1 (PTX) request schemas. JSON keys are camelCase via CamelModel (AGENTS.md 3.1)."""
import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import Field, field_validator

from app.schemas.property import CamelModel


def _mobile(value: Optional[str]) -> Optional[str]:
    if value is None or value == "":
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) != 10 or digits[0] not in "6789":
        raise ValueError("Mobile number must be a 10-digit Indian mobile number starting with 6, 7, 8 or 9.")
    return digits


AppType = Literal["NEW_ASSESSMENT", "SELF_ASSESSMENT", "REASSESSMENT", "USE_CHANGE", "EXEMPTION", "MUTATION",
                  "SUBDIVISION", "AMALGAMATION", "APARTMENT", "DEMOLITION", "BACK_ASSESSMENT"]
PaymentMode = Literal["CASH", "CHEQUE", "DD", "UPI", "POS", "ONLINE", "BBPS"]


class FloorIn(CamelModel):
    """One row of the floor table. A floor may have several rows: a part used differently (PART), an apartment's share of
    common areas (COMMON) or an installation on the roof (ROOFTOP)."""
    floor_no: int = Field(ge=-2, le=60)
    usage_code: str = ""
    construction_code: str = ""
    builtup_sqft: float = Field(gt=0)
    occupancy: Literal["OWNER", "TENANT"] = "OWNER"
    portion: Literal["FULL", "PART", "COMMON", "ROOFTOP"] = "FULL"
    rooftop_type: Optional[str] = None
    declared_accommodation: bool = False


class PartyIn(CamelModel):
    full_name: str = Field(min_length=2)
    mobile_number: Optional[str] = None
    email: Optional[str] = None
    aadhaar_number: Optional[str] = None
    share_percent: Optional[float] = Field(default=None, ge=0, le=100)

    @field_validator("mobile_number")
    @classmethod
    def check_mobile(cls, v):
        return _mobile(v)


class PropertyDetailsIn(CamelModel):
    property_type: Literal["BUILT", "VACANT_LAND"] = "BUILT"
    ward_id: Optional[str] = None
    locality_id: Optional[str] = None
    door_no: Optional[str] = None
    address: Optional[str] = None
    pincode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    footprint_id: Optional[str] = None
    site_area_sqyd: Optional[float] = Field(default=None, ge=0)
    construction_year: Optional[int] = Field(default=None, ge=1800, le=2100)
    exemption_code: Optional[str] = None
    exemption_document: Optional[str] = None
    building_permission_no: Optional[str] = None
    occupancy_certificate_no: Optional[str] = None
    road_class: Optional[str] = None
    approved_setback_ft: Optional[float] = Field(default=None, ge=0, le=500)
    measured_setback_ft: Optional[float] = Field(default=None, ge=0, le=500)


class UnitIn(CamelModel):
    """One flat or unit in an apartment building."""
    unit_no: str = Field(min_length=1, max_length=30)
    floors: List[FloorIn] = Field(min_length=1)
    owners: List[PartyIn] = Field(default_factory=list)


class PartIn(CamelModel):
    """One part of a subdivision."""
    property: PropertyDetailsIn
    floors: List[FloorIn] = Field(default_factory=list)
    owners: List[PartyIn] = Field(default_factory=list)


class ApplicationCreate(CamelModel):
    app_type: AppType
    channel: Literal["PORTAL", "APP", "CSC", "COUNTER", "FIELD", "REGISTRATION"] = "COUNTER"
    upin: Optional[str] = None                       # existing property (changes)
    upins: List[str] = Field(default_factory=list)   # amalgamation inputs
    applicant_name: Optional[str] = None
    mobile_number: Optional[str] = None
    email: Optional[str] = None
    consent: bool = False
    effective_from: Optional[datetime.date] = None
    property: Optional[PropertyDetailsIn] = None
    floors: List[FloorIn] = Field(default_factory=list)
    owners: List[PartyIn] = Field(default_factory=list)
    occupiers: List[PartyIn] = Field(default_factory=list)
    parts: List[PartIn] = Field(default_factory=list)
    units: List[UnitIn] = Field(default_factory=list)
    complex_name: Optional[str] = None
    common_area_sqft: Optional[float] = Field(default=None, ge=0)
    transfer_reason: Optional[str] = None
    transfer_deed_no: Optional[str] = None
    transfer_date: Optional[datetime.date] = None
    reason: Optional[str] = None
    documents: List[str] = Field(default_factory=list)

    @field_validator("mobile_number")
    @classmethod
    def check_mobile(cls, v):
        return _mobile(v)


class ApplicationAction(CamelModel):
    action: Literal["COMPLETE_STEP", "REJECT", "FINALISE", "DECIDE_OBJECTION"]
    remark: str = Field(min_length=3)
    property: Optional[PropertyDetailsIn] = None   # measured values from field inspection
    floors: Optional[List[FloorIn]] = None
    photo_refs: List[str] = Field(default_factory=list)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    objection_upheld: Optional[bool] = None


class PetitionIn(CamelModel):
    level: Literal["REVISION_PETITION", "APPEAL"]
    grounds: str = Field(min_length=20)
    mobile_number: Optional[str] = None  # citizens confirm with the registered mobile


class PetitionDecision(CamelModel):
    outcome: Literal["ALLOW", "PARTLY_ALLOW", "REJECT"]
    remark: str = Field(min_length=5)
    order_reference: Optional[str] = Field(default=None, max_length=120)
    property: Optional[PropertyDetailsIn] = None   # corrected values when the petition or appeal is allowed
    floors: Optional[List[FloorIn]] = None


class CorrectionRequest(CamelModel):
    """A change to one raised bill: plus raises it, minus lowers it (PT-19). Needs approval."""
    amount: float
    reason: str = Field(min_length=5)

    @field_validator("amount")
    @classmethod
    def not_zero(cls, v):
        if abs(v) < 0.01:
            raise ValueError("The correction amount cannot be zero.")
        return v


class ObjectionIn(CamelModel):
    mobile_number: Optional[str] = None  # citizens confirm with the registered mobile
    text: str = Field(min_length=10)


class PropertyUpdate(CamelModel):
    """Corrections that do not change tax. Area, use and ownership go through cases (PT-12, PT-13)."""
    reason: str = Field(min_length=5)
    door_no: Optional[str] = None
    address: Optional[str] = None
    pincode: Optional[str] = None
    locality_id: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    footprint_id: Optional[str] = None
    old_assessment_no: Optional[str] = None
    building_permission_no: Optional[str] = None
    occupancy_certificate_no: Optional[str] = None
    add_photos: List[str] = Field(default_factory=list)
    add_documents: List[str] = Field(default_factory=list)


class OccupierUpdate(CamelModel):
    reason: str = Field(min_length=5)
    occupiers: List[PartyIn] = Field(default_factory=list)


class CalculatePreview(CamelModel):
    property: PropertyDetailsIn
    floors: List[FloorIn] = Field(default_factory=list)
    effective_from: Optional[datetime.date] = None
    rate_table_id: Optional[str] = None


class RateTableProposal(CamelModel):
    effective_from: datetime.date
    rules: Dict[str, Any]
    order_reference: Optional[str] = None
    reason: str = Field(min_length=5)


class DemandRunRequest(CamelModel):
    period: str
    ward_ids: List[str] = Field(default_factory=list)


class RevisionRunRequest(CamelModel):
    rate_table_id: str
    ward_ids: List[str] = Field(default_factory=list)


class PaymentCreate(CamelModel):
    upin: str
    amount: float = Field(gt=0)
    payment_mode: PaymentMode
    channel: Literal["COUNTER", "FIELD", "CSC"] = "COUNTER"
    instrument_no: Optional[str] = None
    instrument_bank: Optional[str] = None
    instrument_date: Optional[datetime.date] = None
    payer_name: Optional[str] = None
    payer_mobile: Optional[str] = None
    idempotency_key: str = Field(min_length=8, max_length=80)

    @field_validator("payer_mobile")
    @classmethod
    def check_mobile(cls, v):
        return _mobile(v)


class OnlineInitiate(CamelModel):
    upin: str
    amount: float = Field(gt=0)
    channel: Literal["PORTAL", "APP", "BBPS", "WHATSAPP"] = "PORTAL"


class StubGatewayPay(CamelModel):
    order_id: str
    outcome: Literal["SUCCESS", "SUCCESS_NO_CALLBACK", "FAILURE"]


class GatewayCallback(CamelModel):
    order_id: str
    gateway_txn_id: Optional[str] = None
    status: Literal["SUCCESS", "FAILURE"]


class ReasonIn(CamelModel):
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


class ReconciliationRequest(CamelModel):
    statement_date: datetime.date
    source: Literal["GATEWAY", "BANK"] = "GATEWAY"
    rows: List[StatementRow] = Field(default_factory=list)


class RefundRequest(CamelModel):
    amount: float = Field(gt=0)
    mode: Literal["PAY", "ADJUST"] = "PAY"
    reason: str = Field(min_length=5)


class WaiverRequest(CamelModel):
    kind: Literal["WAIVER", "WRITE_OFF"]
    bucket: Literal["PENALTY", "FEE", "ARREAR", "CURRENT"]
    amount: float = Field(gt=0)
    reason: str = Field(min_length=5)


class ApprovalDecision(CamelModel):
    decision: Literal["APPROVE", "REJECT"]
    remark: str = Field(min_length=3)


class NoticeRequest(CamelModel):
    notice_type: Literal["DEMAND", "REMINDER", "RECOVERY"]
    upins: List[str] = Field(default_factory=list)   # one at a time ...
    ward_id: Optional[str] = None                    # ... or in bulk by ward
    min_due: float = 0


class NoticeService(CamelModel):
    served: bool
    served_at: Optional[datetime.datetime] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    photo_ref: Optional[str] = None
    reason: Optional[str] = None
    client_ref: Optional[str] = None


class NoticeServiceItem(NoticeService):
    notice_no: str


class NoticeServiceBatch(CamelModel):
    items: List[NoticeServiceItem] = Field(min_length=1, max_length=500)


class RecoveryAdvance(CamelModel):
    remark: str = Field(min_length=3)
    close: bool = False


class SurveyIn(CamelModel):
    client_ref: str = Field(min_length=6, max_length=80)
    survey_type: Literal["VERIFY", "NEW_BUILDING"]
    upin: Optional[str] = None
    footprint_id: Optional[str] = None
    ward_id: Optional[str] = None
    floors: List[FloorIn] = Field(default_factory=list)
    site_area_sqyd: Optional[float] = None
    remarks: Optional[str] = None
    occupant_name: Optional[str] = None
    address: Optional[str] = None
    door_no: Optional[str] = None
    photo_refs: List[str] = Field(default_factory=list)
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    captured_at: Optional[datetime.datetime] = None


class SurveyBatch(CamelModel):
    surveys: List[SurveyIn] = Field(min_length=1, max_length=500)


class SurveyDecision(CamelModel):
    outcome: Literal["MATCHES_RECORD", "OPEN_CASE", "CLOSE"]
    remark: str = Field(min_length=3)


class SettingChange(CamelModel):
    key: str
    value: Any
    effective_from: datetime.date
    reason: str = Field(min_length=5)


class CodeCreate(CamelModel):
    list_name: Literal["USAGE", "CONSTRUCTION", "EXEMPTION", "TRANSFER_REASON", "ROAD_CLASS", "ROOFTOP_TYPE", "COMPLAINT_CATEGORY"]
    code: str = Field(min_length=2, max_length=40)
    name_en: str
    name_te: str
    extra: Dict[str, Any] = Field(default_factory=dict)


class MigrationRecord(CamelModel):
    old_assessment_no: str
    owner_name: str
    owner_mobile: Optional[str] = None
    address: str
    door_no: Optional[str] = None
    ward_number: Optional[int] = None
    property_type: Literal["BUILT", "VACANT_LAND"] = "BUILT"
    site_area_sqyd: float = 0
    construction_year: Optional[int] = None
    usage_code: str = "RESIDENTIAL"
    construction_code: str = "RCC"
    builtup_sqft: float = 0
    road_class: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    opening_arrears: float = 0.0


class MigrationBatch(CamelModel):
    records: List[Dict[str, Any]] = Field(min_length=1, max_length=20000)
    arrears_as_of: datetime.date


class DeedIn(CamelModel):
    """A registered deed as the Registration Department feed sends it (PT-14)."""
    deed_no: str = Field(min_length=2, max_length=60)
    registration_office: str = Field(min_length=2, max_length=120)
    deed_date: datetime.date
    deed_type: str = Field(min_length=2, max_length=30)
    upin: Optional[str] = None
    old_assessment_no: Optional[str] = None
    ward_number: Optional[int] = None
    door_no: Optional[str] = None
    sellers: List[str] = Field(min_length=1)
    buyers: List[PartyIn] = Field(min_length=1)
    consideration_amount: Optional[float] = Field(default=None, ge=0)


class DeedBatch(CamelModel):
    deeds: List[DeedIn] = Field(min_length=1, max_length=100)


class DeedAction(CamelModel):
    remark: str = Field(min_length=3)
    upin: Optional[str] = None  # the property chosen by the officer when the feed could not match it


class StateRecord(CamelModel):
    state_ref: str = Field(min_length=2, max_length=60)
    upin: Optional[str] = None
    old_assessment_no: Optional[str] = None
    door_no: Optional[str] = None
    address: Optional[str] = None
    pincode: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class StateImport(CamelModel):
    records: List[StateRecord] = Field(min_length=1, max_length=2000)


class LinkToggle(CamelModel):
    enabled: bool
    reason: str = Field(min_length=5)


class BbpsFetch(CamelModel):
    request_id: str = Field(min_length=4, max_length=60)
    upin: Optional[str] = None
    old_assessment_no: Optional[str] = None


class BbpsPay(CamelModel):
    request_id: str = Field(min_length=4, max_length=60)
    upin: str
    amount: float = Field(gt=0)
    bbps_txn_ref: str = Field(min_length=6, max_length=60)
    paid_at: Optional[datetime.datetime] = None


class CertificateIssue(CamelModel):
    upin: str
    cert_type: Literal["NO_DUES", "TAX_PAID", "ASSESSMENT_EXTRACT", "NOC"] = "NO_DUES"
    purpose: Optional[str] = Field(default=None, max_length=200)
    mobile_number: Optional[str] = None


class ComplaintIn(CamelModel):
    upin: str
    category: str
    description: str = Field(min_length=10)
    ref_no: Optional[str] = Field(default=None, max_length=60)
    channel: Literal["PORTAL", "APP", "CSC", "COUNTER", "FIELD"] = "COUNTER"
    mobile_number: Optional[str] = None  # citizens confirm with the registered mobile; staff may record the caller's

    @field_validator("mobile_number")
    @classmethod
    def check_mobile(cls, v):
        return _mobile(v)


class ComplaintAction(CamelModel):
    action: Literal["START", "RESOLVE", "REOPEN"]
    remark: str = Field(min_length=3)
    outcome: Optional[Literal["ACTION_TAKEN", "NO_CHANGE_NEEDED"]] = None
    application_no: Optional[str] = None


class DeliveryItem(CamelModel):
    demand_no: str
    delivered: bool
    note: Optional[str] = Field(default=None, max_length=200)
    delivered_at: Optional[datetime.datetime] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class DeliveryBatch(CamelModel):
    items: List[DeliveryItem] = Field(min_length=1, max_length=500)


class RemittanceCreate(CamelModel):
    close_ids: List[str] = Field(min_length=1)
    bank_name: str = Field(min_length=2, max_length=120)
    challan_no: str = Field(min_length=2, max_length=60)
    deposit_date: datetime.date
    deposited_cash: float = Field(ge=0)
    deposited_instruments: float = Field(default=0, ge=0)
    remark: Optional[str] = None


class RemittanceConfirm(CamelModel):
    credit_date: datetime.date
    credited_amount: float = Field(ge=0)
    remark: Optional[str] = None


class PropertyClaim(CamelModel):
    """A citizen adds a property to their account: its number and the owner's registered mobile."""
    number: str = Field(min_length=3, max_length=40)
    mobile_number: str = Field(min_length=10, max_length=14)
    relation: Literal["OWN", "OTHER"] = "OWN"


class CertificateRequest(CamelModel):
    upin: str
    mobile_number: Optional[str] = None
