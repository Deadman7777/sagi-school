import {
  ChangeDetectionStrategy, Component, OnInit, inject, signal,
} from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { MessageService } from 'primeng/api';
import { ApiService } from '../../core/services/api.service';
import { ElevesService } from '../../core/services/eleves.service';

export interface LigneProforma {
  designation: string; detail: string; quantite: number;
  prix_unitaire: number; montant: number; nature: string;
}

export interface ResumeProforma {
  id: string; numero: string; statut: 'EMISE' | 'ANNULEE';
  date_emission: string; date_validite: string; expiree: boolean;
  annee_scolaire: string; nouvel_eleve: boolean;
  beneficiaire: string; matricule: string; section_nom: string; formule_nom: string;
  parent_nom: string; parent_telephone: string;
  total_du: number; deja_regle: number; remise_montant: number; net_a_payer: number;
  motif_annulation: string; emise_par: string;
}

export interface ApercuProforma {
  lignes: LigneProforma[];
  echeancier: { libelle: string; date: string | null; montant: number }[];
  total_du: number; deja_regle: number; part_organisme: number; organisme_nom: string;
  reste: number; remise_libelle: string; remise_montant: number; net_a_payer: number;
  annee_scolaire: string; observations_auto: string;
  beneficiaire: string; parent_nom: string; parent_telephone: string;
}

interface OptionsProforma {
  exercice: { annee_scolaire: string; date_debut: string; date_fin: string } | null;
  annee_suivante: { annee_scolaire: string; date_debut: string; date_fin: string } | null;
  sections: { id: string; nom: string; inscription: number; mensualite: number;
              a_la_journee: boolean; formules: { id: string; nom: string; mensualite: number }[] }[];
  services: { id: string; nom: string; montant: number; periodicite: string }[];
  renouvellement_actif: boolean; libelle_renouvellement: string;
  validite_jours: number; conditions: string;
}

type Mode = 'ELEVE' | 'NOUVEAU';

/**
 * Factures proforma de scolarité : pour le parent qui veut régler toute
 * l'année, ou qui se renseigne avant d'inscrire son enfant. Le chiffrage est
 * entièrement fait par le serveur (apps/paiements/proformas.py) ; l'écran
 * n'affiche que ce qu'il rend, pour que l'aperçu et le PDF disent la même chose.
 */
@Component({
  selector: 'app-proformas',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DecimalPipe, DatePipe, FormsModule, ButtonModule, DialogModule],
  template: `
<div class="pf">
  <div class="pf-head">
    <div>
      <h3 class="pf-title">📄 Factures proforma</h3>
      <div class="pf-sub">Pour une famille qui veut régler l'année, ou qui se renseigne avant l'inscription.
        Document non comptable : rien n'est encaissé ni écrit en comptabilité.</div>
    </div>
    <p-button label="+ Nouvelle proforma" severity="success" (onClick)="ouvrir()" />
  </div>

  <div class="table-wrap">
    <div class="pf-recherche">
      <input class="champ" [(ngModel)]="recherche" (ngModelChange)="onRecherche()"
             placeholder="🔍 N° de proforma, élève, parent, téléphone…" aria-label="Rechercher une proforma" />
    </div>
    <table class="tbl">
      <thead>
        <tr>
          <th>N°</th><th>Émise le</th><th>Élève</th><th>Classe</th><th>Parent</th>
          <th class="tr">Net à payer</th><th>Validité</th><th></th>
        </tr>
      </thead>
      <tbody>
        @for (p of liste(); track p.id) {
          <tr [class.annulee]="p.statut === 'ANNULEE'">
            <td class="gras">{{ p.numero }}</td>
            <td>{{ p.date_emission | date:'dd/MM/yyyy' }}</td>
            <td>
              <span class="gras">{{ p.beneficiaire }}</span>
              @if (p.nouvel_eleve) { <span class="tag tag-bleu">Futur élève</span> }
              <div class="petit">{{ p.annee_scolaire }}</div>
            </td>
            <td>{{ p.section_nom }}@if (p.formule_nom) { · {{ p.formule_nom }} }</td>
            <td>{{ p.parent_nom || '—' }}<div class="petit">{{ p.parent_telephone }}</div></td>
            <td class="tr gras">{{ p.net_a_payer | number:'1.0-0' }}</td>
            <td>
              @if (p.statut === 'ANNULEE') {
                <span class="tag tag-rouge" [title]="p.motif_annulation">Annulée</span>
              } @else if (p.expiree) {
                <span class="tag tag-gris">Expirée</span>
              } @else {
                <span class="petit">jusqu'au {{ p.date_validite | date:'dd/MM/yyyy' }}</span>
              }
            </td>
            <td class="actions">
              <p-button label="📄 PDF" [text]="true" size="small" [ariaLabel]="'Télécharger la proforma ' + p.numero"
                        [loading]="pdfEnCours() === p.id" (onClick)="telecharger(p)" />
              @if (p.statut === 'EMISE') {
                <p-button label="Annuler" [text]="true" size="small" severity="secondary"
                          [ariaLabel]="'Annuler la proforma ' + p.numero" (onClick)="demanderAnnulation(p)" />
              }
            </td>
          </tr>
        } @empty {
          <tr><td colspan="8" class="vide">
            @if (chargement()) { Chargement… } @else { Aucune proforma pour l'instant. }
          </td></tr>
        }
      </tbody>
    </table>
  </div>
</div>

<!-- ═══ Nouvelle proforma ═══ -->
<p-dialog header="📄 Nouvelle facture proforma" [(visible)]="dialogVisible" [modal]="true"
          [style]="{width:'1060px', maxWidth:'96vw'}" [draggable]="false" [dismissableMask]="false">
  <div class="dlg">
    <!-- Colonne gauche : la demande -->
    <div class="dlg-form">
      <div class="modes" role="group" aria-label="Pour qui ?">
        <button type="button" class="mode" [class.active]="mode() === 'ELEVE'" [attr.aria-pressed]="mode() === 'ELEVE'"
                (click)="choisirMode('ELEVE')">
          🎓 Élève inscrit</button>
        <button type="button" class="mode" [class.active]="mode() === 'NOUVEAU'" [attr.aria-pressed]="mode() === 'NOUVEAU'"
                (click)="choisirMode('NOUVEAU')">
          ✨ Futur élève / réinscription</button>
      </div>

      @if (mode() === 'ELEVE') {
        <label class="lbl" for="pf-eleve">Élève *</label>
        @if (eleve(); as e) {
          <div class="eleve-choisi">
            <div><strong>{{ e.nom_complet }}</strong>
              <div class="petit">{{ e.matricule }} · {{ e.section_nom }}</div></div>
            <button type="button" class="lien" (click)="changerEleve()">Changer</button>
          </div>
        } @else {
          <div class="autocomplete">
            <input id="pf-eleve" class="champ" [(ngModel)]="rechercheEleve" (ngModelChange)="chercherEleve($event)"
                   placeholder="Nom, matricule ou père (2 caractères min.)" autocomplete="off" />
            @if (suggestions().length) {
              <ul class="sugg">
                @for (s of suggestions(); track s.id) {
                  <li><button type="button" (click)="choisirEleve(s)">
                    <strong>{{ s.nom_complet }}</strong>
                    <span class="petit"> {{ s.matricule }} · {{ s.section_nom }}</span>
                  </button></li>
                }
              </ul>
            }
          </div>
        }
        <label class="case"><input type="checkbox" [(ngModel)]="inclureEntree" (ngModelChange)="rafraichir()" />
          Inclure l'inscription et les frais uniques restants</label>
        <label class="case"><input type="checkbox" [(ngModel)]="inclureAnterieur" (ngModelChange)="rafraichir()" />
          Inclure le reste dû des années antérieures</label>
      } @else {
        <label class="lbl" for="pf-benef">Nom de l'enfant *</label>
        <input id="pf-benef" class="champ" [(ngModel)]="beneficiaire" placeholder="Prénom NOM" />

        <div class="deux">
          <div>
            <label class="lbl" for="pf-section">Classe (section) *</label>
            <select id="pf-section" class="champ" [(ngModel)]="sectionId" (ngModelChange)="formuleId = ''; rafraichir()">
              <option value="">— Choisir —</option>
              @for (s of options()?.sections || []; track s.id) {
                <option [value]="s.id">{{ s.nom }}</option>
              }
            </select>
          </div>
          @if (formules().length) {
            <div>
              <label class="lbl" for="pf-formule">Formule</label>
              <select id="pf-formule" class="champ" [(ngModel)]="formuleId" (ngModelChange)="rafraichir()">
                <option value="">Mensualité de la section</option>
                @for (f of formules(); track f.id) {
                  <option [value]="f.id">{{ f.nom }} — {{ f.mensualite | number:'1.0-0' }} F</option>
                }
              </select>
            </div>
          }
        </div>

        <div class="deux">
          <div>
            <label class="lbl" for="pf-entree">Mois d'arrivée</label>
            <input id="pf-entree" type="month" class="champ" [(ngModel)]="moisEntree" (ngModelChange)="rafraichir()" />
            <div class="aide">Vide = dès la rentrée. Les mensualités sont comptées à partir de ce mois.</div>
          </div>
          <div class="cases">
            @if (options()?.annee_suivante; as s) {
              <label class="case"><input type="checkbox" [(ngModel)]="anneeSuivante" (ngModelChange)="moisEntree = ''; rafraichir()" />
                Pour l'année {{ s.annee_scolaire }}</label>
            }
            @if (options()?.renouvellement_actif) {
              <label class="case"><input type="checkbox" [(ngModel)]="renouvellement" (ngModelChange)="rafraichir()" />
                Ancien élève ({{ options()?.libelle_renouvellement }})</label>
            }
          </div>
        </div>

        @if (options()?.services?.length) {
          <label class="lbl">Services choisis</label>
          <div class="services">
            @for (s of options()?.services || []; track s.id) {
              <label class="case">
                <input type="checkbox" [checked]="serviceIds().has(s.id)" (change)="basculerService(s.id)" />
                {{ s.nom }} <span class="petit">{{ s.montant | number:'1.0-0' }} F{{ s.periodicite === 'MENSUEL' ? '/mois' : '' }}</span>
              </label>
            }
          </div>
        }
      }

      <div class="deux">
        <div>
          <label class="lbl" for="pf-parent">Parent / tuteur</label>
          <input id="pf-parent" class="champ" [(ngModel)]="parentNom" placeholder="Nom du parent" />
        </div>
        <div>
          <label class="lbl" for="pf-tel">Téléphone</label>
          <input id="pf-tel" class="champ" [(ngModel)]="parentTelephone" placeholder="77 000 00 00" />
        </div>
      </div>

      <details class="bloc" [open]="remiseType !== ''">
        <summary>Remise pour règlement en une fois</summary>
        <div class="trois">
          <select class="champ" [(ngModel)]="remiseType" (ngModelChange)="rafraichir()" aria-label="Type de remise">
            <option value="">Aucune remise</option>
            <option value="TAUX">En pourcentage</option>
            <option value="MONTANT">Montant fixe</option>
          </select>
          @if (remiseType) {
            <input type="number" min="0" class="champ" [(ngModel)]="remiseValeur" (ngModelChange)="rafraichir()"
                   [attr.aria-label]="remiseType === 'TAUX' ? 'Taux (%)' : 'Montant (F)'"
                   [placeholder]="remiseType === 'TAUX' ? '%' : 'F CFA'" />
            <input class="champ" [(ngModel)]="remiseLibelle" (ngModelChange)="rafraichir()"
                   placeholder="Libellé (facultatif)" aria-label="Libellé de la remise" />
          }
        </div>
        <div class="aide">La remise ne vaut que pour un règlement en une fois ; l'échéancier reste au tarif normal.</div>
      </details>

      <details class="bloc" [open]="lignesLibres.length > 0">
        <summary>Autres frais à ajouter ({{ lignesLibres.length }})</summary>
        @for (l of lignesLibres; track $index) {
          <div class="libre">
            <input class="champ" [(ngModel)]="l.designation" (ngModelChange)="rafraichir()" placeholder="Désignation" aria-label="Désignation" />
            <input type="number" min="1" class="champ" [(ngModel)]="l.quantite" (ngModelChange)="rafraichir()" aria-label="Quantité" />
            <input type="number" min="0" class="champ" [(ngModel)]="l.prix_unitaire" (ngModelChange)="rafraichir()" placeholder="Prix unitaire" aria-label="Prix unitaire" />
            <button type="button" class="lien rouge" (click)="retirerLigne($index)" aria-label="Retirer">✕</button>
          </div>
        }
        <button type="button" class="lien" (click)="ajouterLigne()">+ Ajouter une ligne (tenue, transport, livres…)</button>
      </details>

      <details class="bloc">
        <summary>Validité, observations et conditions</summary>
        <label class="lbl" for="pf-validite">Validité (jours)</label>
        <input id="pf-validite" type="number" min="1" max="365" class="champ court" [(ngModel)]="validiteJours" />
        <label class="lbl" for="pf-obs">Observations</label>
        <textarea id="pf-obs" class="champ" rows="2" [(ngModel)]="observations"></textarea>
        <label class="lbl" for="pf-cond">Conditions de règlement</label>
        <textarea id="pf-cond" class="champ" rows="3" [(ngModel)]="conditions"></textarea>
        <div class="aide">Où et comment payer. Reprises automatiquement sur la proforma suivante.</div>
      </details>
    </div>

    <!-- Colonne droite : l'aperçu, rendu par le serveur -->
    <div class="dlg-apercu" aria-live="polite">
      <div class="apercu-titre">Aperçu
        @if (apercu(); as a) { <span class="petit">— année {{ a.annee_scolaire }}</span> }
        @if (calcul()) { <span class="petit">· calcul…</span> }
      </div>
      @if (erreurApercu()) {
        <div class="info">{{ erreurApercu() }}</div>
      } @else if (apercu(); as a) {
        <table class="tbl mini">
          <thead><tr><th>Désignation</th><th class="tr">Qté</th><th class="tr">P.U.</th><th class="tr">Montant</th></tr></thead>
          <tbody>
            @for (l of a.lignes; track $index) {
              <tr [class.reduc]="l.montant < 0">
                <td><span class="gras">{{ l.designation }}</span>
                  @if (l.detail) { <div class="petit">{{ l.detail }}</div> }</td>
                <td class="tr">{{ l.quantite }}</td>
                <td class="tr">{{ l.prix_unitaire | number:'1.0-0' }}</td>
                <td class="tr">{{ l.montant | number:'1.0-0' }}</td>
              </tr>
            }
          </tbody>
        </table>
        <div class="totaux">
          <div><span>Total chiffré</span><strong>{{ a.total_du | number:'1.0-0' }}</strong></div>
          @if (a.deja_regle) { <div class="vert"><span>Déjà réglé</span><strong>− {{ a.deja_regle | number:'1.0-0' }}</strong></div> }
          @if (a.part_organisme) { <div class="vert"><span>Pris en charge ({{ a.organisme_nom }})</span><strong>− {{ a.part_organisme | number:'1.0-0' }}</strong></div> }
          @if (a.remise_montant) { <div class="vert"><span>{{ a.remise_libelle }}</span><strong>− {{ a.remise_montant | number:'1.0-0' }}</strong></div> }
          <div class="net"><span>Net à payer</span><strong>{{ a.net_a_payer | number:'1.0-0' }} F</strong></div>
        </div>
        @if (a.echeancier.length) {
          <div class="apercu-titre" style="margin-top:12px">Ou règlement échelonné{{ a.remise_montant ? ' (sans remise)' : '' }}</div>
          <table class="tbl mini">
            <tbody>
              @for (e of a.echeancier; track $index) {
                <tr><td>{{ e.libelle }}</td>
                  <td class="petit">{{ e.date ? (e.date | date:'dd/MM/yyyy') : '—' }}</td>
                  <td class="tr gras">{{ e.montant | number:'1.0-0' }}</td></tr>
              }
            </tbody>
          </table>
        }
        @if (a.observations_auto) { <div class="info">{{ a.observations_auto }}</div> }
      } @else {
        <div class="vide">
          {{ mode() === 'ELEVE' ? 'Choisissez un élève pour voir le chiffrage.' : 'Choisissez la classe pour voir le chiffrage.' }}
        </div>
      }
    </div>
  </div>

  <ng-template pTemplate="footer">
    <p-button label="Fermer" [text]="true" severity="secondary" (onClick)="dialogVisible = false" />
    <p-button label="Émettre et télécharger le PDF" icon="pi pi-file-pdf" severity="success"
              [loading]="emission()" [disabled]="!apercu() || !!erreurApercu() || calcul()" (onClick)="emettre()" />
  </ng-template>
</p-dialog>

<!-- ═══ Annulation ═══ -->
<p-dialog header="Annuler la proforma" [(visible)]="annulationVisible" [modal]="true"
          [style]="{width:'440px', maxWidth:'96vw'}" [draggable]="false">
  @if (aAnnuler(); as p) {
    <p class="annul-texte">La proforma <strong>{{ p.numero }}</strong> ({{ p.beneficiaire }}) restera consultable,
      marquée « annulée ». Rien d'autre ne change : une proforma n'écrit rien en comptabilité.</p>
    <label class="lbl" for="pf-motif">Motif *</label>
    <input id="pf-motif" class="champ" [(ngModel)]="motifAnnulation" placeholder="Ex. erreur de classe" />
  }
  <ng-template pTemplate="footer">
    <p-button label="Retour" [text]="true" severity="secondary" (onClick)="annulationVisible = false" />
    <p-button label="Annuler la proforma" severity="danger" [disabled]="!motifAnnulation.trim()"
              (onClick)="annuler()" />
  </ng-template>
</p-dialog>
  `,
  styles: [`
    .pf { display:flex; flex-direction:column; gap:14px; }
    .pf-head { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; flex-wrap:wrap; }
    .pf-title { margin:0; font-size:17px; color:var(--text); }
    .pf-sub { font-size:12px; color:var(--text-3); margin-top:3px; max-width:640px; }
    .pf-recherche { padding:12px; }
    .pf-recherche .champ { max-width:380px; }

    .table-wrap { overflow-x:auto; background:var(--surface); border:1px solid var(--border); border-radius:10px; }
    .tbl { width:100%; border-collapse:collapse; font-size:13px; }
    .tbl th { background:var(--surface-2); color:var(--text-3); font-size:11px; text-transform:uppercase; text-align:left; padding:8px 10px; white-space:nowrap; }
    .tbl td { padding:7px 10px; border-top:1px solid var(--border); color:var(--text-2); font-variant-numeric:tabular-nums; vertical-align:top; }
    .tbl.mini { font-size:12px; }
    .tbl.mini td, .tbl.mini th { padding:5px 8px; }
    tr.annulee td { opacity:.55; }
    tr.reduc td { color:#059669; }
    .tr { text-align:right; }
    .gras { font-weight:600; color:var(--text); }
    .petit { font-size:11px; color:var(--text-3); font-weight:400; }
    .vide { text-align:center; padding:24px; color:var(--text-3); font-size:13px; }
    .actions { white-space:nowrap; text-align:right; }
    .tag { display:inline-block; font-size:10.5px; padding:1px 7px; border-radius:10px; margin-left:6px; font-weight:600; }
    .tag-bleu  { background:rgba(3,105,161,.14); color:var(--text); border:1px solid #0369a1; }
    .tag-rouge { background:rgba(220,38,38,.14); color:var(--text); border:1px solid #dc2626; margin-left:0; }
    .tag-gris  { background:var(--surface-2); color:var(--text-3); margin-left:0; }

    .dlg { display:grid; grid-template-columns:minmax(0, 1fr) minmax(0, 1fr); gap:18px; }
    @media (max-width: 860px) { .dlg { grid-template-columns:1fr; } }
    .dlg-form { display:flex; flex-direction:column; gap:6px; }
    .dlg-apercu { background:var(--surface-2); border:1px solid var(--border); border-radius:10px; padding:12px; align-self:start; position:sticky; top:0; }
    .apercu-titre { font-size:12px; font-weight:700; text-transform:uppercase; letter-spacing:.4px; color:var(--text-2); margin-bottom:8px; }

    .modes { display:flex; gap:6px; margin-bottom:6px; flex-wrap:wrap; }
    .mode { flex:1 1 180px; border:1px solid var(--border); background:var(--surface); color:var(--text-2); border-radius:8px; padding:9px 12px; font-size:13px; cursor:pointer; }
    .mode.active { border-color:#00d4aa; color:var(--text); font-weight:600; background:rgba(0,212,170,.1); }
    .mode:focus-visible, .lien:focus-visible { outline:2px solid #00d4aa; outline-offset:2px; }

    .lbl { font-size:12px; font-weight:600; color:var(--text-2); margin-top:6px; }
    .champ { width:100%; box-sizing:border-box; background:var(--surface); border:1px solid var(--border); color:var(--text); border-radius:8px; padding:8px 10px; font-size:13px; font-family:inherit; }
    .champ:focus { outline:2px solid #00d4aa; outline-offset:0; }
    .champ.court { max-width:120px; }
    .aide { font-size:11px; color:var(--text-3); margin-top:2px; }
    .deux { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
    .trois { display:grid; grid-template-columns:1.2fr .8fr 1.4fr; gap:8px; margin-top:8px; }
    @media (max-width: 560px) { .deux, .trois { grid-template-columns:1fr; } }
    .cases { display:flex; flex-direction:column; justify-content:flex-end; gap:4px; padding-bottom:4px; }
    .case { display:flex; align-items:center; gap:7px; font-size:13px; color:var(--text-2); cursor:pointer; margin-top:4px; }
    .services { display:grid; grid-template-columns:1fr 1fr; gap:2px 12px; }

    .autocomplete { position:relative; }
    .sugg { position:absolute; z-index:10; left:0; right:0; top:100%; margin:2px 0 0; padding:4px; list-style:none; background:var(--surface); border:1px solid var(--border); border-radius:8px; max-height:260px; overflow:auto; box-shadow:0 8px 24px rgba(0,0,0,.18); }
    .sugg button { width:100%; text-align:left; background:none; border:0; padding:7px 8px; border-radius:6px; color:var(--text); cursor:pointer; font-size:13px; }
    .sugg button:hover, .sugg button:focus-visible { background:var(--surface-2); outline:none; }
    .eleve-choisi { display:flex; justify-content:space-between; align-items:center; gap:10px; border:1px solid #00d4aa; background:rgba(0,212,170,.07); border-radius:8px; padding:8px 10px; color:var(--text); }

    .bloc { border:1px solid var(--border); border-radius:8px; padding:8px 10px; margin-top:8px; }
    .bloc summary { cursor:pointer; font-size:13px; font-weight:600; color:var(--text-2); }
    .libre { display:grid; grid-template-columns:2fr 70px 1fr 28px; gap:6px; margin-top:6px; align-items:center; }
    .lien { background:none; border:0; color:#0099ff; cursor:pointer; font-size:12.5px; padding:4px 0; text-align:left; }
    .lien.rouge { color:#dc2626; font-size:14px; }

    .totaux { margin-top:8px; font-size:13px; }
    .totaux div { display:flex; justify-content:space-between; padding:3px 8px; color:var(--text-2); }
    .totaux .vert { color:#059669; }
    .totaux .net { margin-top:6px; background:#1e3a8a; color:#fff; border-radius:8px; padding:8px 10px; font-size:15px; }
    .info { background:rgba(3,105,161,.08); border:1px solid rgba(3,105,161,.35); color:var(--text-2); border-radius:8px; padding:8px 10px; font-size:12.5px; margin-top:8px; }
    .annul-texte { font-size:13px; color:var(--text-2); line-height:1.6; margin:0 0 8px; }
  `],
})
export class ProformasComponent implements OnInit {
  private api = inject(ApiService);
  private elevesService = inject(ElevesService);
  private msg = inject(MessageService);

  liste = signal<ResumeProforma[]>([]);
  chargement = signal(false);
  pdfEnCours = signal<string | null>(null);
  recherche = '';
  private minuterieRecherche?: ReturnType<typeof setTimeout>;

  options = signal<OptionsProforma | null>(null);
  dialogVisible = false;
  mode = signal<Mode>('ELEVE');

  // Élève inscrit
  eleve = signal<any | null>(null);
  rechercheEleve = '';
  suggestions = signal<any[]>([]);
  private minuterieEleve?: ReturnType<typeof setTimeout>;
  inclureEntree = true;
  inclureAnterieur = true;

  // Futur élève
  beneficiaire = '';
  sectionId = '';
  formuleId = '';
  moisEntree = '';
  anneeSuivante = false;
  renouvellement = false;
  serviceIds = signal<Set<string>>(new Set());

  // Communs
  parentNom = '';
  parentTelephone = '';
  remiseType: '' | 'TAUX' | 'MONTANT' = '';
  remiseValeur: number | null = null;
  remiseLibelle = '';
  lignesLibres: { designation: string; quantite: number; prix_unitaire: number | null }[] = [];
  validiteJours = 30;
  observations = '';
  conditions = '';

  apercu = signal<ApercuProforma | null>(null);
  erreurApercu = signal('');
  calcul = signal(false);
  emission = signal(false);
  private minuterieApercu?: ReturnType<typeof setTimeout>;
  private jetonApercu = 0;

  annulationVisible = false;
  aAnnuler = signal<ResumeProforma | null>(null);
  motifAnnulation = '';

  /** Formules de la section choisie. Une méthode, pas un computed : sectionId
   *  est un champ lié au formulaire, qu'un computed ne verrait pas changer. */
  formules() {
    return this.options()?.sections.find(s => s.id === this.sectionId)?.formules || [];
  }

  ngOnInit() {
    this.charger();
    this.api.get<OptionsProforma>('/paiements/proformas/options/').subscribe({
      next: o => this.options.set(o),
    });
  }

  charger() {
    this.chargement.set(true);
    this.api.get<ResumeProforma[]>('/paiements/proformas/', { q: this.recherche.trim() }).subscribe({
      next: l => { this.liste.set(l); this.chargement.set(false); },
      error: () => this.chargement.set(false),
    });
  }

  onRecherche() {
    clearTimeout(this.minuterieRecherche);
    this.minuterieRecherche = setTimeout(() => this.charger(), 300);
  }

  // ── Formulaire ────────────────────────────────────────────────────────
  ouvrir() {
    const o = this.options();
    this.mode.set('ELEVE');
    this.eleve.set(null); this.rechercheEleve = ''; this.suggestions.set([]);
    this.inclureEntree = true; this.inclureAnterieur = true;
    this.beneficiaire = ''; this.sectionId = ''; this.formuleId = ''; this.moisEntree = '';
    this.anneeSuivante = false; this.renouvellement = false; this.serviceIds.set(new Set());
    this.parentNom = ''; this.parentTelephone = '';
    this.remiseType = ''; this.remiseValeur = null; this.remiseLibelle = '';
    this.lignesLibres = [];
    this.validiteJours = o?.validite_jours || 30;
    this.observations = '';
    this.conditions = o?.conditions || '';
    this.apercu.set(null); this.erreurApercu.set('');
    this.dialogVisible = true;
  }

  choisirMode(m: Mode) {
    if (this.mode() === m) return;
    this.mode.set(m);
    this.parentNom = ''; this.parentTelephone = '';
    this.rafraichir();
  }

  chercherEleve(q: string) {
    clearTimeout(this.minuterieEleve);
    this.suggestions.set([]);
    if (!q || q.trim().length < 2) return;
    this.minuterieEleve = setTimeout(() => {
      this.elevesService.searchEleves(q.trim()).subscribe({
        next: r => this.suggestions.set(Array.isArray(r) ? r : []),
      });
    }, 300);
  }

  choisirEleve(e: any) {
    this.eleve.set(e);
    this.rechercheEleve = '';
    this.suggestions.set([]);
    // Le contact vient du serveur (contact_effectif) : on le laisse proposer.
    this.parentNom = ''; this.parentTelephone = '';
    this.rafraichir();
  }

  changerEleve() {
    this.eleve.set(null);
    this.apercu.set(null); this.erreurApercu.set('');
  }

  basculerService(id: string) {
    const s = new Set(this.serviceIds());
    s.has(id) ? s.delete(id) : s.add(id);
    this.serviceIds.set(s);
    this.rafraichir();
  }

  ajouterLigne() {
    this.lignesLibres = [...this.lignesLibres, { designation: '', quantite: 1, prix_unitaire: null }];
  }

  retirerLigne(i: number) {
    this.lignesLibres = this.lignesLibres.filter((_, j) => j !== i);
    this.rafraichir();
  }

  private demande(): any {
    const commun = {
      mode: this.mode(),
      parent_nom: this.parentNom.trim(),
      parent_telephone: this.parentTelephone.trim(),
      remise_type: this.remiseType,
      remise_valeur: this.remiseType ? (this.remiseValeur || 0) : 0,
      remise_libelle: this.remiseLibelle.trim(),
      lignes_libres: this.lignesLibres.filter(l => l.designation.trim() && (l.prix_unitaire || 0) > 0),
    };
    if (this.mode() === 'ELEVE') {
      return { ...commun, eleve_id: this.eleve()?.id,
               inclure_entree: this.inclureEntree, inclure_anterieur: this.inclureAnterieur };
    }
    return { ...commun, beneficiaire: this.beneficiaire.trim(), section_id: this.sectionId,
             formule_id: this.formuleId, date_entree: this.moisEntree,
             service_ids: [...this.serviceIds()], renouvellement: this.renouvellement,
             annee_suivante: this.anneeSuivante };
  }

  /** Recalcule l'aperçu (serveur), sans enregistrer. Seule la dernière
   *  réponse compte : une réponse lente ne doit pas écraser une plus récente. */
  rafraichir() {
    clearTimeout(this.minuterieApercu);
    const pret = this.mode() === 'ELEVE' ? !!this.eleve() : !!this.sectionId;
    if (!pret) { this.apercu.set(null); this.erreurApercu.set(''); return; }
    this.calcul.set(true);
    this.minuterieApercu = setTimeout(() => {
      const jeton = ++this.jetonApercu;
      this.api.post<ApercuProforma>('/paiements/proformas/apercu/', this.demande()).subscribe({
        next: a => {
          if (jeton !== this.jetonApercu) return;
          this.apercu.set(a); this.erreurApercu.set(''); this.calcul.set(false);
          if (this.mode() === 'ELEVE') {
            if (!this.parentNom) this.parentNom = a.parent_nom || '';
            if (!this.parentTelephone) this.parentTelephone = a.parent_telephone || '';
          }
        },
        error: err => {
          if (jeton !== this.jetonApercu) return;
          this.apercu.set(null); this.calcul.set(false);
          this.erreurApercu.set(err?.error?.error || 'Chiffrage impossible.');
        },
      });
    }, 250);
  }

  emettre() {
    if (this.mode() === 'NOUVEAU' && !this.beneficiaire.trim()) {
      this.msg.add({ severity: 'warn', summary: 'Nom manquant', detail: "Indiquez le nom de l'enfant." });
      return;
    }
    this.emission.set(true);
    this.api.post<ResumeProforma>('/paiements/proformas/', {
      ...this.demande(), validite_jours: this.validiteJours,
      observations: this.observations, conditions: this.conditions,
    }).subscribe({
      next: p => {
        this.emission.set(false);
        this.dialogVisible = false;
        this.msg.add({ severity: 'success', summary: `Proforma ${p.numero} émise`,
                       detail: `${p.beneficiaire} — ${Math.round(p.net_a_payer).toLocaleString('fr-FR')} F` });
        // Les conditions saisies deviennent la proposition suivante.
        const o = this.options();
        if (o) this.options.set({ ...o, conditions: this.conditions || o.conditions });
        this.charger();
        this.telecharger(p);
      },
      error: err => {
        this.emission.set(false);
        this.msg.add({ severity: 'error', summary: 'Proforma non émise',
                       detail: err?.error?.error || 'Erreur inattendue.' });
      },
    });
  }

  // ── PDF et annulation ─────────────────────────────────────────────────
  telecharger(p: ResumeProforma) {
    this.pdfEnCours.set(p.id);
    this.api.getBlob(`/paiements/proformas/${p.id}/pdf/`).subscribe({
      next: blob => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        // Même nom que celui du serveur : n° + élève, sans accents ni espaces.
        const nom = (p.beneficiaire || '').normalize('NFD').replace(/[̀-ͯ]/g, '')
                                         .replace(/[^A-Za-z0-9-]/g, '');
        a.href = url;
        a.download = `proforma_${p.numero}${nom ? '_' + nom : ''}.pdf`;
        document.body.appendChild(a); a.click(); document.body.removeChild(a);
        URL.revokeObjectURL(url);
        this.pdfEnCours.set(null);
      },
      error: () => {
        this.pdfEnCours.set(null);
        this.msg.add({ severity: 'error', summary: 'Erreur PDF', detail: 'Impossible de générer la proforma.' });
      },
    });
  }

  demanderAnnulation(p: ResumeProforma) {
    this.aAnnuler.set(p);
    this.motifAnnulation = '';
    this.annulationVisible = true;
  }

  annuler() {
    const p = this.aAnnuler();
    if (!p) return;
    this.api.post<ResumeProforma>(`/paiements/proformas/${p.id}/annuler/`,
                                  { motif: this.motifAnnulation.trim() }).subscribe({
      next: () => {
        this.annulationVisible = false;
        this.msg.add({ severity: 'info', summary: `Proforma ${p.numero} annulée` });
        this.charger();
      },
      error: err => this.msg.add({ severity: 'error', summary: 'Annulation impossible',
                                   detail: err?.error?.error || 'Erreur inattendue.' }),
    });
  }
}
