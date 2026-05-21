import { Component, OnInit, inject, signal } from '@angular/core';
import { environment } from '../../../environments/environment';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AcademiqueService } from '../../core/services/academique.service';
import { ElevesService } from '../../core/services/eleves.service';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { TagModule } from 'primeng/tag';
import { InputNumberModule } from 'primeng/inputnumber';
import { MessageService } from 'primeng/api';
import { ToastModule } from 'primeng/toast';
import { TranslateModule, TranslateService } from '@ngx-translate/core';

@Component({
  selector: 'app-academique',
  standalone: true,
  imports: [CommonModule, FormsModule, TableModule, ButtonModule, DialogModule,
            InputTextModule, SelectModule, TagModule, InputNumberModule, ToastModule, TranslateModule],
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
    </div>

    <!-- PARAMÉTRAGE -->
    <div *ngIf="onglet()==='parametrage'">
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
              <span class="badge">{{ c.niveau_nom }}</span>
            </div>
            <div class="empty-msg" *ngIf="classes().length===0">{{ 'academique.aucune_classe' | translate }}</div>
          </div>
        </div>

        <!-- Matières -->
        <div class="param-card">
          <div class="pc-header">
            <span>📖 {{ 'academique.matieres' | translate }}</span>
            <p-button icon="pi pi-plus" [rounded]="true" [text]="true"
                      severity="success" (onClick)="ouvrirDialogMatiere()" />
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
              <span class="badge">{{ 'academique.coef' | translate }} {{ m.coefficient }}</span>
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
              <span class="badge">{{ 'academique.poids' | translate }} {{ t.poids }}</span>
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
                  [placeholder]="'academique.trimestre_filter' | translate" styleClass="filter-drop"
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
          <span style="font-size:11px;color:#64748b;text-transform:uppercase;font-weight:600">
            Évaluations — {{ trimestreNotes || 'Tous trimestres' }}
          </span>
          <span style="font-size:11px;color:#2a3f5f">{{ evaluations().length }} évaluation(s)</span>
        </div>
        <div class="evals-list" *ngIf="evaluations().length > 0">
          <div class="eval-card" *ngFor="let e of evaluations()"
               [class.active]="evalSelectionnee?.id === e.id"
               (click)="selectionnerEvaluation(e)">
            <div class="ec-titre">{{ e.type_eval_nom || e.titre || 'Évaluation' }}</div>
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
        <div style="padding:12px 16px;border-bottom:1px solid #2a3f5f;display:flex;justify-content:space-between;align-items:center">
          <div>
            <span style="color:#e8f0fe;font-weight:600">
              {{ evalSelectionnee.matiere_nom }} · {{ evalSelectionnee.type_eval_nom }}
            </span>
            <span style="color:#64748b;font-size:11px;margin-left:8px">
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
                               styleClass="note-input" />
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
                  [placeholder]="'academique.trimestre_filter' | translate" styleClass="filter-drop" />
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
              <td class="mono" *ngFor="let m of r.matieres">
                {{ m.moyenne !== null ? m.moyenne : '—' }}
              </td>
              <td class="mono bold" style="color:#00d4aa">{{ r.moy_generale }}</td>
              <td>{{ getAppreciation(r.moy_generale, 20) }}</td>
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

    <!-- Dialog Classe -->
    <p-dialog [header]="'🏫 ' + ('academique.nouvelle_classe' | translate)" [(visible)]="dialogClasseVisible"
              [modal]="true" [style]="{width:'400px'}">
      <div class="form-grid" style="grid-template-columns:1fr">
        <div class="form-group">
          <label>{{ 'academique.niveau' | translate }} *</label>
          <p-select [options]="niveaux()" [(ngModel)]="formClasse.niveau"
                    optionLabel="nom" optionValue="id" styleClass="w-full" />
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
        <p-button [label]="'common.creer'   | translate" severity="success" (onClick)="creerClasse()" />
      </ng-template>
    </p-dialog>

    <!-- Dialog Matière -->
    <p-dialog [header]="'📖 ' + ('academique.nouvelle_matiere' | translate)" [(visible)]="dialogMatiereVisible"
              [modal]="true" [style]="{width:'400px'}">
      <div class="form-grid" style="grid-template-columns:1fr">
        <div class="form-group">
          <label>{{ 'academique.classe' | translate }} *</label>
          <p-select [options]="classes()" [(ngModel)]="formMatiere.classe"
                    optionLabel="nom" optionValue="id" styleClass="w-full" />
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
          <p-select [options]="noteMaxOptions" [(ngModel)]="formMatiere.note_max"
                    optionLabel="label" optionValue="value" styleClass="w-full" />
        </div>
      </div>
      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler' | translate" severity="secondary" (onClick)="dialogMatiereVisible=false" />
        <p-button [label]="'common.creer'   | translate" severity="success" (onClick)="creerMatiere()" />
      </ng-template>
    </p-dialog>

    <!-- Dialog Type Évaluation -->
    <p-dialog [header]="'📋 ' + ('academique.nouveau_type_eval' | translate)" [(visible)]="dialogTypeEvalVisible"
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
        <p-button [label]="'common.creer'   | translate" severity="success" (onClick)="creerTypeEval()" />
      </ng-template>
    </p-dialog>

    <!-- Dialog Évaluation -->
    <p-dialog [header]="'📝 ' + ('academique.nouvelle_eval' | translate)" [(visible)]="dialogEvalVisible"
              [modal]="true" [style]="{width:'420px'}">
      <div class="form-grid" style="grid-template-columns:1fr 1fr">
        <div class="form-group full">
          <label>{{ 'academique.type_eval' | translate }} *</label>
          <p-select [options]="typesEval()" [(ngModel)]="formEval.type_eval"
                    optionLabel="nom" optionValue="id" styleClass="w-full" />
        </div>
        <div class="form-group">
          <label>{{ 'academique.trimestre' | translate }} *</label>
          <p-select [options]="trimestres" [(ngModel)]="formEval.trimestre"
                    optionLabel="label" optionValue="value" styleClass="w-full" />
        </div>
        <div class="form-group">
          <label>{{ 'academique.date' | translate }} *</label>
          <input pInputText type="date" [(ngModel)]="formEval.date_eval" class="w-full" />
        </div>
        <div class="form-group">
          <label>{{ 'academique.note_max' | translate }}</label>
          <p-select [options]="noteMaxOptions" [(ngModel)]="formEval.note_max"
                    optionLabel="label" optionValue="value" styleClass="w-full" />
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
    .page-title  { font-size:20px; font-weight:600; color:#e8f0fe; margin:0 0 4px; }
    .page-sub    { font-size:12px; color:#64748b; }
    .tabs-bar { display:flex; gap:3px; margin-bottom:16px; background:#111827; border:1px solid #2a3f5f; border-radius:10px; padding:4px; }
    .tab-btn { flex:1; padding:7px 8px; border:none; border-radius:7px; background:transparent; color:#64748b; font-size:12px; cursor:pointer; }
    .tab-btn.active { background:#1e2d45; color:#00d4aa; font-weight:600; border:1px solid #2a3f5f; }
    .param-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:16px; }
    .param-card { background:#1e2d45; border:1px solid #2a3f5f; border-radius:12px; overflow:hidden; }
    .pc-header { display:flex; justify-content:space-between; align-items:center; padding:12px 16px; border-bottom:1px solid #2a3f5f; font-weight:600; color:#e8f0fe; font-size:13px; }
    .pc-filter { padding:8px 16px; border-bottom:1px solid #2a3f5f; }
    .pc-body { padding:8px 0; max-height:300px; overflow-y:auto; }
    .pc-item { display:flex; justify-content:space-between; align-items:center; padding:8px 16px; border-bottom:1px solid rgba(42,63,95,0.3); font-size:13px; color:#94a3b8; }
    .pc-item:hover { background:#1a2235; }
    .badge { font-size:10px; padding:2px 8px; border-radius:20px; background:rgba(0,212,170,0.1); color:#00d4aa; border:1px solid rgba(0,212,170,0.2); }
    .filters-bar { display:flex; gap:8px; flex-wrap:wrap; }
    .filter-drop { min-width:160px; }
    .evals-list { display:flex; gap:8px; flex-wrap:wrap; }
    .eval-card { background:#1e2d45; border:1px solid #2a3f5f; border-radius:8px; padding:10px 14px; cursor:pointer; transition:all 0.2s; }
    .eval-card:hover { border-color:#00d4aa; }
    .eval-card.active { border-color:#00d4aa; background:rgba(0,212,170,0.1); }
    .ec-titre { font-size:13px; font-weight:600; color:#e8f0fe; }
    .ec-info  { font-size:11px; color:#64748b; margin-top:4px; }
    .table-card { background:#1e2d45; border:1px solid #2a3f5f; border-radius:12px; overflow:hidden; }
    ::ng-deep .p-datatable .p-datatable-thead > tr > th { background:#111827 !important; color:#64748b !important; font-size:11px !important; text-transform:uppercase !important; border-color:#2a3f5f !important; }
    ::ng-deep .p-datatable .p-datatable-tbody > tr { background:#1e2d45 !important; color:#94a3b8 !important; border-bottom:1px solid rgba(42,63,95,0.4) !important; }
    ::ng-deep .note-input { width:100px !important; }
    .mono  { font-family:monospace; font-size:12px; }
    .bold  { font-weight:600; color:#e8f0fe; }
    .empty-msg { text-align:center; padding:20px; color:#64748b; font-size:12px; }
    .form-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
    .form-group { display:flex; flex-direction:column; gap:6px; }
    .form-group label { font-size:12px; color:#94a3b8; text-transform:uppercase; }
    .form-group.full { grid-column:1/-1; }
    .w-full { width:100%; }
    .stats-classe { display:flex; gap:16px; padding:12px 16px; border-bottom:1px solid #2a3f5f; }
    .sc-item { display:flex; flex-direction:column; gap:2px; font-size:12px; }
    .sc-item span { color:#64748b; }
    .sc-item strong { color:#e8f0fe; font-family:monospace; }
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
  loading  = signal(false);
  saving   = signal(false);
  calculant= signal(false);

  classeFiltre    = '';
  classeNotes     = '';
  matiereNotes    = '';
  trimestreNotes  = 'T1';
  classeResultats = '';
  trimestreResultats = 'T1';
  evalSelectionnee: any = null;

  dialogClasseVisible   = false;
  dialogMatiereVisible  = false;
  dialogTypeEvalVisible = false;
  dialogEvalVisible     = false;

  formClasse   = { nom: '', code: '', niveau: '' };
  formMatiere  = { nom: '', classe: '', coefficient: 1, note_max: 20 };
  formTypeEval = { nom: '', poids: 1 };
  formEval     = { type_eval: '', trimestre: 'T1', date_eval: '', note_max: 20, titre: '' };

  trimestres: any[] = [];
  noteMaxOptions: any[] = [];

  private translate = inject(TranslateService);

  constructor(
    private acad: AcademiqueService,
    private elevesService: ElevesService,
    private msg: MessageService
  ) {}

  ngOnInit() {
    this.trimestres = [
      { label: this.translate.instant('academique.trimestre_1'), value: 'T1' },
      { label: this.translate.instant('academique.trimestre_2'), value: 'T2' },
      { label: this.translate.instant('academique.trimestre_3'), value: 'T3' },
    ];
    this.noteMaxOptions = [
      { label: this.translate.instant('academique.sur_10'), value: 10 },
      { label: this.translate.instant('academique.sur_20'), value: 20 },
    ];
    this.acad.getNiveaux().subscribe({ next: r => this.niveaux.set(r.results || []) });
    this.acad.getClasses().subscribe({ next: r => this.classes.set(r.results || []) });
    this.acad.getTypesEval().subscribe({ next: r => this.typesEval.set(r.results || []) });
  }

  chargerMatieres() {
    if (!this.classeFiltre) return;
    this.acad.getMatieres({ classe: this.classeFiltre }).subscribe({
      next: r => this.matieres.set(r.results || [])
    });
  }

  onClasseNotesChange() {
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
    this.acad.getElevesPourClasse(this.classeNotes).subscribe({
      next: (eleves: any[]) => {
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
      },
      error: () => this.elevesNotes.set([]),
    });
  }

  sauvegarderNotes() {
    if (!this.evalSelectionnee) return;
    this.saving.set(true);
    const promises = this.elevesNotes().map(e => {
      const data = {
        eleve: e.id,
        evaluation: this.evalSelectionnee.id,
        valeur: e.note_saisie || 0,
        absent: e.absent_saisie || false,
      };
      if (e.note_id) {
        return this.acad.modifierNote(e.note_id, data).toPromise();
      } else {
        return this.acad.creerNote(data).toPromise();
      }
    });
    Promise.all(promises).then(() => {
      this.msg.add({ severity: 'success', summary: this.translate.instant('academique.notes_enregistrees'), detail: `${promises.length}` });
      this.saving.set(false);
      this.selectionnerEvaluation(this.evalSelectionnee);
    }).catch(() => this.saving.set(false));
  }

  calculerMoyennes() {
    if (!this.classeResultats) return;
    this.calculant.set(true);
    this.acad.calculerMoyennes({
      classe_id: this.classeResultats,
      trimestre: this.trimestreResultats,
    }).subscribe({
      next: res => {
        this.resultats.set(res.resultats || []);
        this.statsClasse.set(res.stats);
        if (res.resultats?.length > 0) {
          this.colonnesMatieres.set(res.resultats[0].matieres.map((m: any) => m.matiere));
        }
        this.calculant.set(false);
        this.msg.add({ severity: 'success', summary: this.translate.instant('academique.calcul_termine'), detail: `${res.resultats?.length}` });
      },
      error: () => this.calculant.set(false)
    });
  }

  getAppreciation(moy: number, noteMax: number): string {
    const ratio = moy / noteMax * 20;
    if (ratio >= 18) return this.translate.instant('academique.appr_excellent');
    if (ratio >= 16) return this.translate.instant('academique.appr_tres_bien');
    if (ratio >= 14) return this.translate.instant('academique.appr_bien');
    if (ratio >= 12) return this.translate.instant('academique.appr_assez_bien');
    if (ratio >= 10) return this.translate.instant('academique.appr_passable');
    return this.translate.instant('academique.appr_insuffisant');
  }

  ouvrirDialogClasse()   { this.formClasse   = { nom:'', code:'', niveau:'' }; this.dialogClasseVisible   = true; }
  ouvrirDialogMatiere()  { this.formMatiere  = { nom:'', classe:'', coefficient:1, note_max:20 }; this.dialogMatiereVisible  = true; }
  ouvrirDialogTypeEval() { this.formTypeEval = { nom:'', poids:1 }; this.dialogTypeEvalVisible = true; }
  ouvrirDialogEvaluation() {
    if (!this.matiereNotes) { this.msg.add({ severity:'warn', summary: this.translate.instant('academique.select_matiere') }); return; }
    this.formEval = { type_eval:'', trimestre: this.trimestreNotes, date_eval:'', note_max:20, titre:'' };
    this.dialogEvalVisible = true;
  }

  creerClasse() {
    this.acad.creerClasse(this.formClasse).subscribe({
      next: () => {
        this.dialogClasseVisible = false;
        this.acad.getClasses().subscribe({ next: r => this.classes.set(r.results || []) });
        this.msg.add({ severity:'success', summary: this.translate.instant('academique.classe_creee') });
      }
    });
  }

  creerMatiere() {
    this.acad.creerMatiere(this.formMatiere).subscribe({
      next: () => {
        this.dialogMatiereVisible = false;
        this.chargerMatieres();
        this.msg.add({ severity:'success', summary: this.translate.instant('academique.matiere_creee') });
      }
    });
  }

  creerTypeEval() {
    this.acad.creerTypeEval(this.formTypeEval).subscribe({
      next: () => {
        this.dialogTypeEvalVisible = false;
        this.acad.getTypesEval().subscribe({ next: r => this.typesEval.set(r.results || []) });
        this.msg.add({ severity:'success', summary: this.translate.instant('academique.type_eval_cree') });
      }
    });
  }

  creerEvaluation() {
    const data = { ...this.formEval, matiere: this.matiereNotes };
    this.acad.creerEvaluation(data).subscribe({
      next: () => {
        this.dialogEvalVisible = false;
        this.chargerEvaluationsEtEleves();
        this.msg.add({ severity:'success', summary: this.translate.instant('academique.evaluation_creee') });
      }
    });
  }

    telechargerBulletin(eleveId: string) {
    if (!this.trimestreResultats) {
      alert('Sélectionnez un trimestre avant de télécharger le bulletin.');
      return;
    }
    const token    = localStorage.getItem('access_token');
    const tenantId = localStorage.getItem('tenant_id') || '';
    const now      = new Date();
    // Année scolaire dynamique : si mois >= 9 (sept.) → année N/N+1, sinon N-1/N
    const y = now.getMonth() >= 8 ? now.getFullYear() : now.getFullYear() - 1;
    const annee    = `${y}-${y + 1}`;
    const trimestre = this.trimestreResultats;
    const base = environment.apiUrl.replace(/\/api$/, '');
    fetch(`${base}/api/academique/bulletin-pdf/${eleveId}/${trimestre}/?annee=${annee}`, {
      headers: { 'Authorization': `Bearer ${token}`, 'X-Tenant-ID': tenantId }
    })
    .then(r => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.blob();
    })
    .then(blob => {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `bulletin_${trimestre}_${annee}.pdf`;
      a.click();
      URL.revokeObjectURL(a.href);
    })
    .catch(() => alert('Impossible de générer le bulletin. Vérifiez que les moyennes ont été calculées.'));
  }
}
