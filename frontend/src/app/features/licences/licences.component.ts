import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { LicencesService, NouvelleEcole } from '../../core/services/licences.service';
import { AuthService } from '../../core/services/auth.service';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { TagModule } from 'primeng/tag';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { InputNumberModule } from 'primeng/inputnumber';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';

@Component({
  selector: 'app-licences',
  standalone: true,
  imports: [CommonModule, FormsModule, TableModule, ButtonModule, TagModule,
            DialogModule, InputTextModule, SelectModule, InputNumberModule, ToastModule],
  providers: [MessageService],
  template: `
    <p-toast />

    <!-- Header -->
    <div class="page-header">
      <div>
        <h2 class="page-title">🔐 Licences & Clients</h2>
        <span class="page-sub">Gestion multi-écoles — HADY GESMAN</span>
      </div>
      <p-button label="+ Nouvelle École" severity="success" (onClick)="ouvrirDialog()" />
    </div>

    <!-- Stats globales -->
    <div class="kpi-grid" *ngIf="stats()">
      <div class="kpi-card" style="--acc:#00d4aa">
        <div class="kpi-icon">🏫</div>
        <div class="kpi-label">Total Écoles</div>
        <div class="kpi-value" style="color:#00d4aa">{{ stats().total_ecoles }}</div>
      </div>
      <div class="kpi-card" style="--acc:#10b981">
        <div class="kpi-icon">✅</div>
        <div class="kpi-label">Licences Actives</div>
        <div class="kpi-value" style="color:#10b981">{{ stats().actives }}</div>
      </div>
      <div class="kpi-card" style="--acc:#f59e0b">
        <div class="kpi-icon">⏳</div>
        <div class="kpi-label">En Essai</div>
        <div class="kpi-value" style="color:#f59e0b">{{ stats().essai }}</div>
      </div>
      <div class="kpi-card" style="--acc:#ef4444">
        <div class="kpi-icon">❌</div>
        <div class="kpi-label">Expirées</div>
        <div class="kpi-value" style="color:#ef4444">{{ stats().expirees }}</div>
      </div>
      <div class="kpi-card" style="--acc:#0099ff">
        <div class="kpi-icon">👥</div>
        <div class="kpi-label">Total Élèves</div>
        <div class="kpi-value" style="color:#0099ff">{{ stats().total_eleves }}</div>
      </div>
      <div class="kpi-card" style="--acc:#a855f7">
        <div class="kpi-icon">💵</div>
        <div class="kpi-label">Revenus / An</div>
        <div class="kpi-value" style="color:#a855f7">{{ stats().revenus_annuels | number:'1.0-0' }}</div>
        <div class="kpi-sub">FCFA</div>
      </div>
    </div>

    <!-- Alertes expiration -->
    <div class="alerte-expiration" *ngIf="stats()?.alertes_expiration?.length">
      <div class="ae-title">⚠️ Licences expirant dans 30 jours</div>
      <div class="ae-row" *ngFor="let a of stats().alertes_expiration">
        <span class="ae-ecole">{{ a.ecole }}</span>
        <span class="ae-type">{{ a.type }}</span>
        <span class="ae-jours" [style.color]="a.jours_restants <= 7 ? '#ef4444' : '#f59e0b'">
          {{ a.jours_restants }}j restants
        </span>
        <span class="ae-date">{{ a.date_fin }}</span>
      </div>
    </div>

    <!-- Table licences -->
    <div class="table-card">
      <p-table [value]="licences()" [loading]="loading()"
               styleClass="p-datatable-sm" [paginator]="true" [rows]="15">
        <ng-template pTemplate="header">
          <tr>
            <th>École</th>
            <th>Clé Licence</th>
            <th>Type</th>
            <th>Statut</th>
            <th>Date Début</th>
            <th>Date Fin</th>
            <th>Jours Restants</th>
            <th>Actions</th>
          </tr>
        </ng-template>
        <ng-template pTemplate="body" let-l>
          <tr>
            <td class="bold">{{ l.tenant_nom }}</td>
            <td class="mono cle">{{ l.cle_licence }}</td>
            <td>
              <p-tag [value]="l.type"
                     [severity]="typeSeverity(l.type)" />
            </td>
            <td>
              <p-tag [value]="l.statut"
                     [severity]="statutSeverity(l.statut)" />
            </td>
            <td class="mono">{{ l.date_debut }}</td>
            <td class="mono">{{ l.date_fin }}</td>
            <td>
              <span [style.color]="joursColor(l.jours_restants)"
                    style="font-family:monospace;font-weight:700">
                {{ l.jours_restants }}j
              </span>
            </td>
            <td>
              <p-button icon="pi pi-refresh" [rounded]="true" [text]="true"
                        severity="success" (onClick)="ouvrirRenouvellement(l)"
                        pTooltip="Renouveler" />
              <p-button icon="pi pi-copy" [rounded]="true" [text]="true"
                        severity="info" (onClick)="copierCle(l.cle_licence)"
                        pTooltip="Copier la clé" />
            </td>
          </tr>
        </ng-template>
        <ng-template pTemplate="emptymessage">
          <tr><td colspan="8" class="empty-msg">Aucune licence — créez votre première école</td></tr>
        </ng-template>
      </p-table>
    </div>

    <!-- Dialog nouvelle école -->
    <p-dialog header="🏫 Nouvelle École Cliente" [(visible)]="dialogVisible"
              [modal]="true" [style]="{width:'560px'}" [draggable]="false">
      <div class="form-grid">
        <div class="form-group full">
          <label>Nom de l'École *</label>
          <input pInputText [(ngModel)]="form.nom" class="w-full" placeholder="Ex: École Al Firdaws" />
        </div>
        <div class="form-group">
          <label>Ville</label>
          <input pInputText [(ngModel)]="form.ville" class="w-full" placeholder="Dakar, Thiès..." />
        </div>
        <div class="form-group">
          <label>Téléphone</label>
          <input pInputText [(ngModel)]="form.telephone" class="w-full" placeholder="7X XXX XX XX" />
        </div>
        <div class="form-group">
          <label>Email</label>
          <input pInputText [(ngModel)]="form.email" class="w-full" type="email" />
        </div>
        <div class="form-group">
          <label>RCCM</label>
          <input pInputText [(ngModel)]="form.rccm" class="w-full" placeholder="SN.DKR.2025.A.XXXXX" />
        </div>
        <div class="form-group">
          <label>NINEA</label>
          <input pInputText [(ngModel)]="form.ninea" class="w-full" />
        </div>

        <div class="separator full">⚙️ Licence</div>

        <div class="form-group">
          <label>Type de Licence *</label>
          <p-select [options]="typesLicence" [(ngModel)]="form.type_licence"
                    optionLabel="label" optionValue="value"
                    styleClass="w-full" />
        </div>
        <div class="form-group">
          <label>Durée (mois)</label>
          <p-inputNumber [(ngModel)]="form.mois_licence" [min]="1" [max]="36"
                         styleClass="w-full" />
        </div>
        <div class="form-group">
          <label>Année Scolaire</label>
          <input pInputText [(ngModel)]="form.annee_scolaire" class="w-full" placeholder="2025-2026" />
        </div>
        <div class="form-group">
          <label>Début Exercice</label>
          <input pInputText [(ngModel)]="form.date_debut" class="w-full" type="date" />
        </div>
      </div>

      <!-- Tarif -->
      <div class="tarif-bar">
        <span>Tarif annuel estimé</span>
        <span class="tarif-val">{{ tarifEstime() | number:'1.0-0' }} FCFA</span>
      </div>

      <ng-template pTemplate="footer">
        <p-button label="Annuler" severity="secondary" (onClick)="dialogVisible=false" />
        <p-button label="Créer & Activer Licence" severity="success"
                  [loading]="saving()" (onClick)="creerEcole()" />
      </ng-template>
    </p-dialog>

    <!-- Dialog renouvellement -->
    <p-dialog header="🔄 Renouveler la Licence" [(visible)]="renouvDialogVisible"
              [modal]="true" [style]="{width:'400px'}" [draggable]="false">
      <div *ngIf="licenceSelectionnee">
        <div class="renouv-info">
          <div class="ri-row"><span>École</span><strong>{{ licenceSelectionnee.tenant_nom }}</strong></div>
          <div class="ri-row"><span>Type actuel</span><span>{{ licenceSelectionnee.type }}</span></div>
          <div class="ri-row"><span>Expire le</span><span style="color:#ef4444">{{ licenceSelectionnee.date_fin }}</span></div>
        </div>
        <div class="form-group" style="margin-top:16px">
          <label>Durée du renouvellement</label>
          <p-select [options]="durees" [(ngModel)]="moisRenouvellement"
                    optionLabel="label" optionValue="value" styleClass="w-full" />
        </div>
        <div class="tarif-bar" style="margin-top:12px">
          <span>Montant à facturer</span>
          <span class="tarif-val">{{ montantRenouvellement() | number:'1.0-0' }} FCFA</span>
        </div>
      </div>
      <ng-template pTemplate="footer">
        <p-button label="Annuler" severity="secondary" (onClick)="renouvDialogVisible=false" />
        <p-button label="Confirmer Renouvellement" severity="success"
                  [loading]="saving()" (onClick)="renouveler()" />
      </ng-template>
    </p-dialog>
  `,
  styles: [`
    .page-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:20px; }
    .page-title  { font-size:20px; font-weight:600; color:#e8f0fe; margin:0 0 4px; }
    .page-sub    { font-size:12px; color:#64748b; }

    .kpi-grid { display:grid; grid-template-columns:repeat(6,1fr); gap:12px; margin-bottom:20px; }
    .kpi-card {
      background:#1e2d45; border:1px solid #2a3f5f;
      border-top:2px solid var(--acc,#00d4aa);
      border-radius:10px; padding:14px 16px; position:relative;
    }
    .kpi-icon  { position:absolute; top:10px; right:10px; font-size:18px; opacity:.2; }
    .kpi-label { font-size:10px; color:#64748b; text-transform:uppercase; letter-spacing:1px; margin-bottom:4px; }
    .kpi-value { font-size:22px; font-weight:700; font-family:monospace; }
    .kpi-sub   { font-size:10px; color:#64748b; }

    .alerte-expiration {
      background:rgba(245,158,11,0.08); border:1px solid rgba(245,158,11,0.3);
      border-radius:10px; padding:14px 18px; margin-bottom:16px;
    }
    .ae-title { font-size:13px; font-weight:600; color:#f59e0b; margin-bottom:10px; }
    .ae-row   { display:flex; align-items:center; gap:16px; padding:6px 0; border-bottom:1px solid rgba(245,158,11,0.1); font-size:12px; }
    .ae-ecole { flex:1; font-weight:600; color:#e8f0fe; }
    .ae-type  { color:#64748b; }
    .ae-jours { font-weight:700; font-family:monospace; }
    .ae-date  { color:#64748b; font-family:monospace; }

    .table-card { background:#1e2d45; border:1px solid #2a3f5f; border-radius:12px; overflow:hidden; }

    ::ng-deep .p-datatable .p-datatable-thead > tr > th { background:#111827 !important; color:#64748b !important; font-size:11px !important; text-transform:uppercase !important; border-color:#2a3f5f !important; }
    ::ng-deep .p-datatable .p-datatable-tbody > tr { background:#1e2d45 !important; color:#94a3b8 !important; border-bottom:1px solid rgba(42,63,95,0.4) !important; }
    ::ng-deep .p-datatable .p-datatable-tbody > tr:hover { background:#1a2235 !important; }

    .mono { font-family:monospace; font-size:12px; }
    .bold { font-weight:600; color:#e8f0fe; }
    .cle  { font-size:11px; color:#f0c040; letter-spacing:1px; }
    .empty-msg { text-align:center; padding:40px; color:#64748b; }

    .form-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
    .form-group { display:flex; flex-direction:column; gap:6px; }
    .form-group.full { grid-column:1/-1; }
    .form-group label { font-size:12px; color:#94a3b8; text-transform:uppercase; letter-spacing:0.5px; }
    .separator { grid-column:1/-1; font-size:12px; font-weight:600; color:#00d4aa; padding:8px 0 4px; border-top:1px solid #2a3f5f; margin-top:4px; }

    .tarif-bar { display:flex; justify-content:space-between; align-items:center; background:rgba(0,212,170,0.08); border:1px solid rgba(0,212,170,0.2); border-radius:8px; padding:10px 16px; margin-top:14px; }
    .tarif-val { font-size:18px; font-weight:700; color:#00d4aa; font-family:monospace; }

    .renouv-info { background:#0b0f1a; border-radius:8px; padding:12px; }
    .ri-row { display:flex; justify-content:space-between; font-size:13px; padding:5px 0; border-bottom:1px solid #1e2d45; }
    .ri-row span:first-child { color:#64748b; }
  `]
})
export class LicencesComponent implements OnInit {
  licences             = signal<any[]>([]);
  stats                = signal<any>(null);
  loading              = signal(true);
  saving               = signal(false);
  dialogVisible        = false;
  renouvDialogVisible  = false;
  licenceSelectionnee: any = null;
  moisRenouvellement   = 12;

  form: NouvelleEcole = {
    nom: '', ville: '', telephone: '', email: '',
    rccm: '', ninea: '',
    type_licence: 'ESSAI', mois_licence: 1,
    annee_scolaire: '2025-2026',
    date_debut: '2025-10-01', date_fin: '2026-09-30',
  };

  typesLicence = [
    { label: 'Essai — 30 jours gratuits', value: 'ESSAI' },
    { label: 'Basic — 75 000 FCFA/an',    value: 'BASIC' },
    { label: 'Pro — 150 000 FCFA/an',     value: 'PRO' },
    { label: 'Enterprise — 300 000 FCFA', value: 'ENTERPRISE' },
  ];

  durees = [
    { label: '1 mois',  value: 1  },
    { label: '3 mois',  value: 3  },
    { label: '6 mois',  value: 6  },
    { label: '12 mois', value: 12 },
    { label: '24 mois', value: 24 },
  ];

  TARIFS: Record<string, number> = {
    ESSAI: 0, BASIC: 75000, PRO: 150000, ENTERPRISE: 300000
  };

  constructor(
    private licencesService: LicencesService,
    public auth: AuthService,
    private msg: MessageService
  ) {}

  ngOnInit() {
    this.charger();
  }

  charger() {
    this.loading.set(true);
    this.licencesService.getLicences().subscribe({
      next: res => { this.licences.set(res.results || res); this.loading.set(false); }
    });
    this.licencesService.getStatsGlobales().subscribe({
      next: res => this.stats.set(res)
    });
  }

  typeSeverity(type: string) {
    return type === 'PRO' ? 'success' : type === 'ENTERPRISE' ? 'warn' :
           type === 'BASIC' ? 'info' : 'secondary';
  }

  statutSeverity(statut: string) {
    return statut === 'ACTIVE' ? 'success' : statut === 'EXPIREE' ? 'danger' :
           statut === 'ESSAI'  ? 'warn'    : 'secondary';
  }

  joursColor(jours: number) {
    return jours <= 7 ? '#ef4444' : jours <= 30 ? '#f59e0b' : '#10b981';
  }

  tarifEstime(): number {
    const annuel = this.TARIFS[this.form.type_licence] || 0;
    return (annuel / 12) * this.form.mois_licence;
  }

  montantRenouvellement(): number {
    if (!this.licenceSelectionnee) return 0;
    const annuel = this.TARIFS[this.licenceSelectionnee.type] || 0;
    return (annuel / 12) * this.moisRenouvellement;
  }

  ouvrirDialog() {
    this.form = {
      nom: '', ville: '', telephone: '', email: '',
      rccm: '', ninea: '', type_licence: 'ESSAI', mois_licence: 1,
      annee_scolaire: '2025-2026', date_debut: '2025-10-01', date_fin: '2026-09-30',
    };
    this.dialogVisible = true;
  }

  ouvrirRenouvellement(l: any) {
    this.licenceSelectionnee = l;
    this.moisRenouvellement  = 12;
    this.renouvDialogVisible = true;
  }

  creerEcole() {
    if (!this.form.nom) {
      this.msg.add({ severity:'warn', summary:'Requis', detail:'Le nom de l\'école est obligatoire' });
      return;
    }
    this.saving.set(true);
    this.licencesService.creerEcole(this.form).subscribe({
      next: res => {
        this.msg.add({
          severity: 'success',
          summary:  'École créée ✅',
          detail:   `Clé: ${res.cle_licence}`
        });
        this.dialogVisible = false;
        this.saving.set(false);
        this.charger();
      },
      error: () => {
        this.msg.add({ severity:'error', summary:'Erreur', detail:'Impossible de créer l\'école' });
        this.saving.set(false);
      }
    });
  }

  renouveler() {
    this.saving.set(true);
    this.licencesService.renouveler(this.licenceSelectionnee.id, this.moisRenouvellement).subscribe({
      next: () => {
        this.msg.add({ severity:'success', summary:'Renouvelée ✅', detail:'Licence prolongée' });
        this.renouvDialogVisible = false;
        this.saving.set(false);
        this.charger();
      },
      error: () => {
        this.msg.add({ severity:'error', summary:'Erreur', detail:'Renouvellement échoué' });
        this.saving.set(false);
      }
    });
  }

  copierCle(cle: string) {
    navigator.clipboard.writeText(cle);
    this.msg.add({ severity:'info', summary:'Copié !', detail:cle });
  }
}
