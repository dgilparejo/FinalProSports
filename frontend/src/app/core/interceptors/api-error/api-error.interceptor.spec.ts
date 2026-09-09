import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { TranslateService } from '@ngx-translate/core';

import { LoggerService } from '../../../services/logger/logger.service';
import { KeycloakAuthService } from '../../auth/keycloak-auth.service';

import { apiErrorInterceptor } from './api-error.interceptor';

const MESSAGES: Record<string, string> = {
  'auth.unauthenticated': 'No has iniciado sesión o tu sesión ha caducado.',
  'auth.forbidden.message': 'Tu cuenta no tiene permiso para esta operación (falta el rol «entrenador»).',
};

describe('apiErrorInterceptor', () => {
  let expired = false;
  beforeEach(() => (expired = false));

  const setup = () => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([apiErrorInterceptor])),
        provideHttpClientTesting(),
        { provide: TranslateService, useValue: { instant: (key: string) => MESSAGES[key] ?? key } },
        { provide: KeycloakAuthService, useValue: { sessionExpired: () => expired } },
      ],
    });
    spyOn(console, 'error');
    return { http: TestBed.inject(HttpClient), ctrl: TestBed.inject(HttpTestingController), logger: TestBed.inject(LoggerService) };
  };

  const fail = (status: number, body: Record<string, string>) => {
    const { http, ctrl, logger } = setup();
    let failed = false;
    http.get('http://x/api/v1/clients/CLIENTE_001').subscribe({ error: () => (failed = true) });
    ctrl.expectOne('http://x/api/v1/clients/CLIENTE_001').flush(body, { status, statusText: 'error' });
    return { failed: () => failed, logger };
  };

  it('publishes the backend message through the logger and rethrows', () => {
    const { failed, logger } = fail(404, { code: 'client_not_found', message: 'client not found: CLIENTE_001' });
    expect(failed()).toBeTrue();
    expect(logger.lastError()).toBe('404 GET clients/CLIENTE_001 — client not found: CLIENTE_001');
  });

  it('turns a 401 into a sentence the user can act on, not a status code', () => {
    const { failed, logger } = fail(401, { code: 'unauthenticated', message: 'missing Authorization: Bearer header' });
    expect(failed()).toBeTrue();
    expect(logger.lastError()).toBe(MESSAGES['auth.unauthenticated']);
  });

  it('stays QUIET on a 401 when the expired-session notice is already saying it with a button', () => {
    expired = true;
    const { failed, logger } = fail(401, { code: 'unauthenticated', message: 'token expired' });
    expect(failed()).toBeTrue();
    expect(logger.lastError()).toBeNull();
  });

  it('turns a 403 into the missing-role message, distinct from the 401 one', () => {
    const { failed, logger } = fail(403, { code: 'forbidden', message: "the token carries no 'entrenador' realm role" });
    expect(failed()).toBeTrue();
    expect(logger.lastError()).toBe(MESSAGES['auth.forbidden.message']);
    expect(logger.lastError()).not.toBe(MESSAGES['auth.unauthenticated']);
  });
});
