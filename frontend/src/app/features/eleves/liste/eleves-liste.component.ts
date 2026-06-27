import { Component, OnInit, inject, signal, computed, ChangeDetectionStrategy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ElevesService } from '../../../core/services/eleves.service';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { Eleve, NiveauAlerte, PriseEnChargeStats, TypePEC, Service } from '../../../core/models/eleve.model';
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

interface PecForm {
  prise_en_charge: string | null;
  type_pec: TypePEC | null;
  taux_pec_inscription: number;
  taux_pec_mensualite: number;
  obs_prise_en_charge: string;
}

@Component({
  selector: 'app-eleves-liste',
  changeDetection: ChangeDetectionStrategy.Default,
  imports: [CommonModule, FormsModule, TranslateModule, TableModule, TagModule, ButtonModule,
            InputTextModule, DialogModule, SelectModule, ToastModule, ProgressBarModule, InputNumberModule,
            TooltipModule, MultiSelectModule],
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
        <p-button label="{{ 'eleves.nouveau' | translate }}" severity="success"
                  pTooltip="Inscrire un nouvel élève"
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
      </div>

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
              <th>{{ 'eleves.reste'         | translate }}</th>
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
              <td class="mono" [class.danger]="eleve.reste_a_payer > 0">{{ eleve.reste_a_payer | number }} FCFA</td>
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
              <th class="text-right">Taux inscr.</th>
              <th class="text-right">Taux mens.</th>
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
                  <span style="color:#64748b;font-size:11px">—</span>
                }
              </td>
              <td class="mono text-right">
                {{ e.taux_pec_inscription > 0 ? (e.taux_pec_inscription + ' %') : '—' }}
              </td>
              <td class="mono text-right">
                {{ e.taux_pec_mensualite > 0 ? (e.taux_pec_mensualite + ' %') : '—' }}
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
            <div class="fiche-row"><span>Date inscription</span><strong>{{ e.date_inscription || '—' }}</strong></div>
            @if (e.prise_en_charge || e.type_pec) {
              <div class="fiche-row"><span>Motif PEC</span>
                <p-tag [value]="pecLabel(e.prise_en_charge)" [severity]="pecSeverity(e.prise_en_charge)" /></div>
              @if (e.type_pec) {
                <div class="fiche-row"><span>Type PEC</span>
                  <p-tag [value]="typePecLabel(e.type_pec)" [severity]="typePecSeverity(e.type_pec)" /></div>
                @if (e.taux_pec_inscription > 0) {
                  <div class="fiche-row"><span>Taux inscription</span>
                    <strong style="color:#00d4aa">{{ e.taux_pec_inscription }} %</strong></div>
                }
                @if (e.taux_pec_mensualite > 0) {
                  <div class="fiche-row"><span>Taux mensualités</span>
                    <strong style="color:#00d4aa">{{ e.taux_pec_mensualite }} %</strong></div>
                }
                <div class="fiche-row"><span>PEC annuel</span>
                  <strong style="color:#ef4444">{{ e.montant_pec_annuel | number:'1.0-0' }} FCFA</strong></div>
              }
            }
          </div>
          <div class="fiche-section">
            <div class="fiche-title">Parents / Tuteurs</div>
            <div class="fiche-row"><span>Père</span><strong>{{ e.nom_pere || '—' }}</strong></div>
            <div class="fiche-row"><span>Tél. père</span><strong class="mono">{{ e.telephone_pere || '—' }}</strong></div>
            <div class="fiche-row"><span>Mère</span><strong>{{ e.nom_mere || '—' }}</strong></div>
            <div class="fiche-row"><span>Tél. mère</span><strong class="mono">{{ e.telephone_mere || '—' }}</strong></div>
          </div>
          <div class="fiche-section">
            <div class="fiche-title">Situation financière</div>
            @if (e.montant_pec_annuel > 0) {
              <div class="fiche-row"><span>Total théorique</span>
                <strong class="mono" style="color:#64748b">{{ e.total_theorique | number:'1.0-0' }} FCFA</strong></div>
              <div class="fiche-row"><span>Prise en charge</span>
                <strong class="mono" style="color:#ef4444">- {{ e.montant_pec_annuel | number:'1.0-0' }} FCFA</strong></div>
            }
            <div class="fiche-row"><span>Total attendu</span><strong class="mono">{{ e.total_attendu | number }} FCFA</strong></div>
            <div class="fiche-row"><span>Total payé</span><strong class="mono success">{{ e.total_paye | number }} FCFA</strong></div>
            <div class="fiche-row"><span>Reste à payer</span>
              <strong class="mono" [class.danger]="e.reste_a_payer > 0" [class.success]="e.reste_a_payer <= 0">
                {{ e.reste_a_payer | number }} FCFA
              </strong>
            </div>
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
          <strong style="color:#e8f0fe">{{ eleveSelectionne()!.nom_complet }}</strong>
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

          <!-- Type PEC -->
          <div class="form-group full">
            <label>Type de prise en charge</label>
            <p-select appendTo="body" [options]="typesPEC" [(ngModel)]="formPEC.type_pec"
                      optionLabel="label" optionValue="value" styleClass="w-full"
                      placeholder="Sélectionner le type" [showClear]="true" />
          </div>

          <!-- Taux inscription — si INSCRIPTION ou TOTALE -->
          @if (formPEC.type_pec === 'INSCRIPTION' || formPEC.type_pec === 'TOTALE') {
            <div class="form-group">
              <label>Taux prise en charge inscription (%)</label>
              <p-inputNumber [(ngModel)]="formPEC.taux_pec_inscription"
                             [min]="0" [max]="100" [step]="5" mode="decimal"
                             styleClass="w-full" placeholder="0 – 100" />
            </div>
          }

          <!-- Taux mensualité — si MENSUALITES ou TOTALE -->
          @if (formPEC.type_pec === 'MENSUALITES' || formPEC.type_pec === 'TOTALE') {
            <div class="form-group">
              <label>Taux prise en charge mensualités (%)</label>
              <p-inputNumber [(ngModel)]="formPEC.taux_pec_mensualite"
                             [min]="0" [max]="100" [step]="5" mode="decimal"
                             styleClass="w-full" placeholder="0 – 100" />
            </div>
          }

          <!-- Observations -->
          <div class="form-group full">
            <label>Observations</label>
            <input pInputText [(ngModel)]="formPEC.obs_prise_en_charge" class="w-full"
                   placeholder="Ex : Orphelin de père, suivi par la commune…" />
          </div>
        </div>

        <!-- Simulation financière -->
        @if (formPEC.type_pec && previewPEC()) {
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
          <input pInputText type="date" [(ngModel)]="nouvelEleve.date_inscription" class="w-full" />
          <small style="color:#64748b;font-size:10px">{{ 'eleves.date_entree_aide' | translate }}</small>
        </div>
        <div class="form-group">
          <label>{{ 'eleves.lieu_naissance' | translate }} *</label>
          <input pInputText [(ngModel)]="nouvelEleve.lieu_naissance" class="w-full"
                 [placeholder]="'eleves.lieu_naissance_ph' | translate" />
        </div>
        <div class="form-group full" style="margin-top:2px">
          <small style="color:#64748b;font-size:11px">⚑ {{ 'eleves.parent_obligatoire' | translate }}</small>
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
        <div class="form-group full" *ngIf="servicesActifs().length">
          <label>{{ 'eleves.services' | translate }}</label>
          <p-multiSelect appendTo="body" [options]="servicesActifs()" [(ngModel)]="nouvelEleve.abonnements"
                         optionLabel="nom" optionValue="id" display="chip"
                         [placeholder]="'eleves.services_ph' | translate" styleClass="w-full" />
        </div>
      </div>
      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler'    | translate" severity="secondary" (onClick)="dialogVisible=false" />
        <p-button [label]="'common.enregistrer'| translate" severity="success" [loading]="saving()" (onClick)="sauvegarder()" />
      </ng-template>
    </p-dialog>

    <!-- Dialog services / activités d'un élève -->
    <p-dialog [header]="'🔖 ' + ('eleves.services' | translate)" [(visible)]="dialogServicesVisible"
              [modal]="true" [style]="{width:'440px'}" [draggable]="false">
      <div *ngIf="eleveSelectionne() as e">
        <div style="font-size:13px;color:#94a3b8;margin-bottom:14px">
          <strong style="color:#e8f0fe">{{ e.nom_complet }}</strong> — {{ e.section_nom }}
        </div>
        <div class="form-group" *ngIf="servicesActifs().length; else aucunService">
          <label>{{ 'eleves.services_choix' | translate }}</label>
          <p-multiSelect appendTo="body" [options]="servicesActifs()" [(ngModel)]="formServices" display="chip"
                         optionLabel="nom" optionValue="id"
                         [placeholder]="'eleves.services_ph' | translate" styleClass="w-full" />
        </div>
        <ng-template #aucunService>
          <div style="color:#64748b;font-size:13px">{{ 'eleves.services_aucun' | translate }}</div>
        </ng-template>
      </div>
      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler' | translate" severity="secondary" (onClick)="dialogServicesVisible=false" />
        <p-button [label]="'common.enregistrer' | translate" severity="success" [loading]="saving()" (onClick)="sauvegarderServices()" />
      </ng-template>
    </p-dialog>
  `,
  styles: [`
    .page-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:16px; }
    .page-title  { font-size:20px; font-weight:600; color:#e8f0fe; margin:0 0 4px; }
    .page-sub    { font-size:12px; color:#64748b; }

    .kpi-row { display:flex; gap:10px; flex-wrap:wrap; }
    .kpi-mini { background:#1e2d45; border:1px solid #2a3f5f; border-radius:8px; padding:10px 14px;
                text-align:center; cursor:pointer; min-width:90px; }
    .kpi-mini:hover { border-color:#00d4aa; }
    .kpi-mini.success { border-color:#10b981; }
    .kpi-mini.danger  { border-color:#ef4444; }
    .kpi-mini.warn    { border-color:#f59e0b; }
    .kpi-mini.info    { border-color:#0099ff; }
    .km-val   { display:block; font-size:22px; font-weight:700; color:#e8f0fe; font-family:monospace; }
    .km-label { display:block; font-size:10px; color:#64748b; text-transform:uppercase; margin-top:2px; }

    /* Panel stats financières */
    .stats-panel { background:#111827; border:1px solid #2a3f5f; border-radius:10px;
                   padding:14px 18px; margin-bottom:14px; }
    .stats-panel-title { font-size:11px; font-weight:700; color:#00d4aa; text-transform:uppercase;
                         letter-spacing:.5px; margin-bottom:12px; }
    .stats-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }
    .stat-item { background:#1e2d45; border-radius:8px; padding:10px 12px; }
    .stat-label { display:block; font-size:10px; color:#64748b; text-transform:uppercase;
                  letter-spacing:.3px; margin-bottom:4px; }
    .stat-val { display:block; font-size:15px; font-weight:700; color:#e8f0fe; font-family:monospace; }
    .stat-val.success { color:#10b981; }
    .stat-val.danger  { color:#ef4444; }
    .stat-val.warn    { color:#f59e0b; }

    .filters-bar { display:flex; gap:12px; margin-bottom:16px; }
    .search-input { flex:1; }

    .alerte-aide { margin-bottom:14px; }
    .aide-toggle { background:none; border:none; color:#94a3b8; font-size:12px; cursor:pointer; padding:2px 0; }
    .aide-toggle:hover { color:#e8f0fe; }
    .aide-corps { display:flex; flex-wrap:wrap; gap:18px; margin-top:8px; padding:12px 14px;
                  background:#172338; border:1px solid #2a3f5f; border-radius:8px;
                  font-size:12px; color:#94a3b8; }
    .aide-corps span { display:inline-flex; align-items:center; gap:6px; }
    ::ng-deep .filter-drop { min-width:160px; }

    .table-card { background:#1e2d45; border:1px solid #2a3f5f; border-radius:12px; overflow:hidden; }
    .table-toolbar { display:flex; justify-content:space-between; align-items:center;
                     padding:12px 16px; border-bottom:1px solid #2a3f5f; }
    .tbl-count { color:#e8f0fe; font-weight:600; font-size:13px; }

    ::ng-deep .p-datatable .p-datatable-thead > tr > th {
      background:#111827 !important; color:#64748b !important;
      font-size:11px !important; text-transform:uppercase !important; border-color:#2a3f5f !important;
    }
    ::ng-deep .p-datatable .p-datatable-tbody > tr {
      background:#1e2d45 !important; color:#94a3b8 !important;
      border-bottom:1px solid rgba(42,63,95,0.4) !important;
    }
    ::ng-deep .p-datatable .p-datatable-tbody > tr:hover { background:#1a2235 !important; }

    .mono    { font-family:monospace; font-size:12px; }
    .bold    { font-weight:600; color:#e8f0fe; }
    .success { color:#10b981; }
    .danger  { color:#ef4444; }
    .empty-msg { text-align:center; padding:40px; color:#64748b; }
    .btn-row { display:flex; gap:2px; }
    .text-right { text-align:right; }

    /* Fiche */
    .fiche-grid { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
    .fiche-section { background:#111827; border-radius:8px; padding:12px; }
    .fiche-title { font-size:11px; font-weight:700; color:#00d4aa; text-transform:uppercase;
                   margin-bottom:8px; letter-spacing:.5px; }
    .fiche-row { display:flex; justify-content:space-between; align-items:center; padding:4px 0;
                 border-bottom:1px solid rgba(42,63,95,0.3); font-size:11px; }
    .fiche-row span { color:#64748b; }
    .fiche-row strong { color:#e8f0fe; }

    /* Formulaires */
    .form-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
    .form-group { display:flex; flex-direction:column; gap:5px; }
    .form-group.full { grid-column:1/-1; }
    .form-group label { font-size:11px; color:#94a3b8; text-transform:uppercase; letter-spacing:.3px; }
    .w-full { width:100%; }

    /* Dialog PEC */
    .pec-eleve-header { display:flex; align-items:center; gap:10px; margin-bottom:16px;
                        padding:10px 14px; background:#111827; border-radius:8px; }
    .pec-eleve-header strong { color:#e8f0fe; font-size:14px; }
    .pec-eleve-header span { color:#64748b; font-size:12px; }

    .pec-preview { background:#111827; border:1px solid #2a3f5f; border-radius:8px;
                   padding:14px; margin-top:16px; }
    .pec-preview-title { font-size:10px; font-weight:700; color:#00d4aa; text-transform:uppercase;
                         letter-spacing:.5px; margin-bottom:10px; }
    .pec-preview-grid { display:flex; flex-direction:column; gap:6px; }
    .pv-row { display:flex; justify-content:space-between; align-items:center;
              padding:5px 0; border-bottom:1px solid rgba(42,63,95,0.3); font-size:12px; }
    .pv-row span { color:#94a3b8; }
    .pv-row.highlight { border-top:1px solid #2a3f5f; margin-top:4px; padding-top:8px;
                        border-bottom:none; }
  `]
})
export class ElevesListeComponent implements OnInit {
  private translate     = inject(TranslateService);
  private elevesService = inject(ElevesService);
  private msg           = inject(MessageService);

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
  dialogFicheVisible   = false;
  dialogStatutVisible  = false;
  dialogPECVisible     = false;
  dialogServicesVisible = false;
  eleveSelectionne    = signal<Eleve | null>(null);

  services       = signal<Service[]>([]);
  servicesActifs = computed(() => this.services().filter(s => s.actif));
  formServices: string[] = [];

  recherche    = '';
  filtreAlerte = '';
  filtreStatut = '';
  formStatut   = 'INSCRIT';
  formPEC: PecForm = this.pecFormVide();

  elevesPEC = computed(() =>
    this.eleves().filter(e => e.prise_en_charge || e.type_pec)
  );

  previewPEC = computed(() => {
    const eleve = this.eleveSelectionne();
    const form  = this.formPEC;
    if (!eleve || !form.type_pec) return null;
    const section = this.sections().find(s => s.id === eleve.section);
    if (!section) return null;
    const tauxI   = (form.taux_pec_inscription || 0) / 100;
    const tauxM   = (form.taux_pec_mensualite   || 0) / 100;
    const type    = form.type_pec;
    const inscr   = (type === 'INSCRIPTION' || type === 'TOTALE')
                    ? Math.round(section.frais_inscription * tauxI) : 0;
    const mens    = (type === 'MENSUALITES'  || type === 'TOTALE')
                    ? Math.round(section.frais_mensualite  * tauxM) : 0;
    const annuel  = inscr + mens * 10;
    const restant = Math.max((section.total_annuel || 0) - annuel, 0);
    return { inscr, mens, annuel, restant };
  });

  nouvelEleve: Partial<Eleve> = {};
  editId: string | null = null;
  legendeVisible = false;

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

  ngOnInit() {
    this.chargerEleves();
    this.chargerSections();
    this.chargerServices();
    this.chargerClasses();
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

  chargerEleves() {
    this.loading.set(true);
    this.elevesService.getEleves().subscribe({
      next: res => {
        const data = Array.isArray(res) ? res : ((res as any).results || []);
        this.eleves.set(data);
        this.elevesFiltres.set(data);
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
    this.elevesFiltres.set(data);
  }

  countStatut(s: string)      { return this.eleves().filter(e => e.statut === s).length; }
  countGenre(g: string)       { return this.eleves().filter(e => e.genre === g).length; }
  countTypePEC(t: TypePEC)    { return this.elevesPEC().filter(e => e.type_pec === t).length; }

  alerteLabel(a: NiveauAlerte | string): string {
    return { CRITIQUE: 'CRITIQUE', URGENT: 'URGENT', ATTENTION: 'ATTENTION', OK: 'OK', A_JOUR: 'A JOUR' }[a] || a;
  }
  alerteSeverity(a: NiveauAlerte | string): 'danger' | 'warn' | 'success' | 'secondary' {
    return ({ CRITIQUE:'danger', URGENT:'danger', ATTENTION:'warn', OK:'success', A_JOUR:'success' } as any)[a] || 'secondary';
  }
  statutLabel(s: string) {
    return { INSCRIT:'Inscrit', ABANDONNE:'Abandonné', TRANSFERE:'Transféré', DIPLOME:'Diplômé' }[s] || s;
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

  ouvrirPriseEnCharge(eleve: Eleve) {
    this.eleveSelectionne.set(eleve);
    this.formPEC = {
      prise_en_charge:      eleve.prise_en_charge || null,
      type_pec:             eleve.type_pec        || null,
      taux_pec_inscription: eleve.taux_pec_inscription || 0,
      taux_pec_mensualite:  eleve.taux_pec_mensualite  || 0,
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
      type_pec:             this.formPEC.type_pec        || undefined,
      taux_pec_inscription: this.formPEC.taux_pec_inscription,
      taux_pec_mensualite:  this.formPEC.taux_pec_mensualite,
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

  ouvrirDialog() {
    this.editId = null;
    this.nouvelEleve = { date_inscription: new Date().toISOString().split('T')[0] };
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
      lieu_naissance:   eleve.lieu_naissance,
      nom_pere:         eleve.nom_pere,
      telephone_pere:   eleve.telephone_pere,
      nom_mere:         eleve.nom_mere,
      telephone_mere:   eleve.telephone_mere,
      abonnements:      [...(eleve.abonnements || [])],
    };
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
      error: () => {
        this.msg.add({ severity: 'error', summary: this.translate.instant('common.erreur'),
                       detail: this.translate.instant('eleves.impossible_ajouter') });
        this.saving.set(false);
      }
    });
  }

  private pecFormVide(): PecForm {
    return { prise_en_charge: null, type_pec: null,
             taux_pec_inscription: 0, taux_pec_mensualite: 0,
             obs_prise_en_charge: '' };
  }
}
