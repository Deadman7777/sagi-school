import { Injectable, signal } from '@angular/core';
import { TranslateService } from '@ngx-translate/core';

export type Langue = 'fr' | 'ar' | 'en';

export interface LangueOption {
  code:  Langue;
  label: string;
  flag:  string;
  dir:   'ltr' | 'rtl';
}

@Injectable({ providedIn: 'root' })
export class LangueService {
  langueActuelle = signal<Langue>('fr');

  langues: LangueOption[] = [
    { code: 'fr', label: 'Français', flag: '🇫🇷', dir: 'ltr' },
    { code: 'ar', label: 'العربية',  flag: '🇸🇦', dir: 'rtl' },
    { code: 'en', label: 'English',  flag: '🇬🇧', dir: 'ltr' },
  ];

  constructor(private translate: TranslateService) {
    // Déclarer les langues disponibles
    this.translate.addLangs(['fr', 'ar', 'en']);
    this.translate.setDefaultLang('fr');

    // Charger la langue sauvegardée
    const saved = (localStorage.getItem('langue') as Langue) || 'fr';
    this.changerLangue(saved);
  }

  changerLangue(code: Langue) {
    this.translate.use(code);
    this.langueActuelle.set(code);
    localStorage.setItem('langue', code);

    const dir = this.langues.find(l => l.code === code)?.dir || 'ltr';
    document.documentElement.setAttribute('dir',  dir);
    document.documentElement.setAttribute('lang', code);
  }

  get langueActuelleInfo(): LangueOption {
    return this.langues.find(l => l.code === this.langueActuelle()) || this.langues[0];
  }
}
