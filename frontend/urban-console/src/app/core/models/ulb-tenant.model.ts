export interface Zone {
  id: string;
  tenantId: string;
  code: string;
  name: string;
  totalWards?: number;
}

export interface ZoneCreatePayload {
  code: string;
  name: string;
}

export interface Ward {
  id: string;
  tenantId: string;
  wardNumber: number;
  wardCode?: string;
  wardName: string;
  councilorName?: string;
  zoneId?: string;
  zoneName?: string;
  effectiveFrom?: string;
  boundaryGeometry?: any;
  totalParcels?: number;
}

export interface WardCreatePayload {
  wardNumber: number;
  wardName: string;
  wardCode?: string;
  councilorName?: string;
  zoneId?: string;
  effectiveFrom?: string;
  boundaryGeometry?: any;
}

export interface UlbTenant {
  tenantId: string;
  name: string;
  parentStateTenantId?: string;
  parentStateName?: string;
  stateCode: string;
  ulbCode: string;
  tenantSlug: string;
  ulbType: string;
  administrativeGrade?: string;
  district: string;
  officialWebsite?: string;
  officialEmail?: string;
  contactPhone?: string;
  officeAddress?: string;
  timeZone: string;
  primaryLanguage: string;
  status: 'Draft' | 'Active' | 'Suspended';
  enableZones: boolean;
  enableWards: boolean;
  effectiveDate?: string;
  totalZones?: number;
  totalWards?: number;
  totalParcels?: number;
  createdAt?: string;
  updatedAt?: string;
}

export interface UlbTenantCreatePayload {
  tenantId?: string;
  name: string;
  parentStateTenantId?: string;
  stateCode: string;
  ulbCode: string;
  tenantSlug: string;
  ulbType: string;
  administrativeGrade?: string;
  district: string;
  officialWebsite?: string;
  officialEmail?: string;
  contactPhone?: string;
  officeAddress?: string;
  timeZone?: string;
  primaryLanguage?: string;
  status: 'Draft' | 'Active' | 'Suspended';
  enableZones: boolean;
  enableWards: boolean;
  effectiveDate?: string;
}

export interface UlbTenantUpdatePayload {
  name?: string;
  parentStateTenantId?: string;
  stateCode?: string;
  ulbCode?: string;
  tenantSlug?: string;
  ulbType?: string;
  administrativeGrade?: string;
  district?: string;
  officialWebsite?: string;
  officialEmail?: string;
  contactPhone?: string;
  officeAddress?: string;
  timeZone?: string;
  primaryLanguage?: string;
  status?: 'Draft' | 'Active' | 'Suspended';
  enableZones?: boolean;
  enableWards?: boolean;
  effectiveDate?: string;
}
