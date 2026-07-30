import {
  ChangeDetectionStrategy, Component, OnInit, computed, inject, signal
} from '@angular/core';
import { DecimalPipe, SlicePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/services/api.service';
import { ElevesService } from '../../core/services/eleves.service';
import { TableModule }       from 'primeng/table';
import { ButtonModule }      from 'primeng/button';
import { TagModule }         from 'primeng/tag';
import { AutoCompleteModule }from 'primeng/autocomplete';
import { TranslateModule }   from '@ngx-translate/core';
import { Eleve } from '../../core/models/eleve.model';

@Component({
  selector: 'app-suivi-mensuel',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    DecimalPipe, SlicePipe, FormsModule,
    TableModule, ButtonModule, TagModule, AutoCompleteModule, TranslateModule,
  ],
  template: `
<div class="page-header">
  <div>
    <h2 class="page-title">📅 {{ 'suivi.title' | translate }}</h2>
    <span class="page-sub">{{ synthese()?.exercice }} — {{ 'suivi.subtitle' | translate }}</span>
  </div>
  <button class="btn-refresh" (click)="chargerTout()">↻ Actualiser</button>
</div>

<!-- ── Synthèse globale ── -->
@if (loading()) {
  <div class="empty-state">⏳ Chargement...</div>
}
@if (!loading() && globalData().length === 0) {
  <div class="empty-state">
    <div style="font-size:32px">📅</div>
    <div style="color:var(--text-3);margin-top:8px">Aucun exercice actif ou aucun paiement enregistré.</div>
    <div style="font-size:11px;color:var(--text-5);margin-top:4px">Créez un exercice et enregistrez des paiements pour voir les données.</div>
  </div>
}
@if (!loading()) {
  <div class="kpi-grid">
    <div class="kpi-card" style="--acc:#00d4aa">
      <div class="kpi-icon">👩‍🎓</div>
      <div class="kpi-label">{{ 'suivi.nb_inscrits' | translate }}</div>
      <div class="kpi-value" style="color:#00d4aa">{{ synthese()!.nb_eleves }}</div>
    </div>
    <div class="kpi-card" style="--acc:#0099ff">
      <div class="kpi-icon">🧾</div>
      <div class="kpi-label">{{ 'suivi.total_attendu' | translate }}</div>
      <div class="kpi-value" style="color:#0099ff">{{ synthese()!.total_attendu | number:'1.0-0' }}</div>
      <div class="kpi-sub">FCFA attendus</div>
    </div>
    <div class="kpi-card" style="--acc:#10b981">
      <div class="kpi-icon">✅</div>
      <div class="kpi-label">{{ 'suivi.total_encaisse' | translate }}</div>
      <div class="kpi-value" style="color:#10b981">{{ synthese()!.total_paye | number:'1.0-0' }}</div>
      <div class="kpi-sub">FCFA encaissés</div>
    </div>
    <div class="kpi-card" style="--acc:#ef4444">
      <div class="kpi-icon">⚠️</div>
      <div class="kpi-label">{{ 'suivi.reste_global' | translate }}</div>
      <div class="kpi-value" style="color:#ef4444">{{ synthese()!.reste | number:'1.0-0' }}</div>
      <div class="kpi-sub">FCFA impayés</div>
    </div>
    <div class="kpi-card" style="--acc:#a855f7">
      <div class="kpi-icon">📊</div>
      <div class="kpi-label">{{ 'suivi.taux_recouvrement' | translate }}</div>
      <div class="kpi-value" [style.color]="synthese()!.taux_recouvrement >= 80 ? '#10b981' : synthese()!.taux_recouvrement >= 50 ? '#f59e0b' : '#ef4444'">
        {{ synthese()!.taux_recouvrement }} %
      </div>
      <div class="progress-mini">
        <div class="pm-fill" [style.width.%]="synthese()!.taux_recouvrement"
             [style.background]="synthese()!.taux_recouvrement >= 80 ? '#10b981' : synthese()!.taux_recouvrement >= 50 ? '#f59e0b' : '#ef4444'">
        </div>
      </div>
    </div>
  </div>
}

<!-- ── Onglets ── -->
@if (!loading()) {
<div class="tabs-bar">
  <button class="tab-btn" [class.active]="onglet() === 'global'"
          (click)="onglet.set('global')">📊 Évolution mensuelle</button>
  <button class="tab-btn" [class.active]="onglet() === 'sections'"
          (click)="onglet.set('sections')">🏫 Par section</button>
  <button class="tab-btn" [class.active]="onglet() === 'creances'"
          (click)="onglet.set('creances')">⚠️ Créances
    @if (creances().length > 0) {
      <span class="badge-count">{{ creances().length }}</span>
    }
  </button>
  <button class="tab-btn" [class.active]="onglet() === 'charges'"
          (click)="onglet.set('charges')">💸 Charges &amp; Marge</button>
  <button class="tab-btn" [class.active]="onglet() === 'eleve'"
          (click)="onglet.set('eleve')">👤 Par élève</button>
</div>

<!-- ════ VUE GLOBALE MENSUELLE ════ -->
@if (onglet() === 'global') {

  <!-- ════ SCOLARITÉ ATTENDUE PAR MOIS ════
       Le suivi ne montrait que l'encaissé : utile pour constater, inutile pour
       décider. Ce tableau dit ce que l'école DEVRAIT rentrer chaque mois
       d'après la situation de chaque élève (prorata d'entrée, prise en charge,
       montants saisis à la main). La source est l'échéancier, celle qui fait
       déjà foi sur la fiche et les relances : la prévision ne peut pas
       contredire ce qu'on réclame réellement aux familles. -->
  @if (moisAvecPrevision().length) {
    <div class="table-card" style="margin-bottom:18px">
      <div class="prev-header">
        <div>
          <h3 class="prev-title">📆 Scolarité à encaisser par mois</h3>
          <span class="prev-sub">Mensualités et services mensuels dus — hors frais d'entrée</span>
        </div>
        <div class="prev-total">
          <span class="prev-total-lib">Reste à encaisser sur l'année</span>
          <strong class="mono">{{ totalScolariteReste() | number:'1.0-0' }} FCFA</strong>
        </div>
      </div>
      <p-table [value]="moisAvecPrevision()" styleClass="p-datatable-sm" [showGridlines]="true">
        <ng-template pTemplate="header">
          <tr>
            <th>Mois</th>
            <th class="tr">Élèves concernés</th>
            <th class="tr">Envisagé</th>
            <th class="tr">Encaissé</th>
            <th class="tr">Reste</th>
            <th class="tr">Taux</th>
          </tr>
        </ng-template>
        <ng-template pTemplate="body" let-m>
          <tr>
            <td class="bold">{{ m.mois }}</td>
            <td class="mono tr">{{ m.nb_eleves_dus }}</td>
            <td class="mono tr bold">{{ m.scolarite_prevue | number:'1.0-0' }}</td>
            <td class="mono tr teal">{{ m.scolarite_encaissee | number:'1.0-0' }}</td>
            <td class="mono tr" [class.red]="m.scolarite_reste > 0">
              {{ m.scolarite_reste | number:'1.0-0' }}
            </td>
            <td class="mono tr">{{ tauxMois(m) }} %</td>
          </tr>
        </ng-template>
        <ng-template pTemplate="footer">
          <tr>
            <td class="bold">TOTAL EXERCICE</td>
            <td></td>
            <td class="mono tr bold">{{ totalScolaritePrevue() | number:'1.0-0' }}</td>
            <td class="mono tr bold teal">{{ totalScolariteEncaissee() | number:'1.0-0' }}</td>
            <td class="mono tr bold red">{{ totalScolariteReste() | number:'1.0-0' }}</td>
            <td></td>
          </tr>
        </ng-template>
      </p-table>
    </div>
  }

  <!-- Graphique en barres -->
  @if (globalData().length > 0) {
    <div class="bar-section">
      <div class="bs-header">
        <span class="bs-title">Encaissements mensuels — {{ synthese()?.exercice }}</span>
        <span class="bs-total">Total : {{ totalGlobal() | number:'1.0-0' }} FCFA</span>
      </div>
      <div class="bars-wrap">
        @for (m of globalData(); track m.mois_num) {
          <div class="bar-item" [class.bar-active]="m.total > 0">
            <div class="bar-amount">
              @if (m.total > 0) {
                {{ m.total | number:'1.0-0' }}
              }
            </div>
            <div class="bar-track">
              <div class="bar-fill"
                   [style.height.%]="maxMensuel() > 0 ? (m.total / maxMensuel()) * 100 : 0"
                   [class.bar-fill-active]="m.total > 0">
              </div>
            </div>
            <div class="bar-label">{{ m.mois_court }}</div>
            <div class="bar-nb" [class.nb-active]="m.nb > 0">{{ m.nb > 0 ? m.nb + ' pal.' : '' }}</div>
          </div>
        }
      </div>
    </div>
  }

  <!-- Tableau mensuel -->
  <div class="table-card">
    <p-table [value]="globalData()" [loading]="loading()" styleClass="p-datatable-sm" [showGridlines]="true">
      <ng-template pTemplate="header">
        <tr>
          <th>Mois</th>
          <th class="tr">Nb Paiements</th>
          <th class="tr">{{ 'suivi.inscription_col' | translate }}</th>
          <th class="tr">{{ 'suivi.mensualite_col'  | translate }}</th>
          <th class="tr">{{ 'suivi.uniforme_col'    | translate }}</th>
          <th class="tr">{{ 'suivi.fournitures_col' | translate }}</th>
          <th class="tr">{{ 'suivi.cantine_col'     | translate }}</th>
          <th class="tr">{{ 'suivi.services_col'    | translate }}</th>
          <th class="tr">Total Mois</th>
          <th class="tr">Cumul</th>
        </tr>
      </ng-template>
      <ng-template pTemplate="body" let-m>
        <tr [class.row-empty]="m.total === 0" [class.row-active]="m.total > 0">
          <td class="bold">{{ m.mois }}</td>
          <td class="mono tr">{{ m.nb > 0 ? m.nb : '—' }}</td>
          <td class="mono tr">{{ m.inscription > 0 ? (m.inscription | number:'1.0-0') : '—' }}</td>
          <td class="mono tr">{{ m.mensualite > 0  ? (m.mensualite  | number:'1.0-0') : '—' }}</td>
          <td class="mono tr">{{ m.uniforme > 0    ? (m.uniforme    | number:'1.0-0') : '—' }}</td>
          <td class="mono tr">{{ m.fournitures > 0 ? (m.fournitures | number:'1.0-0') : '—' }}</td>
          <td class="mono tr">{{ m.cantine > 0     ? (m.cantine     | number:'1.0-0') : '—' }}</td>
          <td class="mono tr">{{ m.services > 0    ? (m.services    | number:'1.0-0') : '—' }}</td>
          <td class="mono tr bold" [class.teal]="m.total > 0">
            {{ m.total > 0 ? (m.total | number:'1.0-0') : '—' }}
          </td>
          <td class="mono tr" style="color:#a855f7">{{ cumulJusquau(m) | number:'1.0-0' }}</td>
        </tr>
      </ng-template>
      <ng-template pTemplate="footer">
        <tr>
          <td class="bold">TOTAL EXERCICE</td>
          <td class="mono tr bold">{{ nbTransactions() }}</td>
          <td colspan="6"></td>
          <td class="mono tr bold teal">{{ totalGlobal() | number:'1.0-0' }}</td>
          <td></td>
        </tr>
      </ng-template>
      <ng-template pTemplate="emptymessage">
        <tr><td colspan="10" class="empty-msg">{{ 'suivi.aucun_paiement' | translate }}</td></tr>
      </ng-template>
    </p-table>
  </div>
}

<!-- ════ PAR SECTION ════ -->
@if (onglet() === 'sections') {
  <div class="table-card">
    <p-table [value]="sections()" [loading]="loading()" styleClass="p-datatable-sm">
      <ng-template pTemplate="header">
        <tr>
          <th>Section</th>
          <th class="tr">Effectif</th>
          <th class="tr">Total Attendu</th>
          <th class="tr">Total Encaissé</th>
          <th class="tr">Reste à Payer</th>
          <th style="width:200px">Taux de Recouvrement</th>
        </tr>
      </ng-template>
      <ng-template pTemplate="body" let-s>
        <tr>
          <td class="bold">{{ s.nom }}</td>
          <td class="mono tr">{{ s.nb_eleves }}</td>
          <td class="mono tr">{{ s.total_attendu | number:'1.0-0' }}</td>
          <td class="mono tr success">{{ s.total_paye | number:'1.0-0' }}</td>
          <td class="mono tr danger">{{ s.reste | number:'1.0-0' }}</td>
          <td>
            <div class="taux-row">
              <div class="taux-bar-track">
                <div class="taux-bar-fill"
                     [style.width.%]="s.taux"
                     [style.background]="s.taux >= 80 ? '#10b981' : s.taux >= 50 ? '#f59e0b' : '#ef4444'">
                </div>
              </div>
              <span class="taux-val" [class.success]="s.taux >= 80" [class.warn-txt]="s.taux >= 50 && s.taux < 80" [class.danger]="s.taux < 50">
                {{ s.taux }} %
              </span>
            </div>
          </td>
        </tr>
      </ng-template>
      <ng-template pTemplate="emptymessage">
        <tr><td colspan="6" class="empty-msg">Aucune section</td></tr>
      </ng-template>
    </p-table>
  </div>
}

<!-- ════ CRÉANCES ════ -->
@if (onglet() === 'creances') {
  <div class="table-card">
    <div style="padding:12px 16px;display:flex;justify-content:space-between;align-items:center">
      <span style="color:var(--text);font-weight:600">
        ⚠️ {{ creances().length }} élèves avec solde impayé
      </span>
      <span class="teal bold mono">
        Total créances : {{ totalCreances() | number:'1.0-0' }} FCFA
      </span>
    </div>
    <p-table [value]="creances()" [loading]="loading()" styleClass="p-datatable-sm" [paginator]="true" [rows]="20">
      <ng-template pTemplate="header">
        <tr>
          <th>Élève</th>
          <th>Section</th>
          <th class="tr">Attendu</th>
          <th class="tr">Payé</th>
          <th class="tr">Reste</th>
          <th style="width:200px">Progression</th>
        </tr>
      </ng-template>
      <ng-template pTemplate="body" let-e>
        <tr>
          <td class="bold">{{ e.nom }}</td>
          <td class="small-txt">{{ e.section }}</td>
          <td class="mono tr">{{ e.attendu | number:'1.0-0' }}</td>
          <td class="mono tr success">{{ e.paye | number:'1.0-0' }}</td>
          <td class="mono tr danger bold">{{ e.reste | number:'1.0-0' }}</td>
          <td>
            <div class="taux-row">
              <div class="taux-bar-track">
                <div class="taux-bar-fill"
                     [style.width.%]="e.taux"
                     [style.background]="e.taux >= 80 ? '#10b981' : e.taux >= 50 ? '#f59e0b' : '#ef4444'">
                </div>
              </div>
              <span class="taux-val" [class.success]="e.taux >= 80" [class.danger]="e.taux < 50">
                {{ e.taux }} %
              </span>
            </div>
          </td>
        </tr>
      </ng-template>
      <ng-template pTemplate="emptymessage">
        <tr><td colspan="6" class="empty-msg">✅ Aucune créance — tous les élèves sont à jour !</td></tr>
      </ng-template>
    </p-table>
  </div>
}

<!-- ════ CHARGES & MARGE ════ -->
@if (onglet() === 'charges') {

  <!-- KPIs synthèse financière -->
  @if (synthese(); as s) {
    <div class="kpi-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:16px">
      <div class="kpi-card" style="--acc:#ef4444">
        <div class="kpi-icon">💸</div>
        <div class="kpi-label">Charges opérationnelles</div>
        <div class="kpi-value" style="color:#ef4444">{{ s.total_charges | number:'1.0-0' }}</div>
        <div class="kpi-sub">FCFA décaissés</div>
      </div>
      <div class="kpi-card" style="--acc:#f59e0b">
        <div class="kpi-icon">🏗️</div>
        <div class="kpi-label">Investissements</div>
        <div class="kpi-value" style="color:#f59e0b">{{ s.total_investissements | number:'1.0-0' }}</div>
        <div class="kpi-sub">FCFA immobilisés</div>
      </div>
      <div class="kpi-card" [style]="'--acc:' + (s.marge_globale >= 0 ? '#10b981' : '#ef4444')">
        <div class="kpi-icon">{{ s.marge_globale >= 0 ? '📈' : '📉' }}</div>
        <div class="kpi-label">Marge nette</div>
        <div class="kpi-value" [style.color]="s.marge_globale >= 0 ? '#10b981' : '#ef4444'">
          {{ s.marge_globale | number:'1.0-0' }}
        </div>
        <div class="kpi-sub">{{ s.marge_globale >= 0 ? 'Excédent' : 'Déficit' }}</div>
      </div>
    </div>
  }

  <!-- Tableau mensuel charges vs encaissements -->
  <div class="table-card">
    <p-table [value]="globalData()" [loading]="loading()" styleClass="p-datatable-sm" [showGridlines]="true">
      <ng-template pTemplate="header">
        <tr>
          <th>Mois</th>
          <th class="tr">Encaissements</th>
          <th class="tr">Charges</th>
          <th class="tr">Invest.</th>
          <th class="tr">Total Décaiss.</th>
          <th class="tr">Marge</th>
          <th class="tr">Cumul Marge</th>
        </tr>
      </ng-template>
      <ng-template pTemplate="body" let-m>
        <tr [class.row-empty]="m.total === 0 && m.decaissements === 0"
            [style.background]="m.marge < 0 ? 'rgba(239,68,68,0.04)' : 'inherit'">
          <td class="bold">{{ m.mois }}</td>
          <td class="mono tr success">{{ m.total > 0 ? (m.total | number:'1.0-0') : '—' }}</td>
          <td class="mono tr danger">{{ m.charges > 0 ? (m.charges | number:'1.0-0') : '—' }}</td>
          <td class="mono tr warn-txt">{{ m.investissements > 0 ? (m.investissements | number:'1.0-0') : '—' }}</td>
          <td class="mono tr" style="color:var(--text-2)">
            {{ m.decaissements > 0 ? (m.decaissements | number:'1.0-0') : '—' }}
          </td>
          <td class="mono tr bold"
              [style.color]="m.marge > 0 ? '#10b981' : m.marge < 0 ? '#ef4444' : 'var(--text-3)'">
            {{ (m.total > 0 || m.decaissements > 0) ? (m.marge | number:'1.0-0') : '—' }}
          </td>
          <td class="mono tr" style="color:#a855f7">
            {{ cumulMargeJusquau(m) | number:'1.0-0' }}
          </td>
        </tr>
      </ng-template>
      <ng-template pTemplate="footer">
        <tr>
          <td class="bold">TOTAL EXERCICE</td>
          <td class="mono tr bold success">{{ totalGlobal() | number:'1.0-0' }}</td>
          <td class="mono tr bold danger">{{ totalCharges() | number:'1.0-0' }}</td>
          <td class="mono tr bold warn-txt">{{ totalInvestissements() | number:'1.0-0' }}</td>
          <td class="mono tr bold" style="color:var(--text-2)">{{ totalDecaissements() | number:'1.0-0' }}</td>
          <td class="mono tr bold" [style.color]="margeGlobale() >= 0 ? '#10b981' : '#ef4444'">
            {{ margeGlobale() | number:'1.0-0' }}
          </td>
          <td></td>
        </tr>
      </ng-template>
      <ng-template pTemplate="emptymessage">
        <tr><td colspan="7" class="empty-msg">Aucune donnée disponible</td></tr>
      </ng-template>
    </p-table>
  </div>
}

<!-- ════ PAR ÉLÈVE ════ -->
@if (onglet() === 'eleve') {
  <div class="search-zone">
    <p-autoComplete
      [(ngModel)]="eleveSelectionne"
      [suggestions]="suggestions()"
      (completeMethod)="chercher($event)"
      optionLabel="nom_complet"
      placeholder="Rechercher un élève..."
      styleClass="w-full"
      [forceSelection]="true"
      (onSelect)="chargerSuiviEleve($event.value)">
      <ng-template let-e pTemplate="item">
        <div style="padding:6px 0">
          <div style="font-weight:600">{{ e.nom_complet }}</div>
          <div style="font-size:11px;color:var(--text-3)">
            {{ e.section_nom }} —
            Reste : <span style="color:#ef4444">{{ e.reste_a_payer | number:'1.0-0' }} FCFA</span>
          </div>
        </div>
      </ng-template>
    </p-autoComplete>
  </div>

  @if (eleveDetail()) {
    @let ed = eleveDetail()!;
    <div class="eleve-card">
      <div class="ec-avatar">{{ ed.nom.substring(0,2).toUpperCase() }}</div>
      <div class="ec-info">
        <div class="ec-nom">{{ ed.nom }}</div>
        <div class="ec-section">{{ ed.section }}</div>
      </div>
      <div class="ec-stats">
        <div class="ecs">
          <div class="ecs-label">Attendu</div>
          <div class="ecs-val">{{ ed.attendu | number:'1.0-0' }}</div>
        </div>
        <div class="ecs">
          <div class="ecs-label">Payé</div>
          <div class="ecs-val" style="color:#10b981">{{ ed.total_paye | number:'1.0-0' }}</div>
        </div>
        <div class="ecs">
          <div class="ecs-label">Reste</div>
          <div class="ecs-val" [style.color]="ed.reste > 0 ? '#ef4444' : '#10b981'">{{ ed.reste | number:'1.0-0' }}</div>
        </div>
        <div class="ecs">
          <div class="ecs-label">Taux</div>
          <div class="ecs-val" [style.color]="ed.taux >= 80 ? '#10b981' : ed.taux >= 50 ? '#f59e0b' : '#ef4444'">{{ ed.taux }} %</div>
        </div>
      </div>
    </div>

    <div class="progress-card">
      <div class="pc-header">
        <span>Taux de recouvrement</span>
        <span class="mono" [style.color]="ed.taux >= 80 ? '#10b981' : ed.taux >= 50 ? '#f59e0b' : '#ef4444'">{{ ed.taux }} %</span>
      </div>
      <div class="progress-track">
        <div class="progress-fill"
             [style.width.%]="ed.taux"
             [style.background]="ed.taux >= 80 ? '#10b981' : ed.taux >= 50 ? '#f59e0b' : '#ef4444'">
        </div>
      </div>
    </div>

    <div class="table-card">
      <p-table [value]="ed.paiements" styleClass="p-datatable-sm">
        <ng-template pTemplate="header">
          <tr>
            <th>N° Pièce</th>
            <th>Date</th>
            <th class="tr">Inscription</th>
            <th class="tr">Mensualité</th>
            <th class="tr">Uniforme</th>
            <th class="tr">Fournitures</th>
            <th class="tr">Cantine</th>
            <th class="tr">Total</th>
            <th class="tr">Cumul</th>
            <th>Mode</th>
          </tr>
        </ng-template>
        <ng-template pTemplate="body" let-p>
          <tr>
            <td class="mono">{{ p.no_piece }}</td>
            <td>{{ p.date | slice:0:10 }}</td>
            <td class="mono tr">{{ p.inscription > 0 ? (p.inscription | number:'1.0-0') : '—' }}</td>
            <td class="mono tr">{{ p.mensualite  > 0 ? (p.mensualite  | number:'1.0-0') : '—' }}</td>
            <td class="mono tr">{{ p.uniforme    > 0 ? (p.uniforme    | number:'1.0-0') : '—' }}</td>
            <td class="mono tr">{{ p.fournitures > 0 ? (p.fournitures | number:'1.0-0') : '—' }}</td>
            <td class="mono tr">{{ p.cantine     > 0 ? (p.cantine     | number:'1.0-0') : '—' }}</td>
            <td class="mono tr teal bold">{{ p.total | number:'1.0-0' }}</td>
            <td class="mono tr" style="color:#a855f7">{{ p.cumul | number:'1.0-0' }}</td>
            <td><p-tag [value]="p.mode" severity="info" /></td>
          </tr>
        </ng-template>
        <ng-template pTemplate="emptymessage">
          <tr><td colspan="10" class="empty-msg">Aucun paiement enregistré</td></tr>
        </ng-template>
      </p-table>
    </div>
  }

  @if (!eleveDetail()) {
    <div class="empty-state">
      <div style="font-size:40px">👤</div>
      <div style="color:var(--text-3);margin-top:12px">Recherchez un élève pour voir son historique</div>
    </div>
  }
}
}
`,
  styles: [`
    .page-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:16px; }
    .page-title  { font-size:20px; font-weight:600; color:var(--text); margin:0 0 4px; }
    .page-sub    { font-size:12px; color:var(--text-3); }
    .btn-refresh { background:transparent; border:1px solid var(--border); color:var(--text-3); padding:6px 14px; border-radius:6px; cursor:pointer; font-size:12px; }
    .btn-refresh:hover { color:#00d4aa; border-color:#00d4aa; }
    /* KPIs */
    .kpi-grid  { display:grid; grid-template-columns:repeat(5,1fr); gap:12px; margin-bottom:20px; }
    .kpi-card  { background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:14px; border-top:3px solid var(--acc); }
    .kpi-icon  { font-size:20px; margin-bottom:6px; }
    .kpi-label { font-size:10px; color:var(--text-3); text-transform:uppercase; letter-spacing:.5px; }
    .kpi-value { font-size:20px; font-weight:700; font-family:monospace; margin:4px 0 6px; }
    .kpi-sub   { font-size:10px; color:var(--text-3); }
    .progress-mini { height:4px; background:var(--bg); border-radius:2px; overflow:hidden; }
    .pm-fill   { height:100%; border-radius:2px; transition:width .4s; }
    /* Onglets */
    .tabs-bar  { display:flex; gap:4px; margin-bottom:16px; background:var(--surface-2); border:1px solid var(--border); border-radius:10px; padding:4px; }
    .tab-btn   { flex:1; padding:7px 10px; border:none; border-radius:7px; background:transparent; color:var(--text-3); font-size:12px; cursor:pointer; }
    .tab-btn.active { background:var(--surface); color:#00d4aa; font-weight:600; border:1px solid var(--border); }
    .badge-count { display:inline-block; background:#ef4444; color:white; border-radius:10px; padding:1px 6px; font-size:10px; margin-left:4px; }
    /* Graphique barres */
    .bar-section { background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:16px 20px; margin-bottom:16px; }
    .bs-header   { display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; }
    .bs-title    { font-size:12px; color:var(--text-3); }
    .bs-total    { font-size:12px; color:#00d4aa; font-family:monospace; font-weight:600; }
    .bars-wrap   { display:flex; gap:6px; align-items:flex-end; height:130px; }
    .bar-item    { flex:1; display:flex; flex-direction:column; align-items:center; gap:3px; height:100%; justify-content:flex-end; }
    .bar-amount  { font-size:8px; color:var(--text-3); font-family:monospace; text-align:center; word-break:break-all; min-height:16px; }
    .bar-track   { width:100%; flex:1; display:flex; align-items:flex-end; max-height:90px; }
    .bar-fill    { width:100%; background:var(--border); border-radius:4px 4px 0 0; min-height:3px; transition:height .5s ease; }
    .bar-fill-active { background:linear-gradient(to top,#00d4aa,#0099ff); }
    .bar-label   { font-size:10px; color:var(--text-2); font-weight:500; }
    .bar-nb      { font-size:9px; color:var(--text-3); min-height:12px; }
    .nb-active   { color:#00d4aa; }
    .bar-active .bar-amount { color:var(--text); }
    /* Tableau */
    .table-card  { background:var(--surface); border:1px solid var(--border); border-radius:12px; overflow:hidden; margin-bottom:16px; }
    ::ng-deep .p-datatable .p-datatable-thead > tr > th { background:var(--surface-2) !important; color:var(--text-3) !important; font-size:11px !important; text-transform:uppercase !important; border-color:var(--border) !important; }
    ::ng-deep .p-datatable .p-datatable-tbody > tr { background:var(--surface) !important; color:var(--text-2) !important; border-bottom:1px solid rgba(42,63,95,0.4) !important; }
    ::ng-deep .p-datatable .p-datatable-tfoot > tr { background:var(--surface-2) !important; }
    .row-empty td { opacity:.4; }
    .row-active td.bold { color:var(--text); }
    /* Taux bar */
    .taux-row      { display:flex; align-items:center; gap:8px; }
    .taux-bar-track{ flex:1; height:8px; background:var(--bg); border-radius:4px; overflow:hidden; }
    .taux-bar-fill { height:100%; border-radius:4px; transition:width .4s; }
    .taux-val      { font-size:11px; font-family:monospace; width:40px; text-align:right; }
    /* Élève */
    .search-zone { margin-bottom:20px; }
    .eleve-card  { display:flex; align-items:center; gap:20px; background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:18px 20px; margin-bottom:14px; }
    .ec-avatar   { width:52px; height:52px; border-radius:12px; background:linear-gradient(135deg,#00d4aa,#0099ff); display:flex; align-items:center; justify-content:center; font-size:18px; font-weight:700; color:#000; flex-shrink:0; }
    .ec-info     { flex:1; }
    .ec-nom      { font-size:16px; font-weight:700; color:var(--text); }
    .ec-section  { font-size:12px; color:var(--text-3); margin-top:2px; }
    .ec-stats    { display:flex; gap:24px; }
    .ecs         { text-align:center; }
    .ecs-label   { font-size:10px; color:var(--text-3); text-transform:uppercase; }
    .ecs-val     { font-size:15px; font-weight:700; font-family:monospace; color:var(--text); margin-top:2px; }
    .progress-card  { background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:14px 18px; margin-bottom:14px; }
    .pc-header      { display:flex; justify-content:space-between; font-size:12px; margin-bottom:8px; color:var(--text-2); }
    .progress-track { height:10px; background:var(--bg); border-radius:5px; overflow:hidden; }
    .progress-fill  { height:100%; border-radius:5px; transition:width .5s ease; }
    /* Utils */
    .mono      { font-family:monospace; font-size:12px; }
    .bold      { font-weight:600; color:var(--text); }
    .small-txt { font-size:11px; color:var(--text-3); }
    .teal      { color:#00d4aa; }
    .success   { color:#10b981; }
    .danger    { color:#ef4444; }
    .warn-txt  { color:#f59e0b; }
    .tr        { text-align:right; }
    .red       { color:#ef4444; }
    /* Prévision de scolarité mensuelle */
    .prev-header { display:flex; justify-content:space-between; align-items:flex-start;
                   gap:16px; padding:16px 16px 12px; flex-wrap:wrap; }
    .prev-title  { margin:0; font-size:15px; font-weight:600; color:var(--text); }
    .prev-sub    { font-size:11px; color:var(--text-3); }
    .prev-total  { display:flex; flex-direction:column; align-items:flex-end; gap:2px; }
    .prev-total-lib { font-size:10px; text-transform:uppercase; letter-spacing:.5px;
                      color:var(--text-3); }
    .prev-total strong { font-size:17px; color:#ef4444; }
    .empty-msg   { text-align:center; padding:40px; color:var(--text-3); }
    .empty-state { text-align:center; padding:60px; }
    .w-full { width:100%; }
  `]
})
export class SuiviMensuelComponent implements OnInit {
  private api          = inject(ApiService);
  private elevesService = inject(ElevesService);

  onglet      = signal('global');
  globalData  = signal<any[]>([]);
  synthese    = signal<any>(null);
  sections    = signal<any[]>([]);
  creances    = signal<any[]>([]);
  eleveDetail = signal<any>(null);
  suggestions = signal<Eleve[]>([]);
  loading     = signal(true);

  eleveSelectionne: any = null;

  // ── Scolarité attendue mois par mois ────────────────────────────────────
  // On n'affiche que les mois qui portent réellement un dû : aligner douze
  // lignes à zéro pour une école dont l'année commence en octobre ne renseigne
  // personne.
  moisAvecPrevision = computed(() =>
    this.globalData().filter(m => (m.scolarite_prevue || 0) > 0));

  totalScolaritePrevue    = computed(() => this.sommeMois('scolarite_prevue'));
  totalScolariteEncaissee = computed(() => this.sommeMois('scolarite_encaissee'));
  totalScolariteReste     = computed(() => this.sommeMois('scolarite_reste'));

  private sommeMois(champ: string): number {
    return this.globalData().reduce((t, m) => t + (m[champ] || 0), 0);
  }

  tauxMois(m: any): number {
    const prevu = m.scolarite_prevue || 0;
    return prevu ? Math.round((m.scolarite_encaissee || 0) / prevu * 1000) / 10 : 0;
  }

  ngOnInit() { this.chargerTout(); }

  chargerTout() {
    this.loading.set(true);
    this.api.get<any>('/eleves/suivi-mensuel/').subscribe({
      next: res => {
        this.globalData.set(res.global   || []);
        this.sections.set(res.sections   || []);
        this.creances.set(res.creances   || []);
        // Normaliser synthese : toujours un objet avec des valeurs par défaut
        const s = res.synthese || {};
        this.synthese.set({
          nb_eleves:            s.nb_eleves            ?? 0,
          total_attendu:        s.total_attendu         ?? 0,
          total_paye:           s.total_paye            ?? 0,
          reste:                s.reste                 ?? 0,
          taux_recouvrement:    s.taux_recouvrement     ?? 0,
          exercice:             s.exercice              ?? '—',
          total_charges:        s.total_charges         ?? 0,
          total_investissements:s.total_investissements ?? 0,
          marge_globale:        s.marge_globale         ?? 0,
        });
        this.loading.set(false);
      },
      error: () => {
        this.synthese.set({ nb_eleves: 0, total_attendu: 0, total_paye: 0, reste: 0, taux_recouvrement: 0, exercice: '—', total_charges: 0, total_investissements: 0, marge_globale: 0 });
        this.loading.set(false);
      },
    });
  }

  chercher(event: any) {
    this.elevesService.getEleves({ search: event.query }).subscribe({
      next: res => this.suggestions.set(res.results || []),
    });
  }

  chargerSuiviEleve(eleve: Eleve) {
    this.api.get<any>(`/eleves/suivi-mensuel/?eleve_id=${eleve.id}`).subscribe({
      next: res => this.eleveDetail.set(res.eleve),
    });
  }

  totalGlobal():   number { return this.globalData().reduce((s, m) => s + m.total, 0); }
  nbTransactions():number { return this.globalData().reduce((s, m) => s + m.nb,    0); }
  maxMensuel():    number { return Math.max(...this.globalData().map(m => m.total), 1); }
  totalCreances(): number { return this.creances().reduce((s, e) => s + e.reste, 0); }

  cumulJusquau(mois: any): number {
    let cumul = 0;
    for (const m of this.globalData()) {
      cumul += m.total;
      if (m.mois_num === mois.mois_num && m.annee === mois.annee) break;
    }
    return cumul;
  }

  totalCharges():         number { return this.globalData().reduce((s, m) => s + (m.charges        || 0), 0); }
  totalInvestissements(): number { return this.globalData().reduce((s, m) => s + (m.investissements || 0), 0); }
  totalDecaissements():   number { return this.globalData().reduce((s, m) => s + (m.decaissements   || 0), 0); }
  margeGlobale():         number { return this.totalGlobal() - this.totalDecaissements(); }

  cumulMargeJusquau(mois: any): number {
    let cumul = 0;
    for (const m of this.globalData()) {
      cumul += (m.marge || 0);
      if (m.mois_num === mois.mois_num && m.annee === mois.annee) break;
    }
    return cumul;
  }
}
