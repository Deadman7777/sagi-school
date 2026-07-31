import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { PaiementsService } from '../../core/services/paiements.service';
import { ElevesService } from '../../core/services/eleves.service';
import { ComptabiliteService } from '../../core/services/comptabilite.service';
import { GouvernanceService } from '../../core/services/gouvernance.service';
import { Eleve } from '../../core/models/eleve.model';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { TagModule } from 'primeng/tag';
import { ToastModule } from 'primeng/toast';
import { InputNumberModule } from 'primeng/inputnumber';
import { CheckboxModule } from 'primeng/checkbox';
import { MessageService } from 'primeng/api';
import { TooltipModule } from 'primeng/tooltip';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { PiecesJustificativesComponent } from '../../shared/pieces-justificatives.component';
import { ImportChargesDialogComponent } from './import-charges-dialog.component';

@Component({
  selector: 'app-paiements',
  standalone: true,
  imports: [CommonModule, FormsModule, TableModule, TranslateModule, ButtonModule, DialogModule,
            InputTextModule, SelectModule, TagModule, ToastModule,
            InputNumberModule, CheckboxModule, TooltipModule, PiecesJustificativesComponent,
            ImportChargesDialogComponent],
  providers: [MessageService],
  template: `
    <p-toast />

    <!-- Header -->
    <div class="page-header">
      <div>
        <h2 class="page-title">{{ 'paiements.title' | translate }}</h2>
        <span class="page-sub">{{ stats()?.nb_transactions || 0 }} transactions · Total : {{ (stats()?.total || 0) | number:'1.0-0' }} FCFA</span>
      </div>
      <p-button label="{{ 'paiements.nouveau' | translate }}" severity="success" (onClick)="ouvrirDialog()" />
    </div>

    <!-- Barre d'onglets -->
    <div class="tabs-bar">
      <button class="tab-btn" [class.active]="onglet() === 'paiements'"
              (click)="onglet.set('paiements')">
        💰 {{ 'paiements.title' | translate }}
      </button>
      <button class="tab-btn" [class.active]="onglet() === 'charges'"
              (click)="onglet.set('charges'); chargerCharges()">
        💸 Charges
      </button>
    </div>

    <!-- === ONGLET PAIEMENTS === -->
    <ng-container *ngIf="onglet() === 'paiements'">

    <!-- Stats modes -->
    <div class="modes-grid" *ngIf="stats()?.par_mode?.length">
      <div class="mode-card" *ngFor="let m of stats().par_mode">
        <div class="mode-name">{{ m.mode }}</div>
        <div class="mode-total">{{ m.total | number:'1.0-0' }}</div>
        <div class="mode-nb">{{ m.nb }} opérations</div>
      </div>
    </div>

    <!-- Table paiements -->
    <div class="table-card">
      <!-- Recherche : élève, matricule, n° de reçu ou observations. Retrouver un
           règlement supposait de faire défiler toute l'année. -->
      <div class="search-bar">
        <input pInputText [(ngModel)]="recherchePaiement" (ngModelChange)="onRecherchePaiementChange()"
               class="search-field" placeholder="🔍 Rechercher un règlement — élève, matricule, n° de reçu…" />
        @if (recherchePaiement) {
          <button type="button" class="search-x" (click)="effacerRecherchePaiement()"
                  title="Effacer">✕</button>
        }
      </div>
      <p-table [value]="paiements()" [loading]="loading()"
               styleClass="p-datatable-sm" [paginator]="true" [rows]="20">
        <ng-template pTemplate="header">
          <tr>
            <th>{{ 'paiements.no_piece'    | translate }}</th>
            <th>{{ 'paiements.date'        | translate }}</th>
            <th>{{ 'paiements.eleve_col'   | translate }}</th>
            <th>{{ 'paiements.inscription' | translate }}</th>
            <th>{{ 'paiements.mensualite'  | translate }}</th>
            <th>{{ 'paiements.uniforme'    | translate }}</th>
            <th>{{ 'paiements.fournitures' | translate }}</th>
            <th>{{ 'paiements.cantine'     | translate }}</th>
            <th>{{ 'paiements.total'       | translate }}</th>
            <th>{{ 'paiements.mode'        | translate }}</th>
            <th>Statut</th>
            <th>Actions</th>
          </tr>
        </ng-template>
        <ng-template pTemplate="body" let-p>
          <tr [class.ligne-annulee]="p.statut === 'ANNULE'">
            <td class="mono">{{ p.no_piece }}</td>
            <td>{{ p.date_paiement | date:'dd/MM/yyyy' }}</td>
            <td class="bold">{{ p.eleve_nom }}</td>
            <td class="mono">{{ p.montant_inscription | number:'1.0-0' }}</td>
            <td class="mono">{{ p.montant_mensualite  | number:'1.0-0' }}</td>
            <td class="mono">{{ p.montant_uniforme    | number:'1.0-0' }}</td>
            <td class="mono">{{ p.montant_fournitures | number:'1.0-0' }}</td>
            <td class="mono">{{ p.montant_cantine     | number:'1.0-0' }}</td>
            <td class="mono" [class.success]="p.statut !== 'ANNULE'"
                             [class.annule-val]="p.statut === 'ANNULE'">
              {{ p.total | number:'1.0-0' }} FCFA
            </td>
            <td><p-tag [value]="p.mode_paiement" severity="info" /></td>
            <td>
              <p-tag *ngIf="p.statut === 'ANNULE'" value="ANNULÉ" severity="danger" />
              <p-tag *ngIf="p.statut !== 'ANNULE'" value="Actif"  severity="success" />
            </td>
            <td>
              <div class="btn-row">
                <p-button icon="pi pi-print" [rounded]="true" [text]="true"
                          severity="secondary" (onClick)="imprimerRecu(p)"
                          pTooltip="Imprimer le reçu" tooltipPosition="top"
                          [disabled]="p.statut === 'ANNULE'" />
                <p-button *ngIf="p.statut !== 'ANNULE'"
                          icon="pi pi-pencil" [rounded]="true" [text]="true"
                          severity="warn" pTooltip="Modifier ce paiement" tooltipPosition="top"
                          (onClick)="demanderModificationPaiement(p)" />
                <p-button *ngIf="p.statut !== 'ANNULE'"
                          icon="pi pi-ban" [rounded]="true" [text]="true"
                          severity="danger" pTooltip="Annuler ce paiement (contre-écritures)"
                          tooltipPosition="top" (onClick)="demanderAnnulationPaiement(p)" />
              </div>
            </td>
          </tr>
        </ng-template>
        <ng-template pTemplate="emptymessage">
          <tr><td colspan="12" class="empty-msg">{{ 'paiements.aucun' | translate }}</td></tr>
        </ng-template>
      </p-table>
    </div>

    <!-- Confirmation annulation paiement -->
    <p-dialog header="⚠️ Confirmer l'annulation" [(visible)]="confirmAnnulVisible"
              [modal]="true" [style]="{width:'440px'}" [draggable]="false">
      <div *ngIf="paiementAnnuler" style="padding:8px 0">
        <div style="background:var(--surface-4);border-radius:8px;padding:14px;margin-bottom:16px;border-left:4px solid #ef4444">
          <div style="font-size:13px;color:var(--text);font-weight:600">{{ paiementAnnuler.no_piece }}</div>
          <div style="font-size:12px;color:var(--text-2);margin-top:4px">
            {{ paiementAnnuler.eleve_nom }} · {{ paiementAnnuler.total | number:'1.0-0' }} FCFA
          </div>
        </div>
        <p style="font-size:13px;color:var(--text-2);line-height:1.6;margin:0">
          Cette opération va générer des <strong style="color:#f59e0b">contre-écritures SYSCOHADA</strong>
          pour neutraliser toutes les écritures comptables liées à ce paiement.
          <br><br>
          Le paiement sera marqué <strong style="color:#ef4444">ANNULÉ</strong> et
          n'affectera plus les calculs financiers.
          <br><br>
          ⚠️ Cette action est <strong style="color:#ef4444">irréversible</strong>.
        </p>
      </div>
      <ng-template pTemplate="footer">
        <p-button label="Non, conserver" severity="secondary" (onClick)="confirmAnnulVisible=false" />
        <p-button label="Oui, annuler le paiement" severity="danger"
                  [loading]="savingAnnul()" (onClick)="confirmerAnnulationPaiement()" />
      </ng-template>
    </p-dialog>

    <!-- Dialog modification paiement -->
    <p-dialog header="✏️ Modifier le paiement" [(visible)]="modifVisible"
              [modal]="true" [style]="{width:'520px'}" [draggable]="false">
      <div *ngIf="paiementModifier" style="padding:4px 0">
        <!-- Info paiement original -->
        <div style="background:var(--surface-4);border-radius:8px;padding:12px;margin-bottom:16px;border-left:4px solid #f59e0b">
          <div style="font-size:12px;color:#f59e0b;font-weight:600;margin-bottom:4px">
            Original : {{ paiementModifier.no_piece }}
          </div>
          <div style="font-size:11px;color:var(--text-2)">
            {{ paiementModifier.eleve_nom }} · {{ paiementModifier.total | number:'1.0-0' }} FCFA · {{ paiementModifier.mode_paiement }}
          </div>
        </div>

        <!-- Montants -->
        <div class="montants-grid" style="margin-bottom:12px">
          <div class="form-group">
            <label>Inscription</label>
            <p-inputNumber [(ngModel)]="modifForm.montant_inscription" [min]="0" mode="decimal" styleClass="w-full" />
          </div>
          <div class="form-group">
            <label>Mensualité</label>
            <p-inputNumber [(ngModel)]="modifForm.montant_mensualite" [min]="0" mode="decimal" styleClass="w-full" />
          </div>
          <div class="form-group">
            <label>Uniforme</label>
            <p-inputNumber [(ngModel)]="modifForm.montant_uniforme" [min]="0" mode="decimal" styleClass="w-full" />
          </div>
          <div class="form-group">
            <label>Fournitures</label>
            <p-inputNumber [(ngModel)]="modifForm.montant_fournitures" [min]="0" mode="decimal" styleClass="w-full" />
          </div>
          <div class="form-group">
            <label>Cantine</label>
            <p-inputNumber [(ngModel)]="modifForm.montant_cantine" [min]="0" mode="decimal" styleClass="w-full" />
          </div>
          <div class="form-group">
            <label>Divers</label>
            <p-inputNumber [(ngModel)]="modifForm.montant_divers" [min]="0" mode="decimal" styleClass="w-full" />
          </div>
          <!-- Part reliquat du reçu d'origine : modifiable, plafonnée au
               reliquat encore dû (le backend refuse tout dépassement). -->
          @if (modifForm.montant_reliquat > 0) {
            <div class="form-group">
              <label>🔁 Reliquat antérieur</label>
              <p-inputNumber [(ngModel)]="modifForm.montant_reliquat" [min]="0" mode="decimal" styleClass="w-full" />
            </div>
          }
        </div>

        <div class="total-bar" style="margin-bottom:12px">
          <span>Nouveau total</span>
          <span class="total-val">{{ totalModifForm() | number:'1.0-0' }} FCFA</span>
        </div>

        <div class="form-group" style="margin-bottom:10px">
          <label>Mode de paiement</label>
          <p-select [options]="modesPaiement" [(ngModel)]="modifForm.mode_paiement"
                    optionLabel="label" optionValue="value"
                    placeholder="Choisir le mode..." styleClass="w-full" />
        </div>

        <div class="form-group">
          <label>Observations</label>
          <input pInputText [(ngModel)]="modifForm.observations" class="w-full" />
        </div>
      </div>
      <ng-template pTemplate="footer">
        <p-button label="Annuler" severity="secondary" (onClick)="modifVisible=false" />
        <p-button label="✏️ Enregistrer la modification" severity="warn"
                  [loading]="savingModif()" [disabled]="totalModifForm() <= 0"
                  (onClick)="confirmerModificationPaiement()" />
      </ng-template>
    </p-dialog>

    <!-- Dialog saisie paiement -->
    <p-dialog header="💰 Saisie de Paiement" [(visible)]="dialogVisible"
              [modal]="true" [style]="{width:'600px'}" [draggable]="false">

      <!-- Recherche élève — champ simple + liste déroulante -->
      <div class="search-eleve-wrap">
        <label class="search-label">
          Rechercher l'élève *
          @if (!eleveSelectionne) {
            <span class="search-hint">Nom, matricule ou père (min. 2 caractères)</span>
          }
        </label>

        @if (!eleveSelectionne) {
          <!-- Champ de saisie -->
          <div style="position:relative">
            <input pInputText
                   [(ngModel)]="rechercheInput"
                   (ngModelChange)="onRechercheChange($event)"
                   placeholder="Ex : Diallo, Fatou, 2026-ETB…"
                   class="w-full search-input-field"
                   autocomplete="off" />
            @if (loadingRecherche()) {
              <span class="search-spinner">⟳</span>
            }
          </div>

          <!-- Liste des résultats -->
          @if (elevesSuggestions().length > 0) {
            <div class="suggestions-list">
              @for (e of elevesSuggestions(); track e.id) {
                <div class="suggestion-item" (click)="selectionnerEleve(e)">
                  <div class="si-top">
                    <strong class="si-nom">{{ e.nom_complet }}</strong>
                    @if (e.matricule) {
                      <span class="si-matricule">{{ e.matricule }}</span>
                    }
                    @if (e.statut === 'ABANDONNE') {
                      <span class="badge-statut rouge">Abandonné</span>
                    }
                    @if (e.statut === 'TRANSFERE') {
                      <span class="badge-statut orange">Transféré</span>
                    }
                    @if (e.prise_en_charge) {
                      <span class="badge-statut violet">PEC {{ e.taux_prise_en_charge }}%</span>
                    }
                  </div>
                  <div class="si-bottom">
                    <span>{{ e.section_nom }}</span>
                    @if (e.date_naissance) { <span>· Né(e) {{ e.date_naissance }}</span> }
                    @if (e.nom_pere) { <span>· Père : {{ e.nom_pere }}</span> }
                    @if (e.telephone_pere) { <span>· {{ e.telephone_pere }}</span> }
                  </div>
                </div>
              }
            </div>
          }

          @if (rechercheInput.length >= 2 && !loadingRecherche() && elevesSuggestions().length === 0) {
            <div class="search-empty">Aucun élève trouvé pour "{{ rechercheInput }}"</div>
          }
        }

        <!-- Élève sélectionné -->
        @if (eleveSelectionne) {
          <div class="eleve-selected">
            <div class="es-info">
              <strong class="es-nom">{{ eleveSelectionne.nom_complet }}</strong>
              <span class="si-matricule">{{ eleveSelectionne.matricule }}</span>
              <span class="es-section">{{ eleveSelectionne.section_nom }}</span>
            </div>
            <button class="btn-changer" (click)="changerEleve()" type="button">✕ Changer</button>
          </div>
        }
      </div>

      <!-- Spinner chargement données élève -->
      @if (loadingSaisie()) {
        <div style="text-align:center;padding:10px;color:var(--text-3);font-size:12px">⏳ Chargement des données...</div>
      }

      <!-- Alerte ABANDONNÉ -->
      @if (saisieDonnees()?.statut === 'ABANDONNE') {
        <div style="background:rgba(239,68,68,0.1);border:1px solid #ef4444;border-radius:6px;padding:10px 14px;font-size:12px;color:#ef4444;margin-bottom:10px">
          ⚠️ Cet élève est marqué <strong>ABANDONNÉ</strong>. Le paiement sera enregistré mais ne sera pas comptabilisé dans les statistiques actives.
        </div>
      }

      <!-- Prise en charge, décomposée : le tarif de l'école, la part prise en
           charge, ce qui reste à la famille. Le guichet ne voyait qu'un
           pourcentage — qu'il ne pouvait pas vérifier, et qui ne veut plus rien
           dire depuis que les montants font foi : le badge ne s'affichait donc
           jamais. Un parent qui demande pourquoi on lui réclame 65 000 quand le
           tarif est de 73 000 obtient maintenant sa réponse à l'écran. -->
      @if (saisieDonnees()?.pec?.annuel?.pec > 0) {
        <div class="pec-box">
          <div class="pec-titre">
            🤝 Prise en charge
            @if (saisieDonnees()!.pec.organisme) {
              — <strong>{{ saisieDonnees()!.pec.organisme }}</strong>
            } @else if (saisieDonnees()!.pec.libelle) {
              — <strong>{{ saisieDonnees()!.pec.libelle }}</strong>
            }
          </div>
          <div class="pec-grille">
            <span></span>
            <span class="pec-th">Dû réel</span>
            <span class="pec-th">Prise en charge</span>
            <span class="pec-th">À payer</span>
            @if (saisieDonnees()!.pec.inscription.pec > 0) {
              <span class="pec-lib">Inscription</span>
              <span class="mono">{{ saisieDonnees()!.pec.inscription.brut | number:'1.0-0' }}</span>
              <span class="mono pec-part">− {{ saisieDonnees()!.pec.inscription.pec | number:'1.0-0' }}</span>
              <strong class="mono">{{ saisieDonnees()!.pec.inscription.net | number:'1.0-0' }}</strong>
            }
            @if (saisieDonnees()!.pec.mensuel.pec > 0) {
              <span class="pec-lib">Par mois</span>
              <span class="mono">{{ saisieDonnees()!.pec.mensuel.brut | number:'1.0-0' }}</span>
              <span class="mono pec-part">− {{ saisieDonnees()!.pec.mensuel.pec | number:'1.0-0' }}</span>
              <strong class="mono">{{ saisieDonnees()!.pec.mensuel.net | number:'1.0-0' }}</strong>
            }
            <span class="pec-lib">Sur l'année</span>
            <span class="mono">{{ saisieDonnees()!.pec.annuel.brut | number:'1.0-0' }}</span>
            <span class="mono pec-part">− {{ saisieDonnees()!.pec.annuel.pec | number:'1.0-0' }}</span>
            <strong class="mono">{{ saisieDonnees()!.pec.annuel.net | number:'1.0-0' }}</strong>
          </div>
          @if (saisieDonnees()!.pec.mensuel.pec > 0) {
            <div class="pec-aide">
              « Par mois » comprend les services mensuels auxquels l'élève est abonné.
            </div>
          }
          @if (saisieDonnees()?.obs_prise_en_charge) {
            <div class="pec-aide">{{ saisieDonnees()!.obs_prise_en_charge }}</div>
          }
        </div>
      }

      <!-- Récapitulatif situation financière -->
      @if (saisieDonnees() && !loadingSaisie()) {
        <div class="eleve-info" style="margin-bottom:14px">
          <div class="ei-row"><span>Élève</span><strong>{{ saisieDonnees()!.nom_complet }}</strong></div>
          <div class="ei-row"><span>Section</span><span>{{ saisieDonnees()!.section_nom }}</span></div>
          <div class="ei-row"><span>Total annuel dû</span><span class="mono">{{ saisieDonnees()!.total_annuel_net | number:'1.0-0' }} FCFA</span></div>
          <div class="ei-row"><span>Déjà versé</span><span class="mono success">{{ saisieDonnees()!.total_paye | number:'1.0-0' }} FCFA ({{ saisieDonnees()!.nb_paiements }} pmt)</span></div>
          <div class="ei-row"><span>Reste à payer</span>
            <strong class="mono" [class.success]="saisieDonnees()!.total_restant === 0" [class.danger]="saisieDonnees()!.total_restant > 0">
              {{ saisieDonnees()!.total_restant === 0 ? '✅ Soldé' : (saisieDonnees()!.total_restant | number:'1.0-0') + ' FCFA' }}
            </strong>
          </div>
          @if (saisieDonnees()!.reliquat.restant > 0) {
            <div class="ei-row">
              <span>Reliquat {{ saisieDonnees()!.reliquat.annee }}</span>
              <strong class="mono" style="color:#f97316">
                {{ saisieDonnees()!.reliquat.restant | number:'1.0-0' }} FCFA
              </strong>
            </div>
            <div class="ei-row">
              <span>Dû total (toutes années)</span>
              <strong class="mono danger">
                {{ saisieDonnees()!.total_restant_global | number:'1.0-0' }} FCFA
              </strong>
            </div>
          }
        </div>
      }

      <!-- Type de paiement -->
      @if (saisieDonnees() && !loadingSaisie()) {
        <div class="form-group full" style="margin-bottom:12px">
          <label>Type de paiement *</label>
          <div style="display:flex;gap:8px;margin-top:6px">
            <!-- « Inscription », ou le mot de l'école pour le renouvellement
                 d'un ancien élève : réclamer une inscription à un ndongo qui
                 est là depuis quatre ans n'a aucun sens pour sa famille. -->
            <button [class]="typePaiement === 'INSCRIPTION' ? 'type-btn active-inscr' : 'type-btn'"
                    (click)="setTypePaiement('INSCRIPTION')">
              🎓 {{ libelleEntree() }}
            </button>
            <button [class]="typePaiement === 'MENSUALITE' ? 'type-btn active-mens' : 'type-btn'"
                    (click)="setTypePaiement('MENSUALITE')">
              📅 Mensualité
            </button>
          </div>
        </div>

        <!-- Montants avec indication reste -->
        @if (typePaiement === 'INSCRIPTION') {
          <div class="montants-grid">
            <div class="form-group">
              <label>{{ libelleEntree() }}
                @if (saisieDonnees()!.fees_nets.inscription > 0) {
                  <span class="fee-hint">Dû : {{ saisieDonnees()!.reste.inscription | number:'1.0-0' }}</span>
                }
              </label>
              <p-inputNumber [(ngModel)]="form.montant_inscription" [min]="0" mode="decimal" styleClass="w-full" />
            </div>
            <!-- Uniforme/fournitures : repliés dans la composition de l'inscription ;
                 visibles seulement s'il reste un dû historique sur ces catégories -->
            @if (saisieDonnees()!.fees_nets.uniforme > 0 || saisieDonnees()!.reste.uniforme > 0) {
              <div class="form-group">
                <label>Uniforme
                  @if (saisieDonnees()!.fees_nets.uniforme > 0) {
                    <span class="fee-hint">Dû : {{ saisieDonnees()!.reste.uniforme | number:'1.0-0' }}</span>
                  }
                </label>
                <p-inputNumber [(ngModel)]="form.montant_uniforme" [min]="0" mode="decimal" styleClass="w-full" />
              </div>
            }
            @if (saisieDonnees()!.fees_nets.fournitures > 0 || saisieDonnees()!.reste.fournitures > 0) {
              <div class="form-group">
                <label>Fournitures
                  @if (saisieDonnees()!.fees_nets.fournitures > 0) {
                    <span class="fee-hint">Dû : {{ saisieDonnees()!.reste.fournitures | number:'1.0-0' }}</span>
                  }
                </label>
                <p-inputNumber [(ngModel)]="form.montant_fournitures" [min]="0" mode="decimal" styleClass="w-full" />
              </div>
            }
            <div class="form-group">
              <label>Divers</label>
              <p-inputNumber [(ngModel)]="form.montant_divers" [min]="0" mode="decimal" styleClass="w-full" />
            </div>
          </div>
        }

        @if (typePaiement === 'MENSUALITE') {
          @if (saisieDonnees()?.mois_ecole?.length) {
            <div class="form-group full" style="margin-bottom:10px">
              <label>Mois concerné(s) <span style="color:var(--text-3);font-weight:400">— cocher plusieurs pour anticiper</span></label>
              <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:4px">
                <!-- Un mois entamé porte son reste : c'est la seule façon de
                     voir, au guichet, qu'un acompte a déjà été versé dessus. -->
                @for (m of saisieDonnees()!.mois_ecole; track m.num) {
                  <button type="button" [disabled]="!m.du"
                    [style.background]="moisSelected(m.num) ? '#00d4aa' : (m.statut === 'SOLDE' ? 'var(--pos-bg)' : (m.statut === 'PARTIEL' ? 'rgba(245,158,11,0.14)' : 'var(--surface)'))"
                    [style.border-color]="m.statut === 'PARTIEL' && !moisSelected(m.num) ? 'rgba(245,158,11,0.45)' : 'var(--border)'"
                    [style.color]="moisSelected(m.num) ? '#06281f' : (m.du ? 'var(--text)' : 'var(--text-5)')"
                    style="border:1px solid var(--border);border-radius:6px;padding:5px 10px;font-size:12px;cursor:pointer"
                    (click)="toggleMois(m.num)">
                    {{ m.label }}
                    @if (m.statut === 'SOLDE') { ✓ }
                    @else if (m.statut === 'PARTIEL') {
                      <span class="mois-reste" [style.color]="moisSelected(m.num) ? '#06281f' : '#f59e0b'">
                        reste {{ m.reste | number:'1.0-0' }}
                      </span>
                    }
                  </button>
                }
              </div>
            </div>
          }

          <div class="montants-grid">
            <div class="form-group">
              <label>Mensualité
                @if (saisieDonnees()!.fees_nets.mensualite > 0) {
                  <span class="fee-hint">Tarif : {{ saisieDonnees()!.fees_nets.mensualite | number:'1.0-0' }}</span>
                }
              </label>
              <p-inputNumber [(ngModel)]="form.montant_mensualite" [min]="0" mode="decimal" styleClass="w-full" />
            </div>
            <div class="form-group">
              <label>Divers</label>
              <p-inputNumber [(ngModel)]="form.montant_divers" [min]="0" mode="decimal" styleClass="w-full" />
            </div>
          </div>

        }

        <!-- Services abonnés du contexte : uniques « à l'inscription » en type
             INSCRIPTION, mensuels + uniques du mois coché en type MENSUALITE -->
        @if (form.services.length) {
          <div class="form-group full" style="margin-top:6px">
            <label>Services / Activités abonnés
              @if (typePaiement === 'MENSUALITE' && form.mois_regles.length > 1) {
                <span class="fee-hint">mensuels × {{ form.mois_regles.length }} mois</span>
              }
            </label>
            <div style="display:flex;flex-direction:column;gap:6px;margin-top:4px">
              @for (sv of form.services; track sv.id) {
                <div style="display:flex;align-items:center;gap:8px">
                  <p-checkbox [(ngModel)]="sv.inclus" [binary]="true"
                              (onChange)="onToggleService(sv)" />
                  <span style="flex:1;font-size:13px;color:var(--text)">{{ sv.nom }}</span>
                  <p-inputNumber [(ngModel)]="sv.montant" [min]="0" mode="decimal"
                                 [disabled]="!sv.inclus" styleClass="w-32" inputStyleClass="text-right" />
                </div>
              }
            </div>
          </div>
        }

        <!-- Reliquat d'une année antérieure — encaissable sur le même reçu,
             quel que soit le type de paiement. Il solde une créance reportée :
             il ne constate aucun produit de l'année en cours. -->
        @if (saisieDonnees()!.reliquat.restant > 0) {
          <div class="form-group full reliquat-box">
            <label>
              🔁 Reliquat {{ saisieDonnees()!.reliquat.annee }}
              <span class="fee-hint">Restant dû : {{ saisieDonnees()!.reliquat.restant | number:'1.0-0' }}</span>
            </label>
            <p-inputNumber [(ngModel)]="form.montant_reliquat" [min]="0"
                           [max]="saisieDonnees()!.reliquat.restant"
                           mode="decimal" styleClass="w-full" />
            <div class="reliquat-aide">
              Dette de l'année précédente reportée à l'ouverture de l'exercice.
            </div>
          </div>
        }

        <!-- Ce que l'école réclame pour cette échéance. Ce bloc ne bouge PAS
             quand on change les montants encaissés : le dû est le dû, le versé
             est le versé. Les confondre, c'est annoncer « soldé » à une famille
             qui vient de régler la moitié du mois. -->
        @if (duSaisie().net > 0) {
          <div class="du-box">
            <div class="du-titre">Dû — {{ libelleEcheance() }}</div>
            @if (duSaisie().pec > 0) {
              <div class="du-row"><span>Dû réel</span>
                <span class="mono">{{ duSaisie().brut | number:'1.0-0' }}</span></div>
              <div class="du-row"><span>Prise en charge</span>
                <span class="mono pec-part">− {{ duSaisie().pec | number:'1.0-0' }}</span></div>
            }
            <!-- Ce qui reste des périodes précédentes. Une famille qui a réglé
                 100 000 sur 185 000 d'inscription doit encore 85 000, et cette
                 somme se réclame au passage suivant — pas dans un suivi séparé
                 qu'il faudrait penser à consulter. -->
            @if (reliquatSaisie() > 0) {
              <div class="du-row"><span>dont reliquat — {{ libelleReliquat() }}</span>
                <span class="mono" style="color:#f97316">{{ reliquatSaisie() | number:'1.0-0' }}</span></div>
            }
            <div class="du-row"><span>Montant réel à payer</span>
              <span class="mono">{{ duSaisie().net | number:'1.0-0' }}</span></div>
            @if (duSaisie().verse > 0) {
              <div class="du-row"><span>Déjà versé</span>
                <span class="mono success">− {{ duSaisie().verse | number:'1.0-0' }}</span></div>
            }
            <div class="du-row du-total"><span>Reste à payer</span>
              <strong class="mono">{{ duSaisie().reste | number:'1.0-0' }} FCFA</strong></div>
          </div>
        }

        <!-- Ce qu'on encaisse vraiment, et ce qu'il restera. Le montant versé
             n'est pas une donnée de plus : c'est la somme des lignes ci-dessus,
             vue depuis le guichet. Le saisir les ventile (scolarité d'abord,
             services ensuite), les modifier le met à jour — un seul état, pas
             deux qui finissent par se contredire. -->
        <div class="total-bar verse-bar">
          <div class="verse-champ">
            <label>Montant versé</label>
            <p-inputNumber [(ngModel)]="montantVerse" [min]="0" mode="decimal"
                           styleClass="verse-input" inputStyleClass="text-right" />
          </div>
          <div class="verse-solde">
            @if (resteApresVersement() > 0) {
              <span class="verse-lib">Reste dû après ce paiement</span>
              <strong class="mono danger">{{ resteApresVersement() | number:'1.0-0' }} FCFA</strong>
            } @else if (resteApresVersement() < 0) {
              <span class="verse-lib">Avance au-delà de l'échéance</span>
              <strong class="mono" style="color:#f59e0b">{{ -resteApresVersement() | number:'1.0-0' }} FCFA</strong>
            } @else {
              <span class="verse-lib">Après ce paiement</span>
              <strong class="mono success">✅ Échéance soldée</strong>
            }
          </div>
        </div>

        <!-- Mode(s) de paiement -->
        <div class="form-group" style="margin-top:12px">
          <!-- Qui règle. Vide = la famille. Renseigné = un organisme verse la
               part qu'il prend en charge — c'est ce qui distingue « la famille
               est à jour » de « l'État a versé », deux situations qu'un même
               total confondrait. Affiché seulement si l'école a des
               organismes : inutile d'alourdir la saisie ailleurs. -->
          <div *ngIf="organismes().length" style="margin-bottom:10px">
            <label>Payé par</label>
            <p-select appendTo="body" [options]="organismes()" [(ngModel)]="form.organisme"
                      optionLabel="nom" optionValue="id" styleClass="w-full"
                      [showClear]="true" placeholder="La famille" />
            <small *ngIf="form.organisme" class="payeur-aide">
              Ce versement soldera la part de l'organisme, pas celle de la famille.
            </small>
          </div>

          <div style="display:flex;align-items:center;justify-content:space-between">
            <label style="margin:0">Mode de paiement *</label>
            <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-2);cursor:pointer">
              <input type="checkbox" [(ngModel)]="form.multi_mode" (change)="onToggleMultiMode()" />
              Multi-mode (plusieurs moyens)
            </label>
          </div>

          <p-select *ngIf="!form.multi_mode" [options]="modesPaiement" [(ngModel)]="form.mode_paiement"
                    optionLabel="label" optionValue="value"
                    placeholder="Choisir le mode..." styleClass="w-full" />

          <div *ngIf="form.multi_mode" style="margin-top:6px">
            <div *ngFor="let m of form.modes_reglement; let i = index"
                 style="display:flex;gap:8px;margin-bottom:6px;align-items:center">
              <p-select [options]="modesPaiement" [(ngModel)]="m.mode"
                        optionLabel="label" optionValue="value" placeholder="Mode..."
                        styleClass="w-full" [style]="{flex:'1'}" />
              <input pInputText type="number" [(ngModel)]="m.montant" placeholder="Montant"
                     style="width:130px;text-align:right" />
              <button type="button" class="mode-x" (click)="retirerModeLigne(i)"
                      [disabled]="form.modes_reglement.length <= 1" title="Retirer">✕</button>
            </div>
            <div style="display:flex;justify-content:space-between;align-items:center;margin-top:4px">
              <button type="button" class="mode-add" (click)="ajouterModeLigne()">+ Ajouter un mode</button>
              <span style="font-size:12px;font-family:monospace"
                    [style.color]="resteAVentiler() === 0 ? '#00d4aa' : '#f59e0b'">
                Reste à ventiler : {{ resteAVentiler() | number:'1.0-0' }} FCFA
              </span>
            </div>
          </div>
        </div>

        <div class="form-group" style="margin-top:10px">
          <label>Observations</label>
          <input pInputText [(ngModel)]="form.observations" class="w-full"
                 placeholder="Remarques éventuelles..." />
        </div>
      }

      <ng-template pTemplate="footer">
        <p-button label="Annuler" severity="secondary" (onClick)="dialogVisible=false" />
        <p-button label="💾 Enregistrer + Reçu" severity="success"
                  [loading]="saving()" [disabled]="!saisieDonnees() || totalForm() <= 0"
                  (onClick)="sauvegarder(true)" />
        <p-button label="Enregistrer" severity="success" [outlined]="true"
                  [loading]="saving()" [disabled]="!saisieDonnees() || totalForm() <= 0"
                  (onClick)="sauvegarder(false)" />
      </ng-template>
    </p-dialog>

    <!-- Dialog reçu aperçu -->
    <p-dialog header="🧾 Aperçu du Reçu" [(visible)]="recuVisible"
              [modal]="true" [style]="{width:'480px'}" [draggable]="false">
      <div class="recu" *ngIf="recuData()">
        <!-- Header reçu -->
        <div class="recu-header">
          <div class="recu-titre">{{ recuData().tenant_nom }}</div>
          <div class="recu-no">N° {{ recuData().no_piece }}</div>
          <div style="font-size:11px;color:var(--text-3);margin-top:2px">
            {{ recuData().date }} &nbsp;|&nbsp; Année {{ recuData().annee_scolaire }}
          </div>
        </div>

        <!-- Élève -->
        <div class="recu-section">👤 Élève</div>
        <div class="recu-row"><span>Nom complet</span><strong style="text-transform:uppercase">{{ recuData().eleve }}</strong></div>
        <div class="recu-row"><span>Matricule</span><span>{{ recuData().matricule }}</span></div>
        <div class="recu-row"><span>Section</span><span>{{ recuData().section }}</span></div>
        @if (recuData().nom_pere !== '—') {
          <div class="recu-row"><span>Père / Tuteur</span><span>{{ recuData().nom_pere }} — {{ recuData().telephone_pere }}</span></div>
        }
        @if (recuData().nom_mere !== '—') {
          <div class="recu-row"><span>Mère</span><span>{{ recuData().nom_mere }} — {{ recuData().telephone_mere }}</span></div>
        }

        <!-- Paiement -->
        <div class="recu-section" style="margin-top:10px">💰 Paiement</div>
        @for (ligne of recuData().lignes; track ligne[0]) {
          <div class="recu-row"><span>{{ ligne[0] }}</span><span>{{ ligne[1] | number:'1.0-0' }} FCFA</span></div>
        }
        <div class="recu-total"><span>Total encaissé</span><span>{{ recuData().total | number:'1.0-0' }} FCFA</span></div>
        <div class="recu-row" style="margin-top:4px"><span>Mode</span><span>{{ recuData().mode_label }}</span></div>
        <div *ngFor="let mr of recuData().modes_reglement" class="recu-row" style="font-size:11px;color:var(--text-2)">
          <span style="padding-left:10px">↳ {{ mr.mode_label }}</span><span>{{ mr.montant | number:'1.0-0' }} FCFA</span>
        </div>
        <div class="recu-row"><span>Caissier</span><span>{{ recuData().saisi_par }}</span></div>

        <!-- Suivi -->
        <div class="recu-section" style="margin-top:10px">📊 Suivi Financier</div>
        <div class="recu-row"><span>Total attendu</span><span class="mono">{{ recuData().total_attendu | number:'1.0-0' }} FCFA</span></div>
        <div class="recu-row"><span>Déjà versé (avant)</span><span class="mono success">{{ recuData().deja_paye_avant | number:'1.0-0' }} FCFA</span></div>
        <div class="recu-row"><span>Total versé après</span><span class="mono success">{{ recuData().total_paye_apres | number:'1.0-0' }} FCFA</span></div>
        <div class="recu-row">
          <span>Reste à payer</span>
          <strong [class.success]="recuData().reste_apres === 0" [class.danger]="recuData().reste_apres > 0">
            {{ recuData().reste_apres === 0 ? '✅ SOLDÉ' : (recuData().reste_apres | number:'1.0-0') + ' FCFA' }}
          </strong>
        </div>
      </div>
      <ng-template pTemplate="footer">
        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;justify-content:flex-end">
          <span style="font-size:12px;color:var(--text-3)">Format :</span>
          <p-select appendTo="body" [options]="formatsRecu" [(ngModel)]="recuFormat"
                    optionLabel="label" optionValue="value" styleClass="w-40" />
          <p-button label="📄 Télécharger PDF" severity="success"
                    icon="pi pi-download" (onClick)="telechargerRecuPdf()" />
          <p-button label="Fermer" severity="secondary" (onClick)="recuVisible=false" />
        </div>
      </ng-template>
    </p-dialog>

    </ng-container>
    <!-- === FIN ONGLET PAIEMENTS === -->

    <!-- === ONGLET CHARGES === -->
    <div *ngIf="onglet() === 'charges'">
      <div class="table-card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;padding:16px 16px 0">
          <div>
            <h3 style="margin:0;color:var(--text)">💸 Charges de l'exercice</h3>
            <span style="color:var(--text-3);font-size:12px">
              Total : {{ totalCharges() | number:'1.0-0' }} FCFA
            </span>
          </div>
          <div style="display:flex;gap:8px">
            <p-button label="📥 Importer Excel" severity="secondary" [outlined]="true"
                      (onClick)="importChargesVisible.set(true)" />
            <p-button label="+ Nouvelle charge" severity="danger" (onClick)="ouvrirDialogCharge()" />
          </div>
        </div>

        <app-import-charges-dialog [(visible)]="importChargesVisible"
                                   (importe)="chargerCharges()" />

        <!-- Recherche : libellé, n° de pièce ou compte. -->
        <div class="search-bar">
          <input pInputText [(ngModel)]="rechercheCharge" (ngModelChange)="onRechercheChargeChange()"
                 class="search-field" placeholder="🔍 Rechercher une charge — libellé, n° de pièce, compte…" />
          @if (rechercheCharge) {
            <button type="button" class="search-x" (click)="effacerRechercheCharge()"
                    title="Effacer">✕</button>
          }
        </div>

        <p-table [value]="charges()" [loading]="loadingCharges()"
                [paginator]="true" [rows]="20" styleClass="p-datatable-sm">
          <ng-template pTemplate="header">
            <tr>
              <th>Date</th>
              <th>N° Pièce</th>
              <th>Compte</th>
              <th>Libellé</th>
              <th align="right">Montant</th>
              <th></th>
            </tr>
          </ng-template>
          <ng-template pTemplate="body" let-c>
            <tr>
              <td>{{ c.date | date:'dd/MM/yyyy' }}</td>
              <td class="mono">{{ c.no_piece }}</td>
              <td class="mono">{{ c.no_compte }}</td>
              <td>
                {{ c.libelle }}
                @if (c.source === 'BUDGET') { <p-tag value="Budget" severity="info" [style]="{'font-size':'9px'}" /> }
                @if (c.source === 'PAIE')   { <p-tag value="Paie"   severity="warn" [style]="{'font-size':'9px'}" /> }
                <!-- Le poste consommé. Sans lui, impossible de savoir en lisant
                     la liste si une dépense pèse sur un budget ou non. -->
                @if (c.budget_ligne_libelle) {
                  <span class="imput-tag">🔗 {{ c.budget_ligne_libelle }}</span>
                }
              </td>
              <td class="mono danger" align="right">{{ c.montant | number:'1.0-0' }} FCFA</td>
              <td>
                <div style="display:flex;gap:4px">
                  <p-button icon="pi pi-paperclip" [rounded]="true" [text]="true" severity="info"
                            pTooltip="Pièces justificatives" (onClick)="ouvrirPieces('CHARGE', c.id, c.no_piece)" />
                  <!-- Les écritures de paie se corrigent dans le module RH, pas ici -->
                  @if (c.source !== 'PAIE') {
                    <p-button icon="pi pi-pencil" [rounded]="true" [text]="true" severity="warn"
                              pTooltip="Modifier (contre-écritures + nouvelle charge)" (onClick)="demanderModificationCharge(c)" />
                    <p-button icon="pi pi-times" [rounded]="true" [text]="true" severity="danger"
                              pTooltip="Annuler (contre-écritures SYSCOHADA)" (onClick)="supprimerCharge(c)" />
                  }
                </div>
              </td>
            </tr>
          </ng-template>
          <ng-template pTemplate="emptymessage">
            <tr><td colspan="6" class="empty-msg">Aucune charge enregistrée.</td></tr>
          </ng-template>
        </p-table>
      </div>

      <!-- Dialog Nouvelle Charge -->
      <p-dialog header="💸 Nouvelle Charge" [(visible)]="dialogChargeVisible"
                [modal]="true" [style]="{width:'460px'}" [draggable]="false">
        <div class="form-grid">
          <div class="form-group full">
            <label>Libellé *</label>
            <input pInputText [(ngModel)]="nouvelleCharge.libelle" class="w-full"
                  (ngModelChange)="onLibelleChargeChange()"
                  placeholder="Ex : Facture eau juillet..." />
            <small style="color:var(--text-3);font-size:10px">Le compte de charge se remplit automatiquement d'après le libellé</small>
          </div>
          <!-- Poste de budget consommé. Le budget se réglait sur le seul numéro
               de compte : une dépense imprévue sur un 6xx budgété passait pour
               du réalisé. Vide = hors budget, et c'est le cas normal. -->
          @if (lignesBudget().length) {
            <div class="form-group full">
              <label>Imputer au budget</label>
              <p-select appendTo="body" [options]="lignesBudget()" [(ngModel)]="nouvelleCharge.budget_ligne_id"
                        optionLabel="libelle" optionValue="id" styleClass="w-full"
                        [showClear]="true" [filter]="true" placeholder="— Hors budget —" />
              <small style="color:var(--text-3);font-size:10px">
                À laisser vide pour une dépense non budgétée.
              </small>
            </div>
          }
          <div class="form-group full">
            <label>Compte de charge *</label>
            <p-select appendTo="body" [options]="planChargesPC()" [(ngModel)]="nouvelleCharge.no_compte"
                      optionLabel="label" optionValue="value" styleClass="w-full" [filter]="true"
                      (onChange)="compteChargeVerrouille = true; onCompteChargeChange()" />
            @if (compteSuggere) {
              <small style="color:#00d4aa;font-size:10px">🪄 Suggéré d'après le libellé — modifiable si besoin</small>
            }
          </div>
          <div class="form-group">
            <label>Montant (FCFA) *</label>
            <p-inputNumber [(ngModel)]="nouvelleCharge.montant" [min]="0"
                          mode="decimal" styleClass="w-full" />
          </div>
          <div class="form-group">
            <label>Date</label>
            <input pInputText type="date" [(ngModel)]="nouvelleCharge.date" class="w-full" />
          </div>
          <div class="form-group full">
            <label>Compte fournisseur</label>
            <p-select appendTo="body" [options]="planFournisseurs" [(ngModel)]="nouvelleCharge.compte_fournisseur"
                      optionLabel="label" optionValue="value" styleClass="w-full" />
          </div>
          <div class="form-group full">
            <div style="display:flex;align-items:center;justify-content:space-between">
              <label style="margin:0">Réglé via</label>
              <label style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--text-2);cursor:pointer">
                <input type="checkbox" [(ngModel)]="nouvelleCharge.multi_mode" (change)="onToggleMultiCharge()" />
                Multi-mode
              </label>
            </div>
            <p-select *ngIf="!nouvelleCharge.multi_mode" appendTo="body" [options]="comptesCredit"
                      [(ngModel)]="nouvelleCharge.compte_credit"
                      optionLabel="label" optionValue="value" styleClass="w-full" />
            <div *ngIf="nouvelleCharge.multi_mode" style="margin-top:6px">
              <div *ngFor="let m of nouvelleCharge.modes_reglement; let i = index"
                   style="display:flex;gap:8px;margin-bottom:6px;align-items:center">
                <p-select appendTo="body" [options]="modesPaiement" [(ngModel)]="m.mode"
                          optionLabel="label" optionValue="value" placeholder="Mode..."
                          styleClass="w-full" [style]="{flex:'1'}" />
                <input pInputText type="number" [(ngModel)]="m.montant" placeholder="Montant"
                       style="width:120px;text-align:right" />
                <button type="button" class="mode-x" (click)="retirerModeCharge(i)"
                        [disabled]="nouvelleCharge.modes_reglement.length <= 1">✕</button>
              </div>
              <div style="display:flex;justify-content:space-between;align-items:center;margin-top:4px">
                <button type="button" class="mode-add" (click)="ajouterModeCharge()">+ Ajouter un mode</button>
                <span style="font-size:12px;font-family:monospace"
                      [style.color]="chargeReste() === 0 ? '#00d4aa' : '#f59e0b'">
                  Reste : {{ chargeReste() | number:'1.0-0' }} FCFA
                </span>
              </div>
            </div>
          </div>
          @if (ressourcesGouv().length) {
            <div class="form-group full">
              <label>Financé par (ressource)</label>
              <p-select appendTo="body" [options]="ressourcesGouv()" [(ngModel)]="nouvelleCharge.ressource_id"
                        optionLabel="libelle" optionValue="id" styleClass="w-full" [showClear]="true"
                        placeholder="— Trésorerie générale —" [filter]="true" />
              <small style="color:var(--text-3);font-size:10px">Contrôle automatique du disponible sur l'enveloppe</small>
            </div>
          }
          @if (projetsGouv().length) {
            <div class="form-group full">
              <label>Projet (analytique)</label>
              <p-select appendTo="body" [options]="projetsGouv()" [(ngModel)]="nouvelleCharge.projet_id"
                        optionLabel="libelle" optionValue="id" styleClass="w-full" [showClear]="true"
                        placeholder="— Aucun —" [filter]="true" />
            </div>
          }
        </div>
        <ng-template pTemplate="footer">
          <p-button label="Annuler"       severity="secondary" (onClick)="dialogChargeVisible=false" />
          <p-button label="Enregistrer"   severity="danger"
                    [loading]="savingCharge()" (onClick)="sauvegarderCharge()" />
        </ng-template>
      </p-dialog>

      <!-- Dialog Pièces justificatives (GED) d'une charge -->
      <p-dialog [header]="'📎 Pièces justificatives — ' + piecesTitre()"
                [(visible)]="dialogPiecesVisible" [modal]="true" [style]="{width:'520px'}" [draggable]="false">
        <app-pieces-justificatives [objetType]="piecesObjetType()" [objetId]="piecesObjetId()" />
        <ng-template pTemplate="footer">
          <p-button label="Fermer" severity="secondary" (onClick)="dialogPiecesVisible=false" />
        </ng-template>
      </p-dialog>

      <!-- Dialog modification charge -->
      <p-dialog header="✏️ Modifier la charge" [(visible)]="dialogModifChargeVisible"
                [modal]="true" [style]="{width:'460px'}" [draggable]="false">
        <div *ngIf="chargeModifier" class="form-grid">
          <div class="form-group full">
            <div style="background:var(--surface-4);border-radius:6px;padding:10px;border-left:4px solid #f59e0b;font-size:12px;color:var(--text-2)">
              Original : <strong style="color:#f59e0b">{{ chargeModifier.no_piece }}</strong> —
              {{ chargeModifier.libelle }} · {{ chargeModifier.montant | number:'1.0-0' }} FCFA
            </div>
          </div>
          <div class="form-group full">
            <label>Compte de charge *</label>
            <p-select appendTo="body" [options]="planChargesPC()" [(ngModel)]="modifChargeForm.no_compte"
                      optionLabel="label" optionValue="value" styleClass="w-full" [filter]="true" />
          </div>
          <div class="form-group full">
            <label>Libellé *</label>
            <input pInputText [(ngModel)]="modifChargeForm.libelle" class="w-full" />
          </div>
          <div class="form-group">
            <label>Montant (FCFA) *</label>
            <p-inputNumber [(ngModel)]="modifChargeForm.montant" [min]="0" mode="decimal" styleClass="w-full" />
          </div>
          <div class="form-group">
            <label>Date</label>
            <input pInputText type="date" [(ngModel)]="modifChargeForm.date" class="w-full" />
          </div>
          <div class="form-group full">
            <label>Réglé via</label>
            <p-select appendTo="body" [options]="comptesCredit" [(ngModel)]="modifChargeForm.compte_credit"
                      optionLabel="label" optionValue="value" styleClass="w-full" />
          </div>
        </div>
        <ng-template pTemplate="footer">
          <p-button label="Annuler" severity="secondary" (onClick)="dialogModifChargeVisible=false" />
          <p-button label="✏️ Enregistrer la modification" severity="warn"
                    [loading]="savingModifCharge()" (onClick)="confirmerModificationCharge()" />
        </ng-template>
      </p-dialog>
    </div>
    <!-- === FIN ONGLET CHARGES === -->
  `,
  styles: [`
    .page-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:20px; }
    .page-title  { font-size:20px; font-weight:600; color:var(--text); margin:0 0 4px; }
    .page-sub    { font-size:12px; color:var(--text-3); }

    .modes-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:12px; margin-bottom:20px; }
    .mode-card  { background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:14px; text-align:center; }
    .mode-name  { font-size:11px; color:var(--text-3); text-transform:uppercase; letter-spacing:1px; margin-bottom:4px; }
    .mode-total { font-size:20px; font-weight:700; font-family:monospace; color:#00d4aa; }
    .mode-nb    { font-size:11px; color:var(--text-3); margin-top:2px; }
    .mode-x     { background:#3a1e2d; border:1px solid #5f2a3f; color:#f87171; border-radius:6px; width:30px; height:34px; cursor:pointer; flex:none; }
    .mode-x:disabled { opacity:.4; cursor:not-allowed; }
    .mode-add   { background:transparent; border:1px dashed var(--border); color:#4fc3f7; border-radius:6px; padding:5px 10px; font-size:12px; cursor:pointer; }

    .table-card { background:var(--surface); border:1px solid var(--border); border-radius:12px; overflow:hidden; }

    ::ng-deep .p-datatable .p-datatable-thead > tr > th { background:var(--surface-2) !important; color:var(--text-3) !important; font-size:11px !important; text-transform:uppercase !important; border-color:var(--border) !important; }
    ::ng-deep .p-datatable .p-datatable-tbody > tr { background:var(--surface) !important; color:var(--text-2) !important; border-bottom:1px solid rgba(42,63,95,0.4) !important; }
    ::ng-deep .p-datatable .p-datatable-tbody > tr:hover { background:var(--surface-hover) !important; }

    .mono        { font-family:monospace; font-size:12px; }
    .bold        { font-weight:600; color:var(--text); }
    .success     { color:#10b981; }
    .annule-val  { color:#ef4444; text-decoration:line-through; opacity:0.7; }
    .btn-row     { display:flex; gap:4px; align-items:center; }
    .empty-msg   { text-align:center; padding:40px; color:var(--text-3); }
    ::ng-deep .ligne-annulee td { opacity:0.55 !important; background:rgba(239,68,68,0.04) !important; }

    .eleve-info { background:var(--pos-bg); border:1px solid #2a5c2a; border-radius:8px; padding:12px; margin-bottom:14px; }
    .ei-row { display:flex; justify-content:space-between; font-size:12px; padding:4px 0; border-bottom:1px solid rgba(42,95,42,0.3); }
    .ei-row:last-child { border-bottom:none; }
    .ei-row span:first-child { color:var(--text-3); }
    .ei-row span:last-child  { font-weight:500; color:var(--text); font-family:monospace; }

    .montants-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
    .form-group { display:flex; flex-direction:column; gap:6px; }
    .form-group label { font-size:12px; color:var(--text-2); text-transform:uppercase; letter-spacing:0.5px; }

    .total-bar { display:flex; justify-content:space-between; align-items:center; background:rgba(0,212,170,0.1); border:1px solid rgba(0,212,170,0.2); border-radius:8px; padding:10px 16px; margin-top:14px; }
    .total-val { font-size:20px; font-weight:700; color:#00d4aa; font-family:monospace; }

    .recu { color:var(--text); }
    .recu-header { text-align:center; margin-bottom:16px; }
    .recu-titre { font-size:16px; font-weight:700; color:#00d4aa; }
    .recu-no    { font-size:12px; color:var(--text-3); font-family:monospace; margin-top:4px; }
    .recu-row   { display:flex; justify-content:space-between; font-size:13px; padding:5px 0; border-bottom:1px solid rgba(42,63,95,0.3); }
    .recu-row span:first-child { color:var(--text-3); }
    .recu-total   { display:flex; justify-content:space-between; font-size:14px; font-weight:700; padding:6px 0; color:#00d4aa; border-top:1px solid var(--border); margin-top:4px; }
    .recu-section { font-size:10px; font-weight:700; color:#00d4aa; text-transform:uppercase; letter-spacing:.5px; padding:6px 0 2px; border-bottom:1px solid var(--border); }
    .fee-hint { font-size:10px; color:#00d4aa; margin-left:6px; font-weight:400; font-style:italic; }
    /* Encart reliquat — orange, pour ne pas le confondre avec les frais de
       l'année en cours (turquoise). */
    .reliquat-box { border:1px solid rgba(249,115,22,0.35); background:rgba(249,115,22,0.07);
                    border-radius:8px; padding:10px 12px; margin-top:10px; }
    .reliquat-box .fee-hint { color:#f97316; }
    .reliquat-aide { font-size:11px; color:var(--text-3); margin-top:5px; }
    /* Prise en charge — violet, comme partout ailleurs dans l'application. */
    .pec-box   { border:1px solid #7c3aed; background:rgba(124,58,237,0.1);
                 border-radius:6px; padding:9px 14px; margin-bottom:10px; }
    .pec-titre { font-size:12px; color:#a78bfa; margin-bottom:7px; }
    .pec-grille{ display:grid; grid-template-columns:1fr auto auto auto; gap:3px 14px;
                 align-items:baseline; }
    .pec-th    { font-size:9px; text-transform:uppercase; letter-spacing:.4px;
                 color:var(--text-3); text-align:right; }
    .pec-lib   { font-size:12px; color:var(--text-2); }
    .pec-grille .mono, .pec-grille strong { text-align:right; }
    .pec-part  { color:#a78bfa; }
    .pec-aide  { font-size:10px; color:var(--text-3); margin-top:6px; font-style:italic; }
    /* Reste d'un mois entamé, sur son bouton. */
    .mois-reste { font-size:10px; margin-left:4px; font-family:monospace; }
    /* Ce que l'école réclame pour l'échéance en cours. */
    .du-box   { border:1px solid var(--border); background:var(--surface);
                border-radius:8px; padding:10px 14px; margin-top:14px; }
    .du-titre { font-size:10px; text-transform:uppercase; letter-spacing:.5px;
                color:var(--text-3); margin-bottom:6px; }
    .du-row   { display:flex; justify-content:space-between; align-items:baseline;
                font-size:12px; padding:2px 0; color:var(--text-2); }
    .du-total { border-top:1px solid var(--border); margin-top:5px; padding-top:6px;
                color:var(--text); }
    .du-total strong { font-size:15px; }
    /* Le versement réel, en face du reste. */
    .verse-bar   { align-items:flex-end; gap:16px; }
    .verse-champ { display:flex; flex-direction:column; gap:5px; }
    .verse-champ label { font-size:10px; text-transform:uppercase; letter-spacing:.5px;
                         color:var(--text-2); }
    ::ng-deep .verse-input input { font-size:18px !important; font-weight:700 !important;
                                   max-width:150px; }
    .verse-solde { display:flex; flex-direction:column; align-items:flex-end; gap:3px; }
    .verse-lib   { font-size:10px; text-transform:uppercase; letter-spacing:.5px;
                   color:var(--text-3); }
    .verse-solde strong { font-size:16px; }
    /* Recherche élève */
    .search-eleve-wrap { margin-bottom:14px; }
    .search-label      { display:block; font-size:12px; color:var(--text-2); text-transform:uppercase; letter-spacing:.3px; margin-bottom:6px; }
    .search-hint       { font-size:10px; color:var(--text-5); text-transform:none; margin-left:6px; }
    .search-input-field{ background:var(--surface-2); border:1px solid var(--border); color:var(--text); border-radius:6px; padding:9px 12px; font-size:13px; outline:none; }
    .search-input-field:focus { border-color:#00d4aa; }
    .search-spinner    { position:absolute; right:12px; top:10px; color:#00d4aa; font-size:14px; animation:spin 1s linear infinite; }
    @keyframes spin { to { transform:rotate(360deg); } }
    .suggestions-list  { border:1px solid var(--border); border-radius:6px; background:var(--surface); margin-top:4px; max-height:260px; overflow-y:auto; }
    .suggestion-item   { padding:10px 14px; cursor:pointer; border-bottom:1px solid rgba(42,63,95,0.5); }
    .suggestion-item:last-child { border-bottom:none; }
    .suggestion-item:hover { background:var(--surface-2); }
    .si-top    { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:3px; }
    .si-nom    { color:var(--text); font-size:13px; font-weight:600; }
    .si-matricule { font-family:monospace; font-size:11px; background:var(--surface-2); color:#00d4aa; padding:1px 6px; border-radius:3px; }
    .si-bottom { font-size:11px; color:var(--text-3); display:flex; gap:8px; flex-wrap:wrap; }
    .badge-statut { font-size:9px; padding:1px 5px; border-radius:3px; font-weight:600; }
    .badge-statut.rouge  { background:#ef4444; color:white; }
    .badge-statut.orange { background:#f59e0b; color:white; }
    .badge-statut.violet { background:#7c3aed; color:white; }
    .search-empty { font-size:12px; color:var(--text-3); padding:10px 14px; border:1px solid var(--border); border-radius:6px; margin-top:4px; text-align:center; }
    .eleve-selected { display:flex; justify-content:space-between; align-items:center; background:var(--surface-2); border:1px solid #00d4aa; border-radius:6px; padding:10px 14px; }
    .es-info    { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
    .es-nom     { color:var(--text); font-size:13px; font-weight:700; }
    .es-section { font-size:11px; color:var(--text-3); }
    .btn-changer{ background:transparent; border:1px solid var(--text-5); color:var(--text-2); border-radius:5px; padding:4px 10px; font-size:11px; cursor:pointer; }
    .btn-changer:hover { border-color:#ef4444; color:#ef4444; }
    .type-btn { flex:1; padding:10px; border:1px solid var(--border); border-radius:8px; background:var(--surface-2); color:var(--text-3); cursor:pointer; font-size:13px; transition:all 0.2s; }
    .type-btn:hover { border-color:#00d4aa; color:var(--text); }
    .active-inscr { background:rgba(245,158,11,0.15); border-color:#f59e0b; color:#f59e0b; font-weight:600; }
    .active-mens  { background:rgba(0,212,170,0.15);  border-color:#00d4aa; color:#00d4aa; font-weight:600; }
    .tabs-bar { display:flex; gap:4px; margin-bottom:16px; }
    .tab-btn  { padding:8px 18px; border:1px solid var(--border); border-radius:8px; background:transparent; color:var(--text-3); cursor:pointer; font-size:13px; transition:all 0.15s; }
    .tab-btn:hover  { border-color:#00d4aa; color:var(--text); }
    .tab-btn.active { background:rgba(0,212,170,0.1); border-color:#00d4aa; color:#00d4aa; font-weight:600; }
    .danger { color:#ef4444; }
    .form-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
    .full { grid-column:1/-1; }
  
    .payeur-aide { display:block; margin-top:4px; font-size:10px; color:#f59e0b; }
    /* Recherche en tête de liste (règlements, charges). */
    .search-bar   { display:flex; align-items:center; gap:6px; padding:0 16px 12px; }
    .search-field { flex:1; background:var(--surface-2); border:1px solid var(--border);
                    color:var(--text); border-radius:6px; padding:8px 12px; font-size:13px; }
    .search-x     { background:none; border:none; color:var(--text-3); cursor:pointer;
                    font-size:14px; padding:4px 8px; }
    .search-x:hover { color:var(--text); }
    /* Poste de budget consommé par une charge. */
    .imput-tag    { font-size:10px; color:#4fc3f7; margin-left:6px; white-space:nowrap; }
`]
})
export class PaiementsComponent implements OnInit {
  onglet = signal('paiements');

  // ── Paiements scolarité ─────────────────────────────────────────────────────
  paiements         = signal<any[]>([]);
  stats             = signal<any>(null);
  elevesSuggestions = signal<any[]>([]);
  loading           = signal(true);
  saving            = signal(false);
  savingAnnul       = signal(false);
  savingModif       = signal(false);
  loadingSaisie     = signal(false);
  loadingRecherche  = signal(false);

  // ── Charges ─────────────────────────────────────────────────────────────────
  charges              = signal<any[]>([]);
  loadingCharges       = signal(false);
  savingCharge         = signal(false);
  savingModifCharge    = signal(false);
  dialogChargeVisible  = false;
  dialogModifChargeVisible = false;
  chargeModifier: any  = null;
  modifChargeForm      = { no_compte: '', libelle: '', montant: 0, date: '', compte_credit: '571' };
  nouvelleCharge: any  = { no_compte: '661', libelle: '', montant: 0, date: new Date().toISOString().split('T')[0], compte_credit: '571', compte_fournisseur: '401', ressource_id: null, projet_id: null };
  // Dimensions analytiques gouvernance (facultatives) — proposées à la saisie d'une charge.
  ressourcesGouv = signal<any[]>([]);
  projetsGouv    = signal<any[]>([]);

  // Comptes de charge chargés depuis le plan comptable (classe 6 uniquement, sans immobilisations)
  planChargesData = signal<any[]>([]);
  planFournisseurs = [
    { label: '401 — Fournisseurs (dettes en compte)',            value: '401' },
    { label: '404 — Fournisseurs, acquisitions immobilisations', value: '404' },
    { label: '481 — Fournisseurs d\'immobilisations',            value: '481' },
  ];
  comptesCredit = [
    { label: '571  — Caisse',       value: '571' },
    { label: '521  — Banque',       value: '521' },
    { label: '5521 — WAVE',         value: '5521' },
    { label: '5522 — Orange Money', value: '5522' },
    { label: '5523 — Free Money',   value: '5523' },
  ];

  planChargesPC = computed(() =>
    this.planChargesData()
      .filter(c => c.type === 'CHARGE' && c.est_actif && c.row_type !== 'CLASSE' && c.no_compte)
      .map(c => ({ label: `${c.no_compte} — ${c.libelle}`, value: c.no_compte }))
  );
  comptesFournisseursPC = computed(() => this.planFournisseurs);
  comptesCreditPC = computed(() => this.comptesCredit);
  confirmAnnulVisible = false;
  paiementAnnuler: any = null;
  modifVisible      = false;
  paiementModifier: any = null;

  modifForm = {
    montant_inscription: 0, montant_mensualite: 0, montant_uniforme: 0,
    montant_fournitures: 0, montant_cantine: 0,    montant_divers: 0,
    montant_reliquat: 0,
    mode_paiement: '', observations: '',
  };
  dialogVisible     = false;
  recuVisible       = false;
  recuData          = signal<any>(null);
  recuFormat        = 'A5';
  formatsRecu = [
    { label: 'A5 (demi-A4)',     value: 'A5' },
    { label: 'A4 (page entière)', value: 'A4' },
    { label: '80 mm (thermique)', value: '80mm' },
  ];
  saisieDonnees     = signal<any | null>(null);
  eleveSelectionne: any = null;
  rechercheInput    = '';
  private _searchTimer: any = null;
  exerciceId        = '';
  typePaiement: 'INSCRIPTION' | 'MENSUALITE' = 'MENSUALITE';

  form = {
    montant_inscription: 0,
    montant_mensualite:  0,
    montant_uniforme:    0,
    montant_fournitures: 0,
    montant_cantine:     0,
    montant_divers:      0,
    // Part affectée au reliquat d'un exercice antérieur. Comptée dans
    // totalForm() (qui somme tous les champs montant_*) et donc dans la
    // ventilation multi-mode, puisqu'elle est bien encaissée.
    montant_reliquat:    0,
    mois_regles:         [] as number[],
    // `du` = ce que le service coûte dans ce contexte (tarif × mois cochés pour
    // un service mensuel) ; `montant` = ce qu'on en encaisse. Deux champs, parce
    // que ce sont deux choses : un versement partiel les sépare.
    services:            [] as { id: string; nom: string; periodicite: string;
                                 tarif: number; du: number; montant: number;
                                 inclus: boolean }[],
    mode_paiement:       '',
    // Paiement multi-mode : un même règlement réparti sur plusieurs modes.
    multi_mode:          false,
    modes_reglement:     [] as { mode: string; montant: number }[],
    observations:        '',
    // Qui règle : null = la famille, sinon l'organisme qui verse sa part.
    organisme:           null as string | null,
  };

  private translate = inject(TranslateService);
  private gouv = inject(GouvernanceService);

  modesPaiement: any[] = [];

  /** Organismes payeurs actifs de l'école. Vide chez la plupart : le
   *  sélecteur n'apparaît alors pas du tout. */
  organismes = signal<{ id: string; nom: string }[]>([]);

  constructor(
    private paiementsService: PaiementsService,
    private elevesService: ElevesService,
    private compta: ComptabiliteService,
    private msg: MessageService
  ) {}

  ngOnInit() {
    this.modesPaiement = [
      { label: this.translate.instant('paiements.espece'),       value: 'ESPECE' },
      { label: this.translate.instant('paiements.wave'),         value: 'WAVE' },
      { label: this.translate.instant('paiements.orange_money'), value: 'ORANGE_MONEY' },
      { label: this.translate.instant('paiements.free_money'),   value: 'FREE_MONEY' },
      { label: this.translate.instant('paiements.virement'),     value: 'VIREMENT' },
      { label: this.translate.instant('paiements.cheque'),       value: 'CHEQUE' },
    ];
    this.chargerPaiements();
    this.chargerStats();
    this.chargerExercice();
    this.chargerPlanCharges();
    this.chargerOrganismes();
  }

  private chargerOrganismes() {
    this.elevesService.getOrganismes().subscribe({
      next: (l) => this.organismes.set(
        l.filter(o => o.actif).map(o => ({ id: o.id, nom: o.nom }))),
      // Silencieux : une école sans organisme n'a pas à voir une erreur pour
      // une fonctionnalité qu'elle n'utilise pas.
      error: () => this.organismes.set([]),
    });
  }

  chargerPlanCharges() {
    // Comptes de charge depuis le plan comptable (classe 6 uniquement)
    this.compta.getPlanComptable({ type: 'CHARGE' }).subscribe({
      next: res => this.planChargesData.set(Array.isArray(res) ? res : ((res as any).results || []))
    });
  }

  // ── Recherche d'un règlement ───────────────────────────────────────────
  recherchePaiement = '';
  private _timerPaiement: any = null;

  onRecherchePaiementChange() {
    clearTimeout(this._timerPaiement);
    this._timerPaiement = setTimeout(() => this.chargerPaiements(), 300);
  }

  effacerRecherchePaiement() {
    this.recherchePaiement = '';
    this.chargerPaiements();
  }

  chargerPaiements() {
    this.loading.set(true);
    const q = this.recherchePaiement.trim();
    this.paiementsService.getPaiements(q ? { q } : undefined).subscribe({
      next: res => { 
          const data = Array.isArray(res) ? res : (res.results || []);
          this.paiements.set(data); 
          this.loading.set(false); 
      },
      error: () => this.loading.set(false)
    });
  }

  chargerStats() {
    this.paiementsService.getStats().subscribe({
      next: res => this.stats.set(res)
    });
  }

  chargerExercice() {
    this.paiementsService.getExerciceActif().subscribe({
      next: res => {
        const exercices = res.results || res;
        if (exercices.length > 0) this.exerciceId = exercices[0].id;
      }
    });
  }

  onRechercheChange(q: string) {
    clearTimeout(this._searchTimer);
    this.elevesSuggestions.set([]);
    if (!q || q.trim().length < 2) return;
    this._searchTimer = setTimeout(() => {
      this.loadingRecherche.set(true);
      this.elevesService.searchEleves(q.trim()).subscribe({
        next:  res => { this.elevesSuggestions.set(Array.isArray(res) ? res : []); this.loadingRecherche.set(false); },
        error: ()  => this.loadingRecherche.set(false),
      });
    }, 300);
  }

  selectionnerEleve(e: any) {
    this.eleveSelectionne = e;
    this.rechercheInput   = '';
    this.elevesSuggestions.set([]);
    this.saisieDonnees.set(null);
    this.resetForm();
    // Charger les données de saisie calculées
    this.loadingSaisie.set(true);
    this.elevesService.getSaisiePaiement(e.id).subscribe({
      next: data => {
        this.saisieDonnees.set(data);
        this.loadingSaisie.set(false);
        if (data.exercice_id) this.exerciceId = data.exercice_id;
        this.appliquerAutoRemplissage(data);
      },
      error: () => this.loadingSaisie.set(false),
    });
  }

  changerEleve() {
    this.eleveSelectionne = null;
    this.rechercheInput   = '';
    this.elevesSuggestions.set([]);
    this.saisieDonnees.set(null);
    this.resetForm();
  }

  // Compatibilité avec ancien code (non utilisé mais garde la cohérence)
  rechercherEleve(event: any) { this.onRechercheChange(event?.query || ''); }
  onEleveSelect(event: any)   { this.selectionnerEleve(event?.value ?? event); }
  onEleveClear()              { this.changerEleve(); }

  private appliquerAutoRemplissage(data: any) {
    if (this.typePaiement === 'INSCRIPTION') {
      this.form.montant_mensualite   = 0;
      this.form.montant_cantine      = 0;
      this.form.mois_regles          = [];
    } else {
      // Tous les mois ÉCHUS non soldés, pas seulement le premier : un reliquat
      // se réclame au passage suivant, il ne s'oublie pas jusqu'à ce que la
      // famille repasse. Le caissier peut décocher ce qu'elle ne règle pas.
      const echus = (data.mois_ecole || [])
        .filter((m: any) => m.du && m.reste > 0 && m.echu)
        .map((m: any) => m.num);
      // À défaut d'arriéré, le prochain mois à solder.
      const ouverts = (data.mois_ecole || []).filter((m: any) => m.du && m.reste > 0);
      this.form.mois_regles = echus.length ? echus
                            : (ouverts.length ? [ouverts[0].num] : []);
      // Frais d'entrée partiellement réglés : leur reliquat se réclame avec la
      // mensualité, sur le même reçu. Il n'apparaissait nulle part au guichet.
      this.form.montant_inscription  = data.arrieres?.entree?.reste || 0;
      this.form.montant_uniforme     = 0;
      this.form.montant_fournitures  = 0;
    }
    this.form.montant_divers = 0;
    this.construireServices();
    this.proposerLeResteDu();
  }

  /** Pré-remplit le versement avec ce qu'il reste réellement à payer sur
   *  l'échéance — acomptes déjà encaissés déduits. */
  private proposerLeResteDu() {
    this.montantVerse = this.duSaisie().reste
                      + (Number(this.form.montant_reliquat) || 0)
                      + (Number(this.form.montant_divers) || 0);
  }

  // Services abonnés proposés selon le contexte du paiement :
  // - UNIQUE « à l'inscription » (mois_unique null) → uniquement en type INSCRIPTION
  // - UNIQUE « mois X » → uniquement si le mois X fait partie des mois réglés
  // - MENSUEL → mensualités, montant = tarif × nb mois sélectionnés
  private construireServices() {
    const data = this.saisieDonnees();
    if (!data) { this.form.services = []; return; }
    const inclusAvant = new Map((this.form.services || []).map(s => [s.id, s.inclus]));
    const tous = data.services || [];
    let retenus: any[];
    if (this.typePaiement === 'INSCRIPTION') {
      retenus = tous
        .filter((s: any) => s.periodicite === 'UNIQUE' && !s.mois_unique)
        .map((s: any) => ({ id: s.id, nom: s.nom, periodicite: 'UNIQUE',
                            tarif: s.montant || 0, du: Math.round(s.montant || 0) }));
    } else {
      const nb = this.form.mois_regles.length;
      retenus = [
        ...tous.filter((s: any) => s.periodicite === 'MENSUEL')
               .map((s: any) => ({ id: s.id, nom: s.nom, periodicite: 'MENSUEL',
                                   tarif: s.montant || 0, du: Math.round((s.montant || 0) * nb) })),
        ...tous.filter((s: any) => s.periodicite === 'UNIQUE' && s.mois_unique &&
                                   this.form.mois_regles.includes(s.mois_unique))
               .map((s: any) => ({ id: s.id, nom: s.nom, periodicite: 'UNIQUE',
                                   tarif: s.montant || 0, du: Math.round(s.montant || 0) })),
      ];
    }
    this.form.services = retenus.map(s => ({ ...s, montant: s.du,
                                             inclus: inclusAvant.get(s.id) ?? true }));
  }

  /** Recocher un service en repropose le tarif : après une ventilation qui l'a
   *  laissé à zéro, il rentrerait sinon dans le reçu pour rien. */
  onToggleService(sv: { du: number; montant: number; inclus: boolean }) {
    if (sv.inclus && !Number(sv.montant)) sv.montant = sv.du;
  }

  servicesTotal(): number {
    return (this.form.services || [])
      .filter(s => s.inclus)
      .reduce((a, s) => a + (Number(s.montant) || 0), 0);
  }

  moisSelected(num: number): boolean {
    return this.form.mois_regles.includes(num);
  }

  toggleMois(num: number) {
    const i = this.form.mois_regles.indexOf(num);
    if (i >= 0) this.form.mois_regles.splice(i, 1);
    else        this.form.mois_regles.push(num);
    // Services : les mensuels suivent le nb de mois, les uniques « mois X »
    // n'apparaissent que si leur mois est coché
    this.construireServices();
    // Le montant proposé suit ce qui reste dû sur les mois cochés — acomptes
    // déduits. Il valait « tarif × nb de mois », ce qui réclamait une seconde
    // fois un mois déjà entamé.
    this.proposerLeResteDu();
  }

  // ── Ce qui est dû, ce qui est versé ─────────────────────────────────────
  // Deux notions qu'un seul champ « montant » confondait. Le DÛ vient de
  // l'échéancier — la même source que la fiche, les alertes et les relances ;
  // le VERSÉ vient du formulaire. Un versement partiel les sépare, et c'est
  // exactement le cas qu'on ne savait pas saisir.

  /** Les mois cochés, avec le dû que l'échéancier leur reconnaît. */
  private moisChoisis(): any[] {
    return (this.saisieDonnees()?.mois_ecole || [])
      .filter((m: any) => this.form.mois_regles.includes(m.num));
  }

  /** Total mensuel des services de l'élève. Leur dû est déjà compris dans celui
   *  du mois (`du_mensuel_standard`) : il faut donc le retrancher pour isoler la
   *  part « mensualité », sans quoi la ligne serait comptée deux fois. */
  private servicesMensuelsDus(): number {
    return (this.saisieDonnees()?.services || [])
      .filter((s: any) => s.periodicite === 'MENSUEL')
      .reduce((a: number, s: any) => a + (Number(s.montant) || 0), 0);
  }

  /** Dû de la seule ligne « Mensualité » pour les mois cochés. */
  private duMensualite(): number {
    const svc = this.servicesMensuelsDus();
    return this.moisChoisis()
      .reduce((a, m) => a + Math.max((Number(m.montant) || 0) - svc, 0), 0);
  }

  /** Dû des services proposés dans ce contexte. En mensualité, seuls les
   *  services PONCTUELS s'ajoutent : celui des mensuels est déjà dans le dû du
   *  mois. */
  private servicesProposesDus(): number {
    return (this.form.services || [])
      .filter(s => this.typePaiement === 'INSCRIPTION' || s.periodicite === 'UNIQUE')
      .reduce((a, s) => a + (Number(s.du) || 0), 0);
  }

  /** Dû réel, part prise en charge, dû net, déjà versé et reste — pour CETTE
   *  échéance. Indépendant des montants saisis : c'est ce que l'école réclame. */
  duSaisie(): { brut: number; pec: number; net: number; verse: number; reste: number } {
    const d = this.saisieDonnees();
    if (!d) return { brut: 0, pec: 0, net: 0, verse: 0, reste: 0 };
    const svc = this.servicesProposesDus();
    if (this.typePaiement === 'INSCRIPTION') {
      const b = d.fees_bruts || {}, n = d.fees_nets || {},
            p = d.deja_paye  || {}, r = d.reste     || {};
      const somme = (o: any) => (o.inscription || 0) + (o.uniforme || 0) + (o.fournitures || 0);
      return {
        brut:  Math.round(somme(b) + svc),
        pec:   d.pec?.inscription?.pec || 0,
        net:   Math.round(somme(n) + svc),
        verse: Math.round(somme(p)),
        reste: Math.round(somme(r) + svc),
      };
    }
    const mois = this.moisChoisis();
    const cumul = (cle: string) => mois.reduce((a, m) => a + (Number(m[cle]) || 0), 0);
    // Reliquat des frais d'entrée : il se réclame avec la mensualité, sur le
    // même reçu. Sans lui ici, le total proposé serait inférieur à ce que
    // l'école demande réellement à la famille.
    const entree = this.reliquatEntree();
    return {
      brut:  Math.round(cumul('du_brut') + svc + entree),
      pec:   Math.round(cumul('pec')),
      net:   Math.round(cumul('montant') + svc + entree),
      verse: Math.round(cumul('verse')),
      reste: Math.round(cumul('reste') + svc + entree),
    };
  }

  /** Reliquat des frais d'entrée (inscription ou renouvellement), échu. */
  reliquatEntree(): number {
    return Number(this.saisieDonnees()?.arrieres?.entree?.reste) || 0;
  }

  /** Part de l'échéance en cours qui vient de périodes ANTÉRIEURES : frais
   *  d'entrée partiellement réglés et mois échus non soldés. C'est le
   *  « reliquat » au sens du guichet — celui de l'année en cours, à ne pas
   *  confondre avec l'ardoise d'un exercice antérieur (form.montant_reliquat),
   *  qui solde une créance reportée et ne constate aucun produit. */
  reliquatSaisie(): number {
    if (this.typePaiement === 'INSCRIPTION') return 0;
    const arrieres = new Map<number, number>(
      (this.saisieDonnees()?.arrieres?.mois || [])
        .map((m: { num: number; reste: number }) => [m.num, m.reste]));
    const mois = this.moisChoisis()
      .reduce((t, m) => t + (arrieres.get(m.num) || 0), 0);
    return Math.round(mois + this.reliquatEntree());
  }

  /** Les périodes que ce reliquat couvre, en clair, pour le reçu et l'écran. */
  libelleReliquat(): string {
    const noms: string[] = [];
    if (this.reliquatEntree() > 0) {
      noms.push(this.saisieDonnees()?.arrieres?.entree?.libelle || 'Inscription');
    }
    const arrieres = new Set<number>(
      (this.saisieDonnees()?.arrieres?.mois || [])
        .map((m: { num: number }) => m.num));
    for (const m of this.moisChoisis()) {
      if (arrieres.has(m.num)) noms.push(m.label);
    }
    return noms.join(', ');
  }

  /** Ce que l'école appelle ses frais d'entrée pour CET élève : « Inscription »
   *  pour un nouvel entrant, le mot de l'établissement (Renouvellement,
   *  Réinscription…) pour un ancien. */
  libelleEntree(): string {
    return this.saisieDonnees()?.libelle_entree || 'Inscription';
  }

  /** L'échéance en cours de règlement, en clair. Sans article : le mot varie
   *  d'une école à l'autre (« Renouvellement », « Réinscription »…) et aucun
   *  article ne leur va à tous. */
  libelleEcheance(): string {
    if (this.typePaiement === 'INSCRIPTION') return this.libelleEntree();
    const noms = this.moisChoisis().map(m => m.label);
    return noms.length ? noms.join(', ') : 'ce paiement';
  }

  /** Montant réellement remis par la famille. Ce n'est pas un état de plus :
   *  c'est la somme des lignes du formulaire, vue depuis le guichet. Le saisir
   *  les ventile, les modifier le met à jour — un seul état, jamais deux. */
  get montantVerse(): number {
    return this.totalForm();
  }
  set montantVerse(v: number) {
    this.ventiler(Number(v) || 0);
  }

  /** Part du versement qui règle l'échéance : hors reliquat d'une année
   *  antérieure et hors « divers », qui paient autre chose. */
  private verseSurEcheance(): number {
    return this.totalForm()
         - (Number(this.form.montant_reliquat) || 0)
         - (Number(this.form.montant_divers)   || 0);
  }

  /** Ce que la famille devra encore sur cette échéance après ce versement.
   *  Négatif = elle a payé au-delà (avance). */
  resteApresVersement(): number {
    return Math.round((this.duSaisie().reste - this.verseSurEcheance()) * 100) / 100;
  }

  /** Répartit un montant versé sur les lignes du formulaire, dans l'ordre où
   *  une école impute : la scolarité d'abord, les services ensuite. Un
   *  versement partiel remplit donc la mensualité avant la cantine, et ce que la
   *  famille n'a pas donné reste visiblement dû. L'excédent va sur la scolarité :
   *  une avance sur l'année n'est pas un produit divers.
   *
   *  Le reliquat et les « divers » ne bougent pas — ils règlent autre chose que
   *  l'échéance, les diluer ici fausserait les deux suivis à la fois. */
  private ventiler(verse: number) {
    const d = this.saisieDonnees();
    if (!d) return;
    const fixe = (Number(this.form.montant_reliquat) || 0)
               + (Number(this.form.montant_divers)   || 0);
    let reste = Math.max(0, Math.round(verse) - fixe);
    const prendre = (du: number) => {
      const part = Math.min(Math.max(du, 0), reste);
      reste -= part;
      return part;
    };
    if (this.typePaiement === 'INSCRIPTION') {
      const r = d.reste || {};
      this.form.montant_inscription = prendre(r.inscription || 0);
      this.form.montant_uniforme    = prendre(r.uniforme    || 0);
      this.form.montant_fournitures = prendre(r.fournitures || 0);
      for (const s of this.form.services) s.montant = s.inclus ? prendre(s.du) : 0;
      this.form.montant_inscription += reste;
    } else {
      // Le plus ancien d'abord : le reliquat des frais d'entrée se solde avant
      // la mensualité du mois, sinon un versement partiel laisserait une dette
      // ancienne derrière une dette récente.
      this.form.montant_inscription = prendre(this.reliquatEntree());
      this.form.montant_mensualite  = prendre(this.duMensualite());
      for (const s of this.form.services) s.montant = s.inclus ? prendre(s.du) : 0;
      this.form.montant_mensualite += reste;
    }
  }

  private resetForm() {
    this.form = {
      montant_inscription: 0, montant_mensualite: 0, montant_uniforme: 0,
      montant_fournitures: 0, montant_cantine: 0, montant_divers: 0,
      montant_reliquat: 0,
      mois_regles: [], services: [], mode_paiement: this.form.mode_paiement || '',
      multi_mode: false, modes_reglement: [], observations: '',
      // Le payeur n'est PAS conservé d'une saisie à l'autre, contrairement au
      // mode : enchaîner deux reçus et attribuer le second à l'organisme par
      // inadvertance fausserait le suivi des deux côtés.
      organisme: null,
    };
  }

  get totalForm(): () => number {
    return () => Object.entries(this.form)
      .filter(([k]) => k.startsWith('montant_'))
      .reduce((s, [, v]) => s + (Number(v) || 0), 0) + this.servicesTotal();
  }

  totalModifForm(): number {
    return Object.entries(this.modifForm)
      .filter(([k]) => k.startsWith('montant_'))
      .reduce((s, [, v]) => s + (Number(v) || 0), 0);
  }

  // ── Paiement multi-mode ────────────────────────────────────────────────
  onToggleMultiMode() {
    if (this.form.multi_mode && this.form.modes_reglement.length === 0) {
      // Amorce : une ligne pré-remplie avec le mode déjà choisi et le total.
      this.form.modes_reglement = [{
        mode: this.form.mode_paiement || '',
        montant: this.totalForm(),
      }];
    }
  }

  ajouterModeLigne() {
    this.form.modes_reglement.push({ mode: '', montant: Math.max(0, this.resteAVentiler()) });
  }

  retirerModeLigne(i: number) {
    this.form.modes_reglement.splice(i, 1);
  }

  /** Montant restant à répartir entre les modes (0 = ventilation complète). */
  resteAVentiler(): number {
    const somme = this.form.modes_reglement.reduce((s, m) => s + (Number(m.montant) || 0), 0);
    return Math.round((this.totalForm() - somme) * 100) / 100;
  }

  ouvrirDialog() {
    this.eleveSelectionne = null;
    this.rechercheInput   = '';
    this.elevesSuggestions.set([]);
    this.saisieDonnees.set(null);
    this.resetForm();
    this.typePaiement  = 'MENSUALITE';
    this.dialogVisible = true;
  }

  sauvegarder(avecRecu: boolean) {
    if (!this.eleveSelectionne?.id) {
      this.msg.add({ severity:'warn', summary: this.translate.instant('paiements.champ_requis'), detail: this.translate.instant('paiements.select_eleve') });
      return;
    }
    if (this.totalForm() <= 0) {
      this.msg.add({ severity:'warn', summary: this.translate.instant('common.requis'), detail: this.translate.instant('paiements.montant_invalide') });
      return;
    }
    if (!this.form.multi_mode && !this.form.mode_paiement) {
      this.msg.add({ severity:'warn', summary: this.translate.instant('paiements.champ_requis'), detail: this.translate.instant('paiements.choisir_mode') });
      return;
    }
    if (this.form.multi_mode) {
      if (this.form.modes_reglement.some(m => !m.mode || Number(m.montant) <= 0)) {
        this.msg.add({ severity:'warn', summary: this.translate.instant('paiements.champ_requis'), detail: 'Chaque ligne de mode doit avoir un moyen et un montant > 0.' });
        return;
      }
      if (this.resteAVentiler() !== 0) {
        this.msg.add({ severity:'warn', summary: this.translate.instant('paiements.champ_requis'), detail: `La ventilation doit couvrir exactement le total (reste : ${this.resteAVentiler()} FCFA).` });
        return;
      }
    }
    this.saving.set(true);
    // Services inclus : itemisés dans services_regles ; leur montant est ajouté au montant_divers
    const servicesIncl  = (this.form.services || []).filter(s => s.inclus && Number(s.montant) > 0);
    const servicesTotal = servicesIncl.reduce((a, s) => a + Number(s.montant), 0);
    this.paiementsService.creerPaiement({
      montant_inscription: this.form.montant_inscription,
      montant_mensualite:  this.form.montant_mensualite,
      montant_uniforme:    this.form.montant_uniforme,
      montant_fournitures: this.form.montant_fournitures,
      montant_cantine:     this.form.montant_cantine,
      montant_divers:      Number(this.form.montant_divers || 0) + servicesTotal,
      montant_reliquat:    Number(this.form.montant_reliquat || 0),
      mois_regles:         this.form.mois_regles,
      services_regles:     servicesIncl.map(s => ({ nom: s.nom, montant: Number(s.montant) })),
      mode_paiement:       this.form.multi_mode ? 'MIXTE' : this.form.mode_paiement,
      modes_reglement:     this.form.multi_mode
        ? this.form.modes_reglement.map(m => ({ mode: m.mode, montant: Number(m.montant) }))
        : [],
      observations:        this.form.observations,
      organisme:           this.form.organisme || null,
      eleve:    this.eleveSelectionne.id,
      exercice: this.exerciceId,
    }).subscribe({
      next: (res: any) => {
        this.msg.add({ severity:'success', summary: this.translate.instant('paiements.enregistre'), detail:`Reçu: ${res.no_piece}` });
        this.dialogVisible = false;
        this.saving.set(false);
        this.chargerPaiements();
        this.chargerStats();
        if (avecRecu) this.imprimerRecu(res);
      },
      error: (err) => {
        this.msg.add({ severity:'error', summary: this.translate.instant('common.erreur'), detail: this.translate.instant('paiements.erreur_save') });
        console.error(err);
        this.saving.set(false);
      }
    });
  }

  demanderAnnulationPaiement(p: any) {
    this.paiementAnnuler = p;
    this.confirmAnnulVisible = true;
  }

  demanderModificationPaiement(p: any) {
    this.paiementModifier = p;
    this.modifForm = {
      montant_inscription: p.montant_inscription || 0,
      montant_mensualite:  p.montant_mensualite  || 0,
      montant_uniforme:    p.montant_uniforme    || 0,
      montant_fournitures: p.montant_fournitures || 0,
      montant_cantine:     p.montant_cantine     || 0,
      montant_divers:      p.montant_divers      || 0,
      montant_reliquat:    p.montant_reliquat    || 0,
      mode_paiement:       p.mode_paiement       || '',
      observations:        p.observations        || '',
    };
    this.modifVisible = true;
  }

  confirmerModificationPaiement() {
    if (!this.paiementModifier?.id) return;
    this.savingModif.set(true);
    this.paiementsService.modifierPaiement(this.paiementModifier.id, this.modifForm).subscribe({
      next: (res: any) => {
        this.msg.add({
          severity: 'success',
          summary: 'Paiement modifié',
          detail: `${res.ancien_no_piece} → ${res.nouveau_no_piece} · ${res.nouveau_total?.toLocaleString()} FCFA`,
        });
        this.modifVisible = false;
        this.paiementModifier = null;
        this.savingModif.set(false);
        this.chargerPaiements();
        this.chargerStats();
      },
      error: (err: any) => {
        const msg = err?.error?.error || 'Erreur lors de la modification.';
        this.msg.add({ severity: 'error', summary: 'Erreur', detail: msg });
        this.savingModif.set(false);
      },
    });
  }

  confirmerAnnulationPaiement() {
    if (!this.paiementAnnuler?.id) return;
    this.savingAnnul.set(true);
    this.paiementsService.annulerPaiement(this.paiementAnnuler.id).subscribe({
      next: (res: any) => {
        this.msg.add({
          severity: 'info',
          summary: 'Paiement annulé',
          detail: `Contre-écritures générées : ${res.no_piece_annulation}`,
        });
        this.confirmAnnulVisible = false;
        this.paiementAnnuler = null;
        this.savingAnnul.set(false);
        this.chargerPaiements();
        this.chargerStats();
      },
      error: (err: any) => {
        const msg = err?.error?.error || 'Erreur lors de l\'annulation.';
        this.msg.add({ severity: 'error', summary: 'Erreur', detail: msg });
        this.savingAnnul.set(false);
      },
    });
  }

  imprimerRecu(paiement: any) {
    if (!paiement?.id) return;
    this.paiementsService.getRecu(paiement.id).subscribe({
      next: res => { this.recuData.set(res); this.recuVisible = true; }
    });
  }

  telechargerRecuPdf() {
    const d = this.recuData();
    if (!d?.paiement_id) {
      this.msg.add({ severity: 'warn', summary: 'ID manquant', detail: 'Fermez et rouvrez le reçu.' });
      return;
    }
    this.paiementsService.telechargerRecuPdf(d.paiement_id, this.recuFormat).subscribe({
      next: (blob: Blob) => {
        const url  = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href     = url;
        link.download = `recu_${d.no_piece}_${this.recuFormat}.pdf`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      },
      error: () => this.msg.add({ severity: 'error', summary: 'Erreur PDF',
                                   detail: 'Impossible de générer le reçu.' }),
    });
  }

  setTypePaiement(type: 'INSCRIPTION' | 'MENSUALITE') {
    this.typePaiement = type;
    const data = this.saisieDonnees();
    if (data) this.appliquerAutoRemplissage(data);
  }

  // ── Charges ─────────────────────────────────────────────────────────────────

  chargerCharges() {
    this.loadingCharges.set(true);
    this.compta.getCharges(this.rechercheCharge.trim() || undefined).subscribe({
      next: res => { this.charges.set(Array.isArray(res) ? res : []); this.loadingCharges.set(false); },
      error: () => this.loadingCharges.set(false),
    });
  }

  // ── Recherche d'une charge ─────────────────────────────────────────────
  // Libellé, n° de pièce ou compte. Retrouver une dépense de l'an dernier
  // supposait de faire défiler des centaines de lignes.
  rechercheCharge = '';
  private _timerCharge: any = null;

  onRechercheChargeChange() {
    clearTimeout(this._timerCharge);
    this._timerCharge = setTimeout(() => this.chargerCharges(), 300);
  }

  effacerRechercheCharge() {
    this.rechercheCharge = '';
    this.chargerCharges();
  }

  /** Lignes de budget de l'exercice — pour imputer une charge à un poste. */
  lignesBudget = signal<{ id: string; libelle: string; no_compte: string }[]>([]);

  chargerLignesBudget() {
    this.compta.getBudget().subscribe({
      next: (res: any) => this.lignesBudget.set(
        (res?.lignes || []).map((l: any) => ({
          id: l.id, no_compte: l.no_compte,
          libelle: `${l.libelle} (${l.no_compte})`,
        }))),
      // Silencieux : une école sans budget n'a pas à voir une erreur pour une
      // fonctionnalité qu'elle n'utilise pas.
      error: () => this.lignesBudget.set([]),
    });
  }

  totalCharges(): number {
    return this.charges().reduce((s, c) => s + (c.montant || 0), 0);
  }

  // ── Charge multi-mode ───────────────────────────────────────────────────
  onToggleMultiCharge() {
    if (this.nouvelleCharge.multi_mode && this.nouvelleCharge.modes_reglement.length === 0) {
      this.nouvelleCharge.modes_reglement = [{ mode: 'ESPECE', montant: Number(this.nouvelleCharge.montant) || 0 }];
    }
  }
  ajouterModeCharge() {
    this.nouvelleCharge.modes_reglement.push({ mode: '', montant: Math.max(0, this.chargeReste()) });
  }
  retirerModeCharge(i: number) {
    this.nouvelleCharge.modes_reglement.splice(i, 1);
  }
  chargeReste(): number {
    const somme = (this.nouvelleCharge.modes_reglement || [])
      .reduce((s: number, m: any) => s + (Number(m.montant) || 0), 0);
    return Math.round(((Number(this.nouvelleCharge.montant) || 0) - somme) * 100) / 100;
  }

  // Import Excel des charges
  importChargesVisible = signal(false);

  // ── GED — pièces justificatives (charges) ───────────────────────────────
  dialogPiecesVisible = false;
  piecesObjetType = signal<string>('');
  piecesObjetId   = signal<string>('');
  piecesTitre     = signal<string>('');
  ouvrirPieces(objetType: string, objetId: string, titre: string) {
    this.piecesObjetType.set(objetType);
    this.piecesObjetId.set(objetId);
    this.piecesTitre.set(titre);
    this.dialogPiecesVisible = true;
  }

  ouvrirDialogCharge() {
    this.nouvelleCharge = {
      no_compte: '661', libelle: '', montant: 0,
      date: new Date().toISOString().split('T')[0],
      compte_credit: '571', compte_fournisseur: '401',
      ressource_id: null, projet_id: null,
      // Poste de budget consommé. Vide = dépense hors budget — le cas normal,
      // et celui qu'on ne savait pas exprimer : toute charge sur un compte
      // budgété était comptée comme réalisée, prévue ou non.
      budget_ligne_id: null,
      multi_mode: false, modes_reglement: [] as { mode: string; montant: number }[],
    };
    this.compteSuggere = null;
    this.compteChargeVerrouille = false;
    this.dialogChargeVisible = true;
    this.chargerLignesBudget();
    // Dimensions analytiques facultatives (gouvernance) — listes fraîches.
    this.gouv.getRessources().subscribe({
      next: d => this.ressourcesGouv.set((d || []).filter((r: any) => r.statut === 'ACTIVE')),
      error: () => this.ressourcesGouv.set([]),
    });
    this.gouv.getProjets(true).subscribe({
      next: d => this.projetsGouv.set(d || []),
      error: () => this.projetsGouv.set([]),
    });
  }

  // ── Auto-remplissage du compte de charge d'après le libellé ───────────────
  // Pour les non-comptables : « facture eau » → 6051, « salaire juillet » → 661…
  // Le compte fournisseur suit (onCompteChargeChange). Un choix manuel du
  // compte verrouille la suggestion jusqu'à la prochaine ouverture du dialog.
  compteSuggere: string | null = null;
  compteChargeVerrouille = false;

  private static MOTS_CLES_CHARGES: [RegExp, string][] = [
    [/\beaux?\b|facture sde|sen ?eau/,                                  '6051'],
    [/electricite|senelec|woyofal|courant/,                             '6052'],
    [/craies?|cahiers?|stylos?|papier|rames?|marqueurs?|ardoises?|fournitures?/, '6054'],
    [/marchandises?|denrees?|\briz\b|huile|sucre|cantine/,              '601'],
    [/carburant|essence|gasoil|\bgaz\b/,                                '605'],
    [/gardien|vigile|surveillance|sous.?traitance|prestataire/,         '621'],
    [/loyers?|locations?|\bbail\b/,                                     '622'],
    [/entretien|reparations?|maintenance|plomb(erie|ier)|peinture|menuis(erie|ier)|nettoyage|vidange/, '624'],
    [/assurances?/,                                                     '625'],
    [/etudes?|recherches?|documentation/,                               '626'],
    [/publicite|flyers?|affiches?|banderoles?|communication|sponsor/,   '627'],
    [/telephone|internet|wifi|\borange\b|\bfree\b|\bexpresso\b|connexion/, '628'],
    [/banque|bancaires?|agios|tenue de compte/,                         '631'],
    [/formations?|seminaires?|ateliers?/,                               '633'],
    [/missions?|voyages?|receptions?|hotel|restaurant|deplacements?/,   '635'],
    [/impots?|taxes?|patente|vignette/,                                 '641'],
    [/timbres?|enregistrement/,                                         '645'],
    [/salaires?|paie|appointements?|remunerations?|personnel/,          '661'],
    [/ipres/,                                                           '662'],
    [/\bcss\b|cotisations?|securite sociale/,                           '664'],
    [/indemnites?|primes?|avantages?/,                                  '663'],
    [/interets?|emprunts?|\bprets?\b/,                                  '671'],
    [/transports?|\bbus\b|\bcar\b|navette/,                             '618'],
  ];

  onLibelleChargeChange() {
    if (this.compteChargeVerrouille) return;
    const brut = (this.nouvelleCharge.libelle || '');
    const texte = brut.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    const comptesDispo = new Set(this.planChargesPC().map(c => c.value));
    for (const [motif, compte] of PaiementsComponent.MOTS_CLES_CHARGES) {
      if (!motif.test(texte)) continue;
      // Si le compte précis n'existe pas dans le plan du tenant, remonter au parent (3 chiffres)
      const cible = comptesDispo.has(compte) ? compte
                  : (comptesDispo.has(compte.slice(0, 3)) ? compte.slice(0, 3) : null);
      if (!cible) continue;
      if (this.nouvelleCharge.no_compte !== cible) {
        this.nouvelleCharge.no_compte = cible;
        this.onCompteChargeChange();          // synchronise le compte fournisseur
      }
      this.compteSuggere = cible;
      return;
    }
    this.compteSuggere = null;
  }

  onCompteChargeChange() {
    const no = this.nouvelleCharge.no_compte || '';
    if (no.startsWith('2')) {
      this.nouvelleCharge.compte_fournisseur = '404';
    } else if (no === '681') {
      this.nouvelleCharge.compte_fournisseur = '481';
    } else {
      this.nouvelleCharge.compte_fournisseur = '401';
    }
  }

  sauvegarderCharge() {
    if (!this.nouvelleCharge.no_compte) {
      this.msg.add({ severity: 'warn', summary: 'Champ requis', detail: 'Sélectionnez un compte de charge.' });
      return;
    }
    if (!this.nouvelleCharge.libelle) {
      this.msg.add({ severity: 'warn', summary: 'Champ requis', detail: 'Saisissez un libellé.' });
      return;
    }
    if (!this.nouvelleCharge.montant || this.nouvelleCharge.montant <= 0) {
      this.msg.add({ severity: 'warn', summary: 'Montant invalide', detail: 'Le montant doit être > 0.' });
      return;
    }
    if (this.nouvelleCharge.multi_mode) {
      if (this.nouvelleCharge.modes_reglement.some((m: any) => !m.mode || Number(m.montant) <= 0)) {
        this.msg.add({ severity: 'warn', summary: 'Champ requis', detail: 'Chaque ligne de mode doit avoir un moyen et un montant > 0.' });
        return;
      }
      if (this.chargeReste() !== 0) {
        this.msg.add({ severity: 'warn', summary: 'Ventilation incomplète', detail: `La ventilation doit couvrir le montant (reste : ${this.chargeReste()} FCFA).` });
        return;
      }
    }
    this.savingCharge.set(true);
    this.compta.creerCharge(this.nouvelleCharge).subscribe({
      next: () => {
        this.dialogChargeVisible = false;
        this.savingCharge.set(false);
        this.msg.add({ severity: 'success', summary: 'Charge enregistrée',
                       detail: `${this.nouvelleCharge.no_compte} — ${this.nouvelleCharge.libelle}` });
        this.chargerCharges();
      },
      error: (err) => {
        this.msg.add({ severity: 'error', summary: 'Erreur', detail: err?.error?.error || 'Impossible d\'enregistrer la charge.' });
        this.savingCharge.set(false);
      },
    });
  }

  demanderModificationCharge(c: any) {
    this.chargeModifier = c;
    this.modifChargeForm = {
      no_compte:     c.no_compte  || '',
      libelle:       c.libelle    || '',
      montant:       c.montant    || 0,
      date:          c.date       || '',
      compte_credit: '571',
    };
    this.dialogModifChargeVisible = true;
  }

  confirmerModificationCharge() {
    if (!this.chargeModifier?.id) return;
    if (!this.modifChargeForm.no_compte || !this.modifChargeForm.libelle) {
      this.msg.add({ severity: 'warn', summary: 'Champs requis', detail: 'Compte et libellé obligatoires.' });
      return;
    }
    if (!this.modifChargeForm.montant || this.modifChargeForm.montant <= 0) {
      this.msg.add({ severity: 'warn', summary: 'Montant invalide', detail: 'Le montant doit être > 0.' });
      return;
    }
    this.savingModifCharge.set(true);
    this.compta.modifierCharge(this.chargeModifier.id, this.modifChargeForm).subscribe({
      next: (res: any) => {
        this.msg.add({ severity: 'success', summary: 'Charge modifiée',
                       detail: `${res.ancien_no_piece} → ${res.no_piece_new} · ${res.montant?.toLocaleString()} FCFA` });
        this.dialogModifChargeVisible = false;
        this.chargeModifier = null;
        this.savingModifCharge.set(false);
        this.chargerCharges();
      },
      error: (err: any) => {
        this.msg.add({ severity: 'error', summary: 'Erreur', detail: err?.error?.error || 'Impossible de modifier cette charge.' });
        this.savingModifCharge.set(false);
      },
    });
  }

  supprimerCharge(c: any) {
    if (!confirm(`Annuler la charge ${c.no_piece} — ${c.libelle} ?\nDes contre-écritures SYSCOHADA seront générées automatiquement.`)) return;
    this.compta.supprimerCharge(c.id).subscribe({
      next: (res: any) => {
        this.msg.add({ severity: 'success', summary: 'Charge annulée',
                       detail: `Contre-écritures ${res.no_piece_annulation || ''} générées.` });
        this.chargerCharges();
      },
      error: (err: any) => this.msg.add({ severity: 'error', summary: 'Erreur',
                                           detail: err?.error?.error || 'Impossible d\'annuler cette charge.' }),
    });
  }
}
