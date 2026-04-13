import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/services/api.service';
import { ElevesService } from '../../core/services/eleves.service';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { TagModule } from 'primeng/tag';
import { AutoCompleteModule } from 'primeng/autocomplete';
import { Eleve } from '../../core/models/eleve.model';

@Component({
  selector: 'app-suivi-mensuel',
  standalone: true,
  imports: [CommonModule, FormsModule, TableModule, ButtonModule,
            TagModule, AutoCompleteModule],
  template: `
    <div class="page-header">
      <div>
        <h2 class="page-title">📅 Suivi Mensuel</h2>
        <span class="page-sub">Activité mensuelle & historique par élève</span>
      </div>
    </div>

    <!-- Onglets -->
    <div class="tabs-bar">
      <button class="tab-btn" [class.active]="onglet() === 'global'"
              (click)="onglet.set('global')">📊 Vue Globale</button>
      <button class="tab-btn" [class.active]="onglet() === 'eleve'"
              (click)="onglet.set('eleve')">👤 Par Élève</button>
    </div>

    <!-- ══ VUE GLOBALE ══ -->
    <ng-container *ngIf="onglet() === 'global'">

      <!-- Totaux globaux -->
      <div class="kpi-row" *ngIf="globalData().length > 0">
        <div class="kpi-mini teal">
          <div class="km-label">Total Encaissé</div>
          <div class="km-val">{{ totalGlobal() | number:'1.0-0' }} FCFA</div>
        </div>
        <div class="kpi-mini blue">
          <div class="km-label">Nb Transactions</div>
          <div class="km-val">{{ nbTransactions() }}</div>
        </div>
        <div class="kpi-mini green">
          <div class="km-label">Mois Actifs</div>
          <div class="km-val">{{ globalData().length }}</div>
        </div>
        <div class="kpi-mini orange">
          <div class="km-label">Moyenne/Mois</div>
          <div class="km-val">
            {{ (totalGlobal() / globalData().length) | number:'1.0-0' }} FCFA
          </div>
        </div>
      </div>

      <!-- Barres visuelles -->
      <div class="bar-section" *ngIf="globalData().length > 0">
        <div class="bs-title">Évolution mensuelle des encaissements</div>
        <div class="bars-wrap">
          <div class="bar-item" *ngFor="let m of globalData()">
            <div class="bar-track">
              <div class="bar-fill"
                   [style.height.%]="(m.total / maxMensuel()) * 100"
                   [title]="m.total | number:'1.0-0'">
              </div>
            </div>
            <div class="bar-label">{{ m.mois_court }}</div>
            <div class="bar-val">{{ m.total | number:'1.0-0' }}</div>
          </div>
        </div>
      </div>

      <!-- Tableau détail -->
      <div class="table-card">
        <p-table [value]="globalData()" [loading]="loading()"
                 styleClass="p-datatable-sm" [showGridlines]="true">
          <ng-template pTemplate="header">
            <tr>
              <th>Mois</th>
              <th class="text-right">Nb Paiements</th>
              <th class="text-right">Inscription</th>
              <th class="text-right">Mensualité</th>
              <th class="text-right">Uniforme</th>
              <th class="text-right">Fournitures</th>
              <th class="text-right">Cantine</th>
              <th class="text-right">Total Mois</th>
            </tr>
          </ng-template>
          <ng-template pTemplate="body" let-m>
            <tr>
              <td class="bold">{{ m.mois }}</td>
              <td class="mono text-right">{{ m.nb }}</td>
              <td class="mono text-right">{{ m.inscription | number:'1.0-0' }}</td>
              <td class="mono text-right">{{ m.mensualite  | number:'1.0-0' }}</td>
              <td class="mono text-right">{{ m.uniforme    | number:'1.0-0' }}</td>
              <td class="mono text-right">{{ m.fournitures | number:'1.0-0' }}</td>
              <td class="mono text-right">{{ m.cantine     | number:'1.0-0' }}</td>
              <td class="mono text-right teal bold">{{ m.total | number:'1.0-0' }}</td>
            </tr>
          </ng-template>
          <ng-template pTemplate="footer">
            <tr>
              <td class="bold">TOTAL</td>
              <td class="mono text-right bold">{{ nbTransactions() }}</td>
              <td colspan="5"></td>
              <td class="mono text-right bold teal">{{ totalGlobal() | number:'1.0-0' }}</td>
            </tr>
          </ng-template>
          <ng-template pTemplate="emptymessage">
            <tr><td colspan="8" class="empty-msg">Aucun paiement enregistré</td></tr>
          </ng-template>
        </p-table>
      </div>
    </ng-container>

    <!-- ══ VUE PAR ÉLÈVE ══ -->
    <ng-container *ngIf="onglet() === 'eleve'">

      <!-- Recherche élève -->
      <div class="search-zone">
        <p-autoComplete
          [(ngModel)]="eleveSelectionne"
          [suggestions]="suggestions()"
          (completeMethod)="chercher($event)"
          field="nom_complet"
          placeholder="🔍 Recherchez un élève..."
          styleClass="w-full"
          [forceSelection]="true"
          (onSelect)="chargerSuiviEleve($event.value)">
          <ng-template let-e pTemplate="item">
            <div style="padding:6px 0">
              <div style="font-weight:600">{{ e.nom_complet }}</div>
              <div style="font-size:11px;color:#64748b">
                {{ e.section_nom }} —
                Reste: {{ e.reste_a_payer | number:'1.0-0' }} FCFA
              </div>
            </div>
          </ng-template>
        </p-autoComplete>
      </div>

      <!-- Fiche élève -->
      <ng-container *ngIf="eleveDetail()">
        <!-- Entête -->
        <div class="eleve-card">
          <div class="ec-avatar">
            {{ eleveDetail()!.nom.substring(0,2).toUpperCase() }}
          </div>
          <div class="ec-info">
            <div class="ec-nom">{{ eleveDetail()!.nom }}</div>
            <div class="ec-section">{{ eleveDetail()!.section }}</div>
          </div>
          <div class="ec-stats">
            <div class="ecs">
              <div class="ecs-label">Total Attendu</div>
              <div class="ecs-val">{{ eleveDetail()!.attendu | number:'1.0-0' }} FCFA</div>
            </div>
            <div class="ecs">
              <div class="ecs-label">Total Payé</div>
              <div class="ecs-val" style="color:#10b981">
                {{ eleveDetail()!.total_paye | number:'1.0-0' }} FCFA
              </div>
            </div>
            <div class="ecs">
              <div class="ecs-label">Reste</div>
              <div class="ecs-val"
                   [style.color]="eleveDetail()!.reste > 0 ? '#ef4444' : '#10b981'">
                {{ eleveDetail()!.reste | number:'1.0-0' }} FCFA
              </div>
            </div>
          </div>
        </div>

        <!-- Barre de progression recouvrement -->
        <div class="progress-card">
          <div class="pc-header">
            <span>Taux de recouvrement</span>
            <span class="mono teal">
              {{ pctRecouvrement() | number:'1.0-0' }}%
            </span>
          </div>
          <div class="progress-track">
            <div class="progress-fill"
                 [style.width.%]="pctRecouvrement()"
                 [style.background]="pctRecouvrement() >= 80 ? '#10b981' :
                                     pctRecouvrement() >= 50 ? '#f59e0b' : '#ef4444'">
            </div>
          </div>
        </div>

        <!-- Historique paiements -->
        <div class="table-card">
          <p-table [value]="eleveDetail()!.paiements" styleClass="p-datatable-sm">
            <ng-template pTemplate="header">
              <tr>
                <th>N° Pièce</th><th>Date</th>
                <th class="text-right">Inscription</th>
                <th class="text-right">Mensualité</th>
                <th class="text-right">Uniforme</th>
                <th class="text-right">Fournitures</th>
                <th class="text-right">Cantine</th>
                <th class="text-right">Total</th>
                <th class="text-right">Cumul</th>
                <th>Mode</th>
              </tr>
            </ng-template>
            <ng-template pTemplate="body" let-p>
              <tr>
                <td class="mono">{{ p.no_piece }}</td>
                <td>{{ p.date | date:'dd/MM/yyyy' }}</td>
                <td class="mono text-right">{{ p.inscription | number:'1.0-0' }}</td>
                <td class="mono text-right">{{ p.mensualite  | number:'1.0-0' }}</td>
                <td class="mono text-right">{{ p.uniforme    | number:'1.0-0' }}</td>
                <td class="mono text-right">{{ p.fournitures | number:'1.0-0' }}</td>
                <td class="mono text-right">{{ p.cantine     | number:'1.0-0' }}</td>
                <td class="mono text-right teal bold">{{ p.total | number:'1.0-0' }}</td>
                <td class="mono text-right" style="color:#a855f7">
                  {{ p.cumul | number:'1.0-0' }}
                </td>
                <td><p-tag [value]="p.mode" severity="info" /></td>
              </tr>
            </ng-template>
            <ng-template pTemplate="emptymessage">
              <tr><td colspan="10" class="empty-msg">Aucun paiement pour cet élève</td></tr>
            </ng-template>
          </p-table>
        </div>
      </ng-container>

      <div class="empty-state" *ngIf="!eleveDetail()">
        <div style="font-size:40px">👤</div>
        <div style="color:#64748b;margin-top:12px">
          Recherchez un élève pour voir son historique
        </div>
      </div>

    </ng-container>
  `,
  styles: [`
    .page-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:16px; }
    .page-title  { font-size:20px; font-weight:600; color:#e8f0fe; margin:0 0 4px; }
    .page-sub    { font-size:12px; color:#64748b; }

    .tabs-bar { display:flex; gap:4px; margin-bottom:20px; background:#111827; border:1px solid #2a3f5f; border-radius:10px; padding:4px; }
    .tab-btn { flex:1; padding:8px 12px; border:none; border-radius:7px; background:transparent; color:#64748b; font-size:13px; cursor:pointer; transition:all 0.15s; font-family:inherit; }
    .tab-btn:hover  { background:#1a2235; color:#e8f0fe; }
    .tab-btn.active { background:#1e2d45; color:#00d4aa; font-weight:600; border:1px solid #2a3f5f; }

    .kpi-row { display:flex; gap:12px; margin-bottom:20px; }
    .kpi-mini { flex:1; background:#1e2d45; border:1px solid #2a3f5f; border-radius:10px; padding:14px; text-align:center; }
    .km-label { font-size:10px; color:#64748b; text-transform:uppercase; letter-spacing:1px; margin-bottom:4px; }
    .km-val   { font-size:20px; font-weight:700; font-family:monospace; }
    .kpi-mini.teal  .km-val { color:#00d4aa; }
    .kpi-mini.blue  .km-val { color:#0099ff; }
    .kpi-mini.green .km-val { color:#10b981; }
    .kpi-mini.orange .km-val { color:#f59e0b; }

    .bar-section { background:#1e2d45; border:1px solid #2a3f5f; border-radius:12px; padding:16px 20px; margin-bottom:16px; }
    .bs-title    { font-size:12px; color:#64748b; margin-bottom:14px; }
    .bars-wrap   { display:flex; gap:8px; align-items:flex-end; height:120px; }
    .bar-item    { flex:1; display:flex; flex-direction:column; align-items:center; gap:4px; height:100%; justify-content:flex-end; }
    .bar-track   { width:100%; flex:1; display:flex; align-items:flex-end; }
    .bar-fill    { width:100%; background:linear-gradient(to top,#00d4aa,#0099ff); border-radius:4px 4px 0 0; min-height:4px; transition:height 0.6s ease; }
    .bar-label   { font-size:10px; color:#64748b; }
    .bar-val     { font-size:9px; color:#94a3b8; font-family:monospace; display:none; }

    .table-card { background:#1e2d45; border:1px solid #2a3f5f; border-radius:12px; overflow:hidden; margin-bottom:16px; }

    ::ng-deep .p-datatable .p-datatable-thead > tr > th { background:#111827 !important; color:#64748b !important; font-size:11px !important; text-transform:uppercase !important; border-color:#2a3f5f !important; }
    ::ng-deep .p-datatable .p-datatable-tbody > tr { background:#1e2d45 !important; color:#94a3b8 !important; border-bottom:1px solid rgba(42,63,95,0.4) !important; }
    ::ng-deep .p-datatable .p-datatable-tbody > tr:hover { background:#1a2235 !important; }
    ::ng-deep .p-datatable .p-datatable-tfoot > tr { background:#111827 !important; }

    .search-zone { margin-bottom:20px; }

    .eleve-card { display:flex; align-items:center; gap:20px; background:#1e2d45; border:1px solid #2a3f5f; border-radius:12px; padding:18px 20px; margin-bottom:14px; }
    .ec-avatar  { width:52px; height:52px; border-radius:12px; background:linear-gradient(135deg,#00d4aa,#0099ff); display:flex; align-items:center; justify-content:center; font-size:18px; font-weight:700; color:#000; flex-shrink:0; }
    .ec-info    { flex:1; }
    .ec-nom     { font-size:16px; font-weight:700; color:#e8f0fe; }
    .ec-section { font-size:12px; color:#64748b; margin-top:2px; }
    .ec-stats   { display:flex; gap:20px; }
    .ecs        { text-align:center; }
    .ecs-label  { font-size:10px; color:#64748b; text-transform:uppercase; }
    .ecs-val    { font-size:14px; font-weight:700; font-family:monospace; color:#e8f0fe; margin-top:2px; }

    .progress-card { background:#1e2d45; border:1px solid #2a3f5f; border-radius:10px; padding:14px 18px; margin-bottom:14px; }
    .pc-header { display:flex; justify-content:space-between; font-size:12px; margin-bottom:8px; color:#94a3b8; }
    .progress-track { height:8px; background:#0b0f1a; border-radius:4px; overflow:hidden; }
    .progress-fill  { height:100%; border-radius:4px; transition:width 0.6s ease; }

    .text-right { text-align:right; }
    .mono  { font-family:monospace; font-size:12px; }
    .bold  { font-weight:600; color:#e8f0fe; }
    .teal  { color:#00d4aa; }
    .empty-msg   { text-align:center; padding:40px; color:#64748b; }
    .empty-state { text-align:center; padding:60px; }
    .w-full { width:100%; }
  `]
})
export class SuiviMensuelComponent implements OnInit {
  onglet       = signal('global');
  globalData   = signal<any[]>([]);
  eleveDetail  = signal<any>(null);
  suggestions  = signal<Eleve[]>([]);
  loading      = signal(true);
  eleveSelectionne: any = null;

  constructor(
    private api: ApiService,
    private elevesService: ElevesService
  ) {}

  ngOnInit() {
    this.chargerGlobal();
  }

  chargerGlobal() {
    this.loading.set(true);
    this.api.get<any>('/eleves/suivi-mensuel/').subscribe({
      next: res => {
        this.globalData.set(res.global || []);
        this.loading.set(false);
      },
      error: () => this.loading.set(false)
    });
  }

  chercher(event: any) {
    this.elevesService.getEleves({ search: event.query }).subscribe({
      next: res => this.suggestions.set(res.results || [])
    });
  }

  chargerSuiviEleve(eleve: Eleve) {
    this.api.get<any>(`/eleves/suivi-mensuel/?eleve_id=${eleve.id}`).subscribe({
      next: res => this.eleveDetail.set(res.eleve)
    });
  }

  totalGlobal(): number {
    return this.globalData().reduce((s, m) => s + m.total, 0);
  }

  nbTransactions(): number {
    return this.globalData().reduce((s, m) => s + m.nb, 0);
  }

  maxMensuel(): number {
    return Math.max(...this.globalData().map(m => m.total), 1);
  }

  pctRecouvrement(): number {
    if (!this.eleveDetail() || !this.eleveDetail()!.attendu) return 0;
    return Math.min((this.eleveDetail()!.total_paye / this.eleveDetail()!.attendu) * 100, 100);
  }
}
