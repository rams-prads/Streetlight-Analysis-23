import datetime
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload

from app.core.auth import get_current_user
from app.db.session import get_db
from app.db.models import ModuleModel, ComponentModel, ModuleChangeHistory
from app.schemas.module import (
    ModuleCreate, ModuleUpdate, ModuleResponse,
    ComponentCreate, ComponentUpdate, ComponentResponse,
    ModuleChangeHistoryResponse, CatalogueExportPayload
)
from app.schemas.tenant import ApiResponse

router = APIRouter(
    prefix="/modules",
    tags=["Module Catalogue"],
    dependencies=[Depends(get_current_user)]
)

def generate_permission_keys(module_code: str, component_code: str, action: str) -> str:
    m = module_code.strip().upper()
    c = component_code.strip().upper()
    a = action.strip().upper()
    return f"{m}-{c}:{a}"

@router.get("", response_model=ApiResponse[List[ModuleResponse]])
async def list_modules(
    category: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    query = select(ModuleModel).options(selectinload(ModuleModel.components)).order_by(ModuleModel.display_order.asc(), ModuleModel.code.asc())

    if category and category != "ALL":
        query = query.where(ModuleModel.category == category)
    if status_filter and status_filter != "ALL":
        query = query.where(ModuleModel.status == status_filter)
    if search:
        s = f"%{search.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(ModuleModel.name).like(s),
                func.lower(ModuleModel.code).like(s),
                func.lower(ModuleModel.description).like(s)
            )
        )

    query = query.offset(skip).limit(limit)
    result = await db.scalars(query)
    modules = result.all()

    response_items = []
    for m in modules:
        components_list = [
            ComponentResponse(
                componentId=c.component_id,
                parentModuleCode=c.parent_module_code,
                name=c.name,
                code=c.code,
                description=c.description,
                componentType=c.component_type,
                routePath=c.route_path,
                frontendPermissionKey=c.frontend_permission_key,
                backendApiPermissionKey=c.backend_api_permission_key,
                supportedActions=c.supported_actions or [],
                dependencies=c.dependencies or [],
                status=c.status,
                displayOrder=c.display_order,
                createdAt=c.created_at,
                updatedAt=c.updated_at
            )
            for c in m.components
        ]
        response_items.append(
            ModuleResponse(
                moduleId=m.module_id,
                name=m.name,
                code=m.code,
                description=m.description,
                category=m.category,
                icon=m.icon,
                displayOrder=m.display_order,
                moduleVersion=m.module_version,
                status=m.status,
                dependencies=m.dependencies or [],
                minimumPlatformVersion=m.minimum_platform_version,
                documentationUrl=m.documentation_url,
                effectiveFrom=m.effective_from,
                totalComponents=len(components_list),
                components=components_list,
                createdAt=m.created_at,
                updatedAt=m.updated_at
            )
        )

    return ApiResponse(
        success=True,
        code=2000,
        message=f"Found {len(response_items)} modules",
        data=response_items
    )

@router.get("/audit/history", response_model=ApiResponse[List[ModuleChangeHistoryResponse]])
async def get_catalogue_history(
    entity_code: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    query = select(ModuleChangeHistory).order_by(ModuleChangeHistory.timestamp.desc())
    if entity_code:
        query = query.where(ModuleChangeHistory.entity_code == entity_code.upper())
    if search:
        s = f"%{search.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(ModuleChangeHistory.entity_code).like(s),
                func.lower(ModuleChangeHistory.action).like(s),
                func.lower(ModuleChangeHistory.performed_by).like(s)
            )
        )
    query = query.offset(skip).limit(limit)
    result = await db.scalars(query)
    logs = result.all()

    return ApiResponse(
        success=True,
        code=2000,
        message="Catalogue change history fetched",
        data=[
            ModuleChangeHistoryResponse(
                id=l.id,
                entityType=l.entity_type,
                entityCode=l.entity_code,
                action=l.action,
                performedBy=l.performed_by,
                timestamp=l.timestamp,
                details=l.details
            )
            for l in logs
        ]
    )

@router.get("/export/catalogue", response_model=ApiResponse[CatalogueExportPayload])
async def export_catalogue(db: AsyncSession = Depends(get_db)):
    query = select(ModuleModel).options(selectinload(ModuleModel.components)).order_by(ModuleModel.display_order.asc())
    result = await db.scalars(query)
    modules = result.all()

    total_comps = sum(len(m.components) for m in modules)
    exported_modules = []
    for m in modules:
        comps = [
            ComponentResponse(
                componentId=c.component_id,
                parentModuleCode=c.parent_module_code,
                name=c.name,
                code=c.code,
                description=c.description,
                componentType=c.component_type,
                routePath=c.route_path,
                frontendPermissionKey=c.frontend_permission_key,
                backendApiPermissionKey=c.backend_api_permission_key,
                supportedActions=c.supported_actions or [],
                dependencies=c.dependencies or [],
                status=c.status,
                displayOrder=c.display_order,
                createdAt=c.created_at,
                updatedAt=c.updated_at
            )
            for c in m.components
        ]
        exported_modules.append(
            ModuleResponse(
                moduleId=m.module_id,
                name=m.name,
                code=m.code,
                description=m.description,
                category=m.category,
                icon=m.icon,
                displayOrder=m.display_order,
                moduleVersion=m.module_version,
                status=m.status,
                dependencies=m.dependencies or [],
                minimumPlatformVersion=m.minimum_platform_version,
                documentationUrl=m.documentation_url,
                effectiveFrom=m.effective_from,
                totalComponents=len(comps),
                components=comps,
                createdAt=m.created_at,
                updatedAt=m.updated_at
            )
        )

    payload = CatalogueExportPayload(
        exportedAt=datetime.datetime.utcnow(),
        totalModules=len(modules),
        totalComponents=total_comps,
        modules=exported_modules
    )

    return ApiResponse(
        success=True,
        code=2000,
        message="Master catalogue exported successfully",
        data=payload
    )

@router.get("/{code}", response_model=ApiResponse[ModuleResponse])
async def get_module(code: str, db: AsyncSession = Depends(get_db)):
    query = select(ModuleModel).options(selectinload(ModuleModel.components)).where(ModuleModel.code == code.upper())
    result = await db.scalars(query)
    m = result.first()
    if not m:
        raise HTTPException(status_code=404, detail=f"Module '{code}' not found")

    comps = [
        ComponentResponse(
            componentId=c.component_id,
            parentModuleCode=c.parent_module_code,
            name=c.name,
            code=c.code,
            description=c.description,
            componentType=c.component_type,
            routePath=c.route_path,
            frontendPermissionKey=c.frontend_permission_key,
            backendApiPermissionKey=c.backend_api_permission_key,
            supportedActions=c.supported_actions or [],
            dependencies=c.dependencies or [],
            status=c.status,
            displayOrder=c.display_order,
            createdAt=c.created_at,
            updatedAt=c.updated_at
        )
        for c in m.components
    ]

    return ApiResponse(
        success=True,
        code=2000,
        message="Module details retrieved",
        data=ModuleResponse(
            moduleId=m.module_id,
            name=m.name,
            code=m.code,
            description=m.description,
            category=m.category,
            icon=m.icon,
            displayOrder=m.display_order,
            moduleVersion=m.module_version,
            status=m.status,
            dependencies=m.dependencies or [],
            minimumPlatformVersion=m.minimum_platform_version,
            documentationUrl=m.documentation_url,
            effectiveFrom=m.effective_from,
            totalComponents=len(comps),
            components=comps,
            createdAt=m.created_at,
            updatedAt=m.updated_at
        )
    )

@router.post("", response_model=ApiResponse[ModuleResponse], status_code=status.HTTP_201_CREATED)
async def create_module(payload: ModuleCreate, db: AsyncSession = Depends(get_db)):
    code_norm = payload.code.strip().upper()
    existing = await db.scalar(select(ModuleModel).where(ModuleModel.code == code_norm))
    if existing:
        raise HTTPException(status_code=400, detail=f"Module code '{code_norm}' already exists")

    module = ModuleModel(
        module_id=payload.moduleId or str(uuid.uuid4()),
        name=payload.name.strip(),
        code=code_norm,
        description=payload.description.strip(),
        category=payload.category,
        icon=payload.icon or "ri-apps-2-line",
        display_order=payload.displayOrder,
        module_version=payload.moduleVersion or "1.0.0",
        status=payload.status or "Published",
        dependencies=payload.dependencies or [],
        minimum_platform_version=payload.minimumPlatformVersion,
        documentation_url=payload.documentationUrl,
        effective_from=payload.effectiveFrom or datetime.datetime.utcnow().strftime("%Y-%m-%d")
    )
    db.add(module)

    audit = ModuleChangeHistory(
        entity_type="MODULE",
        entity_code=code_norm,
        action="CREATED",
        performed_by="Platform Admin",
        details=f"Created module '{module.name}' ({module.code}) v{module.module_version} in category {module.category}"
    )
    db.add(audit)
    await db.commit()
    await db.refresh(module)

    return ApiResponse(
        success=True,
        code=2000,
        message=f"Module '{module.name}' created successfully",
        data=ModuleResponse(
            moduleId=module.module_id,
            name=module.name,
            code=module.code,
            description=module.description,
            category=module.category,
            icon=module.icon,
            displayOrder=module.display_order,
            moduleVersion=module.module_version,
            status=module.status,
            dependencies=module.dependencies or [],
            minimumPlatformVersion=module.minimum_platform_version,
            documentationUrl=module.documentation_url,
            effectiveFrom=module.effective_from,
            totalComponents=0,
            components=[],
            createdAt=module.created_at,
            updatedAt=module.updated_at
        )
    )

@router.put("/{code}", response_model=ApiResponse[ModuleResponse])
async def update_module(code: str, payload: ModuleUpdate, db: AsyncSession = Depends(get_db)):
    code_norm = code.strip().upper()
    query = select(ModuleModel).options(selectinload(ModuleModel.components)).where(ModuleModel.code == code_norm)
    m = await db.scalar(query)
    if not m:
        raise HTTPException(status_code=404, detail=f"Module '{code_norm}' not found")

    if payload.name is not None:
        m.name = payload.name.strip()
    if payload.description is not None:
        m.description = payload.description.strip()
    if payload.category is not None:
        m.category = payload.category
    if payload.icon is not None:
        m.icon = payload.icon
    if payload.displayOrder is not None:
        m.display_order = payload.displayOrder
    if payload.moduleVersion is not None:
        m.module_version = payload.moduleVersion
    if payload.status is not None:
        m.status = payload.status
    if payload.dependencies is not None:
        m.dependencies = payload.dependencies
    if payload.minimumPlatformVersion is not None:
        m.minimum_platform_version = payload.minimumPlatformVersion
    if payload.documentationUrl is not None:
        m.documentation_url = payload.documentationUrl
    if payload.effectiveFrom is not None:
        m.effective_from = payload.effectiveFrom

    audit = ModuleChangeHistory(
        entity_type="MODULE",
        entity_code=code_norm,
        action="UPDATED",
        performed_by="Platform Admin",
        details=f"Updated module '{m.name}' details (Status: {m.status}, v{m.module_version})"
    )
    db.add(audit)
    await db.commit()
    await db.refresh(m)

    comps = [
        ComponentResponse(
            componentId=c.component_id,
            parentModuleCode=c.parent_module_code,
            name=c.name,
            code=c.code,
            description=c.description,
            componentType=c.component_type,
            routePath=c.route_path,
            frontendPermissionKey=c.frontend_permission_key,
            backendApiPermissionKey=c.backend_api_permission_key,
            supportedActions=c.supported_actions or [],
            dependencies=c.dependencies or [],
            status=c.status,
            displayOrder=c.display_order,
            createdAt=c.created_at,
            updatedAt=c.updated_at
        )
        for c in m.components
    ]

    return ApiResponse(
        success=True,
        code=2000,
        message=f"Module '{m.name}' updated successfully",
        data=ModuleResponse(
            moduleId=m.module_id,
            name=m.name,
            code=m.code,
            description=m.description,
            category=m.category,
            icon=m.icon,
            displayOrder=m.display_order,
            moduleVersion=m.module_version,
            status=m.status,
            dependencies=m.dependencies or [],
            minimumPlatformVersion=m.minimum_platform_version,
            documentationUrl=m.documentation_url,
            effectiveFrom=m.effective_from,
            totalComponents=len(comps),
            components=comps,
            createdAt=m.created_at,
            updatedAt=m.updated_at
        )
    )

@router.post("/{code}/publish", response_model=ApiResponse[ModuleResponse])
async def publish_module(code: str, db: AsyncSession = Depends(get_db)):
    code_norm = code.strip().upper()
    query = select(ModuleModel).options(selectinload(ModuleModel.components)).where(ModuleModel.code == code_norm)
    m = await db.scalar(query)
    if not m:
        raise HTTPException(status_code=404, detail=f"Module '{code_norm}' not found")

    m.status = "Published"
    audit = ModuleChangeHistory(
        entity_type="MODULE",
        entity_code=code_norm,
        action="PUBLISHED",
        performed_by="Platform Admin",
        details=f"Published module '{m.name}' ({m.code}) v{m.module_version}"
    )
    db.add(audit)
    await db.commit()
    await db.refresh(m)

    comps = [
        ComponentResponse(
            componentId=c.component_id,
            parentModuleCode=c.parent_module_code,
            name=c.name,
            code=c.code,
            description=c.description,
            componentType=c.component_type,
            routePath=c.route_path,
            frontendPermissionKey=c.frontend_permission_key,
            backendApiPermissionKey=c.backend_api_permission_key,
            supportedActions=c.supported_actions or [],
            dependencies=c.dependencies or [],
            status=c.status,
            displayOrder=c.display_order,
            createdAt=c.created_at,
            updatedAt=c.updated_at
        )
        for c in m.components
    ]

    return ApiResponse(
        success=True,
        code=2000,
        message=f"Module '{m.name}' published successfully",
        data=ModuleResponse(
            moduleId=m.module_id,
            name=m.name,
            code=m.code,
            description=m.description,
            category=m.category,
            icon=m.icon,
            displayOrder=m.display_order,
            moduleVersion=m.module_version,
            status=m.status,
            dependencies=m.dependencies or [],
            minimumPlatformVersion=m.minimum_platform_version,
            documentationUrl=m.documentation_url,
            effectiveFrom=m.effective_from,
            totalComponents=len(comps),
            components=comps,
            createdAt=m.created_at,
            updatedAt=m.updated_at
        )
    )

@router.post("/{code}/deprecate", response_model=ApiResponse[ModuleResponse])
async def deprecate_module(code: str, db: AsyncSession = Depends(get_db)):
    code_norm = code.strip().upper()
    query = select(ModuleModel).options(selectinload(ModuleModel.components)).where(ModuleModel.code == code_norm)
    m = await db.scalar(query)
    if not m:
        raise HTTPException(status_code=404, detail=f"Module '{code_norm}' not found")

    m.status = "Deprecated"
    audit = ModuleChangeHistory(
        entity_type="MODULE",
        entity_code=code_norm,
        action="DEPRECATED",
        performed_by="Platform Admin",
        details=f"Deprecated module '{m.name}' ({m.code}) - existing subscriptions remain traceable"
    )
    db.add(audit)
    await db.commit()
    await db.refresh(m)

    comps = [
        ComponentResponse(
            componentId=c.component_id,
            parentModuleCode=c.parent_module_code,
            name=c.name,
            code=c.code,
            description=c.description,
            componentType=c.component_type,
            routePath=c.route_path,
            frontendPermissionKey=c.frontend_permission_key,
            backendApiPermissionKey=c.backend_api_permission_key,
            supportedActions=c.supported_actions or [],
            dependencies=c.dependencies or [],
            status=c.status,
            displayOrder=c.display_order,
            createdAt=c.created_at,
            updatedAt=c.updated_at
        )
        for c in m.components
    ]

    return ApiResponse(
        success=True,
        code=2000,
        message=f"Module '{m.name}' is now marked as Deprecated",
        data=ModuleResponse(
            moduleId=m.module_id,
            name=m.name,
            code=m.code,
            description=m.description,
            category=m.category,
            icon=m.icon,
            displayOrder=m.display_order,
            moduleVersion=m.module_version,
            status=m.status,
            dependencies=m.dependencies or [],
            minimumPlatformVersion=m.minimum_platform_version,
            documentationUrl=m.documentation_url,
            effectiveFrom=m.effective_from,
            totalComponents=len(comps),
            components=comps,
            createdAt=m.created_at,
            updatedAt=m.updated_at
        )
    )

# ----------------- Components Endpoints -----------------

@router.get("/components/all", response_model=ApiResponse[List[ComponentResponse]])
async def list_all_components(
    parent_module: Optional[str] = Query(None, alias="parentModule"),
    component_type: Optional[str] = Query(None, alias="type"),
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    query = select(ComponentModel).order_by(ComponentModel.parent_module_code.asc(), ComponentModel.display_order.asc())

    if parent_module and parent_module != "ALL":
        query = query.where(ComponentModel.parent_module_code == parent_module.upper())
    if component_type and component_type != "ALL":
        query = query.where(ComponentModel.component_type == component_type)
    if status_filter and status_filter != "ALL":
        query = query.where(ComponentModel.status == status_filter)
    if search:
        s = f"%{search.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(ComponentModel.name).like(s),
                func.lower(ComponentModel.code).like(s),
                func.lower(ComponentModel.frontend_permission_key).like(s),
                func.lower(ComponentModel.description).like(s)
            )
        )

    query = query.offset(skip).limit(limit)
    result = await db.scalars(query)
    comps = result.all()

    return ApiResponse(
        success=True,
        code=2000,
        message=f"Found {len(comps)} components",
        data=[
            ComponentResponse(
                componentId=c.component_id,
                parentModuleCode=c.parent_module_code,
                name=c.name,
                code=c.code,
                description=c.description,
                componentType=c.component_type,
                routePath=c.route_path,
                frontendPermissionKey=c.frontend_permission_key,
                backendApiPermissionKey=c.backend_api_permission_key,
                supportedActions=c.supported_actions or [],
                dependencies=c.dependencies or [],
                status=c.status,
                displayOrder=c.display_order,
                createdAt=c.created_at,
                updatedAt=c.updated_at
            )
            for c in comps
        ]
    )

@router.post("/components", response_model=ApiResponse[ComponentResponse], status_code=status.HTTP_201_CREATED)
async def create_component(payload: ComponentCreate, db: AsyncSession = Depends(get_db)):
    mod_code = payload.parentModuleCode.strip().upper()
    comp_code = payload.code.strip().upper()

    # Validate parent module exists
    parent = await db.scalar(select(ModuleModel).where(ModuleModel.code == mod_code))
    if not parent:
        raise HTTPException(status_code=400, detail=f"Parent module '{mod_code}' does not exist")

    # Validate unique code
    existing = await db.scalar(select(ComponentModel).where(ComponentModel.code == comp_code))
    if existing:
        raise HTTPException(status_code=400, detail=f"Component code '{comp_code}' already exists")

    # Validate/auto-generate permission key format: {MODULE}-{COMPONENT}:{ACTION}
    actions = payload.supportedActions or ["VIEW"]
    primary_action = actions[0] if actions else "VIEW"
    fe_key = payload.frontendPermissionKey or f"{comp_code}:{primary_action}"
    be_key = payload.backendApiPermissionKey or f"{mod_code}:{comp_code}:EXECUTE"

    comp = ComponentModel(
        component_id=payload.componentId or str(uuid.uuid4()),
        parent_module_code=mod_code,
        name=payload.name.strip(),
        code=comp_code,
        description=payload.description.strip(),
        component_type=payload.componentType or "Process",
        route_path=payload.routePath,
        frontend_permission_key=fe_key,
        backend_api_permission_key=be_key,
        supported_actions=actions,
        dependencies=payload.dependencies or [],
        status=payload.status or "Published",
        display_order=payload.displayOrder
    )
    db.add(comp)

    audit = ModuleChangeHistory(
        entity_type="COMPONENT",
        entity_code=comp_code,
        action="CREATED",
        performed_by="Platform Admin",
        details=f"Created component '{comp.name}' ({comp_code}) under module {mod_code} with actions {actions}"
    )
    db.add(audit)
    await db.commit()
    await db.refresh(comp)

    return ApiResponse(
        success=True,
        code=2000,
        message=f"Component '{comp.name}' created successfully",
        data=ComponentResponse(
            componentId=comp.component_id,
            parentModuleCode=comp.parent_module_code,
            name=comp.name,
            code=comp.code,
            description=comp.description,
            componentType=comp.component_type,
            routePath=comp.route_path,
            frontendPermissionKey=comp.frontend_permission_key,
            backendApiPermissionKey=comp.backend_api_permission_key,
            supportedActions=comp.supported_actions or [],
            dependencies=comp.dependencies or [],
            status=comp.status,
            displayOrder=comp.display_order,
            createdAt=comp.created_at,
            updatedAt=comp.updated_at
        )
    )

@router.put("/components/{code}", response_model=ApiResponse[ComponentResponse])
async def update_component(code: str, payload: ComponentUpdate, db: AsyncSession = Depends(get_db)):
    comp_code = code.strip().upper()
    comp = await db.scalar(select(ComponentModel).where(ComponentModel.code == comp_code))
    if not comp:
        raise HTTPException(status_code=404, detail=f"Component '{comp_code}' not found")

    if payload.name is not None:
        comp.name = payload.name.strip()
    if payload.description is not None:
        comp.description = payload.description.strip()
    if payload.componentType is not None:
        comp.component_type = payload.componentType
    if payload.routePath is not None:
        comp.route_path = payload.routePath
    if payload.frontendPermissionKey is not None:
        comp.frontend_permission_key = payload.frontendPermissionKey
    if payload.backendApiPermissionKey is not None:
        comp.backend_api_permission_key = payload.backendApiPermissionKey
    if payload.supportedActions is not None:
        comp.supported_actions = payload.supportedActions
    if payload.dependencies is not None:
        comp.dependencies = payload.dependencies
    if payload.status is not None:
        comp.status = payload.status
    if payload.displayOrder is not None:
        comp.display_order = payload.displayOrder

    audit = ModuleChangeHistory(
        entity_type="COMPONENT",
        entity_code=comp_code,
        action="UPDATED",
        performed_by="Platform Admin",
        details=f"Updated component '{comp.name}' ({comp_code})"
    )
    db.add(audit)
    await db.commit()
    await db.refresh(comp)

    return ApiResponse(
        success=True,
        code=2000,
        message=f"Component '{comp.name}' updated",
        data=ComponentResponse(
            componentId=comp.component_id,
            parentModuleCode=comp.parent_module_code,
            name=comp.name,
            code=comp.code,
            description=comp.description,
            componentType=comp.component_type,
            routePath=comp.route_path,
            frontendPermissionKey=comp.frontend_permission_key,
            backendApiPermissionKey=comp.backend_api_permission_key,
            supportedActions=comp.supported_actions or [],
            dependencies=comp.dependencies or [],
            status=comp.status,
            displayOrder=comp.display_order,
            createdAt=comp.created_at,
            updatedAt=comp.updated_at
        )
    )

@router.post("/components/{code}/deprecate", response_model=ApiResponse[ComponentResponse])
async def deprecate_component(code: str, db: AsyncSession = Depends(get_db)):
    comp_code = code.strip().upper()
    comp = await db.scalar(select(ComponentModel).where(ComponentModel.code == comp_code))
    if not comp:
        raise HTTPException(status_code=404, detail=f"Component '{comp_code}' not found")

    comp.status = "Deprecated"
    audit = ModuleChangeHistory(
        entity_type="COMPONENT",
        entity_code=comp_code,
        action="DEPRECATED",
        performed_by="Platform Admin",
        details=f"Deprecated component '{comp.name}' ({comp_code}) - retained for role/audit immutability"
    )
    db.add(audit)
    await db.commit()
    await db.refresh(comp)

    return ApiResponse(
        success=True,
        code=2000,
        message=f"Component '{comp.name}' is now Deprecated",
        data=ComponentResponse(
            componentId=comp.component_id,
            parentModuleCode=comp.parent_module_code,
            name=comp.name,
            code=comp.code,
            description=comp.description,
            componentType=comp.component_type,
            routePath=comp.route_path,
            frontendPermissionKey=comp.frontend_permission_key,
            backendApiPermissionKey=comp.backend_api_permission_key,
            supportedActions=comp.supported_actions or [],
            dependencies=comp.dependencies or [],
            status=comp.status,
            displayOrder=comp.display_order,
            createdAt=comp.created_at,
            updatedAt=comp.updated_at
        )
    )
