import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService } from '../../core/services/api.service';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { ButtonModule } from 'primeng/button';

@Component({
  selector: 'app-fiscal',
  standalone: true,
  imports: [CommonModule, TableModule, TagModule, ButtonModule],
  template: `
    <div class="page-header">
      <div>
        <h2 class="page-title">📋 Déclarations Fiscales</h2>
        <span class="page-sub">Retenues à la Source (BRS) — Conformité fiscale sénégalaise</span>
      </div>
      <p-button label="📤 Exporter" severity="secondary" (onClick)="window.print()" />
    </div>

    <!-- Stats BRS -->
    <div class="kpi-grid" *ngIf="stats()">
      <div class="kpi-card" style="--acc:#0099ff">
        <div class="kpi-icon">💼</div>
        <div class="kpi-label">Masse Salariale</div>
        <div class="kpi-value" style="color:#0099ff">
          {{ stats().masse_salariale | number:'1.0-0' }}
        </div>
        <div class="kpi-sub">FCFA</div>
      </div>
      <div class="kpi-card" style="--acc:#f59e0b">
        <div class="kpi-icon">📊</div>
        <div class="kpi-label">BRS Total Dû</div>
        <div class="kpi-value" style="color:#f59e0b">
          {{ stats().brs_total | number:'1.0-0' }}
        </div>
        <div class="kpi-sub">FCFA (5% masse)</div>
      </div>
      <div class="kpi-card" style="--acc:#ef4444">
        <div class="kpi-icon">⚠️</div>
        <div class="kpi-label">En Retard</div>
        <div class="kpi-value" style="color:#ef4444">
          {{ stats().brs_retard | number:'1.0-0' }}
        </div>
        <div class="kpi-sub">FCFA à régulariser</div>
      </div>
      <div class="kpi-card" style="--acc:#10b981">
        <div class="kpi-icon">✅</div>
        <div class="kpi-label">En Règle</div>
        <div class="kpi-value" style="color:#10b981">
          {{ stats().brs_regle | number:'1.0-0' }}
        </div>
        <div class="kpi-sub">FCFA déclarés</div>
      </div>
    </div>

    <!-- Tableau BRS -->
    <div class="card">
      <div class="card-header">📋 Retenues à la Source (BRS) — Taux 5%</div>
      <div class="table-wrap">
        <p-table [value]="declarations()" [loading]="loading()"
                 styleClass="p-datatable-sm">
          <ng-template pTemplate="header">
            <tr>
              <th>Mois</th>
              <th>Masse Salariale</th>
              <th>Taux BRS</th>
              <th>Montant BRS</th>
              <th>Date Limite</th>
              <th>Statut</th>
            </tr>
          </ng-template>
          <ng-template pTemplate="body" let-d>
            <tr>
              <td class="bold">{{ d.mois }}</td>
              <td class="mono">{{ d.masse_salariale | number:'1.0-0' }} FCFA</td>
              <td class="mono">5%</td>
              <td class="mono">{{ d.montant_brs | number:'1.0-0' }} FCFA</td>
              <td class="mono">{{ d.date_limite | date:'dd/MM/yyyy' }}</td>
              <td>
                <p-tag [value]="d.statut"
                       [severity]="d.statut === 'EN_REGLE' ? 'success' :
                                   d.statut === 'EN_RETARD' ? 'danger' : 'warn'" />
              </td>
            </tr>
          </ng-template>
          <ng-template pTemplate="emptymessage">
            <tr>
              <td colspan="6" class="empty-msg">
                Aucune déclaration — ajoutez des charges salariales
              </td>
            </tr>
          </ng-template>
        </p-table>
      </div>
    </div>

    <!-- Info conformité -->
    <div class="info-card">
      <div class="ic-title">ℹ️ Conformité Fiscale Sénégalaise</div>
      <div class="ic-body">
        <div class="ic-row"><span>Régime</span><span>Retenue à la Source (BRS)</span></div>
        <div class="ic-row"><span>Taux applicable</span><span class="mono">5% de la masse salariale</span></div>
        <div class="ic-row"><span>Date de dépôt</span><span>15 du mois suivant</span></div>
        <div class="ic-row"><span>Organisme</span><span>Direction Générale des Impôts (DGI)</span></div>
        <div class="ic-row"><span>Référence</span><span>Code Général des Impôts — Sénégal</span></div>
      </div>
    </div>
  `,
  styles: [`
    .page-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:20px; }
    .page-title  { font-size:20px; font-weight:600; color:#e8f0fe; margin:0 0 4px; }
    .page-sub    { font-size:12px; color:#64748b; }

    .kpi-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:20px; }
    .kpi-card { background:#1e2d45; border:1px solid #2a3f5f; border-top:2px solid var(--acc,#00d4aa); border-radius:12px; padding:18px 20px; position:relative; }
    .kpi-icon  { position:absolute; top:14px; right:14px; font-size:22px; opacity:.2; }
    .kpi-label { font-size:11px; color:#64748b; text-transform:uppercase; letter-spacing:1px; margin-bottom:6px; }
    .kpi-value { font-size:24px; font-weight:700; font-family:monospace; }
    .kpi-sub   { font-size:11px; color:#64748b; margin-top:4px; }

    .card { background:#1e2d45; border:1px solid #2a3f5f; border-radius:12px; overflow:hidden; margin-bottom:16px; }
    .card-header { padding:12px 18px; border-bottom:1px solid #2a3f5f; font-size:13px; font-weight:600; color:#e8f0fe; }
    .table-wrap { overflow-x:auto; }

    ::ng-deep .p-datatable .p-datatable-thead > tr > th { background:#111827 !important; color:#64748b !important; font-size:11px !important; text-transform:uppercase !important; border-color:#2a3f5f !important; }
    ::ng-deep .p-datatable .p-datatable-tbody > tr { background:#1e2d45 !important; color:#94a3b8 !important; border-bottom:1px solid rgba(42,63,95,0.4) !important; }
    ::ng-deep .p-datatable .p-datatable-tbody > tr:hover { background:#1a2235 !important; }

    .mono    { font-family:monospace; font-size:12px; }
    .bold    { font-weight:600; color:#e8f0fe; }
    .empty-msg { text-align:center; padding:40px; color:#64748b; }

    .info-card { background:#1e2d45; border:1px solid #2a3f5f; border-radius:12px; padding:16px 18px; }
    .ic-title  { font-size:13px; font-weight:600; color:#e8f0fe; margin-bottom:12px; }
    .ic-row    { display:flex; justify-content:space-between; font-size:13px; padding:7px 0; border-bottom:1px solid rgba(42,63,95,0.3); }
    .ic-row:last-child { border-bottom:none; }
    .ic-row span:first-child { color:#64748b; }
    .ic-row span:last-child  { color:#e8f0fe; font-weight:500; }
  `]
})
export class FiscalComponent implements OnInit {
  declarations = signal<any[]>([]);
  stats        = signal<any>(null);
  loading      = signal(true);
  window       = window;

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.api.get<any[]>('/fiscal/declarations/').subscribe({
      next: res => {
        const data = Array.isArray(res) ? res : (res as any).results || [];
        this.declarations.set(data);

        // Calcul stats
        const masse = data.reduce((s: number, d: any) => s + (d.masse_salariale || 0), 0);
        const brs   = data.reduce((s: number, d: any) => s + (d.montant_brs    || 0), 0);
        const retard = data
          .filter((d: any) => d.statut === 'EN_RETARD')
          .reduce((s: number, d: any) => s + (d.montant_brs || 0), 0);
        this.stats.set({
          masse_salariale: masse,
          brs_total:       brs,
          brs_retard:      retard,
          brs_regle:       brs - retard,
        });
        this.loading.set(false);
      },
      error: () => this.loading.set(false)
    });
  }
}
