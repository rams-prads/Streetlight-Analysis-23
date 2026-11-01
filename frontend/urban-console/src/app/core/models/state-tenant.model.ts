export interface MasterState {
  code: string;
  name: string;
  officialName: string;
  defaultSlug: string;
  primaryLanguage: string;
  additionalLanguages: string[];
  zone?: string;
}

export interface District {
  id: string;
  stateCode: string;
  code: string;
  name: string;
  headquarters?: string;
}

export interface City {
  id: string;
  stateCode: string;
  districtId?: string;
  name: string;
  ulbType: string;
  ulbCode: string;
}


export interface StateTenant {
  tenantId: string;
  stateName: string;
  stateCode: string;
  tenantSlug: string;
  status: 'Draft' | 'Active' | 'Suspended';
  country: string;
  timeZone: string;
  primaryLanguage: string;
  additionalLanguages?: string[];
  officialStateName?: string;
  stateEmblemUrl?: string;
  stateWebsite?: string;
  administrativeEmail: string;
  administrativePhone?: string;
  address?: string;
  effectiveDate?: string;
  notes?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface StateTenantCreatePayload {
  stateName: string;
  stateCode: string;
  tenantSlug: string;
  status: 'Draft' | 'Active' | 'Suspended';
  country: string;
  timeZone: string;
  primaryLanguage: string;
  additionalLanguages?: string[];
  officialStateName?: string;
  stateEmblemUrl?: string;
  stateWebsite?: string;
  administrativeEmail: string;
  administrativePhone?: string;
  address?: string;
  effectiveDate?: string;
  notes?: string;
}

export interface TenantAuditLog {
  id: string;
  tenantId: string;
  action: string;
  performedBy: string;
  timestamp: string;
  details?: string;
  ipAddress?: string;
}
