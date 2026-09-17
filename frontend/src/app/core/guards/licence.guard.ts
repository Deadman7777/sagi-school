import { inject } from '@angular/core';
import { CanActivateChildFn, Router } from '@angular/router';
import { AuthService } from '../services/auth.service';

/**
 * Bloque la navigation directe (URL) vers les routes hors licence —
 * même logique que le filtrage du menu dans le shell : la liste
 * `modules` du token dépend du type de licence ET de son expiration
 * (réduite à /ma-licence + /parametres après la période de grâce).
 */
/** Appel de la garderie : fait partie du module Élèves. */
const MODULE_PARENT: Record<string, string> = { garderie: '/eleves' };

export const licenceGuard: CanActivateChildFn = (route) => {
  const auth   = inject(AuthService);
  const router = inject(Router);

  const modules: string[] = auth.currentUser()?.modules || [];
  if (modules.length === 0) return true; // SUPER_ADMIN (pas de tenant)

  const path = route.routeConfig?.path || '';
  if (path === '') return true; // redirection racine, le guard rejouera sur la cible
  if (modules.includes('/' + path)) return true;
  // Écrans rattachés à un module existant : ouverts avec lui, sans exiger
  // une nouvelle connexion pour que le jeton porte leur route.
  const parent = MODULE_PARENT[path];
  if (parent && modules.includes(parent)) return true;

  return router.createUrlTree(['/ma-licence']);
};
