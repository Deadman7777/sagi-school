import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { MessageService } from 'primeng/api';
import { ApiService } from '../../core/services/api.service';

/**
 * Profil fiscal de l'établissement et paramètres fiscaux datés.
 * Rien n'est codé en dur côté serveur : apps/fiscal/models.py, moteur.py.
 */
@Component({
  selector: 'app-profil-fiscal',
  imports: [DatePipe, FormsModule, ButtonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (profil(); as p) {
      <div class="carte">
        <div class="carte-titre">🏛️ Profil fiscal de l'établissement
          <p-button label="Enregistrer" size="small" severity="success" (onClick)="enregistrer()" />
        </div>
        <div class="form">
          <label>Forme juridique
            <select [(ngModel)]="p.forme_juridique">
              @for (c of p.choix.forme_juridique; track c[0]) { <option [value]="c[0]">{{ c[1] }}</option> }
            </select></label>
          <label>Statut
            <select [(ngModel)]="p.statut">
              @for (c of p.choix.statut; track c[0]) { <option [value]="c[0]">{{ c[1] }}</option> }
            </select></label>
          <label>Régime fiscal
            <select [(ngModel)]="p.regime">
              @for (c of p.choix.regime; track c[0]) { <option [value]="c[0]">{{ c[1] }}</option> }
            </select></label>
          <label>Centre fiscal (DGID) <input [(ngModel)]="p.centre_fiscal" /></label>
          <label>Début d'activité <input type="date" [(ngModel)]="p.date_debut_activite" /></label>
          <label>N° d'agrément / convention <input [(ngModel)]="p.numero_agrement" /></label>
          <label class="case"><input type="checkbox" [(ngModel)]="p.but_lucratif" /> But lucratif</label>
          <label class="case"><input type="checkbox" [(ngModel)]="p.assujetti_tva" /> Assujetti à la TVA (activité taxable)</label>
          <label class="case"><input type="checkbox" [(ngModel)]="p.proprietaire_locaux" /> Propriétaire de ses locaux</label>
        </div>

        <div class="sous-titre">Exonérations (datées et motivées)</div>
        @for (e of p.exonerations; track $index) {
          <div class="ligne-saisie">
            <select [(ngModel)]="e.obligation" style="flex:1.4">
              @for (o of p.obligations; track o.code) { <option [value]="o.code">{{ o.libelle }}</option> }
            </select>
            <input [(ngModel)]="e.motif" placeholder="Motif (agrément, texte…)" style="flex:2" />
            <input [(ngModel)]="e.reference" placeholder="Référence" style="flex:1.2" />
            <input type="date" [(ngModel)]="e.date_debut" style="flex:1" />
            <input type="date" [(ngModel)]="e.date_fin" style="flex:1" />
            <button type="button" (click)="p.exonerations.splice($index, 1)">✕</button>
          </div>
        }
        <button type="button" class="lien" (click)="p.exonerations.push({obligation:'IS', motif:'', reference:'', date_debut:null, date_fin:null})">+ exonération</button>
        <p class="aide">Les obligations s'appliquent selon ce profil : une association sans but lucratif n'est pas soumise à l'IS
          sur ses activités non lucratives, un établissement non assujetti ne déclare pas de TVA, une exonération ne vaut
          que pendant sa période.</p>
      </div>
    }

    <div class="carte">
      <div class="carte-titre">📐 Paramètres fiscaux en vigueur</div>
      <table class="tab">
        <thead><tr><th>Code</th><th>Paramètre</th><th class="num">Valeur</th><th>Depuis</th><th>Origine</th><th>Référence</th><th></th></tr></thead>
        <tbody>
          @for (x of parametres(); track x.id) {
            <tr [class.inactif]="!enVigueur(x)">
              <td><code>{{ x.code }}</code></td>
              <td>{{ x.libelle }} @if (x.a_verifier) { <span class="verif" title="Valeur à confirmer avec le texte en vigueur">à vérifier</span> }</td>
              <td class="num">{{ +x.valeur }} {{ x.unite === '%' ? '%' : x.unite }}</td>
              <td>{{ x.date_effet | date:'dd/MM/yyyy' }}{{ x.date_fin ? ' → ' + (x.date_fin | date:'dd/MM/yyyy') : '' }}</td>
              <td>{{ x.national ? 'national' : 'votre école' }}</td>
              <td class="ref">{{ x.reference }}</td>
              <td>@if (!x.national) { <button type="button" class="lien" (click)="supprimer(x)">supprimer</button> }</td>
            </tr>
          }
        </tbody>
      </table>
      <div class="sous-titre">Nouvelle valeur datée</div>
      <div class="ligne-saisie">
        <select [(ngModel)]="nouveau.code" (ngModelChange)="preRemplir()" style="flex:1.5">
          @for (c of codes(); track c) { <option [value]="c">{{ c }}</option> }
        </select>
        <input type="number" [(ngModel)]="nouveau.valeur" placeholder="Valeur" style="flex:1" />
        <input type="date" [(ngModel)]="nouveau.date_effet" style="flex:1" />
        <input [(ngModel)]="nouveau.reference" placeholder="Texte (loi de finances, convention…)" style="flex:2" />
        @if (peutNational()) { <label class="case"><input type="checkbox" [(ngModel)]="nouveau.national" /> national</label> }
        <p-button label="Ajouter" size="small" (onClick)="ajouter()" />
      </div>
      <p class="aide">Une nouvelle valeur ne remplace pas l'ancienne : elle s'applique à partir de sa date d'effet. Les exercices
        passés gardent le taux de leur époque. Une valeur « votre école » prime sur la valeur nationale (régime particulier,
        convention). Les montants calculés restent des estimations à confirmer avec votre expert-comptable ou la DGID.</p>
    </div>
  `,
  styles: [`
    .carte { background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:14px 16px; margin-bottom:16px; }
    .carte-titre { display:flex; justify-content:space-between; align-items:center; font-weight:600; color:var(--text); margin-bottom:10px; }
    .form { display:grid; grid-template-columns:repeat(3, 1fr); gap:10px; }
    @media (max-width: 900px) { .form { grid-template-columns:1fr; } }
    .form label { display:flex; flex-direction:column; font-size:12px; color:var(--text-2); gap:3px; }
    label.case { flex-direction:row !important; align-items:center; gap:6px; font-size:12px; color:var(--text-2); display:flex; }
    input, select { padding:6px 8px; border:1px solid var(--border); border-radius:6px; background:var(--surface); color:var(--text); }
    .ligne-saisie { display:flex; gap:6px; margin-bottom:6px; align-items:center; flex-wrap:wrap; }
    .sous-titre { font-size:12px; font-weight:600; color:var(--text-2); margin:14px 0 6px; }
    .lien { background:none; border:none; color:#1565c0; cursor:pointer; padding:0; font-size:12px; }
    .aide { font-size:12px; color:var(--text-3); margin:8px 0 0; }
    .tab { width:100%; border-collapse:collapse; font-size:12.5px; }
    .tab th { text-align:left; font-size:11px; color:var(--text-3); border-bottom:1px solid var(--border); padding:6px; }
    .tab th.num { text-align:right; }
    .tab td { padding:6px; border-bottom:1px solid var(--border); color:var(--text); }
    .num { text-align:right; } .ref { font-size:11px; color:var(--text-3); }
    tr.inactif td { opacity:.45; }
    .verif { font-size:10px; background:#fef3c7; color:#92400e; padding:1px 6px; border-radius:8px; }
  `],
})
export class ProfilFiscalComponent implements OnInit {
  private api = inject(ApiService);
  private msg = inject(MessageService);

  profil = signal<any>(null);
  parametres = signal<any[]>([]);
  vigueur = signal<Record<string, any>>({});
  codes = signal<string[]>([]);
  peutNational = signal(false);
  nouveau: any = { code: '', valeur: null, date_effet: new Date().toISOString().slice(0, 10), reference: '', national: false };

  ngOnInit() { this.chargerProfil(); this.chargerParametres(); }

  chargerProfil() {
    this.api.get<any>('/fiscal/profil/').subscribe(p => this.profil.set({ ...p, exonerations: p.exonerations || [] }));
  }
  chargerParametres() {
    this.api.get<any>('/fiscal/parametres/').subscribe(r => {
      this.parametres.set(r.parametres || []);
      this.vigueur.set(r.en_vigueur || {});
      this.codes.set(Object.keys(r.en_vigueur || {}));
      this.peutNational.set(!!r.peut_modifier_national);
      if (!this.nouveau.code && this.codes().length) { this.nouveau.code = this.codes()[0]; this.preRemplir(); }
    });
  }
  enVigueur(x: any) { return this.vigueur()[x.code]?.id === x.id; }
  preRemplir() {
    const p = this.parametres().find(x => x.code === this.nouveau.code);
    if (p) this.nouveau = { ...this.nouveau, libelle: p.libelle, unite: p.unite, valeur: +p.valeur };
  }

  enregistrer() {
    const { choix, obligations, id, created_at, updated_at, ...corps } = this.profil();
    this.api.patch<any>('/fiscal/profil/', corps).subscribe({
      next: () => { this.chargerProfil(); this.msg.add({ severity: 'success', summary: 'Profil fiscal enregistré' }); },
      error: e => this.msg.add({ severity: 'error', summary: 'Erreur', detail: JSON.stringify(e?.error || '') }),
    });
  }
  ajouter() {
    this.api.post<any>('/fiscal/parametres/', this.nouveau).subscribe({
      next: () => { this.chargerParametres(); this.msg.add({ severity: 'success', summary: 'Paramètre ajouté' }); },
      error: e => this.msg.add({ severity: 'error', summary: 'Erreur', detail: e?.error?.error || JSON.stringify(e?.error || '') }),
    });
  }
  supprimer(x: any) {
    if (!confirm(`Supprimer la valeur ${x.code} du ${x.date_effet} ?`)) return;
    this.api.delete(`/fiscal/parametres/?id=${x.id}`).subscribe({ next: () => this.chargerParametres() });
  }
}
