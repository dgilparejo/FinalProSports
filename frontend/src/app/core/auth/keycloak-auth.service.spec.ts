import { TestBed } from '@angular/core/testing';

import { APP_CONFIG } from '../../app.config';

import { KeycloakAuthService } from './keycloak-auth.service';

/**
 * The renewal path, with keycloak-js replaced by a stub. What is under test is what the app does around the library:
 * a single in-flight renewal, and the fact that a dead session becomes a STATE the interface can react to instead of
 * a silent `authenticated = false` that only a page reload noticed.
 */
describe('KeycloakAuthService renewal', () => {
  let auth: KeycloakAuthService;
  let updateToken: jasmine.Spy;

  function stub(behaviour: 'ok' | 'fail'): void {
    updateToken =
      behaviour === 'ok'
        ? jasmine.createSpy('updateToken').and.resolveTo(true)
        : jasmine.createSpy('updateToken').and.rejectWith(new Error('refresh token expired'));
    // The service holds its Keycloak instance privately; the stub goes in the same slot init would fill.
    (auth as unknown as { keycloak: unknown }).keycloak = {
      updateToken,
      tokenParsed: { preferred_username: 'entrenador', realm_access: { roles: ['entrenador'] }, sub: 's' },
    };
  }

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [{ provide: APP_CONFIG, useValue: { keycloakUrl: 'http://kc', keycloakRealm: 'fps', keycloakClientId: 'c', requiredRole: 'entrenador' } }],
    });
    auth = TestBed.inject(KeycloakAuthService);
  });

  it('renews and keeps the session alive', async () => {
    stub('ok');
    await expectAsync(auth.refresh()).toBeResolvedTo(true);
    expect(auth.authenticated()).toBeTrue();
    expect(auth.sessionExpired()).toBeFalse();
  });

  it('declares the session expired when there is nothing left to renew', async () => {
    stub('fail');
    await expectAsync(auth.refresh()).toBeResolvedTo(false);
    expect(auth.authenticated()).toBeFalse();
    expect(auth.sessionExpired()).toBeTrue();
  });

  it('renews ONCE for three simultaneous callers: the refresh token is single-use', async () => {
    stub('ok');
    const results = await Promise.all([auth.refresh(), auth.refresh(-1), auth.refresh()]);
    expect(results).toEqual([true, true, true]);
    expect(updateToken).toHaveBeenCalledTimes(1);
  });

  it('lets a later renewal succeed after an earlier one failed', async () => {
    stub('fail');
    await auth.refresh();
    expect(auth.sessionExpired()).toBeTrue();
    stub('ok');
    await auth.refresh();
    expect(auth.sessionExpired()).toBeFalse();
  });

  it('reports no session when there is no Keycloak at all', async () => {
    await expectAsync(auth.refresh()).toBeResolvedTo(false);
  });
});
