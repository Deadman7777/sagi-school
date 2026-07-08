import { Component, ChangeDetectionStrategy, inject, model, output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { TranslateModule } from '@ngx-translate/core';
import { DialogModule } from 'primeng/dialog';
import { ButtonModule } from 'primeng/button';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { ElevesService, RapportImport } from '../../../core/services/eleves.service';

/**
 * Wizard d'import d'élèves depuis Excel, en 3 étapes :
 * fichier (modèle + upload) → rapport (analyse, rien d'écrit) → fait.
 * L'import ne crée que les lignes OK ; il est rejouable sans doublonner.
 */
@Component({
  selector: 'app-import-eleves-dialog',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, TranslateModule, DialogModule, ButtonModule, TableModule, TagModule],
  template: `
    <p-dialog [header]="'eleves.import_titre' | translate" [visible]="visible()"
              (visibleChange)="visible.set($event)" [modal]="true"
              [style]="{ width: '760px', maxWidth: '95vw' }" (onHide)="reinitialiser()">

      <!-- ── Étape 1 : modèle + fichier ─────────────────────────────── -->
      @if (etape() === 'fichier') {
        <p class="intro">{{ 'eleves.import_intro' | translate }}</p>
        <div class="etapes">
          <div class="etape-bloc">
            <span class="num">1</span>
            <div>
              <p>{{ 'eleves.import_etape1' | translate }}</p>
              <p-button icon="pi pi-download" [label]="'eleves.import_template' | translate"
                        severity="secondary" size="small" [loading]="chargeTemplate()"
                        (onClick)="telechargerTemplate()" />
            </div>
          </div>
          <div class="etape-bloc">
            <span class="num">2</span>
            <div>
              <p>{{ 'eleves.import_etape2' | translate }}</p>
              <input type="file" accept=".xlsx" (change)="fichierChoisi($event)" />
              @if (fichier()) {
                <div class="fichier-nom">📄 {{ fichier()!.name }}</div>
              }
            </div>
          </div>
        </div>
        @if (erreur()) {
          <div class="erreur-globale">⚠️ {{ erreur() }}</div>
        }
      }

      <!-- ── Étape 2 : rapport d'analyse ────────────────────────────── -->
      @if (etape() === 'rapport' && rapport(); as r) {
        <p class="intro">{{ 'eleves.import_rapport' | translate }}</p>
        <div class="resume">
          <div class="res-item ok"><b>{{ r.resume.ok }}</b> {{ 'eleves.import_ok' | translate }}</div>
          <div class="res-item warn"><b>{{ r.resume.doublons }}</b> {{ 'eleves.import_doublons' | translate }}</div>
          <div class="res-item err"><b>{{ r.resume.erreurs }}</b> {{ 'eleves.import_erreurs' | translate }}</div>
        </div>
        <p-table [value]="r.lignes" [scrollable]="true" scrollHeight="320px" styleClass="p-datatable-sm">
          <ng-template pTemplate="header">
            <tr>
              <th style="width:70px">{{ 'eleves.import_ligne' | translate }}</th>
              <th>{{ 'eleves.nom' | translate }}</th>
              <th>{{ 'eleves.section' | translate }}</th>
              <th style="width:110px">{{ 'eleves.import_statut' | translate }}</th>
              <th>{{ 'eleves.import_details' | translate }}</th>
            </tr>
          </ng-template>
          <ng-template pTemplate="body" let-l>
            <tr>
              <td>{{ l.ligne }}</td>
              <td>{{ l.nom_complet || '—' }}</td>
              <td>{{ l.section || '—' }}</td>
              <td><p-tag [value]="l.statut" [severity]="severite(l.statut)" /></td>
              <td class="details">
                @for (e of l.erreurs; track e) { <div class="err-txt">{{ e }}</div> }
                @for (a of l.avertissements; track a) { <div class="warn-txt">{{ a }}</div> }
              </td>
            </tr>
          </ng-template>
        </p-table>
      }

      <!-- ── Étape 3 : terminé ──────────────────────────────────────── -->
      @if (etape() === 'fait') {
        <div class="fini">
          <div class="fini-ico">🎉</div>
          <p>{{ 'eleves.import_fait' | translate: { n: crees() } }}</p>
        </div>
      }

      <ng-template pTemplate="footer">
        @if (etape() === 'fichier') {
          <p-button [label]="'common.annuler' | translate" severity="secondary"
                    (onClick)="visible.set(false)" />
          <p-button [label]="'eleves.import_analyser' | translate" icon="pi pi-search"
                    severity="info" [disabled]="!fichier()" [loading]="occupe()"
                    (onClick)="analyser()" />
        }
        @if (etape() === 'rapport') {
          <p-button [label]="'eleves.import_retour' | translate" severity="secondary"
                    (onClick)="etape.set('fichier')" />
          <p-button [label]="('eleves.import_confirmer' | translate: { n: rapport()?.resume?.ok || 0 })"
                    icon="pi pi-check" severity="success"
                    [disabled]="!rapport()?.resume?.ok" [loading]="occupe()"
                    (onClick)="confirmer()" />
        }
        @if (etape() === 'fait') {
          <p-button [label]="'common.fermer' | translate" severity="success"
                    (onClick)="visible.set(false)" />
        }
      </ng-template>
    </p-dialog>
  `,
  styles: [`
    .intro { color: var(--text-color-secondary); margin: 0 0 16px; }
    .etapes { display: flex; flex-direction: column; gap: 18px; }
    .etape-bloc { display: flex; gap: 14px; align-items: flex-start; }
    .etape-bloc p { margin: 0 0 8px; font-weight: 600; }
    .num { flex: none; width: 30px; height: 30px; display: grid; place-items: center;
           border-radius: 50%; background: rgba(0,212,170,.15); color: #00b894; font-weight: 700; }
    .fichier-nom { margin-top: 8px; font-size: .9rem; color: var(--text-color-secondary); }
    .erreur-globale { margin-top: 16px; padding: 10px 14px; border-radius: 8px;
                      background: rgba(239,68,68,.1); border: 1px solid rgba(239,68,68,.35); }
    .resume { display: flex; gap: 12px; margin-bottom: 14px; }
    .res-item { flex: 1; text-align: center; padding: 10px; border-radius: 8px; font-size: .88rem; }
    .res-item b { display: block; font-size: 1.4rem; }
    .res-item.ok   { background: rgba(16,185,129,.12); color: #10b981; }
    .res-item.warn { background: rgba(245,158,11,.12); color: #f59e0b; }
    .res-item.err  { background: rgba(239,68,68,.12);  color: #ef4444; }
    .details { font-size: .82rem; }
    .err-txt  { color: #ef4444; }
    .warn-txt { color: #f59e0b; }
    .fini { text-align: center; padding: 30px 0; }
    .fini-ico { font-size: 3rem; margin-bottom: 10px; }
  `],
})
export class ImportElevesDialogComponent {
  visible = model(false);
  importe = output<number>();

  private eleves = inject(ElevesService);

  etape          = signal<'fichier' | 'rapport' | 'fait'>('fichier');
  fichier        = signal<File | null>(null);
  rapport        = signal<RapportImport | null>(null);
  crees          = signal(0);
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
    this.eleves.telechargerTemplateImport().subscribe({
      next: blob => {
        this.chargeTemplate.set(false);
        const url  = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'import_eleves_sagi.xlsx';
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      },
      error: () => { this.chargeTemplate.set(false); },
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
    this.occupe.set(true);
    this.erreur.set(null);
    this.eleves.importerExcel(f, false).subscribe({
      next: rapport => {
        this.occupe.set(false);
        this.rapport.set(rapport);
        this.etape.set('rapport');
      },
      error: err => {
        this.occupe.set(false);
        this.erreur.set(err?.error?.error || 'Fichier illisible.');
      },
    });
  }

  confirmer() {
    const f = this.fichier();
    if (!f) return;
    this.occupe.set(true);
    this.eleves.importerExcel(f, true).subscribe({
      next: res => {
        this.occupe.set(false);
        this.crees.set(res.crees || 0);
        this.etape.set('fait');
        this.importe.emit(res.crees || 0);
      },
      error: err => {
        this.occupe.set(false);
        this.etape.set('fichier');
        this.erreur.set(err?.error?.error || 'Import échoué.');
      },
    });
  }

  severite(statut: string): 'success' | 'warn' | 'danger' {
    return statut === 'OK' ? 'success' : statut === 'DOUBLON' ? 'warn' : 'danger';
  }
}
