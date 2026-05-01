import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { PaiementsService } from '../../core/services/paiements.service';
import { ElevesService } from '../../core/services/eleves.service';
import { Eleve } from '../../core/models/eleve.model';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { TagModule } from 'primeng/tag';
import { ToastModule } from 'primeng/toast';
import { InputNumberModule } from 'primeng/inputnumber';
import { MessageService } from 'primeng/api';
import { TranslateModule } from '@ngx-translate/core';
import { AutoCompleteModule } from 'primeng/autocomplete';

@Component({
  selector: 'app-paiements',
  standalone: true,
  imports: [CommonModule, FormsModule, TableModule, TranslateModule, ButtonModule, DialogModule,
            InputTextModule, SelectModule, TagModule, ToastModule,
            InputNumberModule, AutoCompleteModule],
  providers: [MessageService],
  template: `
    <p-toast />

    <!-- Header -->
    <div class="page-header">
      <div>
        <h2 class="page-title">{{ 'paiements.title' | translate }}</h2>
        <span class="page-sub">{{ stats()?.nb_transactions || 0 }} transactions · Total : {{ (stats()?.total || 0) | number:'1.0-0' }} FCFA</span>
      </div>
      <p-button label="{{ 'paiements.nouveau' | translate }}" severity="success" (onClick)="ouvrirDialog()" />
    </div>

    <!-- Stats modes -->
    <div class="modes-grid" *ngIf="stats()?.par_mode?.length">
      <div class="mode-card" *ngFor="let m of stats().par_mode">
        <div class="mode-name">{{ m.mode }}</div>
        <div class="mode-total">{{ m.total | number:'1.0-0' }}</div>
        <div class="mode-nb">{{ m.nb }} opérations</div>
      </div>
    </div>

    <!-- Table paiements -->
    <div class="table-card">
      <p-table [value]="paiements()" [loading]="loading()"
               styleClass="p-datatable-sm" [paginator]="true" [rows]="20">
        <ng-template pTemplate="header">
          <tr>
            <th>N° Pièce</th>
            <th>Date</th>
            <th>Élève</th>
            <th>Inscription</th>
            <th>Mensualité</th>
            <th>Uniforme</th>
            <th>Fournitures</th>
            <th>Cantine</th>
            <th>Total</th>
            <th>Mode</th>
            <th>Reçu</th>
          </tr>
        </ng-template>
        <ng-template pTemplate="body" let-p>
          <tr>
            <td class="mono">{{ p.no_piece }}</td>
            <td>{{ p.date_paiement | date:'dd/MM/yyyy' }}</td>
            <td class="bold">{{ p.eleve_nom }}</td>
            <td class="mono">{{ p.montant_inscription | number:'1.0-0' }}</td>
            <td class="mono">{{ p.montant_mensualite  | number:'1.0-0' }}</td>
            <td class="mono">{{ p.montant_uniforme    | number:'1.0-0' }}</td>
            <td class="mono">{{ p.montant_fournitures | number:'1.0-0' }}</td>
            <td class="mono">{{ p.montant_cantine     | number:'1.0-0' }}</td>
            <td class="mono success">{{ p.total | number:'1.0-0' }} FCFA</td>
            <td><p-tag [value]="p.mode_paiement" severity="info" /></td>
            <td>
              <p-button icon="pi pi-print" [rounded]="true" [text]="true"
                        severity="secondary" (onClick)="imprimerRecu(p)" />
            </td>
          </tr>
        </ng-template>
        <ng-template pTemplate="emptymessage">
          <tr><td colspan="11" class="empty-msg">Aucun paiement enregistré</td></tr>
        </ng-template>
      </p-table>
    </div>

    <!-- Dialog saisie paiement -->
    <p-dialog header="💰 Nouveau Paiement" [(visible)]="dialogVisible"
              [modal]="true" [style]="{width:'560px'}" [draggable]="false">

      <!-- Recherche élève -->
      <div class="form-group" style="margin-bottom:20px">
        <label>Élève *</label>
        <p-autoComplete
            [(ngModel)]="eleveTexte"
            [suggestions]="elevesSuggestions()"
            (completeMethod)="rechercherEleve($event)"
            field="nom_complet"
            dataKey="id"
            placeholder="Tapez le nom de l'élève..."
            styleClass="w-full"
            (onSelect)="onEleveSelect($event)">
            <ng-template let-e pTemplate="item">
                <div style="padding:6px 0">
                    <div style="font-weight:600">{{ e.nom_complet }}</div>
                    <div style="font-size:11px;color:#64748b">{{ e.section_nom }} — Reste: {{ e.reste_a_payer | number:'1.0-0' }} FCFA</div>
                </div>
            </ng-template>
        </p-autoComplete>
      </div>

      <!-- Infos élève sélectionné -->
      <div class="eleve-info" *ngIf="eleveSelectionne?.id">
        <div class="ei-row"><span>Section</span><span>{{ eleveSelectionne.section_nom }}</span></div>
        <div class="ei-row"><span>Total attendu</span><span>{{ eleveSelectionne.total_attendu | number:'1.0-0' }} FCFA</span></div>
        <div class="ei-row"><span>Déjà payé</span><span style="color:#10b981">{{ eleveSelectionne.total_paye | number:'1.0-0' }} FCFA</span></div>
        <div class="ei-row"><span>Reste à payer</span><span style="color:#ef4444;font-weight:700">{{ eleveSelectionne.reste_a_payer | number:'1.0-0' }} FCFA</span></div>
      </div>

      <!-- Montants -->
      <div class="montants-grid">
        <!-- Type de paiement -->
        <div class="form-group full" style="margin-bottom:16px">
          <label>Type de paiement *</label>
          <div style="display:flex;gap:8px;margin-top:6px">
            <button [class]="typePaiement === 'INSCRIPTION' ? 'type-btn active-inscr' : 'type-btn'"
                    (click)="setTypePaiement('INSCRIPTION')">
              🎓 Inscription / Début d'année
            </button>
            <button [class]="typePaiement === 'MENSUALITE' ? 'type-btn active-mens' : 'type-btn'"
                    (click)="setTypePaiement('MENSUALITE')">
              📅 Mensualité
            </button>
          </div>
        </div>

        <!-- Champs Inscription -->
        <div class="montants-grid" *ngIf="typePaiement === 'INSCRIPTION'">
          <div class="form-group">
            <label>Inscription</label>
            <p-inputNumber [(ngModel)]="form.montant_inscription" [min]="0" mode="decimal" styleClass="w-full" />
          </div>
          <div class="form-group">
            <label>Uniforme</label>
            <p-inputNumber [(ngModel)]="form.montant_uniforme" [min]="0" mode="decimal" styleClass="w-full" />
          </div>
          <div class="form-group">
            <label>Fournitures</label>
            <p-inputNumber [(ngModel)]="form.montant_fournitures" [min]="0" mode="decimal" styleClass="w-full" />
          </div>
          <div class="form-group">
            <label>Divers</label>
            <p-inputNumber [(ngModel)]="form.montant_divers" [min]="0" mode="decimal" styleClass="w-full" />
          </div>
        </div>

        <!-- Champs Mensualité -->
        <div class="montants-grid" *ngIf="typePaiement === 'MENSUALITE'">
          <div class="form-group">
            <label>Mensualité</label>
            <p-inputNumber [(ngModel)]="form.montant_mensualite" [min]="0" mode="decimal" styleClass="w-full" />
          </div>
          <div class="form-group">
            <label>Cantine</label>
            <p-inputNumber [(ngModel)]="form.montant_cantine" [min]="0" mode="decimal" styleClass="w-full" />
          </div>
          <div class="form-group">
            <label>Divers</label>
            <p-inputNumber [(ngModel)]="form.montant_divers" [min]="0" mode="decimal" styleClass="w-full" />
          </div>
        </div>
      </div>

      <!-- Total calculé -->
      <div class="total-bar">
        <span>Total à encaisser</span>
        <span class="total-val">{{ totalForm() | number:'1.0-0' }} FCFA</span>
      </div>

      <!-- Mode paiement -->
      <div class="form-group" style="margin-top:14px">
        <label>Mode de Paiement *</label>
        <p-select [options]="modesPaiement" [(ngModel)]="form.mode_paiement"
                  optionLabel="label" optionValue="value"
                  placeholder="Choisir..." styleClass="w-full" />
      </div>

      <div class="form-group" style="margin-top:10px">
        <label>Observations</label>
        <input pInputText [(ngModel)]="form.observations" class="w-full" placeholder="Optionnel..." />
      </div>

      <ng-template pTemplate="footer">
        <p-button label="Annuler" severity="secondary" (onClick)="dialogVisible=false" />
        <p-button label="Enregistrer & Imprimer Reçu" severity="success"
                  [loading]="saving()" (onClick)="sauvegarder(true)" />
        <p-button label="Enregistrer" severity="success" [outlined]="true"
                  [loading]="saving()" (onClick)="sauvegarder(false)" />
      </ng-template>
    </p-dialog>

    <!-- Dialog reçu impression -->
    <p-dialog header="🧾 Reçu de Paiement" [(visible)]="recuVisible"
              [modal]="true" [style]="{width:'420px'}" [draggable]="false">
      <div class="recu" *ngIf="recuData()">
        <div class="recu-header">
          <div class="recu-titre">REÇU DE PAIEMENT</div>
          <div class="recu-no">{{ recuData().no_piece }}</div>
        </div>
        <div class="recu-row"><span>Élève</span><strong>{{ recuData().eleve }}</strong></div>
        <div class="recu-row"><span>Section</span><span>{{ recuData().section }}</span></div>
        <div class="recu-row"><span>Date</span><span>{{ recuData().date | date:'dd/MM/yyyy' }}</span></div>
        <hr style="border-color:#2a3f5f;margin:10px 0">
        <div class="recu-row" *ngIf="recuData().inscription">  <span>Inscription</span>  <span>{{ recuData().inscription  | number:'1.0-0' }} FCFA</span></div>
        <div class="recu-row" *ngIf="recuData().mensualite">   <span>Mensualité</span>   <span>{{ recuData().mensualite   | number:'1.0-0' }} FCFA</span></div>
        <div class="recu-row" *ngIf="recuData().uniforme">     <span>Uniforme</span>     <span>{{ recuData().uniforme     | number:'1.0-0' }} FCFA</span></div>
        <div class="recu-row" *ngIf="recuData().fournitures">  <span>Fournitures</span>  <span>{{ recuData().fournitures  | number:'1.0-0' }} FCFA</span></div>
        <div class="recu-row" *ngIf="recuData().cantine">      <span>Cantine</span>      <span>{{ recuData().cantine      | number:'1.0-0' }} FCFA</span></div>
        <hr style="border-color:#2a3f5f;margin:10px 0">
        <div class="recu-total"><span>TOTAL</span><span>{{ recuData().total | number:'1.0-0' }} FCFA</span></div>
        <div class="recu-row" style="margin-top:8px"><span>Mode</span><span>{{ recuData().mode_paiement }}</span></div>
        <div class="recu-row"><span>Saisi par</span><span>{{ recuData().saisi_par }}</span></div>
      </div>
      <ng-template pTemplate="footer">
        <p-button label="Imprimer" icon="pi pi-print" severity="success" (onClick)="imprimer()" />
        <p-button label="Fermer" severity="secondary" (onClick)="recuVisible=false" />
      </ng-template>
    </p-dialog>
  `,
  styles: [`
    .page-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:20px; }
    .page-title  { font-size:20px; font-weight:600; color:#e8f0fe; margin:0 0 4px; }
    .page-sub    { font-size:12px; color:#64748b; }

    .modes-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); gap:12px; margin-bottom:20px; }
    .mode-card  { background:#1e2d45; border:1px solid #2a3f5f; border-radius:10px; padding:14px; text-align:center; }
    .mode-name  { font-size:11px; color:#64748b; text-transform:uppercase; letter-spacing:1px; margin-bottom:4px; }
    .mode-total { font-size:20px; font-weight:700; font-family:monospace; color:#00d4aa; }
    .mode-nb    { font-size:11px; color:#64748b; margin-top:2px; }

    .table-card { background:#1e2d45; border:1px solid #2a3f5f; border-radius:12px; overflow:hidden; }

    ::ng-deep .p-datatable .p-datatable-thead > tr > th { background:#111827 !important; color:#64748b !important; font-size:11px !important; text-transform:uppercase !important; border-color:#2a3f5f !important; }
    ::ng-deep .p-datatable .p-datatable-tbody > tr { background:#1e2d45 !important; color:#94a3b8 !important; border-bottom:1px solid rgba(42,63,95,0.4) !important; }
    ::ng-deep .p-datatable .p-datatable-tbody > tr:hover { background:#1a2235 !important; }

    .mono    { font-family:monospace; font-size:12px; }
    .bold    { font-weight:600; color:#e8f0fe; }
    .success { color:#10b981; }
    .empty-msg { text-align:center; padding:40px; color:#64748b; }

    .eleve-info { background:#0f2010; border:1px solid #2a5c2a; border-radius:8px; padding:12px; margin-bottom:14px; }
    .ei-row { display:flex; justify-content:space-between; font-size:12px; padding:4px 0; border-bottom:1px solid rgba(42,95,42,0.3); }
    .ei-row:last-child { border-bottom:none; }
    .ei-row span:first-child { color:#64748b; }
    .ei-row span:last-child  { font-weight:500; color:#e8f0fe; font-family:monospace; }

    .montants-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
    .form-group { display:flex; flex-direction:column; gap:6px; }
    .form-group label { font-size:12px; color:#94a3b8; text-transform:uppercase; letter-spacing:0.5px; }

    .total-bar { display:flex; justify-content:space-between; align-items:center; background:rgba(0,212,170,0.1); border:1px solid rgba(0,212,170,0.2); border-radius:8px; padding:10px 16px; margin-top:14px; }
    .total-val { font-size:20px; font-weight:700; color:#00d4aa; font-family:monospace; }

    .recu { color:#e8f0fe; }
    .recu-header { text-align:center; margin-bottom:16px; }
    .recu-titre { font-size:16px; font-weight:700; color:#00d4aa; }
    .recu-no    { font-size:12px; color:#64748b; font-family:monospace; margin-top:4px; }
    .recu-row   { display:flex; justify-content:space-between; font-size:13px; padding:5px 0; border-bottom:1px solid rgba(42,63,95,0.3); }
    .recu-row span:first-child { color:#64748b; }
    .recu-total { display:flex; justify-content:space-between; font-size:16px; font-weight:700; padding:8px 0; color:#00d4aa; }
    .type-btn { flex:1; padding:10px; border:1px solid #2a3f5f; border-radius:8px; background:#111827; color:#64748b; cursor:pointer; font-size:13px; transition:all 0.2s; }
    .type-btn:hover { border-color:#00d4aa; color:#e8f0fe; }
    .active-inscr { background:rgba(245,158,11,0.15); border-color:#f59e0b; color:#f59e0b; font-weight:600; }
    .active-mens  { background:rgba(0,212,170,0.15);  border-color:#00d4aa; color:#00d4aa; font-weight:600; }
  `]
})
export class PaiementsComponent implements OnInit {
  paiements        = signal<any[]>([]);
  stats            = signal<any>(null);
  elevesSuggestions = signal<Eleve[]>([]);
  loading          = signal(true);
  saving           = signal(false);
  dialogVisible    = false;
  recuVisible      = false;
  recuData         = signal<any>(null);
  eleveSelectionne: any = null;
  eleveTexte: string = '';
  exerciceId       = '';
  typePaiement: 'INSCRIPTION' | 'MENSUALITE' = 'MENSUALITE';

  form = {
    montant_inscription: 0,
    montant_mensualite:  0,
    montant_uniforme:    0,
    montant_fournitures: 0,
    montant_cantine:     0,
    montant_divers:      0,
    mode_paiement:       '',
    observations:        '',
  };

  modesPaiement = [
    { label: 'Espèce',       value: 'ESPECE' },
    { label: 'Wave',         value: 'WAVE' },
    { label: 'Orange Money', value: 'ORANGE_MONEY' },
    { label: 'Free Money',   value: 'FREE_MONEY' },
    { label: 'Virement',     value: 'VIREMENT' },
    { label: 'Chèque',       value: 'CHEQUE' },
  ];

  constructor(
    private paiementsService: PaiementsService,
    private elevesService: ElevesService,
    private msg: MessageService
  ) {}

  ngOnInit() {
    this.chargerPaiements();
    this.chargerStats();
    this.chargerExercice();
  }

  chargerPaiements() {
    this.loading.set(true);
    this.paiementsService.getPaiements().subscribe({
      next: res => { 
          const data = Array.isArray(res) ? res : (res.results || []);
          this.paiements.set(data); 
          this.loading.set(false); 
      },
      error: () => this.loading.set(false)
    });
  }

  chargerStats() {
    this.paiementsService.getStats().subscribe({
      next: res => this.stats.set(res)
    });
  }

  chargerExercice() {
    this.paiementsService.getExerciceActif().subscribe({
      next: res => {
        const exercices = res.results || res;
        if (exercices.length > 0) this.exerciceId = exercices[0].id;
      }
    });
  }

  rechercherEleve(event: any) {
    this.elevesService.getEleves({ search: event.query }).subscribe({
      next: res => this.elevesSuggestions.set(res.results || [])
    });
  }

  onEleveSelect(event: any) {
    this.eleveSelectionne = event?.value !== undefined ? event.value : event;
    this.eleveTexte = this.eleveSelectionne?.nom_complet || '';
    // Pré-remplir avec les frais de la section
    if (event.section_nom) {
      this.elevesService.getSections().subscribe({
        next: res => {
          const sections = res.results || [];
          const section  = sections.find((s: any) => s.id === event.section);
          if (section) {
            this.form.montant_inscription = Number(section.frais_inscription) - Number(event.total_paye > 0 ? 0 : section.frais_inscription);
            this.form.montant_mensualite  = Number(section.frais_mensualite);
          }
        }
      });
    }
  }

  get totalForm(): () => number {
    return () => Object.entries(this.form)
      .filter(([k]) => k.startsWith('montant_'))
      .reduce((s, [, v]) => s + (Number(v) || 0), 0);
  }

  ouvrirDialog() {
    this.eleveSelectionne = null;
    this.eleveTexte = '';
    this.form = { montant_inscription:0, montant_mensualite:0, montant_uniforme:0,
                  montant_fournitures:0, montant_cantine:0, montant_divers:0,
                  mode_paiement:'', observations:'' };
    this.dialogVisible = true;
    this.typePaiement = 'MENSUALITE';
  }

  sauvegarder(avecRecu: boolean) {
    if (!this.eleveSelectionne?.id) {
      this.msg.add({ severity:'warn', summary:'Champ requis', detail:'Sélectionnez un élève' });
      return;
    }
    if (!this.form.mode_paiement) {
      this.msg.add({ severity:'warn', summary:'Champ requis', detail:'Choisissez un mode de paiement' });
      return;
    }
    if (this.totalForm() <= 0) {
      this.msg.add({ severity:'warn', summary:'Montant invalide', detail:'Le total doit être supérieur à 0' });
      return;
    }
    this.saving.set(true);
    this.paiementsService.creerPaiement({
      ...this.form,
      eleve:    this.eleveSelectionne.id,
      exercice: this.exerciceId,
    }).subscribe({
      next: (res: any) => {
        this.msg.add({ severity:'success', summary:'Paiement enregistré ✅', detail:`Reçu: ${res.no_piece}` });
        this.dialogVisible = false;
        this.saving.set(false);
        this.chargerPaiements();
        this.chargerStats();
        if (avecRecu) this.imprimerRecu(res);
      },
      error: (err) => {
        this.msg.add({ severity:'error', summary:'Erreur', detail:'Impossible d\'enregistrer' });
        console.error(err);
        this.saving.set(false);
      }
    });
  }

  imprimerRecu(paiement: any) {
    this.paiementsService.getRecu(paiement.id).subscribe({
      next: res => { this.recuData.set(res); this.recuVisible = true; }
    });
  }

  setTypePaiement(type: 'INSCRIPTION' | 'MENSUALITE') {
    this.typePaiement = type;
    // Remettre à zéro les champs de l'autre type
    if (type === 'INSCRIPTION') {
        this.form.montant_mensualite = 0;
        this.form.montant_cantine = 0;
        // Pré-remplir depuis la section si élève sélectionné
        if (this.eleveSelectionne?.section) {
            this.elevesService.getSections().subscribe({
                next: res => {
                    const sections = res.results || [];
                    const section = sections.find((s: any) => s.id === this.eleveSelectionne.section);
                    if (section) {
                        this.form.montant_inscription = Number(section.frais_inscription);
                        this.form.montant_uniforme    = Number(section.frais_uniforme);
                        this.form.montant_fournitures = Number(section.frais_fournitures);
                    }
                }
            });
        }
    } else {
        this.form.montant_inscription = 0;
        this.form.montant_uniforme = 0;
        this.form.montant_fournitures = 0;
        // Pré-remplir mensualité
        if (this.eleveSelectionne?.section) {
            this.elevesService.getSections().subscribe({
                next: res => {
                    const sections = res.results || [];
                    const section = sections.find((s: any) => s.id === this.eleveSelectionne.section);
                    if (section) {
                        this.form.montant_mensualite = Number(section.frais_mensualite);
                    }
                }
            });
        }
    }
}

  imprimer() { window.print(); }
}
