import { HttpErrorResponse, HttpHandlerFn, HttpRequest, HttpResponse } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';

import { APP_CONFIG } from '../../../app.config';
import { KeycloakAuthService } from '../../auth/keycloak-auth.service';

import { authInterceptor, isApiRequest } from './auth.interceptor';

const API = 'http://localhost:8000/api/v1';

describe('authInterceptor', () => {
  let auth: { token: string; refresh: jasmine.Spy };

  beforeEach(() => {
    auth = { token: 'a-token', refresh: jasmine.createSpy('refresh').and.resolveTo(true) };
    TestBed.configureTestingModule({
      providers: [
        { provide: KeycloakAuthService, useValue: auth },
        { provide: APP_CONFIG, useValue: { apiBaseUrl: API, requiredRole: 'entrenador' } },
      ],
    });
  });

  const run = (req: HttpRequest<unknown>, next: HttpHandlerFn) => TestBed.runInInjectionContext(() => authInterceptor(req, next));

  it('marks only our API as an API request', () => {
    expect(isApiRequest(`${API}/clients`, API)).toBeTrue();
    expect(isApiRequest('http://localhost:8000/health', API)).toBeFalse();
    expect(isApiRequest('https://evil.example/api/v1/clients', API)).toBeFalse();
    expect(isApiRequest('./assets/i18n/es.json', API)).toBeFalse();
  });

  it('attaches the bearer to an API call', (done) => {
    const next: HttpHandlerFn = (r) => {
      expect(r.headers.get('Authorization')).toBe('Bearer a-token');
      return of(new HttpResponse({ status: 200 }));
    };
    run(new HttpRequest('GET', `${API}/clients`), next).subscribe(() => done());
  });

  it('NEVER attaches the bearer to a third party', (done) => {
    const next: HttpHandlerFn = (r) => {
      expect(r.headers.has('Authorization')).toBeFalse();
      return of(new HttpResponse({ status: 200 }));
    };
    run(new HttpRequest('GET', 'https://fonts.googleapis.com/css'), next).subscribe(() => done());
  });

  it('does not attach the bearer to the assets of the app itself', (done) => {
    const next: HttpHandlerFn = (r) => {
      expect(r.headers.has('Authorization')).toBeFalse();
      return of(new HttpResponse({ status: 200 }));
    };
    run(new HttpRequest('GET', './assets/i18n/es.json'), next).subscribe(() => done());
  });

  it('renews once and replays the request after a 401', (done) => {
    let call = 0;
    auth.refresh.and.callFake(() => {
      auth.token = 'renewed';
      return Promise.resolve(true);
    });
    const next: HttpHandlerFn = (r) => {
      call += 1;
      if (call === 1) return throwError(() => new HttpErrorResponse({ status: 401 }));
      expect(r.headers.get('Authorization')).toBe('Bearer renewed');
      return of(new HttpResponse({ status: 200 }));
    };
    run(new HttpRequest('GET', `${API}/clients`), next).subscribe(() => {
      expect(call).toBe(2);
      expect(auth.refresh).toHaveBeenCalledTimes(1);
      done();
    });
  });

  it('gives up when the renewal fails, instead of looping', (done) => {
    auth.refresh.and.resolveTo(false);
    let call = 0;
    const next: HttpHandlerFn = () => {
      call += 1;
      return throwError(() => new HttpErrorResponse({ status: 401 }));
    };
    run(new HttpRequest('GET', `${API}/clients`), next).subscribe({
      error: () => {
        expect(call).toBe(1);
        done();
      },
    });
  });

  it('does not try to renew on a 403: the token is fine, the role is not', (done) => {
    const next: HttpHandlerFn = () => throwError(() => new HttpErrorResponse({ status: 403 }));
    run(new HttpRequest('GET', `${API}/clients`), next).subscribe({
      error: () => {
        expect(auth.refresh).not.toHaveBeenCalled();
        done();
      },
    });
  });
});
