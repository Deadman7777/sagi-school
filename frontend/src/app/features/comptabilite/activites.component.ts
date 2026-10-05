import { ChangeDetectionStrategy, Component, OnInit, computed, effect, inject, input, signal } from '@angular/core';
import { DecimalPipe, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { SelectModule } from 'primeng/select';
import { MessageService } from 'primeng/api';
import { ApiService } from '../../core/services/api.service';
import { PiecesJustificativesComponent } from '../../shared/pieces-justificatives.component';

/**
 * Comptabilité multi-activité : activités de l'établissement (enseignement,
 * transport, restauration…), leurs factures et leur résultat.
 * Règles comptables côté serveur : apps/comptabilite/activites.py.
 */
@Component({
  selector: 'app-activites',
  imports: [DecimalPipe, DatePipe, FormsModule, ButtonModule, DialogModule, SelectModule,
            PiecesJustificativesComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <!-- Résultat par activité -->
    <div class="carte">
      <div class="carte-titre">📊 Résultat par activité {{ resultats()?.exercice ? '— ' + resultats().exercice : '' }}</div>
      <table class="tab">
        <thead><tr>
          <th>Activité</th><th class="num">Produits</th><th class="num">Charges</th>
          <th class="num">Résultat</th><th class="num">Marge</th><th class="num">Créances clients</th>
        </tr></thead>
        <tbody>
          @for (a of resultats()?.activites || []; track a.activite_id) {
            <tr>
              <td>{{ a.libelle }} @if (a.est_principale) { <span class="badge">principale</span> }</td>
              <td class="num">{{ a.produits | number:'1.0-0' }}</td>
              <td class="num">{{ a.charges | number:'1.0-0' }}</td>
              <td class="num" [class.neg]="a.resultat < 0" [class.pos]="a.resultat > 0">{{ a.resultat | number:'1.0-0' }}</td>
              <td class="num">{{ a.marge === null ? '—' : (a.marge + ' %') }}</td>
              <td class="num">{{ a.creances | number:'1.0-0' }}</td>
            </tr>
          }
        </tbody>
        <tfoot><tr>
          <td>Total exercice</td>
          <td class="num">{{ resultats()?.total_produits | number:'1.0-0' }}</td>
          <td class="num">{{ resultats()?.total_charges | number:'1.0-0' }}</td>
          <td class="num">{{ resultats()?.total_resultat | number:'1.0-0' }}</td>
          <td></td><td></td>
        </tr></tfoot>
      </table>
      <p class="aide">Une écriture sans activité (scolarité, paie…) appartient à l'activité principale.
        Les dépenses s'affectent à une activité à la saisie de la charge.</p>
    </div>

    <div class="grille">
      <!-- Activités -->
      <div class="carte">
        <div class="carte-titre">
          🏷️ Activités
          <span>
            <select class="mini" [ngModel]="''" (ngModelChange)="depuisModele($event)">
              <option value="">+ depuis un modèle…</option>
              @for (m of modeles(); track m.type_activite) { <option [value]="m.type_activite">{{ m.libelle }}</option> }
            </select>
            <p-button icon="pi pi-plus" [rounded]="true" [text]="true" severity="success" (onClick)="ouvrirActivite()" />
          </span>
        </div>
        @for (a of activites(); track a.id) {
          <div class="ligne" [class.inactive]="!a.actif">
            <span><b>{{ a.libelle }}</b> <small>{{ a.code }}</small></span>
            <span class="droite">
              <span class="badge">{{ a.compte_produit }}</span>
              <span class="badge">TVA {{ a.regime_tva === 'TAXABLE' ? (a.taux_tva ? +a.taux_tva + ' %' : 'taux normal') : (a.regime_tva === 'EXONERE' ? 'exonérée' : 'hors champ') }}</span>
              <p-button icon="pi pi-pencil" [rounded]="true" [text]="true" size="small" severity="secondary" (onClick)="ouvrirActivite(a)" />
            </span>
          </div>
        }
      </div>

      <!-- Factures -->
      <div class="carte">
        <div class="carte-titre">
          🧾 Factures d'activité
          <p-button label="Nouvelle facture" icon="pi pi-plus" size="small" [disabled]="lectureSeule()" (onClick)="ouvrirFacture()" />
        </div>
        @for (f of factures(); track f.id) {
          <div class="ligne cliquable" (click)="selection.set(f)" [class.choisie]="selection()?.id === f.id">
            <span><b>{{ f.numero || 'Brouillon' }}</b> — {{ f.client_nom }}<br>
              <small>{{ f.date_facture | date:'dd/MM/yyyy' }} · {{ f.activite_libelle }}</small></span>
            <span class="droite">
              <span class="statut s-{{ f.statut }}">{{ libelleStatut(f.statut) }}</span>
              <b>{{ +f.montant_ttc | number:'1.0-0' }}</b>
            </span>
          </div>
        } @empty { <p class="aide">Aucune facture sur cet exercice.</p> }
      </div>
    </div>

    <!-- Détail de la facture choisie -->
    @if (selection(); as f) {
      <div class="carte">
        <div class="carte-titre">
          {{ f.numero || 'Brouillon' }} — {{ f.client_nom }}
          <span>
            @if (f.statut === 'BROUILLON') {
              <p-button label="Modifier" size="small" [text]="true" (onClick)="ouvrirFacture(f)" />
              <p-button label="Valider et comptabiliser" size="small" severity="success" (onClick)="action(f, 'valider')" />
            }
            @if (f.statut === 'VALIDEE' || f.statut === 'PARTIEL') {
              <p-button label="Encaisser" size="small" severity="success" (onClick)="ouvrirReglement(f)" />
            }
            @if (f.statut !== 'ANNULEE') {
              <p-button [label]="f.statut === 'BROUILLON' ? 'Supprimer' : 'Annuler'" size="small" severity="danger" [text]="true" (onClick)="annuler(f)" />
            }
            <p-button icon="pi pi-file-pdf" size="small" [text]="true" (onClick)="pdf(f)" />
          </span>
        </div>
        <table class="tab">
          <thead><tr><th>Désignation</th><th class="num">Qté</th><th class="num">P.U.</th><th class="num">Montant</th></tr></thead>
          <tbody>
            @for (l of f.lignes; track $index) {
              <tr><td>{{ l.libelle }}</td><td class="num">{{ l.quantite }}</td>
                  <td class="num">{{ l.prix_unitaire | number:'1.0-0' }}</td>
                  <td class="num">{{ l.quantite * l.prix_unitaire | number:'1.0-0' }}</td></tr>
            }
          </tbody>
          <tfoot>
            <tr><td colspan="3">HT · TVA {{ +f.taux_tva }} % · TTC</td>
              <td class="num">{{ +f.montant_ht | number:'1.0-0' }} · {{ +f.montant_tva | number:'1.0-0' }} · <b>{{ +f.montant_ttc | number:'1.0-0' }}</b></td></tr>
            <tr><td colspan="3">Reste à régler</td><td class="num"><b>{{ f.reste_a_regler | number:'1.0-0' }}</b></td></tr>
          </tfoot>
        </table>
        @if (f.reglements?.length) {
          <div class="sous-titre">Règlements</div>
          @for (r of f.reglements; track r.id) {
            <div class="ligne" [class.inactive]="r.annule">
              <span>{{ r.date | date:'dd/MM/yyyy' }} · {{ r.mode }} {{ r.reference ? '· ' + r.reference : '' }} · {{ r.no_piece }}</span>
              <span class="droite"><b>{{ r.montant | number:'1.0-0' }}</b>
                @if (!r.annule) { <p-button label="Annuler" size="small" [text]="true" severity="danger" (onClick)="annulerReglement(r)" /> }
                @else { <small>annulé</small> }
              </span>
            </div>
          }
        }
        <div class="sous-titre">Pièces justificatives (facture signée, chèque, bordereau…)</div>
        <app-pieces-justificatives objetType="FACTURE_ACT" [objetId]="f.id" />
      </div>
    }

    <!-- Dialog activité -->
    <p-dialog [header]="formActivite.id ? 'Modifier l\\'activité' : 'Nouvelle activité'" [(visible)]="dialogActivite"
              [modal]="true" [style]="{width:'480px'}">
      <div class="form">
        <label>Libellé * <input [(ngModel)]="formActivite.libelle" /></label>
        <label>Code * <input [(ngModel)]="formActivite.code" maxlength="20" /></label>
        <label>Type
          <select [(ngModel)]="formActivite.type_activite">
            @for (t of types; track t.v) { <option [value]="t.v">{{ t.l }}</option> }
          </select></label>
        <label>Compte de produit (classe 7) <input [(ngModel)]="formActivite.compte_produit" /></label>
        <label>Compte de charge par défaut (classe 6) <input [(ngModel)]="formActivite.compte_charge" placeholder="Ex. 618 carburant / transport" /></label>
        <label>Compte client <input [(ngModel)]="formActivite.compte_client" /></label>
        <label>TVA
          <select [(ngModel)]="formActivite.regime_tva">
            <option value="EXONERE">Exonérée</option><option value="TAXABLE">Soumise à TVA</option><option value="HORS_CHAMP">Hors champ</option>
          </select></label>
        @if (formActivite.regime_tva === 'TAXABLE') {
          <label>Taux (%) — vide : taux normal en vigueur <input type="number" [(ngModel)]="formActivite.taux_tva" /></label>
        }
        <label class="case"><input type="checkbox" [(ngModel)]="formActivite.actif" /> Active</label>
        <label class="case"><input type="checkbox" [(ngModel)]="formActivite.est_principale" /> Activité principale</label>
      </div>
      <ng-template pTemplate="footer">
        <p-button label="Annuler" severity="secondary" (onClick)="dialogActivite = false" />
        <p-button label="Enregistrer" severity="success" (onClick)="enregistrerActivite()" />
      </ng-template>
    </p-dialog>

    <!-- Dialog facture -->
    <p-dialog [header]="formFacture.id ? 'Modifier la facture' : 'Nouvelle facture'" [(visible)]="dialogFacture"
              [modal]="true" [style]="{width:'680px'}">
      <div class="form">
        <label>Activité *
          <select [(ngModel)]="formFacture.activite">
            @for (a of activitesActives(); track a.id) { <option [value]="a.id">{{ a.libelle }}</option> }
          </select></label>
        <label>Client * <input [(ngModel)]="formFacture.client_nom" /></label>
        <label>Contact / adresse <input [(ngModel)]="formFacture.client_contact" /></label>
        <label>NINEA du client <input [(ngModel)]="formFacture.client_ninea" /></label>
        <label>Date * <input type="date" [(ngModel)]="formFacture.date_facture" /></label>
        <label>Échéance <input type="date" [(ngModel)]="formFacture.date_echeance" /></label>
      </div>
      <div class="sous-titre">Lignes</div>
      @for (l of formFacture.lignes; track $index) {
        <div class="ligne-saisie">
          <input [(ngModel)]="l.libelle" placeholder="Désignation" style="flex:3" />
          <input type="number" [(ngModel)]="l.quantite" placeholder="Qté" style="flex:1" />
          <input type="number" [(ngModel)]="l.prix_unitaire" placeholder="Prix unitaire" style="flex:1.5" />
          <button type="button" (click)="formFacture.lignes.splice($index, 1)">✕</button>
        </div>
      }
      <button type="button" class="lien" (click)="formFacture.lignes.push({libelle:'', quantite:1, prix_unitaire:0})">+ Ajouter une ligne</button>
      <p class="aide">Total HT : <b>{{ totalHT() | number:'1.0-0' }}</b> FCFA — la TVA est calculée selon l'activité à l'enregistrement.</p>
      <ng-template pTemplate="footer">
        <p-button label="Annuler" severity="secondary" (onClick)="dialogFacture = false" />
        <p-button label="Enregistrer le brouillon" severity="success" (onClick)="enregistrerFacture()" />
      </ng-template>
    </p-dialog>

    <!-- Dialog règlement -->
    <p-dialog header="Encaisser la facture" [(visible)]="dialogReglement" [modal]="true" [style]="{width:'420px'}">
      <div class="form">
        <label>Montant <input type="number" [(ngModel)]="formReglement.montant" /></label>
        <label>Date <input type="date" [(ngModel)]="formReglement.date" /></label>
        <label>Mode
          <select [(ngModel)]="formReglement.mode">
            <option value="ESPECE">Espèce</option><option value="CHEQUE">Chèque</option>
            <option value="VIREMENT">Virement</option><option value="WAVE">Wave</option>
            <option value="ORANGE_MONEY">Orange Money</option><option value="FREE_MONEY">Free Money</option>
          </select></label>
        <label>Référence (n° de chèque, de bordereau…) <input [(ngModel)]="formReglement.reference" /></label>
      </div>
      <ng-template pTemplate="footer">
        <p-button label="Annuler" severity="secondary" (onClick)="dialogReglement = false" />
        <p-button label="Encaisser" severity="success" (onClick)="encaisser()" />
      </ng-template>
    </p-dialog>
  `,
  styles: [`
    .carte { background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:14px 16px; margin-bottom:16px; }
    .carte-titre { display:flex; justify-content:space-between; align-items:center; font-weight:600; color:var(--text); margin-bottom:10px; gap:8px; }
    .grille { display:grid; grid-template-columns:1fr 1.4fr; gap:16px; }
    @media (max-width: 900px) { .grille { grid-template-columns:1fr; } }
    .tab { width:100%; border-collapse:collapse; font-size:13px; }
    .tab th { text-align:left; font-size:11px; color:var(--text-3); border-bottom:1px solid var(--border); padding:6px 8px; }
    .tab td { padding:6px 8px; border-bottom:1px solid var(--border); color:var(--text); }
    .tab tfoot td { font-weight:700; }
    .num { text-align:right !important; font-variant-numeric: tabular-nums; }
    .neg { color:#ef4444; } .pos { color:#10b981; }
    .ligne { display:flex; justify-content:space-between; align-items:center; padding:7px 4px; border-bottom:1px solid var(--border); font-size:13px; color:var(--text); gap:8px; }
    .ligne.cliquable { cursor:pointer; } .ligne.choisie { background:var(--surface-hover); }
    .ligne.inactive { opacity:.5; }
    .droite { display:flex; align-items:center; gap:6px; }
    .badge { font-size:10px; padding:2px 6px; border-radius:8px; background:var(--surface-hover); color:var(--text-3); }
    .statut { font-size:10px; padding:2px 6px; border-radius:8px; }
    .s-BROUILLON { background:#e5e7eb; color:#374151; } .s-VALIDEE { background:#dbeafe; color:#1e40af; }
    .s-PARTIEL { background:#fef3c7; color:#92400e; } .s-PAYEE { background:#d1fae5; color:#065f46; }
    .s-ANNULEE { background:#fee2e2; color:#991b1b; }
    .aide { font-size:12px; color:var(--text-3); margin:8px 0 0; }
    .sous-titre { font-size:12px; font-weight:600; color:var(--text-2); margin:12px 0 6px; }
    .form { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
    .form label { display:flex; flex-direction:column; font-size:12px; color:var(--text-2); gap:3px; }
    .form label.case { flex-direction:row; align-items:center; gap:6px; }
    .form input, .form select, .ligne-saisie input { padding:6px 8px; border:1px solid var(--border); border-radius:6px; background:var(--surface); color:var(--text); }
    .ligne-saisie { display:flex; gap:6px; margin-bottom:6px; }
    .mini { font-size:12px; padding:3px 6px; border-radius:6px; border:1px solid var(--border); background:var(--surface); color:var(--text); }
    .lien { background:none; border:none; color:#1565c0; cursor:pointer; padding:0; font-size:12px; }
  `],
})
export class ActivitesComponent implements OnInit {
  /** Exercice consulté ('' = courant) et lecture seule (exercice clôturé). */
  exercice     = input<string>('');
  lectureSeule = input<boolean>(false);

  private api = inject(ApiService);
  private msg = inject(MessageService);

  activites  = signal<any[]>([]);
  modeles    = signal<any[]>([]);
  factures   = signal<any[]>([]);
  resultats  = signal<any>(null);
  selection  = signal<any>(null);
  activitesActives = computed(() => this.activites().filter(a => a.actif));

  dialogActivite = false;
  dialogFacture = false;
  dialogReglement = false;
  formActivite: any = {};
  formFacture: any = { lignes: [] };
  formReglement: any = {};

  types = [
    { v: 'ENSEIGNEMENT', l: 'Enseignement' }, { v: 'TRANSPORT', l: 'Transport' },
    { v: 'RESTAURATION', l: 'Restauration' }, { v: 'HEBERGEMENT', l: 'Hébergement / internat' },
    { v: 'PRESTATION', l: 'Prestations externes' }, { v: 'FORMATION', l: 'Formation continue' },
    { v: 'LOCATION', l: 'Location' }, { v: 'COMMERCE', l: 'Vente' }, { v: 'AUTRE', l: 'Autre' },
  ];

  constructor() {
    effect(() => { this.exercice(); this.chargerFactures(); this.chargerResultats(); });
  }

  ngOnInit() {
    this.chargerActivites();
    this.api.get<any[]>('/comptabilite/activites/modeles/').subscribe(r => this.modeles.set(r || []));
  }

  private params() { return { exercice: this.exercice() || undefined }; }
  private erreur(e: any) {
    this.msg.add({ severity: 'error', summary: 'Erreur', detail: e?.error?.error || JSON.stringify(e?.error || '') });
  }

  chargerActivites() {
    this.api.get<any>('/comptabilite/activites/').subscribe(r => this.activites.set(r.results || r || []));
  }
  chargerFactures() {
    this.api.get<any>('/comptabilite/factures-activite/', this.params()).subscribe(r => {
      const liste = r.results || r || [];
      this.factures.set(liste);
      const sel = this.selection();
      this.selection.set(sel ? liste.find((f: any) => f.id === sel.id) || null : null);
    });
  }
  chargerResultats() {
    this.api.get<any>('/comptabilite/activites-resultats/', this.params()).subscribe(r => this.resultats.set(r));
  }
  private toutRecharger() { this.chargerFactures(); this.chargerResultats(); }

  libelleStatut(s: string) {
    return ({ BROUILLON: 'Brouillon', VALIDEE: 'Validée', PARTIEL: 'Partielle', PAYEE: 'Réglée', ANNULEE: 'Annulée' } as any)[s] || s;
  }
  totalHT() {
    return (this.formFacture.lignes || []).reduce((t: number, l: any) => t + (+l.quantite || 0) * (+l.prix_unitaire || 0), 0);
  }

  depuisModele(type: string) {
    const m = this.modeles().find(x => x.type_activite === type);
    if (!m) return;
    this.ouvrirActivite();
    this.formActivite = { ...this.formActivite, ...m, code: type };
  }
  ouvrirActivite(a?: any) {
    this.formActivite = a ? { ...a } : { libelle: '', code: '', type_activite: 'AUTRE', compte_produit: '706',
                                          compte_charge: '', compte_client: '4111', regime_tva: 'EXONERE',
                                          taux_tva: null, actif: true, est_principale: false };
    this.dialogActivite = true;
  }
  enregistrerActivite() {
    const f = { ...this.formActivite, taux_tva: this.formActivite.taux_tva || null };
    const obs = f.id ? this.api.patch(`/comptabilite/activites/${f.id}/`, f) : this.api.post('/comptabilite/activites/', f);
    obs.subscribe({ next: () => { this.dialogActivite = false; this.chargerActivites(); this.chargerResultats(); },
                    error: e => this.erreur(e) });
  }

  ouvrirFacture(f?: any) {
    this.formFacture = f
      ? { ...f, lignes: (f.lignes || []).map((l: any) => ({ ...l })) }
      : { activite: this.activitesActives().find(a => !a.est_principale)?.id || this.activitesActives()[0]?.id,
          client_nom: '', client_contact: '', client_ninea: '', date_facture: new Date().toISOString().slice(0, 10),
          date_echeance: null, lignes: [{ libelle: '', quantite: 1, prix_unitaire: 0 }] };
    this.dialogFacture = true;
  }
  enregistrerFacture() {
    const f = this.formFacture;
    const corps = { activite: f.activite, client_nom: f.client_nom, client_contact: f.client_contact,
                    client_ninea: f.client_ninea, date_facture: f.date_facture, date_echeance: f.date_echeance || null,
                    lignes: f.lignes, exercice_id: this.exercice() || undefined };
    const obs = f.id ? this.api.patch(`/comptabilite/factures-activite/${f.id}/`, corps)
                     : this.api.post('/comptabilite/factures-activite/', corps);
    obs.subscribe({ next: (r: any) => { this.dialogFacture = false; this.selection.set(r); this.toutRecharger(); },
                    error: e => this.erreur(e) });
  }
  action(f: any, quoi: string) {
    this.api.post<any>(`/comptabilite/factures-activite/${f.id}/${quoi}/`, {}).subscribe({
      next: r => { this.selection.set(r); this.toutRecharger();
                   this.msg.add({ severity: 'success', summary: `Facture ${r.numero} comptabilisée` }); },
      error: e => this.erreur(e),
    });
  }
  annuler(f: any) {
    const motif = f.statut === 'BROUILLON' ? '' : prompt("Motif de l'annulation (extourne comptable) :");
    if (f.statut !== 'BROUILLON' && motif === null) return;
    if (f.statut === 'BROUILLON' && !confirm('Supprimer ce brouillon ?')) return;
    this.api.post<any>(`/comptabilite/factures-activite/${f.id}/annuler/`, { motif }).subscribe({
      next: r => { this.selection.set(r || null); this.toutRecharger(); },
      error: e => this.erreur(e),
    });
  }
  ouvrirReglement(f: any) {
    this.formReglement = { id: f.id, montant: f.reste_a_regler, date: new Date().toISOString().slice(0, 10),
                           mode: 'ESPECE', reference: '' };
    this.dialogReglement = true;
  }
  encaisser() {
    const r = this.formReglement;
    this.api.post<any>(`/comptabilite/factures-activite/${r.id}/regler/`, r).subscribe({
      next: f => { this.dialogReglement = false; this.selection.set(f); this.toutRecharger(); },
      error: e => this.erreur(e),
    });
  }
  annulerReglement(r: any) {
    if (!confirm('Annuler ce règlement (chèque impayé, erreur) ? Une extourne sera passée.')) return;
    this.api.post<any>(`/comptabilite/factures-activite/reglements/${r.id}/annuler/`, {}).subscribe({
      next: f => { this.selection.set(f); this.toutRecharger(); }, error: e => this.erreur(e),
    });
  }
  pdf(f: any) {
    this.api.getBlob(`/comptabilite/factures-activite/${f.id}/pdf/`).subscribe(b => {
      window.open(URL.createObjectURL(b), '_blank');
    });
  }
}
