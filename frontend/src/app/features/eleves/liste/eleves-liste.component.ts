import { Component, OnInit, inject, signal, computed } from '@angular/core';
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
import { InputNumberModule } from 'primeng/inputnumber';

@Component({
  selector: 'app-eleves-liste',
  standalone: true,
  imports: [CommonModule, FormsModule, TranslateModule, TableModule, TagModule, ButtonModule,
            InputTextModule, DialogModule, SelectModule, ToastModule, ProgressBarModule, InputNumberModule],
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
                  (onClick)="onglet.set(onglet() === 'liste' ? 'prise_en_charge' : 'liste')" />
        <p-button label="{{ 'eleves.nouveau' | translate }}" severity="success" (onClick)="ouvrirDialog()" />
      </div>
    </div>

    <!-- KPIs statuts (onglet liste) -->
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

      <!-- Filtres -->
      <div class="filters-bar">
        <input pInputText [(ngModel)]="recherche" (input)="filtrer()"
               [placeholder]="'eleves.rechercher' | translate" class="search-input" />
        <p-select [options]="filtresStatut" [(ngModel)]="filtreStatut"
                  (onChange)="filtrer()" placeholder="Tous statuts"
                  optionLabel="label" optionValue="value" styleClass="filter-drop" />
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
                <p-tag [value]="eleve.niveau_alerte" [severity]="alerteSeverity(eleve.niveau_alerte)" />
              </td>
              <td>
                <div class="btn-row">
                  <p-button icon="pi pi-eye" [rounded]="true" [text]="true"
                            severity="info" pTooltip="Fiche complète" (onClick)="voirFiche(eleve)" />
                  <p-button icon="pi pi-user-edit" [rounded]="true" [text]="true"
                            severity="warn" pTooltip="Changer statut" (onClick)="ouvrirChangerStatut(eleve)" />
                  <p-button icon="pi pi-heart" [rounded]="true" [text]="true"
                            severity="secondary" pTooltip="Prise en charge" (onClick)="ouvrirPriseEnCharge(eleve)" />
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

    <!-- ONGLET PRISE EN CHARGE -->
    @if (onglet() === 'prise_en_charge') {
      <div class="kpi-row" style="margin-bottom:14px">
        <div class="kpi-mini" style="border-color:#7c3aed">
          <span class="km-val" style="color:#7c3aed">{{ elevesPEC().length }}</span>
          <span class="km-label">Bénéficiaires</span>
        </div>
        <div class="kpi-mini" *ngFor="let cat of categoriesPEC">
          <span class="km-val" style="color:#00d4aa">{{ countPEC(cat.value) }}</span>
          <span class="km-label">{{ cat.label }}</span>
        </div>
      </div>

      <div class="table-card">
        <div class="table-toolbar">
          <span class="tbl-count">🤝 Prise en charge — {{ elevesPEC().length }} bénéficiaires</span>
        </div>
        <p-table [value]="elevesPEC()" styleClass="p-datatable-sm" [paginator]="true" [rows]="20">
          <ng-template pTemplate="header">
            <tr>
              <th>Matricule</th>
              <th>Nom complet</th>
              <th>Section</th>
              <th>Catégorie</th>
              <th class="text-right">Taux prise en charge</th>
              <th>Observations</th>
              <th>Actions</th>
            </tr>
          </ng-template>
          <ng-template pTemplate="body" let-e>
            <tr>
              <td class="mono" style="color:#00d4aa;font-size:11px">{{ e.matricule }}</td>
              <td class="bold">{{ e.nom_complet }}</td>
              <td>{{ e.section_nom }}</td>
              <td>
                <p-tag [value]="pecLabel(e.prise_en_charge)" [severity]="pecSeverity(e.prise_en_charge)" />
              </td>
              <td class="mono text-right" style="color:#00d4aa">{{ e.taux_prise_en_charge }} %</td>
              <td style="font-size:11px;color:#64748b">{{ e.obs_prise_en_charge || '—' }}</td>
              <td>
                <p-button icon="pi pi-pencil" [rounded]="true" [text]="true"
                          severity="warn" (onClick)="ouvrirPriseEnCharge(e)" />
              </td>
            </tr>
          </ng-template>
          <ng-template pTemplate="emptymessage">
            <tr><td colspan="7" class="empty-msg">Aucun élève en prise en charge</td></tr>
          </ng-template>
        </p-table>
      </div>
    }

    <!-- Dialog Fiche Élève -->
    <p-dialog header="📋 Fiche Élève" [(visible)]="dialogFicheVisible"
              [modal]="true" [style]="{width:'600px'}" [draggable]="false">
      @if (eleveSelectionne()) {
        @let e = eleveSelectionne()!;
        <div class="fiche-grid">
          <div class="fiche-section">
            <div class="fiche-title">👤 Identité</div>
            <div class="fiche-row"><span>Nom complet</span><strong>{{ e.nom_complet }}</strong></div>
            <div class="fiche-row"><span>Matricule</span><strong class="mono" style="color:#00d4aa">{{ e.matricule }}</strong></div>
            <div class="fiche-row"><span>N° interne</span><strong>{{ e.numero }}</strong></div>
            <div class="fiche-row"><span>Genre</span><strong>{{ e.genre === 'F' ? 'Fille' : 'Garçon' }}</strong></div>
            <div class="fiche-row"><span>Date naissance</span><strong>{{ e.date_naissance || '—' }}</strong></div>
            <div class="fiche-row"><span>Lieu naissance</span><strong>{{ e.lieu_naissance || '—' }}</strong></div>
          </div>
          <div class="fiche-section">
            <div class="fiche-title">🏫 Scolarité</div>
            <div class="fiche-row"><span>Section</span><strong>{{ e.section_nom }}</strong></div>
            <div class="fiche-row"><span>Statut</span>
              <p-tag [value]="statutLabel(e.statut)" [severity]="statutSeverity(e.statut)" /></div>
            <div class="fiche-row"><span>Date inscription</span><strong>{{ e.date_inscription || '—' }}</strong></div>
            @if (e.prise_en_charge) {
              <div class="fiche-row"><span>Prise en charge</span>
                <p-tag [value]="pecLabel(e.prise_en_charge)" [severity]="pecSeverity(e.prise_en_charge)" /></div>
              <div class="fiche-row"><span>Taux PEC</span><strong style="color:#00d4aa">{{ e.taux_prise_en_charge }} %</strong></div>
            }
          </div>
          <div class="fiche-section">
            <div class="fiche-title">👪 Parents / Tuteurs</div>
            <div class="fiche-row"><span>Père</span><strong>{{ e.nom_pere || '—' }}</strong></div>
            <div class="fiche-row"><span>Tél. père</span><strong class="mono">{{ e.telephone_pere || '—' }}</strong></div>
            <div class="fiche-row"><span>Mère</span><strong>{{ e.nom_mere || '—' }}</strong></div>
            <div class="fiche-row"><span>Tél. mère</span><strong class="mono">{{ e.telephone_mere || '—' }}</strong></div>
          </div>
          <div class="fiche-section">
            <div class="fiche-title">💰 Situation financière</div>
            <div class="fiche-row"><span>Total attendu</span><strong class="mono">{{ e.total_attendu | number }} FCFA</strong></div>
            <div class="fiche-row"><span>Total payé</span><strong class="mono success">{{ e.total_paye | number }} FCFA</strong></div>
            <div class="fiche-row"><span>Reste à payer</span>
              <strong class="mono" [class.danger]="e.reste_a_payer > 0" [class.success]="e.reste_a_payer <= 0">
                {{ e.reste_a_payer | number }} FCFA
              </strong>
            </div>
            <div class="fiche-row"><span>Alerte</span>
              <p-tag [value]="e.niveau_alerte" [severity]="alerteSeverity(e.niveau_alerte)" /></div>
          </div>
        </div>
      }
      <ng-template pTemplate="footer">
        <p-button label="Fermer" severity="secondary" (onClick)="dialogFicheVisible=false" />
      </ng-template>
    </p-dialog>

    <!-- Dialog Changer Statut -->
    <p-dialog header="🔄 Changer le statut" [(visible)]="dialogStatutVisible"
              [modal]="true" [style]="{width:'380px'}" [draggable]="false">
      @if (eleveSelectionne()) {
        <div style="margin-bottom:14px">
          <strong style="color:#e8f0fe">{{ eleveSelectionne()!.nom_complet }}</strong>
        </div>
        <div class="form-group">
          <label>Nouveau statut</label>
          <p-select [options]="statutOptions" [(ngModel)]="formStatut"
                    optionLabel="label" optionValue="value" styleClass="w-full" />
        </div>
      }
      <ng-template pTemplate="footer">
        <p-button label="Annuler" severity="secondary" (onClick)="dialogStatutVisible=false" />
        <p-button label="Enregistrer" severity="success" [loading]="saving()" (onClick)="sauvegarderStatut()" />
      </ng-template>
    </p-dialog>

    <!-- Dialog Prise en charge -->
    <p-dialog header="🤝 Prise en charge" [(visible)]="dialogPECVisible"
              [modal]="true" [style]="{width:'440px'}" [draggable]="false">
      @if (eleveSelectionne()) {
        <div style="margin-bottom:14px">
          <strong style="color:#e8f0fe">{{ eleveSelectionne()!.nom_complet }}</strong>
        </div>
        <div class="form-grid">
          <div class="form-group full">
            <label>Catégorie</label>
            <p-select [options]="categoriesPEC" [(ngModel)]="formPEC.prise_en_charge"
                      optionLabel="label" optionValue="value" styleClass="w-full"
                      placeholder="Aucune prise en charge" [showClear]="true" />
          </div>
          <div class="form-group full">
            <label>Taux de prise en charge (%)</label>
            <p-inputNumber [(ngModel)]="formPEC.taux_prise_en_charge"
                           [min]="0" [max]="100" mode="decimal" styleClass="w-full" />
          </div>
          <div class="form-group full">
            <label>Observations</label>
            <input pInputText [(ngModel)]="formPEC.obs_prise_en_charge" class="w-full"
                   placeholder="Ex: Orphelin de père, suivi par la commune..." />
          </div>
        </div>
      }
      <ng-template pTemplate="footer">
        <p-button label="Annuler" severity="secondary" (onClick)="dialogPECVisible=false" />
        <p-button label="Enregistrer" severity="success" [loading]="saving()" (onClick)="sauvegarderPEC()" />
      </ng-template>
    </p-dialog>

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

    .filters-bar { display:flex; gap:12px; margin-bottom:16px; }
    .search-input { flex:1; }
    ::ng-deep .filter-drop { min-width:160px; }

    .table-card { background:#1e2d45; border:1px solid #2a3f5f; border-radius:12px; overflow:hidden; }
    .table-toolbar { display:flex; justify-content:space-between; align-items:center; padding:12px 16px; }
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

    .fiche-grid { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
    .fiche-section { background:#111827; border-radius:8px; padding:12px; }
    .fiche-title { font-size:11px; font-weight:700; color:#00d4aa; text-transform:uppercase; margin-bottom:8px; letter-spacing:.5px; }
    .fiche-row { display:flex; justify-content:space-between; align-items:center; padding:4px 0;
                 border-bottom:1px solid rgba(42,63,95,0.3); font-size:11px; }
    .fiche-row span { color:#64748b; }
    .fiche-row strong { color:#e8f0fe; }

    .form-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
    .form-group { display:flex; flex-direction:column; gap:5px; }
    .form-group.full { grid-column:1/-1; }
    .form-group label { font-size:11px; color:#94a3b8; text-transform:uppercase; letter-spacing:.3px; }
    .w-full { width:100%; }
  `]
})
export class ElevesListeComponent implements OnInit {
  eleves        = signal<Eleve[]>([]);
  elevesFiltres = signal<Eleve[]>([]);
  sections      = signal<any[]>([]);
  loading       = signal(true);
  saving        = signal(false);
  onglet        = signal<'liste' | 'prise_en_charge'>('liste');

  dialogVisible      = false;
  dialogFicheVisible = false;
  dialogStatutVisible = false;
  dialogPECVisible   = false;
  eleveSelectionne   = signal<any | null>(null);
  recherche     = '';
  filtreAlerte  = '';
  filtreStatut  = '';
  formStatut    = 'INSCRIT';
  formPEC: any  = {};

  private translate = inject(TranslateService);
  private elevesService = inject(ElevesService);

  elevesPEC = computed(() => this.eleves().filter(e => e.prise_en_charge));

  filtresAlerte = [
    { label: 'Toutes alertes', value: '' },
    { label: '🔴 URGENT',     value: 'URGENT' },
    { label: '🟡 ATTENTION',  value: 'ATTENTION' },
    { label: '✅ OK',         value: 'OK' },
  ];
  filtresStatut = [
    { label: 'Tous statuts',  value: '' },
    { label: '✅ Inscrit',    value: 'INSCRIT' },
    { label: '❌ Abandonné',  value: 'ABANDONNE' },
    { label: '↗️ Transféré', value: 'TRANSFERE' },
    { label: '🎓 Diplômé',   value: 'DIPLOME' },
  ];
  statutOptions = [
    { label: 'Inscrit',    value: 'INSCRIT' },
    { label: 'Abandonné',  value: 'ABANDONNE' },
    { label: 'Transféré',  value: 'TRANSFERE' },
    { label: 'Diplômé',   value: 'DIPLOME' },
  ];
  categoriesPEC = [
    { label: 'Orphelin',        value: 'ORPHELIN' },
    { label: 'Handicap',        value: 'HANDICAP' },
    { label: 'Famille démunie', value: 'FAMILLE_DEMUNIE' },
    { label: 'Autre',           value: 'AUTRE' },
  ];
  genreOptions = [
    { label: 'Garçon', value: 'G' },
    { label: 'Fille',  value: 'F' },
  ];

  nouvelEleve: Partial<Eleve> = {};

  constructor(private msg: MessageService) {}

  ngOnInit() {
    this.chargerEleves();
    this.chargerSections();
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

  filtrer() {
    let data = this.eleves();
    if (this.recherche)    data = data.filter(e => e.nom_complet.toLowerCase().includes(this.recherche.toLowerCase()));
    if (this.filtreAlerte) data = data.filter(e => (e as any).niveau_alerte === this.filtreAlerte);
    if (this.filtreStatut) data = data.filter(e => (e as any).statut === this.filtreStatut);
    this.elevesFiltres.set(data);
  }

  countStatut(s: string) { return this.eleves().filter(e => (e as any).statut === s).length; }
  countGenre(g: string)  { return this.eleves().filter(e => e.genre === g).length; }
  countPEC(cat: string)  { return this.eleves().filter(e => (e as any).prise_en_charge === cat).length; }

  alerteSeverity(a: string): 'danger' | 'warn' | 'success' {
    return a === 'URGENT' ? 'danger' : a === 'ATTENTION' ? 'warn' : 'success';
  }
  statutLabel(s: string) {
    return { INSCRIT:'Inscrit', ABANDONNE:'Abandonné', TRANSFERE:'Transféré', DIPLOME:'Diplômé' }[s] || s;
  }
  statutSeverity(s: string): any {
    return { INSCRIT:'success', ABANDONNE:'danger', TRANSFERE:'warn', DIPLOME:'info' }[s] || 'secondary';
  }
  pecLabel(c: string) {
    return { ORPHELIN:'Orphelin', HANDICAP:'Handicap', FAMILLE_DEMUNIE:'Fam. démunie', AUTRE:'Autre' }[c] || c;
  }
  pecSeverity(c: string): any {
    return { ORPHELIN:'danger', HANDICAP:'warn', FAMILLE_DEMUNIE:'info', AUTRE:'secondary' }[c] || 'secondary';
  }

  voirFiche(eleve: any) {
    this.eleveSelectionne.set(eleve);
    this.dialogFicheVisible = true;
  }

  ouvrirChangerStatut(eleve: any) {
    this.eleveSelectionne.set(eleve);
    this.formStatut = eleve.statut || 'INSCRIT';
    this.dialogStatutVisible = true;
  }

  sauvegarderStatut() {
    const e = this.eleveSelectionne();
    if (!e) return;
    this.saving.set(true);
    this.elevesService.updateEleve(e.id, { statut: this.formStatut } as any).subscribe({
      next: () => {
        this.msg.add({ severity: 'success', summary: 'Statut mis à jour', detail: e.nom_complet });
        this.dialogStatutVisible = false;
        this.saving.set(false);
        this.chargerEleves();
      },
      error: () => this.saving.set(false),
    });
  }

  ouvrirPriseEnCharge(eleve: any) {
    this.eleveSelectionne.set(eleve);
    this.formPEC = {
      prise_en_charge:      eleve.prise_en_charge || null,
      taux_prise_en_charge: eleve.taux_prise_en_charge || 0,
      obs_prise_en_charge:  eleve.obs_prise_en_charge || '',
    };
    this.dialogPECVisible = true;
  }

  sauvegarderPEC() {
    const e = this.eleveSelectionne();
    if (!e) return;
    this.saving.set(true);
    this.elevesService.updateEleve(e.id, this.formPEC).subscribe({
      next: () => {
        this.msg.add({ severity: 'success', summary: 'Prise en charge enregistrée' });
        this.dialogPECVisible = false;
        this.saving.set(false);
        this.chargerEleves();
      },
      error: () => this.saving.set(false),
    });
  }

  ouvrirDialog() {
    this.nouvelEleve = {};
    this.dialogVisible = true;
  }

  sauvegarder() {
    if (!this.nouvelEleve.nom_complet) {
      this.msg.add({ severity: 'warn', summary: this.translate.instant('eleves.champ_requis'),
                     detail: this.translate.instant('eleves.nom_obligatoire') });
      return;
    }
    this.saving.set(true);
    this.elevesService.createEleve(this.nouvelEleve).subscribe({
      next: () => {
        this.msg.add({ severity: 'success', summary: this.translate.instant('common.succes'),
                       detail: this.translate.instant('eleves.ajoute') });
        this.dialogVisible = false;
        this.saving.set(false);
        this.chargerEleves();
      },
      error: () => {
        this.msg.add({ severity: 'error', summary: this.translate.instant('common.erreur'),
                       detail: this.translate.instant('eleves.impossible_ajouter') });
        this.saving.set(false);
      }
    });
  }
}
