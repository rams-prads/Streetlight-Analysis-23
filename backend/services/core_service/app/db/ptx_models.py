"""
Module 1 (PTX) - Property Tax & Revenue Management data model.

Every table is prefixed `ptx_` and carries `tenant_id` (plus `sub_tenant_id` where records belong to a city)
so it can be filtered per AGENTS.md. Financial rows (ledger, demands, receipts) are append-only: corrections
are reversal or adjustment rows, never edits (SRS 2.5, PT-34). The property register keyed by UPIN is the
city's master property record that later modules will reference (SRS 2.1).
"""
import datetime
import uuid

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint,
)

from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime.datetime:
    """Naive UTC timestamp (columns are TIMESTAMP WITHOUT TIME ZONE, like the core models)."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


MONEY = Numeric(14, 2)
AREA = Numeric(12, 2)


class PtxCounter(Base):
    """Monotonic number series (UPIN, assessment, demand, receipt ...). Never reset, never reused (PT-01)."""
    __tablename__ = "ptx_counters"

    tenant_id = Column(String(50), primary_key=True)
    name = Column(String(40), primary_key=True)
    value = Column(Integer, nullable=False, default=0)


class PtxSetting(Base):
    """Versioned configuration with an effective date: rules, fees, SLAs, workflows (SRS 2.5, 3.4, PT-NF-50)."""
    __tablename__ = "ptx_settings"
    __table_args__ = (Index("ix_ptx_settings_key", "tenant_id", "key", "effective_from"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    key = Column(String(80), nullable=False)
    value_json = Column(Text, nullable=False)
    effective_from = Column(Date, nullable=False)
    reason = Column(Text, nullable=True)
    created_by = Column(String(150), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class PtxCode(Base):
    """Code lists: usage type, construction type, exemption, transfer reason (SRS 3.6.3, PT-NF-64)."""
    __tablename__ = "ptx_codes"
    __table_args__ = (UniqueConstraint("tenant_id", "list_name", "code", name="uq_ptx_code"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    list_name = Column(String(30), nullable=False)  # USAGE, CONSTRUCTION, EXEMPTION, TRANSFER_REASON
    code = Column(String(40), nullable=False)
    name_en = Column(String(120), nullable=False)
    name_te = Column(String(120), nullable=False)
    extra_json = Column(Text, nullable=False, default="{}")  # e.g. exemption percent, required documents
    is_active = Column(Boolean, default=True, nullable=False)


class PtxRateTable(Base):
    """
    Versioned tax rate table (PT-10). Rows are never edited after approval; a new version with a later effective
    date replaces it, and old versions stay so past assessments can be recalculated (SRS 3.4).
    rules_json holds rental values, occupancy factors, depreciation, tax rates, cess and vacant land rates.
    """
    __tablename__ = "ptx_rate_tables"
    __table_args__ = (UniqueConstraint("tenant_id", "version", name="uq_ptx_rate_version"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    effective_from = Column(Date, nullable=False)
    rules_json = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="PENDING_APPROVAL")  # PENDING_APPROVAL, APPROVED, REJECTED
    order_reference = Column(String(200), nullable=True)
    reason = Column(Text, nullable=True)
    requested_by = Column(String(150), nullable=False)
    approved_by = Column(String(150), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class PtxProperty(Base):
    """Property register keyed by a permanent UPIN (PT-01..PT-05, PT-IR-05)."""
    __tablename__ = "ptx_properties"
    __table_args__ = (
        UniqueConstraint("tenant_id", "upin", name="uq_ptx_upin"),
        Index("ix_ptx_prop_latlng", "tenant_id", "latitude", "longitude"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    sub_tenant_id = Column(String(50), nullable=True, index=True)
    upin = Column(String(30), nullable=False)
    old_assessment_no = Column(String(60), nullable=True, index=True)  # from the old system (PT-05)
    property_type = Column(String(15), nullable=False, default="BUILT")  # BUILT, VACANT_LAND
    status = Column(String(15), nullable=False, default="ACTIVE", index=True)  # ACTIVE, RETIRED
    retired_reason = Column(String(20), nullable=True)  # SUBDIVIDED, AMALGAMATED, DEMOLISHED

    ward_id = Column(String(36), ForeignKey("wards.id"), nullable=False, index=True)
    zone_id = Column(String(36), ForeignKey("zones.id"), nullable=True, index=True)
    locality_id = Column(String(36), ForeignKey("localities.id"), nullable=True, index=True)
    door_no = Column(String(60), nullable=True, index=True)
    address = Column(Text, nullable=False)
    pincode = Column(String(10), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    footprint_id = Column(String(36), nullable=True, index=True)  # GIS building footprint (PT-02)
    location_pending = Column(Boolean, default=False, nullable=False)

    site_area_sqyd = Column(AREA, nullable=False, default=0)
    construction_year = Column(Integer, nullable=True)
    exemption_code = Column(String(40), nullable=True)
    exemption_document = Column(String(80), nullable=True)
    building_permission_no = Column(String(80), nullable=True)  # PT-IR-05 (filled from link I-03 later)
    occupancy_certificate_no = Column(String(80), nullable=True)
    road_class = Column(String(40), nullable=True)  # road the property is on; scales rental value (PT-32)
    approved_setback_ft = Column(Float, nullable=True)  # from the building permission (PT-12)
    measured_setback_ft = Column(Float, nullable=True)  # measured at inspection (PT-12)
    state_ref = Column(String(60), nullable=True, index=True)  # the property's id on the state platform (PT-02)
    complex_name = Column(String(150), nullable=True, index=True)  # apartment building this unit belongs to (PT-07)
    unit_no = Column(String(30), nullable=True)
    photos_json = Column(Text, nullable=False, default="[]")
    documents_json = Column(Text, nullable=False, default="[]")
    source = Column(String(20), nullable=False, default="ASSESSMENT")  # ASSESSMENT, MIGRATION, SUBDIVISION, AMALGAMATION

    created_by = Column(String(150), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class PtxFloor(Base):
    """Built-up area, use and construction per floor (PT-03). Replaced as a set when the property is reassessed."""
    __tablename__ = "ptx_floors"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    property_id = Column(String(36), ForeignKey("ptx_properties.id"), nullable=False, index=True)
    floor_no = Column(Integer, nullable=False)  # 0 = ground
    usage_code = Column(String(40), nullable=False)
    construction_code = Column(String(40), nullable=False)
    builtup_sqft = Column(AREA, nullable=False)
    occupancy = Column(String(10), nullable=False, default="OWNER")  # OWNER, TENANT
    portion = Column(String(10), nullable=False, default="FULL")  # FULL, PART, COMMON, ROOFTOP (PT-07, PT-31)
    rooftop_type = Column(String(40), nullable=True)
    declared_accommodation = Column(Boolean, nullable=False, default=False)  # owner-declared guest accommodation (PT-33)
    is_current = Column(Boolean, nullable=False, default=True, index=True)
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date, nullable=True)


class PtxParty(Base):
    """Owners (with share) and occupiers/tenants (PT-03). Mutation closes old owners rather than deleting them."""
    __tablename__ = "ptx_parties"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    property_id = Column(String(36), ForeignKey("ptx_properties.id"), nullable=False, index=True)
    role = Column(String(10), nullable=False, default="OWNER")  # OWNER, OCCUPIER
    citizen_id = Column(String(64), nullable=True, index=True)
    full_name = Column(String(150), nullable=False, index=True)
    mobile_number = Column(String(15), nullable=True, index=True)
    email = Column(String(150), nullable=True)
    aadhaar_hash = Column(String(64), nullable=True)
    aadhaar_last4 = Column(String(4), nullable=True)
    share_percent = Column(Numeric(6, 2), nullable=True)
    is_current = Column(Boolean, nullable=False, default=True, index=True)
    from_date = Column(Date, nullable=False)
    to_date = Column(Date, nullable=True)
    via_application = Column(String(40), nullable=True)


class PtxPropertyLink(Base):
    """Parent / child links kept when properties are split or merged (PT-15, PT-16)."""
    __tablename__ = "ptx_property_links"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    parent_id = Column(String(36), ForeignKey("ptx_properties.id"), nullable=False, index=True)
    child_id = Column(String(36), ForeignKey("ptx_properties.id"), nullable=False, index=True)
    kind = Column(String(15), nullable=False)  # SUBDIVISION, AMALGAMATION
    application_no = Column(String(40), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class PtxPropertyHistory(Base):
    """Field-level change history: old value, new value, who, when and why (PT-07)."""
    __tablename__ = "ptx_property_history"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    property_id = Column(String(36), ForeignKey("ptx_properties.id"), nullable=False, index=True)
    field = Column(String(60), nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    reason = Column(Text, nullable=False)
    changed_by = Column(String(150), nullable=False)
    changed_at = Column(DateTime, default=utcnow, nullable=False)


class PtxApplication(Base):
    """
    Assessment cases and property changes, filed by citizens or started by staff (PT-10..PT-21).
    steps_json is a snapshot of the configured workflow: [{"code","label","slaHours","roles","status","dueAt",...}].
    """
    __tablename__ = "ptx_applications"
    __table_args__ = (UniqueConstraint("tenant_id", "application_no", name="uq_ptx_application_no"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    sub_tenant_id = Column(String(50), nullable=True, index=True)
    application_no = Column(String(40), nullable=False)
    app_type = Column(String(30), nullable=False, index=True)
    property_id = Column(String(36), ForeignKey("ptx_properties.id"), nullable=True, index=True)
    related_property_ids_json = Column(Text, nullable=False, default="[]")  # amalgamation inputs
    channel = Column(String(20), nullable=False, default="COUNTER")
    started_by_staff = Column(Boolean, nullable=False, default=False)

    applicant_name = Column(String(150), nullable=True)
    mobile_number = Column(String(15), nullable=True, index=True)
    email = Column(String(150), nullable=True)
    consent_recorded = Column(Boolean, default=False, nullable=False)
    ward_id = Column(String(36), ForeignKey("wards.id"), nullable=True, index=True)

    details_json = Column(Text, nullable=False, default="{}")    # proposed property data / transfer details / parts
    documents_json = Column(Text, nullable=False, default="[]")
    calculation_json = Column(Text, nullable=True)               # calculation sheet shown to officer and owner (PT-11)
    proposed_annual_tax = Column(MONEY, nullable=True)
    effective_from = Column(Date, nullable=True)
    notice_no = Column(String(40), nullable=True)
    objection_until = Column(Date, nullable=True)
    objection_text = Column(Text, nullable=True)
    objection_filed_at = Column(DateTime, nullable=True)
    objection_decision = Column(Text, nullable=True)
    result_json = Column(Text, nullable=True)                    # UPINs created / retired

    steps_json = Column(Text, nullable=False, default="[]")
    current_step = Column(String(40), nullable=True)
    status = Column(String(20), nullable=False, default="IN_PROGRESS", index=True)  # IN_PROGRESS, COMPLETED, REJECTED
    escalation_level = Column(Integer, nullable=False, default=0)
    created_by = Column(String(150), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)


class PtxAssessment(Base):
    """A finalised (or provisional) tax assessment, linked to the rate table version used (SRS 3.6.1)."""
    __tablename__ = "ptx_assessments"
    __table_args__ = (UniqueConstraint("tenant_id", "assessment_no", name="uq_ptx_assessment_no"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    assessment_no = Column(String(40), nullable=False)
    property_id = Column(String(36), ForeignKey("ptx_properties.id"), nullable=False, index=True)
    application_id = Column(String(36), nullable=True)
    kind = Column(String(25), nullable=False)  # NEW, REASSESSMENT, USE_CHANGE, GENERAL_REVISION, EXEMPTION, MIGRATION, SUBDIVISION, AMALGAMATION
    rate_table_id = Column(String(36), ForeignKey("ptx_rate_tables.id"), nullable=True)
    effective_from = Column(Date, nullable=False)  # start of the demand period it applies from
    annual_tax = Column(MONEY, nullable=False)
    components_json = Column(Text, nullable=False)   # {"PROPERTY_TAX": 1200.0, "LIBRARY_CESS": 96.0}
    calculation_json = Column(Text, nullable=False)  # full calculation sheet (PT-11)
    status = Column(String(15), nullable=False, default="FINAL", index=True)  # PROVISIONAL, NOTICE_ISSUED, FINAL, SUPERSEDED
    notice_no = Column(String(40), nullable=True)
    objection_until = Column(Date, nullable=True)
    approved_by = Column(String(150), nullable=True)
    created_by = Column(String(150), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class PtxDemand(Base):
    """Demand raised for one property and one period, by component (PT-30). Never edited (revisions are ledger rows)."""
    __tablename__ = "ptx_demands"
    __table_args__ = (
        UniqueConstraint("tenant_id", "demand_no", name="uq_ptx_demand_no"),
        UniqueConstraint("property_id", "period", name="uq_ptx_demand_period"),  # nobody billed twice (PT-NF-63)
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    demand_no = Column(String(40), nullable=False)
    property_id = Column(String(36), ForeignKey("ptx_properties.id"), nullable=False, index=True)
    ward_id = Column(String(36), nullable=True, index=True)
    period = Column(String(12), nullable=False, index=True)  # 2026-27-H1, 2026-27-H2 or 2026-27-Y
    financial_year = Column(String(7), nullable=False, index=True)
    period_from = Column(Date, nullable=False)
    period_to = Column(Date, nullable=False)
    due_date = Column(Date, nullable=False, index=True)
    assessment_id = Column(String(36), ForeignKey("ptx_assessments.id"), nullable=False)
    components_json = Column(Text, nullable=False)
    amount = Column(MONEY, nullable=False)
    arrears_at_raise = Column(MONEY, nullable=False, default=0)
    penalty_at_raise = Column(MONEY, nullable=False, default=0)
    verification_code = Column(String(20), nullable=False)
    run_id = Column(String(36), nullable=True)
    delivery_status = Column(String(15), nullable=False, default="PENDING")  # PENDING, DELIVERED, NOT_DELIVERED (PT-20)
    delivered_at = Column(DateTime, nullable=True)
    delivered_by = Column(String(150), nullable=True)
    delivery_note = Column(String(200), nullable=True)
    delivery_lat = Column(Float, nullable=True)
    delivery_lng = Column(Float, nullable=True)
    created_by = Column(String(150), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class PtxJob(Base):
    """Bulk job progress per ward (demand, reassessment, notices) so a stopped run resumes (PT-NF-63)."""
    __tablename__ = "ptx_jobs"
    __table_args__ = (UniqueConstraint("tenant_id", "job_type", "job_key", "ward_id", name="uq_ptx_job_ward"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    job_type = Column(String(25), nullable=False)  # DEMAND, REVISION, NOTICES
    job_key = Column(String(60), nullable=False)   # period / rate table id / notice batch
    ward_id = Column(String(36), nullable=False)
    status = Column(String(15), nullable=False, default="RUNNING")
    processed = Column(Integer, nullable=False, default=0)
    skipped_json = Column(Text, nullable=False, default="[]")
    started_by = Column(String(150), nullable=False)
    started_at = Column(DateTime, default=utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)


class PtxLedger(Base):
    """
    Financial ledger (PT-IR-04). amount is signed: positive raises what the owner owes, negative lowers it.
    Balances are derived from this table; rows are never updated or deleted.
    bucket: PENALTY (interest), FEE, ARREAR, CURRENT (dues) and ADVANCE (excess paid, held as credit).
    """
    __tablename__ = "ptx_ledger"
    __table_args__ = (
        Index("ix_ptx_ledger_prop_bucket", "property_id", "bucket"),
        Index("ix_ptx_ledger_date", "tenant_id", "entry_date"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    property_id = Column(String(36), ForeignKey("ptx_properties.id"), nullable=False, index=True)
    ward_id = Column(String(36), nullable=True, index=True)
    entry_date = Column(Date, nullable=False)
    txn_type = Column(String(25), nullable=False, index=True)
    component = Column(String(30), nullable=False)
    bucket = Column(String(10), nullable=False)
    account_head = Column(String(40), nullable=False, index=True)
    amount = Column(MONEY, nullable=False)
    payment_mode = Column(String(20), nullable=True)
    reference_no = Column(String(60), nullable=True)
    demand_id = Column(String(36), nullable=True, index=True)
    receipt_id = Column(String(36), nullable=True, index=True)
    approval_id = Column(String(36), nullable=True)
    dedupe_key = Column(String(120), nullable=True, index=True)  # e.g. interest for one demand and month
    is_reversal = Column(Boolean, default=False, nullable=False)
    reversal_of_id = Column(String(36), nullable=True)
    narration = Column(Text, nullable=True)
    created_by = Column(String(150), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class PtxReceipt(Base):
    """Receipt for every payment (PT-32). Never edited; only cancelled/bounced through reversal (PT-34, PT-37)."""
    __tablename__ = "ptx_receipts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "receipt_no", name="uq_ptx_receipt_no"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_ptx_receipt_idem"),  # PT-NF-32
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    receipt_no = Column(String(40), nullable=False)
    property_id = Column(String(36), ForeignKey("ptx_properties.id"), nullable=False, index=True)
    ward_id = Column(String(36), nullable=True, index=True)
    amount = Column(MONEY, nullable=False)
    scheme_benefit = Column(MONEY, nullable=False, default=0)  # rebate / one-time settlement given (PT-39)
    payment_mode = Column(String(20), nullable=False)  # CASH, CHEQUE, DD, UPI, ONLINE, BBPS
    channel = Column(String(20), nullable=False)       # COUNTER, FIELD, CSC, PORTAL, APP, BBPS
    instrument_no = Column(String(40), nullable=True)
    instrument_bank = Column(String(100), nullable=True)
    instrument_date = Column(Date, nullable=True)
    gateway_txn_id = Column(String(80), nullable=True, index=True)
    idempotency_key = Column(String(80), nullable=False)
    payer_name = Column(String(150), nullable=True)
    payer_mobile = Column(String(15), nullable=True)
    allocation_json = Column(Text, nullable=False, default="{}")
    status = Column(String(15), nullable=False, default="VALID", index=True)  # VALID, CANCELLED, BOUNCED
    status_reason = Column(Text, nullable=True)
    verification_code = Column(String(20), nullable=False)
    day_close_id = Column(String(36), nullable=True, index=True)
    collected_by = Column(String(150), nullable=False, index=True)
    receipt_date = Column(Date, nullable=False, index=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class PtxPaymentIntent(Base):
    """Online payment order. Completed exactly once, by callback or by gateway status check (PT-36)."""
    __tablename__ = "ptx_payment_intents"
    __table_args__ = (UniqueConstraint("tenant_id", "order_id", name="uq_ptx_payment_order"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    order_id = Column(String(40), nullable=False)
    property_id = Column(String(36), ForeignKey("ptx_properties.id"), nullable=False, index=True)
    amount = Column(MONEY, nullable=False)
    channel = Column(String(20), nullable=False, default="PORTAL")
    status = Column(String(15), nullable=False, default="INITIATED", index=True)  # INITIATED, SUCCESS, FAILED
    gateway_txn_id = Column(String(80), nullable=True)
    receipt_id = Column(String(36), nullable=True)
    completed_via = Column(String(15), nullable=True)  # CALLBACK, STATUS_CHECK
    created_by = Column(String(150), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)


class PtxGatewayStub(Base):
    """Stand-in payment gateway state (PT-IR-08), so the status check and daily statement can be exercised locally."""
    __tablename__ = "ptx_gateway_stub"

    order_id = Column(String(40), primary_key=True)
    tenant_id = Column(String(50), nullable=False, index=True)
    gateway_txn_id = Column(String(80), nullable=True)
    amount = Column(MONEY, nullable=False)
    status = Column(String(15), nullable=False)  # CAPTURED, FAILED
    captured_at = Column(DateTime, default=utcnow, nullable=False)


class PtxApproval(Base):
    """Maker-checker approvals: rate table, receipt cancellation, refund, waiver, write-off, adjustment."""
    __tablename__ = "ptx_approvals"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    approval_type = Column(String(25), nullable=False, index=True)
    property_id = Column(String(36), nullable=True, index=True)
    ref_id = Column(String(36), nullable=True)
    ref_no = Column(String(60), nullable=True)
    amount = Column(MONEY, nullable=True)
    payload_json = Column(Text, nullable=False, default="{}")
    reason = Column(Text, nullable=False)
    status = Column(String(15), nullable=False, default="PENDING", index=True)
    requested_by = Column(String(150), nullable=False)
    requested_at = Column(DateTime, default=utcnow, nullable=False)
    decided_by = Column(String(150), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    decision_remark = Column(Text, nullable=True)


class PtxDayClose(Base):
    """Day-end closing of a collector's cash, matched by the cashier (PT-38)."""
    __tablename__ = "ptx_day_closes"
    __table_args__ = (UniqueConstraint("tenant_id", "collector", "close_date", name="uq_ptx_day_close"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    collector = Column(String(150), nullable=False)
    close_date = Column(Date, nullable=False)
    receipt_count = Column(Integer, nullable=False)
    system_cash = Column(MONEY, nullable=False)
    system_non_cash = Column(MONEY, nullable=False)
    declared_cash = Column(MONEY, nullable=False)
    received_cash = Column(MONEY, nullable=True)
    variance = Column(MONEY, nullable=True)
    status = Column(String(15), nullable=False, default="SUBMITTED")  # SUBMITTED, VERIFIED
    verified_by = Column(String(150), nullable=True)
    verified_at = Column(DateTime, nullable=True)
    remark = Column(Text, nullable=True)
    remittance_id = Column(String(36), nullable=True, index=True)  # set when banked (PT-23)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class PtxReconciliation(Base):
    """Result of matching a gateway / bank statement against online receipts (PT-35)."""
    __tablename__ = "ptx_reconciliations"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    statement_date = Column(Date, nullable=False)
    source = Column(String(20), nullable=False)
    matched_count = Column(Integer, nullable=False)
    mismatches_json = Column(Text, nullable=False)
    run_by = Column(String(150), nullable=False)
    run_at = Column(DateTime, default=utcnow, nullable=False)


class PtxNotice(Base):
    """Assessment, demand, reminder and recovery notices with service details (PT-19, PT-42, PT-43)."""
    __tablename__ = "ptx_notices"
    __table_args__ = (UniqueConstraint("tenant_id", "notice_no", name="uq_ptx_notice_no"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    notice_no = Column(String(40), nullable=False)
    notice_type = Column(String(20), nullable=False, index=True)  # ASSESSMENT, DEMAND, REMINDER, RECOVERY
    property_id = Column(String(36), ForeignKey("ptx_properties.id"), nullable=False, index=True)
    ward_id = Column(String(36), nullable=True, index=True)
    amount = Column(MONEY, nullable=True)
    content_json = Column(Text, nullable=False, default="{}")
    batch_id = Column(String(36), nullable=True, index=True)
    recovery_case_id = Column(String(36), nullable=True, index=True)
    verification_code = Column(String(20), nullable=False)
    service_status = Column(String(15), nullable=False, default="PENDING", index=True)  # PENDING, SERVED, NOT_SERVED
    served_at = Column(DateTime, nullable=True)
    served_by = Column(String(150), nullable=True)
    service_latitude = Column(Float, nullable=True)
    service_longitude = Column(Float, nullable=True)
    service_photo_ref = Column(String(80), nullable=True)
    not_served_reason = Column(Text, nullable=True)
    issued_by = Column(String(150), nullable=False)
    issued_at = Column(DateTime, default=utcnow, nullable=False)


class PtxRecoveryCase(Base):
    """Recovery case tracked stage by stage from first notice to final action (PT-44)."""
    __tablename__ = "ptx_recovery_cases"
    __table_args__ = (UniqueConstraint("tenant_id", "case_no", name="uq_ptx_recovery_no"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    case_no = Column(String(40), nullable=False)
    property_id = Column(String(36), ForeignKey("ptx_properties.id"), nullable=False, index=True)
    ward_id = Column(String(36), nullable=True, index=True)
    stage = Column(String(30), nullable=False)
    status = Column(String(15), nullable=False, default="OPEN", index=True)  # OPEN, CLOSED
    dues_at_open = Column(MONEY, nullable=False)
    stages_json = Column(Text, nullable=False, default="[]")
    closure_reason = Column(Text, nullable=True)
    opened_by = Column(String(150), nullable=False)
    opened_at = Column(DateTime, default=utcnow, nullable=False)
    closed_at = Column(DateTime, nullable=True)


class PtxCertificate(Base):
    """No-dues certificate, verifiable by QR code (PT-47)."""
    __tablename__ = "ptx_certificates"
    __table_args__ = (UniqueConstraint("tenant_id", "certificate_no", name="uq_ptx_certificate_no"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    certificate_no = Column(String(40), nullable=False)
    property_id = Column(String(36), ForeignKey("ptx_properties.id"), nullable=False, index=True)
    issued_on = Column(Date, nullable=False)
    valid_until = Column(Date, nullable=False)
    paid_up_to = Column(String(12), nullable=True)  # last period fully paid
    verification_code = Column(String(20), nullable=False)
    issued_to = Column(String(150), nullable=True)
    cert_type = Column(String(20), nullable=False, default="NO_DUES")  # NO_DUES, TAX_PAID, ASSESSMENT_EXTRACT, NOC (PT-28)
    purpose = Column(String(200), nullable=True)
    content_json = Column(Text, nullable=False, default="{}")  # what was certified, frozen at issue
    created_by = Column(String(150), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class PtxFootprint(Base):
    """Building footprints from the GIS base map, matched to UPINs (PT-02, PT-50, PT-51)."""
    __tablename__ = "ptx_footprints"
    __table_args__ = (UniqueConstraint("tenant_id", "footprint_ref", name="uq_ptx_footprint_ref"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    footprint_ref = Column(String(60), nullable=False)
    ward_id = Column(String(36), nullable=True, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    map_builtup_sqft = Column(AREA, nullable=False)  # footprint area x floors seen on the map / LiDAR
    floors_seen = Column(Integer, nullable=False, default=1)
    property_id = Column(String(36), nullable=True, index=True)  # matched UPIN
    verification_status = Column(String(20), nullable=False, default="NONE")  # NONE, SENT_FOR_VERIFICATION, VERIFIED, NOT_A_BUILDING
    source = Column(String(30), nullable=False, default="BASE_MAP")
    created_at = Column(DateTime, default=utcnow, nullable=False)


class PtxSurvey(Base):
    """Field survey / verification captured offline with GPS and photos, synced later (PT-06)."""
    __tablename__ = "ptx_surveys"
    __table_args__ = (UniqueConstraint("tenant_id", "client_ref", name="uq_ptx_survey_client_ref"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    client_ref = Column(String(80), nullable=False)
    property_id = Column(String(36), nullable=True, index=True)
    footprint_id = Column(String(36), nullable=True, index=True)
    ward_id = Column(String(36), nullable=True, index=True)
    survey_type = Column(String(15), nullable=False)  # VERIFY, NEW_BUILDING
    data_json = Column(Text, nullable=False)
    photos_json = Column(Text, nullable=False, default="[]")
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    captured_at = Column(DateTime, nullable=False)
    captured_by = Column(String(150), nullable=False)
    status = Column(String(20), nullable=False, default="SUBMITTED", index=True)  # SUBMITTED, MATCHES_RECORD, CASE_OPENED, CLOSED
    outcome = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class PtxTimeline(Base):
    """Step-by-step timeline for applications, recovery cases and surveys."""
    __tablename__ = "ptx_timeline"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    entity_type = Column(String(20), nullable=False)
    entity_id = Column(String(36), nullable=False, index=True)
    action = Column(String(40), nullable=False)
    remark = Column(Text, nullable=True)
    actor = Column(String(150), nullable=False)
    at = Column(DateTime, default=utcnow, nullable=False)


class PtxNotification(Base):
    """Outbound SMS / WhatsApp / email queue, sent by a stand-in in this release (PT-32, PT-46, PT-IR-08)."""
    __tablename__ = "ptx_notifications"
    __table_args__ = (UniqueConstraint("tenant_id", "dedupe_key", name="uq_ptx_notification_dedupe"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    channel = Column(String(15), nullable=False)
    recipient = Column(String(150), nullable=True)
    template = Column(String(40), nullable=False, index=True)
    message_en = Column(Text, nullable=False)
    message_te = Column(Text, nullable=False)
    property_id = Column(String(36), nullable=True, index=True)
    ref_no = Column(String(60), nullable=True)
    dedupe_key = Column(String(120), nullable=True)
    status = Column(String(20), nullable=False, default="LOGGED_STAND_IN")
    created_at = Column(DateTime, default=utcnow, nullable=False)


class PtxEvent(Base):
    """Event outbox (PT-IR-02). Written even though nothing listens in this release."""
    __tablename__ = "ptx_events"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    event_type = Column(String(40), nullable=False, index=True)
    aggregate_id = Column(String(36), nullable=True, index=True)
    payload_json = Column(Text, nullable=False)
    published = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class PtxAuditLog(Base):
    """Append-only audit trail (PT-NF-13). No update or delete API exists."""
    __tablename__ = "ptx_audit_log"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    actor = Column(String(150), nullable=False, index=True)
    ip_address = Column(String(64), nullable=True)
    action = Column(String(60), nullable=False, index=True)
    entity_type = Column(String(30), nullable=False)
    entity_id = Column(String(36), nullable=True, index=True)
    old_json = Column(Text, nullable=True)
    new_json = Column(Text, nullable=True)
    at = Column(DateTime, default=utcnow, nullable=False, index=True)


class PtxApiLog(Base):
    """Every Property Tax API call with caller and result (PT-IR-09)."""
    __tablename__ = "ptx_api_log"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=True, index=True)
    caller = Column(String(150), nullable=True)
    method = Column(String(10), nullable=False)
    path = Column(String(300), nullable=False)
    status_code = Column(Integer, nullable=False)
    duration_ms = Column(Integer, nullable=False)
    at = Column(DateTime, default=utcnow, nullable=False, index=True)


class PtxMigrationException(Base):
    """Migrated records that could not be matched or placed on the map, kept for field verification (SRS 3.6.2)."""
    __tablename__ = "ptx_migration_exceptions"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    old_assessment_no = Column(String(60), nullable=True)
    raw_json = Column(Text, nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(String(15), nullable=False, default="OPEN")
    created_by = Column(String(150), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class PtxPetition(Base):
    """
    Second and third level remedies after an assessment is final: a revision petition to the Commissioner and an appeal
    to the appellate authority (PT-24). Decisions that correct the assessment create a new final assessment.
    """
    __tablename__ = "ptx_petitions"
    __table_args__ = (UniqueConstraint("tenant_id", "petition_no", name="uq_ptx_petition_no"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    petition_no = Column(String(40), nullable=False)
    application_id = Column(String(36), ForeignKey("ptx_applications.id"), nullable=False, index=True)
    property_id = Column(String(36), ForeignKey("ptx_properties.id"), nullable=False, index=True)
    ward_id = Column(String(36), ForeignKey("wards.id"), nullable=True, index=True)
    level = Column(String(20), nullable=False)  # REVISION_PETITION, APPEAL
    grounds = Column(Text, nullable=False)
    filed_by = Column(String(150), nullable=False)
    filed_at = Column(DateTime, default=utcnow, nullable=False)
    status = Column(String(20), nullable=False, default="FILED", index=True)  # FILED, ALLOWED, PARTLY_ALLOWED, REJECTED, WITHDRAWN
    order_reference = Column(String(120), nullable=True)  # the order of the Commissioner / appellate authority
    decision = Column(Text, nullable=True)
    decided_by = Column(String(150), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    new_assessment_no = Column(String(40), nullable=True)


class PtxComplaint(Base):
    """A property tax complaint with a time limit (PT-29): wrong area, wrong owner, bill not received, wrong amount ..."""
    __tablename__ = "ptx_complaints"
    __table_args__ = (UniqueConstraint("tenant_id", "complaint_no", name="uq_ptx_complaint_no"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    complaint_no = Column(String(40), nullable=False)
    property_id = Column(String(36), ForeignKey("ptx_properties.id"), nullable=False, index=True)
    ward_id = Column(String(36), ForeignKey("wards.id"), nullable=True, index=True)
    category = Column(String(40), nullable=False, index=True)
    description = Column(Text, nullable=False)
    ref_no = Column(String(60), nullable=True)  # bill, receipt or application the complaint is about
    filed_by = Column(String(150), nullable=False)
    mobile_number = Column(String(15), nullable=True)
    channel = Column(String(10), nullable=False, default="COUNTER")
    status = Column(String(15), nullable=False, default="OPEN", index=True)  # OPEN, IN_PROGRESS, RESOLVED
    due_at = Column(DateTime, nullable=False)
    escalation_level = Column(Integer, nullable=False, default=0)
    outcome = Column(String(20), nullable=True)  # ACTION_TAKEN, NO_CHANGE_NEEDED
    resolution = Column(Text, nullable=True)
    application_no = Column(String(40), nullable=True)  # case opened to fix it
    resolved_by = Column(String(150), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class PtxRemittance(Base):
    """Cash and instruments handed to the bank or treasury, from verified day-end closings, then confirmed against the bank (PT-23)."""
    __tablename__ = "ptx_remittances"
    __table_args__ = (UniqueConstraint("tenant_id", "challan_no", name="uq_ptx_remit_challan"),
                      UniqueConstraint("tenant_id", "remittance_no", name="uq_ptx_remit_no"))

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    remittance_no = Column(String(40), nullable=False)
    deposit_date = Column(Date, nullable=False)
    bank_name = Column(String(120), nullable=False)
    challan_no = Column(String(60), nullable=False)
    close_ids_json = Column(Text, nullable=False)
    expected_cash = Column(MONEY, nullable=False)
    expected_instruments = Column(MONEY, nullable=False)
    deposited_cash = Column(MONEY, nullable=False)
    deposited_instruments = Column(MONEY, nullable=False)
    deposit_variance = Column(MONEY, nullable=False, default=0)
    status = Column(String(15), nullable=False, default="SUBMITTED", index=True)  # SUBMITTED, CONFIRMED, MISMATCH
    prepared_by = Column(String(150), nullable=False)
    prepared_at = Column(DateTime, default=utcnow, nullable=False)
    credit_date = Column(Date, nullable=True)
    credited_amount = Column(MONEY, nullable=True)
    confirmed_by = Column(String(150), nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    remark = Column(Text, nullable=True)


class PtxDeedIntake(Base):
    """A registered deed received from the Registration Department feed, and what became of it (PT-14)."""
    __tablename__ = "ptx_deed_intakes"
    __table_args__ = (UniqueConstraint("tenant_id", "registration_office", "deed_no", name="uq_ptx_deed"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    deed_no = Column(String(60), nullable=False)
    registration_office = Column(String(120), nullable=False)
    deed_date = Column(Date, nullable=False)
    deed_type = Column(String(30), nullable=False)
    payload_json = Column(Text, nullable=False)
    status = Column(String(15), nullable=False, default="RECEIVED", index=True)  # RECEIVED, CASE_OPENED, REVIEW, NO_MATCH, DISMISSED
    message = Column(Text, nullable=True)
    property_id = Column(String(36), ForeignKey("ptx_properties.id"), nullable=True, index=True)
    application_no = Column(String(40), nullable=True)
    received_by = Column(String(150), nullable=False)
    received_at = Column(DateTime, default=utcnow, nullable=False)
    handled_by = Column(String(150), nullable=True)
    handled_at = Column(DateTime, nullable=True)


class PtxSyncRun(Base):
    """One exchange with the state property platform: records sent out (PUSH) or received (PULL) and the outcome (PT-02)."""
    __tablename__ = "ptx_sync_runs"
    __table_args__ = (UniqueConstraint("tenant_id", "run_no", name="uq_ptx_sync_run"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    run_no = Column(String(40), nullable=False)
    direction = Column(String(5), nullable=False)  # PUSH, PULL
    records = Column(Integer, nullable=False, default=0)
    matched = Column(Integer, nullable=False, default=0)
    updated = Column(Integer, nullable=False, default=0)
    unmatched = Column(Integer, nullable=False, default=0)
    errors = Column(Integer, nullable=False, default=0)
    results_json = Column(Text, nullable=False, default="[]")
    started_by = Column(String(150), nullable=False)
    started_at = Column(DateTime, default=utcnow, nullable=False)


class PtxCitizenLink(Base):
    """A property a signed-in citizen has proved is theirs (property number plus the owner's registered mobile), so it is listed
    under their account without typing the numbers again (SRS 3.1.1, ease of use)."""
    __tablename__ = "ptx_citizen_links"
    __table_args__ = (UniqueConstraint("tenant_id", "username", "property_id", name="uq_ptx_citizen_link"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    username = Column(String(150), nullable=False, index=True)
    property_id = Column(String(36), ForeignKey("ptx_properties.id"), nullable=False)
    mobile_number = Column(String(10), nullable=False)  # the owner's registered mobile the citizen gave when linking
    linked_at = Column(DateTime, default=utcnow, nullable=False)
