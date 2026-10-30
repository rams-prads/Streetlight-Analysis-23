"""
Module 2 (WTR) - Water & Utility Billing data model.

Every table is prefixed `wtr_` and carries `tenant_id` (plus optional `sub_tenant_id`)
so it can be filtered per AGENTS.md section 3.1. Financial rows (ledger, receipts, bills)
are append-only: corrections are made with reversal / adjustment rows, never in place
(SRS 2.5, WB-26, WB-33).
"""
import datetime
import uuid
from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Date, ForeignKey, Boolean, Text, Numeric,
    UniqueConstraint, Index
)
from app.db.session import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime.datetime:
    """Naive UTC timestamp (columns are TIMESTAMP WITHOUT TIME ZONE, like the core models)."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


MONEY = Numeric(14, 2)


class WaterCounter(Base):
    """Monotonic number series (consumer, bill, receipt ...). Values are never reset or reused (WB-01)."""
    __tablename__ = "wtr_counters"

    tenant_id = Column(String(50), primary_key=True)
    name = Column(String(40), primary_key=True)
    value = Column(Integer, nullable=False, default=0)


class WaterSetting(Base):
    """Versioned configuration: every rate, fee, SLA and threshold has an effective date (SRS 2.5, 3.4, WB-NF-50)."""
    __tablename__ = "wtr_settings"
    __table_args__ = (Index("ix_wtr_settings_key", "tenant_id", "key", "effective_from"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    key = Column(String(80), nullable=False)
    value_json = Column(Text, nullable=False)
    effective_from = Column(Date, nullable=False)
    reason = Column(Text, nullable=True)
    created_by = Column(String(150), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class WaterCategory(Base):
    """Connection category code list (domestic, non-domestic ...), extendable by configuration (WB-03, WB-NF-64)."""
    __tablename__ = "wtr_categories"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_wtr_category"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    code = Column(String(30), nullable=False)
    name_en = Column(String(100), nullable=False)
    name_te = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)


class WaterTariff(Base):
    """
    Tariff version per category (WB-20). Rows are never edited after approval; a new version with a
    later effective date replaces it, and old versions stay for past bills (WB-21, SRS 3.4).
    slabs_json: [{"uptoKl": 15, "ratePerKl": 7.0}, ..., {"uptoKl": null, "ratePerKl": 20.0}] (telescopic)
    flat_rates_json: {"15": 150.0, "20": 300.0} - monthly flat rate by pipe size in mm (WB-17)
    """
    __tablename__ = "wtr_tariffs"
    __table_args__ = (UniqueConstraint("tenant_id", "category_code", "version", name="uq_wtr_tariff_version"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    category_code = Column(String(30), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    effective_from = Column(Date, nullable=False)
    slabs_json = Column(Text, nullable=False)
    flat_rates_json = Column(Text, nullable=False, default="{}")
    minimum_charge = Column(MONEY, nullable=False, default=0)
    fixed_charge = Column(MONEY, nullable=False, default=0)
    cess_percent = Column(Numeric(6, 2), nullable=False, default=0)
    free_allowance_kl = Column(Numeric(10, 2), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="PENDING_APPROVAL")  # PENDING_APPROVAL, APPROVED, REJECTED
    order_reference = Column(String(150), nullable=True)  # government order behind the rate
    reason = Column(Text, nullable=True)
    requested_by = Column(String(150), nullable=False)
    approved_by = Column(String(150), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class WaterRoute(Base):
    """Reading route: a group of connections read by one meter reader in a set order (WB-12)."""
    __tablename__ = "wtr_routes"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_wtr_route"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    sub_tenant_id = Column(String(50), nullable=True, index=True)
    code = Column(String(30), nullable=False)
    name = Column(String(120), nullable=False)
    ward_id = Column(String(36), ForeignKey("wards.id"), nullable=True, index=True)
    reader_username = Column(String(150), nullable=True, index=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class WaterConnection(Base):
    """Water connection register (WB-01..WB-03, WB-IR-03). Keyed by a permanent consumer number."""
    __tablename__ = "wtr_connections"
    __table_args__ = (
        UniqueConstraint("tenant_id", "consumer_no", name="uq_wtr_consumer_no"),
        Index("ix_wtr_conn_latlng", "tenant_id", "latitude", "longitude"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    sub_tenant_id = Column(String(50), nullable=True, index=True)
    consumer_no = Column(String(30), nullable=False)
    old_consumer_no = Column(String(50), nullable=True, index=True)

    # Consumer (WB-03). citizen_id links to the platform citizen record when available (SRS 3.6.1).
    citizen_id = Column(String(64), nullable=True, index=True)
    consumer_name = Column(String(150), nullable=False, index=True)
    mobile_number = Column(String(15), nullable=True, index=True)
    email = Column(String(150), nullable=True)
    aadhaar_hash = Column(String(64), nullable=True)      # never stored in plain form (WB-NF-21)
    aadhaar_last4 = Column(String(4), nullable=True)

    # Property served (WB-02, WB-IR-03). Not validated against Property Tax in this release.
    door_no = Column(String(50), nullable=True)
    address = Column(Text, nullable=False)
    locality = Column(String(150), nullable=True)
    pincode = Column(String(10), nullable=True)
    old_assessment_no = Column(String(50), nullable=True, index=True)
    upin = Column(String(50), nullable=True, index=True)
    upin_source = Column(String(20), nullable=True)  # APPLICANT, STAFF, LINK

    # Location (WB-01)
    ward_id = Column(String(36), ForeignKey("wards.id"), nullable=False, index=True)
    zone_id = Column(String(36), ForeignKey("zones.id"), nullable=True, index=True)
    supply_area = Column(String(100), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    location_pending = Column(Boolean, default=False, nullable=False)  # migrated without location (SRS 3.6.2)

    # Connection (WB-03)
    category_code = Column(String(30), nullable=False, index=True)
    pipe_size_mm = Column(Integer, nullable=False)
    is_metered = Column(Boolean, nullable=False, default=True)
    connection_date = Column(Date, nullable=False)
    status = Column(String(25), nullable=False, default="ACTIVE", index=True)  # ACTIVE, TEMP_DISCONNECTED, DISCONNECTED, CLOSED
    route_id = Column(String(36), ForeignKey("wtr_routes.id"), nullable=True, index=True)
    route_sequence = Column(Integer, nullable=True)
    application_id = Column(String(36), nullable=True)
    source = Column(String(20), nullable=False, default="APPLICATION")  # APPLICATION, MIGRATION, REGULARISATION

    created_by = Column(String(150), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class WaterConnectionHistory(Base):
    """Field-level change history of a connection: old value, new value, who, when and why (WB-08)."""
    __tablename__ = "wtr_connection_history"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    connection_id = Column(String(36), ForeignKey("wtr_connections.id"), nullable=False, index=True)
    field = Column(String(60), nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    reason = Column(Text, nullable=False)
    changed_by = Column(String(150), nullable=False)
    changed_at = Column(DateTime, default=utcnow, nullable=False)


class WaterApplication(Base):
    """
    New connection and change requests (WB-05, WB-06). steps_json is a snapshot of the configured
    workflow at the time of filing: [{"code","label","slaHours","roles","enabled","status","dueAt","doneAt","doneBy","remark"}].
    """
    __tablename__ = "wtr_applications"
    __table_args__ = (UniqueConstraint("tenant_id", "application_no", name="uq_wtr_application_no"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    sub_tenant_id = Column(String(50), nullable=True, index=True)
    application_no = Column(String(40), nullable=False)
    app_type = Column(String(30), nullable=False, index=True)
    connection_id = Column(String(36), ForeignKey("wtr_connections.id"), nullable=True, index=True)
    channel = Column(String(20), nullable=False, default="COUNTER")  # PORTAL, APP, CSC, COUNTER

    applicant_name = Column(String(150), nullable=True)
    mobile_number = Column(String(15), nullable=True)
    email = Column(String(150), nullable=True)
    aadhaar_hash = Column(String(64), nullable=True)
    aadhaar_last4 = Column(String(4), nullable=True)
    consent_recorded = Column(Boolean, default=False, nullable=False)  # DPDP consent (WB-NF-20)

    ward_id = Column(String(36), ForeignKey("wards.id"), nullable=True, index=True)
    address = Column(Text, nullable=True)
    door_no = Column(String(50), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    details_json = Column(Text, nullable=False, default="{}")    # request-specific fields
    documents_json = Column(Text, nullable=False, default="[]")  # uploaded document refs
    warnings_json = Column(Text, nullable=False, default="[]")   # duplicate warnings (WB-04)

    estimate_json = Column(Text, nullable=True)
    estimate_total = Column(MONEY, nullable=True)
    amount_paid = Column(MONEY, nullable=False, default=0)

    steps_json = Column(Text, nullable=False, default="[]")
    current_step = Column(String(40), nullable=True)
    status = Column(String(20), nullable=False, default="IN_PROGRESS", index=True)  # IN_PROGRESS, COMPLETED, REJECTED
    escalation_level = Column(Integer, nullable=False, default=0)
    created_by = Column(String(150), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)


class WaterMeter(Base):
    """Meter register (WB-10, WB-11, WB-IR-07). make/size/serial kept matchable to Inventory stock later."""
    __tablename__ = "wtr_meters"
    __table_args__ = (UniqueConstraint("tenant_id", "serial_no", name="uq_wtr_meter_serial"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    connection_id = Column(String(36), ForeignKey("wtr_connections.id"), nullable=True, index=True)
    serial_no = Column(String(60), nullable=False)
    make = Column(String(80), nullable=False)
    size_mm = Column(Integer, nullable=False)
    seal_no = Column(String(60), nullable=True)
    initial_reading = Column(Numeric(14, 3), nullable=False, default=0)
    # consumption on the replaced meter since its last billed reading, added to this meter's first reading (WB-11)
    carry_over_kl = Column(Numeric(14, 3), nullable=False, default=0)
    fixed_on = Column(Date, nullable=False)
    status = Column(String(20), nullable=False, default="ACTIVE", index=True)  # ACTIVE, FAULTY, REPLACED, REMOVED
    final_reading = Column(Numeric(14, 3), nullable=True)
    removed_on = Column(Date, nullable=True)
    created_by = Column(String(150), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class WaterReading(Base):
    """
    Meter readings from every source through one intake (WB-13..WB-19). client_ref makes offline sync
    idempotent: a reading re-sent by the field app is not stored twice (WB-NF-33).
    """
    __tablename__ = "wtr_readings"
    __table_args__ = (
        UniqueConstraint("tenant_id", "client_ref", name="uq_wtr_reading_client_ref"),
        Index("ix_wtr_reading_conn_cycle", "connection_id", "cycle"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    connection_id = Column(String(36), ForeignKey("wtr_connections.id"), nullable=False, index=True)
    meter_id = Column(String(36), ForeignKey("wtr_meters.id"), nullable=True)
    route_id = Column(String(36), nullable=True, index=True)
    cycle = Column(String(7), nullable=False, index=True)  # YYYY-MM (first month of the billing cycle)
    reading_value = Column(Numeric(14, 3), nullable=True)
    previous_value = Column(Numeric(14, 3), nullable=True)
    consumption_kl = Column(Numeric(14, 3), nullable=True)
    no_reading_reason = Column(String(40), nullable=True)
    reading_at = Column(DateTime, nullable=False)
    photo_ref = Column(String(80), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    source = Column(String(20), nullable=False, default="FIELD")  # FIELD, CONSUMER, BULK, AMR, OFFICE
    flag = Column(String(25), nullable=False, default="NONE")      # NONE, LOWER_THAN_LAST, HIGH, LOW
    status = Column(String(20), nullable=False, default="ACCEPTED", index=True)  # ACCEPTED, PENDING_REVIEW, REJECTED, SUPERSEDED
    review_remark = Column(Text, nullable=True)
    reviewed_by = Column(String(150), nullable=True)
    client_ref = Column(String(80), nullable=True)
    captured_by = Column(String(150), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class WaterBillRun(Base):
    """One row per (cycle, route) so an interrupted run resumes from where it stopped (WB-23, WB-NF-63)."""
    __tablename__ = "wtr_bill_runs"
    __table_args__ = (UniqueConstraint("tenant_id", "cycle", "route_key", name="uq_wtr_bill_run"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    cycle = Column(String(7), nullable=False)
    route_key = Column(String(36), nullable=False)  # route id or "UNROUTED"
    status = Column(String(20), nullable=False, default="RUNNING")  # RUNNING, DONE
    bills_raised = Column(Integer, nullable=False, default=0)
    held_json = Column(Text, nullable=False, default="[]")
    started_by = Column(String(150), nullable=False)
    started_at = Column(DateTime, default=utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)


class WaterBill(Base):
    """A raised bill. Never edited; corrections go through approved adjustments (WB-24, WB-26)."""
    __tablename__ = "wtr_bills"
    __table_args__ = (
        UniqueConstraint("tenant_id", "bill_no", name="uq_wtr_bill_no"),
        UniqueConstraint("connection_id", "cycle", name="uq_wtr_bill_conn_cycle"),  # no double billing
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    bill_no = Column(String(40), nullable=False)
    connection_id = Column(String(36), ForeignKey("wtr_connections.id"), nullable=False, index=True)
    ward_id = Column(String(36), nullable=True, index=True)
    cycle = Column(String(7), nullable=False, index=True)
    period_from = Column(Date, nullable=False)
    period_to = Column(Date, nullable=False)
    bill_date = Column(Date, nullable=False, index=True)
    due_date = Column(Date, nullable=False, index=True)
    tariff_id = Column(String(36), ForeignKey("wtr_tariffs.id"), nullable=False)
    category_code = Column(String(30), nullable=False)
    basis = Column(String(15), nullable=False)  # ACTUAL, AVERAGE, FLAT
    reading_id = Column(String(36), nullable=True)
    previous_reading = Column(Numeric(14, 3), nullable=True)
    current_reading = Column(Numeric(14, 3), nullable=True)
    consumption_kl = Column(Numeric(14, 3), nullable=False, default=0)
    slab_breakup_json = Column(Text, nullable=False, default="[]")
    water_charge = Column(MONEY, nullable=False)
    fixed_charge = Column(MONEY, nullable=False)
    cess = Column(MONEY, nullable=False)
    current_demand = Column(MONEY, nullable=False)
    arrears = Column(MONEY, nullable=False, default=0)
    penalty = Column(MONEY, nullable=False, default=0)
    other_dues = Column(MONEY, nullable=False, default=0)
    advance_adjusted = Column(MONEY, nullable=False, default=0)
    total_payable = Column(MONEY, nullable=False)
    verification_code = Column(String(20), nullable=False)
    run_id = Column(String(36), nullable=True)
    created_by = Column(String(150), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class WaterLedger(Base):
    """
    Financial transaction ledger (WB-IR-05). amount is signed: positive raises what the consumer owes,
    negative lowers it. Balances are always derived from this table; rows are never updated or deleted.
    bucket: PENALTY, FEE, ARREAR, CURRENT (dues), ADVANCE (excess paid, held as credit), DEPOSIT (security deposit held)
    """
    __tablename__ = "wtr_ledger"
    __table_args__ = (
        Index("ix_wtr_ledger_conn_bucket", "connection_id", "bucket"),
        Index("ix_wtr_ledger_date", "tenant_id", "entry_date"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    connection_id = Column(String(36), ForeignKey("wtr_connections.id"), nullable=True, index=True)
    application_id = Column(String(36), ForeignKey("wtr_applications.id"), nullable=True, index=True)
    ward_id = Column(String(36), nullable=True, index=True)
    entry_date = Column(Date, nullable=False)
    txn_type = Column(String(25), nullable=False, index=True)
    component = Column(String(30), nullable=False)
    bucket = Column(String(10), nullable=False)
    account_head = Column(String(40), nullable=False, index=True)
    amount = Column(MONEY, nullable=False)
    payment_mode = Column(String(20), nullable=True)
    reference_no = Column(String(60), nullable=True)
    bill_id = Column(String(36), nullable=True, index=True)
    receipt_id = Column(String(36), nullable=True, index=True)
    approval_id = Column(String(36), nullable=True)
    is_reversal = Column(Boolean, default=False, nullable=False)
    reversal_of_id = Column(String(36), nullable=True)
    narration = Column(Text, nullable=True)
    created_by = Column(String(150), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class WaterReceipt(Base):
    """Receipt for every payment (WB-31). Never edited; only cancelled/bounced through reversal (WB-33, WB-36)."""
    __tablename__ = "wtr_receipts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "receipt_no", name="uq_wtr_receipt_no"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_wtr_receipt_idem"),  # WB-NF-32
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    receipt_no = Column(String(40), nullable=False)
    connection_id = Column(String(36), ForeignKey("wtr_connections.id"), nullable=True, index=True)
    application_id = Column(String(36), ForeignKey("wtr_applications.id"), nullable=True, index=True)
    ward_id = Column(String(36), nullable=True, index=True)
    amount = Column(MONEY, nullable=False)
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


class WaterPaymentIntent(Base):
    """Online payment order. Completed exactly once, by callback or by the gateway status check (WB-35)."""
    __tablename__ = "wtr_payment_intents"
    __table_args__ = (UniqueConstraint("tenant_id", "order_id", name="uq_wtr_payment_order"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    order_id = Column(String(40), nullable=False)
    connection_id = Column(String(36), ForeignKey("wtr_connections.id"), nullable=True, index=True)
    application_id = Column(String(36), nullable=True)
    amount = Column(MONEY, nullable=False)
    channel = Column(String(20), nullable=False, default="PORTAL")
    status = Column(String(15), nullable=False, default="INITIATED", index=True)  # INITIATED, SUCCESS, FAILED
    gateway_txn_id = Column(String(80), nullable=True)
    receipt_id = Column(String(36), nullable=True)
    completed_via = Column(String(15), nullable=True)  # CALLBACK, STATUS_CHECK
    created_by = Column(String(150), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)


class WaterGatewayStub(Base):
    """
    Stand-in payment gateway state (WB-IR-10). Holds what the 'gateway' knows about an order so the
    status check (WB-35) and daily statement (WB-34) can be exercised locally. Replaced by the real
    gateway adapter later without changing the module.
    """
    __tablename__ = "wtr_gateway_stub"

    order_id = Column(String(40), primary_key=True)
    tenant_id = Column(String(50), nullable=False, index=True)
    gateway_txn_id = Column(String(80), nullable=True)
    amount = Column(MONEY, nullable=False)
    status = Column(String(15), nullable=False)  # CAPTURED, FAILED
    captured_at = Column(DateTime, default=utcnow, nullable=False)


class WaterApproval(Base):
    """Maker-checker approvals: tariff, bill adjustment, receipt cancellation, refund, waiver, write-off."""
    __tablename__ = "wtr_approvals"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    approval_type = Column(String(25), nullable=False, index=True)
    connection_id = Column(String(36), nullable=True, index=True)
    ref_id = Column(String(36), nullable=True)
    ref_no = Column(String(60), nullable=True)
    amount = Column(MONEY, nullable=True)
    payload_json = Column(Text, nullable=False, default="{}")
    reason = Column(Text, nullable=False)
    status = Column(String(15), nullable=False, default="PENDING", index=True)  # PENDING, APPROVED, REJECTED
    requested_by = Column(String(150), nullable=False)
    requested_at = Column(DateTime, default=utcnow, nullable=False)
    decided_by = Column(String(150), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    decision_remark = Column(Text, nullable=True)


class WaterDayClose(Base):
    """Day-end closing of a collector's cash, matched by the cashier (WB-37)."""
    __tablename__ = "wtr_day_closes"
    __table_args__ = (UniqueConstraint("tenant_id", "collector", "close_date", name="uq_wtr_day_close"),)

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
    created_at = Column(DateTime, default=utcnow, nullable=False)


class WaterReconciliation(Base):
    """Result of matching a gateway/bank statement against online receipts (WB-34)."""
    __tablename__ = "wtr_reconciliations"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    statement_date = Column(Date, nullable=False)
    source = Column(String(20), nullable=False)  # GATEWAY, BANK
    matched_count = Column(Integer, nullable=False)
    mismatches_json = Column(Text, nullable=False)
    run_by = Column(String(150), nullable=False)
    run_at = Column(DateTime, default=utcnow, nullable=False)


class WaterOrder(Base):
    """Disconnection notice, disconnection order and reconnection work order (WB-43..WB-45)."""
    __tablename__ = "wtr_orders"
    __table_args__ = (UniqueConstraint("tenant_id", "order_no", name="uq_wtr_order_no"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    order_no = Column(String(40), nullable=False)
    order_type = Column(String(25), nullable=False, index=True)  # NOTICE, DISCONNECTION, RECONNECTION
    connection_id = Column(String(36), ForeignKey("wtr_connections.id"), nullable=False, index=True)
    ward_id = Column(String(36), nullable=True, index=True)
    status = Column(String(20), nullable=False, index=True)
    # NOTICE: OPEN, LISTED, WITHDRAWN | DISCONNECTION: PENDING, EXECUTED, CANCELLED | RECONNECTION: AWAITING_PAYMENT, PENDING, COMPLETED
    dues_at_issue = Column(MONEY, nullable=True)
    notice_until = Column(Date, nullable=True)
    sla_due_at = Column(DateTime, nullable=True)
    parent_order_id = Column(String(36), nullable=True)
    executed_at = Column(DateTime, nullable=True)
    executed_by = Column(String(150), nullable=True)
    photo_ref = Column(String(80), nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    remark = Column(Text, nullable=True)
    created_by = Column(String(150), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class WaterComplaint(Base):
    """Water complaints and field-logged leaks (WB-50..WB-52)."""
    __tablename__ = "wtr_complaints"
    __table_args__ = (UniqueConstraint("tenant_id", "complaint_no", name="uq_wtr_complaint_no"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    complaint_no = Column(String(40), nullable=False)
    complaint_type = Column(String(20), nullable=False, index=True)  # LEAK, NO_SUPPLY, DIRTY_WATER, METER, BILLING, OTHER
    source = Column(String(20), nullable=False)  # PORTAL, APP, WHATSAPP, CALL_CENTRE, FIELD, COUNTER
    connection_id = Column(String(36), ForeignKey("wtr_connections.id"), nullable=True, index=True)
    ward_id = Column(String(36), nullable=True, index=True)
    complainant_name = Column(String(150), nullable=True)
    complainant_mobile = Column(String(15), nullable=True)
    description = Column(Text, nullable=False)
    address = Column(Text, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    photo_ref = Column(String(80), nullable=True)
    assigned_to = Column(String(150), nullable=True, index=True)
    status = Column(String(15), nullable=False, default="OPEN", index=True)  # OPEN, IN_PROGRESS, CLOSED
    sla_due_at = Column(DateTime, nullable=False)
    escalation_level = Column(Integer, nullable=False, default=0)
    closing_photo_ref = Column(String(80), nullable=True)
    closing_remark = Column(Text, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    closed_by = Column(String(150), nullable=True)
    created_by = Column(String(150), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class WaterIllegalCase(Base):
    """Suspected illegal connection, tracked from report to closure (WB-53)."""
    __tablename__ = "wtr_illegal_cases"
    __table_args__ = (UniqueConstraint("tenant_id", "case_no", name="uq_wtr_case_no"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    case_no = Column(String(40), nullable=False)
    source = Column(String(20), nullable=False)  # STAFF, CITIZEN
    ward_id = Column(String(36), nullable=True, index=True)
    address = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    photo_ref = Column(String(80), nullable=True)
    status = Column(String(20), nullable=False, default="REPORTED", index=True)
    # REPORTED, INSPECTED, REGULARISED, DISCONNECTED, CLOSED_NO_ISSUE
    inspection_json = Column(Text, nullable=True)
    penalty_amount = Column(MONEY, nullable=True)
    connection_id = Column(String(36), nullable=True)  # regularised connection
    closure_remark = Column(Text, nullable=True)
    reported_by = Column(String(150), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    closed_at = Column(DateTime, nullable=True)


class WaterTimeline(Base):
    """Step-by-step timeline for complaints, illegal cases, applications and orders."""
    __tablename__ = "wtr_timeline"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    entity_type = Column(String(20), nullable=False)
    entity_id = Column(String(36), nullable=False, index=True)
    action = Column(String(40), nullable=False)
    remark = Column(Text, nullable=True)
    actor = Column(String(150), nullable=False)
    at = Column(DateTime, default=utcnow, nullable=False)


class WaterNotification(Base):
    """
    Outbound SMS / WhatsApp / email queue (WB-25, WB-31, WB-42, WB-51). The local build uses a stand-in
    sender that only records the message (WB-IR-10). dedupe_key stops the same reminder going twice.
    """
    __tablename__ = "wtr_notifications"
    __table_args__ = (UniqueConstraint("tenant_id", "dedupe_key", name="uq_wtr_notification_dedupe"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    channel = Column(String(15), nullable=False)
    recipient = Column(String(150), nullable=True)
    template = Column(String(40), nullable=False, index=True)
    message_en = Column(Text, nullable=False)
    message_te = Column(Text, nullable=False)
    connection_id = Column(String(36), nullable=True, index=True)
    ref_no = Column(String(60), nullable=True)
    dedupe_key = Column(String(120), nullable=True)
    status = Column(String(20), nullable=False, default="LOGGED_STAND_IN")
    created_at = Column(DateTime, default=utcnow, nullable=False)


class WaterEvent(Base):
    """Event outbox (WB-IR-02). Events are written even though nothing listens in this release."""
    __tablename__ = "wtr_events"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    event_type = Column(String(40), nullable=False, index=True)
    aggregate_id = Column(String(36), nullable=True, index=True)
    payload_json = Column(Text, nullable=False)
    published = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)


class WaterAuditLog(Base):
    """Append-only audit trail of every create, change, approval and payment (WB-NF-13). No update/delete API exists."""
    __tablename__ = "wtr_audit_log"

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


class WaterApiLog(Base):
    """Log of every Water API call with caller and result, for tracing between modules (WB-IR-11)."""
    __tablename__ = "wtr_api_log"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=True, index=True)
    caller = Column(String(150), nullable=True)
    method = Column(String(10), nullable=False)
    path = Column(String(300), nullable=False)
    status_code = Column(Integer, nullable=False)
    duration_ms = Column(Integer, nullable=False)
    at = Column(DateTime, default=utcnow, nullable=False, index=True)


class WaterMigrationException(Base):
    """Migrated records that could not be matched or located, kept for field verification (SRS 3.6.2)."""
    __tablename__ = "wtr_migration_exceptions"

    id = Column(String(36), primary_key=True, default=_uuid)
    tenant_id = Column(String(50), nullable=False, index=True)
    old_consumer_no = Column(String(50), nullable=True)
    raw_json = Column(Text, nullable=False)
    reason = Column(Text, nullable=False)
    status = Column(String(15), nullable=False, default="OPEN")
    created_by = Column(String(150), nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
