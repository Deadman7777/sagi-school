import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DashboardService, DashboardKPI, DashboardSuperAdmin } from '../../core/services/dashboard.service';
import { AuthService } from '../../core/services/auth.service';
import { TagModule } from 'primeng/tag';
// import { TranslateModule } from '@ngx-translate/core';
import { TableModule } from 'primeng/table';
import { SkeletonModule } from 'primeng/skeleton';
import { TranslateModule } from '@ngx-translate/core';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, TagModule, TranslateModule, TableModule, SkeletonModule, TranslateModule],
  template: `
    <!-- ══ VUE SUPER ADMIN ══ -->
    <ng-container *ngIf="isSuperAdmin()">
      <div class="page-header">
        <div>
          <h2 class="page-title">👑 Vue Globale — HADY GESMAN</h2>
          <span class="page-sub">Tableau de bord administrateur</span>
        </div>
      </div>

      <div class="kpi-grid" *ngIf="saData(); else skelSA">
        <div class="kpi-card" style="--acc:#00d4aa">
          <div class="kpi-icon">🏫</div>
          <div class="kpi-label">Écoles Actives</div>
          <div class="kpi-value" style="color:#00d4aa">{{ saData()!.ecoles.actives }}</div>
          <div class="kpi-sub">sur {{ saData()!.ecoles.total }} total</div>
        </div>
        <div class="kpi-card" style="--acc:#f59e0b">
          <div class="kpi-icon">⏳</div>
          <div class="kpi-label">En Essai</div>
          <div class="kpi-value" style="color:#f59e0b">{{ saData()!.ecoles.essai }}</div>
          <div class="kpi-sub">à convertir</div>
        </div>
        <div class="kpi-card" style="--acc:#ef4444">
          <div class="kpi-icon">❌</div>
          <div class="kpi-label">Expirées</div>
          <div class="kpi-value" style="color:#ef4444">{{ saData()!.ecoles.expirees }}</div>
          <div class="kpi-sub">à relancer</div>
        </div>
        <div class="kpi-card" style="--acc:#a855f7">
          <div class="kpi-icon">💵</div>
          <div class="kpi-label">Revenus / An</div>
          <div class="kpi-value" style="color:#a855f7">
            {{ saData()!.finances.revenus_annuels | number:'1.0-0' }}
          </div>
          <div class="kpi-sub">FCFA estimés</div>
        </div>
      </div>

      <ng-template #skelSA>
        <div class="kpi-grid">
          <div class="kpi-card" *ngFor="let i of [1,2,3,4]">
            <p-skeleton height="80px" />
          </div>
        </div>
      </ng-template>

      <!-- Nouvelles ce mois -->
      <div class="info-banner" *ngIf="saData()">
        🆕 <strong>{{ saData()!.ecoles.nouvelles_ce_mois }}</strong>
        nouvelle(s) école(s) ce mois ·
        Revenu mensuel estimé :
        <strong>{{ saData()!.finances.revenus_mensuels | number:'1.0-0' }} FCFA</strong>
      </div>

      <!-- Alertes expiration -->
      <ng-container *ngIf="saData() as data"> 
        <div class="card" *ngIf="data.alertes_expiration.length > 0">
          <div class="card-header">⚠️ Licences expirant dans 30 jours</div>
          <p-table [value]="data.alertes_expiration" styleClass="p-datatable-sm">
            <ng-template pTemplate="header">
              <tr><th>École</th><th>Type</th><th>Jours Restants</th><th>Date Fin</th></tr>
            </ng-template>
            <ng-template pTemplate="body" let-a>
              <tr>
                <td class="bold">{{ a.ecole }}</td>
                <td><p-tag [value]="a.type" severity="info" /></td>
                <td class="mono" [style.color]="a.jours_restants <= 7 ? '#ef4444' : '#f59e0b'">
                  {{ a.jours_restants }}j
                </td>
                <td class="mono">{{ a.date_fin }}</td>
              </tr>
            </ng-template>
          </p-table>
        </div>

        <div class="empty-sa" *ngIf="data.alertes_expiration.length === 0">
          <div style="font-size:32px">✅</div>
          <div style="color:#10b981;margin-top:8px;font-weight:600">Aucune licence en danger</div>
          <div style="color:#64748b;font-size:12px">Toutes les licences actives sont en règle</div>
        </div>
      </ng-container>

    </ng-container>

    <!-- ══ VUE ÉCOLE ══ -->
    <ng-container *ngIf="!isSuperAdmin()">
      <div class="kpi-grid" *ngIf="data(); else skelEcole">
        <div class="exercice-bar" style="grid-column:1/-1" *ngIf="data()!.exercice">
          📅 Exercice {{ data()!.exercice!.annee_scolaire }} —
          du {{ data()!.exercice!.date_debut | date:'dd/MM/yyyy' }}
          au {{ data()!.exercice!.date_fin   | date:'dd/MM/yyyy' }}
        </div>
        <div class="kpi-card" style="--acc:#00d4aa">
          <div class="kpi-icon">💰</div>
          <div class="kpi-label">{{ 'dashboard.total_recettes' | translate }}</div>
          <div class="kpi-value" style="color:#00d4aa">{{ data()!.kpis.total_recettes | number:'1.0-0' }}</div>
          <div class="kpi-sub">FCFA</div>
        </div>
        <div class="kpi-card" style="--acc:#0099ff">
          <div class="kpi-icon">💸</div>
          <div class="kpi-label">{{ 'dashboard.total_charges' | translate }}</div>
          <div class="kpi-value" style="color:#0099ff">{{ data()!.kpis.total_charges | number:'1.0-0' }}</div>
          <div class="kpi-sub">FCFA</div>
        </div>
        <div class="kpi-card" style="--acc:#10b981">
          <div class="kpi-icon">📈</div>
          <div class="kpi-label">{{ 'dashboard.resultat_net' | translate }}</div>
          <div class="kpi-value" [style.color]="data()!.kpis.resultat_net >= 0 ? '#10b981' : '#ef4444'">
            {{ data()!.kpis.resultat_net | number:'1.0-0' }}
          </div>
          <div class="kpi-sub">{{ data()!.kpis.resultat_net >= 0 ? '✅ Bénéfice' : '🔴 Déficit' }}</div>
        </div>
        <div class="kpi-card" style="--acc:#f59e0b">
          <div class="kpi-icon">🏦</div>
          <div class="kpi-label">{{ 'dashboard.tresorerie' | translate }}</div>
          <div class="kpi-value" style="color:#f59e0b">{{ data()!.kpis.tresorerie | number:'1.0-0' }}</div>
          <div class="kpi-sub">FCFA</div>
        </div>
      </div>

      <ng-template #skelEcole>
        <div class="kpi-grid">
          <div class="kpi-card" *ngFor="let i of [1,2,3,4]">
            <p-skeleton height="20px" styleClass="mb-2" />
            <p-skeleton height="40px" styleClass="mb-2" />
            <p-skeleton height="14px" width="60%" />
          </div>
        </div>
      </ng-template>

      <div class="grid-2" *ngIf="data()">
        <div class="card">
          <div class="card-header">🚨 {{ 'dashboard.alertes' | translate }}</div>
          <div class="card-body">
            <div class="alert-row urgent">
              <div class="alert-num">{{ data()!.eleves.urgent }}</div>
              <div><div class="alert-title">{{ 'dashboard.urgent' | translate }}</div><div class="alert-sub">Retard &gt; 60 jours</div></div>
            </div>
            <div class="alert-row attention">
              <div class="alert-num">{{ data()!.eleves.attention }}</div>
              <div><div class="alert-title">{{ 'dashboard.attention' | translate }}</div><div class="alert-sub">Retard &gt; 30 jours</div></div>
            </div>
            <div class="alert-row ok">
              <div class="alert-num">{{ data()!.eleves.ok }}</div>
              <div><div class="alert-title">{{ 'dashboard.a_jour' | translate }}</div><div class="alert-sub">Paiements OK</div></div>
            </div>
            <div class="total-eleves">Total : <strong>{{ data()!.eleves.total }}</strong> élèves</div>
          </div>
        </div>
        <div class="card">
          <div class="card-header">📱 {{ 'dashboard.modes' | translate }}</div>
          <div class="card-body">
            <div class="mode-row" *ngFor="let m of data()!.modes_paiement">
              <div class="mode-info">
                <span class="mode-name">{{ m.mode_paiement }}</span>
                <span class="mode-nb">{{ m.nb }} opérations</span>
              </div>
              <span class="mode-total">{{ m.total | number:'1.0-0' }} FCFA</span>
            </div>
          </div>
        </div>
      </div>

      <div class="card" *ngIf="alertes().length > 0">
        <div class="card-header">📋 Élèves à Relancer</div>
        <p-table [value]="alertes()" styleClass="p-datatable-sm" [rows]="10" [paginator]="true">
          <ng-template pTemplate="header">
            <tr><th>Nom</th><th>Section</th><th>Reste</th><th>Retard</th><th>Alerte</th><th>Tél</th></tr>
          </ng-template>
          <ng-template pTemplate="body" let-e>
            <tr>
              <td class="bold">{{ e.nom_complet }}</td>
              <td>{{ e.section }}</td>
              <td class="mono danger">{{ e.reste_a_payer | number:'1.0-0' }} FCFA</td>
              <td class="mono">{{ e.jours_retard }}j</td>
              <td><p-tag [value]="e.niveau_alerte" [severity]="e.niveau_alerte === 'URGENT' ? 'danger' : 'warn'" /></td>
              <td class="mono">{{ e.telephone }}</td>
            </tr>
          </ng-template>
        </p-table>
      </div>
    </ng-container>
  `,
  styles: [`
    .page-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:20px; }
    .page-title  { font-size:20px; font-weight:600; color:#e8f0fe; margin:0 0 4px; }
    .page-sub    { font-size:12px; color:#64748b; }

    .kpi-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:20px; }
    .exercice-bar { background:rgba(0,153,255,0.1); border:1px solid rgba(0,153,255,0.2); border-radius:8px; padding:8px 16px; font-size:12px; color:#0099ff; }
    .kpi-card { background:#1e2d45; border:1px solid #2a3f5f; border-top:2px solid var(--acc,#00d4aa); border-radius:12px; padding:18px 20px; position:relative; animation:fadeIn 0.3s ease; }
    @keyframes fadeIn { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:none} }
    .kpi-icon  { position:absolute; top:14px; right:14px; font-size:22px; opacity:.2; }
    .kpi-label { font-size:11px; color:#64748b; text-transform:uppercase; letter-spacing:1px; margin-bottom:6px; }
    .kpi-value { font-size:26px; font-weight:700; font-family:monospace; }
    .kpi-sub   { font-size:11px; color:#64748b; margin-top:4px; }

    .info-banner { background:rgba(0,212,170,0.08); border:1px solid rgba(0,212,170,0.2); border-radius:8px; padding:10px 16px; font-size:13px; color:#94a3b8; margin-bottom:16px; }
    .info-banner strong { color:#00d4aa; }

    .empty-sa { text-align:center; padding:40px; }

    .grid-2 { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:16px; }
    .card { background:#1e2d45; border:1px solid #2a3f5f; border-radius:12px; overflow:hidden; margin-bottom:16px; }
    .card-header { padding:12px 18px; border-bottom:1px solid #2a3f5f; font-size:13px; font-weight:600; color:#e8f0fe; }
    .card-body   { padding:16px 18px; }

    .alert-row { display:flex; align-items:center; gap:16px; padding:10px 0; border-bottom:1px solid rgba(42,63,95,0.4); }
    .alert-num  { font-size:32px; font-weight:700; font-family:monospace; min-width:48px; }
    .alert-title { font-size:13px; font-weight:600; }
    .alert-sub   { font-size:11px; color:#64748b; }
    .urgent   .alert-num { color:#ef4444; }
    .attention .alert-num { color:#f59e0b; }
    .ok        .alert-num { color:#10b981; }
    .total-eleves { font-size:12px; color:#64748b; margin-top:12px; padding-top:8px; border-top:1px solid #2a3f5f; }

    .mode-row   { display:flex; justify-content:space-between; align-items:center; padding:8px 0; border-bottom:1px solid rgba(42,63,95,0.3); }
    .mode-info  { display:flex; flex-direction:column; gap:2px; }
    .mode-name  { font-size:13px; font-weight:500; color:#e8f0fe; }
    .mode-nb    { font-size:11px; color:#64748b; }
    .mode-total { font-family:monospace; font-size:13px; color:#00d4aa; }

    .mono   { font-family:monospace; font-size:12px; }
    .bold   { font-weight:600; color:#e8f0fe; }
    .danger { color:#ef4444; }

    ::ng-deep .p-datatable .p-datatable-thead > tr > th { background:#111827 !important; color:#64748b !important; font-size:11px !important; text-transform:uppercase !important; border-color:#2a3f5f !important; }
    ::ng-deep .p-datatable .p-datatable-tbody > tr { background:#1e2d45 !important; color:#94a3b8 !important; border-bottom:1px solid rgba(42,63,95,0.4) !important; }
    ::ng-deep .p-datatable .p-datatable-tbody > tr:hover { background:#1a2235 !important; }
  `]
})
export class DashboardComponent implements OnInit {
  data    = signal<DashboardKPI | null>(null);
  saData  = signal<DashboardSuperAdmin | null>(null);
  alertes = signal<any[]>([]);

  constructor(
    private dashService: DashboardService,
    public auth: AuthService
  ) {}

  isSuperAdmin() { return this.auth.currentUser()?.role === 'SUPER_ADMIN'; }

  ngOnInit() {
    if (this.isSuperAdmin()) {
      this.dashService.getSuperAdmin().subscribe({
        next: res => this.saData.set(res),
        error: err => console.error('SuperAdmin dashboard error', err)
      });
    } else {
      this.dashService.getKPIs().subscribe({
        next: res => this.data.set(res.exercice ? res : null),
        error: err => console.error('KPI error', err)
      });
      this.dashService.getAlertes().subscribe({
        next:  res => this.alertes.set(res),
        error: err => console.error('Alertes error', err)
      });
    }
  }
}
