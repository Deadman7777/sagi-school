import { Routes } from '@angular/router';
import { authGuard } from './core/guards/auth.guard';

export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () => import('./features/auth/login/login.component').then(m => m.LoginComponent)
  },
  {
    path: '',
    loadComponent: () => import('./layout/shell/shell.component').then(m => m.ShellComponent),
    canActivate: [authGuard],
    children: [
      { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
      { path: 'dashboard',    loadComponent: () => import('./features/dashboard/dashboard.component').then(m => m.DashboardComponent) },
      { path: 'eleves',       loadComponent: () => import('./features/eleves/liste/eleves-liste.component').then(m => m.ElevesListeComponent) },
      { path: 'paiements',    loadComponent: () => import('./features/paiements/paiements.component').then(m => m.PaiementsComponent) },
      { path: 'comptabilite', loadComponent: () => import('./features/comptabilite/comptabilite.component').then(m => m.ComptabiliteComponent) },
      { path: 'fiscal',       loadComponent: () => import('./features/fiscal/fiscal.component').then(m => m.FiscalComponent) },
      { path: 'licences',     loadComponent: () => import('./features/licences/licences.component').then(m => m.LicencesComponent) },
      { path: 'ma-licence',   loadComponent: () => import('./features/ma-licence/ma-licence.component').then(m => m.MaLicenceComponent) },
      { path: 'parametres',   loadComponent: () => import('./features/parametres/parametres.component').then(m => m.ParametresComponent) },
      {
        path: 'suivi-mensuel',
        loadComponent: () => import('./features/suivi-mensuel/suivi-mensuel.component')
          .then(m => m.SuiviMensuelComponent)
      },
    ]
  },
  { path: '**', redirectTo: '' }
];
