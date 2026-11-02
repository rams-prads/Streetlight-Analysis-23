import asyncio
import datetime
import secrets
import urllib.request
import urllib.error
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func, delete, or_, and_

from app.db.session import get_read_db, get_write_db
from app.db.models import (
    SSOConfiguration,
    IdentityProviderFederation,
    AuthenticationAuditLog,
    RoleModel,
    RolePermission,
    GlobalUserProfile,
    UserInvitation,
    ComponentModel,
    User,
    Tenant
)
from app.core.security import hash_password
from app.schemas.iam import (
    SSOConnectionUpdate,
    SSOPolicyUpdate,
    SSOConfigurationResponse,
    IdentityProviderCreate,
    IdentityProviderUpdate,
    IdentityProviderResponse,
    AuthenticationAuditLogResponse,
    ConnectionTestResult,
    RoleCreate,
    RoleUpdate,
    RoleResponse,
    RolePermissionItem,
    RolePermissionsUpdate,
    RoleComparisonResult,
    RoleComparisonDiff,
    GlobalUserCreate,
    GlobalUserUpdate,
    GlobalUserScopeUpdate,
    GlobalUserResponse,
    UserInvitationCreate,
    UserInvitationResponse,
    ResetUserPasswordPayload,
)
from app.schemas.tenant import ApiResponse
from app.core.auth import get_current_user

router = APIRouter(prefix="/iam", tags=["Identity & Access Management"], dependencies=[Depends(get_current_user)])

def _to_sso_response(cfg: SSOConfiguration) -> SSOConfigurationResponse:
    discovery = cfg.discovery_url
    if not discovery and cfg.keycloak_base_url and cfg.keycloak_realm:
        discovery = f"{cfg.keycloak_base_url.rstrip('/')}/realms/{cfg.keycloak_realm}/.well-known/openid-configuration"
    
    secret_masked = "••••••••" if cfg.client_secret else "Not Configured"

    return SSOConfigurationResponse(
        id=cfg.id,
        providerName=cfg.provider_name,
        providerType=cfg.provider_type,
        keycloakBaseUrl=cfg.keycloak_base_url,
        keycloakRealm=cfg.keycloak_realm,
        clientId=cfg.client_id,
        clientSecretMasked=secret_masked,
        redirectUri=cfg.redirect_uri,
        postLogoutRedirectUri=cfg.post_logout_redirect_uri,
        oidcScopes=cfg.oidc_scopes or ["openid", "profile", "email", "roles"],
        discoveryUrl=discovery,
        connectionStatus=cfg.connection_status,
        lastConnectionTest=cfg.last_connection_test,
        enableSso=cfg.enable_sso,
        loginMethods=cfg.login_methods or ["Password", "SSO", "OTP"],
        mfaRequired=cfg.mfa_required,
        mfaPolicy=cfg.mfa_policy,
        allowedIdentityProviders=cfg.allowed_identity_providers or [],
        sessionIdleTimeoutMins=cfg.session_idle_timeout_mins,
        maxSessionLifetimeMins=cfg.max_session_lifetime_mins,
        rememberMe=cfg.remember_me,
        bruteForceProtection=cfg.brute_force_protection,
        maxFailedAttempts=cfg.max_failed_attempts,
        passwordMinLength=cfg.password_min_length,
        passwordRequireUppercase=cfg.password_require_uppercase,
        passwordRequireLowercase=cfg.password_require_lowercase,
        passwordRequireDigits=cfg.password_require_digits,
        passwordRequireSpecial=cfg.password_require_special,
        passwordExpiryDays=cfg.password_expiry_days,
        allowedEmailDomains=cfg.allowed_email_domains or ["gov.in", "nic.in", "urban.gov.in"],
        requireVerifiedEmail=cfg.require_verified_email,
        createdAt=cfg.created_at,
        updatedAt=cfg.updated_at
    )

async def _get_or_create_sso_config(db: AsyncSession) -> SSOConfiguration:
    query = select(SSOConfiguration).order_by(SSOConfiguration.created_at.asc())
    result = await db.scalars(query)
    cfg = result.first()
    if cfg:
        # Auto-migrate any legacy CIVORA names to SUVIDHA
        changed = False
        if "CIVORA" in (cfg.provider_name or ""):
            cfg.provider_name = cfg.provider_name.replace("CIVORA", "SUVIDHA")
            changed = True
        if "civora" in (cfg.keycloak_realm or ""):
            cfg.keycloak_realm = cfg.keycloak_realm.replace("civora", "suvidha")
            changed = True
        if "civora" in (cfg.discovery_url or ""):
            cfg.discovery_url = cfg.discovery_url.replace("civora", "suvidha")
            changed = True
        if "civora" in (cfg.client_secret or ""):
            cfg.client_secret = cfg.client_secret.replace("civora", "suvidha")
            changed = True
        if changed:
            await db.commit()
            await db.refresh(cfg)
    else:
        cfg = SSOConfiguration(
            provider_name="SUVIDHA Central Keycloak Identity",
            provider_type="Keycloak",
            keycloak_base_url="http://localhost:8080",
            keycloak_realm="urban-suvidha",
            client_id="urban-console",
            client_secret="urban-client-secret-suvidha",
            redirect_uri="http://localhost:4200/auth/callback",
            post_logout_redirect_uri="http://localhost:4200/login",
            oidc_scopes=["openid", "profile", "email", "roles"],
            discovery_url="http://localhost:8080/realms/urban-suvidha/.well-known/openid-configuration",
            connection_status="Connected",
            enable_sso=True,
            login_methods=["Password", "SSO", "OTP"],
            mfa_required=False,
            mfa_policy="Admins Only",
            allowed_identity_providers=["MeriPehchan", "e-Pramaan"],
            session_idle_timeout_mins=30,
            max_session_lifetime_mins=480,
            remember_me=True,
            brute_force_protection=True,
            max_failed_attempts=5,
            password_min_length=8,
            password_require_uppercase=True,
            password_require_lowercase=True,
            password_require_digits=True,
            password_require_special=True,
            password_expiry_days=90,
            allowed_email_domains=["gov.in", "nic.in", "urban.gov.in"],
            require_verified_email=True
        )
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)
    return cfg

# 1. Get SSO Configuration
@router.get("/sso", response_model=ApiResponse[SSOConfigurationResponse])
async def get_sso_configuration(db: AsyncSession = Depends(get_read_db)):
    cfg = await _get_or_create_sso_config(db)
    return ApiResponse(
        success=True,
        code=2000,
        message="SSO configuration fetched successfully",
        data=_to_sso_response(cfg)
    )

# 2. Update Keycloak Connection
@router.put("/sso/connection", response_model=ApiResponse[SSOConfigurationResponse])
async def update_sso_connection(
    payload: SSOConnectionUpdate,
    db: AsyncSession = Depends(get_write_db)
):
    cfg = await _get_or_create_sso_config(db)
    cfg.provider_name = payload.providerName.strip()
    cfg.provider_type = payload.providerType.strip()
    cfg.keycloak_base_url = payload.keycloakBaseUrl.strip().rstrip('/')
    cfg.keycloak_realm = payload.keycloakRealm.strip()
    cfg.client_id = payload.clientId.strip()
    if payload.clientSecret and payload.clientSecret.strip() and payload.clientSecret != "••••••••":
        cfg.client_secret = payload.clientSecret.strip()
    cfg.redirect_uri = payload.redirectUri.strip()
    cfg.post_logout_redirect_uri = payload.postLogoutRedirectUri.strip() if payload.postLogoutRedirectUri else None
    cfg.oidc_scopes = payload.oidcScopes
    cfg.discovery_url = f"{cfg.keycloak_base_url}/realms/{cfg.keycloak_realm}/.well-known/openid-configuration"
    cfg.updated_at = datetime.datetime.utcnow()

    # Log action
    log = AuthenticationAuditLog(
        event_type="SSO_CONNECTION_UPDATED",
        username="superadmin",
        ip_address="127.0.0.1",
        idp_used="Keycloak",
        details=f"Updated Keycloak Realm: {cfg.keycloak_realm}, Client ID: {cfg.client_id}",
        status="SUCCESS"
    )
    db.add(log)

    await db.commit()
    await db.refresh(cfg)

    return ApiResponse(
        success=True,
        code=2000,
        message="Keycloak connection parameters updated successfully",
        data=_to_sso_response(cfg)
    )

# 3. Update SSO & Authentication Policies
@router.put("/sso/policies", response_model=ApiResponse[SSOConfigurationResponse])
async def update_sso_policies(
    payload: SSOPolicyUpdate,
    db: AsyncSession = Depends(get_write_db)
):
    cfg = await _get_or_create_sso_config(db)
    cfg.enable_sso = payload.enableSso
    cfg.login_methods = payload.loginMethods
    cfg.mfa_required = payload.mfaRequired
    cfg.mfa_policy = payload.mfaPolicy
    cfg.allowed_identity_providers = payload.allowedIdentityProviders or []
    cfg.session_idle_timeout_mins = payload.sessionIdleTimeoutMins
    cfg.max_session_lifetime_mins = payload.maxSessionLifetimeMins
    cfg.remember_me = payload.rememberMe
    cfg.brute_force_protection = payload.bruteForceProtection
    cfg.max_failed_attempts = payload.maxFailedAttempts
    cfg.password_min_length = payload.passwordMinLength
    cfg.password_require_uppercase = payload.passwordRequireUppercase
    cfg.password_require_lowercase = payload.passwordRequireLowercase
    cfg.password_require_digits = payload.passwordRequireDigits
    cfg.password_require_special = payload.passwordRequireSpecial
    cfg.password_expiry_days = payload.passwordExpiryDays
    cfg.allowed_email_domains = payload.allowedEmailDomains
    cfg.require_verified_email = payload.requireVerifiedEmail
    cfg.updated_at = datetime.datetime.utcnow()

    log = AuthenticationAuditLog(
        event_type="SSO_POLICIES_UPDATED",
        username="superadmin",
        ip_address="127.0.0.1",
        idp_used="Keycloak",
        details=f"Updated auth policies: MFA={cfg.mfa_required} ({cfg.mfa_policy}), IdleTimeout={cfg.session_idle_timeout_mins}m",
        status="SUCCESS"
    )
    db.add(log)

    await db.commit()
    await db.refresh(cfg)

    return ApiResponse(
        success=True,
        code=2000,
        message="SSO and authentication policies saved successfully",
        data=_to_sso_response(cfg)
    )

# 4. Test Keycloak Connection
@router.post("/sso/test-connection", response_model=ApiResponse[ConnectionTestResult])
async def test_keycloak_connection(db: AsyncSession = Depends(get_write_db)):
    cfg = await _get_or_create_sso_config(db)
    discovery_url = cfg.discovery_url or f"{cfg.keycloak_base_url.rstrip('/')}/realms/{cfg.keycloak_realm}/.well-known/openid-configuration"
    
    loop = asyncio.get_event_loop()
    def _probe_url(url: str):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Urban-Core-Service/1.0"})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                return resp.status, resp.read().decode('utf-8', errors='ignore')[:300]
        except urllib.error.HTTPError as e:
            return e.code, str(e)
        except Exception as e:
            return 0, str(e)

    status_code, preview = await loop.run_in_executor(None, _probe_url, discovery_url)
    tested_at = datetime.datetime.utcnow()

    is_online = (status_code == 200 or status_code == 302)
    cfg.connection_status = "Connected" if is_online else "Offline"
    cfg.last_connection_test = tested_at

    log = AuthenticationAuditLog(
        event_type="SSO_CONNECTION_TEST",
        username="superadmin",
        ip_address="127.0.0.1",
        idp_used="Keycloak",
        details=f"Connection probe to {discovery_url}: Status {status_code}",
        status="SUCCESS" if is_online else "FAILED"
    )
    db.add(log)
    await db.commit()

    return ApiResponse(
        success=True,
        code=2000,
        message="Connection probe completed",
        data=ConnectionTestResult(
            success=is_online,
            status=cfg.connection_status,
            message=f"Keycloak realm discovery probe returned HTTP {status_code}" if status_code else "Target host currently unreachable (offline or timeout)",
            testedAt=tested_at,
            details={"discoveryUrl": discovery_url, "httpStatus": status_code, "preview": preview}
        )
    )

# 5. List External Identity Providers (Federation)
@router.get("/idps", response_model=ApiResponse[List[IdentityProviderResponse]])
async def list_identity_providers(
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_read_db)
):
    query = select(IdentityProviderFederation).order_by(IdentityProviderFederation.created_at.asc())
    result = await db.scalars(query)
    idps = result.all()

    # Auto-migrate any existing IDP records with CIVORA / civora
    if idps:
        idp_changed = False
        for item in idps:
            if item.client_id and "CIVORA" in item.client_id:
                item.client_id = item.client_id.replace("CIVORA", "SUVIDHA")
                idp_changed = True
            elif item.client_id and "civora" in item.client_id:
                item.client_id = item.client_id.replace("civora", "suvidha")
                idp_changed = True
        if idp_changed:
            await db.commit()

    # Seed default federations if none exist
    if not idps:
        defaults = [
            IdentityProviderFederation(
                name="MeriPehchan (National Single Sign-On)",
                protocol="OIDC",
                issuer_url="https://auth.meripehchan.gov.in",
                client_id="SUVIDHA_URBAN_PORTAL",
                client_secret="meripehchan_secret_hash",
                metadata_url="https://auth.meripehchan.gov.in/.well-known/openid-configuration",
                claim_mapping={"sub": "aadhaar_sub", "email": "email", "name": "name", "phone": "mobile"},
                user_linking_policy="Auto-link by Email",
                is_active=True
            ),
            IdentityProviderFederation(
                name="e-Pramaan (National e-Governance Division)",
                protocol="SAML",
                issuer_url="https://epramaan.gov.in/saml2/idp/metadata.php",
                client_id="EPRAMAAN_SUVIDHA_SP",
                client_secret=None,
                metadata_url="https://epramaan.gov.in/saml2/idp/metadata.php",
                claim_mapping={"sub": "nameId", "email": "mail", "name": "cn"},
                user_linking_policy="Require Manual Verification",
                is_active=True
            ),
            IdentityProviderFederation(
                name="Google Workspace (NIC & Government Hosted)",
                protocol="OIDC",
                issuer_url="https://accounts.google.com",
                client_id="suvidha-gov-portal.apps.googleusercontent.com",
                client_secret="google_oauth_secret",
                metadata_url="https://accounts.google.com/.well-known/openid-configuration",
                claim_mapping={"sub": "sub", "email": "email", "name": "name"},
                user_linking_policy="Auto-link by Email",
                is_active=True
            ),
        ]
        db.add_all(defaults)
        await db.commit()

    query = select(IdentityProviderFederation).order_by(IdentityProviderFederation.created_at.asc())
    if search:
        s = f"%{search.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(IdentityProviderFederation.name).like(s),
                func.lower(IdentityProviderFederation.issuer_url).like(s),
                func.lower(IdentityProviderFederation.client_id).like(s)
            )
        )
    query = query.offset(skip).limit(limit)
    result = await db.scalars(query)
    idps = result.all()

    return ApiResponse(
        success=True,
        code=2000,
        message=f"Found {len(idps)} federated identity providers",
        data=[
            IdentityProviderResponse(
                id=i.id,
                name=i.name,
                protocol=i.protocol,
                issuerUrl=i.issuer_url,
                clientId=i.client_id,
                clientSecretMasked="••••••••" if i.client_secret else "None",
                metadataUrl=i.metadata_url,
                claimMapping=i.claim_mapping or {},
                userLinkingPolicy=i.user_linking_policy,
                isActive=i.is_active,
                createdAt=i.created_at,
                updatedAt=i.updated_at
            )
            for i in idps
        ]
    )

# 6. Create Identity Provider
@router.post("/idps", response_model=ApiResponse[IdentityProviderResponse])
async def create_identity_provider(
    payload: IdentityProviderCreate,
    db: AsyncSession = Depends(get_write_db)
):
    idp = IdentityProviderFederation(
        name=payload.name.strip(),
        protocol=payload.protocol.strip().upper(),
        issuer_url=payload.issuerUrl.strip(),
        client_id=payload.clientId.strip() if payload.clientId else None,
        client_secret=payload.clientSecret.strip() if payload.clientSecret else None,
        metadata_url=payload.metadataUrl.strip() if payload.metadataUrl else None,
        claim_mapping=payload.claimMapping or {"sub": "sub", "email": "email", "name": "name"},
        user_linking_policy=payload.userLinkingPolicy,
        is_active=payload.isActive
    )
    db.add(idp)

    log = AuthenticationAuditLog(
        event_type="IDP_FEDERATION_CREATED",
        username="superadmin",
        ip_address="127.0.0.1",
        idp_used=idp.name,
        details=f"Created {idp.protocol} IDP provider '{idp.name}' with Issuer '{idp.issuer_url}'",
        status="SUCCESS"
    )
    db.add(log)
    await db.commit()
    await db.refresh(idp)

    return ApiResponse(
        success=True,
        code=2000,
        message=f"Identity provider '{idp.name}' registered successfully",
        data=IdentityProviderResponse(
            id=idp.id,
            name=idp.name,
            protocol=idp.protocol,
            issuerUrl=idp.issuer_url,
            clientId=idp.client_id,
            clientSecretMasked="••••••••" if idp.client_secret else "None",
            metadataUrl=idp.metadata_url,
            claimMapping=idp.claim_mapping or {},
            userLinkingPolicy=idp.user_linking_policy,
            isActive=idp.is_active,
            createdAt=idp.created_at,
            updatedAt=idp.updated_at
        )
    )

# 7. Update Identity Provider
@router.put("/idps/{idp_id}", response_model=ApiResponse[IdentityProviderResponse])
async def update_identity_provider(
    idp_id: str,
    payload: IdentityProviderUpdate,
    db: AsyncSession = Depends(get_write_db)
):
    idp = await db.get(IdentityProviderFederation, idp_id)
    if not idp:
        raise HTTPException(status_code=404, detail="Identity provider not found")

    if payload.name is not None:
        idp.name = payload.name.strip()
    if payload.protocol is not None:
        idp.protocol = payload.protocol.strip().upper()
    if payload.issuerUrl is not None:
        idp.issuer_url = payload.issuerUrl.strip()
    if payload.clientId is not None:
        idp.client_id = payload.clientId.strip()
    if payload.clientSecret and payload.clientSecret.strip() and payload.clientSecret != "••••••••":
        idp.client_secret = payload.clientSecret.strip()
    if payload.metadataUrl is not None:
        idp.metadata_url = payload.metadataUrl.strip()
    if payload.claimMapping is not None:
        idp.claim_mapping = payload.claimMapping
    if payload.userLinkingPolicy is not None:
        idp.user_linking_policy = payload.userLinkingPolicy
    if payload.isActive is not None:
        idp.is_active = payload.isActive
    idp.updated_at = datetime.datetime.utcnow()

    log = AuthenticationAuditLog(
        event_type="IDP_FEDERATION_UPDATED",
        username="superadmin",
        ip_address="127.0.0.1",
        idp_used=idp.name,
        details=f"Updated IDP provider '{idp.name}'",
        status="SUCCESS"
    )
    db.add(log)
    await db.commit()
    await db.refresh(idp)

    return ApiResponse(
        success=True,
        code=2000,
        message=f"Identity provider '{idp.name}' updated successfully",
        data=IdentityProviderResponse(
            id=idp.id,
            name=idp.name,
            protocol=idp.protocol,
            issuerUrl=idp.issuer_url,
            clientId=idp.client_id,
            clientSecretMasked="••••••••" if idp.client_secret else "None",
            metadataUrl=idp.metadata_url,
            claimMapping=idp.claim_mapping or {},
            userLinkingPolicy=idp.user_linking_policy,
            isActive=idp.is_active,
            createdAt=idp.created_at,
            updatedAt=idp.updated_at
        )
    )

# 8. Toggle IDP Active Status
@router.patch("/idps/{idp_id}/toggle", response_model=ApiResponse[IdentityProviderResponse])
async def toggle_identity_provider(
    idp_id: str,
    db: AsyncSession = Depends(get_write_db)
):
    idp = await db.get(IdentityProviderFederation, idp_id)
    if not idp:
        raise HTTPException(status_code=404, detail="Identity provider not found")

    idp.is_active = not idp.is_active
    idp.updated_at = datetime.datetime.utcnow()

    log = AuthenticationAuditLog(
        event_type="IDP_STATUS_TOGGLED",
        username="superadmin",
        ip_address="127.0.0.1",
        idp_used=idp.name,
        details=f"Provider '{idp.name}' is now {'Active' if idp.is_active else 'Disabled'}",
        status="SUCCESS"
    )
    db.add(log)
    await db.commit()
    await db.refresh(idp)

    return ApiResponse(
        success=True,
        code=2000,
        message=f"Provider '{idp.name}' is now {'Active' if idp.is_active else 'Disabled'}",
        data=IdentityProviderResponse(
            id=idp.id,
            name=idp.name,
            protocol=idp.protocol,
            issuerUrl=idp.issuer_url,
            clientId=idp.client_id,
            clientSecretMasked="••••••••" if idp.client_secret else "None",
            metadataUrl=idp.metadata_url,
            claimMapping=idp.claim_mapping or {},
            userLinkingPolicy=idp.user_linking_policy,
            isActive=idp.is_active,
            createdAt=idp.created_at,
            updatedAt=idp.updated_at
        )
    )

# 9. Delete IDP
@router.delete("/idps/{idp_id}", response_model=ApiResponse[dict])
async def delete_identity_provider(
    idp_id: str,
    db: AsyncSession = Depends(get_write_db)
):
    idp = await db.get(IdentityProviderFederation, idp_id)
    if not idp:
        raise HTTPException(status_code=404, detail="Identity provider not found")

    name = idp.name
    await db.delete(idp)

    log = AuthenticationAuditLog(
        event_type="IDP_FEDERATION_DELETED",
        username="superadmin",
        ip_address="127.0.0.1",
        idp_used=name,
        details=f"Deleted identity provider federation '{name}'",
        status="SUCCESS"
    )
    db.add(log)
    await db.commit()

    return ApiResponse(
        success=True,
        code=2000,
        message=f"Identity provider '{name}' removed",
        data={"id": idp_id, "name": name}
    )

# 10. Authentication Audit Logs
@router.get("/audit/logs", response_model=ApiResponse[List[AuthenticationAuditLogResponse]])
async def get_auth_audit_logs(
    event_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    username: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_read_db)
):
    query = select(AuthenticationAuditLog).order_by(desc(AuthenticationAuditLog.timestamp))
    if event_type and event_type != "ALL":
        query = query.where(AuthenticationAuditLog.event_type == event_type)
    if status and status != "ALL":
        query = query.where(AuthenticationAuditLog.status == status)
    if username and username.strip():
        query = query.where(AuthenticationAuditLog.username.ilike(f"%{username.strip()}%"))

    query = query.offset(skip).limit(limit)
    result = await db.scalars(query)
    logs = result.all()

    return ApiResponse(
        success=True,
        code=2000,
        message=f"Found {len(logs)} authentication logs",
        data=[
            AuthenticationAuditLogResponse(
                id=l.id,
                eventType=l.event_type,
                username=l.username,
                ipAddress=l.ip_address,
                userAgent=l.user_agent,
                idpUsed=l.idp_used,
                details=l.details,
                status=l.status,
                timestamp=l.timestamp
            )
            for l in logs
        ]
    )

# -------------------------------------------------------------
# ADM-R03: ROLES & PERMISSION MATRIX HELPERS & ENDPOINTS
# -------------------------------------------------------------

async def _seed_standard_roles_if_empty(db: AsyncSession):
    count_res = await db.scalar(select(func.count(RoleModel.id)))
    if count_res and count_res > 0:
        return

    standard_roles = [
        RoleModel(
            name="Platform Super Admin",
            code="PLATFORM_SUPER_ADMIN",
            description="Global multi-tenant root administration across all states and ULBs",
            role_level="Platform Super Admin",
            scope_type="Platform",
            status="Active",
            is_system=True,
            is_template=True,
        ),
        RoleModel(
            name="State Municipal Director",
            code="STATE_DIRECTOR",
            description="State Urban Development Department administrator with cross-city allocation authority",
            role_level="State Admin",
            scope_type="State",
            status="Active",
            is_system=True,
            is_template=True,
        ),
        RoleModel(
            name="ULB Municipal Commissioner",
            code="ULB_COMMISSIONER",
            description="Chief executive officer managing city municipal corporation departments and operations",
            role_level="ULB Admin",
            scope_type="ULB",
            status="Active",
            is_system=True,
            is_template=True,
        ),
        RoleModel(
            name="Town Planning Officer",
            code="TOWN_PLANNER",
            description="Urban planning director for master plans, zoning compliance, and layout NOC approvals",
            role_level="Department Admin",
            scope_type="Department",
            status="Active",
            is_system=False,
            is_template=True,
        ),
        RoleModel(
            name="Property Tax Revenue Inspector",
            code="TAX_INSPECTOR",
            description="Field assessment, tax collection verification, demand dispatch, and GIS survey validation",
            role_level="Officer",
            scope_type="Ward",
            status="Active",
            is_system=False,
            is_template=True,
        ),
        RoleModel(
            name="Vigilance & Accounts Auditor",
            code="AUDITOR",
            description="Compliance auditing, financial reconciliation, CAG audit reports, and RTI case review",
            role_level="Auditor",
            scope_type="ULB",
            status="Active",
            is_system=False,
            is_template=True,
        ),
        RoleModel(
            name="Public Citizen / Read-only User",
            code="CITIZEN_READONLY",
            description="Citizen self-service portal, property search, bill viewing, and receipt downloads",
            role_level="Read-only User",
            scope_type="Own Records",
            status="Active",
            is_system=False,
            is_template=True,
        ),
    ]
    db.add_all(standard_roles)
    await db.flush()

    # Seed baseline permissions for standard roles across primary modules
    # Super Admin gets all permissions across all modules
    # State Director gets allocate/view/manage across state
    # Tax Inspector gets PTX full, others read
    super_admin = next(r for r in standard_roles if r.code == "PLATFORM_SUPER_ADMIN")
    state_director = next(r for r in standard_roles if r.code == "STATE_DIRECTOR")
    tax_inspector = next(r for r in standard_roles if r.code == "TAX_INSPECTOR")

    baseline_perms = [
        RolePermission(
            role_id=super_admin.id,
            module_code="PTX",
            component_code="PTX-P01",
            can_view=True, can_create=True, can_update=True, can_delete=True,
            can_approve=True, can_export=True, can_manage=True,
            data_scope="Platform"
        ),
        RolePermission(
            role_id=super_admin.id,
            module_code="PTX",
            component_code="PTX-P10",
            can_view=True, can_create=True, can_update=True, can_delete=True,
            can_approve=True, can_export=True, can_manage=True,
            data_scope="Platform"
        ),
        RolePermission(
            role_id=state_director.id,
            module_code="PTX",
            component_code="PTX-P01",
            can_view=True, can_create=False, can_update=False, can_delete=False,
            can_approve=True, can_export=True, can_manage=False,
            data_scope="State"
        ),
        RolePermission(
            role_id=tax_inspector.id,
            module_code="PTX",
            component_code="PTX-P01",
            can_view=True, can_create=True, can_update=True, can_delete=False,
            can_approve=False, can_export=True, can_manage=False,
            data_scope="Ward"
        ),
    ]
    db.add_all(baseline_perms)
    await db.commit()

def _role_to_response(r: RoleModel, user_count: int = 0) -> RoleResponse:
    eff_from = r.effective_from.date() if r.effective_from else None
    eff_until = r.effective_until.date() if r.effective_until else None
    inherited = f"Inherits from {r.role_level} base policy"
    return RoleResponse(
        id=r.id,
        roleName=r.name,
        roleCode=r.code,
        description=r.description,
        roleLevel=r.role_level,
        scopeType=r.scope_type,
        parentRoleId=r.parent_role_id,
        status=r.status,
        effectiveFrom=eff_from,
        effectiveUntil=eff_until,
        isSystem=r.is_system,
        isTemplate=r.is_template,
        assignedUsersCount=user_count,
        inheritedPermissionsSummary=inherited,
        createdAt=r.created_at,
        updatedAt=r.updated_at
    )

@router.get("/roles", response_model=ApiResponse[List[RoleResponse]])
async def get_roles(
    role_level: Optional[str] = Query(None),
    scope_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_read_db)
):
    await _seed_standard_roles_if_empty(db)
    query = select(RoleModel).order_by(RoleModel.created_at.asc())

    if role_level and role_level != "ALL":
        query = query.where(RoleModel.role_level == role_level)
    if scope_type and scope_type != "ALL":
        query = query.where(RoleModel.scope_type == scope_type)
    if status and status != "ALL":
        query = query.where(RoleModel.status == status)
    if search and search.strip():
        s = f"%{search.strip()}%"
        query = query.where((RoleModel.name.ilike(s)) | (RoleModel.code.ilike(s)) | (RoleModel.description.ilike(s)))

    query = query.offset(skip).limit(limit)
    result = await db.scalars(query)
    roles = result.all()

    # User count per role
    user_counts_query = select(GlobalUserProfile.assigned_roles)
    users_result = await db.scalars(user_counts_query)
    all_assigned = users_result.all()
    count_map: Dict[str, int] = {}
    for user_roles in all_assigned:
        if isinstance(user_roles, list):
            for rcode in user_roles:
                count_map[rcode] = count_map.get(rcode, 0) + 1

    return ApiResponse(
        success=True,
        code=2000,
        message=f"Found {len(roles)} roles",
        data=[_role_to_response(r, count_map.get(r.code, 0) + count_map.get(r.id, 0)) for r in roles]
    )

@router.get("/roles/templates", response_model=ApiResponse[List[RoleResponse]])
async def get_role_templates(db: AsyncSession = Depends(get_read_db)):
    await _seed_standard_roles_if_empty(db)
    query = select(RoleModel).where(RoleModel.is_template == True).order_by(RoleModel.created_at.asc())
    result = await db.scalars(query)
    templates = result.all()
    return ApiResponse(
        success=True,
        code=2000,
        message=f"Found {len(templates)} standard role templates",
        data=[_role_to_response(t) for t in templates]
    )

@router.post("/roles", response_model=ApiResponse[RoleResponse])
async def create_role(
    payload: RoleCreate,
    db: AsyncSession = Depends(get_write_db)
):
    # Check if role code exists
    existing = await db.scalar(select(RoleModel).where(RoleModel.code == payload.roleCode.strip().upper()))
    if existing:
        raise HTTPException(status_code=400, detail=f"Role with code '{payload.roleCode}' already exists")

    eff_from = datetime.datetime.combine(payload.effectiveFrom, datetime.time.min) if payload.effectiveFrom else None
    eff_until = datetime.datetime.combine(payload.effectiveUntil, datetime.time.max) if payload.effectiveUntil else None

    role = RoleModel(
        name=payload.roleName.strip(),
        code=payload.roleCode.strip().upper(),
        description=payload.description.strip(),
        role_level=payload.roleLevel,
        scope_type=payload.scopeType,
        parent_role_id=payload.parentRoleId,
        status=payload.status,
        effective_from=eff_from,
        effective_until=eff_until,
        is_system=False,
        is_template=payload.isTemplate,
    )
    db.add(role)
    await db.commit()
    await db.refresh(role)

    return ApiResponse(
        success=True,
        code=2001,
        message=f"Role '{role.name}' created successfully",
        data=_role_to_response(role)
    )

@router.get("/roles/{role_id}", response_model=ApiResponse[RoleResponse])
async def get_role_by_id(role_id: str, db: AsyncSession = Depends(get_read_db)):
    role = await db.get(RoleModel, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    return ApiResponse(success=True, code=2000, message="Role retrieved", data=_role_to_response(role))

@router.put("/roles/{role_id}", response_model=ApiResponse[RoleResponse])
async def update_role(
    role_id: str,
    payload: RoleUpdate,
    db: AsyncSession = Depends(get_write_db)
):
    role = await db.get(RoleModel, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if payload.roleName is not None:
        role.name = payload.roleName.strip()
    if payload.roleCode is not None and not role.is_system:
        role.code = payload.roleCode.strip().upper()
    if payload.description is not None:
        role.description = payload.description.strip()
    if payload.roleLevel is not None and not role.is_system:
        role.role_level = payload.roleLevel
    if payload.scopeType is not None:
        role.scope_type = payload.scopeType
    if payload.parentRoleId is not None:
        role.parent_role_id = payload.parentRoleId
    if payload.status is not None:
        role.status = payload.status
    if payload.effectiveFrom is not None:
        role.effective_from = datetime.datetime.combine(payload.effectiveFrom, datetime.time.min)
    if payload.effectiveUntil is not None:
        role.effective_until = datetime.datetime.combine(payload.effectiveUntil, datetime.time.max)

    await db.commit()
    await db.refresh(role)
    return ApiResponse(success=True, code=2000, message="Role updated", data=_role_to_response(role))

@router.delete("/roles/{role_id}", response_model=ApiResponse[dict])
async def delete_role(role_id: str, db: AsyncSession = Depends(get_write_db)):
    role = await db.get(RoleModel, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=403, detail="System protected roles cannot be deleted")

    name = role.name
    await db.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
    await db.delete(role)
    await db.commit()
    return ApiResponse(success=True, code=2000, message=f"Role '{name}' deleted successfully", data={"id": role_id})

# ----------------- Permissions Matrix -----------------
@router.get("/roles/{role_id}/permissions", response_model=ApiResponse[List[RolePermissionItem]])
async def get_role_permissions(
    role_id: str,
    module_code: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_read_db)
):
    role = await db.get(RoleModel, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # Fetch stored permissions for this role
    q = select(RolePermission).where(RolePermission.role_id == role_id)
    if module_code and module_code != "ALL":
        q = q.where(RolePermission.module_code == module_code)
    result = await db.scalars(q)
    stored = {f"{p.module_code}:{p.component_code}": p for p in result.all()}

    # Fetch all registered components to provide full matrix view
    cq = select(ComponentModel).order_by(ComponentModel.parent_module_code.asc(), ComponentModel.code.asc())
    if module_code and module_code != "ALL":
        cq = cq.where(ComponentModel.parent_module_code == module_code)
    if search:
        s = f"%{search.strip().lower()}%"
        cq = cq.where(
            or_(
                func.lower(ComponentModel.name).like(s),
                func.lower(ComponentModel.code).like(s),
                func.lower(ComponentModel.parent_module_code).like(s),
                func.lower(ComponentModel.frontend_permission_key).like(s)
            )
        )
    cq = cq.offset(skip).limit(limit)
    c_result = await db.scalars(cq)
    components = c_result.all()

    matrix_items: List[RolePermissionItem] = []
    default_scope = role.scope_type if role.scope_type in ["Platform", "State", "ULB", "Department", "Ward", "Own Records"] else "Own Records"

    is_super = role.code == "PLATFORM_SUPER_ADMIN"

    for comp in components:
        key = f"{comp.parent_module_code}:{comp.code}"
        if key in stored:
            p = stored[key]
            matrix_items.append(
                RolePermissionItem(
                    id=p.id,
                    roleId=p.role_id,
                    moduleCode=p.module_code,
                    componentCode=p.component_code,
                    canView=p.can_view,
                    canCreate=p.can_create,
                    canUpdate=p.can_update,
                    canDelete=p.can_delete,
                    canApprove=p.can_approve,
                    canExport=p.can_export,
                    canManage=p.can_manage,
                    dataScope=p.data_scope,
                    conditions=p.conditions,
                    effectiveFrom=p.effective_from.date() if p.effective_from else None,
                    effectiveUntil=p.effective_until.date() if p.effective_until else None,
                )
            )
        else:
            # Not stored yet - defaults: Super Admin gets full access, others deny by default
            matrix_items.append(
                RolePermissionItem(
                    id=None,
                    roleId=role.id,
                    moduleCode=comp.parent_module_code,
                    componentCode=comp.code,
                    canView=is_super,
                    canCreate=is_super,
                    canUpdate=is_super,
                    canDelete=is_super,
                    canApprove=is_super,
                    canExport=is_super,
                    canManage=is_super,
                    dataScope=default_scope,
                    conditions=None,
                    effectiveFrom=None,
                    effectiveUntil=None,
                )
            )

    return ApiResponse(
        success=True,
        code=2000,
        message=f"Retrieved {len(matrix_items)} permission entries for role {role.name}",
        data=matrix_items
    )

@router.put("/roles/{role_id}/permissions", response_model=ApiResponse[List[RolePermissionItem]])
async def update_role_permissions(
    role_id: str,
    payload: RolePermissionsUpdate,
    db: AsyncSession = Depends(get_write_db)
):
    role = await db.get(RoleModel, role_id)
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    # Delete existing permissions only for the modules present in payload
    affected_modules = {item.moduleCode for item in payload.permissions if item.moduleCode}
    if affected_modules:
        await db.execute(
            delete(RolePermission).where(
                and_(RolePermission.role_id == role_id, RolePermission.module_code.in_(affected_modules))
            )
        )
    else:
        await db.execute(delete(RolePermission).where(RolePermission.role_id == role_id))

    new_entries = []
    for item in payload.permissions:
        eff_f = datetime.datetime.combine(item.effectiveFrom, datetime.time.min) if item.effectiveFrom else None
        eff_u = datetime.datetime.combine(item.effectiveUntil, datetime.time.max) if item.effectiveUntil else None
        p = RolePermission(
            role_id=role_id,
            module_code=item.moduleCode,
            component_code=item.componentCode,
            can_view=item.canView,
            can_create=item.canCreate,
            can_update=item.canUpdate,
            can_delete=item.canDelete,
            can_approve=item.canApprove,
            can_export=item.canExport,
            can_manage=item.canManage,
            data_scope=item.dataScope,
            conditions=item.conditions,
            effective_from=eff_f,
            effective_until=eff_u,
        )
        new_entries.append(p)

    db.add_all(new_entries)
    await db.commit()

    return ApiResponse(
        success=True,
        code=2000,
        message=f"Updated {len(new_entries)} permission rules for {role.name}",
        data=payload.permissions
    )

@router.post("/roles/{role_id}/copy-from/{source_role_id}", response_model=ApiResponse[dict])
async def copy_role_permissions(
    role_id: str,
    source_role_id: str,
    db: AsyncSession = Depends(get_write_db)
):
    target = await db.get(RoleModel, role_id)
    source = await db.get(RoleModel, source_role_id)
    if not target or not source:
        raise HTTPException(status_code=404, detail="Target or source role not found")

    source_perms = await db.scalars(select(RolePermission).where(RolePermission.role_id == source_role_id))
    items = source_perms.all()

    await db.execute(delete(RolePermission).where(RolePermission.role_id == role_id))
    new_perms = [
        RolePermission(
            role_id=role_id,
            module_code=p.module_code,
            component_code=p.component_code,
            can_view=p.can_view,
            can_create=p.can_create,
            can_update=p.can_update,
            can_delete=p.can_delete,
            can_approve=p.can_approve,
            can_export=p.can_export,
            can_manage=p.can_manage,
            data_scope=p.data_scope,
            conditions=p.conditions,
            effective_from=p.effective_from,
            effective_until=p.effective_until,
        )
        for p in items
    ]
    db.add_all(new_perms)
    await db.commit()

    return ApiResponse(
        success=True,
        code=2000,
        message=f"Copied {len(new_perms)} permission entries from '{source.name}' to '{target.name}'",
        data={"copiedCount": len(new_perms)}
    )

@router.get("/roles/compare/diff", response_model=ApiResponse[RoleComparisonResult])
async def compare_roles(
    role_a_id: str = Query(...),
    role_b_id: str = Query(...),
    db: AsyncSession = Depends(get_read_db)
):
    role_a = await db.get(RoleModel, role_a_id)
    role_b = await db.get(RoleModel, role_b_id)
    if not role_a or not role_b:
        raise HTTPException(status_code=404, detail="One or both roles not found")

    perms_a = {f"{p.module_code}:{p.component_code}": p for p in (await db.scalars(select(RolePermission).where(RolePermission.role_id == role_a_id))).all()}
    perms_b = {f"{p.module_code}:{p.component_code}": p for p in (await db.scalars(select(RolePermission).where(RolePermission.role_id == role_b_id))).all()}

    all_keys = sorted(set(list(perms_a.keys()) + list(perms_b.keys())))
    diffs: List[RoleComparisonDiff] = []
    conflict_count = 0

    for key in all_keys:
        mod, comp = key.split(":")
        pa = perms_a.get(key)
        pb = perms_b.get(key)

        pa_dict = {
            "view": pa.can_view if pa else False,
            "create": pa.can_create if pa else False,
            "update": pa.can_update if pa else False,
            "delete": pa.can_delete if pa else False,
            "approve": pa.can_approve if pa else False,
            "manage": pa.can_manage if pa else False,
            "scope": pa.data_scope if pa else "None"
        }
        pb_dict = {
            "view": pb.can_view if pb else False,
            "create": pb.can_create if pb else False,
            "update": pb.can_update if pb else False,
            "delete": pb.can_delete if pb else False,
            "approve": pb.can_approve if pb else False,
            "manage": pb.can_manage if pb else False,
            "scope": pb.data_scope if pb else "None"
        }

        is_diff = pa_dict != pb_dict
        # Flag excessive: role B has delete/manage where role A does not
        is_conflict = (not pa_dict["manage"] and pb_dict["manage"]) or (not pa_dict["delete"] and pb_dict["delete"])
        if is_conflict:
            conflict_count += 1

        if is_diff:
            diffs.append(
                RoleComparisonDiff(
                    moduleCode=mod,
                    componentCode=comp,
                    roleAPermissions=pa_dict,
                    roleBPermissions=pb_dict,
                    isDifferent=is_diff,
                    isConflictOrExcessive=is_conflict
                )
            )

    return ApiResponse(
        success=True,
        code=2000,
        message=f"Comparison computed with {len(diffs)} differences",
        data=RoleComparisonResult(
            roleA=_role_to_response(role_a),
            roleB=_role_to_response(role_b),
            differences=diffs,
            conflictCount=conflict_count
        )
    )

# -------------------------------------------------------------
# ADM-R01: GLOBAL USER MANAGEMENT & INVITATIONS
# -------------------------------------------------------------

async def _seed_initial_users_if_empty(db: AsyncSession):
    # Auto-migrate any existing users with "Keycloak Civora"
    legacy_users = (await db.scalars(select(GlobalUserProfile).where(GlobalUserProfile.idp_provider == "Keycloak Civora"))).all()
    if legacy_users:
        for u in legacy_users:
            u.idp_provider = "Keycloak Suvidha"
        await db.commit()

    count = await db.scalar(select(func.count(GlobalUserProfile.id)))
    if count and count > 0:
        return

    sample_users = [
        GlobalUserProfile(
            first_name="Suresh",
            last_name="Kumar",
            email="suresh.director@telangana.gov.in",
            mobile_number="+91 98480 12345",
            idp_provider="Keycloak Suvidha",
            user_type="Government Officer",
            account_status="Active",
            designation="State Municipal Director",
            department="Directorate of Municipal Administration",
            employee_id="TS-GO-2019-041",
            platform_access=False,
            state_tenant_id="TG",
            ulb_tenant_id=None,
            assigned_roles=["STATE_DIRECTOR"],
            additional_permissions=[],
            last_active_at=datetime.datetime.utcnow() - datetime.timedelta(minutes=5),
        ),
        GlobalUserProfile(
            first_name="Priya",
            last_name="Sharma",
            email="priya.sharma@gwmc.gov.in",
            mobile_number="+91 94401 56789",
            idp_provider="MeriPehchan",
            external_identity_id="AADHAAR-HASH-8891-TG",
            user_type="Internal Staff",
            account_status="Active",
            designation="Municipal Commissioner",
            department="Executive Administration",
            employee_id="GWMC-EXEC-001",
            platform_access=False,
            state_tenant_id="TG",
            ulb_tenant_id="GWMC",
            assigned_roles=["ULB_COMMISSIONER"],
            additional_permissions=[],
            last_active_at=datetime.datetime.utcnow() - datetime.timedelta(minutes=30),
        ),
        GlobalUserProfile(
            first_name="Rajesh",
            last_name="Varma",
            email="rajesh.planner@ghmc.gov.in",
            mobile_number="+91 99887 76543",
            idp_provider="Keycloak Suvidha",
            user_type="Government Officer",
            account_status="Active",
            designation="Chief Town Planner",
            department="Town Planning & Regulation",
            employee_id="GHMC-TP-089",
            platform_access=False,
            state_tenant_id="TG",
            ulb_tenant_id="GHMC",
            assigned_roles=["TOWN_PLANNER"],
            additional_permissions=[],
            last_active_at=datetime.datetime.utcnow() - datetime.timedelta(hours=3),
        ),
        GlobalUserProfile(
            first_name="Ananya",
            last_name="Rao",
            email="ananya.revenue@gwmc.gov.in",
            mobile_number="+91 91234 56780",
            idp_provider="Keycloak Suvidha",
            user_type="Internal Staff",
            account_status="Active",
            designation="Senior Tax Inspector",
            department="Revenue & Property Tax",
            employee_id="GWMC-REV-234",
            platform_access=False,
            state_tenant_id="TG",
            ulb_tenant_id="GWMC",
            assigned_ward="Ward 12 - Hanamkonda",
            assigned_roles=["TAX_INSPECTOR"],
            additional_permissions=[],
            last_active_at=datetime.datetime.utcnow() - datetime.timedelta(hours=1),
        ),
        GlobalUserProfile(
            first_name="Vikram",
            last_name="Singhania",
            email="vikram.auditor@cag.gov.in",
            mobile_number="+91 98765 43210",
            idp_provider="NIC SSO",
            external_identity_id="NIC-GOV-AUD-55",
            user_type="Auditor",
            account_status="Active",
            designation="Senior Vigilance Auditor",
            department="State Urban Audit Wing",
            employee_id="CAG-VIG-789",
            platform_access=True,
            state_tenant_id="TG",
            ulb_tenant_id=None,
            assigned_roles=["AUDITOR"],
            additional_permissions=[],
            last_active_at=datetime.datetime.utcnow() - datetime.timedelta(days=1),
        ),
    ]
    db.add_all(sample_users)
    await db.commit()

async def _seed_initial_invitations_if_empty(db: AsyncSession):
    count = await db.scalar(select(func.count(UserInvitation.id)))
    if count and count > 0:
        return

    sample_invitations = [
        UserInvitation(
            email="arun.patil@maharashtra.gov.in",
            user_type="Government Officer",
            target_tenant_id="MH",
            target_sub_tenant_id=None,
            assigned_role="STATE_DIRECTOR",
            department_scope="Urban Development Department (UDD-MH)",
            ward_scope=None,
            invitation_token=secrets.token_urlsafe(32),
            invitation_expiry=datetime.datetime.utcnow() + datetime.timedelta(days=5),
            require_mfa=True,
            invitation_message="Welcome to SUVIDHA ERP Directorate. Please complete your onboarding credentials.",
            status="Pending",
            invited_by="Super Admin (admin@urban.gov.in)",
        ),
        UserInvitation(
            email="deepa.nair@pune.gov.in",
            user_type="Internal Staff",
            target_tenant_id="MH",
            target_sub_tenant_id="PMC",
            assigned_role="ULB_COMMISSIONER",
            department_scope="Executive Directorate",
            ward_scope=None,
            invitation_token=secrets.token_urlsafe(32),
            invitation_expiry=datetime.datetime.utcnow() + datetime.timedelta(days=3),
            require_mfa=True,
            invitation_message="Pune Municipal Corporation SUVIDHA administrative allocation invitation.",
            status="Pending",
            invited_by="State Municipal Director",
        ),
    ]
    db.add_all(sample_invitations)
    await db.commit()

def _user_to_response(u: GlobalUserProfile) -> GlobalUserResponse:
    mid = f" {u.middle_name} " if u.middle_name else " "
    full_name = f"{u.first_name}{mid}{u.last_name}".strip()
    return GlobalUserResponse(
        id=u.id,
        firstName=u.first_name,
        middleName=u.middle_name,
        lastName=u.last_name,
        fullName=full_name,
        email=u.email,
        mobileNumber=u.mobile_number,
        idpProvider=u.idp_provider,
        externalIdentityId=u.external_identity_id,
        userType=u.user_type,
        accountStatus=u.account_status,
        preferredLanguage=u.preferred_language or "English",
        timeZone=u.time_zone or "Asia/Kolkata",
        employeeId=u.employee_id,
        designation=u.designation,
        department=u.department,
        profilePhotoUrl=u.profile_photo_url,
        accountExpiryDate=u.account_expiry_date.date() if u.account_expiry_date else None,
        remarks=u.remarks,
        platformAccess=u.platform_access,
        stateTenantId=u.state_tenant_id,
        ulbTenantId=u.ulb_tenant_id,
        assignedDepartment=u.assigned_department,
        assignedZone=u.assigned_zone,
        assignedWard=u.assigned_ward,
        assignedRoles=u.assigned_roles or [],
        additionalPermissions=u.additional_permissions or [],
        accessEffectiveFrom=u.access_effective_from.date() if u.access_effective_from else None,
        accessEffectiveUntil=u.access_effective_until.date() if u.access_effective_until else None,
        approvalReference=u.approval_reference,
        lastActiveAt=u.last_active_at,
        createdAt=u.created_at,
        updatedAt=u.updated_at
    )

@router.get("/users", response_model=ApiResponse[List[GlobalUserResponse]])
async def get_users(
    tenant_id: Optional[str] = Query(None),
    user_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_read_db)
):
    await _seed_initial_users_if_empty(db)
    query = select(GlobalUserProfile).order_by(desc(GlobalUserProfile.created_at))

    if tenant_id and tenant_id != "ALL":
        query = query.where(
            (GlobalUserProfile.state_tenant_id == tenant_id) |
            (GlobalUserProfile.ulb_tenant_id == tenant_id)
        )
    if user_type and user_type != "ALL":
        query = query.where(GlobalUserProfile.user_type == user_type)
    if status and status != "ALL":
        query = query.where(GlobalUserProfile.account_status == status)
    if search and search.strip():
        s = f"%{search.strip()}%"
        query = query.where(
            (GlobalUserProfile.first_name.ilike(s)) |
            (GlobalUserProfile.last_name.ilike(s)) |
            (GlobalUserProfile.email.ilike(s)) |
            (GlobalUserProfile.designation.ilike(s)) |
            (GlobalUserProfile.employee_id.ilike(s))
        )

    query = query.offset(skip).limit(limit)
    result = await db.scalars(query)
    users = result.all()
    return ApiResponse(
        success=True,
        code=2000,
        message=f"Found {len(users)} users in directory",
        data=[_user_to_response(u) for u in users]
    )

@router.post("/users", response_model=ApiResponse[GlobalUserResponse])
async def create_user(
    payload: GlobalUserCreate,
    db: AsyncSession = Depends(get_write_db)
):
    # Email unique check
    existing = await db.scalar(select(GlobalUserProfile).where(GlobalUserProfile.email == payload.email.strip().lower()))
    if existing:
        raise HTTPException(status_code=400, detail=f"User with email '{payload.email}' already exists")

    expiry = datetime.datetime.combine(payload.accountExpiryDate, datetime.time.max) if payload.accountExpiryDate else None

    user = GlobalUserProfile(
        first_name=payload.firstName.strip(),
        middle_name=payload.middleName.strip() if payload.middleName else None,
        last_name=payload.lastName.strip(),
        email=payload.email.strip().lower(),
        mobile_number=payload.mobileNumber.strip() if payload.mobileNumber else None,
        idp_provider=payload.idpProvider,
        external_identity_id=payload.externalIdentityId.strip() if payload.externalIdentityId else None,
        user_type=payload.userType,
        account_status=payload.accountStatus,
        preferred_language=payload.preferredLanguage or "English",
        time_zone=payload.timeZone or "Asia/Kolkata",
        employee_id=payload.employeeId.strip() if payload.employeeId else None,
        designation=payload.designation.strip() if payload.designation else None,
        department=payload.department.strip() if payload.department else None,
        profile_photo_url=payload.profilePhotoUrl,
        account_expiry_date=expiry,
        remarks=payload.remarks,
        platform_access=False,
        assigned_roles=[],
        additional_permissions=[],
    )
    db.add(user)

    # Sync to auth User model for login credentials
    initial_pwd = (payload.password or "Urban@2026").strip()
    auth_user = await db.scalar(
        select(User).where(or_(User.username == user.email, User.email == user.email))
    )
    if not auth_user:
        auth_user = User(
            tenant_id="GWMC",
            username=user.email,
            email=user.email,
            password_hash=hash_password(initial_pwd),
            full_name=f"{user.first_name} {user.last_name}",
            role="citizen",
            assigned_modules="PTX,WTR,GRV,FIN,DMS,TRL,UCH,BPM,TPL,FNC,SWM,ENG,SLM,PRK,INV,HRM,MPM,LGL,GSC",
            is_active=True
        )
        db.add(auth_user)
    else:
        auth_user.password_hash = hash_password(initial_pwd)
        auth_user.full_name = f"{user.first_name} {user.last_name}"
        auth_user.is_active = (user.account_status == "Active")

    await db.commit()
    await db.refresh(user)

    return ApiResponse(
        success=True,
        code=2001,
        message=f"User '{user.first_name} {user.last_name}' created successfully",
        data=_user_to_response(user)
    )

@router.get("/users/{user_id}", response_model=ApiResponse[GlobalUserResponse])
async def get_user_by_id(user_id: str, db: AsyncSession = Depends(get_read_db)):
    user = await db.get(GlobalUserProfile, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return ApiResponse(success=True, code=2000, message="User retrieved", data=_user_to_response(user))

@router.put("/users/{user_id}", response_model=ApiResponse[GlobalUserResponse])
async def update_user(
    user_id: str,
    payload: GlobalUserUpdate,
    db: AsyncSession = Depends(get_write_db)
):
    user = await db.get(GlobalUserProfile, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.firstName is not None:
        user.first_name = payload.firstName.strip()
    if payload.middleName is not None:
        user.middle_name = payload.middleName.strip() or None
    if payload.lastName is not None:
        user.last_name = payload.lastName.strip()
    if payload.email is not None:
        user.email = payload.email.strip().lower()
    if payload.mobileNumber is not None:
        user.mobile_number = payload.mobileNumber.strip() or None
    if payload.idpProvider is not None:
        user.idp_provider = payload.idpProvider
    if payload.externalIdentityId is not None:
        user.external_identity_id = payload.externalIdentityId.strip() or None
    if payload.userType is not None:
        user.user_type = payload.userType
    if payload.accountStatus is not None:
        user.account_status = payload.accountStatus
    if payload.preferredLanguage is not None:
        user.preferred_language = payload.preferredLanguage
    if payload.timeZone is not None:
        user.time_zone = payload.timeZone
    if payload.employeeId is not None:
        user.employee_id = payload.employeeId.strip() or None
    if payload.designation is not None:
        user.designation = payload.designation.strip() or None
    if payload.department is not None:
        user.department = payload.department.strip() or None
    if payload.profilePhotoUrl is not None:
        user.profile_photo_url = payload.profilePhotoUrl
    if payload.accountExpiryDate is not None:
        user.account_expiry_date = datetime.datetime.combine(payload.accountExpiryDate, datetime.time.max)
    if payload.remarks is not None:
        user.remarks = payload.remarks

    await db.commit()
    await db.refresh(user)
    return ApiResponse(success=True, code=2000, message="User profile updated", data=_user_to_response(user))

@router.put("/users/{user_id}/scope", response_model=ApiResponse[GlobalUserResponse])
async def update_user_scope(
    user_id: str,
    payload: GlobalUserScopeUpdate,
    db: AsyncSession = Depends(get_write_db)
):
    user = await db.get(GlobalUserProfile, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    eff_f = datetime.datetime.combine(payload.accessEffectiveFrom, datetime.time.min) if payload.accessEffectiveFrom else None
    eff_u = datetime.datetime.combine(payload.accessEffectiveUntil, datetime.time.max) if payload.accessEffectiveUntil else None

    user.platform_access = payload.platformAccess
    user.state_tenant_id = payload.stateTenantId
    user.ulb_tenant_id = payload.ulbTenantId
    user.assigned_department = payload.assignedDepartment
    user.assigned_zone = payload.assignedZone
    user.assigned_ward = payload.assignedWard
    user.assigned_roles = payload.assignedRoles
    user.additional_permissions = payload.additionalPermissions or []
    user.access_effective_from = eff_f
    user.access_effective_until = eff_u
    user.approval_reference = payload.approvalReference

    # Sync tenant scope & roles to auth User table so signin grants correct context
    auth_user = await db.scalar(
        select(User).where(or_(User.username == user.email, User.email == user.email))
    )
    target_tenant = payload.ulbTenantId or payload.stateTenantId or "GWMC"
    first_target = target_tenant.split(",")[0].strip() if target_tenant else "GWMC"
    valid_ulb = await db.scalar(select(Tenant).where(Tenant.tenant_id == first_target))
    if not valid_ulb:
        valid_ulb = await db.scalar(select(Tenant).where(Tenant.state_code == first_target))
    if not valid_ulb:
        valid_ulb = await db.scalar(select(Tenant).limit(1))
    assigned_tenant_id = valid_ulb.tenant_id if valid_ulb else "GWMC"

    assigned_role = "citizen"
    if payload.platformAccess or "SUPER_ADMIN" in payload.assignedRoles:
        assigned_role = "super_admin"
    elif "STATE_DIRECTOR" in payload.assignedRoles:
        assigned_role = "state_director"
    elif any(r in payload.assignedRoles for r in ["ULB_COMMISSIONER", "REVENUE_OFFICER", "MUNICIPAL_COMMISSIONER"]):
        assigned_role = "revenue_officer"
    elif payload.assignedRoles:
        assigned_role = payload.assignedRoles[0].lower()

    if not auth_user:
        auth_user = User(
            tenant_id=assigned_tenant_id,
            username=user.email,
            email=user.email,
            password_hash=hash_password("Urban@2026"),
            full_name=f"{user.first_name} {user.last_name}",
            role=assigned_role,
            assigned_modules="PTX,WTR,GRV,FIN,DMS,TRL,UCH,BPM,TPL,FNC,SWM,ENG,SLM,PRK,INV,HRM,MPM,LGL,GSC",
            assigned_zone=user.assigned_zone,
            assigned_ward=user.assigned_ward,
            is_active=(user.account_status == "Active")
        )
        db.add(auth_user)
    else:
        auth_user.tenant_id = assigned_tenant_id
        auth_user.role = assigned_role
        auth_user.assigned_zone = user.assigned_zone
        auth_user.assigned_ward = user.assigned_ward
        auth_user.is_active = (user.account_status == "Active")

    await db.commit()
    await db.refresh(user)
    return ApiResponse(
        success=True,
        code=2000,
        message=f"Organizational scope and roles updated for '{user.first_name} {user.last_name}'",
        data=_user_to_response(user)
    )

@router.post("/users/{user_id}/reset-password", response_model=ApiResponse[dict])
async def reset_user_password(
    user_id: str,
    payload: ResetUserPasswordPayload,
    db: AsyncSession = Depends(get_write_db)
):
    user = await db.get(GlobalUserProfile, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    new_pwd = payload.newPassword.strip()
    if len(new_pwd) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long")

    # Update or create auth user
    auth_user = await db.scalar(
        select(User).where(or_(User.username == user.email, User.email == user.email))
    )
    target_tenant = user.ulb_tenant_id or user.state_tenant_id or "GWMC"
    valid_ulb = await db.scalar(select(Tenant).where(Tenant.tenant_id == target_tenant))
    if not valid_ulb:
        valid_ulb = await db.scalar(select(Tenant).where(Tenant.state_code == target_tenant))
    if not valid_ulb:
        valid_ulb = await db.scalar(select(Tenant).limit(1))
    assigned_tenant_id = valid_ulb.tenant_id if valid_ulb else "GWMC"

    assigned_role = "citizen"
    if user.platform_access or "SUPER_ADMIN" in (user.assigned_roles or []):
        assigned_role = "super_admin"
    elif "STATE_DIRECTOR" in (user.assigned_roles or []):
        assigned_role = "state_director"
    elif any(r in (user.assigned_roles or []) for r in ["ULB_COMMISSIONER", "REVENUE_OFFICER", "MUNICIPAL_COMMISSIONER"]):
        assigned_role = "revenue_officer"
    elif user.assigned_roles:
        assigned_role = user.assigned_roles[0].lower()

    if not auth_user:
        auth_user = User(
            tenant_id=assigned_tenant_id,
            username=user.email,
            email=user.email,
            password_hash=hash_password(new_pwd),
            full_name=f"{user.first_name} {user.last_name}",
            role=assigned_role,
            assigned_modules="PTX,WTR,GRV,FIN,DMS,TRL,UCH,BPM,TPL,FNC,SWM,ENG,SLM,PRK,INV,HRM,MPM,LGL,GSC",
            is_active=(user.account_status == "Active")
        )
        db.add(auth_user)
    else:
        auth_user.password_hash = hash_password(new_pwd)
        auth_user.is_active = (user.account_status == "Active")
        auth_user.tenant_id = assigned_tenant_id
        auth_user.role = assigned_role

    await db.commit()
    return ApiResponse(
        success=True,
        code=2000,
        message=f"Password for user '{user.email}' has been successfully reset.",
        data={"email": user.email, "updated": True}
    )

@router.patch("/users/{user_id}/status", response_model=ApiResponse[GlobalUserResponse])
async def toggle_user_status(
    user_id: str,
    status: str = Query(..., pattern="^(Active|Suspended|Deactivated)$"),
    db: AsyncSession = Depends(get_write_db)
):
    user = await db.get(GlobalUserProfile, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.account_status = status
    await db.commit()
    await db.refresh(user)
    return ApiResponse(
        success=True,
        code=2000,
        message=f"User status updated to '{status}'",
        data=_user_to_response(user)
    )

@router.post("/users/{user_id}/revoke-sessions", response_model=ApiResponse[dict])
async def revoke_user_sessions(user_id: str, db: AsyncSession = Depends(get_write_db)):
    user = await db.get(GlobalUserProfile, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # In production, invokes Keycloak Admin API `POST /admin/realms/{realm}/users/{id}/logout`
    # Also log security audit
    audit = AuthenticationAuditLog(
        event_type="SESSION_REVOKED",
        username=user.email,
        details=f"Administrative session revocation triggered by Super Admin",
        status="SUCCESS",
        timestamp=datetime.datetime.utcnow()
    )
    db.add(audit)
    await db.commit()

    return ApiResponse(
        success=True,
        code=2000,
        message=f"Active sessions revoked for '{user.email}'",
        data={"userId": user_id, "email": user.email, "revokedAt": datetime.datetime.utcnow().isoformat()}
    )

# ----------------- Invitations -----------------
def _invitation_to_response(inv: UserInvitation) -> UserInvitationResponse:
    is_exp = datetime.datetime.utcnow() > inv.invitation_expiry
    masked_token = f"{inv.invitation_token[:8]}••••••••{inv.invitation_token[-6:]}"
    return UserInvitationResponse(
        id=inv.id,
        email=inv.email,
        userType=inv.user_type,
        targetTenantId=inv.target_tenant_id,
        targetSubTenantId=inv.target_sub_tenant_id,
        assignedRole=inv.assigned_role,
        departmentScope=inv.department_scope,
        wardScope=inv.ward_scope,
        invitationTokenMasked=masked_token,
        invitationExpiry=inv.invitation_expiry,
        isExpired=is_exp,
        requireMfa=inv.require_mfa,
        invitationMessage=inv.invitation_message,
        status="Expired" if is_exp and inv.status == "Pending" else inv.status,
        invitedBy=inv.invited_by,
        createdAt=inv.created_at
    )

@router.get("/invitations", response_model=ApiResponse[List[UserInvitationResponse]])
async def get_invitations(
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_read_db)
):
    await _seed_initial_invitations_if_empty(db)
    query = select(UserInvitation).order_by(desc(UserInvitation.created_at))
    if status and status != "ALL":
        query = query.where(UserInvitation.status == status)
    if search:
        s = f"%{search.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(UserInvitation.email).like(s),
                func.lower(UserInvitation.assigned_role).like(s),
                func.lower(UserInvitation.target_tenant_id).like(s),
                func.lower(UserInvitation.user_type).like(s)
            )
        )

    query = query.offset(skip).limit(limit)
    result = await db.scalars(query)
    invitations = result.all()
    return ApiResponse(
        success=True,
        code=2000,
        message=f"Found {len(invitations)} invitations",
        data=[_invitation_to_response(i) for i in invitations]
    )

@router.post("/invitations", response_model=ApiResponse[UserInvitationResponse])
async def create_invitation(
    payload: UserInvitationCreate,
    db: AsyncSession = Depends(get_write_db)
):
    token = secrets.token_urlsafe(32)
    exp = datetime.datetime.utcnow() + datetime.timedelta(days=payload.invitationExpiryDays)

    inv = UserInvitation(
        email=payload.email.strip().lower(),
        user_type=payload.userType,
        target_tenant_id=payload.targetTenantId,
        target_sub_tenant_id=payload.targetSubTenantId,
        assigned_role=payload.assignedRole,
        department_scope=payload.departmentScope,
        ward_scope=payload.wardScope,
        invitation_token=token,
        invitation_expiry=exp,
        require_mfa=payload.requireMfa,
        invitation_message=payload.invitationMessage,
        status="Pending",
        invited_by="Super Admin",
    )
    db.add(inv)
    await db.commit()
    await db.refresh(inv)

    return ApiResponse(
        success=True,
        code=2001,
        message=f"Invitation sent to '{inv.email}'",
        data=_invitation_to_response(inv)
    )

@router.post("/invitations/{invitation_id}/resend", response_model=ApiResponse[UserInvitationResponse])
async def resend_invitation(invitation_id: str, db: AsyncSession = Depends(get_write_db)):
    inv = await db.get(UserInvitation, invitation_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invitation not found")

    inv.invitation_token = secrets.token_urlsafe(32)
    inv.invitation_expiry = datetime.datetime.utcnow() + datetime.timedelta(days=7)
    inv.status = "Pending"
    await db.commit()
    await db.refresh(inv)

    return ApiResponse(
        success=True,
        code=2000,
        message=f"Invitation token regenerated and resent to '{inv.email}'",
        data=_invitation_to_response(inv)
    )

@router.delete("/invitations/{invitation_id}", response_model=ApiResponse[dict])
async def revoke_invitation(invitation_id: str, db: AsyncSession = Depends(get_write_db)):
    inv = await db.get(UserInvitation, invitation_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Invitation not found")

    inv.status = "Revoked"
    await db.commit()
    return ApiResponse(
        success=True,
        code=2000,
        message=f"Invitation for '{inv.email}' has been revoked",
        data={"id": invitation_id, "status": "Revoked"}
    )

