import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { TagModule } from 'primeng/tag';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { TextareaModule } from 'primeng/textarea';
import { SelectModule } from 'primeng/select';
import { DatePickerModule } from 'primeng/datepicker';
import { ToastModule } from 'primeng/toast';
import { TooltipModule } from 'primeng/tooltip';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { ConfirmationService, MessageService } from 'primeng/api';
import { TranslateModule, TranslateService } from '@ngx-translate/core';

import { Catalogue, Devis, Prospect, ProspectsService, StatsProspects }
  from '../../core/services/prospects.service';

/**
 * Le fichier prospects de HADY GESMAN.
 *
 * L'écran est organisé autour d'une seule question : **quelle demande attend
 * encore un rappel ?** D'où l'ordre des indicateurs — les demandes jamais
 * rappelées d'abord, le chiffre d'affaires ensuite — et le bandeau d'alerte qui
 * ne s'affiche que lorsqu'il y a effectivement quelqu'un à rappeler.
 */
@Component({
  selector: 'app-prospects',
  imports: [CommonModule, FormsModule, TableModule, ButtonModule, TagModule,
            DialogModule, InputTextModule, TextareaModule, SelectModule,
            DatePickerModule, ToastModule, TooltipModule, ConfirmDialogModule,
            TranslateModule],
  providers: [MessageService, ConfirmationService],
  template: `
    <p-toast />
    <p-confirmDialog />

    <div class="page-header">
      <div>
        <h2 class="page-title">🎯 {{ 'prospects.title' | translate }}</h2>
        <span class="page-sub">{{ 'prospects.subtitle' | translate }}</span>
      </div>
      <p-button [label]="'prospects.nouveau' | translate" severity="success"
                icon="pi pi-plus" (onClick)="ouvrirCreation()" />
    </div>

    @if (stats(); as s) {
    <div class="kpi-grid">
      <div class="kpi-card" style="--acc:#f59e0b">
        <div class="kpi-icon">🔔</div>
        <div class="kpi-label">{{ 'prospects.kpi_a_relancer' | translate }}</div>
        <div class="kpi-value" style="color:#f59e0b">{{ s.a_relancer }}</div>
      </div>
      <div class="kpi-card" style="--acc:#0099ff">
        <div class="kpi-icon">🆕</div>
        <div class="kpi-label">{{ 'prospects.kpi_nouveaux' | translate }}</div>
        <div class="kpi-value" style="color:#0099ff">{{ s.nouveaux }}</div>
      </div>
      <div class="kpi-card" style="--acc:#00d4aa">
        <div class="kpi-icon">💬</div>
        <div class="kpi-label">{{ 'prospects.kpi_en_cours' | translate }}</div>
        <div class="kpi-value" style="color:#00d4aa">{{ s.en_cours }}</div>
      </div>
      <div class="kpi-card" style="--acc:#10b981">
        <div class="kpi-icon">🏆</div>
        <div class="kpi-label">{{ 'prospects.kpi_gagnes' | translate }}</div>
        <div class="kpi-value" style="color:#10b981">{{ s.gagnes }}</div>
      </div>
      <div class="kpi-card" style="--acc:#a855f7">
        <div class="kpi-icon">📈</div>
        <div class="kpi-label">{{ 'prospects.kpi_conversion' | translate }}</div>
        <div class="kpi-value" style="color:#a855f7">{{ s.taux_conversion }}%</div>
      </div>
      <div class="kpi-card" style="--acc:#64748b">
        <div class="kpi-icon">📅</div>
        <div class="kpi-label">{{ 'prospects.kpi_30j' | translate }}</div>
        <div class="kpi-value" style="color:#94a3b8">{{ s.recus_30j }}</div>
      </div>
    </div>
    }

    <!-- Le seul vrai échec de ce fichier : une demande reçue et jamais rappelée. -->
    @if (stats()?.jamais_contactes) {
    <div class="alerte-oubli">
      <span class="ao-icon">⚠️</span>
      <span class="ao-texte">
        {{ 'prospects.alerte_oubli' | translate:{ nombre: stats()!.jamais_contactes } }}
      </span>
      <p-button [label]="'prospects.voir_ces_demandes' | translate" size="small"
                severity="warn" [text]="true" (onClick)="filtrerNonTraites()" />
    </div>
    }

    <div class="filtres">
      <input pInputText [(ngModel)]="recherche" (keyup.enter)="charger()"
             [placeholder]="'prospects.recherche' | translate" class="f-recherche" />
      <p-select [(ngModel)]="filtreStatut" [options]="optionsStatut()"
                optionLabel="label" optionValue="value" (onChange)="charger()"
                [overlayOptions]="overlayNoHideOnScroll" styleClass="f-select" />
      <p-button [label]="'prospects.filtre_a_relancer' | translate" size="small"
                [outlined]="!filtreARelancer" severity="warn"
                (onClick)="basculerARelancer()" />
      <p-button icon="pi pi-refresh" [text]="true" (onClick)="charger()"
                [pTooltip]="'prospects.actualiser' | translate" />
      <span class="f-compte">{{ prospects().length }} {{ 'prospects.fiches' | translate }}</span>
    </div>

    <div class="table-card">
      <p-table [value]="prospects()" [loading]="loading()" styleClass="p-datatable-sm"
               [paginator]="true" [rows]="20" [rowHover]="true">
        <ng-template pTemplate="header">
          <tr>
            <th>{{ 'prospects.col_etablissement' | translate }}</th>
            <th>{{ 'prospects.col_contact' | translate }}</th>
            <th>{{ 'prospects.col_telephone' | translate }}</th>
            <th class="ta-r">{{ 'prospects.col_effectif' | translate }}</th>
            <th>{{ 'prospects.col_statut' | translate }}</th>
            <th>{{ 'prospects.col_source' | translate }}</th>
            <th>{{ 'prospects.col_recu' | translate }}</th>
            <th>{{ 'prospects.col_relance' | translate }}</th>
            <th></th>
          </tr>
        </ng-template>
        <ng-template pTemplate="body" let-p>
          <tr (dblclick)="ouvrirFiche(p)">
            <td>
              <div class="bold">{{ p.etablissement }}</div>
              <div class="sous">{{ p.ville || '—' }}@if (p.type_organisation) {<span> · {{ p.type_organisation }}</span>}</div>
            </td>
            <td>
              <div>{{ p.contact_nom || '—' }}</div>
              <div class="sous">{{ p.contact_fonction }}</div>
            </td>
            <td class="mono">{{ p.telephone || '—' }}</td>
            <td class="ta-r mono">{{ p.nb_eleves ?? '—' }}</td>
            <td><p-tag [value]="p.statut_libelle" [severity]="statutSeverity(p.statut)" /></td>
            <td><span class="source" [class.source-sama]="p.source === 'ASSISTANT'">{{ sourceLibelle(p.source) }}</span></td>
            <td class="mono sous">
              {{ p.cree_le | date:'dd/MM/yy' }}
              @if (p.statut === 'NOUVEAU' && p.anciennete_jours > 2) {
                <span class="retard">· {{ p.anciennete_jours }}j</span>
              }
            </td>
            <td class="mono">
              @if (p.relance_le) {
                <span [class.retard]="p.relance_en_retard">{{ p.relance_le | date:'dd/MM/yy' }}</span>
              } @else {
                <span class="sous">—</span>
              }
            </td>
            <td class="ta-r">
              <p-button icon="pi pi-eye" [text]="true" size="small"
                        (onClick)="ouvrirFiche(p)"
                        [pTooltip]="'prospects.ouvrir' | translate" />
            </td>
          </tr>
        </ng-template>
        <ng-template pTemplate="emptymessage">
          <tr><td colspan="9" class="empty-msg">{{ 'prospects.aucun' | translate }}</td></tr>
        </ng-template>
      </p-table>
    </div>

    <!-- ── Fiche ────────────────────────────────────────────────────── -->
    <p-dialog [(visible)]="ficheVisible" [modal]="true" [style]="{width:'860px'}"
              [header]="fiche()?.etablissement || ''" [draggable]="false">
      @if (fiche(); as f) {
        <div class="fiche-entete">
          <p-tag [value]="f.statut_libelle" [severity]="statutSeverity(f.statut)" />
          <span class="sous">{{ 'prospects.recu_le' | translate }} {{ f.cree_le | date:'dd/MM/yyyy' }}
                · {{ sourceLibelle(f.source) }}</span>
        </div>

        <div class="form-grid">
          <div class="separator">{{ 'prospects.sec_suivi' | translate }}</div>
          <div class="form-group">
            <label>{{ 'prospects.col_statut' | translate }}</label>
            <p-select [(ngModel)]="editStatut" [options]="statutsSaisie()"
                      optionLabel="libelle" optionValue="code"
                      [overlayOptions]="overlayNoHideOnScroll" />
          </div>
          <div class="form-group">
            <label>{{ 'prospects.col_relance' | translate }}</label>
            <p-datepicker [(ngModel)]="editRelance" dateFormat="dd/mm/yy"
                          [showButtonBar]="true" appendTo="body" />
          </div>
          @if (editStatut === 'PERDU') {
          <div class="form-group full">
            <label>{{ 'prospects.motif_perdu' | translate }}</label>
            <input pInputText [(ngModel)]="editMotif" />
          </div>
          }
          <div class="form-group full">
            <label>{{ 'prospects.notes' | translate }}</label>
            <textarea pTextarea rows="2" [(ngModel)]="editNotes"></textarea>
          </div>
          <div class="form-group full ta-r">
            <div>
              <p-button [label]="'common.enregistrer' | translate" size="small"
                        [loading]="saving()" (onClick)="enregistrerSuivi()" />
            </div>
          </div>

          <div class="separator">{{ 'prospects.sec_identification' | translate }}</div>
          <div class="lig"><span>{{ 'prospects.col_telephone' | translate }}</span><b class="mono">{{ f.telephone || '—' }}</b></div>
          <div class="lig"><span>{{ 'prospects.email' | translate }}</span><b>{{ f.email || '—' }}</b></div>
          <div class="lig"><span>{{ 'prospects.ville' | translate }}</span><b>{{ f.ville || '—' }}</b></div>
          <div class="lig"><span>{{ 'prospects.type_orga' | translate }}</span><b>{{ f.type_organisation || '—' }}</b></div>
          <div class="lig"><span>{{ 'prospects.adresse' | translate }}</span><b>{{ f['adresse'] || '—' }}</b></div>
          <div class="lig"><span>{{ 'prospects.site_web' | translate }}</span><b>{{ f['site_web'] || '—' }}</b></div>

          <div class="separator">{{ 'prospects.sec_contact' | translate }}</div>
          <div class="lig"><span>{{ 'prospects.nom' | translate }}</span><b>{{ f.contact_nom || '—' }}</b></div>
          <div class="lig"><span>{{ 'prospects.fonction' | translate }}</span><b>{{ f.contact_fonction || '—' }}</b></div>
          <div class="lig"><span>{{ 'prospects.col_telephone' | translate }}</span><b class="mono">{{ f.contact_telephone || '—' }}</b></div>
          <div class="lig"><span>{{ 'prospects.email' | translate }}</span><b>{{ f['contact_email'] || '—' }}</b></div>
          <div class="lig"><span>{{ 'prospects.pouvoir' | translate }}</span><b>{{ f['pouvoir_decisionnel'] || '—' }}</b></div>
          <div class="lig"><span>{{ 'prospects.origine' | translate }}</span><b>{{ (f['origines'] || []).join(', ') || '—' }}</b></div>

          <div class="separator">{{ 'prospects.sec_organisation' | translate }}</div>
          <div class="lig"><span>{{ 'prospects.col_effectif' | translate }}</span><b class="mono">{{ f.nb_eleves ?? '—' }}</b></div>
          <div class="lig"><span>{{ 'prospects.employes' | translate }}</span><b class="mono">{{ f['nb_employes'] ?? '—' }}</b></div>
          <div class="lig"><span>{{ 'prospects.classes' | translate }}</span><b class="mono">{{ f['nb_classes'] ?? '—' }}</b></div>
          <div class="lig"><span>{{ 'prospects.sites' | translate }}</span><b class="mono">{{ f['nb_sites'] ?? '—' }}</b></div>
          @if (f['disponibilites']) {
          <div class="lig full">
            <span>{{ 'prospects.disponibilites' | translate }}</span><b>{{ f['disponibilites'] }}</b>
          </div>
          }
          @if (f['message']) {
          <div class="bloc-message full">{{ f['message'] }}</div>
          }
        </div>

        <!-- ── Les propositions chiffrées ──────────────────────────── -->
        <div class="separator sep-hist">{{ 'prospects.sec_devis' | translate }}</div>
        <p class="aide">{{ 'prospects.aide_devis' | translate }}</p>

        @if (!f.devis?.length) {
        <div class="devis-vide">
          {{ 'prospects.aucun_devis' | translate }}
        </div>
        }

        @for (d of f.devis; track d.id) {
        <div class="devis-ligne">
          <div class="dv-gauche">
            <span class="dv-numero mono">{{ d.numero }}</span>
            <span class="dv-offre">{{ d.type_licence }} · {{ d.mois }} {{ 'prospects.mois' | translate }}</span>
          </div>
          <span class="dv-montant mono">{{ d.montant_total | number:'1.0-0' }} {{ 'common.fcfa' | translate }}</span>
          <p-tag [value]="d.expire ? ('prospects.devis_expire' | translate) : d.statut_libelle"
                 [severity]="d.expire ? 'danger' : devisSeverity(d.statut)" />
          <span class="dv-actions">
            <p-button icon="pi pi-file-pdf" [text]="true" size="small"
                      (onClick)="voirPdf(d)" [pTooltip]="'prospects.voir_pdf' | translate" />
            @if (d.statut === 'BROUILLON') {
              <p-button [label]="'prospects.valider' | translate"
                        size="small" severity="success" (onClick)="validerDevis(d)" />
            }
            @if (d.statut === 'VALIDE' && !d.expire) {
              <p-button [label]="'prospects.marquer_envoye' | translate"
                        size="small" [outlined]="true" (onClick)="envoyerDevis(d)" />
            }
            @if (d.statut === 'ENVOYE') {
              <p-button [label]="'prospects.accepte' | translate"
                        size="small" severity="success" [text]="true" (onClick)="trancherDevis(d, 'ACCEPTE')" />
              <p-button [label]="'prospects.refuse' | translate"
                        size="small" severity="danger" [text]="true" (onClick)="trancherDevis(d, 'REFUSE')" />
            }
            @if (d.statut === 'BROUILLON') {
              <p-button icon="pi pi-trash" [text]="true"
                        size="small" severity="danger" (onClick)="supprimerDevis(d)" />
            }
          </span>
        </div>
        }

        <div class="ta-r" style="margin-top:8px">
          <p-button [label]="'prospects.etablir_devis' | translate" icon="pi pi-plus"
                    size="small" [outlined]="true" (onClick)="ouvrirDevis()" />
        </div>

        <!-- ── Ce que le visiteur a dit à SAMA ─────────────────────── -->
        @if (f.conversations?.length) {
          <div class="separator sep-hist">{{ 'prospects.sec_conversation' | translate }}</div>
          <p class="aide">{{ 'prospects.aide_conversation' | translate }}</p>
          @for (c of f.conversations; track c.id) {
          <div class="conversation">
            <div class="conv-date mono">{{ c.date | date:'dd/MM/yyyy HH:mm' }}</div>
            @for (m of c.messages; track $index) {
            <div class="bulle" [class.bulle-sama]="m.role === 'assistant'">
              <span class="bulle-qui">{{ (m.role === 'assistant' ? 'prospects.sama' : 'prospects.visiteur') | translate }}</span>
              <span class="bulle-texte">{{ m.contenu }}</span>
            </div>
            }
          </div>
          }
        }

        <!-- ── L'historique de la relation ─────────────────────────── -->
        <div class="separator sep-hist">{{ 'prospects.sec_echanges' | translate }}</div>

        <div class="nouvel-echange">
          <p-select [(ngModel)]="echangeCanal" [options]="canauxSaisie()"
                    optionLabel="libelle" optionValue="code" styleClass="ne-canal"
                    [overlayOptions]="overlayNoHideOnScroll" appendTo="body" />
          <input pInputText [(ngModel)]="echangeResume" class="ne-resume"
                 [placeholder]="'prospects.echange_placeholder' | translate"
                 (keyup.enter)="consigner()" />
          <p-button [label]="'prospects.consigner' | translate" size="small"
                    [loading]="saving()" (onClick)="consigner()" />
        </div>

        <div class="timeline">
          @for (e of f.interactions; track e.id) {
          <div class="tl-item">
            <div class="tl-tete">
              <span class="tl-canal">{{ e.canal_libelle }}</span>
              <span class="tl-date mono">{{ e.date | date:'dd/MM/yyyy' }}</span>
              @if (e.auteur) {<span class="tl-auteur">· {{ e.auteur }}</span>}
            </div>
            <div class="tl-resume">{{ e.resume }}</div>
          </div>
          }
        </div>
      }

      <ng-template pTemplate="footer">
        <p-button [label]="'common.supprimer' | translate" severity="danger"
                  [text]="true" (onClick)="confirmerSuppression()" />
        <p-button [label]="'common.fermer' | translate" [text]="true"
                  (onClick)="ficheVisible = false" />
      </ng-template>
    </p-dialog>

    <!-- ── Établir un devis ─────────────────────────────────────────── -->
    <p-dialog [(visible)]="devisVisible" [modal]="true" [style]="{width:'620px'}"
              [header]="'prospects.etablir_devis' | translate" [draggable]="false">
      <p class="aide">{{ 'prospects.aide_chiffrage' | translate }}</p>
      <div class="form-grid">
        <div class="form-group">
          <label>{{ 'prospects.licence' | translate }}</label>
          <p-select [(ngModel)]="nouveauDevis.type_licence" [options]="licencesCatalogue()"
                    optionLabel="libelle" optionValue="code" (onChange)="rechiffrer()"
                    [overlayOptions]="overlayNoHideOnScroll" appendTo="body" />
        </div>
        <div class="form-group">
          <label>{{ 'prospects.cycle' | translate }}</label>
          <p-select [(ngModel)]="nouveauDevis.cycle" [options]="cyclesCatalogue()"
                    optionLabel="libelle" optionValue="code" (onChange)="surCycle()"
                    [overlayOptions]="overlayNoHideOnScroll" appendTo="body" />
        </div>
        <div class="form-group">
          <label>{{ 'prospects.duree_mois' | translate }}</label>
          <input pInputText type="number" [(ngModel)]="nouveauDevis.mois" (input)="rechiffrer()" />
        </div>
        <div class="form-group">
          <label>{{ 'prospects.frais_installation' | translate }}</label>
          <input pInputText type="number" [(ngModel)]="nouveauDevis.frais_installation" />
        </div>
        <div class="form-group full">
          <label>{{ 'prospects.prestations' | translate }}</label>
          <textarea pTextarea rows="2" [(ngModel)]="nouveauDevis.prestations"></textarea>
        </div>
        <div class="form-group">
          <label>{{ 'prospects.montant_prestations' | translate }}</label>
          <input pInputText type="number" [(ngModel)]="nouveauDevis.montant_prestations" />
        </div>
        <div class="form-group full">
          <label>{{ 'prospects.observations' | translate }}</label>
          <textarea pTextarea rows="2" [(ngModel)]="nouveauDevis.observations"></textarea>
        </div>
      </div>

      <!-- Le chiffrage affiché vient du catalogue servi par le serveur : c'est
           lui qui produira le devis, l'écran ne fait que le montrer. -->
      @if (chiffrage(); as c) {
      <div class="chiffrage">
        <div class="ch-ligne"><span>{{ 'prospects.licence' | translate }}</span>
          <b class="mono">{{ c.brut | number:'1.0-0' }}</b></div>
        @if (c.remise) {
        <div class="ch-ligne"><span>{{ 'prospects.remise' | translate }} ({{ c.taux }} %)</span>
          <b class="mono vert">− {{ c.remise | number:'1.0-0' }}</b></div>
        }
        <div class="ch-ligne ch-total"><span>{{ 'prospects.net_a_payer' | translate }}</span>
          <b class="mono">{{ c.total | number:'1.0-0' }} {{ 'common.fcfa' | translate }}</b></div>
      </div>
      }

      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler' | translate" [text]="true"
                  (onClick)="devisVisible = false" />
        <p-button [label]="'prospects.etablir' | translate" [loading]="saving()"
                  (onClick)="etablirDevis()" />
      </ng-template>
    </p-dialog>

    <!-- ── Création manuelle ────────────────────────────────────────── -->
    <p-dialog [(visible)]="creationVisible" [modal]="true" [style]="{width:'660px'}"
              [header]="'prospects.nouveau' | translate" [draggable]="false">
      <p class="aide">{{ 'prospects.aide_creation' | translate }}</p>
      <div class="form-grid">
        <div class="form-group full">
          <label>{{ 'prospects.col_etablissement' | translate }} *</label>
          <input pInputText [(ngModel)]="nouveau.etablissement" />
        </div>
        <div class="form-group">
          <label>{{ 'prospects.type_orga' | translate }}</label>
          <p-select [(ngModel)]="nouveau.type_organisation" [options]="typesOrganisation()"
                    [editable]="true" [overlayOptions]="overlayNoHideOnScroll" appendTo="body" />
        </div>
        <div class="form-group">
          <label>{{ 'prospects.ville' | translate }}</label>
          <input pInputText [(ngModel)]="nouveau.ville" />
        </div>
        <div class="form-group">
          <label>{{ 'prospects.col_telephone' | translate }} *</label>
          <input pInputText [(ngModel)]="nouveau.telephone" />
        </div>
        <div class="form-group">
          <label>{{ 'prospects.email' | translate }}</label>
          <input pInputText [(ngModel)]="nouveau.email" />
        </div>
        <div class="form-group">
          <label>{{ 'prospects.nom' | translate }} *</label>
          <input pInputText [(ngModel)]="nouveau.contact_nom" />
        </div>
        <div class="form-group">
          <label>{{ 'prospects.fonction' | translate }}</label>
          <input pInputText [(ngModel)]="nouveau.contact_fonction" />
        </div>
        <div class="form-group">
          <label>{{ 'prospects.col_effectif' | translate }}</label>
          <input pInputText [(ngModel)]="nouveau.nb_eleves" />
        </div>
        <div class="form-group">
          <label>{{ 'prospects.origine' | translate }}</label>
          <p-select [(ngModel)]="nouvelleOrigine" [options]="origines()"
                    [overlayOptions]="overlayNoHideOnScroll" appendTo="body" />
        </div>
        <div class="form-group full">
          <label>{{ 'prospects.premier_echange' | translate }}</label>
          <textarea pTextarea rows="2" [(ngModel)]="nouveau.resume"></textarea>
        </div>
      </div>
      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler' | translate" [text]="true"
                  (onClick)="creationVisible = false" />
        <p-button [label]="'common.enregistrer' | translate" [loading]="saving()"
                  (onClick)="creer()" />
      </ng-template>
    </p-dialog>
  `,
  styles: [`
    .page-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:18px; }
    .page-title { font-size:20px; font-weight:600; color:var(--text); margin:0; }
    .page-sub   { font-size:12px; color:var(--text-3); }

    .kpi-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; margin-bottom:16px; }
    .kpi-card { background:var(--surface); border:1px solid var(--border); border-left:3px solid var(--acc); border-radius:10px; padding:12px 14px; }
    .kpi-icon  { font-size:16px; }
    .kpi-label { font-size:11px; color:var(--text-3); text-transform:uppercase; letter-spacing:0.5px; margin-top:4px; }
    .kpi-value { font-size:22px; font-weight:700; font-family:monospace; }

    .alerte-oubli { display:flex; align-items:center; gap:12px; background:rgba(245,158,11,0.08);
      border:1px solid rgba(245,158,11,0.25); border-radius:10px; padding:10px 16px; margin-bottom:16px; }
    .ao-icon  { font-size:16px; }
    .ao-texte { flex:1; font-size:13px; color:#f59e0b; }

    .filtres { display:flex; align-items:center; gap:10px; margin-bottom:14px; flex-wrap:wrap; }
    .f-recherche { min-width:260px; }
    .f-compte { margin-left:auto; font-size:12px; color:var(--text-3); }
    ::ng-deep .f-select { min-width:200px; }

    .table-card { background:var(--surface); border:1px solid var(--border); border-radius:12px; overflow:hidden; }
    ::ng-deep .p-datatable .p-datatable-thead > tr > th { background:var(--surface-2) !important; color:var(--text-3) !important; font-size:11px !important; text-transform:uppercase !important; border-color:var(--border) !important; }
    ::ng-deep .p-datatable .p-datatable-tbody > tr { background:var(--surface) !important; color:var(--text-2) !important; border-bottom:1px solid rgba(42,63,95,0.4) !important; }
    ::ng-deep .p-datatable .p-datatable-tbody > tr:hover { background:var(--surface-hover) !important; }

    .mono { font-family:monospace; font-size:12px; }
    .bold { font-weight:600; color:var(--text); }
    .sous { font-size:11px; color:var(--text-3); }
    .ta-r { text-align:right; }
    .retard { color:#ef4444; font-weight:700; }
    .empty-msg { text-align:center; padding:40px; color:var(--text-3); }
    .source { font-size:11px; color:var(--text-3); }
    .source-sama { color:#a855f7; font-weight:600; }

    .fiche-entete { display:flex; align-items:center; gap:12px; margin-bottom:14px; }

    /* Jamais de classe .grid ici : les marges négatives de PrimeFlex rognent
       la première ligne des dialogs. */
    .form-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
    .form-group { display:flex; flex-direction:column; gap:6px; }
    .form-group.full, .lig.full, .bloc-message.full { grid-column:1/-1; }
    .form-group label { font-size:12px; color:var(--text-2); text-transform:uppercase; letter-spacing:0.5px; }
    .separator { grid-column:1/-1; font-size:12px; font-weight:600; color:#00d4aa; padding:8px 0 4px; border-top:1px solid var(--border); margin-top:4px; }
    .sep-hist { margin-top:18px; }

    .lig { display:flex; justify-content:space-between; gap:10px; font-size:13px; padding:4px 0; border-bottom:1px solid var(--surface-2); }
    .lig span { color:var(--text-3); }
    .lig b { color:var(--text); font-weight:500; text-align:right; }
    .bloc-message { background:var(--bg); border-radius:8px; padding:10px 12px; font-size:13px; color:var(--text-2); white-space:pre-wrap; }
    .aide { font-size:12px; color:var(--text-3); margin:0 0 12px; }

    .nouvel-echange { display:flex; gap:8px; align-items:center; margin:10px 0 14px; }
    .ne-resume { flex:1; }
    ::ng-deep .ne-canal { min-width:170px; }

    .devis-vide { font-size:12px; color:var(--text-3); padding:6px 0; }
    .devis-ligne { display:flex; align-items:center; gap:10px; padding:7px 0; border-bottom:1px solid var(--surface-2); }
    .dv-gauche { flex:1; display:flex; flex-direction:column; }
    .dv-numero { font-size:12px; font-weight:600; color:var(--text); }
    .dv-offre  { font-size:11px; color:var(--text-3); }
    .dv-montant { font-size:13px; font-weight:700; color:var(--text); }
    .dv-actions { display:flex; align-items:center; gap:4px; }

    .chiffrage { background:var(--bg); border-radius:8px; padding:10px 14px; margin-top:14px; }
    .ch-ligne { display:flex; justify-content:space-between; font-size:13px; padding:4px 0; }
    .ch-ligne span { color:var(--text-3); }
    .ch-total { border-top:1px solid var(--border); margin-top:4px; padding-top:8px; font-size:15px; }
    .ch-total b { color:#00d4aa; }
    .vert { color:#10b981; }

    .conversation { background:var(--bg); border-radius:8px; padding:10px 12px; margin-bottom:10px; max-height:260px; overflow-y:auto; }
    .conv-date { font-size:11px; color:var(--text-3); margin-bottom:8px; }
    .bulle { display:block; font-size:13px; line-height:1.5; margin-bottom:8px; white-space:pre-wrap; }
    .bulle-qui { display:block; font-size:10px; text-transform:uppercase; letter-spacing:0.5px; color:var(--text-3); margin-bottom:2px; }
    .bulle-texte { color:var(--text-2); }
    .bulle-sama .bulle-qui { color:#a855f7; }

    .timeline { display:flex; flex-direction:column; gap:10px; max-height:280px; overflow-y:auto; }
    .tl-item { border-left:2px solid var(--border); padding:2px 0 2px 12px; }
    .tl-tete { display:flex; gap:8px; align-items:baseline; font-size:11px; }
    .tl-canal  { font-weight:600; color:#00d4aa; text-transform:uppercase; letter-spacing:0.5px; }
    .tl-date   { color:var(--text-3); }
    .tl-auteur { color:var(--text-3); }
    .tl-resume { font-size:13px; color:var(--text-2); white-space:pre-wrap; margin-top:2px; }
  `]
})
export class ProspectsComponent implements OnInit {
  private service   = inject(ProspectsService);
  private msg       = inject(MessageService);
  private confirm   = inject(ConfirmationService);
  private translate = inject(TranslateService);

  prospects = signal<Prospect[]>([]);
  stats     = signal<StatsProspects | null>(null);
  fiche     = signal<Prospect | null>(null);
  loading   = signal(true);
  saving    = signal(false);

  refs = signal<any>({ statuts: [], sources: [], canaux: [],
                       types_organisation: [], origines: [] });

  statutsSaisie      = computed(() => this.refs().statuts || []);
  canauxSaisie       = computed(() => this.refs().canaux  || []);
  typesOrganisation  = computed(() => this.refs().types_organisation || []);
  origines           = computed(() => this.refs().origines || []);

  optionsStatut = computed(() => [
    { label: this.translate.instant('prospects.tous_statuts'), value: '' },
    { label: this.translate.instant('prospects.filtre_en_cours'), value: 'EN_COURS' },
    ...(this.refs().statuts || []).map((s: any) => ({ label: s.libelle, value: s.code })),
  ]);

  // PrimeNG ferme ses overlays au scroll : dans un dialog long, le menu se
  // refermait dès qu'on faisait défiler pour l'atteindre.
  overlayNoHideOnScroll = {
    listener: (_e: any, options: any) => options.type === 'scroll' ? false : options.valid,
  };

  recherche = '';
  filtreStatut = '';
  filtreARelancer = false;

  ficheVisible = false;
  creationVisible = false;

  editStatut = 'NOUVEAU';
  editRelance: Date | null = null;
  editNotes = '';
  editMotif = '';

  echangeCanal = 'APPEL';
  echangeResume = '';

  nouveau: any = {};
  nouvelleOrigine = '';

  // ── Devis ──────────────────────────────────────────────────────────
  catalogue = signal<Catalogue | null>(null);
  devisVisible = false;
  nouveauDevis: any = { type_licence: 'PRO', cycle: 'ANNUEL', mois: 12,
                        frais_installation: 0, prestations: '',
                        montant_prestations: 0, observations: '' };

  licencesCatalogue = computed(() =>
    (this.catalogue()?.licences || []).filter(l => l.code !== 'ESSAI'));
  cyclesCatalogue = computed(() => this.catalogue()?.cycles || []);

  /**
   * Le chiffrage montré pendant la saisie. Il reproduit celui du serveur, qui
   * reste seul à produire la pièce : l'écran n'affiche jamais un montant qu'il
   * a décidé, il montre à l'avance celui qui sera établi. Le devis renvoyé
   * après l'établissement fait foi.
   */
  chiffrage = computed(() => {
    const grille = this.catalogue();
    if (!grille) return null;
    const ligne = grille.licences.find(l => l.code === this.nouveauDevis.type_licence);
    if (!ligne) return null;

    const mois = Math.max(Number(this.nouveauDevis.mois) || 0, 0);
    const brut = ligne.prix_mensuel * mois;
    const taux = this.nouveauDevis.cycle === 'ANNUEL' ? grille.taux_remise_annuelle : 0;
    const remise = Math.round(brut * taux);
    const extras = (Number(this.nouveauDevis.frais_installation) || 0)
                 + (Number(this.nouveauDevis.montant_prestations) || 0);
    return { brut, remise, taux: Math.round(taux * 100),
             total: brut - remise + extras };
  });

  ngOnInit() {
    this.service.referentiels().subscribe({ next: r => this.refs.set(r) });
    this.service.catalogue().subscribe({ next: c => this.catalogue.set(c) });
    this.charger();
  }

  charger() {
    this.loading.set(true);
    this.service.liste({
      q: this.recherche.trim() || undefined,
      statut: this.filtreStatut || undefined,
      a_relancer: this.filtreARelancer ? '1' : undefined,
    }).subscribe({
      next: liste => { this.prospects.set(liste); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
    this.service.stats().subscribe({ next: s => this.stats.set(s) });
  }

  basculerARelancer() { this.filtreARelancer = !this.filtreARelancer; this.charger(); }

  filtrerNonTraites() {
    this.filtreStatut = 'NOUVEAU';
    this.filtreARelancer = false;
    this.recherche = '';
    this.charger();
  }

  ouvrirFiche(p: Prospect) {
    this.service.fiche(p.id).subscribe({ next: f => {
      this.fiche.set(f);
      this.editStatut  = f.statut;
      // `relance_le` arrive en `YYYY-MM-DD` : construit tel quel, il serait lu
      // en UTC et pourrait reculer d'un jour à l'affichage.
      this.editRelance = f.relance_le ? this.enDateLocale(f.relance_le) : null;
      this.editNotes   = f['notes'] || '';
      this.editMotif   = f['perdu_motif'] || '';
      this.echangeResume = '';
      this.ficheVisible = true;
    }});
  }

  enregistrerSuivi() {
    const f = this.fiche();
    if (!f) return;
    this.saving.set(true);
    this.service.modifier(f.id, {
      statut: this.editStatut,
      relance_le: this.editRelance ? this.enChaineISO(this.editRelance) : null,
      notes: this.editNotes,
      perdu_motif: this.editStatut === 'PERDU' ? this.editMotif : '',
    }).subscribe({
      next: maj => {
        this.fiche.set(maj);
        this.editRelance = maj.relance_le ? this.enDateLocale(maj.relance_le) : null;
        this.saving.set(false);
        this.msg.add({ severity: 'success',
                       summary: this.translate.instant('prospects.suivi_enregistre') });
        this.charger();
      },
      error: () => this.saving.set(false),
    });
  }

  consigner() {
    const f = this.fiche();
    if (!f || !this.echangeResume.trim()) return;
    this.saving.set(true);
    this.service.consigner(f.id, {
      canal: this.echangeCanal,
      resume: this.echangeResume.trim(),
    }).subscribe({
      next: maj => {
        this.fiche.set(maj);
        this.editStatut = maj.statut;
        this.echangeResume = '';
        this.saving.set(false);
        this.charger();
      },
      error: () => this.saving.set(false),
    });
  }

  ouvrirCreation() {
    this.nouveau = { etablissement: '', type_organisation: '', ville: '',
                     telephone: '', email: '', contact_nom: '',
                     contact_fonction: '', nb_eleves: '', resume: '' };
    this.nouvelleOrigine = '';
    this.creationVisible = true;
  }

  creer() {
    if (!this.nouveau.etablissement?.trim()) {
      this.msg.add({ severity: 'warn',
                     summary: this.translate.instant('prospects.etablissement_requis') });
      return;
    }
    this.saving.set(true);
    this.service.creer({
      ...this.nouveau,
      origines: this.nouvelleOrigine ? [this.nouvelleOrigine] : [],
    }).subscribe({
      next: (p: any) => {
        this.saving.set(false);
        this.creationVisible = false;
        this.charger();
        // Le serveur rapproche les doublons : le dire, sinon on croit avoir
        // créé une fiche alors qu'on a complété une fiche existante.
        this.msg.add({
          severity: p.cree === false ? 'info' : 'success',
          summary: this.translate.instant(
            p.cree === false ? 'prospects.rattache_existant' : 'prospects.cree'),
          detail: p.etablissement,
        });
        this.ouvrirFiche(p);
      },
      error: err => {
        this.saving.set(false);
        this.msg.add({ severity: 'error',
                       summary: err?.error?.error || this.translate.instant('common.erreur') });
      },
    });
  }

  confirmerSuppression() {
    const f = this.fiche();
    if (!f) return;
    this.confirm.confirm({
      message: this.translate.instant('prospects.confirmer_suppression',
                                      { nom: f.etablissement }),
      accept: () => this.service.supprimer(f.id).subscribe({
        next: () => { this.ficheVisible = false; this.charger(); },
      }),
    });
  }

  // ── Devis ──────────────────────────────────────────────────────────
  ouvrirDevis() {
    // Pré-rempli avec ce que le diagnostic a laissé entendre, quand SAMA a
    // proposé une orientation. Ce n'est qu'un point de départ : c'est le
    // commercial qui décide de l'offre.
    const pressentie = this.fiche()?.['donnees_brutes']?.['licence_pressentie'];
    this.nouveauDevis = {
      type_licence: pressentie || 'PRO', cycle: 'ANNUEL', mois: 12,
      frais_installation: 0, prestations: '', montant_prestations: 0,
      observations: '',
    };
    this.devisVisible = true;
  }

  /** Le cycle commande la durée par défaut, sans l'imposer. */
  surCycle() {
    this.nouveauDevis.mois = this.nouveauDevis.cycle === 'ANNUEL' ? 12 : 1;
    this.rechiffrer();
  }

  /** Force le recalcul du signal : `nouveauDevis` est un objet mutable. */
  rechiffrer() { this.nouveauDevis = { ...this.nouveauDevis }; }

  etablirDevis() {
    const f = this.fiche();
    if (!f) return;
    this.saving.set(true);
    this.service.etablirDevis({ prospect: f.id, ...this.nouveauDevis }).subscribe({
      next: d => {
        this.saving.set(false);
        this.devisVisible = false;
        this.msg.add({ severity: 'success',
                       summary: this.translate.instant('prospects.devis_etabli'),
                       detail: d.numero });
        this.rafraichirFiche();
      },
      error: err => {
        this.saving.set(false);
        this.msg.add({ severity: 'error',
                       summary: err?.error?.error || this.translate.instant('common.erreur') });
      },
    });
  }

  validerDevis(d: Devis) {
    this.confirm.confirm({
      message: this.translate.instant('prospects.confirmer_validation',
                                      { numero: d.numero }),
      accept: () => this.service.validerDevis(d.id).subscribe({
        next: () => this.rafraichirFiche(),
      }),
    });
  }

  envoyerDevis(d: Devis) {
    // Aucun courriel n'est expédié : le commercial l'envoie lui-même, avec son
    // mot d'accompagnement. On enregistre seulement qu'il l'a fait.
    this.confirm.confirm({
      message: this.translate.instant('prospects.confirmer_envoi', { numero: d.numero }),
      accept: () => this.service.envoyerDevis(d.id).subscribe({
        next: () => this.rafraichirFiche(),
        error: err => this.msg.add({ severity: 'error',
                                     summary: err?.error?.error }),
      }),
    });
  }

  trancherDevis(d: Devis, reponse: 'ACCEPTE' | 'REFUSE') {
    this.service.trancherDevis(d.id, reponse).subscribe({
      next: () => this.rafraichirFiche(),
    });
  }

  supprimerDevis(d: Devis) {
    this.confirm.confirm({
      message: this.translate.instant('prospects.confirmer_suppression_devis',
                                      { numero: d.numero }),
      accept: () => this.service.supprimerDevis(d.id).subscribe({
        next: () => this.rafraichirFiche(),
      }),
    });
  }

  voirPdf(d: Devis) {
    // L'API demande un jeton : un simple lien ouvrirait une page d'erreur.
    this.service.pdfDevis(d.id).subscribe({
      next: blob => {
        const url = URL.createObjectURL(blob);
        window.open(url, '_blank');
        // Libéré après ouverture : l'onglet a déjà chargé le document.
        setTimeout(() => URL.revokeObjectURL(url), 60_000);
      },
    });
  }

  devisSeverity(statut: string): 'success' | 'warn' | 'danger' | 'info' | 'secondary' {
    const map: Record<string, 'success' | 'warn' | 'danger' | 'info' | 'secondary'> = {
      BROUILLON: 'warn', VALIDE: 'info', ENVOYE: 'secondary',
      ACCEPTE: 'success', REFUSE: 'danger',
    };
    return map[statut] || 'secondary';
  }

  private rafraichirFiche() {
    const f = this.fiche();
    if (f) this.service.fiche(f.id).subscribe({ next: maj => this.fiche.set(maj) });
    this.charger();
  }

  statutSeverity(statut: string): 'success' | 'warn' | 'danger' | 'info' | 'secondary' | 'contrast' {
    const map: Record<string, 'success' | 'warn' | 'danger' | 'info' | 'secondary' | 'contrast'> = {
      NOUVEAU: 'info', CONTACTE: 'secondary', QUALIFIE: 'warn',
      DEVIS: 'contrast', GAGNE: 'success', PERDU: 'danger',
    };
    return map[statut] || 'secondary';
  }

  sourceLibelle(code: string): string {
    const trouve = (this.refs().sources || []).find((s: any) => s.code === code);
    return trouve?.libelle || code;
  }

  /** `YYYY-MM-DD` → Date à minuit LOCAL (et non UTC, qui reculerait d'un jour
   *  à l'ouest de Greenwich). */
  private enDateLocale(iso: string): Date {
    const [a, m, j] = iso.split('-').map(Number);
    return new Date(a, m - 1, j);
  }

  /** Date locale → `YYYY-MM-DD`, sans passer par `toISOString()` qui convertit
   *  en UTC et décale la veille. */
  private enChaineISO(d: Date): string {
    const p = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
  }
}
