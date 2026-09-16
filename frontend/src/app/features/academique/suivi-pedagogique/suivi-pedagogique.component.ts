import { ChangeDetectionStrategy, Component, inject, input, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { SelectModule } from 'primeng/select';
import { ButtonModule } from 'primeng/button';
import { TagModule } from 'primeng/tag';
import { MessageService } from 'primeng/api';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { AcademiqueService } from '../../../core/services/academique.service';

/**
 * Suivi pédagogique d'un élève : évolution de sa moyenne, matière par matière,
 * et lecture de ses points forts, faibles et à améliorer.
 *
 * Les chiffres viennent du même calcul que les bulletins (voir
 * backend/apps/academique/resultats.py) : la fiche ne peut pas contredire le
 * bulletin remis à la famille.
 */
@Component({
  selector: 'app-suivi-pedagogique',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, FormsModule, SelectModule, ButtonModule, TagModule, TranslateModule],
  template: `
    <div class="filters-bar">
      <p-select [options]="classes()" [(ngModel)]="classeId" optionLabel="nom" optionValue="id"
                [placeholder]="'academique.classe_filter' | translate" styleClass="filter-drop"
                [filter]="true" filterBy="nom" (onChange)="onClasseChange()" />
      <p-select [options]="eleves()" [(ngModel)]="eleveId" optionLabel="nom_complet" optionValue="id"
                [placeholder]="'pedago.choisir_eleve' | translate" styleClass="filter-drop"
                [filter]="true" filterBy="nom_complet" [disabled]="!classeId" (onChange)="charger()" />
      @if (hybride()) {
        <p-select [options]="programmes()" [(ngModel)]="programme" optionLabel="label" optionValue="value"
                  styleClass="filter-drop" (onChange)="charger()" />
      }
      <p-button icon="pi pi-file-pdf" severity="danger" [label]="'pedago.telecharger' | translate"
                [disabled]="!fiche()" [loading]="telechargement()" (onClick)="telecharger()" />
    </div>

    @if (!eleveId) {
      <div class="empty-msg">{{ 'pedago.aide' | translate }}</div>
    } @else if (chargement()) {
      <div class="empty-msg">{{ 'pedago.chargement' | translate }}</div>
    } @else if (fiche(); as f) {
      @if (!f.periodes.length) {
        <div class="empty-msg">{{ 'pedago.aucune_note' | translate }}</div>
      } @else {
        <div class="periodes">
          @for (p of f.periodes; track p.code; let last = $last) {
            <div class="periode-card" [class.derniere]="last">
              <div class="pc-lbl">{{ libellePeriode(p.code) }}</div>
              <div class="pc-moy">{{ p.moyenne }}</div>
              <div class="pc-sub">{{ 'pedago.rang' | translate }} {{ p.rang }} / {{ p.effectif }}
                · {{ 'pedago.moy_classe' | translate }} {{ p.moy_classe }}</div>
            </div>
          }
          @if (f.evolution_generale !== null) {
            <div class="periode-card">
              <div class="pc-lbl">{{ 'pedago.evolution' | translate }}</div>
              <div class="pc-moy" [class.hausse]="f.evolution_generale > 0" [class.baisse]="f.evolution_generale < 0">
                {{ f.evolution_generale > 0 ? '+' : '' }}{{ f.evolution_generale }}
              </div>
            </div>
          }
        </div>

        <div class="table-card table-scroll">
          <table class="suivi-table">
            <thead>
              <tr>
                <th>{{ 'pedago.matiere' | translate }}</th>
                <th>{{ 'pedago.coef' | translate }}</th>
                @for (p of f.periodes; track p.code) { <th>{{ libellePeriode(p.code) }}</th> }
                <th>{{ 'pedago.derniere' | translate }}</th>
                <th>{{ 'pedago.moy_classe' | translate }}</th>
                <th>{{ 'pedago.evolution' | translate }}</th>
                <th>{{ 'pedago.lecture' | translate }}</th>
              </tr>
            </thead>
            <tbody>
              @for (m of f.matieres; track m.matiere_id) {
                <tr>
                  <td class="bold">{{ m.nom }}</td>
                  <td class="centre">{{ m.coefficient }}</td>
                  @for (p of f.periodes; track p.code) {
                    <td class="centre mono">{{ m.par_periode[p.code] ?? '—' }}</td>
                  }
                  <td class="centre mono bold">{{ m.derniere }}</td>
                  <td class="centre mono">{{ m.moy_classe ?? '—' }}</td>
                  <td class="centre mono" [class.hausse]="m.evolution > 0" [class.baisse]="m.evolution < 0">
                    {{ m.evolution === null ? '—' : (m.evolution > 0 ? '+' : '') + m.evolution }}
                  </td>
                  <td>
                    <p-tag [value]="('pedago.statut_' + m.statut) | translate"
                           [severity]="m.statut === 'FORT' ? 'success' : m.statut === 'FAIBLE' ? 'danger' : 'secondary'" />
                    @for (r of m.a_ameliorer; track r) {
                      <p-tag [value]="('pedago.raison_' + r) | translate" severity="warn" styleClass="ml-tag" />
                    }
                    @if (m.en_progres) {
                      <p-tag [value]="'pedago.raison_PROGRES' | translate" severity="info" styleClass="ml-tag" />
                    }
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>

        <div class="lecture-grid">
          <div class="lecture-card fort">
            <div class="lc-titre">{{ 'pedago.points_forts' | translate }}</div>
            <div>{{ f.points_forts.length ? f.points_forts.join(', ') : ('pedago.aucun' | translate) }}</div>
          </div>
          <div class="lecture-card faible">
            <div class="lc-titre">{{ 'pedago.points_faibles' | translate }}</div>
            <div>{{ f.points_faibles.length ? f.points_faibles.join(', ') : ('pedago.aucun' | translate) }}</div>
          </div>
          <div class="lecture-card ameliorer">
            <div class="lc-titre">{{ 'pedago.a_ameliorer' | translate }}</div>
            <div>{{ f.a_ameliorer.length ? nomsAmeliorer(f) : ('pedago.aucun' | translate) }}</div>
          </div>
        </div>

        <div class="table-card recommandations">
          <div class="lc-titre">{{ 'pedago.recommandations' | translate }}</div>
          <ul>
            @for (r of recommandations(f); track r) { <li>{{ r }}</li> }
          </ul>
        </div>
      }
    }
  `,
  styles: [`
    .filters-bar { display:flex; gap:10px; flex-wrap:wrap; align-items:center; margin-bottom:16px; }
    .empty-msg { padding:30px; text-align:center; color:var(--text-3); font-size:13px; }
    .periodes { display:grid; grid-template-columns:repeat(auto-fill, minmax(170px, 1fr)); gap:10px; margin-bottom:14px; }
    .periode-card { background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:12px; }
    .periode-card.derniere { border-top:3px solid #00d4aa; }
    .pc-lbl { font-size:11px; color:var(--text-3); text-transform:uppercase; }
    .pc-moy { font-size:22px; font-weight:700; color:var(--text); font-family:monospace; }
    .pc-sub { font-size:11px; color:var(--text-2); }
    .table-card { background:var(--surface); border:1px solid var(--border); border-radius:10px; margin-bottom:14px; }
    .table-scroll { overflow-x:auto; }
    .suivi-table { width:100%; border-collapse:collapse; font-size:12px; }
    .suivi-table th { text-align:left; padding:8px; color:var(--text-3); font-size:11px; border-bottom:1px solid var(--border); white-space:nowrap; }
    .suivi-table td { padding:7px 8px; border-bottom:1px solid var(--border); color:var(--text); }
    .centre { text-align:center; }
    .mono { font-family:monospace; }
    .bold { font-weight:600; }
    .hausse { color:#10b981; }
    .baisse { color:#ef4444; }
    :host ::ng-deep .ml-tag { margin-left:4px; }
    .lecture-grid { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:10px; margin-bottom:14px; }
    @media (max-width:700px) { .lecture-grid { grid-template-columns:1fr; } }
    .lecture-card { background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:12px; font-size:13px; color:var(--text); }
    .lecture-card.fort { border-top:3px solid #10b981; }
    .lecture-card.faible { border-top:3px solid #ef4444; }
    .lecture-card.ameliorer { border-top:3px solid #f59e0b; }
    .lc-titre { font-size:11px; color:var(--text-3); text-transform:uppercase; margin-bottom:6px; font-weight:600; }
    .recommandations { padding:12px 16px; }
    .recommandations ul { margin:0; padding-inline-start:18px; font-size:13px; color:var(--text); }
    .recommandations li { margin:3px 0; }
  `],
})
export class SuiviPedagogiqueComponent {
  classes = input<any[]>([]);
  hybride = input(false);
  /** Mot du découpage de l'année (« Trimestre », « Semestre »…). */
  periodeLabel = input('Trimestre');

  private acad = inject(AcademiqueService);
  private translate = inject(TranslateService);
  private msg = inject(MessageService);

  classeId = '';
  eleveId = '';
  programme = 'FR';
  eleves = signal<any[]>([]);
  fiche = signal<any>(null);
  chargement = signal(false);
  telechargement = signal(false);

  programmes() {
    return [
      { label: this.translate.instant('academique.programme_FR'), value: 'FR' },
      { label: this.translate.instant('academique.programme_AR'), value: 'AR' },
    ];
  }

  onClasseChange() {
    this.eleveId = '';
    this.fiche.set(null);
    this.acad.getElevesPourClasse(this.classeId).subscribe({
      next: e => this.eleves.set(e || []),
      error: () => this.eleves.set([]),
    });
  }

  charger() {
    if (!this.eleveId) return;
    this.chargement.set(true);
    this.acad.getFichePedagogique(this.eleveId, this.hybride() ? this.programme : null).subscribe({
      next: f => { this.fiche.set(f); this.chargement.set(false); },
      error: err => {
        this.fiche.set(null);
        this.chargement.set(false);
        this.msg.add({ severity: 'error', summary: this.translate.instant('common.erreur'),
                       detail: err?.error?.error || this.translate.instant('pedago.erreur') });
      },
    });
  }

  telecharger() {
    const f = this.fiche();
    if (!f) return;
    this.telechargement.set(true);
    this.acad.getFichePedagogiquePdf(this.eleveId, this.hybride() ? this.programme : null).subscribe({
      next: blob => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `fiche_pedagogique_${(f.eleve?.nom_complet || 'eleve').replace(/ /g, '_')}_${f.programme}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
        this.telechargement.set(false);
      },
      error: () => {
        this.telechargement.set(false);
        this.msg.add({ severity: 'error', summary: this.translate.instant('common.erreur'),
                       detail: this.translate.instant('pedago.erreur') });
      },
    });
  }

  libellePeriode(code: string): string {
    const n = (code || '').replace(/\D/g, '');
    return n ? `${this.periodeLabel()} ${n}` : code;
  }

  nomsAmeliorer(f: any): string {
    return f.a_ameliorer.map((a: any) => a.nom).join(', ');
  }

  /** Les recommandations sont décidées par le serveur (mêmes que la fiche PDF),
   *  l'écran ne fait que les rédiger dans la langue de l'utilisateur. */
  recommandations(f: any): string[] {
    return (f.recommandations || []).map((r: any) => this.translate.instant(`pedago.rec_${r.code}`, {
      noms: (r.noms || []).join(', '),
      n: r.code === 'hausse_gen' ? `+${r.n}` : r.n,
    }));
  }
}
