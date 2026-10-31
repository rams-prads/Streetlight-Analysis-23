export interface MicroserviceOverviewStats {
  totalServices: number;
  healthyServices: number;
  degradedServices: number;
  unavailableServices: number;
  averageResponseTimeMs: number;
  errorRatePct: number;
  cpuUtilisationPct: number;
  memoryUtilisationPct: number;
  totalPods: number;
  runningPods: number;
  totalQueues: number;
  activeDbConnections: number;
}

export interface MicroserviceRegistryItem {
  id: string;
  serviceCode: string;
  serviceName: string;
  serviceDescription: string;
  serviceCategory: 'Core Platform' | 'Domain Microservice' | 'Worker Daemon' | 'Integration Gateway' | 'Data & Analytics' | string;
  serviceType: 'Stateless HTTP' | 'Async Worker' | 'Event Streamer' | 'Stateful Cache' | string;
  environments: string[];
  baseUrl: string;
  healthCheckEndpoint: string;
  healthCheckMethod: 'GET' | 'POST' | 'HEAD' | string;
  healthCheckIntervalSeconds: number;
  timeoutSeconds: number;
  retryCount: number;
  criticalityLevel: 'P0 - Critical' | 'P1 - High' | 'P2 - Normal' | 'P3 - Low' | string;
  monitoringEnabled: boolean;
  alertPolicy?: string | null;
  status: 'Healthy' | 'Degraded' | 'Unavailable' | string;
  version: string;
  region: string;
  uptimePct: number;
  avgLatencyMs: number;
  errorRatePct: number;
  cpuUsagePct: number;
  memoryUsagePct: number;
  createdAt: string;
  updatedAt?: string | null;
}

export interface MicroserviceRegisterPayload {
  serviceCode: string;
  serviceName: string;
  serviceDescription: string;
  serviceCategory: string;
  serviceType: string;
  environments: string[];
  baseUrl: string;
  healthCheckEndpoint: string;
  healthCheckMethod: string;
  healthCheckIntervalSeconds: number;
  timeoutSeconds: number;
  retryCount: number;
  criticalityLevel: string;
  monitoringEnabled: boolean;
  alertPolicy?: string | null;
  version: string;
  region: string;
}

export interface PodMonitoringItem {
  id: string;
  podName: string;
  serviceCode: string;
  serviceName: string;
  cluster: string;
  namespace: string;
  deployment: string;
  nodeName: string;
  podStatus: 'Running' | 'Pending' | 'CrashLoopBackOff' | 'Terminating' | string;
  readinessStatus: string;
  livenessStatus: string;
  cpuMillicores: number;
  memoryMb: number;
  restartCount: number;
  podUptime: string;
  createdAt: string;
}

export interface WorkerQueueItem {
  id: string;
  queueName: string;
  workerService: string;
  queueType: 'Celery / Redis' | 'Kafka Topic' | 'RabbitMQ' | 'Cloud PubSub' | string;
  queueStatus: 'Optimal' | 'Backlogged' | 'Stalled' | 'Paused' | string;
  pendingJobs: number;
  processingJobs: number;
  failedJobs: number;
  avgProcessingTimeMs: number;
  throughputJobsSec: number;
  workerAvailability: number;
  alertThreshold: number;
  notificationRecipients: string[];
  createdAt: string;
  updatedAt?: string | null;
}

export interface DatabaseConnectionPoolItem {
  id: string;
  poolName: string;
  databaseCluster: string;
  databaseName: string;
  serviceName: string;
  connectionStatus: 'Optimal' | 'Congested' | 'Pool Exhausted' | 'Degraded' | string;
  activeConnections: number;
  idleConnections: number;
  maxPoolSize: number;
  connectionWaitTimeMs: number;
  connectionFailures: number;
  queryLatencyP95Ms: number;
  alertThresholdPct: number;
  createdAt: string;
  updatedAt?: string | null;
}

