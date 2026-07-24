import { Injectable, signal } from '@angular/core';

export type Theme = 'dark' | 'light';
const STORAGE_KEY = 'sagi-theme';

/**
 * Gère le thème visuel de l'application (sombre par défaut, clair en option).
 * Le choix est persisté dans le navigateur et appliqué via une classe sur
 * <body> (theme-dark / theme-light) qui redéfinit les tokens CSS de styles.scss.
 */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  readonly theme = signal<Theme>(this.read());

  /** À appeler une fois au démarrage pour appliquer le thème persisté. */
  init(): void {
    this.apply(this.theme());
  }

  set(theme: Theme): void {
    this.theme.set(theme);
    try { localStorage.setItem(STORAGE_KEY, theme); } catch { /* stockage indisponible */ }
    this.apply(theme);
  }

  toggle(): void {
    this.set(this.theme() === 'dark' ? 'light' : 'dark');
  }

  private read(): Theme {
    try {
      return localStorage.getItem(STORAGE_KEY) === 'light' ? 'light' : 'dark';
    } catch {
      return 'dark';
    }
  }

  private apply(theme: Theme): void {
    const body = document.body;
    body.classList.toggle('theme-light', theme === 'light');
    body.classList.toggle('theme-dark', theme === 'dark');
  }
}
