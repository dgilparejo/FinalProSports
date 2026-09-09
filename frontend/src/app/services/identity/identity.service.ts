import { Injectable, computed, inject } from '@angular/core';

import { KeycloakAuthService } from '../../core/auth/keycloak-auth.service';

/**
 * v2: the identity is the one in the validated token. The professional id is NOT here any more — the
 * backend derives it from the token's subject and the frontend never sees it, which is what keeps a
 * client of the browser from choosing whose data it reads.
 */
@Injectable({ providedIn: 'root' })
export class IdentityService {
  private readonly auth = inject(KeycloakAuthService);
  readonly displayName = computed(() => this.auth.displayName());
  /**
   * Iniciales para el avatar. Del nombre de usuario del token, que es lo único que hay: el realm no guarda correo
   * ni nombre completo a propósito (el criterio 0 de la auditoría PII no admite excepciones, la memoria (capítulo de seguridad)).
   */
  readonly initials = computed(() => {
    const parts = this.displayName()
      .trim()
      .split(/[\s._-]+/)
      .filter(Boolean);
    return (parts.length > 1 ? parts[0][0] + parts[1][0] : this.displayName().slice(0, 2)).toUpperCase() || '?';
  });
  /** Los roles del realm que el token trae, sin los internos de Keycloak, que no dicen nada al profesional. */
  readonly visibleRoles = computed(() =>
    this.auth.roles().filter((r) => !r.startsWith('default-roles') && !['offline_access', 'uma_authorization'].includes(r)),
  );
  readonly roles = computed(() => this.auth.roles());
  readonly authenticated = computed(() => this.auth.authenticated());
  /** La sesión se ha ido y no queda nada que renovar: la interfaz lo tiene que DECIR, no seguir pintando datos viejos. */
  readonly sessionExpired = computed(() => this.auth.sessionExpired());

  hasRole(role: string): boolean {
    return this.auth.hasRole(role);
  }

  logout(): Promise<void> {
    return this.auth.logout();
  }

  reauthenticate(): Promise<void> {
    return this.auth.reauthenticate();
  }
}
