"""Schemas for the real (not decorative) Roles & Permission Matrix - app/api/v1/iam_permissions.py."""
import datetime
from typing import List, Optional

from app.schemas.tenant import CamelModel


class OverrideDetail(CamelModel):
    role: str
    granted: bool
    reason: Optional[str] = None
    createdBy: str
    effectiveFrom: datetime.date


class PermissionRow(CamelModel):
    key: str
    group: str
    label: Optional[str] = None
    defaultRoles: List[str]
    effectiveRoles: List[str]
    overrides: List[OverrideDetail]


class PermissionMatrix(CamelModel):
    moduleCode: str
    roles: List[str]
    permissions: List[PermissionRow]


class OverrideChange(CamelModel):
    permissionKey: str
    role: str
    granted: Optional[bool] = None  # None = revert to the hardcoded default
    reason: Optional[str] = None


class BulkOverrideRequest(CamelModel):
    changes: List[OverrideChange]
    effectiveFrom: Optional[datetime.date] = None  # default: today
