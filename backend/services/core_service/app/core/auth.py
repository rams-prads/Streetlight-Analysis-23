import logging
import time
from typing import Dict, List, Optional
from fastapi import Depends, HTTPException, Security, status, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import httpx
from jose import jwt, JWTError
from app.core.config import settings

logger = logging.getLogger(__name__)
security = HTTPBearer(auto_error=False)

_jwks_cache: Optional[Dict] = None
# When Keycloak is unreachable, skip retrying for this long so requests don't each wait on it.
_JWKS_RETRY_SECONDS = 300
_jwks_failed_at: Optional[float] = None

async def get_keycloak_jwks() -> Dict:
    global _jwks_cache, _jwks_failed_at
    if _jwks_cache:
        return _jwks_cache
    if _jwks_failed_at is not None and time.monotonic() - _jwks_failed_at < _JWKS_RETRY_SECONDS:
        return {}
    jwks_url = f"{settings.KEYCLOAK_URL}/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/certs"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(jwks_url)
            if resp.status_code == 200:
                _jwks_cache = resp.json()
                return _jwks_cache
    except Exception as e:
        logger.warning(f"Failed to fetch Keycloak JWKS from {jwks_url}: {e}")
    _jwks_failed_at = time.monotonic()
    return {}

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security)
) -> Dict:
    # Development bypass if no token provided in local dev mode
    if not credentials:
        if settings.ENVIRONMENT == "development":
            return {
                "preferred_username": "officer@gwmc.gov.in",
                "email": "officer@gwmc.gov.in",
                "name": "Ramesh Reddy (Officer Dev Mode)",
                "realm_access": {"roles": ["revenue_officer", "super_admin"]},
                "tenant_id": settings.DEFAULT_TENANT_ID,
                "assigned_zone": "Zone-1",
                "assigned_ward": "Ward-14"
            }
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    # 1. First check if token is signed with our internal SSO secret
    from app.core.security import decode_access_token
    internal_payload = decode_access_token(token)
    if internal_payload:
        return internal_payload

    # 2. Check Keycloak JWKS
    jwks = await get_keycloak_jwks()

    if not jwks and settings.ENVIRONMENT == "development":
        # In local dev if Keycloak not fully bootstrapped, allow token parse without key verification
        try:
            unverified_claims = jwt.get_unverified_claims(token)
            return unverified_claims
        except Exception:
            return {
                "preferred_username": "dev_user",
                "realm_access": {"roles": ["revenue_officer", "super_admin"]},
                "tenant_id": settings.DEFAULT_TENANT_ID
            }

    try:
        unverified_header = jwt.get_unverified_header(token)
        rsa_key = {}
        for key in jwks.get("keys", []):
            if key["kid"] == unverified_header.get("kid"):
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key.get("use"),
                    "n": key["n"],
                    "e": key["e"]
                }
                break

        if rsa_key:
            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=["RS256"],
                audience=settings.KEYCLOAK_CLIENT_ID,
                options={"verify_aud": False}
            )
            return payload
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unable to find appropriate signing key"
            )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )

def require_roles(allowed_roles: List[str]):
    async def role_checker(user: Dict = Depends(get_current_user)) -> Dict:
        user_roles = user.get("realm_access", {}).get("roles", [])
        if any(role in user_roles for role in allowed_roles) or "super_admin" in user_roles:
            return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Operation requires one of the following roles: {allowed_roles}"
        )
    return role_checker

async def get_current_tenant(
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-ID"),
    user: Dict = Depends(get_current_user)
) -> str:
    """
    Multi-tenant SaaS Context Resolver:
    1. HTTP Header 'X-Tenant-ID' (allows switching tenant context in SaaS console)
    2. Tenant ID embedded in authenticated JWT / user token
    3. Fallback to DEFAULT_TENANT_ID
    """
    if x_tenant_id and x_tenant_id.strip():
        resolved = x_tenant_id.strip().upper()
        if user:
            user["tenant_id"] = resolved
        return resolved
    if user and user.get("tenant_id"):
        return str(user["tenant_id"]).strip().upper()
    return settings.DEFAULT_TENANT_ID

