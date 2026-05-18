import { Component, NgModule, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ComptabiliteService } from '../../core/services/comptabilite.service';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { ButtonModule } from 'primeng/button';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { InputNumberModule} from 'primeng/inputnumber';
import { DialogModule } from 'primeng/dialog';
import { SelectModule } from 'primeng/select';

@Component({
  selector: 'app-comptabilite',
  standalone: true,
  imports: [CommonModule, FormsModule, TableModule, TagModule, ButtonModule, TranslateModule, InputNumberModule, DialogModule, SelectModule],
  template: `
    <div class="page-header">
      <div>
        <h2 class="page-title">📒 {{ 'comptabilite.title' | translate }}</h2>
        <span class="page-sub">{{ 'comptabilite.subtitle' | translate }}</span>
      </div>
      <button class="btn-export" (click)="exporter()">📤 {{ 'comptabilite.exporter_pdf' | translate }}</button>
    </div>

    <!-- Onglets -->
    <div class="tabs-bar">
      <button class="tab-btn" [class.active]="onglet() === 'journal'"
              (click)="onglet.set('journal')">📒 {{ 'comptabilite.journal'     | translate }}</button>
      <button class="tab-btn" [class.active]="onglet() === 'grand-livre'"
              (click)="onglet.set('grand-livre')">📖 {{ 'comptabilite.grand_livre' | translate }}</button>
      <button class="tab-btn" [class.active]="onglet() === 'balance'"
              (click)="onglet.set('balance')">⚖️ {{ 'comptabilite.balance'     | translate }}</button>
      <button class="tab-btn" [class.active]="onglet() === 'resultat'"
              (click)="onglet.set('resultat')">📈 {{ 'comptabilite.resultat'   | translate }}</button>
      <button class="tab-btn" [class.active]="onglet() === 'bilan'"
              (click)="onglet.set('bilan')">🏦 {{ 'comptabilite.bilan'         | translate }}</button>
      <button class="tab-btn" [class.active]="onglet() === 'flux'"
              *ngIf="systeme() === 'SN'"
              (click)="onglet.set('flux')">💧 {{ 'comptabilite.flux'           | translate }}</button>
      <button class="tab-btn" [class.active]="onglet() === 'historique'"
              (click)="onglet.set('historique')">📚 {{ 'comptabilite.historique'| translate }}</button>
      <button class="tab-btn" [class.active]="onglet() === 'notes'"
              (click)="onglet.set('notes')">📎 {{ 'comptabilite.notes_annexes' | translate }}</button>
      <button class="tab-btn" [class.active]="onglet() === 'charges'"
        (click)="onglet.set('charges')">💸 {{ 'comptabilite.charges_tab'       | translate }}</button>
    </div>

    <!-- JOURNAL -->
    <div class="table-card" *ngIf="onglet() === 'journal'">
      <p-table [value]="journal()" [loading]="loadingJournal()"
               styleClass="p-datatable-sm" [paginator]="true" [rows]="25">
        <ng-template pTemplate="header">
          <tr>
            <th>{{ 'comptabilite.date'     | translate }}</th>
            <th>{{ 'comptabilite.no_piece' | translate }}</th>
            <th>{{ 'comptabilite.no_compte'| translate }}</th>
            <th>{{ 'comptabilite.libelle'  | translate }}</th>
            <th>{{ 'comptabilite.debit'    | translate }}</th>
            <th>{{ 'comptabilite.credit'   | translate }}</th>
            <th>{{ 'comptabilite.source'   | translate }}</th>
          </tr>
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
          <tr><td colspan="7" class="empty-msg">{{ 'comptabilite.aucune_ecriture' | translate }}</td></tr>
        </ng-template>
      </p-table>
    </div>

    <!-- GRAND LIVRE -->
    <div class="table-card" *ngIf="onglet() === 'grand-livre'">
      <p-table [value]="grandLivre()" [loading]="loadingGL()" styleClass="p-datatable-sm">
        <ng-template pTemplate="header">
          <tr>
            <th>{{ 'comptabilite.no_compte'     | translate }}</th>
            <th>{{ 'comptabilite.libelle'        | translate }}</th>
            <th>{{ 'comptabilite.total_debit'    | translate }}</th>
            <th>{{ 'comptabilite.total_credit'   | translate }}</th>
            <th>{{ 'comptabilite.solde_debiteur' | translate }}</th>
            <th>{{ 'comptabilite.solde_crediteur'| translate }}</th>
          </tr>
        </ng-template>
        <ng-template pTemplate="body" let-c>
          <tr [class.synthetic-row]="c.is_synthetic">
            <td class="mono bold">{{ c.no_compte }}</td>
            <td [class.bold]="c.is_synthetic">{{ c.libelle }}</td>
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
      <tr>
        <th rowspan="2">N° Compte</th>
        <th rowspan="2">Libellé</th>
        <th colspan="2" style="text-align:center;background:#1a2235">{{ 'comptabilite.so_ouverture'    | translate }}</th>
        <th colspan="2" style="text-align:center;background:#1a2235">{{ 'comptabilite.mouvements'      | translate }}</th>
        <th colspan="2" style="text-align:center;background:#1a2235">{{ 'comptabilite.solde_cloture_col'| translate }}</th>
      </tr>
      <tr>
        <th>Débit</th><th>Crédit</th>
        <th>Débit</th><th>Crédit</th>
        <th>Débiteur</th><th>Créditeur</th>
      </tr>
    </ng-template>
    <ng-template pTemplate="body" let-l>
      <tr [class.synthetic-row]="l.is_synthetic">
        <td class="mono bold">{{ l.no_compte }}</td>
        <td [class.bold]="l.is_synthetic">{{ l.libelle }}</td>
        <td class="mono">{{ l.so_debiteur  > 0 ? (l.so_debiteur  | number:'1.0-0') : '' }}</td>
        <td class="mono">{{ l.so_crediteur > 0 ? (l.so_crediteur | number:'1.0-0') : '' }}</td>
        <td class="mono success">{{ l.mvt_debit   > 0 ? (l.mvt_debit   | number:'1.0-0') : '' }}</td>
        <td class="mono info">   {{ l.mvt_credit  > 0 ? (l.mvt_credit  | number:'1.0-0') : '' }}</td>
        <td class="mono success">{{ l.sf_debiteur  > 0 ? (l.sf_debiteur  | number:'1.0-0') : '' }}</td>
        <td class="mono info">   {{ l.sf_crediteur > 0 ? (l.sf_crediteur | number:'1.0-0') : '' }}</td>
      </tr>
    </ng-template>
    <ng-template pTemplate="footer" *ngIf="balance()?.totaux">
      <tr class="totaux-row">
        <td colspan="2"><strong>{{ 'comptabilite.totaux' | translate }}</strong></td>
        <td class="mono"><strong>{{ balance().totaux.so_debiteur  | number:'1.0-0' }}</strong></td>
        <td class="mono"><strong>{{ balance().totaux.so_crediteur | number:'1.0-0' }}</strong></td>
        <td class="mono"><strong>{{ balance().totaux.mvt_debit    | number:'1.0-0' }}</strong></td>
        <td class="mono"><strong>{{ balance().totaux.mvt_credit   | number:'1.0-0' }}</strong></td>
        <td class="mono"><strong>{{ balance().totaux.sf_debiteur  | number:'1.0-0' }}</strong></td>
        <td class="mono"><strong>{{ balance().totaux.sf_crediteur | number:'1.0-0' }}</strong></td>
      </tr>
    </ng-template>
  </p-table>
</div>

    <!-- COMPTE DE RÉSULTAT — SIG SYSCOHADA Révisé -->
    <div *ngIf="onglet() === 'resultat' && resultat()">
      <div class="systeme-badge" [class.sn]="resultat().systeme === 'SN'">
        {{ resultat().systeme === 'SN' ? '📊 Système Normal' : '📋 Système Minimal de Trésorerie' }}
        — CAHT : {{ resultat().caht | number:'1.0-0' }} FCFA
      </div>

      <!-- Détail produits / charges côte à côte -->
      <div class="grid-2">
        <div class="card">
          <div class="card-header" style="color:#10b981">💰 {{ 'comptabilite.produits' | translate }}</div>
          <div class="card-body">
            <div class="cr-row" *ngFor="let p of resultat().detail_produits">
              <span>{{ p.libelle }}</span>
              <span class="mono success">{{ p.montant | number:'1.0-0' }} FCFA</span>
            </div>
            <div class="cr-total">
              <span>{{ 'comptabilite.total_produits' | translate }}</span>
              <span class="mono">{{ resultat().total_produits | number:'1.0-0' }} FCFA</span>
            </div>
          </div>
        </div>
        <div class="card">
          <div class="card-header" style="color:#ef4444">💸 {{ 'comptabilite.charges' | translate }}</div>
          <div class="card-body">
            <div class="cr-row" *ngFor="let c of resultat().detail_charges">
              <span>{{ c.libelle }}</span>
              <span class="mono danger">{{ c.montant | number:'1.0-0' }} FCFA</span>
            </div>
            <div class="cr-total">
              <span>{{ 'comptabilite.total_charges' | translate }}</span>
              <span class="mono">{{ resultat().total_charges | number:'1.0-0' }} FCFA</span>
            </div>
          </div>
        </div>
      </div>

      <!-- SIG en cascade -->
      <div class="card" style="margin-bottom:14px">
        <div class="card-header" style="color:#00d4aa">📊 {{ 'comptabilite.sig_titre' | translate }}</div>
        <div class="card-body">
          <div class="sig-row" *ngIf="resultat().sig.ventes_marchandises > 0">
            <span class="sig-label">Ventes de marchandises</span>
            <span class="mono success">{{ resultat().sig.ventes_marchandises | number:'1.0-0' }}</span>
          </div>
          <div class="sig-row" *ngIf="resultat().sig.achats_marchandises > 0">
            <span class="sig-label">— Achats de marchandises</span>
            <span class="mono danger">{{ resultat().sig.achats_marchandises | number:'1.0-0' }}</span>
          </div>
          <div class="sig-subtotal">
            <span>= Marge Commerciale (MC)</span>
            <span class="mono" [style.color]="resultat().sig.mc >= 0 ? '#10b981' : '#ef4444'">
              {{ resultat().sig.mc | number:'1.0-0' }} FCFA</span>
          </div>
          <div class="sig-row">
            <span class="sig-label">+ Production de l'exercice (services)</span>
            <span class="mono success">{{ resultat().sig.production_exercice | number:'1.0-0' }}</span>
          </div>
          <div class="sig-row" *ngIf="resultat().sig.consommations_interm > 0">
            <span class="sig-label">— Consommations intermédiaires</span>
            <span class="mono danger">{{ resultat().sig.consommations_interm | number:'1.0-0' }}</span>
          </div>
          <div class="sig-subtotal">
            <span>= Valeur Ajoutée Brute (VAB)</span>
            <span class="mono" [style.color]="resultat().sig.vab >= 0 ? '#10b981' : '#ef4444'">
              {{ resultat().sig.vab | number:'1.0-0' }} FCFA</span>
          </div>
          <div class="sig-row" *ngIf="resultat().sig.charges_personnel > 0">
            <span class="sig-label">— Charges de personnel (661+662)</span>
            <span class="mono danger">{{ resultat().sig.charges_personnel | number:'1.0-0' }}</span>
          </div>
          <div class="sig-row" *ngIf="resultat().sig.impots_taxes > 0">
            <span class="sig-label">— Impôts et taxes (64x)</span>
            <span class="mono danger">{{ resultat().sig.impots_taxes | number:'1.0-0' }}</span>
          </div>
          <div class="sig-subtotal">
            <span>= Excédent Brut d'Exploitation (EBE)</span>
            <span class="mono" [style.color]="resultat().sig.ebe >= 0 ? '#10b981' : '#ef4444'">
              {{ resultat().sig.ebe | number:'1.0-0' }} FCFA</span>
          </div>
          <div class="sig-row" *ngIf="resultat().sig.dotations_amort > 0">
            <span class="sig-label">— Dotations aux amortissements (681)</span>
            <span class="mono danger">{{ resultat().sig.dotations_amort | number:'1.0-0' }}</span>
          </div>
          <div class="sig-row" *ngIf="resultat().sig.autres_charges > 0">
            <span class="sig-label">— Autres charges d'exploitation</span>
            <span class="mono danger">{{ resultat().sig.autres_charges | number:'1.0-0' }}</span>
          </div>
          <div class="sig-subtotal">
            <span>= Résultat d'Exploitation (RE)</span>
            <span class="mono" [style.color]="resultat().sig.re >= 0 ? '#10b981' : '#ef4444'">
              {{ resultat().sig.re | number:'1.0-0' }} FCFA</span>
          </div>
          <div class="sig-row" *ngIf="resultat().sig.rf !== 0">
            <span class="sig-label">± Résultat Financier (RF)</span>
            <span class="mono">{{ resultat().sig.rf | number:'1.0-0' }}</span>
          </div>
          <div class="sig-subtotal" style="border-top:2px solid #00d4aa">
            <span>= Résultat des Activités Ordinaires (RAO)</span>
            <span class="mono" [style.color]="resultat().sig.rao >= 0 ? '#10b981' : '#ef4444'">
              {{ resultat().sig.rao | number:'1.0-0' }} FCFA</span>
          </div>
          <div class="sig-row" *ngIf="resultat().sig.resultat_hao !== 0">
            <span class="sig-label">± Résultat HAO</span>
            <span class="mono">{{ resultat().sig.resultat_hao | number:'1.0-0' }}</span>
          </div>
          <div class="sig-row" *ngIf="resultat().sig.impot > 0">
            <span class="sig-label">— Impôt sur le résultat (89x)</span>
            <span class="mono danger">{{ resultat().sig.impot | number:'1.0-0' }}</span>
          </div>
        </div>
      </div>

      <div class="resultat-net"
           [style.border-color]="resultat().resultat_net >= 0 ? '#10b981' : '#ef4444'"
           [style.background]="resultat().resultat_net >= 0 ? 'rgba(16,185,129,0.08)' : 'rgba(239,68,68,0.08)'">
        <span>{{ 'comptabilite.resultat_net_ex' | translate }} {{ resultat().exercice }}</span>
        <span class="mono" [style.color]="resultat().resultat_net >= 0 ? '#10b981' : '#ef4444'">
          {{ resultat().resultat_net >= 0 ? '+' : '' }}{{ resultat().resultat_net | number:'1.0-0' }} FCFA
        </span>
      </div>
    </div>

    <!-- BILAN SYSCOHADA Révisé (AUDCIF Art. 7-11 & 23) -->
    <div *ngIf="onglet() === 'bilan' && bilan()">
      <div class="bilan-header">
        <span>📊 {{ 'comptabilite.bilan_titre' | translate }} {{ bilan().exercice }}</span>
        <div style="display:flex;gap:8px;align-items:center">
          <span class="systeme-badge" [class.sn]="bilan().systeme === 'SN'">
            {{ bilan().systeme }} — CAHT {{ bilan().caht | number:'1.0-0' }} FCFA
          </span>
          <span class="equilibre-badge" [class.ok]="bilan().equilibre">
            {{ (bilan().equilibre ? 'comptabilite.equilibre' : 'comptabilite.desequilibre') | translate }}
          </span>
        </div>
      </div>

      <div class="grid-2">
        <!-- ═══════════ ACTIF ═══════════ -->
        <div class="card">
          <div class="card-header" style="color:#0099ff">🏦 {{ 'comptabilite.actif' | translate }}</div>
          <div class="card-body">

            <!-- A — Actif Immobilisé -->
            <div class="bilan-section">A — {{ 'comptabilite.actif_immobilise' | translate }}</div>
            <div class="bilan-subsection">Immobilisations incorporelles</div>
            <div *ngIf="bilan().actif.immobilise.incorporel.length === 0" class="cr-row italic-row">
              <span>Aucune immobilisation incorporelle</span><span class="mono">—</span>
            </div>
            <div class="cr-row" *ngFor="let i of bilan().actif.immobilise.incorporel">
              <span>{{ i.libelle }}</span><span class="mono info">{{ i.montant | number:'1.0-0' }}</span>
            </div>
            <div class="bilan-subsection">Immobilisations corporelles</div>
            <div *ngIf="bilan().actif.immobilise.corporel.length === 0" class="cr-row italic-row">
              <span>Aucune immobilisation corporelle</span><span class="mono">—</span>
            </div>
            <div class="cr-row" *ngFor="let i of bilan().actif.immobilise.corporel">
              <span>{{ i.libelle }}</span><span class="mono info">{{ i.montant | number:'1.0-0' }}</span>
            </div>
            <div class="bilan-subsection">Immobilisations financières</div>
            <div *ngIf="bilan().actif.immobilise.financier.length === 0" class="cr-row italic-row">
              <span>Aucune immobilisation financière</span><span class="mono">—</span>
            </div>
            <div class="cr-row" *ngFor="let i of bilan().actif.immobilise.financier">
              <span>{{ i.libelle }}</span><span class="mono info">{{ i.montant | number:'1.0-0' }}</span>
            </div>
            <div class="bilan-total-masse">
              <span>TOTAL A — Actif Immobilisé</span>
              <span class="mono" style="color:#0099ff">{{ bilan().actif.immobilise.total | number:'1.0-0' }}</span>
            </div>

            <!-- B — Actif Circulant AO -->
            <div class="bilan-section">B — {{ 'comptabilite.actif_circulant' | translate }}</div>
            <div class="cr-row italic-row"><span>Stocks (marchandises, fournitures)</span><span class="mono">—</span></div>
            <div class="cr-row">
              <span>{{ 'comptabilite.creances_clients' | translate }}</span>
              <span class="mono info">{{ bilan().actif.circulant_ao.creances_clients | number:'1.0-0' }}</span>
            </div>
            <div class="bilan-total-masse">
              <span>TOTAL B — Actif Circulant AO</span>
              <span class="mono" style="color:#0099ff">{{ bilan().actif.circulant_ao.total | number:'1.0-0' }}</span>
            </div>

            <!-- C — Actif Circulant HAO -->
            <div class="bilan-section">C — {{ 'comptabilite.actif_circulant_hao' | translate }}</div>
            <div class="cr-row italic-row"><span>Créances HAO</span><span class="mono">—</span></div>
            <div class="bilan-total-masse"><span>TOTAL C</span><span class="mono">0</span></div>

            <!-- D — Trésorerie-Actif -->
            <div class="bilan-section">D — {{ 'comptabilite.tresorerie_actif' | translate }}</div>
            <div *ngIf="bilan().actif.tresorerie_actif.detail.length === 0" class="cr-row italic-row">
              <span>Aucun solde de trésorerie</span><span class="mono">—</span>
            </div>
            <div class="cr-row" *ngFor="let t of bilan().actif.tresorerie_actif.detail">
              <span>{{ t.libelle }}</span><span class="mono info">{{ t.montant | number:'1.0-0' }}</span>
            </div>
            <div class="bilan-total-masse">
              <span>TOTAL D — Trésorerie-Actif</span>
              <span class="mono" style="color:#00d4aa">{{ bilan().actif.tresorerie_actif.total | number:'1.0-0' }}</span>
            </div>

            <!-- E — Écart de conversion -->
            <div class="bilan-section">E — {{ 'comptabilite.ecart_conversion' | translate }}</div>
            <div class="cr-row italic-row"><span>Pertes de change latentes</span><span class="mono">—</span></div>
            <div class="bilan-total-masse"><span>TOTAL E</span><span class="mono">0</span></div>

            <div class="cr-total" style="margin-top:12px">
              <span>{{ 'comptabilite.total_actif' | translate }} (A+B+C+D+E)</span>
              <span class="mono" style="color:#0099ff;font-size:16px">{{ bilan().actif.total_actif | number:'1.0-0' }} FCFA</span>
            </div>
          </div>
        </div>

        <!-- ═══════════ PASSIF ═══════════ -->
        <div class="card">
          <div class="card-header" style="color:#a855f7">📋 {{ 'comptabilite.passif' | translate }}</div>
          <div class="card-body">

            <!-- F — Capitaux Propres & Ressources Assimilées -->
            <div class="bilan-section">F — {{ 'comptabilite.capitaux_propres' | translate }}</div>
            <div class="cr-row">
              <span>{{ 'comptabilite.capital' | translate }}</span>
              <span class="mono" style="color:#a855f7">{{ bilan().passif.capitaux_propres.capital | number:'1.0-0' }}</span>
            </div>
            <div class="cr-row">
              <span>{{ 'comptabilite.resultat_exercice' | translate }}</span>
              <span class="mono" [style.color]="bilan().passif.capitaux_propres.resultat_net >= 0 ? '#10b981' : '#ef4444'">
                {{ bilan().passif.capitaux_propres.resultat_net >= 0 ? '+' : '' }}{{ bilan().passif.capitaux_propres.resultat_net | number:'1.0-0' }}
              </span>
            </div>
            <div class="bilan-total-masse">
              <span>TOTAL F — Capitaux Propres</span>
              <span class="mono" style="color:#a855f7">{{ bilan().passif.capitaux_propres.total | number:'1.0-0' }}</span>
            </div>

            <!-- G — Dettes Financières & Ressources Assimilées -->
            <div class="bilan-section">G — {{ 'comptabilite.dettes_financieres' | translate }}</div>
            <div class="cr-row italic-row" *ngIf="bilan().passif.dettes_financieres.total === 0">
              <span>Emprunts et dettes financières</span><span class="mono">—</span>
            </div>
            <div class="cr-row" *ngIf="bilan().passif.dettes_financieres.total > 0">
              <span>Emprunts et dettes assimilées (16x-19x)</span>
              <span class="mono danger">{{ bilan().passif.dettes_financieres.total | number:'1.0-0' }}</span>
            </div>
            <div class="bilan-total-masse">
              <span>TOTAL G — Dettes Financières</span>
              <span class="mono">{{ bilan().passif.dettes_financieres.total | number:'1.0-0' }}</span>
            </div>

            <!-- H — Passif Circulant AO -->
            <div class="bilan-section">H — {{ 'comptabilite.passif_circulant' | translate }}</div>
            <div class="cr-row">
              <span>{{ 'comptabilite.dettes_fournisseurs' | translate }}</span>
              <span class="mono danger">{{ bilan().passif.passif_circulant_ao.fournisseurs | number:'1.0-0' }}</span>
            </div>
            <div class="cr-row" *ngIf="bilan().passif.passif_circulant_ao.dettes_fiscales > 0">
              <span>Dettes fiscales (44x)</span>
              <span class="mono danger">{{ bilan().passif.passif_circulant_ao.dettes_fiscales | number:'1.0-0' }}</span>
            </div>
            <div class="cr-row" *ngIf="bilan().passif.passif_circulant_ao.dettes_sociales > 0">
              <span>Dettes sociales (43x)</span>
              <span class="mono danger">{{ bilan().passif.passif_circulant_ao.dettes_sociales | number:'1.0-0' }}</span>
            </div>
            <div class="bilan-total-masse">
              <span>TOTAL H — Passif Circulant AO</span>
              <span class="mono" style="color:#ef4444">{{ bilan().passif.passif_circulant_ao.total | number:'1.0-0' }}</span>
            </div>

            <!-- I — Passif Circulant HAO -->
            <div class="bilan-section">I — {{ 'comptabilite.passif_circulant_hao' | translate }}</div>
            <div class="cr-row italic-row"><span>Dettes HAO</span><span class="mono">—</span></div>
            <div class="bilan-total-masse"><span>TOTAL I</span><span class="mono">0</span></div>

            <!-- J — Trésorerie-Passif -->
            <div class="bilan-section">J — {{ 'comptabilite.tresorerie_passif' | translate }}</div>
            <div *ngIf="bilan().passif.tresorerie_passif.detail.length === 0" class="cr-row italic-row">
              <span>Aucun découvert bancaire</span><span class="mono">—</span>
            </div>
            <div class="cr-row" *ngFor="let t of bilan().passif.tresorerie_passif.detail">
              <span>{{ t.libelle }}</span><span class="mono danger">{{ t.montant | number:'1.0-0' }}</span>
            </div>
            <div class="bilan-total-masse">
              <span>TOTAL J — Trésorerie-Passif</span>
              <span class="mono danger">{{ bilan().passif.tresorerie_passif.total | number:'1.0-0' }}</span>
            </div>

            <!-- K — Écart de conversion -->
            <div class="bilan-section">K — {{ 'comptabilite.ecart_conversion' | translate }}</div>
            <div class="cr-row italic-row"><span>Gains de change latents</span><span class="mono">—</span></div>
            <div class="bilan-total-masse"><span>TOTAL K</span><span class="mono">0</span></div>

            <div class="cr-total" style="margin-top:12px">
              <span>{{ 'comptabilite.total_passif' | translate }} (F+G+H+I+J+K)</span>
              <span class="mono" style="color:#a855f7;font-size:16px">{{ bilan().passif.total_passif | number:'1.0-0' }} FCFA</span>
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
        <div class="card-header">⚙️ {{ 'comptabilite.flux_exploitation' | translate }}</div>
        <div class="card-body">
          <div class="cr-row">
            <span>{{ 'comptabilite.encaissements' | translate }}</span>
            <span class="mono success">+{{ flux().flux_exploitation.encaissements_clients | number:'1.0-0' }}</span>
          </div>
          <div class="cr-row">
            <span>{{ 'comptabilite.decaissements' | translate }}</span>
            <span class="mono danger">-{{ flux().flux_exploitation.decaissements_charges | number:'1.0-0' }}</span>
          </div>
          <div class="flux-total" [style.color]="flux().flux_exploitation.flux_net >= 0 ? '#10b981' : '#ef4444'">
            <span>{{ 'comptabilite.flux_net_exploit' | translate }}</span>
            <span class="mono">{{ flux().flux_exploitation.flux_net >= 0 ? '+' : '' }}{{ flux().flux_exploitation.flux_net | number:'1.0-0' }} FCFA</span>
          </div>
        </div>
      </div>

      <!-- Flux investissement -->
      <div class="card" style="margin-bottom:14px">
        <div class="card-header">🏗️ {{ 'comptabilite.flux_investissement' | translate }}</div>
        <div class="card-body">
          <div class="cr-row"><span>{{ 'comptabilite.acquisitions' | translate }}</span><span class="mono">0</span></div>
          <div class="cr-row"><span>{{ 'comptabilite.cessions'     | translate }}</span><span class="mono">0</span></div>
          <div class="flux-total" style="color:#64748b">
            <span>{{ 'comptabilite.flux_net_invest' | translate }}</span><span class="mono">0 FCFA</span>
          </div>
        </div>
      </div>

      <!-- Flux financement -->
      <div class="card" style="margin-bottom:14px">
        <div class="card-header">💼 {{ 'comptabilite.flux_financement' | translate }}</div>
        <div class="card-body">
          <div class="cr-row">
            <span>{{ 'comptabilite.apports_capital' | translate }}</span>
            <span class="mono success">+{{ flux().flux_financement.apports_capital | number:'1.0-0' }}</span>
          </div>
          <div class="flux-total" style="color:#10b981">
            <span>{{ 'comptabilite.flux_net_finance' | translate }}</span>
            <span class="mono">+{{ flux().flux_financement.flux_net | number:'1.0-0' }} FCFA</span>
          </div>
        </div>
      </div>

      <!-- Trésorerie nette -->
      <div class="tresorerie-box">
        <div class="tb-row">
          <span>{{ 'comptabilite.treso_ouverture' | translate }}</span>
          <span class="mono">{{ flux().tresorerie.solde_initial | number:'1.0-0' }} FCFA</span>
        </div>
        <div class="tb-row">
          <span>{{ 'comptabilite.variation_nette' | translate }}</span>
          <span class="mono" [style.color]="flux().tresorerie.variation >= 0 ? '#10b981' : '#ef4444'">
            {{ flux().tresorerie.variation >= 0 ? '+' : '' }}{{ flux().tresorerie.variation | number:'1.0-0' }} FCFA
          </span>
        </div>
        <div class="tb-final">
          <span>{{ 'comptabilite.treso_cloture' | translate }}</span>
          <span class="mono" style="color:#00d4aa">{{ flux().tresorerie.solde_final | number:'1.0-0' }} FCFA</span>
        </div>
      </div>

      <!-- Flux mensuels -->
      <div class="card" *ngIf="flux().flux_mensuels?.length > 0">
        <div class="card-header">📅 {{ 'comptabilite.flux_mensuels' | translate }}</div>
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
        <div class="ea-badge">📅 {{ 'comptabilite.exercice_en_cours' | translate }}</div>
        <div class="ea-annee">{{ historique().exercice_actif.annee_scolaire }}</div>
        <div class="ea-dates">
          {{ historique().exercice_actif.date_debut | date:'dd/MM/yyyy' }}
          → {{ historique().exercice_actif.date_fin | date:'dd/MM/yyyy' }}
        </div>
      </div>

      <!-- Historique clôturés -->
      <div class="section-title-hist">
        📚 {{ 'comptabilite.exercices_clotures' | translate }} ({{ historique()?.nb_exercices_clotures || 0 }})
      </div>

      <div *ngIf="historique()?.historique?.length === 0" class="empty-msg" style="padding:40px;text-align:center">
        {{ 'comptabilite.aucun_cloture' | translate }}
      </div>

      <div class="table-card" *ngIf="historique()?.historique?.length > 0">
        <p-table [value]="historique().historique" styleClass="p-datatable-sm">
          <ng-template pTemplate="header">
            <tr>
              <th>{{ 'comptabilite.annee_scolaire'   | translate }}</th>
              <th>{{ 'comptabilite.periode'          | translate }}</th>
              <th>{{ 'comptabilite.date_cloture'     | translate }}</th>
              <th>{{ 'comptabilite.nb_eleves'        | translate }}</th>
              <th class="text-right">{{ 'comptabilite.total_recettes'    | translate }}</th>
              <th class="text-right">{{ 'comptabilite.total_charges_hist'| translate }}</th>
              <th class="text-right">{{ 'comptabilite.resultat_net'      | translate }}</th>
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
              <td colspan="4" class="bold">{{ 'comptabilite.total_cumule' | translate }}</td>
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
          <!-- Charges -->
      <div class="table-card" *ngIf="onglet() === 'charges'">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
          <div>
            <h3 style="margin:0;color:#e8f0fe">💸 {{ 'comptabilite.charges_exercice' | translate }}</h3>
            <span style="color:#64748b;font-size:12px">
              {{ 'comptabilite.total_label' | translate }} {{ totalCharges() | number:'1.0-0' }} FCFA
            </span>
          </div>
          <p-button [label]="'comptabilite.nouvelle_charge' | translate" severity="danger" (onClick)="ouvrirDialogCharge()" />
        </div>

        <p-table [value]="charges()" [loading]="loadingCharges()"
                [paginator]="true" [rows]="20" styleClass="p-datatable-sm">
          <ng-template pTemplate="header">
            <tr>
              <th>{{ 'comptabilite.date'     | translate }}</th>
              <th>{{ 'comptabilite.no_piece' | translate }}</th>
              <th>{{ 'comptabilite.no_compte'| translate }}</th>
              <th>{{ 'comptabilite.libelle'  | translate }}</th>
              <th align="right">{{ 'common.total' | translate }}</th>
            </tr>
          </ng-template>
          <ng-template pTemplate="body" let-c>
            <tr>
              <td>{{ c.date | date:'dd/MM/yyyy' }}</td>
              <td class="mono">{{ c.no_piece }}</td>
              <td class="mono">{{ c.no_compte }}</td>
              <td>{{ c.libelle }}</td>
              <td class="mono danger" align="right">{{ c.montant | number:'1.0-0' }} FCFA</td>
            </tr>
          </ng-template>
          <ng-template pTemplate="emptymessage">
            <tr><td colspan="5" class="empty-msg">{{ 'comptabilite.aucune_charge' | translate }}</td></tr>
          </ng-template>
        </p-table>
      </div>

  <!-- NOTES ANNEXES -->
  <div *ngIf="onglet() === 'notes' && notesAnnexes()">
    <div class="systeme-badge" [class.sn]="notesAnnexes().systeme === 'SN'" style="margin-bottom:16px">
      📎 Notes Annexes — {{ notesAnnexes().systeme === 'SN' ? 'Système Normal' : 'Système Minimal de Trésorerie' }}
      — Exercice {{ notesAnnexes().exercice }}
    </div>

    <!-- Note 1 — Présentation de l'entité -->
    <div class="card" style="margin-bottom:14px">
      <div class="card-header" style="color:#00d4aa">Note 1 — Présentation de l'entité</div>
      <div class="card-body">
        <div class="cr-row"><span>Secteur d'activité</span><span class="mono">{{ notesAnnexes().note1.secteur }}</span></div>
        <div class="cr-row"><span>Référentiel comptable applicable</span><span class="mono">{{ notesAnnexes().note1.referentiel }}</span></div>
        <div class="cr-row"><span>Exercice</span><span class="mono">{{ notesAnnexes().date_debut | date:'dd/MM/yyyy' }} → {{ notesAnnexes().date_fin | date:'dd/MM/yyyy' }}</span></div>
        <div class="cr-row"><span>Nombre d'élèves inscrits</span><span class="mono">{{ notesAnnexes().note1.nb_eleves }}</span></div>
        <div class="cr-row"><span>Nombre de paiements enregistrés</span><span class="mono">{{ notesAnnexes().note1.nb_paiements }}</span></div>
        <div class="cr-row"><span>CAHT de l'exercice</span><span class="mono success">{{ notesAnnexes().caht | number:'1.0-0' }} FCFA</span></div>
        <div class="cr-row"><span>Seuil SMT (services)</span><span class="mono">{{ notesAnnexes().seuil_smt | number:'1.0-0' }} FCFA</span></div>
        <div style="margin-top:12px;font-size:11px;color:#64748b">Répartition par section :</div>
        <div class="cr-row" *ngFor="let s of notesAnnexes().note1.sections">
          <span style="padding-left:12px">└ {{ s.nom }}</span><span class="mono">{{ s.nb }} élèves</span>
        </div>
      </div>
    </div>

    <!-- Note 2 — Méthodes et principes comptables -->
    <div class="card" style="margin-bottom:14px">
      <div class="card-header" style="color:#00d4aa">Note 2 — Méthodes et principes comptables</div>
      <div class="card-body">
        <div class="cr-row"><span>Base d'évaluation</span><span class="mono">{{ notesAnnexes().note2.base_evaluation }}</span></div>
        <div class="cr-row"><span>Amortissements</span><span class="mono">{{ notesAnnexes().note2.amortissement }}</span></div>
        <div class="cr-row"><span>Créances clients</span><span class="mono">{{ notesAnnexes().note2.creances }}</span></div>
        <div class="cr-row"><span>Trésorerie</span><span class="mono">{{ notesAnnexes().note2.tresorerie }}</span></div>
        <div class="cr-row"><span>Méthode de comptabilisation</span><span class="mono">{{ notesAnnexes().note2.comptabilite }}</span></div>
      </div>
    </div>

    <div class="grid-2">
      <!-- Note 3 — Charges de personnel -->
      <div class="card">
        <div class="card-header" style="color:#00d4aa">Note 3 — Charges de personnel</div>
        <div class="card-body">
          <div class="cr-row"><span>Masse salariale (661+662)</span><span class="mono danger">{{ notesAnnexes().note3.masse_salariale | number:'1.0-0' }} FCFA</span></div>
          <div class="cr-row"><span>Total charges de l'exercice</span><span class="mono danger">{{ notesAnnexes().note3.total_charges | number:'1.0-0' }} FCFA</span></div>
        </div>
      </div>

      <!-- Note 4 — Trésorerie de clôture -->
      <div class="card">
        <div class="card-header" style="color:#00d4aa">Note 4 — Trésorerie de clôture</div>
        <div class="card-body">
          <div class="cr-row" *ngFor="let t of notesAnnexes().note4.comptes">
            <span>{{ t.libelle }} ({{ t.compte }})</span>
            <span class="mono" [style.color]="t.solde >= 0 ? '#10b981' : '#ef4444'">{{ t.solde | number:'1.0-0' }} FCFA</span>
          </div>
          <div *ngIf="notesAnnexes().note4.comptes.length === 0" class="cr-row italic-row">
            <span>Aucun solde de trésorerie</span>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Dialog Nouvelle Charge -->
  <p-dialog [header]="'💸 ' + ('comptabilite.nouvelle_charge' | translate)" [(visible)]="dialogChargeVisible"
            [modal]="true" [style]="{width:'460px'}" [draggable]="false">
    <div class="form-grid">
      <div class="form-group full">
        <label>{{ 'comptabilite.compte_charge' | translate }} *</label>
        <p-select [options]="planCharges" [(ngModel)]="nouvelleCharge.no_compte"
                  optionLabel="label" optionValue="value" styleClass="w-full"
                  (onChange)="onCompteChargeChange()" />
      </div>
      <div class="form-group full">
        <label>{{ 'comptabilite.libelle' | translate }} *</label>
        <input pInputText [(ngModel)]="nouvelleCharge.libelle" class="w-full"
              [placeholder]="'comptabilite.ex_libelle' | translate" />
      </div>
      <div class="form-group">
        <label>{{ 'comptabilite.montant_fcfa' | translate }} *</label>
        <p-inputNumber [(ngModel)]="nouvelleCharge.montant" [min]="0"
                      mode="decimal" styleClass="w-full" />
      </div>
      <div class="form-group">
        <label>{{ 'comptabilite.date' | translate }}</label>
        <input pInputText type="date" [(ngModel)]="nouvelleCharge.date" class="w-full" />
      </div>
      <div class="form-group full">
        <label>{{ 'comptabilite.compte_fournisseur' | translate }}</label>
        <p-select [options]="planFournisseurs" [(ngModel)]="nouvelleCharge.compte_fournisseur"
                  optionLabel="label" optionValue="value" styleClass="w-full" />
      </div>
      <div class="form-group full">
        <label>{{ 'comptabilite.regle_via' | translate }}</label>
        <p-select [options]="comptesCredit" [(ngModel)]="nouvelleCharge.compte_credit"
                  optionLabel="label" optionValue="value" styleClass="w-full" />
      </div>
    </div>
    <ng-template pTemplate="footer">
      <p-button [label]="'common.annuler'    | translate" severity="secondary" (onClick)="dialogChargeVisible=false" />
      <p-button [label]="'common.enregistrer'| translate" severity="danger"
                [loading]="savingCharge()" (onClick)="sauvegarderCharge()" />
    </ng-template>
  </p-dialog>
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
    .bilan-section        { font-size:11px; color:#00d4aa; text-transform:uppercase; letter-spacing:1px; margin:14px 0 4px; font-weight:600; border-bottom:1px solid rgba(0,212,170,0.2); padding-bottom:4px; }
    .bilan-subsection     { font-size:10px; color:#64748b; text-transform:uppercase; letter-spacing:0.5px; margin:8px 0 2px; }
    .bilan-total-masse    { display:flex; justify-content:space-between; padding:6px 0; font-size:12px; font-weight:700; color:#e8f0fe; background:rgba(0,0,0,0.15); margin:2px -18px; padding:6px 18px; }
    .italic-row span:first-child { font-style:italic; color:#475569; }
    ::ng-deep .synthetic-row td { background:rgba(0,212,170,0.06) !important; border-top:1px solid rgba(0,212,170,0.25) !important; }
    .systeme-badge   { display:inline-block; font-size:11px; padding:4px 12px; border-radius:20px; background:rgba(100,116,139,0.2); color:#64748b; }
    .systeme-badge.sn { background:rgba(0,212,170,0.15); color:#00d4aa; }
    .sig-row      { display:flex; justify-content:space-between; padding:5px 0; font-size:12px; color:#94a3b8; border-bottom:1px solid rgba(42,63,95,0.2); }
    .sig-label    { color:#94a3b8; padding-left:16px; }
    .sig-subtotal { display:flex; justify-content:space-between; padding:8px 0; font-size:13px; font-weight:700; color:#e8f0fe; border-top:1px solid #2a3f5f; margin-top:4px; }

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
  notesAnnexes   = signal<any>(null);
  systeme        = signal<string>('SN');
  loadingJournal = signal(true);
  loadingGL      = signal(true);
  loadingBalance = signal(true);
  charges        = signal<any[]>([]);
loadingCharges = signal(false);
savingCharge   = signal(false);
dialogChargeVisible = false;
nouvelleCharge = {
    no_compte:          '661',
    libelle:            '',
    montant:            0,
    date:               new Date().toISOString().split('T')[0],
    compte_credit:      '571',
    compte_fournisseur: '401',
};
planCharges = [
    { label: '── CHARGES D\'EXPLOITATION ──', value: '' },
    { label: '601 — Achats de marchandises',          value: '601' },
    { label: '604 — Achats de fournitures',           value: '604' },
    { label: '606 — Eau, électricité, fournitures',   value: '606' },
    { label: '611 — Transports',                      value: '611' },
    { label: '612 — Loyer',                           value: '612' },
    { label: '613 — Locations diverses',              value: '613' },
    { label: '621 — Personnel extérieur',             value: '621' },
    { label: '622 — Rémunérations intermédiaires',    value: '622' },
    { label: '623 — Publicité',                       value: '623' },
    { label: '624 — Transport du personnel',          value: '624' },
    { label: '625 — Déplacements et missions',        value: '625' },
    { label: '631 — Frais bancaires',                 value: '631' },
    { label: '641 — Impôts et taxes',                 value: '641' },
    { label: '661 — Salaires',                        value: '661' },
    { label: '662 — Charges sociales (IPRES/CSS)',    value: '662' },
    { label: '681 — Dotations aux amortissements',    value: '681' },
    { label: '── ACQUISITIONS D\'IMMOBILISATIONS ──', value: '' },
    { label: '221 — Bâtiments',                       value: '221' },
    { label: '231 — Matériel et outillage',           value: '231' },
    { label: '241 — Mobilier',                        value: '241' },
    { label: '244 — Matériel informatique',           value: '244' },
    { label: '245 — Matériel de transport',           value: '245' },
];
planFournisseurs = [
    { label: '401 — Fournisseurs (dettes en compte)',           value: '401' },
    { label: '404 — Fournisseurs, acquisitions immobilisations', value: '404' },
    { label: '481 — Fournisseurs d\'immobilisations',           value: '481' },
];
comptesCredit = [
    { label: '571  — Caisse',        value: '571' },
    { label: '521  — Banque',        value: '521' },
    { label: '5521 — WAVE',          value: '5521' },
    { label: '5522 — Orange Money',  value: '5522' },
    { label: '5523 — Free Money',    value: '5523' },
];

  private translate = inject(TranslateService);

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
      next: res => {
        this.bilan.set(res);
        if (res?.systeme) this.systeme.set(res.systeme);
      }
    });
    this.compta.getNotesAnnexes().subscribe({
      next: res => this.notesAnnexes.set(res)
    });
    this.compta.getTableauFlux().subscribe({
      next: res => this.flux.set(res)
    });
    this.compta.getHistorique().subscribe({
      next: res => this.historique.set(res)
    });
    this.chargerCharges();
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
      alert(this.translate.instant('comptabilite.export_indispo'));
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

  chargerCharges() {
    this.loadingCharges.set(true);
    this.compta.getCharges().subscribe({
        next: res => { this.charges.set(Array.isArray(res) ? res : []); this.loadingCharges.set(false); },
        error: () => this.loadingCharges.set(false)
    });
}

  ouvrirDialogCharge() {
      this.nouvelleCharge = {
          no_compte: '661', libelle: '', montant: 0,
          date: new Date().toISOString().split('T')[0],
          compte_credit: '571', compte_fournisseur: '401',
      };
      this.dialogChargeVisible = true;
  }

  onCompteChargeChange() {
      const no = this.nouvelleCharge.no_compte || '';
      // Auto-sélection du compte fournisseur selon la nature de la charge
      if (no.startsWith('2')) {
          // Acquisition immobilisation → 404
          this.nouvelleCharge.compte_fournisseur = '404';
      } else if (no === '681') {
          // Dotation amortissement → 481 (provision interne)
          this.nouvelleCharge.compte_fournisseur = '481';
      } else {
          // Charge d'exploitation → 401
          this.nouvelleCharge.compte_fournisseur = '401';
      }
  }

  sauvegarderCharge() {
      if (!this.nouvelleCharge.libelle || this.nouvelleCharge.montant <= 0) return;
      this.savingCharge.set(true);
      this.compta.creerCharge(this.nouvelleCharge).subscribe({
          next: () => {
              this.dialogChargeVisible = false;
              this.savingCharge.set(false);
              this.chargerCharges();
              this.compta.getCompteResultat().subscribe({ next: res => this.resultat.set(res) });
          },
          error: () => this.savingCharge.set(false)
      });
  }

  totalCharges(): number {
      return this.charges().reduce((s, c) => s + (c.montant || 0), 0);
  }
}
