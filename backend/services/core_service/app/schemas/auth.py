from typing import List, Optional
from pydantic import BaseModel, EmailStr, ConfigDict
from pydantic.alias_generators import to_camel

class CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )

class SignInRequest(CamelModel):
    userName: str
    password: str

    @property
    def identifier(self) -> str:
        return (self.userName or "").strip()


class SignUpRequest(CamelModel):
    username: str
    email: EmailStr
    password: str
    fullName: str
    role: str = "citizen"
    tenantId: Optional[str] = "GWMC"
    assignedZone: Optional[str] = None
    assignedWard: Optional[str] = None

class UserProfileResponse(CamelModel):
    id: str
    username: str
    email: str
    fullName: str
    role: str
    tenantId: str
    assignedModules: List[str]
    assignedZone: Optional[str] = None
    assignedWard: Optional[str] = None

class AccessibleUlb(CamelModel):
    code: str
    name: str
    ulbType: str = "Municipal Corporation"
    district: Optional[str] = None
    stateCode: str

class AccessibleTenant(CamelModel):
    stateCode: str
    stateName: str
    status: str = "Active"
    ulbs: List[AccessibleUlb] = []

class AuthResponse(CamelModel):
    accessToken: str
    tokenType: str = "bearer"
    user: UserProfileResponse
    accessibleTenants: List[AccessibleTenant] = []

class ModuleMetadata(CamelModel):
    code: str
    name: str
    domain: str
    phase: int
    icon: str
    description: str
    hasAccess: bool = False
    route: str

