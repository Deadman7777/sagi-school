import { Component, OnInit, signal } from '@angular/core';
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

@Component({
  selector: 'app-academique',
  standalone: true,
  imports: [CommonModule, FormsModule, TableModule, ButtonModule, DialogModule,
            InputTextModule, SelectModule, TagModule, InputNumberModule, ToastModule],
  providers: [MessageService],
  template: `
    <p-toast />
    <div class="page-header">
      <div>
        <h2 class="page-title">📚 Gestion Académique</h2>
        <span class="page-sub">Classes · Matières · Notes · Bulletins</span>
      </div>
    </div>

    <!-- Onglets -->
    <div class="tabs-bar">
      <button class="tab-btn" [class.active]="onglet()==='parametrage'" (click)="onglet.set('parametrage')">⚙️ Paramétrage</button>
      <button class="tab-btn" [class.active]="onglet()==='notes'" (click)="onglet.set('notes')">📝 Saisie Notes</button>
      <button class="tab-btn" [class.active]="onglet()==='resultats'" (click)="onglet.set('resultats')">📊 Résultats</button>
    </div>

    <!-- PARAMÉTRAGE -->
    <div *ngIf="onglet()==='parametrage'">
      <div class="param-grid">

        <!-- Classes -->
        <div class="param-card">
          <div class="pc-header">
            <span>🏫 Classes</span>
            <p-button icon="pi pi-plus" [rounded]="true" [text]="true"
                      severity="success" (onClick)="ouvrirDialogClasse()" />
          </div>
          <div class="pc-body">
            <div class="pc-item" *ngFor="let c of classes()">
              <span>{{ c.nom }}</span>
              <span class="badge">{{ c.niveau_nom }}</span>
            </div>
            <div class="empty-msg" *ngIf="classes().length===0">Aucune classe</div>
          </div>
        </div>

        <!-- Matières -->
        <div class="param-card">
          <div class="pc-header">
            <span>📖 Matières</span>
            <p-button icon="pi pi-plus" [rounded]="true" [text]="true"
                      severity="success" (onClick)="ouvrirDialogMatiere()" />
          </div>
          <div class="pc-filter">
            <p-select [options]="classes()" [(ngModel)]="classeFiltre"
                      optionLabel="nom" optionValue="id"
                      placeholder="Filtrer par classe..."
                      styleClass="w-full" (onChange)="chargerMatieres()" />
          </div>
          <div class="pc-body">
            <div class="pc-item" *ngFor="let m of matieres()">
              <span>{{ m.nom }}</span>
              <span class="badge">Coef {{ m.coefficient }}</span>
            </div>
            <div class="empty-msg" *ngIf="matieres().length===0">Sélectionnez une classe</div>
          </div>
        </div>

        <!-- Types d'évaluation -->
        <div class="param-card">
          <div class="pc-header">
            <span>📋 Types d'Évaluation</span>
            <p-button icon="pi pi-plus" [rounded]="true" [text]="true"
                      severity="success" (onClick)="ouvrirDialogTypeEval()" />
          </div>
          <div class="pc-body">
            <div class="pc-item" *ngFor="let t of typesEval()">
              <span>{{ t.nom }}</span>
              <span class="badge">Poids {{ t.poids }}</span>
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
                  placeholder="Classe..." styleClass="filter-drop"
                  (onChange)="onClasseNotesChange()" />
        <p-select [options]="matieresNotes()" [(ngModel)]="matiereNotes"
                  optionLabel="nom" optionValue="id"
                  placeholder="Matière..." styleClass="filter-drop"
                  (onChange)="chargerEvaluations()" />
        <p-select [options]="trimestres" [(ngModel)]="trimestreNotes"
                  optionLabel="label" optionValue="value"
                  placeholder="Trimestre..." styleClass="filter-drop" />
        <p-button label="+ Évaluation" severity="success"
                  (onClick)="ouvrirDialogEvaluation()" [disabled]="!matiereNotes" />
      </div>

      <!-- Liste évaluations -->
      <div class="evals-list" *ngIf="evaluations().length > 0">
        <div class="eval-card" *ngFor="let e of evaluations()"
             [class.active]="evalSelectionnee?.id === e.id"
             (click)="selectionnerEvaluation(e)">
          <div class="ec-titre">{{ e.matiere_nom }} — {{ e.type_eval_nom }}</div>
          <div class="ec-info">{{ e.trimestre }} · {{ e.date_eval | date:'dd/MM/yyyy' }} · /{{ e.note_max }}</div>
        </div>
      </div>

      <!-- Grille de saisie notes -->
      <div class="table-card" *ngIf="evalSelectionnee" style="margin-top:16px">
        <div style="padding:12px 16px;border-bottom:1px solid #2a3f5f;display:flex;justify-content:space-between">
          <span style="color:#e8f0fe;font-weight:600">
            Notes — {{ evalSelectionnee.matiere_nom }} / {{ evalSelectionnee.type_eval_nom }}
          </span>
          <p-button label="Enregistrer tout" severity="success"
                    [loading]="saving()" (onClick)="sauvegarderNotes()" />
        </div>
        <p-table [value]="elevesNotes()" styleClass="p-datatable-sm">
          <ng-template pTemplate="header">
            <tr>
              <th>N°</th>
              <th>Nom Élève</th>
              <th>Note /{{ evalSelectionnee.note_max }}</th>
              <th>Absent</th>
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
              <td>
                <input type="checkbox" [(ngModel)]="e.absent_saisie"
                       (change)="e.absent_saisie && (e.note_saisie = 0)" />
              </td>
            </tr>
          </ng-template>
        </p-table>
      </div>
    </div>

    <!-- RÉSULTATS -->
    <div *ngIf="onglet()==='resultats'">
      <div class="filters-bar" style="margin-bottom:16px">
        <p-select [options]="classes()" [(ngModel)]="classeResultats"
                  optionLabel="nom" optionValue="id"
                  placeholder="Classe..." styleClass="filter-drop" />
        <p-select [options]="trimestres" [(ngModel)]="trimestreResultats"
                  optionLabel="label" optionValue="value"
                  placeholder="Trimestre..." styleClass="filter-drop" />
        <p-button label="🔢 Calculer Moyennes" severity="success"
                  [loading]="calculant()" (onClick)="calculerMoyennes()" />
      </div>

      <!-- Résultats -->
      <div class="table-card" *ngIf="resultats().length > 0">
        <!-- Stats classe -->
        <div class="stats-classe" *ngIf="statsClasse()">
          <div class="sc-item"><span>Moy. classe</span><strong>{{ statsClasse().moy_classe }}</strong></div>
          <div class="sc-item"><span>Plus haute</span><strong style="color:#10b981">{{ statsClasse().moy_max }}</strong></div>
          <div class="sc-item"><span>Plus basse</span><strong style="color:#ef4444">{{ statsClasse().moy_min }}</strong></div>
          <div class="sc-item"><span>Taux réussite</span><strong style="color:#0099ff">{{ statsClasse().taux_reussite }}%</strong></div>
        </div>

        <p-table [value]="resultats()" styleClass="p-datatable-sm"
                 [paginator]="true" [rows]="20">
          <ng-template pTemplate="header">
            <tr>
              <th>Rang</th>
              <th>Élève</th>
              <th *ngFor="let m of colonnesMatieres()">{{ m }}</th>
              <th>Moy. Générale</th>
              <th>Appréciation</th>
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
            </tr>
          </ng-template>
        </p-table>
      </div>
    </div>

    <!-- Dialog Classe -->
    <p-dialog header="🏫 Nouvelle Classe" [(visible)]="dialogClasseVisible"
              [modal]="true" [style]="{width:'400px'}">
      <div class="form-grid" style="grid-template-columns:1fr">
        <div class="form-group">
          <label>Niveau *</label>
          <p-select [options]="niveaux()" [(ngModel)]="formClasse.niveau"
                    optionLabel="nom" optionValue="id" styleClass="w-full" />
        </div>
        <div class="form-group">
          <label>Nom *</label>
          <input pInputText [(ngModel)]="formClasse.nom" class="w-full" placeholder="Ex: CE1 A" />
        </div>
        <div class="form-group">
          <label>Code</label>
          <input pInputText [(ngModel)]="formClasse.code" class="w-full" placeholder="Ex: CE1A" />
        </div>
      </div>
      <ng-template pTemplate="footer">
        <p-button label="Annuler" severity="secondary" (onClick)="dialogClasseVisible=false" />
        <p-button label="Créer" severity="success" (onClick)="creerClasse()" />
      </ng-template>
    </p-dialog>

    <!-- Dialog Matière -->
    <p-dialog header="📖 Nouvelle Matière" [(visible)]="dialogMatiereVisible"
              [modal]="true" [style]="{width:'400px'}">
      <div class="form-grid" style="grid-template-columns:1fr">
        <div class="form-group">
          <label>Classe *</label>
          <p-select [options]="classes()" [(ngModel)]="formMatiere.classe"
                    optionLabel="nom" optionValue="id" styleClass="w-full" />
        </div>
        <div class="form-group">
          <label>Nom *</label>
          <input pInputText [(ngModel)]="formMatiere.nom" class="w-full" placeholder="Ex: Mathématiques" />
        </div>
        <div class="form-group">
          <label>Coefficient</label>
          <p-inputNumber [(ngModel)]="formMatiere.coefficient" [min]="0.5" [max]="10"
                         mode="decimal" styleClass="w-full" />
        </div>
        <div class="form-group">
          <label>Note maximale</label>
          <p-select [options]="[{label:'Sur 10', value:10},{label:'Sur 20', value:20}]"
                    [(ngModel)]="formMatiere.note_max"
                    optionLabel="label" optionValue="value" styleClass="w-full" />
        </div>
      </div>
      <ng-template pTemplate="footer">
        <p-button label="Annuler" severity="secondary" (onClick)="dialogMatiereVisible=false" />
        <p-button label="Créer" severity="success" (onClick)="creerMatiere()" />
      </ng-template>
    </p-dialog>

    <!-- Dialog Type Évaluation -->
    <p-dialog header="📋 Type d'Évaluation" [(visible)]="dialogTypeEvalVisible"
              [modal]="true" [style]="{width:'400px'}">
      <div class="form-grid" style="grid-template-columns:1fr">
        <div class="form-group">
          <label>Nom *</label>
          <input pInputText [(ngModel)]="formTypeEval.nom" class="w-full" placeholder="Ex: Devoir" />
        </div>
        <div class="form-group">
          <label>Poids</label>
          <p-inputNumber [(ngModel)]="formTypeEval.poids" [min]="0.5" [max]="5"
                         mode="decimal" styleClass="w-full" />
        </div>
      </div>
      <ng-template pTemplate="footer">
        <p-button label="Annuler" severity="secondary" (onClick)="dialogTypeEvalVisible=false" />
        <p-button label="Créer" severity="success" (onClick)="creerTypeEval()" />
      </ng-template>
    </p-dialog>

    <!-- Dialog Évaluation -->
    <p-dialog header="📝 Nouvelle Évaluation" [(visible)]="dialogEvalVisible"
              [modal]="true" [style]="{width:'420px'}">
      <div class="form-grid" style="grid-template-columns:1fr 1fr">
        <div class="form-group full">
          <label>Type d'évaluation *</label>
          <p-select [options]="typesEval()" [(ngModel)]="formEval.type_eval"
                    optionLabel="nom" optionValue="id" styleClass="w-full" />
        </div>
        <div class="form-group">
          <label>Trimestre *</label>
          <p-select [options]="trimestres" [(ngModel)]="formEval.trimestre"
                    optionLabel="label" optionValue="value" styleClass="w-full" />
        </div>
        <div class="form-group">
          <label>Date *</label>
          <input pInputText type="date" [(ngModel)]="formEval.date_eval" class="w-full" />
        </div>
        <div class="form-group">
          <label>Note max</label>
          <p-select [options]="[{label:'Sur 10', value:10},{label:'Sur 20', value:20}]"
                    [(ngModel)]="formEval.note_max"
                    optionLabel="label" optionValue="value" styleClass="w-full" />
        </div>
        <div class="form-group full">
          <label>Titre (optionnel)</label>
          <input pInputText [(ngModel)]="formEval.titre" class="w-full" placeholder="Ex: Devoir n°1" />
        </div>
      </div>
      <ng-template pTemplate="footer">
        <p-button label="Annuler" severity="secondary" (onClick)="dialogEvalVisible=false" />
        <p-button label="Créer" severity="success" (onClick)="creerEvaluation()" />
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

  trimestres = [
    { label: 'Trimestre 1', value: 'T1' },
    { label: 'Trimestre 2', value: 'T2' },
    { label: 'Trimestre 3', value: 'T3' },
  ];

  constructor(
    private acad: AcademiqueService,
    private elevesService: ElevesService,
    private msg: MessageService
  ) {}

  ngOnInit() {
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
  }

  chargerEvaluations() {
    if (!this.matiereNotes) return;
    this.acad.getEvaluations({ matiere: this.matiereNotes }).subscribe({
      next: r => this.evaluations.set(r.results || [])
    });
  }

  selectionnerEvaluation(eval_: any) {
    this.evalSelectionnee = eval_;
    // Charger les élèves de la classe avec leurs notes existantes
    this.elevesService.getEleves({ section: this.classeNotes }).subscribe({
      next: r => {
        const eleves = (r.results || []).map((e: any) => ({
          ...e,
          note_saisie: 0,
          absent_saisie: false,
          note_id: null,
        }));
        // Charger notes existantes
        this.acad.getNotes({ evaluation: eval_.id }).subscribe({
          next: rn => {
            const notes = rn.results || [];
            eleves.forEach((e: any) => {
              const n = notes.find((n: any) => n.eleve === e.id);
              if (n) { e.note_saisie = n.valeur; e.absent_saisie = n.absent; e.note_id = n.id; }
            });
            this.elevesNotes.set(eleves);
          }
        });
      }
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
      this.msg.add({ severity: 'success', summary: 'Notes enregistrées ✅', detail: `${promises.length} notes sauvegardées` });
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
        this.msg.add({ severity: 'success', summary: 'Calcul terminé ✅', detail: `${res.resultats?.length} élèves traités` });
      },
      error: () => this.calculant.set(false)
    });
  }

  getAppreciation(moy: number, noteMax: number): string {
    const ratio = moy / noteMax * 20;
    if (ratio >= 18) return '🌟 Excellent';
    if (ratio >= 16) return '👍 Très Bien';
    if (ratio >= 14) return '✅ Bien';
    if (ratio >= 12) return '🆗 Assez Bien';
    if (ratio >= 10) return '⚠️ Passable';
    return '❌ Insuffisant';
  }

  ouvrirDialogClasse()   { this.formClasse   = { nom:'', code:'', niveau:'' }; this.dialogClasseVisible   = true; }
  ouvrirDialogMatiere()  { this.formMatiere  = { nom:'', classe:'', coefficient:1, note_max:20 }; this.dialogMatiereVisible  = true; }
  ouvrirDialogTypeEval() { this.formTypeEval = { nom:'', poids:1 }; this.dialogTypeEvalVisible = true; }
  ouvrirDialogEvaluation() {
    if (!this.matiereNotes) { this.msg.add({ severity:'warn', summary:'Sélectionnez une matière' }); return; }
    this.formEval = { type_eval:'', trimestre: this.trimestreNotes, date_eval:'', note_max:20, titre:'' };
    this.dialogEvalVisible = true;
  }

  creerClasse() {
    this.acad.creerClasse(this.formClasse).subscribe({
      next: () => {
        this.dialogClasseVisible = false;
        this.acad.getClasses().subscribe({ next: r => this.classes.set(r.results || []) });
        this.msg.add({ severity:'success', summary:'Classe créée ✅' });
      }
    });
  }

  creerMatiere() {
    this.acad.creerMatiere(this.formMatiere).subscribe({
      next: () => {
        this.dialogMatiereVisible = false;
        this.chargerMatieres();
        this.msg.add({ severity:'success', summary:'Matière créée ✅' });
      }
    });
  }

  creerTypeEval() {
    this.acad.creerTypeEval(this.formTypeEval).subscribe({
      next: () => {
        this.dialogTypeEvalVisible = false;
        this.acad.getTypesEval().subscribe({ next: r => this.typesEval.set(r.results || []) });
        this.msg.add({ severity:'success', summary:'Type d\'évaluation créé ✅' });
      }
    });
  }

  creerEvaluation() {
    const data = { ...this.formEval, matiere: this.matiereNotes };
    this.acad.creerEvaluation(data).subscribe({
      next: () => {
        this.dialogEvalVisible = false;
        this.chargerEvaluations();
        this.msg.add({ severity:'success', summary:'Évaluation créée ✅' });
      }
    });
  }
}
