"""The real (not decorative) Roles & Permission Matrix: introspects each module's own PERMISSIONS dict instead of
hand-duplicating it, and lets a super admin grant or revoke a role's access to one permission key - backed by
app/db/models.py::PermissionOverride (app/core/permission_overrides.py), with zero behaviour change until an
override is actually written. Only PTX and Water have a real backend today; add one tuple to _MODULES once a
third module does.
"""
import datetime
from typing import Callable, Dict, List, Set, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.ptx import common as ptx_common
from app.api.v1.water import common as water_common
from app.core.auth import get_current_tenant, get_current_user
from app.core.permission_overrides import invalidate_overrides, list_overrides
from app.db.models import PermissionOverride
from app.db.session import get_read_db, get_write_db
from app.schemas.iam_permissions import BulkOverrideRequest, OverrideDetail, PermissionMatrix, PermissionRow

from .iam_permissions_labels import PERMISSION_LABELS

router = APIRouter(prefix="/iam/permissions", tags=["Identity & Access Management"])

_MODULES: Dict[str, Tuple[Callable[[], Dict[str, Set[str]]], Callable[[], Set[str]], Set[str]]] = {
    "PTX": (ptx_common.permission_catalog, ptx_common.role_catalog, ptx_common.ADMIN),
    "WTR": (water_common.permission_catalog, water_common.role_catalog, water_common.ADMIN),
}


async def require_super_admin(user: Dict = Depends(get_current_user)) -> str:
    """Only a platform administrator may view or change what every role can do - never a module's own officer."""
    roles = set(user.get("realm_access", {}).get("roles", []) or [])
    if user.get("role"):
        roles.add(user["role"])
    if not (roles & {"super_admin", "system_admin"}):
        raise HTTPException(status_code=403, detail="Only a platform administrator may manage permissions.")
    return user.get("preferred_username") or user.get("email") or user.get("sub") or "unknown"


def _module(module_code: str):
    entry = _MODULES.get(module_code.upper())
    if entry is None:
        raise HTTPException(status_code=404, detail=f"'{module_code}' has no real backend yet.")
    return entry


async def _build_matrix(db: AsyncSession, tenant_id: str, module_code: str) -> PermissionMatrix:
    module_code = module_code.upper()
    permission_catalog, role_catalog, admin_roles = _module(module_code)
    defaults = permission_catalog()
    overrides_by_key: Dict[str, List[PermissionOverride]] = {}
    for row in await list_overrides(db, tenant_id, module_code):
        overrides_by_key.setdefault(row.permission_key, []).append(row)
    labels = PERMISSION_LABELS.get(module_code, {})

    permissions = []
    for key in sorted(defaults):
        default_roles = defaults[key]
        effective = set(default_roles)
        for row in overrides_by_key.get(key, []):
            if row.granted:
                effective.add(row.role)
            else:
                effective.discard(row.role)
        effective |= admin_roles  # the platform admin bypass is absolute, regardless of any override
        permissions.append(PermissionRow(
            key=key,
            group=key.split(".")[0],
            label=labels.get(key),
            defaultRoles=sorted(default_roles),
            effectiveRoles=sorted(effective),
            overrides=[OverrideDetail(role=r.role, granted=r.granted, reason=r.reason, createdBy=r.created_by,
                                      effectiveFrom=r.effective_from) for r in overrides_by_key.get(key, [])],
        ))
    return PermissionMatrix(moduleCode=module_code, roles=sorted(role_catalog()), permissions=permissions)


@router.get("/{module_code}/matrix", response_model=PermissionMatrix)
async def get_matrix(module_code: str, _admin: str = Depends(require_super_admin),
                     tenant_id: str = Depends(get_current_tenant), db: AsyncSession = Depends(get_read_db)):
    return await _build_matrix(db, tenant_id, module_code)


@router.put("/{module_code}/overrides/bulk", response_model=PermissionMatrix)
async def save_overrides(module_code: str, payload: BulkOverrideRequest, admin: str = Depends(require_super_admin),
                         tenant_id: str = Depends(get_current_tenant), db: AsyncSession = Depends(get_write_db)):
    module_code = module_code.upper()
    permission_catalog, role_catalog, _ = _module(module_code)
    defaults = permission_catalog()
    valid_roles = role_catalog()
    if not payload.changes:
        raise HTTPException(status_code=400, detail="No changes were sent.")
    effective_from = payload.effectiveFrom or datetime.date.today()
    for change in payload.changes:
        if change.permissionKey not in defaults:
            raise HTTPException(status_code=400, detail=f"'{change.permissionKey}' is not a real permission key for {module_code}.")
        if change.role not in valid_roles:
            raise HTTPException(status_code=400, detail=f"'{change.role}' is not a role {module_code} recognises.")
        if change.role in ("super_admin", "system_admin"):
            raise HTTPException(status_code=400, detail="The platform administrator roles cannot be overridden - they always have every permission.")
        db.add(PermissionOverride(tenant_id=tenant_id, module_code=module_code, permission_key=change.permissionKey,
                                  role=change.role, granted=change.granted, reason=change.reason,
                                  created_by=admin, effective_from=effective_from))
    await db.commit()
    await invalidate_overrides(tenant_id, module_code)
    return await _build_matrix(db, tenant_id, module_code)


def all_real_roles(module_codes: List[str] = None) -> Set[str]:
    """Every role string across the given modules (default: every module with a real backend) - the
    source of truth for validating Global User Management's primaryRole/assignedRoles, so that module
    stays the only place a role string is ever guessed or duplicated."""
    codes = module_codes or list(_MODULES.keys())
    roles: Set[str] = set()
    for code in codes:
        _, role_catalog, _ = _module(code)
        roles |= role_catalog()
    return roles


@router.get("/roles")
async def list_roles(modules: str = Query(..., description="Comma-separated module codes, e.g. PTX,WTR"),
                     _admin: str = Depends(require_super_admin)):
    """Every role string across the named modules - for assigning a user's real role (Global User Management)."""
    codes = [m.strip().upper() for m in modules.split(",") if m.strip()]
    return {"roles": sorted(all_real_roles(codes))}
