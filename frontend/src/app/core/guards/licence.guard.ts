import { inject } from '@angular/core';
import { CanActivateChildFn, Router } from '@angular/router';
import { AuthService } from '../services/auth.service';

/**
 * Bloque la navigation directe (URL) vers les routes hors licence —
 * même logique que le filtrage du menu dans le shell : la liste
 * `modules` du token dépend du type de licence ET de son expiration
 * (réduite à /ma-licence + /parametres après la période de grâce).
 */
export const licenceGuard: CanActivateChildFn = (route) => {
  const auth   = inject(AuthService);
  const router = inject(Router);

  const modules: string[] = auth.currentUser()?.modules || [];
  if (modules.length === 0) return true; // SUPER_ADMIN (pas de tenant)

  const path = route.routeConfig?.path || '';
  if (path === '') return true; // redirection racine, le guard rejouera sur la cible
  if (modules.includes('/' + path)) return true;

  return router.createUrlTree(['/ma-licence']);
};
