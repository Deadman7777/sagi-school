import { Injectable, inject, signal } from '@angular/core';
import { AppModeService } from './app-mode.service';

/** Événement Chrome/Edge/Android, absent des types DOM standard. */
interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

/**
 * Bouton « Installer l'app » du mode cloud (raccourci bureau / écran d'accueil).
 *
 * Il ne s'agit PAS du mode local : l'app installée ouvre app.sagi-school.com
 * dans sa propre fenêtre, les données restent sur le serveur.
 *
 * Le navigateur émet `beforeinstallprompt` une seule fois, tôt, souvent avant
 * la connexion : le service doit donc être instancié au démarrage
 * (provideAppInitializer), pas par le shell.
 *
 * iPhone/iPad : Safari n'émet pas l'événement et n'offre aucune API
 * d'installation ; on ne peut qu'expliquer le geste (Partager → Sur l'écran
 * d'accueil).
 */
@Injectable({ providedIn: 'root' })
export class InstallationAppService {
  private appMode = inject(AppModeService);
  private invite: BeforeInstallPromptEvent | null = null;

  /** Chrome/Edge/Android : l'installation peut être proposée en un clic. */
  readonly disponible = signal(false);
  /** iOS hors app installée : seul le geste manuel est possible. */
  readonly iosManuel = signal(false);

  constructor() {
    if (!this.appMode.isCloud() || typeof window === 'undefined') return;
    if (this.dejaInstallee()) return;

    window.addEventListener('beforeinstallprompt', (e: Event) => {
      e.preventDefault();  // on garde la main : l'invite part du bouton
      this.invite = e as BeforeInstallPromptEvent;
      this.disponible.set(true);
    });
    window.addEventListener('appinstalled', () => this.oublier());

    const ua = navigator.userAgent;
    const ios = /iphone|ipad|ipod/i.test(ua)
      // iPadOS se déclare « Macintosh » mais a un écran tactile
      || (/macintosh/i.test(ua) && navigator.maxTouchPoints > 1);
    this.iosManuel.set(ios);
  }

  /** Ouvre l'invite du navigateur. Renvoie true si l'utilisateur accepte. */
  async installer(): Promise<boolean> {
    const invite = this.invite;
    if (!invite) return false;
    await invite.prompt();
    const { outcome } = await invite.userChoice;
    // Une invite ne sert qu'une fois ; le navigateur en réémettra une
    // plus tard si l'utilisateur a refusé.
    this.invite = null;
    this.disponible.set(false);
    if (outcome === 'accepted') this.oublier();
    return outcome === 'accepted';
  }

  private oublier() {
    this.invite = null;
    this.disponible.set(false);
    this.iosManuel.set(false);
  }

  private dejaInstallee(): boolean {
    return window.matchMedia?.('(display-mode: standalone)').matches
      || (navigator as Navigator & { standalone?: boolean }).standalone === true;
  }
}
