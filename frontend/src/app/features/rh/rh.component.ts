import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RhService } from '../../core/services/rh.service';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { TagModule } from 'primeng/tag';
import { InputNumberModule } from 'primeng/inputnumber';
import { MessageService } from 'primeng/api';
import { ToastModule } from 'primeng/toast';

@Component({
  selector: 'app-rh',
  standalone: true,
  imports: [CommonModule, FormsModule, TableModule, ButtonModule, DialogModule,
            InputTextModule, SelectModule, TagModule, InputNumberModule, ToastModule],
  providers: [MessageService],
  template: `
    <p-toast />
    <div class="page-header">
      <div>
        <h2 class="page-title">👥 Ressources Humaines</h2>
        <span class="page-sub">Personnel · Paie · Bulletins</span>
      </div>
    </div>

    <!-- KPIs -->
    <div class="kpi-grid" *ngIf="stats()">
      <div class="kpi-card" style="--acc:#00d4aa">
        <div class="kpi-icon">👥</div>
        <div class="kpi-label">Total Employés</div>
        <div class="kpi-value" style="color:#00d4aa">{{ stats().total_employes }}</div>
        <div class="kpi-sub">{{ stats().actifs }} actifs</div>
      </div>
      <div class="kpi-card" style="--acc:#0099ff">
        <div class="kpi-icon">📚</div>
        <div class="kpi-label">Enseignants</div>
        <div class="kpi-value" style="color:#0099ff">{{ stats().enseignants }}</div>
      </div>
      <div class="kpi-card" style="--acc:#a855f7">
        <div class="kpi-icon">🏢</div>
        <div class="kpi-label">Administration</div>
        <div class="kpi-value" style="color:#a855f7">{{ stats().administration }}</div>
      </div>
      <div class="kpi-card" style="--acc:#f59e0b">
        <div class="kpi-icon">💰</div>
        <div class="kpi-label">Masse Salariale</div>
        <div class="kpi-value" style="color:#f59e0b">{{ stats().masse_salariale | number:'1.0-0' }}</div>
        <div class="kpi-sub">FCFA / mois</div>
      </div>
    </div>

    <!-- Onglets -->
    <div class="tabs-bar">
      <button class="tab-btn" [class.active]="onglet() === 'employes'" (click)="onglet.set('employes')">👤 Employés</button>
      <button class="tab-btn" [class.active]="onglet() === 'paie'" (click)="onglet.set('paie')">💰 Paie</button>
    </div>

    <!-- EMPLOYÉS -->
    <div class="table-card" *ngIf="onglet() === 'employes'">
      <div style="display:flex;justify-content:space-between;align-items:center;padding:16px">
        <span style="color:#e8f0fe;font-weight:600">{{ employes().length }} employés</span>
        <p-button label="Nouvel Employé" severity="success" (onClick)="ouvrirDialogEmploye()" />
      </div>
      <p-table [value]="employes()" [loading]="loading()" styleClass="p-datatable-sm"
               [paginator]="true" [rows]="15">
        <ng-template pTemplate="header">
          <tr>
            <th>Matricule</th>
            <th>Nom Complet</th>
            <th>Type</th>
            <th>Poste</th>
            <th>Contrat</th>
            <th>Salaire Base</th>
            <th>Salaire Net</th>
            <th>Statut</th>
            <th>Actions</th>
          </tr>
        </ng-template>
        <ng-template pTemplate="body" let-e>
          <tr>
            <td class="mono">{{ e.matricule }}</td>
            <td class="bold">{{ e.nom_complet }}</td>
            <td>{{ e.type_employe }}</td>
            <td>{{ e.poste }}</td>
            <td>{{ e.type_contrat }}</td>
            <td class="mono">{{ e.salaire_base | number:'1.0-0' }}</td>
            <td class="mono success">{{ e.salaire_net | number:'1.0-0' }}</td>
            <td>
              <p-tag [value]="e.statut"
                     [severity]="e.statut === 'ACTIF' ? 'success' : e.statut === 'CONGE' ? 'warn' : 'danger'" />
            </td>
            <td>
              <p-button icon="pi pi-money-bill" [rounded]="true" [text]="true"
                        severity="success" (onClick)="ouvrirDialogPaie(e)"
                        title="Générer paie" />
            </td>
          </tr>
        </ng-template>
        <ng-template pTemplate="emptymessage">
          <tr><td colspan="9" class="empty-msg">Aucun employé — ajoutez du personnel</td></tr>
        </ng-template>
      </p-table>
    </div>

    <!-- PAIE -->
    <div class="table-card" *ngIf="onglet() === 'paie'">
      <div style="padding:16px">
        <span style="color:#e8f0fe;font-weight:600">Historique des paies</span>
      </div>
      <p-table [value]="paies()" styleClass="p-datatable-sm" [paginator]="true" [rows]="15">
        <ng-template pTemplate="header">
          <tr>
            <th>Mois</th>
            <th>Employé</th>
            <th>Salaire Brut</th>
            <th>IPRES</th>
            <th>CSS</th>
            <th>IR</th>
            <th>Salaire Net</th>
            <th>Statut</th>
          </tr>
        </ng-template>
        <ng-template pTemplate="body" let-p>
          <tr>
            <td class="mono bold">{{ p.mois }}</td>
            <td>{{ p.employe_nom }}</td>
            <td class="mono">{{ p.salaire_brut | number:'1.0-0' }}</td>
            <td class="mono danger">{{ p.ipres | number:'1.0-0' }}</td>
            <td class="mono danger">{{ p.css | number:'1.0-0' }}</td>
            <td class="mono danger">{{ p.ir | number:'1.0-0' }}</td>
            <td class="mono success">{{ p.salaire_net | number:'1.0-0' }}</td>
            <td><p-tag [value]="p.statut" severity="success" /></td>
          </tr>
        </ng-template>
        <ng-template pTemplate="emptymessage">
          <tr><td colspan="8" class="empty-msg">Aucune paie enregistrée</td></tr>
        </ng-template>
      </p-table>
    </div>

    <!-- Dialog Employé -->
    <p-dialog header="👤 Nouvel Employé" [(visible)]="dialogEmployeVisible"
              [modal]="true" [style]="{width:'520px'}" [draggable]="false">
      <div class="form-grid">
        <div class="form-group full">
          <label>Nom Complet *</label>
          <input pInputText [(ngModel)]="formEmploye.nom_complet" class="w-full" />
        </div>
        <div class="form-group">
          <label>Type *</label>
          <p-select [options]="typesEmploye" [(ngModel)]="formEmploye.type_employe"
                    optionLabel="label" optionValue="value" styleClass="w-full" />
        </div>
        <div class="form-group">
          <label>Poste *</label>
          <input pInputText [(ngModel)]="formEmploye.poste" class="w-full" />
        </div>
        <div class="form-group">
          <label>Type Contrat</label>
          <p-select [options]="typesContrat" [(ngModel)]="formEmploye.type_contrat"
                    optionLabel="label" optionValue="value" styleClass="w-full" />
        </div>
        <div class="form-group">
          <label>Date Embauche *</label>
          <input pInputText type="date" [(ngModel)]="formEmploye.date_embauche" class="w-full" />
        </div>
        <div class="form-group full">
          <label>Salaire de Base (FCFA) *</label>
          <p-inputNumber [(ngModel)]="formEmploye.salaire_base" [min]="0"
                         mode="decimal" styleClass="w-full" />
        </div>
        <div class="form-group">
          <label>Téléphone</label>
          <input pInputText [(ngModel)]="formEmploye.telephone" class="w-full" />
        </div>
        <div class="form-group">
          <label>Email</label>
          <input pInputText [(ngModel)]="formEmploye.email" class="w-full" />
        </div>
      </div>
      <ng-template pTemplate="footer">
        <p-button label="Annuler" severity="secondary" (onClick)="dialogEmployeVisible=false" />
        <p-button label="Enregistrer" severity="success"
                  [loading]="saving()" (onClick)="sauvegarderEmploye()" />
      </ng-template>
    </p-dialog>

    <!-- Dialog Paie -->
    <p-dialog header="💰 Générer Bulletin de Paie" [(visible)]="dialogPaieVisible"
              [modal]="true" [style]="{width:'460px'}" [draggable]="false">
      <div *ngIf="employeSelectionne" class="employe-info" style="margin-bottom:16px">
        <div style="font-weight:700;color:#e8f0fe;margin-bottom:8px">
          {{ employeSelectionne.nom_complet }}
        </div>
        <div style="font-size:12px;color:#64748b">{{ employeSelectionne.poste }}</div>
      </div>
      <div class="form-grid">
        <div class="form-group full">
          <label>Mois (YYYY-MM) *</label>
          <input pInputText [(ngModel)]="formPaie.mois" class="w-full"
                 placeholder="Ex: 2026-04" />
        </div>
        <div class="form-group full">
          <label>Salaire Brut (FCFA)</label>
          <p-inputNumber [(ngModel)]="formPaie.salaire_brut" [min]="0"
                         mode="decimal" styleClass="w-full" />
        </div>
      </div>
      <!-- Aperçu calcul -->
      <div class="calcul-paie" *ngIf="formPaie.salaire_brut > 0">
        <div class="cp-row"><span>Salaire Brut</span><span>{{ formPaie.salaire_brut | number:'1.0-0' }}</span></div>
        <div class="cp-row danger"><span>IPRES (5.6%)</span><span>-{{ formPaie.salaire_brut * 0.056 | number:'1.0-0' }}</span></div>
        <div class="cp-row danger"><span>CSS (0.7%)</span><span>-{{ formPaie.salaire_brut * 0.007 | number:'1.0-0' }}</span></div>
        <div class="cp-row danger"><span>IR</span><span>-{{ calculIR(formPaie.salaire_brut) | number:'1.0-0' }}</span></div>
        <div class="cp-total"><span>NET À PAYER</span><span>{{ calculNet(formPaie.salaire_brut) | number:'1.0-0' }} FCFA</span></div>
      </div>
      <ng-template pTemplate="footer">
        <p-button label="Annuler" severity="secondary" (onClick)="dialogPaieVisible=false" />
        <p-button label="Enregistrer" severity="success"
                  [loading]="saving()" (onClick)="sauvegarderPaie()" />
      </ng-template>
    </p-dialog>
  `,
  styles: [`
    .page-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:16px; }
    .page-title  { font-size:20px; font-weight:600; color:#e8f0fe; margin:0 0 4px; }
    .page-sub    { font-size:12px; color:#64748b; }
    .kpi-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:20px; }
    .kpi-card { background:#1e2d45; border:1px solid #2a3f5f; border-radius:12px; padding:16px; border-top:3px solid var(--acc); }
    .kpi-icon  { font-size:24px; margin-bottom:8px; }
    .kpi-label { font-size:11px; color:#64748b; text-transform:uppercase; letter-spacing:0.5px; }
    .kpi-value { font-size:24px; font-weight:700; font-family:monospace; margin:4px 0; }
    .kpi-sub   { font-size:11px; color:#64748b; }
    .tabs-bar { display:flex; gap:3px; margin-bottom:16px; background:#111827; border:1px solid #2a3f5f; border-radius:10px; padding:4px; }
    .tab-btn { flex:1; padding:7px 8px; border:none; border-radius:7px; background:transparent; color:#64748b; font-size:12px; cursor:pointer; }
    .tab-btn.active { background:#1e2d45; color:#00d4aa; font-weight:600; border:1px solid #2a3f5f; }
    .table-card { background:#1e2d45; border:1px solid #2a3f5f; border-radius:12px; overflow:hidden; }
    ::ng-deep .p-datatable .p-datatable-thead > tr > th { background:#111827 !important; color:#64748b !important; font-size:11px !important; text-transform:uppercase !important; border-color:#2a3f5f !important; }
    ::ng-deep .p-datatable .p-datatable-tbody > tr { background:#1e2d45 !important; color:#94a3b8 !important; border-bottom:1px solid rgba(42,63,95,0.4) !important; }
    .mono { font-family:monospace; font-size:12px; }
    .bold { font-weight:600; color:#e8f0fe; }
    .success { color:#10b981; }
    .danger  { color:#ef4444; }
    .empty-msg { text-align:center; padding:40px; color:#64748b; }
    .form-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
    .form-group { display:flex; flex-direction:column; gap:6px; }
    .form-group label { font-size:12px; color:#94a3b8; text-transform:uppercase; }
    .form-group.full { grid-column:1/-1; }
    .w-full { width:100%; }
    .employe-info { background:#0f1a2e; border:1px solid #2a3f5f; border-radius:8px; padding:12px; }
    .calcul-paie { background:#0f1a2e; border:1px solid #2a3f5f; border-radius:8px; padding:14px; margin-top:12px; }
    .cp-row { display:flex; justify-content:space-between; font-size:13px; padding:5px 0; border-bottom:1px solid rgba(42,63,95,0.3); color:#94a3b8; }
    .cp-row.danger span:last-child { color:#ef4444; }
    .cp-total { display:flex; justify-content:space-between; font-size:15px; font-weight:700; padding:10px 0 0; color:#00d4aa; }
  `]
})
export class RhComponent implements OnInit {
  onglet   = signal('employes');
  employes = signal<any[]>([]);
  paies    = signal<any[]>([]);
  stats    = signal<any>(null);
  loading  = signal(true);
  saving   = signal(false);
  dialogEmployeVisible = false;
  dialogPaieVisible    = false;
  employeSelectionne: any = null;

  formEmploye = {
    nom_complet: '', type_employe: 'ENSEIGNANT', poste: '',
    type_contrat: 'CDI', date_embauche: '', salaire_base: 0,
    telephone: '', email: ''
  };

  formPaie = { mois: '', salaire_brut: 0, employe: '' };

  typesEmploye = [
    { label: 'Enseignant',    value: 'ENSEIGNANT' },
    { label: 'Administration',value: 'ADMINISTRATION' },
    { label: 'Personnel d\'appui', value: 'APPUI' },
  ];

  typesContrat = [
    { label: 'CDI',       value: 'CDI' },
    { label: 'CDD',       value: 'CDD' },
    { label: 'Vacataire', value: 'VACATAIRE' },
    { label: 'Stagiaire', value: 'STAGIAIRE' },
  ];

  constructor(private rh: RhService, private msg: MessageService) {}

  ngOnInit() {
    this.chargerDonnees();
  }

  chargerDonnees() {
    this.loading.set(true);
    this.rh.getStats().subscribe({ next: res => this.stats.set(res) });
    this.rh.getEmployes().subscribe({
      next: res => {
        this.employes.set(Array.isArray(res) ? res : res.results || []);
        this.loading.set(false);
      },
      error: () => this.loading.set(false)
    });
    this.rh.getPaies().subscribe({
      next: res => this.paies.set(Array.isArray(res) ? res : res.results || [])
    });
  }

  ouvrirDialogEmploye() {
    this.formEmploye = {
      nom_complet: '', type_employe: 'ENSEIGNANT', poste: '',
      type_contrat: 'CDI', date_embauche: '', salaire_base: 0,
      telephone: '', email: ''
    };
    this.dialogEmployeVisible = true;
  }

  ouvrirDialogPaie(employe: any) {
    this.employeSelectionne = employe;
    const now = new Date();
    this.formPaie = {
      mois: `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`,
      salaire_brut: employe.salaire_base,
      employe: employe.id
    };
    this.dialogPaieVisible = true;
  }

  sauvegarderEmploye() {
    if (!this.formEmploye.nom_complet || !this.formEmploye.poste) {
      this.msg.add({ severity: 'warn', summary: 'Champs requis', detail: 'Nom et poste obligatoires' });
      return;
    }
    this.saving.set(true);
    this.rh.creerEmploye(this.formEmploye).subscribe({
      next: () => {
        this.msg.add({ severity: 'success', summary: 'Succès', detail: 'Employé ajouté ✅' });
        this.dialogEmployeVisible = false;
        this.saving.set(false);
        this.chargerDonnees();
      },
      error: () => { this.saving.set(false); }
    });
  }

  sauvegarderPaie() {
    if (!this.formPaie.mois || this.formPaie.salaire_brut <= 0) return;
    this.saving.set(true);
    const brut = this.formPaie.salaire_brut;
    const ipres = brut * 0.056;
    const css   = brut * 0.007;
    const ir    = this.calculIR(brut);
    const net   = this.calculNet(brut);
    this.rh.creerPaie({
      ...this.formPaie,
      ipres: Math.round(ipres),
      css:   Math.round(css),
      ir:    Math.round(ir),
      salaire_net: Math.round(net),
    }).subscribe({
      next: () => {
        this.msg.add({ severity: 'success', summary: 'Paie enregistrée ✅', detail: `Net: ${Math.round(net).toLocaleString()} FCFA` });
        this.dialogPaieVisible = false;
        this.saving.set(false);
        this.chargerDonnees();
      },
      error: () => { this.saving.set(false); }
    });
  }

  calculIR(brut: number): number {
    return Math.max(brut - 500000, 0) * 0.20;
  }

  calculNet(brut: number): number {
    return brut - (brut * 0.056) - (brut * 0.007) - this.calculIR(brut);
  }
}
