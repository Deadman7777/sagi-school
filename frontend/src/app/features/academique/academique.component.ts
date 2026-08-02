import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AcademiqueService } from '../../core/services/academique.service';
import { ElevesService } from '../../core/services/eleves.service';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { MemorisationComponent } from './memorisation/memorisation.component';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { TooltipModule } from 'primeng/tooltip';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { TagModule } from 'primeng/tag';
import { InputNumberModule } from 'primeng/inputnumber';
import { MultiSelectModule } from 'primeng/multiselect';
import { MessageService } from 'primeng/api';
import { ToastModule } from 'primeng/toast';
import { TranslateModule, TranslateService } from '@ngx-translate/core';

@Component({
  selector: 'app-academique',
  standalone: true,
  imports: [CommonModule, FormsModule, TableModule, ButtonModule, DialogModule,
            InputTextModule, SelectModule, TagModule, InputNumberModule, MultiSelectModule, ToastModule, TooltipModule, TranslateModule,
            MemorisationComponent],
  providers: [MessageService],
  template: `
    <p-toast />
    <div class="page-header">
      <div>
        <h2 class="page-title">📚 {{ 'academique.title' | translate }}</h2>
        <span class="page-sub">{{ 'academique.subtitle' | translate }}</span>
      </div>
    </div>

    <!-- Onglets -->
    <div class="tabs-bar">
      <button class="tab-btn" [class.active]="onglet()==='parametrage'" (click)="onglet.set('parametrage')">⚙️ {{ 'academique.onglet_parametrage' | translate }}</button>
      <button class="tab-btn" [class.active]="onglet()==='notes'" (click)="onglet.set('notes')">📝 {{ 'academique.onglet_notes' | translate }}</button>
      <button class="tab-btn" [class.active]="onglet()==='resultats'" (click)="onglet.set('resultats')">📊 {{ 'academique.onglet_resultats' | translate }}</button>
      <button class="tab-btn" [class.active]="onglet()==='analyse'" (click)="onglet.set('analyse'); chargerAnalyse()">📈 Analyse</button>
      <button class="tab-btn" [class.active]="onglet()==='historique'" (click)="onglet.set('historique'); chargerHistorique()">📋 Historique</button>
      @if (estDaara) {
        <button class="tab-btn" [class.active]="onglet()==='memorisation'" (click)="onglet.set('memorisation')">🕌 {{ 'daara.onglet' | translate }}</button>
      }
    </div>

    <!-- MÉMORISATION CORANIQUE (Taxawu Daara) -->
    @if (onglet()==='memorisation') {
      <app-memorisation />
    }

    <!-- PARAMÉTRAGE -->
    <div *ngIf="onglet()==='parametrage'">
      <!-- Découpage de l'année : trimestres ou semestres -->
      <div class="periode-bar">
        <span class="periode-label">📅 Découpage de l'année scolaire</span>
        <p-select [options]="periodesOptions" [(ngModel)]="periode"
                  optionLabel="label" optionValue="value" styleClass="periode-select"
                  (onChange)="sauvegarderPeriode()" />
        <span class="periode-hint">Nombre :</span>
        <p-inputNumber [(ngModel)]="nbPeriodes" [min]="1" [max]="12" [showButtons]="true"
                       (onInput)="construireTrimestres()" (onBlur)="sauvegarderPeriode()" styleClass="periode-nb" />
        <span class="periode-hint">Ex. {{ periodeLabel() }} 1 … {{ periodeLabel() }} {{ nbPeriodes }}.</span>
      </div>

      <div class="param-grid">

        <!-- Classes -->
        <div class="param-card">
          <div class="pc-header">
            <span>🏫 {{ 'academique.classes' | translate }}</span>
            <p-button icon="pi pi-plus" [rounded]="true" [text]="true"
                      severity="success" (onClick)="ouvrirDialogClasse()" />
          </div>
          <div class="pc-body">
            <div class="pc-item" *ngFor="let c of classes()">
              <span>{{ c.nom }}</span>
              <span class="pc-right">
                <span class="badge">{{ c.niveau_nom }}</span>
                <span class="pc-actions">
                  <p-button icon="pi pi-pencil" [rounded]="true" [text]="true" size="small"
                            severity="secondary" (onClick)="ouvrirEditionClasse(c)" [pTooltip]="'common.modifier' | translate" tooltipPosition="top" />
                  <p-button icon="pi pi-trash" [rounded]="true" [text]="true" size="small"
                            severity="danger" (onClick)="supprimerClasse(c)" [pTooltip]="'common.supprimer' | translate" tooltipPosition="top" />
                </span>
              </span>
            </div>
            <div class="empty-msg" *ngIf="classes().length===0">{{ 'academique.aucune_classe' | translate }}</div>
          </div>
        </div>

        <!-- Matières -->
        <div class="param-card">
          <div class="pc-header">
            <span>📖 {{ 'academique.matieres' | translate }}</span>
            <span>
              <!-- Les filières d'un même établissement partagent un tronc
                   commun : recopier évite des centaines de saisies identiques,
                   et des coefficients qui divergent d'une classe à l'autre. -->
              <p-button icon="pi pi-copy" [rounded]="true" [text]="true" severity="secondary"
                        [disabled]="!classeFiltre || matieres().length === 0"
                        (onClick)="ouvrirCopieMatieres()"
                        pTooltip="Copier ces matières vers d'autres classes" tooltipPosition="top" />
              <p-button icon="pi pi-plus" [rounded]="true" [text]="true"
                        severity="success" (onClick)="ouvrirDialogMatiere()" />
            </span>
          </div>
          <div class="pc-filter">
            <p-select [options]="classes()" [(ngModel)]="classeFiltre"
                      optionLabel="nom" optionValue="id"
                      [placeholder]="'academique.filtrer_classe' | translate"
                      styleClass="w-full" (onChange)="chargerMatieres()" />
          </div>
          <div class="pc-body">
            <div class="pc-item" *ngFor="let m of matieres()">
              <span>{{ m.nom }}</span>
              <span class="pc-right">
                <span class="badge">{{ 'academique.coef' | translate }} {{ m.coefficient }}</span>
                <span class="pc-actions">
                  <p-button icon="pi pi-pencil" [rounded]="true" [text]="true" size="small"
                            severity="secondary" (onClick)="ouvrirEditionMatiere(m)" [pTooltip]="'common.modifier' | translate" tooltipPosition="top" />
                  <p-button icon="pi pi-trash" [rounded]="true" [text]="true" size="small"
                            severity="danger" (onClick)="supprimerMatiere(m)" [pTooltip]="'common.supprimer' | translate" tooltipPosition="top" />
                </span>
              </span>
            </div>
            <div class="empty-msg" *ngIf="matieres().length===0">{{ 'academique.selectionner_classe' | translate }}</div>
          </div>
        </div>

        <!-- Types d'évaluation -->
        <div class="param-card">
          <div class="pc-header">
            <span>📋 {{ 'academique.types_eval' | translate }}</span>
            <p-button icon="pi pi-plus" [rounded]="true" [text]="true"
                      severity="success" (onClick)="ouvrirDialogTypeEval()" />
          </div>
          <div class="pc-body">
            <div class="pc-item" *ngFor="let t of typesEval()">
              <span>{{ t.nom }}</span>
              <span class="pc-right">
                <span class="badge">{{ 'academique.poids' | translate }} {{ t.poids }}</span>
                <span class="pc-actions">
                  <p-button icon="pi pi-pencil" [rounded]="true" [text]="true" size="small"
                            severity="secondary" (onClick)="ouvrirEditionTypeEval(t)" [pTooltip]="'common.modifier' | translate" tooltipPosition="top" />
                  <p-button icon="pi pi-trash" [rounded]="true" [text]="true" size="small"
                            severity="danger" (onClick)="supprimerTypeEval(t)" [pTooltip]="'common.supprimer' | translate" tooltipPosition="top" />
                </span>
              </span>
            </div>
          </div>
        </div>

      </div>
    </div>

    <!-- SAISIE NOTES -->
    <div *ngIf="onglet()==='notes'">
      <div class="filters-bar" style="margin-bottom:16px">
        <p-select [options]="classes()" [(ngModel)]="classeNotes"
                  optionLabel="nom" optionValue="id"
                  [placeholder]="'academique.classe_filter' | translate" styleClass="filter-drop"
                  (onChange)="onClasseNotesChange()" />
        <p-select [options]="matieresNotes()" [(ngModel)]="matiereNotes"
                  optionLabel="nom" optionValue="id"
                  [placeholder]="'academique.matiere_filter' | translate" styleClass="filter-drop"
                  (onChange)="onMatiereNotesChange()" />
        <p-select [options]="trimestres" [(ngModel)]="trimestreNotes"
                  optionLabel="label" optionValue="value"
                  [placeholder]="periodeLabel()" styleClass="filter-drop"
                  (onChange)="onTrimestreNotesChange()" />
        <p-button [label]="'academique.ajouter_eval' | translate" severity="secondary" size="small"
                  (onClick)="ouvrirDialogEvaluation()" [disabled]="!matiereNotes" />
      </div>

      <!-- Message guide -->
      <div *ngIf="!classeNotes" class="empty-msg" style="padding:20px">
        ① Sélectionnez une classe → ② Sélectionnez une matière → ③ Choisissez le trimestre → Les élèves s'affichent automatiquement
      </div>

      <!-- Évaluations disponibles + création rapide -->
      <div *ngIf="classeNotes && matiereNotes" style="margin-bottom:12px">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
          <span style="font-size:11px;color:var(--text-3);text-transform:uppercase;font-weight:600">
            Évaluations — {{ trimestreNotes || 'Tous trimestres' }}
          </span>
          <span style="font-size:11px;color:var(--border)">{{ evaluations().length }} évaluation(s)</span>
        </div>
        <div class="evals-list" *ngIf="evaluations().length > 0">
          <div class="eval-card" *ngFor="let e of evaluations()"
               [class.active]="evalSelectionnee?.id === e.id"
               (click)="selectionnerEvaluation(e)">
            <div class="ec-titre">{{ (e.type_eval_nom || 'Évaluation') + (e.titre ? ' — ' + e.titre : '') }}</div>
            <div class="ec-info">{{ e.trimestre }} · {{ e.date_eval | date:'dd/MM/yyyy' }} · /{{ e.note_max }}</div>
          </div>
        </div>
        <div *ngIf="evaluations().length === 0" class="empty-msg" style="padding:10px;display:flex;align-items:center;gap:12px">
          <span>Aucune évaluation — créez-en une pour commencer la saisie</span>
          <p-button label="+ Créer évaluation" severity="success" size="small"
                    (onClick)="ouvrirDialogEvaluation()" />
        </div>
      </div>

      <!-- Grille de saisie notes — s'affiche dès qu'une évaluation est sélectionnée -->
      <div class="table-card" *ngIf="evalSelectionnee">
        <div style="padding:12px 16px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center">
          <div>
            <span style="color:var(--text);font-weight:600">
              {{ evalSelectionnee.matiere_nom }} · {{ evalSelectionnee.type_eval_nom }}{{ evalSelectionnee.titre ? ' — ' + evalSelectionnee.titre : '' }}
            </span>
            <span style="color:var(--text-3);font-size:11px;margin-left:8px">
              {{ evalSelectionnee.trimestre }} · /{{ evalSelectionnee.note_max }} ·
              {{ elevesNotes().length }} élève(s)
            </span>
          </div>
          <p-button [label]="'academique.enregistrer_tout' | translate" severity="success"
                    [loading]="saving()" (onClick)="sauvegarderNotes()" />
        </div>
        <p-table [value]="elevesNotes()" styleClass="p-datatable-sm">
          <ng-template pTemplate="header">
            <tr>
              <th style="width:60px">N°</th>
              <th>Élève</th>
              <th style="width:140px">Note /{{ evalSelectionnee.note_max }}</th>
              <th style="width:80px">Absent</th>
              <th style="width:80px">Saisie</th>
            </tr>
          </ng-template>
          <ng-template pTemplate="body" let-e>
            <tr>
              <td class="mono">{{ e.numero }}</td>
              <td class="bold">{{ e.nom_complet }}</td>
              <td>
                <p-inputNumber [(ngModel)]="e.note_saisie"
                               [min]="0" [max]="evalSelectionnee.note_max"
                               [disabled]="e.absent_saisie"
                               mode="decimal" [maxFractionDigits]="2"
                               [inputStyle]="{width:'100px'}" />
              </td>
              <td style="text-align:center">
                <input type="checkbox" [(ngModel)]="e.absent_saisie"
                       (change)="e.absent_saisie && (e.note_saisie = 0)" />
              </td>
              <td>
                <p-tag *ngIf="e.note_id" value="Déjà saisie" severity="success" />
                <p-tag *ngIf="!e.note_id" value="Nouvelle" severity="secondary" />
              </td>
            </tr>
          </ng-template>
          <ng-template pTemplate="emptymessage">
            <tr><td colspan="5" class="empty-msg">Aucun élève chargé pour cette classe</td></tr>
          </ng-template>
        </p-table>
      </div>
    </div>

    <!-- RÉSULTATS -->
    <div *ngIf="onglet()==='resultats'">
      <div class="filters-bar" style="margin-bottom:16px">
        <p-select [options]="classes()" [(ngModel)]="classeResultats"
                  optionLabel="nom" optionValue="id"
                  [placeholder]="'academique.classe_filter' | translate" styleClass="filter-drop" />
        <p-select [options]="trimestres" [(ngModel)]="trimestreResultats"
                  optionLabel="label" optionValue="value"
                  [placeholder]="periodeLabel()" styleClass="filter-drop" />
        <p-button [label]="'🔢 ' + ('academique.calculer_moyennes' | translate)" severity="success"
                  [loading]="calculant()" (onClick)="calculerMoyennes()" />
      </div>

      <!-- Résultats -->
      <div class="table-card" *ngIf="resultats().length > 0">
        <!-- Stats classe -->
        <div class="stats-classe" *ngIf="statsClasse()">
          <div class="sc-item"><span>{{ 'academique.moy_classe'    | translate }}</span><strong>{{ statsClasse().moy_classe }}</strong></div>
          <div class="sc-item"><span>{{ 'academique.plus_haute'    | translate }}</span><strong style="color:#10b981">{{ statsClasse().moy_max }}</strong></div>
          <div class="sc-item"><span>{{ 'academique.plus_basse'    | translate }}</span><strong style="color:#ef4444">{{ statsClasse().moy_min }}</strong></div>
          <div class="sc-item"><span>{{ 'academique.taux_reussite' | translate }}</span><strong style="color:#0099ff">{{ statsClasse().taux_reussite }}%</strong></div>
        </div>

        <p-table [value]="resultats()" styleClass="p-datatable-sm"
                 [paginator]="true" [rows]="20">
          <ng-template pTemplate="header">
            <tr>
              <th>{{ 'academique.rang'        | translate }}</th>
              <th>{{ 'academique.eleve_col'   | translate }}</th>
              <th *ngFor="let m of colonnesMatieres()">{{ m }}</th>
              <th>{{ 'academique.moy_generale'| translate }}</th>
              <th>{{ 'academique.appreciation'| translate }}</th>
              <th>{{ 'academique.bulletin'    | translate }}</th>
            </tr>
          </ng-template>
          <ng-template pTemplate="body" let-r>
            <tr>
              <td class="mono bold" style="color:#f59e0b">{{ r.rang }}e</td>
              <td class="bold">{{ r.eleve_nom }}</td>
              <td class="mono" *ngFor="let m of r.matieres" style="text-align:center">
                <div>{{ m.moyenne !== null ? m.moyenne : '—' }}</div>
                <div *ngIf="m.rang_matiere" style="font-size:10px;color:var(--text-3)">{{ m.rang_matiere }}e</div>
              </td>
              <td class="mono bold" style="color:#00d4aa">{{ r.moy_generale }}</td>
              <td>{{ r.appreciation_generale }}</td>
              <td>
                <p-button icon="pi pi-file-pdf" [rounded]="true" [text]="true"
                          severity="danger" (onClick)="telechargerBulletin(r.eleve_id)"
                          [title]="'academique.telecharger_bulletin' | translate" />
              </td>
            </tr>
          </ng-template>
        </p-table>
      </div>
    </div>

    <!-- ANALYSE PERFORMANCE -->
    <div *ngIf="onglet()==='analyse'">
      @if (loadingAnalyse()) {
        <div class="empty-msg" style="padding:40px; text-align:center; color:var(--text-3)">Chargement...</div>
      } @else if (analyse()) {
        <!-- KPI distribution -->
        <div class="analyse-grid" style="display:grid; grid-template-columns:repeat(5,1fr); gap:12px; margin-bottom:20px">
          <div class="kpi-card" style="background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:14px; text-align:center; border-top:3px solid #f59e0b">
            <div style="font-size:11px; color:var(--text-3); margin-bottom:4px">Excellent ≥16</div>
            <div style="font-size:22px; font-weight:700; color:#f59e0b">{{ analyse()!.distribution.excellent }}</div>
          </div>
          <div class="kpi-card" style="background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:14px; text-align:center; border-top:3px solid #10b981">
            <div style="font-size:11px; color:var(--text-3); margin-bottom:4px">Bien ≥14</div>
            <div style="font-size:22px; font-weight:700; color:#10b981">{{ analyse()!.distribution.bien }}</div>
          </div>
          <div class="kpi-card" style="background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:14px; text-align:center; border-top:3px solid #0099ff">
            <div style="font-size:11px; color:var(--text-3); margin-bottom:4px">Assez bien ≥12</div>
            <div style="font-size:22px; font-weight:700; color:#0099ff">{{ analyse()!.distribution.assez_bien }}</div>
          </div>
          <div class="kpi-card" style="background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:14px; text-align:center; border-top:3px solid #a855f7">
            <div style="font-size:11px; color:var(--text-3); margin-bottom:4px">Passable ≥10</div>
            <div style="font-size:22px; font-weight:700; color:#a855f7">{{ analyse()!.distribution.passable }}</div>
          </div>
          <div class="kpi-card" style="background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:14px; text-align:center; border-top:3px solid #ef4444">
            <div style="font-size:11px; color:var(--text-3); margin-bottom:4px">Insuffisant &lt;10</div>
            <div style="font-size:22px; font-weight:700; color:#ef4444">{{ analyse()!.distribution.insuffisant }}</div>
          </div>
        </div>

        <!-- Évolution par trimestre -->
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:16px">

          <div class="table-card" style="background:var(--surface); border:1px solid var(--border); border-radius:12px; overflow:hidden">
            <div style="padding:12px 16px; border-bottom:1px solid var(--border); font-weight:600; color:var(--text)">📈 Évolution par trimestre</div>
            <table style="width:100%; border-collapse:collapse">
              <thead><tr>
                <th style="padding:8px 12px; text-align:left; font-size:11px; color:var(--text-3); border-bottom:1px solid var(--border)">Trimestre</th>
                <th style="padding:8px 12px; text-align:right; font-size:11px; color:var(--text-3); border-bottom:1px solid var(--border)">Moyenne</th>
                <th style="padding:8px 12px; text-align:right; font-size:11px; color:var(--text-3); border-bottom:1px solid var(--border)">Élèves</th>
              </tr></thead>
              <tbody>
                @for (t of analyse()!.evolution; track t.trimestre) {
                  <tr style="border-bottom:1px solid rgba(42,63,95,0.3)">
                    <td style="padding:8px 12px; font-weight:600; color:#00d4aa">{{ t.trimestre }}</td>
                    <td style="padding:8px 12px; text-align:right; font-family:monospace; color:var(--text)">{{ t.moyenne }}/20</td>
                    <td style="padding:8px 12px; text-align:right; color:var(--text-3)">{{ t.nb_eleves }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>

          <!-- Top classes -->
          <div class="table-card" style="background:var(--surface); border:1px solid var(--border); border-radius:12px; overflow:hidden">
            <div style="padding:12px 16px; border-bottom:1px solid var(--border); font-weight:600; color:var(--text)">🏫 Top Classes — {{ analyse()!.trimestre_ref }}</div>
            <table style="width:100%; border-collapse:collapse">
              <thead><tr>
                <th style="padding:8px 12px; text-align:left; font-size:11px; color:var(--text-3); border-bottom:1px solid var(--border)">Rang</th>
                <th style="padding:8px 12px; text-align:left; font-size:11px; color:var(--text-3); border-bottom:1px solid var(--border)">Classe</th>
                <th style="padding:8px 12px; text-align:right; font-size:11px; color:var(--text-3); border-bottom:1px solid var(--border)">Moyenne</th>
                <th style="padding:8px 12px; text-align:right; font-size:11px; color:var(--text-3); border-bottom:1px solid var(--border)">Effectif</th>
              </tr></thead>
              <tbody>
                @for (c of analyse()!.top_classes; track c.rang) {
                  <tr style="border-bottom:1px solid rgba(42,63,95,0.3)">
                    <td style="padding:8px 12px; color:#f59e0b; font-weight:700">{{ c.rang }}</td>
                    <td style="padding:8px 12px; color:var(--text)">{{ c.classe }}</td>
                    <td style="padding:8px 12px; text-align:right; font-family:monospace; color:#00d4aa">{{ c.moyenne }}/20</td>
                    <td style="padding:8px 12px; text-align:right; color:var(--text-3)">{{ c.nb }}</td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        </div>

        <!-- Top élèves -->
        <div class="table-card" style="background:var(--surface); border:1px solid var(--border); border-radius:12px; overflow:hidden; margin-top:16px">
          <div style="padding:12px 16px; border-bottom:1px solid var(--border); font-weight:600; color:var(--text)">🏆 Top 10 Élèves — {{ analyse()!.trimestre_ref }}</div>
          <table style="width:100%; border-collapse:collapse">
            <thead><tr>
              <th style="padding:8px 12px; text-align:left; font-size:11px; color:var(--text-3); border-bottom:1px solid var(--border)">Rang</th>
              <th style="padding:8px 12px; text-align:left; font-size:11px; color:var(--text-3); border-bottom:1px solid var(--border)">Élève</th>
              <th style="padding:8px 12px; text-align:left; font-size:11px; color:var(--text-3); border-bottom:1px solid var(--border)">Classe</th>
              <th style="padding:8px 12px; text-align:right; font-size:11px; color:var(--text-3); border-bottom:1px solid var(--border)">Moyenne</th>
            </tr></thead>
            <tbody>
              @for (e of analyse()!.top_eleves; track e.rang) {
                <tr style="border-bottom:1px solid rgba(42,63,95,0.3)">
                  <td style="padding:8px 12px; font-weight:700; color:{{ e.rang === 1 ? '#f59e0b' : e.rang <= 3 ? '#0099ff' : 'var(--text-3)' }}">{{ e.rang }}</td>
                  <td style="padding:8px 12px; font-weight:600; color:var(--text)">{{ e.nom }}</td>
                  <td style="padding:8px 12px; color:var(--text-3)">{{ e.classe }}</td>
                  <td style="padding:8px 12px; text-align:right; font-family:monospace; color:#00d4aa; font-weight:700">{{ e.moyenne }}/20</td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      } @else {
        <div style="text-align:center; padding:60px; color:var(--text-3)">Aucune donnée disponible. Calculez d'abord les moyennes.</div>
      }
    </div>

    <!-- HISTORIQUE BULLETINS -->
    <div *ngIf="onglet()==='historique'">
      <!-- Filtres -->
      <div class="filters-bar" style="margin-bottom:14px;flex-wrap:wrap">
        <input pInputText [(ngModel)]="histSearch" placeholder="🔍 Rechercher un élève..."
               style="min-width:200px" (ngModelChange)="appliquerFiltreHistorique()" />
        <p-select [options]="histClasseOptions()" [(ngModel)]="histClasse"
                  optionLabel="label" optionValue="value"
                  placeholder="Toutes les classes" styleClass="filter-drop"
                  (onChange)="appliquerFiltreHistorique()" />
        <p-select [options]="trimestres" [(ngModel)]="histTrimestre"
                  optionLabel="label" optionValue="value"
                  placeholder="Tous les trimestres" styleClass="filter-drop"
                  (onChange)="appliquerFiltreHistorique()" />
        <p-select [options]="histAnneeOptions()" [(ngModel)]="histAnnee"
                  optionLabel="label" optionValue="value"
                  placeholder="Toutes les années" styleClass="filter-drop"
                  (onChange)="appliquerFiltreHistorique()" />
        <p-button icon="pi pi-refresh" severity="secondary" [text]="true"
                  [loading]="loadingHistorique()" (onClick)="chargerHistorique(true)" title="Rafraîchir" />
      </div>

      <!-- Compteur -->
      <div style="font-size:11px;color:var(--text-3);margin-bottom:10px" *ngIf="!loadingHistorique()">
        {{ historiqueFiltres().length }} bulletin(s) trouvé(s)
      </div>

      <!-- Chargement -->
      <div *ngIf="loadingHistorique()" class="empty-msg" style="padding:40px">Chargement...</div>

      <!-- Table -->
      <div class="table-card" *ngIf="!loadingHistorique()">
        @if (historiqueFiltres().length === 0) {
          <div class="empty-msg" style="padding:40px">
            Aucun bulletin calculé. Lancez d'abord le calcul des moyennes dans l'onglet Résultats.
          </div>
        } @else {
          <p-table [value]="historiqueFiltres()" styleClass="p-datatable-sm"
                   [paginator]="true" [rows]="25" [rowsPerPageOptions]="[25,50,100]">
            <ng-template pTemplate="header">
              <tr>
                <th style="width:32%">Élève</th>
                <th style="width:18%">Classe</th>
                <th style="width:10%">Trimestre</th>
                <th style="width:14%">Année scolaire</th>
                <th style="width:10%;text-align:center">Moyenne</th>
                <th style="width:8%;text-align:center">Matières</th>
                <th style="width:8%;text-align:center">PDF</th>
              </tr>
            </ng-template>
            <ng-template pTemplate="body" let-b>
              <tr>
                <td class="bold">{{ b.eleve_nom }}</td>
                <td style="color:var(--text-2)">{{ b.classe }}</td>
                <td>
                  <p-tag [value]="b.trimestre"
                         [severity]="b.trimestre==='T1' ? 'info' : b.trimestre==='T2' ? 'warn' : 'success'" />
                </td>
                <td class="mono" style="color:var(--text-3)">{{ b.annee_scolaire }}</td>
                <td style="text-align:center">
                  <span class="mono bold" [style.color]="b.moy_generale >= 10 ? '#10b981' : '#ef4444'">
                    {{ b.moy_generale }}
                  </span>
                </td>
                <td style="text-align:center;color:var(--text-3)">{{ b.nb_matieres }}</td>
                <td style="text-align:center">
                  <p-button icon="pi pi-file-pdf" [rounded]="true" [text]="true" severity="danger"
                            (onClick)="telechargerBulletinHistorique(b)"
                            title="Télécharger le bulletin PDF" />
                </td>
              </tr>
            </ng-template>
          </p-table>
        }
      </div>
    </div>

    <!-- Dialog Classe -->
    <p-dialog [header]="'🏫 ' + (formClasse.id ? ('common.modifier' | translate) : ('academique.nouvelle_classe' | translate))" [(visible)]="dialogClasseVisible"
              [modal]="true" [style]="{width:'400px'}">
      <div class="form-grid" style="grid-template-columns:1fr">
        <div class="form-group">
          <label>{{ 'academique.niveau' | translate }} *</label>
          <p-select appendTo="body" [overlayOptions]="overlayNoHideOnScroll" [options]="niveaux()" [(ngModel)]="formClasse.niveau"
                    optionLabel="nom" optionValue="id" styleClass="w-full" scrollHeight="320px" />
        </div>
        <div class="form-group">
          <label>{{ 'academique.nom' | translate }} *</label>
          <input pInputText [(ngModel)]="formClasse.nom" class="w-full" [placeholder]="'academique.ex_classe' | translate" />
        </div>
        <div class="form-group">
          <label>{{ 'academique.code' | translate }}</label>
          <input pInputText [(ngModel)]="formClasse.code" class="w-full" [placeholder]="'academique.ex_code' | translate" />
        </div>
      </div>
      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler' | translate" severity="secondary" (onClick)="dialogClasseVisible=false" />
        <p-button [label]="(formClasse.id ? 'common.enregistrer' : 'common.creer') | translate" severity="success" (onClick)="creerClasse()" />
      </ng-template>
    </p-dialog>

    <!-- Dialog Matière -->
    <p-dialog [header]="'📖 ' + (formMatiere.id ? ('common.modifier' | translate) : ('academique.nouvelle_matiere' | translate))" [(visible)]="dialogMatiereVisible"
              [modal]="true" [style]="{width:'400px'}">
      <div class="form-grid" style="grid-template-columns:1fr">
        <div class="form-group">
          <label>{{ 'academique.classe' | translate }} *</label>
          <p-select appendTo="body" [overlayOptions]="overlayNoHideOnScroll" [options]="classes()" [(ngModel)]="formMatiere.classe"
                    optionLabel="nom" optionValue="id" styleClass="w-full" scrollHeight="320px" />
        </div>
        <div class="form-group">
          <label>{{ 'academique.nom' | translate }} *</label>
          <input pInputText [(ngModel)]="formMatiere.nom" class="w-full" [placeholder]="'academique.ex_matiere' | translate" />
        </div>
        <div class="form-group">
          <label>{{ 'academique.coefficient' | translate }}</label>
          <p-inputNumber [(ngModel)]="formMatiere.coefficient" [min]="0.5" [max]="10" mode="decimal" styleClass="w-full" />
        </div>
        <div class="form-group">
          <label>{{ 'academique.note_max' | translate }}</label>
          <p-select appendTo="body" [overlayOptions]="overlayNoHideOnScroll" [options]="noteMaxOptions" [(ngModel)]="formMatiere.note_max"
                    optionLabel="label" optionValue="value" styleClass="w-full" scrollHeight="320px" />
        </div>
      </div>
      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler' | translate" severity="secondary" (onClick)="dialogMatiereVisible=false" />
        <p-button [label]="(formMatiere.id ? 'common.enregistrer' : 'common.creer') | translate" severity="success" (onClick)="creerMatiere()" />
      </ng-template>
    </p-dialog>

    <!-- Dialog Copie des matières -->
    <p-dialog header="📑 Copier les matières" [(visible)]="dialogCopieVisible"
              [modal]="true" [style]="{width:'520px'}">
      <p class="copie-aide">
        Les <b>{{ matieres().length }}</b> matières de
        <b>{{ nomClasseFiltre() }}</b> seront recopiées avec leurs coefficients.
        Une matière déjà présente dans la classe cible n'est jamais dupliquée.
      </p>
      <div class="form-group">
        <label>Classes destinataires</label>
        <p-multiSelect [options]="classesCibles()" [(ngModel)]="copieCibles"
                       optionLabel="nom" optionValue="id" styleClass="w-full"
                       placeholder="Choisir une ou plusieurs classes"
                       scrollHeight="280px" [filter]="true" />
      </div>
      <label class="copie-ecraser">
        <input type="checkbox" [(ngModel)]="copieEcraser" />
        <span>Aligner aussi les matières déjà présentes sur les coefficients de la source</span>
      </label>
      @if (copieRapport()) {
        <div class="copie-rapport">
          @for (r of copieRapport()!; track r.classe) {
            <div>· <b>{{ r.classe }}</b> — {{ r.creees }} ajoutée(s),
              {{ r.alignees }} alignée(s), {{ r.inchangees }} inchangée(s)</div>
          }
        </div>
      }
      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler' | translate" severity="secondary"
                  (onClick)="dialogCopieVisible=false" />
        <p-button label="Copier" severity="success" [loading]="copieEnCours()"
                  [disabled]="copieCibles.length === 0" (onClick)="copierMatieres()" />
      </ng-template>
    </p-dialog>

    <!-- Dialog Type Évaluation -->
    <p-dialog [header]="'📋 ' + (formTypeEval.id ? ('common.modifier' | translate) : ('academique.nouveau_type_eval' | translate))" [(visible)]="dialogTypeEvalVisible"
              [modal]="true" [style]="{width:'400px'}">
      <div class="form-grid" style="grid-template-columns:1fr">
        <div class="form-group">
          <label>{{ 'academique.nom' | translate }} *</label>
          <input pInputText [(ngModel)]="formTypeEval.nom" class="w-full" [placeholder]="'academique.ex_type_eval' | translate" />
        </div>
        <div class="form-group">
          <label>{{ 'academique.poids' | translate }}</label>
          <p-inputNumber [(ngModel)]="formTypeEval.poids" [min]="0.5" [max]="5" mode="decimal" styleClass="w-full" />
        </div>
      </div>
      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler' | translate" severity="secondary" (onClick)="dialogTypeEvalVisible=false" />
        <p-button [label]="(formTypeEval.id ? 'common.enregistrer' : 'common.creer') | translate" severity="success" (onClick)="creerTypeEval()" />
      </ng-template>
    </p-dialog>

    <!-- Dialog Évaluation -->
    <p-dialog [header]="'📝 ' + ('academique.nouvelle_eval' | translate)" [(visible)]="dialogEvalVisible"
              [modal]="true" [style]="{width:'420px'}">
      <div class="form-grid" style="grid-template-columns:1fr 1fr">
        <div class="form-group full">
          <label>{{ 'academique.type_eval' | translate }} *</label>
          <p-select appendTo="body" [overlayOptions]="overlayNoHideOnScroll" [options]="typesEval()" [(ngModel)]="formEval.type_eval"
                    optionLabel="nom" optionValue="id" styleClass="w-full" scrollHeight="320px" />
        </div>
        <div class="form-group">
          <label>{{ periodeLabel() }} *</label>
          <p-select appendTo="body" [overlayOptions]="overlayNoHideOnScroll" [options]="trimestres" [(ngModel)]="formEval.trimestre"
                    optionLabel="label" optionValue="value" styleClass="w-full" scrollHeight="320px" />
        </div>
        <div class="form-group">
          <label>{{ 'academique.date' | translate }} *</label>
          <input pInputText type="date" [(ngModel)]="formEval.date_eval" class="w-full" />
        </div>
        <div class="form-group">
          <label>{{ 'academique.note_max' | translate }}</label>
          <p-select appendTo="body" [overlayOptions]="overlayNoHideOnScroll" [options]="noteMaxOptions" [(ngModel)]="formEval.note_max"
                    optionLabel="label" optionValue="value" styleClass="w-full" scrollHeight="320px" />
        </div>
        <div class="form-group full">
          <label>{{ 'academique.titre_optionnel' | translate }}</label>
          <input pInputText [(ngModel)]="formEval.titre" class="w-full" [placeholder]="'academique.ex_titre_eval' | translate" />
        </div>
      </div>
      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler' | translate" severity="secondary" (onClick)="dialogEvalVisible=false" />
        <p-button [label]="'common.creer'   | translate" severity="success" (onClick)="creerEvaluation()" />
      </ng-template>
    </p-dialog>
  `,
  styles: [`
    .page-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:16px; }
    .page-title  { font-size:20px; font-weight:600; color:var(--text); margin:0 0 4px; }
    .page-sub    { font-size:12px; color:var(--text-3); }
    .tabs-bar { display:flex; gap:3px; margin-bottom:16px; background:var(--surface-2); border:1px solid var(--border); border-radius:10px; padding:4px; }
    .tab-btn { flex:1; padding:7px 8px; border:none; border-radius:7px; background:transparent; color:var(--text-3); font-size:12px; cursor:pointer; }
    .tab-btn.active { background:var(--surface); color:#00d4aa; font-weight:600; border:1px solid var(--border); }
    .param-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; }
    .param-card { background:var(--surface); border:1px solid var(--border); border-radius:12px; overflow:hidden; }
    .pc-header { display:flex; justify-content:space-between; align-items:center; padding:12px 16px; border-bottom:1px solid var(--border); font-weight:600; color:var(--text); font-size:13px; }
    .pc-filter { padding:8px 16px; border-bottom:1px solid var(--border); }
    .pc-body { padding:8px 0; max-height:300px; overflow-y:auto; }
    .pc-item { display:flex; justify-content:space-between; align-items:center; padding:8px 16px; border-bottom:1px solid rgba(42,63,95,0.3); font-size:13px; color:var(--text-2); }
    .pc-item:hover { background:var(--surface-hover); }
    .pc-right { display:flex; align-items:center; gap:2px; }
    .pc-actions { display:flex; align-items:center; gap:2px; }
    .periode-bar { display:flex; align-items:center; gap:12px; flex-wrap:wrap; background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:12px 16px; margin-bottom:16px; }
    .periode-label { font-weight:600; color:var(--text); font-size:13px; }
    .periode-hint { font-size:11px; color:var(--text-3); }
    ::ng-deep .periode-select { min-width:150px; }
    ::ng-deep .periode-nb { width:110px; }
    .badge { font-size:10px; padding:2px 8px; border-radius:20px; background:rgba(0,212,170,0.1); color:#00d4aa; border:1px solid rgba(0,212,170,0.2); }
    .filters-bar { display:flex; gap:8px; flex-wrap:wrap; }
    .filter-drop { min-width:160px; }
    .evals-list { display:flex; gap:8px; flex-wrap:wrap; }
    .eval-card { background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:10px 14px; cursor:pointer; transition:all 0.2s; }
    .eval-card:hover { border-color:#00d4aa; }
    .eval-card.active { border-color:#00d4aa; background:rgba(0,212,170,0.1); }
    .ec-titre { font-size:13px; font-weight:600; color:var(--text); }
    .ec-info  { font-size:11px; color:var(--text-3); margin-top:4px; }
    .table-card { background:var(--surface); border:1px solid var(--border); border-radius:12px; overflow:hidden; }
    ::ng-deep .p-datatable .p-datatable-thead > tr > th { background:var(--surface-2) !important; color:var(--text-3) !important; font-size:11px !important; text-transform:uppercase !important; border-color:var(--border) !important; }
    ::ng-deep .p-datatable .p-datatable-tbody > tr { background:var(--surface) !important; color:var(--text-2) !important; border-bottom:1px solid rgba(42,63,95,0.4) !important; }
    .mono  { font-family:monospace; font-size:12px; }
    .bold  { font-weight:600; color:var(--text); }
    .copie-aide { font-size:13px; color:var(--text-2); line-height:1.55; margin-bottom:14px; }
    .copie-ecraser { display:flex; gap:8px; align-items:flex-start; margin-top:12px; font-size:12.5px; color:var(--text-2); cursor:pointer; }
    .copie-ecraser input { margin-top:2px; }
    .copie-rapport { background:var(--surface-hover); border-radius:8px; padding:10px 12px; font-size:12.5px; line-height:1.7; margin-top:14px; }
    .empty-msg { text-align:center; padding:20px; color:var(--text-3); font-size:12px; }
    .form-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
    .form-group { display:flex; flex-direction:column; gap:6px; }
    .form-group label { font-size:12px; color:var(--text-2); text-transform:uppercase; }
    .form-group.full { grid-column:1/-1; }
    .w-full { width:100%; }
    .stats-classe { display:flex; gap:16px; padding:12px 16px; border-bottom:1px solid var(--border); }
    .sc-item { display:flex; flex-direction:column; gap:2px; font-size:12px; }
    .sc-item span { color:var(--text-3); }
    .sc-item strong { color:var(--text); font-family:monospace; }
  `]
})
export class AcademiqueComponent implements OnInit {
  onglet   = signal('parametrage');
  niveaux  = signal<any[]>([]);
  classes  = signal<any[]>([]);
  matieres = signal<any[]>([]);
  typesEval= signal<any[]>([]);
  evaluations   = signal<any[]>([]);
  elevesNotes   = signal<any[]>([]);
  matieresNotes = signal<any[]>([]);
  resultats     = signal<any[]>([]);
  statsClasse   = signal<any>(null);
  colonnesMatieres = signal<string[]>([]);
  loading          = signal(false);
  saving           = signal(false);
  calculant        = signal(false);
  loadingAnalyse   = signal(false);
  analyse          = signal<any>(null);
  loadingHistorique= signal(false);
  historiqueAll    = signal<any[]>([]);
  historiqueFiltres= signal<any[]>([]);
  histAnneeOptions = signal<any[]>([]);
  histClasseOptions= signal<any[]>([]);

  classeFiltre    = '';

  // ── Copie des matières d'une classe vers d'autres ─────────────────────
  dialogCopieVisible = false;
  copieCibles: string[] = [];
  copieEcraser = false;
  copieEnCours = signal(false);
  copieRapport = signal<{ classe: string; creees: number;
                          alignees: number; inchangees: number }[] | null>(null);

  /** Les classes proposées comme destinataires — toutes sauf la source. */
  classesCibles = computed(() =>
    this.classes().filter((c: any) => c.id !== this.classeFiltre));

  nomClasseFiltre = computed(() =>
    this.classes().find((c: any) => c.id === this.classeFiltre)?.nom || '');
  classeNotes     = '';
  matiereNotes    = '';
  trimestreNotes  = 'T1';
  classeResultats = '';
  trimestreResultats = 'T1';
  evalSelectionnee: any = null;
  private _elevesClasseCache: { classeId: string; eleves: any[] } | null = null;

  histSearch    = '';
  histClasse    = '';
  histTrimestre = '';
  histAnnee     = '';

  dialogClasseVisible   = false;
  dialogMatiereVisible  = false;
  dialogTypeEvalVisible = false;
  dialogEvalVisible     = false;

  // Empêche les dropdowns de se fermer au scroll dans un dialog (comme licences)
  overlayNoHideOnScroll = {
    listener: (_event: any, options: any) => options.type === 'scroll' ? false : options.valid,
  };

  formClasse:   any = { id: null, nom: '', code: '', niveau: '' };
  formMatiere:  any = { id: null, nom: '', classe: '', coefficient: 1, note_max: 20 };
  formTypeEval: any = { id: null, nom: '', poids: 1 };
  formEval     = { type_eval: '', trimestre: 'T1', date_eval: '', note_max: 20, titre: '' };

  trimestres: any[] = [];
  noteMaxOptions: any[] = [];
  periode = 'TRIMESTRE';   // type/mot : TRIMESTRE | SEMESTRE | PERIODE
  nbPeriodes = 3;          // nombre de périodes (libre)
  periodesOptions = [
    { label: 'Trimestre', value: 'TRIMESTRE' },
    { label: 'Semestre',  value: 'SEMESTRE' },
    { label: 'Période',   value: 'PERIODE' },
  ];

  // Mot singulier + préfixe de code selon le type
  periodeLabel(): string {
    return this.periode === 'SEMESTRE' ? 'Semestre' : this.periode === 'PERIODE' ? 'Période' : 'Trimestre';
  }
  private periodePrefixe(): string {
    return this.periode === 'SEMESTRE' ? 'S' : this.periode === 'PERIODE' ? 'P' : 'T';
  }

  // Construit les options de période (mot + nombre choisis par l'école)
  construireTrimestres() {
    const n = Math.max(1, Math.min(12, +this.nbPeriodes || 1));
    const mot = this.periodeLabel();
    const pre = this.periodePrefixe();
    this.trimestres = Array.from({ length: n }, (_, i) => ({ label: `${mot} ${i + 1}`, value: `${pre}${i + 1}` }));
    const vals = this.trimestres.map(t => t.value);
    if (!vals.includes(this.trimestreNotes))     this.trimestreNotes = vals[0];
    if (!vals.includes(this.trimestreResultats)) this.trimestreResultats = vals[0];
  }

  sauvegarderPeriode() {
    this.nbPeriodes = Math.max(1, Math.min(12, +this.nbPeriodes || 1));
    this.construireTrimestres();
    this.api.patch<any>('/tenants/mon_ecole/', { periode_scolaire: this.periode, nb_periodes: this.nbPeriodes }).subscribe({
      next: () => this.msg.add({ severity: 'success', summary: this.translate.instant('common.succes') }),
      error: () => this.msg.add({ severity: 'error', summary: this.translate.instant('common.erreur') }),
    });
  }

  private translate = inject(TranslateService);

  private auth = inject(AuthService);
  get estDaara(): boolean {
    return this.auth.currentUser()?.type_licence === 'TAXAWU_DAARA';
  }

  constructor(
    private acad: AcademiqueService,
    private elevesService: ElevesService,
    private api: ApiService,
    private msg: MessageService
  ) {}

  ngOnInit() {
    this.construireTrimestres();
    // Réglage période (trimestre/semestre) de l'école
    this.api.get<any>('/tenants/mon_ecole/').subscribe({
      next: e => {
        this.periode = e?.periode_scolaire || 'TRIMESTRE';
        this.nbPeriodes = e?.nb_periodes || 3;
        this.construireTrimestres();
      },
    });
    this.noteMaxOptions = [
      { label: this.translate.instant('academique.sur_10'), value: 10 },
      { label: this.translate.instant('academique.sur_20'), value: 20 },
    ];
    this.acad.getNiveaux().subscribe({ next: r => this.niveaux.set(r.results || []) });
    this.acad.getClasses().subscribe({ next: r => this.classes.set(r.results || []) });
    this.acad.getTypesEval().subscribe({ next: r => this.typesEval.set(r.results || []) });
  }

  ouvrirCopieMatieres() {
    this.copieCibles = [];
    this.copieEcraser = false;
    this.copieRapport.set(null);
    this.dialogCopieVisible = true;
  }

  copierMatieres() {
    if (!this.classeFiltre || !this.copieCibles.length) return;
    this.copieEnCours.set(true);
    this.acad.copierMatieres(this.classeFiltre, this.copieCibles, this.copieEcraser)
      .subscribe({
        next: (r) => {
          this.copieRapport.set(r.rapport);
          this.copieEnCours.set(false);
          const ajoutees = r.rapport.reduce((t, x) => t + x.creees, 0);
          this.msg.add({ severity: 'success', summary: 'Matières copiées',
                         detail: `${ajoutees} matière(s) ajoutée(s) dans `
                                 + `${r.rapport.length} classe(s).` });
        },
        error: (e) => {
          this.copieEnCours.set(false);
          this.msg.add({ severity: 'error', summary: 'Échec',
                         detail: e?.error?.error || e?.error?.cibles
                                 || 'La copie a échoué.' });
        },
      });
  }

  chargerMatieres() {
    if (!this.classeFiltre) return;
    this.acad.getMatieres({ classe: this.classeFiltre }).subscribe({
      next: r => this.matieres.set(r.results || [])
    });
  }

  chargerAnalyse() {
    if (this.analyse()) return;
    this.loadingAnalyse.set(true);
    this.acad.getAnalysePerformance().subscribe({
      next: r => { this.analyse.set(r); this.loadingAnalyse.set(false); },
      error: ()  => this.loadingAnalyse.set(false),
    });
  }

  onClasseNotesChange() {
    this._elevesClasseCache = null;
    this.acad.getMatieres({ classe: this.classeNotes }).subscribe({
      next: r => this.matieresNotes.set(r.results || [])
    });
    this.evalSelectionnee = null;
    this.evaluations.set([]);
    this.elevesNotes.set([]);
    this.matiereNotes = '';
  }

  onMatiereNotesChange() {
    this.chargerEvaluationsEtEleves();
  }

  onTrimestreNotesChange() {
    if (this.matiereNotes) this.chargerEvaluationsEtEleves();
  }

  chargerEvaluationsEtEleves() {
    if (!this.matiereNotes) return;
    const params: Record<string, string> = { matiere: this.matiereNotes };
    if (this.trimestreNotes) params['trimestre'] = this.trimestreNotes;
    this.acad.getEvaluations(params).subscribe({
      next: r => {
        const evals = r.results || [];
        this.evaluations.set(evals);
        // Auto-sélectionner la première évaluation si une seule existe
        if (evals.length === 1) {
          this.selectionnerEvaluation(evals[0]);
        } else {
          this.evalSelectionnee = null;
          this.elevesNotes.set([]);
        }
      }
    });
  }

  selectionnerEvaluation(eval_: any) {
    this.evalSelectionnee = eval_;
    const chargerNotes = (eleves: any[]) => {
      const mapped = eleves.map((e: any) => ({
        ...e,
        note_saisie: 0,
        absent_saisie: false,
        note_id: null,
      }));
      this.acad.getNotes({ evaluation: eval_.id }).subscribe({
        next: rn => {
          const notes = rn.results || [];
          mapped.forEach((e: any) => {
            const n = notes.find((n: any) => n.eleve === e.id);
            if (n) { e.note_saisie = parseFloat(n.valeur); e.absent_saisie = n.absent; e.note_id = n.id; }
          });
          this.elevesNotes.set(mapped);
        },
        error: () => this.elevesNotes.set(mapped),
      });
    };

    // Utiliser le cache élèves si la classe n'a pas changé
    if (this._elevesClasseCache?.classeId === this.classeNotes) {
      chargerNotes(this._elevesClasseCache.eleves);
    } else {
      this.acad.getElevesPourClasse(this.classeNotes).subscribe({
        next: (eleves: any[]) => {
          this._elevesClasseCache = { classeId: this.classeNotes, eleves };
          chargerNotes(eleves);
        },
        error: () => this.elevesNotes.set([]),
      });
    }
  }

  sauvegarderNotes() {
    if (!this.evalSelectionnee) return;
    const eleves = this.elevesNotes().filter(e => e.id);
    if (!eleves.length) {
      this.msg.add({ severity: 'warn', summary: 'Aucun élève', detail: 'Aucune note à enregistrer.' });
      return;
    }
    const notes = eleves.map(e => ({
      eleve:      e.id,
      evaluation: this.evalSelectionnee.id,
      valeur:     e.note_saisie  ?? 0,
      absent:     e.absent_saisie ?? false,
    }));
    this.saving.set(true);
    this.acad.bulkSaveNotes(notes).subscribe({
      next: (res: any) => {
        this.saving.set(false);
        const total = (res.created || 0) + (res.updated || 0);
        if (!res.errors) {
          this.msg.add({ severity: 'success', summary: 'Notes enregistrées',
                         detail: `${total} note(s) sauvegardée(s).` });
        } else {
          this.msg.add({ severity: 'warn', summary: `${total} OK / ${res.errors} erreur(s)`,
                         detail: 'Certaines notes n\'ont pas pu être enregistrées.' });
        }
        this.selectionnerEvaluation(this.evalSelectionnee);
      },
      error: () => {
        this.saving.set(false);
        this.msg.add({ severity: 'error', summary: 'Erreur', detail: 'Impossible d\'enregistrer les notes.' });
      },
    });
  }

  private _getAnneeScolaire(): string {
    const now = new Date();
    const y = now.getMonth() >= 8 ? now.getFullYear() : now.getFullYear() - 1;
    return `${y}-${y + 1}`;
  }

  calculerMoyennes() {
    if (!this.classeResultats) {
      this.msg.add({ severity: 'warn', summary: 'Classe requise', detail: 'Sélectionnez une classe.' });
      return;
    }
    if (!this.trimestreResultats) {
      this.msg.add({ severity: 'warn', summary: 'Trimestre requis', detail: 'Sélectionnez un trimestre.' });
      return;
    }
    this.calculant.set(true);
    this.acad.calculerMoyennes({
      classe_id:     this.classeResultats,
      trimestre:     this.trimestreResultats,
      annee_scolaire: this._getAnneeScolaire(),
    }).subscribe({
      next: res => {
        const resultats = res.resultats || [];
        this.resultats.set(resultats);
        this.statsClasse.set(res.stats);
        if (resultats.length > 0) {
          this.colonnesMatieres.set(resultats[0].matieres.map((m: any) => m.matiere));
        }
        this.calculant.set(false);
        if (resultats.length === 0) {
          this.msg.add({ severity: 'warn', summary: 'Aucun résultat',
                         detail: 'Aucun élève trouvé pour cette classe. Vérifiez que le nom de la section correspond exactement au nom de la classe.' });
        } else {
          this.msg.add({ severity: 'success', summary: 'Calcul terminé',
                         detail: `${resultats.length} élève(s) — Moy. classe : ${res.stats?.moy_classe}` });
        }
      },
      error: (err) => {
        this.msg.add({ severity: 'error', summary: 'Erreur calcul',
                       detail: err?.error?.error || 'Impossible de calculer les moyennes.' });
        this.calculant.set(false);
      }
    });
  }

  getAppreciation(moy: number, noteMax: number): string {
    const ratio = moy / noteMax * 20;
    if (ratio >= 18) return 'Excellent';
    if (ratio >= 16) return 'Très Bien';
    if (ratio >= 14) return 'Bien';
    if (ratio >= 12) return 'Assez Bien';
    if (ratio >= 10) return 'Passable';
    if (ratio >= 8)  return 'Insuffisant';
    return 'Très Insuffisant';
  }

  ouvrirDialogClasse()   {
    this.formClasse = { id:null, nom:'', code:'', niveau:'' };
    this.dialogClasseVisible = true;
  }
  ouvrirEditionClasse(c: any) {
    this.formClasse = { id:c.id, nom:c.nom, code:c.code || '', niveau:c.niveau };
    this.dialogClasseVisible = true;
  }
  ouvrirDialogMatiere()  {
    // Pré-remplir avec la classe filtrée si active
    this.formMatiere = { id:null, nom:'', classe: this.classeFiltre || '', coefficient:1, note_max:20 };
    this.dialogMatiereVisible = true;
  }
  ouvrirEditionMatiere(m: any) {
    this.formMatiere = { id:m.id, nom:m.nom, classe:m.classe, coefficient:+m.coefficient, note_max:+m.note_max };
    this.dialogMatiereVisible = true;
  }
  ouvrirDialogTypeEval() { this.formTypeEval = { id:null, nom:'', poids:1 }; this.dialogTypeEvalVisible = true; }
  ouvrirEditionTypeEval(t: any) {
    this.formTypeEval = { id:t.id, nom:t.nom, poids:+t.poids };
    this.dialogTypeEvalVisible = true;
  }
  ouvrirDialogEvaluation() {
    if (!this.matiereNotes) { this.msg.add({ severity:'warn', summary: this.translate.instant('academique.select_matiere') }); return; }
    this.formEval = { type_eval:'', trimestre: this.trimestreNotes, date_eval:'', note_max:20, titre:'' };
    this.dialogEvalVisible = true;
  }

  creerClasse() {
    if (!this.formClasse.nom?.trim() || !this.formClasse.niveau) {
      this.msg.add({ severity:'warn', summary:'Champs requis', detail:'Nom et niveau sont obligatoires.' });
      return;
    }
    const obs = this.formClasse.id
      ? this.acad.modifierClasse(this.formClasse.id, this.formClasse)
      : this.acad.creerClasse(this.formClasse);
    obs.subscribe({
      next: () => {
        this.dialogClasseVisible = false;
        this.acad.getClasses().subscribe({ next: r => this.classes.set(r.results || []) });
        this.msg.add({ severity:'success', summary: this.translate.instant('academique.classe_creee') });
      },
      error: (err) => this.msg.add({ severity:'error', summary:'Erreur',
                                      detail: err?.error?.detail || 'Impossible d\'enregistrer la classe.' }),
    });
  }

  supprimerClasse(c: any) {
    if (!confirm(`Supprimer la classe « ${c.nom} » ?\nLes élèves de cette classe ne seront pas supprimés.`)) return;
    this.acad.supprimerClasse(c.id).subscribe({
      next: () => {
        this.acad.getClasses().subscribe({ next: r => this.classes.set(r.results || []) });
        this.msg.add({ severity:'success', summary: this.translate.instant('common.succes') });
      },
      error: (err) => this.msg.add({ severity:'error', summary:'Erreur',
                                      detail: err?.error?.detail || 'Impossible de supprimer la classe.' }),
    });
  }

  creerMatiere() {
    if (!this.formMatiere.nom?.trim() || !this.formMatiere.classe) {
      this.msg.add({ severity:'warn', summary:'Champs requis', detail:'Nom et classe sont obligatoires.' });
      return;
    }
    const obs = this.formMatiere.id
      ? this.acad.modifierMatiere(this.formMatiere.id, this.formMatiere)
      : this.acad.creerMatiere(this.formMatiere);
    obs.subscribe({
      next: () => {
        this.dialogMatiereVisible = false;
        this.chargerMatieres();
        this.msg.add({ severity:'success', summary: this.translate.instant('academique.matiere_creee') });
      },
      error: (err) => this.msg.add({ severity:'error', summary:'Erreur',
                                      detail: err?.error?.detail || 'Impossible d\'enregistrer la matière.' }),
    });
  }

  supprimerMatiere(m: any) {
    if (!confirm(`Supprimer la matière « ${m.nom} » ?\nLes notes liées seront aussi supprimées.`)) return;
    this.acad.supprimerMatiere(m.id).subscribe({
      next: () => {
        this.chargerMatieres();
        this.msg.add({ severity:'success', summary: this.translate.instant('common.succes') });
      },
      error: (err) => this.msg.add({ severity:'error', summary:'Erreur',
                                      detail: err?.error?.detail || 'Impossible de supprimer la matière.' }),
    });
  }

  creerTypeEval() {
    if (!this.formTypeEval.nom?.trim()) {
      this.msg.add({ severity:'warn', summary:'Champ requis', detail:'Le nom est obligatoire.' });
      return;
    }
    const obs = this.formTypeEval.id
      ? this.acad.modifierTypeEval(this.formTypeEval.id, this.formTypeEval)
      : this.acad.creerTypeEval(this.formTypeEval);
    obs.subscribe({
      next: () => {
        this.dialogTypeEvalVisible = false;
        this.acad.getTypesEval().subscribe({ next: r => this.typesEval.set(r.results || []) });
        this.msg.add({ severity:'success', summary: this.translate.instant('academique.type_eval_cree') });
      },
      error: (err) => this.msg.add({ severity:'error', summary:'Erreur',
                                      detail: err?.error?.detail || 'Impossible d\'enregistrer le type.' }),
    });
  }

  supprimerTypeEval(t: any) {
    if (!confirm(`Supprimer le type d'évaluation « ${t.nom} » ?`)) return;
    this.acad.supprimerTypeEval(t.id).subscribe({
      next: () => {
        this.acad.getTypesEval().subscribe({ next: r => this.typesEval.set(r.results || []) });
        this.msg.add({ severity:'success', summary: this.translate.instant('common.succes') });
      },
      error: (err) => this.msg.add({ severity:'error', summary:'Erreur',
                                      detail: err?.error?.detail || 'Impossible de supprimer le type.' }),
    });
  }

  creerEvaluation() {
    if (!this.formEval.type_eval) {
      this.msg.add({ severity:'warn', summary:'Champ requis', detail:'Sélectionnez un type d\'évaluation.' });
      return;
    }
    if (!this.formEval.date_eval) {
      this.msg.add({ severity:'warn', summary:'Champ requis', detail:'La date est obligatoire.' });
      return;
    }
    if (!this.matiereNotes) {
      this.msg.add({ severity:'warn', summary:'Matière requise', detail:'Sélectionnez une matière.' });
      return;
    }
    const data = { ...this.formEval, matiere: this.matiereNotes };
    this.acad.creerEvaluation(data).subscribe({
      next: () => {
        this.dialogEvalVisible = false;
        this.chargerEvaluationsEtEleves();
        this.msg.add({ severity:'success', summary: this.translate.instant('academique.evaluation_creee') });
      },
      error: (err) => this.msg.add({ severity:'error', summary:'Erreur',
                                      detail: err?.error?.detail || 'Impossible de créer l\'évaluation.' }),
    });
  }

    telechargerBulletin(eleveId: string) {
    if (!this.trimestreResultats) {
      this.msg.add({ severity: 'warn', summary: 'Trimestre requis',
                     detail: 'Sélectionnez un trimestre avant de télécharger.' });
      return;
    }
    const annee     = this._getAnneeScolaire();
    const trimestre = this.trimestreResultats;
    this.acad.getBulletinPdf(eleveId, trimestre, annee).subscribe({
      next: (blob: Blob) => {
        const url  = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href     = url;
        link.download = `bulletin_${trimestre}_${annee}.pdf`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      },
      error: () => this.msg.add({ severity: 'error', summary: 'Erreur PDF',
                                   detail: 'Impossible de générer le bulletin. Calculez d\'abord les moyennes.' }),
    });
  }

  chargerHistorique(forceRefresh = false) {
    if (!forceRefresh && this.historiqueAll().length > 0) return;
    this.loadingHistorique.set(true);
    this.acad.getHistoriqueBulletins().subscribe({
      next: (res: any) => {
        const bulletins = res.bulletins || [];
        this.historiqueAll.set(bulletins);
        this.historiqueFiltres.set(bulletins);

        // Options années
        const annees = (res.annees || []).map((a: string) => ({ label: a, value: a }));
        this.histAnneeOptions.set([{ label: 'Toutes les années', value: '' }, ...annees]);

        // Options classes (déduites des bulletins)
        const classesSet = new Set<string>(bulletins.map((b: any) => b.classe).filter((c: string) => c !== '—'));
        const classesOpts = Array.from(classesSet).sort().map((c: string) => ({ label: c, value: c }));
        this.histClasseOptions.set([{ label: 'Toutes les classes', value: '' }, ...classesOpts]);

        this.loadingHistorique.set(false);
      },
      error: () => this.loadingHistorique.set(false),
    });
  }

  appliquerFiltreHistorique() {
    let liste = this.historiqueAll();
    const search = this.histSearch.toLowerCase().trim();
    if (search)                liste = liste.filter(b => b.eleve_nom.toLowerCase().includes(search));
    if (this.histClasse)       liste = liste.filter(b => b.classe === this.histClasse);
    if (this.histTrimestre)    liste = liste.filter(b => b.trimestre === this.histTrimestre);
    if (this.histAnnee)        liste = liste.filter(b => b.annee_scolaire === this.histAnnee);
    this.historiqueFiltres.set(liste);
  }

  telechargerBulletinHistorique(b: any) {
    this.acad.getBulletinPdf(b.eleve_id, b.trimestre, b.annee_scolaire).subscribe({
      next: (blob: Blob) => {
        const url  = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href     = url;
        link.download = `bulletin_${b.eleve_nom.replace(/ /g, '_')}_${b.trimestre}_${b.annee_scolaire}.pdf`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      },
      error: () => this.msg.add({ severity: 'error', summary: 'Erreur PDF',
                                   detail: 'Impossible de générer le bulletin.' }),
    });
  }
}
