from typing import List, Optional, Any, Dict
import datetime
from app.schemas.tenant import CamelModel, ApiResponse

class ComponentBase(CamelModel):
    name: str
    code: str
    description: str
    componentType: str = "Process"
    routePath: Optional[str] = None
    frontendPermissionKey: str
    backendApiPermissionKey: str
    supportedActions: List[str] = ["VIEW", "CREATE", "UPDATE", "DELETE", "APPROVE", "EXPORT", "MANAGE"]
    dependencies: Optional[List[str]] = []
    status: str = "Published"
    displayOrder: int = 1

class ComponentCreate(ComponentBase):
    parentModuleCode: str
    componentId: Optional[str] = None

class ComponentUpdate(CamelModel):
    name: Optional[str] = None
    description: Optional[str] = None
    componentType: Optional[str] = None
    routePath: Optional[str] = None
    frontendPermissionKey: Optional[str] = None
    backendApiPermissionKey: Optional[str] = None
    supportedActions: Optional[List[str]] = None
    dependencies: Optional[List[str]] = None
    status: Optional[str] = None
    displayOrder: Optional[int] = None

class ComponentResponse(ComponentBase):
    componentId: str
    parentModuleCode: str
    createdAt: Optional[datetime.datetime] = None
    updatedAt: Optional[datetime.datetime] = None

class ModuleBase(CamelModel):
    name: str
    code: str
    description: str
    category: str
    icon: Optional[str] = None
    displayOrder: int = 1
    moduleVersion: str = "1.0.0"
    status: str = "Published"
    dependencies: Optional[List[str]] = []
    minimumPlatformVersion: Optional[str] = None
    documentationUrl: Optional[str] = None
    effectiveFrom: Optional[str] = None

class ModuleCreate(ModuleBase):
    moduleId: Optional[str] = None

class ModuleUpdate(CamelModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    icon: Optional[str] = None
    displayOrder: Optional[int] = None
    moduleVersion: Optional[str] = None
    status: Optional[str] = None
    dependencies: Optional[List[str]] = None
    minimumPlatformVersion: Optional[str] = None
    documentationUrl: Optional[str] = None
    effectiveFrom: Optional[str] = None

class ModuleResponse(ModuleBase):
    moduleId: str
    totalComponents: Optional[int] = 0
    components: Optional[List[ComponentResponse]] = []
    createdAt: Optional[datetime.datetime] = None
    updatedAt: Optional[datetime.datetime] = None

class ModuleChangeHistoryResponse(CamelModel):
    id: str
    entityType: str
    entityCode: str
    action: str
    performedBy: str
    timestamp: datetime.datetime
    details: Optional[str] = None

class CatalogueExportPayload(CamelModel):
    exportedAt: datetime.datetime
    totalModules: int
    totalComponents: int
    modules: List[ModuleResponse]
