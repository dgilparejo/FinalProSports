import { Injectable, computed, inject, signal } from '@angular/core';
import Keycloak from 'keycloak-js';

import { APP_CONFIG } from '../../app.config';

/**
 * Authorization Code + PKCE (S256) against the `fps` realm.
 *
 * The token lives ONLY in memory — in this instance, in keycloak-js's own field. It is never written
 * to localStorage or sessionStorage: anything persisted there is readable by any script that ends up
 * running on the origin, and it survives the tab. A short-lived token held in memory is the
 * mitigation this design accepts in exchange for not putting a BFF in front (la memoria (capítulo de seguridad)).
 */
@Injectable({ providedIn: 'root' })
export class KeycloakAuthService {
  private readonly config = inject(APP_CONFIG);
  private keycloak: Keycloak | null = null;
  private renewal: Promise<boolean> | null = null;

  readonly authenticated = signal(false);
  /**
   * La sesión se ha ido y no queda nada que renovar en silencio. Existe porque `authenticated` a solas no lo arreglaba:
   * el guard solo corre al NAVEGAR, y quien se queda quieto en una pantalla no navega. El síntoma era exactamente ese —
   * la sesión caducaba, la pantalla se quedaba con datos viejos y solo un F5 la despertaba.
   */
  readonly sessionExpired = signal(false);
  readonly username = signal('');
  readonly roles = signal<readonly string[]>([]);
  readonly subject = signal('');
  readonly displayName = computed(() => this.username() || 'sin identificar');

  hasRole(role: string): boolean {
    return this.roles().includes(role);
  }

  get isTrainer(): boolean {
    return this.hasRole(this.config.requiredRole);
  }

  /** Runs before the app boots: no screen is ever painted without an identity behind it. */
  async init(): Promise<void> {
    this.keycloak = new Keycloak({ url: this.config.keycloakUrl, realm: this.config.keycloakRealm, clientId: this.config.keycloakClientId });

    const authenticated = await this.keycloak.init({
      onLoad: 'login-required', // no anonymous mode: Keycloak is required to start (la memoria (capítulo de seguridad))
      pkceMethod: 'S256',
      checkLoginIframe: false, // the iframe polls a third-party cookie; the silent refresh below covers the same ground
      responseMode: 'query',
    });

    this.readClaims(authenticated);
    // Access tokens last 5 minutes on purpose, so this path is exercised in any real session
    // rather than shipping as untested code.
    this.keycloak.onTokenExpired = () => void this.refresh();
    this.renewWhenTheTabComesBack();
  }

  /**
   * `onTokenExpired` es un temporizador, y un temporizador en una pestaña de fondo lo estrangula el navegador: se
   * despierta tarde o no se despierta. Volver a la pestaña después de un rato significaba encontrarse el token ya
   * caducado y enterarse por una petición fallida. Aquí se renueva al RECUPERAR EL FOCO y al volver la red, que es
   * cuando se sabe que el reloj ha corrido sin nosotros; `updateToken` no hace nada si al token le queda cuerda, así
   * que no cuesta peticiones.
   */
  private renewWhenTheTabComesBack(): void {
    const check = () => {
      if (document.visibilityState === 'visible' && !this.sessionExpired()) void this.refresh();
    };
    document.addEventListener('visibilitychange', check);
    window.addEventListener('online', check);
    window.addEventListener('focus', check);
  }

  private readClaims(authenticated: boolean): void {
    const parsed = this.keycloak?.tokenParsed as { preferred_username?: string; realm_access?: { roles?: string[] }; sub?: string } | undefined;
    this.authenticated.set(authenticated);
    this.username.set(parsed?.preferred_username ?? '');
    this.roles.set(parsed?.realm_access?.roles ?? []); // the claim is ABSENT for a user with no realm role
    this.subject.set(parsed?.sub ?? '');
  }

  /** The bearer for the NEXT request, or '' when there is none. Read at call time: it is rotated. */
  get token(): string {
    return this.keycloak?.token ?? '';
  }

  /**
   * Renews when the token has less than `minValiditySeconds` left (or is already expired).
   * Returns true when a usable token is in hand afterwards.
   */
  async refresh(minValiditySeconds = 30): Promise<boolean> {
    if (!this.keycloak) return false;
    // Un solo vuelo: el temporizador, el 401 del interceptor y la vuelta a la pestaña pueden pedir renovación a la vez,
    // y tres renovaciones en paralelo con el MISMO token de refresco son tres carreras por un token de un solo uso.
    this.renewal ??= this.renew(minValiditySeconds).finally(() => (this.renewal = null));
    return this.renewal;
  }

  private async renew(minValiditySeconds: number): Promise<boolean> {
    try {
      await this.keycloak!.updateToken(minValiditySeconds);
      this.readClaims(true);
      this.sessionExpired.set(false);
      return true;
    } catch {
      // The refresh token is gone too (30 minutes idle): there is nothing left to renew silently.
      this.authenticated.set(false);
      this.sessionExpired.set(true);
      return false;
    }
  }

  /**
   * Vuelve a entrar SIN perder de vista dónde estaba. `login()` a secas vuelve a la raíz, y quien caducó dentro de un
   * expediente aterrizaba en el listado. Si la sesión en Keycloak sigue viva, el viaje es de ida y vuelta y no se ve
   * ni el formulario.
   */
  async reauthenticate(): Promise<void> {
    await this.keycloak?.login({ redirectUri: window.location.href });
  }

  /** Ends the session in KEYCLOAK, not only in this tab: otherwise the next visit walks straight back in. */
  async logout(): Promise<void> {
    await this.keycloak?.logout({ redirectUri: window.location.origin });
  }

  async login(): Promise<void> {
    await this.keycloak?.login();
  }
}
