import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { ApplicationConfig, InjectionToken, inject, provideAppInitializer, provideZoneChangeDetection } from '@angular/core';
import { MAT_DATE_LOCALE } from '@angular/material/core';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { provideRouter, withComponentInputBinding } from '@angular/router';
import { TranslateLoader, provideTranslateService } from '@ngx-translate/core';
import { TranslateHttpLoader } from '@ngx-translate/http-loader';

import { environment } from '@env/environment';

import { routes } from './app.routes';
import { KeycloakAuthService } from './core/auth/keycloak-auth.service';
import { apiErrorInterceptor } from './core/interceptors/api-error/api-error.interceptor';
import { authInterceptor } from './core/interceptors/auth/auth.interceptor';

/** Own configuration token (replaces the W2M API_CONFIG): everything the app needs from the environment, injectable. */
export interface AppConfig {
  apiBaseUrl: string;
  professionalId: string;
  brand: string;
  keycloakUrl: string;
  keycloakRealm: string;
  keycloakClientId: string;
  requiredRole: string;
}
export const APP_CONFIG = new InjectionToken<AppConfig>('APP_CONFIG');

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes, withComponentInputBinding()),
    // EL ORDEN IMPORTA, y estaba al revés. El primero de la lista envuelve al segundo en la petición, así que en la
    // RESPUESTA el último es el primero en ver el error. Con `authInterceptor` delante, el de errores veía el 401
    // antes de que auth intentara renovar: una renovación que salía bien dejaba igualmente un mensaje rojo por una
    // petición que acabó en 200. Ahora auth es el interior: renueva, reintenta, y el de errores solo se enteraba
    // cuando ya no hay nada que hacer. El bearer se sigue añadiendo igual, porque en la petición auth sigue estando
    // antes que la red.
    provideHttpClient(withInterceptors([apiErrorInterceptor, authInterceptor])),
    // Keycloak resolves BEFORE the app boots: no screen is painted without an identity behind it.
    provideAppInitializer(() => inject(KeycloakAuthService).init()),
    provideAnimationsAsync(),
    provideTranslateService({
      defaultLanguage: 'es',
      loader: { provide: TranslateLoader, useFactory: (http: HttpClient) => new TranslateHttpLoader(http, './assets/i18n/', '.json'), deps: [HttpClient] },
    }),
    {
      provide: APP_CONFIG,
      useValue: {
        apiBaseUrl: environment.apiBaseUrl,
        professionalId: environment.professionalId,
        brand: environment.brand,
        keycloakUrl: environment.keycloakUrl,
        keycloakRealm: environment.keycloakRealm,
        keycloakClientId: environment.keycloakClientId,
        requiredRole: environment.requiredRole,
      },
    },
    { provide: MAT_DATE_LOCALE, useValue: 'es-ES' },
  ],
};
