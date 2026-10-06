import {
  ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal,
} from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { SelectModule } from 'primeng/select';
import { ApiService } from '../../core/services/api.service';
import { BoutonImprimerComponent } from '../../shared/bouton-imprimer.component';

type CodeMode = 'ESPECE' | 'WAVE' | 'ORANGE_MONEY' | 'FREE_MONEY' | 'BANQUE';

interface Montants { total: number; par_mode: Record<CodeMode, number>; }

interface Cumul {
  nb_operations: number; nb_annulations: number;
  /** Signé : négatif quand on annule un encaissement, positif pour une dépense. */
  entrees: Montants; sorties: Montants; annulations: Montants; solde: number;
}

interface LigneResponsable extends Cumul { id: string; nom: string; }

interface Jour extends Cumul {
  date: string; nb_transferts: number; solde_fin: Montants; responsables: LigneResponsable[];
}

interface Mois extends Cumul { annee: number; mois: number; libelle: string; solde_fin: Montants; }

interface Operation {
  heure: string; piece: string; libelle: string; mode: CodeMode; mode_libelle: string;
  nature: 'OPERATION' | 'ANNULATION' | 'TRANSFERT'; annulee_jour: boolean;
  entree: number; sortie: number; responsable: string;
}

export interface PointTresorerie {
  exercice: string; exercice_id: string; debut: string; fin: string; genere_le: string;
  modes: { code: CodeMode; libelle: string }[];
  solde_ouverture: Montants; solde_cloture: Montants;
  totaux: Cumul; responsables: LigneResponsable[]; jours: Jour[]; mois: Mois[];
  operations?: Operation[];
}

type Periode = 'jour' | 'mois';

const RAFRAICHISSEMENT_MS = 60_000;

function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

const JOURS = ['dim.', 'lun.', 'mar.', 'mer.', 'jeu.', 'ven.', 'sam.'];

/** « lun. 25/05/2026 » — sans dépendre de la locale enregistrée dans l'app. */
function dateCourte(isoDate: string): string {
  const [a, m, j] = isoDate.split('-').map(Number);
  return `${JOURS[new Date(a, m - 1, j).getDay()]} ${String(j).padStart(2, '0')}/${String(m).padStart(2, '0')}/${a}`;
}

function finDuMois(annee: number, mois: number): string {
  return iso(new Date(annee, mois, 0));
}

/**
 * Point de trésorerie — le point que les chargés de scolarité font chaque soir :
 * nombre d'opérations, entrées et sorties par mode, par responsable, et ce que
 * la trésorerie doit contenir en fin de journée ; le mois entier et l'exercice
 * mois par mois se relisent de la même façon. Mêmes chiffres que le PDF et que
 * les soldes par canal du tableau de bord : tout vient du journal.
 */
@Component({
  selector: 'app-point-tresorerie',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [BoutonImprimerComponent, DecimalPipe, DatePipe, FormsModule, ButtonModule, SelectModule],
  template: `
<div class="pt">
  <div class="pt-head">
    <div>
      <h3 class="pt-title">🧾 Point de trésorerie</h3>
      <div class="pt-sub">
        @if (point(); as p) {
          Exercice {{ p.exercice }} · mis à jour à {{ p.genere_le | date:'HH:mm:ss' }} · actualisation automatique
        } @else { Chargement… }
      </div>
    </div>
    <div class="pt-actions">
      <div class="bascule" role="radiogroup" aria-label="Période du point">
        <button type="button" role="radio" [attr.aria-checked]="periode() === 'jour'"
                [class.active]="periode() === 'jour'" (click)="voirJour(jour())">Journée</button>
        <button type="button" role="radio" [attr.aria-checked]="periode() === 'mois'"
                [class.active]="periode() === 'mois'" (click)="voirMois(moisCle())">Mois</button>
      </div>
      @if (periode() === 'jour') {
        <input type="date" class="pt-date" aria-label="Jour du point"
               [ngModel]="jour()" (ngModelChange)="voirJour($event)" />
        <p-button label="Aujourd'hui" [text]="true" size="small" (onClick)="voirJour(aujourdhui)" />
      } @else {
        <p-select [options]="optionsMois()" optionLabel="libelle" optionValue="cle"
                  [ngModel]="moisCle()" (ngModelChange)="voirMois($event)"
                  ariaLabel="Mois du point" styleClass="pt-select" appendTo="body" />
      }
      <p-button icon="pi pi-refresh" [text]="true" severity="secondary" ariaLabel="Actualiser"
                [loading]="loading()" (onClick)="charger()" />
      <p-button label="PDF à signer" icon="pi pi-file-pdf" severity="danger"
                [loading]="pdfEnCours()" [disabled]="!point()" (onClick)="telechargerPdf()" />
      <app-bouton-imprimer [pdf]="pdfPoint" [disabled]="!point()" [taille]="undefined" />
    </div>
  </div>

  @if (erreur()) {
    <div class="pt-erreur" role="alert">{{ erreur() }}</div>
  }

  @if (point(); as p) {
    <div class="kpis">
      <div class="kpi" style="--acc:#0369a1">
        <div class="kpi-l">Trésorerie à l'ouverture</div>
        <div class="kpi-v">{{ p.solde_ouverture.total | number:'1.0-0' }}</div>
        <div class="kpi-s">{{ periode() === 'jour' ? 'début de journée' : 'début du mois' }}</div>
      </div>
      <div class="kpi" style="--acc:#7c3aed">
        <div class="kpi-l">Opérations</div>
        <div class="kpi-v">{{ p.totaux.nb_operations }}</div>
        <div class="kpi-s">
          @if (p.totaux.nb_annulations) { {{ p.totaux.nb_annulations }} annulation(s) }
          @else { aucune annulation }
        </div>
      </div>
      <div class="kpi" style="--acc:#059669">
        <div class="kpi-l">Total entrées</div>
        <div class="kpi-v txt-vert">{{ p.totaux.entrees.total | number:'1.0-0' }}</div>
        <div class="kpi-s">FCFA</div>
      </div>
      <div class="kpi" style="--acc:#d97706">
        <div class="kpi-l">Total sorties</div>
        <div class="kpi-v txt-orange">{{ p.totaux.sorties.total | number:'1.0-0' }}</div>
        <div class="kpi-s">FCFA</div>
      </div>
      <div class="kpi" [style.--acc]="p.totaux.solde >= 0 ? '#059669' : '#dc2626'">
        <div class="kpi-l">{{ periode() === 'jour' ? 'Solde du jour' : 'Solde du mois' }}</div>
        <div class="kpi-v" [class.txt-rouge]="p.totaux.solde < 0">{{ p.totaux.solde | number:'1.0-0' }}</div>
        <div class="kpi-s">entrées − sorties{{ p.totaux.annulations.total ? ' ± annulations' : '' }}</div>
      </div>
      <div class="kpi" style="--acc:#00d4aa">
        <div class="kpi-l">Trésorerie à la clôture</div>
        <div class="kpi-v">{{ p.solde_cloture.total | number:'1.0-0' }}</div>
        <div class="kpi-s">ce que la trésorerie doit contenir</div>
      </div>
    </div>

    <div class="grille">
      <section class="bloc">
        <h4 class="bloc-titre">Par mode de paiement</h4>
        <div class="table-wrap">
          <table class="tbl">
            <thead>
              <tr>
                <th scope="col">Mode</th><th scope="col" class="tr">Ouverture</th>
                <th scope="col" class="tr">Entrées</th><th scope="col" class="tr">Sorties</th>
                @if (aAnnulations()) { <th scope="col" class="tr">Annulations</th> }
                <th scope="col" class="tr">Clôture</th>
              </tr>
            </thead>
            <tbody>
              @for (m of modesActifs(); track m.code) {
                <tr>
                  <td class="gras">{{ m.libelle }}</td>
                  <td class="tr">{{ p.solde_ouverture.par_mode[m.code] | number:'1.0-0' }}</td>
                  <td class="tr txt-vert">{{ p.totaux.entrees.par_mode[m.code] | number:'1.0-0' }}</td>
                  <td class="tr txt-orange">{{ p.totaux.sorties.par_mode[m.code] | number:'1.0-0' }}</td>
                  @if (aAnnulations()) { <td class="tr">{{ p.totaux.annulations.par_mode[m.code] | number:'1.0-0' }}</td> }
                  <td class="tr gras">{{ p.solde_cloture.par_mode[m.code] | number:'1.0-0' }}</td>
                </tr>
              }
            </tbody>
            <tfoot>
              <tr>
                <td>Total</td>
                <td class="tr">{{ p.solde_ouverture.total | number:'1.0-0' }}</td>
                <td class="tr">{{ p.totaux.entrees.total | number:'1.0-0' }}</td>
                <td class="tr">{{ p.totaux.sorties.total | number:'1.0-0' }}</td>
                @if (aAnnulations()) { <td class="tr">{{ p.totaux.annulations.total | number:'1.0-0' }}</td> }
                <td class="tr">{{ p.solde_cloture.total | number:'1.0-0' }}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </section>
    </div>

      <section class="bloc">
        <h4 class="bloc-titre">Par responsable</h4>
        <div class="table-wrap">
          <table class="tbl">
            <thead>
              <tr>
                <th scope="col">Responsable</th><th scope="col" class="tr">Opérations</th>
                @for (m of modesActifs(); track m.code) {
                  <th scope="col" class="tr">{{ m.libelle }}</th>
                }
                <th scope="col" class="tr">Entrées</th><th scope="col" class="tr">Sorties</th>
                <th scope="col" class="tr">Solde</th>
              </tr>
            </thead>
            <tbody>
              @for (r of p.responsables; track r.id + r.nom) {
                <tr>
                  <td class="gras">{{ r.nom }}
                    @if (r.nb_annulations) { <div class="petit">{{ r.nb_annulations }} annulation(s)</div> }
                  </td>
                  <td class="tr">{{ r.nb_operations }}</td>
                  @for (m of modesActifs(); track m.code) {
                    <td class="tr">{{ r.entrees.par_mode[m.code] | number:'1.0-0' }}</td>
                  }
                  <td class="tr txt-vert gras">{{ r.entrees.total | number:'1.0-0' }}</td>
                  <td class="tr txt-orange">{{ r.sorties.total | number:'1.0-0' }}</td>
                  <td class="tr gras" [class.txt-rouge]="r.solde < 0">{{ r.solde | number:'1.0-0' }}</td>
                </tr>
              } @empty {
                <tr><td [attr.colspan]="modesActifs().length + 5" class="vide">Aucune opération sur la période.</td></tr>
              }
            </tbody>
          </table>
        </div>
      </section>

    @if (periode() === 'jour') {
      <section class="bloc">
        <div class="bloc-entete">
          <h4 class="bloc-titre">Opérations de la journée ({{ operationsFiltrees().length }})</h4>
          <select class="filtre" aria-label="Filtrer par responsable"
                  [ngModel]="filtreResponsable()" (ngModelChange)="filtreResponsable.set($event)">
            <option value="">Tous les responsables</option>
            @for (r of p.responsables; track r.id + r.nom) { <option [value]="r.nom">{{ r.nom }}</option> }
          </select>
        </div>
        <div class="table-wrap">
          <table class="tbl">
            <thead>
              <tr>
                <th scope="col">Heure</th><th scope="col">Pièce</th><th scope="col">Libellé</th>
                <th scope="col">Mode</th><th scope="col" class="tr">Entrée</th>
                <th scope="col" class="tr">Sortie</th><th scope="col">Responsable</th>
              </tr>
            </thead>
            <tbody>
              @for (o of operationsFiltrees(); track $index) {
                <tr [class.ligne-annulation]="o.nature === 'ANNULATION' || o.annulee_jour" [class.barree]="o.annulee_jour">
                  <td>{{ o.heure }}</td>
                  <td class="mono">{{ o.piece }}</td>
                  <td>
                    @if (o.annulee_jour) { <span class="tag" title="Erreur de saisie corrigée le jour même : hors des totaux">Annulé le jour même</span> }
                    @else if (o.nature === 'ANNULATION') { <span class="tag tag-annul">Annulation</span> }
                    @if (o.nature === 'TRANSFERT') { <span class="tag">Transfert</span> }
                    {{ o.libelle }}
                  </td>
                  <td>{{ o.mode_libelle }}</td>
                  <td class="tr txt-vert">{{ o.entree ? (o.entree | number:'1.0-0') : '' }}</td>
                  <td class="tr txt-orange">{{ o.sortie ? (o.sortie | number:'1.0-0') : '' }}</td>
                  <td>{{ o.responsable }}</td>
                </tr>
              } @empty {
                <tr><td colspan="7" class="vide">Aucune opération ce jour.</td></tr>
              }
            </tbody>
          </table>
        </div>
      </section>
    } @else {
      <section class="bloc">
        <h4 class="bloc-titre">Jour par jour <span class="aide">— cliquez sur un jour pour le détail de ses opérations</span></h4>
        <div class="table-wrap">
          <table class="tbl">
            <thead>
              <tr>
                <th scope="col">Date</th><th scope="col">Responsable</th>
                <th scope="col" class="tr">Opérations</th>
                @for (m of modesActifs(); track m.code) {
                  <th scope="col" class="tr">{{ m.libelle }}</th>
                }
                <th scope="col" class="tr">Entrées</th><th scope="col" class="tr">Sorties</th>
                @if (aAnnulations()) { <th scope="col" class="tr">Annulations</th> }
                <th scope="col" class="tr">Solde du jour</th><th scope="col" class="tr">Trésorerie fin de journée</th>
              </tr>
            </thead>
            <tbody>
              @for (j of p.jours; track j.date) {
                <tr class="ligne-jour" tabindex="0" (click)="voirJour(j.date)" (keydown.enter)="voirJour(j.date)">
                  <td class="gras nowrap">{{ dateCourte(j.date) }}</td>
                  <td class="petit">Tous</td>
                  <td class="tr">{{ j.nb_operations }}</td>
                  @for (m of modesActifs(); track m.code) {
                    <td class="tr">{{ j.entrees.par_mode[m.code] | number:'1.0-0' }}</td>
                  }
                  <td class="tr txt-vert gras">{{ j.entrees.total | number:'1.0-0' }}</td>
                  <td class="tr txt-orange">{{ j.sorties.total | number:'1.0-0' }}</td>
                  @if (aAnnulations()) { <td class="tr">{{ j.annulations.total | number:'1.0-0' }}</td> }
                  <td class="tr" [class.txt-rouge]="j.solde < 0">{{ j.solde | number:'1.0-0' }}</td>
                  <td class="tr gras">{{ j.solde_fin.total | number:'1.0-0' }}</td>
                </tr>
                @if (j.responsables.length > 1) {
                  @for (r of j.responsables; track r.id + r.nom) {
                    <tr class="ligne-resp">
                      <td></td>
                      <td>{{ r.nom }}</td>
                      <td class="tr">{{ r.nb_operations }}</td>
                      @for (m of modesActifs(); track m.code) {
                        <td class="tr">{{ r.entrees.par_mode[m.code] | number:'1.0-0' }}</td>
                      }
                      <td class="tr">{{ r.entrees.total | number:'1.0-0' }}</td>
                      <td class="tr">{{ r.sorties.total | number:'1.0-0' }}</td>
                      @if (aAnnulations()) { <td class="tr">{{ r.annulations.total | number:'1.0-0' }}</td> }
                      <td class="tr">{{ r.solde | number:'1.0-0' }}</td>
                      <td></td>
                    </tr>
                  }
                } @else if (j.responsables.length === 1) {
                  <tr class="ligne-resp"><td></td><td [attr.colspan]="modesActifs().length + (aAnnulations() ? 7 : 6)">{{ j.responsables[0].nom }}</td></tr>
                }
              } @empty {
                <tr><td [attr.colspan]="modesActifs().length + (aAnnulations() ? 8 : 7)" class="vide">Aucune opération ce mois.</td></tr>
              }
            </tbody>
            <tfoot>
              <tr>
                <td colspan="2">Total du mois</td>
                <td class="tr">{{ p.totaux.nb_operations }}</td>
                @for (m of modesActifs(); track m.code) {
                  <td class="tr">{{ p.totaux.entrees.par_mode[m.code] | number:'1.0-0' }}</td>
                }
                <td class="tr">{{ p.totaux.entrees.total | number:'1.0-0' }}</td>
                <td class="tr">{{ p.totaux.sorties.total | number:'1.0-0' }}</td>
                @if (aAnnulations()) { <td class="tr">{{ p.totaux.annulations.total | number:'1.0-0' }}</td> }
                <td class="tr">{{ p.totaux.solde | number:'1.0-0' }}</td>
                <td class="tr">{{ p.solde_cloture.total | number:'1.0-0' }}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </section>
    }

    <section class="bloc">
      <h4 class="bloc-titre">Trésorerie mois par mois — exercice {{ p.exercice }}</h4>
      <div class="table-wrap">
        <table class="tbl">
          <thead>
            <tr>
              <th scope="col">Mois</th><th scope="col" class="tr">Opérations</th>
              <th scope="col" class="tr">Entrées</th><th scope="col" class="tr">Sorties</th>
              <th scope="col" class="tr">Annulations</th><th scope="col" class="tr">Solde du mois</th><th scope="col" class="tr">Trésorerie fin de mois</th>
            </tr>
          </thead>
          <tbody>
            @for (m of p.mois; track m.annee * 100 + m.mois) {
              <tr class="ligne-jour" tabindex="0" [class.courant]="periode() === 'mois' && moisCle() === m.annee + '-' + m.mois"
                  (click)="voirMois(m.annee + '-' + m.mois)" (keydown.enter)="voirMois(m.annee + '-' + m.mois)">
                <td class="gras">{{ m.libelle }}</td>
                <td class="tr">{{ m.nb_operations }}</td>
                <td class="tr txt-vert">{{ m.entrees.total | number:'1.0-0' }}</td>
                <td class="tr txt-orange">{{ m.sorties.total | number:'1.0-0' }}</td>
                <td class="tr">{{ m.annulations.total | number:'1.0-0' }}</td>
                <td class="tr" [class.txt-rouge]="m.solde < 0">{{ m.solde | number:'1.0-0' }}</td>
                <td class="tr gras">{{ m.solde_fin.total | number:'1.0-0' }}</td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    </section>

    <p class="note">
      Montants en FCFA, lus dans le journal sur les comptes de trésorerie — les mêmes que les soldes du tableau de bord.
      Une opération annulée le jour même est une erreur de saisie : elle et son annulation restent dans le détail mais sortent des totaux.
      Annulée un autre jour, elle apparaît ce jour-là dans la colonne « Annulations » (négative pour un encaissement annulé).
      « Non renseigné » : écritures passées avant la mise en place du suivi par responsable.
      Les transferts entre caisse, banque et mobile money changent la répartition par mode, pas le total.
    </p>
  }
</div>
`,
  styles: [`
    .pt { display:flex; flex-direction:column; gap:14px; }
    .pt-head { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; flex-wrap:wrap; }
    .pt-title { margin:0; font-size:17px; color:var(--text); }
    .pt-sub { font-size:12px; color:var(--text-3); margin-top:3px; }
    .pt-actions { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
    :host ::ng-deep .pt-select { min-width:170px; }
    .pt-date { background:var(--surface); border:1px solid var(--border); color:var(--text); border-radius:8px; padding:6px 10px; font-size:13px; font-family:inherit; }
    .bascule { display:inline-flex; border:1px solid var(--border); border-radius:8px; overflow:hidden; }
    .bascule button { background:var(--surface); color:var(--text-2); border:none; padding:7px 14px; font-size:13px; cursor:pointer; font-family:inherit; }
    .bascule button.active { background:rgba(0,212,170,.15); color:var(--text); font-weight:600; }
    .bascule button:focus-visible, .pt-date:focus-visible, .ligne-jour:focus-visible, .filtre:focus-visible { outline:2px solid #00d4aa; outline-offset:2px; }
    .pt-erreur { background:rgba(220,38,38,.1); border:1px solid #dc2626; color:#dc2626; padding:10px 14px; border-radius:8px; font-size:13px; }

    .kpis { display:grid; grid-template-columns:repeat(auto-fit, minmax(160px, 1fr)); gap:10px; }
    .kpi { background:var(--surface); border:1px solid var(--border); border-top:3px solid var(--acc); border-radius:10px; padding:12px 14px; }
    .kpi-l { font-size:11px; text-transform:uppercase; letter-spacing:.5px; color:var(--text-3); }
    .kpi-v { font-size:20px; font-weight:700; color:var(--text); margin:4px 0 2px; font-variant-numeric:tabular-nums; }
    .kpi-s { font-size:11px; color:var(--text-3); }

    .grille { display:grid; grid-template-columns:minmax(0, 1fr); gap:14px; max-width:860px; }
    .bloc { display:flex; flex-direction:column; gap:8px; min-width:0; }
    .bloc-entete { display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; }
    .bloc-titre { margin:0; font-size:14px; color:var(--text); }
    .aide { font-weight:400; font-size:12px; color:var(--text-3); }
    .filtre { background:var(--surface); border:1px solid var(--border); color:var(--text); border-radius:8px; padding:6px 10px; font-size:13px; font-family:inherit; }

    .table-wrap { overflow-x:auto; background:var(--surface); border:1px solid var(--border); border-radius:10px; }
    .tbl { width:100%; border-collapse:collapse; font-size:13px; }
    .tbl th { background:var(--surface-2); color:var(--text-3); font-size:11px; text-transform:uppercase; text-align:left; padding:8px 10px; white-space:nowrap; }
    .tbl th.tr { text-align:right; }
    .tbl td { padding:7px 10px; border-top:1px solid var(--border); color:var(--text-2); font-variant-numeric:tabular-nums; }
    .tbl tfoot td { font-weight:700; color:var(--text); background:var(--surface-2); }
    .ligne-jour { cursor:pointer; }
    .ligne-jour:hover td { background:var(--surface-hover); }
    .ligne-jour.courant td { background:rgba(0,212,170,.08); }
    .ligne-resp td { border-top:none; font-size:12px; color:var(--text-3); padding-top:2px; padding-bottom:4px; }
    .ligne-annulation td { color:var(--text-3); }
    .barree td.tr { text-decoration:line-through; }
    .nowrap { white-space:nowrap; }
    .tag { display:inline-block; font-size:10px; font-weight:600; padding:1px 6px; border-radius:8px; background:var(--surface-2); color:var(--text-2); margin-right:4px; }
    .tag-annul { background:rgba(220,38,38,.15); color:#dc2626; }
    .tr { text-align:right; }
    .gras { font-weight:600; color:var(--text); }
    .petit { font-size:11px; color:var(--text-3); font-weight:400; }
    .mono { font-family:ui-monospace, monospace; font-size:12px; }
    .vide { text-align:center; padding:24px; color:var(--text-3); }
    .txt-rouge { color:#dc2626; }
    .txt-vert { color:#059669; }
    .txt-orange { color:#d97706; }
    .note { margin:0; font-size:12px; color:var(--text-3); line-height:1.6; }
  `],
})
export class PointTresorerieComponent implements OnInit {
  private api = inject(ApiService);
  private destroyRef = inject(DestroyRef);

  readonly aujourdhui = iso(new Date());

  point      = signal<PointTresorerie | null>(null);
  loading    = signal(false);
  pdfEnCours = signal(false);
  erreur     = signal('');
  periode    = signal<Periode>('jour');
  jour       = signal(this.aujourdhui);
  /** « 2026-10 » ; vide tant que le serveur n'a pas dit quel mois afficher. */
  moisCle    = signal('');
  filtreResponsable = signal('');

  /** Les mois de l'exercice — renvoyés avec chaque point. */
  optionsMois = computed(() =>
    (this.point()?.mois ?? []).map(m => ({ libelle: m.libelle, cle: `${m.annee}-${m.mois}` })));

  /** Modes qui ont servi sur la période (les espèces toujours). */
  modesActifs = computed(() => {
    const p = this.point();
    if (!p) return [];
    return p.modes.filter(m => m.code === 'ESPECE' || [
      p.solde_ouverture.par_mode[m.code], p.solde_cloture.par_mode[m.code],
      p.totaux.entrees.par_mode[m.code], p.totaux.sorties.par_mode[m.code],
    ].some(v => v !== 0));
  });

  /** La colonne « Annulations » n'apparaît que si la période en compte une. */
  aAnnulations = computed(() => {
    const p = this.point();
    return !!p && (p.totaux.nb_annulations > 0 || p.mois.some(m => m.annulations.total !== 0));
  });

  readonly dateCourte = dateCourte;

  operationsFiltrees = computed(() => {
    const ops = this.point()?.operations ?? [];
    const r = this.filtreResponsable();
    return r ? ops.filter(o => o.responsable === r) : ops;
  });

  ngOnInit() {
    this.charger();
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') this.charger(true);
    }, RAFRAICHISSEMENT_MS);
    this.destroyRef.onDestroy(() => clearInterval(timer));
  }

  private params(): Record<string, string> {
    if (this.periode() === 'jour') return { debut: this.jour(), fin: this.jour() };
    const [annee, mois] = this.moisCle().split('-').map(Number);
    return annee && mois
      ? { debut: `${annee}-${String(mois).padStart(2, '0')}-01`, fin: finDuMois(annee, mois) }
      : {};
  }

  charger(silencieux = false) {
    if (!silencieux) this.loading.set(true);
    this.api.get<PointTresorerie>('/paiements/point-tresorerie/', this.params()).subscribe({
      next: p => {
        this.point.set(p);
        if (!this.moisCle()) {
          const [a, m] = p.debut.split('-').map(Number);
          this.moisCle.set(`${a}-${m}`);
        }
        this.erreur.set('');
        this.loading.set(false);
      },
      error: err => {
        this.loading.set(false);
        if (!silencieux) this.erreur.set(err?.error?.error || 'Impossible de charger le point de trésorerie.');
      },
    });
  }

  voirJour(date: string) {
    if (!date) return;
    this.periode.set('jour');
    this.jour.set(date);
    this.filtreResponsable.set('');
    this.charger();
  }

  voirMois(cle: string) {
    this.periode.set('mois');
    if (cle) this.moisCle.set(cle);
    else {
      const [a, m] = this.jour().split('-').map(Number);
      this.moisCle.set(`${a}-${m}`);
    }
    this.charger();
  }

  /** Requête du PDF pour <app-bouton-imprimer>. */
  readonly pdfPoint = () => {
    const p = this.point();
    return this.api.getBlob('/paiements/point-tresorerie/pdf/', { debut: p?.debut, fin: p?.fin });
  };

  telechargerPdf() {
    const p = this.point();
    if (!p) return;
    this.pdfEnCours.set(true);
    this.api.getBlob('/paiements/point-tresorerie/pdf/', { debut: p.debut, fin: p.fin }).subscribe({
      next: blob => {
        const url = URL.createObjectURL(blob);
        const lien = document.createElement('a');
        lien.href = url;
        lien.download = p.debut === p.fin
          ? `point_tresorerie_${p.debut}.pdf` : `point_tresorerie_${p.debut}_${p.fin}.pdf`;
        document.body.appendChild(lien);
        lien.click();
        document.body.removeChild(lien);
        URL.revokeObjectURL(url);
        this.pdfEnCours.set(false);
      },
      error: () => { this.pdfEnCours.set(false); this.erreur.set('Impossible de générer le PDF du point de trésorerie.'); },
    });
  }
}
