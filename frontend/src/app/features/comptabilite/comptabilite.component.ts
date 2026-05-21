import { Component, NgModule, OnInit, computed, inject, signal } from '@angular/core';
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
              (click)="chargerJournal(); onglet.set('journal')">📒 {{ 'comptabilite.journal'     | translate }}</button>
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
      <button class="tab-btn" [class.active]="onglet() === 'plan'"
        (click)="chargerPlan(); onglet.set('plan')">📋 Plan Comptable</button>
      <button class="tab-btn" [class.active]="onglet() === 'budget'"
        (click)="chargerBudget(); onglet.set('budget')">🎯 Budget</button>
      <button class="tab-btn" [class.active]="onglet() === 'investissement'"
        (click)="chargerImmobilisations(); onglet.set('investissement')">🏗️ Investissement</button>
    </div>

    <!-- JOURNAL -->
    <div class="table-card" *ngIf="onglet() === 'journal'">
      <!-- Filtre source -->
      <div style="display:flex;gap:10px;padding:10px 16px 0;align-items:center">
        <span style="font-size:11px;color:#64748b;text-transform:uppercase">Filtrer :</span>
        <button class="src-btn" [class.active]="filtreSource === ''"     (click)="filtrerJournal('')">Tout</button>
        <button class="src-btn paie" [class.active]="filtreSource === 'PAIE'"    (click)="filtrerJournal('PAIE')">💰 Paie</button>
        <button class="src-btn pmt"  [class.active]="filtreSource === 'PAIEMENT'" (click)="filtrerJournal('PAIEMENT')">🎓 Scolarité</button>
        <button class="src-btn chg"  [class.active]="filtreSource === 'CHARGE'"  (click)="filtrerJournal('CHARGE')">📋 Charges</button>
        <button class="src-btn ava"  [class.active]="filtreSource === 'AVANCE'"  (click)="filtrerJournal('AVANCE')">💸 Avances</button>
        <button class="src-btn inv"  [class.active]="filtreSource === 'INVEST'"  (click)="filtrerJournal('INVEST')">🏗️ Investissement</button>
        <button class="src-btn amt"  [class.active]="filtreSource === 'AMORT'"   (click)="filtrerJournal('AMORT')">📉 Amortissements</button>
        <span style="margin-left:auto;font-size:11px;color:#64748b">{{ journal().length }} écritures</span>
      </div>
      <p-table [value]="journal()" [loading]="loadingJournal()"
               styleClass="p-datatable-sm" [paginator]="true" [rows]="25">
        <ng-template pTemplate="header">
          <tr>
            <th>Source</th>
            <th>{{ 'comptabilite.date'     | translate }}</th>
            <th>{{ 'comptabilite.no_piece' | translate }}</th>
            <th>{{ 'comptabilite.no_compte'| translate }}</th>
            <th>Compte (libellé)</th>
            <th>{{ 'comptabilite.libelle'  | translate }}</th>
            <th>{{ 'comptabilite.debit'    | translate }}</th>
            <th>{{ 'comptabilite.credit'   | translate }}</th>
          </tr>
        </ng-template>
        <ng-template pTemplate="body" let-e>
          <tr>
            <td>
              <p-tag [value]="e.source"
                     [severity]="e.source === 'PAIEMENT' ? 'success'
                               : e.source === 'PAIE'     ? 'info'
                               : e.source === 'AVANCE'   ? 'warn'
                               : 'secondary'" />
            </td>
            <td class="mono">{{ e.date | date:'dd/MM/yyyy' }}</td>
            <td class="mono">{{ e.no_piece }}</td>
            <td class="mono bold">{{ e.no_compte }}</td>
            <td style="font-size:11px;color:#64748b">{{ e.libelle_compte }}</td>
            <td style="font-size:11px">{{ e.libelle }}</td>
            <td class="mono success">{{ e.debit  > 0 ? (e.debit  | number:'1.0-0') : '—' }}</td>
            <td class="mono info">   {{ e.credit > 0 ? (e.credit | number:'1.0-0') : '—' }}</td>
          </tr>
        </ng-template>
        <ng-template pTemplate="emptymessage">
          <tr><td colspan="8" class="empty-msg">{{ 'comptabilite.aucune_ecriture' | translate }}</td></tr>
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
    <div *ngIf="onglet() === 'resultat' && resultat() !== null">
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

  <!-- ════════════════ PLAN COMPTABLE ════════════════ -->
  <div class="table-card" *ngIf="onglet() === 'plan'">
    <div style="display:flex;justify-content:space-between;align-items:center;padding:14px 16px">
      <div style="display:flex;gap:8px;align-items:center">
        <span style="color:#e8f0fe;font-weight:600">Plan comptable SYSCOHADA Révisé</span>
        <span style="font-size:11px;color:#64748b">({{ planComptable().length }} comptes)</span>
      </div>
      <div style="display:flex;gap:8px">
        <p-select [options]="classesFiltres" [(ngModel)]="filtreClasse"
                  (onChange)="filtrerPlan()" [showClear]="true"
                  placeholder="Classe" styleClass="filter-sel" />
        <p-select [options]="typesFiltres" [(ngModel)]="filtreType"
                  (onChange)="filtrerPlan()" [showClear]="true"
                  placeholder="Type" styleClass="filter-sel" />
        <p-button label="+ Compte" severity="success" size="small" (onClick)="ouvrirDialogCompte()" />
      </div>
    </div>
    <p-table [value]="planComptable()" [loading]="loadingPlan()"
             styleClass="p-datatable-sm" [paginator]="true" [rows]="30"
             [globalFilterFields]="['no_compte','libelle']">
      <ng-template pTemplate="header">
        <tr>
          <th style="width:100px">N° Compte</th>
          <th>Libellé</th>
          <th style="width:80px">Classe</th>
          <th style="width:100px">Type</th>
          <th style="width:80px">Statut</th>
          <th style="width:90px">Actions</th>
        </tr>
      </ng-template>
      <ng-template pTemplate="body" let-c>
        <tr [class.compte-inactif]="!c.est_actif">
          <td class="mono bold">{{ c.no_compte }}</td>
          <td [class.bold]="c.no_compte.length <= 2">
            {{ c.libelle }}
            <span *ngIf="c.est_systeme" class="badge-sys">SYS</span>
            <span *ngIf="c.est_personnalise && !c.est_systeme" class="badge-custom">✎</span>
          </td>
          <td class="mono text-center">{{ c.classe }}</td>
          <td>
            <p-tag [value]="c.type"
                   [severity]="c.type === 'CHARGE' ? 'danger' : c.type === 'PRODUIT' ? 'success' : 'info'" />
          </td>
          <td>
            <p-tag [value]="c.est_actif ? 'Actif' : 'Inactif'"
                   [severity]="c.est_actif ? 'success' : 'secondary'" />
          </td>
          <td>
            <div class="btn-row">
              <p-button icon="pi pi-pencil" [rounded]="true" [text]="true" severity="info"
                        (onClick)="ouvrirDialogCompte(c)" pTooltip="Modifier" />
              <p-button *ngIf="!c.est_systeme" icon="pi pi-trash" [rounded]="true" [text]="true" severity="danger"
                        (onClick)="supprimerCompte(c)" pTooltip="Supprimer" />
            </div>
          </td>
        </tr>
      </ng-template>
    </p-table>
  </div>

  <!-- ════════════════ BUDGET ════════════════ -->
  <div class="budget-card" *ngIf="onglet() === 'budget'">
    <div class="budget-header">
      <div>
        <h3 class="budget-title">🎯 Budget Prévisionnel — {{ budget()?.exercice }}</h3>
        <span style="font-size:12px;color:#64748b">Charges fixes et variables · Prévision vs Réalisé</span>
      </div>
      <p-button label="+ Ligne budget" severity="success" (onClick)="ouvrirDialogBudget()" />
    </div>

    <!-- KPIs budget -->
    <div class="kpi-grid" *ngIf="budget()?.totaux">
      <div class="kpi-card" style="--acc:#0099ff">
        <div class="kpi-label">Charges Fixes Prévues</div>
        <div class="kpi-value" style="color:#0099ff">{{ budget()!.totaux.fixe.prevu | number:'1.0-0' }}</div>
        <div class="kpi-sub">Réalisé : {{ budget()!.totaux.fixe.realise | number:'1.0-0' }}</div>
      </div>
      <div class="kpi-card" style="--acc:#f59e0b">
        <div class="kpi-label">Charges Variables Prévues</div>
        <div class="kpi-value" style="color:#f59e0b">{{ budget()!.totaux.variable.prevu | number:'1.0-0' }}</div>
        <div class="kpi-sub">Réalisé : {{ budget()!.totaux.variable.realise | number:'1.0-0' }}</div>
      </div>
      <div class="kpi-card" style="--acc:#00d4aa">
        <div class="kpi-label">Total Charges Prévues</div>
        <div class="kpi-value" style="color:#00d4aa">{{ budget()!.totaux.total.prevu | number:'1.0-0' }}</div>
        <div class="kpi-sub">Réalisé : {{ budget()!.totaux.total.realise | number:'1.0-0' }}</div>
      </div>
      <div class="kpi-card" style="--acc:#10b981">
        <div class="kpi-label">Taux de Réalisation Global</div>
        <div class="kpi-value" [style.color]="txRealisation() >= 100 ? '#ef4444' : '#10b981'">
          {{ txRealisation() }} %
        </div>
      </div>
    </div>

    <!-- Tableau budget -->
    <div class="budget-table-wrap" *ngIf="budget()?.lignes?.length">
      <table class="budget-tbl">
        <thead>
          <tr>
            <th class="compte-col">Compte</th>
            <th class="libelle-col">Libellé</th>
            <th class="type-col">Type</th>
            <th *ngFor="let m of budget()!.mois_noms" class="mois-col">{{ m }}</th>
            <th class="total-col">Prévu</th>
            <th class="total-col realise-col">Réalisé</th>
            <th class="pct-col">%</th>
            <th style="width:50px"></th>
          </tr>
        </thead>
        <tbody>
          <tr *ngFor="let l of budget()!.lignes" [class.ligne-depasse]="l.total_realise > l.total_prevu">
            <td class="mono bold">{{ l.no_compte }}</td>
            <td>{{ l.libelle }}</td>
            <td>
              <p-tag [value]="l.type_charge === 'FIXE' ? 'Fixe' : 'Variable'"
                     [severity]="l.type_charge === 'FIXE' ? 'info' : 'warn'" />
            </td>
            <td *ngFor="let m of l.mois" class="mois-cell">
              <span class="prevu-val">{{ m.prevu | number:'1.0-0' }}</span>
              <span class="realise-small" *ngIf="m.realise > 0">{{ m.realise | number:'1.0-0' }}</span>
            </td>
            <td class="mono bold total-prevu">{{ l.total_prevu | number:'1.0-0' }}</td>
            <td class="mono bold" [class.over-budget]="l.total_realise > l.total_prevu">{{ l.total_realise | number:'1.0-0' }}</td>
            <td class="pct-cell" [class.over-budget]="l.taux_realisation > 100">{{ l.taux_realisation }} %</td>
            <td>
              <p-button icon="pi pi-pencil" [rounded]="true" [text]="true" severity="warn"
                        pTooltip="Modifier" (onClick)="ouvrirModifierBudget(l)" />
              <p-button icon="pi pi-trash" [rounded]="true" [text]="true" severity="danger"
                        pTooltip="Supprimer" (onClick)="supprimerBudgetLigne(l)" />
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div *ngIf="!budget()?.lignes?.length && !loadingBudget()" class="empty-msg" style="padding:40px">
      Aucune ligne de budget — ajoutez des postes de dépense
    </div>
  </div>

  <!-- Dialog Plan Comptable -->
  <p-dialog [header]="formCompte.no_compte ? 'Modifier compte ' + formCompte.no_compte : '+ Nouveau Compte'"
            [(visible)]="dialogCompteVisible" [modal]="true" [style]="{width:'480px'}" [draggable]="false">
    <div class="form-grid" style="grid-template-columns:1fr 1fr">
      <div class="form-group">
        <label>N° Compte *</label>
        <input pInputText [(ngModel)]="formCompte.no_compte" class="w-full" [disabled]="editCompteMode" />
      </div>
      <div class="form-group">
        <label>Classe (1-9)</label>
        <p-select [options]="classeOptions" [(ngModel)]="formCompte.classe"
                  optionLabel="label" optionValue="value" styleClass="w-full" />
      </div>
      <div class="form-group" style="grid-column:1/-1">
        <label>Libellé *</label>
        <input pInputText [(ngModel)]="formCompte.libelle" class="w-full" />
      </div>
      <div class="form-group" style="grid-column:1/-1">
        <label>Type de compte</label>
        <p-select [options]="typesCompte" [(ngModel)]="formCompte.type"
                  optionLabel="label" optionValue="value" styleClass="w-full" />
      </div>
    </div>
    <ng-template pTemplate="footer">
      <p-button label="Annuler" severity="secondary" (onClick)="dialogCompteVisible=false" />
      <p-button label="Enregistrer" severity="success" [loading]="savingCompte()" (onClick)="sauvegarderCompte()" />
    </ng-template>
  </p-dialog>

  <!-- INVESTISSEMENT -->
  <div *ngIf="onglet() === 'investissement'">
    <!-- KPIs -->
    <div class="kpi-grid" style="margin-bottom:16px">
      <div class="kpi-card" style="--acc:#7c3aed">
        <div class="kpi-icon">🏗️</div>
        <div class="kpi-label">Valeur Brute Totale</div>
        <div class="kpi-value" style="color:#7c3aed">{{ (immobilisations()?.synthese?.total_brut || 0) | number:'1.0-0' }}</div>
        <div class="kpi-sub">FCFA</div>
      </div>
      <div class="kpi-card" style="--acc:#ef4444">
        <div class="kpi-icon">📉</div>
        <div class="kpi-label">Cumul Amortissements</div>
        <div class="kpi-value" style="color:#ef4444">{{ (immobilisations()?.synthese?.total_amort || 0) | number:'1.0-0' }}</div>
        <div class="kpi-sub">FCFA</div>
      </div>
      <div class="kpi-card" style="--acc:#10b981">
        <div class="kpi-icon">💎</div>
        <div class="kpi-label">Valeur Nette Comptable</div>
        <div class="kpi-value" style="color:#10b981">{{ (immobilisations()?.synthese?.total_vnc || 0) | number:'1.0-0' }}</div>
        <div class="kpi-sub">FCFA</div>
      </div>
      <div class="kpi-card" style="--acc:#00d4aa">
        <div class="kpi-icon">📦</div>
        <div class="kpi-label">Nombre de Biens</div>
        <div class="kpi-value" style="color:#00d4aa">{{ immobilisations()?.synthese?.nb_biens || 0 }}</div>
        <div class="kpi-sub">immobilisations</div>
      </div>
    </div>

    <div class="table-card">
      <div class="table-toolbar">
        <span class="tbl-count">🏗️ Immobilisations</span>
        <p-button label="+ Ajouter un bien" severity="success" (onClick)="ouvrirDialogImmo()" />
      </div>
      <p-table [value]="immobilisations()?.immobilisations || []" [loading]="loadingImmo()"
               styleClass="p-datatable-sm" [paginator]="true" [rows]="15">
        <ng-template pTemplate="header">
          <tr>
            <th>N° Bien</th>
            <th>Libellé</th>
            <th>Compte</th>
            <th>Date entrée</th>
            <th class="text-right">Valeur brute</th>
            <th class="text-right">Cumul amort.</th>
            <th class="text-right">VNC</th>
            <th class="text-right">Taux</th>
            <th class="text-right">Annuité</th>
            <th>Statut</th>
            <th>Actions</th>
          </tr>
        </ng-template>
        <ng-template pTemplate="body" let-i>
          <tr>
            <td class="mono bold">{{ i.no_bien }}</td>
            <td>{{ i.libelle }}</td>
            <td class="mono" style="font-size:10px">{{ i.no_compte_immobilisation }} — {{ i.libelle_compte_immo }}</td>
            <td>{{ i.date_entree }}</td>
            <td class="mono text-right">{{ i.valeur_entree | number:'1.0-0' }}</td>
            <td class="mono text-right" style="color:#ef4444">{{ i.cumul_amortissements | number:'1.0-0' }}</td>
            <td class="mono text-right" style="color:#10b981;font-weight:700">{{ i.valeur_nette_comptable | number:'1.0-0' }}</td>
            <td class="mono text-right">{{ i.taux_amortissement }} %</td>
            <td class="mono text-right">{{ i.annuite_amortissement | number:'1.0-0' }}</td>
            <td>
              <p-tag *ngIf="i.est_amorti" value="Amorti"  severity="secondary" />
              <p-tag *ngIf="!i.est_amorti" value="Actif" severity="success" />
            </td>
            <td>
              <div class="btn-row">
                <p-button icon="pi pi-calculator" [rounded]="true" [text]="true" severity="info"
                          pTooltip="Enregistrer dotation" [disabled]="i.est_amorti"
                          (onClick)="ouvrirDialogAmortir(i)" />
                <p-button icon="pi pi-pencil" [rounded]="true" [text]="true" severity="warn"
                          pTooltip="Modifier" (onClick)="ouvrirDialogImmo(i)" />
                <p-button icon="pi pi-trash" [rounded]="true" [text]="true" severity="danger"
                          pTooltip="Supprimer" (onClick)="supprimerImmo(i)" />
              </div>
            </td>
          </tr>
        </ng-template>
        <ng-template pTemplate="emptymessage">
          <tr><td colspan="11" class="empty-msg">Aucune immobilisation — cliquez sur "+ Ajouter un bien"</td></tr>
        </ng-template>
      </p-table>
    </div>
  </div>

  <!-- Dialog Immobilisation -->
  <p-dialog [header]="editImmoMode ? '✏️ Modifier un bien' : '🏗️ Ajouter une immobilisation'"
            [(visible)]="dialogImmoVisible" [modal]="true" [style]="{width:'560px'}" [draggable]="false">
    <div class="form-grid">
      <div class="form-group full">
        <label>Libellé *</label>
        <input pInputText [(ngModel)]="formImmo.libelle" class="w-full" placeholder="Ex: Ordinateur portable Dell" />
      </div>
      <div class="form-group">
        <label>Compte immobilisation *</label>
        <p-select [options]="comptesImmo" optionLabel="label" optionValue="value"
                  [(ngModel)]="formImmo.no_compte_immobilisation"
                  (onChange)="onImmoCompteChange()" styleClass="w-full" />
      </div>
      <div class="form-group">
        <label>Compte amortissement</label>
        <p-select [options]="comptesAmort" optionLabel="label" optionValue="value"
                  [(ngModel)]="formImmo.no_compte_amortissement" styleClass="w-full" />
      </div>
      <div class="form-group">
        <label>Valeur d'entrée (FCFA) *</label>
        <p-inputNumber [(ngModel)]="formImmo.valeur_entree" [min]="1" mode="decimal" styleClass="w-full" />
      </div>
      <div class="form-group">
        <label>Durée d'utilisation (années) *</label>
        <p-inputNumber [(ngModel)]="formImmo.duree_utilisation" [min]="1" [max]="50" mode="decimal" styleClass="w-full" />
      </div>
      <div class="form-group">
        <label>Date d'entrée</label>
        <input pInputText type="date" [(ngModel)]="formImmo.date_entree" class="w-full" />
      </div>
      <div class="form-group">
        <label>Mode d'amortissement</label>
        <p-select [options]="[{label:'Linéaire',value:'LINEAIRE'},{label:'Dégressif',value:'DEGRESSIF'}]"
                  optionLabel="label" optionValue="value"
                  [(ngModel)]="formImmo.mode_amortissement" styleClass="w-full" />
      </div>
      <div class="form-group full" *ngIf="formImmo.valeur_entree && formImmo.duree_utilisation">
        <div style="background:#111827;border-radius:6px;padding:10px;font-size:11px;color:#94a3b8">
          Taux : <strong style="color:#00d4aa">{{ (100 / formImmo.duree_utilisation) | number:'1.2-2' }} %</strong> &nbsp;|&nbsp;
          Annuité : <strong style="color:#00d4aa">{{ (formImmo.valeur_entree / formImmo.duree_utilisation) | number:'1.0-0' }} FCFA</strong>
        </div>
      </div>
    </div>
    <ng-template pTemplate="footer">
      <p-button label="Annuler" severity="secondary" (onClick)="dialogImmoVisible=false" />
      <p-button [label]="editImmoMode ? 'Mettre à jour' : 'Enregistrer'" severity="success"
                [loading]="savingImmo()" (onClick)="sauvegarderImmo()" />
    </ng-template>
  </p-dialog>

  <!-- Dialog Amortissement -->
  <p-dialog header="📉 Enregistrer une dotation aux amortissements"
            [(visible)]="dialogAmortirVisible" [modal]="true" [style]="{width:'440px'}" [draggable]="false">
    @if (immoAAmortir()) {
      <div class="employe-banner" style="margin-bottom:14px">
        <div class="eb-name">{{ immoAAmortir()!.no_bien }} — {{ immoAAmortir()!.libelle }}</div>
        <div style="font-size:11px;color:#64748b;margin-top:4px">
          VNC actuelle : <strong style="color:#10b981">{{ immoAAmortir()!.valeur_nette_comptable | number:'1.0-0' }} FCFA</strong>
        </div>
      </div>
      <div class="form-grid">
        <div class="form-group full">
          <label>Montant de la dotation (FCFA)</label>
          <p-inputNumber [(ngModel)]="formAmortir.montant" [min]="1" mode="decimal" styleClass="w-full" />
          <span style="font-size:10px;color:#64748b">Annuité théorique : {{ immoAAmortir()!.annuite_amortissement | number:'1.0-0' }} FCFA</span>
        </div>
        <div class="form-group full">
          <label>Date d'écriture</label>
          <input pInputText type="date" [(ngModel)]="formAmortir.date" class="w-full" />
        </div>
      </div>
    }
    <ng-template pTemplate="footer">
      <p-button label="Annuler" severity="secondary" (onClick)="dialogAmortirVisible=false" />
      <p-button label="Enregistrer la dotation" severity="warn"
                [loading]="savingImmo()" (onClick)="enregistrerAmortissement()" />
    </ng-template>
  </p-dialog>

  <!-- Dialog Ligne Budget -->
  <p-dialog [header]="editBudgetMode ? '✏️ Modifier Ligne Budget' : '🎯 Nouvelle Ligne Budget'"
            [(visible)]="dialogBudgetVisible" [modal]="true" [style]="{width:'700px'}" [draggable]="false">
    <div class="form-grid" style="grid-template-columns:1fr 1fr">
      <div class="form-group">
        <label>N° Compte *</label>
        <p-select [options]="planComptableCharges()" optionLabel="label" optionValue="value"
                  [(ngModel)]="formBudget.no_compte" (onChange)="onBudgetCompteChange($event)"
                  [filter]="true" filterBy="label" styleClass="w-full"
                  placeholder="Sélectionner un compte" />
      </div>
      <div class="form-group">
        <label>Type</label>
        <p-select [options]="[{label:'Charge fixe',value:'FIXE'},{label:'Charge variable',value:'VARIABLE'}]"
                  [(ngModel)]="formBudget.type_charge" optionLabel="label" optionValue="value" styleClass="w-full" />
      </div>
      <div class="form-group" style="grid-column:1/-1">
        <label>Libellé</label>
        <input pInputText [(ngModel)]="formBudget.libelle" class="w-full" />
      </div>
    </div>
    <!-- Répartition mensuelle -->
    <div style="margin-top:14px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <span style="font-size:11px;color:#64748b;text-transform:uppercase;font-weight:600">Montants mensuels (FCFA)</span>
        <p-button label="Répliquer Jan sur tous" severity="secondary" size="small" (onClick)="repliquerMontant()" />
      </div>
      <div class="mois-grid">
        <div *ngFor="let m of moisLabels; let i = index" class="mois-input-cell">
          <label>{{ m }}</label>
          <p-inputNumber [(ngModel)]="formBudget['m' + (i+1).toString().padStart(2,'0')]"
                         [min]="0" mode="decimal" styleClass="mois-inp" />
        </div>
      </div>
    </div>
    <ng-template pTemplate="footer">
      <p-button label="Annuler" severity="secondary" (onClick)="dialogBudgetVisible=false" />
      <p-button label="Enregistrer" severity="success" [loading]="savingBudget()" (onClick)="sauvegarderBudget()" />
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
    .src-btn { border:1px solid #2a3f5f; border-radius:6px; background:transparent; color:#64748b; font-size:11px; padding:4px 10px; cursor:pointer; }
    .src-btn.active, .src-btn:hover { background:#1e2d45; color:#e8f0fe; }
    .src-btn.paie.active  { color:#38bdf8; border-color:#38bdf8; }
    .src-btn.pmt.active   { color:#10b981; border-color:#10b981; }
    .src-btn.chg.active   { color:#94a3b8; border-color:#94a3b8; }
    .src-btn.ava.active   { color:#f59e0b; border-color:#f59e0b; }
    .src-btn.inv.active   { color:#7c3aed; border-color:#7c3aed; }
    .src-btn.amt.active   { color:#ef4444; border-color:#ef4444; }
    /* Plan comptable */
    .compte-inactif td { opacity:0.45; }
    .badge-sys    { font-size:9px; background:#7c3aed; color:white; padding:1px 5px; border-radius:3px; margin-left:6px; }
    .badge-custom { font-size:10px; color:#00d4aa; margin-left:4px; }
    .text-center  { text-align:center; }
    /* Budget */
    .budget-card   { background:#1e2d45; border:1px solid #2a3f5f; border-radius:12px; padding:20px; }
    .budget-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:16px; }
    .budget-title  { font-size:16px; font-weight:600; color:#e8f0fe; margin:0 0 4px; }
    .budget-table-wrap { overflow-x:auto; margin-top:14px; }
    .budget-tbl    { width:100%; border-collapse:collapse; font-size:11px; }
    .budget-tbl th { background:#111827; color:#64748b; font-size:10px; text-transform:uppercase; padding:6px 8px; text-align:left; white-space:nowrap; border-bottom:2px solid #2a3f5f; }
    .budget-tbl td { padding:5px 8px; border-bottom:1px solid rgba(42,63,95,0.3); color:#94a3b8; vertical-align:middle; }
    .mois-col      { width:70px; text-align:right; }
    .total-col     { width:90px; text-align:right; font-weight:700; }
    .realise-col   { color:#00d4aa; }
    .pct-col       { width:60px; text-align:center; }
    .mois-cell     { text-align:right; }
    .prevu-val     { display:block; color:#e8f0fe; }
    .realise-small { display:block; font-size:9px; color:#00d4aa; }
    .total-prevu   { color:#e8f0fe; }
    .over-budget   { color:#ef4444; }
    .ligne-depasse { background:rgba(239,68,68,0.04); }
    .mois-grid { display:grid; grid-template-columns:repeat(6,1fr); gap:8px; }
    .mois-input-cell { display:flex; flex-direction:column; gap:4px; }
    .mois-input-cell label { font-size:10px; color:#64748b; text-align:center; }
    .mois-inp { width:100%; }
    .btn-row { display:flex; gap:4px; }
  `]
})
export class ComptabiliteComponent implements OnInit {
  onglet         = signal('journal');
  filtreSource   = '';
  journal        = signal<any[]>([]);
  grandLivre     = signal<any[]>([]);
  balance        = signal<any>(null);
  // Plan comptable
  planComptable     = signal<any[]>([]);
  loadingPlan       = signal(false);
  savingCompte      = signal(false);
  dialogCompteVisible = false;
  editCompteMode    = false;
  filtreClasse      = '';
  filtreType        = '';
  formCompte: any   = {};
  // Budget
  budget            = signal<any>(null);
  loadingBudget     = signal(false);
  savingBudget      = signal(false);
  dialogBudgetVisible = false;
  editBudgetMode      = false;
  formBudget: any   = {};

  // Investissement
  immobilisations    = signal<any>(null);
  loadingImmo        = signal(false);
  savingImmo         = signal(false);
  dialogImmoVisible  = false;
  editImmoMode       = false;
  dialogAmortirVisible = false;
  immoAAmortir       = signal<any | null>(null);
  formImmo: any      = {};
  formAmortir: any   = {};

  comptesImmo = [
    { label: '211 — Terrains',                     value: '211'  },
    { label: '221 — Bâtiments',                    value: '221'  },
    { label: '231 — Matériel et outillage',        value: '231'  },
    { label: '241 — Mobilier',                     value: '241'  },
    { label: '244 — Matériel informatique',        value: '244'  },
    { label: '245 — Matériel de transport',        value: '245'  },
    { label: '248 — Autres immobilisations',       value: '248'  },
  ];
  comptesAmort = [
    { label: '2811 — Amort. Terrains',             value: '2811' },
    { label: '2821 — Amort. Bâtiments',            value: '2821' },
    { label: '2831 — Amort. Matériel/outillage',   value: '2831' },
    { label: '2841 — Amort. Mobilier',             value: '2841' },
    { label: '2844 — Amort. Matériel informatique',value: '2844' },
    { label: '2845 — Amort. Matériel transport',   value: '2845' },
    { label: '2848 — Amort. Autres immo.',         value: '2848' },
  ];
  private immoAmortMap: Record<string, string> = {
    '211': '2811', '221': '2821', '231': '2831',
    '241': '2841', '244': '2844', '245': '2845', '248': '2848',
  };
  txRealisation     = computed(() => {
    const t = this.budget()?.totaux?.total;
    if (!t || !t.prevu) return 0;
    return Math.round(t.realise / t.prevu * 100);
  });
  planComptableCharges = computed(() =>
    this.planComptable()
      .filter(c => c.type === 'CHARGE' && c.est_actif)
      .map(c => ({ label: `${c.no_compte} — ${c.libelle}`, value: c.no_compte, libelle: c.libelle }))
  );
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

  moisLabels = ['Jan','Fév','Mar','Avr','Mai','Jun','Jul','Aoû','Sep','Oct','Nov','Déc'];
  classesFiltres = [1,2,3,4,5,6,7,8,9].map(i => ({label:`Classe ${i}`, value: String(i)}));
  typesFiltres   = [
    {label:'Bilan',   value:'BILAN'},
    {label:'Charge',  value:'CHARGE'},
    {label:'Produit', value:'PRODUIT'},
  ];
  typesCompte    = [
    {label:'Compte de bilan',   value:'BILAN'},
    {label:'Compte de charge',  value:'CHARGE'},
    {label:'Compte de produit', value:'PRODUIT'},
  ];
  classeOptions  = [1,2,3,4,5,6,7,8,9].map(i => ({label:`Classe ${i}`, value: i}));

  constructor(private compta: ComptabiliteService) {}

  // ── Plan comptable ─────────────────────────────────────────────────────────
  chargerPlan() {
    this.loadingPlan.set(true);
    const p: Record<string, string> = {};
    if (this.filtreClasse) p['classe'] = this.filtreClasse;
    if (this.filtreType)   p['type']   = this.filtreType;
    this.compta.getPlanComptable(p).subscribe({
      next: r => { this.planComptable.set(r); this.loadingPlan.set(false); },
      error: () => this.loadingPlan.set(false),
    });
  }

  filtrerPlan() { this.chargerPlan(); }

  ouvrirDialogCompte(c?: any) {
    this.editCompteMode = !!c;
    this.formCompte = c
      ? { no_compte: c.no_compte, libelle: c.libelle, type: c.type, classe: c.classe }
      : { no_compte: '', libelle: '', type: 'CHARGE', classe: 6 };
    this.dialogCompteVisible = true;
  }

  sauvegarderCompte() {
    if (!this.formCompte.no_compte || !this.formCompte.libelle) return;
    this.savingCompte.set(true);
    const obs = this.editCompteMode
      ? this.compta.modifierCompte(this.formCompte.no_compte, this.formCompte)
      : this.compta.creerCompte(this.formCompte);
    obs.subscribe({
      next: () => {
        this.dialogCompteVisible = false;
        this.savingCompte.set(false);
        this.filtreClasse = '';
        this.filtreType   = '';
        this.chargerPlan();
      },
      error: () => this.savingCompte.set(false),
    });
  }

  supprimerCompte(c: any) {
    if (!confirm(`Supprimer le compte ${c.no_compte} — ${c.libelle} ?`)) return;
    this.compta.supprimerCompte(c.no_compte).subscribe({ next: () => this.chargerPlan() });
  }

  // ── Budget ──────────────────────────────────────────────────────────────────
  chargerBudget() {
    this.loadingBudget.set(true);
    this.compta.getBudget().subscribe({
      next: r => { this.budget.set(r); this.loadingBudget.set(false); },
      error: () => this.loadingBudget.set(false),
    });
  }

  ouvrirDialogBudget() {
    this.editBudgetMode = false;
    const base: any = { no_compte: '', libelle: '', type_charge: 'FIXE' };
    for (let i = 1; i <= 12; i++) base[`m${String(i).padStart(2,'0')}`] = 0;
    this.formBudget = base;
    this.dialogBudgetVisible = true;
    if (!this.planComptable().length) this.chargerPlan();
  }

  ouvrirModifierBudget(l: any) {
    this.editBudgetMode = true;
    this.formBudget = { ...l };
    for (let i = 1; i <= 12; i++) {
      const k = `m${String(i).padStart(2,'0')}`;
      if (this.formBudget[k] === undefined) this.formBudget[k] = 0;
    }
    this.dialogBudgetVisible = true;
    if (!this.planComptable().length) this.chargerPlan();
  }

  onBudgetCompteChange(ev: any) {
    const c = this.planComptableCharges().find(x => x.value === ev.value);
    if (c) this.formBudget.libelle = c.libelle;
  }

  repliquerMontant() {
    const m1 = this.formBudget['m01'] || 0;
    for (let i = 2; i <= 12; i++) this.formBudget[`m${String(i).padStart(2,'0')}`] = m1;
  }

  sauvegarderBudget() {
    if (!this.formBudget.no_compte) return;
    this.savingBudget.set(true);
    this.compta.sauvegarderBudgetLigne(this.formBudget).subscribe({
      next: () => { this.dialogBudgetVisible = false; this.savingBudget.set(false); this.chargerBudget(); },
      error: () => this.savingBudget.set(false),
    });
  }

  supprimerBudgetLigne(l: any) {
    if (!confirm(`Supprimer la ligne budget ${l.no_compte} ?`)) return;
    this.compta.supprimerBudgetLigne(l.id).subscribe({ next: () => this.chargerBudget() });
  }

  chargerJournal(source = this.filtreSource) {
    this.loadingJournal.set(true);
    const params = source ? { source } : undefined;
    this.compta.getJournal(params).subscribe({
      next: res => { this.journal.set(res); this.loadingJournal.set(false); },
      error: () => this.loadingJournal.set(false),
    });
  }

  filtrerJournal(source: string) {
    this.filtreSource = source;
    this.chargerJournal(source);
  }

  ngOnInit() {
    this.chargerJournal();
    this.chargerBalance();
    this.chargerResultat();
    this.compta.getGrandLivre().subscribe({
      next:  res => { this.grandLivre.set(res); this.loadingGL.set(false); },
      error: ()  => this.loadingGL.set(false),
    });
    this.compta.getBilan().subscribe({
      next:  res => { this.bilan.set(res); if (res?.systeme) this.systeme.set(res.systeme); },
      error: ()  => {},
    });
    this.compta.getNotesAnnexes().subscribe({ next: res => this.notesAnnexes.set(res), error: () => {} });
    this.compta.getTableauFlux().subscribe({  next: res => this.flux.set(res),          error: () => {} });
    this.compta.getHistorique().subscribe({   next: res => this.historique.set(res),    error: () => {} });
    this.chargerCharges();
  }

  // ── Investissement ──────────────────────────────────────────────────────────
  chargerImmobilisations() {
    this.loadingImmo.set(true);
    this.compta.getImmobilisations().subscribe({
      next:  r => { this.immobilisations.set(r); this.loadingImmo.set(false); },
      error: () => this.loadingImmo.set(false),
    });
  }

  ouvrirDialogImmo(i?: any) {
    this.editImmoMode = !!i;
    const today = new Date().toISOString().split('T')[0];
    this.formImmo = i ? { ...i } : {
      libelle: '', valeur_entree: 0, duree_utilisation: 5,
      date_entree: today, mode_amortissement: 'LINEAIRE',
      no_compte_immobilisation: '231', no_compte_amortissement: '2831',
    };
    this.dialogImmoVisible = true;
  }

  onImmoCompteChange() {
    const mapped = this.immoAmortMap[this.formImmo.no_compte_immobilisation];
    if (mapped) this.formImmo.no_compte_amortissement = mapped;
  }

  sauvegarderImmo() {
    if (!this.formImmo.libelle || !this.formImmo.valeur_entree) return;
    this.savingImmo.set(true);
    const obs = this.editImmoMode
      ? this.compta.modifierImmobilisation(this.formImmo.id, this.formImmo)
      : this.compta.creerImmobilisation(this.formImmo);
    obs.subscribe({
      next: () => {
        this.dialogImmoVisible = false;
        this.savingImmo.set(false);
        this.chargerImmobilisations();
        this.chargerJournal();
      },
      error: () => this.savingImmo.set(false),
    });
  }

  supprimerImmo(i: any) {
    if (!confirm(`Supprimer ${i.no_bien} — ${i.libelle} ?`)) return;
    this.compta.supprimerImmobilisation(i.id).subscribe({ next: () => this.chargerImmobilisations() });
  }

  ouvrirDialogAmortir(i: any) {
    this.immoAAmortir.set(i);
    this.formAmortir = {
      montant: i.annuite_amortissement,
      date:    new Date().toISOString().split('T')[0],
    };
    this.dialogAmortirVisible = true;
  }

  enregistrerAmortissement() {
    const i = this.immoAAmortir();
    if (!i || !this.formAmortir.montant) return;
    this.savingImmo.set(true);
    this.compta.amortirImmobilisation(i.id, this.formAmortir).subscribe({
      next: () => {
        this.dialogAmortirVisible = false;
        this.savingImmo.set(false);
        this.chargerImmobilisations();
        this.chargerJournal();
      },
      error: () => this.savingImmo.set(false),
    });
  }

  chargerBalance() {
    this.loadingBalance.set(true);
    this.compta.getBalance().subscribe({
      next:  res => { this.balance.set(res); this.loadingBalance.set(false); },
      error: ()  => { this.balance.set({ lignes: [], totaux: {} }); this.loadingBalance.set(false); },
    });
  }

  chargerResultat() {
    this.compta.getCompteResultat().subscribe({
      next:  res => this.resultat.set(res),
      error: ()  => this.resultat.set({}),
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
