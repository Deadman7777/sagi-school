import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { AuthService } from '../services/auth.service';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth     = inject(AuthService);
  const token    = localStorage.getItem('access_token');
  const tenantId = auth.effectiveTenantId;

  let cloned = req;

  if (token) {
    cloned = cloned.clone({
      setHeaders: { 'Authorization': `Bearer ${token}` }
    });
  }

  if (tenantId && tenantId !== 'null' && tenantId !== '') {
    cloned = cloned.clone({
      setHeaders: { 'X-Tenant-ID': tenantId }
    });
  }

  return next(cloned);
};
