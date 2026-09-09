import { Routes } from '@angular/router';

import { authGuard } from './core/guards/auth.guard';

/**
 * Every page of the application hangs off one guarded parent, so a new screen is protected by being
 * added rather than by remembering to guard it. `/forbidden` sits OUTSIDE it: it is where the guard
 * sends someone who lacks the role, and guarding it would loop.
 */
export const routes: Routes = [
  {
    path: 'forbidden',
    loadComponent: () => import('./pages/forbidden/forbidden.component').then((m) => m.ForbiddenComponent),
    title: 'Acceso denegado · Final Pro Sports',
  },
  {
    path: '',
    canActivateChild: [authGuard],
    children: [
      { path: '', loadComponent: () => import('./pages/clients/clients.component').then((m) => m.ClientsComponent), title: 'Clientes · Final Pro Sports' },
      {
        path: 'clients/:id',
        loadComponent: () => import('./pages/client-detail/client-detail.component').then((m) => m.ClientDetailComponent),
        title: 'Ficha · Final Pro Sports',
      },
      {
        path: 'clients/:id/intake',
        loadComponent: () => import('./pages/client-intake/client-intake.component').then((m) => m.ClientIntakeComponent),
        title: 'Alta · Final Pro Sports',
      },
      {
        path: 'clients/:id/propose',
        loadComponent: () => import('./pages/diet-proposal/diet-proposal.component').then((m) => m.DietProposalComponent),
        title: 'Propuesta · Final Pro Sports',
      },
      {
        path: 'diets/:id',
        loadComponent: () => import('./pages/diet-view/diet-view.component').then((m) => m.DietViewComponent),
        title: 'Dieta guardada · Final Pro Sports',
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
