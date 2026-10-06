import { ChangeDetectionStrategy, Component, effect, inject, input, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { ButtonModule } from 'primeng/button';
import { ApiService } from '../../../core/services/api.service';

interface LigneEtat {
  type: 'groupe' | 'sous_total'; code: string; libelle: string;
  nb: number; montant: number; anterieur: number; annee: number;
}

interface EtatImpayes {
  exercice: string; date: string; nb_eleves: number; nb_a_jour: number;
  lignes: LigneEtat[];
  total: { nb: number; montant: number; anterieur: number; annee: number };
}

/**
 * État des impayés par statut — pour le comité de gestion. Critique, urgent
 * (sous-total prioritaires), puis attention en retard / mois en cours
 * (sous-total attention), total général ; téléchargeable en PDF et Excel avec
 * la liste des élèves de chaque statut. Mêmes chiffres que la colonne
 * « Alerte » de la liste : même échéancier.
 */
@Component({
  selector: 'app-etat-impayes',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DecimalPipe, ButtonModule],
  template: `
<div class="ei">
  <button type="button" class="ei-toggle" [attr.aria-expanded]="ouvert()" (click)="basculer()">
    {{ ouvert() ? '▾' : '▸' }} 📊 État des impayés par statut (comité de gestion)
  </button>
  @if (ouvert()) {
    <div class="ei-corps">
      @if (erreur()) { <div class="ei-erreur" role="alert">{{ erreur() }}</div> }
      @if (etat(); as e) {
        <div class="ei-tete">
          <span>Arrêté au {{ e.date.split('-').reverse().join('/') }} · {{ e.nb_eleves }} élèves présents,
            {{ e.nb_a_jour }} sans impayé exigible</span>
          <span class="ei-actions">
            <p-button label="PDF" icon="pi pi-file-pdf" size="small" severity="danger" [outlined]="true"
                      [loading]="telechargement() === 'pdf'" (onClick)="telecharger('pdf')" />
            <p-button label="Excel" icon="pi pi-file-excel" size="small" severity="success" [outlined]="true"
                      [loading]="telechargement() === 'xlsx'" (onClick)="telecharger('xlsx')" />
          </span>
        </div>
        <div class="table-wrap">
          <table class="tbl">
            <thead>
              <tr>
                <th scope="col">Statut</th><th scope="col" class="tr">Élèves</th>
                <th scope="col" class="tr">Années antérieures</th>
                <th scope="col" class="tr">Année en cours (échu)</th>
                <th scope="col" class="tr">Total exigible</th>
              </tr>
            </thead>
            <tbody>
              @for (l of e.lignes; track l.code) {
                <tr [class.sous-total]="l.type === 'sous_total'">
                  <td>
                    @if (l.type === 'groupe') { <span class="pastille" [class]="'pastille p-' + l.code"></span> }
                    {{ l.libelle }}
                  </td>
                  <td class="tr">{{ l.nb }}</td>
                  <td class="tr">{{ l.anterieur | number:'1.0-0' }}</td>
                  <td class="tr">{{ l.annee | number:'1.0-0' }}</td>
                  <td class="tr gras">{{ l.montant | number:'1.0-0' }}</td>
                </tr>
              }
            </tbody>
            <tfoot>
              <tr>
                <td>Total général</td><td class="tr">{{ e.total.nb }}</td>
                <td class="tr">{{ e.total.anterieur | number:'1.0-0' }}</td>
                <td class="tr">{{ e.total.annee | number:'1.0-0' }}</td>
                <td class="tr">{{ e.total.montant | number:'1.0-0' }}</td>
              </tr>
            </tfoot>
          </table>
        </div>
        <p class="ei-note">
          « Mois en cours seulement » : la mensualité du mois vient d'échoir — au début de chaque mois,
          les élèves à jour y passent, c'est normal. Le PDF et l'Excel donnent la liste des élèves
          de chaque statut, avec le téléphone à appeler, du plus gros montant au plus petit.
        </p>
      } @else if (!erreur()) {
        <div class="ei-note">Calcul en cours…</div>
      }
    </div>
  }
</div>
`,
  styles: [`
    .ei { margin:8px 0; }
    .ei-toggle { background:none; border:none; color:var(--text-2); font-size:13px; cursor:pointer; padding:4px 0; font-family:inherit; font-weight:600; }
    .ei-toggle:focus-visible { outline:2px solid #00d4aa; outline-offset:2px; }
    .ei-corps { background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:12px; display:flex; flex-direction:column; gap:10px; }
    .ei-tete { display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; font-size:12px; color:var(--text-3); }
    .ei-actions { display:flex; gap:6px; }
    .ei-erreur { color:#dc2626; font-size:13px; }
    .table-wrap { overflow-x:auto; }
    .tbl { width:100%; border-collapse:collapse; font-size:13px; }
    .tbl th { background:var(--surface-2); color:var(--text-3); font-size:11px; text-transform:uppercase; text-align:left; padding:7px 10px; white-space:nowrap; }
    .tbl th.tr { text-align:right; }
    .tbl td { padding:6px 10px; border-top:1px solid var(--border); color:var(--text-2); font-variant-numeric:tabular-nums; }
    .tbl tr.sous-total td { font-weight:700; color:var(--text); background:var(--surface-2); }
    .tbl tfoot td { font-weight:700; color:var(--text); background:rgba(0,212,170,.12); }
    .tr { text-align:right; }
    .gras { font-weight:600; color:var(--text); }
    .pastille { display:inline-block; width:9px; height:9px; border-radius:50%; margin-right:6px; vertical-align:middle; }
    .p-CRITIQUE { background:#dc2626; } .p-URGENT { background:#ea580c; }
    .p-ATTENTION_RETARD { background:#ca8a04; } .p-ATTENTION_MOIS { background:#facc15; }
    .ei-note { margin:0; font-size:12px; color:var(--text-3); line-height:1.5; }
  `],
})
export class EtatImpayesComponent {
  private api = inject(ApiService);

  /** Exercice affiché par la liste (vide = l'exercice actif). */
  exercice = input<string>('');

  ouvert = signal(false);
  etat = signal<EtatImpayes | null>(null);
  erreur = signal('');
  telechargement = signal<'' | 'pdf' | 'xlsx'>('');

  constructor() {
    // Changer d'exercice dans la liste recharge l'état s'il est ouvert.
    effect(() => {
      this.exercice();
      if (this.ouvert()) this.charger();
    });
  }

  private params(extra: Record<string, string> = {}): Record<string, string> {
    const ex = this.exercice();
    return ex ? { exercice: ex, ...extra } : extra;
  }

  basculer() {
    this.ouvert.update(v => !v);
  }

  charger() {
    this.etat.set(null);
    this.erreur.set('');
    this.api.get<EtatImpayes>('/eleves/etat-impayes/', this.params()).subscribe({
      next: e => this.etat.set(e),
      error: err => this.erreur.set(err?.error?.error || "Impossible de calculer l'état des impayés."),
    });
  }

  telecharger(format: 'pdf' | 'xlsx') {
    const e = this.etat();
    this.telechargement.set(format);
    this.api.getBlob('/eleves/etat-impayes/', this.params({ export: format })).subscribe({
      next: blob => {
        const url = URL.createObjectURL(blob);
        const lien = document.createElement('a');
        lien.href = url;
        lien.download = `etat_impayes_${e?.exercice ?? ''}_${e?.date ?? ''}.${format}`;
        document.body.appendChild(lien);
        lien.click();
        document.body.removeChild(lien);
        URL.revokeObjectURL(url);
        this.telechargement.set('');
      },
      error: () => { this.telechargement.set(''); this.erreur.set('Téléchargement impossible.'); },
    });
  }
}
