import { ChangeDetectionStrategy, Component, effect, inject, input, signal } from '@angular/core';
import { DecimalPipe, DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { MessageService } from 'primeng/api';
import { ApiService } from '../../core/services/api.service';
import { BoutonImprimerComponent } from '../../shared/bouton-imprimer.component';

/**
 * Dossier ETAFI d'un exercice (SYSCOHADA Révisé) : contrôles de cohérence,
 * téléchargement de chaque document, génération du dossier complet (ZIP) et
 * archives versionnées. Calculs : apps/comptabilite/etats.py et etafi.py.
 */
@Component({
  selector: 'app-etafi-dossier',
  imports: [BoutonImprimerComponent, DecimalPipe, DatePipe, FormsModule, ButtonModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (dossier(); as d) {
      <div class="carte">
        <div class="carte-titre">
          🗂️ Dossier ETAFI — exercice {{ d.exercice.annee_scolaire }}
          <span class="droite">
            <select [ngModel]="systeme()" (ngModelChange)="systeme.set($event); charger()">
              <option value="">Système conseillé ({{ d.systeme_conseille === 'SN' ? 'normal' : 'minimal de trésorerie' }})</option>
              <option value="SN">Système normal</option>
              <option value="SMT">Système minimal de trésorerie</option>
            </select>
            <p-button label="Générer et télécharger le dossier complet" icon="pi pi-download" size="small"
                      [loading]="generation()" (onClick)="generer()" />
          </span>
        </div>
        <div class="kpis">
          <div><span>Total bilan</span><b>{{ d.bilan.total_actif | number:'1.0-0' }}</b></div>
          <div><span>Chiffre d'affaires</span><b>{{ d.cr.chiffre_affaires | number:'1.0-0' }}</b></div>
          <div><span>Résultat net</span><b [class.ko]="d.cr.resultat < 0">{{ d.cr.resultat | number:'1.0-0' }}</b></div>
          <div><span>Trésorerie</span><b>{{ d.tft.tresorerie_bilan | number:'1.0-0' }}</b></div>
          <div><span>Statut</span><b [class.ok]="d.exercice.cloture">{{ d.exercice.cloture ? 'Définitif' : 'Provisoire' }}</b></div>
        </div>

        <div class="sous-titre">Contrôles de cohérence</div>
        @for (c of d.controles; track c.libelle) {
          <div class="ligne">
            <span>{{ c.libelle }}</span>
            <span [class.ok]="c.ok === true" [class.ko]="c.ok === false" [class.na]="c.ok === null">
              {{ c.ok === true ? '✓ Conforme' : c.ok === false ? '⚠ Écart' : 'À noter' }} — {{ c.detail }}</span>
          </div>
        }

        <div class="sous-titre">Documents</div>
        <div class="docs">
          @for (doc of d.documents; track doc.code) {
            <button type="button" class="doc" (click)="telechargerDocument(doc)">📄 {{ doc.titre }}</button>
            <app-bouton-imprimer [pdf]="pdfDocument" [arg]="doc" [avecLibelle]="false" [texte]="true" [contour]="false" />
          }
        </div>
      </div>

      <div class="carte">
        <div class="carte-titre">🗄️ Archives de l'exercice</div>
        @for (a of d.archives; track a.id) {
          <div class="ligne">
            <span><b>Version {{ a.version }}</b> · {{ a.statut === 'DEFINITIF' ? 'définitive' : 'provisoire' }} ·
              {{ a.systeme === 'SN' ? 'système normal' : 'SMT' }} · {{ a.cree_le | date:'dd/MM/yyyy HH:mm' }}
              @if (a.genere_par) { · {{ a.genere_par }} }<br>
              <small>Résultat {{ a.resume?.resultat | number:'1.0-0' }} · empreinte {{ a.empreinte.slice(0, 12) }}…
                {{ a.resume?.controles_ok ? '' : '· ⚠ contrôles en écart' }}</small></span>
            <span class="droite">
              <p-button icon="pi pi-download" size="small" [text]="true" (onClick)="telechargerArchive(a)" />
              @if (a.statut !== 'DEFINITIF') {
                <p-button icon="pi pi-trash" size="small" [text]="true" severity="danger" (onClick)="supprimer(a)" />
              }
            </span>
          </div>
        } @empty { <p class="aide">Aucun dossier généré pour cet exercice.</p> }
        <p class="aide">Chaque génération crée une nouvelle version, conservée telle qu'elle a été remise. Une version
          générée après la clôture est définitive et ne se supprime pas.</p>
      </div>
    } @else {
      <p class="aide">Chargement du dossier…</p>
    }
  `,
  styles: [`
    .carte { background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:14px 16px; margin-bottom:16px; }
    .carte-titre { display:flex; justify-content:space-between; align-items:center; font-weight:600; color:var(--text); margin-bottom:10px; gap:8px; flex-wrap:wrap; }
    .droite { display:flex; align-items:center; gap:8px; }
    select { padding:5px 8px; border:1px solid var(--border); border-radius:6px; background:var(--surface); color:var(--text); font-size:12px; }
    .kpis { display:grid; grid-template-columns:repeat(auto-fit, minmax(140px, 1fr)); gap:10px; margin-bottom:12px; }
    .kpis div { display:flex; flex-direction:column; background:var(--surface-hover); border-radius:8px; padding:8px 10px; }
    .kpis span { font-size:11px; color:var(--text-3); } .kpis b { font-size:15px; color:var(--text); font-variant-numeric:tabular-nums; }
    .sous-titre { font-size:12px; font-weight:600; color:var(--text-2); margin:12px 0 6px; }
    .ligne { display:flex; justify-content:space-between; align-items:center; gap:8px; padding:6px 2px; border-bottom:1px solid var(--border); font-size:12.5px; color:var(--text); }
    .ok { color:#059669 !important; } .ko { color:#dc2626 !important; } .na { color:#b45309; }
    .docs { display:grid; grid-template-columns:repeat(auto-fill, minmax(220px, 1fr)); gap:8px; }
    .doc { text-align:left; padding:8px 10px; border:1px solid var(--border); border-radius:8px; background:var(--surface); color:var(--text); cursor:pointer; font-size:12.5px; }
    .doc:hover { border-color:#1565c0; }
    .aide { font-size:12px; color:var(--text-3); margin:8px 0 0; }
  `],
})
export class EtafiDossierComponent {
  exercice = input<string>('');

  private api = inject(ApiService);
  private msg = inject(MessageService);

  dossier = signal<any>(null);
  systeme = signal('');
  generation = signal(false);

  constructor() { effect(() => { this.exercice(); this.charger(); }); }

  private params() { return { exercice: this.exercice() || undefined, systeme: this.systeme() || undefined }; }

  charger() {
    this.api.get<any>('/comptabilite/etafi/', this.params()).subscribe({
      next: d => this.dossier.set(d),
      error: e => this.msg.add({ severity: 'error', summary: 'ETAFI', detail: e?.error?.error || 'Chargement impossible' }),
    });
  }

  private enregistrer(blob: Blob, nom: string) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = nom; document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
  }

  /** Requête du PDF pour <app-bouton-imprimer>. */
  readonly pdfDocument = (doc: any) => this.api.getBlob(`/comptabilite/etafi/document/${doc.code}/`, this.params());

  telechargerDocument(doc: any) {
    this.api.getBlob(`/comptabilite/etafi/document/${doc.code}/`, this.params()).subscribe({
      next: b => window.open(URL.createObjectURL(b), '_blank'),
      error: () => this.msg.add({ severity: 'error', summary: 'Document indisponible' }),
    });
  }

  generer() {
    const d = this.dossier();
    this.generation.set(true);
    this.api.post<any>('/comptabilite/etafi/archiver/', { exercice_id: d.exercice.id, systeme: this.systeme() || undefined })
      .subscribe({
        next: a => { this.generation.set(false); this.charger(); this.telechargerArchive(a);
                     if (!a.resume?.controles_ok) this.msg.add({ severity: 'warn', summary: 'Dossier généré avec des écarts',
                       detail: 'Voir les contrôles de cohérence avant tout dépôt.', life: 8000 }); },
        error: () => { this.generation.set(false); this.msg.add({ severity: 'error', summary: 'Génération impossible' }); },
      });
  }

  telechargerArchive(a: any) {
    const ex = this.dossier()?.exercice?.annee_scolaire || '';
    this.api.getBlob(`/comptabilite/etafi/archives/${a.id}/`).subscribe(b =>
      this.enregistrer(b, `ETAFI_${ex}_v${a.version}_${(a.statut || '').toLowerCase()}.zip`));
  }

  supprimer(a: any) {
    if (!confirm(`Supprimer la version ${a.version} (provisoire) ?`)) return;
    this.api.delete(`/comptabilite/etafi/archives/${a.id}/`).subscribe({ next: () => this.charger() });
  }
}
