import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { TagModule } from 'primeng/tag';
import { ToggleSwitchModule } from 'primeng/toggleswitch';
import { TooltipModule } from 'primeng/tooltip';
import { MessageService } from 'primeng/api';
import { TranslateModule, TranslateService } from '@ngx-translate/core';

import { LicencesService, LigneRelance } from '../../core/services/licences.service';

/**
 * Les licences qui arrivent à échéance (7 jours ou moins) et leurs relances.
 *
 * Le serveur relance seul chaque matin à J-7, J-3, J-1 et J0 (tâche planifiée
 * `relancer_licences`) ; cet écran montre ce qui est parti, ce qui a échoué,
 * permet de relancer tout de suite et d'ouvrir WhatsApp avec le même message.
 */
@Component({
  selector: 'app-relances-licences',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, FormsModule, ButtonModule, TagModule, ToggleSwitchModule, TooltipModule,
            TranslateModule],
  template: `
    <div class="carte">
      <div class="entete">
        <div class="titre">🔔 {{ 'commercial.relances_titre' | translate }}
          <span class="nb">{{ lignes().length }}</span></div>
        <label class="auto" [pTooltip]="'commercial.relances_auto_aide' | translate">
          <p-toggleswitch [ngModel]="auto()" (onChange)="basculerAuto($event.checked)" />
          <span>{{ 'commercial.relances_auto' | translate }}</span>
        </label>
      </div>
      @if (!smtp()) { <div class="alerte">{{ 'commercial.smtp_absent' | translate }}</div> }
      @if (!lignes().length) {
        <div class="vide">{{ 'commercial.aucune_echeance' | translate }}</div>
      }
      @for (l of lignes(); track l.licence) {
      <div class="ligne">
        <div class="gauche">
          <span class="ecole">{{ l.ecole }}</span>
          <span class="discret">{{ l.type }} · {{ 'commercial.fin_le' | translate }} {{ l.date_fin | date:'dd/MM/yyyy' }}
            · @if (l.destinataires.length) { {{ l.destinataires.join(', ') }} }
              @else { <span class="rouge">{{ 'commercial.sans_adresse' | translate }}</span> }</span>
        </div>
        <p-tag [value]="libelleJours(l.jours)" [severity]="l.jours < 0 ? 'danger' : l.jours <= 1 ? 'danger' : l.jours <= 3 ? 'warn' : 'info'" />
        <span class="paliers">
          @for (p of [7, 3, 1, 0]; track p) {
            <span class="palier" [class.fait]="fait(l, p)" [class.echec]="echec(l, p) && !fait(l, p)"
                  [pTooltip]="infoPalier(l, p)">J-{{ p }}</span>
          }
        </span>
        <span class="actions">
          <p-button [label]="'commercial.relancer' | translate" icon="pi pi-envelope" size="small"
                    [outlined]="!l.a_envoyer" [loading]="enCours() === l.licence"
                    [disabled]="!l.destinataires.length || !smtp()" (onClick)="relancer(l)" />
          @if (l.whatsapp) {
            <p-button icon="pi pi-whatsapp" size="small" severity="success" [text]="true"
                      (onClick)="ouvrir(l.whatsapp)" [pTooltip]="'commercial.whatsapp_relance' | translate" />
          }
        </span>
      </div>
      }
    </div>
  `,
  styles: [`
    .carte { background:rgba(245,158,11,.06); border:1px solid rgba(245,158,11,.35); border-radius:10px;
             padding:12px 16px; margin-bottom:16px; }
    .entete { display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:6px; }
    .titre { font-weight:700; font-size:14px; }
    .nb { background:#f59e0b; color:#fff; border-radius:10px; padding:1px 8px; font-size:12px; margin-left:6px; }
    .auto { display:flex; align-items:center; gap:8px; font-size:12.5px; cursor:pointer; }
    .alerte { background:#fef3c7; color:#92400e; border-radius:6px; padding:6px 10px; font-size:12.5px; margin:6px 0; }
    .vide { font-size:12.5px; color:var(--text-3); padding:6px 0; }
    .ligne { display:flex; align-items:center; gap:12px; padding:8px 0; border-top:1px solid rgba(245,158,11,.2); flex-wrap:wrap; }
    .gauche { display:flex; flex-direction:column; flex:1; min-width:220px; }
    .ecole { font-weight:600; }
    .discret { font-size:12px; color:var(--text-3); }
    .rouge { color:#dc2626; }
    .paliers { display:flex; gap:4px; }
    .palier { font-size:11px; padding:2px 6px; border-radius:6px; border:1px solid var(--surface-3, #cbd5e1);
              color:var(--text-3); }
    .palier.fait { background:#10b981; border-color:#10b981; color:#fff; }
    .palier.echec { background:#fee2e2; border-color:#ef4444; color:#b91c1c; }
    .actions { display:flex; gap:4px; align-items:center; }
  `],
})
export class RelancesLicencesComponent implements OnInit {
  private service = inject(LicencesService);
  private msg = inject(MessageService);
  private translate = inject(TranslateService);

  lignes = signal<LigneRelance[]>([]);
  auto = signal(true);
  smtp = signal(true);
  enCours = signal<string | null>(null);

  ngOnInit() { this.charger(); }

  charger() {
    this.service.getRelances().subscribe({
      next: r => { this.lignes.set(r.lignes); this.auto.set(r.relances_auto); this.smtp.set(r.smtp); },
    });
  }

  libelleJours(jours: number): string {
    if (jours < 0) return this.translate.instant('commercial.expiree_depuis', { n: -jours });
    if (jours === 0) return this.translate.instant('commercial.expire_aujourdhui');
    return this.translate.instant('commercial.dans_n_jours', { n: jours });
  }

  fait(l: LigneRelance, p: number)  { return l.relances.some(r => r.palier === p && r.succes && !r.simulee); }
  echec(l: LigneRelance, p: number) { return l.relances.some(r => r.palier === p && !r.succes); }

  infoPalier(l: LigneRelance, p: number): string {
    const r = l.relances.find(x => x.palier === p);
    if (!r) return this.translate.instant('commercial.palier_pas_envoye');
    const quand = new Date(r.le).toLocaleString('fr-FR');
    return r.succes ? `${quand} — ${r.par} — ${r.destinataires}` : `${quand} — ${r.erreur}`;
  }

  basculerAuto(actif: boolean) {
    this.service.activerRelances(actif).subscribe({
      next: () => this.auto.set(actif),
      error: () => this.msg.add({ severity: 'error', summary: this.translate.instant('common.erreur') }),
    });
  }

  relancer(l: LigneRelance) {
    this.enCours.set(l.licence);
    this.service.relancer(l.licence).subscribe({
      next: r => {
        this.enCours.set(null);
        this.msg.add({ severity: 'success', summary: this.translate.instant('commercial.relance_envoyee'),
                       detail: r.destinataires });
        this.charger();
      },
      error: e => {
        this.enCours.set(null);
        this.msg.add({ severity: 'error', summary: this.translate.instant('common.erreur'),
                       detail: e?.error?.error || '' });
        this.charger();
      },
    });
  }

  ouvrir(lien: string) { window.open(lien, '_blank', 'noopener'); }
}
