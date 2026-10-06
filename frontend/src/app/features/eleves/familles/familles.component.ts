import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { TagModule } from 'primeng/tag';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { TextareaModule } from 'primeng/textarea';
import { SelectModule } from 'primeng/select';
import { MultiSelectModule } from 'primeng/multiselect';
import { CheckboxModule } from 'primeng/checkbox';
import { InputNumberModule } from 'primeng/inputnumber';
import { ToastModule } from 'primeng/toast';
import { TooltipModule } from 'primeng/tooltip';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { ConfirmationService, MessageService } from 'primeng/api';
import { TranslateModule, TranslateService } from '@ngx-translate/core';

import { Famille, FratrieProbable, LigneReductionFratrie,
         ResponsableFamille, SituationFamille } from '../../../core/models/eleve.model';
import { ElevesService } from '../../../core/services/eleves.service';
import { FORMATS_RECU, ImpressionService } from '../../../core/services/impression.service';
import { EncaissementGroupeComponent, FinEncaissement }
  from '../encaissement-groupe/encaissement-groupe.component';

/**
 * Les familles (fratries) d'une école.
 *
 * Mr NDIAYE a cinq enfants inscrits à cinq niveaux différents. Ses
 * coordonnées étaient saisies cinq fois — et divergeaient —, l'école ne
 * savait pas ce que la famille lui devait au total, et les rappels partaient
 * cinq fois au même numéro.
 *
 * L'écran est organisé autour de la seule question qui vaut le regroupement :
 * **que doit cette famille, tous enfants confondus ?** D'où la colonne du
 * reste dû sur chaque ligne, avant même d'ouvrir la fiche.
 *
 * Regrouper ne change AUCUN montant : le dû reste calculé fiche par fiche.
 * C'est ce qui permet à une école de commencer à regrouper quand elle veut,
 * sans rien bousculer de sa comptabilité.
 */
type LigneReduction = LigneReductionFratrie & {
  forme_inscription: string; valeur_inscription: number;
  forme_mensualite: string;  valeur_mensualite: number;
};

@Component({
  selector: 'app-familles',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, FormsModule, TableModule, ButtonModule, TagModule,
            DialogModule, InputTextModule, TextareaModule, SelectModule,
            MultiSelectModule, CheckboxModule, InputNumberModule, ToastModule, TooltipModule,
            ConfirmDialogModule, EncaissementGroupeComponent,
            TranslateModule],
  providers: [MessageService, ConfirmationService],
  template: `
    <p-toast />
    <p-confirmDialog />

    <div class="barre-familles">
      <input pInputText type="search" [(ngModel)]="recherche"
             [placeholder]="'familles.recherche' | translate"
             (keyup.enter)="charger()" class="champ-recherche" />
      <p-button icon="pi pi-search" size="small" severity="secondary" [outlined]="true"
                (onClick)="charger()" [ariaLabel]="'familles.recherche' | translate" />
      <span class="espace"></span>
      <!-- Une école qui arrive avec deux mille fiches ne créera pas ses
           familles une par une : on lui propose les groupes déduits des
           numéros de parents, à elle de valider. -->
      <p-button icon="pi pi-sitemap" [label]="'familles.regrouper' | translate" size="small"
                severity="info" [outlined]="true"
                [pTooltip]="'familles.regrouper_aide' | translate"
                (onClick)="ouvrirRegroupement()" />
      <p-button icon="pi pi-plus" [label]="'familles.nouvelle' | translate" size="small"
                severity="success" (onClick)="ouvrirDialog()" />
    </div>

    @if (familles().length === 0 && !chargement()) {
      <!-- Une école qui n'a jamais regroupé arrive ici : on lui dit à quoi ça
           sert, plutôt que de lui montrer un tableau vide. -->
      <div class="vide">
        <p>{{ 'familles.vide_titre' | translate }}</p>
        <p class="aide">{{ 'familles.vide_aide' | translate }}</p>
      </div>
    } @else {
      <p-table [value]="familles()" [loading]="chargement()" [paginator]="familles().length > 20"
               [rows]="20" styleClass="p-datatable-sm">
        <ng-template pTemplate="header">
          <tr>
            <th>{{ 'familles.code' | translate }}</th>
            <th>{{ 'familles.nom' | translate }}</th>
            <th>{{ 'familles.contact' | translate }}</th>
            <th class="col-nb">{{ 'familles.nb_enfants' | translate }}</th>
            <th class="col-actions"></th>
          </tr>
        </ng-template>
        <ng-template pTemplate="body" let-f>
          <tr>
            <td><span class="code">{{ f.code }}</span></td>
            <td class="nom">{{ f.nom }}</td>
            <td>
              @if (f.contact) {
                <div>{{ f.contact.nom }} <span class="lien">{{ f.contact.lien }}</span></div>
                <div class="tel">{{ f.contact.telephone || ('familles.sans_numero' | translate) }}</div>
              } @else {
                <span class="tel">{{ 'familles.sans_responsable' | translate }}</span>
              }
            </td>
            <td class="col-nb"><p-tag [value]="f.nb_enfants" severity="info" /></td>
            <td class="col-actions">
              <p-button icon="pi pi-users" size="small" severity="secondary" [text]="true"
                        [pTooltip]="'familles.voir_situation' | translate"
                        (onClick)="ouvrirSituation(f)" />
              <p-button icon="pi pi-pencil" size="small" severity="secondary" [text]="true"
                        [pTooltip]="'common.modifier' | translate" (onClick)="ouvrirDialog(f)" />
              <p-button icon="pi pi-trash" size="small" severity="danger" [text]="true"
                        [pTooltip]="'common.supprimer' | translate" (onClick)="supprimer(f)" />
            </td>
          </tr>
        </ng-template>
      </p-table>
    }

    <!-- ══ CRÉATION / MODIFICATION ══ -->
    <p-dialog [(visible)]="dialogVisible" [modal]="true" [style]="{ width: '620px' }"
              [header]="(form.id ? 'familles.modifier' : 'familles.nouvelle') | translate">
      <div class="form-grid">
        <div class="champ">
          <label for="fam-nom">{{ 'familles.nom' | translate }} *</label>
          <input pInputText id="fam-nom" [(ngModel)]="form.nom" [fluid]="true"
                 [placeholder]="'familles.nom_exemple' | translate" />
        </div>
        <div class="champ">
          <label for="fam-adresse">{{ 'familles.adresse' | translate }}</label>
          <input pInputText id="fam-adresse" [(ngModel)]="form.adresse" [fluid]="true" />
        </div>
      </div>

      <h4 class="titre-section">{{ 'familles.responsables' | translate }}</h4>
      <p class="aide">{{ 'familles.responsables_aide' | translate }}</p>

      @for (r of responsables(); track $index) {
        <div class="ligne-responsable">
          <input pInputText [(ngModel)]="r.nom" [placeholder]="'familles.resp_nom' | translate" />
          <p-select [(ngModel)]="r.lien" [options]="liens" optionLabel="label" optionValue="value"
                    appendTo="body" />
          <input pInputText [(ngModel)]="r.telephone"
                 [placeholder]="'familles.resp_tel' | translate" />
          <!-- Un seul principal : un bouton radio, pas une case à cocher. En
               cocher deux rouvrirait la question « qui appeler ? » que ce
               regroupement est censé fermer. -->
          <label class="principal" [pTooltip]="'familles.principal_aide' | translate">
            <input type="radio" name="principal" [checked]="r.principal"
                   (change)="designerPrincipal($index)" />
            {{ 'familles.principal' | translate }}
          </label>
          <p-button icon="pi pi-times" size="small" severity="danger" [text]="true"
                    (onClick)="retirerResponsable($index)"
                    [ariaLabel]="'common.supprimer' | translate" />
        </div>
      }
      <p-button icon="pi pi-plus" [label]="'familles.ajouter_responsable' | translate"
                size="small" severity="secondary" [outlined]="true"
                (onClick)="ajouterResponsable()" />

      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler' | translate" severity="secondary" [text]="true"
                  (onClick)="dialogVisible = false" />
        <p-button [label]="'common.enregistrer' | translate" severity="success"
                  [loading]="enregistrement()" (onClick)="enregistrer()" />
      </ng-template>
    </p-dialog>

    <!-- ══ SITUATION DE LA FAMILLE ══ -->
    <p-dialog [(visible)]="situationVisible" [modal]="true" [style]="{ width: '860px' }"
              [header]="situation()?.nom || ''">
      @if (situation(); as s) {
        <div class="kpi-famille">
          <div class="kpi"><span class="val">{{ s.nb_enfants }}</span>
            <span class="lbl">{{ 'familles.nb_enfants' | translate }}</span></div>
          <div class="kpi"><span class="val">{{ s.total_attendu | number:'1.0-0' }}</span>
            <span class="lbl">{{ 'familles.total_attendu' | translate }}</span></div>
          <div class="kpi"><span class="val vert">{{ s.total_paye | number:'1.0-0' }}</span>
            <span class="lbl">{{ 'familles.total_paye' | translate }}</span></div>
          <div class="kpi"><span class="val rouge">{{ s.reste_a_payer | number:'1.0-0' }}</span>
            <span class="lbl">{{ 'familles.reste' | translate }}</span></div>
        </div>

        <div class="ligne-encaisser">
          <p-button icon="pi pi-wallet" [label]="'familles.encaisser' | translate"
                    size="small" severity="success"
                    [pTooltip]="'familles.encaisser_aide' | translate"
                    (onClick)="ouvrirEncaissement()" />
          <p-button icon="pi pi-file-pdf" [label]="'familles.situation_pdf' | translate"
                    size="small" severity="secondary" [outlined]="true"
                    [loading]="telechargementSituation()"
                    (onClick)="telechargerSituation()" />
          @if (dernierVersement()) {
            <span class="recu-groupe">
              <span class="meta">{{ 'familles.recu_groupe' | translate }}</span>
              <p-select [options]="formatsRecu" [(ngModel)]="formatRecu" optionLabel="label"
                        optionValue="value" appendTo="body" size="small"
                        [ariaLabel]="'familles.format_recu' | translate" />
              <p-button icon="pi pi-print" [label]="'familles.imprimer' | translate"
                        size="small" [loading]="impressionRecu()"
                        (onClick)="imprimerRecu()" />
              <p-button icon="pi pi-download" size="small" severity="secondary" [outlined]="true"
                        [pTooltip]="'familles.telecharger' | translate"
                        [ariaLabel]="'familles.telecharger' | translate"
                        (onClick)="telechargerRecu()" />
            </span>
          }
        </div>

        <p-table [value]="s.enfants" styleClass="p-datatable-sm">
          <ng-template pTemplate="header">
            <tr>
              <th>{{ 'familles.enfant' | translate }}</th>
              <th>{{ 'eleves.classe' | translate }}</th>
              <th class="droite">{{ 'familles.total_attendu' | translate }}</th>
              <th class="droite">{{ 'familles.total_paye' | translate }}</th>
              <th class="droite">{{ 'familles.reste' | translate }}</th>
              <th></th>
            </tr>
          </ng-template>
          <ng-template pTemplate="body" let-e>
            <tr>
              <td>{{ e.nom_complet }} <span class="mat">{{ e.matricule }}</span></td>
              <td>{{ e.classe }}</td>
              <td class="droite">{{ e.total_attendu | number:'1.0-0' }}</td>
              <td class="droite">{{ e.total_paye | number:'1.0-0' }}</td>
              <td class="droite" [class.rouge]="e.reste_a_payer > 0">
                {{ e.reste_a_payer | number:'1.0-0' }}</td>
              <td class="droite">
                <p-button icon="pi pi-user-minus" size="small" severity="danger" [text]="true"
                          [pTooltip]="'familles.detacher' | translate"
                          (onClick)="detacher(e.eleve_id)" />
              </td>
            </tr>
          </ng-template>
        </p-table>

        <!-- Réduction fratrie : l'école nomme l'enfant et sa remise, sans
             barème par rang. Une prise en charge d'un autre motif (orphelin,
             bourse…) reste intouchable ici : elle se modifie sur la fiche. -->
        <h4 class="titre-section">{{ 'familles.reduction' | translate }}</h4>
        @if (reductions().length) {
          <p-table [value]="reductions()" styleClass="p-datatable-sm">
            <ng-template pTemplate="header">
              <tr>
                <th>{{ 'familles.enfant' | translate }}</th>
                <th>{{ 'familles.sur_inscription' | translate }}</th>
                <th>{{ 'familles.sur_mensualite' | translate }}</th>
              </tr>
            </ng-template>
            <ng-template pTemplate="body" let-l>
              <tr>
                <td>{{ l.nom_complet }} <span class="mat">{{ l.classe }}</span>
                  @if (l.protege) {
                    <p-tag severity="warn" [value]="l.motif"
                           [pTooltip]="'familles.protege_aide' | translate" />
                  }
                </td>
                @if (l.protege) {
                  <td colspan="2" class="aide">{{ 'familles.reduction_protegee' | translate }}</td>
                } @else {
                  <td>
                    <div class="saisie-remise">
                      <p-inputNumber [(ngModel)]="l.valeur_inscription" [min]="0" [fluid]="true"
                                     styleClass="champ-valeur" />
                      <p-select [(ngModel)]="l.forme_inscription" [options]="formes" optionLabel="label"
                                optionValue="value" appendTo="body" />
                    </div>
                    <span class="aide">{{ 'familles.tarif' | translate }} {{ l.tarif_inscription | number:'1.0-0' }}</span>
                  </td>
                  <td>
                    <div class="saisie-remise">
                      <p-inputNumber [(ngModel)]="l.valeur_mensualite" [min]="0" [fluid]="true"
                                     styleClass="champ-valeur" />
                      <p-select [(ngModel)]="l.forme_mensualite" [options]="formes" optionLabel="label"
                                optionValue="value" appendTo="body" />
                    </div>
                    <span class="aide">{{ 'familles.tarif' | translate }} {{ l.tarif_mensualite | number:'1.0-0' }}</span>
                  </td>
                }
              </tr>
            </ng-template>
          </p-table>
          <p class="aide">{{ 'familles.reduction_aide' | translate }}</p>
          <p-button [label]="'familles.enregistrer_reduction' | translate" icon="pi pi-check" size="small"
                    severity="success" [loading]="enregistrementReduction()"
                    (onClick)="enregistrerReductions()" />
        }

        <h4 class="titre-section">{{ 'familles.rattacher' | translate }}</h4>
        <p class="aide">{{ 'familles.rattacher_aide' | translate }}</p>
        <div class="ligne-rattacher">
          <p-multiSelect [options]="elevesLibres()" [(ngModel)]="aRattacher"
                         optionLabel="nom_complet" optionValue="id" [filter]="true"
                         [placeholder]="'familles.choisir_eleves' | translate"
                         appendTo="body" styleClass="select-eleves" />
          <p-button icon="pi pi-user-plus" [label]="'familles.rattacher' | translate"
                    size="small" severity="success" [disabled]="aRattacher.length === 0"
                    [loading]="rattachement()" (onClick)="rattacher()" />
        </div>
      }
    </p-dialog>

    <!-- ══ ENCAISSER POUR LA FAMILLE ══
         La logique du guichet, pour toute la fratrie : chaque enfant montre
         ses échéances, échues ou à venir, et l'école coche ce que le parent
         règle — y compris d'avance. Chaque ligne reste un règlement normal,
         avec ses écritures. -->
    <p-dialog [(visible)]="encaissementVisible" [modal]="true"
              [style]="{ width: '960px', maxWidth: '96vw' }"
              [header]="'familles.encaisser' | translate">
      @if (encaissementVisible && situation(); as s) {
        <app-encaissement-groupe type="famille" [cibleId]="s.famille_id"
                                 [payeurs]="responsablesFamille()"
                                 (termine)="finEncaissement($event)" />
      }
    </p-dialog>


    <!-- ══ REGROUPEMENT ASSISTÉ ══
         Rien n'est créé tant que l'école n'a pas validé : fusionner deux
         familles homonymes sans lien est très difficile à défaire. -->
    <p-dialog [(visible)]="regroupementVisible" [modal]="true" [style]="{ width: '900px' }"
              [header]="'familles.regrouper' | translate">
      @if (chargementFratries()) {
        <p class="aide">{{ 'common.chargement' | translate }}</p>
      } @else if (fratries().length === 0) {
        <div class="vide">
          <p>{{ 'familles.aucune_fratrie' | translate }}</p>
          <p class="aide">{{ 'familles.aucune_fratrie_aide' | translate }}</p>
        </div>
      } @else {
        <p class="aide">{{ 'familles.regrouper_resume' | translate:
                           { nb: fratries().length, nbEleves: totalEleves() } }}</p>

        @for (g of fratries(); track g.cle) {
          <div class="groupe">
            <div class="groupe-tete">
              <p-checkbox [(ngModel)]="coches" [value]="g.cle" [inputId]="'g-' + g.cle" />
              <input pInputText [(ngModel)]="noms[g.cle]" class="nom-groupe" />
              @if (g.confiance === 'A_VERIFIER') {
                <p-tag severity="warn" [value]="'familles.a_verifier' | translate"
                       [pTooltip]="'familles.a_verifier_aide' | translate" />
              } @else {
                <p-tag severity="success" [value]="'familles.sure' | translate" />
              }
              <span class="contact-groupe">
                {{ g.contact.nom }} · {{ g.contact.telephone }}
              </span>
            </div>
            <div class="enfants">
              @for (e of g.eleves; track e.id) {
                <span class="puce">{{ e.nom_complet }}<span class="cl">{{ e.classe }}</span></span>
              }
            </div>
          </div>
        }
      }

      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler' | translate" severity="secondary" [text]="true"
                  (onClick)="regroupementVisible = false" />
        <p-button [label]="'familles.creer_cochees' | translate" severity="success"
                  [disabled]="coches.length === 0" [loading]="creation()"
                  (onClick)="creerFamilles()" />
      </ng-template>
    </p-dialog>
  `,
  styles: [`
    .barre-familles { display:flex; align-items:center; gap:8px; margin-bottom:12px; flex-wrap:wrap; }
    .barre-familles .espace { flex:1 1 auto; }
    .champ-recherche { min-width:260px; }
    .vide { text-align:center; padding:36px 16px; color:var(--text-color-secondary); }
    .vide .aide { font-size:.88rem; max-width:560px; margin:6px auto 0; }
    .code { font-weight:600; color:var(--primary-color); }
    .nom { font-weight:600; }
    .lien { font-size:.75rem; color:var(--text-color-secondary); }
    .tel { font-size:.82rem; color:var(--text-color-secondary); }
    .col-nb, .droite { text-align:right; }
    .col-actions { text-align:right; white-space:nowrap; }
    .mat { font-size:.75rem; color:var(--text-color-secondary); margin-left:6px; }
    /* Jamais de classe locale « grid » : les marges négatives de PrimeFlex
       rognent la première ligne des dialogs. */
    .form-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:8px; }
    .champ { display:flex; flex-direction:column; gap:4px; }
    .champ label { font-size:.8rem; color:var(--text-color-secondary); }
    .titre-section { margin:16px 0 4px; font-size:.95rem; }
    .aide { font-size:.8rem; color:var(--text-color-secondary); margin:0 0 8px; }
    .ligne-responsable { display:flex; align-items:center; gap:8px; margin-bottom:8px; flex-wrap:wrap; }
    .ligne-responsable input[type=text], .ligne-responsable input:not([type]) { min-width:150px; }
    .principal { display:flex; align-items:center; gap:4px; font-size:.82rem; white-space:nowrap; }
    .kpi-famille { display:flex; gap:12px; margin-bottom:14px; flex-wrap:wrap; }
    .kpi { flex:1 1 130px; background:var(--surface-100); border-radius:8px; padding:10px 12px; }
    .kpi .val { display:block; font-size:1.25rem; font-weight:700; }
    .kpi .lbl { font-size:.72rem; color:var(--text-color-secondary); text-transform:uppercase; }
    .vert { color:var(--green-600); } .rouge { color:var(--red-600); }
    .ligne-rattacher { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
    .ligne-rattacher .select-eleves { min-width:320px; }
    .groupe { border:1px solid var(--surface-300); border-radius:8px; padding:10px 12px;
              margin-bottom:10px; }
    .groupe-tete { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
    .nom-groupe { min-width:220px; font-weight:600; }
    .contact-groupe { font-size:.82rem; color:var(--text-color-secondary); }
    .enfants { margin-top:8px; display:flex; gap:6px; flex-wrap:wrap; }
    .puce { background:var(--surface-100); border-radius:12px; padding:2px 10px; font-size:.82rem; }
    .puce .cl { color:var(--text-color-secondary); margin-left:6px; font-size:.74rem; }
    .ligne-encaisser { display:flex; gap:8px; margin-bottom:10px; flex-wrap:wrap; }
    .recu-groupe { display:inline-flex; gap:6px; align-items:center; flex-wrap:wrap; }
    .recu-groupe .meta { font-size:12px; color:var(--text-3); }
    .ligne-versement { display:flex; gap:8px; align-items:center; margin-bottom:12px;
                       flex-wrap:wrap; }
    .ligne-versement .champ-montant { width:170px; position:relative; }
    .detail-imputation { display:flex; gap:4px; flex-wrap:wrap; }
    .cl { font-size:.74rem; color:var(--text-color-secondary); margin-left:6px; }
    .avertissement { margin-top:10px; font-size:.84rem; color:var(--orange-700);
                     background:var(--orange-50); border-radius:6px; padding:8px 10px; }
    .saisie-remise { display:flex; gap:4px; align-items:center; }
    /* [fluid] + largeur explicite : un p-inputNumber garde sinon sa largeur
       naturelle et recouvre ses voisins sur la ligne. */
    .saisie-remise .champ-valeur { width:96px; position:relative; }
    @media (max-width: 640px) {
      .form-grid { grid-template-columns:1fr; }
      .champ-recherche { min-width:0; flex:1 1 100%; }
    }
  `],
})
export class FamillesComponent implements OnInit {
  private eleves   = inject(ElevesService);
  private msg      = inject(MessageService);
  private confirm  = inject(ConfirmationService);
  private translate = inject(TranslateService);

  familles      = signal<Famille[]>([]);
  chargement    = signal(false);
  enregistrement = signal(false);
  rattachement  = signal(false);
  situation     = signal<SituationFamille | null>(null);
  responsables  = signal<ResponsableFamille[]>([]);
  /** Élèves sans famille : les seuls qu'on propose de rattacher. Montrer
   *  toute l'école inviterait à déplacer un enfant d'une famille à l'autre
   *  par mégarde. */
  elevesLibres  = signal<{ id: string; nom_complet: string }[]>([]);

  telechargementSituation = signal(false);
  dernierVersement  = signal<string | null>(null);
  private impression = inject(ImpressionService);
  readonly formatsRecu = FORMATS_RECU;
  formatRecu = 'A5';
  impressionRecu = signal(false);
  responsablesFamille = signal<ResponsableFamille[]>([]);
  encaissementVisible = false;
  /** Remise fratrie de chaque enfant, en cours de saisie. */
  reductions        = signal<LigneReduction[]>([]);
  enregistrementReduction = signal(false);
  formes = [
    { label: '%',    value: 'POURCENTAGE' },
    { label: 'FCFA', value: 'MONTANT' },
  ];

  fratries          = signal<FratrieProbable[]>([]);
  chargementFratries = signal(false);
  creation          = signal(false);

  recherche = '';
  aRattacher: string[] = [];
  /** Groupes cochés, et le nom que l'école leur donne : elle corrige souvent
   *  « Famille NDIAYE » en « Famille Ousmane NDIAYE » quand deux foyers du
   *  même patronyme se côtoient dans l'école. */
  coches: string[] = [];
  noms: Record<string, string> = {};
  regroupementVisible = false;
  dialogVisible = false;
  situationVisible = false;
  form: Partial<Famille> = { nom: '', adresse: '' };

  liens = [
    { label: 'Père',   value: 'PERE' },
    { label: 'Mère',   value: 'MERE' },
    { label: 'Tuteur', value: 'TUTEUR' },
    { label: 'Autre',  value: 'AUTRE' },
  ];

  ngOnInit() { this.charger(); }

  charger() {
    this.chargement.set(true);
    this.eleves.getFamilles(this.recherche || undefined).subscribe({
      next: f => { this.familles.set(f); this.chargement.set(false); },
      error: () => { this.chargement.set(false); this.erreur('familles.erreur_chargement'); },
    });
  }

  // ── Création / modification ───────────────────────────────────────────
  ouvrirDialog(famille?: Famille) {
    this.form = famille
      ? { id: famille.id, nom: famille.nom, adresse: famille.adresse,
          observations: famille.observations }
      : { nom: '', adresse: '' };
    // Copie : éditer les objets de la liste ferait bouger le tableau derrière
    // le dialog, y compris si l'école annule.
    this.responsables.set((famille?.responsables || []).map(r => ({ ...r })));
    if (this.responsables().length === 0) this.ajouterResponsable();
    this.dialogVisible = true;
  }

  ajouterResponsable() {
    const premier = this.responsables().length === 0;
    this.responsables.update(rs => [...rs, {
      nom: '', lien: 'PERE', telephone: '', principal: premier }]);
  }

  retirerResponsable(index: number) {
    this.responsables.update(rs => rs.filter((_, i) => i !== index));
    // Le principal retiré : on redésigne, sinon la famille n'a plus personne
    // à appeler et les rappels retombent sur les fiches individuelles.
    if (this.responsables().length && !this.responsables().some(r => r.principal)) {
      this.designerPrincipal(0);
    }
  }

  designerPrincipal(index: number) {
    this.responsables.update(rs => rs.map((r, i) => ({ ...r, principal: i === index })));
  }

  enregistrer() {
    const nom = (this.form.nom || '').trim();
    if (!nom) { this.erreur('familles.nom_obligatoire'); return; }
    const responsables = this.responsables().filter(r => (r.nom || '').trim());
    const corps: Partial<Famille> = { ...this.form, nom, responsables };

    this.enregistrement.set(true);
    const appel = this.form.id
      ? this.eleves.majFamille(this.form.id, corps)
      : this.eleves.creerFamille(corps);
    appel.subscribe({
      next: () => {
        this.enregistrement.set(false);
        this.dialogVisible = false;
        this.charger();
        this.msg.add({ severity: 'success',
                       summary: this.translate.instant('familles.enregistree') });
      },
      error: () => { this.enregistrement.set(false); this.erreur('familles.erreur_enregistrement'); },
    });
  }

  supprimer(famille: Famille) {
    this.confirm.confirm({
      // On annonce le nombre d'enfants détachés : cinq fiches qui « perdent
      // leur famille » sans prévenir ressemblent à une perte de données.
      message: this.translate.instant('familles.confirmer_suppression',
                                      { nom: famille.nom, nb: famille.nb_enfants }),
      accept: () => this.eleves.supprimerFamille(famille.id).subscribe({
        next: () => { this.charger();
                      this.msg.add({ severity: 'success',
                                     summary: this.translate.instant('familles.supprimee') }); },
        error: () => this.erreur('familles.erreur_suppression'),
      }),
    });
  }

  // ── Situation et rattachement ─────────────────────────────────────────
  ouvrirSituation(famille: Famille) {
    this.situationVisible = true;
    this.situation.set(null);
    this.aRattacher = [];
    this.reductions.set([]);
    this.dernierVersement.set(null);
    this.eleves.getSituationFamille(famille.id).subscribe({
      next: s => this.situation.set(s),
      error: () => { this.situationVisible = false; this.erreur('familles.erreur_situation'); },
    });
    this.chargerReductions(famille.id);
    this.chargerElevesLibres();
  }

  private chargerElevesLibres() {
    this.eleves.getEleves().subscribe({
      next: r => this.elevesLibres.set(
        (r.results || []).filter(e => !(e as any).famille)
          .map(e => ({ id: e.id, nom_complet: e.nom_complet }))),
      error: () => this.elevesLibres.set([]),
    });
  }

  rattacher() {
    const s = this.situation();
    if (!s || this.aRattacher.length === 0) return;
    this.rattachement.set(true);
    this.eleves.rattacherALaFamille(s.famille_id, this.aRattacher).subscribe({
      next: r => {
        this.rattachement.set(false);
        this.aRattacher = [];
        this.msg.add({ severity: 'success',
                       summary: this.translate.instant('familles.rattaches', { nb: r.nb }) });
        this.rafraichirSituation(s.famille_id);
      },
      error: () => { this.rattachement.set(false); this.erreur('familles.erreur_rattachement'); },
    });
  }

  detacher(eleveId: string) {
    const s = this.situation();
    if (!s) return;
    this.eleves.rattacherALaFamille(s.famille_id, [eleveId], true).subscribe({
      next: () => this.rafraichirSituation(s.famille_id),
      error: () => this.erreur('familles.erreur_rattachement'),
    });
  }

  private rafraichirSituation(familleId: string) {
    this.eleves.getSituationFamille(familleId).subscribe({
      next: s => this.situation.set(s),
    });
    this.chargerReductions(familleId);
    this.chargerElevesLibres();
    this.charger();
  }

  // ── Encaisser pour la famille ─────────────────────────────────────────
  ouvrirEncaissement() {
    const famille = this.familles().find(f => f.id === this.situation()?.famille_id);
    this.responsablesFamille.set(famille?.responsables || []);
    this.encaissementVisible = true;
  }

  finEncaissement(fin: FinEncaissement) {
    this.encaissementVisible = false;
    this.dernierVersement.set(fin.nbReglements ? fin.reference : null);
    if (fin.echecs.length) {
      // On ne masque pas un échec partiel : le reçu n'annoncera que ce qui
      // est réellement passé en caisse, et l'école doit le savoir.
      this.msg.add({ severity: 'warn', life: 9000,
                     summary: this.translate.instant('familles.encaissement_partiel',
                                                     { nb: fin.echecs.length }),
                     detail: fin.echecs.join(', ') });
    } else if (fin.nbReglements) {
      this.msg.add({ severity: 'success',
                     summary: this.translate.instant('familles.encaisse',
                                                     { nb: fin.nbReglements }) });
    }
    const s = this.situation();
    if (s) this.rafraichirSituation(s.famille_id);
    // La liste affiche le reste de chaque famille : elle doit suivre.
    this.charger();
  }

  telechargerSituation() {
    const s = this.situation();
    if (!s) return;
    this.telechargementSituation.set(true);
    this.eleves.situationFamillePdf(s.famille_id).subscribe({
      next: blob => {
        this.telechargementSituation.set(false);
        this.telechargerPdf(blob, `situation_${s.code}.pdf`);
      },
      error: () => { this.telechargementSituation.set(false); this.erreur('familles.erreur_situation_pdf'); },
    });
  }

  telechargerRecu() {
    const s = this.situation();
    const reference = this.dernierVersement();
    if (!s || !reference) return;
    this.eleves.recuGroupe(s.famille_id, reference, this.formatRecu).subscribe({
      next: blob => this.telechargerPdf(blob,
                                        `recu_${s.code}_${reference.slice(0, 8)}_${this.formatRecu}.pdf`),
      error: () => this.erreur('familles.erreur_recu'),
    });
  }

  /** Imprime le reçu du versement : directement (app installée) ou fenêtre du navigateur. */
  imprimerRecu() {
    const s = this.situation();
    const reference = this.dernierVersement();
    if (!s || !reference || this.impressionRecu()) return;
    this.impressionRecu.set(true);
    this.eleves.recuGroupe(s.famille_id, reference, this.formatRecu).subscribe({
      next: async blob => {
        try {
          const res = await this.impression.imprimer(blob, ImpressionService.typePourFormat(this.formatRecu));
          if (res.direct) {
            this.msg.add({ severity: 'success',
                           summary: this.translate.instant('familles.recu_envoye'),
                           detail: res.imprimante });
          }
        } catch (e: any) {
          this.msg.add({ severity: 'error', summary: this.translate.instant('familles.erreur_impression'),
                         detail: e?.message, life: 8000 });
        } finally {
          this.impressionRecu.set(false);
        }
      },
      error: () => { this.impressionRecu.set(false); this.erreur('familles.erreur_recu'); },
    });
  }

  private telechargerPdf(blob: Blob, nom: string) {
    const url = URL.createObjectURL(blob);
    const lien = document.createElement('a');
    lien.href = url;
    lien.download = nom;
    lien.click();
    URL.revokeObjectURL(url);
  }

  // ── Réduction fratrie (saisie directe) ───────────────────────────────
  /** La fiche ne garde que des montants : on les réaffiche en FCFA. */
  private chargerReductions(familleId: string) {
    this.eleves.getReductionsFamille(familleId).subscribe({
      next: r => this.reductions.set(r.lignes.map(l => ({
        ...l,
        forme_inscription: 'MONTANT', valeur_inscription: l.inscription,
        forme_mensualite:  'MONTANT', valeur_mensualite:  l.mensualite,
      }))),
      error: () => this.reductions.set([]),
    });
  }

  enregistrerReductions() {
    const s = this.situation();
    if (!s) return;
    const lignes = this.reductions().filter(l => !l.protege).map(l => ({
      eleve_id: l.eleve_id,
      forme_inscription: l.forme_inscription, valeur_inscription: Number(l.valeur_inscription) || 0,
      forme_mensualite:  l.forme_mensualite,  valeur_mensualite:  Number(l.valeur_mensualite) || 0,
    }));
    this.enregistrementReduction.set(true);
    this.eleves.enregistrerReductionsFamille(s.famille_id, lignes).subscribe({
      next: r => {
        this.enregistrementReduction.set(false);
        this.msg.add({ severity: 'success',
                       summary: this.translate.instant('familles.reduction_enregistree', { nb: r.nb_modifie }) });
        // Le dû des fiches a changé : la situation affichée doit suivre.
        this.rafraichirSituation(s.famille_id);
      },
      error: err => {
        this.enregistrementReduction.set(false);
        this.msg.add({ severity: 'error', summary: this.translate.instant('common.erreur'),
                       detail: err?.error?.error || this.translate.instant('familles.erreur_bareme') });
      },
    });
  }

  // ── Regroupement assisté ──────────────────────────────────────────────
  totalEleves() { return this.fratries().reduce((t, g) => t + g.nb, 0); }

  ouvrirRegroupement() {
    this.regroupementVisible = true;
    this.chargementFratries.set(true);
    this.fratries.set([]);
    this.coches = [];
    this.noms = {};
    this.eleves.getFratriesProbables().subscribe({
      next: r => {
        this.fratries.set(r.groupes);
        // Tout est coché d'avance SAUF ce qui demande vérification : l'école
        // ne doit pas créer sans regarder une famille dont les enfants ne
        // portent pas le même nom.
        this.coches = r.groupes.filter(g => g.confiance === 'SURE').map(g => g.cle);
        r.groupes.forEach(g => (this.noms[g.cle] = g.nom_propose));
        this.chargementFratries.set(false);
      },
      error: () => { this.chargementFratries.set(false); this.erreur('familles.erreur_fratries'); },
    });
  }

  creerFamilles() {
    const groupes = this.fratries()
      .filter(g => this.coches.includes(g.cle))
      .map(g => ({ nom: (this.noms[g.cle] || g.nom_propose).trim(),
                   contact: g.contact,
                   eleve_ids: g.eleves.map(e => e.id) }));
    if (groupes.length === 0) return;

    this.creation.set(true);
    this.eleves.regrouperFratries(groupes).subscribe({
      next: r => {
        this.creation.set(false);
        this.regroupementVisible = false;
        this.charger();
        this.msg.add({ severity: 'success', life: 7000,
                       summary: this.translate.instant('familles.regroupement_fait',
                                                       { nb: r.nb_familles }),
                       detail: this.translate.instant('familles.regroupement_detail',
                                                      { nb: r.nb_eleves }) });
      },
      error: () => { this.creation.set(false); this.erreur('familles.erreur_regroupement'); },
    });
  }

  private erreur(cle: string) {
    this.msg.add({ severity: 'error', summary: this.translate.instant('common.erreur'),
                   detail: this.translate.instant(cle) });
  }
}
