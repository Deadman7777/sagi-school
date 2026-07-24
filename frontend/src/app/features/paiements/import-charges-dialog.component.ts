import { ChangeDetectionStrategy, Component, inject, model, output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DialogModule } from 'primeng/dialog';
import { ButtonModule } from 'primeng/button';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { ComptabiliteService } from '../../core/services/comptabilite.service';

interface LigneCharge {
  ligne: number; date: string; libelle: string; no_compte: string;
  compte_suggere: boolean; montant: number; statut: string; erreurs: string[];
}
interface RapportCharges {
  resume: { total_lignes: number; ok: number; erreurs: number; montant_total: number };
  lignes: LigneCharge[];
}

/**
 * Import Excel des charges — modèle + upload → aperçu ligne par ligne → création.
 * Même flux que l'import des élèves, appliqué aux dépenses.
 */
@Component({
  selector: 'app-import-charges-dialog',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, DialogModule, ButtonModule, TableModule, TagModule],
  template: `
    <p-dialog header="📥 Importer des charges (Excel)" [(visible)]="visible"
              [modal]="true" [style]="{width:'760px'}" [draggable]="false" (onHide)="reinitialiser()">

      @if (etape() === 'fichier') {
        <div class="imp-intro">
          <p>Téléchargez le modèle, remplissez-le (Date, Libellé, Compte optionnel, Montant, Réglé via),
             puis importez-le. Le compte de charge est <strong>suggéré automatiquement</strong> d'après le libellé.</p>
          <p-button icon="pi pi-download" label="Télécharger le modèle" severity="secondary"
                    [outlined]="true" [loading]="chargeTemplate()" (onClick)="telechargerTemplate()" />
          <div class="imp-file">
            <input type="file" accept=".xlsx" (change)="fichierChoisi($event)" />
            @if (fichier()) { <div class="imp-nom">📄 {{ fichier()!.name }}</div> }
          </div>
          @if (erreur()) { <div class="imp-err">⚠️ {{ erreur() }}</div> }
        </div>
      }

      @if (etape() === 'rapport' && rapport(); as r) {
        <div class="imp-resume">
          <span class="ok">✓ {{ r.resume.ok }} valides</span>
          @if (r.resume.erreurs) { <span class="err">✕ {{ r.resume.erreurs }} en erreur</span> }
          <span class="tot">Total : {{ r.resume.montant_total | number:'1.0-0' }} FCFA</span>
        </div>
        <p-table [value]="r.lignes" [scrollable]="true" scrollHeight="340px" styleClass="p-datatable-sm">
          <ng-template pTemplate="header">
            <tr><th>#</th><th>Date</th><th>Libellé</th><th>Compte</th><th style="text-align:right">Montant</th><th>Statut</th></tr>
          </ng-template>
          <ng-template pTemplate="body" let-l>
            <tr>
              <td>{{ l.ligne }}</td>
              <td>{{ l.date }}</td>
              <td>{{ l.libelle }}</td>
              <td class="mono">{{ l.no_compte }}<span *ngIf="l.compte_suggere" class="sugg" title="Suggéré d'après le libellé">🪄</span></td>
              <td class="mono" style="text-align:right">{{ l.montant | number:'1.0-0' }}</td>
              <td>
                <p-tag [value]="l.statut" [severity]="l.statut === 'OK' ? 'success' : 'danger'" />
                @if (l.erreurs.length) { <div class="ligne-err">{{ l.erreurs.join(', ') }}</div> }
              </td>
            </tr>
          </ng-template>
        </p-table>
      }

      @if (etape() === 'fait') {
        <div class="imp-fait">
          <div class="big">✅</div>
          <p><strong>{{ crees() }}</strong> charge(s) créée(s) — {{ montantTotal() | number:'1.0-0' }} FCFA.</p>
        </div>
      }

      <ng-template pTemplate="footer">
        @if (etape() === 'fichier') {
          <p-button label="Fermer" severity="secondary" (onClick)="visible.set(false)" />
          <p-button label="Analyser" icon="pi pi-search" severity="info"
                    [disabled]="!fichier()" [loading]="occupe()" (onClick)="analyser()" />
        }
        @if (etape() === 'rapport') {
          <p-button label="← Retour" severity="secondary" (onClick)="etape.set('fichier')" />
          <p-button [label]="'Créer ' + (rapport()?.resume?.ok || 0) + ' charge(s)'" icon="pi pi-check"
                    severity="success" [disabled]="!(rapport()?.resume?.ok)" [loading]="occupe()"
                    (onClick)="confirmer()" />
        }
        @if (etape() === 'fait') {
          <p-button label="Terminer" severity="success" (onClick)="visible.set(false)" />
        }
      </ng-template>
    </p-dialog>
  `,
  styles: [`
    .imp-intro p { font-size:.9rem; color:var(--text-2); margin-bottom:12px; }
    .imp-file { margin-top:14px; }
    .imp-nom { margin-top:8px; font-size:.9rem; color:var(--text); }
    .imp-err { margin-top:10px; color:#f87171; font-size:.85rem; }
    .imp-resume { display:flex; gap:16px; margin-bottom:10px; font-size:.85rem; }
    .imp-resume .ok { color:#10b981; font-weight:600; }
    .imp-resume .err { color:#ef4444; font-weight:600; }
    .imp-resume .tot { color:var(--text); margin-left:auto; font-family:monospace; }
    .mono { font-family:monospace; }
    .sugg { margin-left:4px; }
    .ligne-err { font-size:10px; color:#f87171; margin-top:2px; }
    .imp-fait { text-align:center; padding:20px; }
    .imp-fait .big { font-size:2.4rem; }
  `],
})
export class ImportChargesDialogComponent {
  visible  = model(false);
  importe  = output<number>();

  private compta = inject(ComptabiliteService);

  etape          = signal<'fichier' | 'rapport' | 'fait'>('fichier');
  fichier        = signal<File | null>(null);
  rapport        = signal<RapportCharges | null>(null);
  crees          = signal(0);
  montantTotal   = signal(0);
  occupe         = signal(false);
  chargeTemplate = signal(false);
  erreur         = signal<string | null>(null);

  reinitialiser() {
    this.etape.set('fichier');
    this.fichier.set(null);
    this.rapport.set(null);
    this.erreur.set(null);
  }

  telechargerTemplate() {
    this.chargeTemplate.set(true);
    this.compta.telechargerTemplateCharges().subscribe({
      next: blob => {
        this.chargeTemplate.set(false);
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url; link.download = 'import_charges_sagi.xlsx';
        document.body.appendChild(link); link.click(); document.body.removeChild(link);
        URL.revokeObjectURL(url);
      },
      error: () => this.chargeTemplate.set(false),
    });
  }

  fichierChoisi(event: Event) {
    const input = event.target as HTMLInputElement;
    this.fichier.set(input.files?.[0] ?? null);
    this.erreur.set(null);
  }

  analyser() {
    const f = this.fichier();
    if (!f) return;
    this.occupe.set(true); this.erreur.set(null);
    this.compta.importerChargesExcel(f, false).subscribe({
      next: r => { this.occupe.set(false); this.rapport.set(r); this.etape.set('rapport'); },
      error: err => { this.occupe.set(false); this.erreur.set(err?.error?.error || 'Fichier illisible.'); },
    });
  }

  confirmer() {
    const f = this.fichier();
    if (!f) return;
    this.occupe.set(true);
    this.compta.importerChargesExcel(f, true).subscribe({
      next: res => {
        this.occupe.set(false);
        this.crees.set(res.crees || 0);
        this.montantTotal.set(res.montant_total || 0);
        this.etape.set('fait');
        this.importe.emit(res.crees || 0);
      },
      error: err => {
        this.occupe.set(false); this.etape.set('fichier');
        this.erreur.set(err?.error?.error || 'Import échoué.');
      },
    });
  }
}
