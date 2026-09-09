import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { APP_CONFIG } from '../../app.config';
import { KeycloakAuthService } from '../auth/keycloak-auth.service';

/**
 * Authentication AND the `entrenador` role. Without the role the user goes to a page that says so,
 * not to a blank screen or a silent redirect loop: the backend is going to answer 403 anyway, and a
 * screen that explains the refusal is the difference between a bug report and an understood rule.
 */
export const authGuard: CanActivateFn = () => {
  const auth = inject(KeycloakAuthService);
  const router = inject(Router);
  const { requiredRole } = inject(APP_CONFIG);

  if (!auth.authenticated()) {
    void auth.login();
    return false;
  }
  return auth.hasRole(requiredRole) ? true : router.createUrlTree(['/forbidden']);
};
