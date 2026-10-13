import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { MessageService } from 'primeng/api';
import { ChequeRecu, PaiementsService, StatutCheque } from '../../core/services/paiements.service';

type Filtre = 'A_SUIVRE' | 'TOUS' | StatutCheque;

const LIBELLE_STATUT: Record<StatutCheque, string> = {
  EN_PORTEFEUILLE: 'En portefeuille',
  REMIS: 'Remis en banque',
  ENCAISSE: 'Encaissé',
  IMPAYE: 'Impayé',
  ANNULE: 'Annulé',
};

function aujourdhui(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/**
 * Registre des chèques reçus : chaque chèque, de sa réception à son
 * encaissement — qui l'a reçu, quand il a été remis en banque et par qui,
 * quand le crédit a été constaté, ou pourquoi il est revenu impayé.
 * Les écritures (513 → 521, retour d'impayé) sont passées par le serveur
 * (apps/paiements/cheques.py).
 */
@Component({
  selector: 'app-registre-cheques',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DecimalPipe, DatePipe, FormsModule, ButtonModule, DialogModule],
  template: `
<div class="rc">
  <div class="rc-head">
    <div>
      <h3 class="rc-title">Registre des chèques</h3>
      <div class="rc-sub">
        Un chèque reçu attend en portefeuille (compte 513) jusqu'à sa remise en banque (521).
        Cochez les chèques déposés pour les remettre en banque, puis confirmez leur encaissement
        quand le crédit apparaît sur le relevé.
      </div>
    </div>
  </div>

  <div class="cartes">
    @for (c of cartes(); track c.statut) {
      <button type="button" class="carte" [class.active]="filtre() === c.statut" [style.--acc]="c.couleur"
              (click)="choisirFiltre(c.statut)">
        <span class="carte-lbl">{{ c.libelle }}</span>
        <span class="carte-val">{{ c.montant | number:'1.0-0' }} <small>FCFA</small></span>
        <span class="carte-nb">{{ c.nb }} chèque(s)</span>
      </button>
    }
  </div>

  <div class="barre">
    <div class="seg" role="group" aria-label="Filtrer les chèques">
      @for (f of filtres; track f.value) {
        <button type="button" class="seg-btn" [class.active]="filtre() === f.value"
                (click)="choisirFiltre(f.value)">{{ f.label }}</button>
      }
    </div>
    <input class="champ recherche" type="search" placeholder="N°, banque, tireur, élève, reçu, bordereau…"
           aria-label="Rechercher un chèque" [ngModel]="recherche()" (ngModelChange)="rechercher($event)" />
  </div>

  @if (selection().length) {
    <div class="selection">
      <span><b>{{ selection().length }}</b> chèque(s) sélectionné(s) — {{ totalSelection() | number:'1.0-0' }} FCFA</span>
      <span class="sel-actions">
        @if (selectionRemettable()) {
          <p-button label="Remettre en banque" icon="pi pi-building-columns" size="small"
                    (onClick)="ouvrirRemise()" />
        }
        @if (selectionEncaissable()) {
          <p-button label="Confirmer l'encaissement" icon="pi pi-check" size="small" severity="success"
                    (onClick)="ouvrirEncaissement()" />
        }
        <button type="button" class="lien" (click)="selection.set([])">Désélectionner</button>
      </span>
    </div>
  }

  <div class="table-wrap">
    <table class="tbl">
      <thead>
        <tr>
          <th scope="col"><span class="sr-only">Sélection</span></th>
          <th scope="col">Chèque</th>
          <th scope="col">Tireur</th>
          <th scope="col">Reçu</th>
          <th scope="col" class="tr">Montant</th>
          <th scope="col">Règle</th>
          <th scope="col">Suivi</th>
          <th scope="col"><span class="sr-only">Actions</span></th>
        </tr>
      </thead>
      <tbody>
        @for (c of cheques(); track c.id) {
          <tr [class.attenue]="c.statut === 'ANNULE'">
            <td>
              @if (c.statut === 'EN_PORTEFEUILLE' || c.statut === 'REMIS') {
                <input type="checkbox" [checked]="estSelectionne(c)" (change)="basculer(c)"
                       [attr.aria-label]="'Sélectionner le chèque ' + (c.numero || 'sans numéro')" />
              }
            </td>
            <td>
              <div class="gras">n° {{ c.numero || '—' }}</div>
              <div class="petit">{{ c.banque || 'Banque ?' }}</div>
              @if (!c.numero || !c.banque) { <span class="tag tag-orange">À compléter</span> }
              @if (c.compte_reception === '521') { <span class="tag tag-gris" title="Reçu avant le registre : déjà porté en banque, sa remise n'écrit rien">Avant registre</span> }
            </td>
            <td>
              {{ c.tireur || '—' }}
              @if (c.date_emission) { <div class="petit">émis le {{ c.date_emission | date:'dd/MM/yyyy' }}</div> }
            </td>
            <td>
              {{ c.date_reception | date:'dd/MM/yyyy' }}
              @if (c.recu_par_nom) { <div class="petit">par {{ c.recu_par_nom }}</div> }
            </td>
            <td class="tr gras">
              {{ c.montant | number:'1.0-0' }}
              @if (c.montant_affecte !== c.montant && c.statut === 'EN_PORTEFEUILLE') {
                <div class="petit alerte">affecté : {{ c.montant_affecte | number:'1.0-0' }}</div>
              }
            </td>
            <td>
              @for (r of c.recus; track r.paiement) {
                <div [class.barre-txt]="r.statut === 'ANNULE'">
                  {{ r.eleve }} <span class="petit">· {{ r.no_piece }} · {{ r.montant | number:'1.0-0' }}</span>
                </div>
              }
            </td>
            <td>
              <span class="statut" [class]="'statut st-' + c.statut">{{ libelle(c.statut) }}</span>
              @if (c.date_remise) {
                <div class="petit">Remis le {{ c.date_remise | date:'dd/MM/yyyy' }}
                  @if (c.bordereau) { · bordereau {{ c.bordereau }} }
                  @if (c.remis_par_nom) { · par {{ c.remis_par_nom }} }
                  @if (c.no_piece_remise) { · {{ c.no_piece_remise }} }
                </div>
              }
              @if (c.date_encaissement) {
                <div class="petit">Crédité le {{ c.date_encaissement | date:'dd/MM/yyyy' }}
                  @if (c.encaisse_par_nom) { · par {{ c.encaisse_par_nom }} }
                </div>
              }
              @if (c.date_impaye) {
                <div class="petit alerte">Impayé le {{ c.date_impaye | date:'dd/MM/yyyy' }} — {{ c.motif_impaye }}
                  @if (c.impaye_par_nom) { · par {{ c.impaye_par_nom }} }
                </div>
              }
              @if (c.observations) { <div class="petit">{{ c.observations }}</div> }
            </td>
            <td class="actions">
              <button type="button" class="lien" (click)="ouvrirComplement(c)"
                      [attr.aria-label]="'Compléter le chèque ' + (c.numero || '')">✏️ Détails</button>
              @if (c.statut === 'EN_PORTEFEUILLE' || c.statut === 'REMIS' || c.statut === 'ENCAISSE') {
                <button type="button" class="lien rouge" (click)="ouvrirImpaye(c)">Impayé</button>
              }
            </td>
          </tr>
        } @empty {
          <tr><td colspan="8" class="vide">{{ chargement() ? 'Chargement…' : 'Aucun chèque.' }}</td></tr>
        }
      </tbody>
    </table>
  </div>
</div>

<!-- Remise en banque -->
<p-dialog header="Remise en banque" [(visible)]="remiseVisible" [modal]="true" [style]="{width:'440px'}">
  <p class="aide">{{ selection().length }} chèque(s) — <b>{{ totalSelection() | number:'1.0-0' }} FCFA</b>.
    Écriture : Banque 521 au débit, Chèques à encaisser 513 au crédit.</p>
  <label class="lbl" for="rc-date-remise">Date de remise *</label>
  <input id="rc-date-remise" class="champ" type="date" [(ngModel)]="dateAction" />
  <label class="lbl" for="rc-bordereau">N° du bordereau de remise</label>
  <input id="rc-bordereau" class="champ" [(ngModel)]="bordereau" />
  <ng-template pTemplate="footer">
    <p-button label="Annuler" [text]="true" (onClick)="remiseVisible = false" />
    <p-button label="Remettre en banque" [loading]="envoi()" (onClick)="remettre()" />
  </ng-template>
</p-dialog>

<!-- Encaissement -->
<p-dialog header="Confirmer l'encaissement" [(visible)]="encaissementVisible" [modal]="true" [style]="{width:'440px'}">
  <p class="aide">Le crédit de {{ selection().length }} chèque(s) ({{ totalSelection() | number:'1.0-0' }} FCFA)
    apparaît sur le relevé bancaire. Un chèque encore en portefeuille est d'abord remis à cette date.</p>
  <label class="lbl" for="rc-date-enc">Date du crédit *</label>
  <input id="rc-date-enc" class="champ" type="date" [(ngModel)]="dateAction" />
  <ng-template pTemplate="footer">
    <p-button label="Annuler" [text]="true" (onClick)="encaissementVisible = false" />
    <p-button label="Confirmer" severity="success" [loading]="envoi()" (onClick)="encaisser()" />
  </ng-template>
</p-dialog>

<!-- Compléter les détails -->
<p-dialog header="Détails du chèque" [(visible)]="complementVisible" [modal]="true" [style]="{width:'480px'}">
  @if (enEdition(); as c) {
    <div class="deux">
      <div><label class="lbl" for="rc-num">N° du chèque</label>
        <input id="rc-num" class="champ" [(ngModel)]="edition.numero" /></div>
      <div><label class="lbl" for="rc-banque">Banque</label>
        <input id="rc-banque" class="champ" [(ngModel)]="edition.banque" /></div>
      <div><label class="lbl" for="rc-tireur">Tireur</label>
        <input id="rc-tireur" class="champ" [(ngModel)]="edition.tireur" /></div>
      <div><label class="lbl" for="rc-emis">Date d'émission</label>
        <input id="rc-emis" class="champ" type="date" [(ngModel)]="edition.date_emission" /></div>
    </div>
    <label class="lbl" for="rc-obs">Observations</label>
    <textarea id="rc-obs" class="champ" rows="2" [(ngModel)]="edition.observations"></textarea>
  }
  <ng-template pTemplate="footer">
    <p-button label="Annuler" [text]="true" (onClick)="complementVisible = false" />
    <p-button label="Enregistrer" [loading]="envoi()" (onClick)="enregistrerComplement()" />
  </ng-template>
</p-dialog>

<!-- Impayé -->
<p-dialog header="Chèque impayé" [(visible)]="impayeVisible" [modal]="true" [style]="{width:'500px'}">
  @if (enEdition(); as c) {
    <p class="aide">Chèque n° {{ c.numero || '—' }} {{ c.banque }} — <b>{{ c.montant | number:'1.0-0' }} FCFA</b>.</p>
    <div class="info alerte-bloc">
      Les reçus réglés par ce chèque seront <b>annulés</b> et la famille redevra la somme :
      @for (r of c.recus; track r.paiement) { @if (r.statut === 'ACTIF') { <div>· {{ r.eleve }} — {{ r.no_piece }}</div> } }
      @if (c.statut !== 'EN_PORTEFEUILLE' && c.compte_reception === '513') {
        <div>La banque reprend le montant : 513 au débit, 521 au crédit.</div>
      }
    </div>
    <label class="lbl" for="rc-date-imp">Date du rejet *</label>
    <input id="rc-date-imp" class="champ" type="date" [(ngModel)]="dateAction" />
    <label class="lbl" for="rc-motif">Motif *</label>
    <input id="rc-motif" class="champ" [(ngModel)]="motif" placeholder="Provision insuffisante, signature non conforme…" />
  }
  <ng-template pTemplate="footer">
    <p-button label="Annuler" [text]="true" (onClick)="impayeVisible = false" />
    <p-button label="Déclarer impayé" severity="danger" [loading]="envoi()" (onClick)="declarerImpaye()" />
  </ng-template>
</p-dialog>
  `,
  styles: [`
    .rc { display:flex; flex-direction:column; gap:12px; }
    .rc-title { margin:0; font-size:17px; color:var(--text); }
    .rc-sub { font-size:12px; color:var(--text-3); margin-top:3px; max-width:760px; }
    .cartes { display:grid; grid-template-columns:repeat(auto-fit, minmax(170px, 1fr)); gap:10px; }
    .carte { display:flex; flex-direction:column; gap:2px; text-align:left; background:var(--surface); border:1px solid var(--border);
             border-top:3px solid var(--acc); border-radius:10px; padding:10px 12px; cursor:pointer; font:inherit; color:var(--text); }
    .carte.active { border-color:var(--acc); }
    .carte:focus-visible { outline:2px solid #00d4aa; outline-offset:2px; }
    .carte-lbl { font-size:11px; text-transform:uppercase; color:var(--text-3); }
    .carte-val { font-size:17px; font-weight:700; font-variant-numeric:tabular-nums; }
    .carte-nb { font-size:12px; color:var(--text-3); }
    .barre { display:flex; gap:10px; flex-wrap:wrap; align-items:center; justify-content:space-between; }
    .seg { display:flex; gap:4px; flex-wrap:wrap; }
    .seg-btn { border:1px solid var(--border); background:var(--surface); color:var(--text-2); border-radius:8px; padding:6px 10px; font-size:12.5px; cursor:pointer; }
    .seg-btn.active { border-color:#00d4aa; color:var(--text); font-weight:600; background:rgba(0,212,170,.1); }
    .seg-btn:focus-visible, .lien:focus-visible { outline:2px solid #00d4aa; outline-offset:2px; }
    .champ { width:100%; box-sizing:border-box; background:var(--surface); border:1px solid var(--border); color:var(--text); border-radius:8px; padding:8px 10px; font-size:13px; font-family:inherit; }
    .recherche { max-width:340px; }
    .selection { display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap;
                 background:rgba(0,212,170,.08); border:1px solid #00d4aa; border-radius:8px; padding:8px 12px; font-size:13px; color:var(--text); }
    .sel-actions { display:flex; gap:8px; align-items:center; }
    .table-wrap { overflow-x:auto; background:var(--surface); border:1px solid var(--border); border-radius:10px; }
    .tbl { width:100%; border-collapse:collapse; font-size:13px; }
    .tbl th { background:var(--surface-2); color:var(--text-3); font-size:11px; text-transform:uppercase; text-align:left; padding:8px 10px; white-space:nowrap; }
    .tbl th.tr { text-align:right; }
    .tbl td { padding:7px 10px; border-top:1px solid var(--border); color:var(--text-2); vertical-align:top; font-variant-numeric:tabular-nums; }
    tr.attenue td { opacity:.55; }
    .tr { text-align:right; }
    .gras { font-weight:600; color:var(--text); }
    .petit { font-size:11.5px; color:var(--text-3); }
    .alerte { color:#dc2626; }
    .barre-txt { text-decoration:line-through; opacity:.6; }
    .vide { text-align:center; padding:24px; color:var(--text-3); }
    .actions { white-space:nowrap; text-align:right; }
    .lien { background:none; border:0; color:#0099ff; cursor:pointer; font-size:12.5px; padding:2px 4px; }
    .lien.rouge { color:#dc2626; }
    .tag { display:inline-block; font-size:10.5px; padding:1px 7px; border-radius:10px; margin:2px 4px 0 0; font-weight:600; }
    .tag-orange { background:rgba(245,158,11,.15); color:var(--text); border:1px solid #f59e0b; }
    .tag-gris { background:var(--surface-2); color:var(--text-3); }
    .statut { display:inline-block; font-size:11px; font-weight:700; padding:2px 8px; border-radius:10px; color:var(--text); }
    .st-EN_PORTEFEUILLE { background:rgba(245,158,11,.18); border:1px solid #f59e0b; }
    .st-REMIS { background:rgba(3,105,161,.15); border:1px solid #0369a1; }
    .st-ENCAISSE { background:rgba(5,150,105,.15); border:1px solid #059669; }
    .st-IMPAYE { background:rgba(220,38,38,.15); border:1px solid #dc2626; }
    .st-ANNULE { background:var(--surface-2); border:1px solid var(--border); }
    .lbl { display:block; font-size:12px; font-weight:600; color:var(--text-2); margin:8px 0 3px; }
    .aide { font-size:12.5px; color:var(--text-2); margin:0 0 6px; }
    .deux { display:grid; grid-template-columns:1fr 1fr; gap:0 10px; }
    .info { background:rgba(3,105,161,.08); border:1px solid rgba(3,105,161,.35); color:var(--text-2); border-radius:8px; padding:8px 10px; font-size:12.5px; }
    .alerte-bloc { background:rgba(220,38,38,.07); border-color:rgba(220,38,38,.4); }
    .sr-only { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; }
  `],
})
export class RegistreChequesComponent implements OnInit {
  private api = inject(PaiementsService);
  private msg = inject(MessageService);

  readonly cheques = signal<ChequeRecu[]>([]);
  readonly totaux = signal<Record<string, { nb: number; montant: number }>>({});
  readonly filtre = signal<Filtre>('A_SUIVRE');
  readonly recherche = signal('');
  readonly selection = signal<ChequeRecu[]>([]);
  readonly chargement = signal(false);
  readonly envoi = signal(false);
  readonly enEdition = signal<ChequeRecu | null>(null);

  readonly filtres: { value: Filtre; label: string }[] = [
    { value: 'A_SUIVRE', label: 'À suivre' },
    { value: 'EN_PORTEFEUILLE', label: 'En portefeuille' },
    { value: 'REMIS', label: 'Remis' },
    { value: 'ENCAISSE', label: 'Encaissés' },
    { value: 'IMPAYE', label: 'Impayés' },
    { value: 'ANNULE', label: 'Annulés' },
    { value: 'TOUS', label: 'Tous' },
  ];

  readonly cartes = computed(() => {
    const t = this.totaux();
    const carte = (statut: StatutCheque, couleur: string) => ({
      statut, couleur, libelle: LIBELLE_STATUT[statut],
      nb: t[statut]?.nb ?? 0, montant: t[statut]?.montant ?? 0,
    });
    return [carte('EN_PORTEFEUILLE', '#f59e0b'), carte('REMIS', '#0369a1'),
            carte('ENCAISSE', '#059669'), carte('IMPAYE', '#dc2626')];
  });

  readonly totalSelection = computed(() => this.selection().reduce((s, c) => s + Number(c.montant), 0));
  readonly selectionRemettable = computed(() =>
    this.selection().every(c => c.statut === 'EN_PORTEFEUILLE'));
  readonly selectionEncaissable = computed(() =>
    this.selection().every(c => c.statut === 'EN_PORTEFEUILLE' || c.statut === 'REMIS'));

  remiseVisible = false;
  encaissementVisible = false;
  complementVisible = false;
  impayeVisible = false;
  dateAction = aujourdhui();
  bordereau = '';
  motif = '';
  edition = { numero: '', banque: '', tireur: '', date_emission: '', observations: '' };
  private minuterie: ReturnType<typeof setTimeout> | undefined;

  ngOnInit() { this.charger(); }

  libelle(s: StatutCheque) { return LIBELLE_STATUT[s]; }

  charger() {
    const f = this.filtre();
    const params: Record<string, string> = {};
    if (f === 'A_SUIVRE') params['statut'] = 'EN_PORTEFEUILLE,REMIS';
    else if (f !== 'TOUS') params['statut'] = f;
    if (this.recherche().trim()) params['q'] = this.recherche().trim();
    this.chargement.set(true);
    this.api.getCheques(params).subscribe({
      next: r => {
        this.cheques.set(r.results);
        this.chargement.set(false);
        this.selection.set([]);
        // Les cartes donnent toujours la vue d'ensemble, quel que soit le filtre.
        if (f === 'TOUS' && !params['q']) this.totaux.set(r.totaux);
      },
      error: err => { this.chargement.set(false); this.erreur(err); },
    });
    if (f !== 'TOUS' || params['q']) {
      this.api.getCheques().subscribe({ next: r => this.totaux.set(r.totaux) });
    }
  }

  choisirFiltre(f: Filtre) { this.filtre.set(f); this.charger(); }

  rechercher(q: string) {
    this.recherche.set(q);
    clearTimeout(this.minuterie);
    this.minuterie = setTimeout(() => this.charger(), 300);
  }

  estSelectionne(c: ChequeRecu) { return this.selection().some(s => s.id === c.id); }

  basculer(c: ChequeRecu) {
    this.selection.update(sel => this.estSelectionne(c) ? sel.filter(s => s.id !== c.id) : [...sel, c]);
  }

  ouvrirRemise() { this.dateAction = aujourdhui(); this.bordereau = ''; this.remiseVisible = true; }
  ouvrirEncaissement() { this.dateAction = aujourdhui(); this.encaissementVisible = true; }

  remettre() {
    this.envoi.set(true);
    this.api.remettreCheques(this.selection().map(c => c.id), this.dateAction, this.bordereau).subscribe({
      next: r => {
        this.msg.add({ severity: 'success', summary: `Remise ${r.no_piece}`,
                       detail: `${r.nb} chèque(s) remis en banque — ${r.total.toLocaleString('fr-FR')} FCFA` });
        this.remiseVisible = false;
        this.envoi.set(false);
        this.charger();
      },
      error: err => { this.envoi.set(false); this.erreur(err); },
    });
  }

  encaisser() {
    this.envoi.set(true);
    this.api.encaisserCheques(this.selection().map(c => c.id), this.dateAction).subscribe({
      next: r => {
        this.msg.add({ severity: 'success', summary: 'Encaissement confirmé', detail: `${r.nb} chèque(s)` });
        this.encaissementVisible = false;
        this.envoi.set(false);
        this.charger();
      },
      error: err => { this.envoi.set(false); this.erreur(err); },
    });
  }

  ouvrirComplement(c: ChequeRecu) {
    this.enEdition.set(c);
    this.edition = { numero: c.numero, banque: c.banque, tireur: c.tireur,
                     date_emission: c.date_emission ?? '', observations: c.observations };
    this.complementVisible = true;
  }

  enregistrerComplement() {
    const c = this.enEdition();
    if (!c) return;
    this.envoi.set(true);
    this.api.completerCheque(c.id, { ...this.edition, date_emission: this.edition.date_emission || null })
      .subscribe({
        next: () => {
          this.complementVisible = false;
          this.envoi.set(false);
          this.charger();
        },
        error: err => { this.envoi.set(false); this.erreur(err); },
      });
  }

  ouvrirImpaye(c: ChequeRecu) {
    this.enEdition.set(c);
    this.dateAction = aujourdhui();
    this.motif = '';
    this.impayeVisible = true;
  }

  declarerImpaye() {
    const c = this.enEdition();
    if (!c) return;
    if (!this.motif.trim()) {
      this.msg.add({ severity: 'warn', summary: 'Motif requis', detail: 'Indiquez le motif du rejet.' });
      return;
    }
    this.envoi.set(true);
    this.api.declarerChequeImpaye(c.id, this.dateAction, this.motif.trim()).subscribe({
      next: r => {
        const recus = r.recus_annules.map(x => x.no_piece).join(', ') || 'aucun';
        this.msg.add({ severity: 'warn', summary: 'Chèque impayé', life: 10000,
                       detail: `Reçus annulés : ${recus}. La famille redoit ces montants.` });
        for (const a of r.autres_modes) {
          this.msg.add({ severity: 'info', summary: `${a.eleve} — ${a.no_piece}`, life: 15000,
                         detail: `${a.montant.toLocaleString('fr-FR')} FCFA de ce reçu ont été payés autrement `
                               + `(espèces, Wave…) : ressaisissez-les sur un nouveau reçu.` });
        }
        this.impayeVisible = false;
        this.envoi.set(false);
        this.charger();
      },
      error: err => { this.envoi.set(false); this.erreur(err); },
    });
  }

  private erreur(err: unknown) {
    const e = err as { error?: { error?: string; detail?: string } };
    this.msg.add({ severity: 'error', summary: 'Erreur',
                   detail: e?.error?.error || e?.error?.detail || 'Opération impossible.' });
  }
}
