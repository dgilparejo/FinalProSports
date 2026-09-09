import { Component, inject } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

import { KeycloakAuthService } from '../../core/auth/keycloak-auth.service';

/** Where the route guard sends an authenticated user who does not carry the `entrenador` role. */
@Component({
  selector: 'app-forbidden',
  imports: [TranslatePipe],
  templateUrl: './forbidden.component.html',
  styleUrl: './forbidden.component.sass',
})
export class ForbiddenComponent {
  readonly auth = inject(KeycloakAuthService);
}
