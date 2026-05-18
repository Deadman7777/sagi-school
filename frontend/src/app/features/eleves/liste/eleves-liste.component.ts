import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ElevesService } from '../../../core/services/eleves.service';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { Eleve } from '../../../core/models/eleve.model';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { DialogModule } from 'primeng/dialog';
import { SelectModule } from 'primeng/select';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';
import { ProgressBarModule } from 'primeng/progressbar';

@Component({
  selector: 'app-eleves-liste',
  standalone: true,
  imports: [CommonModule, FormsModule, TranslateModule, TableModule, TagModule, ButtonModule,
            InputTextModule, DialogModule, SelectModule, ToastModule, ProgressBarModule],
  providers: [MessageService],
  template: `
    <p-toast />

    <!-- Header -->
    <div class="page-header">
      <div>
        <h2 class="page-title">{{ 'eleves.title' | translate }}</h2>
        <span class="page-sub">{{ eleves().length }} élèves · Année 2025-2026</span>
      </div>
      <p-button label="{{ 'eleves.nouveau' | translate }}" severity="success" (onClick)="ouvrirDialog()" />
    </div>

    <!-- Filtres -->
    <div class="filters-bar">
      <input pInputText [(ngModel)]="recherche" (input)="filtrer()"
             [placeholder]="'eleves.rechercher' | translate" class="search-input" />
      <p-select [options]="filtresAlerte" [(ngModel)]="filtreAlerte"
                  (onChange)="filtrer()" [placeholder]="'eleves.toutes_alertes' | translate"
                  optionLabel="label" optionValue="value" styleClass="filter-drop" />
    </div>

    <!-- Table -->
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
            <td class="mono">{{ eleve.total_attendu | number }} FCFA</td>
            <td class="mono success">{{ eleve.total_paye | number }} FCFA</td>
            <td class="mono" [class.danger]="eleve.reste_a_payer > 0">
              {{ eleve.reste_a_payer | number }} FCFA
            </td>
            <td>
              <p-tag [value]="eleve.niveau_alerte"
                     [severity]="alerteSeverity(eleve.niveau_alerte)" />
            </td>
            <td>
              <p-button icon="pi pi-eye" [rounded]="true" [text]="true"
                        severity="info" (onClick)="voirEleve(eleve)" />
            </td>
          </tr>
        </ng-template>
        <ng-template pTemplate="emptymessage">
          <tr><td colspan="9" class="empty-msg">{{ 'eleves.aucun' | translate }}</td></tr>
        </ng-template>
      </p-table>
    </div>

    <!-- Dialog Nouvel Élève -->
    <p-dialog [header]="'eleves.nouveau' | translate" [(visible)]="dialogVisible"
              [modal]="true" [style]="{width: '480px'}" [draggable]="false">
      <div class="form-grid">
        <div class="form-group full">
          <label>{{ 'eleves.nom_complet' | translate }} *</label>
          <input pInputText [(ngModel)]="nouvelEleve.nom_complet" class="w-full" />
        </div>
        <div class="form-group">
          <label>{{ 'eleves.section' | translate }} *</label>
          <p-select [options]="sections()" [(ngModel)]="nouvelEleve.section"
                      optionLabel="nom" optionValue="id"
                      [placeholder]="'eleves.choisir' | translate" styleClass="w-full" />
        </div>
        <div class="form-group">
          <label>{{ 'eleves.genre' | translate }}</label>
          <p-select [options]="genreOptions" [(ngModel)]="nouvelEleve.genre"
                      optionLabel="label" optionValue="value" styleClass="w-full" />
        </div>
        <div class="form-group">
          <label>{{ 'eleves.date_naissance' | translate }}</label>
          <input pInputText type="date" [(ngModel)]="nouvelEleve.date_naissance" class="w-full" />
        </div>
        <div class="form-group">
          <label>{{ 'eleves.lieu_naissance' | translate }}</label>
          <input pInputText [(ngModel)]="nouvelEleve.lieu_naissance" class="w-full"
                 [placeholder]="'eleves.lieu_naissance_ph' | translate" />
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
      </div>
      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler'    | translate" severity="secondary" (onClick)="dialogVisible = false" />
        <p-button [label]="'common.enregistrer'| translate" severity="success" [loading]="saving()" (onClick)="sauvegarder()" />
      </ng-template>
    </p-dialog>
  `,
  styles: [`
    .page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
    .page-title  { font-size: 20px; font-weight: 600; color: #e8f0fe; margin: 0 0 4px; }
    .page-sub    { font-size: 12px; color: #64748b; }

    .filters-bar { display: flex; gap: 12px; margin-bottom: 16px; }
    .search-input { flex: 1; }
    ::ng-deep .filter-drop { min-width: 180px; }

    .table-card { background: #1e2d45; border: 1px solid #2a3f5f; border-radius: 12px; overflow: hidden; }

    ::ng-deep .p-datatable .p-datatable-thead > tr > th {
      background: #111827 !important; color: #64748b !important;
      font-size: 11px !important; text-transform: uppercase !important;
      letter-spacing: 0.5px !important; border-color: #2a3f5f !important;
    }
    ::ng-deep .p-datatable .p-datatable-tbody > tr {
      background: #1e2d45 !important; color: #94a3b8 !important;
      border-bottom: 1px solid rgba(42,63,95,0.4) !important;
    }
    ::ng-deep .p-datatable .p-datatable-tbody > tr:hover {
      background: #1a2235 !important;
    }

    .mono    { font-family: monospace; font-size: 12px; }
    .bold    { font-weight: 600; color: #e8f0fe; }
    .success { color: #10b981; }
    .danger  { color: #ef4444; }
    .empty-msg { text-align: center; padding: 40px; color: #64748b; }

    .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    .form-group { display: flex; flex-direction: column; gap: 6px; }
    .form-group.full { grid-column: 1 / -1; }
    .form-group label { font-size: 12px; color: #94a3b8; }
  `]
})
export class ElevesListeComponent implements OnInit {
  eleves        = signal<Eleve[]>([]);
  elevesFiltres = signal<Eleve[]>([]);
  sections      = signal<any[]>([]);
  loading       = signal(true);
  saving        = signal(false);
  dialogVisible = false;
  recherche     = '';
  filtreAlerte  = '';

  private translate = inject(TranslateService);

  filtresAlerte = [
    { label: 'Toutes alertes', value: '' },
    { label: '🔴 URGENT',      value: 'URGENT' },
    { label: '🟡 ATTENTION',   value: 'ATTENTION' },
    { label: '✅ OK',          value: 'OK' },
  ];

  genreOptions = [
    { label: 'Garçon', value: 'G' },
    { label: 'Fille',  value: 'F' },
  ];

  nouvelEleve: Partial<Eleve> = {};

  constructor(private elevesService: ElevesService, private msg: MessageService) {}

  chargerEleves() {
    this.loading.set(true);
    this.elevesService.getEleves().subscribe({
      next: res => {
          const data = Array.isArray(res) ? res : (res.results || []);
          this.eleves.set(data);
          this.elevesFiltres.set(data);
          this.loading.set(false);
      },
      error: () => this.loading.set(false)
    });
  }

  chargerSections() {
    this.elevesService.getSections().subscribe({
      next: res => this.sections.set(res.results)
    });
  }

  filtrer() {
    let data = this.eleves();
    if (this.recherche) {
      data = data.filter(e => e.nom_complet.toLowerCase().includes(this.recherche.toLowerCase()));
    }
    if (this.filtreAlerte) {
      data = data.filter(e => e.niveau_alerte === this.filtreAlerte);
    }
    this.elevesFiltres.set(data);
  }

  alerteSeverity(alerte: string): 'danger' | 'warn' | 'success' {
    return alerte === 'URGENT' ? 'danger' : alerte === 'ATTENTION' ? 'warn' : 'success';
  }

  ouvrirDialog() {
    this.nouvelEleve = {};
    this.dialogVisible = true;
  }

  voirEleve(eleve: Eleve) {
    this.msg.add({ severity: 'info', summary: eleve.nom_complet,
                   detail: `Reste à payer: ${eleve.reste_a_payer.toLocaleString()} FCFA` });
  }

  ngOnInit() {
    this.genreOptions = [
      { label: this.translate.instant('eleves.garcon'), value: 'G' },
      { label: this.translate.instant('eleves.fille'),  value: 'F' },
    ];
    this.chargerEleves();
    this.chargerSections();
  }

  sauvegarder() {
    if (!this.nouvelEleve.nom_complet) {
      this.msg.add({ severity: 'warn', summary: this.translate.instant('eleves.champ_requis'), detail: this.translate.instant('eleves.nom_obligatoire') });
      return;
    }
    this.saving.set(true);
    this.elevesService.createEleve(this.nouvelEleve).subscribe({
      next: () => {
        this.msg.add({ severity: 'success', summary: this.translate.instant('common.succes'), detail: this.translate.instant('eleves.ajoute') });
        this.dialogVisible = false;
        this.saving.set(false);
        this.chargerEleves();
      },
      error: () => {
        this.msg.add({ severity: 'error', summary: this.translate.instant('common.erreur'), detail: this.translate.instant('eleves.impossible_ajouter') });
        this.saving.set(false);
      }
    });
  }
}
