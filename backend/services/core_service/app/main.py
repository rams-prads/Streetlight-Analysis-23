import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.redis import redis_client
from app.db.session import engine, Base, AsyncSessionLocal
from app.db.dev_schema import ensure_local_schema
from app.db.brand_rename import rename_legacy_brand
from app.db.seed import seed_initial_data
from app.api.v1.properties import router as properties_router
from app.api.v1.boundaries import router as boundaries_router
from app.api.v1.auth import router as auth_router
from app.api.v1.tenants import router as tenants_router
from app.api.v1.water import router as water_router
from app.db.water_seed import seed_water_data
from app.api.v1.ptx import router as ptx_router
from app.db.ptx_seed import seed_ptx_data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("urban-core")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Urban Core Service...")
    # Connect Redis
    await redis_client.connect()
    
    # A local SQLite file left by older code is set aside and rebuilt, so start-up never half-works on a stale schema
    ensure_local_schema(settings.write_db_url, Base.metadata)

    # Auto-create tables (for rapid development/docker start)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(rename_legacy_brand, Base.metadata)

        # Seed default GWMC data
        async with AsyncSessionLocal() as session:
            await seed_initial_data(session)
    except Exception as e:
        logger.warning(f"Database bootstrap warning: {e}")

    # Module 2 (Water) reference/demo data, in its own session so it never affects the core seed
    try:
        async with AsyncSessionLocal() as session:
            await seed_water_data(session)
    except Exception:
        logger.exception("Water module seed failed; the rest of the service continues.")

    # Module 1 (Property Tax) reference/demo data, in its own session for the same reason
    try:
        async with AsyncSessionLocal() as session:
            await seed_ptx_data(session)
    except Exception:
        logger.exception("Property tax module seed failed; the rest of the service continues.")

    yield

    # Cleanup
    await redis_client.close()
    await engine.dispose()
    logger.info("Urban Core Service shutdown complete.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://localhost:80", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.v1.admin import router as admin_router
from app.api.v1.ulbs import router as ulbs_router
from app.api.v1.tenant_lifecycle import router as tenant_lifecycle_router
from app.api.v1.modules import router as modules_router
from app.api.v1.subscriptions import router as subscriptions_router
from app.api.v1.delegation import router as delegation_router
from app.api.v1.iam import router as iam_router
from app.api.v1.iam_permissions import router as iam_permissions_router
from app.api.v1.security import router as security_router
from app.api.v1.audit_vault import router as audit_vault_router
from app.api.v1.fleet import router as fleet_router
from app.api.v1.backup_dr import router as backup_dr_router

# Include Routers
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(tenants_router, prefix=settings.API_V1_STR)
app.include_router(ulbs_router, prefix=settings.API_V1_STR)
app.include_router(tenant_lifecycle_router, prefix=settings.API_V1_STR)
app.include_router(subscriptions_router, prefix=settings.API_V1_STR)
app.include_router(delegation_router, prefix=settings.API_V1_STR)
app.include_router(modules_router, prefix=settings.API_V1_STR)
app.include_router(iam_router, prefix=settings.API_V1_STR)
app.include_router(iam_permissions_router, prefix=settings.API_V1_STR)
app.include_router(security_router, prefix=settings.API_V1_STR)
app.include_router(audit_vault_router, prefix=settings.API_V1_STR)
app.include_router(fleet_router, prefix=settings.API_V1_STR)
app.include_router(backup_dr_router, prefix=settings.API_V1_STR)
app.include_router(properties_router, prefix=settings.API_V1_STR)
app.include_router(boundaries_router, prefix=settings.API_V1_STR)
app.include_router(admin_router, prefix=settings.API_V1_STR)
app.include_router(water_router, prefix=settings.API_V1_STR)
app.include_router(ptx_router, prefix=settings.API_V1_STR)

@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "UP",
        "service": "urban-core-service",
        "tenant": settings.DEFAULT_TENANT_ID,
        "environment": settings.ENVIRONMENT
    }
