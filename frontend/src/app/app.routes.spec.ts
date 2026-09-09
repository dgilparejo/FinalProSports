import { Route } from '@angular/router';

import { authGuard } from './core/guards/auth.guard';

import { routes } from './app.routes';

const guarded = routes.find((r) => r.path === '' && r.children) as Route;
const pages = guarded.children ?? [];

describe('routes', () => {
  it('declares the five pages, the access-denied page and a wildcard', () => {
    expect(pages.map((r) => r.path)).toEqual(['', 'clients/:id', 'clients/:id/intake', 'clients/:id/propose', 'diets/:id']);
    expect(routes.map((r) => r.path)).toEqual(['forbidden', '', '**']);
  });

  it('lazy-loads every page', () => {
    expect(pages.every((r) => typeof r.loadComponent === 'function')).toBeTrue();
    expect(typeof routes.find((r) => r.path === 'forbidden')?.loadComponent).toBe('function');
  });

  it('puts EVERY page behind the guard, so a new screen is protected by being added', () => {
    expect(guarded.canActivateChild).toEqual([authGuard]);
    expect(pages.length).toBe(5);
  });

  it('leaves the access-denied page outside the guard, or it would loop', () => {
    expect(routes.find((r) => r.path === 'forbidden')?.canActivate).toBeUndefined();
    expect(routes.find((r) => r.path === 'forbidden')?.canActivateChild).toBeUndefined();
  });
});
