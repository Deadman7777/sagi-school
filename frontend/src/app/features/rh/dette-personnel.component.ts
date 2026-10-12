import { ChangeDetectionStrategy, Component, effect, inject, input, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MessageService } from 'primeng/api';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { InputNumberModule } from 'primeng/inputnumber';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { TooltipModule } from 'primeng/tooltip';
import {
  LigneSuiviDette, RhService, SituationDettePersonnel,
} from '../../core/services/rh.service';

/** Ce que l'école doit à son personnel : reliquat d'un exercice antérieur et
 *  reste de chaque bulletin, réglés ensuite en versements ou par compensation
 *  sur la scolarité des enfants. Le calcul est celui du serveur
 *  (apps/rh/dette_personnel.py) — cet écran ne fait que l'afficher. */
@Component({
  selector: 'app-dette-personnel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DecimalPipe, DatePipe, FormsModule, ButtonModule, DialogModule, InputNumberModule,
            InputTextModule, SelectModule, TableModule, TagModule, TooltipModule],
  template: `
@if (afficherTableau()) {
  <div class="table-card">
    <div class="dp-entete">
      <div>
        <div class="dp-titre">Dû au personnel</div>
        <div class="dp-aide">
          Reliquat de l'année passée (fiche de l'employé) et reste des bulletins validés
          sans être entièrement versés. Les enfants du personnel peuvent régler leur
          scolarité avec cette somme : mode « Compensation » au guichet.
        </div>
      </div>
      <div class="dp-total">
        <span>Reste dû au personnel</span>
        <strong>{{ resteTotal() | number:'1.0-0' }} FCFA</strong>
      </div>
    </div>
    <p-table [value]="lignes()" [loading]="chargement()" styleClass="p-datatable-sm">
      <ng-template pTemplate="header">
        <tr>
          <th>Employé</th>
          <th class="num">Reliquat antérieur</th>
          <th class="num">Total dû</th>
          <th class="num">Versé</th>
          <th class="num">Compensé (scolarité)</th>
          <th class="num">Reste dû</th>
          <th class="num">Enfants</th>
          <th></th>
        </tr>
      </ng-template>
      <ng-template pTemplate="body" let-l>
        <tr>
          <td><strong>{{ l.nom_complet }}</strong><div class="dp-sous">{{ l.matricule }} · {{ l.poste }}</div></td>
          <td class="num">{{ l.reliquat | number:'1.0-0' }}</td>
          <td class="num">{{ l.du | number:'1.0-0' }}</td>
          <td class="num">{{ (l.verse_validation + l.versements) | number:'1.0-0' }}</td>
          <td class="num">{{ l.compense | number:'1.0-0' }}</td>
          <td class="num"><strong [class.dp-rouge]="l.reste > 0">{{ l.reste | number:'1.0-0' }}</strong></td>
          <td class="num">{{ l.nb_enfants }}</td>
          <td><p-button icon="pi pi-eye" [rounded]="true" [text]="true" severity="info"
                        (onClick)="ouvrir(l.id)" pTooltip="Situation mois par mois" tooltipPosition="top"
                        [ariaLabel]="'Situation de ' + l.nom_complet" /></td>
        </tr>
      </ng-template>
      <ng-template pTemplate="emptymessage">
        <tr><td colspan="8" class="dp-vide">
          Aucun membre du personnel à qui l'école doit quelque chose. Saisissez un reliquat
          sur la fiche de l'employé, ou reliez un élève à son parent employé.
        </td></tr>
      </ng-template>
    </p-table>
  </div>
}

<p-dialog [header]="'Situation — ' + (situation()?.employe?.nom_complet || '')" [(visible)]="dialogVisible"
          [modal]="true" [style]="{width:'820px'}" [draggable]="false">
  @if (situation(); as s) {
    <div class="dp-kpis">
      <div><span>Total dû</span><strong>{{ s.totaux.du | number:'1.0-0' }}</strong></div>
      <div><span>Versé à la paie</span><strong>{{ s.totaux.verse_validation | number:'1.0-0' }}</strong></div>
      <div><span>Versements</span><strong>{{ s.totaux.versements | number:'1.0-0' }}</strong></div>
      <div><span>Compensé (scolarité)</span><strong>{{ s.totaux.compense | number:'1.0-0' }}</strong></div>
      <div class="dp-kpi-reste"><span>Reste dû</span><strong>{{ s.totaux.reste | number:'1.0-0' }} FCFA</strong></div>
    </div>

    <div class="dp-section">Mois par mois</div>
    <table class="dp-tbl">
      <thead><tr>
        <th>Période</th><th class="num">Dû</th><th class="num">Versé à la paie</th>
        <th class="num">Réglé ensuite</th><th class="num">Reste</th><th>Statut</th>
      </tr></thead>
      <tbody>
        @for (l of s.lignes; track $index) {
          <tr>
            <td>{{ l.type === 'RELIQUAT' ? '🔁 ' : '' }}{{ l.libelle }}</td>
            <td class="num">{{ l.du | number:'1.0-0' }}</td>
            <td class="num">{{ l.verse | number:'1.0-0' }}</td>
            <td class="num">{{ l.regle_ensuite | number:'1.0-0' }}</td>
            <td class="num"><strong>{{ l.reste | number:'1.0-0' }}</strong></td>
            <td><p-tag [value]="libelleStatut(l.statut)" [severity]="severiteStatut(l.statut)" /></td>
          </tr>
        } @empty {
          <tr><td colspan="6" class="dp-vide">Aucune dette : ni reliquat ni bulletin validé.</td></tr>
        }
      </tbody>
    </table>
    <div class="dp-note">Un règlement (versement ou compensation) solde d'abord la dette la plus ancienne.</div>

    <div class="dp-deux">
      <div>
        <div class="dp-section">Enfants dans l'établissement</div>
        @for (e of s.enfants; track e.id) {
          <div class="dp-ligne">
            <span>{{ e.nom_complet }} <span class="dp-sous">{{ e.classe || e.section }}</span></span>
            <span>reste à payer {{ e.reste_a_payer | number:'1.0-0' }}</span>
          </div>
        } @empty {
          <div class="dp-sous">Aucun élève relié à cet employé (fiche élève → « Parent membre du personnel »).</div>
        }
      </div>
      <div>
        <div class="dp-section">Compensations sur la scolarité</div>
        @for (c of s.compensations; track c.paiement) {
          <div class="dp-ligne">
            <span>{{ c.date | date:'dd/MM/yyyy' }} · {{ c.no_piece }} · {{ c.eleve }}</span>
            <strong>{{ c.montant | number:'1.0-0' }}</strong>
          </div>
        } @empty {
          <div class="dp-sous">Aucune.</div>
        }
      </div>
    </div>

    <div class="dp-section">Versements</div>
    @for (v of s.versements; track v.id) {
      <div class="dp-ligne">
        <span>{{ v.date | date:'dd/MM/yyyy' }} · {{ v.no_piece }} · {{ libelleMode(v.mode_paiement) }}
          @if (v.observations) { · {{ v.observations }} }</span>
        <span>
          <strong>{{ v.montant | number:'1.0-0' }}</strong>
          <p-button icon="pi pi-times" [rounded]="true" [text]="true" severity="danger" size="small"
                    (onClick)="annulerVersement(v.id)" pTooltip="Annuler ce versement" tooltipPosition="top"
                    [ariaLabel]="'Annuler le versement ' + v.no_piece" [loading]="enCours()" />
        </span>
      </div>
    } @empty {
      <div class="dp-sous">Aucun versement.</div>
    }

    @if (s.totaux.reste > 0) {
      <div class="dp-section">Verser à l'employé</div>
      <div class="dp-form">
        <div class="form-group">
          <label for="dp-montant">Montant</label>
          <p-inputNumber inputId="dp-montant" [(ngModel)]="form.montant" [min]="0" [max]="s.totaux.reste"
                         mode="decimal" [fluid]="true" />
        </div>
        <div class="form-group">
          <label for="dp-mode">Mode</label>
          <p-select inputId="dp-mode" appendTo="body" [options]="modes" optionLabel="label" optionValue="value"
                    [(ngModel)]="form.mode_paiement" [fluid]="true" />
        </div>
        <div class="form-group">
          <label for="dp-date">Date</label>
          <input pInputText id="dp-date" type="date" [(ngModel)]="form.date_versement" />
        </div>
        <div class="form-group">
          <label for="dp-obs">Observations</label>
          <input pInputText id="dp-obs" [(ngModel)]="form.observations" />
        </div>
      </div>
      <p-button label="Enregistrer le versement" severity="success" icon="pi pi-check"
                [loading]="enCours()" [disabled]="!(form.montant > 0)" (onClick)="verser()" />
    }
  }
</p-dialog>
`,
  styles: [`
    .dp-entete { display:flex; justify-content:space-between; gap:16px; padding:12px 14px; flex-wrap:wrap; }
    .dp-titre { font-size:15px; font-weight:600; color:var(--text); }
    .dp-aide, .dp-note { font-size:12px; color:var(--text-3); max-width:640px; line-height:1.45; }
    .dp-note { margin:4px 0 10px; }
    .dp-total { display:flex; flex-direction:column; align-items:flex-end; font-size:12px; color:var(--text-2); }
    .dp-total strong { font-size:18px; color:#ef4444; }
    .dp-sous { font-size:11px; color:var(--text-3); }
    .dp-rouge { color:#ef4444; }
    .dp-vide { text-align:center; color:var(--text-3); padding:16px; }
    .num { text-align:right; }
    th.num { text-align:right; }
    .dp-kpis { display:grid; grid-template-columns:repeat(5, 1fr); gap:8px; margin-bottom:12px; }
    .dp-kpis div { background:var(--surface-4); border-radius:8px; padding:8px 10px; display:flex; flex-direction:column; }
    .dp-kpis span { font-size:11px; color:var(--text-3); }
    .dp-kpis strong { font-size:14px; color:var(--text); }
    .dp-kpi-reste strong { color:#ef4444; }
    .dp-section { font-size:12px; font-weight:600; color:var(--text-2); text-transform:uppercase;
                  letter-spacing:.04em; margin:14px 0 6px; }
    .dp-tbl { width:100%; border-collapse:collapse; font-size:13px; }
    .dp-tbl th, .dp-tbl td { padding:6px 8px; border-bottom:1px solid var(--border); }
    .dp-tbl th { text-align:left; font-weight:600; color:var(--text-2); font-size:12px; }
    .dp-deux { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
    .dp-ligne { display:flex; justify-content:space-between; align-items:center; gap:8px; font-size:13px;
                padding:4px 0; border-bottom:1px dashed var(--border); }
    .dp-form { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:10px; }
    .form-group { display:flex; flex-direction:column; gap:4px; }
    .form-group label { font-size:12px; color:var(--text-2); }
  `],
})
export class DettePersonnelComponent {
  /** Le tableau de suivi n'est affiché (et chargé) que sur son onglet ; la
   *  fiche de situation, elle, s'ouvre aussi depuis la liste des employés. */
  afficherTableau = input(false);

  private rh = inject(RhService);
  private msg = inject(MessageService);

  lignes = signal<LigneSuiviDette[]>([]);
  resteTotal = signal(0);
  chargement = signal(false);
  situation = signal<SituationDettePersonnel | null>(null);
  enCours = signal(false);
  dialogVisible = false;

  readonly modes = [
    { label: 'Caisse (espèces)', value: 'CAISSE' },
    { label: 'Banque (virement)', value: 'BANQUE' },
    { label: 'Wave', value: 'WAVE' },
    { label: 'Orange Money', value: 'ORANGE_MONEY' },
    { label: 'Free Money', value: 'FREE_MONEY' },
    { label: 'Wizall', value: 'WIZALL' },
  ];
  form = this.formVide();

  constructor() {
    effect(() => { if (this.afficherTableau()) this.charger(); });
  }

  charger() {
    this.chargement.set(true);
    this.rh.suiviDettes().subscribe({
      next: r => { this.lignes.set(r.results); this.resteTotal.set(r.reste_total); this.chargement.set(false); },
      error: err => { this.erreur(err); this.chargement.set(false); },
    });
  }

  ouvrir(employeId: string) {
    this.form = this.formVide();
    this.situation.set(null);
    this.dialogVisible = true;
    this.rh.situationDette(employeId).subscribe({
      next: s => this.situation.set(s),
      error: err => this.erreur(err),
    });
  }

  verser() {
    const s = this.situation();
    if (!s) return;
    this.enCours.set(true);
    this.rh.verserPersonnel(s.employe.id, this.form).subscribe({
      next: maj => {
        this.situation.set(maj);
        this.form = this.formVide();
        this.enCours.set(false);
        this.msg.add({ severity: 'success', summary: 'Versement enregistré',
                       detail: `Reste dû : ${maj.totaux.reste.toLocaleString('fr-FR')} FCFA` });
        if (this.afficherTableau()) this.charger();
      },
      error: err => { this.erreur(err); this.enCours.set(false); },
    });
  }

  annulerVersement(versementId: string) {
    const s = this.situation();
    if (!s) return;
    this.enCours.set(true);
    this.rh.annulerVersementPersonnel(s.employe.id, versementId).subscribe({
      next: maj => {
        this.situation.set(maj);
        this.enCours.set(false);
        this.msg.add({ severity: 'info', summary: 'Versement annulé', detail: 'Écritures extournées.' });
        if (this.afficherTableau()) this.charger();
      },
      error: err => { this.erreur(err); this.enCours.set(false); },
    });
  }

  libelleStatut(s: string): string {
    return ({ SOLDE: 'Soldé', PARTIEL: 'Partiel', IMPAYE: 'Impayé' } as Record<string, string>)[s] || s;
  }

  severiteStatut(s: string): 'success' | 'warn' | 'danger' {
    return s === 'SOLDE' ? 'success' : s === 'PARTIEL' ? 'warn' : 'danger';
  }

  libelleMode(m: string): string {
    return this.modes.find(x => x.value === m)?.label || m;
  }

  private formVide() {
    return { montant: 0, mode_paiement: 'CAISSE',
             date_versement: new Date().toISOString().slice(0, 10), observations: '' };
  }

  private erreur(err: unknown) {
    const e = (err as { error?: unknown })?.error;
    let detail = 'Opération impossible.';
    if (e && typeof e === 'object') {
      const valeurs = Object.values(e as Record<string, unknown>).flat();
      if (typeof valeurs[0] === 'string') detail = valeurs[0];
    }
    this.msg.add({ severity: 'error', summary: 'Erreur', detail, life: 8000 });
  }
}
