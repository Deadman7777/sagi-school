import { ChangeDetectionStrategy, ChangeDetectorRef, Component, ElementRef, OnInit, computed, inject, signal,
         viewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { TagModule } from 'primeng/tag';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { TextareaModule } from 'primeng/textarea';
import { SelectModule } from 'primeng/select';
import { ToastModule } from 'primeng/toast';
import { TooltipModule } from 'primeng/tooltip';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { ConfirmationService, MessageService, OverlayListenerOptions, OverlayOptions } from 'primeng/api';
import { TranslateModule, TranslateService } from '@ngx-translate/core';

import { DocumentCommercial, EcoleCliente, FacturationService, Justificatif, LigneDocument, Recu,
         SyntheseFacturation, TypeDocument } from '../../core/services/facturation.service';
import { Prospect, ProspectsService } from '../../core/services/prospects.service';

type Severite = 'success' | 'warn' | 'danger' | 'info' | 'secondary';

/**
 * Facturation commerciale de HADY GESMAN : proformas, factures, avoirs et reçus.
 *
 * L'écran ne calcule aucun montant : chaque enregistrement renvoie la pièce
 * recalculée par le serveur (lignes, HT, TVA, TTC, solde). Une pièce émise
 * s'affiche en lecture seule — on la corrige par un avoir.
 */
@Component({
  selector: 'app-facturation',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, FormsModule, TableModule, ButtonModule, TagModule, DialogModule,
            InputTextModule, TextareaModule, SelectModule, ToastModule, TooltipModule,
            ConfirmDialogModule, TranslateModule],
  providers: [MessageService, ConfirmationService],
  template: `
    <p-toast />
    <p-confirmDialog />

    <div class="page-header">
      <div>
        <h2 class="page-title">🧾 {{ 'facturation.title' | translate }}</h2>
        <span class="page-sub">{{ 'facturation.subtitle' | translate }}</span>
      </div>
      <div class="entete-actions">
        <p-button icon="pi pi-cog" severity="secondary" [outlined]="true"
                  [label]="'facturation.parametres' | translate" (onClick)="ouvrirParametres()" />
        <p-button icon="pi pi-plus" severity="info" [outlined]="true"
                  [label]="'facturation.nouvelle_proforma' | translate" (onClick)="ouvrirCreation('PROFORMA')" />
        <p-button icon="pi pi-plus" severity="success"
                  [label]="'facturation.nouvelle_facture' | translate" (onClick)="ouvrirCreation('FACTURE')" />
      </div>
    </div>

    @if (synthese(); as s) {
    <div class="kpi-grid">
      <div class="kpi-card" style="--acc:#0099ff">
        <div class="kpi-label">{{ 'facturation.kpi_facture' | translate }}</div>
        <div class="kpi-value">{{ s.facture | number:'1.0-0' }}</div>
      </div>
      <div class="kpi-card" style="--acc:#10b981">
        <div class="kpi-label">{{ 'facturation.kpi_encaisse' | translate }}</div>
        <div class="kpi-value vert">{{ s.encaisse | number:'1.0-0' }}</div>
      </div>
      <div class="kpi-card" style="--acc:#f59e0b">
        <div class="kpi-label">{{ 'facturation.kpi_restant' | translate }} ({{ s.nb_impayees }})</div>
        <div class="kpi-value orange">{{ s.restant | number:'1.0-0' }}</div>
      </div>
      <div class="kpi-card" style="--acc:#ef4444">
        <div class="kpi-label">{{ 'facturation.kpi_retard' | translate }} ({{ s.nb_en_retard }})</div>
        <div class="kpi-value rouge">{{ s.en_retard | number:'1.0-0' }}</div>
      </div>
      <div class="kpi-card" style="--acc:#8b5cf6">
        <div class="kpi-label">{{ 'facturation.kpi_acomptes' | translate }} ({{ s.nb_acomptes_attendus }})</div>
        <div class="kpi-value violet">{{ s.acomptes_attendus | number:'1.0-0' }}</div>
        <div class="sous">{{ 'facturation.kpi_prestations' | translate:{ n: s.nb_prestations_en_cours } }}</div>
      </div>
    </div>
    }

    <div class="filtres">
      @for (f of filtresType; track f.value) {
        <p-button size="small" [outlined]="filtre() !== f.value" [label]="f.label | translate"
                  (onClick)="filtre.set(f.value); charger()" />
      }
      <input pInputText [(ngModel)]="recherche" (keyup.enter)="charger()"
             [placeholder]="'facturation.recherche' | translate" class="f-recherche" />
      <p-button icon="pi pi-refresh" [text]="true" (onClick)="charger()" />
      <p-button icon="pi pi-file-pdf" [outlined]="true" size="small" [label]="'facturation.etat_pdf' | translate"
                [loading]="exportEtat()" (onClick)="telechargerEtat()" />
    </div>

    <div class="table-card">
      <p-table [value]="documents()" [loading]="loading()" styleClass="p-datatable-sm"
               [paginator]="true" [rows]="20" [rowHover]="true">
        <ng-template pTemplate="header">
          <tr>
            <th>{{ 'facturation.col_numero' | translate }}</th>
            <th>{{ 'facturation.col_client' | translate }}</th>
            <th>{{ 'facturation.col_date' | translate }}</th>
            <th class="ta-r">{{ 'facturation.col_ttc' | translate }}</th>
            <th>{{ 'facturation.col_situation' | translate }}</th>
            <th></th>
          </tr>
        </ng-template>
        <ng-template pTemplate="body" let-d>
          <tr (dblclick)="ouvrir(d.id)">
            <td>
              <div class="bold mono">{{ d.numero || ('facturation.brouillon' | translate) }}</div>
              <div class="sous">{{ d.type_libelle }}</div>
            </td>
            <td>
              <div>{{ d.client_nom }}</div>
              <div class="sous">{{ d.objet }}</div>
            </td>
            <td class="mono sous">
              {{ d.date_emission ? (d.date_emission | date:'dd/MM/yyyy') : '—' }}
              @if (d.date_echeance && d.type === 'FACTURE') {
                <div [class.retard]="d.en_retard">→ {{ d.date_echeance | date:'dd/MM/yyyy' }}</div>
              }
            </td>
            <td class="ta-r mono bold">{{ d.total_ttc | number:'1.0-0' }}</td>
            <td>
              <p-tag [value]="situation(d)" [severity]="severite(d)" />
              @if (d.etape === 'ACOMPTE_ATTENDU') {
                <div class="sous">{{ 'facturation.acompte' | translate }} {{ d.montant_acompte | number:'1.0-0' }}</div>
              } @else if (d.statut_paiement === 'PARTIELLE') {
                <div class="sous">{{ 'facturation.reste' | translate }} {{ d.solde | number:'1.0-0' }}</div>
              }
            </td>
            <td class="ta-r nowrap">
              <p-button icon="pi pi-eye" [text]="true" size="small" (onClick)="ouvrir(d.id)"
                        [pTooltip]="'facturation.ouvrir' | translate" />
              <p-button icon="pi pi-download" [text]="true" size="small" (onClick)="telecharger(d)"
                        [pTooltip]="'facturation.telecharger_pdf' | translate" />
            </td>
          </tr>
        </ng-template>
        <ng-template pTemplate="emptymessage">
          <tr><td colspan="6" class="empty-msg">{{ 'facturation.aucun_document' | translate }}</td></tr>
        </ng-template>
      </p-table>
    </div>

    <!-- ── Nouvelle pièce ────────────────────────────────────────────── -->
    <p-dialog [visible]="creationVisible()" (visibleChange)="creationVisible.set($event)" [modal]="true"
              [style]="{ width: '560px', maxWidth: '96vw' }" [draggable]="false"
              [header]="(nouveauType === 'PROFORMA' ? 'facturation.nouvelle_proforma' : 'facturation.nouvelle_facture') | translate">
      <div class="form-grid">
        <div class="form-group full">
          <label>{{ 'facturation.destinataire' | translate }}</label>
          <p-select [(ngModel)]="source" [options]="sources" optionLabel="label" optionValue="value"
                    appendTo="body" [overlayOptions]="overlaySansFermeture">
            <ng-template let-o pTemplate="item">{{ o.label | translate }}</ng-template>
            <ng-template let-o pTemplate="selectedItem">{{ o.label | translate }}</ng-template>
          </p-select>
        </div>
        @if (source === 'prospect') {
          <div class="form-group full">
            <label>{{ 'facturation.prospect' | translate }} *</label>
            <p-select [(ngModel)]="prospectId" [options]="prospects()" optionLabel="etablissement" optionValue="id"
                      [filter]="true" filterBy="etablissement" appendTo="body" [overlayOptions]="overlaySansFermeture" />
          </div>
        }
        @if (source === 'ecole') {
          <div class="form-group full">
            <label>{{ 'facturation.ecole' | translate }} *</label>
            <p-select [(ngModel)]="tenantId" [options]="ecoles()" optionLabel="nom" optionValue="id"
                      [filter]="true" filterBy="nom" appendTo="body" [overlayOptions]="overlaySansFermeture">
              <ng-template let-e pTemplate="item">
                {{ e.nom }} <span class="sous">· {{ e.licence_type || '—' }}{{ e.licence_fin ? ' → ' + (e.licence_fin | date:'dd/MM/yyyy') : '' }}</span>
              </ng-template>
            </p-select>
          </div>
          <div class="form-group full">
            <label>{{ 'facturation.renouvellement_mois' | translate }}</label>
            <input pInputText type="number" min="0" max="60" [(ngModel)]="renouvellementMois" />
            <small class="sous">{{ 'facturation.renouvellement_aide' | translate }}</small>
          </div>
        }
        @if (source === 'libre') {
          <div class="form-group full">
            <label>{{ 'facturation.client_nom' | translate }} *</label>
            <input pInputText [(ngModel)]="clientLibre" />
          </div>
        }
      </div>
      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler' | translate" [text]="true" (onClick)="creationVisible.set(false)" />
        <p-button [label]="'facturation.creer_brouillon' | translate" [loading]="saving()" (onClick)="creer()" />
      </ng-template>
    </p-dialog>

    <!-- ── Pièce : édition du brouillon, ou consultation ─────────────── -->
    <p-dialog [visible]="docVisible()" (visibleChange)="fermerDocument($event)" [modal]="true"
              [style]="{ width: '1000px', maxWidth: '98vw' }" [draggable]="false"
              [header]="titreDocument()">
      @if (doc(); as d) {
        <div class="doc-entete">
          <p-tag [value]="d.statut_libelle" [severity]="d.modifiable ? 'warn' : 'info'" />
          @if (d.type === 'FACTURE' && !d.modifiable) {
            <p-tag [value]="situation(d)" [severity]="severite(d)" />
          }
          @if (d['devis_numero']) { <span class="sous">{{ 'facturation.ref_devis' | translate }} {{ d['devis_numero'] }}</span> }
          @if (d['origine_numero']) { <span class="sous">{{ 'facturation.ref_origine' | translate }} {{ d['origine_numero'] }}</span> }
          <span class="espace"></span>
          <p-button icon="pi pi-eye" [text]="true" [label]="'facturation.apercu' | translate" (onClick)="voirPdf(d)" />
          <p-button icon="pi pi-download" [outlined]="true" [label]="'facturation.telecharger_pdf' | translate" (onClick)="telecharger(d)" />
          <p-button icon="pi pi-list" [outlined]="true" severity="secondary" [label]="'facturation.releve_pdf' | translate" (onClick)="telechargerReleve(d)" />
        </div>

        @if (d.modifiable) {
          <p class="aide">{{ 'facturation.aide_brouillon' | translate }}</p>
          <div class="form-grid trois">
            <div class="form-group"><label>{{ 'facturation.client_nom' | translate }} *</label><input pInputText [(ngModel)]="edition['client_nom']" /></div>
            <div class="form-group"><label>{{ 'facturation.client_contact' | translate }}</label><input pInputText [(ngModel)]="edition['client_contact']" /></div>
            <div class="form-group"><label>{{ 'facturation.client_ninea' | translate }}</label><input pInputText [(ngModel)]="edition['client_ninea']" /></div>
            <div class="form-group"><label>{{ 'facturation.client_adresse' | translate }}</label><input pInputText [(ngModel)]="edition['client_adresse']" /></div>
            <div class="form-group"><label>{{ 'facturation.client_ville' | translate }}</label><input pInputText [(ngModel)]="edition['client_ville']" /></div>
            <div class="form-group"><label>{{ 'facturation.client_telephone' | translate }}</label><input pInputText [(ngModel)]="edition['client_telephone']" /></div>
            <div class="form-group"><label>{{ 'facturation.client_email' | translate }}</label><input pInputText [(ngModel)]="edition['client_email']" /></div>
            <div class="form-group deux"><label>{{ 'facturation.objet' | translate }}</label><input pInputText [(ngModel)]="edition['objet']" /></div>
            @if (d.type === 'AVOIR') {
              <div class="form-group full"><label>{{ 'facturation.motif' | translate }} *</label><textarea pTextarea rows="2" [(ngModel)]="edition['motif']"></textarea></div>
            } @else {
              <div class="form-group">
                <label>{{ 'facturation.taux_acompte' | translate }}</label>
                <div class="acompte-saisie">
                  <input pInputText type="number" min="0" max="99" [(ngModel)]="edition['taux_acompte']" />
                  @if (+edition['taux_acompte'] !== tauxAcompteDefaut) {
                    <p-button size="small" [text]="true" [label]="tauxAcompteDefaut + ' %'" (onClick)="edition['taux_acompte'] = tauxAcompteDefaut" />
                  }
                </div>
                <small class="sous">{{ 'facturation.aide_acompte' | translate }}</small>
              </div>
              <div class="form-group">
                <label>{{ 'facturation.tva' | translate }}</label>
                <label class="case"><input type="checkbox" [(ngModel)]="edition['tva_applicable']" /> {{ 'facturation.tva_applicable' | translate }}</label>
              </div>
              @if (edition['tva_applicable']) {
                <div class="form-group"><label>{{ 'facturation.taux_tva' | translate }}</label><input pInputText type="number" [(ngModel)]="edition['taux_tva']" /></div>
              } @else {
                <div class="form-group deux"><label>{{ 'facturation.mention_tva' | translate }}</label><input pInputText [(ngModel)]="edition['mention_tva']" /></div>
              }
            }
          </div>

          <div class="separator">{{ 'facturation.lignes' | translate }}</div>
          <div class="table-scroll">
            <table class="lignes-edit">
              <thead>
                <tr>
                  <th style="min-width:230px">{{ 'facturation.designation' | translate }}</th>
                  <th style="width:90px">{{ 'facturation.quantite' | translate }}</th>
                  <th style="width:90px">{{ 'facturation.unite' | translate }}</th>
                  <th style="width:130px">{{ 'facturation.prix_unitaire' | translate }}</th>
                  <th style="width:120px" class="ta-r">{{ 'facturation.montant_ht' | translate }}</th>
                  <th style="width:40px"></th>
                </tr>
              </thead>
              <tbody>
                @for (l of lignes; track $index; let i = $index) {
                  <tr>
                    <td>
                      <input pInputText [(ngModel)]="l.designation" class="w-full" />
                      <input pInputText [(ngModel)]="l.detail" class="w-full detail" [placeholder]="'facturation.detail' | translate" />
                    </td>
                    <td><input pInputText type="number" min="0" step="any" [(ngModel)]="l.quantite" class="w-full" /></td>
                    <td><input pInputText [(ngModel)]="l.unite" class="w-full" /></td>
                    <td><input pInputText type="number" step="1" [(ngModel)]="l.prix_unitaire" class="w-full" /></td>
                    <td class="ta-r mono">{{ l.montant === undefined ? '…' : (l.montant | number:'1.0-0') }}</td>
                    <td><p-button icon="pi pi-times" [text]="true" size="small" severity="danger" (onClick)="retirerLigne(i)" /></td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
          <div class="ligne-actions">
            <p-button icon="pi pi-plus" size="small" [outlined]="true" [label]="'facturation.ajouter_ligne' | translate" (onClick)="ajouterLigne()" />
            <small class="sous">{{ 'facturation.aide_remise' | translate }}</small>
          </div>
        } @else {
          <div class="lecture">
            <div class="lecture-client">
              <div class="bold">{{ d['client_nom'] }}</div>
              @if (d['client_contact']) { <div>{{ d['client_contact'] }}</div> }
              <div class="sous">{{ d['client_adresse'] }} {{ d['client_ville'] }}</div>
              <div class="sous">{{ d['client_telephone'] }} {{ d['client_email'] }}</div>
            </div>
            <div class="lecture-dates sous">
              @if (d.date_emission) { <div>{{ 'facturation.emis_le' | translate }} {{ d.date_emission | date:'dd/MM/yyyy' }}</div> }
              @if (d.date_echeance && d.type === 'FACTURE') { <div [class.retard]="d.en_retard">{{ 'facturation.echeance' | translate }} {{ d.date_echeance | date:'dd/MM/yyyy' }}</div> }
              @if (d.date_validite && d.type === 'PROFORMA') { <div>{{ 'facturation.validite' | translate }} {{ d.date_validite | date:'dd/MM/yyyy' }}</div> }
            </div>
          </div>
          @if (d.type === 'AVOIR' && d['motif']) { <p class="aide">{{ 'facturation.motif' | translate }} : {{ d['motif'] }}</p> }
          <table class="lignes-lecture">
            @for (l of d.lignes; track l.id) {
              <tr>
                <td><div>{{ l.designation }}</div>@if (l.detail) {<div class="sous">{{ l.detail }}</div>}</td>
                <td class="ta-r mono">{{ l.quantite }} {{ l.unite }}</td>
                <td class="ta-r mono">{{ l.prix_unitaire | number:'1.0-0' }}</td>
                <td class="ta-r mono bold">{{ l.montant | number:'1.0-0' }}</td>
              </tr>
            }
          </table>
        }

        <div class="totaux">
          <div><span>{{ 'facturation.total_ht' | translate }}</span><b class="mono">{{ d.total_ht | number:'1.0-0' }}</b></div>
          @if (d['tva_applicable']) {
            <div><span>TVA {{ d['taux_tva'] }} %</span><b class="mono">{{ d.montant_tva | number:'1.0-0' }}</b></div>
          }
          <div class="ttc"><span>{{ (d['tva_applicable'] ? 'facturation.total_ttc' : 'facturation.net_a_payer') | translate }}</span><b class="mono">{{ d.total_ttc | number:'1.0-0' }} F</b></div>
          @if (!d['tva_applicable'] && d['mention_tva']) { <div class="sous">{{ d['mention_tva'] }}</div> }
        </div>

        <!-- Acompte : échéancier, et suivi de la prestation jusqu'à sa finalisation -->
        @if (d.echeancier?.length) {
          <div class="separator">{{ 'facturation.echeancier' | translate }}</div>
          <table class="lignes-lecture">
            @for (e of d.echeancier; track $index) {
              <tr>
                <td>{{ e.libelle }}</td>
                <td class="ta-r mono bold">{{ e.montant | number:'1.0-0' }}</td>
                <td class="ta-r" style="width:150px">
                  @if (e.etat !== 'A_VENIR') {
                    <p-tag [value]="('facturation.echeance_' + e.etat | translate) + (e.etat === 'PARTIEL' ? ' ' + (e.paye | number:'1.0-0') : '')"
                           [severity]="e.etat === 'PAYE' ? 'success' : e.etat === 'PARTIEL' ? 'warn' : 'secondary'" />
                  }
                </td>
              </tr>
            }
          </table>
        }
        @if (d.etape) {
          <div class="separator">{{ 'facturation.suivi_prestation' | translate }}</div>
          <div class="etapes">
            @for (e of etapes; track e; let i = $index) {
              <span class="etape" [class.faite]="rangEtape(d) > i" [class.courante]="rangEtape(d) === i">
                {{ 'facturation.etape_' + e | translate }}
              </span>
            }
          </div>
          <div class="suivi-actions">
            @if (d.prestation_demarree_le) { <span class="sous">{{ 'facturation.demarree_le' | translate }} {{ d.prestation_demarree_le | date:'dd/MM/yyyy' }}</span> }
            @if (d.prestation_livree_le) { <span class="sous">· {{ 'facturation.livree_le' | translate }} {{ d.prestation_livree_le | date:'dd/MM/yyyy' }}</span> }
            <span class="espace"></span>
            @if (!d.prestation_demarree_le) {
              <p-button icon="pi pi-play" size="small" [label]="'facturation.demarrer' | translate" [disabled]="!d.acompte_recu"
                        [pTooltip]="d.acompte_recu ? '' : ('facturation.acompte_requis' | translate)" (onClick)="demarrer(d)" />
            } @else if (!d.prestation_livree_le) {
              <p-button icon="pi pi-check-circle" size="small" severity="success" [label]="'facturation.livrer' | translate" (onClick)="livrer(d)" />
            }
          </div>
        }

        <!-- Paiements d'une facture émise -->
        @if (d.type === 'FACTURE' && !d.modifiable) {
          <div class="separator">{{ 'facturation.paiements' | translate }}</div>
          <div class="situation">
            <span>{{ 'facturation.encaisse' | translate }} <b class="mono">{{ d['montant_encaisse'] | number:'1.0-0' }}</b></span>
            @if (d['montant_avoirs']) { <span>{{ 'facturation.avoirs' | translate }} <b class="mono">{{ d['montant_avoirs'] | number:'1.0-0' }}</b></span> }
            <span>{{ 'facturation.reste' | translate }} <b class="mono" [class.rouge]="d.solde > 0">{{ d.solde | number:'1.0-0' }}</b></span>
          </div>
          @for (r of d.encaissements; track r.id) {
            <div class="recu" [class.annule]="r.annule">
              <span class="mono bold">{{ r.numero }}</span>
              <span class="sous">{{ r.date | date:'dd/MM/yyyy' }} · {{ r.mode_libelle }}{{ r.reference ? ' · ' + r.reference : '' }}</span>
              <span class="espace"></span>
              @if (r.annule) { <p-tag severity="danger" [value]="'facturation.annule' | translate" [pTooltip]="r.annule_motif" /> }
              <b class="mono">{{ r.montant | number:'1.0-0' }}</b>
              <p-button icon="pi pi-download" [text]="true" size="small" (onClick)="telechargerRecu(r)" [pTooltip]="'facturation.recu_pdf' | translate" />
              <p-button icon="pi pi-paperclip" [text]="true" size="small" (onClick)="choisirFichier({ encaissement: r.id })"
                        [pTooltip]="'facturation.joindre_preuve' | translate" />
              @if (!r.annule) {
                <p-button icon="pi pi-ban" [text]="true" size="small" severity="danger" (onClick)="annulerRecu(r)" [pTooltip]="'facturation.annuler_recu' | translate" />
              }
            </div>
            @for (j of r.justificatifs; track j.id) {
              <div class="piece">
                <i class="pi" aria-hidden="true" [class.pi-file-pdf]="j.mime_type === 'application/pdf'" [class.pi-image]="j.mime_type !== 'application/pdf'"></i>
                <button type="button" class="lien" (click)="voirJustificatif(j)">{{ j.nom }}</button>
                <span class="sous">{{ j.type_libelle }} · {{ taille(j.taille) }}</span>
                <p-button icon="pi pi-times" [text]="true" size="small" severity="danger" (onClick)="supprimerJustificatif(j)"
                          [pTooltip]="'facturation.retirer_piece' | translate" />
              </div>
            } @empty {
              @if (!r.annule) { <div class="piece sous manque">{{ 'facturation.sans_preuve' | translate }}</div> }
            }
          }
          @if (d.solde > 0) {
            @if (d.montant_acompte && !d.acompte_recu) {
              <div class="raccourcis">
                <p-button size="small" [outlined]="true" [label]="('facturation.payer_acompte' | translate) + ' · ' + (resteAcompte(d) | number:'1.0-0')"
                          (onClick)="paiement.montant = resteAcompte(d)" />
                <p-button size="small" [outlined]="true" [label]="('facturation.payer_tout' | translate) + ' · ' + (d.solde | number:'1.0-0')"
                          (onClick)="paiement.montant = d.solde" />
              </div>
            }
            <div class="form-grid quatre paiement">
              <div class="form-group"><label>{{ 'facturation.montant' | translate }}</label><input pInputText type="number" [(ngModel)]="paiement.montant" /></div>
              <div class="form-group"><label>{{ 'facturation.mode' | translate }}</label>
                <p-select [(ngModel)]="paiement.mode" [options]="modes()" optionLabel="label" optionValue="value" appendTo="body" [overlayOptions]="overlaySansFermeture" /></div>
              <div class="form-group"><label>{{ 'facturation.date' | translate }}</label><input pInputText type="date" [(ngModel)]="paiement.date" /></div>
              <div class="form-group"><label>{{ 'facturation.reference' | translate }}</label><input pInputText [(ngModel)]="paiement.reference" /></div>
              <div class="form-group full">
                <label>{{ 'facturation.preuve_paiement' | translate }}</label>
                <div class="fichier">
                  <p-button icon="pi pi-paperclip" size="small" [outlined]="true" severity="secondary"
                            [label]="(preuve ? 'facturation.changer_fichier' : 'facturation.choisir_fichier') | translate"
                            (onClick)="choisirPreuve()" />
                  @if (preuve) {
                    <span class="sous">{{ preuve.nom }}</span>
                    <p-button icon="pi pi-times" [text]="true" size="small" (onClick)="preuve = null" />
                  } @else {
                    <span class="sous">{{ 'facturation.aide_preuve' | translate }}</span>
                  }
                </div>
              </div>
            </div>
            <div class="ta-r"><p-button icon="pi pi-check" severity="success" [label]="'facturation.enregistrer_paiement' | translate" [loading]="saving()" (onClick)="encaisser(d)" /></div>
          }
        }

        @if (!d.modifiable && d.type !== 'AVOIR') {
          <div class="separator">{{ 'facturation.dossier' | translate }}</div>
          @for (j of d.justificatifs; track j.id) {
            <div class="piece">
              <i class="pi" aria-hidden="true" [class.pi-file-pdf]="j.mime_type === 'application/pdf'" [class.pi-image]="j.mime_type !== 'application/pdf'"></i>
              <button type="button" class="lien" (click)="voirJustificatif(j)">{{ j.nom }}</button>
              <span class="sous">{{ j.type_libelle }} · {{ taille(j.taille) }} · {{ j.created_at | date:'dd/MM/yyyy' }}</span>
              <p-button icon="pi pi-times" [text]="true" size="small" severity="danger" (onClick)="supprimerJustificatif(j)"
                        [pTooltip]="'facturation.retirer_piece' | translate" />
            </div>
          }
          <div class="fichier">
            <p-select [(ngModel)]="typePieceDossier" [options]="typesDossier()" optionLabel="label" optionValue="value"
                      appendTo="body" [overlayOptions]="overlaySansFermeture" styleClass="type-piece" />
            <p-button icon="pi pi-upload" size="small" [outlined]="true" [label]="'facturation.joindre' | translate"
                      (onClick)="choisirFichier({ document: d.id }, typePieceDossier)" />
            <small class="sous">{{ 'facturation.aide_dossier' | translate }}</small>
          </div>
        }

        @if (d.derives?.length) {
          <div class="separator">{{ 'facturation.pieces_liees' | translate }}</div>
          @for (x of d.derives; track x.id) {
            <div class="recu">
              <a class="lien" (click)="ouvrir(x.id)">{{ x.numero || ('facturation.brouillon' | translate) }}</a>
              <span class="sous">{{ x.type }} · {{ x.statut }}</span>
              <span class="espace"></span>
              <b class="mono">{{ x.total_ttc | number:'1.0-0' }}</b>
            </div>
          }
        }
      }
      <ng-template pTemplate="footer">
        @if (doc(); as d) {
          @if (d.modifiable) {
            <p-button icon="pi pi-trash" severity="danger" [text]="true" [label]="'facturation.supprimer' | translate" (onClick)="supprimer(d)" />
            <p-button icon="pi pi-save" [outlined]="true" [label]="'facturation.enregistrer' | translate" [loading]="saving()" (onClick)="enregistrer()" />
            <p-button icon="pi pi-send" severity="success" [label]="'facturation.emettre' | translate" [loading]="saving()" (onClick)="emettre(d)" />
          } @else {
            @if (d.type === 'PROFORMA' && d.statut === 'EMIS') {
              <p-button icon="pi pi-arrow-right" severity="success" [label]="'facturation.convertir' | translate" (onClick)="convertir(d)" />
            }
            @if (d.type === 'FACTURE') {
              <p-button icon="pi pi-replay" severity="danger" [outlined]="true" [label]="'facturation.etablir_avoir' | translate" (onClick)="etablirAvoir(d)" />
            }
            <p-button [label]="'common.fermer' | translate" [text]="true" (onClick)="fermerDocument(false)" />
          }
        }
      </ng-template>
    </p-dialog>

    <!-- ── Paramètres de facturation ──────────────────────────────────── -->
    <p-dialog [visible]="parametresVisible()" (visibleChange)="parametresVisible.set($event)" [modal]="true"
              [style]="{ width: '720px', maxWidth: '96vw' }" [draggable]="false"
              [header]="'facturation.parametres' | translate">
      <p class="aide">{{ 'facturation.aide_parametres' | translate }}</p>
      <div class="form-grid">
        <div class="form-group"><label>{{ 'facturation.raison_sociale' | translate }}</label><input pInputText [(ngModel)]="params['raison_sociale']" /></div>
        <div class="form-group"><label>{{ 'facturation.forme_juridique' | translate }}</label><input pInputText [(ngModel)]="params['forme_juridique']" /></div>
        <div class="form-group"><label>{{ 'facturation.client_adresse' | translate }}</label><input pInputText [(ngModel)]="params['adresse']" /></div>
        <div class="form-group"><label>{{ 'facturation.client_ville' | translate }}</label><input pInputText [(ngModel)]="params['ville']" /></div>
        <div class="form-group"><label>{{ 'facturation.client_telephone' | translate }}</label><input pInputText [(ngModel)]="params['telephone']" /></div>
        <div class="form-group"><label>{{ 'facturation.client_email' | translate }}</label><input pInputText [(ngModel)]="params['email']" /></div>
        <div class="form-group"><label>NINEA</label><input pInputText [(ngModel)]="params['ninea']" /></div>
        <div class="form-group"><label>RCCM</label><input pInputText [(ngModel)]="params['rccm']" /></div>
        <div class="separator">{{ 'facturation.tva' | translate }}</div>
        <div class="form-group full">
          <label class="case"><input type="checkbox" [(ngModel)]="params['tva_applicable']" /> {{ 'facturation.tva_applicable' | translate }}</label>
          <small class="sous">{{ 'facturation.aide_tva' | translate }}</small>
        </div>
        @if (params['tva_applicable']) {
          <div class="form-group"><label>{{ 'facturation.taux_tva' | translate }}</label><input pInputText type="number" [(ngModel)]="params['taux_tva']" /></div>
        } @else {
          <div class="form-group full"><label>{{ 'facturation.mention_tva' | translate }}</label><input pInputText [(ngModel)]="params['mention_sans_tva']" /></div>
        }
        <div class="separator">{{ 'facturation.conditions' | translate }}</div>
        <div class="form-group"><label>{{ 'facturation.delai_paiement' | translate }}</label><input pInputText type="number" [(ngModel)]="params['delai_paiement_jours']" /></div>
        <div class="form-group"><label>{{ 'facturation.validite_proforma' | translate }}</label><input pInputText type="number" [(ngModel)]="params['validite_proforma_jours']" /></div>
        <div class="form-group"><label>{{ 'facturation.taux_acompte_defaut' | translate }}</label><input pInputText type="number" min="0" max="99" [(ngModel)]="params['taux_acompte_defaut']" /></div>
        <div class="form-group full"><label>{{ 'facturation.coordonnees_paiement' | translate }}</label><textarea pTextarea rows="2" [(ngModel)]="params['coordonnees_paiement']"></textarea></div>
        <div class="form-group full"><label>{{ 'facturation.conditions_generales' | translate }}</label><textarea pTextarea rows="2" [(ngModel)]="params['conditions']"></textarea></div>
      </div>
      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler' | translate" [text]="true" (onClick)="parametresVisible.set(false)" />
        <p-button [label]="'facturation.enregistrer' | translate" [loading]="saving()" (onClick)="enregistrerParametres()" />
      </ng-template>
    </p-dialog>

    <input #fichierInput type="file" accept="application/pdf,image/jpeg,image/png,image/webp,image/heic"
           class="cache" tabindex="-1" [attr.aria-label]="'facturation.choisir_fichier' | translate"
           (change)="fichierChoisi($event)" />
  `,
  styles: [`
    .page-header { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; flex-wrap:wrap; margin-bottom:18px; }
    .page-title { font-size:20px; font-weight:600; color:var(--text); margin:0; }
    .page-sub   { font-size:12px; color:var(--text-3); }
    .entete-actions { display:flex; gap:8px; flex-wrap:wrap; }

    .kpi-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; margin-bottom:16px; }
    .kpi-card { background:var(--surface); border:1px solid var(--border); border-left:3px solid var(--acc); border-radius:10px; padding:12px 14px; }
    .kpi-label { font-size:11px; color:var(--text-3); text-transform:uppercase; letter-spacing:0.5px; }
    .kpi-value { font-size:22px; font-weight:700; font-family:monospace; color:var(--text); }
    .vert { color:#10b981; } .orange { color:#f59e0b; } .rouge { color:#ef4444; }

    .filtres { display:flex; align-items:center; gap:8px; margin-bottom:14px; flex-wrap:wrap; }
    .f-recherche { min-width:240px; margin-left:auto; }

    .table-card { background:var(--surface); border:1px solid var(--border); border-radius:12px; overflow:hidden; }
    .mono { font-family:monospace; font-size:12px; }
    .bold { font-weight:600; color:var(--text); }
    .sous { font-size:11px; color:var(--text-3); }
    .ta-r { text-align:right; }
    .nowrap { white-space:nowrap; }
    .retard { color:#ef4444; font-weight:700; }
    .empty-msg { text-align:center; padding:40px; color:var(--text-3); }
    .aide { font-size:12px; color:var(--text-3); margin:0 0 12px; }
    .espace { flex:1; }

    /* Jamais de classe .grid : les marges négatives de PrimeFlex rognent les dialogs. */
    .form-grid { display:grid; grid-template-columns:1fr 1fr; gap:10px 12px; }
    .form-grid.trois { grid-template-columns:repeat(3, minmax(0,1fr)); }
    .form-grid.quatre { grid-template-columns:repeat(4, minmax(0,1fr)); }
    @media (max-width:760px) { .form-grid, .form-grid.trois, .form-grid.quatre { grid-template-columns:1fr; } }
    .form-group { display:flex; flex-direction:column; gap:5px; }
    .form-group.full, .separator { grid-column:1/-1; }
    .form-group.deux { grid-column:span 2; }
    .form-group label { font-size:11px; color:var(--text-2); text-transform:uppercase; letter-spacing:0.4px; }
    label.case { display:flex; align-items:center; gap:6px; text-transform:none; font-size:13px; color:var(--text); }
    .separator { font-size:12px; font-weight:600; color:#00d4aa; padding:10px 0 6px; border-top:1px solid var(--border); margin-top:10px; }

    .doc-entete { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-bottom:12px; }
    .table-scroll { overflow-x:auto; }
    .lignes-edit { width:100%; border-collapse:collapse; }
    .lignes-edit th { text-align:left; font-size:11px; color:var(--text-3); padding:4px; }
    .lignes-edit td { padding:4px; vertical-align:top; }
    .lignes-edit .detail { margin-top:4px; font-size:12px; }
    .ligne-actions { display:flex; align-items:center; gap:12px; margin-top:6px; flex-wrap:wrap; }

    .lecture { display:flex; justify-content:space-between; gap:12px; margin-bottom:10px; flex-wrap:wrap; }
    .lignes-lecture { width:100%; border-collapse:collapse; margin-bottom:6px; }
    .lignes-lecture td { padding:6px 4px; border-bottom:1px solid var(--surface-2); font-size:13px; color:var(--text-2); }

    .totaux { margin-left:auto; max-width:340px; margin-top:10px; }
    .totaux > div { display:flex; justify-content:space-between; padding:3px 0; font-size:13px; color:var(--text-2); }
    .totaux .ttc { border-top:1px solid var(--border); margin-top:4px; padding-top:6px; font-size:16px; }
    .totaux .ttc b { color:#00d4aa; }

    .situation { display:flex; gap:18px; flex-wrap:wrap; font-size:13px; color:var(--text-2); margin-bottom:8px; }
    .recu { display:flex; align-items:center; gap:10px; padding:6px 0; border-bottom:1px solid var(--surface-2); font-size:13px; color:var(--text-2); flex-wrap:wrap; }
    .recu.annule { opacity:.6; }
    .paiement { margin-top:10px; }
    .lien { color:#0099ff; cursor:pointer; font-weight:600; }
    .violet { color:#8b5cf6; }
    .cache { display:none; }
    button.lien { background:none; border:0; padding:0; font:inherit; font-weight:600; text-align:left; }
    .acompte-saisie { display:flex; align-items:center; gap:4px; }
    .acompte-saisie input { width:90px; }
    .etapes { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:8px; }
    .etape { font-size:12px; padding:4px 10px; border-radius:14px; border:1px solid var(--border); color:var(--text-3); }
    .etape.faite { border-color:#10b981; color:#10b981; }
    .etape.courante { border-color:#0099ff; background:rgba(0,153,255,.12); color:var(--text); font-weight:600; }
    .suivi-actions { display:flex; align-items:center; gap:8px; flex-wrap:wrap; }
    .raccourcis { display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }
    .piece { display:flex; align-items:center; gap:8px; padding:3px 0 3px 18px; font-size:12px; color:var(--text-2); flex-wrap:wrap; }
    .piece.manque { font-style:italic; }
    .fichier { display:flex; align-items:center; gap:8px; flex-wrap:wrap; margin-top:6px; }
  `],
})
export class FacturationComponent implements OnInit {
  private service = inject(FacturationService);
  private prospectsService = inject(ProspectsService);
  private msg = inject(MessageService);
  private confirm = inject(ConfirmationService);
  private translate = inject(TranslateService);
  private route = inject(ActivatedRoute);

  documents = signal<DocumentCommercial[]>([]);
  synthese = signal<SyntheseFacturation | null>(null);
  loading = signal(false);
  saving = signal(false);
  filtre = signal('');
  recherche = '';

  filtresType = [
    { value: '', label: 'facturation.filtre_tous' },
    { value: 'FACTURE', label: 'facturation.filtre_factures' },
    { value: 'PROFORMA', label: 'facturation.filtre_proformas' },
    { value: 'AVOIR', label: 'facturation.filtre_avoirs' },
    { value: 'IMPAYEES', label: 'facturation.filtre_impayees' },
    { value: 'SUIVI', label: 'facturation.filtre_suivi' },
  ];

  /** Les étapes d'une facture avec acompte, dans l'ordre. */
  etapes = ['ACOMPTE_ATTENDU', 'A_DEMARRER', 'EN_COURS', 'LIVREE', 'TERMINEE'];
  tauxAcompteDefaut = 40;
  typesDossier = signal<{ value: string; label: string }[]>([]);
  typePieceDossier = 'BON_COMMANDE';
  /** Preuve jointe au paiement en cours de saisie, envoyée une fois le reçu créé. */
  preuve: { nom: string; contenu: string } | null = null;
  private cibleFichier: { document?: string; encaissement?: string } | 'PREUVE' | null = null;
  private typeFichier = '';
  private fichierInput = viewChild<ElementRef<HTMLInputElement>>('fichierInput');
  private cdr = inject(ChangeDetectorRef);

  // Un menu déroulant dans un dialog ne se ferme pas au défilement.
  overlaySansFermeture: OverlayOptions = {
    listener: (_e: Event, options?: OverlayListenerOptions) => options?.type === 'scroll' ? false : options?.valid,
  };

  // ── Création ──
  creationVisible = signal(false);
  nouveauType: TypeDocument = 'FACTURE';
  sources = [
    { value: 'prospect', label: 'facturation.source_prospect' },
    { value: 'ecole', label: 'facturation.source_ecole' },
    { value: 'libre', label: 'facturation.source_libre' },
  ];
  source = 'prospect';
  prospectId = '';
  tenantId = '';
  renouvellementMois = 12;
  clientLibre = '';
  prospects = signal<Prospect[]>([]);
  ecoles = signal<EcoleCliente[]>([]);

  // ── Pièce ouverte ──
  docVisible = signal(false);
  doc = signal<DocumentCommercial | null>(null);
  edition: Record<string, any> = {};
  lignes: LigneDocument[] = [];
  paiement = { montant: 0, mode: 'VIREMENT', date: '', reference: '' };
  modes = signal<{ value: string; label: string }[]>([]);

  titreDocument = computed(() => {
    const d = this.doc();
    return d ? `${d.type_libelle} ${d.numero || '— ' + this.translate.instant('facturation.brouillon')}` : '';
  });

  // ── Paramètres ──
  parametresVisible = signal(false);
  params: Record<string, any> = {};

  ngOnInit() {
    this.charger();
    this.service.parametres().subscribe({ next: p => {
      this.modes.set(p.modes || []);
      this.tauxAcompteDefaut = p.taux_acompte_defaut ?? 40;
      // Le dossier d'une facture : tout sauf les preuves de paiement, qui vont sur le reçu.
      this.typesDossier.set((p.types_justificatif || []).filter(
        (t: { value: string }) => !['PREUVE_PAIEMENT', 'BORDEREAU', 'CHEQUE'].includes(t.value)));
    } });
    const id = this.route.snapshot.queryParamMap.get('document');
    if (id) this.ouvrir(id);
  }

  charger() {
    this.loading.set(true);
    this.service.documents(this.filtresActifs()).subscribe({
      next: docs => { this.documents.set(docs); this.loading.set(false); },
      error: err => { this.loading.set(false); this.erreur(err); },
    });
    this.service.synthese().subscribe({ next: s => this.synthese.set(s) });
  }

  /** Les mêmes filtres pour la liste et pour son export PDF. */
  private filtresActifs() {
    const f = this.filtre();
    return {
      type: f === 'SUIVI' ? 'FACTURE' : f && f !== 'IMPAYEES' ? f : undefined,
      impayees: f === 'IMPAYEES' ? 1 : undefined,
      suivi: f === 'SUIVI' ? 1 : undefined,
      recherche: this.recherche.trim() || undefined,
    };
  }

  exportEtat = signal(false);

  telechargerEtat() {
    this.exportEtat.set(true);
    this.service.etatPdf(this.filtresActifs()).subscribe({
      next: blob => { this.exportEtat.set(false); this.enregistrerFichier(blob, `etat-facturation-${this.aujourdhui()}.pdf`); },
      error: err => { this.exportEtat.set(false); this.erreur(err); },
    });
  }

  telechargerReleve(d: DocumentCommercial) {
    this.service.relevePdf(d.id).subscribe({
      next: blob => this.enregistrerFichier(blob,
        `releve-${(d.client_nom || 'client').replace(/[^A-Za-z0-9]+/g, '-')}-${this.aujourdhui()}.pdf`),
      error: err => this.erreur(err),
    });
  }

  situation(d: DocumentCommercial): string {
    if (d.statut === 'BROUILLON') return this.translate.instant('facturation.brouillon');
    if (d.type === 'FACTURE') {
      if (d.en_retard) return this.translate.instant('facturation.en_retard');
      if (d.etape) return this.translate.instant('facturation.etape_' + d.etape);
      return this.translate.instant('facturation.paiement_' + d.statut_paiement);
    }
    return d.statut_libelle;
  }

  severite(d: DocumentCommercial): Severite {
    if (d.statut === 'BROUILLON') return 'warn';
    if (d.type === 'AVOIR') return 'secondary';
    if (d.type === 'PROFORMA') return d.statut === 'CONVERTI' ? 'success' : 'info';
    if (d.en_retard) return 'danger';
    if (d.etape && d.etape !== 'TERMINEE') return d.etape === 'ACOMPTE_ATTENDU' ? 'warn' : 'info';
    return d.statut_paiement === 'PAYEE' ? 'success' : d.statut_paiement === 'PARTIELLE' ? 'warn' : 'info';
  }

  // ── Création ─────────────────────────────────────────────────────────
  ouvrirCreation(type: TypeDocument) {
    this.nouveauType = type;
    this.source = 'prospect';
    this.prospectId = this.tenantId = this.clientLibre = '';
    this.renouvellementMois = 12;
    if (!this.prospects().length) this.prospectsService.liste().subscribe({ next: p => this.prospects.set(p) });
    if (!this.ecoles().length) this.service.clients().subscribe({ next: e => this.ecoles.set(e) });
    this.creationVisible.set(true);
  }

  creer() {
    const data: Record<string, unknown> = { type: this.nouveauType };
    if (this.source === 'prospect') {
      if (!this.prospectId) return this.avertir('facturation.choisir_prospect');
      data['prospect'] = this.prospectId;
    } else if (this.source === 'ecole') {
      if (!this.tenantId) return this.avertir('facturation.choisir_ecole');
      data['tenant'] = this.tenantId;
      if (+this.renouvellementMois > 0) data['renouvellement_mois'] = +this.renouvellementMois;
    } else {
      if (!this.clientLibre.trim()) return this.avertir('facturation.choisir_client');
      data['client_nom'] = this.clientLibre.trim();
    }
    this.saving.set(true);
    this.service.creer(data).subscribe({
      next: d => { this.saving.set(false); this.creationVisible.set(false); this.afficher(d); this.charger(); },
      error: err => { this.saving.set(false); this.erreur(err); },
    });
  }

  // ── Pièce ────────────────────────────────────────────────────────────
  ouvrir(id: string) {
    this.service.document(id).subscribe({ next: d => this.afficher(d), error: err => this.erreur(err) });
  }

  private afficher(d: DocumentCommercial) {
    this.doc.set(d);
    this.edition = {
      client_nom: d['client_nom'], client_contact: d['client_contact'], client_adresse: d['client_adresse'],
      client_ville: d['client_ville'], client_telephone: d['client_telephone'], client_email: d['client_email'],
      client_ninea: d['client_ninea'], objet: d.objet, motif: d['motif'],
      tva_applicable: d['tva_applicable'], taux_tva: d['taux_tva'], mention_tva: d['mention_tva'],
      taux_acompte: d.taux_acompte,
    };
    this.lignes = (d.lignes || []).map(l => ({ ...l }));
    // Tant que l'acompte n'est pas réglé, c'est lui qu'on attend.
    const attendu = d.montant_acompte && !d.acompte_recu ? this.resteAcompte(d) : Math.max(d.solde, 0);
    this.paiement = { montant: attendu, mode: 'VIREMENT', date: this.aujourdhui(), reference: '' };
    this.preuve = null;
    this.docVisible.set(true);
  }

  fermerDocument(visible: boolean) {
    if (!visible) { this.docVisible.set(false); this.doc.set(null); }
  }

  ajouterLigne() {
    this.lignes = [...this.lignes, { designation: '', detail: '', quantite: 1, unite: '', prix_unitaire: 0 }];
  }

  retirerLigne(i: number) {
    this.lignes = this.lignes.filter((_, j) => j !== i);
  }

  private payloadEdition(): Record<string, unknown> {
    const data: Record<string, unknown> = { ...this.edition };
    if (this.doc()?.type === 'AVOIR') {
      delete data['tva_applicable']; delete data['taux_tva']; delete data['mention_tva']; delete data['taux_acompte'];
    } else {
      data['taux_acompte'] = Number(data['taux_acompte']) || 0;
    }
    data['lignes'] = this.lignes.map(l => ({
      designation: l.designation, detail: l.detail, quantite: +l.quantite, unite: l.unite,
      prix_unitaire: +l.prix_unitaire,
    }));
    return data;
  }

  enregistrer(ensuite?: (d: DocumentCommercial) => void) {
    const d = this.doc();
    if (!d) return;
    this.saving.set(true);
    this.service.modifier(d.id, this.payloadEdition()).subscribe({
      next: maj => {
        this.saving.set(false);
        this.afficher(maj);
        this.charger();
        if (ensuite) ensuite(maj);
        else this.msg.add({ severity: 'success', summary: this.translate.instant('facturation.enregistre') });
      },
      error: err => { this.saving.set(false); this.erreur(err); },
    });
  }

  emettre(d: DocumentCommercial) {
    this.confirm.confirm({
      header: this.translate.instant('facturation.emettre'),
      message: this.translate.instant('facturation.confirmer_emission'),
      accept: () => this.enregistrer(maj => {
        this.saving.set(true);
        this.service.emettre(maj.id).subscribe({
          next: emis => {
            this.saving.set(false);
            this.afficher(emis);
            this.charger();
            this.msg.add({ severity: 'success', summary: this.translate.instant('facturation.emis'), detail: emis.numero });
          },
          error: err => { this.saving.set(false); this.erreur(err); },
        });
      }),
    });
  }

  supprimer(d: DocumentCommercial) {
    this.confirm.confirm({
      header: this.translate.instant('facturation.supprimer'),
      message: this.translate.instant('facturation.confirmer_suppression'),
      accept: () => this.service.supprimer(d.id).subscribe({
        next: () => { this.fermerDocument(false); this.charger(); },
        error: err => this.erreur(err),
      }),
    });
  }

  convertir(d: DocumentCommercial) {
    this.service.convertir(d.id).subscribe({
      next: facture => { this.afficher(facture); this.charger(); },
      error: err => this.erreur(err),
    });
  }

  etablirAvoir(d: DocumentCommercial) {
    this.service.avoir(d.id, '').subscribe({
      next: avoir => {
        this.afficher(avoir);
        this.charger();
        this.msg.add({ severity: 'info', summary: this.translate.instant('facturation.avoir_prepare') });
      },
      error: err => this.erreur(err),
    });
  }

  encaisser(d: DocumentCommercial) {
    if (!(+this.paiement.montant > 0)) return this.avertir('facturation.montant_requis');
    this.saving.set(true);
    this.service.encaisser(d.id, {
      montant: +this.paiement.montant, mode: this.paiement.mode,
      date: this.paiement.date || undefined, reference: this.paiement.reference,
    }).subscribe({
      next: r => {
        const preuve = this.preuve;
        this.saving.set(false);
        this.afficher(r.facture);
        this.charger();
        this.msg.add({ severity: 'success', summary: this.translate.instant('facturation.paiement_enregistre'), detail: r.recu.numero });
        this.telechargerRecu(r.recu);
        if (preuve) this.envoyerJustificatif({ encaissement: r.recu.id }, preuve, 'PREUVE_PAIEMENT');
      },
      error: err => { this.saving.set(false); this.erreur(err); },
    });
  }

  resteAcompte(d: DocumentCommercial): number {
    return Math.max(d.montant_acompte - (d['montant_encaisse'] || 0), 0);
  }

  rangEtape(d: DocumentCommercial): number {
    // Terminée : toutes les étapes sont faites.
    return d.etape === 'TERMINEE' ? this.etapes.length : this.etapes.indexOf(d.etape || '');
  }

  demarrer(d: DocumentCommercial) {
    this.confirm.confirm({
      header: this.translate.instant('facturation.demarrer'),
      message: this.translate.instant('facturation.confirmer_demarrage'),
      accept: () => this.service.demarrer(d.id).subscribe({
        next: maj => { this.afficher(maj); this.charger(); },
        error: err => this.erreur(err),
      }),
    });
  }

  livrer(d: DocumentCommercial) {
    this.confirm.confirm({
      header: this.translate.instant('facturation.livrer'),
      message: this.translate.instant('facturation.confirmer_livraison'),
      accept: () => this.service.livrer(d.id).subscribe({
        next: maj => { this.afficher(maj); this.charger(); },
        error: err => this.erreur(err),
      }),
    });
  }

  // ── Pièces justificatives ────────────────────────────────────────────
  choisirPreuve() {
    this.cibleFichier = 'PREUVE';
    this.fichierInput()?.nativeElement.click();
  }

  choisirFichier(cible: { document?: string; encaissement?: string }, type = '') {
    this.cibleFichier = cible;
    this.typeFichier = type;
    this.fichierInput()?.nativeElement.click();
  }

  fichierChoisi(event: Event) {
    const input = event.target as HTMLInputElement;
    const fichier = input.files?.[0];
    input.value = '';               // le même fichier pourra être choisi à nouveau
    const cible = this.cibleFichier;
    if (!fichier || !cible) return;
    if (fichier.size > 5 * 1024 * 1024) return this.avertir('facturation.fichier_trop_gros');
    const lecteur = new FileReader();
    lecteur.onload = () => {
      const lu = { nom: fichier.name, contenu: String(lecteur.result) };
      if (cible === 'PREUVE') {
        this.preuve = lu;
        this.cdr.markForCheck();
      } else {
        this.envoyerJustificatif(cible, lu, this.typeFichier);
      }
    };
    lecteur.readAsDataURL(fichier);
  }

  private envoyerJustificatif(cible: { document?: string; encaissement?: string },
                              fichier: { nom: string; contenu: string }, type_piece: string) {
    this.service.ajouterJustificatif(cible, { ...fichier, type_piece }).subscribe({
      next: () => {
        this.msg.add({ severity: 'success', summary: this.translate.instant('facturation.piece_jointe'), detail: fichier.nom });
        const d = this.doc();
        if (d) this.ouvrir(d.id);
      },
      error: err => this.erreur(err),
    });
  }

  voirJustificatif(j: Justificatif) {
    this.service.fichierJustificatif(j.id).subscribe({
      next: blob => {
        const url = URL.createObjectURL(blob);
        window.open(url, '_blank');
        setTimeout(() => URL.revokeObjectURL(url), 60_000);
      },
      error: err => this.erreur(err),
    });
  }

  supprimerJustificatif(j: Justificatif) {
    this.confirm.confirm({
      header: this.translate.instant('facturation.retirer_piece'),
      message: this.translate.instant('facturation.confirmer_retrait', { nom: j.nom }),
      accept: () => this.service.supprimerJustificatif(j.id).subscribe({
        next: () => { const d = this.doc(); if (d) this.ouvrir(d.id); },
        error: err => this.erreur(err),
      }),
    });
  }

  taille(octets: number): string {
    return octets >= 1024 * 1024 ? `${(octets / 1024 / 1024).toFixed(1)} Mo` : `${Math.max(1, Math.round(octets / 1024))} Ko`;
  }

  annulerRecu(r: Recu) {
    const motif = window.prompt(this.translate.instant('facturation.motif_annulation'));
    if (!motif?.trim()) return;
    this.service.annulerRecu(r.id, motif.trim()).subscribe({
      next: () => { const d = this.doc(); if (d) this.ouvrir(d.id); this.charger(); },
      error: err => this.erreur(err),
    });
  }

  // ── PDF ──────────────────────────────────────────────────────────────
  voirPdf(d: DocumentCommercial) {
    this.service.pdf(d.id).subscribe({
      next: blob => {
        const url = URL.createObjectURL(blob);
        window.open(url, '_blank');
        setTimeout(() => URL.revokeObjectURL(url), 60_000);
      },
      error: err => this.erreur(err),
    });
  }

  telecharger(d: DocumentCommercial) {
    this.service.pdf(d.id).subscribe({
      next: blob => this.enregistrerFichier(blob, `${d.numero || d.type + '-BROUILLON'}.pdf`),
      error: err => this.erreur(err),
    });
  }

  telechargerRecu(r: Recu) {
    this.service.pdfRecu(r.id).subscribe({
      next: blob => this.enregistrerFichier(blob, `${r.numero}.pdf`),
      error: err => this.erreur(err),
    });
  }

  private enregistrerFichier(blob: Blob, nom: string) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = nom;
    a.click();
    URL.revokeObjectURL(url);
  }

  // ── Paramètres ───────────────────────────────────────────────────────
  ouvrirParametres() {
    this.service.parametres().subscribe({
      next: p => { this.params = { ...p }; this.parametresVisible.set(true); },
      error: err => this.erreur(err),
    });
  }

  enregistrerParametres() {
    const data = { ...this.params };
    delete data['modes'];
    this.saving.set(true);
    this.service.modifierParametres(data).subscribe({
      next: () => {
        this.saving.set(false);
        this.parametresVisible.set(false);
        this.msg.add({ severity: 'success', summary: this.translate.instant('facturation.enregistre') });
      },
      error: err => { this.saving.set(false); this.erreur(err); },
    });
  }

  // ── Outils ───────────────────────────────────────────────────────────
  private aujourdhui(): string {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }

  private avertir(cle: string) {
    this.msg.add({ severity: 'warn', summary: this.translate.instant(cle) });
  }

  private erreur(err: any) {
    this.msg.add({ severity: 'error', summary: this.translate.instant('common.erreur'),
                   detail: err?.error?.error || err?.error?.detail || this.translate.instant('facturation.erreur') });
  }
}
