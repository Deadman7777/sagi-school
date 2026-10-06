import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { DecimalPipe, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { MessageService } from 'primeng/api';
import { ApiService } from '../../core/services/api.service';

/**
 * Exercices multiples et continuité comptable : situation de chaque exercice,
 * à-nouveaux (régénérables tant que l'exercice source est ouvert), écritures
 * diverses de régularisation, import de balance.
 * Règles côté serveur : apps/comptabilite/exercices.py.
 */
@Component({
  selector: 'app-exercices',
  imports: [DecimalPipe, DatePipe, FormsModule, ButtonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="carte">
      <div class="carte-titre">📅 Exercices et continuité
        <p-button label="Créer un exercice antérieur" size="small" [text]="true" (onClick)="formEx.visible = !formEx.visible" />
      </div>
      @if (formEx.visible) {
        <div class="form ligne-form">
          <label>Année <input [(ngModel)]="formEx.annee_scolaire" placeholder="2024-2025" /></label>
          <label>Début <input type="date" [(ngModel)]="formEx.date_debut" /></label>
          <label>Fin <input type="date" [(ngModel)]="formEx.date_fin" /></label>
          <p-button label="Créer" size="small" severity="success" (onClick)="creerExercice()" />
        </div>
        <p class="aide">Pour une année non régularisée à l'arrivée sur SAGI SCHOOL : elle reste ouverte à côté de
          l'année courante, le temps d'y passer la balance et les régularisations, puis d'en produire les ETAFI.</p>
      }
      <table class="tab">
        <thead><tr><th>Exercice</th><th>Période</th><th>État</th><th class="num">Écritures</th>
          <th>Journal</th><th>Ouverture</th><th>Continuité</th><th>ETAFI</th><th></th></tr></thead>
        <tbody>
          @for (e of exercices(); track e.id; let i = $index) {
            <tr>
              <td><b>{{ e.annee_scolaire }}</b></td>
              <td>{{ e.date_debut | date:'dd/MM/yy' }} – {{ e.date_fin | date:'dd/MM/yy' }}</td>
              <td>
                @if (e.cloture) { <span class="pastille gris">clôturé</span> }
                @else if (e.courant) { <span class="pastille vert">courant</span> }
                @else { <span class="pastille orange">antérieur ouvert</span> }
              </td>
              <td class="num">{{ e.nb_ecritures }}</td>
              <td>{{ e.equilibre ? '✓ équilibré' : '⚠ écart ' + (e.ecart_journal | number:'1.0-0') }}</td>
              <td>{{ e.a_nouveaux ? 'à-nouveaux ' + e.an_depuis : (e.balance_importee ? 'balance importée' : 'soldes initiaux') }}</td>
              <td>
                @if (e.continuite_ok === true) { <span class="ok">✓ conforme</span> }
                @else if (e.continuite_ok === false) { <span class="ko">⚠ à régénérer ({{ e.ecarts_continuite.length }})</span> }
                @else { — }
              </td>
              <td>{{ e.nb_etafi || '—' }}</td>
              <td class="actions">
                @if (i < exercices().length - 1 && !exercices()[i + 1].cloture) {
                  <p-button [label]="e.cloture ? 'Reporter à-nouveaux' : 'À-nouveaux (provisoires)'" size="small" [text]="true"
                            (onClick)="genererAN(e)" />
                }
                @if (!e.cloture && !e.courant) {
                  <p-button label="Clôturer" size="small" [text]="true" severity="danger" (onClick)="cloturer(e)" />
                }
              </td>
            </tr>
          }
        </tbody>
      </table>
      <p class="aide">Les à-nouveaux reportent tout le bilan de clôture (trésorerie, créances, dettes, immobilisations,
        capitaux) sur l'exercice suivant. Tant que l'exercice source est ouvert, ils se régénèrent après chaque régularisation.</p>
    </div>

    <div class="grille">
      <!-- Écriture diverse -->
      <div class="carte">
        <div class="carte-titre">✍️ Écriture diverse (régularisation)</div>
        <div class="form">
          <label>Exercice
            <select [(ngModel)]="od.exercice_id">
              @for (e of exercicesOuverts(); track e.id) { <option [value]="e.id">{{ e.annee_scolaire }}</option> }
            </select></label>
          <label>Date <input type="date" [(ngModel)]="od.date" /></label>
          <label class="large">Libellé <input [(ngModel)]="od.libelle" /></label>
        </div>
        @for (l of od.lignes; track $index) {
          <div class="ligne-saisie">
            <input [(ngModel)]="l.no_compte" placeholder="Compte" style="flex:1" />
            <input [(ngModel)]="l.libelle" placeholder="Libellé (facultatif)" style="flex:2.5" />
            <input type="number" [(ngModel)]="l.debit" placeholder="Débit" style="flex:1.2" />
            <input type="number" [(ngModel)]="l.credit" placeholder="Crédit" style="flex:1.2" />
            <button type="button" (click)="od.lignes.splice($index, 1)">✕</button>
          </div>
        }
        <button type="button" class="lien" (click)="od.lignes.push({no_compte:'', libelle:'', debit:null, credit:null})">+ ligne</button>
        <p class="aide">Débit {{ totalOD('debit') | number:'1.0-0' }} · Crédit {{ totalOD('credit') | number:'1.0-0' }}
          @if (totalOD('debit') !== totalOD('credit')) { <span class="ko">— déséquilibrée</span> }</p>
        <p-button label="Enregistrer l'écriture" size="small" severity="success"
                  [disabled]="totalOD('debit') === 0 || totalOD('debit') !== totalOD('credit')" (onClick)="saisirOD()" />
      </div>

      <!-- Import de balance -->
      <div class="carte">
        <div class="carte-titre">📥 Import de balance</div>
        <div class="form">
          <label>Exercice
            <select [(ngModel)]="imp.exercice_id">
              @for (e of exercicesOuverts(); track e.id) { <option [value]="e.id">{{ e.annee_scolaire }}</option> }
            </select></label>
          <label>Nature
            <select [(ngModel)]="imp.nature">
              <option value="CLOTURE">Balance de clôture (tous les comptes de l'année)</option>
              <option value="OUVERTURE">Balance d'ouverture (comptes de bilan)</option>
            </select></label>
          <label class="large">Fichier Excel ou CSV (colonnes Compte, Libellé, Débit, Crédit)
            <input type="file" accept=".xlsx,.csv" (change)="imp.fichier = $any($event.target).files[0]" /></label>
        </div>
        <p-button label="Contrôler" size="small" [text]="true" [disabled]="!imp.fichier" (onClick)="importer(true)" />
        <p-button label="Importer" size="small" severity="success" [disabled]="!apercu()" (onClick)="importer(false)" />
        @if (apercu(); as a) {
          <p class="aide">{{ a.nb_lignes }} comptes, total {{ a.total_debit | number:'1.0-0' }} FCFA — balance équilibrée.
            Un nouvel import remplace le précédent.</p>
        }
      </div>
    </div>

    <div class="carte">
      <div class="carte-titre">📒 Écritures diverses et balances importées {{ pieces()?.exercice ? '— ' + pieces().exercice : '' }}</div>
      @for (p of pieces()?.pieces || []; track p.no_piece) {
        <div class="piece">
          <div class="piece-tete"><b>{{ p.no_piece }}</b> · {{ p.date | date:'dd/MM/yyyy' }} · {{ p.total | number:'1.0-0' }} FCFA
            @if (p.extournee) { <small>(extournée)</small> }
            @if (p.source === 'OD' && !p.extournee && !pieces().cloture) {
              <p-button label="Extourner" size="small" [text]="true" severity="danger" (onClick)="extourner(p)" />
            }
          </div>
          @for (l of p.lignes.slice(0, 6); track $index) {
            <div class="piece-ligne"><span>{{ l.no_compte }}</span><span>{{ l.libelle }}</span>
              <span class="num">{{ l.debit ? (l.debit | number:'1.0-0') : '' }}</span>
              <span class="num">{{ l.credit ? (l.credit | number:'1.0-0') : '' }}</span></div>
          }
          @if (p.lignes.length > 6) { <small>… {{ p.lignes.length - 6 }} autres lignes</small> }
        </div>
      } @empty { <p class="aide">Aucune écriture diverse sur cet exercice.</p> }
    </div>
  `,
  styles: [`
    .carte { background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:14px 16px; margin-bottom:16px; }
    .carte-titre { display:flex; justify-content:space-between; align-items:center; font-weight:600; color:var(--text); margin-bottom:10px; }
    .grille { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
    @media (max-width: 900px) { .grille { grid-template-columns:1fr; } }
    .tab { width:100%; border-collapse:collapse; font-size:12.5px; }
    .tab th { text-align:left; font-size:11px; color:var(--text-3); border-bottom:1px solid var(--border); padding:6px; }
    .tab th.num { text-align:right; }
    .tab td { padding:6px; border-bottom:1px solid var(--border); color:var(--text); }
    .num { text-align:right; font-variant-numeric:tabular-nums; }
    .actions { white-space:nowrap; }
    .pastille { font-size:10px; padding:2px 7px; border-radius:8px; }
    .vert { background:#d1fae5; color:#065f46; } .orange { background:#fef3c7; color:#92400e; } .gris { background:#e5e7eb; color:#374151; }
    .ok { color:#059669; } .ko { color:#dc2626; }
    .aide { font-size:12px; color:var(--text-3); margin:8px 0; }
    .form { display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-bottom:8px; }
    .form label { display:flex; flex-direction:column; font-size:12px; color:var(--text-2); gap:3px; }
    .form .large { grid-column: 1 / -1; }
    .ligne-form { grid-template-columns:repeat(4, 1fr); align-items:end; }
    .form input, .form select, .ligne-saisie input { padding:6px 8px; border:1px solid var(--border); border-radius:6px; background:var(--surface); color:var(--text); }
    .ligne-saisie { display:flex; gap:6px; margin-bottom:6px; }
    .lien { background:none; border:none; color:#1565c0; cursor:pointer; padding:0; font-size:12px; }
    .piece { border-bottom:1px solid var(--border); padding:6px 0; font-size:12.5px; color:var(--text); }
    .piece-tete { display:flex; align-items:center; gap:8px; }
    .piece-ligne { display:grid; grid-template-columns:70px 1fr 110px 110px; gap:6px; color:var(--text-2); font-size:12px; }
  `],
})
export class ExercicesComponent implements OnInit {
  private api = inject(ApiService);
  private msg = inject(MessageService);

  exercices = signal<any[]>([]);
  pieces = signal<any>(null);
  apercu = signal<any>(null);
  formEx: any = { visible: false, annee_scolaire: '', date_debut: '', date_fin: '' };
  od: any = this.odVide();
  imp: any = { exercice_id: '', nature: 'CLOTURE', fichier: null };

  ngOnInit() { this.charger(); }

  exercicesOuverts() { return this.exercices().filter(e => !e.cloture); }

  private odVide() {
    return { exercice_id: '', date: new Date().toISOString().slice(0, 10), libelle: '',
             lignes: [{ no_compte: '', libelle: '', debit: null, credit: null },
                      { no_compte: '', libelle: '', debit: null, credit: null }] };
  }
  private erreur(e: any) {
    this.msg.add({ severity: 'error', summary: 'Erreur', detail: e?.error?.error || JSON.stringify(e?.error || '') });
  }

  charger() {
    this.api.get<any>('/comptabilite/exercices-situation/').subscribe(r => {
      this.exercices.set(r.exercices || []);
      const ouverts = this.exercicesOuverts();
      const defaut = (ouverts.find(e => !e.courant) || ouverts[0])?.id || '';
      if (!this.od.exercice_id) this.od.exercice_id = defaut;
      if (!this.imp.exercice_id) this.imp.exercice_id = defaut;
      this.chargerPieces();
    });
  }
  chargerPieces() {
    this.api.get<any>('/comptabilite/ecritures-diverses/', { exercice: this.od.exercice_id || undefined })
      .subscribe(r => this.pieces.set(r));
  }

  creerExercice() {
    const f = this.formEx;
    this.api.post('/paiements/exercices/', { annee_scolaire: f.annee_scolaire, date_debut: f.date_debut,
      date_fin: f.date_fin, solde_initial_caisse: 0, solde_initial_banque: 0, solde_initial_mobile: 0 }).subscribe({
      next: () => { this.formEx = { visible: false }; this.charger();
                    this.msg.add({ severity: 'success', summary: 'Exercice créé' }); },
      error: e => this.msg.add({ severity: 'error', summary: 'Erreur',
                                 detail: Object.values(e?.error || {}).flat().join(' ') }),
    });
  }

  genererAN(e: any) {
    if (!confirm(`Générer les à-nouveaux de ${e.annee_scolaire} vers l'exercice suivant ?\nLes à-nouveaux existants seront remplacés et les soldes initiaux de trésorerie mis à jour.`)) return;
    this.api.post<any>('/comptabilite/a-nouveaux/', { source: e.id }).subscribe({
      next: r => { this.charger();
                   this.msg.add({ severity: 'success', summary: `À-nouveaux ${r.source} → ${r.cible}`,
                                  detail: `${r.nb_lignes} lignes${r.provisoire ? ' (provisoires : exercice source ouvert)' : ''}` }); },
      error: err => this.erreur(err),
    });
  }

  cloturer(e: any) {
    if (!confirm(`Clôturer l'exercice ${e.annee_scolaire} ?\nIl passera en lecture seule ; ses à-nouveaux seront reportés sur l'exercice suivant.`)) return;
    this.api.post<any>('/paiements/cloturer-exercice/', { exercice_id: e.id, confirme: true, a_nouveaux: true,
                                                          creer_suivant: false }).subscribe({
      next: () => { this.charger(); this.msg.add({ severity: 'success', summary: `Exercice ${e.annee_scolaire} clôturé` }); },
      error: err => this.msg.add({ severity: 'error', summary: 'Clôture impossible',
                                   detail: (err?.error?.problemes || []).join(' ; ') || err?.error?.error }),
    });
  }

  totalOD(sens: 'debit' | 'credit') {
    return Math.round(this.od.lignes.reduce((t: number, l: any) => t + (+l[sens] || 0), 0) * 100) / 100;
  }
  saisirOD() {
    const lignes = this.od.lignes.filter((l: any) => l.no_compte && (+l.debit || +l.credit))
      .map((l: any) => ({ no_compte: l.no_compte, libelle: l.libelle, debit: +l.debit || 0, credit: +l.credit || 0 }));
    this.api.post<any>('/comptabilite/ecritures-diverses/', { ...this.od, lignes }).subscribe({
      next: r => { const ex = this.od.exercice_id; this.od = this.odVide(); this.od.exercice_id = ex; this.charger();
                   this.msg.add({ severity: 'success', summary: `Écriture ${r.no_piece} enregistrée` }); },
      error: e => this.erreur(e),
    });
  }
  extourner(p: any) {
    if (!confirm(`Extourner l'écriture ${p.no_piece} ?`)) return;
    this.api.post<any>(`/comptabilite/ecritures-diverses/${p.no_piece}/extourner/`, {}).subscribe({
      next: () => this.charger(), error: e => this.erreur(e),
    });
  }

  importer(apercu: boolean) {
    const f = new FormData();
    f.append('fichier', this.imp.fichier);
    f.append('exercice_id', this.imp.exercice_id);
    f.append('nature', this.imp.nature);
    if (apercu) f.append('apercu', '1');
    this.api.post<any>('/comptabilite/import-balance/', f).subscribe({
      next: r => {
        if (apercu) { this.apercu.set(r); return; }
        this.apercu.set(null); this.charger();
        this.msg.add({ severity: 'success', summary: 'Balance importée', detail: `${r.nb_lignes} lignes — pièce ${r.no_piece}` });
      },
      error: e => { this.apercu.set(null); this.erreur(e); },
    });
  }
}
