export interface ApiResponse<T = any> {
  success: boolean;
  code?: number;
  message?: string;
  data: T;
}

export interface ComponentCatalogueItem {
  componentId: string;
  parentModuleCode: string;
  name: string;
  code: string;
  description: string;
  componentType: 'Process' | 'Service' | 'UI View' | 'Report' | 'Workflow';
  routePath?: string;
  frontendPermissionKey: string;
  backendApiPermissionKey: string;
  supportedActions: string[];
  dependencies?: string[];
  status: 'Draft' | 'Published' | 'Deprecated';
  displayOrder: number;
  createdAt?: string;
  updatedAt?: string;
}

export interface ComponentCreatePayload {
  componentId?: string;
  parentModuleCode: string;
  name: string;
  code: string;
  description: string;
  componentType: string;
  routePath?: string;
  frontendPermissionKey?: string;
  backendApiPermissionKey?: string;
  supportedActions: string[];
  dependencies?: string[];
  status: string;
  displayOrder: number;
}

export interface ModuleCatalogueItem {
  moduleId: string;
  name: string;
  code: string;
  description: string;
  category: string;
  icon?: string;
  displayOrder: number;
  moduleVersion: string;
  status: 'Draft' | 'Published' | 'Deprecated';
  dependencies?: string[];
  minimumPlatformVersion?: string;
  documentationUrl?: string;
  effectiveFrom?: string;
  totalComponents?: number;
  components?: ComponentCatalogueItem[];
  createdAt?: string;
  updatedAt?: string;
}

export interface ModuleCreatePayload {
  moduleId?: string;
  name: string;
  code: string;
  description: string;
  category: string;
  icon?: string;
  displayOrder: number;
  moduleVersion: string;
  status: string;
  dependencies?: string[];
  minimumPlatformVersion?: string;
  documentationUrl?: string;
  effectiveFrom?: string;
}

export interface ModuleChangeHistoryItem {
  id: string;
  entityType: 'MODULE' | 'COMPONENT';
  entityCode: string;
  action: string;
  performedBy: string;
  timestamp: string;
  details?: string;
}

export interface CatalogueExportData {
  exportedAt: string;
  totalModules: number;
  totalComponents: number;
  modules: ModuleCatalogueItem[];
}

export type ModuleModel = ModuleCatalogueItem;

export interface ActionDependencyRule {
  id: string;
  sourceModuleCode: string;
  sourceComponentCode: string;
  sourceAction: string;
  targetModuleCode: string;
  targetComponentCode: string;
  targetAction: string;
  ruleType: 'Prerequisite' | 'Trigger' | 'Cross-Module Gate' | 'Audit Chain';
  enforcementLevel: 'Strict Block' | 'Workflow Gate' | 'Async Verification';
  description: string;
  status: 'Active' | 'Deprecated';
}
