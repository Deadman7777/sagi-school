import { ChangeDetectionStrategy, Component, inject, model, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { CheckboxModule } from 'primeng/checkbox';
import { TagModule } from 'primeng/tag';
import { TooltipModule } from 'primeng/tooltip';
import { ConfirmationService, MessageService } from 'primeng/api';
import { TranslateModule, TranslateService } from '@ngx-translate/core';

import { CommercialService, DocumentBibliotheque } from '../../core/services/commercial.service';

/**
 * La bibliothèque commerciale : brochures, catalogue des offres et tarifs,
 * plaquettes. Déposés ici (PDF), ils sont proposés en pièces jointes des
 * propositions ; « Joint par défaut » les coche d'office. Une nouvelle
 * brochure remplace l'ancienne sans nouvelle version du logiciel.
 */
@Component({
  selector: 'app-bibliotheque-commerciale',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, FormsModule, ButtonModule, DialogModule, InputTextModule, SelectModule,
            CheckboxModule, TagModule, TooltipModule, TranslateModule],
  template: `
    <p-dialog [visible]="visible()" (visibleChange)="visible.set($event)"
              (onShow)="charger()" [modal]="true" appendTo="body" [style]="{width:'760px'}"
              [breakpoints]="{'800px':'96vw'}" [header]="'commercial.bibliotheque' | translate"
              [draggable]="false">
      <p class="aide">{{ 'commercial.aide_bibliotheque' | translate }}</p>

      @if (!documents().length) {
        <div class="vide">{{ 'commercial.bibliotheque_vide' | translate }}</div>
      }
      @for (d of documents(); track d.id) {
      <div class="ligne" [class.inactif]="!d.actif">
        <span class="icone">{{ d.categorie === 'CATALOGUE' ? '📘' : d.categorie === 'BROCHURE' ? '📰' : '📄' }}</span>
        <div class="gauche">
          <input pInputText class="titre" [ngModel]="d.titre" (change)="renommer(d, $any($event.target).value)" />
          <span class="discret">{{ d.categorie_libelle }} · {{ d.nom_fichier }} · {{ taille(d.taille) }}</span>
        </div>
        <label class="case" [pTooltip]="'commercial.joint_defaut_aide' | translate">
          <p-checkbox [ngModel]="d.joindre_par_defaut" [binary]="true" [inputId]="'jd-' + d.id"
                      (onChange)="basculer(d, 'joindre_par_defaut', $event.checked)" />
          <span>{{ 'commercial.joint_defaut' | translate }}</span>
        </label>
        @if (!d.actif) { <p-tag [value]="'commercial.retire' | translate" severity="secondary" /> }
        <p-button icon="pi pi-eye" [text]="true" size="small" (onClick)="voir(d)"
                  [pTooltip]="'commercial.ouvrir' | translate" />
        @if (d.actif) {
          <p-button icon="pi pi-trash" [text]="true" size="small" severity="danger" (onClick)="supprimer(d)"
                    [pTooltip]="'common.supprimer' | translate" />
        } @else {
          <p-button icon="pi pi-replay" [text]="true" size="small" (onClick)="basculer(d, 'actif', true)"
                    [pTooltip]="'commercial.remettre' | translate" />
        }
      </div>
      }

      <div class="bloc-titre">{{ 'commercial.ajouter_document' | translate }}</div>
      <div class="ajout">
        <input pInputText [(ngModel)]="nouveauTitre" [placeholder]="'commercial.titre_document' | translate" />
        <p-select [(ngModel)]="nouvelleCategorie" [options]="categories" optionLabel="label"
                  optionValue="value" appendTo="body" />
        <input #fichier type="file" accept="application/pdf" hidden (change)="deposer(fichier)" />
        <p-button [label]="'commercial.choisir_pdf' | translate" icon="pi pi-upload" [loading]="occupe()"
                  (onClick)="fichier.click()" />
      </div>
    </p-dialog>
  `,
  styles: [`
    .aide { font-size:12px; color:var(--text-3); margin:0 0 10px; }
    .vide { font-size:12.5px; color:var(--text-3); padding:8px 0; }
    .ligne { display:flex; align-items:center; gap:10px; padding:7px 0; border-bottom:1px solid var(--surface-2); flex-wrap:wrap; }
    .ligne.inactif { opacity:.55; }
    .icone { font-size:20px; }
    .gauche { display:flex; flex-direction:column; flex:1; min-width:200px; gap:2px; }
    .titre { font-weight:600; padding:4px 6px; }
    .discret { color:var(--text-3); font-size:11.5px; overflow-wrap:anywhere; }
    .case { display:flex; align-items:center; gap:6px; font-size:12.5px; cursor:pointer; }
    .bloc-titre { font-weight:700; font-size:12.5px; margin:16px 0 8px; padding-bottom:4px;
                  border-bottom:2px solid #b98a2e; }
    .ajout { display:flex; gap:8px; flex-wrap:wrap; align-items:center; }
    .ajout input { flex:1; min-width:200px; }
  `],
})
export class BibliothequeCommercialeComponent {
  private service = inject(CommercialService);
  private msg = inject(MessageService);
  private confirm = inject(ConfirmationService);
  private translate = inject(TranslateService);

  visible = model(false);
  documents = signal<DocumentBibliotheque[]>([]);
  occupe = signal(false);
  nouveauTitre = '';
  nouvelleCategorie = 'BROCHURE';
  categories = [
    { label: 'Brochure', value: 'BROCHURE' },
    { label: 'Catalogue des offres et tarifs', value: 'CATALOGUE' },
    { label: 'Autre document', value: 'AUTRE' },
  ];

  charger() {
    this.service.documents().subscribe({ next: d => this.documents.set(d) });
  }

  taille(octets: number): string {
    return octets > 1048576 ? `${(octets / 1048576).toFixed(1)} Mo` : `${Math.max(1, Math.round(octets / 1024))} Ko`;
  }

  private erreur(err: any) {
    this.occupe.set(false);
    this.msg.add({ severity: 'error', summary: this.translate.instant('common.erreur'),
                   detail: err?.error?.error || this.translate.instant('commercial.erreur') });
  }

  private remplacer(d: DocumentBibliotheque) {
    this.documents.update(l => l.map(x => x.id === d.id ? d : x));
  }

  deposer(champ: HTMLInputElement) {
    const fichier = champ.files?.[0];
    champ.value = '';
    if (!fichier) return;
    if (fichier.type !== 'application/pdf') {
      this.erreur({ error: { error: this.translate.instant('commercial.pdf_seulement') } });
      return;
    }
    this.occupe.set(true);
    const lecteur = new FileReader();
    lecteur.onload = () => {
      this.service.deposer({
        titre: this.nouveauTitre.trim() || fichier.name.replace(/\.pdf$/i, ''),
        categorie: this.nouvelleCategorie, nom_fichier: fichier.name,
        contenu: String(lecteur.result), joindre_par_defaut: true,
      }).subscribe({
        next: d => {
          this.occupe.set(false);
          this.nouveauTitre = '';
          this.documents.update(l => [...l, d]);
          this.msg.add({ severity: 'success', summary: this.translate.instant('commercial.document_ajoute') });
        },
        error: e => this.erreur(e),
      });
    };
    lecteur.onerror = () => this.erreur({});
    lecteur.readAsDataURL(fichier);
  }

  renommer(d: DocumentBibliotheque, titre: string) {
    if (!titre.trim() || titre === d.titre) return;
    this.service.modifierDocument(d.id, { titre }).subscribe({ next: x => this.remplacer(x), error: e => this.erreur(e) });
  }

  basculer(d: DocumentBibliotheque, champ: 'joindre_par_defaut' | 'actif', valeur: boolean) {
    this.service.modifierDocument(d.id, { [champ]: valeur }).subscribe({
      next: x => this.remplacer(x), error: e => this.erreur(e),
    });
  }

  voir(d: DocumentBibliotheque) {
    this.service.fichier(d.id).subscribe({
      next: blob => {
        const url = URL.createObjectURL(blob);
        window.open(url, '_blank');
        setTimeout(() => URL.revokeObjectURL(url), 60_000);
      },
      error: e => this.erreur(e),
    });
  }

  supprimer(d: DocumentBibliotheque) {
    this.confirm.confirm({
      message: this.translate.instant('commercial.confirmer_suppression_doc', { titre: d.titre }),
      header: this.translate.instant('common.supprimer'),
      accept: () => this.service.supprimerDocument(d.id).subscribe({
        // Déjà remis à un client : retiré des listes mais conservé (réponse = le document).
        next: r => r ? this.remplacer(r) : this.documents.update(l => l.filter(x => x.id !== d.id)),
        error: e => this.erreur(e),
      }),
    });
  }
}
