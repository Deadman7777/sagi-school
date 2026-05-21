import { Component, OnInit, signal } from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import { ApiService } from '../../core/services/api.service';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { ButtonModule } from 'primeng/button';
import { TranslateModule } from '@ngx-translate/core';

@Component({
  selector: 'app-fiscal',
  standalone: true,
  imports: [CommonModule, DecimalPipe, TableModule, TagModule, ButtonModule, TranslateModule],
  template: `
    <div class="page-header">
      <div>
        <h2 class="page-title">📋 Déclarations Fiscales — {{ exercice() }}</h2>
        <span class="page-sub">Sénégal · Convention Collective Enseignement Privé 2018 · CGI</span>
      </div>
      <button class="btn-print" onclick="window.print()">🖨️ Imprimer</button>
    </div>

    <!-- Alerte source estimation -->
    @if (synthese()?.source === 'ESTIMATION') {
      <div class="alert-banner">
        ⚠️ Les données sont <strong>estimées</strong> (aucun bulletin de paie validé).
        Validez des bulletins dans le module RH pour obtenir des données réelles.
      </div>
    }
    @if (synthese()?.source === 'BULLETINS') {
      <div class="success-banner">
        ✅ Données issues des <strong>bulletins de paie validés</strong> (module RH).
      </div>
    }

    <!-- KPIs -->
    @if (synthese()) {
      <div class="kpi-grid">
        <div class="kpi-card" style="--acc:#0099ff">
          <div class="kpi-icon">💼</div>
          <div class="kpi-label">Masse Salariale Brute</div>
          <div class="kpi-value" style="color:#0099ff">{{ synthese()!.masse_salariale | number:'1.0-0' }}</div>
          <div class="kpi-sub">FCFA</div>
        </div>
        <div class="kpi-card" style="--acc:#f59e0b">
          <div class="kpi-icon">📊</div>
          <div class="kpi-label">BRS dû (5%)</div>
          <div class="kpi-value" style="color:#f59e0b">{{ synthese()!.brs_total | number:'1.0-0' }}</div>
          <div class="kpi-sub">FCFA</div>
        </div>
        <div class="kpi-card" style="--acc:#7c3aed">
          <div class="kpi-icon">🏦</div>
          <div class="kpi-label">Total Impôts & Cotisations</div>
          <div class="kpi-value" style="color:#7c3aed">{{ synthese()!.total_impots | number:'1.0-0' }}</div>
          <div class="kpi-sub">FCFA cumulé</div>
        </div>
        <div class="kpi-card" style="--acc:#ef4444">
          <div class="kpi-icon">⚠️</div>
          <div class="kpi-label">Retards</div>
          <div class="kpi-value" style="color:#ef4444">{{ synthese()!.brs_retard | number:'1.0-0' }}</div>
          <div class="kpi-sub">FCFA à régulariser</div>
        </div>
        <div class="kpi-card" style="--acc:#10b981">
          <div class="kpi-icon">✅</div>
          <div class="kpi-label">En règle</div>
          <div class="kpi-value" style="color:#10b981">{{ synthese()!.brs_regle | number:'1.0-0' }}</div>
          <div class="kpi-sub">FCFA déclarés</div>
        </div>
        <div class="kpi-card" style="--acc:#00d4aa">
          <div class="kpi-icon">📅</div>
          <div class="kpi-label">IR retenu (total)</div>
          <div class="kpi-value" style="color:#00d4aa">{{ synthese()!.ir_total | number:'1.0-0' }}</div>
          <div class="kpi-sub">FCFA</div>
        </div>
        <div class="kpi-card" style="--acc:#f59e0b">
          <div class="kpi-icon">🏗️</div>
          <div class="kpi-label">CFCE (3%)</div>
          <div class="kpi-value" style="color:#f59e0b">{{ synthese()!.cfce_total | number:'1.0-0' }}</div>
          <div class="kpi-sub">FCFA</div>
        </div>
        <div class="kpi-card" style="--acc:#a855f7">
          <div class="kpi-icon">👥</div>
          <div class="kpi-label">CSS + ATMP</div>
          <div class="kpi-value" style="color:#a855f7">{{ synthese()!.css_atmp_total | number:'1.0-0' }}</div>
          <div class="kpi-sub">FCFA</div>
        </div>
      </div>
    }

    <!-- Tableau BRS mensuel -->
    <div class="card">
      <div class="card-header">
        📋 Bordereau de Règlement des Salaires (BRS) — Mensuel
        <span class="badge-source" *ngIf="synthese()?.source">{{ synthese()!.source }}</span>
      </div>
      <div class="table-wrap">
        <p-table [value]="declarations()" [loading]="loading()" styleClass="p-datatable-sm"
                 [scrollable]="true" scrollHeight="400px">
          <ng-template pTemplate="header">
            <tr>
              <th>Mois</th>
              <th class="tr">Masse sal. brute</th>
              <th class="tr">BRS (5%)</th>
              <th class="tr">IPRES Sal. (5.6%)</th>
              <th class="tr">IPRES Pat. (8.4%)</th>
              <th class="tr">CSS+ATMP (8%)</th>
              <th class="tr">IR retenu</th>
              <th class="tr">CFCE (3%)</th>
              <th class="tr bold">Total impôts</th>
              <th>Date limite</th>
              <th>Statut</th>
            </tr>
          </ng-template>
          <ng-template pTemplate="body" let-d>
            <tr>
              <td class="bold">{{ d.mois }}</td>
              <td class="mono tr">{{ d.masse_salariale | number:'1.0-0' }}</td>
              <td class="mono tr" style="color:#f59e0b">{{ d.brs | number:'1.0-0' }}</td>
              <td class="mono tr">{{ d.ipres_salarie | number:'1.0-0' }}</td>
              <td class="mono tr">{{ d.ipres_patronal | number:'1.0-0' }}</td>
              <td class="mono tr">{{ d.css_atmp | number:'1.0-0' }}</td>
              <td class="mono tr">{{ d.ir | number:'1.0-0' }}</td>
              <td class="mono tr">{{ d.cfce | number:'1.0-0' }}</td>
              <td class="mono tr bold" style="color:#a855f7">{{ d.total_impots | number:'1.0-0' }}</td>
              <td class="mono" style="font-size:11px">{{ d.date_limite }}</td>
              <td>
                <p-tag [value]="statutLabel(d.statut)"
                       [severity]="d.statut === 'EN_REGLE' ? 'success' :
                                   d.statut === 'EN_RETARD' ? 'danger' : 'warn'" />
              </td>
            </tr>
          </ng-template>
          <ng-template pTemplate="footer">
            <tr style="background:#0b0f1a">
              <td class="bold" style="color:#00d4aa">TOTAL</td>
              <td class="mono tr bold">{{ synthese()?.masse_salariale | number:'1.0-0' }}</td>
              <td class="mono tr" style="color:#f59e0b">{{ synthese()?.brs_total | number:'1.0-0' }}</td>
              <td class="mono tr">{{ synthese()?.ipres_salarie | number:'1.0-0' }}</td>
              <td class="mono tr">{{ synthese()?.ipres_patronal | number:'1.0-0' }}</td>
              <td class="mono tr">{{ synthese()?.css_atmp_total | number:'1.0-0' }}</td>
              <td class="mono tr">{{ synthese()?.ir_total | number:'1.0-0' }}</td>
              <td class="mono tr">{{ synthese()?.cfce_total | number:'1.0-0' }}</td>
              <td class="mono tr bold" style="color:#a855f7">{{ synthese()?.total_impots | number:'1.0-0' }}</td>
              <td colspan="2"></td>
            </tr>
          </ng-template>
          <ng-template pTemplate="emptymessage">
            <tr><td colspan="11" class="empty-msg">Aucune déclaration — vérifiez qu'un exercice est actif et que des bulletins de paie sont enregistrés.</td></tr>
          </ng-template>
        </p-table>
      </div>
    </div>

    <!-- Référentiel taux Sénégal -->
    <div class="card">
      <div class="card-header">⚖️ Référentiel fiscal — Sénégal (2024)</div>
      <div class="card-body">
        <div class="ref-grid">
          <div class="ref-section">
            <div class="rs-title">IPRES (Institut de Prévoyance Retraite)</div>
            <div class="rs-row"><span>Régime Général — Salarial</span><span class="mono" style="color:#0099ff">5.6 %</span></div>
            <div class="rs-row"><span>Régime Général — Patronal</span><span class="mono" style="color:#0099ff">8.4 %</span></div>
            <div class="rs-row"><span>Régime Cadre — Salarial</span><span class="mono">2.4 %</span></div>
            <div class="rs-row"><span>Régime Cadre — Patronal</span><span class="mono">3.6 %</span></div>
            <div class="rs-row small"><span>Plafond régime général</span><span class="mono">1 578 000 FCFA/mois</span></div>
          </div>
          <div class="ref-section">
            <div class="rs-title">CSS / ATMP (Caisse Sécurité Sociale)</div>
            <div class="rs-row"><span>Prestations familiales (patronal)</span><span class="mono" style="color:#a855f7">7.0 %</span></div>
            <div class="rs-row"><span>ATMP — Éducation (patronal)</span><span class="mono" style="color:#a855f7">1.0 %</span></div>
            <div class="rs-row small"><span>Base CSS</span><span class="mono">Brut limité à 63 000 FCFA/j</span></div>
          </div>
          <div class="ref-section">
            <div class="rs-title">CFCE & BRS</div>
            <div class="rs-row"><span>CFCE (Art. 188 CGI)</span><span class="mono" style="color:#f59e0b">3.0 %</span></div>
            <div class="rs-row"><span>BRS — taux global</span><span class="mono" style="color:#f59e0b">5.0 %</span></div>
            <div class="rs-row"><span>Date de dépôt BRS</span><span class="mono">15 du mois M+1</span></div>
            <div class="rs-row"><span>Organisme</span><span class="mono">DGID / Direction des Impôts</span></div>
          </div>
          <div class="ref-section">
            <div class="rs-title">IR — Impôt sur le Revenu (barème progressif)</div>
            <div class="rs-row"><span>≤ 630 000 FCFA/an</span><span class="mono">0 %</span></div>
            <div class="rs-row"><span>630 001 → 1 500 000</span><span class="mono">20 %</span></div>
            <div class="rs-row"><span>1 500 001 → 4 000 000</span><span class="mono">30 %</span></div>
            <div class="rs-row"><span>4 000 001 → 8 000 000</span><span class="mono">35 %</span></div>
            <div class="rs-row"><span>8 000 001 → 13 500 000</span><span class="mono">37 %</span></div>
            <div class="rs-row"><span>&gt; 13 500 000</span><span class="mono">40 %</span></div>
          </div>
        </div>
        <div class="ref-note">
          Références : Code Général des Impôts du Sénégal · Convention Collective Nationale
          de l'Enseignement Privé du Sénégal (2018) · Loi n° 97-17 du 1er décembre 1997
          portant Code du Travail · Décret IPRES
        </div>
      </div>
    </div>
  `,
  styles: [`
    .page-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:16px; }
    .page-title  { font-size:20px; font-weight:600; color:#e8f0fe; margin:0 0 4px; }
    .page-sub    { font-size:12px; color:#64748b; }
    .btn-print   { background:transparent; border:1px solid #2a3f5f; color:#64748b; padding:7px 14px; border-radius:6px; cursor:pointer; font-size:12px; }
    .btn-print:hover { border-color:#00d4aa; color:#00d4aa; }

    .alert-banner   { background:rgba(245,158,11,0.1); border:1px solid rgba(245,158,11,0.3); border-radius:8px; padding:10px 14px; font-size:12px; color:#f59e0b; margin-bottom:14px; }
    .success-banner { background:rgba(16,185,129,0.1); border:1px solid rgba(16,185,129,0.3); border-radius:8px; padding:10px 14px; font-size:12px; color:#10b981; margin-bottom:14px; }

    .kpi-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:16px; }
    .kpi-card { background:#1e2d45; border:1px solid #2a3f5f; border-top:2px solid var(--acc,#00d4aa); border-radius:10px; padding:14px 16px; position:relative; }
    .kpi-icon  { position:absolute; top:12px; right:12px; font-size:20px; opacity:.2; }
    .kpi-label { font-size:10px; color:#64748b; text-transform:uppercase; letter-spacing:1px; margin-bottom:4px; }
    .kpi-value { font-size:22px; font-weight:700; font-family:monospace; }
    .kpi-sub   { font-size:10px; color:#64748b; margin-top:2px; }

    .card { background:#1e2d45; border:1px solid #2a3f5f; border-radius:12px; overflow:hidden; margin-bottom:14px; }
    .card-header { display:flex; align-items:center; gap:10px; padding:12px 16px; border-bottom:1px solid #2a3f5f; font-size:13px; font-weight:600; color:#e8f0fe; }
    .card-body   { padding:14px 16px; }
    .badge-source { font-size:10px; background:#2a3f5f; color:#94a3b8; padding:2px 8px; border-radius:10px; }

    .table-wrap { overflow-x:auto; }
    ::ng-deep .p-datatable .p-datatable-thead > tr > th { background:#111827 !important; color:#64748b !important; font-size:10px !important; text-transform:uppercase !important; border-color:#2a3f5f !important; }
    ::ng-deep .p-datatable .p-datatable-tbody > tr { background:#1e2d45 !important; color:#94a3b8 !important; border-bottom:1px solid rgba(42,63,95,0.4) !important; }
    ::ng-deep .p-datatable .p-datatable-tfoot > tr > td { background:#0b0f1a !important; border-color:#2a3f5f !important; }

    .ref-grid { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
    .ref-section { background:#111827; border-radius:8px; padding:12px; }
    .rs-title { font-size:11px; font-weight:700; color:#00d4aa; text-transform:uppercase; letter-spacing:.5px; margin-bottom:8px; }
    .rs-row { display:flex; justify-content:space-between; font-size:11px; padding:4px 0; border-bottom:1px solid rgba(42,63,95,0.3); color:#94a3b8; }
    .rs-row.small { font-size:10px; color:#64748b; }
    .ref-note { font-size:10px; color:#475569; margin-top:12px; line-height:1.6; border-top:1px solid #2a3f5f; padding-top:10px; }

    .mono    { font-family:monospace; font-size:11px; }
    .bold    { font-weight:600; color:#e8f0fe; }
    .tr      { text-align:right; }
    .empty-msg { text-align:center; padding:30px; color:#64748b; }

    @media print {
      .btn-print, .alert-banner { display:none; }
      .kpi-grid { grid-template-columns:repeat(4,1fr); }
    }
  `]
})
export class FiscalComponent implements OnInit {
  declarations = signal<any[]>([]);
  synthese     = signal<any>(null);
  exercice     = signal<string>('');
  loading      = signal(true);

  constructor(private api: ApiService) {}

  ngOnInit() {
    this.api.get<any>('/fiscal/declarations/').subscribe({
      next: res => {
        const data = res.declarations || (Array.isArray(res) ? res : []);
        this.declarations.set(data);
        this.synthese.set(res.synthese || null);
        this.exercice.set(res.exercice || '');
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  statutLabel(s: string) {
    return { EN_REGLE: 'En règle', EN_RETARD: 'En retard', A_VENIR: 'À venir' }[s] || s;
  }
}
