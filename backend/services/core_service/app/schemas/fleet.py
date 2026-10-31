import datetime
from typing import List, Optional, Any, Dict
from pydantic import field_validator
from app.schemas.tenant import CamelModel, ApiResponse


# 1. Overview System-Generated Metrics
class MicroserviceOverviewStats(CamelModel):
    totalServices: int = 0
    healthyServices: int = 0
    degradedServices: int = 0
    unavailableServices: int = 0
    averageResponseTimeMs: float = 0.0
    errorRatePct: float = 0.0
    cpuUtilisationPct: float = 0.0
    memoryUtilisationPct: float = 0.0
    totalPods: int = 0
    runningPods: int = 0
    totalQueues: int = 0
    activeDbConnections: int = 0


# 2. Service Registry Schemas
class MicroserviceRegistryResponse(CamelModel):
    id: str
    serviceCode: str
    serviceName: str
    serviceDescription: str
    serviceCategory: str
    serviceType: str
    environments: List[str] = []
    baseUrl: str
    healthCheckEndpoint: str
    healthCheckMethod: str
    healthCheckIntervalSeconds: int
    timeoutSeconds: int
    retryCount: int
    criticalityLevel: str
    monitoringEnabled: bool
    alertPolicy: Optional[str] = None
    status: str
    version: str
    region: str
    uptimePct: float
    avgLatencyMs: float
    errorRatePct: float
    cpuUsagePct: float
    memoryUsagePct: float
    createdAt: datetime.datetime
    updatedAt: Optional[datetime.datetime] = None


class MicroserviceRegisterPayload(CamelModel):
    serviceCode: str
    serviceName: str
    serviceDescription: str
    serviceCategory: str = "Core Platform"
    serviceType: str = "Stateless HTTP"
    environments: List[str] = ["Production"]
    baseUrl: str
    healthCheckEndpoint: str = "/health"
    healthCheckMethod: str = "GET"
    healthCheckIntervalSeconds: int = 15
    timeoutSeconds: int = 5
    retryCount: int = 3
    criticalityLevel: str = "P1 - High"
    monitoringEnabled: bool = True
    alertPolicy: Optional[str] = None
    version: str = "v1.0.0"
    region: str = "ap-south-1 (Hyderabad)"


class MicroserviceUpdatePayload(CamelModel):
    serviceName: Optional[str] = None
    serviceDescription: Optional[str] = None
    serviceCategory: Optional[str] = None
    serviceType: Optional[str] = None
    environments: Optional[List[str]] = None
    baseUrl: Optional[str] = None
    healthCheckEndpoint: Optional[str] = None
    healthCheckMethod: Optional[str] = None
    healthCheckIntervalSeconds: Optional[int] = None
    timeoutSeconds: Optional[int] = None
    retryCount: Optional[int] = None
    criticalityLevel: Optional[str] = None
    monitoringEnabled: Optional[bool] = None
    alertPolicy: Optional[str] = None
    version: Optional[str] = None
    region: Optional[str] = None


# 3. Pod Monitoring Schemas
class PodMonitoringResponse(CamelModel):
    id: str
    podName: str
    serviceCode: str
    serviceName: str
    cluster: str
    namespace: str
    deployment: str
    nodeName: str
    podStatus: str
    readinessStatus: str
    livenessStatus: str
    cpuMillicores: int
    memoryMb: int
    restartCount: int
    podUptime: str
    createdAt: datetime.datetime


# 4. Worker Queue Schemas
class WorkerQueueResponse(CamelModel):
    id: str
    queueName: str
    workerService: str
    queueType: str
    queueStatus: str
    pendingJobs: int
    processingJobs: int
    failedJobs: int
    avgProcessingTimeMs: float
    throughputJobsSec: float
    workerAvailability: int
    alertThreshold: int
    notificationRecipients: List[str] = []
    createdAt: datetime.datetime
    updatedAt: Optional[datetime.datetime] = None


class WorkerQueueUpdatePayload(CamelModel):
    queueStatus: Optional[str] = None
    alertThreshold: Optional[int] = None
    notificationRecipients: Optional[List[str]] = None


# 5. Database Connection Pool Schemas (Sanitized, No Passwords/Credentials)
class DatabaseConnectionPoolResponse(CamelModel):
    id: str
    poolName: str
    databaseCluster: str
    databaseName: str
    serviceName: str
    connectionStatus: str
    activeConnections: int
    idleConnections: int
    maxPoolSize: int
    connectionWaitTimeMs: float
    connectionFailures: int
    queryLatencyP95Ms: float
    alertThresholdPct: int
    createdAt: datetime.datetime
    updatedAt: Optional[datetime.datetime] = None

