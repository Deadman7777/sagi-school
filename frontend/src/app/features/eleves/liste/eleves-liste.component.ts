import { Component, OnInit, inject, signal, computed, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ElevesService } from '../../../core/services/eleves.service';
import { AuthService } from '../../../core/services/auth.service';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { Eleve, NiveauAlerte, PriseEnChargeStats, TypePEC, Service,
         LigneImpayeAnterieur } from '../../../core/models/eleve.model';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { DialogModule } from 'primeng/dialog';
import { SelectModule } from 'primeng/select';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';
import { ProgressBarModule } from 'primeng/progressbar';
import { InputNumberModule } from 'primeng/inputnumber';
import { TooltipModule } from 'primeng/tooltip';
import { MultiSelectModule } from 'primeng/multiselect';
import { ImportElevesDialogComponent } from './import-eleves-dialog.component';

/** Ligne de la grille de saisie, augmentée de sa valeur d'origine. */
type LigneImpayeEditable = LigneImpayeAnterieur & { montant0: number; note0: string };

interface PecForm {
  prise_en_charge: string | null;
  pec_inscription: number;
  pec_mensualite: number;
  obs_prise_en_charge: string;
}

@Component({
  selector: 'app-eleves-liste',
  changeDetection: ChangeDetectionStrategy.Default,
  imports: [CommonModule, FormsModule, TranslateModule, TableModule, TagModule, ButtonModule,
            InputTextModule, DialogModule, SelectModule, ToastModule, ProgressBarModule, InputNumberModule,
            TooltipModule, MultiSelectModule, ImportElevesDialogComponent],
  providers: [MessageService],
  template: `
    <p-toast />

    <!-- Header -->
    <div class="page-header">
      <div>
        <h2 class="page-title">{{ 'eleves.title' | translate }}</h2>
        <span class="page-sub">{{ eleves().length }} élèves</span>
      </div>
      <div style="display:flex;gap:8px">
        <p-button [label]="onglet() === 'liste' ? 'Prise en charge' : 'Liste élèves'"
                  severity="secondary" size="small"
                  [pTooltip]="onglet() === 'liste' ? 'Voir les prises en charge sociales' : 'Revenir à la liste des élèves'"
                  (onClick)="basculerOnglet()" />
        <p-button icon="pi pi-file-pdf" label="Export PDF" severity="danger" size="small"
                  pTooltip="Exporter la liste en PDF"
                  [loading]="exportant()" (onClick)="exporterListePDF()" />
        <p-button icon="pi pi-file-import" [label]="'eleves.import_btn' | translate"
                  severity="info" size="small"
                  [pTooltip]="'eleves.import_titre' | translate" [disabled]="estAnneeCloturee()"
                  (onClick)="dialogImportVisible = true" />
        <p-button icon="pi pi-history" [label]="'eleves.saisie_impayes' | translate"
                  severity="warn" size="small"
                  [pTooltip]="'eleves.saisie_impayes_aide' | translate" [disabled]="estAnneeCloturee()"
                  (onClick)="ouvrirSaisieImpayes()" />
        <p-button label="{{ 'eleves.nouveau' | translate }}" severity="success"
                  pTooltip="Inscrire un nouvel élève" [disabled]="estAnneeCloturee()"
                  (onClick)="ouvrirDialog()" />
      </div>
    </div>

    <!-- ══════════════════════════ ONGLET LISTE ══════════════════════════ -->
    @if (onglet() === 'liste') {
      <div class="kpi-row" style="margin-bottom:14px">
        <div class="kpi-mini" (click)="filtreStatut='';filtrer()">
          <span class="km-val">{{ eleves().length }}</span>
          <span class="km-label">Total</span>
        </div>
        <div class="kpi-mini success" (click)="filtreStatut='INSCRIT';filtrer()">
          <span class="km-val">{{ countStatut('INSCRIT') }}</span>
          <span class="km-label">Inscrits</span>
        </div>
        <div class="kpi-mini danger" (click)="filtreStatut='ABANDONNE';filtrer()">
          <span class="km-val">{{ countStatut('ABANDONNE') }}</span>
          <span class="km-label">Abandons</span>
        </div>
        <div class="kpi-mini warn" (click)="filtreStatut='TRANSFERE';filtrer()">
          <span class="km-val">{{ countStatut('TRANSFERE') }}</span>
          <span class="km-label">Transférés</span>
        </div>
        <div class="kpi-mini info" (click)="filtreStatut='DIPLOME';filtrer()">
          <span class="km-val">{{ countStatut('DIPLOME') }}</span>
          <span class="km-label">Diplômés</span>
        </div>
        <div class="kpi-mini" style="border-color:#7c3aed">
          <span class="km-val" style="color:#7c3aed">{{ countGenre('G') }}</span>
          <span class="km-label">Garçons</span>
        </div>
        <div class="kpi-mini" style="border-color:#ec4899">
          <span class="km-val" style="color:#ec4899">{{ countGenre('F') }}</span>
          <span class="km-label">Filles</span>
        </div>
        <!-- Dettes des années antérieures : compteur cliquable pour isoler
             les élèves à relancer. -->
        @if (nbAvecReliquat() > 0) {
          <div class="kpi-mini" style="border-color:#f97316;cursor:pointer"
               (click)="filtreReliquat = !filtreReliquat; filtrer()"
               [style.background]="filtreReliquat ? 'rgba(249,115,22,0.12)' : ''">
            <span class="km-val" style="color:#f97316">{{ nbAvecReliquat() }}</span>
            <span class="km-label">{{ 'eleves.reliquat' | translate }}
              ({{ totalReliquat() | number:'1.0-0' }})</span>
          </div>
        }
      </div>

      <div class="filters-bar">
        <input pInputText [(ngModel)]="recherche" (input)="filtrer()"
               [placeholder]="'eleves.rechercher' | translate" class="search-input" />
        <p-select appendTo="body" [options]="filtresStatut" [(ngModel)]="filtreStatut"
                  (onChange)="filtrer()" placeholder="Tous statuts"
                  optionLabel="label" optionValue="value" styleClass="filter-drop" />
        <p-select appendTo="body" [options]="filtresAlerte" [(ngModel)]="filtreAlerte"
                  (onChange)="filtrer()" [placeholder]="'eleves.toutes_alertes' | translate"
                  optionLabel="label" optionValue="value" styleClass="filter-drop" />
        <p-select appendTo="body" [options]="tris" [(ngModel)]="tri"
                  (onChange)="filtrer()" placeholder="Trier par…"
                  optionLabel="label" optionValue="value" styleClass="filter-drop" />
        <select class="ex-select" [(ngModel)]="exerciceSel" (ngModelChange)="changerExercice()">
          <option value="">{{ 'comptabilite.annee_active' | translate }}</option>
          @for (ex of exercices(); track ex.id) {
            <option [value]="ex.id">{{ ex.annee_scolaire }}{{ ex.cloture ? ' 🔒' : '' }}</option>
          }
        </select>
      </div>
      @if (estAnneeCloturee()) {
        <div class="readonly-banner-el">🔒 {{ 'eleves.annee_cloturee' | translate }}</div>
      }

      <!-- Légende des alertes (repliable) -->
      <div class="alerte-aide">
        <button class="aide-toggle" (click)="legendeVisible = !legendeVisible">
          {{ legendeVisible ? '▾' : '▸' }} {{ 'eleves.alertes_aide' | translate }}
        </button>
        @if (legendeVisible) {
          <div class="aide-corps">
            <span><p-tag value="CRITIQUE" severity="danger" /> {{ 'eleves.alerte_critique' | translate }}</span>
            <span><p-tag value="URGENT" severity="danger" /> {{ 'eleves.alerte_urgent' | translate }}</span>
            <span><p-tag value="ATTENTION" severity="warn" /> {{ 'eleves.alerte_attention' | translate }}</span>
            <span><p-tag value="OK" severity="success" /> {{ 'eleves.alerte_ok' | translate }}</span>
            <span><p-tag value="A JOUR" severity="success" /> {{ 'eleves.alerte_a_jour' | translate }}</span>
          </div>
        }
      </div>

      <div class="table-card">
        <p-table [value]="elevesFiltres()" [loading]="loading()"
                 [rowHover]="true" styleClass="p-datatable-sm"
                 [paginator]="true" [rows]="20">
          <ng-template pTemplate="header">
            <tr>
              <th>{{ 'eleves.numero'        | translate }}</th>
              <th>{{ 'eleves.matricule'     | translate }}</th>
              <th>{{ 'eleves.nom_complet'   | translate }}</th>
              <th>{{ 'eleves.section'       | translate }}</th>
              <th>{{ 'eleves.genre'         | translate }}</th>
              <th>Statut</th>
              <th>{{ 'eleves.total_attendu' | translate }}</th>
              <th>{{ 'eleves.paye'          | translate }}</th>
              <th>{{ 'eleves.du_global'     | translate }}</th>
              <th>{{ 'eleves.reliquat'      | translate }}</th>
              <th>{{ 'eleves.alerte'        | translate }}</th>
              <th>{{ 'eleves.actions'       | translate }}</th>
            </tr>
          </ng-template>
          <ng-template pTemplate="body" let-eleve>
            <tr>
              <td class="mono">{{ eleve.numero }}</td>
              <td class="mono" style="color:#00d4aa;font-size:11px">{{ eleve.matricule }}</td>
              <td class="bold">{{ eleve.nom_complet }}</td>
              <td>{{ eleve.section_nom }}</td>
              <td>
                <p-tag [value]="eleve.genre === 'F' ? ('eleves.fille' | translate) : ('eleves.garcon' | translate)"
                       [severity]="eleve.genre === 'F' ? 'info' : 'success'" />
              </td>
              <td>
                <p-tag [value]="statutLabel(eleve.statut)" [severity]="statutSeverity(eleve.statut)" />
              </td>
              <td class="mono">{{ eleve.total_attendu | number }} FCFA</td>
              <td class="mono success">{{ eleve.total_paye | number }} FCFA</td>
              <!-- Ce que la famille doit RÉELLEMENT : année en cours + ardoise
                   des années d'avant. La décomposition est au survol. -->
              <td class="mono" [class.danger]="eleve.reste_a_payer_global > 0"
                  [pTooltip]="detailDu(eleve)">
                {{ eleve.reste_a_payer_global | number }} FCFA
              </td>
              <!-- Dette d'une année antérieure : canal de suivi distinct de
                   l'alerte, qui ne juge que l'année en cours. -->
              <td>
                @if (eleve.reliquat_restant > 0) {
                  <span class="reliquat-badge"
                        [pTooltip]="('eleves.reliquat_de' | translate) + ' ' + eleve.reliquat_origine_libelle">
                    {{ eleve.reliquat_restant | number }} FCFA
                  </span>
                } @else {
                  <span class="mono" style="color:var(--text-3)">—</span>
                }
              </td>
              <td>
                <p-tag [value]="alerteLabel(eleve.niveau_alerte)"
                       [severity]="alerteSeverity(eleve.niveau_alerte)" />
              </td>
              <td>
                <div class="btn-row">
                  <p-button icon="pi pi-eye" [rounded]="true" [text]="true"
                            severity="info" pTooltip="Fiche complète" (onClick)="voirFiche(eleve)" />
                  <p-button icon="pi pi-file-pdf" [rounded]="true" [text]="true"
                            severity="danger" pTooltip="Certificat de scolarité" (onClick)="genererCertificat(eleve)" />
                  <p-button icon="pi pi-wallet" [rounded]="true" [text]="true"
                            severity="success" pTooltip="Situation financière PDF" (onClick)="telechargerSituationPDF(eleve)" />
                  <p-button icon="pi pi-user-edit" [rounded]="true" [text]="true"
                            severity="warn" pTooltip="Changer statut" (onClick)="ouvrirChangerStatut(eleve)" />
                  <p-button icon="pi pi-heart" [rounded]="true" [text]="true"
                            severity="secondary" pTooltip="Prise en charge" (onClick)="ouvrirPriseEnCharge(eleve)" />
                  <p-button icon="pi pi-bookmark" [rounded]="true" [text]="true"
                            severity="help" pTooltip="Services / Activités" (onClick)="ouvrirServices(eleve)" />
                  <p-button icon="pi pi-pencil" [rounded]="true" [text]="true"
                            severity="contrast" pTooltip="Corriger le déjà payé (reprise)"
                            (onClick)="ouvrirReprise(eleve)" />
                </div>
              </td>
            </tr>
          </ng-template>
          <ng-template pTemplate="emptymessage">
            <tr><td colspan="11" class="empty-msg">{{ 'eleves.aucun' | translate }}</td></tr>
          </ng-template>
        </p-table>
      </div>
    }

    <!-- ══════════════════════ ONGLET PRISE EN CHARGE ══════════════════════ -->
    @if (onglet() === 'prise_en_charge') {

      <!-- KPIs prises en charge -->
      <div class="kpi-row" style="margin-bottom:14px">
        <div class="kpi-mini" style="border-color:#7c3aed">
          <span class="km-val" style="color:#7c3aed">{{ elevesPEC().length }}</span>
          <span class="km-label">Bénéficiaires</span>
        </div>
        <div class="kpi-mini" style="border-color:#3b82f6">
          <span class="km-val" style="color:#3b82f6">{{ countTypePEC('INSCRIPTION') }}</span>
          <span class="km-label">Inscription</span>
        </div>
        <div class="kpi-mini" style="border-color:#10b981">
          <span class="km-val" style="color:#10b981">{{ countTypePEC('MENSUALITES') }}</span>
          <span class="km-label">Mensualités</span>
        </div>
        <div class="kpi-mini" style="border-color:#f59e0b">
          <span class="km-val" style="color:#f59e0b">{{ countTypePEC('TOTALE') }}</span>
          <span class="km-label">Totale</span>
        </div>
        @if (statsPEC()) {
          <div class="kpi-mini" style="border-color:#ef4444">
            <span class="km-val" style="color:#ef4444">{{ statsPEC()!.financier.perte_annuelle_pec | number:'1.0-0' }}</span>
            <span class="km-label">Perte annuelle (FCFA)</span>
          </div>
          <div class="kpi-mini" style="border-color:#f59e0b">
            <span class="km-val" style="color:#f59e0b">{{ statsPEC()!.financier.cout_mensuel_pec | number:'1.0-0' }}</span>
            <span class="km-label">Coût mensuel (FCFA)</span>
          </div>
        }
      </div>

      <!-- Panel financier impact -->
      @if (statsPEC()) {
        @let fin = statsPEC()!.financier;
        <div class="stats-panel">
          <div class="stats-panel-title">Impact financier des prises en charge</div>
          <div class="stats-grid">
            <div class="stat-item">
              <span class="stat-label">Recettes théoriques annuelles</span>
              <span class="stat-val">{{ fin.recettes_theoriques_annuelles | number:'1.0-0' }} FCFA</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">Recettes réelles attendues</span>
              <span class="stat-val success">{{ fin.recettes_reelles_attendues | number:'1.0-0' }} FCFA</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">Perte annuelle (écart PEC)</span>
              <span class="stat-val danger">{{ fin.perte_annuelle_pec | number:'1.0-0' }} FCFA</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">Coût mensuel total PEC</span>
              <span class="stat-val warn">{{ fin.cout_mensuel_pec | number:'1.0-0' }} FCFA</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">Coût annuel total PEC</span>
              <span class="stat-val warn">{{ fin.cout_annuel_pec | number:'1.0-0' }} FCFA</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">Écart mensuel sur mensualités</span>
              <span class="stat-val" style="color:#a78bfa">{{ fin.ecart_mensuel | number:'1.0-0' }} FCFA</span>
            </div>
          </div>
        </div>
      }

      <!-- Table détail PEC -->
      <div class="table-card">
        <div class="table-toolbar">
          <span class="tbl-count">Prise en charge — {{ elevesPEC().length }} bénéficiaires</span>
        </div>
        <p-table [value]="elevesPEC()" styleClass="p-datatable-sm" [paginator]="true" [rows]="20">
          <ng-template pTemplate="header">
            <tr>
              <th>Matricule</th>
              <th>Nom complet</th>
              <th>Section</th>
              <th>Motif</th>
              <th>Type PEC</th>
              <th class="text-right">PEC inscr.</th>
              <th class="text-right">PEC mens.</th>
              <th class="text-right">PEC mensuel</th>
              <th class="text-right">PEC annuel</th>
              <th class="text-right">Reste à payer</th>
              <th>Alerte</th>
              <th>Actions</th>
            </tr>
          </ng-template>
          <ng-template pTemplate="body" let-e>
            <tr>
              <td class="mono" style="color:#00d4aa;font-size:11px">{{ e.matricule }}</td>
              <td class="bold">{{ e.nom_complet }}</td>
              <td>{{ e.section_nom }}</td>
              <td>
                <p-tag [value]="pecLabel(e.prise_en_charge)"
                       [severity]="pecSeverity(e.prise_en_charge)" />
              </td>
              <td>
                @if (e.type_pec) {
                  <p-tag [value]="typePecLabel(e.type_pec)"
                         [severity]="typePecSeverity(e.type_pec)" />
                } @else {
                  <span style="color:var(--text-3);font-size:11px">—</span>
                }
              </td>
              <td class="mono text-right">
                {{ e.pec_inscription > 0 ? ((e.pec_inscription | number:'1.0-0') + ' F') : '—' }}
              </td>
              <td class="mono text-right">
                {{ e.pec_mensualite > 0 ? ((e.pec_mensualite | number:'1.0-0') + ' F') : '—' }}
              </td>
              <td class="mono text-right" style="color:#f59e0b">
                {{ e.montant_pec_mensualite_mensuel > 0 ? ((e.montant_pec_mensualite_mensuel | number:'1.0-0') + ' FCFA') : '—' }}
              </td>
              <td class="mono text-right" style="color:#ef4444">
                {{ e.montant_pec_annuel > 0 ? ((e.montant_pec_annuel | number:'1.0-0') + ' FCFA') : '—' }}
              </td>
              <td class="mono text-right" [class.danger]="e.reste_a_payer > 0">
                {{ e.reste_a_payer | number:'1.0-0' }} FCFA
              </td>
              <td>
                <p-tag [value]="alerteLabel(e.niveau_alerte)"
                       [severity]="alerteSeverity(e.niveau_alerte)" />
              </td>
              <td>
                <p-button icon="pi pi-pencil" [rounded]="true" [text]="true"
                          severity="warn" pTooltip="Modifier PEC" (onClick)="ouvrirPriseEnCharge(e)" />
              </td>
            </tr>
          </ng-template>
          <ng-template pTemplate="emptymessage">
            <tr><td colspan="12" class="empty-msg">Aucun élève en prise en charge</td></tr>
          </ng-template>
        </p-table>
      </div>
    }

    <!-- ══════════════════════════ DIALOG FICHE ══════════════════════════ -->
    <p-dialog header="Fiche Élève" [(visible)]="dialogFicheVisible"
              [modal]="true" [style]="{width:'620px'}" [draggable]="false">
      @if (eleveSelectionne()) {
        @let e = eleveSelectionne()!;
        <div class="fiche-grid">
          <div class="fiche-section">
            <div class="fiche-title">Identité</div>
            <div class="fiche-row"><span>Nom complet</span><strong>{{ e.nom_complet }}</strong></div>
            <div class="fiche-row"><span>Matricule</span><strong class="mono" style="color:#00d4aa">{{ e.matricule }}</strong></div>
            <div class="fiche-row"><span>N° interne</span><strong>{{ e.numero }}</strong></div>
            <div class="fiche-row"><span>Genre</span><strong>{{ e.genre === 'F' ? 'Fille' : 'Garçon' }}</strong></div>
            <div class="fiche-row"><span>Date naissance</span><strong>{{ e.date_naissance || '—' }}</strong></div>
            <div class="fiche-row"><span>Lieu naissance</span><strong>{{ e.lieu_naissance || '—' }}</strong></div>
          </div>
          <div class="fiche-section">
            <div class="fiche-title">Scolarité</div>
            <div class="fiche-row"><span>Section</span><strong>{{ e.section_nom }}</strong></div>
            <div class="fiche-row"><span>Statut</span>
              <p-tag [value]="statutLabel(e.statut)" [severity]="statutSeverity(e.statut)" /></div>
            <div class="fiche-row"><span>Date inscription</span><strong>{{ e.date_inscription_libelle || '—' }}</strong></div>
            @if (e.regime === 'PASSAGER') {
              <div class="fiche-row"><span>{{ 'eleves.regime' | translate }}</span>
                <p-tag [value]="('eleves.regime_passager' | translate) + ' — ' + e.nb_mois_passager + ' ' + ('eleves.mois' | translate)"
                       severity="info" /></div>
            }
            @if (e.prise_en_charge || e.pec_inscription > 0 || e.pec_mensualite > 0) {
              <div class="fiche-row"><span>Motif PEC</span>
                <p-tag [value]="pecLabel(e.prise_en_charge)" [severity]="pecSeverity(e.prise_en_charge)" /></div>
              @if (e.pec_inscription > 0) {
                <div class="fiche-row"><span>PEC inscription</span>
                  <strong style="color:#00d4aa">{{ e.pec_inscription | number:'1.0-0' }} FCFA</strong></div>
              }
              @if (e.pec_mensualite > 0) {
                <div class="fiche-row"><span>PEC mensualité</span>
                  <strong style="color:#00d4aa">{{ e.pec_mensualite | number:'1.0-0' }} FCFA / mois</strong></div>
              }
              <div class="fiche-row"><span>PEC annuel</span>
                <strong style="color:#ef4444">{{ e.montant_pec_annuel | number:'1.0-0' }} FCFA</strong></div>
            }
          </div>
          <div class="fiche-section">
            <div class="fiche-title">Parents / Tuteurs</div>
            <div class="fiche-row"><span>Père</span><strong>{{ e.nom_pere || '—' }}</strong></div>
            <div class="fiche-row"><span>Tél. père</span><strong class="mono">{{ e.telephone_pere || '—' }}</strong></div>
            <div class="fiche-row"><span>Mère</span><strong>{{ e.nom_mere || '—' }}</strong></div>
            <div class="fiche-row"><span>Tél. mère</span><strong class="mono">{{ e.telephone_mere || '—' }}</strong></div>
            @if (e.nom_tuteur) {
              <div class="fiche-row"><span>Tuteur</span><strong>{{ e.nom_tuteur }}{{ e.lien_tuteur ? ' (' + e.lien_tuteur + ')' : '' }}</strong></div>
            }
            @if (e.telephone_tuteur) {
              <div class="fiche-row"><span>Tél. tuteur</span><strong class="mono">{{ e.telephone_tuteur }}</strong></div>
            }
          </div>
          <div class="fiche-section">
            <div class="fiche-title">Santé</div>
            <div class="fiche-row"><span>État</span><strong>{{ etatSanteLabel(e.etat_sante) }}</strong></div>
            @if (e.observations_sante) {
              <div class="fiche-row"><span>Observations</span><strong>{{ e.observations_sante }}</strong></div>
            }
          </div>
          <div class="fiche-section">
            <div class="fiche-title">Situation financière</div>
            @if (e.montant_pec_annuel > 0) {
              <div class="fiche-row"><span>Total théorique</span>
                <strong class="mono" style="color:var(--text-3)">{{ e.total_theorique | number:'1.0-0' }} FCFA</strong></div>
              <div class="fiche-row"><span>Prise en charge</span>
                <strong class="mono" style="color:#ef4444">- {{ e.montant_pec_annuel | number:'1.0-0' }} FCFA</strong></div>
            }
            <div class="fiche-row"><span>Total attendu</span><strong class="mono">{{ e.total_attendu | number }} FCFA</strong></div>
            <div class="fiche-row"><span>Total payé</span><strong class="mono success">{{ e.total_paye | number }} FCFA</strong></div>
            <div class="fiche-row"><span>Reste à payer (année en cours)</span>
              <strong class="mono" [class.danger]="e.reste_a_payer > 0" [class.success]="e.reste_a_payer <= 0">
                {{ e.reste_a_payer | number }} FCFA
              </strong>
            </div>
            @if (e.reliquat_anterieur > 0) {
              <div class="fiche-row">
                <span>{{ 'eleves.impaye_anterieur' | translate }}{{ e.reliquat_origine_libelle ? ' (' + e.reliquat_origine_libelle + ')' : '' }}</span>
                <strong class="mono">{{ e.reliquat_anterieur | number }} FCFA</strong></div>
              @if (e.reliquat_paye > 0) {
                <div class="fiche-row"><span>Dont déjà réglé</span>
                  <strong class="mono success">- {{ e.reliquat_paye | number }} FCFA</strong></div>
              }
              <div class="fiche-row"><span>{{ 'eleves.du_global' | translate }}</span>
                <strong class="mono" [class.danger]="e.reste_a_payer_global > 0"
                        [class.success]="e.reste_a_payer_global <= 0">
                  {{ e.reste_a_payer_global | number }} FCFA
                </strong></div>
            }
            <div class="fiche-row"><span>Alerte</span>
              <p-tag [value]="alerteLabel(e.niveau_alerte)" [severity]="alerteSeverity(e.niveau_alerte)" /></div>
          </div>
        </div>
      }
      <ng-template pTemplate="footer">
        <p-button label="Modifier" severity="warn" icon="pi pi-pencil"
                  (onClick)="ouvrirModifier(eleveSelectionne())" />
        <p-button label="Exporter la fiche" severity="info" icon="pi pi-file-pdf"
                  [loading]="exportantFiche()" (onClick)="telechargerFichePDF(eleveSelectionne()!)" />
        <p-button label="Certificat de scolarité" severity="danger" icon="pi pi-file-pdf"
                  (onClick)="genererCertificat(eleveSelectionne())" />
        <p-button label="Situation financière" severity="success" icon="pi pi-wallet"
                  (onClick)="telechargerSituationPDF(eleveSelectionne()!)" />
        <p-button label="Fermer" severity="secondary" (onClick)="dialogFicheVisible=false" />
      </ng-template>
    </p-dialog>

    <!-- ══════════════════════ DIALOG CHANGER STATUT ══════════════════════ -->
    <p-dialog header="Changer le statut" [(visible)]="dialogStatutVisible"
              [modal]="true" [style]="{width:'380px'}" [draggable]="false">
      @if (eleveSelectionne()) {
        <div style="margin-bottom:14px">
          <strong style="color:var(--text)">{{ eleveSelectionne()!.nom_complet }}</strong>
        </div>
        <div class="form-group">
          <label>Nouveau statut</label>
          <p-select appendTo="body" [options]="statutOptions" [(ngModel)]="formStatut"
                    optionLabel="label" optionValue="value" styleClass="w-full" />
        </div>
      }
      <ng-template pTemplate="footer">
        <p-button label="Annuler" severity="secondary" (onClick)="dialogStatutVisible=false" />
        <p-button label="Enregistrer" severity="success" [loading]="saving()" (onClick)="sauvegarderStatut()" />
      </ng-template>
    </p-dialog>

    <!-- ══════════════════════ DIALOG PRISE EN CHARGE ══════════════════════ -->
    <p-dialog header="Prise en charge" [(visible)]="dialogPECVisible"
              [modal]="true" [style]="{width:'520px'}" [draggable]="false">
      @if (eleveSelectionne()) {
        @let e = eleveSelectionne()!;
        <div class="pec-eleve-header">
          <strong>{{ e.nom_complet }}</strong>
          <span>{{ e.section_nom }}</span>
        </div>

        <div class="form-grid">
          <!-- Motif -->
          <div class="form-group full">
            <label>Motif / Catégorie</label>
            <p-select appendTo="body" [options]="categoriesPEC" [(ngModel)]="formPEC.prise_en_charge"
                      optionLabel="label" optionValue="value" styleClass="w-full"
                      placeholder="Aucune prise en charge" [showClear]="true" />
          </div>

          <!-- Montant PEC inscription -->
          <div class="form-group">
            <label>Montant PEC inscription (FCFA)</label>
            <p-inputNumber [(ngModel)]="formPEC.pec_inscription" [min]="0" mode="decimal"
                           styleClass="w-full" placeholder="0" />
          </div>

          <!-- Montant PEC mensualité (par mois) -->
          <div class="form-group">
            <label>Montant PEC mensualité (FCFA / mois)</label>
            <p-inputNumber [(ngModel)]="formPEC.pec_mensualite" [min]="0" mode="decimal"
                           styleClass="w-full" placeholder="0" />
          </div>

          <!-- Observations -->
          <div class="form-group full">
            <label>Observations</label>
            <input pInputText [(ngModel)]="formPEC.obs_prise_en_charge" class="w-full"
                   placeholder="Ex : Orphelin de père, suivi par la commune…" />
          </div>
        </div>

        <!-- Simulation financière -->
        @if (previewPEC()) {
          @let pv = previewPEC()!;
          <div class="pec-preview">
            <div class="pec-preview-title">Simulation impact financier</div>
            <div class="pec-preview-grid">
              @if (pv.inscr > 0) {
                <div class="pv-row">
                  <span>Réduction inscription</span>
                  <strong style="color:#3b82f6">{{ pv.inscr | number:'1.0-0' }} FCFA</strong>
                </div>
              }
              @if (pv.mens > 0) {
                <div class="pv-row">
                  <span>Réduction mensualité</span>
                  <strong style="color:#3b82f6">{{ pv.mens | number:'1.0-0' }} FCFA / mois</strong>
                </div>
              }
              <div class="pv-row highlight">
                <span>Prise en charge annuelle totale</span>
                <strong style="color:#f59e0b">{{ pv.annuel | number:'1.0-0' }} FCFA</strong>
              </div>
              <div class="pv-row">
                <span>Reste à payer par l'élève</span>
                <strong style="color:#10b981">{{ pv.restant | number:'1.0-0' }} FCFA</strong>
              </div>
            </div>
          </div>
        }
      }
      <ng-template pTemplate="footer">
        <p-button label="Annuler" severity="secondary" (onClick)="dialogPECVisible=false" />
        <p-button label="Enregistrer" severity="success" [loading]="saving()" (onClick)="sauvegarderPEC()" />
      </ng-template>
    </p-dialog>

    <!-- Dialog : corriger le déjà payé (reprise migrée) -->
    <p-dialog header="Corriger le déjà payé (reprise)" [(visible)]="dialogRepriseVisible"
              [modal]="true" [style]="{width:'460px'}" [draggable]="false">
      @if (eleveSelectionne()) {
        <div class="pec-eleve-header">
          <strong>{{ eleveSelectionne()!.nom_complet }}</strong>
          <span>{{ eleveSelectionne()!.section_nom }}</span>
        </div>
        <p style="font-size:12px;color:var(--text-3);margin:8px 0">
          Ajuste les montants déjà réglés avant la migration. Le reste à payer se recalcule ;
          le produit réel (706) n'est pas modifié en cas de migration.
        </p>
        <div class="form-grid">
          <div class="form-group full">
            <label>Inscription déjà payée (FCFA)</label>
            <p-inputNumber [(ngModel)]="formReprise.montant_inscription" [min]="0" mode="decimal" styleClass="w-full" />
          </div>
          <div class="form-group full">
            <label>Mensualités déjà payées (FCFA)</label>
            <p-inputNumber [(ngModel)]="formReprise.montant_mensualite" [min]="0" mode="decimal" styleClass="w-full" />
          </div>
          <div class="form-group full">
            <label>Services déjà payés (FCFA)</label>
            <p-inputNumber [(ngModel)]="formReprise.montant_divers" [min]="0" mode="decimal" styleClass="w-full" />
          </div>
        </div>
        <div class="pec-preview">
          <div class="pv-row"><span>Total attendu</span>
            <strong>{{ formReprise.total_attendu | number:'1.0-0' }} FCFA</strong></div>
          <div class="pv-row"><span>Déjà payé (saisi)</span>
            <strong style="color:#00d4aa">{{ (formReprise.montant_inscription + formReprise.montant_mensualite + formReprise.montant_divers) | number:'1.0-0' }} FCFA</strong></div>
          <div class="pv-row"><span>Reste à payer (estimé)</span>
            <strong style="color:#ef4444">{{ (formReprise.total_attendu - (formReprise.montant_inscription + formReprise.montant_mensualite + formReprise.montant_divers)) | number:'1.0-0' }} FCFA</strong></div>
        </div>
      }
      <ng-template pTemplate="footer">
        <p-button label="Annuler" severity="secondary" (onClick)="dialogRepriseVisible=false" />
        <p-button label="Enregistrer" severity="success" [loading]="saving()" (onClick)="sauvegarderReprise()" />
      </ng-template>
    </p-dialog>

    <!-- ══════════════════════ DIALOG NOUVEL ÉLÈVE ══════════════════════ -->
    <p-dialog [header]="(editId ? 'eleves.modifier' : 'eleves.nouveau') | translate" [(visible)]="dialogVisible"
              [modal]="true" [style]="{width:'480px'}" [draggable]="false">
      <div class="form-grid">
        <div class="form-group full">
          <label>{{ 'eleves.nom_complet' | translate }} *</label>
          <input pInputText [(ngModel)]="nouvelEleve.nom_complet" class="w-full" />
        </div>
        <div class="form-group">
          <label>{{ 'eleves.section' | translate }} *</label>
          <p-select appendTo="body" [options]="sections()" [(ngModel)]="nouvelEleve.section"
                    optionLabel="nom" optionValue="id" (onChange)="onSectionChange()"
                    [placeholder]="'eleves.choisir' | translate" styleClass="w-full" />
        </div>
        @if (classesSection().length) {
          <div class="form-group">
            <label>{{ 'eleves.classe' | translate }} *</label>
            <p-select appendTo="body" [options]="classesSection()" [(ngModel)]="nouvelEleve.classe"
                      optionLabel="nom" optionValue="id"
                      [placeholder]="'eleves.choisir' | translate" styleClass="w-full" />
          </div>
        }
        <div class="form-group">
          <label>{{ 'eleves.genre' | translate }} *</label>
          <p-select appendTo="body" [options]="genreOptions" [(ngModel)]="nouvelEleve.genre"
                    optionLabel="label" optionValue="value" styleClass="w-full" />
        </div>
        <div class="form-group">
          <label>{{ 'eleves.date_naissance' | translate }} *</label>
          <input pInputText type="date" [(ngModel)]="nouvelEleve.date_naissance" class="w-full" />
        </div>
        <div class="form-group">
          <label>{{ 'eleves.date_entree' | translate }} *</label>
          @if (jourInconnu) {
            <input pInputText type="month" [(ngModel)]="moisInscription" (ngModelChange)="onMoisChange()" class="w-full" />
          } @else {
            <input pInputText type="date" [(ngModel)]="nouvelEleve.date_inscription" class="w-full" />
          }
          <label class="chk-jour">
            <input type="checkbox" [(ngModel)]="jourInconnu" (ngModelChange)="onJourInconnuChange()" />
            {{ 'eleves.jour_inconnu' | translate }}
          </label>
          <small style="color:var(--text-3);font-size:10px">{{ 'eleves.date_entree_aide' | translate }}</small>
        </div>
        <!-- Daara : type de ndongo (permanent = exercice / passager = durée en mois) -->
        @if (estDaara()) {
          <div class="form-group">
            <label>{{ 'eleves.regime' | translate }} *</label>
            <p-select appendTo="body" [options]="regimeOptions" [(ngModel)]="nouvelEleve.regime"
                      optionLabel="label" optionValue="value" styleClass="w-full" />
          </div>
          @if (nouvelEleve.regime === 'PASSAGER') {
            <div class="form-group">
              <label>{{ 'eleves.nb_mois' | translate }} *</label>
              <p-inputNumber [(ngModel)]="nouvelEleve.nb_mois_passager" [min]="1" [max]="36"
                             [showButtons]="true" styleClass="w-full" inputStyleClass="w-full" />
              <small style="color:var(--text-3);font-size:10px">{{ 'eleves.nb_mois_aide' | translate }}</small>
            </div>
          }
        }
        <div class="form-group">
          <label>{{ 'eleves.lieu_naissance' | translate }} *</label>
          <input pInputText [(ngModel)]="nouvelEleve.lieu_naissance" class="w-full"
                 [placeholder]="'eleves.lieu_naissance_ph' | translate" />
        </div>
        <div class="form-group full" style="margin-top:2px">
          <small style="color:var(--text-3);font-size:11px">⚑ {{ 'eleves.parent_obligatoire' | translate }}</small>
        </div>
        <div class="form-group">
          <label>{{ 'eleves.nom_pere' | translate }}</label>
          <input pInputText [(ngModel)]="nouvelEleve.nom_pere" class="w-full"
                 [placeholder]="'eleves.nom_pere_ph' | translate" />
        </div>
        <div class="form-group">
          <label>{{ 'eleves.telephone_pere' | translate }}</label>
          <input pInputText [(ngModel)]="nouvelEleve.telephone_pere" class="w-full" placeholder="7X XXX XX XX" />
        </div>
        <div class="form-group">
          <label>{{ 'eleves.nom_mere' | translate }}</label>
          <input pInputText [(ngModel)]="nouvelEleve.nom_mere" class="w-full"
                 [placeholder]="'eleves.nom_mere_ph' | translate" />
        </div>
        <div class="form-group">
          <label>{{ 'eleves.telephone_mere' | translate }}</label>
          <input pInputText [(ngModel)]="nouvelEleve.telephone_mere" class="w-full" placeholder="7X XXX XX XX" />
        </div>
        <div class="form-group">
          <label>{{ 'eleves.nom_tuteur' | translate }}</label>
          <input pInputText [(ngModel)]="nouvelEleve.nom_tuteur" class="w-full"
                 [placeholder]="'eleves.nom_tuteur_ph' | translate" />
        </div>
        <div class="form-group">
          <label>{{ 'eleves.telephone_tuteur' | translate }}</label>
          <input pInputText [(ngModel)]="nouvelEleve.telephone_tuteur" class="w-full" placeholder="7X XXX XX XX" />
        </div>
        <div class="form-group">
          <label>{{ 'eleves.lien_tuteur' | translate }}</label>
          <input pInputText [(ngModel)]="nouvelEleve.lien_tuteur" class="w-full"
                 [placeholder]="'eleves.lien_tuteur_ph' | translate" />
        </div>
        <div class="form-group">
          <label>{{ 'eleves.etat_sante' | translate }}</label>
          <p-select appendTo="body" [options]="santeOptions" [(ngModel)]="nouvelEleve.etat_sante"
                    optionLabel="label" optionValue="value" styleClass="w-full" />
        </div>
        <div class="form-group full">
          <label>{{ 'eleves.observations_sante' | translate }}</label>
          <textarea [(ngModel)]="nouvelEleve.observations_sante" rows="2" class="w-full ta-sante"
                    [placeholder]="'eleves.observations_sante_ph' | translate"></textarea>
        </div>
        <div class="form-group full" *ngIf="servicesActifs().length">
          <label>{{ 'eleves.services' | translate }}</label>
          <p-multiSelect appendTo="body" [options]="servicesActifs()" [(ngModel)]="nouvelEleve.abonnements"
                         optionLabel="nom" optionValue="id" display="chip"
                         [placeholder]="'eleves.services_ph' | translate" styleClass="w-full" />
        </div>
        <!-- Ardoise des années d'avant : montant global, sans justification par
             poste — c'est ce que les écoles savent donner à la migration. -->
        <div class="form-group">
          <label>{{ 'eleves.impaye_anterieur' | translate }}</label>
          <p-inputNumber [(ngModel)]="nouvelEleve.reliquat_anterieur" [min]="0" [step]="1000"
                         suffix=" FCFA" styleClass="w-full" inputStyleClass="w-full" />
        </div>
        <div class="form-group">
          <label>{{ 'eleves.impaye_origine' | translate }}</label>
          <input pInputText [(ngModel)]="nouvelEleve.reliquat_note" class="w-full" maxlength="120"
                 [placeholder]="'eleves.impaye_origine_ph' | translate" />
        </div>
        <div class="form-group full" style="margin-top:-4px">
          <small style="color:var(--text-3);font-size:11px">{{ 'eleves.impaye_anterieur_aide' | translate }}</small>
        </div>
      </div>
      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler'    | translate" severity="secondary" (onClick)="dialogVisible=false" />
        <p-button [label]="'common.enregistrer'| translate" severity="success" [loading]="saving()" (onClick)="sauvegarder()" />
      </ng-template>
    </p-dialog>

    <!-- ═══════════ SAISIE EN LOT DES IMPAYÉS ANTÉRIEURS (migration) ═══════════ -->
    <p-dialog [header]="'eleves.saisie_impayes_titre' | translate" [(visible)]="dialogImpayesVisible"
              [modal]="true" [style]="{width:'900px'}" [draggable]="false">
      <p style="font-size:12px;color:var(--text-2);margin:0 0 12px">
        {{ 'eleves.saisie_impayes_aide' | translate }}
      </p>
      <div class="filters-bar" style="margin-bottom:10px">
        <input pInputText [(ngModel)]="rechercheImpaye" class="search-input"
               [placeholder]="'eleves.rechercher' | translate" />
        <span class="impayes-total">
          {{ 'eleves.saisie_impayes_total' | translate:{
               n: lignesImpayesSaisies(), montant: (totalImpayesSaisi() | number:'1.0-0') } }}
        </span>
      </div>
      <p-table [value]="lignesImpayesFiltrees()" [loading]="chargementImpayes()"
               styleClass="p-datatable-sm" [scrollable]="true" scrollHeight="46vh">
        <ng-template pTemplate="header">
          <tr>
            <th style="width:130px">{{ 'eleves.matricule' | translate }}</th>
            <th>{{ 'eleves.nom_complet' | translate }}</th>
            <th style="width:120px">{{ 'eleves.section' | translate }}</th>
            <th style="width:150px">{{ 'eleves.impaye_anterieur' | translate }}</th>
            <th style="width:200px">{{ 'eleves.impaye_origine' | translate }}</th>
          </tr>
        </ng-template>
        <ng-template pTemplate="body" let-l>
          <tr>
            <td class="mono" style="font-size:11px;color:#00d4aa">{{ l.matricule || '—' }}</td>
            <td class="bold">{{ l.nom_complet }}</td>
            <td>{{ l.section }}</td>
            <td>
              <p-inputNumber [(ngModel)]="l.montant" [min]="0" [step]="1000"
                             styleClass="w-full" inputStyleClass="w-full" />
            </td>
            <td>
              <input pInputText [(ngModel)]="l.note" class="w-full" maxlength="120"
                     [placeholder]="'eleves.impaye_origine_ph' | translate" />
            </td>
          </tr>
        </ng-template>
      </p-table>
      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler' | translate" severity="secondary"
                  (onClick)="dialogImpayesVisible=false" />
        <p-button [label]="'common.enregistrer' | translate" severity="success"
                  [loading]="sauvegardeImpayes()" (onClick)="enregistrerImpayes()" />
      </ng-template>
    </p-dialog>

    <!-- Dialog services / activités d'un élève -->
    <p-dialog [header]="'🔖 ' + ('eleves.services' | translate)" [(visible)]="dialogServicesVisible"
              [modal]="true" [style]="{width:'440px'}" [draggable]="false">
      <div *ngIf="eleveSelectionne() as e">
        <div style="font-size:13px;color:var(--text-2);margin-bottom:14px">
          <strong style="color:var(--text)">{{ e.nom_complet }}</strong> — {{ e.section_nom }}
        </div>
        <div class="form-group" *ngIf="servicesActifs().length; else aucunService">
          <label>{{ 'eleves.services_choix' | translate }}</label>
          <p-multiSelect appendTo="body" [options]="servicesActifs()" [(ngModel)]="formServices" display="chip"
                         optionLabel="nom" optionValue="id"
                         [placeholder]="'eleves.services_ph' | translate" styleClass="w-full" />
        </div>
        <ng-template #aucunService>
          <div style="color:var(--text-3);font-size:13px">{{ 'eleves.services_aucun' | translate }}</div>
        </ng-template>
      </div>
      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler' | translate" severity="secondary" (onClick)="dialogServicesVisible=false" />
        <p-button [label]="'common.enregistrer' | translate" severity="success" [loading]="saving()" (onClick)="sauvegarderServices()" />
      </ng-template>
    </p-dialog>

    <!-- ════════════════════ DIALOG IMPORT EXCEL ════════════════════ -->
    <app-import-eleves-dialog [(visible)]="dialogImportVisible" (importe)="chargerEleves()" />
  `,
  styles: [`
    .page-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:16px; }
    .page-title  { font-size:20px; font-weight:600; color:var(--text); margin:0 0 4px; }
    .page-sub    { font-size:12px; color:var(--text-3); }

    .kpi-row { display:flex; gap:10px; flex-wrap:wrap; }
    .kpi-mini { background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:10px 14px;
                text-align:center; cursor:pointer; min-width:90px; }
    .kpi-mini:hover { border-color:#00d4aa; }
    .kpi-mini.success { border-color:#10b981; }
    .kpi-mini.danger  { border-color:#ef4444; }
    .kpi-mini.warn    { border-color:#f59e0b; }
    .kpi-mini.info    { border-color:#0099ff; }
    .km-val   { display:block; font-size:22px; font-weight:700; color:var(--text); font-family:monospace; }
    .km-label { display:block; font-size:10px; color:var(--text-3); text-transform:uppercase; margin-top:2px; }

    /* Panel stats financières */
    .stats-panel { background:var(--surface-2); border:1px solid var(--border); border-radius:10px;
                   padding:14px 18px; margin-bottom:14px; }
    .stats-panel-title { font-size:11px; font-weight:700; color:#00d4aa; text-transform:uppercase;
                         letter-spacing:.5px; margin-bottom:12px; }
    .stats-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }
    .stat-item { background:var(--surface); border-radius:8px; padding:10px 12px; }
    .stat-label { display:block; font-size:10px; color:var(--text-3); text-transform:uppercase;
                  letter-spacing:.3px; margin-bottom:4px; }
    .stat-val { display:block; font-size:15px; font-weight:700; color:var(--text); font-family:monospace; }
    .stat-val.success { color:#10b981; }
    .stat-val.danger  { color:#ef4444; }
    .stat-val.warn    { color:#f59e0b; }

    .filters-bar { display:flex; gap:12px; margin-bottom:16px; }
    .search-input { flex:1; }
    .ta-sante { padding:8px 10px; border-radius:8px; border:1px solid var(--p-inputtext-border-color,#334155);
                background:var(--p-inputtext-background,#1e293b); color:inherit; font:inherit; resize:vertical; }
    .chk-jour { display:flex; align-items:center; gap:6px; margin-top:6px;
                font-weight:400; font-size:12px; color:var(--text-2); cursor:pointer; }
    .chk-jour input { width:auto; margin:0; }
    .ex-select { background:var(--surface); color:var(--text); border:1px solid var(--border); border-radius:8px; padding:8px 10px; font-size:13px; cursor:pointer; }
    .ex-select:hover { border-color:#00d4aa; }
    .readonly-banner-el { background:rgba(240,192,64,0.1); border:1px solid rgba(240,192,64,0.35); color:#f0c040; border-radius:8px; padding:8px 14px; font-size:13px; margin-bottom:16px; }

    .alerte-aide { margin-bottom:14px; }
    .aide-toggle { background:none; border:none; color:var(--text-2); font-size:12px; cursor:pointer; padding:2px 0; }
    .aide-toggle:hover { color:var(--text); }
    .aide-corps { display:flex; flex-wrap:wrap; gap:18px; margin-top:8px; padding:12px 14px;
                  background:var(--surface-2); border:1px solid var(--border); border-radius:8px;
                  font-size:12px; color:var(--text-2); }
    .aide-corps span { display:inline-flex; align-items:center; gap:6px; }
    ::ng-deep .filter-drop { min-width:160px; }

    .table-card { background:var(--surface); border:1px solid var(--border); border-radius:12px; overflow:hidden; }
    .table-toolbar { display:flex; justify-content:space-between; align-items:center;
                     padding:12px 16px; border-bottom:1px solid var(--border); }
    .tbl-count { color:var(--text); font-weight:600; font-size:13px; }

    ::ng-deep .p-datatable .p-datatable-thead > tr > th {
      background:var(--surface-2) !important; color:var(--text-3) !important;
      font-size:11px !important; text-transform:uppercase !important; border-color:var(--border) !important;
    }
    ::ng-deep .p-datatable .p-datatable-tbody > tr {
      background:var(--surface) !important; color:var(--text-2) !important;
      border-bottom:1px solid rgba(42,63,95,0.4) !important;
    }
    ::ng-deep .p-datatable .p-datatable-tbody > tr:hover { background:var(--surface-hover) !important; }

    .mono    { font-family:monospace; font-size:12px; }
    .bold    { font-weight:600; color:var(--text); }
    /* Dette d'une année antérieure — orange, distinct du rouge « en retard
       cette année » pour qu'on lise d'où vient l'impayé. */
    .reliquat-badge { display:inline-block; font-family:monospace; font-size:11px; font-weight:600;
                      color:#f97316; background:rgba(249,115,22,0.12);
                      border:1px solid rgba(249,115,22,0.35); border-radius:6px; padding:2px 7px; }
    .success { color:#10b981; }
    .danger  { color:#ef4444; }
    .empty-msg { text-align:center; padding:40px; color:var(--text-3); }
    .btn-row { display:flex; gap:2px; }
    .text-right { text-align:right; }

    /* Fiche */
    .fiche-grid { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
    .fiche-section { background:var(--surface-2); border-radius:8px; padding:12px; }
    .fiche-title { font-size:11px; font-weight:700; color:#00d4aa; text-transform:uppercase;
                   margin-bottom:8px; letter-spacing:.5px; }
    .fiche-row { display:flex; justify-content:space-between; align-items:center; padding:4px 0;
                 border-bottom:1px solid rgba(42,63,95,0.3); font-size:11px; }
    .fiche-row span { color:var(--text-3); }
    .fiche-row strong { color:var(--text); }

    /* Formulaires */
    .form-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
    .form-group { display:flex; flex-direction:column; gap:5px; }
    .form-group.full { grid-column:1/-1; }
    .form-group label { font-size:11px; color:var(--text-2); text-transform:uppercase; letter-spacing:.3px; }
    .w-full { width:100%; }

    /* Saisie en lot des impayés antérieurs */
    .impayes-total { margin-left:auto; font-size:12px; font-weight:600; color:#f97316;
                     white-space:nowrap; }

    /* Dialog PEC */
    .pec-eleve-header { display:flex; align-items:center; gap:10px; margin-bottom:16px;
                        padding:10px 14px; background:var(--surface-2); border-radius:8px; }
    .pec-eleve-header strong { color:var(--text); font-size:14px; }
    .pec-eleve-header span { color:var(--text-3); font-size:12px; }

    .pec-preview { background:var(--surface-2); border:1px solid var(--border); border-radius:8px;
                   padding:14px; margin-top:16px; }
    .pec-preview-title { font-size:10px; font-weight:700; color:#00d4aa; text-transform:uppercase;
                         letter-spacing:.5px; margin-bottom:10px; }
    .pec-preview-grid { display:flex; flex-direction:column; gap:6px; }
    .pv-row { display:flex; justify-content:space-between; align-items:center;
              padding:5px 0; border-bottom:1px solid rgba(42,63,95,0.3); font-size:12px; }
    .pv-row span { color:var(--text-2); }
    .pv-row.highlight { border-top:1px solid var(--border); margin-top:4px; padding-top:8px;
                        border-bottom:none; }
  `]
})
export class ElevesListeComponent implements OnInit {
  private translate     = inject(TranslateService);
  private elevesService = inject(ElevesService);
  private msg           = inject(MessageService);
  private auth          = inject(AuthService);

  // Licence Taxawu Daara : les ndongos peuvent être « passagers » (durée en mois)
  estDaara(): boolean {
    return this.auth.currentUser()?.type_licence === 'TAXAWU_DAARA';
  }

  eleves        = signal<Eleve[]>([]);
  elevesFiltres = signal<Eleve[]>([]);
  sections      = signal<any[]>([]);
  classes       = signal<any[]>([]);
  statsPEC      = signal<PriseEnChargeStats | null>(null);
  loading       = signal(true);
  saving        = signal(false);
  exportant     = signal(false);
  exportantFiche = signal(false);
  onglet        = signal<'liste' | 'prise_en_charge'>('liste');

  dialogVisible        = false;
  dialogImportVisible  = false;
  dialogFicheVisible   = false;
  dialogStatutVisible  = false;
  dialogPECVisible     = false;
  dialogServicesVisible = false;
  eleveSelectionne    = signal<Eleve | null>(null);

  // Saisie en lot des impayés antérieurs (migration). Les lignes sont un
  // tableau simple : ngModel écrit directement dedans, et la CD par défaut
  // suffit à rafraîchir les totaux.
  dialogImpayesVisible = false;
  chargementImpayes    = signal(false);
  sauvegardeImpayes    = signal(false);
  lignesImpayes: LigneImpayeEditable[] = [];
  rechercheImpaye      = '';

  services       = signal<Service[]>([]);
  servicesActifs = computed(() => this.services().filter(s => s.actif));
  formServices: string[] = [];

  recherche    = '';
  filtreAlerte = '';
  filtreStatut = '';
  filtreReliquat = false;
  tri          = 'numero';
  // Date d'entrée : jour inconnu → on ne saisit que le mois (input type=month,
  // valeur AAAA-MM), stocké au 1er du mois avec le drapeau jour_estime.
  jourInconnu     = false;
  moisInscription = '';
  // Sélecteur d'exercice : '' = année active ; sinon id d'un exercice (clôturé
  // = consultation/fiches en lecture seule, création d'élève désactivée).
  exercices    = signal<any[]>([]);
  exerciceSel  = '';
  estAnneeCloturee(): boolean {
    return !!this.exercices().find((e: any) => e.id === this.exerciceSel)?.cloture;
  }
  formStatut   = 'INSCRIT';
  formPEC: PecForm = this.pecFormVide();

  elevesPEC = computed(() =>
    this.eleves().filter(e => e.prise_en_charge || e.pec_inscription > 0 || e.pec_mensualite > 0)
  );

  previewPEC = computed(() => {
    const eleve = this.eleveSelectionne();
    const form  = this.formPEC;
    if (!eleve) return null;
    const section = this.sections().find(s => s.id === eleve.section);
    if (!section) return null;
    // Montants directs, plafonnés aux frais.
    const inscr = Math.min(form.pec_inscription || 0, section.frais_inscription);
    const mens  = Math.min(form.pec_mensualite  || 0, section.frais_mensualite);
    if (!inscr && !mens) return null;
    const annuel  = inscr + mens * 10;
    const restant = Math.max((section.total_annuel || 0) - annuel, 0);
    return { inscr, mens, annuel, restant };
  });

  nouvelEleve: Partial<Eleve> = {};
  editId: string | null = null;
  legendeVisible = false;

  tris = [
    { label: 'Tri : Matricule',        value: 'numero' },
    { label: 'Tri : Nom (A → Z)',      value: 'nom' },
    { label: 'Tri : Nom (Z → A)',      value: 'nom_desc' },
    { label: 'Tri : Arrivée (récent)', value: 'arrivee_recent' },
    { label: 'Tri : Arrivée (ancien)', value: 'arrivee_ancien' },
    { label: 'Tri : Classe',           value: 'classe' },
  ];
  filtresAlerte = [
    { label: 'Toutes alertes', value: '' },
    { label: 'CRITIQUE',       value: 'CRITIQUE' },
    { label: 'URGENT',         value: 'URGENT' },
    { label: 'ATTENTION',      value: 'ATTENTION' },
    { label: 'OK',             value: 'OK' },
    { label: 'A JOUR',         value: 'A_JOUR' },
  ];
  filtresStatut = [
    { label: 'Tous statuts',  value: '' },
    { label: 'Inscrit',       value: 'INSCRIT' },
    { label: 'Abandonné',     value: 'ABANDONNE' },
    { label: 'Transféré',     value: 'TRANSFERE' },
    { label: 'Diplômé',       value: 'DIPLOME' },
  ];
  statutOptions = [
    { label: 'Inscrit',   value: 'INSCRIT' },
    { label: 'Abandonné', value: 'ABANDONNE' },
    { label: 'Transféré', value: 'TRANSFERE' },
    { label: 'Diplômé',   value: 'DIPLOME' },
  ];
  categoriesPEC = [
    { label: 'Orphelin',        value: 'ORPHELIN' },
    { label: 'Handicap',        value: 'HANDICAP' },
    { label: 'Famille démunie', value: 'FAMILLE_DEMUNIE' },
    { label: 'Autre',           value: 'AUTRE' },
  ];
  typesPEC = [
    { label: "Frais d'inscription uniquement", value: 'INSCRIPTION' },
    { label: 'Mensualités uniquement',          value: 'MENSUALITES' },
    { label: 'Prise en charge totale',          value: 'TOTALE' },
  ];
  genreOptions = [
    { label: 'Garçon', value: 'G' },
    { label: 'Fille',  value: 'F' },
  ];
  get regimeOptions() {
    return [
      { label: this.translate.instant('eleves.regime_permanent'), value: 'EXERCICE' },
      { label: this.translate.instant('eleves.regime_passager'),  value: 'PASSAGER' },
    ];
  }
  get santeOptions() {
    return [
      { label: this.translate.instant('eleves.sante_sain'),      value: 'SAIN' },
      { label: this.translate.instant('eleves.sante_suivi'),     value: 'SUIVI' },
      { label: this.translate.instant('eleves.sante_chronique'), value: 'CHRONIQUE' },
    ];
  }

  ngOnInit() {
    this.chargerEleves();
    this.chargerSections();
    this.chargerServices();
    this.chargerClasses();
    this.elevesService.getExercices().subscribe({
      next: (r: any) => this.exercices.set(r?.results || r || []),
      error: () => {},
    });
  }

  chargerClasses() {
    this.elevesService.getClasses().subscribe({
      next: res => this.classes.set((res as any).results || res || []),
    });
  }

  // Classes de la section sélectionnée (les classes ont niveau_nom = nom de la section).
  // Méthode (pas computed) car nouvelEleve.section n'est pas un signal.
  classesSection(): any[] {
    const secNom = this.sections().find(s => s.id === this.nouvelEleve.section)?.nom;
    if (!secNom) return [];
    return this.classes().filter(c => c.niveau_nom === secNom);
  }

  onSectionChange() {
    // Réinitialise la classe ; pré-sélectionne si la section n'a qu'une classe
    const cs = this.classesSection();
    this.nouvelEleve.classe = cs.length === 1 ? cs[0].id : undefined;
  }

  chargerServices() {
    this.elevesService.getServices().subscribe({
      next: res => this.services.set(((res as any).results || res || []).map((s: any) => ({ ...s, montant: +s.montant })))
    });
  }

  ouvrirServices(eleve: Eleve) {
    this.eleveSelectionne.set(eleve);
    this.formServices = [...(eleve.abonnements || [])];
    this.dialogServicesVisible = true;
  }

  sauvegarderServices() {
    const e = this.eleveSelectionne();
    if (!e) return;
    this.saving.set(true);
    this.elevesService.updateEleve(e.id, { abonnements: this.formServices } as any).subscribe({
      next: () => {
        this.msg.add({ severity: 'success', summary: this.translate.instant('common.succes'), detail: e.nom_complet });
        this.dialogServicesVisible = false;
        this.saving.set(false);
        this.chargerEleves();
      },
      error: () => this.saving.set(false),
    });
  }

  basculerOnglet() {
    const next = this.onglet() === 'liste' ? 'prise_en_charge' : 'liste';
    this.onglet.set(next);
    if (next === 'prise_en_charge' && !this.statsPEC()) {
      this.chargerStatsPEC();
    }
  }

  changerExercice() {
    this.chargerEleves();
  }

  chargerEleves() {
    this.loading.set(true);
    const params = this.exerciceSel ? { exercice: this.exerciceSel } : undefined;
    this.elevesService.getEleves(params).subscribe({
      next: res => {
        const data = Array.isArray(res) ? res : ((res as any).results || []);
        this.eleves.set(data);
        this.elevesFiltres.set(this.trier(data));
        this.loading.set(false);
      },
      error: () => this.loading.set(false)
    });
  }

  chargerSections() {
    this.elevesService.getSections().subscribe({
      next: res => this.sections.set((res as any).results || [])
    });
  }

  chargerStatsPEC() {
    this.elevesService.getPriseEnChargeStats().subscribe({
      next: stats => this.statsPEC.set(stats),
      error: ()   => {}
    });
  }

  filtrer() {
    let data = this.eleves();
    if (this.recherche)    data = data.filter(e => e.nom_complet.toLowerCase().includes(this.recherche.toLowerCase()));
    if (this.filtreAlerte) data = data.filter(e => e.niveau_alerte === this.filtreAlerte as NiveauAlerte);
    if (this.filtreStatut) data = data.filter(e => e.statut === this.filtreStatut);
    if (this.filtreReliquat) data = data.filter(e => (e.reliquat_restant || 0) > 0);
    this.elevesFiltres.set(this.trier(data));
  }

  // Tri côté client : on copie avant de trier pour ne pas muter le tableau
  // du signal source (this.eleves()).
  private trier(data: Eleve[]): Eleve[] {
    const parNom  = (a: Eleve, b: Eleve) =>
      (a.nom_complet || '').localeCompare(b.nom_complet || '', 'fr', { sensitivity: 'base' });
    const parDate = (a: Eleve, b: Eleve) =>
      (a.date_inscription || '').localeCompare(b.date_inscription || '');
    const copie = [...data];
    switch (this.tri) {
      case 'nom':            return copie.sort(parNom);
      case 'nom_desc':       return copie.sort((a, b) => parNom(b, a));
      case 'arrivee_ancien': return copie.sort(parDate);
      case 'arrivee_recent': return copie.sort((a, b) => parDate(b, a));
      case 'classe':         return copie.sort((a, b) =>
        (a.classe_nom || '').localeCompare(b.classe_nom || '', 'fr', { sensitivity: 'base' }) || parNom(a, b));
      default:               return copie.sort((a, b) => a.numero - b.numero);
    }
  }

  countStatut(s: string)      { return this.eleves().filter(e => e.statut === s).length; }
  countGenre(g: string)       { return this.eleves().filter(e => e.genre === g).length; }

  // Dettes antérieures encore ouvertes — recalculées à chaque chargement.
  nbAvecReliquat = computed(() => this.eleves().filter(e => (e.reliquat_restant || 0) > 0).length);
  totalReliquat  = computed(() =>
    this.eleves().reduce((s, e) => s + (e.reliquat_restant || 0), 0));
  countTypePEC(t: TypePEC)    { return this.elevesPEC().filter(e => e.type_pec === t).length; }

  /** Décomposition du dû global, affichée au survol de la colonne. */
  detailDu(e: Eleve): string {
    return this.translate.instant('eleves.du_detail', {
      annee:     (e.reste_a_payer || 0).toLocaleString('fr-FR'),
      anterieur: (e.reliquat_restant || 0).toLocaleString('fr-FR'),
    });
  }

  // ── Saisie en lot des impayés antérieurs ────────────────────────────────
  ouvrirSaisieImpayes() {
    this.dialogImpayesVisible = true;
    this.rechercheImpaye = '';
    this.chargementImpayes.set(true);
    this.elevesService.getImpayesAnterieurs().subscribe({
      next: r => {
        // montant0/note0 = valeur d'origine, pour ne renvoyer que ce qui bouge.
        this.lignesImpayes = r.lignes.map(l => ({
          ...l, montant0: l.montant || 0, note0: l.note || '' }));
        this.chargementImpayes.set(false);
      },
      error: () => {
        this.chargementImpayes.set(false);
        this.msg.add({ severity: 'error', summary: this.translate.instant('common.erreur'),
                       detail: this.translate.instant('eleves.saisie_impayes_titre') });
      },
    });
  }

  lignesImpayesFiltrees(): LigneImpayeEditable[] {
    const q = this.rechercheImpaye.trim().toLowerCase();
    if (!q) return this.lignesImpayes;
    return this.lignesImpayes.filter(l =>
      l.nom_complet.toLowerCase().includes(q) || (l.matricule || '').toLowerCase().includes(q));
  }
  lignesImpayesSaisies(): number {
    return this.lignesImpayes.filter(l => (l.montant || 0) > 0).length;
  }
  totalImpayesSaisi(): number {
    return this.lignesImpayes.reduce((s, l) => s + (l.montant || 0), 0);
  }

  enregistrerImpayes() {
    // N'envoyer que ce qui a changé : sur 300 élèves, rejouer les lignes
    // intactes réécrirait autant d'écritures pour rien.
    const lignes = this.lignesImpayes
      .filter(l => (l.montant || 0) !== l.montant0 || (l.note || '') !== l.note0)
      .map(l => ({ eleve_id: l.eleve_id, montant: l.montant || 0, note: l.note || '' }));
    if (!lignes.length) { this.dialogImpayesVisible = false; return; }

    this.sauvegardeImpayes.set(true);
    this.elevesService.enregistrerImpayesAnterieurs(lignes).subscribe({
      next: r => {
        this.sauvegardeImpayes.set(false);
        this.dialogImpayesVisible = false;
        this.msg.add({ severity: r.nb_refuses ? 'warn' : 'success',
                       summary: this.translate.instant('common.succes'),
                       detail: this.translate.instant('eleves.saisie_impayes_ok', { n: r.nb_appliques })
                             + (r.nb_refuses
                                ? ' ' + this.translate.instant('eleves.saisie_impayes_refus', { n: r.nb_refuses })
                                : ''),
                       life: r.nb_refuses ? 8000 : 4000 });
        // Les refus sont détaillés : ils portent le motif exact (montant sous le
        // déjà encaissé, exercice clôturé…), sans quoi l'école corrige à l'aveugle.
        for (const refus of (r.refuses || []).slice(0, 5)) {
          this.msg.add({ severity: 'error', summary: refus.nom_complet || '—',
                         detail: refus.motif, life: 8000 });
        }
        this.chargerEleves();
      },
      error: (err) => {
        this.sauvegardeImpayes.set(false);
        this.msg.add({ severity: 'error', summary: this.translate.instant('common.erreur'),
                       detail: err?.error?.error || 'Enregistrement impossible' });
      },
    });
  }

  alerteLabel(a: NiveauAlerte | string): string {
    return { CRITIQUE: 'CRITIQUE', URGENT: 'URGENT', ATTENTION: 'ATTENTION', OK: 'OK', A_JOUR: 'A JOUR' }[a] || a;
  }
  alerteSeverity(a: NiveauAlerte | string): 'danger' | 'warn' | 'success' | 'secondary' {
    return ({ CRITIQUE:'danger', URGENT:'danger', ATTENTION:'warn', OK:'success', A_JOUR:'success' } as any)[a] || 'secondary';
  }
  statutLabel(s: string) {
    return { INSCRIT:'Inscrit', ABANDONNE:'Abandonné', TRANSFERE:'Transféré', DIPLOME:'Diplômé' }[s] || s;
  }
  etatSanteLabel(s: string | undefined): string {
    const cle = { SAIN:'eleves.sante_sain', SUIVI:'eleves.sante_suivi', CHRONIQUE:'eleves.sante_chronique' }[s || 'SAIN'];
    return cle ? this.translate.instant(cle) : (s || '—');
  }
  statutSeverity(s: string): 'success' | 'danger' | 'warn' | 'info' | 'secondary' {
    return ({ INSCRIT:'success', ABANDONNE:'danger', TRANSFERE:'warn', DIPLOME:'info' } as any)[s] || 'secondary';
  }
  pecLabel(c: string | null): string {
    return { ORPHELIN:'Orphelin', HANDICAP:'Handicap', FAMILLE_DEMUNIE:'Fam. démunie', AUTRE:'Autre' }[c || ''] || (c || '—');
  }
  pecSeverity(c: string | null): 'danger' | 'warn' | 'info' | 'secondary' {
    return ({ ORPHELIN:'danger', HANDICAP:'warn', FAMILLE_DEMUNIE:'info', AUTRE:'secondary' } as any)[c || ''] || 'secondary';
  }
  typePecLabel(t: TypePEC | null): string {
    return ({ INSCRIPTION:'Inscription', MENSUALITES:'Mensualités', TOTALE:'Totale' } as any)[t || ''] || (t || '—');
  }
  typePecSeverity(t: TypePEC | null): 'info' | 'success' | 'warn' | 'secondary' {
    return ({ INSCRIPTION:'info', MENSUALITES:'success', TOTALE:'warn' } as any)[t || ''] || 'secondary';
  }

  voirFiche(eleve: Eleve) {
    this.eleveSelectionne.set(eleve);
    this.dialogFicheVisible = true;
  }

  genererCertificat(eleve: Eleve | null) {
    if (!eleve?.id) return;
    this.elevesService.telechargerCertificat(eleve.id).subscribe({
      next: (blob: Blob) => {
        const url  = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href     = url;
        link.download = `certificat_${(eleve.nom_complet || 'eleve').replace(/ /g, '_')}.pdf`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      },
      error: () => this.msg.add({ severity: 'error', summary: 'Erreur PDF',
                                   detail: 'Impossible de générer le certificat.' }),
    });
  }

  telechargerSituationPDF(eleve: Eleve) {
    if (!eleve?.id) return;
    this.elevesService.situationPDF(eleve.id).subscribe({
      next: (blob: Blob) => {
        const url  = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href     = url;
        link.download = `situation_${(eleve.nom_complet || 'eleve').replace(/ /g, '_')}.pdf`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      },
      error: () => this.msg.add({ severity: 'error', summary: 'Erreur PDF',
                                   detail: 'Impossible de générer la situation.' }),
    });
  }

  telechargerFichePDF(eleve: Eleve) {
    if (!eleve?.id) return;
    this.exportantFiche.set(true);
    this.elevesService.fichePDF(eleve.id).subscribe({
      next: (blob: Blob) => {
        const url  = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href     = url;
        link.download = `fiche_${(eleve.nom_complet || 'eleve').replace(/ /g, '_')}.pdf`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
        this.exportantFiche.set(false);
      },
      error: () => {
        this.msg.add({ severity: 'error', summary: 'Erreur PDF',
                       detail: 'Impossible de générer la fiche.' });
        this.exportantFiche.set(false);
      },
    });
  }

  exporterListePDF() {
    this.exportant.set(true);
    const params: Record<string, string> = {};
    if (this.filtreStatut) params['statut'] = this.filtreStatut;
    if (this.filtreAlerte) params['alerte']  = this.filtreAlerte;
    if (this.exerciceSel)  params['exercice'] = this.exerciceSel;
    this.elevesService.exporterListePDF(params).subscribe({
      next: (blob: Blob) => {
        const url  = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href     = url;
        link.download = `eleves_liste.pdf`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
        this.exportant.set(false);
      },
      error: () => {
        this.msg.add({ severity: 'error', summary: 'Erreur PDF',
                       detail: 'Impossible de générer la liste PDF.' });
        this.exportant.set(false);
      },
    });
  }

  ouvrirChangerStatut(eleve: Eleve) {
    this.eleveSelectionne.set(eleve);
    this.formStatut = eleve.statut || 'INSCRIT';
    this.dialogStatutVisible = true;
  }

  sauvegarderStatut() {
    const e = this.eleveSelectionne();
    if (!e) return;
    this.saving.set(true);
    this.elevesService.updateEleve(e.id, { statut: this.formStatut } as Partial<Eleve>).subscribe({
      next: () => {
        this.msg.add({ severity: 'success', summary: 'Statut mis à jour', detail: e.nom_complet });
        this.dialogStatutVisible = false;
        this.saving.set(false);
        this.chargerEleves();
      },
      error: () => this.saving.set(false),
    });
  }

  // ── Correction du déjà payé (reprise) ─────────────────────────────────
  dialogRepriseVisible = false;
  formReprise = { montant_inscription: 0, montant_mensualite: 0, montant_divers: 0, total_attendu: 0 };

  ouvrirReprise(eleve: Eleve) {
    this.eleveSelectionne.set(eleve);
    this.formReprise = { montant_inscription: 0, montant_mensualite: 0, montant_divers: 0,
                         total_attendu: eleve.total_attendu || 0 };
    this.dialogRepriseVisible = true;
    this.elevesService.getReprise(eleve.id).subscribe({
      next: (d: any) => this.formReprise = {
        montant_inscription: d.montant_inscription || 0,
        montant_mensualite:  d.montant_mensualite  || 0,
        montant_divers:      d.montant_divers       || 0,
        total_attendu:       d.total_attendu        || 0,
      },
      error: () => {},
    });
  }

  sauvegarderReprise() {
    const e = this.eleveSelectionne();
    if (!e) return;
    this.saving.set(true);
    this.elevesService.corrigerReprise(e.id, {
      montant_inscription: this.formReprise.montant_inscription || 0,
      montant_mensualite:  this.formReprise.montant_mensualite  || 0,
      montant_divers:      this.formReprise.montant_divers       || 0,
    }).subscribe({
      next: () => {
        this.msg.add({ severity: 'success', summary: 'Déjà payé corrigé', detail: e.nom_complet });
        this.dialogRepriseVisible = false;
        this.saving.set(false);
        this.chargerEleves();
      },
      error: (err) => {
        this.msg.add({ severity: 'error', summary: 'Erreur', detail: err?.error?.error || 'Correction impossible' });
        this.saving.set(false);
      },
    });
  }

  ouvrirPriseEnCharge(eleve: Eleve) {
    this.eleveSelectionne.set(eleve);
    this.formPEC = {
      prise_en_charge:      eleve.prise_en_charge || null,
      pec_inscription:      eleve.pec_inscription || 0,
      pec_mensualite:       eleve.pec_mensualite  || 0,
      obs_prise_en_charge:  eleve.obs_prise_en_charge  || '',
    };
    this.dialogPECVisible = true;
  }

  sauvegarderPEC() {
    const e = this.eleveSelectionne();
    if (!e) return;
    this.saving.set(true);
    const payload: Partial<Eleve> = {
      prise_en_charge:      this.formPEC.prise_en_charge || undefined,
      pec_inscription:      this.formPEC.pec_inscription || 0,
      pec_mensualite:       this.formPEC.pec_mensualite  || 0,
      obs_prise_en_charge:  this.formPEC.obs_prise_en_charge,
    } as Partial<Eleve>;
    this.elevesService.updateEleve(e.id, payload).subscribe({
      next: () => {
        this.msg.add({ severity: 'success', summary: 'Prise en charge enregistrée',
                       detail: e.nom_complet });
        this.dialogPECVisible = false;
        this.saving.set(false);
        this.statsPEC.set(null);  // invalider le cache stats
        this.chargerEleves();
      },
      error: () => this.saving.set(false),
    });
  }

  onJourInconnuChange() {
    this.nouvelEleve.date_inscription_jour_estime = this.jourInconnu;
    if (this.jourInconnu) {
      const d = this.nouvelEleve.date_inscription || new Date().toISOString().split('T')[0];
      this.moisInscription = d.slice(0, 7);                 // AAAA-MM
      this.nouvelEleve.date_inscription = this.moisInscription + '-01';
    }
  }
  onMoisChange() {
    if (this.moisInscription) this.nouvelEleve.date_inscription = this.moisInscription + '-01';
  }

  ouvrirDialog() {
    this.editId = null;
    this.jourInconnu = false;
    this.moisInscription = '';
    this.nouvelEleve = { date_inscription: new Date().toISOString().split('T')[0], regime: 'EXERCICE',
                         etat_sante: 'SAIN', date_inscription_jour_estime: false,
                         reliquat_anterieur: 0, reliquat_note: '' };
    this.dialogVisible = true;
  }

  ouvrirModifier(eleve: Eleve | null) {
    if (!eleve) return;
    this.editId = eleve.id;
    this.nouvelEleve = {
      nom_complet:      eleve.nom_complet,
      section:          eleve.section,
      classe:           eleve.classe,
      genre:            eleve.genre,
      date_naissance:   eleve.date_naissance,
      date_inscription: eleve.date_inscription,
      date_inscription_jour_estime: eleve.date_inscription_jour_estime || false,
      regime:           eleve.regime || 'EXERCICE',
      nb_mois_passager: eleve.nb_mois_passager,
      lieu_naissance:   eleve.lieu_naissance,
      nom_pere:         eleve.nom_pere,
      telephone_pere:   eleve.telephone_pere,
      nom_mere:         eleve.nom_mere,
      telephone_mere:   eleve.telephone_mere,
      nom_tuteur:       eleve.nom_tuteur,
      telephone_tuteur: eleve.telephone_tuteur,
      lien_tuteur:      eleve.lien_tuteur,
      etat_sante:       eleve.etat_sante || 'SAIN',
      observations_sante: eleve.observations_sante,
      abonnements:      [...(eleve.abonnements || [])],
      reliquat_anterieur: Number(eleve.reliquat_anterieur || 0),
      reliquat_note:      eleve.reliquat_note || '',
    };
    this.jourInconnu = !!eleve.date_inscription_jour_estime;
    this.moisInscription = this.jourInconnu ? (eleve.date_inscription || '').slice(0, 7) : '';
    this.dialogFicheVisible = false;
    this.dialogVisible = true;
  }

  sauvegarder() {
    if (!this.nouvelEleve.nom_complet) {
      this.msg.add({ severity: 'warn', summary: this.translate.instant('eleves.champ_requis'),
                     detail: this.translate.instant('eleves.nom_obligatoire') });
      return;
    }
    if (!this.nouvelEleve.section) {
      this.msg.add({ severity: 'warn', summary: this.translate.instant('eleves.champ_requis'),
                     detail: this.translate.instant('eleves.section_classe_obligatoire') });
      return;
    }
    // Classe requise uniquement si la section possède des classes
    if (this.classesSection().length && !this.nouvelEleve.classe) {
      this.msg.add({ severity: 'warn', summary: this.translate.instant('eleves.champ_requis'),
                     detail: this.translate.instant('eleves.classe') });
      return;
    }
    // Tous les champs obligatoires (sauf services) : genre, naissance, lieu, date d'entrée
    const e = this.nouvelEleve;
    if (!e.genre || !e.date_naissance || !e.lieu_naissance || !e.date_inscription) {
      this.msg.add({ severity: 'warn', summary: this.translate.instant('eleves.champ_requis'),
                     detail: this.translate.instant('eleves.tous_champs_obligatoires') });
      return;
    }
    // Ndongo passager (daara) : la durée en mois est obligatoire
    if (e.regime === 'PASSAGER' && !e.nb_mois_passager) {
      this.msg.add({ severity: 'warn', summary: this.translate.instant('eleves.champ_requis'),
                     detail: this.translate.instant('eleves.nb_mois_obligatoire') });
      return;
    }
    // Au moins un parent complet (nom + téléphone)
    const pereOk = !!(e.nom_pere && e.telephone_pere);
    const mereOk = !!(e.nom_mere && e.telephone_mere);
    if (!pereOk && !mereOk) {
      this.msg.add({ severity: 'warn', summary: this.translate.instant('eleves.champ_requis'),
                     detail: this.translate.instant('eleves.parent_obligatoire') });
      return;
    }
    this.saving.set(true);
    const obs = this.editId
      ? this.elevesService.updateEleve(this.editId, this.nouvelEleve)
      : this.elevesService.createEleve(this.nouvelEleve);
    obs.subscribe({
      next: () => {
        this.msg.add({ severity: 'success', summary: this.translate.instant('common.succes'),
                       detail: this.translate.instant(this.editId ? 'eleves.modifie' : 'eleves.ajoute') });
        this.dialogVisible = false;
        this.saving.set(false);
        this.editId = null;
        this.statsPEC.set(null);  // les montants peuvent changer (section, PEC…)
        this.chargerEleves();
      },
      error: (err) => {
        // Remonter le motif du backend quand il y en a un : « montant inférieur
        // au déjà encaissé », « exercice clôturé »… un message générique
        // laisserait l'école corriger à l'aveugle.
        const champ = err?.error && Object.values(err.error)[0];
        const detail = Array.isArray(champ) ? champ[0] : (typeof champ === 'string' ? champ : null);
        this.msg.add({ severity: 'error', summary: this.translate.instant('common.erreur'),
                       detail: detail || this.translate.instant('eleves.impossible_ajouter'),
                       life: detail ? 8000 : 4000 });
        this.saving.set(false);
      }
    });
  }

  private pecFormVide(): PecForm {
    return { prise_en_charge: null, pec_inscription: 0, pec_mensualite: 0,
             obs_prise_en_charge: '' };
  }
}
