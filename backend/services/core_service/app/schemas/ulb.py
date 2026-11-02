from typing import List, Optional, Any, Dict
import datetime
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from app.schemas.tenant import CamelModel, ApiResponse

class ZoneBase(CamelModel):
    code: str
    name: str

class ZoneCreate(ZoneBase):
    pass

class ZoneResponse(ZoneBase):
    id: str
    tenantId: str
    totalWards: Optional[int] = 0

class WardBase(CamelModel):
    wardNumber: int
    wardName: str
    wardCode: Optional[str] = None
    councilorName: Optional[str] = None
    zoneId: Optional[str] = None
    effectiveFrom: Optional[str] = None
    boundaryGeometry: Optional[Dict[str, Any]] = None

class WardCreate(WardBase):
    pass

class WardResponse(WardBase):
    id: str
    tenantId: str
    zoneName: Optional[str] = None
    totalParcels: Optional[int] = 0

class UlbTenantBase(CamelModel):
    name: str
    parentStateTenantId: Optional[str] = None
    stateCode: str = "TG"
    ulbCode: str
    tenantSlug: str
    ulbType: str = "Municipal Corporation"
    administrativeGrade: Optional[str] = None
    district: str
    officialWebsite: Optional[str] = None
    officialEmail: Optional[str] = None
    contactPhone: Optional[str] = None
    officeAddress: Optional[str] = None
    timeZone: str = "Asia/Kolkata"
    primaryLanguage: str = "English"
    status: str = "Draft"
    enableZones: bool = False
    enableWards: bool = True
    effectiveDate: Optional[str] = None

class UlbTenantCreate(UlbTenantBase):
    tenantId: Optional[str] = None

class UlbTenantUpdate(CamelModel):
    name: Optional[str] = None
    parentStateTenantId: Optional[str] = None
    stateCode: Optional[str] = None
    ulbCode: Optional[str] = None
    tenantSlug: Optional[str] = None
    ulbType: Optional[str] = None
    administrativeGrade: Optional[str] = None
    district: Optional[str] = None
    officialWebsite: Optional[str] = None
    officialEmail: Optional[str] = None
    contactPhone: Optional[str] = None
    officeAddress: Optional[str] = None
    timeZone: Optional[str] = None
    primaryLanguage: Optional[str] = None
    status: Optional[str] = None
    enableZones: Optional[bool] = None
    enableWards: Optional[bool] = None
    effectiveDate: Optional[str] = None

class UlbTenantResponse(UlbTenantBase):
    tenantId: str
    parentStateName: Optional[str] = None
    totalZones: int = 0
    totalWards: int = 0
    totalParcels: int = 0
    createdAt: Optional[datetime.datetime] = None
    updatedAt: Optional[datetime.datetime] = None
