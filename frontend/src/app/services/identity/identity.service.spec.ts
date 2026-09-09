import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { KeycloakAuthService } from '../../core/auth/keycloak-auth.service';

import { IdentityService } from './identity.service';

describe('IdentityService', () => {
  const configure = (username: string, roles: string[]) => {
    TestBed.resetTestingModule();
    const logout = jasmine.createSpy('logout').and.resolveTo(undefined);
    TestBed.configureTestingModule({
      providers: [
        {
          provide: KeycloakAuthService,
          useValue: {
            authenticated: signal(true),
            roles: signal(roles),
            displayName: signal(username),
            hasRole: (r: string) => roles.includes(r),
            logout,
          },
        },
      ],
    });
    return logout;
  };

  it('exposes the identity of the validated token, and no professional id', () => {
    configure('entrenador', ['entrenador']);
    const identity = TestBed.inject(IdentityService);
    expect(identity.displayName()).toBe('entrenador');
    expect(identity.authenticated()).toBeTrue();
    expect(identity.hasRole('entrenador')).toBeTrue();
    expect(identity.hasRole('admin')).toBeFalse();
    // v2: the tenant is derived from the token's subject by the backend and is never exposed here
    expect('professionalId' in identity).toBeFalse();
  });

  it('reports a user with no realm role as having none', () => {
    configure('sinrol', []);
    const identity = TestBed.inject(IdentityService);
    expect(identity.roles()).toEqual([]);
    expect(identity.hasRole('entrenador')).toBeFalse();
  });

  it('logs out through Keycloak, not only in the tab', async () => {
    const logout = configure('entrenador', ['entrenador']);
    await TestBed.inject(IdentityService).logout();
    expect(logout).toHaveBeenCalled();
  });

  it('builds the initials the avatar shows from the token username', () => {
    configure('entrenador', ['entrenador']);
    expect(TestBed.inject(IdentityService).initials()).toBe('EN');
    configure('ana.lopez', ['entrenador']);
    expect(TestBed.inject(IdentityService).initials()).toBe('AL');
  });

  it('hides the roles Keycloak adds to everyone: they say nothing to the professional', () => {
    configure('entrenador', ['entrenador', 'default-roles-fps', 'offline_access', 'uma_authorization']);
    expect(TestBed.inject(IdentityService).visibleRoles()).toEqual(['entrenador']);
  });
});
