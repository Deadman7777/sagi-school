import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { PaiementsService } from '../../core/services/paiements.service';
import { ElevesService } from '../../core/services/eleves.service';
import { ComptabiliteService } from '../../core/services/comptabilite.service';
import { Eleve } from '../../core/models/eleve.model';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { TagModule } from 'primeng/tag';
import { ToastModule } from 'primeng/toast';
import { InputNumberModule } from 'primeng/inputnumber';
import { MessageService } from 'primeng/api';
import { TooltipModule } from 'primeng/tooltip';
import { TranslateModule, TranslateService } from '@ngx-translate/core';

@Component({
  selector: 'app-paiements',
  standalone: true,
  imports: [CommonModule, FormsModule, TableModule, TranslateModule, ButtonModule, DialogModule,
            InputTextModule, SelectModule, TagModule, ToastModule,
            InputNumberModule, TooltipModule],
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
        <div style="background:#1a1a2e;border-radius:8px;padding:14px;margin-bottom:16px;border-left:4px solid #ef4444">
          <div style="font-size:13px;color:#e8f0fe;font-weight:600">{{ paiementAnnuler.no_piece }}</div>
          <div style="font-size:12px;color:#94a3b8;margin-top:4px">
            {{ paiementAnnuler.eleve_nom }} · {{ paiementAnnuler.total | number:'1.0-0' }} FCFA
          </div>
        </div>
        <p style="font-size:13px;color:#94a3b8;line-height:1.6;margin:0">
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
        <div style="background:#1a1a2e;border-radius:8px;padding:12px;margin-bottom:16px;border-left:4px solid #f59e0b">
          <div style="font-size:12px;color:#f59e0b;font-weight:600;margin-bottom:4px">
            Original : {{ paiementModifier.no_piece }}
          </div>
          <div style="font-size:11px;color:#94a3b8">
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
        <div style="text-align:center;padding:10px;color:#64748b;font-size:12px">⏳ Chargement des données...</div>
      }

      <!-- Alerte ABANDONNÉ -->
      @if (saisieDonnees()?.statut === 'ABANDONNE') {
        <div style="background:rgba(239,68,68,0.1);border:1px solid #ef4444;border-radius:6px;padding:10px 14px;font-size:12px;color:#ef4444;margin-bottom:10px">
          ⚠️ Cet élève est marqué <strong>ABANDONNÉ</strong>. Le paiement sera enregistré mais ne sera pas comptabilisé dans les statistiques actives.
        </div>
      }

      <!-- Badge Prise en charge -->
      @if (saisieDonnees()?.taux_pec > 0) {
        <div style="background:rgba(124,58,237,0.1);border:1px solid #7c3aed;border-radius:6px;padding:8px 14px;font-size:12px;color:#a78bfa;margin-bottom:10px">
          🤝 Prise en charge : <strong>{{ saisieDonnees()!.taux_pec }}%</strong>
          ({{ saisieDonnees()!.prise_en_charge }})
          — Montants réduits automatiquement.
          @if (saisieDonnees()?.obs_prise_en_charge) {
            <span style="color:#64748b"> · {{ saisieDonnees()!.obs_prise_en_charge }}</span>
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
        </div>
      }

      <!-- Type de paiement -->
      @if (saisieDonnees() && !loadingSaisie()) {
        <div class="form-group full" style="margin-bottom:12px">
          <label>Type de paiement *</label>
          <div style="display:flex;gap:8px;margin-top:6px">
            <button [class]="typePaiement === 'INSCRIPTION' ? 'type-btn active-inscr' : 'type-btn'"
                    (click)="setTypePaiement('INSCRIPTION')">
              🎓 Inscription / Frais d'entrée
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
              <label>Inscription
                @if (saisieDonnees()!.fees_nets.inscription > 0) {
                  <span class="fee-hint">Dû : {{ saisieDonnees()!.reste.inscription | number:'1.0-0' }}</span>
                }
              </label>
              <p-inputNumber [(ngModel)]="form.montant_inscription" [min]="0" mode="decimal" styleClass="w-full" />
            </div>
            <div class="form-group">
              <label>Uniforme
                @if (saisieDonnees()!.fees_nets.uniforme > 0) {
                  <span class="fee-hint">Dû : {{ saisieDonnees()!.reste.uniforme | number:'1.0-0' }}</span>
                }
              </label>
              <p-inputNumber [(ngModel)]="form.montant_uniforme" [min]="0" mode="decimal" styleClass="w-full" />
            </div>
            <div class="form-group">
              <label>Fournitures
                @if (saisieDonnees()!.fees_nets.fournitures > 0) {
                  <span class="fee-hint">Dû : {{ saisieDonnees()!.reste.fournitures | number:'1.0-0' }}</span>
                }
              </label>
              <p-inputNumber [(ngModel)]="form.montant_fournitures" [min]="0" mode="decimal" styleClass="w-full" />
            </div>
            <div class="form-group">
              <label>Divers</label>
              <p-inputNumber [(ngModel)]="form.montant_divers" [min]="0" mode="decimal" styleClass="w-full" />
            </div>
          </div>
        }

        @if (typePaiement === 'MENSUALITE') {
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
              <label>Cantine</label>
              <p-inputNumber [(ngModel)]="form.montant_cantine" [min]="0" mode="decimal" styleClass="w-full" />
            </div>
            <div class="form-group">
              <label>Divers</label>
              <p-inputNumber [(ngModel)]="form.montant_divers" [min]="0" mode="decimal" styleClass="w-full" />
            </div>
          </div>
        }

        <!-- Total -->
        <div class="total-bar">
          <span>Total à encaisser</span>
          <span class="total-val">{{ totalForm() | number:'1.0-0' }} FCFA</span>
        </div>

        <!-- Mode paiement -->
        <div class="form-group" style="margin-top:12px">
          <label>Mode de paiement *</label>
          <p-select [options]="modesPaiement" [(ngModel)]="form.mode_paiement"
                    optionLabel="label" optionValue="value"
                    placeholder="Choisir le mode..." styleClass="w-full" />
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
          <div style="font-size:11px;color:#64748b;margin-top:2px">
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
        <p-button label="📄 Télécharger PDF" severity="success"
                  icon="pi pi-download" (onClick)="telechargerRecuPdf()" />
        <p-button label="Fermer" severity="secondary" (onClick)="recuVisible=false" />
      </ng-template>
    </p-dialog>

    </ng-container>
    <!-- === FIN ONGLET PAIEMENTS === -->

    <!-- === ONGLET CHARGES === -->
    <div *ngIf="onglet() === 'charges'">
      <div class="table-card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;padding:16px 16px 0">
          <div>
            <h3 style="margin:0;color:#e8f0fe">💸 Charges de l'exercice</h3>
            <span style="color:#64748b;font-size:12px">
              Total : {{ totalCharges() | number:'1.0-0' }} FCFA
            </span>
          </div>
          <p-button label="+ Nouvelle charge" severity="danger" (onClick)="ouvrirDialogCharge()" />
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
              <td>{{ c.libelle }}</td>
              <td class="mono danger" align="right">{{ c.montant | number:'1.0-0' }} FCFA</td>
              <td>
                <div style="display:flex;gap:4px">
                  <p-button icon="pi pi-pencil" [rounded]="true" [text]="true" severity="warn"
                            pTooltip="Modifier (contre-écritures + nouvelle charge)" (onClick)="demanderModificationCharge(c)" />
                  <p-button icon="pi pi-times" [rounded]="true" [text]="true" severity="danger"
                            pTooltip="Annuler (contre-écritures SYSCOHADA)" (onClick)="supprimerCharge(c)" />
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
            <label>Compte de charge *</label>
            <p-select appendTo="body" [options]="planChargesPC()" [(ngModel)]="nouvelleCharge.no_compte"
                      optionLabel="label" optionValue="value" styleClass="w-full" [filter]="true"
                      (onChange)="onCompteChargeChange()" />
          </div>
          <div class="form-group full">
            <label>Libellé *</label>
            <input pInputText [(ngModel)]="nouvelleCharge.libelle" class="w-full"
                  placeholder="Ex : Facture eau juillet..." />
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
            <label>Réglé via</label>
            <p-select appendTo="body" [options]="comptesCredit" [(ngModel)]="nouvelleCharge.compte_credit"
                      optionLabel="label" optionValue="value" styleClass="w-full" />
          </div>
        </div>
        <ng-template pTemplate="footer">
          <p-button label="Annuler"       severity="secondary" (onClick)="dialogChargeVisible=false" />
          <p-button label="Enregistrer"   severity="danger"
                    [loading]="savingCharge()" (onClick)="sauvegarderCharge()" />
        </ng-template>
      </p-dialog>

      <!-- Dialog modification charge -->
      <p-dialog header="✏️ Modifier la charge" [(visible)]="dialogModifChargeVisible"
                [modal]="true" [style]="{width:'460px'}" [draggable]="false">
        <div *ngIf="chargeModifier" class="form-grid">
          <div class="form-group full">
            <div style="background:#1a1a2e;border-radius:6px;padding:10px;border-left:4px solid #f59e0b;font-size:12px;color:#94a3b8">
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
    .page-title  { font-size:20px; font-weight:600; color:#e8f0fe; margin:0 0 4px; }
    .page-sub    { font-size:12px; color:#64748b; }

    .modes-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:12px; margin-bottom:20px; }
    .mode-card  { background:#1e2d45; border:1px solid #2a3f5f; border-radius:10px; padding:14px; text-align:center; }
    .mode-name  { font-size:11px; color:#64748b; text-transform:uppercase; letter-spacing:1px; margin-bottom:4px; }
    .mode-total { font-size:20px; font-weight:700; font-family:monospace; color:#00d4aa; }
    .mode-nb    { font-size:11px; color:#64748b; margin-top:2px; }

    .table-card { background:#1e2d45; border:1px solid #2a3f5f; border-radius:12px; overflow:hidden; }

    ::ng-deep .p-datatable .p-datatable-thead > tr > th { background:#111827 !important; color:#64748b !important; font-size:11px !important; text-transform:uppercase !important; border-color:#2a3f5f !important; }
    ::ng-deep .p-datatable .p-datatable-tbody > tr { background:#1e2d45 !important; color:#94a3b8 !important; border-bottom:1px solid rgba(42,63,95,0.4) !important; }
    ::ng-deep .p-datatable .p-datatable-tbody > tr:hover { background:#1a2235 !important; }

    .mono        { font-family:monospace; font-size:12px; }
    .bold        { font-weight:600; color:#e8f0fe; }
    .success     { color:#10b981; }
    .annule-val  { color:#ef4444; text-decoration:line-through; opacity:0.7; }
    .btn-row     { display:flex; gap:4px; align-items:center; }
    .empty-msg   { text-align:center; padding:40px; color:#64748b; }
    ::ng-deep .ligne-annulee td { opacity:0.55 !important; background:rgba(239,68,68,0.04) !important; }

    .eleve-info { background:#0f2010; border:1px solid #2a5c2a; border-radius:8px; padding:12px; margin-bottom:14px; }
    .ei-row { display:flex; justify-content:space-between; font-size:12px; padding:4px 0; border-bottom:1px solid rgba(42,95,42,0.3); }
    .ei-row:last-child { border-bottom:none; }
    .ei-row span:first-child { color:#64748b; }
    .ei-row span:last-child  { font-weight:500; color:#e8f0fe; font-family:monospace; }

    .montants-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
    .form-group { display:flex; flex-direction:column; gap:6px; }
    .form-group label { font-size:12px; color:#94a3b8; text-transform:uppercase; letter-spacing:0.5px; }

    .total-bar { display:flex; justify-content:space-between; align-items:center; background:rgba(0,212,170,0.1); border:1px solid rgba(0,212,170,0.2); border-radius:8px; padding:10px 16px; margin-top:14px; }
    .total-val { font-size:20px; font-weight:700; color:#00d4aa; font-family:monospace; }

    .recu { color:#e8f0fe; }
    .recu-header { text-align:center; margin-bottom:16px; }
    .recu-titre { font-size:16px; font-weight:700; color:#00d4aa; }
    .recu-no    { font-size:12px; color:#64748b; font-family:monospace; margin-top:4px; }
    .recu-row   { display:flex; justify-content:space-between; font-size:13px; padding:5px 0; border-bottom:1px solid rgba(42,63,95,0.3); }
    .recu-row span:first-child { color:#64748b; }
    .recu-total   { display:flex; justify-content:space-between; font-size:14px; font-weight:700; padding:6px 0; color:#00d4aa; border-top:1px solid #2a3f5f; margin-top:4px; }
    .recu-section { font-size:10px; font-weight:700; color:#00d4aa; text-transform:uppercase; letter-spacing:.5px; padding:6px 0 2px; border-bottom:1px solid #2a3f5f; }
    .fee-hint { font-size:10px; color:#00d4aa; margin-left:6px; font-weight:400; font-style:italic; }
    /* Recherche élève */
    .search-eleve-wrap { margin-bottom:14px; }
    .search-label      { display:block; font-size:12px; color:#94a3b8; text-transform:uppercase; letter-spacing:.3px; margin-bottom:6px; }
    .search-hint       { font-size:10px; color:#475569; text-transform:none; margin-left:6px; }
    .search-input-field{ background:#111827; border:1px solid #2a3f5f; color:#e8f0fe; border-radius:6px; padding:9px 12px; font-size:13px; outline:none; }
    .search-input-field:focus { border-color:#00d4aa; }
    .search-spinner    { position:absolute; right:12px; top:10px; color:#00d4aa; font-size:14px; animation:spin 1s linear infinite; }
    @keyframes spin { to { transform:rotate(360deg); } }
    .suggestions-list  { border:1px solid #2a3f5f; border-radius:6px; background:#1e2d45; margin-top:4px; max-height:260px; overflow-y:auto; }
    .suggestion-item   { padding:10px 14px; cursor:pointer; border-bottom:1px solid rgba(42,63,95,0.5); }
    .suggestion-item:last-child { border-bottom:none; }
    .suggestion-item:hover { background:#263450; }
    .si-top    { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:3px; }
    .si-nom    { color:#e8f0fe; font-size:13px; font-weight:600; }
    .si-matricule { font-family:monospace; font-size:11px; background:#0b1220; color:#00d4aa; padding:1px 6px; border-radius:3px; }
    .si-bottom { font-size:11px; color:#64748b; display:flex; gap:8px; flex-wrap:wrap; }
    .badge-statut { font-size:9px; padding:1px 5px; border-radius:3px; font-weight:600; }
    .badge-statut.rouge  { background:#ef4444; color:white; }
    .badge-statut.orange { background:#f59e0b; color:white; }
    .badge-statut.violet { background:#7c3aed; color:white; }
    .search-empty { font-size:12px; color:#64748b; padding:10px 14px; border:1px solid #2a3f5f; border-radius:6px; margin-top:4px; text-align:center; }
    .eleve-selected { display:flex; justify-content:space-between; align-items:center; background:#0f2240; border:1px solid #00d4aa; border-radius:6px; padding:10px 14px; }
    .es-info    { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
    .es-nom     { color:#e8f0fe; font-size:13px; font-weight:700; }
    .es-section { font-size:11px; color:#64748b; }
    .btn-changer{ background:transparent; border:1px solid #475569; color:#94a3b8; border-radius:5px; padding:4px 10px; font-size:11px; cursor:pointer; }
    .btn-changer:hover { border-color:#ef4444; color:#ef4444; }
    .type-btn { flex:1; padding:10px; border:1px solid #2a3f5f; border-radius:8px; background:#111827; color:#64748b; cursor:pointer; font-size:13px; transition:all 0.2s; }
    .type-btn:hover { border-color:#00d4aa; color:#e8f0fe; }
    .active-inscr { background:rgba(245,158,11,0.15); border-color:#f59e0b; color:#f59e0b; font-weight:600; }
    .active-mens  { background:rgba(0,212,170,0.15);  border-color:#00d4aa; color:#00d4aa; font-weight:600; }
    .tabs-bar { display:flex; gap:4px; margin-bottom:16px; }
    .tab-btn  { padding:8px 18px; border:1px solid #2a3f5f; border-radius:8px; background:transparent; color:#64748b; cursor:pointer; font-size:13px; transition:all 0.15s; }
    .tab-btn:hover  { border-color:#00d4aa; color:#e8f0fe; }
    .tab-btn.active { background:rgba(0,212,170,0.1); border-color:#00d4aa; color:#00d4aa; font-weight:600; }
    .danger { color:#ef4444; }
    .form-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
    .full { grid-column:1/-1; }
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
  nouvelleCharge       = { no_compte: '661', libelle: '', montant: 0, date: new Date().toISOString().split('T')[0], compte_credit: '571', compte_fournisseur: '401' };

  planCharges = [
    { label: '601 — Achats de marchandises',          value: '601' },
    { label: '604 — Achats de fournitures',           value: '604' },
    { label: '606 — Eau, électricité, fournitures',   value: '606' },
    { label: '611 — Transports',                      value: '611' },
    { label: '612 — Loyer',                           value: '612' },
    { label: '613 — Locations diverses',              value: '613' },
    { label: '621 — Personnel extérieur',             value: '621' },
    { label: '622 — Rémunérations intermédiaires',    value: '622' },
    { label: '623 — Publicité',                       value: '623' },
    { label: '624 — Transport du personnel',          value: '624' },
    { label: '625 — Déplacements et missions',        value: '625' },
    { label: '631 — Frais bancaires',                 value: '631' },
    { label: '641 — Impôts et taxes',                 value: '641' },
    { label: '651 — Pertes sur créances',             value: '651' },
    { label: '658 — Charges diverses',                value: '658' },
    { label: '661 — Salaires',                        value: '661' },
    { label: '662 — Charges sociales (IPRES/CSS)',    value: '662' },
    { label: '681 — Dotations aux amortissements',    value: '681' },
    { label: '221 — Bâtiments (acquisition)',         value: '221' },
    { label: '231 — Matériel et outillage (acq.)',    value: '231' },
    { label: '241 — Mobilier (acquisition)',          value: '241' },
    { label: '244 — Matériel informatique (acq.)',    value: '244' },
    { label: '245 — Matériel de transport (acq.)',    value: '245' },
  ];
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

  planChargesPC = computed(() => this.planCharges);
  comptesFournisseursPC = computed(() => this.planFournisseurs);
  comptesCreditPC = computed(() => this.comptesCredit);
  confirmAnnulVisible = false;
  paiementAnnuler: any = null;
  modifVisible      = false;
  paiementModifier: any = null;

  modifForm = {
    montant_inscription: 0, montant_mensualite: 0, montant_uniforme: 0,
    montant_fournitures: 0, montant_cantine: 0,    montant_divers: 0,
    mode_paiement: '', observations: '',
  };
  dialogVisible     = false;
  recuVisible       = false;
  recuData          = signal<any>(null);
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
    mode_paiement:       '',
    observations:        '',
  };

  private translate = inject(TranslateService);

  modesPaiement: any[] = [];

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
  }

  chargerPaiements() {
    this.loading.set(true);
    this.paiementsService.getPaiements().subscribe({
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
    const reste = data.reste || {};
    const nets  = data.fees_nets || {};
    if (this.typePaiement === 'INSCRIPTION') {
      this.form.montant_inscription  = reste.inscription  || 0;
      this.form.montant_uniforme     = reste.uniforme     || 0;
      this.form.montant_fournitures  = reste.fournitures  || 0;
      this.form.montant_mensualite   = 0;
      this.form.montant_cantine      = 0;
    } else {
      this.form.montant_mensualite   = nets.mensualite    || 0;
      this.form.montant_inscription  = 0;
      this.form.montant_uniforme     = 0;
      this.form.montant_fournitures  = 0;
    }
    this.form.montant_divers = 0;
  }

  private resetForm() {
    this.form = {
      montant_inscription: 0, montant_mensualite: 0, montant_uniforme: 0,
      montant_fournitures: 0, montant_cantine: 0, montant_divers: 0,
      mode_paiement: this.form.mode_paiement || '', observations: '',
    };
  }

  get totalForm(): () => number {
    return () => Object.entries(this.form)
      .filter(([k]) => k.startsWith('montant_'))
      .reduce((s, [, v]) => s + (Number(v) || 0), 0);
  }

  totalModifForm(): number {
    return Object.entries(this.modifForm)
      .filter(([k]) => k.startsWith('montant_'))
      .reduce((s, [, v]) => s + (Number(v) || 0), 0);
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
    if (!this.form.mode_paiement) {
      this.msg.add({ severity:'warn', summary: this.translate.instant('paiements.champ_requis'), detail: this.translate.instant('paiements.choisir_mode') });
      return;
    }
    if (this.totalForm() <= 0) {
      this.msg.add({ severity:'warn', summary: this.translate.instant('common.requis'), detail: this.translate.instant('paiements.montant_invalide') });
      return;
    }
    this.saving.set(true);
    this.paiementsService.creerPaiement({
      ...this.form,
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
    this.paiementsService.telechargerRecuPdf(d.paiement_id).subscribe({
      next: (blob: Blob) => {
        const url  = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href     = url;
        link.download = `recu_${d.no_piece}.pdf`;
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
    this.compta.getCharges().subscribe({
      next: res => { this.charges.set(Array.isArray(res) ? res : []); this.loadingCharges.set(false); },
      error: () => this.loadingCharges.set(false),
    });
  }

  totalCharges(): number {
    return this.charges().reduce((s, c) => s + (c.montant || 0), 0);
  }

  ouvrirDialogCharge() {
    this.nouvelleCharge = {
      no_compte: '661', libelle: '', montant: 0,
      date: new Date().toISOString().split('T')[0],
      compte_credit: '571', compte_fournisseur: '401',
    };
    this.dialogChargeVisible = true;
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
