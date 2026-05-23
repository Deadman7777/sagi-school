import { Component, OnInit, signal, ChangeDetectionStrategy } from '@angular/core';
import { DashboardService, DashboardKPI, DashboardSuperAdmin, TresorerieCanaux } from '../../core/services/dashboard.service';
import { AuthService } from '../../core/services/auth.service';
import { TagModule } from 'primeng/tag';
import { TableModule } from 'primeng/table';
import { SkeletonModule } from 'primeng/skeleton';
import { TranslateModule } from '@ngx-translate/core';
import { DecimalPipe, DatePipe } from '@angular/common';

@Component({
  selector: 'app-dashboard',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [TagModule, TranslateModule, TableModule, SkeletonModule, DecimalPipe, DatePipe],
  template: `
    <!-- ══ VUE SUPER ADMIN ══ -->
    @if (isSuperAdmin()) {
      <div class="page-header">
        <div>
          <h2 class="page-title">👑 {{ 'dashboard.vue_globale' | translate }}</h2>
          <span class="page-sub">{{ 'dashboard.admin_dashboard' | translate }}</span>
        </div>
      </div>

      @if (saData(); as sa) {
        <div class="kpi-grid">
          <div class="kpi-card" style="--acc:#00d4aa">
            <div class="kpi-icon">🏫</div>
            <div class="kpi-label">{{ 'dashboard.ecoles_actives' | translate }}</div>
            <div class="kpi-value" style="color:#00d4aa">{{ sa.ecoles.actives }}</div>
            <div class="kpi-sub">{{ 'dashboard.sur_total' | translate:{ val: sa.ecoles.total } }}</div>
          </div>
          <div class="kpi-card" style="--acc:#f59e0b">
            <div class="kpi-icon">⏳</div>
            <div class="kpi-label">{{ 'dashboard.en_essai' | translate }}</div>
            <div class="kpi-value" style="color:#f59e0b">{{ sa.ecoles.essai }}</div>
            <div class="kpi-sub">{{ 'dashboard.a_convertir' | translate }}</div>
          </div>
          <div class="kpi-card" style="--acc:#ef4444">
            <div class="kpi-icon">❌</div>
            <div class="kpi-label">{{ 'dashboard.expirees' | translate }}</div>
            <div class="kpi-value" style="color:#ef4444">{{ sa.ecoles.expirees }}</div>
            <div class="kpi-sub">{{ 'dashboard.a_relancer' | translate }}</div>
          </div>
          <div class="kpi-card" style="--acc:#a855f7">
            <div class="kpi-icon">💵</div>
            <div class="kpi-label">{{ 'dashboard.revenus_an' | translate }}</div>
            <div class="kpi-value" style="color:#a855f7">
              {{ sa.finances.revenus_annuels | number:'1.0-0' }}
            </div>
            <div class="kpi-sub">{{ 'dashboard.fcfa_estimes' | translate }}</div>
          </div>
        </div>

        <div class="info-banner">
          🆕 <strong>{{ sa.ecoles.nouvelles_ce_mois }}</strong>
          {{ 'dashboard.nouvelles_ecoles' | translate }} ·
          {{ 'dashboard.revenu_mensuel' | translate }} :
          <strong>{{ sa.finances.revenus_mensuels | number:'1.0-0' }} FCFA</strong>
        </div>

        @if (sa.alertes_expiration.length > 0) {
          <div class="card">
            <div class="card-header">⚠️ {{ 'dashboard.licences_expirant' | translate }}</div>
            <p-table [value]="sa.alertes_expiration" styleClass="p-datatable-sm">
              <ng-template pTemplate="header">
                <tr>
                  <th>{{ 'dashboard.ecole_col'         | translate }}</th>
                  <th>{{ 'dashboard.type_col'           | translate }}</th>
                  <th>{{ 'dashboard.jours_restants_col' | translate }}</th>
                  <th>{{ 'dashboard.date_fin_col'       | translate }}</th>
                </tr>
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
        } @else {
          <div class="empty-sa">
            <div style="font-size:32px">✅</div>
            <div style="color:#10b981;margin-top:8px;font-weight:600">{{ 'dashboard.aucune_danger' | translate }}</div>
            <div style="color:#64748b;font-size:12px">{{ 'dashboard.toutes_regle' | translate }}</div>
          </div>
        }
      } @else {
        <div class="kpi-grid">
          @for (i of [1,2,3,4]; track i) {
            <div class="kpi-card"><p-skeleton height="80px" /></div>
          }
        </div>
      }
    }

    <!-- ══ VUE ÉCOLE ══ -->
    @if (!isSuperAdmin()) {
      @if (data(); as d) {
        <div class="kpi-grid">
          @if (d.exercice) {
            <div class="exercice-bar" style="grid-column:1/-1">
              📅 Exercice {{ d.exercice.annee_scolaire }} —
              du {{ d.exercice.date_debut | date:'dd/MM/yyyy' }}
              au {{ d.exercice.date_fin   | date:'dd/MM/yyyy' }}
            </div>
          }
          <div class="kpi-card" style="--acc:#00d4aa">
            <div class="kpi-icon">💰</div>
            <div class="kpi-label">{{ 'dashboard.total_recettes' | translate }}</div>
            <div class="kpi-value" style="color:#00d4aa">{{ d.kpis.total_recettes | number:'1.0-0' }}</div>
            <div class="kpi-sub">FCFA</div>
          </div>
          <div class="kpi-card" style="--acc:#0099ff">
            <div class="kpi-icon">💸</div>
            <div class="kpi-label">{{ 'dashboard.total_charges' | translate }}</div>
            <div class="kpi-value" style="color:#0099ff">{{ d.kpis.total_charges | number:'1.0-0' }}</div>
            <div class="kpi-sub">FCFA</div>
          </div>
          <div class="kpi-card" style="--acc:#10b981">
            <div class="kpi-icon">📈</div>
            <div class="kpi-label">{{ 'dashboard.resultat_net' | translate }}</div>
            <div class="kpi-value" [style.color]="d.kpis.resultat_net >= 0 ? '#10b981' : '#ef4444'">
              {{ d.kpis.resultat_net | number:'1.0-0' }}
            </div>
            <div class="kpi-sub">{{ d.kpis.resultat_net >= 0 ? '✅ Bénéfice' : '🔴 Déficit' }}</div>
          </div>
          <div class="kpi-card" style="--acc:#f59e0b">
            <div class="kpi-icon">🏦</div>
            <div class="kpi-label">{{ 'dashboard.tresorerie' | translate }}</div>
            <div class="kpi-value" style="color:#f59e0b">{{ d.kpis.tresorerie | number:'1.0-0' }}</div>
            <div class="kpi-sub">FCFA</div>
          </div>
          <div class="kpi-card" style="--acc:#10b981">
            <div class="kpi-icon">📊</div>
            <div class="kpi-label">{{ 'dashboard.taux_recouvrement' | translate }}</div>
            <div class="kpi-value" style="color:#10b981">{{ d.kpis.taux_recouvrement || 0 }}%</div>
            <div class="kpi-sub">{{ 'dashboard.des_frais' | translate }}</div>
          </div>
          <div class="kpi-card" style="--acc:#ef4444">
            <div class="kpi-icon">⚠️</div>
            <div class="kpi-label">{{ 'dashboard.total_impayes' | translate }}</div>
            <div class="kpi-value" style="color:#ef4444">{{ d.kpis.total_impayes | number:'1.0-0' }} FCFA</div>
            <div class="kpi-sub">{{ 'dashboard.fcfa_recouvrer' | translate }}</div>
          </div>
          <div class="kpi-card" style="--acc:#a855f7">
            <div class="kpi-icon">🎯</div>
            <div class="kpi-label">{{ 'dashboard.total_attendu_dash' | translate }}</div>
            <div class="kpi-value" style="color:#a855f7">{{ d.kpis.total_attendu | number:'1.0-0' }} FCFA</div>
            <div class="kpi-sub">{{ 'dashboard.frais_annuels' | translate }}</div>
          </div>
          <!-- Effectif -->
          <div class="kpi-card" style="--acc:#00d4aa">
            <div class="kpi-icon">🎓</div>
            <div class="kpi-label">Effectif Total</div>
            <div class="kpi-value" style="color:#00d4aa">{{ d.eleves.total }}</div>
            <div class="kpi-sub">
              <span style="color:#7c3aed">{{ d.eleves.garcons || 0 }}G</span> /
              <span style="color:#ec4899">{{ d.eleves.filles || 0 }}F</span>
            </div>
          </div>
          <div class="kpi-card" style="--acc:#ef4444">
            <div class="kpi-icon">🚪</div>
            <div class="kpi-label">Abandons</div>
            <div class="kpi-value" style="color:#ef4444">{{ d.eleves.abandonnes || 0 }}</div>
            <div class="kpi-sub">sur {{ d.eleves.total }} élèves</div>
          </div>
          <div class="kpi-card" style="--acc:#f59e0b">
            <div class="kpi-icon">🤝</div>
            <div class="kpi-label">Prises en charge</div>
            <div class="kpi-value" style="color:#f59e0b">{{ d.prises_en_charge?.total || 0 }}</div>
            <div class="kpi-sub">bénéficiaires</div>
          </div>
        </div>

        <div class="grid-2">
          <div class="card">
            <div class="card-header">🚨 {{ 'dashboard.alertes' | translate }}</div>
            <div class="card-body">
              <div class="alert-row urgent">
                <div class="alert-num">{{ d.eleves.urgent }}</div>
                <div><div class="alert-title">{{ 'dashboard.urgent' | translate }}</div><div class="alert-sub">Retard &gt; 60 jours</div></div>
              </div>
              <div class="alert-row attention">
                <div class="alert-num">{{ d.eleves.attention }}</div>
                <div><div class="alert-title">{{ 'dashboard.attention' | translate }}</div><div class="alert-sub">Retard &gt; 30 jours</div></div>
              </div>
              <div class="alert-row ok">
                <div class="alert-num">{{ d.eleves.ok }}</div>
                <div><div class="alert-title">{{ 'dashboard.a_jour' | translate }}</div><div class="alert-sub">{{ 'dashboard.paiements_ok' | translate }}</div></div>
              </div>
              <div class="total-eleves">
                Inscrits : <strong>{{ d.eleves.inscrits || d.eleves.total }}</strong> ·
                Abandons : <strong style="color:#ef4444">{{ d.eleves.abandonnes || 0 }}</strong> ·
                Transférés : <strong style="color:#f59e0b">{{ d.eleves.transferes || 0 }}</strong>
              </div>
            </div>
          </div>
          @if (d.prises_en_charge?.categories?.length) {
            <div class="card">
              <div class="card-header">🤝 Prises en charge</div>
              <div class="card-body">
                @for (cat of d.prises_en_charge!.categories; track cat.categorie) {
                  <div class="mode-row">
                    <div class="mode-info">
                      <span class="mode-name">{{ pecLabel(cat.categorie) }}</span>
                    </div>
                    <span class="mode-total">{{ cat.nb }} élève(s)</span>
                  </div>
                }
                <div class="total-eleves">Total : <strong>{{ d.prises_en_charge!.total }}</strong> bénéficiaires</div>
              </div>
            </div>
          }
          <div class="card">
            <div class="card-header">🏦 Trésorerie par canal</div>
            @if (tresoCanaux(); as tc) {
              <div class="card-body" style="padding:0">
                <table style="width:100%;border-collapse:collapse;font-size:11px">
                  <thead>
                    <tr style="background:#111827">
                      <th style="padding:6px 12px;color:#64748b;text-align:left;font-weight:500">Canal</th>
                      <th style="padding:6px 8px;color:#64748b;text-align:right">Encaissements</th>
                      <th style="padding:6px 8px;color:#64748b;text-align:right">Décaissements</th>
                      <th style="padding:6px 12px;color:#64748b;text-align:right">Solde</th>
                    </tr>
                  </thead>
                  <tbody>
                    @for (c of tc.canaux; track c.canal) {
                      <tr style="border-bottom:1px solid rgba(42,63,95,0.4)">
                        <td style="padding:8px 12px">
                          <span style="margin-right:6px">{{ canalIcon(c.canal) }}</span>
                          <span style="color:#e8f0fe;font-weight:500">{{ c.libelle }}</span>
                          @if (c.nb > 0) {
                            <span style="color:#64748b;font-size:10px;margin-left:6px">{{ c.nb }} op.</span>
                          }
                          @if (c.solde_initial > 0) {
                            <div style="color:#64748b;font-size:10px;margin-top:2px">
                              Init : {{ c.solde_initial | number:'1.0-0' }}
                            </div>
                          }
                        </td>
                        <td style="padding:8px;text-align:right;color:#10b981;font-family:monospace">
                          {{ c.encaissements | number:'1.0-0' }}
                        </td>
                        <td style="padding:8px;text-align:right;color:#ef4444;font-family:monospace">
                          {{ c.decaissements > 0 ? (c.decaissements | number:'1.0-0') : '—' }}
                        </td>
                        <td style="padding:8px 12px;text-align:right;font-family:monospace;font-weight:700"
                            [style.color]="c.solde >= 0 ? '#00d4aa' : '#ef4444'">
                          {{ c.solde | number:'1.0-0' }}
                        </td>
                      </tr>
                    }
                  </tbody>
                  <tfoot>
                    <tr style="background:#111827;border-top:2px solid #2a3f5f">
                      <td style="padding:8px 12px;color:#94a3b8;font-weight:600;font-size:11px">TOTAL</td>
                      <td style="padding:8px;text-align:right;color:#10b981;font-family:monospace;font-weight:700">
                        {{ tc.totaux.encaissements | number:'1.0-0' }}
                      </td>
                      <td style="padding:8px;text-align:right;color:#ef4444;font-family:monospace;font-weight:700">
                        {{ tc.totaux.decaissements | number:'1.0-0' }}
                      </td>
                      <td style="padding:8px 12px;text-align:right;font-family:monospace;font-weight:700;font-size:13px"
                          [style.color]="tc.totaux.solde >= 0 ? '#00d4aa' : '#ef4444'">
                        {{ tc.totaux.solde | number:'1.0-0' }}
                      </td>
                    </tr>
                  </tfoot>
                </table>
                <div style="padding:8px 12px;font-size:10px;color:#64748b;border-top:1px solid #2a3f5f">
                  Solde initial global : <strong style="color:#94a3b8">{{ tc.totaux.solde_initial | number:'1.0-0' }} FCFA</strong>
                  &nbsp;·&nbsp; Exercice {{ tc.exercice }}
                </div>
              </div>
            } @else {
              <div class="card-body">
                <div class="empty-msg" style="padding:20px;text-align:center;color:#64748b;font-size:12px">
                  Chargement...
                </div>
              </div>
            }
          </div>
        </div>

        @if (auditLog().length > 0) {
          <div class="card" style="margin-bottom:16px">
            <div class="card-header">🔍 Journal d'audit (100 dernières actions)</div>
            <p-table [value]="auditLog()" styleClass="p-datatable-sm" [rows]="10" [paginator]="true">
              <ng-template pTemplate="header">
                <tr>
                  <th style="width:140px">Date</th>
                  <th style="width:100px">Action</th>
                  <th style="width:130px">Module</th>
                  <th style="width:140px">Utilisateur</th>
                  <th>Détail</th>
                </tr>
              </ng-template>
              <ng-template pTemplate="body" let-e>
                <tr>
                  <td class="mono" style="font-size:11px">{{ e.created_at | date:'dd/MM/yy HH:mm' }}</td>
                  <td>
                    <p-tag [value]="e.action"
                           [severity]="e.action === 'DELETE' || e.action === 'ANNULER' ? 'danger' : e.action === 'VALIDATE' ? 'success' : 'info'"
                           [style]="{'font-size':'10px'}" />
                  </td>
                  <td style="font-size:11px; color:#94a3b8">{{ e.modele }}</td>
                  <td style="font-size:11px">{{ e.utilisateur }}</td>
                  <td style="font-size:11px; color:#64748b">{{ e.description }}</td>
                </tr>
              </ng-template>
            </p-table>
          </div>
        }

        @if (alertes().length > 0) {
          <div class="card">
            <div class="card-header">📋 {{ 'dashboard.relancer' | translate }}</div>
            <p-table [value]="alertes()" styleClass="p-datatable-sm" [rows]="10" [paginator]="true">
              <ng-template pTemplate="header">
                <tr>
                  <th>{{ 'dashboard.nom_col'     | translate }}</th>
                  <th>{{ 'dashboard.section_col' | translate }}</th>
                  <th>{{ 'dashboard.reste_col'   | translate }}</th>
                  <th>{{ 'dashboard.retard_60'   | translate }}</th>
                  <th>{{ 'dashboard.alerte_col'  | translate }}</th>
                  <th>{{ 'dashboard.tel_col'     | translate }}</th>
                </tr>
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
        }
      } @else {
        <div class="kpi-grid">
          @for (i of [1,2,3,4]; track i) {
            <div class="kpi-card">
              <p-skeleton height="20px" styleClass="mb-2" />
              <p-skeleton height="40px" styleClass="mb-2" />
              <p-skeleton height="14px" width="60%" />
            </div>
          }
        </div>
      }
    }
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
  data             = signal<DashboardKPI | null>(null);
  saData           = signal<DashboardSuperAdmin | null>(null);
  alertes          = signal<any[]>([]);
  tresoCanaux      = signal<TresorerieCanaux | null>(null);
  auditLog         = signal<any[]>([]);

  constructor(
    private dashService: DashboardService,
    public auth: AuthService
  ) {}

  isSuperAdmin() { return this.auth.currentUser()?.role === 'SUPER_ADMIN'; }

  pecLabel(cat: string) {
    return { ORPHELIN: 'Orphelin', HANDICAP: 'Handicap', FAMILLE_DEMUNIE: 'Famille démunie', AUTRE: 'Autre' }[cat] || cat;
  }

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
      this.dashService.getTresorerieCanaux().subscribe({
        next:  res => this.tresoCanaux.set(res),
        error: () => {}
      });
      this.dashService.getAuditLog().subscribe({
        next:  res => this.auditLog.set(res),
        error: () => {}
      });
    }
  }

  canalIcon(canal: string): string {
    const icons: Record<string, string> = {
      ESPECE: '💵', WAVE: '📱', ORANGE_MONEY: '🟠',
      FREE_MONEY: '🔴', VIREMENT: '🏦', CHEQUE: '📝',
    };
    return icons[canal] ?? '💰';
  }
}
