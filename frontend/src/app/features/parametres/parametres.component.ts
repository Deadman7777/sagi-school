import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/services/api.service';
import { AuthService } from '../../core/services/auth.service';
import { InputTextModule } from 'primeng/inputtext';
import { ButtonModule } from 'primeng/button';
import { SelectModule } from 'primeng/select';
import { InputNumberModule } from 'primeng/inputnumber';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { DialogModule } from 'primeng/dialog';
import { TranslateModule } from '@ngx-translate/core';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';

@Component({
  selector: 'app-parametres',
  standalone: true,
  imports: [CommonModule, FormsModule, TranslateModule, InputTextModule, ButtonModule,
            SelectModule, InputNumberModule, TableModule, TagModule,
            DialogModule, ToastModule],
  providers: [MessageService],
  template: `
    <p-toast />

    <div class="page-header">
      <div>
        <h2 class="page-title">{{ 'parametres.title' | translate }}</h2>
        <span class="page-sub">Configuration de votre établissement</span>
      </div>
    </div>

    <!-- Onglets -->
    <div class="tabs-bar">
      <button class="tab-btn" [class.active]="onglet() === 'ecole'"
              (click)="onglet.set('ecole')">🏫 {{ 'parametres.infos_ecole' | translate }}</button>
      <button class="tab-btn" [class.active]="onglet() === 'exercice'"
              (click)="onglet.set('exercice')">📅 Exercice</button>
      <button class="tab-btn" [class.active]="onglet() === 'sections'"
              (click)="onglet.set('sections')">📚 {{ 'parametres.sections' | translate }}</button>
      <button class="tab-btn" [class.active]="onglet() === 'users'"
              (click)="onglet.set('users')">👥 {{ 'parametres.utilisateurs' | translate }}</button>
      <button class="tab-btn" [class.active]="onglet() === 'cloture'"
        (click)="onglet.set('cloture'); chargerVerification()">
        🔒 {{ 'cloture.title' | translate }}
      </button>
    </div>

    <!-- ══ ONGLET INFOS ÉCOLE ══ -->
    <div *ngIf="onglet() === 'ecole'">
      <div class="form-card" *ngIf="ecole()">
        <div class="fc-title">🏫 Informations de l'Établissement</div>
        <div class="form-grid">
          <div class="form-group full">
            <label>Nom de l'établissement *</label>
            <input pInputText [(ngModel)]="ecole()!.nom" class="w-full" />
          </div>
          <div class="form-group">
            <label>Ville</label>
            <input pInputText [(ngModel)]="ecole()!.ville" class="w-full" />
          </div>
          <div class="form-group">
            <label>Téléphone</label>
            <input pInputText [(ngModel)]="ecole()!.telephone" class="w-full" />
          </div>
          <div class="form-group">
            <label>Email</label>
            <input pInputText [(ngModel)]="ecole()!.email" class="w-full" type="email" />
          </div>
          <div class="form-group">
            <label>RCCM</label>
            <input pInputText [(ngModel)]="ecole()!.rccm" class="w-full" />
          </div>
          <div class="form-group full">
            <label>Adresse complète</label>
            <input pInputText [(ngModel)]="ecole()!.adresse" class="w-full" />
          </div>
          <div class="form-group">
            <label>NINEA</label>
            <input pInputText [(ngModel)]="ecole()!.ninea" class="w-full" />
          </div>
        </div>
        <div class="form-actions">
          <p-button label="💾 Sauvegarder" severity="success"
                    [loading]="saving()" (onClick)="sauvegarderEcole()" />
        </div>
      </div>
    </div>

    <!-- ══ ONGLET EXERCICE ══ -->
    <div *ngIf="onglet() === 'exercice'">
      <div class="form-card" *ngIf="exercice()">
        <div class="fc-title">📅 Exercice Scolaire Actif</div>
        <div class="form-grid">
          <div class="form-group full">
            <label>Année scolaire</label>
            <input pInputText [(ngModel)]="exercice()!.annee_scolaire"
                   class="w-full" placeholder="2025-2026" />
          </div>
          <div class="form-group">
            <label>Date de début</label>
            <input type="date" [(ngModel)]="exercice()!.date_debut"
                   class="form-input w-full" />
          </div>
          <div class="form-group">
            <label>Date de fin</label>
            <input type="date" [(ngModel)]="exercice()!.date_fin"
                   class="form-input w-full" />
          </div>
          <div class="form-group">
            <label>Solde initial Caisse (FCFA)</label>
            <p-inputNumber [(ngModel)]="exercice()!.solde_initial_caisse"
                           mode="decimal" [min]="0" styleClass="w-full" />
          </div>
          <div class="form-group">
            <label>Solde initial Banque (FCFA)</label>
            <p-inputNumber [(ngModel)]="exercice()!.solde_initial_banque"
                           mode="decimal" [min]="0" styleClass="w-full" />
          </div>
          <div class="form-group">
            <label>Solde initial Mobile Money (FCFA)</label>
            <p-inputNumber [(ngModel)]="exercice()!.solde_initial_mobile"
                           mode="decimal" [min]="0" styleClass="w-full" />
          </div>
        </div>

        <!-- Total trésorerie initiale -->
        <div class="total-tresorerie">
          <span>Trésorerie initiale totale</span>
          <span class="tt-val">
            {{ (exercice()!.solde_initial_caisse +
                exercice()!.solde_initial_banque +
                exercice()!.solde_initial_mobile) | number:'1.0-0' }} FCFA
          </span>
        </div>

        <div class="form-actions">
          <p-button label="💾 Sauvegarder" severity="success"
                    [loading]="saving()" (onClick)="sauvegarderExercice()" />
        </div>
      </div>
    </div>

    <!-- ══ ONGLET SECTIONS ══ -->
    <div *ngIf="onglet() === 'sections'">
      <div class="section-header-row">
        <div class="fc-title" style="margin:0">📚 Frais par Section</div>
        <p-button label="+ Ajouter Section" severity="success" size="small"
                  (onClick)="ouvrirDialogSection()" />
      </div>

      <div class="sections-list">
        <div class="section-card" *ngFor="let s of sections(); let i = index">
          <div class="sc-name">{{ s.nom }}</div>
          <div class="sc-frais-grid">
            <div class="sc-frais">
              <span>Inscription</span>
              <p-inputNumber [(ngModel)]="s.frais_inscription" mode="decimal"
                             [min]="0" styleClass="w-full" inputStyleClass="text-right" />
            </div>
            <div class="sc-frais">
              <span>Mensualité</span>
              <p-inputNumber [(ngModel)]="s.frais_mensualite" mode="decimal"
                             [min]="0" styleClass="w-full" inputStyleClass="text-right" />
            </div>
            <div class="sc-frais">
              <span>Uniforme</span>
              <p-inputNumber [(ngModel)]="s.frais_uniforme" mode="decimal"
                             [min]="0" styleClass="w-full" inputStyleClass="text-right" />
            </div>
            <div class="sc-frais">
              <span>Fournitures</span>
              <p-inputNumber [(ngModel)]="s.frais_fournitures" mode="decimal"
                             [min]="0" styleClass="w-full" inputStyleClass="text-right" />
            </div>
            <div class="sc-frais">
              <span>Cantine/Yendu</span>
              <p-inputNumber [(ngModel)]="s.frais_yendu" mode="decimal"
                             [min]="0" styleClass="w-full" inputStyleClass="text-right" />
            </div>
            <div class="sc-frais total">
              <span>Total Annuel</span>
              <div class="sc-total">
                {{ (s.frais_inscription + s.frais_uniforme +
                    s.frais_fournitures + (s.frais_mensualite * 10) +
                    s.frais_yendu) | number:'1.0-0' }} FCFA
              </div>
            </div>
          </div>
          <div class="sc-actions">
            <p-button label="💾 Sauvegarder" severity="success" size="small"
                      (onClick)="sauvegarderSection(s)" />
          </div>
        </div>
      </div>
    </div>

    <!-- ══ ONGLET UTILISATEURS ══ -->
    <div *ngIf="onglet() === 'users'">
      <div class="section-header-row">
        <div class="fc-title" style="margin:0">👥 {{ 'parametres.utilisateurs' | translate }} de l'École</div>
        <p-button label="+ Ajouter Utilisateur" severity="success" size="small"
                  (onClick)="ouvrirDialogUser()" />
      </div>

      <div class="table-card">
        <p-table [value]="users()" [loading]="loadingUsers()"
                 styleClass="p-datatable-sm">
          <ng-template pTemplate="header">
            <tr>
              <th>Nom</th><th>Email</th><th>Rôle</th><th>Statut</th><th>Actions</th>
            </tr>
          </ng-template>
          <ng-template pTemplate="body" let-u>
            <tr>
              <td class="bold">{{ u.nom }} {{ u.prenom }}</td>
              <td class="mono">{{ u.email }}</td>
              <td>
                <p-tag [value]="u.role"
                       [severity]="u.role === 'ADMIN_ECOLE' ? 'success' :
                                   u.role === 'COMPTABLE' ? 'info' : 'warn'" />
              </td>
              <td>
                <p-tag [value]="u.actif ? 'Actif' : 'Inactif'"
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
            <tr><td colspan="5" class="empty-msg">Aucun utilisateur</td></tr>
          </ng-template>
        </p-table>
      </div>
    </div>

    <!-- ══ ONGLET CLÔTURE ══ -->
<div *ngIf="onglet() === 'cloture'">
  <div class="form-card" *ngIf="verification()">

    <div class="fc-title">🔒 Clôture de l'Exercice {{ verification()!.exercice?.annee_scolaire }}</div>

    <!-- Résumé financier -->
    <div class="kpi-row" style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:20px">
      <div class="kpi-mini teal">
        <div class="km-label">Total Recettes</div>
        <div class="km-val" style="color:#00d4aa;font-size:16px">
          {{ verification()!.stats.total_recettes | number:'1.0-0' }} FCFA
        </div>
      </div>
      <div class="kpi-mini blue">
        <div class="km-label">Total Charges</div>
        <div class="km-val" style="color:#0099ff;font-size:16px">
          {{ verification()!.stats.total_charges | number:'1.0-0' }} FCFA
        </div>
      </div>
      <div class="kpi-mini"
           [style.border-color]="verification()!.stats.resultat_net >= 0 ? '#10b981' : '#ef4444'">
        <div class="km-label">Résultat Net</div>
        <div class="km-val" style="font-size:16px"
             [style.color]="verification()!.stats.resultat_net >= 0 ? '#10b981' : '#ef4444'">
          {{ verification()!.stats.resultat_net | number:'1.0-0' }} FCFA
        </div>
      </div>
    </div>

    <!-- Élèves -->
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:20px">
      <div style="background:#0b0f1a;border:1px solid #2a3f5f;border-radius:8px;padding:12px">
        <div style="font-size:11px;color:#64748b;margin-bottom:4px">Total Élèves</div>
        <div style="font-size:20px;font-weight:700;color:#e8f0fe;font-family:monospace">
          {{ verification()!.stats.eleves_total }}
        </div>
      </div>
      <div style="background:#0b0f1a;border:1px solid #2a3f5f;border-radius:8px;padding:12px"
           [style.border-color]="verification()!.stats.eleves_impayes > 0 ? '#f59e0b' : '#2a3f5f'">
        <div style="font-size:11px;color:#64748b;margin-bottom:4px">Élèves avec solde impayé</div>
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
        ✅ L'exercice peut être clôturé
      </span>
      <span *ngIf="!verification()!.peut_cloturer">
        ❌ Des problèmes bloquants doivent être résolus avant la clôture
      </span>
    </div>

    <!-- Option nouvel exercice -->
    <div class="option-row" *ngIf="verification()!.peut_cloturer">
      <label style="display:flex;align-items:center;gap:10px;cursor:pointer;font-size:13px;color:#94a3b8">
        <input type="checkbox" [(ngModel)]="creerSuivant" style="width:16px;height:16px">
        Créer automatiquement le nouvel exercice après clôture
      </label>
    </div>

    <!-- Bouton clôture -->
    <div class="form-actions" style="gap:12px" *ngIf="verification()!.peut_cloturer">
      <div style="font-size:12px;color:#ef4444;align-self:center">
        ⚠️ Cette opération est irréversible
      </div>
      <p-button
        label="🔒 Clôturer l'Exercice"
        severity="danger"
        [loading]="saving()"
        (onClick)="confirmerCloture()" />
    </div>

  </div>

  <!-- Loading -->
  <div class="empty-msg" *ngIf="!verification()">
    Chargement de la vérification...
  </div>
</div>

    <!-- Dialog nouvel utilisateur -->
    <p-dialog header="👤 Nouvel Utilisateur" [(visible)]="userDialogVisible"
              [modal]="true" [style]="{width:'460px'}" [draggable]="false">
      <div class="form-grid">
        <div class="form-group">
          <label>Nom *</label>
          <input pInputText [(ngModel)]="newUser.nom" class="w-full" />
        </div>
        <div class="form-group">
          <label>Prénom</label>
          <input pInputText [(ngModel)]="newUser.prenom" class="w-full" />
        </div>
        <div class="form-group full">
          <label>Email *</label>
          <input pInputText [(ngModel)]="newUser.email" class="w-full" type="email" />
        </div>
        <div class="form-group full">
          <label>Mot de passe *</label>
          <input pInputText [(ngModel)]="newUser.password" class="w-full" type="password" />
        </div>
        <div class="form-group full">
          <label>Rôle *</label>
          <p-select [options]="rolesDisponibles" [(ngModel)]="newUser.role"
                    optionLabel="label" optionValue="value" styleClass="w-full" />
        </div>
      </div>
      <ng-template pTemplate="footer">
        <p-button label="Annuler" severity="secondary" (onClick)="userDialogVisible=false" />
        <p-button label="Créer" severity="success"
                  [loading]="saving()" (onClick)="creerUser()" />
      </ng-template>
    </p-dialog>

    <!-- Dialog nouvelle section -->
    <p-dialog header="📚 Nouvelle Section" [(visible)]="sectionDialogVisible"
              [modal]="true" [style]="{width:'400px'}" [draggable]="false">
      <div class="form-group" style="margin-bottom:14px">
        <label>Nom de la section *</label>
        <input pInputText [(ngModel)]="newSection.nom" class="w-full"
               placeholder="Ex: CP1, CE1, Maternelle..." />
      </div>
      <ng-template pTemplate="footer">
        <p-button label="Annuler" severity="secondary" (onClick)="sectionDialogVisible=false" />
        <p-button label="Créer" severity="success"
                  [loading]="saving()" (onClick)="creerSection()" />
      </ng-template>
    </p-dialog>

    <!-- Dialog changer mot de passe -->
    <p-dialog header="🔑 Changer le Mot de Passe" [(visible)]="mdpDialogVisible"
              [modal]="true" [style]="{width:'380px'}" [draggable]="false">
      <div *ngIf="userSelectionne">
        <div style="font-size:13px;color:#94a3b8;margin-bottom:16px">
          Utilisateur : <strong style="color:#e8f0fe">{{ userSelectionne.nom }}</strong>
        </div>
        <div class="form-group">
          <label>Nouveau mot de passe *</label>
          <input pInputText [(ngModel)]="nouveauMdp" class="w-full"
                 type="password" placeholder="Min. 6 caractères" />
        </div>
      </div>
      <ng-template pTemplate="footer">
        <p-button label="Annuler" severity="secondary" (onClick)="mdpDialogVisible=false" />
        <p-button label="Confirmer" severity="success"
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

  userDialogVisible    = false;
  sectionDialogVisible = false;
  mdpDialogVisible     = false;
  userSelectionne: any = null;
  nouveauMdp           = '';

  newUser    = { nom:'', prenom:'', email:'', password:'', role:'CAISSIER' };
  newSection = { nom:'' };

  rolesDisponibles = [
    { label: 'Admin École',   value: 'ADMIN_ECOLE' },
    { label: 'Comptable',     value: 'COMPTABLE' },
    { label: 'Caissier',      value: 'CAISSIER' },
    { label: 'Lecture seule', value: 'LECTURE' },
  ];

  constructor(
    private api: ApiService,
    public auth: AuthService,
    private msg: MessageService
  ) {}

  ngOnInit() {
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
        const e = list[0];
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
        frais_yendu:        +s.frais_yendu,
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

  sauvegarderEcole() {
    if (!this.ecole()) return;
    this.saving.set(true);
    this.api.patch<any>('/tenants/mon_ecole/', this.ecole()).subscribe({
      next: res => {
        this.ecole.set(res);
        this.msg.add({ severity:'success', summary:'Sauvegardé ✅', detail:'Infos école mises à jour' });
        this.saving.set(false);
      },
      error: () => { this.msg.add({ severity:'error', summary:'Erreur', detail:'Sauvegarde échouée' }); this.saving.set(false); }
    });
  }

  sauvegarderExercice() {
    if (!this.exercice()) return;
    this.saving.set(true);
    this.api.patch<any>(`/paiements/exercices/${this.exercice().id}/`, this.exercice()).subscribe({
      next: res => {
        this.exercice.set(res);
        this.msg.add({ severity:'success', summary:'Sauvegardé ✅', detail:'Exercice mis à jour' });
        this.saving.set(false);
      },
      error: () => { this.msg.add({ severity:'error', summary:'Erreur', detail:'Sauvegarde échouée' }); this.saving.set(false); }
    });
  }

  sauvegarderSection(s: any) {
    this.saving.set(true);
    this.api.patch<any>(`/eleves/sections/${s.id}/`, s).subscribe({
      next: () => {
        this.msg.add({ severity:'success', summary:'Sauvegardé ✅', detail:`Section ${s.nom} mise à jour` });
        this.saving.set(false);
      },
      error: () => { this.msg.add({ severity:'error', summary:'Erreur', detail:'Sauvegarde échouée' }); this.saving.set(false); }
    });
  }

  ouvrirDialogSection() {
    this.newSection = { nom:'' };
    this.sectionDialogVisible = true;
  }

  creerSection() {
    if (!this.newSection.nom) {
      this.msg.add({ severity:'warn', summary:'Requis', detail:'Le nom est obligatoire' });
      return;
    }
    this.saving.set(true);
    this.api.post<any>('/eleves/sections/', this.newSection).subscribe({
      next: () => {
        this.msg.add({ severity:'success', summary:'Créée ✅', detail:`Section ${this.newSection.nom} ajoutée` });
        this.sectionDialogVisible = false;
        this.saving.set(false);
        this.chargerSections();
      },
      error: () => { this.saving.set(false); }
    });
  }

  ouvrirDialogUser() {
    this.newUser = { nom:'', prenom:'', email:'', password:'', role:'CAISSIER' };
    this.userDialogVisible = true;
  }

  creerUser() {
    if (!this.newUser.nom || !this.newUser.email || !this.newUser.password) {
      this.msg.add({ severity:'warn', summary:'Requis', detail:'Remplissez tous les champs obligatoires' });
      return;
    }
    this.saving.set(true);
    this.api.post<any>('/auth/users/', this.newUser).subscribe({
      next: () => {
        this.msg.add({ severity:'success', summary:'Créé ✅', detail:`Utilisateur ${this.newUser.nom} ajouté` });
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
        this.msg.add({ severity:'success', summary:'Supprimé', detail:u.nom });
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
      this.msg.add({ severity:'warn', summary:'Trop court', detail:'Min. 6 caractères' });
      return;
    }
    this.saving.set(true);
    this.api.post(`/auth/users/${this.userSelectionne.id}/changer_mot_de_passe/`,
      { password: this.nouveauMdp }
    ).subscribe({
      next: () => {
        this.msg.add({ severity:'success', summary:'Modifié ✅', detail:'Mot de passe changé' });
        this.mdpDialogVisible = false;
        this.saving.set(false);
      },
      error: () => { this.saving.set(false); }
    });
  }
}
