import {
  ChangeDetectionStrategy, Component, OnInit, computed, inject, signal
} from '@angular/core';
import { DecimalPipe, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { ButtonModule }      from 'primeng/button';
import { DialogModule }      from 'primeng/dialog';
import { InputNumberModule } from 'primeng/inputnumber';
import { InputTextModule }   from 'primeng/inputtext';
import { Textarea }          from 'primeng/textarea';
import { SelectModule }      from 'primeng/select';
import { TableModule }       from 'primeng/table';
import { TagModule }         from 'primeng/tag';
import { ToastModule }       from 'primeng/toast';
import { TooltipModule }     from 'primeng/tooltip';
import { ProgressBarModule } from 'primeng/progressbar';
import { DatePickerModule }  from 'primeng/datepicker';
import { TranslateModule }   from '@ngx-translate/core';
import { GmrfService } from '../../core/services/gmrf.service';

@Component({
  selector: 'app-gmrf',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [
    DecimalPipe, DatePipe, FormsModule, TableModule, ButtonModule, DialogModule,
    InputTextModule, InputNumberModule, SelectModule, TagModule, ToastModule,
    TooltipModule, ProgressBarModule, DatePickerModule, Textarea, TranslateModule,
  ],
  providers: [MessageService],
  template: `
<p-toast />
<div class="gmrf">
  <header class="head">
    <div>
      <h1>🏦 Mobilisation des Ressources Financières</h1>
      <p class="sub">Dons, subventions, partenariats, NATT/Tontine — synchronisés avec la comptabilité</p>
    </div>
  </header>

  <nav class="tabs">
    @for (t of tabs; track t.id) {
      <button class="tab" [class.active]="tab() === t.id" (click)="tab.set(t.id)">
        <span>{{ t.icon }}</span> {{ t.label }}
      </button>
    }
  </nav>

  <!-- ══ TABLEAU DE BORD ══ -->
  @if (tab() === 'dashboard') {
    @if (dashboard(); as db) {
      <div class="kpis">
        <div class="kpi">
          <div class="kpi-label">Total mobilisé</div>
          <div class="kpi-value teal">{{ db.ressources.total_mobilise | number:'1.0-0' }} <small>F</small></div>
        </div>
        <div class="kpi">
          <div class="kpi-label">Dons reçus</div>
          <div class="kpi-value">{{ db.ressources.total_dons | number:'1.0-0' }} <small>F</small></div>
        </div>
        <div class="kpi">
          <div class="kpi-label">Subventions</div>
          <div class="kpi-value">{{ db.ressources.total_subventions | number:'1.0-0' }} <small>F</small></div>
        </div>
        <div class="kpi">
          <div class="kpi-label">NATT en cours</div>
          <div class="kpi-value blue">{{ db.natt.nombre_en_cours }}</div>
        </div>
      </div>

      <h3 class="sec">⏰ Échéances à venir (30 jours)</h3>
      <p-table [value]="db.echeances_a_venir" styleClass="p-datatable-sm">
        <ng-template pTemplate="header">
          <tr><th>NATT</th><th>Échéance</th><th>Date</th><th class="r">Montant</th><th>Statut</th></tr>
        </ng-template>
        <ng-template pTemplate="body" let-e>
          <tr>
            <td>{{ e.nom }} <small class="muted">({{ e.cycle }})</small></td>
            <td>#{{ e.numero }}</td>
            <td>{{ e.date_echeance | date:'dd/MM/yyyy' }}</td>
            <td class="r">{{ e.montant | number:'1.0-0' }} F</td>
            <td>
              @if (e.en_retard) { <p-tag severity="danger" value="En retard" /> }
              @else { <p-tag severity="warn" value="À payer" /> }
            </td>
          </tr>
        </ng-template>
        <ng-template pTemplate="emptymessage">
          <tr><td colspan="5" class="muted center">Aucune échéance imminente</td></tr>
        </ng-template>
      </p-table>
    }
  }

  <!-- ══ FINANCEMENTS ══ -->
  @if (tab() === 'financements') {
    <div class="toolbar">
      <button class="btn primary" (click)="ouvrirFinancement()">+ Nouveau financement</button>
    </div>
    <p-table [value]="financements()" styleClass="p-datatable-sm" [paginator]="financements().length > 15" [rows]="15">
      <ng-template pTemplate="header">
        <tr><th>Réf.</th><th>Type</th><th>Libellé</th><th>Source</th>
            <th class="r">Montant</th><th>Statut</th><th></th></tr>
      </ng-template>
      <ng-template pTemplate="body" let-f>
        <tr>
          <td>{{ f.reference }}</td>
          <td>{{ f.type_libelle }}</td>
          <td>{{ f.libelle }}</td>
          <td>{{ f.source || '—' }}</td>
          <td class="r">{{ f.montant | number:'1.0-0' }} {{ f.devise }}</td>
          <td>
            @switch (f.statut) {
              @case ('RECU')    { <p-tag severity="success" value="Reçu" /> }
              @case ('ATTENDU') { <p-tag severity="warn" value="Attendu" /> }
              @default          { <p-tag severity="secondary" value="Annulé" /> }
            }
          </td>
          <td class="r">
            @if (f.statut === 'ATTENDU') {
              <button class="btn xs" (click)="encaisser(f)">Encaisser</button>
            }
            @if (f.statut === 'RECU') {
              <button class="btn xs ghost" (click)="annulerFinancement(f)">Annuler</button>
            }
          </td>
        </tr>
      </ng-template>
      <ng-template pTemplate="emptymessage">
        <tr><td colspan="7" class="muted center">Aucun financement enregistré</td></tr>
      </ng-template>
    </p-table>
  }

  <!-- ══ NATT / TONTINE ══ -->
  @if (tab() === 'natt') {
    @if (!cycleActif()) {
      <div class="toolbar">
        <button class="btn primary" (click)="ouvrirCycle()">+ Souscrire à un NATT / Tontine</button>
      </div>
      <div class="cards">
        @for (c of cycles(); track c.id) {
          <button class="card" (click)="ouvrirDetail(c.id)">
            <div class="card-top">
              <strong>{{ c.nom }}</strong>
              <p-tag [severity]="c.statut === 'EN_COURS' ? 'info' : 'secondary'" [value]="c.statut" />
            </div>
            <div class="card-org">{{ c.organisateur || 'Organisateur non renseigné' }}</div>
            <div class="card-line">
              <span>{{ c.montant_cotisation | number:'1.0-0' }} F × {{ c.nb_participants }} part.</span>
              <span>{{ c.duree }} éch. — {{ periodeLabel(c.periodicite) }}</span>
            </div>
            <p-progressBar [value]="c.pourcentage_avancement" [showValue]="true" />
            <div class="card-line muted">
              <span>Versé : {{ c.total_verse | number:'1.0-0' }} F</span>
              @if (c.cagnotte_recue) { <span class="teal">✔ Cagnotte reçue</span> }
              @else { <span>Reste : {{ c.reste_a_verser | number:'1.0-0' }} F</span> }
            </div>
          </button>
        }
        @if (!cycles().length) {
          <div class="empty">Aucune participation à un NATT / Tontine.</div>
        }
      </div>
    } @else {
      <!-- Détail cycle : tableau de suivi -->
      @if (cycleActif(); as c) {
        <button class="btn ghost sm" (click)="cycleActif.set(null)">← Retour</button>
        <div class="detail-head">
          <div>
            <h2>{{ c.nom }} <small class="muted">{{ c.reference }}</small></h2>
            <div class="muted">{{ c.organisateur }} · {{ modeLabel(c.mode_attribution) }} · cagnotte {{ c.montant_cagnotte | number:'1.0-0' }} F</div>
          </div>
          @if (!c.cagnotte_recue && c.statut === 'EN_COURS') {
            <button class="btn primary" (click)="ouvrirReception(c)">💰 Recevoir la cagnotte</button>
          }
        </div>

        <div class="suivi-grid">
          <div class="suivi-box"><span>Cotisations payées</span><b>{{ c.nb_cotisations_payees }} / {{ c.duree }}</b></div>
          <div class="suivi-box"><span>Total versé</span><b>{{ c.total_verse | number:'1.0-0' }} F</b></div>
          <div class="suivi-box"><span>Reste à verser</span><b>{{ c.reste_a_verser | number:'1.0-0' }} F</b></div>
          <div class="suivi-box"><span>Montant reçu</span><b class="teal">{{ c.montant_recu | number:'1.0-0' }} F</b></div>
        </div>

        <p-table [value]="c.cotisations" styleClass="p-datatable-sm">
          <ng-template pTemplate="header">
            <tr><th>Éch.</th><th>Date</th><th class="r">Montant</th><th>Statut</th><th></th></tr>
          </ng-template>
          <ng-template pTemplate="body" let-co>
            <tr [class.recept-row]="c.numero_echeance_reception === co.numero">
              <td>#{{ co.numero }}
                @if (c.numero_echeance_reception === co.numero) { <span class="tag-recep">cagnotte</span> }
              </td>
              <td>{{ co.date_echeance | date:'dd/MM/yyyy' }}</td>
              <td class="r">{{ co.montant | number:'1.0-0' }} F</td>
              <td>
                @switch (co.statut) {
                  @case ('PAYE')      { <p-tag severity="success" value="Payée" /> }
                  @case ('EN_RETARD') { <p-tag severity="danger" value="En retard" /> }
                  @default            { <p-tag severity="warn" value="À payer" /> }
                }
              </td>
              <td class="r">
                @if (co.statut !== 'PAYE') {
                  <button class="btn xs" (click)="payerCotisation(co)">Payer</button>
                } @else {
                  <button class="btn xs ghost" (click)="annulerCotisation(co)">Annuler</button>
                }
              </td>
            </tr>
          </ng-template>
        </p-table>
      }
    }
  }

  <!-- ══ PARAMÈTRES (types) ══ -->
  @if (tab() === 'params') {
    <div class="toolbar">
      <button class="btn primary" (click)="ouvrirType()">+ Type de financement</button>
      <p class="hint">Les numéros de comptes sont paramétrables selon les recommandations de votre expert-comptable.</p>
    </div>
    <p-table [value]="types()" styleClass="p-datatable-sm">
      <ng-template pTemplate="header">
        <tr><th>Libellé</th><th>Catégorie</th><th>Nature</th><th>Compte ressource</th><th></th></tr>
      </ng-template>
      <ng-template pTemplate="body" let-t>
        <tr>
          <td>{{ t.libelle }} @if (t.est_systeme) { <span class="tag-sys">système</span> }</td>
          <td>{{ t.categorie_label }}</td>
          <td>{{ natureLabel(t.nature_comptable) }}</td>
          <td><code>{{ t.compte_ressource }}</code></td>
          <td class="r"><button class="btn xs ghost" (click)="ouvrirType(t)">Modifier</button></td>
        </tr>
      </ng-template>
    </p-table>
  }
</div>

<!-- ══════ DIALOGS ══════ -->
<!-- Financement -->
<p-dialog [(visible)]="dlgFin" [modal]="true" header="Nouveau financement" [style]="{width:'560px'}">
  <div class="form">
    <label>Type de financement</label>
    <p-select [options]="types()" optionLabel="libelle" optionValue="id"
              [(ngModel)]="fin.type_financement" placeholder="Choisir" appendTo="body" />
    <label>Libellé</label>
    <input pInputText [(ngModel)]="fin.libelle" />
    <div class="row">
      <div><label>Montant</label><p-inputNumber [(ngModel)]="fin.montant" mode="decimal" [min]="0" /></div>
      <div><label>Source / bailleur</label><input pInputText [(ngModel)]="fin.source" /></div>
    </div>
    <div class="row">
      <div><label>Compte trésorerie</label><input pInputText [(ngModel)]="fin.compte_tresorerie" /></div>
      <div><label>Statut</label>
        <p-select [options]="statutFinOpts" optionLabel="label" optionValue="value"
                  [(ngModel)]="fin.statut" appendTo="body" />
      </div>
    </div>
    <label>Observations</label>
    <textarea pTextarea [(ngModel)]="fin.observations" rows="2"></textarea>
  </div>
  <ng-template pTemplate="footer">
    <button class="btn ghost" (click)="dlgFin.set(false)">Annuler</button>
    <button class="btn primary" (click)="enregistrerFinancement()">Enregistrer</button>
  </ng-template>
</p-dialog>

<!-- Cycle NATT -->
<p-dialog [(visible)]="dlgCycle" [modal]="true" header="Souscrire à un NATT / Tontine" [style]="{width:'620px'}">
  <div class="form">
    <div class="row">
      <div><label>Nom du NATT</label><input pInputText [(ngModel)]="cyc.nom" /></div>
      <div><label>Organisateur</label><input pInputText [(ngModel)]="cyc.organisateur" /></div>
    </div>
    <div class="row">
      <div><label>Type organisateur</label>
        <p-select [options]="orgOpts" optionLabel="label" optionValue="value" [(ngModel)]="cyc.type_organisateur" appendTo="body" /></div>
      <div><label>Mode d'attribution</label>
        <p-select [options]="modeOpts" optionLabel="label" optionValue="value" [(ngModel)]="cyc.mode_attribution" appendTo="body" /></div>
    </div>
    <div class="row">
      <div><label>Nb participants</label><p-inputNumber [(ngModel)]="cyc.nb_participants" [min]="1" /></div>
      <div><label>Durée (échéances)</label><p-inputNumber [(ngModel)]="cyc.duree" [min]="1" /></div>
      <div><label>Périodicité</label>
        <p-select [options]="periodeOpts" optionLabel="label" optionValue="value" [(ngModel)]="cyc.periodicite" appendTo="body" /></div>
    </div>
    <div class="row">
      <div><label>Cotisation (F)</label><p-inputNumber [(ngModel)]="cyc.montant_cotisation" [min]="0" /></div>
      <div><label>Date de début</label><p-datepicker [(ngModel)]="cyc.date_debut" dateFormat="dd/mm/yy" appendTo="body" /></div>
    </div>
    <div class="calc" >
      Cagnotte perçue : <b>{{ (cyc.montant_cotisation || 0) * (cyc.nb_participants || 0) | number:'1.0-0' }} F</b> ·
      Total à cotiser : <b>{{ (cyc.montant_cotisation || 0) * (cyc.duree || 0) | number:'1.0-0' }} F</b>
    </div>
    <div class="row">
      <div><label>Compte trésorerie</label><input pInputText [(ngModel)]="cyc.compte_tresorerie" /></div>
      <div><label>Compte créance</label><input pInputText [(ngModel)]="cyc.compte_creance" /></div>
      <div><label>Compte dette</label><input pInputText [(ngModel)]="cyc.compte_dette" /></div>
    </div>
  </div>
  <ng-template pTemplate="footer">
    <button class="btn ghost" (click)="dlgCycle.set(false)">Annuler</button>
    <button class="btn primary" (click)="enregistrerCycle()">Créer + générer l'échéancier</button>
  </ng-template>
</p-dialog>

<!-- Réception cagnotte -->
<p-dialog [(visible)]="dlgRecep" [modal]="true" header="Réception de la cagnotte" [style]="{width:'460px'}">
  <div class="form">
    <div class="row">
      <div><label>Échéance de réception</label><p-inputNumber [(ngModel)]="recep.numero_echeance" [min]="1" /></div>
      <div><label>Date</label><p-datepicker [(ngModel)]="recep.date_reception" dateFormat="dd/mm/yy" appendTo="body" /></div>
    </div>
    <label>Montant reçu (F)</label>
    <p-inputNumber [(ngModel)]="recep.montant_recu" [min]="0" />
    <p class="hint">Écriture auto : débit trésorerie / crédit créance (cotisations versées) + crédit dette (avance du groupe).</p>
  </div>
  <ng-template pTemplate="footer">
    <button class="btn ghost" (click)="dlgRecep.set(false)">Annuler</button>
    <button class="btn primary" (click)="enregistrerReception()">Enregistrer</button>
  </ng-template>
</p-dialog>

<!-- Type de financement -->
<p-dialog [(visible)]="dlgType" [modal]="true" [header]="typeEdit.id ? 'Modifier le type' : 'Nouveau type'" [style]="{width:'480px'}">
  <div class="form">
    <label>Libellé</label>
    <input pInputText [(ngModel)]="typeEdit.libelle" />
    <div class="row">
      <div><label>Catégorie</label>
        <p-select [options]="categorieOpts" optionLabel="label" optionValue="value" [(ngModel)]="typeEdit.categorie" appendTo="body" /></div>
      <div><label>Nature comptable</label>
        <p-select [options]="natureOpts" optionLabel="label" optionValue="value" [(ngModel)]="typeEdit.nature_comptable" appendTo="body" /></div>
    </div>
    <div class="row">
      <div><label>Compte ressource</label><input pInputText [(ngModel)]="typeEdit.compte_ressource" /></div>
      <div><label>Compte trésorerie déf.</label><input pInputText [(ngModel)]="typeEdit.compte_tresorerie_defaut" /></div>
    </div>
  </div>
  <ng-template pTemplate="footer">
    <button class="btn ghost" (click)="dlgType.set(false)">Annuler</button>
    <button class="btn primary" (click)="enregistrerType()">Enregistrer</button>
  </ng-template>
</p-dialog>
  `,
  styles: [`
    .gmrf { color:#e8f0fe; }
    .head { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:16px; }
    .head h1 { font-size:20px; margin:0; }
    .sub { color:#64748b; font-size:12px; margin:4px 0 0; }
    .tabs { display:flex; gap:4px; border-bottom:1px solid #1e2d45; margin-bottom:18px; flex-wrap:wrap; }
    .tab { background:transparent; border:none; color:#94a3b8; padding:10px 16px; cursor:pointer; font-size:13px; border-bottom:2px solid transparent; }
    .tab.active { color:#00d4aa; border-bottom-color:#00d4aa; }
    .kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:14px; margin-bottom:24px; }
    .kpi { background:#111827; border:1px solid #1e2d45; border-radius:10px; padding:16px; }
    .kpi-label { color:#64748b; font-size:11px; text-transform:uppercase; letter-spacing:1px; }
    .kpi-value { font-size:24px; font-weight:700; margin-top:6px; }
    .kpi-value small { font-size:13px; color:#64748b; }
    .kpi-value.teal { color:#00d4aa; } .kpi-value.blue { color:#0099ff; }
    .sec { font-size:14px; margin:20px 0 10px; }
    .toolbar { display:flex; align-items:center; gap:14px; margin-bottom:14px; }
    .hint, .card-org { color:#64748b; font-size:12px; }
    .cards { display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:14px; }
    .card { text-align:left; background:#111827; border:1px solid #1e2d45; border-radius:10px; padding:16px; cursor:pointer; color:#e8f0fe; display:flex; flex-direction:column; gap:8px; }
    .card:hover { border-color:#00d4aa; }
    .card-top { display:flex; justify-content:space-between; align-items:center; }
    .card-line { display:flex; justify-content:space-between; font-size:12px; }
    .detail-head { display:flex; justify-content:space-between; align-items:center; margin:12px 0 18px; }
    .detail-head h2 { margin:0; font-size:18px; }
    .suivi-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin-bottom:18px; }
    .suivi-box { background:#0f1a2e; border:1px solid #1e2d45; border-radius:8px; padding:12px; display:flex; flex-direction:column; gap:4px; }
    .suivi-box span { color:#64748b; font-size:11px; } .suivi-box b { font-size:16px; }
    .teal { color:#00d4aa; } .muted { color:#64748b; } .center { text-align:center; } .r { text-align:right; }
    .recept-row { background:rgba(0,212,170,0.06); }
    .tag-recep, .tag-sys, .tag-recep { background:rgba(0,212,170,0.15); color:#00d4aa; font-size:10px; padding:1px 6px; border-radius:8px; margin-left:6px; }
    .tag-sys { background:rgba(100,116,139,0.2); color:#94a3b8; }
    .empty { color:#64748b; padding:30px; text-align:center; grid-column:1/-1; }
    .form { display:flex; flex-direction:column; gap:6px; }
    .form label { font-size:12px; color:#94a3b8; margin-top:6px; }
    .form .row { display:flex; gap:10px; }
    .form .row > div { flex:1; display:flex; flex-direction:column; gap:4px; }
    .calc { background:#0f1a2e; border:1px solid #1e2d45; border-radius:8px; padding:8px 12px; font-size:12px; margin-top:8px; }
    .btn { background:#1a2235; border:1px solid #2a3f5f; color:#e8f0fe; border-radius:6px; padding:8px 14px; cursor:pointer; font-size:13px; }
    .btn:hover { border-color:#00d4aa; }
    .btn.primary { background:#00d4aa; color:#04121a; border-color:#00d4aa; font-weight:600; }
    .btn.ghost { background:transparent; } .btn.sm { padding:5px 10px; font-size:12px; } .btn.xs { padding:4px 9px; font-size:11px; }
    :host ::ng-deep .p-datatable { --p-datatable-header-cell-background:#0f1a2e; }
    :host ::ng-deep .p-inputtext, :host ::ng-deep .p-inputnumber-input, :host ::ng-deep .p-select { width:100%; }
  `],
})
export class GmrfComponent implements OnInit {
  private gmrf = inject(GmrfService);
  private msg  = inject(MessageService);

  tabs = [
    { id: 'dashboard',    icon: '📊', label: 'Tableau de bord' },
    { id: 'financements', icon: '💠', label: 'Financements' },
    { id: 'natt',         icon: '🤝', label: 'NATT / Tontine' },
    { id: 'params',       icon: '⚙️', label: 'Paramètres' },
  ];
  tab = signal('dashboard');

  dashboard    = signal<any>(null);
  financements = signal<any[]>([]);
  cycles       = signal<any[]>([]);
  types        = signal<any[]>([]);
  cycleActif   = signal<any>(null);

  dlgFin = signal(false); dlgCycle = signal(false); dlgRecep = signal(false); dlgType = signal(false);

  fin: any = {};
  cyc: any = {};
  recep: any = {};
  typeEdit: any = {};
  private receptionCycleId = '';

  statutFinOpts = [{ label: 'Reçu', value: 'RECU' }, { label: 'Attendu', value: 'ATTENDU' }];
  orgOpts = [
    { label: 'Association', value: 'ASSOCIATION' }, { label: 'Particulier', value: 'PARTICULIER' },
    { label: 'Groupement', value: 'GROUPEMENT' }, { label: 'Entreprise', value: 'ENTREPRISE' },
    { label: 'Autre', value: 'AUTRE' },
  ];
  modeOpts = [
    { label: 'Tirage au sort', value: 'TIRAGE' }, { label: 'Ordre prédéfini', value: 'ORDRE' },
    { label: 'Consensus', value: 'CONSENSUS' }, { label: 'Autre', value: 'AUTRE' },
  ];
  periodeOpts = [
    { label: 'Hebdomadaire', value: 'HEBDOMADAIRE' }, { label: 'Mensuelle', value: 'MENSUELLE' },
    { label: 'Trimestrielle', value: 'TRIMESTRIELLE' },
  ];
  categorieOpts = [
    { label: 'Don', value: 'DON' }, { label: "Subvention d'investissement", value: 'SUBV_INVEST' },
    { label: "Subvention d'exploitation", value: 'SUBV_EXPLOIT' }, { label: 'Partenariat', value: 'PARTENARIAT' },
    { label: 'Crowdfunding', value: 'CROWDFUNDING' }, { label: 'Revenu exceptionnel', value: 'REVENU_EXCEPT' },
    { label: 'Autre', value: 'AUTRE' },
  ];
  natureOpts = [
    { label: 'Produit', value: 'PRODUIT' }, { label: 'Capitaux propres', value: 'CAPITAUX' },
    { label: 'Dette / financement', value: 'DETTE' },
  ];

  ngOnInit() {
    this.chargerDashboard();
    this.chargerFinancements();
    this.chargerCycles();
    this.chargerTypes();
  }

  chargerDashboard() { this.gmrf.getDashboard().subscribe(d => this.dashboard.set(d)); }
  chargerFinancements() { this.gmrf.getFinancements().subscribe(r => this.financements.set(r.financements || [])); }
  chargerCycles() { this.gmrf.getCycles().subscribe(r => this.cycles.set(r)); }
  chargerTypes() { this.gmrf.getTypes().subscribe(r => this.types.set(r)); }

  private ok(m: string) { this.msg.add({ severity: 'success', summary: m }); }
  private err(e: any) { this.msg.add({ severity: 'error', summary: e?.error?.error || 'Erreur' }); }

  periodeLabel(v: string) { return this.periodeOpts.find(o => o.value === v)?.label || v; }
  modeLabel(v: string) { return this.modeOpts.find(o => o.value === v)?.label || v; }
  natureLabel(v: string) { return this.natureOpts.find(o => o.value === v)?.label || v; }

  // ── Financements ──
  ouvrirFinancement() {
    const t = this.types()[0];
    this.fin = { type_financement: t?.id, statut: 'RECU', compte_tresorerie: t?.compte_tresorerie_defaut || '571', montant: 0 };
    this.dlgFin.set(true);
  }
  enregistrerFinancement() {
    this.gmrf.creerFinancement(this.fin).subscribe({
      next: () => { this.dlgFin.set(false); this.ok('Financement enregistré'); this.chargerFinancements(); this.chargerDashboard(); },
      error: e => this.err(e),
    });
  }
  encaisser(f: any) {
    this.gmrf.actionFinancement(f.id, { action: 'encaisser' }).subscribe({
      next: () => { this.ok('Encaissé'); this.chargerFinancements(); this.chargerDashboard(); }, error: e => this.err(e),
    });
  }
  annulerFinancement(f: any) {
    this.gmrf.actionFinancement(f.id, { action: 'annuler' }).subscribe({
      next: () => { this.ok('Annulé'); this.chargerFinancements(); this.chargerDashboard(); }, error: e => this.err(e),
    });
  }

  // ── NATT ──
  ouvrirCycle() {
    this.cyc = { periodicite: 'MENSUELLE', type_organisateur: 'AUTRE', mode_attribution: 'TIRAGE',
                 nb_participants: 10, duree: 10, montant_cotisation: 0, date_debut: new Date(),
                 compte_tresorerie: '571', compte_creance: '4718', compte_dette: '4798' };
    this.dlgCycle.set(true);
  }
  enregistrerCycle() {
    const p = { ...this.cyc, date_debut: this.toIso(this.cyc.date_debut) };
    this.gmrf.creerCycle(p).subscribe({
      next: () => { this.dlgCycle.set(false); this.ok('NATT créé'); this.chargerCycles(); this.chargerDashboard(); },
      error: e => this.err(e),
    });
  }
  ouvrirDetail(id: string) { this.gmrf.getCycle(id).subscribe(c => this.cycleActif.set(c)); }
  rafraichirDetail() { if (this.cycleActif()) this.ouvrirDetail(this.cycleActif().id); }

  payerCotisation(co: any) {
    this.gmrf.actionCotisation(co.id, { action: 'payer' }).subscribe({
      next: () => { this.ok('Cotisation payée'); this.rafraichirDetail(); this.chargerCycles(); this.chargerDashboard(); },
      error: e => this.err(e),
    });
  }
  annulerCotisation(co: any) {
    this.gmrf.actionCotisation(co.id, { action: 'annuler' }).subscribe({
      next: () => { this.ok('Cotisation annulée'); this.rafraichirDetail(); this.chargerCycles(); }, error: e => this.err(e),
    });
  }
  ouvrirReception(c: any) {
    this.receptionCycleId = c.id;
    this.recep = { numero_echeance: 1, date_reception: new Date(), montant_recu: c.montant_cagnotte };
    this.dlgRecep.set(true);
  }
  enregistrerReception() {
    const p = { ...this.recep, date_reception: this.toIso(this.recep.date_reception) };
    this.gmrf.recevoirCagnotte(this.receptionCycleId, p).subscribe({
      next: c => { this.dlgRecep.set(false); this.ok('Cagnotte reçue'); this.cycleActif.set(c); this.chargerCycles(); this.chargerDashboard(); },
      error: e => this.err(e),
    });
  }

  // ── Types ──
  ouvrirType(t?: any) {
    this.typeEdit = t ? { ...t } : { categorie: 'AUTRE', nature_comptable: 'PRODUIT', compte_ressource: '7588', compte_tresorerie_defaut: '571' };
    this.dlgType.set(true);
  }
  enregistrerType() {
    const obs = this.typeEdit.id
      ? this.gmrf.modifierType(this.typeEdit.id, this.typeEdit)
      : this.gmrf.creerType(this.typeEdit);
    obs.subscribe({ next: () => { this.dlgType.set(false); this.ok('Type enregistré'); this.chargerTypes(); }, error: e => this.err(e) });
  }

  private toIso(d: any): string {
    if (!d) return '';
    const dt = d instanceof Date ? d : new Date(d);
    return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, '0')}-${String(dt.getDate()).padStart(2, '0')}`;
  }
}
