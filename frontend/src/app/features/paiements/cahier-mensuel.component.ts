import {
  ChangeDetectionStrategy, Component, DestroyRef, OnInit, computed, inject, signal,
} from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { SelectModule } from 'primeng/select';
import { ApiService } from '../../core/services/api.service';

/** Une ligne élève du cahier : ce qu'il devait pour le mois, payé, reste. */
export interface LigneEleveCahier {
  eleve_id: string; matricule: string; nom_complet: string; classe: string;
  telephone: string; du: number; paye: number; reste: number; sorti: boolean;
}

export interface LigneChargeCahier {
  id: string; no_compte: string; libelle: string; type_charge: string;
  prevu: number; realise: number; reste: number; ecart: number;
  etat: 'PAYEE' | 'PARTIELLE' | 'NON_PAYEE' | 'DEPASSEMENT' | 'HORS_PREVISION';
}

export interface CahierMensuel {
  exercice: string; exercice_id: string; annee: number; mois: number;
  libelle_mois: string; periode: 'PASSE' | 'EN_COURS' | 'A_VENIR';
  jours_restants: number; genere_le: string;
  mois_disponibles: { annee: number; mois: number; libelle: string }[];
  scolarite: {
    payes: LigneEleveCahier[]; partiels: LigneEleveCahier[]; impayes: LigneEleveCahier[];
    totaux: { nb_eleves: number; nb_payes: number; nb_partiels: number; nb_impayes: number;
              nb_exoneres: number; attendu: number; encaisse: number; reste: number; taux: number };
  };
  charges: {
    lignes: LigneChargeCahier[];
    totaux: { prevu: number; realise: number; reste: number; ecart: number;
              nb_payees: number; nb_non_payees: number; nb_depassements: number };
  };
  caisse: { entrees: number; charges: number };
  synthese: { attendu: number; encaisse: number; reste_a_encaisser: number;
              charges_prevues: number; charges_payees: number; charges_a_payer: number;
              solde_previsionnel: number; solde_constate: number };
}

type Vue = 'impayes' | 'partiels' | 'payes' | 'charges';

const RAFRAICHISSEMENT_MS = 60_000;

/**
 * « Mon cahier de notes mensuel » — qui a payé ce mois, qui ne l'a pas encore
 * fait, ce qui devait entrer et ce qui reste ; et côté dépenses, les charges
 * budgétées payées ou non. Mêmes chiffres que le PDF et que la carte
 * « Pilotage du mois » du tableau de bord : tous lisent le même endpoint.
 */
@Component({
  selector: 'app-cahier-mensuel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DecimalPipe, DatePipe, FormsModule, ButtonModule, SelectModule],
  template: `
<div class="cahier">
  <div class="cm-head">
    <div>
      <h3 class="cm-title">📒 Mon cahier de notes mensuel</h3>
      <div class="cm-sub">
        @if (cahier(); as c) {
          Exercice {{ c.exercice }} · mis à jour à {{ c.genere_le | date:'HH:mm:ss' }} · actualisation automatique
        } @else { Chargement… }
      </div>
    </div>
    <div class="cm-actions">
      <p-select [options]="optionsMois()" optionLabel="libelle" optionValue="cle"
                [ngModel]="cleSelection()" (ngModelChange)="choisirMois($event)"
                ariaLabel="Mois du cahier" styleClass="cm-select" appendTo="body" />
      <p-button icon="pi pi-refresh" [text]="true" severity="secondary" ariaLabel="Actualiser"
                [loading]="loading()" (onClick)="charger()" />
      <p-button label="Télécharger le PDF" icon="pi pi-file-pdf" severity="danger"
                [loading]="pdfEnCours()" [disabled]="!cahier()" (onClick)="telechargerPdf()" />
    </div>
  </div>

  @if (erreur()) {
    <div class="cm-erreur" role="alert">{{ erreur() }}</div>
  }

  @if (cahier(); as c) {
    <!-- Rappel visuel : ce qu'il reste à faire sur le mois, en une phrase. -->
    <div class="rappel" [class]="'rappel niveau-' + niveauRappel()" role="status">
      <div class="rappel-icone" aria-hidden="true">{{ niveauRappel() === 'ok' ? '✅' : '🔔' }}</div>
      <div class="rappel-texte">
        <strong>{{ c.libelle_mois }}</strong>
        @if (c.periode === 'EN_COURS') { — plus que {{ c.jours_restants }} jour(s) dans le mois. }
        @if (c.periode === 'PASSE') { — mois clôturé. }
        @if (c.periode === 'A_VENIR') { — mois à venir. }
        <br>
        @if (c.scolarite.totaux.nb_impayes + c.scolarite.totaux.nb_partiels > 0) {
          <strong>{{ c.scolarite.totaux.nb_impayes }}</strong> élève(s) n'ont pas encore payé et
          <strong>{{ c.scolarite.totaux.nb_partiels }}</strong> ont payé en partie :
          <strong>{{ c.synthese.reste_a_encaisser | number:'1.0-0' }} FCFA</strong> restent à encaisser.
        } @else {
          Toute la scolarité du mois est encaissée.
        }
        @if (c.charges.totaux.nb_non_payees > 0) {
          <strong>{{ c.charges.totaux.nb_non_payees }}</strong> charge(s) budgétée(s) à régler
          ({{ c.synthese.charges_a_payer | number:'1.0-0' }} FCFA).
        }
        @if (c.charges.totaux.nb_depassements > 0) {
          <strong class="txt-rouge">{{ c.charges.totaux.nb_depassements }} dépassement(s) de budget.</strong>
        }
      </div>
    </div>

    <div class="kpis">
      <div class="kpi" style="--acc:#0369a1">
        <div class="kpi-l">Devait entrer</div>
        <div class="kpi-v">{{ c.synthese.attendu | number:'1.0-0' }}</div>
        <div class="kpi-s">{{ c.scolarite.totaux.nb_eleves }} élèves concernés</div>
      </div>
      <div class="kpi" style="--acc:#059669">
        <div class="kpi-l">Est entré</div>
        <div class="kpi-v txt-vert">{{ c.synthese.encaisse | number:'1.0-0' }}</div>
        <div class="kpi-s">{{ c.scolarite.totaux.taux }} % recouvré</div>
      </div>
      <div class="kpi" style="--acc:#dc2626">
        <div class="kpi-l">Reste à encaisser</div>
        <div class="kpi-v txt-rouge">{{ c.synthese.reste_a_encaisser | number:'1.0-0' }}</div>
        <div class="kpi-s">FCFA</div>
      </div>
      <div class="kpi" style="--acc:#7c3aed">
        <div class="kpi-l">Entré en caisse ce mois</div>
        <div class="kpi-v">{{ c.caisse.entrees | number:'1.0-0' }}</div>
        <div class="kpi-s">toutes rubriques, tous mois</div>
      </div>
      <div class="kpi" style="--acc:#d97706">
        <div class="kpi-l">Charges budgétées</div>
        <div class="kpi-v">{{ c.synthese.charges_prevues | number:'1.0-0' }}</div>
        <div class="kpi-s">payé {{ c.synthese.charges_payees | number:'1.0-0' }} · reste {{ c.synthese.charges_a_payer | number:'1.0-0' }}</div>
      </div>
      <div class="kpi" [style.--acc]="c.synthese.solde_constate >= 0 ? '#059669' : '#dc2626'">
        <div class="kpi-l">Solde du mois</div>
        <div class="kpi-v" [class.txt-rouge]="c.synthese.solde_constate < 0">{{ c.synthese.solde_constate | number:'1.0-0' }}</div>
        <div class="kpi-s">prévisionnel {{ c.synthese.solde_previsionnel | number:'1.0-0' }}</div>
      </div>
    </div>

    <div class="barre" aria-hidden="true">
      <div class="barre-fill" [style.width.%]="c.scolarite.totaux.taux"></div>
    </div>

    <div class="vues" role="tablist">
      <button type="button" role="tab" class="vue" [class.active]="vue() === 'impayes'"
              [attr.aria-selected]="vue() === 'impayes'" (click)="vue.set('impayes')">
        🔴 Pas encore payé <span class="nb">{{ c.scolarite.totaux.nb_impayes }}</span>
      </button>
      <button type="button" role="tab" class="vue" [class.active]="vue() === 'partiels'"
              [attr.aria-selected]="vue() === 'partiels'" (click)="vue.set('partiels')">
        🟠 Partiel <span class="nb">{{ c.scolarite.totaux.nb_partiels }}</span>
      </button>
      <button type="button" role="tab" class="vue" [class.active]="vue() === 'payes'"
              [attr.aria-selected]="vue() === 'payes'" (click)="vue.set('payes')">
        🟢 Déjà payé <span class="nb">{{ c.scolarite.totaux.nb_payes }}</span>
      </button>
      <button type="button" role="tab" class="vue" [class.active]="vue() === 'charges'"
              [attr.aria-selected]="vue() === 'charges'" (click)="vue.set('charges')">
        💸 Charges budgétées <span class="nb">{{ c.charges.lignes.length }}</span>
      </button>
      @if (vue() !== 'charges') {
        <input class="recherche" type="search" placeholder="Rechercher un élève, une classe…"
               aria-label="Rechercher un élève" [ngModel]="recherche()"
               (ngModelChange)="recherche.set($event)" />
      }
    </div>

    @if (vue() !== 'charges') {
      <div class="table-wrap">
        <table class="tbl">
          <thead>
            <tr>
              <th scope="col">N°</th><th scope="col">Élève</th><th scope="col">Classe</th>
              <th scope="col">Téléphone</th><th scope="col" class="tr">Dû du mois</th>
              <th scope="col" class="tr">Payé</th><th scope="col" class="tr">Reste</th>
            </tr>
          </thead>
          <tbody>
            @for (e of lignesEleves(); track e.eleve_id; let i = $index) {
              <tr>
                <td>{{ i + 1 }}</td>
                <td class="gras">{{ e.nom_complet }}
                  @if (e.sorti) { <span class="badge-sorti">sorti</span> }
                  <div class="petit">{{ e.matricule }}</div>
                </td>
                <td>{{ e.classe }}</td>
                <td>@if (e.telephone) { <a [href]="'tel:' + e.telephone">{{ e.telephone }}</a> }</td>
                <td class="tr">{{ e.du | number:'1.0-0' }}</td>
                <td class="tr txt-vert">{{ e.paye | number:'1.0-0' }}</td>
                <td class="tr" [class.txt-rouge]="e.reste > 0">{{ e.reste | number:'1.0-0' }}</td>
              </tr>
            } @empty {
              <tr><td colspan="7" class="vide">Aucun élève dans cette liste.</td></tr>
            }
          </tbody>
          <tfoot>
            <tr>
              <td colspan="4">Total ({{ lignesEleves().length }})</td>
              <td class="tr">{{ totalListe().du | number:'1.0-0' }}</td>
              <td class="tr">{{ totalListe().paye | number:'1.0-0' }}</td>
              <td class="tr">{{ totalListe().reste | number:'1.0-0' }}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    } @else {
      <div class="table-wrap">
        <table class="tbl">
          <thead>
            <tr>
              <th scope="col">Compte</th><th scope="col">Poste</th>
              <th scope="col" class="tr">Budgété</th><th scope="col" class="tr">Payé</th>
              <th scope="col" class="tr">Écart</th><th scope="col">État</th>
            </tr>
          </thead>
          <tbody>
            @for (l of c.charges.lignes; track l.id) {
              <tr>
                <td>{{ l.no_compte }}</td>
                <td class="gras">{{ l.libelle }}</td>
                <td class="tr">{{ l.prevu | number:'1.0-0' }}</td>
                <td class="tr">{{ l.realise | number:'1.0-0' }}</td>
                <td class="tr" [class.txt-rouge]="l.ecart < 0">{{ l.ecart | number:'1.0-0' }}</td>
                <td><span class="etat" [class]="'etat etat-' + l.etat">{{ libelleEtat(l.etat) }}</span></td>
              </tr>
            } @empty {
              <tr><td colspan="6" class="vide">Aucune charge budgétée pour ce mois. Saisissez le budget dans Comptabilité → Budget.</td></tr>
            }
          </tbody>
          <tfoot>
            <tr>
              <td colspan="2">Total charges</td>
              <td class="tr">{{ c.charges.totaux.prevu | number:'1.0-0' }}</td>
              <td class="tr">{{ c.charges.totaux.realise | number:'1.0-0' }}</td>
              <td class="tr">{{ c.charges.totaux.ecart | number:'1.0-0' }}</td>
              <td></td>
            </tr>
          </tfoot>
        </table>
      </div>
    }
  }
</div>
`,
  styles: [`
    .cahier { display:flex; flex-direction:column; gap:14px; }
    .cm-head { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; flex-wrap:wrap; }
    .cm-title { margin:0; font-size:17px; color:var(--text); }
    .cm-sub { font-size:12px; color:var(--text-3); margin-top:3px; }
    .cm-actions { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
    :host ::ng-deep .cm-select { min-width:170px; }
    .cm-erreur { background:rgba(220,38,38,.1); border:1px solid #dc2626; color:#dc2626; padding:10px 14px; border-radius:8px; font-size:13px; }

    .rappel { display:flex; gap:12px; align-items:flex-start; padding:12px 16px; border-radius:10px; border:1px solid; font-size:13px; line-height:1.6; color:var(--text); }
    .rappel-icone { font-size:22px; line-height:1; }
    .niveau-critique  { background:rgba(220,38,38,.10); border-color:#dc2626; }
    .niveau-urgent    { background:rgba(234,88,12,.10); border-color:#ea580c; }
    .niveau-attention { background:rgba(234,179,8,.12); border-color:#ca8a04; }
    .niveau-ok        { background:rgba(5,150,105,.10); border-color:#059669; }

    .kpis { display:grid; grid-template-columns:repeat(auto-fit, minmax(160px, 1fr)); gap:10px; }
    .kpi { background:var(--surface); border:1px solid var(--border); border-top:3px solid var(--acc); border-radius:10px; padding:12px 14px; }
    .kpi-l { font-size:11px; text-transform:uppercase; letter-spacing:.5px; color:var(--text-3); }
    .kpi-v { font-size:20px; font-weight:700; color:var(--text); margin:4px 0 2px; font-variant-numeric:tabular-nums; }
    .kpi-s { font-size:11px; color:var(--text-3); }
    .barre { height:8px; background:var(--surface-2); border-radius:4px; overflow:hidden; }
    .barre-fill { height:100%; background:#059669; transition:width .4s; }

    .vues { display:flex; gap:6px; flex-wrap:wrap; align-items:center; }
    .vue { border:1px solid var(--border); background:var(--surface); color:var(--text-2); border-radius:8px; padding:7px 12px; font-size:13px; cursor:pointer; }
    .vue.active { border-color:#00d4aa; color:var(--text); font-weight:600; background:rgba(0,212,170,.1); }
    .vue:focus-visible, .recherche:focus-visible { outline:2px solid #00d4aa; outline-offset:2px; }
    .nb { display:inline-block; min-width:20px; padding:0 6px; margin-left:4px; border-radius:10px; background:var(--surface-2); font-size:11px; }
    .recherche { margin-left:auto; flex:1 1 220px; max-width:320px; background:var(--surface); border:1px solid var(--border); color:var(--text); border-radius:8px; padding:7px 10px; font-size:13px; }

    .table-wrap { overflow-x:auto; background:var(--surface); border:1px solid var(--border); border-radius:10px; }
    .tbl { width:100%; border-collapse:collapse; font-size:13px; }
    .tbl th { background:var(--surface-2); color:var(--text-3); font-size:11px; text-transform:uppercase; text-align:left; padding:8px 10px; white-space:nowrap; }
    .tbl td { padding:7px 10px; border-top:1px solid var(--border); color:var(--text-2); font-variant-numeric:tabular-nums; }
    .tbl tfoot td { font-weight:700; color:var(--text); background:var(--surface-2); }
    .tbl a { color:#0099ff; text-decoration:none; }
    .tr { text-align:right; }
    .gras { font-weight:600; color:var(--text); }
    .petit { font-size:11px; color:var(--text-3); font-weight:400; }
    .vide { text-align:center; padding:24px; color:var(--text-3); }
    .txt-rouge { color:#dc2626; }
    .txt-vert { color:#059669; }
    .badge-sorti { font-size:10px; background:var(--surface-2); color:var(--text-3); border-radius:4px; padding:1px 5px; margin-left:4px; font-weight:400; }
    .etat { font-size:11px; font-weight:600; padding:2px 8px; border-radius:10px; white-space:nowrap; }
    .etat-PAYEE { background:rgba(5,150,105,.15); color:#059669; }
    .etat-PARTIELLE { background:rgba(234,88,12,.15); color:#ea580c; }
    .etat-NON_PAYEE { background:rgba(220,38,38,.15); color:#dc2626; }
    .etat-DEPASSEMENT { background:rgba(220,38,38,.25); color:#dc2626; }
    .etat-HORS_PREVISION { background:var(--surface-2); color:var(--text-3); }
  `],
})
export class CahierMensuelComponent implements OnInit {
  private api = inject(ApiService);
  private destroyRef = inject(DestroyRef);

  cahier    = signal<CahierMensuel | null>(null);
  loading   = signal(false);
  pdfEnCours = signal(false);
  erreur    = signal('');
  vue       = signal<Vue>('impayes');
  recherche = signal('');
  /** Mois choisi ; vide = mois en cours (choisi par le serveur). */
  selection = signal<{ annee: number; mois: number } | null>(null);

  optionsMois = computed(() =>
    (this.cahier()?.mois_disponibles ?? []).map(m => ({ ...m, cle: `${m.annee}-${m.mois}` })));

  cleSelection = computed(() => {
    const c = this.cahier();
    return c ? `${c.annee}-${c.mois}` : '';
  });

  lignesEleves = computed<LigneEleveCahier[]>(() => {
    const c = this.cahier();
    const v = this.vue();
    if (!c || v === 'charges') return [];
    const q = this.normaliser(this.recherche());
    const liste = c.scolarite[v];
    return q ? liste.filter(e => this.normaliser(`${e.nom_complet} ${e.matricule} ${e.classe} ${e.telephone}`).includes(q))
             : liste;
  });

  totalListe = computed(() => this.lignesEleves().reduce(
    (t, e) => ({ du: t.du + e.du, paye: t.paye + e.paye, reste: t.reste + e.reste }),
    { du: 0, paye: 0, reste: 0 }));

  /** Rouge : mois passé avec impayés ; orange : fin de mois proche ; jaune : impayés en cours. */
  niveauRappel = computed<'critique' | 'urgent' | 'attention' | 'ok'>(() => {
    const c = this.cahier();
    if (!c) return 'ok';
    const restant = c.scolarite.totaux.nb_impayes + c.scolarite.totaux.nb_partiels
                    + c.charges.totaux.nb_non_payees;
    if (restant === 0 && c.charges.totaux.nb_depassements === 0) return 'ok';
    if (c.periode === 'PASSE' || c.charges.totaux.nb_depassements > 0) return 'critique';
    if (c.periode === 'EN_COURS' && c.jours_restants <= 7) return 'urgent';
    return 'attention';
  });

  ngOnInit() {
    this.charger();
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible') this.charger(true);
    }, RAFRAICHISSEMENT_MS);
    this.destroyRef.onDestroy(() => clearInterval(timer));
  }

  private params(): Record<string, string> {
    const s = this.selection();
    return s ? { annee: String(s.annee), mois: String(s.mois) } : {};
  }

  charger(silencieux = false) {
    if (!silencieux) this.loading.set(true);
    this.api.get<CahierMensuel>('/paiements/cahier-mensuel/', this.params()).subscribe({
      next: c => { this.cahier.set(c); this.erreur.set(''); this.loading.set(false); },
      error: err => {
        this.loading.set(false);
        if (!silencieux) this.erreur.set(err?.error?.error || 'Impossible de charger le cahier mensuel.');
      },
    });
  }

  choisirMois(cle: string) {
    const [annee, mois] = (cle || '').split('-').map(Number);
    if (!annee || !mois) return;
    this.selection.set({ annee, mois });
    this.charger();
  }

  telechargerPdf() {
    const c = this.cahier();
    if (!c) return;
    this.pdfEnCours.set(true);
    this.api.getBlob('/paiements/cahier-mensuel/pdf/', { annee: String(c.annee), mois: String(c.mois) }).subscribe({
      next: blob => {
        const url = URL.createObjectURL(blob);
        const lien = document.createElement('a');
        lien.href = url;
        lien.download = `cahier_mensuel_${c.annee}_${String(c.mois).padStart(2, '0')}.pdf`;
        document.body.appendChild(lien);
        lien.click();
        document.body.removeChild(lien);
        URL.revokeObjectURL(url);
        this.pdfEnCours.set(false);
      },
      error: () => { this.pdfEnCours.set(false); this.erreur.set('Impossible de générer le PDF du cahier.'); },
    });
  }

  libelleEtat(etat: LigneChargeCahier['etat']): string {
    return { PAYEE: 'Payée', PARTIELLE: 'Partielle', NON_PAYEE: 'Non payée',
             DEPASSEMENT: 'Dépassement', HORS_PREVISION: 'Hors prévision' }[etat];
  }

  private normaliser(v: string): string {
    return (v || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').trim();
  }
}
