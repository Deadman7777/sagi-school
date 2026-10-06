import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';
import { ButtonModule } from 'primeng/button';
import { TooltipModule } from 'primeng/tooltip';
import { MenuItem, MessageService } from 'primeng/api';
import { MenuModule } from 'primeng/menu';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { Observable, firstValueFrom } from 'rxjs';

import { ImpressionService, TypeImpression } from '../core/services/impression.service';

/**
 * Bouton « Imprimer » d'un document PDF, à poser à côté de « Télécharger ».
 *
 * `pdf` est une fonction STABLE qui fabrique la requête du document, appelée
 * avec `arg` au clic seulement. Pas `[pdf]="pdfRecu(r)"` : une nouvelle
 * requête à chaque passage de l'affichage déclenche NG0100 en développement. L'impression passe par ImpressionService : directe sur l'imprimante
 * du poste dans l'app installée, fenêtre d'impression du navigateur en cloud.
 * Les messages vont dans le <p-toast> de l'écran hôte (son MessageService).
 *
 *   readonly pdfRecu = (r: Recu) => this.service.pdfRecu(r.id);   // dans le composant hôte
 *   <app-bouton-imprimer [pdf]="pdfRecu" [arg]="r" />
 *   <app-bouton-imprimer [pdf]="pdfEtat" type="ticket" [texte]="true" />
 *
 * Plusieurs documents au même endroit : `choix` (tableau stable, mémorisé par
 * l'hôte) affiche un menu « Imprimer ▾ ».
 */
@Component({
  selector: 'app-bouton-imprimer',
  imports: [ButtonModule, MenuModule, TooltipModule, TranslateModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (choix().length) {
      <p-button icon="pi pi-print" [label]="('common.imprimer' | translate) + ' ▾'"
                [outlined]="contour()" [size]="taille()" [severity]="severite()"
                [loading]="enCours()" [disabled]="disabled()"
                (onClick)="menu.toggle($event)" />
      <p-menu #menu [model]="elementsMenu()" [popup]="true" appendTo="body" />
    } @else {
    <p-button icon="pi pi-print" [label]="avecLibelle() ? ('common.imprimer' | translate) : ''"
              [text]="texte()" [outlined]="contour()" [size]="taille()" [severity]="severite()"
              [loading]="enCours()" [disabled]="disabled()"
              [pTooltip]="avecLibelle() ? '' : ('common.imprimer' | translate)"
              [ariaLabel]="'common.imprimer' | translate"
              (onClick)="imprimer()" />
    }
  `,
})
export class BoutonImprimerComponent {
  private impression = inject(ImpressionService);
  private translate = inject(TranslateService);
  private msg = inject(MessageService, { optional: true });

  pdf = input<((arg?: any) => Observable<Blob>) | null>(null);
  arg = input<unknown>(undefined);
  choix = input<{ libelle: string; pdf: Observable<Blob> }[]>([]);
  type = input<TypeImpression>('document');
  avecLibelle = input(true);
  texte = input(false);
  contour = input(true);
  taille = input<'small' | 'large' | undefined>('small');
  severite = input<'secondary' | 'success' | 'info' | 'help' | 'primary' | undefined>('secondary');
  disabled = input(false);

  enCours = signal(false);

  elementsMenu = computed<MenuItem[]>(() =>
    this.choix().map(c => ({ label: c.libelle, command: () => this.imprimer(c.pdf) })));

  async imprimer(source?: Observable<Blob>) {
    const fabrique = this.pdf();
    source ??= fabrique ? fabrique(this.arg()) : undefined;
    if (this.enCours() || !source) return;
    this.enCours.set(true);
    try {
      const blob = await firstValueFrom(source);
      const res = await this.impression.imprimer(blob, this.type());
      if (res.direct) {
        this.msg?.add({ severity: 'success', summary: this.translate.instant('common.impression_envoyee'),
                        detail: res.imprimante });
      }
    } catch (e: any) {
      // Erreur HTTP (PDF non généré) ou d'imprimante : on le dit, sans jargon.
      const detail = e?.status !== undefined ? this.translate.instant('common.erreur') : e?.message;
      this.msg?.add({ severity: 'error', summary: this.translate.instant('common.impression_impossible'),
                      detail, life: 8000 });
    } finally {
      this.enCours.set(false);
    }
  }
}
