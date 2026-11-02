import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { KeycloakAuthService } from '../services/keycloak.service';

export const authHeaderInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(KeycloakAuthService);
  const token = authService.getToken();
  const tenantId = authService.getTenantId();
  const subTenantId = authService.getSubTenantId();

  let headers = req.headers;

  if (token && !headers.has('Authorization')) {
    headers = headers.set('Authorization', `Bearer ${token}`);
  }

  if (tenantId && !headers.has('X-Tenant-ID')) {
    headers = headers.set('X-Tenant-ID', tenantId);
  }

  if (subTenantId && !headers.has('X-Sub-Tenant-ID')) {
    headers = headers.set('X-Sub-Tenant-ID', subTenantId);
  }

  const clonedReq = req.clone({ headers });
  return next(clonedReq);
};

