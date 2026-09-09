import { Component, inject } from '@angular/core';
import { MatMenuModule } from '@angular/material/menu';
import { TranslatePipe } from '@ngx-translate/core';

import { IdentityService } from '@services/identity/identity.service';

/**
 * El profesional que ha entrado, y lo que puede hacer con su sesión. Antes era un icono y un texto fijos, que no
 * decían de dónde salía el nombre ni permitían nada; ahora es un menú.
 *
 * Lo que hay dentro sale del TOKEN, y solo eso: quién ha entrado, con qué rol, y cerrar sesión.
 *
 * NO hay «editar perfil» ni enlace a la cuenta de Keycloak, y las dos ausencias son decisiones. La primera, porque no
 * hay perfil propio que editar: el realm no guarda ni correo ni nombre completo, y está declarado en
 * la memoria (capítulo de seguridad). La segunda, porque el proveedor de identidad es infraestructura — el profesional no tiene por
 * qué saber que detrás hay un Keycloak, y menos aún acabar en su consola. Quien administra usuarios entra por ahí, no
 * el usuario.
 */
@Component({
  selector: 'app-profile-menu',
  imports: [MatMenuModule, TranslatePipe],
  template: `
    <button type="button" class="trigger" [matMenuTriggerFor]="menu" [attr.aria-label]="'profile.open' | translate">
      <span class="avatar" aria-hidden="true">{{ identity.initials() }}</span>
      <span class="name">{{ identity.displayName() }}</span>
      <span class="material-icons chevron" aria-hidden="true">expand_more</span>
    </button>

    <mat-menu #menu="matMenu" class="profile-panel">
      <div class="head">
        <span class="avatar big" aria-hidden="true">{{ identity.initials() }}</span>
        <span class="who">
          <strong>{{ identity.displayName() }}</strong>
          <span class="roles small">
            @if (identity.visibleRoles().length) {
              <!-- Etiquetado: en este realm el usuario se llama igual que su rol, y sin la etiqueta parecía el nombre repetido. -->
              {{ 'profile.role' | translate }} {{ identity.visibleRoles().join(' · ') }}
            } @else {
              {{ 'profile.noRoles' | translate }}
            }
          </span>
        </span>
      </div>
      <button mat-menu-item type="button" class="danger" (click)="identity.logout()">
        <span class="material-icons">logout</span>
        <span>{{ 'auth.logout' | translate }}</span>
      </button>
    </mat-menu>
  `,
  styles: `
    :host {
      display: block;
    }
    .trigger {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      max-width: 220px;
      padding: 4px 6px 4px 4px;
      background: none;
      border: 1px solid transparent;
      border-radius: 999px;
      color: var(--text-muted);
      font: inherit;
      font-size: 13px;
      cursor: pointer;
    }
    .trigger:hover,
    .trigger[aria-expanded='true'] {
      color: var(--text);
      border-color: var(--border);
      background: var(--surface-alt);
    }
    .trigger:focus-visible {
      outline: 2px solid var(--accent);
      outline-offset: 1px;
    }
    .avatar {
      display: grid;
      place-items: center;
      flex: 0 0 auto;
      width: 26px;
      height: 26px;
      border-radius: 50%;
      background: var(--accent);
      color: var(--accent-ink);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.02em;
    }
    .avatar.big {
      width: 34px;
      height: 34px;
      font-size: 13px;
    }
    .name {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .chevron {
      font-size: 18px;
      flex: 0 0 auto;
    }
    .head {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 10px 14px;
      border-bottom: 1px solid var(--border);
      cursor: default;
    }
    .head .who {
      display: flex;
      flex-direction: column;
      min-width: 0;
    }
    .head strong {
      color: var(--text);
    }
    .head .roles {
      color: var(--text-muted);
    }
    .material-icons {
      font-size: 18px;
      margin-right: 8px;
      vertical-align: text-bottom;
    }
    .danger {
      color: var(--danger);
    }

    /* El nombre sale del disparador en un móvil: el avatar y el chevron ya dicen que se puede pulsar, y el nombre
       entero está dentro del menú. Lo que no se recorta es la acción. */
    @media (max-width: 720px) {
      .trigger {
        gap: 2px;
        max-width: none;
      }
      .name {
        display: none;
      }
    }
  `,
})
export class ProfileMenuComponent {
  readonly identity = inject(IdentityService);
}
