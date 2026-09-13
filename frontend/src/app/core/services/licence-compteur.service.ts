import { Injectable, computed, inject, signal } from '@angular/core';
import { AuthService } from './auth.service';
import { LicencesService } from './licences.service';

export type NiveauLicence = 'ok' | 'attention' | 'urgent' | 'critique' | 'expiree';

const JOUR_MS = 86_400_000;

/**
 * Compte à rebours de la licence de l'école, en temps réel.
 *
 * Une seule source pour le badge permanent de la barre du haut et pour
 * l'écran « Ma licence » : les jours restants sont recalculés chaque minute
 * depuis la date de fin, et la licence est relue toutes les heures (un
 * renouvellement fait par HADY GESMAN apparaît sans reconnexion).
 */
@Injectable({ providedIn: 'root' })
export class LicenceCompteurService {
  private auth = inject(AuthService);
  private licences = inject(LicencesService);

  readonly licence = signal<any | null>(null);
  private maintenant = signal(Date.now());
  private demarre = false;

  /** Jours pleins restants avant la date de fin (négatif si dépassée). */
  readonly joursRestants = computed<number | null>(() => {
    const l = this.licence();
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
    setInterval(() => this.charger(), 3_600_000);
  }

  charger() {
    this.licences.getLicences().subscribe({
      next: res => {
        const liste = res?.results || res || [];
        const tenantId = this.auth.effectiveTenantId;
        const l = tenantId ? liste.find((x: any) => x.tenant === tenantId) : null;
        this.licence.set(l || (liste.length === 1 ? liste[0] : null));
        this.maintenant.set(Date.now());
      },
      error: () => {},
    });
  }
}
