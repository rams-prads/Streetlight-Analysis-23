import {
  ApplicationConfig,
  provideBrowserGlobalErrorListeners,
  provideAppInitializer,
  inject,
} from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { routes } from './app.routes';
import { KeycloakAuthService } from './core/services/keycloak.service';
import { loadingInterceptor } from './core/interceptors/loading.interceptor';
import { authHeaderInterceptor } from './core/interceptors/auth-header.interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideHttpClient(withInterceptors([authHeaderInterceptor, loadingInterceptor])),
    provideAppInitializer(() => {
      const auth = inject(KeycloakAuthService);
      return auth.init();
    }),
  ],
};
