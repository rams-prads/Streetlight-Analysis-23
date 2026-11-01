import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_

from app.db.session import get_read_db, get_write_db
from app.db.models import Tenant, Ward, PropertyParcel, Zone, StateTenant, TenantAuditLog, State, District, City
from app.schemas.tenant import (
    ApiResponse,
    TenantResponse, TenantCreate, TenantSummary,
    StateTenantCreate, StateTenantUpdate, StateTenantResponse, TenantAuditLogResponse,
    MasterStateResponse, DistrictResponse, CityResponse
)
from app.core.auth import get_current_user, get_current_tenant, require_roles
from app.core.redis import redis_client

router = APIRouter(prefix="/tenants", tags=["SaaS Tenant Management"])

@router.get("", response_model=List[TenantResponse])
async def list_tenants(
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user)
):
    """List all registered tenants (ULBs / Municipal Corporations)"""
    stmt = (
        select(
            Tenant.tenant_id,
            Tenant.name,
            Tenant.state_code,
            Tenant.district,
            Tenant.created_at,
            func.count(PropertyParcel.id.distinct()).label("total_parcels"),
            func.count(Ward.id.distinct()).label("total_wards")
        )
        .outerjoin(PropertyParcel, PropertyParcel.tenant_id == Tenant.tenant_id)
        .outerjoin(Ward, Ward.tenant_id == Tenant.tenant_id)
    )
    if search:
        s = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Tenant.name).like(s),
                func.lower(Tenant.state_code).like(s),
                func.lower(Tenant.district).like(s)
            )
        )
    stmt = (
        stmt.group_by(Tenant.tenant_id, Tenant.name, Tenant.state_code, Tenant.district, Tenant.created_at)
        .order_by(Tenant.name)
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    return [
        TenantResponse(
            tenantId=r.tenant_id,
            name=r.name,
            stateCode=r.state_code,
            district=r.district,
            createdAt=r.created_at,
            totalParcels=r.total_parcels,
            totalWards=r.total_wards
        )
        for r in rows
    ]

@router.get("/current", response_model=TenantResponse)
async def get_active_tenant(
    tenant_id: str = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user)
):
    """Retrieve details and metrics of currently active tenant context"""
    tenant = await db.scalar(select(Tenant).where(Tenant.tenant_id == tenant_id))
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant '{tenant_id}' not found"
        )

    parcels_count = await db.scalar(
        select(func.count(PropertyParcel.id)).where(PropertyParcel.tenant_id == tenant_id)
    ) or 0
    wards_count = await db.scalar(
        select(func.count(Ward.id)).where(Ward.tenant_id == tenant_id)
    ) or 0

    return TenantResponse(
        tenantId=tenant.tenant_id,
        name=tenant.name,
        stateCode=tenant.state_code,
        district=tenant.district,
        createdAt=tenant.created_at,
        totalParcels=parcels_count,
        totalWards=wards_count
    )

@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    payload: TenantCreate,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(get_current_user)
):
    """Provision a new SaaS tenant (ULB / Municipality)"""
    norm_id = payload.tenantId.strip().upper()
    existing = await db.scalar(select(Tenant).where(Tenant.tenant_id == norm_id))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant with ID '{norm_id}' already exists"
        )

    tenant = Tenant(
        tenant_id=norm_id,
        name=payload.name.strip(),
        state_code=payload.stateCode.strip().upper(),
        district=payload.district.strip()
    )
    db.add(tenant)
    await db.flush()

    # Automatically provision default Zone-1 and Ward-1 for new tenant
    default_zone = Zone(
        tenant_id=norm_id,
        code="ZONE-1",
        name=f"{payload.name} Central Zone"
    )
    db.add(default_zone)
    await db.flush()

    default_ward = Ward(
        tenant_id=norm_id,
        zone_id=default_zone.id,
        ward_number=1,
        ward_name="Ward 1 (Headquarters)",
        councilor_name="Elected Representative"
    )
    db.add(default_ward)
    await db.commit()
    await db.refresh(tenant)

    return TenantResponse(
        tenantId=tenant.tenant_id,
        name=tenant.name,
        stateCode=tenant.state_code,
        district=tenant.district,
        createdAt=tenant.created_at,
        totalParcels=0,
        totalWards=1
    )

# -------------------------------------------------------------
# Master Indian States & UTs Catalogue
# -------------------------------------------------------------

MASTER_INDIAN_STATES = [
    {"code": "AP", "name": "Andhra Pradesh", "officialName": "Government of Andhra Pradesh (MA&UD)", "defaultSlug": "andhra-pradesh", "primaryLanguage": "English", "additionalLanguages": ["Telugu", "Urdu"], "zone": "South"},
    {"code": "AR", "name": "Arunachal Pradesh", "officialName": "Government of Arunachal Pradesh (UD)", "defaultSlug": "arunachal-pradesh", "primaryLanguage": "English", "additionalLanguages": ["Hindi"], "zone": "North East"},
    {"code": "AS", "name": "Assam", "officialName": "Government of Assam (UDD)", "defaultSlug": "assam", "primaryLanguage": "English", "additionalLanguages": ["Assamese", "Bengali", "Bodo"], "zone": "North East"},
    {"code": "BR", "name": "Bihar", "officialName": "Urban Development & Housing Department, Bihar", "defaultSlug": "bihar", "primaryLanguage": "Hindi", "additionalLanguages": ["Urdu", "Maithili"], "zone": "East"},
    {"code": "CG", "name": "Chhattisgarh", "officialName": "Urban Administration & Development, Chhattisgarh", "defaultSlug": "chhattisgarh", "primaryLanguage": "Hindi", "additionalLanguages": ["Chhattisgarhi"], "zone": "Central"},
    {"code": "GA", "name": "Goa", "officialName": "Directorate of Municipal Administration, Goa", "defaultSlug": "goa", "primaryLanguage": "English", "additionalLanguages": ["Konkani", "Marathi"], "zone": "West"},
    {"code": "GJ", "name": "Gujarat", "officialName": "Urban Development & Urban Housing Department, Gujarat", "defaultSlug": "gujarat", "primaryLanguage": "Gujarati", "additionalLanguages": ["Hindi", "English"], "zone": "West"},
    {"code": "HR", "name": "Haryana", "officialName": "Urban Local Bodies Department, Haryana", "defaultSlug": "haryana", "primaryLanguage": "Hindi", "additionalLanguages": ["Punjabi", "English"], "zone": "North"},
    {"code": "HP", "name": "Himachal Pradesh", "officialName": "Urban Development Department, Himachal Pradesh", "defaultSlug": "himachal-pradesh", "primaryLanguage": "Hindi", "additionalLanguages": ["English"], "zone": "North"},
    {"code": "JH", "name": "Jharkhand", "officialName": "Urban Development & Housing Department, Jharkhand", "defaultSlug": "jharkhand", "primaryLanguage": "Hindi", "additionalLanguages": ["Urdu", "Bengali", "Santhali"], "zone": "East"},
    {"code": "KA", "name": "Karnataka", "officialName": "Directorate of Municipal Administration, Government of Karnataka", "defaultSlug": "karnataka", "primaryLanguage": "English", "additionalLanguages": ["Kannada", "Hindi"], "zone": "South"},
    {"code": "KL", "name": "Kerala", "officialName": "Local Self Government Department, Kerala", "defaultSlug": "kerala", "primaryLanguage": "English", "additionalLanguages": ["Malayalam"], "zone": "South"},
    {"code": "MP", "name": "Madhya Pradesh", "officialName": "Directorate of Urban Administration & Development, MP", "defaultSlug": "madhya-pradesh", "primaryLanguage": "Hindi", "additionalLanguages": ["English"], "zone": "Central"},
    {"code": "MH", "name": "Maharashtra", "officialName": "Urban Development Department, Government of Maharashtra", "defaultSlug": "maharashtra", "primaryLanguage": "English", "additionalLanguages": ["Marathi", "Hindi"], "zone": "West"},
    {"code": "MN", "name": "Manipur", "officialName": "Municipal Administration, Housing & Urban Development, Manipur", "defaultSlug": "manipur", "primaryLanguage": "English", "additionalLanguages": ["Manipuri"], "zone": "North East"},
    {"code": "ML", "name": "Meghalaya", "officialName": "Urban Affairs Department, Meghalaya", "defaultSlug": "meghalaya", "primaryLanguage": "English", "additionalLanguages": ["Khasi", "Garo"], "zone": "North East"},
    {"code": "MZ", "name": "Mizoram", "officialName": "Urban Development & Poverty Alleviation Department, Mizoram", "defaultSlug": "mizoram", "primaryLanguage": "English", "additionalLanguages": ["Mizo"], "zone": "North East"},
    {"code": "NL", "name": "Nagaland", "officialName": "Urban Development Department, Nagaland", "defaultSlug": "nagaland", "primaryLanguage": "English", "additionalLanguages": ["Hindi"], "zone": "North East"},
    {"code": "OD", "name": "Odisha", "officialName": "Housing & Urban Development Department, Odisha", "defaultSlug": "odisha", "primaryLanguage": "English", "additionalLanguages": ["Odia"], "zone": "East"},
    {"code": "PB", "name": "Punjab", "officialName": "Department of Local Government, Punjab", "defaultSlug": "punjab", "primaryLanguage": "Punjabi", "additionalLanguages": ["Hindi", "English"], "zone": "North"},
    {"code": "RJ", "name": "Rajasthan", "officialName": "Local Self Government Department, Rajasthan", "defaultSlug": "rajasthan", "primaryLanguage": "Hindi", "additionalLanguages": ["English"], "zone": "North"},
    {"code": "SK", "name": "Sikkim", "officialName": "Urban Development Department, Government of Sikkim", "defaultSlug": "sikkim", "primaryLanguage": "English", "additionalLanguages": ["Nepali", "Hindi"], "zone": "North East"},
    {"code": "TN", "name": "Tamil Nadu", "officialName": "Municipal Administration & Water Supply Department, Tamil Nadu", "defaultSlug": "tamil-nadu", "primaryLanguage": "English", "additionalLanguages": ["Tamil"], "zone": "South"},
    {"code": "TG", "name": "Telangana", "officialName": "Government of Telangana (CDMA & UDD)", "defaultSlug": "telangana", "primaryLanguage": "English", "additionalLanguages": ["Telugu", "Urdu", "Hindi"], "zone": "South"},
    {"code": "TR", "name": "Tripura", "officialName": "Urban Development Department, Government of Tripura", "defaultSlug": "tripura", "primaryLanguage": "English", "additionalLanguages": ["Bengali", "Kokborok", "Hindi"], "zone": "North East"},
    {"code": "UP", "name": "Uttar Pradesh", "officialName": "Urban Development Department, Uttar Pradesh", "defaultSlug": "uttar-pradesh", "primaryLanguage": "Hindi", "additionalLanguages": ["Urdu", "English"], "zone": "North"},
    {"code": "UK", "name": "Uttarakhand", "officialName": "Urban Development Directorate, Uttarakhand", "defaultSlug": "uttarakhand", "primaryLanguage": "Hindi", "additionalLanguages": ["Sanskrit", "English"], "zone": "North"},
    {"code": "WB", "name": "West Bengal", "officialName": "Urban Development & Municipal Affairs Department, West Bengal", "defaultSlug": "west-bengal", "primaryLanguage": "English", "additionalLanguages": ["Bengali", "Hindi", "Urdu"], "zone": "East"},
    {"code": "AN", "name": "Andaman & Nicobar", "officialName": "Andaman & Nicobar Administration (Municipal Council)", "defaultSlug": "andaman-nicobar", "primaryLanguage": "English", "additionalLanguages": ["Hindi", "Tamil", "Bengali"], "zone": "UT"},
    {"code": "CH", "name": "Chandigarh", "officialName": "Chandigarh Municipal Corporation", "defaultSlug": "chandigarh", "primaryLanguage": "English", "additionalLanguages": ["Hindi", "Punjabi"], "zone": "UT"},
    {"code": "DN", "name": "Dadra & Nagar Haveli and Daman & Diu", "officialName": "DNH & DD Municipal Council Administration", "defaultSlug": "dnh-dd", "primaryLanguage": "English", "additionalLanguages": ["Gujarati", "Hindi", "Marathi"], "zone": "UT"},
    {"code": "DL", "name": "Delhi (NCT)", "officialName": "Urban Development Department, Government of NCT of Delhi", "defaultSlug": "delhi", "primaryLanguage": "English", "additionalLanguages": ["Hindi", "Punjabi", "Urdu"], "zone": "UT"},
    {"code": "JK", "name": "Jammu & Kashmir", "officialName": "Housing & Urban Development Department, J&K", "defaultSlug": "jammu-kashmir", "primaryLanguage": "English", "additionalLanguages": ["Urdu", "Kashmiri", "Dogri", "Hindi"], "zone": "UT"},
    {"code": "LA", "name": "Ladakh", "officialName": "Administration of Union Territory of Ladakh (Urban Development)", "defaultSlug": "ladakh", "primaryLanguage": "English", "additionalLanguages": ["Ladakhi", "Hindi", "Urdu"], "zone": "UT"},
    {"code": "LD", "name": "Lakshadweep", "officialName": "Lakshadweep Administration (Urban Affairs)", "defaultSlug": "lakshadweep", "primaryLanguage": "English", "additionalLanguages": ["Malayalam"], "zone": "UT"},
    {"code": "PY", "name": "Puducherry", "officialName": "Local Administration Department, Puducherry", "defaultSlug": "puducherry", "primaryLanguage": "English", "additionalLanguages": ["Tamil", "Telugu", "Malayalam", "French"], "zone": "UT"},
]

@router.get("/master-states", response_model=ApiResponse[List[MasterStateResponse]])
async def list_master_states(db: AsyncSession = Depends(get_read_db)):
    """Canonical catalogue of all Indian States and Union Territories queried from Database"""
    stmt = select(State).order_by(State.name)
    result = await db.execute(stmt)
    db_states = result.scalars().all()
    if db_states:
        data = [
            MasterStateResponse(
                code=s.code,
                name=s.name,
                officialName=s.official_name,
                defaultSlug=s.default_slug,
                primaryLanguage=s.primary_language,
                additionalLanguages=s.additional_languages or [],
                zone=s.zone
            )
            for s in db_states
        ]
        return ApiResponse(success=True, code=2000, data=data)
    # Fallback to in-memory catalogue if DB not yet seeded
    data = [
        MasterStateResponse(
            code=s["code"],
            name=s["name"],
            officialName=s["officialName"],
            defaultSlug=s["defaultSlug"],
            primaryLanguage=s["primaryLanguage"],
            additionalLanguages=s["additionalLanguages"],
            zone=s.get("zone")
        )
        for s in sorted(MASTER_INDIAN_STATES, key=lambda x: x["name"])
    ]
    return ApiResponse(success=True, code=2000, data=data)

@router.get("/master-states/{state_code}/districts", response_model=ApiResponse[List[DistrictResponse]])
async def list_state_districts(
    state_code: str,
    db: AsyncSession = Depends(get_read_db)
):
    """Retrieve districts for a given State from database"""
    stmt = select(District).where(District.state_code == state_code.upper()).order_by(District.name)
    result = await db.execute(stmt)
    districts = result.scalars().all()
    data = [
        DistrictResponse(
            id=d.id,
            stateCode=d.state_code,
            code=d.code,
            name=d.name,
            headquarters=d.headquarters
        )
        for d in districts
    ]
    return ApiResponse(success=True, code=2000, data=data)

@router.get("/master-states/{state_code}/cities", response_model=ApiResponse[List[CityResponse]])
async def list_state_cities(
    state_code: str,
    district_id: Optional[str] = None,
    db: AsyncSession = Depends(get_read_db)
):
    """Retrieve cities/ULBs for a given State from database"""
    stmt = select(City).where(City.state_code == state_code.upper())
    if district_id:
        stmt = stmt.where(City.district_id == district_id)
    stmt = stmt.order_by(City.name)
    result = await db.execute(stmt)
    cities = result.scalars().all()
    data = [
        CityResponse(
            id=c.id,
            stateCode=c.state_code,
            districtId=c.district_id,
            name=c.name,
            ulbType=c.ulb_type,
            ulbCode=c.ulb_code
        )
        for c in cities
    ]
    return ApiResponse(success=True, code=2000, data=data)

@router.get("/districts", response_model=ApiResponse[List[DistrictResponse]])
async def list_all_districts(
    state_code: Optional[str] = None,
    db: AsyncSession = Depends(get_read_db)
):
    """Retrieve all districts from database with optional state filter"""
    stmt = select(District)
    if state_code:
        stmt = stmt.where(District.state_code == state_code.upper())
    stmt = stmt.order_by(District.name)
    result = await db.execute(stmt)
    districts = result.scalars().all()
    data = [
        DistrictResponse(
            id=d.id,
            stateCode=d.state_code,
            code=d.code,
            name=d.name,
            headquarters=d.headquarters
        )
        for d in districts
    ]
    return ApiResponse(success=True, code=2000, data=data)

@router.get("/cities", response_model=ApiResponse[List[CityResponse]])
async def list_all_cities(
    state_code: Optional[str] = None,
    district_id: Optional[str] = None,
    db: AsyncSession = Depends(get_read_db)
):
    """Retrieve all cities/ULBs from database with optional state & district filter"""
    stmt = select(City)
    if state_code:
        stmt = stmt.where(City.state_code == state_code.upper())
    if district_id:
        stmt = stmt.where(City.district_id == district_id)
    stmt = stmt.order_by(City.name)
    result = await db.execute(stmt)
    cities = result.scalars().all()
    data = [
        CityResponse(
            id=c.id,
            stateCode=c.state_code,
            districtId=c.district_id,
            name=c.name,
            ulbType=c.ulb_type,
            ulbCode=c.ulb_code
        )
        for c in cities
    ]
    return ApiResponse(success=True, code=2000, data=data)


# -------------------------------------------------------------
# ADM-T01: Level 1 Tenant Management
# -------------------------------------------------------------

@router.get("/states", response_model=ApiResponse[List[StateTenantResponse]])
async def list_state_tenants(
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user)
):
    """List all Level 1 State Tenants (State Urban Development Departments)"""
    stmt = select(StateTenant)
    if search:
        s = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(StateTenant.state_name).like(s),
                func.lower(StateTenant.state_code).like(s),
                func.lower(StateTenant.tenant_slug).like(s)
            )
        )
    stmt = stmt.order_by(StateTenant.state_name).offset(skip).limit(limit)
    result = await db.execute(stmt)
    records = result.scalars().all()
    data = [
        StateTenantResponse(
            tenantId=r.tenant_id,
            stateName=r.state_name,
            stateCode=r.state_code,
            tenantSlug=r.tenant_slug,
            status=r.status,
            country=r.country,
            timeZone=r.time_zone,
            primaryLanguage=r.primary_language,
            additionalLanguages=r.additional_languages or [],
            officialStateName=r.official_state_name,
            stateEmblemUrl=r.state_emblem_url,
            stateWebsite=r.state_website,
            administrativeEmail=r.administrative_email,
            administrativePhone=r.administrative_phone,
            address=r.address,
            effectiveDate=r.effective_date,
            notes=r.notes,
            createdAt=r.created_at,
            updatedAt=r.updated_at
        )
        for r in records
    ]
    return ApiResponse(success=True, code=2000, data=data)

@router.get("/states/audit-logs", response_model=ApiResponse[List[TenantAuditLogResponse]])
async def get_all_tenant_audit_logs(
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user)
):
    """Retrieve audit history logs across all State Tenants"""
    stmt = select(TenantAuditLog).order_by(TenantAuditLog.timestamp.desc()).limit(100)
    result = await db.execute(stmt)
    logs = result.scalars().all()
    data = [
        TenantAuditLogResponse(
            id=l.id,
            tenantId=l.tenant_id,
            action=l.action,
            performedBy=l.performed_by,
            timestamp=l.timestamp,
            details=l.details,
            ipAddress=l.ip_address
        )
        for l in logs
    ]
    return ApiResponse(success=True, code=2000, data=data)

@router.get("/states/{tenant_id}", response_model=ApiResponse[StateTenantResponse])
async def get_state_tenant(
    tenant_id: str,
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user)
):
    """Retrieve single Level 1 State Tenant by UUID or Code"""
    st = await db.scalar(
        select(StateTenant).where(
            (StateTenant.tenant_id == tenant_id) | (StateTenant.state_code == tenant_id.upper())
        )
    )
    if not st:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"State Tenant '{tenant_id}' not found"
        )
    data = StateTenantResponse(
        tenantId=st.tenant_id,
        stateName=st.state_name,
        stateCode=st.state_code,
        tenantSlug=st.tenant_slug,
        status=st.status,
        country=st.country,
        timeZone=st.time_zone,
        primaryLanguage=st.primary_language,
        additionalLanguages=st.additional_languages or [],
        officialStateName=st.official_state_name,
        stateEmblemUrl=st.state_emblem_url,
        stateWebsite=st.state_website,
        administrativeEmail=st.administrative_email,
        administrativePhone=st.administrative_phone,
        address=st.address,
        effectiveDate=st.effective_date,
        notes=st.notes,
        createdAt=st.created_at,
        updatedAt=st.updated_at
    )
    return ApiResponse(success=True, code=2000, data=data)

@router.post("/states", response_model=ApiResponse[StateTenantResponse], status_code=status.HTTP_201_CREATED)
async def create_state_tenant(
    payload: StateTenantCreate,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(require_roles(["super_admin"]))
):
    """Create or Save Draft of a new Level 1 State Tenant (Platform Admin Only)"""
    norm_code = payload.stateCode.strip().upper()
    norm_slug = payload.tenantSlug.strip().lower()

    # Rule: State code uniqueness
    existing_code = await db.scalar(select(StateTenant).where(StateTenant.state_code == norm_code))
    if existing_code:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"State Code '{norm_code}' is already registered."
        )

    # Rule: Tenant slug uniqueness
    existing_slug = await db.scalar(select(StateTenant).where(StateTenant.tenant_slug == norm_slug))
    if existing_slug:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Tenant Slug '{norm_slug}' is already taken."
        )

    # Generate immutable backend UUID
    gen_tenant_id = str(uuid.uuid4())

    status_val = payload.status if payload.status in ["Draft", "Active", "Suspended"] else "Draft"

    st = StateTenant(
        tenant_id=gen_tenant_id,
        state_name=payload.stateName.strip(),
        state_code=norm_code,
        tenant_slug=norm_slug,
        status=status_val,
        country=payload.country.strip() or "India",
        time_zone=payload.timeZone.strip() or "Asia/Kolkata",
        primary_language=payload.primaryLanguage.strip() or "English",
        additional_languages=payload.additionalLanguages or [],
        official_state_name=payload.officialStateName.strip() if payload.officialStateName else None,
        state_emblem_url=payload.stateEmblemUrl,
        state_website=payload.stateWebsite.strip() if payload.stateWebsite else None,
        administrative_email=payload.administrativeEmail.strip(),
        administrative_phone=payload.administrativePhone.strip() if payload.administrativePhone else None,
        address=payload.address.strip() if payload.address else None,
        effective_date=payload.effectiveDate,
        notes=payload.notes.strip() if payload.notes else None
    )
    db.add(st)
    await db.flush()

    action_name = "CREATED" if status_val == "Active" else "DRAFT_SAVED"
    audit = TenantAuditLog(
        tenant_id=gen_tenant_id,
        action=action_name,
        performed_by=user.get("email") or user.get("sub") or "Super Admin",
        details=f"State Tenant {payload.stateName} ({norm_code}) registered with status {status_val}.",
        ip_address="127.0.0.1"
    )
    db.add(audit)
    await db.commit()
    await db.refresh(st)

    data = StateTenantResponse(
        tenantId=st.tenant_id,
        stateName=st.state_name,
        stateCode=st.state_code,
        tenantSlug=st.tenant_slug,
        status=st.status,
        country=st.country,
        timeZone=st.time_zone,
        primaryLanguage=st.primary_language,
        additionalLanguages=st.additional_languages or [],
        officialStateName=st.official_state_name,
        stateEmblemUrl=st.state_emblem_url,
        stateWebsite=st.state_website,
        administrativeEmail=st.administrative_email,
        administrativePhone=st.administrative_phone,
        address=st.address,
        effectiveDate=st.effective_date,
        notes=st.notes,
        createdAt=st.created_at,
        updatedAt=st.updated_at
    )
    return ApiResponse(success=True, code=2000, data=data)

@router.put("/states/{tenant_id}", response_model=ApiResponse[StateTenantResponse])
async def update_state_tenant(
    tenant_id: str,
    payload: StateTenantUpdate,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(require_roles(["super_admin"]))
):
    """Update configuration for a Level 1 State Tenant"""
    st = await db.scalar(select(StateTenant).where(StateTenant.tenant_id == tenant_id))
    if not st:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="State Tenant not found")

    if payload.stateName is not None:
        st.state_name = payload.stateName.strip()
    if payload.stateCode is not None:
        norm_code = payload.stateCode.strip().upper()
        if norm_code != st.state_code:
            dup = await db.scalar(select(StateTenant).where(StateTenant.state_code == norm_code, StateTenant.tenant_id != tenant_id))
            if dup:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="State code in use")
            st.state_code = norm_code
    if payload.tenantSlug is not None:
        norm_slug = payload.tenantSlug.strip().lower()
        if norm_slug != st.tenant_slug:
            dup = await db.scalar(select(StateTenant).where(StateTenant.tenant_slug == norm_slug, StateTenant.tenant_id != tenant_id))
            if dup:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Slug in use")
            st.tenant_slug = norm_slug
    if payload.status is not None and payload.status in ["Draft", "Active", "Suspended"]:
        st.status = payload.status
    if payload.country is not None:
        st.country = payload.country
    if payload.timeZone is not None:
        st.time_zone = payload.timeZone
    if payload.primaryLanguage is not None:
        st.primary_language = payload.primaryLanguage
    if payload.additionalLanguages is not None:
        st.additional_languages = payload.additionalLanguages
    if payload.officialStateName is not None:
        st.official_state_name = payload.officialStateName
    if payload.stateEmblemUrl is not None:
        st.state_emblem_url = payload.stateEmblemUrl
    if payload.stateWebsite is not None:
        st.state_website = payload.stateWebsite
    if payload.administrativeEmail is not None:
        st.administrative_email = payload.administrativeEmail
    if payload.administrativePhone is not None:
        st.administrative_phone = payload.administrativePhone
    if payload.address is not None:
        st.address = payload.address
    if payload.effectiveDate is not None:
        st.effective_date = payload.effectiveDate
    if payload.notes is not None:
        st.notes = payload.notes

    audit = TenantAuditLog(
        tenant_id=tenant_id,
        action="UPDATED",
        performed_by=user.get("email") or "Super Admin",
        details="Configuration and administrative details updated.",
        ip_address="127.0.0.1"
    )
    db.add(audit)
    await db.commit()
    await db.refresh(st)

    data = StateTenantResponse(
        tenantId=st.tenant_id,
        stateName=st.state_name,
        stateCode=st.state_code,
        tenantSlug=st.tenant_slug,
        status=st.status,
        country=st.country,
        timeZone=st.time_zone,
        primaryLanguage=st.primary_language,
        additionalLanguages=st.additional_languages or [],
        officialStateName=st.official_state_name,
        stateEmblemUrl=st.state_emblem_url,
        stateWebsite=st.state_website,
        administrativeEmail=st.administrative_email,
        administrativePhone=st.administrative_phone,
        address=st.address,
        effectiveDate=st.effective_date,
        notes=st.notes,
        createdAt=st.created_at,
        updatedAt=st.updated_at
    )
    return ApiResponse(success=True, code=2000, data=data)

@router.post("/states/{tenant_id}/activate", response_model=ApiResponse[StateTenantResponse])
async def activate_state_tenant(
    tenant_id: str,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(require_roles(["super_admin"]))
):
    """Activate Level 1 State Tenant (Platform Admin Only)"""
    st = await db.scalar(select(StateTenant).where(StateTenant.tenant_id == tenant_id))
    if not st:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="State Tenant not found")

    st.status = "Active"
    audit = TenantAuditLog(
        tenant_id=tenant_id,
        action="ACTIVATED",
        performed_by=user.get("email") or "Super Admin",
        details=f"State Tenant {st.state_name} ({st.state_code}) transitioned to Active.",
        ip_address="127.0.0.1"
    )
    db.add(audit)
    await db.commit()
    await db.refresh(st)

    data = StateTenantResponse(
        tenantId=st.tenant_id,
        stateName=st.state_name,
        stateCode=st.state_code,
        tenantSlug=st.tenant_slug,
        status=st.status,
        country=st.country,
        timeZone=st.time_zone,
        primaryLanguage=st.primary_language,
        additionalLanguages=st.additional_languages or [],
        officialStateName=st.official_state_name,
        stateEmblemUrl=st.state_emblem_url,
        stateWebsite=st.state_website,
        administrativeEmail=st.administrative_email,
        administrativePhone=st.administrative_phone,
        address=st.address,
        effectiveDate=st.effective_date,
        notes=st.notes,
        createdAt=st.created_at,
        updatedAt=st.updated_at
    )
    return ApiResponse(success=True, code=2000, data=data)

@router.post("/states/{tenant_id}/suspend", response_model=ApiResponse[StateTenantResponse])
async def suspend_state_tenant(
    tenant_id: str,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(require_roles(["super_admin"]))
):
    """Suspend Level 1 State Tenant (Platform Admin Only)"""
    st = await db.scalar(select(StateTenant).where(StateTenant.tenant_id == tenant_id))
    if not st:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="State Tenant not found")

    st.status = "Suspended"
    audit = TenantAuditLog(
        tenant_id=tenant_id,
        action="SUSPENDED",
        performed_by=user.get("email") or "Super Admin",
        details=f"State Tenant {st.state_name} ({st.state_code}) suspended by Platform Super Admin.",
        ip_address="127.0.0.1"
    )
    db.add(audit)
    await db.commit()
    await db.refresh(st)

    data = StateTenantResponse(
        tenantId=st.tenant_id,
        stateName=st.state_name,
        stateCode=st.state_code,
        tenantSlug=st.tenant_slug,
        status=st.status,
        country=st.country,
        timeZone=st.time_zone,
        primaryLanguage=st.primary_language,
        additionalLanguages=st.additional_languages or [],
        officialStateName=st.official_state_name,
        stateEmblemUrl=st.state_emblem_url,
        stateWebsite=st.state_website,
        administrativeEmail=st.administrative_email,
        administrativePhone=st.administrative_phone,
        address=st.address,
        effectiveDate=st.effective_date,
        notes=st.notes,
        createdAt=st.created_at,
        updatedAt=st.updated_at
    )
    return ApiResponse(success=True, code=2000, data=data)

@router.delete("/states/{tenant_id}", response_model=ApiResponse[dict])
async def delete_state_tenant(
    tenant_id: str,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(require_roles(["super_admin"]))
):
    """Delete Level 1 State Tenant (Platform Admin Only)"""
    st = await db.scalar(select(StateTenant).where(StateTenant.tenant_id == tenant_id))
    if not st:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="State Tenant not found")

    state_name = st.state_name
    state_code = st.state_code

    audit = TenantAuditLog(
        tenant_id=tenant_id,
        action="DELETED",
        performed_by=user.get("email") or "Super Admin",
        details=f"State Tenant {state_name} ({state_code}) permanently removed by Platform Super Admin.",
        ip_address="127.0.0.1"
    )
    db.add(audit)
    await db.delete(st)
    await db.commit()

    return ApiResponse(
        success=True,
        code=2000,
        data={"message": f"State Tenant '{state_name}' deleted successfully", "tenantId": tenant_id}
    )
