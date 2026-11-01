import datetime
import uuid
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_, desc

from app.db.session import get_read_db, get_write_db
from app.db.models import (
    MicroserviceRegistryModel,
    PodMonitoringModel,
    WorkerQueueModel,
    DatabaseConnectionPoolModel,
)
from app.core.auth import get_current_user
from app.schemas.tenant import ApiResponse
from app.schemas.fleet import (
    MicroserviceOverviewStats,
    MicroserviceRegistryResponse,
    MicroserviceRegisterPayload,
    MicroserviceUpdatePayload,
    PodMonitoringResponse,
    WorkerQueueResponse,
    WorkerQueueUpdatePayload,
    DatabaseConnectionPoolResponse,
)

router = APIRouter(prefix="/fleet/cluster", tags=["ADM-O01 Platform Fleet & Microservice Cluster Health"])


async def _ensure_fleet_seeded(db: AsyncSession):
    # Check if services exist
    svc_count_res = await db.execute(select(func.count(MicroserviceRegistryModel.id)))
    svc_count = svc_count_res.scalar() or 0

    if svc_count == 0:
        seed_services = [
            {
                "service_code": "CORE-SVC",
                "service_name": "Urban Core Municipal Service",
                "service_description": "Central FastAPI master orchestration service managing tenancy, Level 1 state subscriptions, and Level 2 city jurisdictions.",
                "service_category": "Core Platform",
                "service_type": "Stateless HTTP",
                "environments": ["Production", "Staging", "Dev"],
                "base_url": "http://core-service.suvidha.internal:8000",
                "health_check_endpoint": "/health",
                "health_check_method": "GET",
                "health_check_interval_seconds": 10,
                "timeout_seconds": 3,
                "retry_count": 3,
                "criticality_level": "P0 - Critical",
                "status": "Healthy",
                "version": "v2.4.2",
                "uptime_pct": 99.99,
                "avg_latency_ms": 18.4,
                "error_rate_pct": 0.01,
                "cpu_usage_pct": 32.5,
                "memory_usage_pct": 54.0,
            },
            {
                "service_code": "AUTH-SVC",
                "service_name": "Keycloak IAM & OIDC Broker Gateway",
                "service_description": "Central identity federation cluster handling MeriPehchan, Aadhaar e-Pramaan OTP, and Jan Parichay SSO assertions.",
                "service_category": "Core Platform",
                "service_type": "Stateless HTTP",
                "environments": ["Production", "Staging"],
                "base_url": "https://auth.suvidha.gov.in",
                "health_check_endpoint": "/health/ready",
                "health_check_method": "GET",
                "health_check_interval_seconds": 15,
                "timeout_seconds": 4,
                "retry_count": 3,
                "criticality_level": "P0 - Critical",
                "status": "Healthy",
                "version": "v24.0.3",
                "uptime_pct": 99.99,
                "avg_latency_ms": 14.2,
                "error_rate_pct": 0.00,
                "cpu_usage_pct": 28.1,
                "memory_usage_pct": 62.4,
            },
            {
                "service_code": "BILLING-SVC",
                "service_name": "Revenue Demand & Payment Engine",
                "service_description": "Asynchronous municipal billing calculations, quarterly demand notices, payment gateway reconciliations, and BBPS integrations.",
                "service_category": "Domain Microservice",
                "service_type": "Stateless HTTP",
                "environments": ["Production", "Staging"],
                "base_url": "http://billing-service.suvidha.internal:8080",
                "health_check_endpoint": "/actuator/health",
                "health_check_method": "GET",
                "health_check_interval_seconds": 15,
                "timeout_seconds": 5,
                "retry_count": 3,
                "criticality_level": "P1 - High",
                "status": "Healthy",
                "version": "v3.1.0",
                "uptime_pct": 99.95,
                "avg_latency_ms": 36.8,
                "error_rate_pct": 0.04,
                "cpu_usage_pct": 44.0,
                "memory_usage_pct": 58.2,
            },
            {
                "service_code": "GIS-SPATIAL-SVC",
                "service_name": "GIS Geospatial & Cadastral Engine",
                "service_description": "PostGIS vector boundary processor, GIS parcel geo-fencing, drone orthomosaic imagery tiler, and property tax shapefile overlay.",
                "service_category": "Domain Microservice",
                "service_type": "Stateless HTTP",
                "environments": ["Production", "Staging"],
                "base_url": "http://gis-service.suvidha.internal:8082",
                "health_check_endpoint": "/api/v1/health",
                "health_check_method": "GET",
                "health_check_interval_seconds": 30,
                "timeout_seconds": 10,
                "retry_count": 2,
                "criticality_level": "P2 - Normal",
                "status": "Healthy",
                "version": "v1.8.5",
                "uptime_pct": 99.88,
                "avg_latency_ms": 84.1,
                "error_rate_pct": 0.08,
                "cpu_usage_pct": 58.6,
                "memory_usage_pct": 71.3,
            },
            {
                "service_code": "NOTIF-DISPATCH-SVC",
                "service_name": "Citizen SMS, WhatsApp & Push Gateway",
                "service_description": "High-throughput statutory notification router delivering tax demand alerts, grievance tracking, and citizen OTPs via CDAC NIC SMS.",
                "service_category": "Worker Daemon",
                "service_type": "Async Worker",
                "environments": ["Production", "Staging", "Dev"],
                "base_url": "http://notif-worker.suvidha.internal:9090",
                "health_check_endpoint": "/healthz",
                "health_check_method": "GET",
                "health_check_interval_seconds": 20,
                "timeout_seconds": 5,
                "retry_count": 4,
                "criticality_level": "P1 - High",
                "status": "Healthy",
                "version": "v2.0.1",
                "uptime_pct": 99.97,
                "avg_latency_ms": 22.0,
                "error_rate_pct": 0.02,
                "cpu_usage_pct": 19.4,
                "memory_usage_pct": 38.0,
            },
            {
                "service_code": "AUDIT-VAULT-SVC",
                "service_name": "Immutable Audit Vault WORM Daemon",
                "service_description": "Cryptographic hash chaining engine validating CERT-In and CAG statutory audit ledgers with SHA-256 HMAC digital signatures.",
                "service_category": "Core Platform",
                "service_type": "Event Streamer",
                "environments": ["Production"],
                "base_url": "http://audit-vault.suvidha.internal:8000",
                "health_check_endpoint": "/compliance/audit/stats",
                "health_check_method": "GET",
                "health_check_interval_seconds": 15,
                "timeout_seconds": 5,
                "retry_count": 3,
                "criticality_level": "P0 - Critical",
                "status": "Healthy",
                "version": "v1.0.0",
                "uptime_pct": 100.0,
                "avg_latency_ms": 12.5,
                "error_rate_pct": 0.00,
                "cpu_usage_pct": 15.2,
                "memory_usage_pct": 42.1,
            },
            {
                "service_code": "BBPS-INTEGRATION-SVC",
                "service_name": "Bharat BillPay (BBPS) NPCI Gateway",
                "service_description": "Standardized NPCI BBPS central payment gateway connector for utility bills, water charges, and property tax instant collections.",
                "service_category": "Integration Gateway",
                "service_type": "Stateless HTTP",
                "environments": ["Production"],
                "base_url": "http://bbps-gateway.suvidha.internal:8085",
                "health_check_endpoint": "/ping",
                "health_check_method": "GET",
                "health_check_interval_seconds": 15,
                "timeout_seconds": 4,
                "retry_count": 3,
                "criticality_level": "P1 - High",
                "status": "Degraded",
                "version": "v1.4.2",
                "uptime_pct": 98.60,
                "avg_latency_ms": 145.2,
                "error_rate_pct": 1.45,
                "cpu_usage_pct": 62.1,
                "memory_usage_pct": 68.4,
            },
            {
                "service_code": "ANALYTICS-ETL-SVC",
                "service_name": "Statewide Municipal KPI Aggregator",
                "service_description": "Nightly batch aggregator compiling state-wide revenue benchmarks, collection efficiency, and departmental SLA compliance metrics.",
                "service_category": "Data & Analytics",
                "service_type": "Async Worker",
                "environments": ["Production", "Staging"],
                "base_url": "http://analytics-etl.suvidha.internal:9000",
                "health_check_endpoint": "/status",
                "health_check_method": "GET",
                "health_check_interval_seconds": 60,
                "timeout_seconds": 15,
                "retry_count": 2,
                "criticality_level": "P3 - Low",
                "status": "Healthy",
                "version": "v2.1.0",
                "uptime_pct": 99.70,
                "avg_latency_ms": 210.0,
                "error_rate_pct": 0.05,
                "cpu_usage_pct": 74.5,
                "memory_usage_pct": 82.0,
            },
        ]

        for s in seed_services:
            m = MicroserviceRegistryModel(
                service_code=s["service_code"],
                service_name=s["service_name"],
                service_description=s["service_description"],
                service_category=s["service_category"],
                service_type=s["service_type"],
                environments=s["environments"],
                base_url=s["base_url"],
                health_check_endpoint=s["health_check_endpoint"],
                health_check_method=s["health_check_method"],
                health_check_interval_seconds=s["health_check_interval_seconds"],
                timeout_seconds=s["timeout_seconds"],
                retry_count=s["retry_count"],
                criticality_level=s["criticality_level"],
                status=s["status"],
                version=s["version"],
                uptime_pct=s["uptime_pct"],
                avg_latency_ms=s["avg_latency_ms"],
                error_rate_pct=s["error_rate_pct"],
                cpu_usage_pct=s["cpu_usage_pct"],
                memory_usage_pct=s["memory_usage_pct"],
            )
            db.add(m)
        await db.commit()

    # Check pods
    pod_count_res = await db.execute(select(func.count(PodMonitoringModel.id)))
    pod_count = pod_count_res.scalar() or 0

    if pod_count == 0:
        seed_pods = [
            {"pod_name": "suvidha-core-7f8d9b-a1b2", "service_code": "CORE-SVC", "service_name": "Urban Core Municipal Service", "deployment": "suvidha-core-deploy", "node_name": "gke-prod-pool-01-node-7b", "cpu_millicores": 290, "memory_mb": 512, "restart_count": 0, "pod_uptime": "18d 4h"},
            {"pod_name": "suvidha-core-7f8d9b-c3d4", "service_code": "CORE-SVC", "service_name": "Urban Core Municipal Service", "deployment": "suvidha-core-deploy", "node_name": "gke-prod-pool-02-node-9a", "cpu_millicores": 310, "memory_mb": 524, "restart_count": 0, "pod_uptime": "18d 4h"},
            {"pod_name": "suvidha-auth-64b81c-x1y2", "service_code": "AUTH-SVC", "service_name": "Keycloak IAM & OIDC Broker Gateway", "deployment": "suvidha-auth-deploy", "node_name": "gke-prod-pool-01-node-7b", "cpu_millicores": 250, "memory_mb": 1024, "restart_count": 0, "pod_uptime": "24d 11h"},
            {"pod_name": "suvidha-auth-64b81c-w3z4", "service_code": "AUTH-SVC", "service_name": "Keycloak IAM & OIDC Broker Gateway", "deployment": "suvidha-auth-deploy", "node_name": "gke-prod-pool-03-node-4f", "cpu_millicores": 265, "memory_mb": 1048, "restart_count": 0, "pod_uptime": "24d 11h"},
            {"pod_name": "billing-engine-5d9c2a-m7n8", "service_code": "BILLING-SVC", "service_name": "Revenue Demand & Payment Engine", "deployment": "suvidha-billing-deploy", "node_name": "gke-prod-pool-02-node-9a", "cpu_millicores": 420, "memory_mb": 768, "restart_count": 1, "pod_uptime": "12d 8h"},
            {"pod_name": "gis-spatial-3b8e7f-k9l0", "service_code": "GIS-SPATIAL-SVC", "service_name": "GIS Geospatial & Cadastral Engine", "deployment": "suvidha-gis-deploy", "node_name": "gke-prod-pool-03-node-4f", "cpu_millicores": 580, "memory_mb": 1536, "restart_count": 0, "pod_uptime": "9d 2h"},
            {"pod_name": "notif-dispatcher-2a1c4e-p5q6", "service_code": "NOTIF-DISPATCH-SVC", "service_name": "Citizen SMS, WhatsApp & Push Gateway", "deployment": "suvidha-notif-deploy", "node_name": "gke-prod-pool-01-node-7b", "cpu_millicores": 180, "memory_mb": 384, "restart_count": 0, "pod_uptime": "30d 1h"},
            {"pod_name": "bbps-gateway-9f1e3c-r7s8", "service_code": "BBPS-INTEGRATION-SVC", "service_name": "Bharat BillPay (BBPS) NPCI Gateway", "deployment": "suvidha-bbps-deploy", "node_name": "gke-prod-pool-02-node-9a", "cpu_millicores": 610, "memory_mb": 640, "restart_count": 2, "pod_uptime": "3d 14h"},
        ]
        for p in seed_pods:
            pm = PodMonitoringModel(
                pod_name=p["pod_name"],
                service_code=p["service_code"],
                service_name=p["service_name"],
                deployment=p["deployment"],
                node_name=p["node_name"],
                cpu_millicores=p["cpu_millicores"],
                memory_mb=p["memory_mb"],
                restart_count=p["restart_count"],
                pod_uptime=p["pod_uptime"],
            )
            db.add(pm)
        await db.commit()

    # Check worker queues
    q_count_res = await db.execute(select(func.count(WorkerQueueModel.id)))
    q_count = q_count_res.scalar() or 0

    if q_count == 0:
        seed_queues = [
            {"queue_name": "tax-demand-notice-gen", "worker_service": "billing-worker", "queue_type": "Celery / Redis", "pending_jobs": 42, "processing_jobs": 12, "failed_jobs": 0, "avg_processing_time_ms": 145.0, "throughput_jobs_sec": 42.0, "worker_availability": 8},
            {"queue_name": "sms-citizen-otp-outbox", "worker_service": "notif-dispatcher", "queue_type": "Kafka Topic", "pending_jobs": 6, "processing_jobs": 24, "failed_jobs": 2, "avg_processing_time_ms": 28.5, "throughput_jobs_sec": 120.0, "worker_availability": 12},
            {"queue_name": "gis-cadastral-raster-tile", "worker_service": "gis-spatial-worker", "queue_type": "RabbitMQ", "pending_jobs": 84, "processing_jobs": 4, "failed_jobs": 1, "avg_processing_time_ms": 840.0, "throughput_jobs_sec": 8.5, "worker_availability": 4},
            {"queue_name": "cag-statutory-audit-stream", "worker_service": "audit-vault-worker", "queue_type": "Cloud PubSub", "pending_jobs": 0, "processing_jobs": 8, "failed_jobs": 0, "avg_processing_time_ms": 18.0, "throughput_jobs_sec": 65.0, "worker_availability": 6},
        ]
        for q in seed_queues:
            qm = WorkerQueueModel(
                queue_name=q["queue_name"],
                worker_service=q["worker_service"],
                queue_type=q["queue_type"],
                pending_jobs=q["pending_jobs"],
                processing_jobs=q["processing_jobs"],
                failed_jobs=q["failed_jobs"],
                avg_processing_time_ms=q["avg_processing_time_ms"],
                throughput_jobs_sec=q["throughput_jobs_sec"],
                worker_availability=q["worker_availability"],
            )
            db.add(qm)
        await db.commit()

    # Check DB Connection Pools
    pool_count_res = await db.execute(select(func.count(DatabaseConnectionPoolModel.id)))
    pool_count = pool_count_res.scalar() or 0

    if pool_count == 0:
        seed_pools = [
            {"pool_name": "suvidha-core-primary-write-pool", "database_cluster": "pg-primary-cluster-ha (Primary)", "database_name": "urban_erp_core", "service_name": "Urban Core Service", "active_connections": 22, "idle_connections": 14, "max_pool_size": 60, "connection_wait_time_ms": 1.4, "query_latency_p95_ms": 6.8},
            {"pool_name": "suvidha-core-readonly-replica-pool", "database_cluster": "pg-replica-south (Read Replica)", "database_name": "urban_erp_core", "service_name": "Urban Core Service", "active_connections": 34, "idle_connections": 26, "max_pool_size": 100, "connection_wait_time_ms": 0.8, "query_latency_p95_ms": 4.2},
            {"pool_name": "billing-ptx-dedicated-pool", "database_cluster": "pg-primary-cluster-ha (Primary)", "database_name": "urban_ptx_billing", "service_name": "Revenue Billing Engine", "active_connections": 18, "idle_connections": 12, "max_pool_size": 50, "connection_wait_time_ms": 2.1, "query_latency_p95_ms": 11.4},
            {"pool_name": "valkey-redis-sentinel-cache-pool", "database_cluster": "valkey-redis-sentinel (In-Memory)", "database_name": "cache_db_0", "service_name": "Platform Redis Cache", "active_connections": 48, "idle_connections": 52, "max_pool_size": 150, "connection_wait_time_ms": 0.2, "query_latency_p95_ms": 0.8},
        ]
        for p in seed_pools:
            pm = DatabaseConnectionPoolModel(
                pool_name=p["pool_name"],
                database_cluster=p["database_cluster"],
                database_name=p["database_name"],
                service_name=p["service_name"],
                active_connections=p["active_connections"],
                idle_connections=p["idle_connections"],
                max_pool_size=p["max_pool_size"],
                connection_wait_time_ms=p["connection_wait_time_ms"],
                query_latency_p95_ms=p["query_latency_p95_ms"],
            )
            db.add(pm)
        await db.commit()


# 1. Cluster Overview System-Generated Metrics
@router.get("/stats", response_model=ApiResponse[MicroserviceOverviewStats])
async def get_cluster_stats(
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    await _ensure_fleet_seeded(db)

    # Services metrics
    total_svc_res = await db.execute(select(func.count(MicroserviceRegistryModel.id)))
    total_services = total_svc_res.scalar() or 0

    healthy_res = await db.execute(
        select(func.count(MicroserviceRegistryModel.id)).where(MicroserviceRegistryModel.status == "Healthy")
    )
    healthy_services = healthy_res.scalar() or 0

    degraded_res = await db.execute(
        select(func.count(MicroserviceRegistryModel.id)).where(MicroserviceRegistryModel.status == "Degraded")
    )
    degraded_services = degraded_res.scalar() or 0

    unavail_res = await db.execute(
        select(func.count(MicroserviceRegistryModel.id)).where(MicroserviceRegistryModel.status == "Unavailable")
    )
    unavailable_services = unavail_res.scalar() or 0

    avg_lat_res = await db.execute(select(func.avg(MicroserviceRegistryModel.avg_latency_ms)))
    avg_latency = float(avg_lat_res.scalar() or 24.5)

    err_rate_res = await db.execute(select(func.avg(MicroserviceRegistryModel.error_rate_pct)))
    avg_error_rate = float(err_rate_res.scalar() or 0.05)

    cpu_res = await db.execute(select(func.avg(MicroserviceRegistryModel.cpu_usage_pct)))
    avg_cpu = float(cpu_res.scalar() or 38.2)

    mem_res = await db.execute(select(func.avg(MicroserviceRegistryModel.memory_usage_pct)))
    avg_mem = float(mem_res.scalar() or 59.4)

    # Pods
    total_pods_res = await db.execute(select(func.count(PodMonitoringModel.id)))
    total_pods = total_pods_res.scalar() or 0

    running_pods_res = await db.execute(
        select(func.count(PodMonitoringModel.id)).where(PodMonitoringModel.pod_status == "Running")
    )
    running_pods = running_pods_res.scalar() or 0

    # Queues & DB
    q_res = await db.execute(select(func.count(WorkerQueueModel.id)))
    total_queues = q_res.scalar() or 0

    db_res = await db.execute(select(func.sum(DatabaseConnectionPoolModel.active_connections)))
    active_db_conn = int(db_res.scalar() or 0)

    return ApiResponse(
        success=True,
        data=MicroserviceOverviewStats(
            totalServices=total_services,
            healthyServices=healthy_services,
            degradedServices=degraded_services,
            unavailableServices=unavailable_services,
            averageResponseTimeMs=round(avg_latency, 1),
            errorRatePct=round(avg_error_rate, 2),
            cpuUtilisationPct=round(avg_cpu, 1),
            memoryUtilisationPct=round(avg_mem, 1),
            totalPods=total_pods,
            runningPods=running_pods,
            totalQueues=total_queues,
            activeDbConnections=active_db_conn,
        ),
    )


# 2. Service Registry Endpoints
@router.get("/services", response_model=ApiResponse[List[MicroserviceRegistryResponse]])
async def list_microservices(
    search: Optional[str] = Query(None),
    environment: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    region: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    await _ensure_fleet_seeded(db)

    stmt = select(MicroserviceRegistryModel).order_by(MicroserviceRegistryModel.service_code.asc())

    if category and category != "ALL":
        stmt = stmt.where(MicroserviceRegistryModel.service_category == category)
    if status_filter and status_filter != "ALL":
        stmt = stmt.where(MicroserviceRegistryModel.status == status_filter)
    if region and region != "ALL":
        stmt = stmt.where(MicroserviceRegistryModel.region == region)

    if search and search.strip():
        s = f"%{search.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(MicroserviceRegistryModel.service_code).like(s),
                func.lower(MicroserviceRegistryModel.service_name).like(s),
                func.lower(MicroserviceRegistryModel.service_description).like(s),
            )
        )

    stmt = stmt.offset(skip).limit(limit)
    res = await db.execute(stmt)
    records = res.scalars().all()

    items = []
    for r in records:
        if environment and environment != "ALL" and environment not in (r.environments or []):
            continue

        items.append(
            MicroserviceRegistryResponse(
                id=r.id,
                serviceCode=r.service_code,
                serviceName=r.service_name,
                serviceDescription=r.service_description,
                serviceCategory=r.service_category,
                serviceType=r.service_type,
                environments=r.environments or [],
                baseUrl=r.base_url,
                healthCheckEndpoint=r.health_check_endpoint,
                healthCheckMethod=r.health_check_method,
                healthCheckIntervalSeconds=r.health_check_interval_seconds,
                timeoutSeconds=r.timeout_seconds,
                retryCount=r.retry_count,
                criticalityLevel=r.criticality_level,
                monitoringEnabled=r.monitoring_enabled,
                alertPolicy=r.alert_policy,
                status=r.status,
                version=r.version,
                region=r.region,
                uptimePct=r.uptime_pct,
                avgLatencyMs=r.avg_latency_ms,
                errorRatePct=r.error_rate_pct,
                cpuUsagePct=r.cpu_usage_pct,
                memoryUsagePct=r.memory_usage_pct,
                createdAt=r.created_at,
                updatedAt=r.updated_at,
            )
        )

    return ApiResponse(success=True, message=f"Retrieved {len(items)} microservices", data=items)


@router.post("/services", response_model=ApiResponse[MicroserviceRegistryResponse])
async def register_microservice(
    payload: MicroserviceRegisterPayload,
    db: AsyncSession = Depends(get_write_db),
    user: dict = Depends(get_current_user),
):
    code_up = payload.serviceCode.strip().upper()
    dup_res = await db.execute(
        select(MicroserviceRegistryModel).where(MicroserviceRegistryModel.service_code == code_up)
    )
    if dup_res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Service with code '{code_up}' is already registered.")

    new_svc = MicroserviceRegistryModel(
        service_code=code_up,
        service_name=payload.serviceName.strip(),
        service_description=payload.serviceDescription.strip(),
        service_category=payload.serviceCategory,
        service_type=payload.serviceType,
        environments=payload.environments,
        base_url=payload.baseUrl.strip(),
        health_check_endpoint=payload.healthCheckEndpoint.strip(),
        health_check_method=payload.healthCheckMethod,
        health_check_interval_seconds=payload.healthCheckIntervalSeconds,
        timeout_seconds=payload.timeoutSeconds,
        retry_count=payload.retryCount,
        criticality_level=payload.criticalityLevel,
        monitoring_enabled=payload.monitoringEnabled,
        alert_policy=payload.alertPolicy,
        version=payload.version,
        region=payload.region,
        status="Healthy",
    )
    db.add(new_svc)
    await db.commit()
    await db.refresh(new_svc)

    return ApiResponse(
        success=True,
        message=f"Microservice '{code_up}' registered successfully.",
        data=MicroserviceRegistryResponse(
            id=new_svc.id,
            serviceCode=new_svc.service_code,
            serviceName=new_svc.service_name,
            serviceDescription=new_svc.service_description,
            serviceCategory=new_svc.service_category,
            serviceType=new_svc.service_type,
            environments=new_svc.environments or [],
            baseUrl=new_svc.base_url,
            healthCheckEndpoint=new_svc.health_check_endpoint,
            healthCheckMethod=new_svc.health_check_method,
            healthCheckIntervalSeconds=new_svc.health_check_interval_seconds,
            timeoutSeconds=new_svc.timeout_seconds,
            retryCount=new_svc.retry_count,
            criticalityLevel=new_svc.criticality_level,
            monitoringEnabled=new_svc.monitoring_enabled,
            alertPolicy=new_svc.alert_policy,
            status=new_svc.status,
            version=new_svc.version,
            region=new_svc.region,
            uptimePct=new_svc.uptime_pct,
            avgLatencyMs=new_svc.avg_latency_ms,
            errorRatePct=new_svc.error_rate_pct,
            cpuUsagePct=new_svc.cpu_usage_pct,
            memoryUsagePct=new_svc.memory_usage_pct,
            createdAt=new_svc.created_at,
            updatedAt=new_svc.updated_at,
        ),
    )


# 3. Pod Monitoring Endpoint
@router.get("/pods", response_model=ApiResponse[List[PodMonitoringResponse]])
async def list_pods(
    cluster: Optional[str] = Query(None),
    namespace: Optional[str] = Query(None),
    deployment: Optional[str] = Query(None),
    pod_name: Optional[str] = Query(None),
    service_code: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    node_name: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    await _ensure_fleet_seeded(db)

    stmt = select(PodMonitoringModel).order_by(PodMonitoringModel.pod_name.asc())

    if cluster and cluster != "ALL":
        stmt = stmt.where(PodMonitoringModel.cluster == cluster)
    if namespace and namespace != "ALL":
        stmt = stmt.where(PodMonitoringModel.namespace == namespace)
    if deployment and deployment != "ALL":
        stmt = stmt.where(PodMonitoringModel.deployment == deployment)
    if service_code and service_code != "ALL":
        stmt = stmt.where(PodMonitoringModel.service_code == service_code)
    if status_filter and status_filter != "ALL":
        stmt = stmt.where(PodMonitoringModel.pod_status == status_filter)
    if node_name and node_name != "ALL":
        stmt = stmt.where(PodMonitoringModel.node_name == node_name)
    if pod_name and pod_name.strip():
        stmt = stmt.where(func.lower(PodMonitoringModel.pod_name).like(f"%{pod_name.strip().lower()}%"))

    res = await db.execute(stmt)
    records = res.scalars().all()

    return ApiResponse(
        success=True,
        data=[
            PodMonitoringResponse(
                id=r.id,
                podName=r.pod_name,
                serviceCode=r.service_code,
                serviceName=r.service_name,
                cluster=r.cluster,
                namespace=r.namespace,
                deployment=r.deployment,
                nodeName=r.node_name,
                podStatus=r.pod_status,
                readinessStatus=r.readiness_status,
                livenessStatus=r.liveness_status,
                cpuMillicores=r.cpu_millicores,
                memoryMb=r.memory_mb,
                restartCount=r.restart_count,
                podUptime=r.pod_uptime,
                createdAt=r.created_at,
            )
            for r in records
        ],
    )


# 4. Worker Queues Endpoint
@router.get("/queues", response_model=ApiResponse[List[WorkerQueueResponse]])
async def list_worker_queues(
    queue_name: Optional[str] = Query(None),
    worker_service: Optional[str] = Query(None),
    queue_type: Optional[str] = Query(None),
    queue_status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    await _ensure_fleet_seeded(db)

    stmt = select(WorkerQueueModel).order_by(WorkerQueueModel.queue_name.asc())

    if queue_name and queue_name != "ALL":
        stmt = stmt.where(WorkerQueueModel.queue_name == queue_name)
    if worker_service and worker_service != "ALL":
        stmt = stmt.where(WorkerQueueModel.worker_service == worker_service)
    if queue_type and queue_type != "ALL":
        stmt = stmt.where(WorkerQueueModel.queue_type == queue_type)
    if queue_status and queue_status != "ALL":
        stmt = stmt.where(WorkerQueueModel.queue_status == queue_status)

    res = await db.execute(stmt)
    records = res.scalars().all()

    return ApiResponse(
        success=True,
        data=[
            WorkerQueueResponse(
                id=r.id,
                queueName=r.queue_name,
                workerService=r.worker_service,
                queueType=r.queue_type,
                queueStatus=r.queue_status,
                pendingJobs=r.pending_jobs,
                processingJobs=r.processing_jobs,
                failedJobs=r.failed_jobs,
                avgProcessingTimeMs=r.avg_processing_time_ms,
                throughputJobsSec=r.throughput_jobs_sec,
                workerAvailability=r.worker_availability,
                alertThreshold=r.alert_threshold,
                notificationRecipients=r.notification_recipients or [],
                createdAt=r.created_at,
                updatedAt=r.updated_at,
            )
            for r in records
        ],
    )


# 5. Database Connections Monitoring Endpoint (Sanitized, No Passwords/Secrets)
@router.get("/db-pools", response_model=ApiResponse[List[DatabaseConnectionPoolResponse]])
async def list_database_connection_pools(
    database_cluster: Optional[str] = Query(None),
    database_name: Optional[str] = Query(None),
    service_name: Optional[str] = Query(None),
    connection_status: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_read_db),
    user: dict = Depends(get_current_user),
):
    await _ensure_fleet_seeded(db)

    stmt = select(DatabaseConnectionPoolModel).order_by(DatabaseConnectionPoolModel.pool_name.asc())

    if database_cluster and database_cluster != "ALL":
        stmt = stmt.where(DatabaseConnectionPoolModel.database_cluster == database_cluster)
    if database_name and database_name != "ALL":
        stmt = stmt.where(DatabaseConnectionPoolModel.database_name == database_name)
    if service_name and service_name != "ALL":
        stmt = stmt.where(DatabaseConnectionPoolModel.service_name == service_name)
    if connection_status and connection_status != "ALL":
        stmt = stmt.where(DatabaseConnectionPoolModel.connection_status == connection_status)

    res = await db.execute(stmt)
    records = res.scalars().all()

    return ApiResponse(
        success=True,
        data=[
            DatabaseConnectionPoolResponse(
                id=r.id,
                poolName=r.pool_name,
                databaseCluster=r.database_cluster,
                databaseName=r.database_name,
                serviceName=r.service_name,
                connectionStatus=r.connection_status,
                activeConnections=r.active_connections,
                idleConnections=r.idle_connections,
                maxPoolSize=r.max_pool_size,
                connectionWaitTimeMs=r.connection_wait_time_ms,
                connectionFailures=r.connection_failures,
                queryLatencyP95Ms=r.query_latency_p95_ms,
                alertThresholdPct=r.alert_threshold_pct,
                createdAt=r.created_at,
                updatedAt=r.updated_at,
            )
            for r in records
        ],
    )

