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
  LigneDettePersonnel, LigneSuiviDette, RhService, SituationDettePersonnel,
} from '../../core/services/rh.service';
import { BoutonImprimerComponent } from '../../shared/bouton-imprimer.component';

/** Ce que l'école doit à son personnel : reliquat d'un exercice antérieur et
 *  reste de chaque bulletin, réglés ensuite en versements ou par compensation
 *  sur la scolarité des enfants. Le calcul est celui du serveur
 *  (apps/rh/dette_personnel.py) — cet écran ne fait que l'afficher. */
@Component({
  selector: 'app-dette-personnel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DecimalPipe, DatePipe, FormsModule, ButtonModule, DialogModule, InputNumberModule,
            InputTextModule, SelectModule, TableModule, TagModule, TooltipModule, BoutonImprimerComponent],
  template: `
@if (afficherTableau()) {
  <div class="table-card">
    <div class="dp-entete">
      <div>
        <div class="dp-titre">Dû au personnel</div>
        <div class="dp-aide">
          Pour chaque employé : le reliquat de l'année passée (fiche de l'employé) et chaque mois
          de paie de l'année scolaire — le net du bulletin validé, sinon le salaire convenu.
          Les enfants du personnel peuvent régler leur scolarité avec cette somme : mode
          « Compensation » au guichet.
        </div>
      </div>
      <div class="dp-total">
        <span>Dû à ce jour</span>
        <strong>{{ resteEchuTotal() | number:'1.0-0' }} FCFA</strong>
        <span class="dp-sous">sur {{ resteTotal() | number:'1.0-0' }} FCFA pour toute l'année</span>
      </div>
    </div>
    <p-table [value]="lignes()" [loading]="chargement()" styleClass="p-datatable-sm">
      <ng-template pTemplate="header">
        <tr>
          <th>Employé</th>
          <th class="num">Antérieur</th>
          <th class="num">Dû de l'année</th>
          <th class="num">Total dû</th>
          <th class="num">Réglé</th>
          <th class="num">dont compensé</th>
          <th class="num">Dû à ce jour</th>
          <th class="num">Reste (année)</th>
          <th class="num">Enfants</th>
          <th></th>
        </tr>
      </ng-template>
      <ng-template pTemplate="body" let-l>
        <tr>
          <td><strong>{{ l.nom_complet }}</strong><div class="dp-sous">{{ l.matricule }} · {{ l.poste }}</div></td>
          <td class="num">{{ l.du_anterieur | number:'1.0-0' }}</td>
          <td class="num">{{ l.du_annee | number:'1.0-0' }}</td>
          <td class="num">{{ l.du | number:'1.0-0' }}</td>
          <td class="num">{{ l.regle | number:'1.0-0' }}</td>
          <td class="num">{{ l.compense | number:'1.0-0' }}</td>
          <td class="num"><strong [class.dp-rouge]="l.reste_echu > 0">{{ l.reste_echu | number:'1.0-0' }}</strong></td>
          <td class="num">{{ l.reste | number:'1.0-0' }}</td>
          <td class="num">{{ l.nb_enfants }}</td>
          <td><p-button label="Fiche" icon="pi pi-id-card" size="small" severity="info" [outlined]="true"
                        (onClick)="ouvrir(l.id)" [ariaLabel]="'Fiche de ' + l.nom_complet" /></td>
        </tr>
      </ng-template>
      <ng-template pTemplate="emptymessage">
        <tr><td colspan="10" class="dp-vide">Aucun membre du personnel.</td></tr>
      </ng-template>
    </p-table>
  </div>
}

<p-dialog [header]="'Situation — ' + (situation()?.employe?.nom_complet || '')" [(visible)]="dialogVisible"
          [modal]="true" [style]="{width:'820px'}" [draggable]="false">
  @if (situation(); as s) {
    <div class="dp-barre">
      <span class="dp-sous">
        {{ s.employe.poste }} · {{ s.employe.matricule }} · salaire convenu
        {{ s.employe.salaire_mensuel | number:'1.0-0' }} FCFA/mois · année {{ s.exercice.annee_scolaire }}
        ({{ s.exercice.nb_mois }} mois : {{ s.exercice.premier_mois }} → {{ s.exercice.dernier_mois }})
      </span>
      <app-bouton-imprimer [pdf]="pdfSituation" [arg]="s.employe.id" />
    </div>
    <div class="dp-kpis">
      <div><span>Dû antérieur</span><strong>{{ s.totaux.du_anterieur | number:'1.0-0' }}</strong></div>
      <div><span>Dû de l'année</span><strong>{{ s.totaux.du_annee | number:'1.0-0' }}</strong></div>
      <div><span>Total dû</span><strong>{{ s.totaux.du | number:'1.0-0' }}</strong></div>
      <div><span>Réglé (dont compensé {{ s.totaux.compense | number:'1.0-0' }})</span><strong>{{ s.totaux.regle | number:'1.0-0' }}</strong></div>
      <div class="dp-kpi-reste"><span>Dû à ce jour</span><strong>{{ s.totaux.reste_echu | number:'1.0-0' }}</strong></div>
      <div><span>Reste sur l'année</span><strong>{{ s.totaux.reste | number:'1.0-0' }} FCFA</strong></div>
    </div>

    <div class="dp-section">Mois par mois</div>
    <table class="dp-tbl">
      <thead><tr>
        <th>Période</th><th>Base</th><th class="num">Dû</th><th class="num">Versé à la paie</th>
        <th class="num">Réglé ensuite</th><th class="num">Reste</th><th>Statut</th>
      </tr></thead>
      <tbody>
        @for (l of s.lignes; track $index) {
          <tr [class.dp-avenir]="!l.echu">
            <td>{{ l.type !== 'MOIS' ? '🔁 ' : '' }}{{ l.libelle }}</td>
            <td class="dp-sous">{{ libelleBase(l) }}</td>
            <td class="num">{{ l.du | number:'1.0-0' }}</td>
            <td class="num">{{ l.verse | number:'1.0-0' }}</td>
            <td class="num">{{ l.regle_ensuite | number:'1.0-0' }}</td>
            <td class="num"><strong>{{ l.reste | number:'1.0-0' }}</strong></td>
            <td><p-tag [value]="libelleStatut(l)" [severity]="severiteStatut(l)" /></td>
          </tr>
        } @empty {
          <tr><td colspan="7" class="dp-vide">Aucun mois de paie : vérifiez l'exercice et le salaire de la fiche.</td></tr>
        }
      </tbody>
      <tfoot><tr>
        <td colspan="2"><strong>Total</strong></td>
        <td class="num"><strong>{{ s.totaux.du | number:'1.0-0' }}</strong></td>
        <td class="num"><strong>{{ s.totaux.verse_validation | number:'1.0-0' }}</strong></td>
        <td class="num"><strong>{{ (s.totaux.versements + s.totaux.compense) | number:'1.0-0' }}</strong></td>
        <td class="num"><strong>{{ s.totaux.reste | number:'1.0-0' }}</strong></td>
        <td></td>
      </tr></tfoot>
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
            <span>{{ c.date | date:'dd/MM/yyyy' }} · {{ c.no_piece }} · {{ c.eleve }}
              @if (c.objet) { <span class="dp-sous">({{ c.objet }})</span> }</span>
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

    @if (s.totaux.reste_echu > 0) {
      <div class="dp-section">Verser à l'employé</div>
      <div class="dp-form">
        <div class="form-group">
          <label for="dp-montant">Montant</label>
          <p-inputNumber inputId="dp-montant" [(ngModel)]="form.montant" [min]="0" [max]="s.totaux.reste_echu"
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
    .dp-kpis { display:grid; grid-template-columns:repeat(6, 1fr); gap:8px; margin-bottom:12px; }
    .dp-barre { display:flex; justify-content:space-between; align-items:center; gap:10px; margin-bottom:10px; }
    .dp-avenir td { color:var(--text-3); }
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
  resteEchuTotal = signal(0);
  /** Requête du PDF pour <app-bouton-imprimer>. */
  readonly pdfSituation = (id: string) => this.rh.situationDettePdf(id);
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
      next: r => {
        this.lignes.set(r.results);
        this.resteTotal.set(r.reste_total);
        this.resteEchuTotal.set(r.reste_echu_total);
        this.chargement.set(false);
      },
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
                       detail: `Dû à ce jour : ${maj.totaux.reste_echu.toLocaleString('fr-FR')} FCFA` });
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

  libelleStatut(l: LigneDettePersonnel): string {
    if (l.statut !== 'SOLDE' && !l.echu) return l.statut === 'PARTIEL' ? 'Avancé' : 'À venir';
    return ({ SOLDE: 'Soldé', PARTIEL: 'Partiel', IMPAYE: 'Impayé' } as Record<string, string>)[l.statut] || l.statut;
  }

  severiteStatut(l: LigneDettePersonnel): 'success' | 'warn' | 'danger' | 'secondary' {
    if (l.statut === 'SOLDE') return 'success';
    if (!l.echu) return 'secondary';
    return l.statut === 'PARTIEL' ? 'warn' : 'danger';
  }

  libelleBase(l: LigneDettePersonnel): string {
    if (l.type === 'RELIQUAT') return 'Reliquat saisi';
    if (l.type === 'ANTERIEUR') return 'Bulletin antérieur';
    return l.source === 'BULLETIN' ? 'Bulletin' : 'Salaire convenu';
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
