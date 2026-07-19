import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { AppModeService } from '../../core/services/app-mode.service';
import { InputTextModule } from 'primeng/inputtext';
import { ButtonModule } from 'primeng/button';
import { SelectModule } from 'primeng/select';
import { InputNumberModule } from 'primeng/inputnumber';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { DialogModule } from 'primeng/dialog';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { ToastModule } from 'primeng/toast';
import { CheckboxModule } from 'primeng/checkbox';
import { MessageService } from 'primeng/api';

@Component({
  selector: 'app-parametres',
  standalone: true,
  imports: [CommonModule, FormsModule, TranslateModule, InputTextModule, ButtonModule,
            SelectModule, InputNumberModule, TableModule, TagModule,
            DialogModule, ToastModule, CheckboxModule],
  providers: [MessageService],
  template: `
    <p-toast />

    <div class="page-header">
      <div>
        <h2 class="page-title">{{ 'parametres.title' | translate }}</h2>
        <span class="page-sub">{{ 'parametres.configuration' | translate }}</span>
      </div>
    </div>

    <!-- Onglets -->
    <div class="tabs-bar">
      <button class="tab-btn" [class.active]="onglet() === 'ecole'"
              (click)="onglet.set('ecole')">🏫 {{ 'parametres.infos_ecole' | translate }}</button>
      <button class="tab-btn" [class.active]="onglet() === 'exercice'"
              (click)="onglet.set('exercice')">📅 {{ 'parametres.exercice' | translate }}</button>
      <button class="tab-btn" [class.active]="onglet() === 'sections'"
              (click)="onglet.set('sections')">📚 {{ 'parametres.sections' | translate }}</button>
      <button class="tab-btn" [class.active]="onglet() === 'services'"
              (click)="onglet.set('services'); chargerServices()">🍽️ {{ 'parametres.services' | translate }}</button>
      <button class="tab-btn" [class.active]="onglet() === 'certificat'"
              (click)="onglet.set('certificat'); initCertConfig()">📜 {{ 'parametres.certificat' | translate }}</button>
      <button class="tab-btn" [class.active]="onglet() === 'users'"
              (click)="onglet.set('users')">👥 {{ 'parametres.utilisateurs' | translate }}</button>
      <button class="tab-btn" *ngIf="estLocal" [class.active]="onglet() === 'sauvegarde'"
              (click)="onglet.set('sauvegarde'); chargerSauvegarde()">☁️ {{ 'parametres.sauvegarde' | translate }}</button>
      <button class="tab-btn" [class.active]="onglet() === 'cloture'"
        (click)="onglet.set('cloture'); chargerVerification()">
        🔒 {{ 'cloture.title' | translate }}
      </button>
    </div>

    <!-- ══ ONGLET INFOS ÉCOLE ══ -->
    <div *ngIf="onglet() === 'ecole'">
      <div class="form-card" *ngIf="ecole()">
        <div class="fc-title">🏫 {{ 'parametres.infos_titre' | translate }}</div>
        <div class="form-grid">
          <div class="form-group full">
            <label>{{ 'parametres.nom_requis' | translate }}</label>
            <input pInputText [(ngModel)]="ecole()!.nom" class="w-full" />
          </div>
          <div class="form-group">
            <label>{{ 'parametres.ville'     | translate }}</label>
            <input pInputText [(ngModel)]="ecole()!.ville" class="w-full" />
          </div>
          <div class="form-group">
            <label>{{ 'parametres.telephone' | translate }}</label>
            <input pInputText [(ngModel)]="ecole()!.telephone" class="w-full" />
          </div>
          <div class="form-group">
            <label>{{ 'parametres.email'     | translate }}</label>
            <input pInputText [(ngModel)]="ecole()!.email" class="w-full" type="email" />
          </div>
          <div class="form-group">
            <label>{{ 'parametres.rccm'      | translate }}</label>
            <input pInputText [(ngModel)]="ecole()!.rccm" class="w-full" />
          </div>
          <div class="form-group full">
            <label>{{ 'parametres.adresse'   | translate }}</label>
            <input pInputText [(ngModel)]="ecole()!.adresse" class="w-full" />
          </div>
          <div class="form-group">
            <label>{{ 'parametres.ninea'     | translate }}</label>
            <input pInputText [(ngModel)]="ecole()!.ninea" class="w-full" />
          </div>
          <div class="form-group">
            <label>{{ 'parametres.autorisation' | translate }}</label>
            <input pInputText [(ngModel)]="ecole()!.numero_autorisation" class="w-full" />
          </div>
          <div class="form-group full">
            <label>{{ 'parametres.logo' | translate }}</label>
            <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
              <div style="width:90px;height:90px;border:1px dashed #2a3f5f;border-radius:8px;display:flex;align-items:center;justify-content:center;background:#0f1729;overflow:hidden">
                @if (ecole()?.logo) {
                  <img [src]="ecole()!.logo" style="max-width:100%;max-height:100%;object-fit:contain" alt="logo" />
                } @else {
                  <span style="font-size:11px;color:#475569">{{ 'parametres.logo_aucun' | translate }}</span>
                }
              </div>
              <div style="display:flex;flex-direction:column;gap:6px">
                <input type="file" accept="image/*" (change)="onLogoSelected($event)" />
                <small style="color:#64748b;font-size:11px">{{ 'parametres.logo_aide' | translate }}</small>
                @if (ecole()?.logo) {
                  <p-button [label]="'common.supprimer' | translate" severity="danger" size="small"
                            [outlined]="true" (onClick)="retirerLogo()" />
                }
              </div>
            </div>
          </div>
        </div>
        <div class="form-actions">
          <p-button [label]="'parametres.enregistrer_btn' | translate" severity="success"
                    [loading]="saving()" (onClick)="sauvegarderEcole()" />
        </div>
      </div>
    </div>

    <!-- ══ ONGLET EXERCICE ══ -->
    <div *ngIf="onglet() === 'exercice'">
      <div class="form-card" *ngIf="exercice()">
        <div class="fc-title">📅 {{ 'parametres.exercice_titre' | translate }}</div>
        <div class="form-grid">
          <div class="form-group full">
            <label>{{ 'parametres.annee_scolaire' | translate }}</label>
            <input pInputText [(ngModel)]="exercice()!.annee_scolaire"
                   class="w-full" [placeholder]="'parametres.annee_placeholder' | translate" />
          </div>
          <div class="form-group">
            <label>{{ 'parametres.date_debut' | translate }}</label>
            <input type="date" [(ngModel)]="exercice()!.date_debut"
                   class="form-input w-full" />
          </div>
          <div class="form-group">
            <label>{{ 'parametres.date_fin' | translate }}</label>
            <input type="date" [(ngModel)]="exercice()!.date_fin"
                   class="form-input w-full" />
          </div>
          <div class="form-group">
            <label>{{ 'parametres.nb_mensualites' | translate }}</label>
            <p-inputNumber [(ngModel)]="exercice()!.nb_mensualites"
                           mode="decimal" [min]="1" [max]="12" [showButtons]="true"
                           styleClass="w-full" />
          </div>
          <div class="form-group">
            <label>{{ 'parametres.solde_caisse' | translate }}</label>
            <p-inputNumber [(ngModel)]="exercice()!.solde_initial_caisse"
                           mode="decimal" [min]="0" styleClass="w-full" />
          </div>
          <div class="form-group">
            <label>{{ 'parametres.solde_banque' | translate }}</label>
            <p-inputNumber [(ngModel)]="exercice()!.solde_initial_banque"
                           mode="decimal" [min]="0" styleClass="w-full" />
          </div>
          <div class="form-group">
            <label>{{ 'parametres.solde_mobile' | translate }}</label>
            <p-inputNumber [(ngModel)]="exercice()!.solde_initial_mobile"
                           mode="decimal" [min]="0" styleClass="w-full" />
          </div>
        </div>

        <!-- Total trésorerie initiale -->
        <div class="total-tresorerie">
          <span>{{ 'parametres.tresorerie_initiale' | translate }}</span>
          <span class="tt-val">
            {{ (exercice()!.solde_initial_caisse +
                exercice()!.solde_initial_banque +
                exercice()!.solde_initial_mobile) | number:'1.0-0' }} FCFA
          </span>
        </div>

        <div class="form-actions">
          <p-button [label]="'parametres.enregistrer_btn' | translate" severity="success"
                    [loading]="saving()" (onClick)="sauvegarderExercice()" />
        </div>
      </div>
    </div>

    <!-- ══ ONGLET SECTIONS ══ -->
    <div *ngIf="onglet() === 'sections'">
      <div class="section-header-row">
        <div class="fc-title" style="margin:0">📚 {{ 'parametres.frais_par_section' | translate }}</div>
        <p-button [label]="'parametres.ajouter_section' | translate" severity="success" size="small"
                  (onClick)="ouvrirDialogSection()" />
      </div>

      <div class="sections-list">
        <div class="section-card" *ngFor="let s of sections(); let i = index">
          <div class="sc-name">{{ s.nom }}</div>
          <div class="sc-frais-grid">
            <div class="sc-frais">
              <span>{{ 'parametres.inscription_frais' | translate }}</span>
              <p-inputNumber [(ngModel)]="s.frais_inscription" mode="decimal"
                             [min]="0" styleClass="w-full" inputStyleClass="text-right"
                             [disabled]="s.composition_inscription?.length > 0" />
              <a class="compo-link" (click)="ouvrirComposition(s)">
                🧩 {{ 'parametres.composer_inscription' | translate }}
                <span *ngIf="s.composition_inscription?.length"> ({{ s.composition_inscription.length }})</span>
              </a>
            </div>
            <div class="sc-frais">
              <span>{{ 'parametres.mensualite_frais' | translate }}</span>
              <p-inputNumber [(ngModel)]="s.frais_mensualite" mode="decimal"
                             [min]="0" styleClass="w-full" inputStyleClass="text-right" />
            </div>
            <!-- Uniforme / fournitures : désormais des éléments de la composition
                 de l'inscription (repliés par la migration eleves/0015) -->
          </div>
          <div class="sc-actions" style="display:flex;gap:8px">
            <p-button [label]="'parametres.enregistrer_btn' | translate" severity="success" size="small"
                      (onClick)="sauvegarderSection(s)" />
            <p-button [label]="'common.supprimer' | translate" severity="danger" size="small" [outlined]="true"
                      (onClick)="supprimerSection(s)" />
          </div>
        </div>
      </div>
    </div>

    <!-- ══ ONGLET SERVICES / ACTIVITÉS ══ -->
    <div *ngIf="onglet() === 'services'">
      <div class="section-header-row">
        <div class="fc-title" style="margin:0">🍽️ {{ 'parametres.services_titre' | translate }}</div>
        <p-button [label]="'parametres.ajouter_service' | translate" severity="success" size="small"
                  (onClick)="ouvrirDialogService()" />
      </div>
      <p style="font-size:12px;color:#64748b;margin:4px 0 12px">{{ 'parametres.services_aide' | translate }}</p>

      <div class="sections-list">
        <div class="section-card" *ngFor="let sv of services()">
          <div class="sc-frais-grid">
            <div class="sc-frais">
              <span>{{ 'parametres.service_nom' | translate }}</span>
              <input pInputText [(ngModel)]="sv.nom" class="w-full" />
            </div>
            <div class="sc-frais">
              <span>{{ 'parametres.service_montant' | translate }}</span>
              <p-inputNumber [(ngModel)]="sv.montant" mode="decimal"
                             [min]="0" styleClass="w-full" inputStyleClass="text-right" />
            </div>
            <div class="sc-frais">
              <span>{{ 'parametres.service_periodicite' | translate }}</span>
              <p-select appendTo="body" [options]="periodiciteOptions" [(ngModel)]="sv.periodicite"
                        optionLabel="label" optionValue="value" styleClass="w-full" />
            </div>
            <div class="sc-frais" *ngIf="sv.periodicite === 'UNIQUE'">
              <span>{{ 'parametres.service_periode' | translate }}</span>
              <p-select appendTo="body" [options]="periodeUniqueOptions" [(ngModel)]="sv.mois_unique"
                        optionLabel="label" optionValue="value" styleClass="w-full" />
            </div>
            <div class="sc-frais">
              <span>{{ 'parametres.service_actif' | translate }}</span>
              <p-select appendTo="body" [options]="actifOptions" [(ngModel)]="sv.actif"
                        optionLabel="label" optionValue="value" styleClass="w-full" />
            </div>
          </div>
          <div class="sc-actions" style="display:flex;gap:8px">
            <p-button [label]="'parametres.enregistrer_btn' | translate" severity="success" size="small"
                      (onClick)="sauvegarderService(sv)" />
            <p-button [label]="'common.supprimer' | translate" severity="danger" size="small" [outlined]="true"
                      (onClick)="supprimerService(sv)" />
          </div>
        </div>
        <div *ngIf="services().length === 0" style="color:#64748b;font-size:13px;padding:8px">
          {{ 'parametres.services_vide' | translate }}
        </div>
      </div>
    </div>

    <!-- ══ ONGLET CERTIFICAT ══ -->
    <div *ngIf="onglet() === 'certificat'">
      <div class="form-card">
        <div class="fc-title">📜 {{ 'parametres.cert_titre' | translate }}</div>
        <p style="color:#94a3b8;font-size:12px;margin:0 0 14px">{{ 'parametres.cert_aide' | translate }}</p>
        <div class="form-grid">
          @for (k of certElements; track k) {
            <div class="form-group" style="flex-direction:row;align-items:center;gap:8px">
              <p-checkbox [(ngModel)]="certCfg[k]" [binary]="true" [inputId]="'cert_' + k" />
              <label [for]="'cert_' + k" style="margin:0;cursor:pointer">{{ ('parametres.cert_' + k) | translate }}</label>
            </div>
          }
          <div class="form-group full">
            <label>{{ 'parametres.cert_texte_intro' | translate }}</label>
            <textarea rows="3" class="w-full cert-textarea" [(ngModel)]="certCfg.texte_intro"></textarea>
          </div>
          <div class="form-group full">
            <label>{{ 'parametres.cert_texte_conclusion' | translate }}</label>
            <textarea rows="3" class="w-full cert-textarea" [(ngModel)]="certCfg.texte_conclusion"></textarea>
          </div>
        </div>
        <div class="form-actions">
          <p-button [label]="'parametres.enregistrer_btn' | translate" severity="success"
                    [loading]="saving()" (onClick)="sauvegarderCertificat()" />
        </div>
      </div>
    </div>

    <!-- ══ ONGLET UTILISATEURS ══ -->
    <div *ngIf="onglet() === 'users'">
      <div class="section-header-row">
        <div class="fc-title" style="margin:0">👥 {{ 'parametres.utilisateurs' | translate }} de l'École</div>
        <p-button [label]="'parametres.ajouter_user' | translate" severity="success" size="small"
                  (onClick)="ouvrirDialogUser()" />
      </div>

      <div class="table-card">
        <p-table [value]="users()" [loading]="loadingUsers()"
                 styleClass="p-datatable-sm">
          <ng-template pTemplate="header">
            <tr>
              <th>{{ 'parametres.nom'         | translate }}</th>
              <th>{{ 'parametres.email_col'   | translate }}</th>
              <th>{{ 'parametres.role'        | translate }}</th>
              <th>{{ 'parametres.statut_col'  | translate }}</th>
              <th>{{ 'parametres.actions_col' | translate }}</th>
            </tr>
          </ng-template>
          <ng-template pTemplate="body" let-u>
            <tr>
              <td class="bold">{{ u.nom }} {{ u.prenom }}</td>
              <td class="mono">{{ u.email }}</td>
              <td>
                <p-tag [value]="u.role"
                       [severity]="u.role === 'ADMIN_ECOLE' ? 'success' :
                                   u.role === 'ADMIN_COMPTABLE' ? 'info' :
                                   u.role === 'ADMIN_RH' ? 'warn' :
                                   u.role === 'ADMIN_SCOLARITE' ? 'warn' : 'secondary'" />
              </td>
              <td>
                <p-tag [value]="u.actif ? ('parametres.actif' | translate) : ('parametres.inactif' | translate)"
                       [severity]="u.actif ? 'success' : 'danger'" />
              </td>
              <td>
                <p-button icon="pi pi-key" [rounded]="true" [text]="true"
                          severity="warn" (onClick)="ouvrirChangeMdp(u)"
                          pTooltip="Changer mot de passe" />
                <p-button icon="pi pi-trash" [rounded]="true" [text]="true"
                          severity="danger" (onClick)="supprimerUser(u)"
                          pTooltip="Supprimer" />
              </td>
            </tr>
          </ng-template>
          <ng-template pTemplate="emptymessage">
            <tr><td colspan="5" class="empty-msg">{{ 'parametres.aucun_utilisateur' | translate }}</td></tr>
          </ng-template>
        </p-table>
      </div>
    </div>

    <!-- ══ ONGLET SAUVEGARDE CLOUD (mode local) ══ -->
    <div *ngIf="onglet() === 'sauvegarde'">
      <div class="form-card">
        <div class="fc-title">☁️ {{ 'sauvegarde.titre' | translate }}</div>
        <p style="font-size:13px;color:#94a3b8;margin-bottom:16px">
          {{ 'sauvegarde.explication' | translate }}
        </p>

        <div class="statut-cloture"
             [class.ok]="sauvegarde()?.statut?.statut === 'OK'"
             [class.bloque]="sauvegarde()?.statut?.statut === 'ERREUR'"
             *ngIf="sauvegarde()?.statut">
          <span *ngIf="sauvegarde()!.statut.statut === 'OK'">
            ✅ {{ 'sauvegarde.derniere' | translate }} :
            {{ sauvegarde()!.statut.date | date:'dd/MM/yyyy HH:mm' }}
            — {{ sauvegarde()!.statut.message }}
          </span>
          <span *ngIf="sauvegarde()!.statut.statut === 'ERREUR'">
            ❌ {{ sauvegarde()!.statut.date | date:'dd/MM/yyyy HH:mm' }}
            — {{ sauvegarde()!.statut.message }}
          </span>
        </div>
        <div class="alerte-orange" *ngIf="sauvegarde() && !sauvegarde()?.statut">
          ⚠️ {{ 'sauvegarde.aucune' | translate }}
        </div>

        <div class="kpi-row" style="display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin:16px 0"
             *ngIf="sauvegarde()">
          <div class="kpi-mini">
            <div class="km-label">{{ 'sauvegarde.copies_locales' | translate }}</div>
            <div class="km-val">{{ sauvegarde()!.nb_dumps_locaux }}</div>
          </div>
          <div class="kpi-mini">
            <div class="km-label">{{ 'sauvegarde.taille' | translate }}</div>
            <div class="km-val">{{ ((sauvegarde()!.statut?.taille || 0) / 1048576) | number:'1.1-1' }} Mo</div>
          </div>
        </div>

        <div class="form-actions">
          <p-button [label]="'☁️ ' + ('sauvegarde.maintenant' | translate)"
                    [loading]="sauvegardeEnCours()"
                    (onClick)="declencherSauvegarde()" />
        </div>
      </div>
    </div>

    <!-- ══ ONGLET CLÔTURE ══ -->
<div *ngIf="onglet() === 'cloture'">
  <div class="form-card" *ngIf="verification()">

    <div class="fc-title">🔒 {{ 'cloture.title' | translate }} {{ verification()!.exercice?.annee_scolaire }}</div>

    <!-- Résumé financier -->
    <div class="kpi-row" style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:20px">
      <div class="kpi-mini teal">
        <div class="km-label">{{ 'cloture.total_recettes' | translate }}</div>
        <div class="km-val" style="color:#00d4aa;font-size:16px">
          {{ verification()!.stats.total_recettes | number:'1.0-0' }} FCFA
        </div>
      </div>
      <div class="kpi-mini blue">
        <div class="km-label">{{ 'cloture.total_charges' | translate }}</div>
        <div class="km-val" style="color:#0099ff;font-size:16px">
          {{ verification()!.stats.total_charges | number:'1.0-0' }} FCFA
        </div>
      </div>
      <div class="kpi-mini"
           [style.border-color]="verification()!.stats.resultat_net >= 0 ? '#10b981' : '#ef4444'">
        <div class="km-label">{{ 'cloture.resultat_net' | translate }}</div>
        <div class="km-val" style="font-size:16px"
             [style.color]="verification()!.stats.resultat_net >= 0 ? '#10b981' : '#ef4444'">
          {{ verification()!.stats.resultat_net | number:'1.0-0' }} FCFA
        </div>
      </div>
    </div>

    <!-- Élèves -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px">
      <div style="background:#0b0f1a;border:1px solid #2a3f5f;border-radius:8px;padding:12px">
        <div style="font-size:11px;color:#64748b;margin-bottom:4px">{{ 'cloture.total_eleves' | translate }}</div>
        <div style="font-size:20px;font-weight:700;color:#e8f0fe;font-family:monospace">
          {{ verification()!.stats.eleves_total }}
        </div>
      </div>
      <div style="background:#0b0f1a;border:1px solid #2a3f5f;border-radius:8px;padding:12px"
           [style.border-color]="verification()!.stats.eleves_impayes > 0 ? '#f59e0b' : '#2a3f5f'">
        <div style="font-size:11px;color:#64748b;margin-bottom:4px">{{ 'cloture.eleves_impayes' | translate }}</div>
        <div style="font-size:20px;font-weight:700;font-family:monospace"
             [style.color]="verification()!.stats.eleves_impayes > 0 ? '#f59e0b' : '#10b981'">
          {{ verification()!.stats.eleves_impayes }}
        </div>
        <div style="font-size:11px;color:#64748b" *ngIf="verification()!.stats.eleves_impayes > 0">
          {{ verification()!.stats.montant_impaye | number:'1.0-0' }} FCFA impayés
        </div>
      </div>
    </div>

    <!-- Problèmes bloquants -->
    <div class="alerte-rouge" *ngFor="let p of verification()!.problemes">
      ❌ {{ p }}
    </div>

    <!-- Warnings non bloquants -->
    <div class="alerte-orange" *ngFor="let w of verification()!.warnings">
      ⚠️ {{ w }}
    </div>

    <!-- Statut final -->
    <div class="statut-cloture"
         [class.ok]="verification()!.peut_cloturer"
         [class.bloque]="!verification()!.peut_cloturer">
      <span *ngIf="verification()!.peut_cloturer">
        ✅ {{ 'cloture.peut_cloturer' | translate }}
      </span>
      <span *ngIf="!verification()!.peut_cloturer">
        ❌ {{ 'cloture.bloque' | translate }}
      </span>
    </div>

    <!-- Option nouvel exercice -->
    <div class="option-row" *ngIf="verification()!.peut_cloturer">
      <label style="display:flex;align-items:center;gap:10px;cursor:pointer;font-size:13px;color:#94a3b8">
        <input type="checkbox" [(ngModel)]="creerSuivant" style="width:16px;height:16px">
        {{ 'parametres.creer_auto' | translate }}
      </label>
    </div>

    <!-- Bouton clôture -->
    <div class="form-actions" style="gap:12px" *ngIf="verification()!.peut_cloturer">
      <div style="font-size:12px;color:#ef4444;align-self:center">
        ⚠️ {{ 'cloture.irreversible' | translate }}
      </div>
      <p-button
        [label]="'🔒 ' + ('cloture.confirmer' | translate)"
        severity="danger"
        [loading]="saving()"
        (onClick)="confirmerCloture()" />
    </div>

  </div>

  <!-- Loading -->
  <div class="empty-msg" *ngIf="!verification()">
    {{ 'parametres.chargement_verif' | translate }}
  </div>
</div>

    <!-- Dialog nouvel utilisateur -->
    <p-dialog [header]="'👤 ' + ('parametres.nouveau_user_titre' | translate)" [(visible)]="userDialogVisible"
              [modal]="true" [style]="{width:'460px'}" [draggable]="false">
      <div class="form-grid">
        <div class="form-group">
          <label>{{ 'parametres.nom' | translate }} *</label>
          <input pInputText [(ngModel)]="newUser.nom" class="w-full" />
        </div>
        <div class="form-group">
          <label>{{ 'parametres.prenom' | translate }}</label>
          <input pInputText [(ngModel)]="newUser.prenom" class="w-full" />
        </div>
        <div class="form-group full">
          <label>{{ 'parametres.email' | translate }} *</label>
          <input pInputText [(ngModel)]="newUser.email" class="w-full" type="email" />
        </div>
        <div class="form-group full">
          <label>{{ 'parametres.mot_de_passe' | translate }} *</label>
          <input pInputText [(ngModel)]="newUser.password" class="w-full" type="password" />
        </div>
        <div class="form-group full">
          <label>{{ 'parametres.role' | translate }} *</label>
          <p-select [options]="rolesDisponibles" [(ngModel)]="newUser.role"
                    optionLabel="label" optionValue="value"
                    appendTo="body" [scrollHeight]="'260px'"
                    styleClass="w-full" />
        </div>
      </div>
      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler' | translate" severity="secondary" (onClick)="userDialogVisible=false" />
        <p-button [label]="'common.creer'   | translate" severity="success"
                  [loading]="saving()" (onClick)="creerUser()" />
      </ng-template>
    </p-dialog>

    <!-- Dialog nouvelle section -->
    <p-dialog [header]="'📚 ' + ('parametres.nouvelle_section_titre' | translate)" [(visible)]="sectionDialogVisible"
              [modal]="true" [style]="{width:'400px'}" [draggable]="false">
      <div class="form-group" style="margin-bottom:14px">
        <label>{{ 'parametres.nom_section_requis' | translate }}</label>
        <input pInputText [(ngModel)]="newSection.nom" class="w-full"
               [placeholder]="'parametres.section_placeholder' | translate" />
      </div>
      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler' | translate" severity="secondary" (onClick)="sectionDialogVisible=false" />
        <p-button [label]="'common.creer'   | translate" severity="success"
                  [loading]="saving()" (onClick)="creerSection()" />
      </ng-template>
    </p-dialog>

    <!-- Dialog nouveau service -->
    <p-dialog [header]="'🍽️ ' + ('parametres.nouveau_service_titre' | translate)" [(visible)]="serviceDialogVisible"
              [modal]="true" [style]="{width:'420px'}" [draggable]="false">
      <div class="form-group" style="margin-bottom:14px">
        <label>{{ 'parametres.service_nom' | translate }} *</label>
        <input pInputText [(ngModel)]="newService.nom" class="w-full"
               [placeholder]="'parametres.service_placeholder' | translate" />
      </div>
      <div class="form-group" style="margin-bottom:14px">
        <label>{{ 'parametres.service_montant' | translate }}</label>
        <p-inputNumber [(ngModel)]="newService.montant" mode="decimal" [min]="0" styleClass="w-full" />
      </div>
      <div class="form-group" style="margin-bottom:14px">
        <label>{{ 'parametres.service_periodicite' | translate }}</label>
        <p-select appendTo="body" [options]="periodiciteOptions" [(ngModel)]="newService.periodicite"
                  optionLabel="label" optionValue="value" styleClass="w-full" />
      </div>
      <div class="form-group" style="margin-bottom:14px" *ngIf="newService.periodicite === 'UNIQUE'">
        <label>{{ 'parametres.service_periode' | translate }}</label>
        <p-select appendTo="body" [options]="periodeUniqueOptions" [(ngModel)]="newService.mois_unique"
                  optionLabel="label" optionValue="value" styleClass="w-full" />
        <small style="color:#64748b;font-size:10px">{{ 'parametres.service_periode_aide' | translate }}</small>
      </div>
      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler' | translate" severity="secondary" (onClick)="serviceDialogVisible=false" />
        <p-button [label]="'common.creer'   | translate" severity="success"
                  [loading]="saving()" (onClick)="creerService()" />
      </ng-template>
    </p-dialog>

    <!-- Dialog composition de l'inscription -->
    <p-dialog [header]="'🧩 ' + ('parametres.composition_titre' | translate) + (sectionCompo ? ' — ' + sectionCompo.nom : '')"
              [(visible)]="compositionDialogVisible" [modal]="true" [style]="{width:'520px'}" [draggable]="false">
      <p style="font-size:12px;color:#64748b;margin:0 0 12px">{{ 'parametres.composition_aide' | translate }}</p>
      <div class="compo-row" *ngFor="let r of compoRows; let i = index">
        <input pInputText [(ngModel)]="r.libelle" class="w-full"
               [placeholder]="'parametres.element_libelle' | translate" />
        <p-inputNumber [(ngModel)]="r.montant" mode="decimal" [min]="0"
                       styleClass="compo-montant" inputStyleClass="text-right" placeholder="0" />
        <p-button icon="pi pi-trash" [rounded]="true" [text]="true" severity="danger"
                  (onClick)="retirerCompoRow(i)" />
      </div>
      <p-button [label]="'parametres.ajouter_element' | translate" icon="pi pi-plus"
                severity="secondary" size="small" (onClick)="ajouterCompoRow()" />
      <div class="compo-total">
        {{ 'parametres.composition_total' | translate }} :
        <strong style="color:#00d4aa">{{ totalCompo() | number:'1.0-0' }} FCFA</strong>
      </div>
      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler' | translate" severity="secondary" (onClick)="compositionDialogVisible=false" />
        <p-button [label]="'common.enregistrer' | translate" severity="success"
                  [loading]="saving()" (onClick)="validerComposition()" />
      </ng-template>
    </p-dialog>

    <!-- Dialog changer mot de passe -->
    <p-dialog [header]="'🔑 ' + ('parametres.changer_mdp_titre' | translate)" [(visible)]="mdpDialogVisible"
              [modal]="true" [style]="{width:'380px'}" [draggable]="false">
      <div *ngIf="userSelectionne">
        <div style="font-size:13px;color:#94a3b8;margin-bottom:16px">
          {{ 'parametres.utilisateur_label' | translate }} : <strong style="color:#e8f0fe">{{ userSelectionne.nom }}</strong>
        </div>
        <div class="form-group">
          <label>{{ 'parametres.nouveau_mdp' | translate }}</label>
          <input pInputText [(ngModel)]="nouveauMdp" class="w-full"
                 type="password" [placeholder]="'parametres.mdp_min' | translate" />
        </div>
      </div>
      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler'  | translate" severity="secondary" (onClick)="mdpDialogVisible=false" />
        <p-button [label]="'common.confirmer'| translate" severity="success"
                  [loading]="saving()" (onClick)="changerMdp()" />
      </ng-template>
    </p-dialog>
  `,
  styles: [`
    .page-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:16px; }
    .page-title  { font-size:20px; font-weight:600; color:#e8f0fe; margin:0 0 4px; }
    .page-sub    { font-size:12px; color:#64748b; }

    .tabs-bar { display:flex; gap:4px; margin-bottom:20px; background:#111827; border:1px solid #2a3f5f; border-radius:10px; padding:4px; }
    .tab-btn { flex:1; padding:8px 12px; border:none; border-radius:7px; background:transparent; color:#64748b; font-size:13px; cursor:pointer; transition:all 0.15s; font-family:inherit; }
    .tab-btn:hover  { background:#1a2235; color:#e8f0fe; }
    .tab-btn.active { background:#1e2d45; color:#00d4aa; font-weight:600; border:1px solid #2a3f5f; }

    .form-card { background:#1e2d45; border:1px solid #2a3f5f; border-radius:12px; padding:20px 24px; }
    .cert-textarea { background:#0f1729; border:1px solid #2a3f5f; border-radius:6px; color:#e8f0fe;
                     padding:8px 10px; font-family:inherit; font-size:13px; resize:vertical; }
    .fc-title  { font-size:14px; font-weight:600; color:#e8f0fe; margin-bottom:16px; }

    .form-grid    { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
    .form-group   { display:flex; flex-direction:column; gap:6px; }
    .form-group.full { grid-column:1/-1; }
    .form-group label { font-size:11px; color:#94a3b8; text-transform:uppercase; letter-spacing:0.5px; }
    .form-input { background:#0b0f1a; border:1px solid #2a3f5f; border-radius:8px; padding:9px 14px; color:#e8f0fe; font-family:inherit; font-size:13px; outline:none; }
    .form-input:focus { border-color:#00d4aa; }

    .form-actions { display:flex; justify-content:flex-end; margin-top:20px; padding-top:16px; border-top:1px solid #2a3f5f; }

    .total-tresorerie { display:flex; justify-content:space-between; align-items:center; background:rgba(0,212,170,0.08); border:1px solid rgba(0,212,170,0.2); border-radius:8px; padding:12px 16px; margin-top:16px; font-size:13px; color:#94a3b8; }
    .tt-val { font-size:18px; font-weight:700; color:#00d4aa; font-family:monospace; }

    .section-header-row { display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; }

    .sections-list { display:flex; flex-direction:column; gap:14px; }
    .section-card { background:#1e2d45; border:1px solid #2a3f5f; border-radius:12px; padding:18px 20px; }
    .sc-name { font-size:15px; font-weight:600; color:#00d4aa; margin-bottom:14px; }
    .sc-frais-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }
    .sc-frais { display:flex; flex-direction:column; gap:6px; }
    .sc-frais span { font-size:11px; color:#94a3b8; text-transform:uppercase; letter-spacing:0.5px; }
    .compo-link { font-size:11px; color:#00d4aa; cursor:pointer; user-select:none; }
    .compo-link:hover { text-decoration:underline; }
    .compo-row { display:grid; grid-template-columns:1fr 140px 40px; gap:8px; align-items:center; margin-bottom:8px; }
    .compo-total { margin-top:14px; padding-top:10px; border-top:1px solid #2a3f5f; font-size:13px; color:#94a3b8; text-align:right; }
    .sc-frais.total { grid-column:3/4; }
    .sc-total { font-size:16px; font-weight:700; color:#00d4aa; font-family:monospace; padding:8px 0; }
    .sc-actions { display:flex; justify-content:flex-end; margin-top:14px; padding-top:12px; border-top:1px solid #2a3f5f; }

    .table-card { background:#1e2d45; border:1px solid #2a3f5f; border-radius:12px; overflow:hidden; }

    ::ng-deep .p-datatable .p-datatable-thead > tr > th { background:#111827 !important; color:#64748b !important; font-size:11px !important; text-transform:uppercase !important; border-color:#2a3f5f !important; }
    ::ng-deep .p-datatable .p-datatable-tbody > tr { background:#1e2d45 !important; color:#94a3b8 !important; border-bottom:1px solid rgba(42,63,95,0.4) !important; }
    ::ng-deep .p-datatable .p-datatable-tbody > tr:hover { background:#1a2235 !important; }

    .mono  { font-family:monospace; font-size:12px; }
    .bold  { font-weight:600; color:#e8f0fe; }
    .empty-msg { text-align:center; padding:40px; color:#64748b; }

    .alerte-rouge  { background:rgba(239,68,68,0.1); border:1px solid rgba(239,68,68,0.3); border-radius:8px; padding:10px 14px; font-size:13px; color:#ef4444; margin-bottom:8px; }
    .alerte-orange { background:rgba(245,158,11,0.1); border:1px solid rgba(245,158,11,0.3); border-radius:8px; padding:10px 14px; font-size:13px; color:#f59e0b; margin-bottom:8px; }
    .statut-cloture { border-radius:8px; padding:12px 16px; font-size:13px; font-weight:600; margin-bottom:16px; }
    .statut-cloture.ok     { background:rgba(16,185,129,0.1); border:1px solid rgba(16,185,129,0.3); color:#10b981; }
    .statut-cloture.bloque { background:rgba(239,68,68,0.1); border:1px solid rgba(239,68,68,0.3); color:#ef4444; }
    .option-row { padding:12px 0; border-top:1px solid #2a3f5f; margin-bottom:12px; }
    .kpi-mini { border:1px solid #2a3f5f; border-radius:8px; padding:12px; text-align:center; }
    .km-label { font-size:10px; color:#64748b; text-transform:uppercase; margin-bottom:4px; }
    .km-val   { font-weight:700; font-family:monospace; }
  `]
})
export class ParametresComponent implements OnInit {
  onglet       = signal('ecole');
  ecole        = signal<any>(null);
  exercice     = signal<any>(null);
  sections     = signal<any[]>([]);
  users        = signal<any[]>([]);
  saving       = signal(false);
  loadingUsers = signal(false);

  // Nb de mensualités de l'exercice (défaut 10) — utilisé pour le total annuel des sections
  nbMensualites = computed(() => this.exercice()?.nb_mensualites || 10);

  services     = signal<any[]>([]);

  userDialogVisible    = false;
  sectionDialogVisible = false;
  serviceDialogVisible = false;
  mdpDialogVisible     = false;
  userSelectionne: any = null;
  nouveauMdp           = '';

  newUser    = { nom:'', prenom:'', email:'', password:'', role:'ADMIN_SCOLARITE' };
  newSection = { nom:'' };
  newService: any = { nom:'', montant:0, periodicite:'MENSUEL', mois_unique:null, actif:true };

  // Période d'exigibilité d'un service à paiement unique
  // (null = à l'inscription, 1..12 = mois calendaire, libellés dans la langue active)
  get periodeUniqueOptions() {
    const lang = this.translate.currentLang || 'fr';
    const opts: any[] = [{ label: this.translate.instant('parametres.periode_inscription'), value: null }];
    for (let m = 1; m <= 12; m++) {
      const nom = new Date(2000, m - 1, 1).toLocaleDateString(lang, { month: 'long' });
      opts.push({ label: nom.charAt(0).toUpperCase() + nom.slice(1), value: m });
    }
    return opts;
  }

  // ── Composition libre de l'inscription (frais de section flexibles) ──
  compositionDialogVisible = false;
  sectionCompo: any = null;
  compoRows: { libelle: string; montant: number }[] = [];

  ouvrirComposition(s: any) {
    this.sectionCompo = s;
    this.compoRows = (s.composition_inscription || []).map((e: any) => ({ ...e }));
    if (!this.compoRows.length) this.compoRows.push({ libelle: '', montant: 0 });
    this.compositionDialogVisible = true;
  }
  ajouterCompoRow()        { this.compoRows.push({ libelle: '', montant: 0 }); }
  retirerCompoRow(i: number) { this.compoRows.splice(i, 1); }
  totalCompo(): number     { return this.compoRows.reduce((t, r) => t + (+r.montant || 0), 0); }

  validerComposition() {
    const rows = this.compoRows
      .filter(r => (r.libelle || '').trim())
      .map(r => ({ libelle: r.libelle.trim(), montant: +r.montant || 0 }));
    this.sectionCompo.composition_inscription = rows;
    // Liste vide = retour à la saisie directe du montant global
    if (rows.length) this.sectionCompo.frais_inscription = rows.reduce((t, r) => t + r.montant, 0);
    this.compositionDialogVisible = false;
    this.sauvegarderSection(this.sectionCompo);
  }

  periodiciteOptions = [
    { label: 'Mensuel',         value: 'MENSUEL' },
    { label: 'Paiement unique', value: 'UNIQUE'  },
  ];
  actifOptions = [
    { label: 'Actif',   value: true  },
    { label: 'Inactif', value: false },
  ];

  rolesDisponibles: any[] = [];

  private translate = inject(TranslateService);
  private appMode = inject(AppModeService);

  estLocal = this.appMode.isLocal();
  sauvegarde        = signal<any>(null);
  sauvegardeEnCours = signal(false);

  constructor(
    private api: ApiService,
    public auth: AuthService,
    private msg: MessageService
  ) {}

  chargerSauvegarde() {
    this.api.get<any>('/sauvegarde/statut/').subscribe({
      next: res => this.sauvegarde.set(res),
      error: err => console.error(err),
    });
  }

  declencherSauvegarde() {
    this.sauvegardeEnCours.set(true);
    this.api.post<any>('/sauvegarde/declencher/', {}).subscribe({
      next: () => {
        this.sauvegardeEnCours.set(false);
        this.msg.add({ severity: 'success',
                       summary: this.translate.instant('sauvegarde.ok_toast') });
        this.chargerSauvegarde();
      },
      error: err => {
        this.sauvegardeEnCours.set(false);
        this.msg.add({ severity: 'error',
                       summary: this.translate.instant('sauvegarde.erreur_toast'),
                       detail: err?.error?.message || '' });
        this.chargerSauvegarde();
      },
    });
  }

  ngOnInit() {
    this.rolesDisponibles = [
      { label: this.translate.instant('parametres.admin_ecole'),       value: 'ADMIN_ECOLE' },
      { label: this.translate.instant('parametres.admin_comptable'),   value: 'ADMIN_COMPTABLE' },
      { label: this.translate.instant('parametres.admin_rh'),          value: 'ADMIN_RH' },
      { label: this.translate.instant('parametres.admin_scolarite'),   value: 'ADMIN_SCOLARITE' },
      { label: this.translate.instant('parametres.lecteur'),           value: 'LECTEUR' },
    ];
    this.chargerEcole();
    this.chargerExercice();
    this.chargerSections();
    this.chargerUsers();
  }

  verification  = signal<any>(null);
creerSuivant  = true;

chargerVerification() {
  this.api.get<any>('/paiements/cloturer-exercice/').subscribe({
    next: res => this.verification.set(res),
    error: err => console.error(err)
  });
}

confirmerCloture() {
  if (!confirm(
    `Clôturer définitivement l'exercice ${this.verification()?.exercice?.annee_scolaire} ?\n\nCette opération est IRRÉVERSIBLE.`
  )) return;

  this.saving.set(true);
  this.api.post('/paiements/cloturer-exercice/', {
    confirme:      true,
    creer_suivant: this.creerSuivant
  }).subscribe({
    next: (res: any) => {
      this.msg.add({
        severity: 'success',
        summary:  'Exercice clôturé ✅',
        detail:   res.message
      });
      this.saving.set(false);
      this.verification.set(null);
      // Recharger pour voir le nouvel exercice
      setTimeout(() => this.chargerVerification(), 1000);
    },
    error: (err) => {
      const detail = err.error?.problemes?.join(', ') || 'Clôture impossible';
      this.msg.add({ severity:'error', summary:'Erreur', detail });
      this.saving.set(false);
    }
  });
}

  chargerEcole() {
    this.api.get<any>('/tenants/mon_ecole/').subscribe({
      next: res => this.ecole.set({...res}),
      error: err => console.error(err)
    });
  }

chargerExercice() {
  this.api.get<any>('/paiements/exercices/').subscribe({
    next: res => {
      const list = res.results || res;
      if (list.length > 0) {
        // Toujours l'exercice actif : jamais un exercice clôturé (historique migré)
        const e = list.find((x: any) => !x.cloture) || list[0];
        this.exercice.set({
          ...e,
          solde_initial_caisse: +e.solde_initial_caisse,
          solde_initial_banque: +e.solde_initial_banque,
          solde_initial_mobile: +e.solde_initial_mobile,
        });
      }
    }
  });
}

 chargerSections() {
  this.api.get<any>('/eleves/sections/').subscribe({
    next: res => {
      const sections = (res.results || res).map((s: any) => ({
        ...s,
        frais_inscription:  +s.frais_inscription,
        frais_mensualite:   +s.frais_mensualite,
        frais_uniforme:     +s.frais_uniforme,
        frais_fournitures:  +s.frais_fournitures,
      }));
      this.sections.set(sections);
    }
  });
}

  chargerUsers() {
    this.loadingUsers.set(true);
    this.api.get<any>('/auth/users/').subscribe({
      next: res => { this.users.set(res.results || res); this.loadingUsers.set(false); },
      error: () => this.loadingUsers.set(false)
    });
  }

  onLogoSelected(event: Event) {
    const input = event.target as HTMLInputElement;
    const file  = input.files?.[0];
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      this.msg.add({ severity:'warn', summary: this.translate.instant('common.erreur'), detail: this.translate.instant('parametres.logo_format') });
      return;
    }
    if (file.size > 1024 * 1024) {  // 1 Mo max
      this.msg.add({ severity:'warn', summary: this.translate.instant('common.erreur'), detail: this.translate.instant('parametres.logo_trop_gros') });
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      this.ecole.update(e => ({ ...e, logo: reader.result as string }));
    };
    reader.readAsDataURL(file);  // data URI base64 (tous formats image)
    input.value = '';
  }

  retirerLogo() {
    this.ecole.update(e => ({ ...e, logo: '' }));
  }

  // ── Certificat personnalisable ──
  // Éléments togglables du certificat de scolarité (défaut = tout affiché,
  // version standard). Les clés correspondent au cfg lu par le PDF backend.
  certElements = ['entete_ministere', 'reference', 'matricule', 'naissance',
                  'parents', 'signature_parent', 'cachet', 'mention_validite'];
  certCfg: any = {};

  initCertConfig() {
    const saved = this.ecole()?.config_certificat || {};
    const cfg: any = {};
    for (const k of this.certElements) cfg[k] = saved[k] !== false;
    cfg.texte_intro      = saved.texte_intro || '';
    cfg.texte_conclusion = saved.texte_conclusion || '';
    this.certCfg = cfg;
  }

  sauvegarderCertificat() {
    this.saving.set(true);
    this.api.patch<any>('/tenants/mon_ecole/', { config_certificat: this.certCfg }).subscribe({
      next: res => {
        this.ecole.set(res);
        this.msg.add({ severity:'success', summary: this.translate.instant('parametres.sauvegarde_ok'), detail: this.translate.instant('parametres.certificat') });
        this.saving.set(false);
      },
      error: () => { this.msg.add({ severity:'error', summary: this.translate.instant('parametres.erreur'), detail: this.translate.instant('parametres.sauvegarde_echouee') }); this.saving.set(false); }
    });
  }

  sauvegarderEcole() {
    if (!this.ecole()) return;
    this.saving.set(true);
    this.api.patch<any>('/tenants/mon_ecole/', this.ecole()).subscribe({
      next: res => {
        this.ecole.set(res);
        this.msg.add({ severity:'success', summary: this.translate.instant('parametres.sauvegarde_ok'), detail: this.translate.instant('parametres.nom_ecole') });
        this.saving.set(false);
      },
      error: () => { this.msg.add({ severity:'error', summary: this.translate.instant('parametres.erreur'), detail: this.translate.instant('parametres.sauvegarde_echouee') }); this.saving.set(false); }
    });
  }

  sauvegarderExercice() {
    if (!this.exercice()) return;
    this.saving.set(true);
    this.api.patch<any>(`/paiements/exercices/${this.exercice().id}/`, this.exercice()).subscribe({
      next: res => {
        this.exercice.set(res);
        this.msg.add({ severity:'success', summary: this.translate.instant('parametres.sauvegarde_ok'), detail: this.translate.instant('parametres.exercice') });
        this.saving.set(false);
      },
      error: () => { this.msg.add({ severity:'error', summary: this.translate.instant('parametres.erreur'), detail: this.translate.instant('parametres.sauvegarde_echouee') }); this.saving.set(false); }
    });
  }

  sauvegarderSection(s: any) {
    this.saving.set(true);
    this.api.patch<any>(`/eleves/sections/${s.id}/`, s).subscribe({
      next: () => {
        this.msg.add({ severity:'success', summary: this.translate.instant('parametres.sauvegarde_ok'), detail: s.nom });
        this.saving.set(false);
      },
      error: () => { this.msg.add({ severity:'error', summary: this.translate.instant('parametres.erreur'), detail: this.translate.instant('parametres.sauvegarde_echouee') }); this.saving.set(false); }
    });
  }

  supprimerSection(s: any) {
    if (!confirm(this.translate.instant('parametres.section_confirm_suppr') + ' "' + s.nom + '" ?\n' +
                 this.translate.instant('parametres.section_suppr_info'))) return;
    this.api.delete<any>(`/eleves/sections/${s.id}/`).subscribe({
      next: () => {
        this.msg.add({ severity:'success', summary: this.translate.instant('parametres.sauvegarde_ok'), detail: s.nom });
        this.chargerSections();
      },
      error: () => { this.msg.add({ severity:'error', summary: this.translate.instant('parametres.erreur'), detail: this.translate.instant('parametres.sauvegarde_echouee') }); }
    });
  }

  ouvrirDialogSection() {
    this.newSection = { nom:'' };
    this.sectionDialogVisible = true;
  }

  creerSection() {
    if (!this.newSection.nom) {
      this.msg.add({ severity:'warn', summary: this.translate.instant('common.requis'), detail: this.translate.instant('parametres.nom_section_requis') });
      return;
    }
    this.saving.set(true);
    this.api.post<any>('/eleves/sections/', this.newSection).subscribe({
      next: () => {
        this.msg.add({ severity:'success', summary: this.translate.instant('parametres.cree_ok'), detail: this.newSection.nom });
        this.sectionDialogVisible = false;
        this.saving.set(false);
        this.chargerSections();
      },
      error: () => { this.saving.set(false); }
    });
  }

  // ── Services / Activités ───────────────────────────────────────────────
  chargerServices() {
    this.api.get<any>('/eleves/services/').subscribe({
      next: res => {
        const services = (res.results || res).map((s: any) => ({ ...s, montant: +s.montant }));
        this.services.set(services);
      }
    });
  }

  ouvrirDialogService() {
    this.newService = { nom:'', montant:0, periodicite:'MENSUEL', mois_unique:null, actif:true };
    this.serviceDialogVisible = true;
  }

  creerService() {
    if (!this.newService.nom) {
      this.msg.add({ severity:'warn', summary: this.translate.instant('common.requis'), detail: this.translate.instant('parametres.service_nom') });
      return;
    }
    this.saving.set(true);
    this.api.post<any>('/eleves/services/', this.newService).subscribe({
      next: () => {
        this.msg.add({ severity:'success', summary: this.translate.instant('parametres.cree_ok'), detail: this.newService.nom });
        this.serviceDialogVisible = false;
        this.saving.set(false);
        this.chargerServices();
      },
      error: () => { this.saving.set(false); }
    });
  }

  sauvegarderService(sv: any) {
    this.saving.set(true);
    this.api.patch<any>(`/eleves/services/${sv.id}/`, sv).subscribe({
      next: () => {
        this.msg.add({ severity:'success', summary: this.translate.instant('parametres.sauvegarde_ok'), detail: sv.nom });
        this.saving.set(false);
      },
      error: () => { this.msg.add({ severity:'error', summary: this.translate.instant('parametres.erreur'), detail: this.translate.instant('parametres.sauvegarde_echouee') }); this.saving.set(false); }
    });
  }

  supprimerService(sv: any) {
    if (!confirm(this.translate.instant('parametres.service_confirm_suppr') + ' "' + sv.nom + '" ?')) return;
    this.api.delete<any>(`/eleves/services/${sv.id}/`).subscribe({
      next: () => {
        this.msg.add({ severity:'success', summary: this.translate.instant('parametres.sauvegarde_ok'), detail: sv.nom });
        this.chargerServices();
      },
      error: () => { this.msg.add({ severity:'error', summary: this.translate.instant('parametres.erreur'), detail: this.translate.instant('parametres.sauvegarde_echouee') }); }
    });
  }

  ouvrirDialogUser() {
    this.newUser = { nom:'', prenom:'', email:'', password:'', role:'ADMIN_SCOLARITE' };
    this.userDialogVisible = true;
  }

  creerUser() {
    if (!this.newUser.nom || !this.newUser.email || !this.newUser.password) {
      this.msg.add({ severity:'warn', summary: this.translate.instant('common.requis'), detail: this.translate.instant('parametres.tous_champs') });
      return;
    }
    this.saving.set(true);
    this.api.post<any>('/auth/users/', this.newUser).subscribe({
      next: () => {
        this.msg.add({ severity:'success', summary: this.translate.instant('parametres.cree_ok'), detail: this.newUser.nom });
        this.userDialogVisible = false;
        this.saving.set(false);
        this.chargerUsers();
      },
      error: err => {
        const detail = err.error?.email?.[0] || 'Création échouée';
        this.msg.add({ severity:'error', summary:'Erreur', detail });
        this.saving.set(false);
      }
    });
  }

  supprimerUser(u: any) {
    if (!confirm(`Supprimer ${u.nom} ?`)) return;
    this.api.delete(`/auth/users/${u.id}/`).subscribe({
      next: () => {
        this.msg.add({ severity:'success', summary: this.translate.instant('parametres.supprime'), detail: u.nom });
        this.chargerUsers();
      }
    });
  }

  ouvrirChangeMdp(u: any) {
    this.userSelectionne = u;
    this.nouveauMdp      = '';
    this.mdpDialogVisible = true;
  }

  changerMdp() {
    if (!this.nouveauMdp || this.nouveauMdp.length < 6) {
      this.msg.add({ severity:'warn', summary: this.translate.instant('parametres.trop_court'), detail: this.translate.instant('parametres.mdp_min') });
      return;
    }
    this.saving.set(true);
    this.api.post(`/auth/users/${this.userSelectionne.id}/changer_mot_de_passe/`,
      { password: this.nouveauMdp }
    ).subscribe({
      next: () => {
        this.msg.add({ severity:'success', summary: this.translate.instant('parametres.sauvegarde_ok'), detail: this.translate.instant('parametres.mdp_change') });
        this.mdpDialogVisible = false;
        this.saving.set(false);
      },
      error: () => { this.saving.set(false); }
    });
  }
}
