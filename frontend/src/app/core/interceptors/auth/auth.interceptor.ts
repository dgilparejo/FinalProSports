import { HttpErrorResponse, HttpInterceptorFn, HttpRequest } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, from, switchMap, throwError } from 'rxjs';

import { APP_CONFIG } from '../../../app.config';
import { KeycloakAuthService } from '../../auth/keycloak-auth.service';

/** True only for calls to OUR api. Everything else (i18n assets, fonts, anything third-party) is left alone. */
export function isApiRequest(url: string, apiBaseUrl: string): boolean {
  const target = new URL(url, window.location.origin);
  const api = new URL(apiBaseUrl, window.location.origin);
  return target.origin === api.origin && target.pathname.startsWith(api.pathname);
}

/**
 * Attaches the bearer to API calls, and ONLY to API calls: a blanket interceptor would hand the
 * professional's access token to every host the app happens to fetch from, which is how tokens leak.
 *
 * On a 401 it renews once and replays the request. With five-minute tokens the window between "valid
 * when the user clicked" and "expired when it arrived" is real, and without this the user would see a
 * random error instead of the page.
 */
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(KeycloakAuthService);
  const { apiBaseUrl } = inject(APP_CONFIG);

  if (!isApiRequest(req.url, apiBaseUrl)) return next(req);

  const withBearer = (token: string): HttpRequest<unknown> => (token ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }) : req);

  return next(withBearer(auth.token)).pipe(
    catchError((err: unknown) => {
      if (!(err instanceof HttpErrorResponse) || err.status !== 401) return throwError(() => err);
      return from(auth.refresh(-1)).pipe(switchMap((renewed) => (renewed ? next(withBearer(auth.token)) : throwError(() => err))));
    }),
  );
};
