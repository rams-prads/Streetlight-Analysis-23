from typing import List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.db.session import get_read_db, get_write_db
from app.db.models import User, StateTenant, Tenant, GlobalUserProfile
from app.schemas.auth import (
    SignInRequest, SignUpRequest, AuthResponse, UserProfileResponse, ModuleMetadata,
    AccessibleTenant, AccessibleUlb
)
from app.core.security import hash_password, verify_password, create_access_token, decode_access_token
from app.core.auth import get_current_user
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["Authentication & SSO"])

# Official 19 Municipal Modules Catalogue
OFFICIAL_MODULES: List[Dict] = [
    {
        "code": "PTX",
        "name": "Property Tax & Revenue Management",
        "domain": "Revenue & Billing",
        "phase": 1,
        "icon": "ptx",
        "description": "ULPIN property assessment, demand notices, online tax collection, GIS sync",
        "route": "/modules/ptx"
    },
    {
        "code": "WTR",
        "name": "Water, Sewerage & Utility Billing",
        "domain": "Revenue & Billing",
        "phase": 1,
        "icon": "wtr",
        "description": "Consumer tap connections, volumetric meter readings, water tariffs & sewerage cess",
        "route": "/modules/wtr"
    },
    {
        "code": "GRV",
        "name": "Citizen Service Desk, Grievance & RTI",
        "domain": "Citizen Engagement & Welfare",
        "phase": 1,
        "icon": "grv",
        "description": "Multi-channel grievance ticketing, SLA timers, WhatsApp/SMS alerts & RTI tracking",
        "route": "/modules/grv"
    },
    {
        "code": "FIN",
        "name": "Finance & Accounting",
        "domain": "Finance & Administration",
        "phase": 1,
        "icon": "fin",
        "description": "Double-entry municipal accounting, budget sanctions, vouchers & PFMS integration",
        "route": "/modules/fin"
    },
    {
        "code": "DMS",
        "name": "Document Management System",
        "domain": "Finance & Administration",
        "phase": 1,
        "icon": "dms",
        "description": "Central dossier repository, OCR document indexing, digital signatures & DigiLocker",
        "route": "/modules/dms"
    },
    {
        "code": "TRL",
        "name": "Trade Licence Management",
        "domain": "Revenue & Billing",
        "phase": 2,
        "icon": "trl",
        "description": "Commercial trade registrations, hazardous trade inspections, renewal & fee collection",
        "route": "/modules/trl"
    },
    {
        "code": "UCH",
        "name": "User Charges Management",
        "domain": "Revenue & Billing",
        "phase": 2,
        "icon": "uch",
        "description": "Sanitation charges, parking fees, advertisement tax, septage emptying fees",
        "route": "/modules/uch"
    },
    {
        "code": "BPM",
        "name": "Building Permission Management",
        "domain": "Planning & Regulation",
        "phase": 2,
        "icon": "bpm",
        "description": "TS-bPASS integration, architectural scrutiny, plan approvals & occupancy certificates",
        "route": "/modules/bpm"
    },
    {
        "code": "TPL",
        "name": "Town Planning",
        "domain": "Planning & Regulation",
        "phase": 2,
        "icon": "tpl",
        "description": "Master plan zoning, land pooling schemes, TDR certificates & layout approvals",
        "route": "/modules/tpl"
    },
    {
        "code": "FNC",
        "name": "Fire NOC Management",
        "domain": "Planning & Regulation",
        "phase": 2,
        "icon": "fnc",
        "description": "Provisional and final Fire NOC applications with state fire service scrutiny",
        "route": "/modules/fnc"
    },
    {
        "code": "SWM",
        "name": "Solid Waste Management",
        "domain": "Infrastructure & Field Ops",
        "phase": 3,
        "icon": "swm",
        "description": "Door-to-door RFID bin collection, weighbridge mass balance & GPS tipper tracking",
        "route": "/modules/swm"
    },
    {
        "code": "ENG",
        "name": "Engineering Project Management",
        "domain": "Infrastructure & Field Ops",
        "phase": 3,
        "icon": "eng",
        "description": "SoR estimates, e-Measurement books, contractor bills, quality checks & defect liability",
        "route": "/modules/eng"
    },
    {
        "code": "SLM",
        "name": "Street Light Management",
        "domain": "Infrastructure & Field Ops",
        "phase": 3,
        "icon": "slm",
        "description": "CCMS pole monitoring, energy audits, dark spot mapping & DISCOM reconciliation",
        "route": "/modules/slm"
    },
    {
        "code": "PRK",
        "name": "Parks & Horticulture Management",
        "domain": "Infrastructure & Field Ops",
        "phase": 3,
        "icon": "prk",
        "description": "Tree census, urban forestry, 10% green budget tracking & park maintenance",
        "route": "/modules/prk"
    },
    {
        "code": "INV",
        "name": "Inventory & Stores Management",
        "domain": "Finance & Administration",
        "phase": 3,
        "icon": "inv",
        "description": "Central stores indenting, stock replenishment, GeM procurement & auction disposal",
        "route": "/modules/inv"
    },
    {
        "code": "HRM",
        "name": "Payroll & HR Management",
        "domain": "Finance & Administration",
        "phase": 4,
        "icon": "hrm",
        "description": "Sanctioned cadre rosters, face-liveness biometric attendance & salary generation",
        "route": "/modules/hrm"
    },
    {
        "code": "MPM",
        "name": "Municipal Property Management",
        "domain": "Revenue & Billing",
        "phase": 4,
        "icon": "mpm",
        "description": "Municipal land bank register, shopping complex shop leases, e-auctions & rent demand",
        "route": "/modules/mpm"
    },
    {
        "code": "LGL",
        "name": "Legal Case Management",
        "domain": "Planning & Regulation",
        "phase": 4,
        "icon": "lgl",
        "description": "LIMBS / eCourts tracking, court stay orders, advocate appointments & counter-affidavits",
        "route": "/modules/lgl"
    },
    {
        "code": "GSC",
        "name": "Government Schemes Management",
        "domain": "Citizen Engagement & Welfare",
        "phase": 4,
        "icon": "gsc",
        "description": "PMAY-U 2.0 geo-tagged stages, PM SVANidhi loans, SBM-U & beneficiary DBT transfers",
        "route": "/modules/gsc"
    }
]

ROLE_DEFAULT_MODULES: Dict[str, str] = {
    "super_admin": ",".join([m["code"] for m in OFFICIAL_MODULES]),
    "revenue_officer": "PTX,WTR,TRL,UCH,MPM,FIN,DMS",
    "town_planner": "BPM,TPL,FNC,DMS,LGL",
    "engineering_officer": "ENG,SLM,SWM,PRK,INV,DMS",
    "citizen": "GRV,PTX,WTR,TRL,GSC,DMS"
}

@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignUpRequest, db: AsyncSession = Depends(get_write_db)):
    # Check duplicate
    existing = await db.scalar(
        select(User).where(or_(User.username == payload.username, User.email == payload.email))
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered"
        )

    # Determine assigned modules
    modules = ROLE_DEFAULT_MODULES.get(payload.role, ROLE_DEFAULT_MODULES["citizen"])

    user_tenant = (payload.tenantId or settings.DEFAULT_TENANT_ID).strip().upper()
    user = User(
        tenant_id=user_tenant,
        username=payload.username.strip(),
        email=str(payload.email).lower().strip(),
        password_hash=hash_password(payload.password),
        full_name=payload.fullName.strip(),
        role=payload.role,
        assigned_modules=modules,
        assigned_zone=payload.assignedZone,
        assigned_ward=payload.assignedWard
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Issue JWT token
    token_claims = {
        "sub": user.id,
        "preferred_username": user.username,
        "email": user.email,
        "name": user.full_name,
        "realm_access": {"roles": [user.role]},
        "tenant_id": user.tenant_id,
        "assigned_modules": user.assigned_modules.split(",")
    }
    accessToken = create_access_token(token_claims)

    userProfile = UserProfileResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        fullName=user.full_name,
        role=user.role,
        tenantId=user.tenant_id,
        assignedModules=user.assigned_modules.split(","),
        assignedZone=user.assigned_zone,
        assignedWard=user.assigned_ward
    )

    effective_tenant = user.tenant_id
    gup_rec = await db.scalar(select(GlobalUserProfile).where(GlobalUserProfile.email == user.email))
    if gup_rec:
        parts = [p.strip() for p in [gup_rec.state_tenant_id, gup_rec.ulb_tenant_id] if p and p.strip()]
        if parts:
            effective_tenant = ",".join(parts)

    accessible_tenants = await _get_accessible_tenants(db, user.role, effective_tenant)
    return AuthResponse(accessToken=accessToken, user=userProfile, accessibleTenants=accessible_tenants)

async def _get_accessible_tenants(
    db: AsyncSession, user_role: str, user_tenant_id: Optional[str]
) -> List[AccessibleTenant]:
    """
    100% database-driven resolution of Level 1 State Tenants and Level 2 child ULBs.
    No hardcoded fallbacks.
    """
    state_tenants = (await db.scalars(select(StateTenant).order_by(StateTenant.state_name))).all()
    all_ulbs = (await db.scalars(select(Tenant).order_by(Tenant.name))).all()

    ulbs_by_state: Dict[str, List[AccessibleUlb]] = {}
    for u in all_ulbs:
        st_code = (u.state_code or "").strip().upper()
        if st_code not in ulbs_by_state:
            ulbs_by_state[st_code] = []
        ulbs_by_state[st_code].append(
            AccessibleUlb(
                code=u.tenant_id,
                name=u.name,
                ulbType="Municipal Corporation",
                district=u.district,
                stateCode=st_code,
            )
        )

    accessible_tenants: List[AccessibleTenant] = []
    for st in state_tenants:
        st_code = (st.state_code or "").strip().upper()
        st_ulbs = ulbs_by_state.get(st_code, [])
        accessible_tenants.append(
            AccessibleTenant(
                stateCode=st_code,
                stateName=st.state_name,
                status=st.status,
                ulbs=st_ulbs,
            )
        )

    # Scoped filtering for non-superadmin users
    if user_role != "super_admin":
        if not user_tenant_id:
            return []
        targets = [x.strip().upper() for x in user_tenant_id.split(",") if x.strip()]
        filtered: List[AccessibleTenant] = []
        for t in accessible_tenants:
            if t.stateCode in targets:
                filtered.append(t)
            else:
                matched_ulbs = [u for u in t.ulbs if u.code.strip().upper() in targets]
                if matched_ulbs:
                    filtered.append(
                        AccessibleTenant(
                            stateCode=t.stateCode,
                            stateName=t.stateName,
                            status=t.status,
                            ulbs=matched_ulbs,
                        )
                    )
        return filtered

    return accessible_tenants

@router.post("/signin", response_model=AuthResponse)
async def signin(payload: SignInRequest, db: AsyncSession = Depends(get_write_db)):
    identifier = payload.identifier
    if not identifier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Official Email or Username is required."
        )
    user = await db.scalar(
        select(User).where(or_(User.username == identifier, User.email == identifier.lower()))
    )

    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials. Please verify your username/email and password."
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated. Contact Municipal Administrator."
        )

    # Issue SSO JWT Token
    modulesList = [m.strip() for m in user.assigned_modules.split(",") if m.strip()]
    token_claims = {
        "sub": user.id,
        "preferred_username": user.username,
        "email": user.email,
        "name": user.full_name,
        "realm_access": {"roles": [user.role]},
        "tenant_id": user.tenant_id,
        "assigned_modules": modulesList
    }
    accessToken = create_access_token(token_claims)

    userProfile = UserProfileResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        fullName=user.full_name,
        role=user.role,
        tenantId=user.tenant_id,
        assignedModules=modulesList,
        assignedZone=user.assigned_zone,
        assignedWard=user.assigned_ward
    )

    effective_tenant = user.tenant_id
    gup_rec = await db.scalar(select(GlobalUserProfile).where(GlobalUserProfile.email == user.email))
    if gup_rec:
        parts = [p.strip() for p in [gup_rec.state_tenant_id, gup_rec.ulb_tenant_id] if p and p.strip()]
        if parts:
            effective_tenant = ",".join(parts)

    accessible_tenants = await _get_accessible_tenants(db, user.role, effective_tenant)
    return AuthResponse(accessToken=accessToken, user=userProfile, accessibleTenants=accessible_tenants)

@router.get("/me", response_model=UserProfileResponse)
async def get_me(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_read_db)):
    username = user.get("preferred_username") or user.get("username")
    db_user = await db.scalar(select(User).where(User.username == username))
    
    if db_user:
        modules = [m.strip() for m in db_user.assigned_modules.split(",") if m.strip()]
        return UserProfileResponse(
            id=db_user.id,
            username=db_user.username,
            email=db_user.email,
            fullName=db_user.full_name,
            role=db_user.role,
            tenantId=db_user.tenant_id,
            assignedModules=modules,
            assignedZone=db_user.assigned_zone,
            assignedWard=db_user.assigned_ward
        )

    # Fallback to token claims
    roles = user.get("realm_access", {}).get("roles", ["citizen"])
    role = roles[0] if roles else "citizen"
    assigned = user.get("assigned_modules") or ROLE_DEFAULT_MODULES.get(role, ROLE_DEFAULT_MODULES["citizen"]).split(",")

    return UserProfileResponse(
        id="dev-user-id",
        username=user.get("preferred_username", "officer@gwmc.gov.in"),
        email=user.get("email", "officer@gwmc.gov.in"),
        fullName=user.get("name", "Ramesh Reddy"),
        role=role,
        tenantId=user.get("tenant_id", settings.DEFAULT_TENANT_ID),
        assignedModules=assigned,
        assignedZone=user.get("assigned_zone", "Zone-1"),
        assignedWard=user.get("assigned_ward", "Ward-14")
    )

@router.get("/modules", response_model=List[ModuleMetadata])
async def list_modules_for_user(user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_read_db)):
    username = user.get("preferred_username") or user.get("username")
    db_user = await db.scalar(select(User).where(User.username == username))

    allowed_set = set()
    if db_user:
        allowed_set = {m.strip() for m in db_user.assigned_modules.split(",") if m.strip()}
    else:
        roles = user.get("realm_access", {}).get("roles", [])
        if "super_admin" in roles:
            allowed_set = {m["code"] for m in OFFICIAL_MODULES}
        else:
            def_mods = ROLE_DEFAULT_MODULES.get(roles[0] if roles else "citizen", ROLE_DEFAULT_MODULES["citizen"])
            allowed_set = {m.strip() for m in def_mods.split(",") if m.strip()}

    response: List[ModuleMetadata] = []
    for mod in OFFICIAL_MODULES:
        hasAccess = mod["code"] in allowed_set or "super_admin" in user.get("realm_access", {}).get("roles", [])
        response.append(
            ModuleMetadata(
                code=mod["code"],
                name=mod["name"],
                domain=mod["domain"],
                phase=mod["phase"],
                icon=mod["icon"],
                description=mod["description"],
                hasAccess=hasAccess,
                route=mod["route"]
            )
        )
    return response
