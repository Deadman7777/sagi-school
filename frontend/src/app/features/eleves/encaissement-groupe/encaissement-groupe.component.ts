import { ChangeDetectionStrategy, Component, computed, effect, inject, input, output,
         signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { CheckboxModule } from 'primeng/checkbox';
import { InputNumberModule } from 'primeng/inputnumber';
import { InputTextModule } from 'primeng/inputtext';
import { SelectModule } from 'primeng/select';
import { TagModule } from 'primeng/tag';
import { TranslateModule, TranslateService } from '@ngx-translate/core';
import { firstValueFrom } from 'rxjs';

import { EcheancesEleve, PosteEcheance, ReglementPrepare } from '../../../core/models/eleve.model';
import { ApiService } from '../../../core/services/api.service';
import { ElevesService, PreparationDemande } from '../../../core/services/eleves.service';
import { PaiementsService } from '../../../core/services/paiements.service';

export interface FinEncaissement {
  reference: string;
  nbReglements: number;
  echecs: string[];
}

/**
 * Encaisser pour plusieurs élèves à la fois : une fratrie, ou les boursiers
 * d'un organisme.
 *
 * La même logique qu'au guichet : chaque élève montre ses échéances — impayé
 * antérieur, frais d'entrée, uniforme, services, chaque mois — échues OU À
 * VENIR, et l'école coche ce que le parent règle, y compris d'avance. Elle
 * peut aussi saisir le montant versé et laisser le logiciel servir le plus
 * ancien dû d'abord.
 *
 * Rien n'est écrit ici : le serveur traduit la sélection en règlements
 * ordinaires, envoyés un par un à l'API des paiements — celle qui écrit les
 * écritures. Il n'existe pas une seconde façon d'encaisser.
 */
@Component({
  selector: 'app-encaissement-groupe',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, FormsModule, ButtonModule, CheckboxModule, InputNumberModule,
            InputTextModule, SelectModule, TagModule, TranslateModule],
  template: `
    @if (chargement()) {
      <p class="aide">{{ 'common.chargement' | translate }}</p>
    } @else {
      <!-- Répartir un montant : le parent arrive avec une somme. -->
      <div class="bloc-repartir">
        <label class="champ">
          <span>{{ (type() === 'organisme' ? 'encaissement.montant_organisme'
                                          : 'encaissement.montant_verse') | translate }}</span>
          <p-inputNumber inputId="enc-montant" [(ngModel)]="montantVerse" [min]="0" [fluid]="true"
                         suffix=" FCFA" />
        </label>
        @if (type() === 'famille') {
          <label class="case">
            <p-checkbox inputId="enc-anticiper" [(ngModel)]="anticiper" [binary]="true" />
            <span>{{ 'encaissement.anticiper' | translate }}</span>
          </label>
        }
        <p-button icon="pi pi-calculator" [label]="'encaissement.repartir' | translate"
                  size="small" severity="info" [outlined]="true"
                  [disabled]="!montantVerse" [loading]="repartition()" (onClick)="repartir()" />
        <span class="espace"></span>
        <p-button [label]="'encaissement.tout_echu' | translate" size="small"
                  severity="secondary" [text]="true" (onClick)="toutEchu()" />
        <p-button [label]="'encaissement.tout_decocher' | translate" size="small"
                  severity="secondary" [text]="true" (onClick)="choix.set({})" />
      </div>
      @if (nonImpute() > 0) {
        <p class="avertissement">
          {{ 'encaissement.non_impute' | translate: { montant: (nonImpute() | number:'1.0-0') } }}
        </p>
      }

      @for (e of eleves(); track e.eleve_id) {
        <div class="eleve">
          <div class="eleve-tete">
            <strong>{{ e.nom_complet }}</strong>
            <span class="meta">{{ e.classe }} · {{ e.matricule }}</span>
            @if (e.organisme && type() === 'famille') {
              <p-tag severity="info" [value]="'encaissement.boursier' | translate: { organisme: e.organisme }" />
            }
            <span class="espace"></span>
            <span class="meta">{{ 'encaissement.echu' | translate }}
              <b class="rouge">{{ resteEleve(e, true) | number:'1.0-0' }}</b>
              · {{ 'encaissement.a_venir' | translate }}
              <b>{{ resteEleve(e, false) | number:'1.0-0' }}</b></span>
          </div>
          @if (postes(e).length === 0) {
            <p class="aide">{{ 'encaissement.rien_du' | translate }}</p>
          } @else {
            <table class="postes">
              <thead>
                <tr>
                  <th class="col-case"></th>
                  <th>{{ 'encaissement.echeance' | translate }}</th>
                  <th>{{ 'encaissement.situation' | translate }}</th>
                  <th class="droite">{{ 'encaissement.reste' | translate }}</th>
                  <th class="droite col-montant">{{ 'encaissement.a_encaisser' | translate }}</th>
                </tr>
              </thead>
              <tbody>
                @for (p of postes(e); track p.cle) {
                  <tr [class.coche]="estCoche(e, p)">
                    <td class="col-case">
                      <p-checkbox [inputId]="'c-' + e.eleve_id + '-' + p.cle" [binary]="true"
                                  [ngModel]="estCoche(e, p)"
                                  (ngModelChange)="basculer(e, p, $event)" />
                    </td>
                    <td><label [for]="'c-' + e.eleve_id + '-' + p.cle">{{ p.libelle }}</label>
                      @if (type() === 'famille' && p.part_organisme > 0) {
                        <span class="note">{{ 'encaissement.dont_organisme' | translate:
                          { montant: (p.part_organisme | number:'1.0-0') } }}</span>
                      }
                    </td>
                    <td>
                      @if (p.echu) {
                        <span class="pastille retard">{{ (p.statut === 'PARTIEL' ? 'encaissement.partiel_retard'
                          : 'encaissement.en_retard') | translate }}</span>
                      } @else {
                        <span class="pastille avenir">{{ (p.statut === 'PARTIEL' ? 'encaissement.partiel_avenir'
                          : 'encaissement.a_venir') | translate }}</span>
                      }
                    </td>
                    <td class="droite mono">{{ reste(p) | number:'1.0-0' }}</td>
                    <td class="droite col-montant">
                      @if (estCoche(e, p)) {
                        <p-inputNumber [inputId]="'m-' + e.eleve_id + '-' + p.cle"
                                       [ngModel]="choix()[cle(e, p)]"
                                       (ngModelChange)="fixer(e, p, $event)"
                                       [min]="0" [max]="reste(p)" [fluid]="true"
                                       [ariaLabel]="p.libelle" />
                      }
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          }
        </div>
      }

      <!-- Comment l'argent entre : mode, caisse, date, payeur. -->
      <div class="bloc-reglement">
        <label class="champ">
          <span>{{ 'encaissement.mode' | translate }}</span>
          <p-select inputId="enc-mode" [options]="modes" [(ngModel)]="mode" optionLabel="label"
                    optionValue="value" appendTo="body" />
        </label>
        @if (mode === 'ESPECE' && caisses().length) {
          <label class="champ">
            <span>{{ 'encaissement.caisse' | translate }}</span>
            <p-select inputId="enc-caisse" [options]="optionsCaisses()" [(ngModel)]="caisse"
                      optionLabel="nom" optionValue="id" appendTo="body" />
          </label>
        }
        <label class="champ">
          <span>{{ 'encaissement.date' | translate }}</span>
          <input pInputText id="enc-date" type="date" [(ngModel)]="date" />
        </label>
        @if (type() === 'famille' && payeurs().length > 1) {
          <label class="champ">
            <span>{{ 'encaissement.payeur' | translate }}</span>
            <p-select inputId="enc-payeur" [options]="payeurs()" [(ngModel)]="payeur"
                      optionLabel="nom" optionValue="id" appendTo="body" />
          </label>
        }
        <label class="champ large">
          <span>{{ (type() === 'organisme' ? 'encaissement.reference_virement'
                                          : 'encaissement.observations') | translate }}</span>
          <input pInputText id="enc-obs" [(ngModel)]="observations" />
        </label>
      </div>

      <div class="pied">
        <span class="total">{{ 'encaissement.total' | translate }}
          <b>{{ total() | number:'1.0-0' }} FCFA</b>
          <span class="meta">· {{ 'encaissement.nb_eleves' | translate: { nb: nbEleves() } }}</span>
        </span>
        <span class="espace"></span>
        @if (progression()) { <span class="meta">{{ progression() }}</span> }
        <p-button icon="pi pi-check" [label]="'encaissement.encaisser' | translate"
                  severity="success" [disabled]="total() <= 0 || enCours()"
                  [loading]="enCours()" (onClick)="encaisser()" />
      </div>
    }
  `,
  styles: [`
    :host { display: flex; flex-direction: column; gap: 12px; }
    .aide { color: var(--text-3); font-size: 13px; margin: 0; }
    .eleve .aide { padding: 8px 12px; }
    .bloc-repartir, .bloc-reglement { display: flex; flex-wrap: wrap; gap: 10px 14px;
      align-items: flex-end; padding: 10px 12px; border: 1px solid var(--border);
      border-radius: 8px; background: var(--surface-2); }
    .champ { display: flex; flex-direction: column; gap: 4px; font-size: 12px;
      color: var(--text-2); min-width: 160px; }
    .champ.large { flex: 1 1 220px; }
    .case { display: flex; align-items: center; gap: 6px; font-size: 13px; }
    .espace { flex: 1; }
    .avertissement { margin: 0; padding: 8px 12px; border-radius: 8px; font-size: 13px;
      background: rgba(217,119,6,.14); border-left: 3px solid #d97706; }
    .eleve { border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
    .eleve-tete { display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
      padding: 8px 12px; background: var(--surface-2); }
    .meta { color: var(--text-3); font-size: 12px; }
    .rouge { color: #ef4444; }
    .postes { width: 100%; border-collapse: collapse; font-size: 13px; }
    .postes th { text-align: left; font-size: 11px; font-weight: 600; color: var(--text-3);
      padding: 6px 10px; border-bottom: 1px solid var(--border); }
    .postes td { padding: 5px 10px; border-bottom: 1px solid var(--border); }
    .postes tr.coche td { background: rgba(0,212,170,.07); }
    .droite { text-align: right; }
    .mono { font-variant-numeric: tabular-nums; }
    .col-case { width: 36px; }
    .col-montant { width: 150px; }
    .note { display: block; font-size: 11px; color: var(--text-3); }
    .pastille { font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 12px; }
    .pastille.retard { color: #ef4444; background: rgba(239,68,68,.12); }
    .pastille.avenir { color: #3b82f6; background: rgba(59,130,246,.12); }
    .pied { display: flex; flex-wrap: wrap; align-items: center; gap: 10px;
      position: sticky; bottom: 0; padding: 10px 0 0; background: var(--surface-2); }
    .total { font-size: 14px; }
  `],
})
export class EncaissementGroupeComponent {
  private elevesApi = inject(ElevesService);
  private paiements = inject(PaiementsService);
  private api = inject(ApiService);
  private translate = inject(TranslateService);

  /** « famille » : ce que la famille doit ; « organisme » : la part de la bourse. */
  type = input<'famille' | 'organisme'>('famille');
  cibleId = input.required<string>();
  payeurs = input<{ id?: string; nom: string; principal?: boolean }[]>([]);
  termine = output<FinEncaissement>();

  eleves = signal<EcheancesEleve[]>([]);
  chargement = signal(false);
  repartition = signal(false);
  enCours = signal(false);
  progression = signal('');
  nonImpute = signal(0);
  /** Montant choisi par poste : « eleve_id|cle » → montant. */
  choix = signal<Record<string, number>>({});
  caisses = signal<{ id: string; nom: string }[]>([]);

  montantVerse: number | null = null;
  anticiper = false;
  mode = 'ESPECE';
  caisse: string | null = null;
  date = new Date().toISOString().slice(0, 10);
  payeur: string | null = null;
  observations = '';

  modes = [
    { label: 'Espèces', value: 'ESPECE' },
    { label: 'Wave', value: 'WAVE' },
    { label: 'Orange Money', value: 'ORANGE_MONEY' },
    { label: 'Free Money', value: 'FREE_MONEY' },
    { label: 'Virement', value: 'VIREMENT' },
    { label: 'Chèque', value: 'CHEQUE' },
  ];

  total = computed(() => Object.values(this.choix()).reduce((t, m) => t + (Number(m) || 0), 0));
  nbEleves = computed(() => new Set(Object.keys(this.choix())
    .filter(k => (this.choix()[k] || 0) > 0).map(k => k.split('|')[0])).size);
  optionsCaisses = computed(() => [
    { id: null, nom: this.translate.instant('encaissement.caisse_principale') },
    ...this.caisses()]);

  constructor() {
    effect(() => {
      const id = this.cibleId();
      if (id) this.charger(id);
    });
    effect(() => {
      const liste = this.payeurs();
      this.payeur = liste.find(p => p.principal)?.id || liste[0]?.id || null;
    });
    this.api.get<any>('/comptabilite/caisses/', { actives: 1 }).subscribe({
      next: r => this.caisses.set((r?.results || r || []) as any[]),
      error: () => this.caisses.set([]),
    });
  }

  private charger(id: string) {
    this.chargement.set(true);
    this.choix.set({});
    this.nonImpute.set(0);
    const requete = this.type() === 'organisme'
      ? this.elevesApi.echeancesOrganisme(id) : this.elevesApi.echeancesFamille(id);
    requete.subscribe({
      next: r => {
        this.eleves.set(r.enfants || r.boursiers || []);
        this.chargement.set(false);
        if (this.type() === 'organisme') this.mode = 'VIREMENT';
      },
      error: () => { this.eleves.set([]); this.chargement.set(false); },
    });
  }

  // ── Lecture des postes ──────────────────────────────────────────────
  reste(p: PosteEcheance): number {
    return this.type() === 'organisme' ? (p.reste_organisme || 0) : p.reste_famille;
  }
  postes(e: EcheancesEleve): PosteEcheance[] {
    return e.postes.filter(p => this.reste(p) > 0);
  }
  resteEleve(e: EcheancesEleve, echu: boolean): number {
    return this.postes(e).filter(p => p.echu === echu).reduce((t, p) => t + this.reste(p), 0);
  }
  cle(e: EcheancesEleve, p: PosteEcheance) { return `${e.eleve_id}|${p.cle}`; }
  estCoche(e: EcheancesEleve, p: PosteEcheance) { return this.cle(e, p) in this.choix(); }

  // ── Sélection ───────────────────────────────────────────────────────
  basculer(e: EcheancesEleve, p: PosteEcheance, coche: boolean) {
    const suivant = { ...this.choix() };
    if (coche) suivant[this.cle(e, p)] = this.reste(p);
    else delete suivant[this.cle(e, p)];
    this.choix.set(suivant);
  }
  fixer(e: EcheancesEleve, p: PosteEcheance, montant: number | null) {
    this.choix.set({ ...this.choix(),
                     [this.cle(e, p)]: Math.min(Number(montant) || 0, this.reste(p)) });
  }
  toutEchu() {
    const suivant: Record<string, number> = {};
    for (const e of this.eleves()) {
      for (const p of this.postes(e)) if (p.echu) suivant[this.cle(e, p)] = this.reste(p);
    }
    this.choix.set(suivant);
    this.nonImpute.set(0);
  }

  /** Le serveur sert le plus ancien dû d'abord ; l'écran coche ce qu'il a servi. */
  repartir() {
    if (!this.montantVerse) return;
    this.repartition.set(true);
    const corps: PreparationDemande = { montant: this.montantVerse, anticiper: this.anticiper };
    const requete = this.type() === 'organisme'
      ? this.elevesApi.preparerOrganisme(this.cibleId(), corps)
      : this.elevesApi.preparerFamille(this.cibleId(), corps);
    requete.subscribe({
      next: r => {
        const suivant: Record<string, number> = {};
        for (const s of r.selection) suivant[`${s.eleve_id}|${s.cle}`] = s.montant;
        this.choix.set(suivant);
        this.nonImpute.set(r.non_impute || 0);
        this.repartition.set(false);
      },
      error: () => this.repartition.set(false),
    });
  }

  // ── Encaissement ────────────────────────────────────────────────────
  async encaisser() {
    const selection = Object.entries(this.choix())
      .filter(([, m]) => (Number(m) || 0) > 0)
      .map(([k, montant]) => {
        const [eleve_id, cle] = k.split('|');
        return { eleve_id, cle, montant: Number(montant) };
      });
    if (!selection.length) return;
    this.enCours.set(true);
    const reference = this.nouvelleReference();
    const echecs: string[] = [];
    let nb = 0;
    try {
      const corps: PreparationDemande = { selection };
      const preparation = await firstValueFrom(this.type() === 'organisme'
        ? this.elevesApi.preparerOrganisme(this.cibleId(), corps)
        : this.elevesApi.preparerFamille(this.cibleId(), corps));
      const reglements: (ReglementPrepare & { nom: string })[] = preparation.lignes.flatMap(
        l => l.reglements.map(r => ({ ...r, nom: l.nom_complet })));
      // Un règlement après l'autre : le numéro de reçu est une séquence de
      // l'école, deux envois simultanés se la disputeraient.
      for (const [i, r] of reglements.entries()) {
        this.progression.set(`${i + 1} / ${reglements.length}`);
        const { detail, total, nom, ...champs } = r;
        try {
          await firstValueFrom(this.paiements.creerPaiement({
            ...champs,
            mode_paiement: this.mode,
            caisse: this.mode === 'ESPECE' ? this.caisse : null,
            date_paiement: this.date || undefined,
            payeur: this.type() === 'famille' ? this.payeur : null,
            reference_groupe: reference,
            observations: this.observations,
          } as any));
          nb++;
        } catch {
          echecs.push(nom);
        }
      }
    } finally {
      this.enCours.set(false);
      this.progression.set('');
    }
    this.termine.emit({ reference, nbReglements: nb, echecs });
    this.charger(this.cibleId());
  }

  private nouvelleReference(): string {
    const c: any = globalThis.crypto;
    if (c?.randomUUID) return c.randomUUID();
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, ch => {
      const r = Math.random() * 16 | 0;
      return (ch === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
  }
}
