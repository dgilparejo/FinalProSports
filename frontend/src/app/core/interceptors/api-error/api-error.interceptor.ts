import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { Injector, inject } from '@angular/core';
import { TranslateService } from '@ngx-translate/core';
import { catchError, throwError } from 'rxjs';

import { LoggerService } from '../../../services/logger/logger.service';
import { KeycloakAuthService } from '../../auth/keycloak-auth.service';

/** Turns API errors ({code, message} from the backend's exception handlers) into one user-facing message, then rethrows. */
export const apiErrorInterceptor: HttpInterceptorFn = (req, next) => {
  const logger = inject(LoggerService);
  // Injector, NOT TranslateService: injecting the service HERE deadlocks it. Its constructor issues the
  // HTTP request for the dictionary, that request walks this very chain, and asking for the service while
  // it is still being constructed is a circular dependency. The request then fails before reaching the
  // network and ngx-translate SWALLOWS that error (`void err` in loadAndCompileTranslations), so the app
  // silently renders every key untranslated, for ever, with nothing in the console.
  // Resolved lazily instead: by the time an API call fails, the service is long built.
  const injector = inject(Injector);
  return next(req).pipe(
    catchError((err: unknown) => {
      if (err instanceof HttpErrorResponse) {
        const body = err.error as { code?: string; message?: string; detail?: unknown } | null;
        // 401 and 403 are not developer detail: they are the two things the user can act on, so
        // they get a sentence instead of a status code and an English message from the backend.
        if (err.status === 401 || err.status === 403) {
          // Con la sesión ya declarada caducada, el aviso a pantalla completa lo está diciendo con un botón que lo
          // arregla: un mensaje rojo más solo añade ruido a algo que el usuario ya está leyendo.
          if (err.status === 401 && injector.get(KeycloakAuthService).sessionExpired()) return throwError(() => err);
          const key = err.status === 401 ? 'auth.unauthenticated' : 'auth.forbidden.message';
          logger.error(injector.get(TranslateService).instant(key));
          return throwError(() => err);
        }
        const detail = body?.message ?? (typeof body?.detail === 'string' ? body.detail : Array.isArray(body?.detail) ? 'datos no válidos' : null);
        logger.error(`${err.status} ${req.method} ${req.url.replace(/^.*\/api\/v1\//, '')}${detail ? ` — ${detail}` : ''}`);
      }
      return throwError(() => err);
    }),
  );
};
