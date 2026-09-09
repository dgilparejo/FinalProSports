import { Component, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';

import { ButtonComponent } from './components/button/button.component';
import { ProfileMenuComponent } from './components/profile-menu/profile-menu.component';
import { BreadcrumbComponent } from './components/breadcrumb/breadcrumb.component';

import { APP_CONFIG } from './app.config';
import { IdentityService } from './services/identity/identity.service';
import { LoggerService } from './services/logger/logger.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, TranslatePipe, BreadcrumbComponent, ButtonComponent, ProfileMenuComponent],
  templateUrl: './app.component.html',
  styleUrl: './app.component.sass',
})
export class AppComponent {
  readonly config = inject(APP_CONFIG);
  readonly identity = inject(IdentityService);
  readonly logger = inject(LoggerService);
}
