import { Injectable, computed, inject, signal } from '@angular/core';
import { AuthService } from './auth.service';
import { AlerteLicence, LicencesService } from './licences.service';

export type NiveauLicence = 'ok' | 'attention' | 'urgent' | 'critique' | 'expiree';

const JOUR_MS = 86_400_000;
const HEURE_MS = 3_600_000;
/** En alerte ou paiement déclaré : on guette la confirmation de près. */
const VEILLE_MS = 5 * 60_000;
const CLE_RAPPEL = 'sagi_rappel_licence';

/**
 * Compte à rebours et alertes de fin de licence, en temps réel.
 *
 * Une seule source pour le badge de la barre du haut, le badge de l'icône de
 * l'application, le rappel de connexion, le bandeau prioritaire et l'écran
 * « Ma licence ». Le serveur calcule l'alerte (apps/licences/alertes.py :
 * paliers réglables, messages, formules chiffrées) ; ce service ne fait que
 * la relire — toutes les heures, toutes les 5 minutes quand une échéance
 * approche ou qu'un paiement attend sa confirmation, et au retour sur la
 * fenêtre. Un renouvellement confirmé par HADY GESMAN rend les modules
 * sans reconnexion.
 */
@Injectable({ providedIn: 'root' })
export class LicenceCompteurService {
  private auth = inject(AuthService);
  private licences = inject(LicencesService);

  readonly alerte = signal<AlerteLicence | null>(null);
  /** Compatibilité : la licence telle que la barre du haut l'affichait. */
  readonly licence = computed(() => {
    const a = this.alerte();
    return a?.licence ? { id: a.licence, date_fin: a.date_fin, type: a.type } : null;
  });
  /** Rappel affiché à la connexion (une fois par palier et par connexion). */
  readonly rappelVisible = signal(false);
  /** Dialogue « Renouveler maintenant » (hébergé par le shell). */
  readonly renouvellementVisible = signal(false);
  /** Message affiché quand le renouvellement vient d'être constaté. */
  readonly renouvellee = signal<string | null>(null);

  private maintenant = signal(Date.now());
  private demarre = false;
  private minuteur: ReturnType<typeof setTimeout> | null = null;
  private dernierChargement = 0;

  /** Jours pleins restants avant la date de fin (négatif si dépassée). */
  readonly joursRestants = computed<number | null>(() => {
    const l = this.alerte();
    if (!l?.date_fin) return null;
    const [a, m, j] = String(l.date_fin).split('-').map(Number);
    const fin = new Date(a, m - 1, j, 23, 59, 59).getTime();
    return Math.ceil((fin - this.maintenant()) / JOUR_MS) - 1;
  });

  /** Vert > 30 j · jaune ≤ 30 j · orange ≤ 15 j · rouge ≤ 7 j · expirée. */
  readonly niveau = computed<NiveauLicence>(() => {
    const j = this.joursRestants();
    if (j === null) return 'ok';
    if (j < 0) return 'expiree';
    if (j <= 7) return 'critique';
    if (j <= 15) return 'urgent';
    if (j <= 30) return 'attention';
    return 'ok';
  });

  demarrer() {
    if (this.demarre) return;
    this.demarre = true;
    this.charger();
    setInterval(() => this.maintenant.set(Date.now()), 60_000);
    // Retour sur l'onglet ou la fenêtre : le renouvellement a peut-être été confirmé.
    const auRetour = () => {
      if (document.visibilityState === 'visible' && Date.now() - this.dernierChargement > 60_000) this.charger();
    };
    document.addEventListener('visibilitychange', auRetour);
    window.addEventListener('focus', auRetour);
  }

  /** Relit l'alerte. `actualiser` : relit aussi le cloud tout de suite (installation locale). */
  charger(actualiser = false, apres?: (a: AlerteLicence | null) => void) {
    this.dernierChargement = Date.now();
    this.licences.getAlerte(actualiser).subscribe({
      next: a => {
        const avant = this.alerte();
        const nouvelle = a?.licence ? a : null;
        this.alerte.set(nouvelle);
        this.maintenant.set(Date.now());
        if (nouvelle) {
          this.constaterRenouvellement(avant, nouvelle);
          this.appliquerModules(nouvelle);
          this.decider(nouvelle);
        }
        this.appliquerBadge(nouvelle);
        this.planifier(nouvelle);
        apres?.(nouvelle);
      },
      error: () => { this.planifier(this.alerte()); apres?.(this.alerte()); },
    });
  }

  ouvrirRenouvellement() {
    this.rappelVisible.set(false);
    this.renouvellementVisible.set(true);
  }

  fermerRappel() {
    this.rappelVisible.set(false);
  }

  // ── Interne ────────────────────────────────────────────────────────────

  private planifier(a: AlerteLicence | null) {
    if (this.minuteur) clearTimeout(this.minuteur);
    const proche = !!a && (a.alerte || !!a.demande_en_attente);
    this.minuteur = setTimeout(() => this.charger(), proche ? VEILLE_MS : HEURE_MS);
  }

  /** Rappel à la connexion : une fois par palier, à chaque nouvelle connexion. */
  private decider(a: AlerteLicence) {
    if (!a.alerte) return;
    const connexion = (localStorage.getItem('refresh_token') || '').slice(-24);
    const cle = `${connexion}|${a.cle_rappel}`;
    let vu = '';
    try { vu = sessionStorage.getItem(CLE_RAPPEL) || ''; } catch { /* stockage indisponible */ }
    if (vu === cle) return;
    try { sessionStorage.setItem(CLE_RAPPEL, cle); } catch { /* idem */ }
    this.rappelVisible.set(true);
  }

  /** Date de fin repoussée ou accès rendu : on le dit, on ferme les alertes. */
  private constaterRenouvellement(avant: AlerteLicence | null, apres: AlerteLicence) {
    if (!avant?.date_fin || !apres.date_fin) return;
    if (apres.date_fin > avant.date_fin) {
      this.renouvellee.set(`Licence renouvelée jusqu'au ${apres.date_fin_longue}. Merci !`);
      this.rappelVisible.set(false);
      this.renouvellementVisible.set(false);
    }
  }

  /** Les modules suivent la licence sans reconnexion (le jeton les figeait jusqu'au prochain login). */
  private appliquerModules(a: AlerteLicence) {
    const user = this.auth.currentUser();
    if (!user || user.role === 'SUPER_ADMIN' || this.auth.impersonatedTenantId() || !a.modules?.length) return;
    const actuels = user.modules || [];
    if (actuels.length === a.modules.length && actuels.every(m => a.modules.includes(m))) return;
    const maj = { ...user, modules: a.modules };
    this.auth.currentUser.set(maj);
    try { localStorage.setItem('user', JSON.stringify(maj)); } catch { /* stockage indisponible */ }
  }

  /**
   * Badge sur l'icône : « 3 » à trois jours, un signal le jour J et après.
   * PWA installée (Chrome/Edge) : API Badging. Electron : pastille Windows /
   * compteur macOS-Linux (electron/badge-licence.js).
   */
  private appliquerBadge(a: AlerteLicence | null) {
    const badge = a?.badge ?? null;
    const nav: any = navigator;
    try {
      if (badge === null) nav.clearAppBadge?.();
      else if (typeof badge === 'number') nav.setAppBadge?.(badge);
      else nav.setAppBadge?.();
    } catch { /* navigateur sans API Badging */ }
    const electron = (window as any).electronAPI;
    if (electron?.badgeLicence) {
      electron.badgeLicence({
        nombre: badge === null ? null : typeof badge === 'number' ? badge : 0,
        image: badge === null ? null : this.dessinerPastille(String(badge)),
        texte: a?.titre || '',
        prioritaire: !!a?.prioritaire,
      });
    }
  }

  /** Pastille rouge 32×32 (Windows superpose une image, pas un nombre). */
  private dessinerPastille(texte: string): string | null {
    try {
      const c = document.createElement('canvas');
      c.width = c.height = 32;
      const g = c.getContext('2d');
      if (!g) return null;
      g.fillStyle = '#dc2626';
      g.beginPath(); g.arc(16, 16, 15, 0, Math.PI * 2); g.fill();
      g.fillStyle = '#ffffff';
      g.font = `bold ${texte.length > 1 ? 15 : 20}px Arial, sans-serif`;
      g.textAlign = 'center'; g.textBaseline = 'middle';
      g.fillText(texte, 16, 17);
      return c.toDataURL('image/png');
    } catch {
      return null;
    }
  }
}
