import datetime
import uuid
from sqlalchemy import (
    Column, String, Integer, BigInteger, Float, DateTime, ForeignKey, Boolean, Text, Numeric, JSON
)
from sqlalchemy.orm import relationship
from app.db.session import Base

class Tenant(Base):
    __tablename__ = "tenants"

    tenant_id = Column(String(50), primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    state_code = Column(String(10), nullable=False, default="TG")
    district = Column(String(100), nullable=False, default="Warangal")
    parent_state_tenant_id = Column(String(50), nullable=True, index=True)
    ulb_code = Column(String(30), nullable=True, index=True)
    tenant_slug = Column(String(100), nullable=True, index=True)
    ulb_type = Column(String(50), nullable=False, default="Municipal Corporation")
    administrative_grade = Column(String(50), nullable=True)
    official_website = Column(String(255), nullable=True)
    official_email = Column(String(150), nullable=True)
    contact_phone = Column(String(30), nullable=True)
    office_address = Column(Text, nullable=True)
    time_zone = Column(String(50), default="Asia/Kolkata", nullable=False)
    primary_language = Column(String(50), default="English", nullable=False)
    status = Column(String(20), default="Draft", nullable=False) # Draft, Active, Suspended
    enable_zones = Column(Boolean, default=False)
    enable_wards = Column(Boolean, default=True)
    effective_date = Column(String(30), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    zones = relationship("Zone", back_populates="tenant", cascade="all, delete-orphan")
    wards = relationship("Ward", back_populates="tenant", cascade="all, delete-orphan")
    parcels = relationship("PropertyParcel", back_populates="tenant", cascade="all, delete-orphan")

class Zone(Base):
    __tablename__ = "zones"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    code = Column(String(20), nullable=False)
    name = Column(String(100), nullable=False)

    tenant = relationship("Tenant", back_populates="zones")
    wards = relationship("Ward", back_populates="zone")

class Ward(Base):
    __tablename__ = "wards"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    zone_id = Column(String(36), ForeignKey("zones.id"), nullable=True, index=True)
    ward_number = Column(Integer, nullable=False, index=True)
    ward_code = Column(String(30), nullable=True)
    ward_name = Column(String(100), nullable=False)
    councilor_name = Column(String(100), nullable=True)
    boundary_geometry = Column(JSON, nullable=True)
    effective_from = Column(String(30), nullable=True)

    tenant = relationship("Tenant", back_populates="wards")
    zone = relationship("Zone", back_populates="wards")
    localities = relationship("Locality", back_populates="ward", cascade="all, delete-orphan")
    parcels = relationship("PropertyParcel", back_populates="ward")

class Locality(Base):
    __tablename__ = "localities"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    ward_id = Column(String(36), ForeignKey("wards.id"), nullable=False, index=True)
    locality_code = Column(String(30), nullable=False)
    locality_name = Column(String(150), nullable=False)
    pincode = Column(String(10), nullable=False)

    ward = relationship("Ward", back_populates="localities")
    parcels = relationship("PropertyParcel", back_populates="locality")

class PropertyParcel(Base):
    __tablename__ = "property_parcels"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    ulpin = Column(String(50), unique=True, nullable=False, index=True)
    survey_number = Column(String(50), nullable=False)
    plot_number = Column(String(50), nullable=True)
    total_area_sqyd = Column(Float, nullable=False)
    
    ward_id = Column(String(36), ForeignKey("wards.id"), nullable=False, index=True)
    locality_id = Column(String(36), ForeignKey("localities.id"), nullable=True)
    
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    address = Column(Text, nullable=False)
    
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    tenant = relationship("Tenant", back_populates="parcels")
    ward = relationship("Ward", back_populates="parcels")
    locality = relationship("Locality", back_populates="parcels")
    buildings = relationship("Building", back_populates="parcel", cascade="all, delete-orphan")

class Building(Base):
    __tablename__ = "buildings"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), nullable=False, index=True)
    parcel_id = Column(String(36), ForeignKey("property_parcels.id"), nullable=False, index=True)
    
    building_name = Column(String(150), nullable=True)
    building_type = Column(String(50), nullable=False) # Residential, Commercial, Mixed, Industrial
    total_floors = Column(Integer, default=1)
    construction_year = Column(Integer, nullable=True)
    building_permission_no = Column(String(100), nullable=True)

    parcel = relationship("PropertyParcel", back_populates="buildings")
    units = relationship("PropertyUnit", back_populates="building", cascade="all, delete-orphan")

class PropertyUnit(Base):
    __tablename__ = "property_units"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), nullable=False, index=True)
    building_id = Column(String(36), ForeignKey("buildings.id"), nullable=False, index=True)
    
    ptin = Column(String(30), unique=True, nullable=False, index=True) # 10-digit Property Tax Identification Number
    unit_number = Column(String(50), nullable=False)
    floor_number = Column(Integer, default=0) # 0 = Ground
    usage_category = Column(String(50), nullable=False) # Residential, Commercial, Institutional, Vacant Land
    
    carpet_area_sqft = Column(Float, nullable=False)
    built_up_area_sqft = Column(Float, nullable=False)
    occupancy_type = Column(String(30), nullable=False) # Owner, Tenant, Vacant
    
    annual_rental_value = Column(Numeric(12, 2), default=0.0)
    current_demand_amount = Column(Numeric(12, 2), default=0.0)
    tax_status = Column(String(30), default="PAID") # PAID, DUE, ARREARS, EXEMPT

    building = relationship("Building", back_populates="units")
    owners = relationship("Owner", back_populates="unit", cascade="all, delete-orphan")

class Owner(Base):
    __tablename__ = "owners"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), nullable=False, index=True)
    unit_id = Column(String(36), ForeignKey("property_units.id"), nullable=False, index=True)
    
    full_name = Column(String(150), nullable=False)
    mobile_number = Column(String(15), nullable=False, index=True)
    email = Column(String(100), nullable=True)
    aadhaar_vault_ref = Column(String(64), nullable=True)
    ownership_share = Column(Float, default=100.0) # Percentage

    unit = relationship("PropertyUnit", back_populates="owners")

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), ForeignKey("tenants.tenant_id"), nullable=False, default="GWMC")
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(150), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(150), nullable=False)
    role = Column(String(50), nullable=False, default="citizen") # super_admin, revenue_officer, town_planner, engineering_officer, citizen
    assigned_modules = Column(Text, nullable=False, default="GRV,PTX,WTR") # Comma-separated list of 19 module codes
    assigned_zone = Column(String(50), nullable=True)
    assigned_ward = Column(String(50), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class StateTenant(Base):
    __tablename__ = "state_tenants"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), unique=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    state_name = Column(String(100), nullable=False)
    state_code = Column(String(10), unique=True, index=True, nullable=False)
    tenant_slug = Column(String(100), unique=True, index=True, nullable=False)
    status = Column(String(20), default="Draft", nullable=False) # Draft, Active, Suspended
    country = Column(String(50), default="India", nullable=False)
    time_zone = Column(String(50), default="Asia/Kolkata", nullable=False)
    primary_language = Column(String(50), default="English", nullable=False)
    additional_languages = Column(JSON, default=list, nullable=True)
    official_state_name = Column(String(200), nullable=True)
    state_emblem_url = Column(Text, nullable=True)
    state_website = Column(String(255), nullable=True)
    administrative_email = Column(String(150), nullable=False)
    administrative_phone = Column(String(30), nullable=True)
    address = Column(Text, nullable=True)
    effective_date = Column(String(30), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class TenantAuditLog(Base):
    __tablename__ = "tenant_audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), nullable=False, index=True)
    action = Column(String(50), nullable=False) # CREATED, DRAFT_SAVED, ACTIVATED, SUSPENDED, UPDATED
    performed_by = Column(String(100), nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    details = Column(Text, nullable=True)
    ip_address = Column(String(50), nullable=True)

class TenantLifecycleEvent(Base):
    __tablename__ = "tenant_lifecycle_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), nullable=False, index=True)
    tenant_name = Column(String(150), nullable=True)
    tenant_level = Column(String(20), nullable=False, default="ULB") # State or ULB
    previous_status = Column(String(20), nullable=True)
    new_status = Column(String(20), nullable=False)
    event_type = Column(String(50), nullable=False) # STATUS_CHANGE, SUSPENSION, REACTIVATION, LOCK, MAINTENANCE, ARCHIVE
    reason = Column(Text, nullable=False)
    approval_reference = Column(String(100), nullable=True)
    effective_from = Column(DateTime, default=datetime.datetime.utcnow)
    effective_until = Column(DateTime, nullable=True)
    supporting_document = Column(String(255), nullable=True)
    data_retention_policy = Column(String(100), nullable=True)
    retention_period_years = Column(Integer, nullable=True)
    data_export_destination = Column(String(150), nullable=True)
    approval_authority = Column(String(100), nullable=True)
    performed_by = Column(String(100), nullable=False)
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)

class TenantMaintenanceConfig(Base):
    __tablename__ = "tenant_maintenance_configs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(50), unique=True, nullable=False, index=True)
    is_active = Column(Boolean, default=False, nullable=False)
    title = Column(String(150), nullable=True)
    message = Column(Text, nullable=True)
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    allowed_ips = Column(JSON, default=list, nullable=True)
    allow_admin_access = Column(Boolean, default=True, nullable=False)
    notification_required = Column(Boolean, default=False, nullable=False)
    notification_recipients = Column(JSON, default=list, nullable=True)
    reason = Column(Text, nullable=True)
    updated_by = Column(String(100), nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class State(Base):
    __tablename__ = "states"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code = Column(String(10), unique=True, index=True, nullable=False) # e.g. TR, TG, MH
    name = Column(String(100), nullable=False, index=True)
    official_name = Column(String(200), nullable=False)
    default_slug = Column(String(100), unique=True, nullable=False)
    primary_language = Column(String(50), default="English", nullable=False)
    additional_languages = Column(JSON, default=list, nullable=True)
    zone = Column(String(50), nullable=True) # North, South, East, West, Central, North East, UT
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    districts = relationship("District", back_populates="state", cascade="all, delete-orphan")
    cities = relationship("City", back_populates="state", cascade="all, delete-orphan")

class District(Base):
    __tablename__ = "districts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    state_code = Column(String(10), ForeignKey("states.code"), nullable=False, index=True)
    code = Column(String(20), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False, index=True)
    headquarters = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    state = relationship("State", back_populates="districts")
    cities = relationship("City", back_populates="district", cascade="all, delete-orphan")

class City(Base):
    __tablename__ = "cities"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    state_code = Column(String(10), ForeignKey("states.code"), nullable=False, index=True)
    district_id = Column(String(36), ForeignKey("districts.id"), nullable=True, index=True)
    name = Column(String(100), nullable=False, index=True)
    ulb_type = Column(String(50), default="Municipal Corporation", nullable=False)
    ulb_code = Column(String(30), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    state = relationship("State", back_populates="cities")
    district = relationship("District", back_populates="cities")

class ModuleModel(Base):
    __tablename__ = "modules"

    module_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(150), nullable=False)
    code = Column(String(20), unique=True, index=True, nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(50), nullable=False)  # Revenue & Billing, Finance & Administration, Planning & Regulation, Infrastructure & Field Operations, Citizen Engagement & Welfare
    icon = Column(String(50), nullable=True)
    display_order = Column(Integer, default=1, nullable=False)
    module_version = Column(String(20), default="1.0.0", nullable=False)
    status = Column(String(20), default="Published", nullable=False)  # Draft, Published, Deprecated
    dependencies = Column(JSON, default=list, nullable=True)
    minimum_platform_version = Column(String(20), nullable=True)
    documentation_url = Column(String(255), nullable=True)
    effective_from = Column(String(30), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    components = relationship("ComponentModel", back_populates="module", cascade="all, delete-orphan")

class ComponentModel(Base):
    __tablename__ = "components"

    component_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    parent_module_code = Column(String(20), ForeignKey("modules.code"), nullable=False, index=True)
    name = Column(String(150), nullable=False)
    code = Column(String(30), unique=True, index=True, nullable=False)
    description = Column(Text, nullable=False)
    component_type = Column(String(50), default="Process", nullable=False)  # Process, Service, UI View, Report, Workflow
    route_path = Column(String(255), nullable=True)
    frontend_permission_key = Column(String(100), nullable=False)
    backend_api_permission_key = Column(String(100), nullable=False)
    supported_actions = Column(JSON, default=list, nullable=False)
    dependencies = Column(JSON, default=list, nullable=True)
    status = Column(String(20), default="Published", nullable=False)  # Draft, Published, Deprecated
    display_order = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    module = relationship("ModuleModel", back_populates="components")

class ModuleChangeHistory(Base):
    __tablename__ = "module_change_history"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    entity_type = Column(String(20), nullable=False)  # MODULE or COMPONENT
    entity_code = Column(String(50), nullable=False)
    action = Column(String(50), nullable=False)  # CREATED, UPDATED, PUBLISHED, DEPRECATED, IMPORTED
    performed_by = Column(String(100), nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    details = Column(Text, nullable=True)

class SSOConfiguration(Base):
    __tablename__ = "sso_configurations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    provider_name = Column(String(100), nullable=False, default="SUVIDHA Central Keycloak Identity")
    provider_type = Column(String(50), nullable=False, default="Keycloak")
    keycloak_base_url = Column(String(255), nullable=False, default="http://localhost:8080")
    keycloak_realm = Column(String(100), nullable=False, default="urban-suvidha")
    client_id = Column(String(100), nullable=False, default="urban-console")
    client_secret = Column(String(255), nullable=True)
    redirect_uri = Column(String(255), nullable=False, default="http://localhost:4200/auth/callback")
    post_logout_redirect_uri = Column(String(255), nullable=True, default="http://localhost:4200/login")
    oidc_scopes = Column(JSON, default=lambda: ["openid", "profile", "email", "roles"], nullable=False)
    discovery_url = Column(String(255), nullable=True)
    connection_status = Column(String(30), default="Connected", nullable=False)
    last_connection_test = Column(DateTime, default=datetime.datetime.utcnow)

    # Authentication & SSO Policy
    enable_sso = Column(Boolean, default=True, nullable=False)
    login_methods = Column(JSON, default=lambda: ["Password", "SSO", "OTP"], nullable=False)
    mfa_required = Column(Boolean, default=False, nullable=False)
    mfa_policy = Column(String(50), default="Admins Only", nullable=False)  # Optional, Admins Only, Mandatory All
    allowed_identity_providers = Column(JSON, default=list, nullable=True)
    session_idle_timeout_mins = Column(Integer, default=30, nullable=False)
    max_session_lifetime_mins = Column(Integer, default=480, nullable=False)
    remember_me = Column(Boolean, default=True, nullable=False)
    brute_force_protection = Column(Boolean, default=True, nullable=False)
    max_failed_attempts = Column(Integer, default=5, nullable=False)
    password_min_length = Column(Integer, default=8, nullable=False)
    password_require_uppercase = Column(Boolean, default=True, nullable=False)
    password_require_lowercase = Column(Boolean, default=True, nullable=False)
    password_require_digits = Column(Boolean, default=True, nullable=False)
    password_require_special = Column(Boolean, default=True, nullable=False)
    password_expiry_days = Column(Integer, default=90, nullable=False)
    allowed_email_domains = Column(JSON, default=lambda: ["gov.in", "nic.in", "urban.gov.in"], nullable=False)
    require_verified_email = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class IdentityProviderFederation(Base):
    __tablename__ = "identity_provider_federations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    protocol = Column(String(20), nullable=False, default="OIDC")  # OIDC, SAML
    issuer_url = Column(String(255), nullable=False)
    client_id = Column(String(100), nullable=True)
    client_secret = Column(String(255), nullable=True)
    metadata_url = Column(String(255), nullable=True)
    claim_mapping = Column(JSON, default=lambda: {"sub": "sub", "email": "email", "name": "name", "roles": "roles"}, nullable=False)
    user_linking_policy = Column(String(50), default="Auto-link by Email", nullable=False)  # Auto-link by Email, Require Manual Verification, Disabled
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class AuthenticationAuditLog(Base):
    __tablename__ = "authentication_audit_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_type = Column(String(50), nullable=False)  # LOGIN_SUCCESS, LOGIN_FAILURE, MFA_CHALLENGE, SSO_REDIRECT, PASSWORD_RESET, FEDERATION_TOKEN_EXCHANGED
    username = Column(String(150), nullable=False)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(255), nullable=True)
    idp_used = Column(String(100), nullable=True)
    details = Column(Text, nullable=True)
    status = Column(String(20), default="SUCCESS", nullable=False)  # SUCCESS, FAILED, BLOCKED
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class RoleModel(Base):
    __tablename__ = "roles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False)
    code = Column(String(50), unique=True, index=True, nullable=False)
    description = Column(Text, nullable=False)
    role_level = Column(String(50), nullable=False)  # Platform Super Admin, State Admin, ULB Admin, Department Admin, Officer, Auditor, Read-only User
    scope_type = Column(String(50), nullable=False)  # Platform, State, ULB, Department, Ward
    parent_role_id = Column(String(36), nullable=True)
    status = Column(String(20), default="Active", nullable=False)  # Active, Inactive, Deprecated
    effective_from = Column(DateTime, nullable=True)
    effective_until = Column(DateTime, nullable=True)
    is_system = Column(Boolean, default=False, nullable=False)
    is_template = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class RolePermission(Base):
    __tablename__ = "role_permissions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    role_id = Column(String(36), ForeignKey("roles.id", ondelete="CASCADE"), index=True, nullable=False)
    module_code = Column(String(20), index=True, nullable=False)
    component_code = Column(String(50), index=True, nullable=False)
    can_view = Column(Boolean, default=False, nullable=False)
    can_create = Column(Boolean, default=False, nullable=False)
    can_update = Column(Boolean, default=False, nullable=False)
    can_delete = Column(Boolean, default=False, nullable=False)
    can_approve = Column(Boolean, default=False, nullable=False)
    can_export = Column(Boolean, default=False, nullable=False)
    can_manage = Column(Boolean, default=False, nullable=False)
    data_scope = Column(String(50), default="Own Records", nullable=False)  # Own Records, Assigned Department, Ward, ULB, State, Platform
    conditions = Column(JSON, nullable=True)
    effective_from = Column(DateTime, nullable=True)
    effective_until = Column(DateTime, nullable=True)

class GlobalUserProfile(Base):
    __tablename__ = "global_user_profiles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    first_name = Column(String(50), nullable=False)
    middle_name = Column(String(50), nullable=True)
    last_name = Column(String(50), nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    mobile_number = Column(String(20), nullable=True)
    idp_provider = Column(String(50), default="Keycloak Suvidha", nullable=False)
    external_identity_id = Column(String(100), nullable=True)
    user_type = Column(String(50), default="Internal Staff", nullable=False)  # Internal Staff, Government Officer, Support Staff, Auditor, External Partner
    account_status = Column(String(20), default="Active", nullable=False)  # Active, Suspended, Pending Invitation, Deactivated
    preferred_language = Column(String(20), default="English", nullable=False)
    time_zone = Column(String(50), default="Asia/Kolkata", nullable=False)
    employee_id = Column(String(50), nullable=True)
    designation = Column(String(100), nullable=True)
    department = Column(String(100), nullable=True)
    profile_photo_url = Column(String(255), nullable=True)
    account_expiry_date = Column(DateTime, nullable=True)
    remarks = Column(Text, nullable=True)

    # Scopes
    platform_access = Column(Boolean, default=False, nullable=False)
    state_tenant_id = Column(String(50), nullable=True)
    ulb_tenant_id = Column(String(50), nullable=True)
    assigned_department = Column(String(100), nullable=True)
    assigned_zone = Column(String(50), nullable=True)
    assigned_ward = Column(String(50), nullable=True)
    assigned_roles = Column(JSON, default=list, nullable=False)
    additional_permissions = Column(JSON, default=list, nullable=False)
    access_effective_from = Column(DateTime, nullable=True)
    access_effective_until = Column(DateTime, nullable=True)
    approval_reference = Column(String(100), nullable=True)
    last_active_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class UserInvitation(Base):
    __tablename__ = "user_invitations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(150), index=True, nullable=False)
    user_type = Column(String(50), default="Internal Staff", nullable=False)
    target_tenant_id = Column(String(50), nullable=False)
    target_sub_tenant_id = Column(String(50), nullable=True)
    assigned_role = Column(String(50), nullable=False)
    department_scope = Column(String(100), nullable=True)
    ward_scope = Column(String(50), nullable=True)
    invitation_token = Column(String(100), unique=True, index=True, nullable=False)
    invitation_expiry = Column(DateTime, nullable=False)
    require_mfa = Column(Boolean, default=True, nullable=False)
    invitation_message = Column(Text, nullable=True)
    status = Column(String(20), default="Pending", nullable=False)  # Pending, Accepted, Expired, Revoked
    invited_by = Column(String(150), default="Super Admin", nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class RLSPolicyModel(Base):
    __tablename__ = "rls_policy_registry"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_name = Column(String(255), nullable=False)
    policy_code = Column(String(100), unique=True, index=True, nullable=False)
    database_service = Column(String(100), default="PostgreSQL 16 (Core Service)", nullable=False)
    schema_name = Column(String(100), default="public", nullable=False)
    table_name = Column(String(100), nullable=False)
    tenant_key_column = Column(String(100), default="tenant_id", nullable=False)
    policy_type = Column(String(50), default="ALL", nullable=False)  # SELECT, INSERT, UPDATE, DELETE, ALL
    database_commands = Column(JSON, default=list, nullable=False)  # ['SELECT', 'INSERT', 'UPDATE', 'DELETE']
    applicable_tenant_levels = Column(JSON, default=list, nullable=False)  # ['State', 'ULB', 'Department']
    policy_definition = Column(Text, nullable=False)
    policy_status = Column(String(50), default="ACTIVE", nullable=False)  # ACTIVE, DISABLED, PENDING_VERIFICATION
    last_verified_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_verification_result = Column(String(50), default="VERIFIED", nullable=False)  # VERIFIED, FAILED, UNTESTED
    verification_latency_ms = Column(Float, default=1.2, nullable=False)
    enforcement_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class TenantIsolationTestRun(Base):
    __tablename__ = "tenant_isolation_test_runs"

    id = Column(String(100), primary_key=True)  # e.g. ISO-RUN-2026-001
    test_run_name = Column(String(255), nullable=False)
    environment = Column(String(100), default="Isolated Sandbox", nullable=False)
    source_tenant = Column(String(255), nullable=False)
    target_tenant = Column(String(255), nullable=False)
    test_scenarios = Column(JSON, default=list, nullable=False)
    database_services = Column(JSON, default=list, nullable=False)
    tables_in_scope = Column(JSON, default=list, nullable=False)
    test_type = Column(String(100), default="Synthetic Penetration Test", nullable=False)
    execution_mode = Column(String(50), default="Automated Batch", nullable=False)
    schedule = Column(String(100), nullable=True)
    notification_recipients = Column(JSON, default=list, nullable=False)
    stop_on_critical_failure = Column(Boolean, default=True, nullable=False)
    status = Column(String(50), default="PASSED", nullable=False)  # PASSED, FAILED, RUNNING, SCHEDULED
    start_time = Column(DateTime, default=datetime.datetime.utcnow)
    end_time = Column(DateTime, default=datetime.datetime.utcnow)
    total_tests = Column(Integer, default=8, nullable=False)
    passed_count = Column(Integer, default=8, nullable=False)
    failed_count = Column(Integer, default=0, nullable=False)
    execution_latency_ms = Column(Float, default=42.5, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class IsolationFindingReport(Base):
    __tablename__ = "isolation_finding_reports"

    id = Column(String(100), primary_key=True)  # e.g. SEC-FIND-2026-001
    test_run_id = Column(String(100), nullable=True)
    severity = Column(String(50), default="HIGH", nullable=False)  # CRITICAL, HIGH, MEDIUM, LOW
    finding_title = Column(String(255), nullable=False)
    finding_description = Column(Text, nullable=False)
    affected_tenant = Column(String(255), nullable=False)
    affected_resource = Column(String(255), nullable=False)
    remediation_owner = Column(String(255), nullable=False)
    remediation_due_date = Column(String(50), nullable=False)
    resolution_notes = Column(Text, nullable=True)
    retest_status = Column(String(50), default="OPEN", nullable=False)  # OPEN, IN_REMEDIATION, RESOLVED, VERIFIED
    detected_at = Column(DateTime, default=datetime.datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)


# ADM-M04 State Module Subscription Allocator Models
class StateModuleSubscription(Base):
    __tablename__ = "state_module_subscriptions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    subscription_id = Column(String(50), unique=True, index=True, nullable=False)
    state_tenant_id = Column(String(36), ForeignKey("state_tenants.tenant_id"), nullable=False, index=True)
    subscription_name = Column(String(150), nullable=False)
    subscription_type = Column(String(50), default="Standard", nullable=False)  # Standard, Premium, Custom, Government Sponsored
    subscribed_modules = Column(JSON, default=list, nullable=False)  # List of dicts: [{"code": "PTX", "name": "Property Tax", "version": "1.0.0", "category": "..."}]
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=True)
    billing_cycle = Column(String(30), default="Yearly", nullable=True)  # Monthly, Quarterly, Half-Yearly, Yearly, Custom
    status = Column(String(30), default="Active", nullable=False)  # Active, Suspended, Expired, Revoked, Draft
    auto_renewal = Column(Boolean, default=False, nullable=False)
    remarks = Column(Text, nullable=True)
    approval_reference = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class StateSubscriptionHistory(Base):
    __tablename__ = "state_subscription_histories"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    subscription_id = Column(String(50), index=True, nullable=False)
    state_tenant_id = Column(String(36), nullable=False, index=True)
    module_code = Column(String(30), nullable=True)
    action_type = Column(String(50), nullable=False)  # Allocated, Renewed, Modules_Added, Modules_Revoked, Suspended, Expired, Revoked
    previous_status = Column(String(30), nullable=True)
    new_status = Column(String(30), nullable=True)
    previous_expiry_date = Column(DateTime, nullable=True)
    new_expiry_date = Column(DateTime, nullable=True)
    changed_modules = Column(JSON, default=list, nullable=True)
    changed_by = Column(String(150), nullable=False)
    change_reason = Column(Text, nullable=True)
    approval_reference = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# ADM-M05 Sub-Tenant Cascade Delegation Guard Models
class DelegationRuleModel(Base):
    __tablename__ = "delegation_rules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    rule_code = Column(String(50), unique=True, index=True, nullable=False)
    rule_name = Column(String(150), nullable=False)
    state_tenant_id = Column(String(36), ForeignKey("state_tenants.tenant_id"), nullable=False, index=True)
    applicable_ulb_types = Column(JSON, default=list, nullable=True)
    delegation_mode = Column(String(50), default="Selective Delegation", nullable=False)  # Full Delegation, Selective Delegation, Restricted Delegation, No Delegation
    allow_module_delegation = Column(Boolean, default=True, nullable=False)
    allow_component_delegation = Column(Boolean, default=True, nullable=False)
    allow_role_delegation = Column(Boolean, default=True, nullable=False)
    require_state_approval = Column(Boolean, default=True, nullable=False)
    effective_from = Column(DateTime, nullable=False)
    effective_until = Column(DateTime, nullable=True)
    description = Column(Text, nullable=False)
    rule_status = Column(String(20), default="Active", nullable=False)  # Active, Draft, Deprecated
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class UlbModuleAllocationModel(Base):
    __tablename__ = "ulb_module_allocations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    allocation_id = Column(String(60), unique=True, index=True, nullable=False)
    state_tenant_id = Column(String(36), ForeignKey("state_tenants.tenant_id"), nullable=False, index=True)
    ulb_tenant_id = Column(String(50), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    module_code = Column(String(30), nullable=False, index=True)
    module_name = Column(String(150), nullable=False)
    allocated_components = Column(JSON, default=list, nullable=True)
    allowed_actions = Column(JSON, default=list, nullable=True)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=True)
    status = Column(String(20), default="Active", nullable=False)  # Active, Suspended, Revoked, Draft
    approval_reference = Column(String(100), nullable=True)
    remarks = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class UlbComponentRestrictionModel(Base):
    __tablename__ = "ulb_component_restrictions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    restriction_id = Column(String(60), unique=True, index=True, nullable=False)
    state_tenant_id = Column(String(36), ForeignKey("state_tenants.tenant_id"), nullable=False, index=True)
    ulb_tenant_id = Column(String(50), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    module_code = Column(String(30), nullable=False, index=True)
    component_code = Column(String(50), nullable=False, index=True)
    component_name = Column(String(150), nullable=True)
    restriction_type = Column(String(50), default="Block Selected Actions", nullable=False)  # Block Entire Component, Block Selected Actions, Read Only, Restrict Data Scope
    restricted_actions = Column(JSON, default=list, nullable=True)
    reason = Column(Text, nullable=False)
    effective_from = Column(DateTime, nullable=False)
    effective_until = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class DelegationAuditHistoryModel(Base):
    __tablename__ = "delegation_audit_histories"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    state_tenant_id = Column(String(36), nullable=False, index=True)
    ulb_tenant_id = Column(String(50), nullable=True, index=True)
    module_code = Column(String(30), nullable=True)
    action_type = Column(String(50), nullable=False)
    details = Column(JSON, default=dict, nullable=True)
    changed_by = Column(String(150), nullable=False)
    change_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# ADM-C06 Immutable Audit Vault Models
class ImmutableAuditEventModel(Base):
    __tablename__ = "immutable_audit_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    event_id = Column(String(50), unique=True, index=True, nullable=False)
    sequence_number = Column(BigInteger, index=True, nullable=False)
    tenant_id = Column(String(50), nullable=True, index=True)
    tenant_level = Column(String(20), default="Level 0", nullable=False)  # Level 0, Level 1, Level 2
    sub_tenant_id = Column(String(50), nullable=True, index=True)
    state_code = Column(String(10), nullable=True, index=True)
    module_code = Column(String(20), nullable=True, index=True)
    component_code = Column(String(50), nullable=True, index=True)
    event_category = Column(String(50), nullable=False, index=True)  # Authentication, Authorisation, Tenant Management, User Management, Subscription Changes, Configuration Changes, Data Access, Administrative Actions
    action = Column(String(100), nullable=False, index=True)
    severity = Column(String(20), default="Informational", nullable=False)  # Informational, Low, Medium, High, Critical
    actor_id = Column(String(150), nullable=False, index=True)
    actor_role = Column(String(100), default="Platform Super Admin")
    ip_address = Column(String(50), default="127.0.0.1")
    user_agent = Column(String(255), nullable=True)
    correlation_id = Column(String(100), nullable=False, index=True)
    result = Column(String(20), default="SUCCESS", nullable=False)  # SUCCESS, FAILURE, DENIED, ERROR
    details = Column(JSON, default=dict)
    prev_event_hash = Column(String(128), nullable=False)
    event_hash = Column(String(128), nullable=False, index=True)
    signature = Column(String(255), nullable=True)
    is_legal_hold = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, index=True)


class AuditHashVerificationJobModel(Base):
    __tablename__ = "audit_hash_verification_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(50), unique=True, index=True, nullable=False)
    job_name = Column(String(150), nullable=False)
    verification_scope = Column(String(50), default="Global Platform", nullable=False)  # Global Platform, State Jurisdiction, ULB Scope
    tenant_id = Column(String(50), nullable=True, index=True)
    from_timestamp = Column(DateTime, nullable=False)
    to_timestamp = Column(DateTime, nullable=False)
    algorithm = Column(String(20), default="SHA-256", nullable=False)  # SHA-256, SHA-512
    verification_mode = Column(String(50), default="On-Demand Scan", nullable=False)  # Continuous, On-Demand Scan, Deep Integrity Audit
    notification_recipients = Column(JSON, default=list)
    remarks = Column(Text, nullable=True)
    first_event_hash = Column(String(128), nullable=True)
    last_event_hash = Column(String(128), nullable=True)
    expected_hash = Column(String(128), nullable=True)
    calculated_hash = Column(String(128), nullable=True)
    verification_result = Column(String(50), default="VALID_INTEGRITY_INTACT", nullable=False)  # VALID_INTEGRITY_INTACT, TAMPER_DETECTED, CHAIN_BROKEN
    total_verified_events = Column(Integer, default=0)
    mismatch_count = Column(Integer, default=0)
    executed_by = Column(String(150), default="admin@urban.gov.in")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class AuditRetentionPolicyModel(Base):
    __tablename__ = "audit_retention_policies"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_code = Column(String(50), unique=True, index=True, nullable=False)
    policy_name = Column(String(150), nullable=False)
    applicable_tenant_levels = Column(JSON, default=list)  # ["Level 0", "Level 1", "Level 2"]
    event_categories = Column(JSON, default=list)
    retention_period = Column(Integer, nullable=False, default=7)
    retention_unit = Column(String(20), default="Years", nullable=False)  # Days, Months, Years
    archive_required = Column(Boolean, default=True, nullable=False)
    archive_destination = Column(String(100), default="State Government Cold Storage Vault", nullable=True)
    legal_hold_enabled = Column(Boolean, default=False, nullable=False)
    effective_date = Column(DateTime, nullable=False)
    policy_status = Column(String(20), default="Active", nullable=False)  # Active, Draft, Inactive
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class AuditExportJobModel(Base):
    __tablename__ = "audit_export_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    export_id = Column(String(50), unique=True, index=True, nullable=False)
    export_name = Column(String(150), nullable=False)
    export_format = Column(String(20), default="CSV", nullable=False)  # CSV, JSON, PDF
    tenant_scope = Column(String(50), default="All Tenants", nullable=False)
    state_tenant_id = Column(String(50), nullable=True)
    ulb_tenant_id = Column(String(50), nullable=True)
    event_categories = Column(JSON, default=list)
    date_from = Column(DateTime, nullable=False)
    date_to = Column(DateTime, nullable=False)
    include_hash_info = Column(Boolean, default=True, nullable=False)
    mask_sensitive_info = Column(Boolean, default=True, nullable=False)
    export_reason = Column(Text, nullable=False)
    approval_reference = Column(String(100), nullable=True)
    status = Column(String(20), default="Completed", nullable=False)  # Completed, Processing, Archived
    exported_by = Column(String(150), default="admin@urban.gov.in")
    file_size_bytes = Column(Integer, default=0)
    file_checksum = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


# ADM-O01 Platform Fleet & Microservice Cluster Models
class MicroserviceRegistryModel(Base):
    __tablename__ = "fleet_microservices"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    service_code = Column(String(50), unique=True, index=True, nullable=False)
    service_name = Column(String(150), nullable=False)
    service_description = Column(Text, nullable=False)
    service_category = Column(String(50), default="Core Platform", nullable=False)  # Core Platform, Domain Microservice, Worker Daemon, Integration Gateway, Data & Analytics
    service_type = Column(String(50), default="Stateless HTTP", nullable=False)  # Stateless HTTP, Async Worker, Event Streamer, Stateful Cache
    environments = Column(JSON, default=list, nullable=False)  # ["Production", "Staging", "Dev"]
    base_url = Column(String(255), nullable=False)
    health_check_endpoint = Column(String(100), default="/health", nullable=False)
    health_check_method = Column(String(20), default="GET", nullable=False)  # GET, POST, HEAD
    health_check_interval_seconds = Column(Integer, default=15, nullable=False)
    timeout_seconds = Column(Integer, default=5, nullable=False)
    retry_count = Column(Integer, default=3, nullable=False)
    criticality_level = Column(String(30), default="P1 - High", nullable=False)  # P0 - Critical, P1 - High, P2 - Normal, P3 - Low
    monitoring_enabled = Column(Boolean, default=True, nullable=False)
    alert_policy = Column(String(100), nullable=True)
    status = Column(String(30), default="Healthy", nullable=False)  # Healthy, Degraded, Unavailable
    version = Column(String(30), default="v2.4.0", nullable=False)
    region = Column(String(50), default="ap-south-1 (Hyderabad)", nullable=False)
    uptime_pct = Column(Float, default=99.98)
    avg_latency_ms = Column(Float, default=24.5)
    error_rate_pct = Column(Float, default=0.02)
    cpu_usage_pct = Column(Float, default=34.2)
    memory_usage_pct = Column(Float, default=56.0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class PodMonitoringModel(Base):
    __tablename__ = "fleet_pods"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pod_name = Column(String(100), unique=True, index=True, nullable=False)
    service_code = Column(String(50), index=True, nullable=False)
    service_name = Column(String(150), nullable=False)
    cluster = Column(String(100), default="suvidha-k8s-prod-in-south", nullable=False)
    namespace = Column(String(100), default="prod-municipal-erp", nullable=False)
    deployment = Column(String(100), nullable=False)
    node_name = Column(String(100), nullable=False)
    pod_status = Column(String(30), default="Running", nullable=False)  # Running, Pending, CrashLoopBackOff, Terminating
    readiness_status = Column(String(30), default="Ready (1/1)", nullable=False)
    liveness_status = Column(String(30), default="Passing", nullable=False)
    cpu_millicores = Column(Integer, default=280)
    memory_mb = Column(Integer, default=512)
    restart_count = Column(Integer, default=0)
    pod_uptime = Column(String(50), default="14d 6h")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class WorkerQueueModel(Base):
    __tablename__ = "fleet_worker_queues"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    queue_name = Column(String(100), unique=True, index=True, nullable=False)
    worker_service = Column(String(100), nullable=False)
    queue_type = Column(String(50), default="Celery / Redis", nullable=False)  # Celery / Redis, Kafka Topic, RabbitMQ, Cloud PubSub
    queue_status = Column(String(30), default="Optimal", nullable=False)  # Optimal, Backlogged, Stalled, Paused
    pending_jobs = Column(Integer, default=0)
    processing_jobs = Column(Integer, default=0)
    failed_jobs = Column(Integer, default=0)
    avg_processing_time_ms = Column(Float, default=125.0)
    throughput_jobs_sec = Column(Float, default=45.0)
    worker_availability = Column(Integer, default=6)
    alert_threshold = Column(Integer, default=500)
    notification_recipients = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class DatabaseConnectionPoolModel(Base):
    __tablename__ = "fleet_db_pools"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pool_name = Column(String(100), unique=True, index=True, nullable=False)
    database_cluster = Column(String(100), nullable=False)
    database_name = Column(String(100), nullable=False)
    service_name = Column(String(100), nullable=False)
    connection_status = Column(String(30), default="Optimal", nullable=False)  # Optimal, Congested, Pool Exhausted, Degraded
    active_connections = Column(Integer, default=18)
    idle_connections = Column(Integer, default=12)
    max_pool_size = Column(Integer, default=60)
    connection_wait_time_ms = Column(Float, default=1.6)
    connection_failures = Column(Integer, default=0)
    query_latency_p95_ms = Column(Float, default=7.8)
    alert_threshold_pct = Column(Integer, default=85)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class BackupPolicyModel(Base):
    __tablename__ = "backup_policies"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    policy_name = Column(String(150), nullable=False)
    policy_code = Column(String(80), unique=True, index=True, nullable=False)
    backup_type = Column(String(50), default="Full Backup", nullable=False)  # Full Backup, Incremental Backup, Differential Backup, WAL / Transaction Log Backup
    backup_scope = Column(String(50), default="Platform Full Database", nullable=False)  # Platform Full Database, Tenant Scoped, Configuration Only, Audit Vault WORM
    environment = Column(String(30), default="Production", nullable=False)
    database_cluster = Column(String(100), default="pg-aurora-cluster-prod", nullable=False)
    database_name = Column(String(100), default="urban_core_prod", nullable=False)
    tenant_scope = Column(String(100), default="All State Tenants", nullable=False)
    backup_destination = Column(String(100), default="AWS S3 (Immutable Glacier Lock)", nullable=False)
    storage_bucket_path = Column(String(255), default="s3://suvidha-backup-vault-prod/pg-cluster-01/", nullable=False)
    backup_frequency = Column(String(50), default="Daily", nullable=False)  # Hourly, Daily, Weekly, Monthly, Custom
    backup_schedule = Column(String(100), default="0 2 * * * (02:00 AM IST)", nullable=False)
    time_zone = Column(String(50), default="Asia/Kolkata (IST)", nullable=False)
    retention_period = Column(Integer, default=90, nullable=False)
    retention_unit = Column(String(20), default="Days", nullable=False)  # Days, Months, Years
    encryption_enabled = Column(Boolean, default=True, nullable=False)
    compression_enabled = Column(Boolean, default=True, nullable=False)
    backup_verification = Column(Boolean, default=True, nullable=False)
    notification_recipients = Column(JSON, default=list)
    policy_status = Column(String(30), default="Active", nullable=False)  # Active, Paused, Draft
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


class BackupJobModel(Base):
    __tablename__ = "backup_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(80), unique=True, index=True, nullable=False)
    policy_code = Column(String(80), index=True, nullable=False)
    policy_name = Column(String(150), nullable=False)
    environment = Column(String(30), default="Production", nullable=False)
    database_cluster = Column(String(100), default="pg-aurora-cluster-prod", nullable=False)
    database_name = Column(String(100), default="urban_core_prod", nullable=False)
    backup_type = Column(String(50), default="Full Backup", nullable=False)
    execution_status = Column(String(30), default="Completed", nullable=False)  # Completed, In Progress, Failed, Verified
    start_time = Column(DateTime, default=datetime.datetime.utcnow)
    completion_time = Column(DateTime, default=datetime.datetime.utcnow)
    duration_seconds = Column(Integer, default=1120)
    file_size_bytes = Column(BigInteger, default=153342000000)
    file_size_formatted = Column(String(50), default="142.8 GB")
    storage_location = Column(String(255), nullable=False)
    checksum_sha256 = Column(String(128), nullable=False)
    verification_status = Column(String(50), default="Verified (Restorable)", nullable=False)
    verification_result = Column(String(255), default="Automated sandbox checksum and transaction test passed (100% restorable)")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class RestoreJobModel(Base):
    __tablename__ = "restore_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    restore_job_name = Column(String(150), nullable=False)
    source_backup_id = Column(String(80), nullable=False)
    source_database = Column(String(100), nullable=False)
    target_environment = Column(String(50), default="Staging Recovery Sandbox", nullable=False)
    target_database = Column(String(100), nullable=False)
    restore_type = Column(String(50), default="Full Database Restore", nullable=False)  # Full Database Restore, Point-in-Time Restore, Selected Tenant Restore, Test Environment Restore
    restore_destination = Column(String(255), nullable=False)
    restore_timestamp = Column(DateTime, nullable=True)
    include_transaction_logs = Column(Boolean, default=True)
    validation_required = Column(Boolean, default=True)
    approval_authority = Column(String(100), default="Chief SRE Officer / State IT Sec", nullable=False)
    change_reference = Column(String(100), default="CR-2026-DR-092", nullable=False)
    restore_reason = Column(Text, nullable=False)
    execution_status = Column(String(30), default="Completed", nullable=False)  # Completed, In Progress, Validating, Failed
    duration_seconds = Column(Integer, default=1840)
    initiated_by = Column(String(100), default="sre.lead@urban.gov.in")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class DrillExecutionModel(Base):
    __tablename__ = "dr_drills"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    drill_name = Column(String(150), nullable=False)
    drill_code = Column(String(80), unique=True, index=True, nullable=False)
    drill_type = Column(String(50), default="Cross-Region Failover", nullable=False)  # Cross-Region Failover, Simulated Ransomware Recovery, Database Corruption Playbook, Split-Brain Isolation
    environment = Column(String(30), default="Production Simulation", nullable=False)
    primary_region = Column(String(50), default="ap-south-1 (Mumbai Primary)", nullable=False)
    secondary_region = Column(String(50), default="ap-south-2 (Hyderabad Secondary)", nullable=False)
    services_in_scope = Column(JSON, default=list)
    databases_in_scope = Column(JSON, default=list)
    planned_start_date = Column(DateTime, default=datetime.datetime.utcnow)
    planned_end_date = Column(DateTime, default=datetime.datetime.utcnow)
    expected_rpo_minutes = Column(Integer, default=5, nullable=False)
    expected_rto_minutes = Column(Integer, default=15, nullable=False)
    actual_rpo_minutes = Column(Float, default=1.8)
    actual_rto_minutes = Column(Float, default=11.4)
    recovery_success_rate_pct = Column(Float, default=100.0)
    service_availability_pct = Column(Float, default=99.92)
    data_integrity_result = Column(String(100), default="Verified: 0 transactions lost (Strict Serializability Preserved)")
    completion_status = Column(String(30), default="Passed - SLA Compliant", nullable=False)  # Passed - SLA Compliant, In Progress, Scheduled, Failed
    drill_coordinator = Column(String(100), default="Anand Verma (Lead SRE)", nullable=False)
    approval_authority = Column(String(100), default="Director General (State IT)", nullable=False)
    notification_recipients = Column(JSON, default=list)
    drill_objective = Column(Text, nullable=False)
    rollback_plan = Column(Text, nullable=False)
    findings = Column(Text, default="All critical health probes responded within 12 seconds after DNS failover. Zero data divergence.")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)








