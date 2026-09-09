import { Injectable, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router } from '@angular/router';
import { filter } from 'rxjs';

export interface Crumb {
  /** i18n key when the step is a fixed screen name, `null` when the text is already resolved (an entity name). */
  key: string | null;
  text: string;
  link: string | null;
}

/** Placeholder while the page is still fetching the name of the entity it is about. */
const PENDING = '…';

/** Screen names of the leaf routes that hang off a client. */
const LEAF: Record<string, string> = { intake: 'intake.title', propose: 'proposal.title' };

/**
 * Builds the breadcrumb from the URL, with one piece the URL cannot give: the name of the entity.
 * A page publishes that name with `set()` because it has already loaded it — the breadcrumb does not
 * fetch anything of its own. The name is dropped on every navigation so a stale one cannot be shown.
 */
@Injectable({ providedIn: 'root' })
export class BreadcrumbService {
  private readonly router = inject(Router);
  private readonly entity = signal<{ text: string; link: string | null } | null>(null);
  private readonly url = signal<string>(this.router.url);

  constructor() {
    this.router.events
      .pipe(
        filter((e): e is NavigationEnd => e instanceof NavigationEnd),
        takeUntilDestroyed(),
      )
      .subscribe((e) => {
        this.entity.set(null);
        this.url.set(e.urlAfterRedirects);
      });
  }

  /** `link` is only needed when the entity is not the current page (a saved diet points back to its client). */
  set(text: string | null | undefined, link: string | null = null): void {
    const clean = text?.trim();
    this.entity.set(clean ? { text: clean, link } : null);
  }

  readonly trail = computed<Crumb[]>(() => {
    const seg = this.url().split(/[?#]/)[0].split('/').filter(Boolean);
    const crumbs: Crumb[] = [{ key: 'nav.clients', text: '', link: '/' }];
    const entity = this.entity();

    if (seg[0] === 'clients' && seg[1]) {
      crumbs.push({ key: null, text: entity?.text ?? PENDING, link: `/clients/${seg[1]}` });
      const leaf = LEAF[seg[2]];
      if (leaf) crumbs.push({ key: leaf, text: '', link: null });
    } else if (seg[0] === 'diets' && seg[1]) {
      if (entity) crumbs.push({ key: null, text: entity.text, link: entity.link });
      crumbs.push({ key: 'view.title', text: '', link: null });
    } else {
      return [];
    }

    crumbs[crumbs.length - 1] = { ...crumbs[crumbs.length - 1], link: null };
    return crumbs;
  });
}
