import {
  ChangeDetectionStrategy, Component, OnInit, computed, inject, signal
} from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { ButtonModule }      from 'primeng/button';
import { DialogModule }      from 'primeng/dialog';
import { InputNumberModule } from 'primeng/inputnumber';
import { InputTextModule }   from 'primeng/inputtext';
import { SelectModule }      from 'primeng/select';
import { TableModule }       from 'primeng/table';
import { TagModule }         from 'primeng/tag';
import { ToastModule }       from 'primeng/toast';
import { TooltipModule }     from 'primeng/tooltip';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { AuthService } from '../../core/services/auth.service';
import { ApiService } from '../../core/services/api.service';
import {
  Employe, BulletinPaie, AvanceSalaire, ParametresFiscaux,
  RhService
} from '../../core/services/rh.service';

const MOIS_OPTIONS = [
  { label: 'Janvier',   value: 1  }, { label: 'Février',   value: 2  },
  { label: 'Mars',      value: 3  }, { label: 'Avril',     value: 4  },
  { label: 'Mai',       value: 5  }, { label: 'Juin',      value: 6  },
  { label: 'Juillet',   value: 7  }, { label: 'Août',      value: 8  },
  { label: 'Septembre', value: 9  }, { label: 'Octobre',   value: 10 },
  { label: 'Novembre',  value: 11 }, { label: 'Décembre',  value: 12 },
];

@Component({
  selector: 'app-rh',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    DecimalPipe,
    FormsModule, TableModule, ButtonModule, DialogModule,
    InputTextModule, SelectModule, TagModule, InputNumberModule,
    ToastModule, TooltipModule, TranslateModule,
  ],
  providers: [MessageService],
  template: `
<p-toast />

<!-- ── En-tête ── -->
<div class="page-header">
  <div>
    <h2 class="page-title">{{ 'rh.title' | translate }}</h2>
    <span class="page-sub">{{ 'rh.subtitle' | translate }}</span>
  </div>
</div>

<!-- ── KPIs ── -->
@if (stats()) {
  <div class="kpi-grid">
    <div class="kpi-card" style="--acc:#00d4aa">
      <div class="kpi-icon">👥</div>
      <div class="kpi-label">{{ 'rh.total_employes' | translate }}</div>
      <div class="kpi-value" style="color:#00d4aa">{{ stats()!.total_employes }}</div>
      <div class="kpi-sub">{{ stats()!.actifs }} {{ 'rh.actifs' | translate }}</div>
    </div>
    <div class="kpi-card" style="--acc:#0099ff">
      <div class="kpi-icon">📚</div>
      <div class="kpi-label">{{ 'rh.enseignants' | translate }}</div>
      <div class="kpi-value" style="color:#0099ff">{{ stats()!.enseignants }}</div>
    </div>
    <div class="kpi-card" style="--acc:#a855f7">
      <div class="kpi-icon">🏢</div>
      <div class="kpi-label">{{ 'rh.administration' | translate }}</div>
      <div class="kpi-value" style="color:#a855f7">{{ stats()!.administration }}</div>
    </div>
    <div class="kpi-card" style="--acc:#10b981">
      <div class="kpi-icon">🔧</div>
      <div class="kpi-label">{{ 'rh.appui' | translate }}</div>
      <div class="kpi-value" style="color:#10b981">{{ stats()!.appui }}</div>
    </div>
    <div class="kpi-card" style="--acc:#f59e0b">
      <div class="kpi-icon">💰</div>
      <div class="kpi-label">{{ 'rh.masse_salariale' | translate }}</div>
      <div class="kpi-value" style="color:#f59e0b">{{ stats()!.masse_salariale | number:'1.0-0' }}</div>
      <div class="kpi-sub">{{ 'rh.fcfa_mois' | translate }}</div>
    </div>
  </div>
}

<!-- ── Onglets ── -->
<div class="tabs-bar">
  <button class="tab-btn" [class.active]="onglet() === 'employes'"  (click)="onglet.set('employes')">
    👤 {{ 'rh.onglet_employes' | translate }}
  </button>
  <button class="tab-btn" [class.active]="onglet() === 'bulletins'" (click)="chargerBulletins(); onglet.set('bulletins')">
    📄 {{ 'rh.onglet_bulletins' | translate }}
  </button>
  <button class="tab-btn" [class.active]="onglet() === 'avances'"   (click)="chargerAvances(); onglet.set('avances')">
    💸 {{ 'rh.onglet_avances' | translate }}
  </button>
  @if (canEditParams()) {
    <button class="tab-btn" [class.active]="onglet() === 'params'" (click)="chargerParams(); onglet.set('params')">
      ⚙️ {{ 'rh.onglet_params' | translate }}
    </button>
  }
</div>

<!-- ══════════════════════ EMPLOYÉS ══════════════════════ -->
@if (onglet() === 'employes') {
  <div class="table-card">
    <div class="table-toolbar">
      <span class="tbl-count">{{ employes().length }} {{ 'rh.nb_employes' | translate }}</span>
      <p-button [label]="'rh.nouvel_employe' | translate" severity="success" (onClick)="ouvrirDialogEmploye()" />
    </div>
    <p-table [value]="employes()" [loading]="loading()" styleClass="p-datatable-sm" [paginator]="true" [rows]="15">
      <ng-template pTemplate="header">
        <tr>
          <th>{{ 'rh.matricule'    | translate }}</th>
          <th>{{ 'rh.nom_complet'  | translate }}</th>
          <th>{{ 'rh.type_col'     | translate }}</th>
          <th>{{ 'rh.poste'        | translate }}</th>
          <th>{{ 'rh.contrat'      | translate }}</th>
          <th>{{ 'rh.salaire_base' | translate }}</th>
          <th>{{ 'rh.niveau_enseignement' | translate }}</th>
          <th>{{ 'rh.statut_col'   | translate }}</th>
          <th>{{ 'rh.actions_col'  | translate }}</th>
        </tr>
      </ng-template>
      <ng-template pTemplate="body" let-e>
        <tr>
          <td class="mono">{{ e.matricule }}</td>
          <td>
            <div class="bold">{{ e.nom_complet }}</div>
            @if (e.est_cadre) { <span class="badge-cadre">CADRE</span> }
          </td>
          <td>{{ e.type_employe }}</td>
          <td>{{ e.poste }}</td>
          <td>{{ e.type_contrat }}</td>
          <td class="mono">{{ e.salaire_base | number:'1.0-0' }} <span class="fcfa">FCFA</span></td>
          <td class="small-txt">{{ e.niveau_enseignement || '—' }}</td>
          <td>
            <p-tag [value]="e.statut"
                   [severity]="e.statut === 'ACTIF' ? 'success' : e.statut === 'CONGE' ? 'warn' : 'danger'" />
          </td>
          <td>
            <div class="btn-row">
              <p-button icon="pi pi-pencil"     [rounded]="true" [text]="true" severity="info"    (onClick)="ouvrirDialogEmploye(e)" pTooltip="Modifier l'employé" tooltipPosition="top" />
              <p-button icon="pi pi-file-edit"  [rounded]="true" [text]="true" severity="success" (onClick)="ouvrirDialogBulletin(e)" pTooltip="Générer un bulletin de paie" tooltipPosition="top" />
              <p-button icon="pi pi-credit-card" [rounded]="true" [text]="true" severity="warn"   (onClick)="ouvrirDialogAvance(e)"   pTooltip="Avance sur salaire" tooltipPosition="top" />
            </div>
          </td>
        </tr>
      </ng-template>
      <ng-template pTemplate="emptymessage">
        <tr><td colspan="9" class="empty-msg">{{ 'rh.aucun_employe' | translate }}</td></tr>
      </ng-template>
    </p-table>
  </div>
}

<!-- ══════════════════════ BULLETINS ══════════════════════ -->
@if (onglet() === 'bulletins') {
  <div class="table-card">
    <div class="table-toolbar">
      <span class="tbl-count">{{ bulletins().length }} {{ 'rh.bulletins_titre' | translate }}</span>
      <p-button [label]="'rh.generer_bulletin' | translate" severity="success" (onClick)="ouvrirDialogBulletin()" />
    </div>
    <!-- Filtres rapides -->
    <div class="filter-bar">
      <p-select [options]="employes()" optionLabel="nom_complet" optionValue="id"
                [(ngModel)]="filtreEmployeId" [showClear]="true"
                [placeholder]="'rh.employe_col' | translate"
                (onChange)="chargerBulletins()" styleClass="filter-sel" />
      <p-select [options]="moisOptions" optionLabel="label" optionValue="value"
                [(ngModel)]="filtreMois" [showClear]="true"
                placeholder="Mois" (onChange)="chargerBulletins()" styleClass="filter-sel" />
      <input pInputText [(ngModel)]="filtreAnnee" placeholder="Année" class="filter-input"
             (change)="chargerBulletins()" />
    </div>
    <p-table [value]="bulletins()" [loading]="loadingBulletins()" styleClass="p-datatable-sm" [paginator]="true" [rows]="15">
      <ng-template pTemplate="header">
        <tr>
          <th>{{ 'rh.employe_col'      | translate }}</th>
          <th>{{ 'rh.periode'          | translate }}</th>
          <th>{{ 'rh.salaire_brut_col' | translate }}</th>
          <th>IPRES+IR</th>
          <th>{{ 'rh.net_col'          | translate }}</th>
          <th>Charges Pat.</th>
          <th>{{ 'rh.statut_paie_col'  | translate }}</th>
          <th>{{ 'rh.actions_col'      | translate }}</th>
        </tr>
      </ng-template>
      <ng-template pTemplate="body" let-b>
        <tr>
          <td>
            <div class="bold">{{ b.employe_nom }}</div>
            <div class="small-txt mono">{{ b.employe_matricule }}</div>
          </td>
          <td class="mono bold">{{ b.periode }}</td>
          <td class="mono">{{ b.salaire_brut | number:'1.0-0' }}</td>
          <td class="mono danger">
            {{ (+b.ipres_general_salarie + +b.ipres_cadre_salarie + +b.ir_retenu) | number:'1.0-0' }}
          </td>
          <td class="mono success bold">{{ b.net_a_payer | number:'1.0-0' }}</td>
          <td class="mono warn">{{ b.total_charges_patronales | number:'1.0-0' }}</td>
          <td><p-tag [value]="statutLabel(b.statut)" [severity]="statutSeverity(b.statut)" /></td>
          <td>
            <div class="btn-row">
              <p-button icon="pi pi-eye" [rounded]="true" [text]="true" severity="info"
                        (onClick)="ouvrirDetailBulletin(b)" pTooltip="Voir le détail" tooltipPosition="top" />
              @if (b.statut === 'BROUILLON') {
                <p-button icon="pi pi-check" [rounded]="true" [text]="true" severity="success"
                          (onClick)="demanderValidation(b)" pTooltip="Valider le bulletin" tooltipPosition="top" />
              }
              @if (b.statut === 'VALIDE') {
                <p-button icon="pi pi-wallet" [rounded]="true" [text]="true" severity="warn"
                          (onClick)="demanderPaiement(b)" pTooltip="Marquer comme Payé" tooltipPosition="top" />
              }
              @if (b.statut !== 'BROUILLON') {
                <p-button icon="pi pi-download" [rounded]="true" [text]="true" severity="secondary"
                          (onClick)="telechargerPdf(b)" pTooltip="Télécharger le PDF du bulletin"
                          tooltipPosition="top" [loading]="downloadingId() === b.id" />
              }
              @if (b.statut === 'VALIDE' || b.statut === 'PAYE') {
                <p-button icon="pi pi-ban" [rounded]="true" [text]="true" severity="danger"
                          (onClick)="demanderAnnulationBulletin(b)"
                          pTooltip="Annuler ce bulletin (contre-écritures SYSCOHADA)" tooltipPosition="top" />
              }
            </div>
          </td>
        </tr>
      </ng-template>
      <ng-template pTemplate="emptymessage">
        <tr><td colspan="8" class="empty-msg">{{ 'rh.aucun_bulletin' | translate }}</td></tr>
      </ng-template>
    </p-table>
  </div>

  <!-- Confirmation annulation bulletin -->
  <p-dialog header="⚠️ Annuler ce bulletin de paie" [(visible)]="confirmAnnulBulletinVisible"
            [modal]="true" [style]="{width:'440px'}" [draggable]="false">
    @if (bulletinAnnuler !== null) {
    <div style="padding:8px 0">
      <div style="background:#1a1a2e;border-radius:8px;padding:14px;margin-bottom:16px;border-left:4px solid #ef4444">
        <div style="font-size:13px;color:#e8f0fe;font-weight:600">
          {{ bulletinAnnuler!.employe_nom }} — {{ bulletinAnnuler!.periode }}
        </div>
        <div style="font-size:12px;color:#94a3b8;margin-top:4px">
          Net à payer : {{ bulletinAnnuler!.net_a_payer | number:'1.0-0' }} FCFA
        </div>
      </div>
      <p style="font-size:13px;color:#94a3b8;line-height:1.6;margin:0">
        Cette opération va générer des <strong style="color:#f59e0b">contre-écritures SYSCOHADA</strong>
        pour annuler toutes les écritures de paie (661, 422, IPRES, IR, net à payer).
        <br><br>
        Les avances imputées sur ce bulletin seront <strong style="color:#10b981">restituées</strong>
        en statut EN_ATTENTE.
        <br><br>
        ⚠️ Cette action est <strong style="color:#ef4444">irréversible</strong>.
      </p>
    </div>
    }
    <ng-template pTemplate="footer">
      <p-button label="Non, conserver" severity="secondary" (onClick)="confirmAnnulBulletinVisible=false" />
      <p-button label="Oui, annuler le bulletin" severity="danger"
                [loading]="savingAnnulBulletin()" (onClick)="confirmerAnnulationBulletin()" />
    </ng-template>
  </p-dialog>
}

<!-- ══════════════════════ AVANCES ══════════════════════ -->
@if (onglet() === 'avances') {
  <div class="table-card">
    <div class="table-toolbar">
      <span class="tbl-count">{{ avances().length }} {{ 'rh.avances_titre' | translate }}</span>
      <p-button [label]="'rh.nouvelle_avance' | translate" severity="warn" (onClick)="ouvrirDialogAvance()" />
    </div>
    <p-table [value]="avances()" [loading]="loadingAvances()" styleClass="p-datatable-sm" [paginator]="true" [rows]="15">
      <ng-template pTemplate="header">
        <tr>
          <th>{{ 'rh.employe_col' | translate }}</th>
          <th>{{ 'rh.montant_avance' | translate }}</th>
          <th>{{ 'rh.date_avance'   | translate }}</th>
          <th>{{ 'rh.avance_mode'   | translate }}</th>
          <th>N° Pièce</th>
          <th>{{ 'rh.statut_col'    | translate }}</th>
          <th>{{ 'rh.actions_col'   | translate }}</th>
        </tr>
      </ng-template>
      <ng-template pTemplate="body" let-a>
        <tr>
          <td class="bold">{{ a.employe_nom }}</td>
          <td class="mono warn bold">{{ a.montant | number:'1.0-0' }} FCFA</td>
          <td class="mono">{{ a.date_avance }}</td>
          <td>{{ a.mode_paiement }}</td>
          <td class="mono small-txt">{{ a.no_piece }}</td>
          <td>
            <p-tag [value]="avanceStatutLabel(a.statut)"
                   [severity]="a.statut === 'EN_ATTENTE' ? 'warn' : a.statut === 'IMPUTE' ? 'success' : 'danger'" />
          </td>
          <td>
            @if (a.statut === 'EN_ATTENTE') {
              <p-button icon="pi pi-times" [rounded]="true" [text]="true" severity="danger"
                        (onClick)="annulerAvance(a)" pTooltip="Annuler cette avance" tooltipPosition="top" />
            }
          </td>
        </tr>
      </ng-template>
      <ng-template pTemplate="emptymessage">
        <tr><td colspan="7" class="empty-msg">{{ 'rh.aucune_avance' | translate }}</td></tr>
      </ng-template>
    </p-table>
  </div>
}

<!-- ══════════════════════ PARAMÈTRES FISCAUX ══════════════════════ -->
@if (onglet() === 'params') {
  <div class="params-card">
    <div class="params-header">
      <div>
        <h3 class="params-title">⚙️ {{ 'rh.params_titre' | translate }}</h3>
        @if (parametres()[0]) {
          <span class="params-sub">Exercice {{ parametres()[0].annee }}</span>
        }
      </div>
      @if (!editingParams()) {
        <p-button [label]="'rh.modifier_params' | translate" severity="warn" (onClick)="editingParams.set(true)" />
      }
    </div>

    <!-- Régime de paie de l'établissement -->
    <div class="params-section" style="margin-bottom:16px">
      <div class="ps-title">🏛️ {{ 'rh.regime_titre' | translate }}</div>
      <div class="ps-row">
        <span>{{ 'rh.regime_label' | translate }}</span>
        <p-select [options]="regimesPaie" [(ngModel)]="regimePaie"
                  optionLabel="label" optionValue="value" styleClass="param-input"
                  (onChange)="sauvegarderRegime()" />
      </div>
      <div style="font-size:11px;color:#64748b;margin-top:6px">
        {{ (regimePaie === 'SIMPLIFIE' ? 'rh.regime_aide_simplifie' : 'rh.regime_aide_complet') | translate }}
      </div>
    </div>

    @if (parametres()[0]) {
      <div class="params-grid">
        <!-- IPRES Général -->
        <div class="params-section">
          <div class="ps-title">IPRES — Régime Général</div>
          <div class="ps-row">
            <span>{{ 'rh.ipres_g_sal' | translate }}</span>
            @if (editingParams()) {
              <p-inputNumber [(ngModel)]="formParams.taux_ipres_general_salarie" [minFractionDigits]="1" [maxFractionDigits]="3" styleClass="param-input" suffix=" %" />
            } @else {
              <span class="ps-val">{{ parametres()[0].taux_ipres_general_salarie }} %</span>
            }
          </div>
          <div class="ps-row">
            <span>{{ 'rh.ipres_g_pat' | translate }}</span>
            @if (editingParams()) {
              <p-inputNumber [(ngModel)]="formParams.taux_ipres_general_patronal" [minFractionDigits]="1" [maxFractionDigits]="3" styleClass="param-input" suffix=" %" />
            } @else {
              <span class="ps-val">{{ parametres()[0].taux_ipres_general_patronal }} %</span>
            }
          </div>
          <div class="ps-row">
            <span>{{ 'rh.plafond_ipres_g' | translate }}</span>
            @if (editingParams()) {
              <p-inputNumber [(ngModel)]="formParams.plafond_ipres_general" mode="decimal" styleClass="param-input" suffix=" FCFA" />
            } @else {
              <span class="ps-val">{{ parametres()[0].plafond_ipres_general | number:'1.0-0' }} FCFA</span>
            }
          </div>
        </div>

        <!-- IPRES Cadre -->
        <div class="params-section">
          <div class="ps-title">IPRES — Régime Cadres</div>
          <div class="ps-row">
            <span>{{ 'rh.ipres_c_sal' | translate }}</span>
            @if (editingParams()) {
              <p-inputNumber [(ngModel)]="formParams.taux_ipres_cadre_salarie" [minFractionDigits]="1" [maxFractionDigits]="3" styleClass="param-input" suffix=" %" />
            } @else {
              <span class="ps-val">{{ parametres()[0].taux_ipres_cadre_salarie }} %</span>
            }
          </div>
          <div class="ps-row">
            <span>{{ 'rh.ipres_c_pat' | translate }}</span>
            @if (editingParams()) {
              <p-inputNumber [(ngModel)]="formParams.taux_ipres_cadre_patronal" [minFractionDigits]="1" [maxFractionDigits]="3" styleClass="param-input" suffix=" %" />
            } @else {
              <span class="ps-val">{{ parametres()[0].taux_ipres_cadre_patronal }} %</span>
            }
          </div>
          <div class="ps-row">
            <span>{{ 'rh.plafond_ipres_c' | translate }}</span>
            @if (editingParams()) {
              <p-inputNumber [(ngModel)]="formParams.plafond_ipres_cadre" mode="decimal" styleClass="param-input" suffix=" FCFA" />
            } @else {
              <span class="ps-val">{{ parametres()[0].plafond_ipres_cadre | number:'1.0-0' }} FCFA</span>
            }
          </div>
        </div>

        <!-- CSS / ATMP / CFCE -->
        <div class="params-section">
          <div class="ps-title">CSS · ATMP · CFCE</div>
          <div class="ps-row">
            <span>{{ 'rh.css_prest' | translate }}</span>
            @if (editingParams()) {
              <p-inputNumber [(ngModel)]="formParams.taux_css_prestations_familiales" [minFractionDigits]="1" styleClass="param-input" suffix=" %" />
            } @else {
              <span class="ps-val">{{ parametres()[0].taux_css_prestations_familiales }} %</span>
            }
          </div>
          <div class="ps-row">
            <span>{{ 'rh.taux_atmp_p' | translate }}</span>
            @if (editingParams()) {
              <p-inputNumber [(ngModel)]="formParams.taux_atmp" [minFractionDigits]="1" styleClass="param-input" suffix=" %" />
            } @else {
              <span class="ps-val">{{ parametres()[0].taux_atmp }} %</span>
            }
          </div>
          <div class="ps-row">
            <span>{{ 'rh.taux_cfce_p' | translate }}</span>
            @if (editingParams()) {
              <p-inputNumber [(ngModel)]="formParams.taux_cfce" [minFractionDigits]="1" styleClass="param-input" suffix=" %" />
            } @else {
              <span class="ps-val">{{ parametres()[0].taux_cfce }} %</span>
            }
          </div>
        </div>

        <!-- Allocations -->
        <div class="params-section">
          <div class="ps-title">Transport · Allocations</div>
          <div class="ps-row">
            <span>{{ 'rh.prime_trans_p' | translate }}</span>
            @if (editingParams()) {
              <p-inputNumber [(ngModel)]="formParams.prime_transport" mode="decimal" styleClass="param-input" suffix=" FCFA" />
            } @else {
              <span class="ps-val">{{ parametres()[0].prime_transport | number:'1.0-0' }} FCFA</span>
            }
          </div>
          <div class="ps-row">
            <span>{{ 'rh.alloc_su_base' | translate }}</span>
            @if (editingParams()) {
              <p-inputNumber [(ngModel)]="formParams.allocation_salaire_unique_base" mode="decimal" styleClass="param-input" suffix=" FCFA" />
            } @else {
              <span class="ps-val">{{ parametres()[0].allocation_salaire_unique_base | number:'1.0-0' }} FCFA</span>
            }
          </div>
          <div class="ps-row">
            <span>{{ 'rh.alloc_par_enf' | translate }}</span>
            @if (editingParams()) {
              <p-inputNumber [(ngModel)]="formParams.allocation_par_enfant" mode="decimal" styleClass="param-input" suffix=" FCFA" />
            } @else {
              <span class="ps-val">{{ parametres()[0].allocation_par_enfant | number:'1.0-0' }} FCFA</span>
            }
          </div>
        </div>
      </div>

      @if (editingParams()) {
        <div class="params-footer">
          <p-button [label]="'common.annuler' | translate" severity="secondary" (onClick)="annulerEditParams()" />
          <p-button [label]="'common.enregistrer' | translate" severity="success" [loading]="saving()" (onClick)="sauvegarderParams()" />
        </div>
      }

      <!-- Tranches IR -->
      <div class="tranches-section">
        <div class="ps-title">Barème IR progressif (annuel)</div>
        <table class="tranches-table">
          <thead><tr><th>De (FCFA)</th><th>À (FCFA)</th><th>Taux</th></tr></thead>
          <tbody>
            @for (t of parametres()[0].tranches_ir; track $index) {
              <tr>
                <td class="mono">{{ t.min | number:'1.0-0' }}</td>
                <td class="mono">{{ t.max ? (t.max | number:'1.0-0') : '∞' }}</td>
                <td class="mono bold" [style.color]="t.taux > 0 ? '#f59e0b' : '#64748b'">{{ t.taux }} %</td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    }
  </div>
}

<!-- ══════════════════════ DIALOGS ══════════════════════ -->

<!-- — Dialog Employé — -->
<p-dialog [header]="(formEmploye.id ? '✏️ Modifier' : '👤 ' + ('rh.nouvel_employe_titre' | translate))"
          [(visible)]="dialogEmployeVisible" [modal]="true" [style]="{width:'580px'}" [draggable]="false">
  <div class="form-grid">
    <div class="form-group full">
      <label>{{ 'rh.nom_requis' | translate }} *</label>
      <input pInputText [(ngModel)]="formEmploye.nom_complet" class="w-full" />
    </div>
    <div class="form-group">
      <label>{{ 'rh.type_requis' | translate }} *</label>
      <p-select [options]="typesEmploye" [(ngModel)]="formEmploye.type_employe"
                optionLabel="label" optionValue="value" styleClass="w-full" />
    </div>
    <div class="form-group">
      <label>{{ 'rh.poste_requis' | translate }} *</label>
      <input pInputText [(ngModel)]="formEmploye.poste" class="w-full" />
    </div>
    <div class="form-group">
      <label>{{ 'rh.contrat_type' | translate }}</label>
      <p-select [options]="typesContrat" [(ngModel)]="formEmploye.type_contrat"
                optionLabel="label" optionValue="value" styleClass="w-full" />
    </div>
    <div class="form-group">
      <label>{{ 'rh.date_embauche' | translate }} *</label>
      <input pInputText type="date" [(ngModel)]="formEmploye.date_embauche" class="w-full" />
    </div>
    <div class="form-group">
      <label>{{ 'rh.salaire_base_fcfa' | translate }} *</label>
      <p-inputNumber [(ngModel)]="formEmploye.salaire_base" [min]="0" mode="decimal" styleClass="w-full" />
    </div>
    <div class="form-group">
      <label>{{ 'common.telephone' | translate }}</label>
      <input pInputText [(ngModel)]="formEmploye.telephone" class="w-full" />
    </div>
    <div class="form-group">
      <label>{{ 'rh.email' | translate }}</label>
      <input pInputText [(ngModel)]="formEmploye.email" class="w-full" />
    </div>

    <!-- Séparateur Paie -->
    <div class="form-separator full">💰 Informations Paie SYSCOHADA</div>

    <div class="form-group">
      <label>{{ 'rh.situation_matrimoniale' | translate }}</label>
      <p-select [options]="situationsMatrimoniales" [(ngModel)]="formEmploye.situation_matrimoniale"
                optionLabel="label" optionValue="value" styleClass="w-full" />
    </div>
    <div class="form-group">
      <label>{{ 'rh.nb_enfants' | translate }}</label>
      <p-inputNumber [(ngModel)]="formEmploye.nb_enfants" [min]="0" [max]="20" styleClass="w-full" />
    </div>
    <div class="form-group">
      <label>{{ 'rh.mode_paiement_emp' | translate }}</label>
      <p-select [options]="modesPaiement" [(ngModel)]="formEmploye.mode_paiement"
                optionLabel="label" optionValue="value" styleClass="w-full" />
    </div>
    <div class="form-group full">
      <label>{{ 'rh.numero_compte' | translate }}</label>
      <input pInputText [(ngModel)]="formEmploye.numero_compte" class="w-full" />
    </div>
    <div class="form-group full">
      <label class="toggle-label">
        <input type="checkbox" [(ngModel)]="formEmploye.est_cadre" class="toggle-cb" />
        {{ 'rh.est_cadre' | translate }} (régime IPRES cadres)
      </label>
    </div>

    @if (formEmploye.type_employe === 'ENSEIGNANT') {
      <div class="form-separator full">🎓 {{ 'rh.autorisation_titre' | translate }}</div>
      <div class="form-group">
        <label>{{ 'rh.niveau_enseignement' | translate }}</label>
        <p-select [options]="niveauxEnseignement" [(ngModel)]="formEmploye.niveau_enseignement"
                  optionLabel="label" optionValue="value" [showClear]="true" styleClass="w-full" />
      </div>
      <div class="form-group">
        <label>{{ 'rh.autorisation_numero' | translate }}</label>
        <input pInputText [(ngModel)]="formEmploye.autorisation_numero" class="w-full" />
      </div>
      <div class="form-group">
        <label>{{ 'rh.autorisation_date' | translate }}</label>
        <input pInputText type="date" [(ngModel)]="formEmploye.autorisation_date" class="w-full" />
      </div>
      <div class="form-group">
        <label>{{ 'rh.autorisation_autorite' | translate }}</label>
        <input pInputText [(ngModel)]="formEmploye.autorisation_autorite" class="w-full"
               placeholder="Ex. IA / IEF / Ministère" />
      </div>
      <div class="form-group full">
        <label>{{ 'rh.autorisation_obs' | translate }}</label>
        <input pInputText [(ngModel)]="formEmploye.autorisation_obs" class="w-full" />
      </div>
    }
  </div>
  <ng-template pTemplate="footer">
    <p-button [label]="'common.annuler' | translate"     severity="secondary" (onClick)="dialogEmployeVisible=false" />
    <p-button [label]="'common.enregistrer' | translate" severity="success" [loading]="saving()" (onClick)="sauvegarderEmploye()" />
  </ng-template>
</p-dialog>

<!-- — Dialog Générer Bulletin — -->
<p-dialog header="📄 Générer Bulletin de Paie SYSCOHADA"
          [(visible)]="dialogBulletinVisible" [modal]="true"
          [style]="{width: previewBulletin() ? '900px' : '520px'}"
          [draggable]="false">
  <div [class.dialog-two-col]="previewBulletin()">
    <!-- Formulaire -->
    <div class="bulletin-form">
      @if (formBulletin.employe_nom) {
        <div class="employe-banner">
          <div class="eb-name">{{ formBulletin.employe_nom }}</div>
          <div class="eb-sub">{{ formBulletin.employe_poste }} · {{ formBulletin.employe_niveau || formBulletin.employe_type }}</div>
          <div class="eb-salaire">Base : {{ formBulletin.salaire_base | number:'1.0-0' }} FCFA</div>
        </div>
      } @else {
        <div class="form-group full">
          <label>Employé *</label>
          <p-select [options]="employes()" optionLabel="nom_complet" optionValue="id"
                    [(ngModel)]="formBulletin.employe_id"
                    (onChange)="onEmployeChange($event)"
                    placeholder="Sélectionner un employé" styleClass="w-full" />
        </div>
      }

      <div class="form-grid" style="margin-top:12px">
        <div class="form-group">
          <label>{{ 'rh.mois_label' | translate }} *</label>
          <p-select [options]="moisOptions" optionLabel="label" optionValue="value"
                    [(ngModel)]="formBulletin.mois" styleClass="w-full" />
        </div>
        <div class="form-group">
          <label>{{ 'rh.annee_label' | translate }} *</label>
          <input pInputText type="number" [(ngModel)]="formBulletin.annee" class="w-full" />
        </div>
        <div class="form-group full">
          <label>{{ 'rh.heures_sup_sem' | translate }}</label>
          <p-inputNumber [(ngModel)]="formBulletin.nb_heures_effectuees" [min]="0" [max]="60"
                         [minFractionDigits]="0" [maxFractionDigits]="1" styleClass="w-full"
                         placeholder="0 = aucune heure sup" />
        </div>
        <div class="form-group full">
          <label>{{ 'rh.transport_label' | translate }}</label>
          <p-inputNumber [(ngModel)]="formBulletin.prime_transport" [min]="0" mode="decimal" styleClass="w-full"
                         placeholder="Optionnel — 0 si non applicable" />
        </div>
        <div class="form-group">
          <label>{{ 'rh.indemnite_sujetion' | translate }}</label>
          <p-inputNumber [(ngModel)]="formBulletin.indemnite_sujetion" [min]="0" mode="decimal" styleClass="w-full" />
        </div>
        <div class="form-group">
          <label>{{ 'rh.indemnite_logement' | translate }}</label>
          <p-inputNumber [(ngModel)]="formBulletin.indemnite_logement" [min]="0" mode="decimal" styleClass="w-full" />
        </div>
        <div class="form-group">
          <label>{{ 'rh.primes_diverses' | translate }}</label>
          <p-inputNumber [(ngModel)]="formBulletin.primes_diverses" [min]="0" mode="decimal" styleClass="w-full" />
        </div>
        <div class="form-group">
          <label>{{ 'rh.avantages_nature' | translate }}</label>
          <p-inputNumber [(ngModel)]="formBulletin.avantages_nature" [min]="0" mode="decimal" styleClass="w-full" />
        </div>
        <div class="form-group">
          <label>{{ 'rh.opposition_saisie' | translate }}</label>
          <p-inputNumber [(ngModel)]="formBulletin.opposition_saisie" [min]="0" mode="decimal" styleClass="w-full" />
        </div>
        <div class="form-group">
          <label>{{ 'rh.autres_retenues_label' | translate }}</label>
          <p-inputNumber [(ngModel)]="formBulletin.autres_retenues" [min]="0" mode="decimal" styleClass="w-full" />
        </div>
        <div class="form-group full">
          <label>Mode de paiement</label>
          <p-select [options]="modesPaiement" [(ngModel)]="formBulletin.mode_paiement_effectif"
                    optionLabel="label" optionValue="value" styleClass="w-full" />
        </div>
        <div class="form-group full" style="font-size:11px;color:#64748b">
          ℹ️ {{ 'rh.avances_auto_info' | translate }}
        </div>
      </div>
    </div>

    <!-- Preview -->
    @if (previewBulletin()) {
      <div class="preview-panel">
        <div class="preview-title">📊 {{ 'rh.preview_titre' | translate }}</div>

        <!-- NET en évidence -->
        <div class="net-highlight">
          <div class="nh-label">NET À PAYER</div>
          <div class="nh-val">{{ previewBulletin()!.net_a_payer | number:'1.0-0' }} FCFA</div>
        </div>

        <div class="preview-section">
          <div class="pv-sec-title success-txt">{{ 'rh.gains_label' | translate }}</div>
          <div class="pv-row"><span>Salaire de base</span><span class="mono">{{ previewBulletin()!.salaire_base | number:'1.0-0' }}</span></div>
          @if (+previewBulletin()!.heures_sup_montant > 0) {
            <div class="pv-row"><span>Heures sup. ({{ previewBulletin()!.nb_heures_sup }}h)</span><span class="mono">{{ previewBulletin()!.heures_sup_montant | number:'1.0-0' }}</span></div>
          }
          @if (+previewBulletin()!.allocation_salaire_unique > 0) {
            <div class="pv-row"><span>Alloc. Sal. Unique</span><span class="mono">{{ previewBulletin()!.allocation_salaire_unique | number:'1.0-0' }}</span></div>
          }
          <div class="pv-row"><span>Prime de transport</span><span class="mono">{{ previewBulletin()!.prime_transport | number:'1.0-0' }}</span></div>
          @if (+previewBulletin()!.indemnite_sujetion > 0) {
            <div class="pv-row"><span>Indem. Sujétion</span><span class="mono">{{ previewBulletin()!.indemnite_sujetion | number:'1.0-0' }}</span></div>
          }
          @if (+previewBulletin()!.indemnite_logement > 0) {
            <div class="pv-row"><span>Indem. Logement</span><span class="mono">{{ previewBulletin()!.indemnite_logement | number:'1.0-0' }}</span></div>
          }
          @if (+previewBulletin()!.primes_diverses > 0) {
            <div class="pv-row"><span>Primes diverses</span><span class="mono">{{ previewBulletin()!.primes_diverses | number:'1.0-0' }}</span></div>
          }
          <div class="pv-total"><span>Brut Total</span><span>{{ previewBulletin()!.salaire_brut | number:'1.0-0' }}</span></div>
        </div>

        <div class="preview-section">
          <div class="pv-sec-title danger-txt">{{ 'rh.retenues_label' | translate }}</div>
          <div class="pv-row danger-txt"><span>IPRES Gén. Salarié</span><span class="mono">-{{ previewBulletin()!.ipres_general_salarie | number:'1.0-0' }}</span></div>
          @if (+previewBulletin()!.ipres_cadre_salarie > 0) {
            <div class="pv-row danger-txt"><span>IPRES Cadre</span><span class="mono">-{{ previewBulletin()!.ipres_cadre_salarie | number:'1.0-0' }}</span></div>
          }
          <div class="pv-row danger-txt"><span>IR Retenu</span><span class="mono">-{{ previewBulletin()!.ir_retenu | number:'1.0-0' }}</span></div>
          @if (+previewBulletin()!.avance_sur_salaire > 0) {
            <div class="pv-row danger-txt"><span>Avance</span><span class="mono">-{{ previewBulletin()!.avance_sur_salaire | number:'1.0-0' }}</span></div>
          }
          <div class="pv-total danger-txt"><span>Total Retenues</span><span>-{{ previewBulletin()!.total_retenues_salariales | number:'1.0-0' }}</span></div>
        </div>

        <div class="preview-section">
          <div class="pv-sec-title warn-txt">Charges Patronales</div>
          <div class="pv-row warn-txt"><span>IPRES Pat.</span><span class="mono">{{ (+previewBulletin()!.ipres_general_patronal + +previewBulletin()!.ipres_cadre_patronal) | number:'1.0-0' }}</span></div>
          <div class="pv-row warn-txt"><span>CSS + ATMP</span><span class="mono">{{ (+previewBulletin()!.css_prestations_familiales + +previewBulletin()!.atmp) | number:'1.0-0' }}</span></div>
          <div class="pv-row warn-txt"><span>CFCE</span><span class="mono">{{ previewBulletin()!.cfce | number:'1.0-0' }}</span></div>
          <div class="pv-total warn-txt"><span>Total Charges Pat.</span><span>{{ previewBulletin()!.total_charges_patronales | number:'1.0-0' }}</span></div>
        </div>

        <div class="pv-cout">
          Coût total employeur : <strong>{{ previewBulletin()!.cout_total_employeur | number:'1.0-0' }} FCFA</strong>
        </div>
      </div>
    }
  </div>

  <ng-template pTemplate="footer">
    <p-button [label]="'common.annuler' | translate" severity="secondary" (onClick)="fermerDialogBulletin()" />
    <p-button [label]="'rh.previsualiser' | translate" severity="info"
              [loading]="loadingPreview()" (onClick)="previsualiserBulletin()" />
    @if (previewBulletin()) {
      <p-button [label]="'rh.creer_brouillon' | translate" severity="success"
                [loading]="saving()" (onClick)="creerBulletin()" />
    }
  </ng-template>
</p-dialog>

<!-- — Dialog Avance — -->
<p-dialog header="💸 {{ 'rh.nouvelle_avance' | translate }}"
          [(visible)]="dialogAvanceVisible" [modal]="true" [style]="{width:'440px'}" [draggable]="false">
  @if (formAvance.employe_nom) {
    <div class="employe-banner" style="margin-bottom:14px">
      <div class="eb-name">{{ formAvance.employe_nom }}</div>
    </div>
  } @else {
    <div class="form-group" style="margin-bottom:14px">
      <label>Employé *</label>
      <p-select [options]="employes()" optionLabel="nom_complet" optionValue="id"
                [(ngModel)]="formAvance.employe_id" styleClass="w-full" />
    </div>
  }
  <div class="form-grid">
    <div class="form-group full">
      <label>{{ 'rh.montant_avance' | translate }} *</label>
      <p-inputNumber [(ngModel)]="formAvance.montant" [min]="0" mode="decimal" styleClass="w-full" />
    </div>
    <div class="form-group">
      <label>{{ 'rh.date_avance' | translate }}</label>
      <input pInputText type="date" [(ngModel)]="formAvance.date_avance" class="w-full" />
    </div>
    <div class="form-group">
      <label>{{ 'rh.avance_mode' | translate }}</label>
      <p-select [options]="modesPaiement" optionLabel="label" optionValue="value"
                [(ngModel)]="formAvance.mode_paiement" styleClass="w-full" />
    </div>
    <div class="form-group full">
      <label>{{ 'rh.obs_avance' | translate }}</label>
      <input pInputText [(ngModel)]="formAvance.observations" class="w-full" />
    </div>
  </div>
  <ng-template pTemplate="footer">
    <p-button [label]="'common.annuler' | translate"     severity="secondary" (onClick)="dialogAvanceVisible=false" />
    <p-button [label]="'common.enregistrer' | translate" severity="warn" [loading]="saving()" (onClick)="sauvegarderAvance()" />
  </ng-template>
</p-dialog>

<!-- — Dialog Détail Bulletin — -->
<p-dialog header="📄 Détail Bulletin de Paie"
          [(visible)]="dialogDetailVisible" [modal]="true" [style]="{width:'640px'}" [draggable]="false">
  @if (bulletinDetail()) {
    @let b = bulletinDetail()!;
    <div class="detail-header">
      <div>
        <div class="bold">{{ b.employe_nom }}</div>
        <div class="small-txt mono">{{ b.employe_matricule }} · {{ b.periode }}</div>
      </div>
      <p-tag [value]="statutLabel(b.statut)" [severity]="statutSeverity(b.statut)" />
    </div>

    <div class="detail-grid">
      <div>
        <div class="dg-title success-txt">GAINS</div>
        <div class="dg-row"><span>Salaire de base</span><span>{{ b.salaire_base | number:'1.0-0' }}</span></div>
        @if (+b.heures_sup_montant > 0) {
          <div class="dg-row"><span>Heures sup. ({{ b.nb_heures_sup }}h/sem.)</span><span>{{ b.heures_sup_montant | number:'1.0-0' }}</span></div>
        }
        @if (+b.allocation_salaire_unique > 0) {
          <div class="dg-row"><span>Alloc. Sal. Unique</span><span>{{ b.allocation_salaire_unique | number:'1.0-0' }}</span></div>
        }
        <div class="dg-row"><span>Prime de transport</span><span>{{ b.prime_transport | number:'1.0-0' }}</span></div>
        @if (+b.indemnite_sujetion > 0) { <div class="dg-row"><span>Indem. Sujétion</span><span>{{ b.indemnite_sujetion | number:'1.0-0' }}</span></div> }
        @if (+b.indemnite_logement > 0) { <div class="dg-row"><span>Indem. Logement</span><span>{{ b.indemnite_logement | number:'1.0-0' }}</span></div> }
        @if (+b.primes_diverses > 0)    { <div class="dg-row"><span>Primes diverses</span><span>{{ b.primes_diverses | number:'1.0-0' }}</span></div> }
        @if (+b.avantages_nature > 0)   { <div class="dg-row"><span>Avantages nature</span><span>{{ b.avantages_nature | number:'1.0-0' }}</span></div> }
        <div class="dg-total success-txt"><span>SALAIRE BRUT</span><span>{{ b.salaire_brut | number:'1.0-0' }}</span></div>
      </div>
      <div>
        <div class="dg-title danger-txt">RETENUES</div>
        <div class="dg-row danger-txt"><span>IPRES Gén. Salarié</span><span>{{ b.ipres_general_salarie | number:'1.0-0' }}</span></div>
        @if (+b.ipres_cadre_salarie > 0) { <div class="dg-row danger-txt"><span>IPRES Cadre</span><span>{{ b.ipres_cadre_salarie | number:'1.0-0' }}</span></div> }
        <div class="dg-row danger-txt"><span>IR Retenu</span><span>{{ b.ir_retenu | number:'1.0-0' }}</span></div>
        @if (+b.avance_sur_salaire > 0)  { <div class="dg-row danger-txt"><span>Avance</span><span>{{ b.avance_sur_salaire | number:'1.0-0' }}</span></div> }
        @if (+b.opposition_saisie > 0)   { <div class="dg-row danger-txt"><span>Opposition</span><span>{{ b.opposition_saisie | number:'1.0-0' }}</span></div> }
        @if (+b.autres_retenues > 0)     { <div class="dg-row danger-txt"><span>Autres</span><span>{{ b.autres_retenues | number:'1.0-0' }}</span></div> }
        <div class="dg-total danger-txt"><span>TOTAL RETENUES</span><span>{{ b.total_retenues_salariales | number:'1.0-0' }}</span></div>
        <div class="dg-title warn-txt" style="margin-top:12px">CHARGES PAT.</div>
        <div class="dg-row warn-txt"><span>IPRES Pat.</span><span>{{ (+b.ipres_general_patronal + +b.ipres_cadre_patronal) | number:'1.0-0' }}</span></div>
        <div class="dg-row warn-txt"><span>CSS + ATMP</span><span>{{ (+b.css_prestations_familiales + +b.atmp) | number:'1.0-0' }}</span></div>
        <div class="dg-row warn-txt"><span>CFCE</span><span>{{ b.cfce | number:'1.0-0' }}</span></div>
        <div class="dg-total warn-txt"><span>TOTAL CHARGES</span><span>{{ b.total_charges_patronales | number:'1.0-0' }}</span></div>
      </div>
    </div>

    <div class="net-box-detail">
      <div>NET À PAYER</div>
      <div class="nbd-val">{{ b.net_a_payer | number:'1.0-0' }} FCFA</div>
    </div>
    <div class="cout-box">
      Coût total employeur : <strong>{{ b.cout_total_employeur | number:'1.0-0' }} FCFA</strong>
    </div>
  }
  <ng-template pTemplate="footer">
    <p-button label="Fermer" severity="secondary" (onClick)="dialogDetailVisible=false" />
    @if (bulletinDetail()?.statut !== 'BROUILLON') {
      <p-button icon="pi pi-download" label="Télécharger PDF" severity="info"
                [loading]="downloadingId() === bulletinDetail()?.id"
                (onClick)="telechargerPdf(bulletinDetail()!)" />
    }
  </ng-template>
</p-dialog>

<!-- — Dialog Confirmation Valider — -->
<p-dialog header="✅ Confirmer la validation"
          [(visible)]="dialogConfirmValidation" [modal]="true" [style]="{width:'440px'}" [draggable]="false">
  <p class="confirm-msg">{{ 'rh.confirm_valider' | translate }}</p>
  @if (bulletinAValider()) {
    <div class="confirm-detail">
      <strong>{{ bulletinAValider()!.employe_nom }}</strong> — {{ bulletinAValider()!.periode }}<br>
      Net à payer : <strong class="success-txt">{{ bulletinAValider()!.net_a_payer | number:'1.0-0' }} FCFA</strong>
    </div>
  }
  <ng-template pTemplate="footer">
    <p-button [label]="'common.annuler' | translate"    severity="secondary" (onClick)="dialogConfirmValidation=false" />
    <p-button label="Valider et générer écritures SYSCOHADA" severity="success"
              [loading]="saving()" (onClick)="validerBulletin()" />
  </ng-template>
</p-dialog>

<!-- — Dialog Confirmation Payer — -->
<p-dialog header="💳 Confirmer le paiement"
          [(visible)]="dialogConfirmPaiement" [modal]="true" [style]="{width:'440px'}" [draggable]="false">
  <p class="confirm-msg">{{ 'rh.confirm_payer' | translate }}</p>
  @if (bulletinAValider()) {
    <div class="confirm-detail">
      <strong>{{ bulletinAValider()!.employe_nom }}</strong> — {{ bulletinAValider()!.periode }}<br>
      Net à payer : <strong class="success-txt">{{ bulletinAValider()!.net_a_payer | number:'1.0-0' }} FCFA</strong>
    </div>
  }
  <ng-template pTemplate="footer">
    <p-button [label]="'common.annuler' | translate" severity="secondary" (onClick)="dialogConfirmPaiement=false" />
    <p-button label="Confirmer paiement" severity="warn" [loading]="saving()" (onClick)="payerBulletin()" />
  </ng-template>
</p-dialog>
`,
  styles: [`
    .page-header  { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:16px; }
    .page-title   { font-size:20px; font-weight:600; color:#e8f0fe; margin:0 0 4px; }
    .page-sub     { font-size:12px; color:#64748b; }
    .kpi-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:20px; }
    .kpi-card { background:#1e2d45; border:1px solid #2a3f5f; border-radius:12px; padding:16px; border-top:3px solid var(--acc); }
    .kpi-icon  { font-size:24px; margin-bottom:8px; }
    .kpi-label { font-size:11px; color:#64748b; text-transform:uppercase; letter-spacing:.5px; }
    .kpi-value { font-size:24px; font-weight:700; font-family:monospace; margin:4px 0; }
    .kpi-sub   { font-size:11px; color:#64748b; }
    .tabs-bar  { display:flex; gap:3px; margin-bottom:16px; background:#111827; border:1px solid #2a3f5f; border-radius:10px; padding:4px; }
    .tab-btn   { flex:1; padding:7px 8px; border:none; border-radius:7px; background:transparent; color:#64748b; font-size:12px; cursor:pointer; }
    .tab-btn.active { background:#1e2d45; color:#00d4aa; font-weight:600; border:1px solid #2a3f5f; }
    .table-card    { background:#1e2d45; border:1px solid #2a3f5f; border-radius:12px; overflow:hidden; }
    .table-toolbar { display:flex; justify-content:space-between; align-items:center; padding:14px 16px; }
    .tbl-count     { color:#e8f0fe; font-weight:600; font-size:13px; }
    .filter-bar    { display:flex; gap:10px; padding:8px 16px 12px; background:#151f30; }
    .filter-sel    { width:200px; }
    .filter-input  { background:#1e2d45; border:1px solid #2a3f5f; color:#e8f0fe; border-radius:6px; padding:7px 10px; font-size:12px; width:100px; }
    ::ng-deep .p-datatable .p-datatable-thead > tr > th { background:#111827 !important; color:#64748b !important; font-size:11px !important; text-transform:uppercase !important; border-color:#2a3f5f !important; }
    ::ng-deep .p-datatable .p-datatable-tbody > tr  { background:#1e2d45 !important; color:#94a3b8 !important; border-bottom:1px solid rgba(42,63,95,0.4) !important; }
    .mono      { font-family:monospace; font-size:12px; }
    .bold      { font-weight:600; color:#e8f0fe; }
    .small-txt { font-size:11px; color:#64748b; }
    .fcfa      { font-size:10px; color:#64748b; }
    .success-txt { color:#10b981; }
    .danger-txt  { color:#ef4444; }
    .warn-txt    { color:#f59e0b; }
    .success { color:#10b981; }
    .danger  { color:#ef4444; }
    .warn    { color:#f59e0b; }
    .empty-msg { text-align:center; padding:40px; color:#64748b; }
    .btn-row { display:flex; gap:4px; }
    .badge-cadre { font-size:9px; background:#7c3aed; color:white; padding:1px 5px; border-radius:3px; margin-left:6px; vertical-align:middle; }
    /* Paramètres */
    .params-card   { background:#1e2d45; border:1px solid #2a3f5f; border-radius:12px; padding:20px; }
    .params-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:20px; }
    .params-title  { font-size:16px; font-weight:600; color:#e8f0fe; margin:0 0 4px; }
    .params-sub    { font-size:12px; color:#64748b; }
    .params-grid   { display:grid; grid-template-columns:repeat(2,1fr); gap:16px; margin-bottom:16px; }
    .params-section { background:#111827; border:1px solid #2a3f5f; border-radius:8px; padding:14px; }
    .ps-title      { font-size:11px; font-weight:700; color:#00d4aa; text-transform:uppercase; letter-spacing:.5px; margin-bottom:10px; }
    .ps-row        { display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap; padding:6px 0; border-bottom:1px solid rgba(42,63,95,0.3); font-size:12px; color:#94a3b8; }
    .ps-row > span:first-child { flex:1 1 auto; min-width:0; }
    .ps-val        { font-family:monospace; font-weight:600; color:#e8f0fe; }
    .param-input   { width:130px; flex:0 0 auto; max-width:100%; }
    :host ::ng-deep .param-input .p-inputnumber,
    :host ::ng-deep .param-input input { width:100%; box-sizing:border-box; }
    .params-footer { display:flex; gap:10px; justify-content:flex-end; margin-top:12px; }
    .tranches-section { margin-top:16px; }
    .tranches-table { width:auto; border-collapse:collapse; }
    .tranches-table th { background:#111827; color:#64748b; font-size:10px; text-transform:uppercase; padding:6px 12px; text-align:left; }
    .tranches-table td { padding:5px 12px; border-bottom:1px solid rgba(42,63,95,0.3); font-size:11px; color:#94a3b8; }
    /* Forms */
    .form-grid      { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
    .form-group     { display:flex; flex-direction:column; gap:5px; }
    .form-group label { font-size:11px; color:#94a3b8; text-transform:uppercase; letter-spacing:.3px; }
    .form-group.full { grid-column:1/-1; }
    .form-separator { grid-column:1/-1; font-size:11px; font-weight:700; color:#00d4aa; text-transform:uppercase; border-bottom:1px solid #2a3f5f; padding-bottom:6px; margin-top:4px; }
    .w-full { width:100%; }
    .toggle-label { display:flex; align-items:center; gap:8px; font-size:12px; color:#94a3b8; cursor:pointer; }
    .toggle-cb    { width:16px; height:16px; cursor:pointer; }
    /* Employe banner */
    .employe-banner { background:#111827; border:1px solid #2a3f5f; border-radius:8px; padding:12px; margin-bottom:4px; }
    .eb-name    { font-size:14px; font-weight:700; color:#e8f0fe; }
    .eb-sub     { font-size:11px; color:#64748b; margin-top:3px; }
    .eb-salaire { font-size:12px; color:#00d4aa; margin-top:4px; font-family:monospace; }
    /* Dialog bulletin */
    .dialog-two-col { display:grid; grid-template-columns:1fr 380px; gap:20px; align-items:start; }
    .bulletin-form  { }
    /* Preview panel */
    .preview-panel  { background:#0f1a2e; border:1px solid #2a3f5f; border-radius:8px; padding:14px; }
    .preview-title  { font-size:12px; font-weight:700; color:#00d4aa; text-transform:uppercase; margin-bottom:12px; }
    .net-highlight  { background:#002a1e; border:2px solid #00d4aa; border-radius:6px; padding:10px 14px; margin-bottom:12px; display:flex; justify-content:space-between; align-items:center; }
    .nh-label { font-size:10px; font-weight:700; color:#64748b; text-transform:uppercase; }
    .nh-val   { font-size:18px; font-weight:700; color:#00d4aa; font-family:monospace; }
    .preview-section { margin-bottom:10px; }
    .pv-sec-title { font-size:10px; font-weight:700; text-transform:uppercase; margin-bottom:5px; border-bottom:1px solid rgba(42,63,95,0.5); padding-bottom:3px; }
    .pv-row   { display:flex; justify-content:space-between; font-size:11px; color:#94a3b8; padding:3px 0; }
    .pv-total { display:flex; justify-content:space-between; font-size:11px; font-weight:700; padding:5px 0 0; border-top:1px solid rgba(42,63,95,0.5); margin-top:3px; }
    .pv-cout  { font-size:11px; color:#94a3b8; margin-top:10px; text-align:right; }
    /* Detail dialog */
    .detail-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:14px; padding-bottom:10px; border-bottom:1px solid #2a3f5f; }
    .detail-grid   { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
    .dg-title  { font-size:10px; font-weight:700; text-transform:uppercase; margin-bottom:6px; }
    .dg-row    { display:flex; justify-content:space-between; font-size:11px; color:#94a3b8; padding:4px 0; border-bottom:1px solid rgba(42,63,95,0.2); }
    .dg-total  { display:flex; justify-content:space-between; font-size:12px; font-weight:700; padding:6px 0 0; border-top:1px solid rgba(42,63,95,0.5); margin-top:3px; }
    .net-box-detail { background:#002a1e; border:2px solid #00d4aa; border-radius:8px; padding:12px 18px; display:flex; justify-content:space-between; align-items:center; margin-top:14px; }
    .nbd-val  { font-size:20px; font-weight:700; color:#00d4aa; font-family:monospace; }
    .cout-box { text-align:right; font-size:11px; color:#64748b; margin-top:8px; }
    /* Confirm */
    .confirm-msg    { color:#94a3b8; margin-bottom:12px; line-height:1.5; }
    .confirm-detail { background:#0f1a2e; border:1px solid #2a3f5f; border-radius:6px; padding:10px 14px; font-size:12px; color:#94a3b8; }
  `]
})
export class RhComponent implements OnInit {
  private rh        = inject(RhService);
  private api       = inject(ApiService);
  private msg       = inject(MessageService);
  private translate = inject(TranslateService);
  private auth      = inject(AuthService);

  // — State —
  onglet          = signal('employes');
  employes        = signal<Employe[]>([]);
  bulletins       = signal<BulletinPaie[]>([]);
  avances         = signal<AvanceSalaire[]>([]);
  stats           = signal<any>(null);
  parametres      = signal<ParametresFiscaux[]>([]);
  loading         = signal(false);
  loadingBulletins = signal(false);
  loadingAvances  = signal(false);
  saving          = signal(false);
  loadingPreview  = signal(false);
  downloadingId   = signal<string | null>(null);
  editingParams   = signal(false);
  regimePaie      = 'COMPLET';
  regimesPaie = [
    { label: 'Complet (affilié IPRES/CSS/IR)',     value: 'COMPLET' },
    { label: 'Simplifié (non affilié)',            value: 'SIMPLIFIE' },
  ];
  previewBulletin = signal<any | null>(null);
  bulletinDetail  = signal<BulletinPaie | null>(null);
  bulletinAValider = signal<BulletinPaie | null>(null);
  savingAnnulBulletin = signal(false);
  confirmAnnulBulletinVisible = false;
  bulletinAnnuler: BulletinPaie | null = null;

  // — Dialog visibility —
  dialogEmployeVisible    = false;
  dialogBulletinVisible   = false;
  dialogAvanceVisible     = false;
  dialogDetailVisible     = false;
  dialogConfirmValidation = false;
  dialogConfirmPaiement   = false;

  // — Filtres —
  filtreEmployeId = '';
  filtreMois      = 0;
  filtreAnnee     = '';

  // — Computed —
  canEditParams = computed(() => {
    const role = this.auth.currentUser()?.role;
    return role === 'SUPER_ADMIN' || role === 'ADMIN_ECOLE';
  });

  // — Options listes —
  moisOptions           = MOIS_OPTIONS;
  typesEmploye: any[]   = [];
  typesContrat: any[]   = [];
  niveauxEnseignement: any[] = [];
  situationsMatrimoniales: any[] = [];
  modesPaiement: any[]  = [];

  // — Formulaires —
  formEmploye: any = {};
  formBulletin: any = {};
  formAvance: any  = {};
  formParams: any  = {};

  ngOnInit() {
    this.typesEmploye = [
      { label: this.t('rh.enseignant'),  value: 'ENSEIGNANT'    },
      { label: this.t('rh.admin_type'),  value: 'ADMINISTRATION' },
      { label: this.t('rh.appui'),       value: 'APPUI'          },
    ];
    this.typesContrat = [
      { label: 'CDI',       value: 'CDI'       },
      { label: 'CDD',       value: 'CDD'       },
      { label: 'Vacataire', value: 'VACATAIRE' },
      { label: 'Stagiaire', value: 'STAGIAIRE' },
    ];
    this.niveauxEnseignement = [
      { label: 'Préscolaire', value: 'PRESCOLAIRE' },
      { label: 'Élémentaire', value: 'ELEMENTAIRE' },
      { label: 'Moyen',       value: 'MOYEN'       },
      { label: 'Secondaire',  value: 'SECONDAIRE'  },
      { label: 'Supérieur',   value: 'SUPERIEUR'   },
    ];
    this.situationsMatrimoniales = [
      { label: 'Célibataire', value: 'CELIBATAIRE' },
      { label: 'Marié(e)',    value: 'MARIE'       },
      { label: 'Divorcé(e)', value: 'DIVORCE'     },
      { label: 'Veuf/Veuve', value: 'VEUF'        },
    ];
    this.modesPaiement = [
      { label: 'Caisse (espèces)',  value: 'CAISSE'       },
      { label: 'Banque (virement)', value: 'BANQUE'       },
      { label: 'Wave',              value: 'WAVE'         },
      { label: 'Orange Money',      value: 'ORANGE_MONEY' },
      { label: 'Free Money',        value: 'FREE_MONEY'   },
      { label: 'Wizall',            value: 'WIZALL'       },
    ];
    this.chargerDonnees();
  }

  // ── Chargements ────────────────────────────────────────────
  chargerDonnees() {
    this.loading.set(true);
    this.rh.getStats().subscribe({ next: r => this.stats.set(r) });
    this.rh.getEmployes().subscribe({
      next:  r => { this.employes.set(Array.isArray(r) ? r : r.results ?? []); this.loading.set(false); },
      error: () => this.loading.set(false),
    });
  }

  chargerBulletins() {
    this.loadingBulletins.set(true);
    const p: Record<string, string> = {};
    if (this.filtreEmployeId) p['employe'] = this.filtreEmployeId;
    if (this.filtreMois)      p['mois']    = String(this.filtreMois);
    if (this.filtreAnnee)     p['annee']   = this.filtreAnnee;
    this.rh.getBulletins(p).subscribe({
      next:  r => { this.bulletins.set(Array.isArray(r) ? r : r.results ?? []); this.loadingBulletins.set(false); },
      error: () => this.loadingBulletins.set(false),
    });
  }

  chargerAvances() {
    this.loadingAvances.set(true);
    this.rh.getAvances().subscribe({
      next:  r => { this.avances.set(Array.isArray(r) ? r : r.results ?? []); this.loadingAvances.set(false); },
      error: () => this.loadingAvances.set(false),
    });
  }

  chargerParams() {
    this.rh.getParametresFiscaux().subscribe({
      next: r => {
        this.parametres.set(Array.isArray(r) ? r : [r]);
        if (this.parametres()[0]) this.formParams = { ...this.parametres()[0] };
      },
    });
    // Régime de paie de l'établissement (champ du tenant)
    this.api.get<any>('/tenants/mon_ecole/').subscribe({
      next: e => { this.regimePaie = e?.regime_paie || 'COMPLET'; },
    });
  }

  sauvegarderRegime() {
    this.api.patch<any>('/tenants/mon_ecole/', { regime_paie: this.regimePaie }).subscribe({
      next: () => this.msg.add({ severity: 'success', summary: this.t('common.succes'),
                                 detail: this.t('rh.regime_titre') }),
      error: () => this.msg.add({ severity: 'error', summary: this.t('common.erreur'),
                                  detail: this.t('common.erreur') }),
    });
  }

  // ── Employés ────────────────────────────────────────────────
  ouvrirDialogEmploye(e?: Employe) {
    this.formEmploye = e ? { ...e } : {
      nom_complet: '', type_employe: 'ENSEIGNANT', poste: '', type_contrat: 'CDI',
      date_embauche: '', salaire_base: 0, telephone: '', email: '',
      niveau_enseignement: '', nb_enfants: 0, situation_matrimoniale: 'CELIBATAIRE',
      est_cadre: false, mode_paiement: 'CAISSE', numero_compte: '',
      autorisation_numero: '', autorisation_date: '', autorisation_autorite: '', autorisation_obs: '',
    };
    this.dialogEmployeVisible = true;
  }

  sauvegarderEmploye() {
    if (!this.formEmploye.nom_complet?.trim() || !this.formEmploye.poste?.trim()) {
      this.msg.add({ severity: 'warn', summary: this.t('common.requis'), detail: this.t('rh.champs_requis') });
      return;
    }
    this.saving.set(true);
    const obs = this.formEmploye.id
      ? this.rh.modifierEmploye(this.formEmploye.id, this.formEmploye)
      : this.rh.creerEmploye(this.formEmploye);
    obs.subscribe({
      next: () => {
        this.msg.add({ severity: 'success', summary: this.t('common.succes'), detail: this.t('rh.employe_ajoute') });
        this.dialogEmployeVisible = false;
        this.saving.set(false);
        this.chargerDonnees();
      },
      error: () => this.saving.set(false),
    });
  }

  // ── Bulletins ───────────────────────────────────────────────
  ouvrirDialogBulletin(emp?: Employe) {
    const now = new Date();
    this.previewBulletin.set(null);
    this.formBulletin = {
      employe_id:          emp?.id ?? '',
      employe_nom:         emp?.nom_complet ?? '',
      employe_poste:       emp?.poste ?? '',
      employe_type:        emp?.type_employe ?? '',
      employe_niveau:      emp?.niveau_enseignement ?? '',
      salaire_base:        emp?.salaire_base ?? 0,
      mois:                now.getMonth() + 1,
      annee:               now.getFullYear(),
      nb_heures_effectuees: 0,
      prime_transport:     0,
      indemnite_sujetion:  0,
      indemnite_logement:  0,
      primes_diverses:     0,
      avantages_nature:    0,
      opposition_saisie:   0,
      autres_retenues:     0,
      mode_paiement_effectif: emp?.mode_paiement ?? 'CAISSE',
    };
    this.dialogBulletinVisible = true;
  }

  fermerDialogBulletin() {
    this.dialogBulletinVisible = false;
    this.previewBulletin.set(null);
  }

  onEmployeChange(event: any) {
    const emp = this.employes().find(e => e.id === event.value);
    if (emp) {
      this.formBulletin.employe_nom    = emp.nom_complet;
      this.formBulletin.employe_poste  = emp.poste;
      this.formBulletin.employe_type   = emp.type_employe;
      this.formBulletin.employe_niveau = emp.niveau_enseignement;
      this.formBulletin.salaire_base   = emp.salaire_base;
      this.formBulletin.mode_paiement_effectif = emp.mode_paiement;
    }
  }

  previsualiserBulletin() {
    if (!this.formBulletin.employe_id || !this.formBulletin.mois) return;
    this.loadingPreview.set(true);
    this.previewBulletin.set(null);
    this.rh.calculerBulletin(this._payloadBulletin()).subscribe({
      next: r => {
        this.previewBulletin.set(r);
        this.loadingPreview.set(false);
      },
      error: (err) => {
        this.loadingPreview.set(false);
        const detail = err?.error?.error || err?.error?.detail || 'Impossible de calculer le bulletin.';
        this.msg.add({ severity: 'error', summary: 'Erreur prévisualisation', detail });
      },
    });
  }

  creerBulletin() {
    if (!this.formBulletin.employe_id) return;
    this.saving.set(true);
    this.rh.creerBulletin(this._payloadBulletin()).subscribe({
      next: () => {
        this.msg.add({ severity: 'success', summary: this.t('common.succes'), detail: 'Bulletin créé en brouillon ✅' });
        this.fermerDialogBulletin();
        this.saving.set(false);
        this.onglet.set('bulletins');
        this.chargerBulletins();
      },
      error: (err) => {
        const detail = err?.error?.error ?? 'Erreur lors de la création';
        this.msg.add({ severity: 'error', summary: 'Erreur', detail });
        this.saving.set(false);
      },
    });
  }

  ouvrirDetailBulletin(b: BulletinPaie) {
    this.bulletinDetail.set(b);
    this.dialogDetailVisible = true;
  }

  demanderValidation(b: BulletinPaie) {
    this.bulletinAValider.set(b);
    this.dialogConfirmValidation = true;
  }

  validerBulletin() {
    const b = this.bulletinAValider();
    if (!b) return;
    this.saving.set(true);
    this.rh.validerBulletin(b.id).subscribe({
      next: () => {
        this.msg.add({ severity: 'success', summary: 'Validé', detail: this.t('rh.bulletin_valide_msg') });
        this.dialogConfirmValidation = false;
        this.saving.set(false);
        this.chargerBulletins();
      },
      error: (err) => {
        this.msg.add({ severity: 'error', summary: 'Erreur', detail: err?.error?.error ?? 'Erreur validation' });
        this.saving.set(false);
      },
    });
  }

  demanderPaiement(b: BulletinPaie) {
    this.bulletinAValider.set(b);
    this.dialogConfirmPaiement = true;
  }

  payerBulletin() {
    const b = this.bulletinAValider();
    if (!b) return;
    this.saving.set(true);
    this.rh.payerBulletin(b.id).subscribe({
      next: () => {
        this.msg.add({ severity: 'success', summary: 'Payé', detail: this.t('rh.bulletin_paye_msg') });
        this.dialogConfirmPaiement = false;
        this.saving.set(false);
        this.chargerBulletins();
      },
      error: () => this.saving.set(false),
    });
  }

  telechargerPdf(b: BulletinPaie) {
    this.downloadingId.set(b.id);
    this.rh.telechargerPdf(b.id).subscribe({
      next: (blob) => {
        const url  = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href     = url;
        link.download = `bulletin_${b.employe_matricule}_${String(b.mois).padStart(2,'0')}_${b.annee}.pdf`;
        link.click();
        URL.revokeObjectURL(url);
        this.downloadingId.set(null);
      },
      error: () => {
        this.msg.add({ severity: 'error', summary: 'Erreur', detail: 'Impossible de télécharger le PDF' });
        this.downloadingId.set(null);
      },
    });
  }

  private _payloadBulletin() {
    return {
      employe_id:             this.formBulletin.employe_id,
      mois:                   this.formBulletin.mois,
      annee:                  this.formBulletin.annee,
      nb_heures_effectuees:   this.formBulletin.nb_heures_effectuees || 0,
      indemnite_sujetion:     this.formBulletin.indemnite_sujetion   || 0,
      indemnite_logement:     this.formBulletin.indemnite_logement   || 0,
      primes_diverses:        this.formBulletin.primes_diverses      || 0,
      avantages_nature:       this.formBulletin.avantages_nature     || 0,
      opposition_saisie:      this.formBulletin.opposition_saisie    || 0,
      autres_retenues:        this.formBulletin.autres_retenues      || 0,
      mode_paiement_effectif: this.formBulletin.mode_paiement_effectif,
    };
  }

  // ── Avances ─────────────────────────────────────────────────
  ouvrirDialogAvance(emp?: Employe) {
    const today = new Date().toISOString().split('T')[0];
    this.formAvance = {
      employe_id:  emp?.id ?? '',
      employe_nom: emp?.nom_complet ?? '',
      montant:     0,
      date_avance: today,
      mode_paiement: emp?.mode_paiement ?? 'CAISSE',
      observations: '',
    };
    this.dialogAvanceVisible = true;
  }

  sauvegarderAvance() {
    if (!this.formAvance.employe_id || !this.formAvance.montant) {
      this.msg.add({ severity: 'warn', summary: this.t('common.requis'), detail: 'Employé et montant obligatoires' });
      return;
    }
    this.saving.set(true);
    this.rh.creerAvance(this.formAvance.employe_id, {
      montant:      this.formAvance.montant,
      date_avance:  this.formAvance.date_avance,
      mode_paiement: this.formAvance.mode_paiement,
      observations: this.formAvance.observations,
    }).subscribe({
      next: () => {
        this.msg.add({ severity: 'success', summary: this.t('common.succes'), detail: this.t('rh.avance_creee') });
        this.dialogAvanceVisible = false;
        this.saving.set(false);
        this.chargerAvances();
      },
      error: (err) => {
        this.msg.add({ severity: 'error', summary: 'Erreur', detail: err?.error?.error ?? 'Erreur' });
        this.saving.set(false);
      },
    });
  }

  annulerAvance(a: AvanceSalaire) {
    this.rh.annulerAvance(a.id).subscribe({
      next: () => {
        this.msg.add({ severity: 'info', summary: 'Annulé', detail: 'Avance annulée' });
        this.chargerAvances();
      },
    });
  }

  demanderAnnulationBulletin(b: BulletinPaie) {
    this.bulletinAnnuler = b;
    this.confirmAnnulBulletinVisible = true;
  }

  confirmerAnnulationBulletin() {
    if (!this.bulletinAnnuler?.id) return;
    this.savingAnnulBulletin.set(true);
    this.rh.annulerBulletin(this.bulletinAnnuler.id).subscribe({
      next: (updated: BulletinPaie) => {
        this.msg.add({
          severity: 'info',
          summary: 'Bulletin annulé',
          detail: `Contre-écritures SYSCOHADA générées pour ${updated.employe_nom} — ${updated.periode}`,
        });
        this.confirmAnnulBulletinVisible = false;
        this.bulletinAnnuler = null;
        this.savingAnnulBulletin.set(false);
        this.chargerBulletins();
      },
      error: (err: any) => {
        const detail = err?.error?.error || 'Erreur lors de l\'annulation.';
        this.msg.add({ severity: 'error', summary: 'Erreur', detail });
        this.savingAnnulBulletin.set(false);
      },
    });
  }

  // ── Paramètres Fiscaux ───────────────────────────────────────
  annulerEditParams() {
    this.editingParams.set(false);
    if (this.parametres()[0]) this.formParams = { ...this.parametres()[0] };
  }

  sauvegarderParams() {
    const annee = this.parametres()[0]?.annee;
    if (!annee) return;
    this.saving.set(true);
    this.rh.updateParametresFiscaux(annee, this.formParams).subscribe({
      next: (updated) => {
        this.parametres.set([updated]);
        this.editingParams.set(false);
        this.saving.set(false);
        this.msg.add({ severity: 'success', summary: this.t('common.succes'), detail: this.t('rh.params_sauvegardes') });
      },
      error: () => this.saving.set(false),
    });
  }

  // ── Helpers ─────────────────────────────────────────────────
  statutLabel(s: string) {
    const map: Record<string, string> = {
      BROUILLON: 'Brouillon', VALIDE: 'Validé', PAYE: 'Payé', ANNULE: 'Annulé',
    };
    return map[s] ?? s;
  }

  statutSeverity(s: string): 'warn' | 'success' | 'info' | 'danger' | 'secondary' {
    if (s === 'BROUILLON') return 'warn';
    if (s === 'VALIDE')    return 'info';
    if (s === 'PAYE')      return 'success';
    if (s === 'ANNULE')    return 'danger';
    return 'secondary';
  }

  avanceStatutLabel(s: string) {
    return s === 'EN_ATTENTE' ? 'En attente' : s === 'IMPUTE' ? 'Imputé' : 'Annulé';
  }

  private t(key: string) { return this.translate.instant(key); }
}
