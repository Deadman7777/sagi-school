import {
  ChangeDetectionStrategy, Component, OnInit, inject, signal, computed
} from '@angular/core';
import { DecimalPipe, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { ButtonModule }      from 'primeng/button';
import { DialogModule }      from 'primeng/dialog';
import { InputNumberModule } from 'primeng/inputnumber';
import { InputTextModule }   from 'primeng/inputtext';
import { Textarea }          from 'primeng/textarea';
import { SelectModule }      from 'primeng/select';
import { TableModule }       from 'primeng/table';
import { TagModule }         from 'primeng/tag';
import { ToastModule }       from 'primeng/toast';
import { TooltipModule }     from 'primeng/tooltip';
import { ProgressBarModule } from 'primeng/progressbar';
import { DatePickerModule }  from 'primeng/datepicker';
import { GouvernanceService } from '../../core/services/gouvernance.service';

interface Projet {
  id: string; code: string; libelle: string; description: string; responsable: string;
  date_debut: string | null; date_fin: string | null; budget_prevu: number;
  statut: string; statut_label: string; observations: string; est_actif: boolean;
  montant_consomme: number; montant_restant: number; taux_consommation: number;
}
interface Piece {
  id: string; type_piece: string; type_piece_label: string; nom: string;
  mime_type: string; taille: number; reference: string; date_document: string | null;
  observations: string; created_at: string;
}
interface Ressource {
  id: string; reference: string; type_ressource: string; type_label: string;
  libelle: string; organisme: string; montant: number; date_ressource: string | null;
  convention: string; statut: string; observations: string;
  montant_consomme: number; montant_affecte: number; montant_restant: number;
  disponible_a_affecter: number; taux_consommation: number;
}
interface Affectation {
  id: string; type_emploi: string; type_label: string; libelle: string; montant_affecte: number;
}
interface Canal { compte: string; libelle: string; solde: number; }
interface Transfert {
  id: string; reference: string; date_transfert: string;
  compte_source: string; compte_source_libelle: string;
  compte_destination: string; compte_destination_libelle: string;
  montant: number; frais: number; motif: string; statut: string; statut_label: string;
}

@Component({
  selector: 'app-gouvernance',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    DecimalPipe, DatePipe, FormsModule, TableModule, ButtonModule, DialogModule,
    InputTextModule, InputNumberModule, SelectModule, TagModule, ToastModule,
    TooltipModule, ProgressBarModule, DatePickerModule, Textarea,
  ],
  providers: [MessageService],
  template: `
<p-toast />
<input #fileInput type="file" hidden
       accept=".pdf,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx" (change)="onFichierChoisi($event)" />

<div class="gouv">
  <header class="head">
    <div>
      <h1>🎯 Gouvernance financière</h1>
      <p class="sub">Projets &amp; pièces justificatives, flux internes de trésorerie — synchronisés avec la comptabilité</p>
    </div>
  </header>

  <nav class="tabs">
    <button class="tab" [class.active]="tab() === 'pilotage'" (click)="allerPilotage()">📊 Pilotage</button>
    <button class="tab" [class.active]="tab() === 'projets'" (click)="allerProjets()">📁 Projets</button>
    <button class="tab" [class.active]="tab() === 'ressources'" (click)="allerRessources()">💶 Ressources</button>
    <button class="tab" [class.active]="tab() === 'provisions'" (click)="allerProvisions()">🛡️ Provisions</button>
    <button class="tab" [class.active]="tab() === 'rapprochement'" (click)="allerRapprochement()">🏦 Rapprochement</button>
    <button class="tab" [class.active]="tab() === 'transferts'" (click)="allerTransferts()">🔁 Flux internes</button>
    <button class="tab" [class.active]="tab() === 'tracabilite'" (click)="allerTracabilite()">🔎 Traçabilité</button>
  </nav>

  <!-- ══ PILOTAGE ══ -->
  @if (tab() === 'pilotage') {
    @if (dashboard(); as db) {
      @if (db.pilotage?.alertes?.length) {
        <div class="alertes">
          @for (a of db.pilotage.alertes; track a.message) {
            <div class="alerte" [class.danger]="a.niveau === 'danger'" [class.warn]="a.niveau === 'warn'">
              <span>{{ a.niveau === 'danger' ? '⛔' : (a.niveau === 'warn' ? '⚠️' : 'ℹ️') }}</span> {{ a.message }}
            </div>
          }
        </div>
      }

      <h4 class="trac-h">Pilotage</h4>
      <div class="kpis">
        <div class="kpi"><span class="lbl">Ressources mobilisées</span><span class="val">{{ db.ressources.total_obtenu | number:'1.0-0' }}</span></div>
        <div class="kpi"><span class="lbl">Consommé</span><span class="val">{{ db.ressources.total_consomme | number:'1.0-0' }}</span></div>
        <div class="kpi"><span class="lbl">Disponible</span><span class="val">{{ db.ressources.total_disponible | number:'1.0-0' }}</span></div>
        <div class="kpi"><span class="lbl">Taux de consommation</span><span class="val">{{ db.pilotage.taux_consommation }} %</span></div>
      </div>
      <div class="kpis">
        <div class="kpi"><span class="lbl">Produits</span><span class="val">{{ db.pilotage.indicateurs.produits | number:'1.0-0' }}</span></div>
        <div class="kpi"><span class="lbl">Charges</span><span class="val">{{ db.pilotage.indicateurs.charges | number:'1.0-0' }}</span></div>
        <div class="kpi"><span class="lbl">Résultat</span><span class="val" [style.color]="db.pilotage.indicateurs.resultat < 0 ? '#e24c4c' : '#10b981'">{{ db.pilotage.indicateurs.resultat | number:'1.0-0' }}</span></div>
        <div class="kpi"><span class="lbl">Provisions actives</span><span class="val">{{ db.pilotage.indicateurs.provisions_actives | number:'1.0-0' }}</span></div>
      </div>

      <div class="trac-grid">
        <div class="trac-col card">
          <h4>Origine des ressources</h4>
          @for (o of db.ressources.repartition_origine; track o.origine) {
            <div class="bar-row">
              <span class="bar-lbl">{{ o.origine }}</span>
              <span class="bar-track"><span class="bar-fill" [style.width.%]="pct(o.montant, db.ressources.total_obtenu)"></span></span>
              <span class="bar-val">{{ o.montant | number:'1.0-0' }}</span>
            </div>
          } @empty { <p class="vide">Aucune ressource.</p> }
        </div>
        <div class="trac-col card">
          <h4>Utilisation (emplois)</h4>
          @for (u of db.pilotage.utilisation; track u.nature) {
            <div class="bar-row">
              <span class="bar-lbl">{{ u.nature }}</span>
              <span class="bar-track"><span class="bar-fill alt" [style.width.%]="pct(u.montant, maxUsage(db))"></span></span>
              <span class="bar-val">{{ u.montant | number:'1.0-0' }}</span>
            </div>
          } @empty { <p class="vide">Aucune dépense.</p> }
        </div>
      </div>

      <h4 class="trac-h">Trésorerie</h4>
      <div class="kpis">
        <div class="kpi"><span class="lbl">Banques</span><span class="val">{{ db.tresorerie.banques | number:'1.0-0' }}</span></div>
        <div class="kpi"><span class="lbl">Caisses</span><span class="val">{{ db.tresorerie.caisses | number:'1.0-0' }}</span></div>
        <div class="kpi"><span class="lbl">Mobile Money</span><span class="val">{{ db.tresorerie.mobile | number:'1.0-0' }}</span></div>
        <div class="kpi"><span class="lbl">Total trésorerie</span><span class="val">{{ db.tresorerie.total | number:'1.0-0' }}</span></div>
      </div>
      <div class="kpis">
        <div class="kpi"><span class="lbl">Flux entrants</span><span class="val" style="color:#10b981">{{ db.tresorerie.flux_entrants | number:'1.0-0' }}</span></div>
        <div class="kpi"><span class="lbl">Flux sortants</span><span class="val" style="color:#e24c4c">{{ db.tresorerie.flux_sortants | number:'1.0-0' }}</span></div>
      </div>

      <h4 class="trac-h">Investissements</h4>
      <div class="kpis">
        <div class="kpi"><span class="lbl">Immobilisations</span><span class="val">{{ db.investissements.nombre }}</span></div>
        <div class="kpi"><span class="lbl">Valeur brute</span><span class="val">{{ db.investissements.valeur_brute | number:'1.0-0' }}</span></div>
        <div class="kpi"><span class="lbl">Amortissements</span><span class="val">{{ db.investissements.cumul_amortissements | number:'1.0-0' }}</span></div>
        <div class="kpi"><span class="lbl">Valeur nette</span><span class="val">{{ db.investissements.valeur_nette | number:'1.0-0' }}</span></div>
      </div>
    } @else { <p class="vide">Chargement du tableau de bord…</p> }
  }

  <!-- ══ PROJETS ══ -->
  @if (tab() === 'projets') {
    <div class="barre"><button pButton label="Nouveau projet" icon="pi pi-plus" (click)="ouvrirCreation()"></button></div>
    <div class="kpis">
      <div class="kpi"><span class="lbl">Projets</span><span class="val">{{ projets().length }}</span></div>
      <div class="kpi"><span class="lbl">Budget cumulé</span><span class="val">{{ totalBudget() | number:'1.0-0' }}</span></div>
      <div class="kpi"><span class="lbl">Consommé</span><span class="val">{{ totalConsomme() | number:'1.0-0' }}</span></div>
      <div class="kpi"><span class="lbl">Disponible</span><span class="val">{{ (totalBudget() - totalConsomme()) | number:'1.0-0' }}</span></div>
    </div>

    <p-table [value]="projets()" [loading]="chargement()" styleClass="p-datatable-sm" [paginator]="projets().length > 12" [rows]="12">
      <ng-template pTemplate="header">
        <tr>
          <th>Code</th><th>Libellé</th><th>Statut</th>
          <th class="r">Budget</th><th class="r">Consommé</th><th style="width:200px">Avancement</th><th></th>
        </tr>
      </ng-template>
      <ng-template pTemplate="body" let-p>
        <tr [class.inactif]="!p.est_actif">
          <td><strong>{{ p.code }}</strong></td>
          <td>{{ p.libelle }}@if (p.responsable) {<div class="resp">{{ p.responsable }}</div>}</td>
          <td><p-tag [value]="p.statut_label" [severity]="severite(p.statut)"></p-tag></td>
          <td class="r">{{ p.budget_prevu | number:'1.0-0' }}</td>
          <td class="r">{{ p.montant_consomme | number:'1.0-0' }}</td>
          <td>
            <p-progressBar [value]="borne(p.taux_consommation)" [showValue]="true" [style]="{height:'14px'}"
                           [color]="p.taux_consommation > 100 ? '#e24c4c' : undefined"></p-progressBar>
          </td>
          <td class="actions">
            <button pButton icon="pi pi-search" [text]="true" pTooltip="Traçabilité" (click)="ouvrirTracProjet(p)"></button>
            <button pButton icon="pi pi-paperclip" [text]="true" pTooltip="Pièces justificatives" (click)="ouvrirPieces(p)"></button>
            <button pButton icon="pi pi-pencil" [text]="true" pTooltip="Modifier" (click)="ouvrirEdition(p)"></button>
            <button pButton icon="pi pi-trash" [text]="true" severity="danger" pTooltip="Supprimer" (click)="supprimer(p)"></button>
          </td>
        </tr>
      </ng-template>
      <ng-template pTemplate="emptymessage">
        <tr><td colspan="7" class="vide">Aucun projet. Créez-en un pour commencer le suivi analytique.</td></tr>
      </ng-template>
    </p-table>
  }

  <!-- ══ RESSOURCES ══ -->
  @if (tab() === 'ressources') {
    <div class="barre">
      <button pButton label="Nouvelle ressource" icon="pi pi-plus" (click)="ouvrirRessource()"></button>
      <span class="hint">Prêts, subventions, dons, fonds propres… — suivi affecté / consommé / disponible, lié aux dépenses</span>
    </div>
    <div class="kpis">
      <div class="kpi"><span class="lbl">Ressources</span><span class="val">{{ ressources().length }}</span></div>
      <div class="kpi"><span class="lbl">Mobilisé</span><span class="val">{{ totalRessources() | number:'1.0-0' }}</span></div>
      <div class="kpi"><span class="lbl">Consommé</span><span class="val">{{ totalConsoRes() | number:'1.0-0' }}</span></div>
      <div class="kpi"><span class="lbl">Disponible</span><span class="val">{{ (totalRessources() - totalConsoRes()) | number:'1.0-0' }}</span></div>
    </div>

    <p-table [value]="ressources()" [loading]="chargementRes()" styleClass="p-datatable-sm" [paginator]="ressources().length > 12" [rows]="12">
      <ng-template pTemplate="header">
        <tr>
          <th>Réf.</th><th>Libellé</th><th>Type</th>
          <th class="r">Mobilisé</th><th class="r">Affecté</th><th class="r">Consommé</th>
          <th style="width:170px">Consommation</th><th></th>
        </tr>
      </ng-template>
      <ng-template pTemplate="body" let-r>
        <tr [class.inactif]="r.statut !== 'ACTIVE'">
          <td><strong>{{ r.reference }}</strong></td>
          <td>{{ r.libelle }}@if (r.organisme) {<div class="resp">{{ r.organisme }}</div>}</td>
          <td><p-tag [value]="r.type_label"></p-tag></td>
          <td class="r">{{ r.montant | number:'1.0-0' }}</td>
          <td class="r">{{ r.montant_affecte | number:'1.0-0' }}</td>
          <td class="r">{{ r.montant_consomme | number:'1.0-0' }}</td>
          <td>
            <p-progressBar [value]="borne(r.taux_consommation)" [showValue]="true" [style]="{height:'14px'}"
                           [color]="r.taux_consommation > 100 ? '#e24c4c' : undefined"></p-progressBar>
          </td>
          <td class="actions">
            <button pButton icon="pi pi-sitemap" [text]="true" pTooltip="Affectations" (click)="ouvrirAffectations(r)"></button>
            <button pButton icon="pi pi-search" [text]="true" pTooltip="Traçabilité" (click)="ouvrirTracabilite(r)"></button>
            <button pButton icon="pi pi-pencil" [text]="true" pTooltip="Modifier" (click)="ouvrirRessourceEdit(r)"></button>
            <button pButton icon="pi pi-trash" [text]="true" severity="danger" (click)="supprimerRessource(r)"></button>
          </td>
        </tr>
      </ng-template>
      <ng-template pTemplate="emptymessage">
        <tr><td colspan="8" class="vide">Aucune ressource. Enregistrez vos prêts, subventions, dons…</td></tr>
      </ng-template>
    </p-table>
  }

  <!-- ══ RAPPROCHEMENT BANCAIRE ══ -->
  @if (tab() === 'rapprochement') {
    <div class="barre">
      <button pButton label="Nouveau compte bancaire" icon="pi pi-building-columns" [outlined]="true" (click)="ouvrirCompteBancaire()"></button>
      <button pButton label="Nouveau rapprochement" icon="pi pi-plus" (click)="ouvrirRapprochement()" [disabled]="!comptesBancaires().length"></button>
    </div>
    <div class="canaux">
      @for (c of comptesBancaires(); track c.id) {
        <div class="canal">
          <span class="c-lbl">{{ c.libelle }}@if (c.banque) {<span> · {{ c.banque }}</span>}</span>
          <span class="c-solde" [class.neg]="c.solde_comptable < 0">{{ c.solde_comptable | number:'1.0-0' }}</span>
        </div>
      }
    </div>

    <p-table [value]="rapprochements()" [loading]="chargementRap()" styleClass="p-datatable-sm">
      <ng-template pTemplate="header">
        <tr><th>Réf.</th><th>Compte</th><th>Date</th><th class="r">Solde relevé</th><th class="r">Solde comptable</th><th class="r">Écart</th><th>Statut</th><th></th></tr>
      </ng-template>
      <ng-template pTemplate="body" let-r>
        <tr>
          <td><strong>{{ r.reference }}</strong></td>
          <td>{{ r.compte_bancaire_libelle }}</td>
          <td>{{ r.date_rapprochement | date:'dd/MM/yy' }}</td>
          <td class="r">{{ r.solde_releve | number:'1.0-0' }}</td>
          <td class="r">{{ r.solde_comptable | number:'1.0-0' }}</td>
          <td class="r" [style.color]="r.ecart === 0 ? '#10b981' : '#e24c4c'">{{ r.ecart | number:'1.0-0' }}</td>
          <td><p-tag [value]="r.statut === 'VALIDE' ? 'Validé' : 'En cours'" [severity]="r.statut === 'VALIDE' ? 'success' : 'warn'"></p-tag></td>
          <td class="actions">
            <button pButton icon="pi pi-eye" [text]="true" pTooltip="Ouvrir" (click)="ouvrirDetailRap(r)"></button>
            @if (r.statut !== 'VALIDE') {
              <button pButton icon="pi pi-trash" [text]="true" severity="danger" (click)="supprimerRapprochement(r)"></button>
            }
          </td>
        </tr>
      </ng-template>
      <ng-template pTemplate="emptymessage"><tr><td colspan="8" class="vide">Aucun rapprochement. Créez un compte bancaire puis un rapprochement.</td></tr></ng-template>
    </p-table>
  }

  <!-- ══ PROVISIONS ══ -->
  @if (tab() === 'provisions') {
    <div class="barre">
      <button pButton label="Nouvelle provision" icon="pi pi-plus" (click)="ouvrirProvision()"></button>
      <span class="hint">Risques, litiges, charges, créances douteuses, provisions réglementées — écritures &amp; états auto (SYSCOHADA)</span>
    </div>
    <p-table [value]="provisions()" [loading]="chargementProv()" styleClass="p-datatable-sm" [paginator]="provisions().length > 12" [rows]="12">
      <ng-template pTemplate="header">
        <tr><th>Réf.</th><th>Libellé</th><th>Type</th><th class="r">Dotée</th><th class="r">Reprise</th><th class="r">Actuelle</th><th>Statut</th><th></th></tr>
      </ng-template>
      <ng-template pTemplate="body" let-p>
        <tr [class.inactif]="p.statut === 'ANNULEE'">
          <td><strong>{{ p.reference }}</strong></td>
          <td>{{ p.libelle }}@if (p.tiers) {<div class="resp">{{ p.tiers }}</div>}</td>
          <td><p-tag [value]="p.type_label"></p-tag></td>
          <td class="r">{{ p.montant | number:'1.0-0' }}</td>
          <td class="r">{{ p.montant_repris ? (p.montant_repris | number:'1.0-0') : '—' }}</td>
          <td class="r"><strong>{{ p.montant_actuel | number:'1.0-0' }}</strong></td>
          <td><p-tag [value]="p.statut_label" [severity]="p.statut === 'ACTIVE' ? 'success' : (p.statut === 'SOLDEE' ? 'secondary' : 'danger')"></p-tag></td>
          <td class="actions">
            @if (p.statut === 'ACTIVE') {
              <button pButton icon="pi pi-undo" [text]="true" pTooltip="Reprise" (click)="ouvrirReprise(p)"></button>
              <button pButton icon="pi pi-times" [text]="true" severity="danger" pTooltip="Annuler (extourne)" (click)="annulerProvision(p)"></button>
            }
          </td>
        </tr>
      </ng-template>
      <ng-template pTemplate="emptymessage"><tr><td colspan="8" class="vide">Aucune provision. Constituez vos provisions pour risques, litiges, créances douteuses…</td></tr></ng-template>
    </p-table>
  }

  <!-- ══ TRAÇABILITÉ GLOBALE ══ -->
  @if (tab() === 'tracabilite') {
    @if (tracGlobale(); as tg) {
      <div class="trac-grid">
        <div class="trac-col card">
          <h4>D'où vient l'argent</h4>
          @for (o of tg.origines; track o.origine) {
            <div class="trac-line">
              <span>{{ o.origine }}<em class="tt"> · {{ o.type }}</em></span>
              <span>{{ o.mobilise | number:'1.0-0' }}</span>
            </div>
          } @empty { <p class="vide">Aucune ressource enregistrée.</p> }
        </div>
        <div class="trac-col card">
          <h4>À quoi il sert</h4>
          @for (u of tg.usages; track u.nature) {
            <div class="trac-line"><span>{{ u.nature }}</span><span>{{ u.montant | number:'1.0-0' }}</span></div>
          } @empty { <p class="vide">Aucune dépense sur l'exercice.</p> }
        </div>
      </div>
      <h4 class="trac-h">Impact</h4>
      <div class="kpis">
        <div class="kpi"><span class="lbl">Immobilisations</span><span class="val">{{ tg.impact.nb_immobilisations }}</span></div>
        <div class="kpi"><span class="lbl">Valeur nette immo.</span><span class="val">{{ tg.impact.valeur_nette_immobilisations | number:'1.0-0' }}</span></div>
        <div class="kpi"><span class="lbl">Projets actifs</span><span class="val">{{ tg.impact.nb_projets }}</span></div>
        <div class="kpi"><span class="lbl">Charges exercice</span><span class="val">{{ tg.impact.charges_exercice | number:'1.0-0' }}</span></div>
      </div>
    } @else { <p class="vide">Chargement…</p> }
  }

  <!-- ══ FLUX INTERNES ══ -->
  @if (tab() === 'transferts') {
    <div class="barre">
      <button pButton label="Nouveau transfert" icon="pi pi-plus" (click)="ouvrirTransfert()"></button>
      <span class="hint">Banque ⇄ Caisse ⇄ Mobile Money — écritures automatiques via le compte 585 (virements internes)</span>
    </div>

    <div class="canaux">
      @for (c of canaux(); track c.compte) {
        <div class="canal">
          <span class="c-lbl">{{ c.libelle }}</span>
          <span class="c-solde" [class.neg]="c.solde < 0">{{ c.solde | number:'1.0-0' }}</span>
        </div>
      }
    </div>

    <p-table [value]="transferts()" [loading]="chargementTr()" styleClass="p-datatable-sm" [paginator]="transferts().length > 15" [rows]="15">
      <ng-template pTemplate="header">
        <tr><th>Réf.</th><th>Date</th><th>De</th><th>Vers</th><th class="r">Montant</th><th class="r">Frais</th><th>Motif</th><th></th></tr>
      </ng-template>
      <ng-template pTemplate="body" let-t>
        <tr [class.inactif]="t.statut === 'ANNULE'">
          <td><strong>{{ t.reference }}</strong></td>
          <td>{{ t.date_transfert | date:'dd/MM/yy' }}</td>
          <td>{{ t.compte_source_libelle }}</td>
          <td>{{ t.compte_destination_libelle }}</td>
          <td class="r">{{ t.montant | number:'1.0-0' }}</td>
          <td class="r">{{ t.frais ? (t.frais | number:'1.0-0') : '—' }}</td>
          <td>{{ t.motif }}@if (t.statut === 'ANNULE') {<p-tag value="Annulé" severity="danger" styleClass="ml"></p-tag>}</td>
          <td class="actions">
            @if (t.statut !== 'ANNULE') {
              <button pButton icon="pi pi-times" [text]="true" severity="danger" pTooltip="Annuler (extourne)" (click)="annulerTransfert(t)"></button>
            }
          </td>
        </tr>
      </ng-template>
      <ng-template pTemplate="emptymessage">
        <tr><td colspan="8" class="vide">Aucun transfert interne enregistré.</td></tr>
      </ng-template>
    </p-table>
  }
</div>

<!-- Dialog création / édition projet -->
<p-dialog [(visible)]="dlgProjet" [modal]="true" [style]="{width:'560px'}" [header]="edition() ? 'Modifier le projet' : 'Nouveau projet'">
  <div class="form-grid">
    <label>Libellé *</label>
    <input pInputText [(ngModel)]="form.libelle" placeholder="Ex. Équipement salle informatique" />
    <label>Responsable</label>
    <input pInputText [(ngModel)]="form.responsable" />
    <label>Budget prévisionnel (FCFA)</label>
    <p-inputNumber [(ngModel)]="form.budget_prevu" [min]="0" [useGrouping]="true" mode="decimal"></p-inputNumber>
    <label>Statut</label>
    <p-select [(ngModel)]="form.statut" [options]="statuts" optionLabel="label" optionValue="value" appendTo="body"></p-select>
    <label>Période</label>
    <div class="row2">
      <p-datepicker [(ngModel)]="form.date_debut" dateFormat="dd/mm/yy" [showIcon]="true" appendTo="body" placeholder="Début"></p-datepicker>
      <p-datepicker [(ngModel)]="form.date_fin" dateFormat="dd/mm/yy" [showIcon]="true" appendTo="body" placeholder="Fin"></p-datepicker>
    </div>
    <label>Description</label>
    <textarea pTextarea [(ngModel)]="form.description" rows="2"></textarea>
    <label>Observations</label>
    <textarea pTextarea [(ngModel)]="form.observations" rows="2"></textarea>
  </div>
  <ng-template pTemplate="footer">
    <button pButton label="Annuler" [text]="true" (click)="dlgProjet.set(false)"></button>
    <button pButton label="Enregistrer" icon="pi pi-check" (click)="enregistrer()" [disabled]="!form.libelle"></button>
  </ng-template>
</p-dialog>

<!-- Dialog pièces justificatives (GED) -->
<p-dialog [(visible)]="dlgPieces" [modal]="true" [style]="{width:'640px'}" [header]="'Pièces — ' + (projetCourant()?.code || '')">
  <div class="ged-head">
    <p-select [(ngModel)]="typePieceUpload" [options]="typesPiece" optionLabel="label" optionValue="value" appendTo="body" [style]="{width:'220px'}"></p-select>
    <button pButton label="Ajouter un fichier" icon="pi pi-upload" (click)="fileInput.click()"></button>
  </div>
  <p-table [value]="pieces()" styleClass="p-datatable-sm" [loading]="chargementPieces()">
    <ng-template pTemplate="header">
      <tr><th>Type</th><th>Nom</th><th class="r">Taille</th><th>Ajoutée le</th><th></th></tr>
    </ng-template>
    <ng-template pTemplate="body" let-pc>
      <tr>
        <td><p-tag [value]="pc.type_piece_label"></p-tag></td>
        <td>{{ pc.nom }}</td>
        <td class="r">{{ (pc.taille / 1024) | number:'1.0-0' }} Ko</td>
        <td>{{ pc.created_at | date:'dd/MM/yy' }}</td>
        <td class="actions">
          <button pButton icon="pi pi-download" [text]="true" pTooltip="Télécharger" (click)="telecharger(pc)"></button>
          <button pButton icon="pi pi-trash" [text]="true" severity="danger" (click)="supprimerPiece(pc)"></button>
        </td>
      </tr>
    </ng-template>
    <ng-template pTemplate="emptymessage">
      <tr><td colspan="5" class="vide">Aucune pièce jointe.</td></tr>
    </ng-template>
  </p-table>
</p-dialog>

<!-- Dialog ressource création / édition -->
<p-dialog [(visible)]="dlgRessource" [modal]="true" [style]="{width:'560px'}" [header]="editionRes() ? 'Modifier la ressource' : 'Nouvelle ressource'">
  <div class="form-grid">
    <label>Type *</label>
    <p-select [(ngModel)]="fr.type_ressource" [options]="typesRessource" optionLabel="label" optionValue="value" appendTo="body"></p-select>
    <label>Libellé *</label>
    <input pInputText [(ngModel)]="fr.libelle" placeholder="Ex. Prêt BNDE équipement 2026" />
    <label>Organisme / origine</label>
    <input pInputText [(ngModel)]="fr.organisme" />
    <label>Montant mobilisé (FCFA) *</label>
    <p-inputNumber [(ngModel)]="fr.montant" [min]="0" [useGrouping]="true" mode="decimal"></p-inputNumber>
    <label>Date</label>
    <p-datepicker [(ngModel)]="fr.date_ressource" dateFormat="dd/mm/yy" [showIcon]="true" appendTo="body"></p-datepicker>
    <label>Convention / réf.</label>
    <input pInputText [(ngModel)]="fr.convention" />
    <label>Observations</label>
    <textarea pTextarea [(ngModel)]="fr.observations" rows="2"></textarea>
  </div>
  <ng-template pTemplate="footer">
    <button pButton label="Annuler" [text]="true" (click)="dlgRessource.set(false)"></button>
    <button pButton label="Enregistrer" icon="pi pi-check" (click)="enregistrerRessource()" [disabled]="!fr.libelle || !fr.montant"></button>
  </ng-template>
</p-dialog>

<!-- Dialog affectations -->
<p-dialog [(visible)]="dlgAffect" [modal]="true" [style]="{width:'640px'}" [header]="'Affectations — ' + (ressourceCourante()?.reference || '')">
  @if (ressourceCourante(); as rc) {
    <div class="affect-head">
      <span>Disponible à affecter : <strong>{{ rc.disponible_a_affecter | number:'1.0-0' }}</strong> FCFA</span>
    </div>
    <div class="form-grid">
      <label>Emploi</label>
      <p-select [(ngModel)]="fa.type_emploi" [options]="typesEmploi" optionLabel="label" optionValue="value" appendTo="body"></p-select>
      <label>Libellé</label>
      <input pInputText [(ngModel)]="fa.libelle" placeholder="Ex. Ordinateurs salle info" />
      <label>Montant affecté</label>
      <p-inputNumber [(ngModel)]="fa.montant_affecte" [min]="0" [useGrouping]="true" mode="decimal"></p-inputNumber>
    </div>
    <div class="affect-add">
      <button pButton label="Affecter" icon="pi pi-plus" (click)="ajouterAffectation()" [disabled]="!fa.libelle || !fa.montant_affecte"></button>
    </div>
    <p-table [value]="affectations()" styleClass="p-datatable-sm">
      <ng-template pTemplate="header"><tr><th>Emploi</th><th>Libellé</th><th class="r">Montant</th><th></th></tr></ng-template>
      <ng-template pTemplate="body" let-a>
        <tr>
          <td><p-tag [value]="a.type_label"></p-tag></td>
          <td>{{ a.libelle }}</td>
          <td class="r">{{ a.montant_affecte | number:'1.0-0' }}</td>
          <td class="actions"><button pButton icon="pi pi-trash" [text]="true" severity="danger" (click)="supprimerAffectation(a)"></button></td>
        </tr>
      </ng-template>
      <ng-template pTemplate="emptymessage"><tr><td colspan="4" class="vide">Aucune affectation.</td></tr></ng-template>
    </p-table>
  }
</p-dialog>

<!-- Dialog traçabilité -->
<p-dialog [(visible)]="dlgTrac" [modal]="true" [style]="{width:'720px'}" [header]="'Traçabilité — ' + (tracabilite()?.ressource?.reference || '')">
  @if (tracabilite(); as t) {
    <div class="trac-grid">
      <div class="trac-col">
        <h4>D'où vient l'argent</h4>
        <p class="trac-src">{{ t.ressource.type_label }}@if (t.ressource.organisme) { — {{ t.ressource.organisme }}}</p>
        <p class="trac-montant">{{ t.ressource.montant | number:'1.0-0' }} FCFA</p>
      </div>
      <div class="trac-col">
        <h4>À quoi il sert (planifié)</h4>
        @for (a of t.affectations; track a.id) {
          <div class="trac-line"><span>{{ a.type_label }} — {{ a.libelle }}</span><span>{{ a.montant_affecte | number:'1.0-0' }}</span></div>
        } @empty { <p class="vide">Aucune affectation planifiée.</p> }
      </div>
    </div>
    <h4 class="trac-h">Impact réel (consommations comptables)</h4>
    <p-table [value]="t.consommations" styleClass="p-datatable-sm">
      <ng-template pTemplate="header"><tr><th>Date</th><th>Pièce</th><th>Nature</th><th>Libellé</th><th class="r">Montant</th></tr></ng-template>
      <ng-template pTemplate="body" let-c>
        <tr>
          <td>{{ c.date | date:'dd/MM/yy' }}</td>
          <td>{{ c.no_piece }}</td>
          <td><p-tag [value]="c.nature === 'IMMOBILISATION' ? 'Immo' : 'Charge'" [severity]="c.nature === 'IMMOBILISATION' ? 'warn' : 'info'"></p-tag></td>
          <td>{{ c.libelle }}</td>
          <td class="r">{{ c.montant | number:'1.0-0' }}</td>
        </tr>
      </ng-template>
      <ng-template pTemplate="emptymessage"><tr><td colspan="5" class="vide">Aucune dépense liée pour l'instant.</td></tr></ng-template>
    </p-table>
  }
</p-dialog>

<!-- Dialog compte bancaire -->
<p-dialog [(visible)]="dlgCompteBancaire" [modal]="true" [style]="{width:'480px'}" header="Nouveau compte bancaire">
  <div class="form-grid">
    <label>Libellé *</label>
    <input pInputText [(ngModel)]="fcb.libelle" placeholder="Ex. Compte courant CBAO" />
    <label>Banque</label>
    <input pInputText [(ngModel)]="fcb.banque" />
    <label>N° de compte / RIB</label>
    <input pInputText [(ngModel)]="fcb.numero_compte" />
    <label>Compte comptable</label>
    <input pInputText [(ngModel)]="fcb.no_compte_comptable" placeholder="521" />
    <label>Solde initial</label>
    <p-inputNumber [(ngModel)]="fcb.solde_initial" [useGrouping]="true" mode="decimal"></p-inputNumber>
  </div>
  <ng-template pTemplate="footer">
    <button pButton label="Annuler" [text]="true" (click)="dlgCompteBancaire.set(false)"></button>
    <button pButton label="Enregistrer" icon="pi pi-check" (click)="enregistrerCompteBancaire()" [disabled]="!fcb.libelle"></button>
  </ng-template>
</p-dialog>

<!-- Dialog nouveau rapprochement -->
<p-dialog [(visible)]="dlgRapprochement" [modal]="true" [style]="{width:'480px'}" header="Nouveau rapprochement">
  <div class="form-grid">
    <label>Compte bancaire *</label>
    <p-select [(ngModel)]="frap.compte_bancaire_id" [options]="comptesBancaires()" optionLabel="libelle" optionValue="id" appendTo="body"></p-select>
    <label>Date du relevé *</label>
    <p-datepicker [(ngModel)]="frap.date_rapprochement" dateFormat="dd/mm/yy" [showIcon]="true" appendTo="body"></p-datepicker>
    <label>Solde final du relevé</label>
    <p-inputNumber [(ngModel)]="frap.solde_releve" [useGrouping]="true" mode="decimal"></p-inputNumber>
  </div>
  <ng-template pTemplate="footer">
    <button pButton label="Annuler" [text]="true" (click)="dlgRapprochement.set(false)"></button>
    <button pButton label="Créer" icon="pi pi-check" (click)="enregistrerRapprochement()" [disabled]="!frap.compte_bancaire_id || !frap.date_rapprochement"></button>
  </ng-template>
</p-dialog>

<!-- Dialog détail rapprochement -->
<p-dialog [(visible)]="dlgDetailRap" [modal]="true" [style]="{width:'860px'}" [header]="'Rapprochement — ' + (rapCourant()?.reference || '')">
  @if (rapCourant(); as rap) {
    <div class="kpis">
      <div class="kpi"><span class="lbl">Solde relevé</span><span class="val">{{ rap.solde_releve | number:'1.0-0' }}</span></div>
      <div class="kpi"><span class="lbl">Solde comptable</span><span class="val">{{ rap.solde_comptable | number:'1.0-0' }}</span></div>
      <div class="kpi"><span class="lbl">Écart</span><span class="val" [style.color]="rap.ecart === 0 ? '#10b981' : '#e24c4c'">{{ rap.ecart | number:'1.0-0' }}</span></div>
    </div>
    @if (rap.statut !== 'VALIDE') {
      <div class="barre">
        <button pButton label="Rapprochement automatique" icon="pi pi-bolt" [outlined]="true" (click)="lancerAuto(rap)"></button>
        <button pButton label="Ajouter une ligne" icon="pi pi-plus" [text]="true" (click)="dlgLigne.set(true)"></button>
        <button pButton label="Valider" icon="pi pi-check-circle" severity="success" (click)="validerRapprochement(rap)"
                [disabled]="rap.ecart !== 0" [pTooltip]="rap.ecart !== 0 ? 'Écart non nul : régularisez ou pointez d’abord' : ''"></button>
      </div>
    }

    <h4 class="trac-h">Lignes du relevé</h4>
    <p-table [value]="rap.lignes" styleClass="p-datatable-sm">
      <ng-template pTemplate="header"><tr><th>Date</th><th>Libellé</th><th>Sens</th><th class="r">Montant</th><th>Statut</th><th></th></tr></ng-template>
      <ng-template pTemplate="body" let-l>
        <tr>
          <td>{{ l.date_operation | date:'dd/MM/yy' }}</td>
          <td>{{ l.libelle }}</td>
          <td>{{ l.sens === 'ENTREE' ? '↓ Entrée' : '↑ Sortie' }}</td>
          <td class="r">{{ l.montant | number:'1.0-0' }}</td>
          <td><p-tag [value]="statutLigne(l.statut)" [severity]="l.statut === 'NON_RAPPROCHEE' ? 'warn' : 'success'"></p-tag></td>
          <td class="actions">
            @if (l.statut === 'NON_RAPPROCHEE' && rap.statut !== 'VALIDE') {
              <button pButton icon="pi pi-wrench" [text]="true" pTooltip="Régulariser (créer l'écriture)" (click)="regulariser(rap, l)"></button>
              <button pButton icon="pi pi-trash" [text]="true" severity="danger" (click)="supprimerLigne(rap, l)"></button>
            }
          </td>
        </tr>
      </ng-template>
      <ng-template pTemplate="emptymessage"><tr><td colspan="6" class="vide">Aucune ligne. Importez ou ajoutez les lignes du relevé.</td></tr></ng-template>
    </p-table>

    @if (rap.ecritures_non_pointees?.length) {
      <h4 class="trac-h">Écritures comptables non pointées (chèques non débités, dépôts en transit…)</h4>
      <p-table [value]="rap.ecritures_non_pointees" styleClass="p-datatable-sm">
        <ng-template pTemplate="header"><tr><th>Date</th><th>Pièce</th><th>Libellé</th><th>Sens</th><th class="r">Montant</th></tr></ng-template>
        <ng-template pTemplate="body" let-e>
          <tr>
            <td>{{ e.date | date:'dd/MM/yy' }}</td><td>{{ e.no_piece }}</td><td>{{ e.libelle }}</td>
            <td>{{ e.sens === 'ENTREE' ? '↓ Entrée' : '↑ Sortie' }}</td>
            <td class="r">{{ e.montant | number:'1.0-0' }}</td>
          </tr>
        </ng-template>
      </p-table>
    }
  }
</p-dialog>

<!-- Dialog ajout ligne relevé -->
<p-dialog [(visible)]="dlgLigne" [modal]="true" [style]="{width:'440px'}" header="Ligne du relevé">
  <div class="form-grid">
    <label>Date</label>
    <p-datepicker [(ngModel)]="fligne.date_operation" dateFormat="dd/mm/yy" [showIcon]="true" appendTo="body"></p-datepicker>
    <label>Libellé</label>
    <input pInputText [(ngModel)]="fligne.libelle" />
    <label>Sens</label>
    <p-select [(ngModel)]="fligne.sens" [options]="sensReleve" optionLabel="label" optionValue="value" appendTo="body"></p-select>
    <label>Montant</label>
    <p-inputNumber [(ngModel)]="fligne.montant" [min]="0" [useGrouping]="true" mode="decimal"></p-inputNumber>
  </div>
  <ng-template pTemplate="footer">
    <button pButton label="Annuler" [text]="true" (click)="dlgLigne.set(false)"></button>
    <button pButton label="Ajouter" icon="pi pi-check" (click)="ajouterLigne()" [disabled]="!fligne.montant || !fligne.date_operation"></button>
  </ng-template>
</p-dialog>

<!-- Dialog nouvelle provision -->
<p-dialog [(visible)]="dlgProvision" [modal]="true" [style]="{width:'520px'}" header="Nouvelle provision">
  <div class="form-grid">
    <label>Type *</label>
    <p-select [(ngModel)]="fp.type_provision" [options]="typesProvision" optionLabel="label" optionValue="value" appendTo="body"></p-select>
    <label>Libellé *</label>
    <input pInputText [(ngModel)]="fp.libelle" placeholder="Ex. Litige avec fournisseur X" />
    <label>Montant (FCFA) *</label>
    <p-inputNumber [(ngModel)]="fp.montant" [min]="0" [useGrouping]="true" mode="decimal"></p-inputNumber>
    <label>Tiers concerné</label>
    <input pInputText [(ngModel)]="fp.tiers" placeholder="Ex. Client / fournisseur (optionnel)" />
    <label>Date de dotation</label>
    <p-datepicker [(ngModel)]="fp.date_dotation" dateFormat="dd/mm/yy" [showIcon]="true" appendTo="body"></p-datepicker>
  </div>
  <p-tag styleClass="ml" [value]="apercuComptes()" severity="info"></p-tag>
  <ng-template pTemplate="footer">
    <button pButton label="Annuler" [text]="true" (click)="dlgProvision.set(false)"></button>
    <button pButton label="Doter" icon="pi pi-check" (click)="enregistrerProvision()" [disabled]="!fp.libelle || !fp.montant"></button>
  </ng-template>
</p-dialog>

<!-- Dialog reprise -->
<p-dialog [(visible)]="dlgReprise" [modal]="true" [style]="{width:'420px'}" [header]="'Reprise — ' + (provisionCourante()?.reference || '')">
  @if (provisionCourante(); as pc) {
    <p class="solde-info">Provision actuelle : <strong>{{ pc.montant_actuel | number:'1.0-0' }}</strong> FCFA</p>
    <div class="form-grid">
      <label>Montant à reprendre</label>
      <p-inputNumber [(ngModel)]="montantReprise" [min]="0" [max]="pc.montant_actuel" [useGrouping]="true" mode="decimal"></p-inputNumber>
    </div>
  }
  <ng-template pTemplate="footer">
    <button pButton label="Annuler" [text]="true" (click)="dlgReprise.set(false)"></button>
    <button pButton label="Reprendre" icon="pi pi-check" (click)="confirmerReprise()" [disabled]="!montantReprise"></button>
  </ng-template>
</p-dialog>

<!-- Dialog traçabilité projet -->
<p-dialog [(visible)]="dlgTracProjet" [modal]="true" [style]="{width:'700px'}" [header]="'Traçabilité — ' + (tracProjet()?.projet?.code || '')">
  @if (tracProjet(); as t) {
    <div class="kpis">
      <div class="kpi"><span class="lbl">Budget</span><span class="val">{{ t.projet.budget_prevu | number:'1.0-0' }}</span></div>
      <div class="kpi"><span class="lbl">Consommé</span><span class="val">{{ t.projet.montant_consomme | number:'1.0-0' }}</span></div>
      <div class="kpi"><span class="lbl">Restant</span><span class="val">{{ t.projet.montant_restant | number:'1.0-0' }}</span></div>
    </div>
    <div class="trac-grid">
      <div class="trac-col">
        <h4>Financé par</h4>
        @for (o of t.origines; track o.ressource_id) {
          <div class="trac-line"><span>{{ o.libelle }}<em class="tt"> · {{ o.type }}</em></span><span>{{ o.montant | number:'1.0-0' }}</span></div>
        } @empty { <p class="vide">Aucune ressource liée.</p> }
      </div>
      <div class="trac-col">
        <h4>Emplois</h4>
        @for (e of t.emplois; track e.nature) {
          <div class="trac-line"><span>{{ e.nature }}</span><span>{{ e.montant | number:'1.0-0' }}</span></div>
        } @empty { <p class="vide">Aucune dépense.</p> }
      </div>
    </div>
    <h4 class="trac-h">Immobilisations créées</h4>
    <p-table [value]="t.immobilisations" styleClass="p-datatable-sm">
      <ng-template pTemplate="header"><tr><th>N°</th><th>Libellé</th><th class="r">Valeur</th><th class="r">VNC</th></tr></ng-template>
      <ng-template pTemplate="body" let-im>
        <tr><td>{{ im.no_bien }}</td><td>{{ im.libelle }}</td><td class="r">{{ im.valeur_entree | number:'1.0-0' }}</td><td class="r">{{ im.valeur_nette_comptable | number:'1.0-0' }}</td></tr>
      </ng-template>
      <ng-template pTemplate="emptymessage"><tr><td colspan="4" class="vide">Aucune immobilisation.</td></tr></ng-template>
    </p-table>
  }
</p-dialog>

<!-- Dialog nouveau transfert -->
<p-dialog [(visible)]="dlgTransfert" [modal]="true" [style]="{width:'520px'}" header="Nouveau transfert interne">
  <div class="form-grid">
    <label>Compte source *</label>
    <p-select [(ngModel)]="ft.compte_source" [options]="canaux()" optionLabel="libelle" optionValue="compte" appendTo="body" placeholder="Depuis…"></p-select>
    <label>Compte destination *</label>
    <p-select [(ngModel)]="ft.compte_destination" [options]="canaux()" optionLabel="libelle" optionValue="compte" appendTo="body" placeholder="Vers…"></p-select>
    <label>Montant (FCFA) *</label>
    <p-inputNumber [(ngModel)]="ft.montant" [min]="0" [useGrouping]="true" mode="decimal"></p-inputNumber>
    <label>Frais éventuels</label>
    <p-inputNumber [(ngModel)]="ft.frais" [min]="0" [useGrouping]="true" mode="decimal"></p-inputNumber>
    <label>Date</label>
    <p-datepicker [(ngModel)]="ft.date_transfert" dateFormat="dd/mm/yy" [showIcon]="true" appendTo="body"></p-datepicker>
    <label>Motif</label>
    <input pInputText [(ngModel)]="ft.motif" placeholder="Ex. Dépôt d'espèces en banque" />
  </div>
  @if (soldeSource() !== null) {
    <p class="solde-info" [class.warn]="ft.montant + (ft.frais||0) > soldeSource()!">
      Solde source : {{ soldeSource() | number:'1.0-0' }} FCFA
    </p>
  }
  <ng-template pTemplate="footer">
    <button pButton label="Annuler" [text]="true" (click)="dlgTransfert.set(false)"></button>
    <button pButton label="Transférer" icon="pi pi-check" (click)="enregistrerTransfert()"
            [disabled]="!ft.compte_source || !ft.compte_destination || !ft.montant || ft.compte_source === ft.compte_destination"></button>
  </ng-template>
</p-dialog>
  `,
  styles: [`
    .gouv { padding: 4px; }
    .head h1 { margin:0; font-size:1.5rem; }
    .sub { margin:4px 0 0; color:var(--text-4); font-size:.9rem; }
    .tabs { display:flex; gap:6px; margin:16px 0; border-bottom:1px solid var(--surface-border,#e5e7eb); }
    .tab { background:none; border:none; padding:10px 16px; cursor:pointer; font-size:.95rem; color:var(--text-4); border-bottom:3px solid transparent; }
    .tab.active { color:var(--primary-color,#00d4aa); border-bottom-color:var(--primary-color,#00d4aa); font-weight:600; }
    .barre { display:flex; align-items:center; gap:14px; margin-bottom:14px; }
    .hint { color:var(--text-4); font-size:.83rem; }
    .kpis { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:16px; }
    .kpi { background:var(--surface-card,#fff); border:1px solid var(--surface-border,#e5e7eb); border-radius:10px; padding:12px 16px; display:flex; flex-direction:column; }
    .kpi .lbl { font-size:.8rem; color:var(--text-4); }
    .kpi .val { font-size:1.35rem; font-weight:700; }
    .canaux { display:flex; flex-wrap:wrap; gap:10px; margin-bottom:16px; }
    .canal { background:var(--surface-card,#fff); border:1px solid var(--surface-border,#e5e7eb); border-radius:8px; padding:8px 14px; display:flex; flex-direction:column; min-width:120px; }
    .c-lbl { font-size:.78rem; color:var(--text-4); }
    .c-solde { font-size:1.05rem; font-weight:700; }
    .c-solde.neg { color:#e24c4c; }
    .r { text-align:right; }
    .actions { text-align:right; white-space:nowrap; }
    .resp { font-size:.78rem; color:var(--text-4); }
    tr.inactif { opacity:.5; }
    .vide { text-align:center; color:#9ca3af; padding:24px; }
    .form-grid { display:grid; grid-template-columns:160px 1fr; gap:12px 14px; align-items:center; }
    .form-grid textarea, .form-grid .row2 { grid-column:2; }
    .row2 { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
    .ged-head { display:flex; gap:10px; margin-bottom:14px; align-items:center; }
    .solde-info { margin:12px 0 0; color:var(--text-4); font-size:.85rem; }
    .solde-info.warn { color:#d97706; font-weight:600; }
    :host ::ng-deep .ml { margin-left:8px; }
    .affect-head { margin-bottom:12px; padding:8px 12px; background:var(--surface-100,#f3f4f6); border-radius:8px; font-size:.9rem; }
    .affect-add { margin:12px 0; text-align:right; }
    .trac-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:8px; }
    .trac-col h4 { margin:0 0 8px; font-size:.85rem; text-transform:uppercase; color:var(--text-4); }
    .trac-src { margin:0; font-size:.9rem; }
    .trac-montant { margin:4px 0 0; font-size:1.3rem; font-weight:700; }
    .trac-line { display:flex; justify-content:space-between; font-size:.88rem; padding:3px 0; border-bottom:1px dashed var(--surface-border,#e5e7eb); }
    .trac-h { margin:16px 0 8px; font-size:.85rem; text-transform:uppercase; color:var(--text-4); }
    .trac-col.card { background:var(--surface-card,#fff); border:1px solid var(--surface-border,#e5e7eb); border-radius:10px; padding:14px 16px; }
    .tt { color:#9ca3af; font-style:normal; font-size:.82rem; }
    .alertes { display:flex; flex-direction:column; gap:8px; margin-bottom:16px; }
    .alerte { padding:8px 14px; border-radius:8px; font-size:.88rem; background:#eff6ff; border-left:4px solid #3b82f6; }
    .alerte.warn { background:#fffbeb; border-left-color:#d97706; }
    .alerte.danger { background:#fef2f2; border-left-color:#e24c4c; }
    .bar-row { display:grid; grid-template-columns:130px 1fr auto; align-items:center; gap:10px; padding:5px 0; font-size:.85rem; }
    .bar-lbl { color:var(--text-4); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .bar-track { background:var(--surface-100,#f1f5f9); height:12px; border-radius:6px; overflow:hidden; }
    .bar-fill { display:block; height:100%; background:#00d4aa; border-radius:6px; }
    .bar-fill.alt { background:#6366f1; }
    .bar-val { font-variant-numeric:tabular-nums; font-weight:600; }
  `]
})
export class GouvernanceComponent implements OnInit {
  private gouv = inject(GouvernanceService);
  private toast = inject(MessageService);

  tab = signal<'pilotage' | 'projets' | 'ressources' | 'provisions' | 'rapprochement' | 'transferts' | 'tracabilite'>('pilotage');
  dashboard = signal<any>(null);
  tracGlobale = signal<any>(null);
  dlgTracProjet = signal(false);
  tracProjet = signal<any>(null);

  // Projets
  projets = signal<Projet[]>([]);
  chargement = signal(false);
  dlgProjet = signal(false);
  edition = signal<Projet | null>(null);
  form: any = this.formVide();

  // GED
  dlgPieces = signal(false);
  projetCourant = signal<Projet | null>(null);
  pieces = signal<Piece[]>([]);
  chargementPieces = signal(false);
  typePieceUpload = 'AUTRE';

  // Ressources
  ressources = signal<Ressource[]>([]);
  chargementRes = signal(false);
  dlgRessource = signal(false);
  editionRes = signal<Ressource | null>(null);
  fr: any = this.ressourceVide();
  dlgAffect = signal(false);
  ressourceCourante = signal<Ressource | null>(null);
  affectations = signal<Affectation[]>([]);
  fa: any = { type_emploi: 'EQUIPEMENT', libelle: '', montant_affecte: null };
  dlgTrac = signal(false);
  tracabilite = signal<any>(null);

  // Provisions
  provisions = signal<any[]>([]);
  chargementProv = signal(false);
  dlgProvision = signal(false);
  fp: any = this.provisionVide();
  dlgReprise = signal(false);
  provisionCourante = signal<any>(null);
  montantReprise: number | null = null;

  // Rapprochement bancaire
  comptesBancaires = signal<any[]>([]);
  rapprochements = signal<any[]>([]);
  chargementRap = signal(false);
  dlgCompteBancaire = signal(false);
  fcb: any = { libelle: '', banque: '', numero_compte: '', no_compte_comptable: '521', solde_initial: 0 };
  dlgRapprochement = signal(false);
  frap: any = { compte_bancaire_id: null, date_rapprochement: new Date(), solde_releve: 0 };
  dlgDetailRap = signal(false);
  rapCourant = signal<any>(null);
  dlgLigne = signal(false);
  fligne: any = { date_operation: new Date(), libelle: '', sens: 'SORTIE', montant: null };
  sensReleve = [{ value: 'ENTREE', label: '↓ Entrée (encaissement)' }, { value: 'SORTIE', label: '↑ Sortie (décaissement)' }];

  // Transferts
  canaux = signal<Canal[]>([]);
  transferts = signal<Transfert[]>([]);
  chargementTr = signal(false);
  dlgTransfert = signal(false);
  ft: any = this.transfertVide();

  statuts = [
    { value: 'PLANIFIE', label: 'Planifié' }, { value: 'EN_COURS', label: 'En cours' },
    { value: 'SUSPENDU', label: 'Suspendu' }, { value: 'TERMINE', label: 'Terminé' },
    { value: 'ANNULE', label: 'Annulé' },
  ];
  typesPiece = [
    { value: 'FACTURE', label: 'Facture' }, { value: 'DEVIS', label: 'Devis' },
    { value: 'BON_COMMANDE', label: 'Bon de commande' }, { value: 'BON_LIVRAISON', label: 'Bon de livraison' },
    { value: 'CONTRAT', label: 'Contrat' }, { value: 'CONVENTION', label: 'Convention' },
    { value: 'RECU', label: 'Reçu' }, { value: 'RELEVE', label: 'Relevé bancaire' },
    { value: 'PHOTO', label: 'Photo' }, { value: 'PDF', label: 'Document PDF' },
    { value: 'WORD', label: 'Document Word' }, { value: 'AUTRE', label: 'Autre document' },
  ];

  typesRessource = [
    { value: 'FONDS_PROPRES', label: 'Fonds propres' }, { value: 'PRET', label: 'Prêt' },
    { value: 'SUBVENTION', label: 'Subvention' }, { value: 'DON', label: 'Don' },
    { value: 'PARTENAIRE', label: 'Partenaire' }, { value: 'PROJET', label: 'Financement de projet' },
    { value: 'COTISATION_EXCEPT', label: 'Cotisation exceptionnelle' },
    { value: 'AVANCE_TRESO', label: 'Avance de trésorerie' },
    { value: 'RECETTES_SCOLAIRES', label: 'Recettes scolaires' }, { value: 'AUTRE', label: 'Autre' },
  ];
  typesEmploi = [
    { value: 'IMMOBILISATION', label: 'Immobilisation' }, { value: 'EQUIPEMENT', label: 'Équipement' },
    { value: 'TRAVAUX', label: 'Travaux' }, { value: 'MOBILIER', label: 'Mobilier' },
    { value: 'FONCTIONNEMENT', label: 'Fonctionnement' }, { value: 'SALAIRES', label: 'Salaires' },
    { value: 'PROJET', label: 'Projet' }, { value: 'TRESORERIE', label: 'Trésorerie' },
    { value: 'AUTRE', label: 'Autre' },
  ];

  typesProvision = [
    { value: 'RISQUE', label: 'Provision pour risques', comptes: 'D 6911 / C 191 · reprise 7911' },
    { value: 'LITIGE', label: 'Provision pour litiges', comptes: 'D 6911 / C 191 · reprise 7911' },
    { value: 'CHARGE', label: 'Provision pour charges', comptes: 'D 6911 / C 198 · reprise 7911' },
    { value: 'CREANCE_DOUTEUSE', label: 'Dépréciation créances douteuses', comptes: 'D 6911 / C 491 · reprise 7911' },
    { value: 'REGLEMENTEE', label: 'Provision réglementée', comptes: 'D 851 / C 151 · reprise 861' },
  ];

  totalBudget = computed(() => this.projets().reduce((s, p) => s + (p.budget_prevu || 0), 0));
  totalConsomme = computed(() => this.projets().reduce((s, p) => s + (p.montant_consomme || 0), 0));
  totalRessources = computed(() => this.ressources().reduce((s, r) => s + (r.montant || 0), 0));
  totalConsoRes = computed(() => this.ressources().reduce((s, r) => s + (r.montant_consomme || 0), 0));
  soldeSource = computed<number | null>(() => {
    const c = this.canaux().find(x => x.compte === this.ft.compte_source);
    return c ? c.solde : null;
  });

  ngOnInit() { this.allerPilotage(); }

  // ── Pilotage ──
  allerPilotage() {
    this.tab.set('pilotage');
    this.gouv.getDashboard().subscribe({
      next: d => this.dashboard.set(d),
      error: () => this.erreur('Chargement du tableau de bord impossible'),
    });
  }
  pct(v: number, total: number) { return total > 0 ? Math.min(100, Math.round(v / total * 100)) : 0; }
  maxUsage(db: any): number {
    const arr = db?.pilotage?.utilisation || [];
    return arr.reduce((m: number, u: any) => Math.max(m, u.montant || 0), 0) || 1;
  }

  // ── Projets ──
  allerProjets() { this.tab.set('projets'); this.charger(); }
  charger() {
    this.chargement.set(true);
    this.gouv.getProjets().subscribe({
      next: d => { this.projets.set(d); this.chargement.set(false); },
      error: () => { this.chargement.set(false); this.erreur('Chargement impossible'); },
    });
  }
  formVide() {
    return { libelle: '', responsable: '', budget_prevu: 0, statut: 'PLANIFIE',
             date_debut: null, date_fin: null, description: '', observations: '' };
  }
  severite(s: string): 'success' | 'info' | 'warn' | 'secondary' | 'danger' {
    const map: Record<string, 'success' | 'info' | 'warn' | 'secondary' | 'danger'> =
      { PLANIFIE: 'info', EN_COURS: 'success', SUSPENDU: 'warn', TERMINE: 'secondary', ANNULE: 'danger' };
    return map[s] || 'info';
  }
  borne(v: number) { return Math.min(100, Math.round(v || 0)); }
  ouvrirCreation() { this.edition.set(null); this.form = this.formVide(); this.dlgProjet.set(true); }
  ouvrirEdition(p: Projet) {
    this.edition.set(p);
    this.form = {
      libelle: p.libelle, responsable: p.responsable, budget_prevu: p.budget_prevu,
      statut: p.statut, description: p.description, observations: p.observations,
      date_debut: p.date_debut ? new Date(p.date_debut) : null,
      date_fin: p.date_fin ? new Date(p.date_fin) : null,
    };
    this.dlgProjet.set(true);
  }
  private isoDate(d: any): string | null {
    if (!d) return null;
    const dt = (d instanceof Date) ? d : new Date(d);
    return isNaN(dt.getTime()) ? null : dt.toISOString().slice(0, 10);
  }
  enregistrer() {
    if (!this.form.libelle?.trim()) return;
    const payload = {
      libelle: this.form.libelle.trim(), responsable: this.form.responsable || '',
      budget_prevu: this.form.budget_prevu || 0, statut: this.form.statut,
      description: this.form.description || '', observations: this.form.observations || '',
      date_debut: this.isoDate(this.form.date_debut), date_fin: this.isoDate(this.form.date_fin),
    };
    const p = this.edition();
    const obs = p ? this.gouv.modifierProjet(p.id, payload) : this.gouv.creerProjet(payload);
    obs.subscribe({
      next: () => { this.dlgProjet.set(false); this.charger(); this.ok(p ? 'Projet modifié' : 'Projet créé'); },
      error: (e) => this.erreur(e?.error?.error || 'Enregistrement impossible'),
    });
  }
  supprimer(p: Projet) {
    if (!confirm(`Supprimer le projet « ${p.libelle} » ?`)) return;
    this.gouv.supprimerProjet(p.id).subscribe({
      next: (r: any) => { this.charger(); this.ok(r?.desactive ? 'Projet désactivé (écritures liées)' : 'Projet supprimé'); },
      error: () => this.erreur('Suppression impossible'),
    });
  }

  // ── GED ──
  ouvrirPieces(p: Projet) { this.projetCourant.set(p); this.dlgPieces.set(true); this.chargerPieces(); }
  chargerPieces() {
    const p = this.projetCourant(); if (!p) return;
    this.chargementPieces.set(true);
    this.gouv.getPieces('PROJET', p.id).subscribe({
      next: d => { this.pieces.set(d); this.chargementPieces.set(false); },
      error: () => { this.chargementPieces.set(false); },
    });
  }
  onFichierChoisi(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    const p = this.projetCourant();
    if (!file || !p) return;
    if (file.size > 4_400_000) { this.erreur('Fichier trop volumineux (max ~4,5 Mo)'); input.value = ''; return; }
    const reader = new FileReader();
    reader.onload = () => {
      this.gouv.ajouterPiece({
        objet_type: 'PROJET', objet_id: p.id, type_piece: this.typePieceUpload,
        nom: file.name, contenu: reader.result as string,
      }).subscribe({
        next: () => { this.chargerPieces(); this.ok('Pièce ajoutée'); },
        error: (e) => this.erreur(e?.error?.error || 'Ajout impossible'),
      });
    };
    reader.readAsDataURL(file);
    input.value = '';
  }
  telecharger(pc: Piece) {
    this.gouv.getPiece(pc.id).subscribe({
      next: (full: any) => { const a = document.createElement('a'); a.href = full.contenu; a.download = pc.nom; a.click(); },
      error: () => this.erreur('Téléchargement impossible'),
    });
  }
  supprimerPiece(pc: Piece) {
    if (!confirm(`Supprimer « ${pc.nom} » ?`)) return;
    this.gouv.supprimerPiece(pc.id).subscribe({
      next: () => { this.chargerPieces(); this.ok('Pièce supprimée'); },
      error: () => this.erreur('Suppression impossible'),
    });
  }

  // ── Ressources ──
  ressourceVide() {
    return { type_ressource: 'PRET', libelle: '', organisme: '', montant: null,
             date_ressource: new Date(), convention: '', observations: '' };
  }
  allerRessources() { this.tab.set('ressources'); this.chargerRessources(); }
  chargerRessources() {
    this.chargementRes.set(true);
    this.gouv.getRessources().subscribe({
      next: d => { this.ressources.set(d); this.chargementRes.set(false); },
      error: () => { this.chargementRes.set(false); this.erreur('Chargement impossible'); },
    });
  }
  ouvrirRessource() { this.editionRes.set(null); this.fr = this.ressourceVide(); this.dlgRessource.set(true); }
  ouvrirRessourceEdit(r: Ressource) {
    this.editionRes.set(r);
    this.fr = {
      type_ressource: r.type_ressource, libelle: r.libelle, organisme: r.organisme,
      montant: r.montant, convention: r.convention, observations: r.observations,
      date_ressource: r.date_ressource ? new Date(r.date_ressource) : null,
    };
    this.dlgRessource.set(true);
  }
  enregistrerRessource() {
    if (!this.fr.libelle?.trim() || !this.fr.montant) return;
    const payload = {
      type_ressource: this.fr.type_ressource, libelle: this.fr.libelle.trim(),
      organisme: this.fr.organisme || '', montant: this.fr.montant,
      convention: this.fr.convention || '', observations: this.fr.observations || '',
      date_ressource: this.isoDate(this.fr.date_ressource),
    };
    const r = this.editionRes();
    const obs = r ? this.gouv.modifierRessource(r.id, payload) : this.gouv.creerRessource(payload);
    obs.subscribe({
      next: () => { this.dlgRessource.set(false); this.chargerRessources(); this.ok(r ? 'Ressource modifiée' : 'Ressource créée'); },
      error: (e) => this.erreur(e?.error?.error || 'Enregistrement impossible'),
    });
  }
  supprimerRessource(r: Ressource) {
    if (!confirm(`Supprimer la ressource « ${r.libelle} » ?`)) return;
    this.gouv.supprimerRessource(r.id).subscribe({
      next: (res: any) => { this.chargerRessources(); this.ok(res?.cloturee ? 'Ressource clôturée (dépenses liées)' : 'Ressource supprimée'); },
      error: () => this.erreur('Suppression impossible'),
    });
  }
  ouvrirAffectations(r: Ressource) {
    this.ressourceCourante.set(r);
    this.fa = { type_emploi: 'EQUIPEMENT', libelle: '', montant_affecte: null };
    this.dlgAffect.set(true);
    this.chargerAffectations();
  }
  chargerAffectations() {
    const r = this.ressourceCourante(); if (!r) return;
    this.gouv.getAffectations(r.id).subscribe({ next: d => this.affectations.set(d), error: () => {} });
  }
  ajouterAffectation() {
    const r = this.ressourceCourante(); if (!r || !this.fa.libelle || !this.fa.montant_affecte) return;
    this.gouv.creerAffectation({
      ressource_id: r.id, type_emploi: this.fa.type_emploi,
      libelle: this.fa.libelle, montant_affecte: this.fa.montant_affecte,
    }).subscribe({
      next: () => {
        this.fa = { type_emploi: 'EQUIPEMENT', libelle: '', montant_affecte: null };
        this.chargerAffectations(); this.chargerRessources(); this.ok('Affectation ajoutée');
        // Rafraîchit le disponible affiché dans l'en-tête du dialog.
        this.gouv.getRessources().subscribe(d => {
          const maj = d.find(x => x.id === r.id); if (maj) this.ressourceCourante.set(maj as Ressource);
        });
      },
      error: (e) => this.erreur(e?.error?.error || 'Affectation impossible'),
    });
  }
  supprimerAffectation(a: Affectation) {
    this.gouv.supprimerAffectation(a.id).subscribe({
      next: () => { this.chargerAffectations(); this.chargerRessources(); this.ok('Affectation supprimée'); },
      error: () => this.erreur('Suppression impossible'),
    });
  }
  ouvrirTracabilite(r: Ressource) {
    this.tracabilite.set(null); this.dlgTrac.set(true);
    this.gouv.getTracabilite(r.id).subscribe({
      next: d => this.tracabilite.set(d),
      error: () => this.erreur('Chargement impossible'),
    });
  }

  // ── Provisions ──
  provisionVide() {
    return { type_provision: 'RISQUE', libelle: '', montant: null, tiers: '', date_dotation: new Date() };
  }
  apercuComptes() {
    const t = this.typesProvision.find(x => x.value === this.fp.type_provision);
    return t ? 'Écritures : ' + t.comptes : '';
  }
  allerProvisions() { this.tab.set('provisions'); this.chargerProvisions(); }
  chargerProvisions() {
    this.chargementProv.set(true);
    this.gouv.getProvisions().subscribe({
      next: d => { this.provisions.set(d); this.chargementProv.set(false); },
      error: () => { this.chargementProv.set(false); this.erreur('Chargement impossible'); },
    });
  }
  ouvrirProvision() { this.fp = this.provisionVide(); this.dlgProvision.set(true); }
  enregistrerProvision() {
    if (!this.fp.libelle?.trim() || !this.fp.montant) return;
    this.gouv.creerProvision({
      type_provision: this.fp.type_provision, libelle: this.fp.libelle.trim(),
      montant: this.fp.montant, tiers: this.fp.tiers || '',
      date_dotation: this.isoDate(this.fp.date_dotation),
    }).subscribe({
      next: () => { this.dlgProvision.set(false); this.chargerProvisions(); this.ok('Provision dotée'); },
      error: (e) => this.erreur(e?.error?.error || 'Dotation impossible'),
    });
  }
  ouvrirReprise(p: any) { this.provisionCourante.set(p); this.montantReprise = null; this.dlgReprise.set(true); }
  confirmerReprise() {
    const p = this.provisionCourante();
    if (!p || !this.montantReprise) return;
    this.gouv.reprendreProvision(p.id, this.montantReprise).subscribe({
      next: () => { this.dlgReprise.set(false); this.chargerProvisions(); this.ok('Reprise enregistrée'); },
      error: (e) => this.erreur(e?.error?.error || 'Reprise impossible'),
    });
  }
  annulerProvision(p: any) {
    if (!confirm(`Annuler la provision ${p.reference} ? Les écritures seront extournées.`)) return;
    this.gouv.annulerProvision(p.id).subscribe({
      next: () => { this.chargerProvisions(); this.ok('Provision annulée'); },
      error: (e) => this.erreur(e?.error?.error || 'Annulation impossible'),
    });
  }

  // ── Rapprochement bancaire ──
  allerRapprochement() {
    this.tab.set('rapprochement');
    this.chargementRap.set(true);
    this.gouv.getComptesBancaires().subscribe({ next: d => this.comptesBancaires.set(d || []), error: () => {} });
    this.gouv.getRapprochements().subscribe({
      next: d => { this.rapprochements.set(d); this.chargementRap.set(false); },
      error: () => { this.chargementRap.set(false); this.erreur('Chargement impossible'); },
    });
  }
  ouvrirCompteBancaire() {
    this.fcb = { libelle: '', banque: '', numero_compte: '', no_compte_comptable: '521', solde_initial: 0 };
    this.dlgCompteBancaire.set(true);
  }
  enregistrerCompteBancaire() {
    if (!this.fcb.libelle?.trim()) return;
    this.gouv.creerCompteBancaire(this.fcb).subscribe({
      next: () => { this.dlgCompteBancaire.set(false); this.allerRapprochement(); this.ok('Compte bancaire créé'); },
      error: (e) => this.erreur(e?.error?.error || 'Enregistrement impossible'),
    });
  }
  ouvrirRapprochement() {
    this.frap = { compte_bancaire_id: this.comptesBancaires()[0]?.id || null, date_rapprochement: new Date(), solde_releve: 0 };
    this.dlgRapprochement.set(true);
  }
  enregistrerRapprochement() {
    if (!this.frap.compte_bancaire_id || !this.frap.date_rapprochement) return;
    this.gouv.creerRapprochement({
      compte_bancaire_id: this.frap.compte_bancaire_id,
      date_rapprochement: this.isoDate(this.frap.date_rapprochement),
      solde_releve: this.frap.solde_releve || 0,
    }).subscribe({
      next: (rap) => { this.dlgRapprochement.set(false); this.allerRapprochement(); this.rapCourant.set(rap); this.dlgDetailRap.set(true); this.ok('Rapprochement créé'); },
      error: (e) => this.erreur(e?.error?.error || 'Création impossible'),
    });
  }
  ouvrirDetailRap(r: any) {
    this.dlgDetailRap.set(true);
    this.rafraichirDetail(r.id);
  }
  rafraichirDetail(id: string) {
    this.gouv.getRapprochement(id).subscribe({ next: d => this.rapCourant.set(d), error: () => {} });
  }
  statutLigne(s: string) {
    return { NON_RAPPROCHEE: 'Non rapprochée', RAPPROCHEE: 'Rapprochée', REGULARISEE: 'Régularisée' }[s] || s;
  }
  lancerAuto(rap: any) {
    this.gouv.rapprochementAuto(rap.id).subscribe({
      next: (r: any) => { this.rafraichirDetail(rap.id); this.allerRapprochement(); this.ok(`${r.rapproches} rapprochement(s) automatique(s)`); },
      error: () => this.erreur('Rapprochement automatique impossible'),
    });
  }
  ajouterLigne() {
    const rap = this.rapCourant();
    if (!rap || !this.fligne.montant || !this.fligne.date_operation) return;
    this.gouv.ajouterLigneReleve(rap.id, {
      date_operation: this.isoDate(this.fligne.date_operation), libelle: this.fligne.libelle || '',
      sens: this.fligne.sens, montant: this.fligne.montant,
    }).subscribe({
      next: () => {
        this.fligne = { date_operation: new Date(), libelle: '', sens: 'SORTIE', montant: null };
        this.dlgLigne.set(false); this.rafraichirDetail(rap.id);
      },
      error: (e) => this.erreur(e?.error?.error || 'Ajout impossible'),
    });
  }
  supprimerLigne(rap: any, l: any) {
    this.gouv.supprimerLigneReleve(rap.id, l.id).subscribe({
      next: () => this.rafraichirDetail(rap.id),
      error: (e) => this.erreur(e?.error?.error || 'Suppression impossible'),
    });
  }
  regulariser(rap: any, l: any) {
    const compte = prompt('Compte de contrepartie ?', l.sens === 'SORTIE' ? '631' : '771');
    if (!compte) return;
    this.gouv.regulariserLigne(rap.id, l.id, compte).subscribe({
      next: () => { this.rafraichirDetail(rap.id); this.allerRapprochement(); this.ok('Écriture de régularisation générée'); },
      error: (e) => this.erreur(e?.error?.error || 'Régularisation impossible'),
    });
  }
  validerRapprochement(rap: any) {
    this.gouv.validerRapprochement(rap.id).subscribe({
      next: () => { this.rafraichirDetail(rap.id); this.allerRapprochement(); this.ok('Rapprochement validé'); },
      error: (e) => this.erreur(e?.error?.error || 'Validation impossible'),
    });
  }
  supprimerRapprochement(r: any) {
    if (!confirm(`Supprimer le rapprochement ${r.reference} ?`)) return;
    this.gouv.supprimerRapprochement(r.id).subscribe({
      next: () => this.allerRapprochement(),
      error: (e) => this.erreur(e?.error?.error || 'Suppression impossible'),
    });
  }

  // ── Traçabilité ──
  allerTracabilite() {
    this.tab.set('tracabilite'); this.tracGlobale.set(null);
    this.gouv.getTracabiliteGlobale().subscribe({
      next: d => this.tracGlobale.set(d),
      error: () => this.erreur('Chargement impossible'),
    });
  }
  ouvrirTracProjet(p: Projet) {
    this.tracProjet.set(null); this.dlgTracProjet.set(true);
    this.gouv.getProjetTracabilite(p.id).subscribe({
      next: d => this.tracProjet.set(d),
      error: () => this.erreur('Chargement impossible'),
    });
  }

  // ── Transferts ──
  allerTransferts() { this.tab.set('transferts'); this.chargerTransferts(); }
  chargerTransferts() {
    this.chargementTr.set(true);
    this.gouv.getCanaux().subscribe({ next: d => this.canaux.set(d?.canaux || []), error: () => {} });
    this.gouv.getTransferts().subscribe({
      next: d => { this.transferts.set(d); this.chargementTr.set(false); },
      error: () => { this.chargementTr.set(false); this.erreur('Chargement impossible'); },
    });
  }
  transfertVide() {
    return { compte_source: null, compte_destination: null, montant: null, frais: 0,
             date_transfert: new Date(), motif: '' };
  }
  ouvrirTransfert() { this.ft = this.transfertVide(); this.dlgTransfert.set(true); }
  enregistrerTransfert() {
    if (!this.ft.compte_source || !this.ft.compte_destination || !this.ft.montant) return;
    if (this.ft.compte_source === this.ft.compte_destination) { this.erreur('Source et destination identiques'); return; }
    this.gouv.creerTransfert({
      compte_source: this.ft.compte_source, compte_destination: this.ft.compte_destination,
      montant: this.ft.montant, frais: this.ft.frais || 0,
      date_transfert: this.isoDate(this.ft.date_transfert), motif: this.ft.motif || '',
    }).subscribe({
      next: () => { this.dlgTransfert.set(false); this.chargerTransferts(); this.ok('Transfert enregistré'); },
      error: (e) => this.erreur(e?.error?.error || 'Transfert impossible'),
    });
  }
  annulerTransfert(t: Transfert) {
    if (!confirm(`Annuler le transfert ${t.reference} ? Les écritures seront extournées.`)) return;
    this.gouv.annulerTransfert(t.id).subscribe({
      next: () => { this.chargerTransferts(); this.ok('Transfert annulé'); },
      error: (e) => this.erreur(e?.error?.error || 'Annulation impossible'),
    });
  }

  private ok(m: string) { this.toast.add({ severity: 'success', summary: m, life: 2500 }); }
  private erreur(m: string) { this.toast.add({ severity: 'error', summary: m, life: 4000 }); }
}
