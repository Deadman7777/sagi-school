import { ChangeDetectionStrategy, Component, OnDestroy, OnInit, computed, inject, input,
         signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { TranslateModule } from '@ngx-translate/core';
import { catchError, forkJoin, of } from 'rxjs';

import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';

interface CarteModule {
  route: string;
  queryParams?: Record<string, string>;
  icone: string;
  titre: string;
  /** Deux ou trois chiffres, tels que le module les affiche. */
  chiffres: { libelle: string; valeur: string; ton?: 'bon' | 'alerte' | 'neutre' }[];
  /** La chose à faire, s'il y en a une. */
  action?: string;
}

/**
 * Tous les modules, vus depuis le tableau de bord.
 *
 * Chaque carte relit l'API DU MODULE — celle que son propre écran affiche —
 * et jamais un calcul refait ici : le chiffre du tableau de bord est donc
 * exactement celui qu'on retrouve en cliquant. Un module que la licence ou le
 * rôle n'ouvre pas n'a pas de carte ; un module qui ne répond pas non plus,
 * plutôt qu'un zéro qui passerait pour une vérité.
 */
@Component({
  selector: 'app-synthese-modules',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, RouterLink, TranslateModule],
  template: `
    @if (cartes().length) {
      <section class="synthese" aria-labelledby="synthese-titre">
        <h3 id="synthese-titre" class="titre">🧩 {{ 'dashboard.modules_titre' | translate }}</h3>
        <p class="aide">{{ 'dashboard.modules_aide' | translate }}</p>
        <div class="grille">
          @for (c of cartes(); track c.route + c.titre) {
            <a class="carte" [routerLink]="c.route" [queryParams]="c.queryParams">
              <span class="tete"><span aria-hidden="true">{{ c.icone }}</span> {{ c.titre }}</span>
              @for (ch of c.chiffres; track ch.libelle) {
                <span class="ligne">
                  <span class="lib">{{ ch.libelle }}</span>
                  <span class="val" [class.bon]="ch.ton === 'bon'" [class.alerte]="ch.ton === 'alerte'">
                    {{ ch.valeur }}</span>
                </span>
              }
              @if (c.action) { <span class="action">{{ c.action }}</span> }
              <span class="ouvrir">{{ 'dashboard.ouvrir_module' | translate }} →</span>
            </a>
          }
        </div>
      </section>
    }
  `,
  styles: [`
    .synthese { margin: 18px 0; }
    .titre { margin: 0 0 4px; font-size: 15px; }
    .aide { margin: 0 0 10px; font-size: 12px; color: var(--text-3); }
    .grille { display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); }
    .carte { display: flex; flex-direction: column; gap: 6px; padding: 12px 14px;
      border: 1px solid var(--border); border-radius: 10px; background: var(--surface);
      color: var(--text); text-decoration: none; transition: border-color .15s; }
    .carte:hover, .carte:focus-visible { border-color: #00d4aa; }
    .tete { font-weight: 600; font-size: 13px; }
    .ligne { display: flex; justify-content: space-between; gap: 8px; font-size: 12px; }
    .lib { color: var(--text-3); }
    .val { font-weight: 600; font-variant-numeric: tabular-nums; }
    .val.bon { color: #10b981; }
    .val.alerte { color: #ef4444; }
    .action { font-size: 11.5px; color: #f59e0b; }
    .ouvrir { margin-top: auto; font-size: 11.5px; color: #00d4aa; }
  `],
})
export class SyntheseModulesComponent implements OnInit, OnDestroy {
  private api = inject(ApiService);
  private auth = inject(AuthService);

  /** Mois de référence : celui du « pilotage du mois » du tableau de bord. */
  mois = input<number | null>(null);
  annee = input<number | null>(null);
  libelleMois = input<string>('');

  private resultats = signal<Record<string, any>>({});

  // Même cadence que le reste du tableau de bord : chaque minute tant que
  // l'onglet est visible, et dès qu'on y revient après avoir saisi ailleurs.
  private timer?: ReturnType<typeof setInterval>;
  private surRetour = () => { if (document.visibilityState === 'visible') this.charger(); };

  ngOnInit() {
    this.charger();
    this.timer = setInterval(() => {
      if (document.visibilityState === 'visible') this.charger();
    }, 60_000);
    document.addEventListener('visibilitychange', this.surRetour);
  }

  ngOnDestroy() {
    if (this.timer) clearInterval(this.timer);
    document.removeEventListener('visibilitychange', this.surRetour);
  }

  private ouvert(route: string): boolean {
    const modules = this.auth.currentUser()?.modules || [];
    return modules.length === 0 || modules.includes(route);
  }

  charger() {
    const rien = of(null);
    const lire = (route: string, url: string, params?: Record<string, any>) =>
      this.ouvert(route) ? this.api.get<any>(url, params).pipe(catchError(() => rien)) : rien;
    const mois = this.mois() || new Date().getMonth() + 1;
    const annee = this.annee() || new Date().getFullYear();
    forkJoin({
      organismes: lire('/eleves', '/eleves/organismes/suivi/'),
      familles:   lire('/eleves', '/eleves/familles/', { page_size: 1 }),
      garderie:   lire('/eleves', '/eleves/garderie/recap/', { mois }),
      rh:         lire('/rh', '/rh/stats/'),
      bulletins:  lire('/rh', '/rh/bulletins/', { mois, annee, page_size: 1 }),
      fiscal:     lire('/fiscal', '/fiscal/conseils/'),
      academique: lire('/academique', '/academique/analyse/'),
      gmrf:       lire('/gmrf', '/gmrf/dashboard/'),
      gouvernance: lire('/gouvernance', '/gouvernance/dashboard/'),
    }).subscribe(r => this.resultats.set({ ...r, mois }));
  }

  cartes = computed<CarteModule[]>(() => {
    const r = this.resultats();
    const f = (n: number) => Math.round(n || 0).toLocaleString('fr-FR');
    const cartes: CarteModule[] = [];

    if (r['familles'] || r['organismes']) {
      const org = r['organismes']?.totaux;
      cartes.push({
        route: '/eleves', icone: '👪', titre: 'Familles et boursiers',
        chiffres: [
          { libelle: 'Familles regroupées', valeur: f(r['familles']?.count ?? 0) },
          { libelle: 'Boursiers', valeur: f(org?.nb_boursiers ?? 0) },
          { libelle: 'Dû par les organismes', valeur: f(org?.reste ?? 0) + ' F',
            ton: (org?.reste || 0) > 0 ? 'alerte' : 'bon' },
        ],
        action: (org?.reste || 0) > 0 ? 'Encaisser la bourse ou envoyer le relevé' : undefined,
      });
    }
    if (r['garderie']?.enfants?.length) {
      const t = r['garderie'].totaux;
      cartes.push({
        route: '/garderie', icone: '🧸',
        titre: 'Garderie — ' + (this.libelleMois() || 'mois en cours'),
        chiffres: [
          { libelle: 'Enfants gardés', valeur: f(r['garderie'].enfants.length) },
          { libelle: 'Dû du mois', valeur: f(t.du) + ' F' },
          { libelle: 'Reste à encaisser', valeur: f(t.reste) + ' F',
            ton: t.reste > 0 ? 'alerte' : 'bon' },
        ],
      });
    }
    if (r['rh']) {
      const actifs = r['rh'].actifs || 0;
      const faits = r['bulletins']?.count ?? 0;
      cartes.push({
        route: '/rh', icone: '👥', titre: 'Personnel et paie',
        chiffres: [
          { libelle: 'Salariés présents', valeur: f(actifs) },
          { libelle: 'Masse salariale / mois', valeur: f(r['rh'].masse_salariale) + ' F' },
          { libelle: 'Bulletins du mois', valeur: `${faits} / ${actifs}`,
            ton: faits >= actifs ? 'bon' : 'alerte' },
        ],
        action: faits < actifs ? `${actifs - faits} bulletin(s) à produire` : undefined,
      });
    }
    if (r['fiscal']) {
      const attention = (r['fiscal'].conseils || []).filter((c: any) => c.niveau === 'ATTENTION');
      cartes.push({
        route: '/fiscal', icone: '📋', titre: 'Fiscal et obligations',
        chiffres: [
          { libelle: 'Points à traiter', valeur: f(attention.length),
            ton: attention.length ? 'alerte' : 'bon' },
        ],
        action: attention[0]?.titre,
      });
    }
    if (r['academique']?.distribution) {
      const d = r['academique'].distribution;
      const total = d.excellent + d.bien + d.assez_bien + d.passable + d.insuffisant;
      const reussite = total ? (100 * (total - d.insuffisant) / total) : 0;
      cartes.push({
        route: '/academique', icone: '📚', titre: 'Résultats scolaires',
        chiffres: [
          { libelle: `Élèves classés (${r['academique'].trimestre_ref || '—'})`, valeur: f(total) },
          { libelle: 'Moyenne ≥ passable', valeur: total ? reussite.toFixed(1) + ' %' : '—',
            ton: reussite >= 50 ? 'bon' : 'alerte' },
          { libelle: 'En difficulté', valeur: f(d.insuffisant),
            ton: d.insuffisant ? 'alerte' : 'bon' },
        ],
      });
    }
    if (r['gmrf']) {
      const retards = (r['gmrf'].echeances_a_venir || []).filter((e: any) => e.en_retard);
      cartes.push({
        route: '/gmrf', icone: '🏦', titre: 'Ressources financières',
        chiffres: [
          { libelle: 'Mobilisé hors scolarité', valeur: f(r['gmrf'].ressources?.total_mobilise) + ' F' },
          { libelle: 'Capital de prêts restant dû', valeur: f(r['gmrf'].prets?.capital_restant_du) + ' F' },
          { libelle: 'Échéances en retard', valeur: f(retards.length),
            ton: retards.length ? 'alerte' : 'bon' },
        ],
        action: retards.length
          ? `${f(retards.reduce((t: number, e: any) => t + e.montant, 0))} F à régler` : undefined,
      });
    }
    if (r['gouvernance']?.ressources) {
      const g = r['gouvernance'];
      cartes.push({
        route: '/gouvernance', icone: '🎯', titre: 'Projets et ressources',
        chiffres: [
          { libelle: 'Projets', valeur: f(g.pilotage?.indicateurs?.nb_projets) },
          { libelle: 'Ressources consommées',
            valeur: (g.pilotage?.taux_consommation ?? 0).toFixed(1) + ' %' },
          { libelle: 'Disponible', valeur: f(g.ressources.total_disponible) + ' F' },
        ],
        action: (g.pilotage?.alertes || []).length ? g.pilotage.alertes[0].message : undefined,
      });
    }
    return cartes;
  });
}
