import { ApplicationConfig, inject, provideAppInitializer } from '@angular/core';
import { PreloadAllModules, provideRouter, withPreloading } from '@angular/router';
import { provideHttpClient, withInterceptors, HttpClient } from '@angular/common/http';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { providePrimeNG } from 'primeng/config';
import { provideTranslateService, TranslateLoader, TranslateService } from '@ngx-translate/core';
import Aura from '@primeuix/themes/aura';
import { routes } from './app.routes';
import { authInterceptor } from './core/interceptors/auth.interceptor';
import { Observable, firstValueFrom } from 'rxjs';
import { BUILD_ID } from '../build-id';
import { InstallationAppService } from './core/services/installation-app.service';

// Loader personnalisé — compatible toutes versions.
// Le paramètre ?v=BUILD_ID force le rechargement des traductions après chaque
// déploiement (cache-busting navigateur + Cloudflare).
class CustomTranslateLoader implements TranslateLoader {
  constructor(private http: HttpClient) {}
  getTranslation(lang: string): Observable<any> {
    return this.http.get(`/assets/i18n/${lang}.json?v=${BUILD_ID}`);
  }
}

export const appConfig: ApplicationConfig = {
  providers: [
    // Chaque module est un fichier séparé, téléchargé à la première entrée :
    // d'où un temps mort perceptible au premier clic (08/10/2026). Les
    // modules sont désormais chargés en arrière-plan juste après l'écran
    // d'accueil ; l'entrée dans un module ne télécharge plus rien.
    provideRouter(routes, withPreloading(PreloadAllModules)),
    provideHttpClient(withInterceptors([authInterceptor])),
    provideAnimationsAsync(),
    // Capte l'invite d'installation dès le chargement, avant la connexion.
    provideAppInitializer(() => { inject(InstallationAppService); }),
    // Les traductions sont chargées AVANT le premier écran. Sans cela, les
    // listes construites dans ngOnInit avec translate.instant() (rôles, types
    // d'employé, modes de paiement…) affichaient leurs clés brutes —
    // « parametres.admin_scolarite » — dès qu'on ouvrait une page directement.
    provideAppInitializer(() => {
      let langue = 'fr';
      try { langue = localStorage.getItem('langue') || 'fr'; } catch { /* stockage indisponible */ }
      return firstValueFrom(inject(TranslateService).use(langue)).catch(() => undefined);
    }),
    providePrimeNG({
      theme: { preset: Aura, options: { darkModeSelector: '.dark-mode' } }
    }),
    provideTranslateService({
      loader: {
        provide:    TranslateLoader,
        useFactory: (http: HttpClient) => new CustomTranslateLoader(http),
        deps:       [HttpClient]
      },
      fallbackLang: 'fr',
    }),
  ]
};
