import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { finalize } from 'rxjs/operators';
import { LoadingService } from '../services/loading.service';

export const loadingInterceptor: HttpInterceptorFn = (req, next) => {
  // Option to bypass global loader via header if needed: X-Silent-Request: true
  if (req.headers.has('X-Silent-Request')) {
    const cleanedReq = req.clone({
      headers: req.headers.delete('X-Silent-Request'),
    });
    return next(cleanedReq);
  }

  const loader = inject(LoadingService);
  loader.show();

  return next(req).pipe(
    finalize(() => {
      loader.hide();
    })
  );
};
