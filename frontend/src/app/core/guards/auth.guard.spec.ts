import { TestBed } from '@angular/core/testing';
import { ActivatedRouteSnapshot, Router, RouterStateSnapshot, UrlTree } from '@angular/router';
import { signal } from '@angular/core';

import { APP_CONFIG } from '../../app.config';
import { KeycloakAuthService } from '../auth/keycloak-auth.service';

import { authGuard } from './auth.guard';

describe('authGuard', () => {
  const configure = (authenticated: boolean, roles: string[], login = jasmine.createSpy('login')) => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [
        {
          provide: KeycloakAuthService,
          useValue: { authenticated: signal(authenticated), hasRole: (r: string) => roles.includes(r), login },
        },
        { provide: APP_CONFIG, useValue: { requiredRole: 'entrenador' } },
      ],
    });
  };

  const run = () => TestBed.runInInjectionContext(() => authGuard({} as ActivatedRouteSnapshot, {} as RouterStateSnapshot));

  it('lets a trainer through', () => {
    configure(true, ['entrenador']);
    expect(run()).toBeTrue();
  });

  it('sends an authenticated user WITHOUT the role to the access-denied page, not to a blank screen', () => {
    configure(true, ['otro']);
    const result = run();
    expect(result instanceof UrlTree).toBeTrue();
    expect(TestBed.inject(Router).serializeUrl(result as UrlTree)).toBe('/forbidden');
  });

  it('starts the login when there is no session', () => {
    const login = jasmine.createSpy('login');
    configure(false, [], login);
    expect(run()).toBeFalse();
    expect(login).toHaveBeenCalled();
  });
});
