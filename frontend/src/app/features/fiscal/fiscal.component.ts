import { Component, OnInit, signal } from '@angular/core';
import { CommonModule, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/services/api.service';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { SelectModule } from 'primeng/select';
import { InputNumberModule } from 'primeng/inputnumber';
import { InputTextModule } from 'primeng/inputtext';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';
import { TranslateModule } from '@ngx-translate/core';

@Component({
  selector: 'app-fiscal',
  standalone: true,
  imports: [CommonModule, DecimalPipe, FormsModule, TableModule, TagModule, ButtonModule,
            DialogModule, SelectModule, InputNumberModule, InputTextModule, ToastModule,
            TranslateModule],
  providers: [MessageService],
  template: `
    <p-toast />
    <div class="page-header">
      <div>
        <h2 class="page-title">📋 Fiscalité — {{ exercice() }}</h2>
        <span class="page-sub">Sénégal · Convention Collective Enseignement Privé 2018 · CGI</span>
      </div>
      <button class="btn-print" onclick="window.print()">🖨️ Imprimer</button>
    </div>

    <!-- Onglets -->
    <div class="tabs-bar">
      <button class="tab-btn" [class.active]="onglet() === 'declarations'"
              (click)="onglet.set('declarations')">🧾 Déclarations sociales</button>
      <button class="tab-btn" [class.active]="onglet() === 'obligations'"
              (click)="onglet.set('obligations'); chargerObligations()">🏛️ Obligations de l'établissement</button>
      <button class="tab-btn" [class.active]="onglet() === 'conseils'"
              (click)="onglet.set('conseils'); chargerConseils()">💡 Conseils</button>
    </div>

    <!-- ════════════ OBLIGATIONS ÉTABLISSEMENT ════════════ -->
    @if (onglet() === 'obligations') {
      @if (obligationsData(); as od) {
        @if (!od.identification?.complet) {
          <div class="alert-banner">
            ⚠️ {{ od.message }}
          </div>
        } @else {
          <div class="success-banner">
            ✅ Identification fiscale : RCCM <strong>{{ od.identification.rccm }}</strong> ·
            NINEA <strong>{{ od.identification.ninea }}</strong> — calcul automatique activé.
          </div>
          @if (od.donnees; as dn) {
            <div class="kpi-grid">
              <div class="kpi-card" style="--acc:#10b981">
                <div class="kpi-label">Produits (exercice)</div>
                <div class="kpi-value" style="color:#10b981">{{ dn.produits | number:'1.0-0' }}</div>
                <div class="kpi-sub">FCFA</div>
              </div>
              <div class="kpi-card" style="--acc:#ef4444">
                <div class="kpi-label">Charges</div>
                <div class="kpi-value" style="color:#ef4444">{{ dn.charges | number:'1.0-0' }}</div>
                <div class="kpi-sub">FCFA</div>
              </div>
              <div class="kpi-card" style="--acc:#0099ff">
                <div class="kpi-label">Résultat estimé</div>
                <div class="kpi-value" [style.color]="dn.resultat >= 0 ? '#10b981' : '#ef4444'">{{ dn.resultat | number:'1.0-0' }}</div>
                <div class="kpi-sub">FCFA</div>
              </div>
              <div class="kpi-card" style="--acc:#f59e0b">
                <div class="kpi-label">Masse salariale</div>
                <div class="kpi-value" style="color:#f59e0b">{{ dn.masse_salariale | number:'1.0-0' }}</div>
                <div class="kpi-sub">FCFA ({{ dn.source_paie === 'BULLETINS' ? 'bulletins' : 'estimation' }})</div>
              </div>
            </div>
          }
          @for (o of od.obligations; track o.code) {
            <div class="card ob-card">
              <div class="ob-head">
                <div>
                  <div class="ob-titre">{{ o.libelle }}</div>
                  <div class="ob-desc">{{ o.description }}</div>
                </div>
                <p-tag [value]="statutObligation(o.statut)"
                       [severity]="o.statut === 'EXONERE' || o.statut === 'BULLETINS' || o.statut === 'GERE_PAR_RH' ? 'success' :
                                   o.statut === 'A_SAISIR' ? 'warn' : 'info'" />
              </div>
              <div class="ob-body">
                <div class="ob-item"><span class="ob-lab">Taux</span><span>{{ o.taux }}</span></div>
                @if (o.montant !== null) {
                  <div class="ob-item"><span class="ob-lab">Montant estimé</span>
                    <span class="mono bold">{{ o.montant | number:'1.0-0' }} FCFA</span></div>
                }
                <div class="ob-item"><span class="ob-lab">Périodicité</span><span>{{ o.periodicite }}</span></div>
                <div class="ob-item"><span class="ob-lab">Échéance</span><span>{{ o.echeance }}</span></div>
                @if (o.deja_comptabilise > 0) {
                  <div class="ob-item"><span class="ob-lab">Déjà comptabilisé</span>
                    <span class="mono" style="color:#10b981">{{ o.deja_comptabilise | number:'1.0-0' }} FCFA</span></div>
                }
                @if (o.comptabilisable) {
                  <p-button label="Comptabiliser" icon="pi pi-book" size="small" severity="success"
                            [outlined]="true" (onClick)="ouvrirComptabiliser(o)" />
                }
              </div>
            </div>
          }
          <div class="ref-note">{{ od.disclaimer }}</div>
        }
      } @else {
        <div class="empty-msg">Chargement…</div>
      }
    }

    <!-- ════════════ CONSEILS ════════════ -->
    @if (onglet() === 'conseils') {
      @if (conseils(); as cs) {
        @if (cs.length === 0) {
          <div class="success-banner">✅ Aucun point d'attention : la situation fiscale, comptable et financière ne déclenche aucune alerte.</div>
        }
        @for (c of cs; track c.titre) {
          <div class="conseil" [class.urgent]="c.niveau === 'URGENT'"
               [class.attention]="c.niveau === 'ATTENTION'">
            <div class="conseil-head">
              <span class="conseil-cat">{{ categorieLabel(c.categorie) }}</span>
              <p-tag [value]="c.niveau" [severity]="c.niveau === 'URGENT' ? 'danger' : c.niveau === 'ATTENTION' ? 'warn' : 'info'" />
            </div>
            <div class="conseil-titre">{{ c.titre }}</div>
            <div class="conseil-detail">{{ c.detail }}</div>
          </div>
        }
        <div class="ref-note">Conseils générés automatiquement depuis les données du système — ils ne remplacent pas l'avis d'un expert-comptable.</div>
      } @else {
        <div class="empty-msg">Chargement…</div>
      }
    }

    <!-- Dialog comptabilisation -->
    <p-dialog header="Comptabiliser une obligation fiscale" [(visible)]="dialogCompta"
              [modal]="true" [style]="{width:'480px'}" [draggable]="false">
      @if (obligationActive; as o) {
        <div class="dlg-ob">{{ o.libelle }}</div>
        <div class="form-grid">
          <div class="fg full">
            <label>Montant (FCFA) *</label>
            <p-inputNumber [(ngModel)]="formCompta.montant" [min]="0" styleClass="w-full" />
          </div>
          <div class="fg">
            <label>Mode</label>
            <p-select appendTo="body" [options]="modeComptaOptions" [(ngModel)]="formCompta.mode"
                      optionLabel="label" optionValue="value" styleClass="w-full" />
          </div>
          @if (formCompta.mode === 'PAIEMENT') {
            <div class="fg">
              <label>Canal de paiement</label>
              <p-select appendTo="body" [options]="canauxOptions" [(ngModel)]="formCompta.canal"
                        optionLabel="label" optionValue="value" styleClass="w-full" />
            </div>
          }
          <div class="fg">
            <label>Date</label>
            <input pInputText type="date" [(ngModel)]="formCompta.date" class="w-full" />
          </div>
        </div>
        <div class="dlg-hint">
          Écritures : débit <strong>{{ o.comptes?.debit }}</strong> / crédit <strong>{{ o.comptes?.credit }}</strong>
          @if (formCompta.mode === 'PAIEMENT') { , puis règlement par <strong>{{ formCompta.canal }}</strong> }
          — pièce FISC-xxxx (SYSCOHADA).
        </div>
      }
      <ng-template pTemplate="footer">
        <p-button label="Annuler" severity="secondary" (onClick)="dialogCompta = false" />
        <p-button label="Comptabiliser" severity="success" [loading]="saving()" (onClick)="comptabiliser()" />
      </ng-template>
    </p-dialog>

    @if (onglet() === 'declarations') {

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
    }
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

    .tabs-bar { display:flex; gap:4px; margin-bottom:16px; background:#111827; border:1px solid #2a3f5f; border-radius:10px; padding:4px; }
    .tab-btn { flex:1; padding:8px 12px; border:none; border-radius:7px; background:transparent; color:#64748b; font-size:13px; cursor:pointer; font-family:inherit; }
    .tab-btn:hover  { background:#1a2235; color:#e8f0fe; }
    .tab-btn.active { background:#1e2d45; color:#00d4aa; font-weight:600; border:1px solid #2a3f5f; }

    .ob-card { padding:14px 16px; }
    .ob-head { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; margin-bottom:10px; }
    .ob-titre { font-size:13px; font-weight:600; color:#e8f0fe; margin-bottom:4px; }
    .ob-desc  { font-size:11px; color:#94a3b8; line-height:1.5; max-width:720px; }
    .ob-body  { display:flex; flex-wrap:wrap; gap:18px; align-items:center; }
    .ob-item  { display:flex; flex-direction:column; gap:2px; font-size:12px; color:#cbd5e1; }
    .ob-lab   { font-size:10px; color:#64748b; text-transform:uppercase; letter-spacing:.5px; }

    .conseil { background:#1e2d45; border:1px solid #2a3f5f; border-left:4px solid #0099ff; border-radius:10px; padding:12px 16px; margin-bottom:10px; }
    .conseil.attention { border-left-color:#f59e0b; }
    .conseil.urgent    { border-left-color:#ef4444; }
    .conseil-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:4px; }
    .conseil-cat  { font-size:10px; color:#64748b; text-transform:uppercase; letter-spacing:1px; }
    .conseil-titre { font-size:13px; font-weight:600; color:#e8f0fe; margin-bottom:4px; }
    .conseil-detail { font-size:12px; color:#94a3b8; line-height:1.6; }

    .form-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin:10px 0; }
    .fg { display:flex; flex-direction:column; gap:4px; }
    .fg.full { grid-column:1 / -1; }
    .fg label { font-size:12px; color:#94a3b8; }
    .w-full { width:100%; }
    .dlg-ob { font-size:13px; font-weight:600; color:#e8f0fe; margin-bottom:6px; }
    .dlg-hint { font-size:11px; color:#64748b; margin-top:6px; line-height:1.5; }

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
  saving       = signal(false);

  onglet          = signal<'declarations' | 'obligations' | 'conseils'>('declarations');
  obligationsData = signal<any | null>(null);
  conseils        = signal<any[] | null>(null);

  dialogCompta = false;
  obligationActive: any = null;
  formCompta: any = {};
  modeComptaOptions = [
    { label: 'Provision (constater la dette fiscale)', value: 'PROVISION' },
    { label: 'Paiement immédiat (provision + règlement)', value: 'PAIEMENT' },
  ];
  canauxOptions = [
    { label: 'Caisse (571)', value: '571' },
    { label: 'Banque (521)', value: '521' },
    { label: 'Orange Money (5521)', value: '5521' },
    { label: 'Wave (5522)', value: '5522' },
    { label: 'Free Money (5523)', value: '5523' },
  ];

  constructor(private api: ApiService, private msg: MessageService) {}

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

  chargerObligations() {
    this.obligationsData.set(null);
    this.api.get<any>('/fiscal/obligations/').subscribe({
      next: res => this.obligationsData.set(res),
      error: () => this.obligationsData.set({ identification: { complet: false },
                                              message: 'Erreur de chargement.', obligations: [] }),
    });
  }

  chargerConseils() {
    this.conseils.set(null);
    this.api.get<any>('/fiscal/conseils/').subscribe({
      next: res => this.conseils.set(res.conseils || []),
      error: () => this.conseils.set([]),
    });
  }

  ouvrirComptabiliser(o: any) {
    this.obligationActive = o;
    this.formCompta = {
      code:    o.code,
      montant: o.montant && o.montant > o.deja_comptabilise ? o.montant - o.deja_comptabilise : o.montant || null,
      mode:    'PROVISION',
      canal:   '571',
      date:    new Date().toISOString().split('T')[0],
    };
    this.dialogCompta = true;
  }

  comptabiliser() {
    if (!this.formCompta.montant || this.formCompta.montant <= 0) {
      this.msg.add({ severity: 'warn', summary: 'Montant requis', detail: 'Saisissez un montant supérieur à zéro.' });
      return;
    }
    this.saving.set(true);
    this.api.post<any>('/fiscal/comptabiliser/', this.formCompta).subscribe({
      next: res => {
        this.saving.set(false);
        this.dialogCompta = false;
        this.msg.add({ severity: 'success', summary: 'Comptabilisé',
                       detail: `Pièce ${res.no_piece} enregistrée au journal.` });
        this.chargerObligations();
      },
      error: err => {
        this.saving.set(false);
        this.msg.add({ severity: 'error', summary: 'Erreur',
                       detail: err?.error?.error || 'Comptabilisation impossible.' });
      },
    });
  }

  statutObligation(s: string) {
    return { ESTIMATION: 'Estimation', EXONERE: 'Exonéré', A_SAISIR: 'À saisir',
             BULLETINS: 'Données réelles', GERE_PAR_RH: 'Géré par le module RH' }[s] || s;
  }

  categorieLabel(c: string) {
    return { FISCAL: '🏛️ Fiscal', COMPTABLE: '📒 Comptable', FINANCIER: '💰 Financier' }[c] || c;
  }

  statutLabel(s: string) {
    return { EN_REGLE: 'En règle', EN_RETARD: 'En retard', A_VENIR: 'À venir' }[s] || s;
  }
}
