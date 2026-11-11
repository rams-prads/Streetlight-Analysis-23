"""A super admin's live edits to a module's real PERMISSIONS dict (ptx/common.py, water/common.py), stored in
app/db/models.py::PermissionOverride and loaded once per request. With zero override rows ever written, every
module's .can() behaves exactly as it does today - this is purely additive.

Loaded on every request, so it is cached briefly: a tiny in-process layer first, then Redis (already wired in,
app/core/redis.py - gracefully a no-op if Redis is unreachable), then the database. Written rows invalidate both.
"""
import datetime
import time
from typing import Dict, List, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import redis_client
from app.db.models import PermissionOverride

_L1_TTL_SECONDS = 5
_REDIS_TTL_SECONDS = 60
_l1: Dict[str, Tuple[float, Dict[str, Dict[str, bool]]]] = {}


def _cache_key(tenant_id: str, module_code: str) -> str:
    return f"perm_overrides:{tenant_id}:{module_code}"


async def get_overrides(db: AsyncSession, tenant_id: str, module_code: str) -> Dict[str, Dict[str, bool]]:
    """{permission_key: {role: granted}} - today's effective decision for every (key, role) that has ever been
    overridden. A (key, role) reverted back to the default (granted=None) is left out entirely, so its absence
    here always means 'use the hardcoded PERMISSIONS default', never 'explicitly revoked'."""
    key = _cache_key(tenant_id, module_code)
    now = time.monotonic()
    cached = _l1.get(key)
    if cached is not None and now - cached[0] < _L1_TTL_SECONDS:
        return cached[1]
    from_redis = await redis_client.get(key)
    if from_redis is not None:
        _l1[key] = (now, from_redis)
        return from_redis
    overrides = await _load_from_db(db, tenant_id, module_code)
    _l1[key] = (now, overrides)
    await redis_client.set(key, overrides, expire_seconds=_REDIS_TTL_SECONDS)
    return overrides


async def _load_from_db(db: AsyncSession, tenant_id: str, module_code: str) -> Dict[str, Dict[str, bool]]:
    today = datetime.date.today()
    rows = (await db.execute(
        select(PermissionOverride.permission_key, PermissionOverride.role, PermissionOverride.granted)
        .where(PermissionOverride.tenant_id == tenant_id, PermissionOverride.module_code == module_code,
               PermissionOverride.effective_from <= today)
        .order_by(PermissionOverride.effective_from.desc(), PermissionOverride.created_at.desc())
    )).all()
    resolved: Dict[str, Dict[str, bool]] = {}
    seen = set()
    for permission_key, role, granted in rows:
        combo = (permission_key, role)
        if combo in seen:  # a later row (already seen, since we ordered newest-first) wins
            continue
        seen.add(combo)
        if granted is not None:
            resolved.setdefault(permission_key, {})[role] = granted
    return resolved


async def invalidate_overrides(tenant_id: str, module_code: str) -> None:
    """Call right after committing a write to PermissionOverride for this (tenant, module)."""
    key = _cache_key(tenant_id, module_code)
    _l1.pop(key, None)
    await redis_client.delete(key)


async def list_overrides(db: AsyncSession, tenant_id: str, module_code: str) -> List[PermissionOverride]:
    """Every currently-active override for a module, full row detail (who, why, since when) - for the admin
    matrix screen. Deliberately not cached like get_overrides(): this is an admin viewing/editing the matrix,
    not a permission check on the hot path, and it should always show the latest truth."""
    today = datetime.date.today()
    rows = (await db.execute(
        select(PermissionOverride).where(PermissionOverride.tenant_id == tenant_id, PermissionOverride.module_code == module_code,
               PermissionOverride.effective_from <= today)
        .order_by(PermissionOverride.effective_from.desc(), PermissionOverride.created_at.desc())
    )).scalars().all()
    seen = set()
    active: List[PermissionOverride] = []
    for row in rows:
        combo = (row.permission_key, row.role)
        if combo in seen:
            continue
        seen.add(combo)
        if row.granted is not None:
            active.append(row)
    return active
