import uuid
import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, delete

from app.db.session import get_read_db, get_write_db
from app.db.models import Tenant, Ward, PropertyParcel, Zone, StateTenant, TenantAuditLog
from app.schemas.tenant import ApiResponse
from app.schemas.ulb import (
    UlbTenantCreate,
    UlbTenantUpdate,
    UlbTenantResponse,
    ZoneCreate,
    ZoneResponse,
    WardCreate,
    WardResponse,
)
from app.core.auth import get_current_user, require_roles

router = APIRouter(prefix="/ulbs", tags=["ADM-T02 ULB / City Management"])

@router.get("", response_model=ApiResponse[List[UlbTenantResponse]])
async def list_ulbs(
    search: Optional[str] = Query(None),
    state_code: Optional[str] = Query(None),
    ulb_type: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    stmt = (
        select(
            Tenant,
            StateTenant.state_name.label("parent_state_name"),
            func.count(Zone.id.distinct()).label("total_zones"),
            func.count(Ward.id.distinct()).label("total_wards"),
            func.count(PropertyParcel.id.distinct()).label("total_parcels"),
        )
        .outerjoin(StateTenant, Tenant.parent_state_tenant_id == StateTenant.tenant_id)
        .outerjoin(Zone, Zone.tenant_id == Tenant.tenant_id)
        .outerjoin(Ward, Ward.tenant_id == Tenant.tenant_id)
        .outerjoin(PropertyParcel, PropertyParcel.tenant_id == Tenant.tenant_id)
        .group_by(Tenant.tenant_id, StateTenant.state_name)
        .order_by(Tenant.name)
    )

    if search:
        search_fmt = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Tenant.name).like(search_fmt),
                func.lower(Tenant.tenant_id).like(search_fmt),
                func.lower(Tenant.ulb_code).like(search_fmt),
                func.lower(Tenant.district).like(search_fmt),
            )
        )

    if state_code:
        stmt = stmt.where(Tenant.state_code == state_code.upper())

    if ulb_type:
        stmt = stmt.where(Tenant.ulb_type == ulb_type)

    if status_filter:
        stmt = stmt.where(Tenant.status == status_filter)

    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    rows = result.all()

    data: List[UlbTenantResponse] = []
    for tenant_obj, parent_state_name, total_zones, total_wards, total_parcels in rows:
        data.append(
            UlbTenantResponse(
                tenantId=tenant_obj.tenant_id,
                name=tenant_obj.name,
                parentStateTenantId=tenant_obj.parent_state_tenant_id,
                parentStateName=parent_state_name,
                stateCode=tenant_obj.state_code,
                ulbCode=tenant_obj.ulb_code or tenant_obj.tenant_id,
                tenantSlug=tenant_obj.tenant_slug or tenant_obj.tenant_id.lower(),
                ulbType=tenant_obj.ulb_type or "Municipal Corporation",
                administrativeGrade=tenant_obj.administrative_grade,
                district=tenant_obj.district,
                officialWebsite=tenant_obj.official_website,
                officialEmail=tenant_obj.official_email,
                contactPhone=tenant_obj.contact_phone,
                officeAddress=tenant_obj.office_address,
                timeZone=tenant_obj.time_zone or "Asia/Kolkata",
                primaryLanguage=tenant_obj.primary_language or "English",
                status=tenant_obj.status or "Active",
                enableZones=bool(tenant_obj.enable_zones),
                enableWards=bool(tenant_obj.enable_wards),
                effectiveDate=tenant_obj.effective_date,
                totalZones=total_zones or 0,
                totalWards=total_wards or 0,
                totalParcels=total_parcels or 0,
                createdAt=tenant_obj.created_at,
                updatedAt=tenant_obj.updated_at,
            )
        )

    return ApiResponse(data=data)

@router.get("/{tenant_id}", response_model=ApiResponse[UlbTenantResponse])
async def get_ulb(
    tenant_id: str,
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    stmt = (
        select(
            Tenant,
            StateTenant.state_name.label("parent_state_name"),
            func.count(Zone.id.distinct()).label("total_zones"),
            func.count(Ward.id.distinct()).label("total_wards"),
            func.count(PropertyParcel.id.distinct()).label("total_parcels"),
        )
        .outerjoin(StateTenant, Tenant.parent_state_tenant_id == StateTenant.tenant_id)
        .outerjoin(Zone, Zone.tenant_id == Tenant.tenant_id)
        .outerjoin(Ward, Ward.tenant_id == Tenant.tenant_id)
        .outerjoin(PropertyParcel, PropertyParcel.tenant_id == Tenant.tenant_id)
        .where(Tenant.tenant_id == tenant_id)
        .group_by(Tenant.tenant_id, StateTenant.state_name)
    )
    result = await db.execute(stmt)
    row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail=f"ULB with ID '{tenant_id}' not found")

    tenant_obj, parent_state_name, total_zones, total_wards, total_parcels = row
    return ApiResponse(
        data=UlbTenantResponse(
            tenantId=tenant_obj.tenant_id,
            name=tenant_obj.name,
            parentStateTenantId=tenant_obj.parent_state_tenant_id,
            parentStateName=parent_state_name,
            stateCode=tenant_obj.state_code,
            ulbCode=tenant_obj.ulb_code or tenant_obj.tenant_id,
            tenantSlug=tenant_obj.tenant_slug or tenant_obj.tenant_id.lower(),
            ulbType=tenant_obj.ulb_type or "Municipal Corporation",
            administrativeGrade=tenant_obj.administrative_grade,
            district=tenant_obj.district,
            officialWebsite=tenant_obj.official_website,
            officialEmail=tenant_obj.official_email,
            contactPhone=tenant_obj.contact_phone,
            officeAddress=tenant_obj.office_address,
            timeZone=tenant_obj.time_zone or "Asia/Kolkata",
            primaryLanguage=tenant_obj.primary_language or "English",
            status=tenant_obj.status or "Active",
            enableZones=bool(tenant_obj.enable_zones),
            enableWards=bool(tenant_obj.enable_wards),
            effectiveDate=tenant_obj.effective_date,
            totalZones=total_zones or 0,
            totalWards=total_wards or 0,
            totalParcels=total_parcels or 0,
            createdAt=tenant_obj.created_at,
            updatedAt=tenant_obj.updated_at,
        )
    )

@router.post("", response_model=ApiResponse[UlbTenantResponse], status_code=status.HTTP_201_CREATED)
async def create_ulb(
    payload: UlbTenantCreate,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(require_roles(["super_admin", "state_director"])),
):
    assigned_tenant_id = (payload.tenantId or payload.ulbCode or str(uuid.uuid4())[:8]).strip().upper()

    existing = await db.execute(select(Tenant).where(Tenant.tenant_id == assigned_tenant_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Tenant ID '{assigned_tenant_id}' already exists")

    # Look up parent state
    parent_state_name = None
    if payload.parentStateTenantId:
        state_res = await db.execute(
            select(StateTenant).where(StateTenant.tenant_id == payload.parentStateTenantId)
        )
        state_obj = state_res.scalar_one_or_none()
        if state_obj:
            parent_state_name = state_obj.state_name
            if not payload.stateCode:
                payload.stateCode = state_obj.state_code

    new_tenant = Tenant(
        tenant_id=assigned_tenant_id,
        name=payload.name.strip(),
        state_code=payload.stateCode.strip().upper(),
        district=payload.district.strip(),
        parent_state_tenant_id=payload.parentStateTenantId,
        ulb_code=payload.ulbCode.strip(),
        tenant_slug=payload.tenantSlug.strip().lower(),
        ulb_type=payload.ulbType,
        administrative_grade=payload.administrativeGrade,
        official_website=payload.officialWebsite,
        official_email=payload.officialEmail,
        contact_phone=payload.contactPhone,
        office_address=payload.officeAddress,
        time_zone=payload.timeZone,
        primary_language=payload.primaryLanguage,
        status=payload.status or "Draft",
        enable_zones=payload.enableZones,
        enable_wards=payload.enableWards,
        effective_date=payload.effectiveDate,
    )
    db.add(new_tenant)

    # Audit log
    user_name = user.get("preferred_username") or user.get("email") or "system"
    audit = TenantAuditLog(
        tenant_id=assigned_tenant_id,
        action="ULB_CREATED",
        performed_by=user_name,
        details=f"Created ULB {new_tenant.name} ({new_tenant.ulb_type}) under state {new_tenant.state_code}",
    )
    db.add(audit)
    await db.commit()
    await db.refresh(new_tenant)

    return ApiResponse(
        data=UlbTenantResponse(
            tenantId=new_tenant.tenant_id,
            name=new_tenant.name,
            parentStateTenantId=new_tenant.parent_state_tenant_id,
            parentStateName=parent_state_name,
            stateCode=new_tenant.state_code,
            ulbCode=new_tenant.ulb_code,
            tenantSlug=new_tenant.tenant_slug,
            ulbType=new_tenant.ulb_type,
            administrativeGrade=new_tenant.administrative_grade,
            district=new_tenant.district,
            officialWebsite=new_tenant.official_website,
            officialEmail=new_tenant.official_email,
            contactPhone=new_tenant.contact_phone,
            officeAddress=new_tenant.office_address,
            timeZone=new_tenant.time_zone,
            primaryLanguage=new_tenant.primary_language,
            status=new_tenant.status,
            enableZones=new_tenant.enable_zones,
            enableWards=new_tenant.enable_wards,
            effectiveDate=new_tenant.effective_date,
            totalZones=0,
            totalWards=0,
            totalParcels=0,
            createdAt=new_tenant.created_at,
            updatedAt=new_tenant.updated_at,
        )
    )

@router.put("/{tenant_id}", response_model=ApiResponse[UlbTenantResponse])
async def update_ulb(
    tenant_id: str,
    payload: UlbTenantUpdate,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(require_roles(["super_admin", "state_director"])),
):
    result = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
    tenant_obj = result.scalar_one_or_none()
    if not tenant_obj:
        raise HTTPException(status_code=404, detail=f"ULB with ID '{tenant_id}' not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, val in update_data.items():
        # Map camelCase model fields to snake_case column names
        column_name = {
            "parentStateTenantId": "parent_state_tenant_id",
            "stateCode": "state_code",
            "ulbCode": "ulb_code",
            "tenantSlug": "tenant_slug",
            "ulbType": "ulb_type",
            "administrativeGrade": "administrative_grade",
            "officialWebsite": "official_website",
            "officialEmail": "official_email",
            "contactPhone": "contact_phone",
            "officeAddress": "office_address",
            "timeZone": "time_zone",
            "primaryLanguage": "primary_language",
            "enableZones": "enable_zones",
            "enableWards": "enable_wards",
            "effectiveDate": "effective_date",
        }.get(key, key)
        if hasattr(tenant_obj, column_name):
            setattr(tenant_obj, column_name, val)

    tenant_obj.updated_at = datetime.datetime.utcnow()

    user_name = user.get("preferred_username") or user.get("email") or "system"
    audit = TenantAuditLog(
        tenant_id=tenant_id,
        action="ULB_UPDATED",
        performed_by=user_name,
        details=f"Updated ULB details for {tenant_obj.name}",
    )
    db.add(audit)
    await db.commit()
    await db.refresh(tenant_obj)

    # Get aggregate counts
    zones_count = (await db.execute(select(func.count(Zone.id)).where(Zone.tenant_id == tenant_id))).scalar() or 0
    wards_count = (await db.execute(select(func.count(Ward.id)).where(Ward.tenant_id == tenant_id))).scalar() or 0
    parcels_count = (await db.execute(select(func.count(PropertyParcel.id)).where(PropertyParcel.tenant_id == tenant_id))).scalar() or 0

    parent_state_name = None
    if tenant_obj.parent_state_tenant_id:
        st_res = await db.execute(select(StateTenant.state_name).where(StateTenant.tenant_id == tenant_obj.parent_state_tenant_id))
        parent_state_name = st_res.scalar()

    return ApiResponse(
        data=UlbTenantResponse(
            tenantId=tenant_obj.tenant_id,
            name=tenant_obj.name,
            parentStateTenantId=tenant_obj.parent_state_tenant_id,
            parentStateName=parent_state_name,
            stateCode=tenant_obj.state_code,
            ulbCode=tenant_obj.ulb_code,
            tenantSlug=tenant_obj.tenant_slug,
            ulbType=tenant_obj.ulb_type,
            administrativeGrade=tenant_obj.administrative_grade,
            district=tenant_obj.district,
            officialWebsite=tenant_obj.official_website,
            officialEmail=tenant_obj.official_email,
            contactPhone=tenant_obj.contact_phone,
            officeAddress=tenant_obj.office_address,
            timeZone=tenant_obj.time_zone,
            primaryLanguage=tenant_obj.primary_language,
            status=tenant_obj.status,
            enableZones=tenant_obj.enable_zones,
            enableWards=tenant_obj.enable_wards,
            effectiveDate=tenant_obj.effective_date,
            totalZones=zones_count,
            totalWards=wards_count,
            totalParcels=parcels_count,
            createdAt=tenant_obj.created_at,
            updatedAt=tenant_obj.updated_at,
        )
    )

@router.post("/{tenant_id}/activate", response_model=ApiResponse[UlbTenantResponse])
async def activate_ulb(
    tenant_id: str,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(require_roles(["super_admin", "state_director"])),
):
    result = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
    tenant_obj = result.scalar_one_or_none()
    if not tenant_obj:
        raise HTTPException(status_code=404, detail=f"ULB with ID '{tenant_id}' not found")

    tenant_obj.status = "Active"
    tenant_obj.updated_at = datetime.datetime.utcnow()

    user_name = user.get("preferred_username") or user.get("email") or "system"
    audit = TenantAuditLog(
        tenant_id=tenant_id,
        action="ULB_ACTIVATED",
        performed_by=user_name,
        details=f"Activated ULB {tenant_obj.name}",
    )
    db.add(audit)
    await db.commit()
    await db.refresh(tenant_obj)

    zones_count = (await db.execute(select(func.count(Zone.id)).where(Zone.tenant_id == tenant_id))).scalar() or 0
    wards_count = (await db.execute(select(func.count(Ward.id)).where(Ward.tenant_id == tenant_id))).scalar() or 0
    parcels_count = (await db.execute(select(func.count(PropertyParcel.id)).where(PropertyParcel.tenant_id == tenant_id))).scalar() or 0

    return ApiResponse(
        data=UlbTenantResponse(
            tenantId=tenant_obj.tenant_id,
            name=tenant_obj.name,
            parentStateTenantId=tenant_obj.parent_state_tenant_id,
            stateCode=tenant_obj.state_code,
            ulbCode=tenant_obj.ulb_code,
            tenantSlug=tenant_obj.tenant_slug,
            ulbType=tenant_obj.ulb_type,
            administrativeGrade=tenant_obj.administrative_grade,
            district=tenant_obj.district,
            officialWebsite=tenant_obj.official_website,
            officialEmail=tenant_obj.official_email,
            contactPhone=tenant_obj.contact_phone,
            officeAddress=tenant_obj.office_address,
            timeZone=tenant_obj.time_zone,
            primaryLanguage=tenant_obj.primary_language,
            status=tenant_obj.status,
            enableZones=tenant_obj.enable_zones,
            enableWards=tenant_obj.enable_wards,
            effectiveDate=tenant_obj.effective_date,
            totalZones=zones_count,
            totalWards=wards_count,
            totalParcels=parcels_count,
            createdAt=tenant_obj.created_at,
            updatedAt=tenant_obj.updated_at,
        )
    )

@router.post("/{tenant_id}/suspend", response_model=ApiResponse[UlbTenantResponse])
async def suspend_ulb(
    tenant_id: str,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(require_roles(["super_admin", "state_director"])),
):
    result = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
    tenant_obj = result.scalar_one_or_none()
    if not tenant_obj:
        raise HTTPException(status_code=404, detail=f"ULB with ID '{tenant_id}' not found")

    tenant_obj.status = "Suspended"
    tenant_obj.updated_at = datetime.datetime.utcnow()

    user_name = user.get("preferred_username") or user.get("email") or "system"
    audit = TenantAuditLog(
        tenant_id=tenant_id,
        action="ULB_SUSPENDED",
        performed_by=user_name,
        details=f"Suspended ULB {tenant_obj.name}",
    )
    db.add(audit)
    await db.commit()
    await db.refresh(tenant_obj)

    zones_count = (await db.execute(select(func.count(Zone.id)).where(Zone.tenant_id == tenant_id))).scalar() or 0
    wards_count = (await db.execute(select(func.count(Ward.id)).where(Ward.tenant_id == tenant_id))).scalar() or 0
    parcels_count = (await db.execute(select(func.count(PropertyParcel.id)).where(PropertyParcel.tenant_id == tenant_id))).scalar() or 0

    return ApiResponse(
        data=UlbTenantResponse(
            tenantId=tenant_obj.tenant_id,
            name=tenant_obj.name,
            parentStateTenantId=tenant_obj.parent_state_tenant_id,
            stateCode=tenant_obj.state_code,
            ulbCode=tenant_obj.ulb_code,
            tenantSlug=tenant_obj.tenant_slug,
            ulbType=tenant_obj.ulb_type,
            administrativeGrade=tenant_obj.administrative_grade,
            district=tenant_obj.district,
            officialWebsite=tenant_obj.official_website,
            officialEmail=tenant_obj.official_email,
            contactPhone=tenant_obj.contact_phone,
            officeAddress=tenant_obj.office_address,
            timeZone=tenant_obj.time_zone,
            primaryLanguage=tenant_obj.primary_language,
            status=tenant_obj.status,
            enableZones=tenant_obj.enable_zones,
            enableWards=tenant_obj.enable_wards,
            effectiveDate=tenant_obj.effective_date,
            totalZones=zones_count,
            totalWards=wards_count,
            totalParcels=parcels_count,
            createdAt=tenant_obj.created_at,
            updatedAt=tenant_obj.updated_at,
        )
    )

@router.delete("/{tenant_id}", response_model=ApiResponse[dict])
async def delete_ulb(
    tenant_id: str,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(require_roles(["super_admin"])),
):
    result = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
    tenant_obj = result.scalar_one_or_none()
    if not tenant_obj:
        raise HTTPException(status_code=404, detail=f"ULB with ID '{tenant_id}' not found")

    user_name = user.get("preferred_username") or user.get("email") or "system"
    audit = TenantAuditLog(
        tenant_id=tenant_id,
        action="ULB_DELETED",
        performed_by=user_name,
        details=f"Deleted ULB {tenant_obj.name} ({tenant_id})",
    )
    db.add(audit)
    await db.delete(tenant_obj)
    await db.commit()

    return ApiResponse(data={"deleted": True, "tenantId": tenant_id})

# ----------------- Zones Endpoints -----------------

@router.get("/{tenant_id}/zones", response_model=ApiResponse[List[ZoneResponse]])
async def list_zones(
    tenant_id: str,
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    stmt = (
        select(
            Zone.id,
            Zone.tenant_id,
            Zone.code,
            Zone.name,
            func.count(Ward.id.distinct()).label("total_wards"),
        )
        .outerjoin(Ward, Ward.zone_id == Zone.id)
        .where(Zone.tenant_id == tenant_id)
        .group_by(Zone.id, Zone.tenant_id, Zone.code, Zone.name)
        .order_by(Zone.code)
    )
    result = await db.execute(stmt)
    rows = result.all()

    data = [
        ZoneResponse(
            id=r.id,
            tenantId=r.tenant_id,
            code=r.code,
            name=r.name,
            totalWards=r.total_wards or 0,
        )
        for r in rows
    ]
    return ApiResponse(data=data)

@router.post("/{tenant_id}/zones", response_model=ApiResponse[ZoneResponse], status_code=status.HTTP_201_CREATED)
async def create_zone(
    tenant_id: str,
    payload: ZoneCreate,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(require_roles(["super_admin", "state_director", "revenue_officer"])),
):
    # Verify tenant exists
    t_res = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
    if not t_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"ULB '{tenant_id}' not found")

    # Check duplicate code
    existing = await db.execute(
        select(Zone).where(Zone.tenant_id == tenant_id, Zone.code == payload.code.strip())
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Zone code '{payload.code}' already exists in this ULB")

    new_zone = Zone(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        code=payload.code.strip(),
        name=payload.name.strip(),
    )
    db.add(new_zone)
    await db.commit()
    await db.refresh(new_zone)

    return ApiResponse(
        data=ZoneResponse(
            id=new_zone.id,
            tenantId=new_zone.tenant_id,
            code=new_zone.code,
            name=new_zone.name,
            totalWards=0,
        )
    )

@router.delete("/{tenant_id}/zones/{zone_id}", response_model=ApiResponse[dict])
async def delete_zone(
    tenant_id: str,
    zone_id: str,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(require_roles(["super_admin", "state_director", "revenue_officer"])),
):
    result = await db.execute(
        select(Zone).where(Zone.id == zone_id, Zone.tenant_id == tenant_id)
    )
    zone_obj = result.scalar_one_or_none()
    if not zone_obj:
        raise HTTPException(status_code=404, detail=f"Zone '{zone_id}' not found for ULB '{tenant_id}'")

    # Set wards zone_id to null before delete if any
    await db.execute(
        Ward.__table__.update().where(Ward.zone_id == zone_id).values(zone_id=None)
    )
    await db.delete(zone_obj)
    await db.commit()

    return ApiResponse(data={"deleted": True, "zoneId": zone_id})

# ----------------- Wards Endpoints -----------------

@router.get("/{tenant_id}/wards", response_model=ApiResponse[List[WardResponse]])
async def list_wards(
    tenant_id: str,
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    stmt = (
        select(
            Ward.id,
            Ward.tenant_id,
            Ward.ward_number,
            Ward.ward_code,
            Ward.ward_name,
            Ward.councilor_name,
            Ward.zone_id,
            Ward.effective_from,
            Ward.boundary_geometry,
            Zone.name.label("zone_name"),
            func.count(PropertyParcel.id.distinct()).label("total_parcels"),
        )
        .outerjoin(Zone, Zone.id == Ward.zone_id)
        .outerjoin(PropertyParcel, PropertyParcel.ward_id == Ward.id)
        .where(Ward.tenant_id == tenant_id)
        .group_by(Ward.id, Zone.name)
        .order_by(Ward.ward_number)
    )
    result = await db.execute(stmt)
    rows = result.all()

    data = [
        WardResponse(
            id=r.id,
            tenantId=r.tenant_id,
            wardNumber=r.ward_number,
            wardCode=r.ward_code,
            wardName=r.ward_name,
            councilorName=r.councilor_name,
            zoneId=r.zone_id,
            zoneName=r.zone_name,
            effectiveFrom=r.effective_from,
            boundaryGeometry=r.boundary_geometry,
            totalParcels=r.total_parcels or 0,
        )
        for r in rows
    ]
    return ApiResponse(data=data)

@router.post("/{tenant_id}/wards", response_model=ApiResponse[WardResponse], status_code=status.HTTP_201_CREATED)
async def create_ward(
    tenant_id: str,
    payload: WardCreate,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(require_roles(["super_admin", "state_director", "revenue_officer"])),
):
    # Verify tenant exists
    t_res = await db.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
    if not t_res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"ULB '{tenant_id}' not found")

    # Check duplicate ward number
    existing = await db.execute(
        select(Ward).where(Ward.tenant_id == tenant_id, Ward.ward_number == payload.wardNumber)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Ward number '{payload.wardNumber}' already exists in this ULB")

    zone_name = None
    if payload.zoneId:
        z_res = await db.execute(select(Zone).where(Zone.id == payload.zoneId, Zone.tenant_id == tenant_id))
        z_obj = z_res.scalar_one_or_none()
        if z_obj:
            zone_name = z_obj.name

    new_ward = Ward(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        ward_number=payload.wardNumber,
        ward_code=payload.wardCode or f"W-{payload.wardNumber:03d}",
        ward_name=payload.wardName.strip(),
        councilor_name=payload.councilorName,
        zone_id=payload.zoneId,
        effective_from=payload.effectiveFrom,
        boundary_geometry=payload.boundaryGeometry,
    )
    db.add(new_ward)
    await db.commit()
    await db.refresh(new_ward)

    return ApiResponse(
        data=WardResponse(
            id=new_ward.id,
            tenantId=new_ward.tenant_id,
            wardNumber=new_ward.ward_number,
            wardCode=new_ward.ward_code,
            wardName=new_ward.ward_name,
            councilorName=new_ward.councilor_name,
            zoneId=new_ward.zone_id,
            zoneName=zone_name,
            effectiveFrom=new_ward.effective_from,
            boundaryGeometry=new_ward.boundary_geometry,
            totalParcels=0,
        )
    )

@router.delete("/{tenant_id}/wards/{ward_id}", response_model=ApiResponse[dict])
async def delete_ward(
    tenant_id: str,
    ward_id: str,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(require_roles(["super_admin", "state_director", "revenue_officer"])),
):
    result = await db.execute(
        select(Ward).where(Ward.id == ward_id, Ward.tenant_id == tenant_id)
    )
    ward_obj = result.scalar_one_or_none()
    if not ward_obj:
        raise HTTPException(status_code=404, detail=f"Ward '{ward_id}' not found for ULB '{tenant_id}'")

    await db.delete(ward_obj)
    await db.commit()

    return ApiResponse(data={"deleted": True, "wardId": ward_id})
