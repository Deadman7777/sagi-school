import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ComptabiliteService } from '../../core/services/comptabilite.service';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { ButtonModule } from 'primeng/button';
import { TranslateModule } from '@ngx-translate/core';

@Component({
  selector: 'app-comptabilite',
  standalone: true,
  imports: [CommonModule, TableModule, TagModule, ButtonModule, TranslateModule],
  template: `
    <div class="page-header">
      <div>
        <h2 class="page-title">📒 Comptabilité SYSCOHADA</h2>
        <span class="page-sub">Journal · Grand Livre · Balance · Résultat · Bilan · Flux</span>
      </div>
      <button class="btn-export" (click)="exporter()">📤 Exporter PDF</button>
    </div>

    <!-- Onglets -->
    <div class="tabs-bar">
      <button class="tab-btn" [class.active]="onglet() === 'journal'"
              (click)="onglet.set('journal')">📒 Journal</button>
      <button class="tab-btn" [class.active]="onglet() === 'grand-livre'"
              (click)="onglet.set('grand-livre')">📖 Grand Livre</button>
      <button class="tab-btn" [class.active]="onglet() === 'balance'"
              (click)="onglet.set('balance')">⚖️ Balance</button>
      <button class="tab-btn" [class.active]="onglet() === 'resultat'"
              (click)="onglet.set('resultat')">📈 Résultat</button>
      <button class="tab-btn" [class.active]="onglet() === 'bilan'"
              (click)="onglet.set('bilan')">🏦 Bilan</button>
      <button class="tab-btn" [class.active]="onglet() === 'flux'"
              (click)="onglet.set('flux')">💧 Flux Trésorerie</button>
      <button class="tab-btn" [class.active]="onglet() === 'historique'"
              (click)="onglet.set('historique')">📚 Historique</button>
    </div>

    <!-- JOURNAL -->
    <div class="table-card" *ngIf="onglet() === 'journal'">
      <p-table [value]="journal()" [loading]="loadingJournal()"
               styleClass="p-datatable-sm" [paginator]="true" [rows]="25">
        <ng-template pTemplate="header">
          <tr><th>Date</th><th>N° Pièce</th><th>N° Compte</th>
              <th>Libellé</th><th>Débit</th><th>Crédit</th><th>Source</th></tr>
        </ng-template>
        <ng-template pTemplate="body" let-e>
          <tr>
            <td>{{ e.date | date:'dd/MM/yyyy' }}</td>
            <td class="mono">{{ e.no_piece }}</td>
            <td class="mono">{{ e.no_compte }}</td>
            <td>{{ e.libelle }}</td>
            <td class="mono success">{{ e.debit  > 0 ? (e.debit  | number:'1.0-0') : '—' }}</td>
            <td class="mono info">   {{ e.credit > 0 ? (e.credit | number:'1.0-0') : '—' }}</td>
            <td><p-tag [value]="e.source" [severity]="e.source === 'RECETTE' ? 'success' : 'danger'" /></td>
          </tr>
        </ng-template>
        <ng-template pTemplate="emptymessage">
          <tr><td colspan="7" class="empty-msg">Aucune écriture</td></tr>
        </ng-template>
      </p-table>
    </div>

    <!-- GRAND LIVRE -->
    <div class="table-card" *ngIf="onglet() === 'grand-livre'">
      <p-table [value]="grandLivre()" [loading]="loadingGL()" styleClass="p-datatable-sm">
        <ng-template pTemplate="header">
          <tr><th>N° Compte</th><th>Libellé</th>
              <th>Total Débit</th><th>Total Crédit</th>
              <th>Solde Débiteur</th><th>Solde Créditeur</th></tr>
        </ng-template>
        <ng-template pTemplate="body" let-c>
          <tr>
            <td class="mono bold">{{ c.no_compte }}</td>
            <td>{{ c.libelle }}</td>
            <td class="mono success">{{ c.total_debit    | number:'1.0-0' }}</td>
            <td class="mono info">   {{ c.total_credit   | number:'1.0-0' }}</td>
            <td class="mono">{{ c.solde_debiteur  > 0 ? (c.solde_debiteur  | number:'1.0-0') : '—' }}</td>
            <td class="mono">{{ c.solde_crediteur > 0 ? (c.solde_crediteur | number:'1.0-0') : '—' }}</td>
          </tr>
        </ng-template>
      </p-table>
    </div>

    <!-- BALANCE -->
    <div class="table-card" *ngIf="onglet() === 'balance'">
      <p-table [value]="balance()?.lignes || []" [loading]="loadingBalance()"
               styleClass="p-datatable-sm" [showGridlines]="true">
        <ng-template pTemplate="header">
          <tr><th>N° Compte</th><th>Libellé</th>
              <th>Mvt Débit</th><th>Mvt Crédit</th>
              <th>Solde Débiteur</th><th>Solde Créditeur</th></tr>
        </ng-template>
        <ng-template pTemplate="body" let-l>
          <tr>
            <td class="mono bold">{{ l.no_compte }}</td>
            <td>{{ l.libelle }}</td>
            <td class="mono">{{ l.total_debit    | number:'1.0-0' }}</td>
            <td class="mono">{{ l.total_credit   | number:'1.0-0' }}</td>
            <td class="mono success">{{ l.solde_debiteur  > 0 ? (l.solde_debiteur  | number:'1.0-0') : '' }}</td>
            <td class="mono info">   {{ l.solde_crediteur > 0 ? (l.solde_crediteur | number:'1.0-0') : '' }}</td>
          </tr>
        </ng-template>
        <ng-template pTemplate="footer" *ngIf="balance()?.totaux">
          <tr class="totaux-row">
            <td colspan="2"><strong>TOTAUX</strong></td>
            <td class="mono"><strong>{{ balance().totaux.total_debit    | number:'1.0-0' }}</strong></td>
            <td class="mono"><strong>{{ balance().totaux.total_credit   | number:'1.0-0' }}</strong></td>
            <td class="mono"><strong>{{ balance().totaux.solde_debiteur  | number:'1.0-0' }}</strong></td>
            <td class="mono"><strong>{{ balance().totaux.solde_crediteur | number:'1.0-0' }}</strong></td>
          </tr>
        </ng-template>
      </p-table>
    </div>

    <!-- COMPTE DE RÉSULTAT -->
    <div *ngIf="onglet() === 'resultat' && resultat()">
      <div class="grid-2">
        <div class="card">
          <div class="card-header" style="color:#10b981">💰 PRODUITS</div>
          <div class="card-body">
            <div class="cr-row" *ngFor="let p of resultat().detail_produits">
              <span>{{ p.libelle }}</span>
              <span class="mono success">{{ p.montant | number:'1.0-0' }} FCFA</span>
            </div>
            <div class="cr-total">
              <span>TOTAL PRODUITS</span>
              <span class="mono">{{ resultat().total_produits | number:'1.0-0' }} FCFA</span>
            </div>
          </div>
        </div>
        <div class="card">
          <div class="card-header" style="color:#ef4444">💸 CHARGES</div>
          <div class="card-body">
            <div class="cr-row" *ngFor="let c of resultat().detail_charges">
              <span>{{ c.libelle }}</span>
              <span class="mono danger">{{ c.montant | number:'1.0-0' }} FCFA</span>
            </div>
            <div class="cr-total">
              <span>TOTAL CHARGES</span>
              <span class="mono">{{ resultat().total_charges | number:'1.0-0' }} FCFA</span>
            </div>
          </div>
        </div>
      </div>
      <div class="resultat-net"
           [style.border-color]="resultat().resultat_net >= 0 ? '#10b981' : '#ef4444'"
           [style.background]="resultat().resultat_net >= 0 ? 'rgba(16,185,129,0.08)' : 'rgba(239,68,68,0.08)'">
        <span>RÉSULTAT NET — Exercice {{ resultat().exercice }}</span>
        <span class="mono" [style.color]="resultat().resultat_net >= 0 ? '#10b981' : '#ef4444'">
          {{ resultat().resultat_net >= 0 ? '+' : '' }}{{ resultat().resultat_net | number:'1.0-0' }} FCFA
        </span>
      </div>
    </div>

    <!-- BILAN -->
    <div *ngIf="onglet() === 'bilan' && bilan()">
      <div class="bilan-header">
        <span>📊 BILAN COMPTABLE — Exercice {{ bilan().exercice }}</span>
        <span class="equilibre-badge" [class.ok]="bilan().equilibre">
          {{ bilan().equilibre ? '✅ Équilibré' : '⚠️ Déséquilibré' }}
        </span>
      </div>

      <div class="grid-2">
        <!-- ACTIF -->
        <div class="card">
          <div class="card-header" style="color:#0099ff">🏦 ACTIF</div>
          <div class="card-body">
            <div class="bilan-section">Actif Circulant</div>
            <div class="cr-row">
              <span>Créances clients (élèves)</span>
              <span class="mono info">{{ bilan().actif.creances_clients | number:'1.0-0' }}</span>
            </div>
            <div class="bilan-section">Trésorerie & Équivalents</div>
            <div class="cr-row" *ngFor="let t of bilan().actif.tresorerie">
              <span>{{ t.libelle }}</span>
              <span class="mono info">{{ t.montant | number:'1.0-0' }}</span>
            </div>
            <div class="cr-total">
              <span>TOTAL ACTIF</span>
              <span class="mono" style="color:#0099ff">{{ bilan().actif.total_actif | number:'1.0-0' }} FCFA</span>
            </div>
          </div>
        </div>

        <!-- PASSIF -->
        <div class="card">
          <div class="card-header" style="color:#a855f7">📋 PASSIF</div>
          <div class="card-body">
            <div class="bilan-section">Capitaux Propres</div>
            <div class="cr-row">
              <span>Capital (Trésorerie initiale)</span>
              <span class="mono" style="color:#a855f7">{{ bilan().passif.capital | number:'1.0-0' }}</span>
            </div>
            <div class="cr-row">
              <span>Résultat de l'exercice</span>
              <span class="mono" [style.color]="bilan().passif.resultat_net >= 0 ? '#10b981' : '#ef4444'">
                {{ bilan().passif.resultat_net >= 0 ? '+' : '' }}{{ bilan().passif.resultat_net | number:'1.0-0' }}
              </span>
            </div>
            <div class="cr-row bold-row">
              <span>Total Capitaux Propres</span>
              <span class="mono" style="color:#a855f7">{{ bilan().passif.total_capitaux | number:'1.0-0' }}</span>
            </div>
            <div class="bilan-section">Dettes</div>
            <div class="cr-row">
              <span>Dettes fournisseurs (estimées)</span>
              <span class="mono danger">{{ bilan().passif.dettes | number:'1.0-0' }}</span>
            </div>
            <div class="cr-total">
              <span>TOTAL PASSIF</span>
              <span class="mono" style="color:#a855f7">{{ bilan().passif.total_passif | number:'1.0-0' }} FCFA</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- TABLEAU DES FLUX -->
    <div *ngIf="onglet() === 'flux' && flux()">
      <div class="flux-header">
        💧 Tableau des Flux de Trésorerie — Méthode {{ flux().methode }} — {{ flux().exercice }}
      </div>

      <!-- Flux exploitation -->
      <div class="card" style="margin-bottom:14px">
        <div class="card-header">⚙️ Flux liés à l'Activité (Exploitation)</div>
        <div class="card-body">
          <div class="cr-row">
            <span>Encaissements reçus des clients</span>
            <span class="mono success">+{{ flux().flux_exploitation.encaissements_clients | number:'1.0-0' }}</span>
          </div>
          <div class="cr-row">
            <span>Décaissements aux fournisseurs & charges</span>
            <span class="mono danger">-{{ flux().flux_exploitation.decaissements_charges | number:'1.0-0' }}</span>
          </div>
          <div class="flux-total" [style.color]="flux().flux_exploitation.flux_net >= 0 ? '#10b981' : '#ef4444'">
            <span>Flux net d'exploitation</span>
            <span class="mono">{{ flux().flux_exploitation.flux_net >= 0 ? '+' : '' }}{{ flux().flux_exploitation.flux_net | number:'1.0-0' }} FCFA</span>
          </div>
        </div>
      </div>

      <!-- Flux investissement -->
      <div class="card" style="margin-bottom:14px">
        <div class="card-header">🏗️ Flux liés aux Investissements</div>
        <div class="card-body">
          <div class="cr-row"><span>Acquisitions d'immobilisations</span><span class="mono">0</span></div>
          <div class="cr-row"><span>Cessions d'immobilisations</span><span class="mono">0</span></div>
          <div class="flux-total" style="color:#64748b">
            <span>Flux net d'investissement</span><span class="mono">0 FCFA</span>
          </div>
        </div>
      </div>

      <!-- Flux financement -->
      <div class="card" style="margin-bottom:14px">
        <div class="card-header">💼 Flux liés au Financement</div>
        <div class="card-body">
          <div class="cr-row">
            <span>Apports en capital (trésorerie initiale)</span>
            <span class="mono success">+{{ flux().flux_financement.apports_capital | number:'1.0-0' }}</span>
          </div>
          <div class="flux-total" style="color:#10b981">
            <span>Flux net de financement</span>
            <span class="mono">+{{ flux().flux_financement.flux_net | number:'1.0-0' }} FCFA</span>
          </div>
        </div>
      </div>

      <!-- Trésorerie nette -->
      <div class="tresorerie-box">
        <div class="tb-row">
          <span>Trésorerie d'ouverture</span>
          <span class="mono">{{ flux().tresorerie.solde_initial | number:'1.0-0' }} FCFA</span>
        </div>
        <div class="tb-row">
          <span>Variation nette de trésorerie</span>
          <span class="mono" [style.color]="flux().tresorerie.variation >= 0 ? '#10b981' : '#ef4444'">
            {{ flux().tresorerie.variation >= 0 ? '+' : '' }}{{ flux().tresorerie.variation | number:'1.0-0' }} FCFA
          </span>
        </div>
        <div class="tb-final">
          <span>TRÉSORERIE DE CLÔTURE</span>
          <span class="mono" style="color:#00d4aa">{{ flux().tresorerie.solde_final | number:'1.0-0' }} FCFA</span>
        </div>
      </div>

      <!-- Flux mensuels -->
      <div class="card" *ngIf="flux().flux_mensuels?.length > 0">
        <div class="card-header">📅 Flux Mensuels</div>
        <div class="card-body">
          <div class="bars-mensuel">
            <div class="bm-item" *ngFor="let m of flux().flux_mensuels">
              <div class="bm-bar-wrap">
                <div class="bm-bar"
                     [style.height.%]="(m.encaisse / maxFlux()) * 100"
                     [title]="m.encaisse | number:'1.0-0'">
                </div>
              </div>
              <div class="bm-label">{{ m.mois }}</div>
              <div class="bm-val">{{ m.encaisse | number:'1.0-0' }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- HISTORIQUE -->
    <div *ngIf="onglet() === 'historique'">

      <!-- Exercice actif -->
      <div class="exercice-actif" *ngIf="historique()?.exercice_actif">
        <div class="ea-badge">📅 Exercice en cours</div>
        <div class="ea-annee">{{ historique().exercice_actif.annee_scolaire }}</div>
        <div class="ea-dates">
          {{ historique().exercice_actif.date_debut | date:'dd/MM/yyyy' }}
          → {{ historique().exercice_actif.date_fin | date:'dd/MM/yyyy' }}
        </div>
      </div>

      <!-- Historique clôturés -->
      <div class="section-title-hist">
        📚 Exercices Clôturés ({{ historique()?.nb_exercices_clotures || 0 }})
      </div>

      <div *ngIf="historique()?.historique?.length === 0" class="empty-msg" style="padding:40px;text-align:center">
        Aucun exercice clôturé — utilisez Paramètres → Clôture Exercice
      </div>

      <div class="table-card" *ngIf="historique()?.historique?.length > 0">
        <p-table [value]="historique().historique" styleClass="p-datatable-sm">
          <ng-template pTemplate="header">
            <tr>
              <th>Année Scolaire</th>
              <th>Période</th>
              <th>Date Clôture</th>
              <th>Élèves</th>
              <th class="text-right">Total Recettes</th>
              <th class="text-right">Total Charges</th>
              <th class="text-right">Résultat Net</th>
            </tr>
          </ng-template>
          <ng-template pTemplate="body" let-h>
            <tr>
              <td class="bold">{{ h.annee_scolaire }}</td>
              <td class="mono" style="font-size:11px">
                {{ h.date_debut | date:'dd/MM/yy' }} → {{ h.date_fin | date:'dd/MM/yy' }}
              </td>
              <td class="mono">{{ h.date_cloture | date:'dd/MM/yyyy' }}</td>
              <td class="mono text-center">{{ h.nb_eleves }}</td>
              <td class="mono text-right success">{{ h.total_recettes | number:'1.0-0' }}</td>
              <td class="mono text-right danger">{{ h.total_charges | number:'1.0-0' }}</td>
              <td class="mono text-right"
                  [style.color]="h.resultat_net >= 0 ? '#10b981' : '#ef4444'">
                {{ h.resultat_net >= 0 ? '+' : '' }}{{ h.resultat_net | number:'1.0-0' }}
              </td>
            </tr>
          </ng-template>
          <!-- Total comparatif -->
          <ng-template pTemplate="footer">
            <tr class="totaux-row">
              <td colspan="4" class="bold">TOTAL CUMULÉ</td>
              <td class="mono text-right bold success">
                {{ totalHistorique('total_recettes') | number:'1.0-0' }}
              </td>
              <td class="mono text-right bold danger">
                {{ totalHistorique('total_charges') | number:'1.0-0' }}
              </td>
              <td class="mono text-right bold"
                  [style.color]="totalHistorique('resultat_net') >= 0 ? '#10b981' : '#ef4444'">
                {{ totalHistorique('resultat_net') | number:'1.0-0' }}
              </td>
            </tr>
          </ng-template>
        </p-table>
      </div>
    </div>
  `,
  styles: [`
    .page-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:16px; }
    .page-title  { font-size:20px; font-weight:600; color:#e8f0fe; margin:0 0 4px; }
    .page-sub    { font-size:12px; color:#64748b; }
    .btn-export  { background:transparent; border:1px solid #2a3f5f; color:#94a3b8; border-radius:8px; padding:7px 14px; cursor:pointer; font-size:13px; }
    .btn-export:hover { border-color:#00d4aa; color:#00d4aa; }

    .tabs-bar { display:flex; gap:3px; margin-bottom:16px; background:#111827; border:1px solid #2a3f5f; border-radius:10px; padding:4px; flex-wrap:wrap; }
    .tab-btn { flex:1; min-width:80px; padding:7px 8px; border:none; border-radius:7px; background:transparent; color:#64748b; font-size:12px; cursor:pointer; transition:all 0.15s; font-family:inherit; white-space:nowrap; }
    .tab-btn:hover  { background:#1a2235; color:#e8f0fe; }
    .tab-btn.active { background:#1e2d45; color:#00d4aa; font-weight:600; border:1px solid #2a3f5f; }

    .table-card { background:#1e2d45; border:1px solid #2a3f5f; border-radius:12px; overflow:hidden; }
    ::ng-deep .p-datatable .p-datatable-thead > tr > th { background:#111827 !important; color:#64748b !important; font-size:11px !important; text-transform:uppercase !important; border-color:#2a3f5f !important; }
    ::ng-deep .p-datatable .p-datatable-tbody > tr { background:#1e2d45 !important; color:#94a3b8 !important; border-bottom:1px solid rgba(42,63,95,0.4) !important; }
    ::ng-deep .p-datatable .p-datatable-tbody > tr:hover { background:#1a2235 !important; }
    .totaux-row td { background:#111827 !important; color:#e8f0fe !important; border-top:2px solid #2a3f5f !important; }

    .mono    { font-family:monospace; font-size:12px; }
    .bold    { font-weight:600; color:#e8f0fe; }
    .success { color:#10b981; }
    .info    { color:#0099ff; }
    .danger  { color:#ef4444; }
    .empty-msg { color:#64748b; }
    .text-right  { text-align:right !important; }
    .text-center { text-align:center !important; }

    .grid-2 { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:16px; }
    .card { background:#1e2d45; border:1px solid #2a3f5f; border-radius:12px; overflow:hidden; margin-bottom:14px; }
    .card-header { padding:12px 18px; border-bottom:1px solid #2a3f5f; font-size:13px; font-weight:600; color:#e8f0fe; }
    .card-body   { padding:16px 18px; }

    .cr-row { display:flex; justify-content:space-between; padding:7px 0; border-bottom:1px solid rgba(42,63,95,0.3); font-size:13px; }
    .cr-row span:first-child { color:#94a3b8; }
    .cr-total { display:flex; justify-content:space-between; padding:10px 0 0; font-weight:700; font-size:13px; color:#e8f0fe; border-top:2px solid #2a3f5f; margin-top:4px; }
    .bold-row span { font-weight:600 !important; color:#e8f0fe !important; }

    .resultat-net { display:flex; justify-content:space-between; align-items:center; border:2px solid; border-radius:12px; padding:16px 24px; font-size:16px; font-weight:700; color:#e8f0fe; }
    .resultat-net .mono { font-size:24px; }

    .bilan-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; font-size:13px; font-weight:600; color:#e8f0fe; }
    .equilibre-badge { font-size:12px; padding:4px 12px; border-radius:20px; background:rgba(16,185,129,0.15); color:#10b981; }
    .bilan-section { font-size:11px; color:#64748b; text-transform:uppercase; letter-spacing:1px; margin:10px 0 4px; }

    .flux-header { background:#1e2d45; border:1px solid #2a3f5f; border-radius:10px; padding:12px 18px; font-size:13px; font-weight:600; color:#0099ff; margin-bottom:14px; }
    .flux-total { display:flex; justify-content:space-between; padding:10px 0 0; font-weight:700; font-size:13px; border-top:2px solid #2a3f5f; margin-top:4px; }

    .tresorerie-box { background:#0f1a2e; border:2px solid #00d4aa; border-radius:12px; padding:18px 20px; margin-bottom:16px; }
    .tb-row   { display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid rgba(0,212,170,0.15); font-size:13px; color:#94a3b8; }
    .tb-final { display:flex; justify-content:space-between; padding:12px 0 0; font-size:16px; font-weight:700; color:#00d4aa; }
    .tb-final .mono { font-size:20px; }

    .bars-mensuel { display:flex; gap:8px; align-items:flex-end; height:100px; }
    .bm-item  { flex:1; display:flex; flex-direction:column; align-items:center; gap:4px; height:100%; justify-content:flex-end; }
    .bm-bar-wrap { width:100%; flex:1; display:flex; align-items:flex-end; }
    .bm-bar   { width:100%; background:linear-gradient(to top,#00d4aa,#0099ff); border-radius:4px 4px 0 0; min-height:4px; }
    .bm-label { font-size:10px; color:#64748b; }
    .bm-val   { font-size:9px; color:#94a3b8; font-family:monospace; }

    .exercice-actif { background:rgba(0,212,170,0.08); border:1px solid rgba(0,212,170,0.3); border-radius:10px; padding:16px 20px; margin-bottom:16px; display:flex; align-items:center; gap:16px; }
    .ea-badge  { font-size:11px; padding:3px 10px; border-radius:20px; background:rgba(0,212,170,0.15); color:#00d4aa; flex-shrink:0; }
    .ea-annee  { font-size:16px; font-weight:700; color:#e8f0fe; }
    .ea-dates  { font-size:12px; color:#64748b; font-family:monospace; margin-left:auto; }
    .section-title-hist { font-size:14px; font-weight:600; color:#e8f0fe; margin-bottom:12px; }
  `]
})
export class ComptabiliteComponent implements OnInit {
  onglet         = signal('journal');
  journal        = signal<any[]>([]);
  grandLivre     = signal<any[]>([]);
  balance        = signal<any>(null);
  resultat       = signal<any>(null);
  bilan          = signal<any>(null);
  flux           = signal<any>(null);
  historique     = signal<any>(null);
  loadingJournal = signal(true);
  loadingGL      = signal(true);
  loadingBalance = signal(true);

  constructor(private compta: ComptabiliteService) {}

  ngOnInit() {
    this.compta.getJournal().subscribe({
      next: res => { this.journal.set(res); this.loadingJournal.set(false); }
    });
    this.compta.getGrandLivre().subscribe({
      next: res => { this.grandLivre.set(res); this.loadingGL.set(false); }
    });
    this.compta.getBalance().subscribe({
      next: res => { this.balance.set(res); this.loadingBalance.set(false); }
    });
    this.compta.getCompteResultat().subscribe({
      next: res => this.resultat.set(res)
    });
    this.compta.getBilan().subscribe({
      next: res => this.bilan.set(res)
    });
    this.compta.getTableauFlux().subscribe({
      next: res => this.flux.set(res)
    });
    this.compta.getHistorique().subscribe({
      next: res => this.historique.set(res)
    });
  }

  maxFlux(): number {
    return Math.max(...(this.flux()?.flux_mensuels || []).map((m: any) => m.encaisse), 1);
  }

  totalHistorique(field: string): number {
    return (this.historique()?.historique || []).reduce(
      (s: number, h: any) => s + (h[field] || 0), 0
    );
  }

    exporter() {
    const type = this.onglet() === 'bilan'    ? 'bilan'
              : this.onglet() === 'flux'     ? 'tableau_flux'
              : this.onglet() === 'resultat' ? 'compte_resultat'
              : this.onglet() === 'balance'  ? 'balance'
              : 'eleves';

    if (!['bilan','tableau_flux','compte_resultat','balance','eleves'].includes(type)) {
      alert('Export PDF non disponible pour cet onglet');
      return;
    }

    const token    = localStorage.getItem('access_token');
    const tenantId = localStorage.getItem('tenant_id') || '';

    fetch(`http://127.0.0.1:8765/api/comptabilite/export-pdf/${type}/`, {
      headers: {
        'Authorization': `Bearer ${token}`,
        'X-Tenant-ID':   tenantId
      }
    })
    .then(r => r.blob())
    .then(blob => {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `${type}_sagi_school.pdf`;
      a.click();
    });
  }
}
