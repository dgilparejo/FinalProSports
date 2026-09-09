import { Component, inject } from '@angular/core';
import { RouterLink } from '@angular/router';
import { TranslatePipe } from '@ngx-translate/core';

import { BreadcrumbService } from '@services/breadcrumb/breadcrumb.service';

/** Where you are and one click back to each step above. Renders nothing on the list, which has nothing above it. */
@Component({
  selector: 'app-breadcrumb',
  imports: [RouterLink, TranslatePipe],
  template: `
    @if (breadcrumb.trail().length > 1) {
      <nav class="crumbs" aria-label="Ruta de navegación">
        @for (c of breadcrumb.trail(); track $index) {
          @if (!$first) {
            <span class="sep material-icons" aria-hidden="true">chevron_right</span>
          }
          @if (c.link) {
            <a [routerLink]="c.link">{{ c.key ? (c.key | translate) : c.text }}</a>
          } @else {
            <span class="here" aria-current="page">{{ c.key ? (c.key | translate) : c.text }}</span>
          }
        }
      </nav>
    }
  `,
  styles: `
    :host {
      display: block;
    }
    .crumbs {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 2px;
      font-size: 13px;
      margin-bottom: 12px;
      min-width: 0;
    }
    a {
      color: var(--text-muted);
      text-decoration: none;
      padding: 2px 4px;
      border-radius: var(--radius);
    }
    a:hover,
    a:focus-visible {
      color: var(--accent);
      background: var(--surface-alt);
    }
    .here {
      color: var(--text);
      font-weight: 600;
      padding: 2px 4px;
      min-width: 0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .sep {
      font-size: 16px;
      color: var(--text-faint);
    }
  `,
})
export class BreadcrumbComponent {
  readonly breadcrumb = inject(BreadcrumbService);
}
