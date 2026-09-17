import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ButtonModule } from 'primeng/button';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';
import { TranslateModule, TranslateService } from '@ngx-translate/core';

import { ApiService } from '../../core/services/api.service';
import { ElevesService } from '../../core/services/eleves.service';

type Formule = 'DEMI_JOURNEE' | 'JOURNEE' | null;

interface SoirGarde {
  id: string;
  eleve: string;
  nom_complet: string;
  classe: string;
  heure_depart: string;
  tranches: number;
  montant: number;
}

interface EnfantAppel {
  eleve: string;
  nom_complet: string;
  matricule: string;
  classe: string;
  section: string;
  tarif_demi_journee: number;
  tarif_journee: number;
  formule: Formule;
  hors_periode: boolean;
}

interface LigneReprise {
  paiement: string;
  no_piece: string;
  date: string;
  eleve: string;
  nom_complet: string;
  divers: number;
  observations: string;
  mois_propose: number | null;
}

interface LigneRecap {
  eleve: string;
  nom_complet: string;
  classe: string;
  demi: number;
  journee: number;
  du: number;
  paye: number;
  reste: number;
}

/**
 * Garderie à la journée : l'appel du jour et le récapitulatif du mois.
 *
 * L'écran ne calcule aucun montant : le serveur fige le tarif de chaque jour
 * à l'enregistrement, et le récapitulatif lit l'échéancier — le même que la
 * fiche de l'enfant et le guichet. L'argent s'encaisse au guichet (Paiements),
 * en cochant le mois : au jour, à la semaine ou au mois, selon la famille.
 */
@Component({
  selector: 'app-garderie',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DatePipe, DecimalPipe, FormsModule, RouterLink, ButtonModule, ToastModule, TranslateModule],
  providers: [MessageService],
  template: `
    <p-toast />
    <div class="page-header">
      <div>
        <h2 class="page-title">🧸 {{ 'garderie.title' | translate }}</h2>
        <span class="page-sub">{{ 'garderie.subtitle' | translate }}</span>
      </div>
      <div class="onglets" role="tablist">
        <button type="button" role="tab" [attr.aria-selected]="onglet() === 'appel'"
                [class.actif]="onglet() === 'appel'" (click)="onglet.set('appel')">
          {{ 'garderie.onglet_appel' | translate }}</button>
        <button type="button" role="tab" [attr.aria-selected]="onglet() === 'recap'"
                [class.actif]="onglet() === 'recap'" (click)="ouvrirRecap()">
          {{ 'garderie.onglet_recap' | translate }}</button>
        @if (gardeSoir().actif) {
          <button type="button" role="tab" [attr.aria-selected]="onglet() === 'soir'"
                  [class.actif]="onglet() === 'soir'" (click)="ouvrirSoir()">
            {{ 'garderie.onglet_soir' | translate }}</button>
        }
        @if (aReprendre().length) {
          <button type="button" role="tab" [attr.aria-selected]="onglet() === 'reprise'"
                  [class.actif]="onglet() === 'reprise'" (click)="onglet.set('reprise')">
            {{ 'garderie.onglet_reprise' | translate }} ({{ aReprendre().length }})</button>
        }
      </div>
    </div>

    @if (onglet() === 'soir') {
      <p class="aide">{{ 'garderie.soir_aide' | translate:{ limite: gardeSoir().limite,
                          facturation: gardeSoir().facturation_a, tarif: gardeSoir().tarif } }}</p>
      <div class="filtres">
        <label class="champ">
          <span>{{ 'garderie.date' | translate }}</span>
          <input type="date" [max]="aujourdhui" [ngModel]="date()" (ngModelChange)="date.set($event); chargerSoir()" />
        </label>
        <label class="champ" style="flex:1;min-width:220px">
          <span>{{ 'garderie.enfant' | translate }}</span>
          <input type="text" [(ngModel)]="rechercheSoir" (ngModelChange)="chercherEleve($event)"
                 [placeholder]="'garderie.chercher_enfant' | translate" />
          @if (suggestions().length) {
            <div class="suggestions">
              @for (e of suggestions(); track e.id) {
                <button type="button" (click)="choisirEleve(e)">{{ e.nom_complet }}
                  <span class="sous">{{ e.classe_nom || e.section_nom }}</span></button>
              }
            </div>
          }
        </label>
        <label class="champ">
          <span>{{ 'garderie.heure_depart' | translate }}</span>
          <input type="time" [(ngModel)]="heureSoir" />
        </label>
        <label class="champ" style="justify-content:flex-end">
          <span>&nbsp;</span>
          <p-button icon="pi pi-plus" [label]="'garderie.ajouter_soir' | translate" [loading]="saving()"
                    [disabled]="!eleveSoir" (onClick)="enregistrerSoir()" />
        </label>
      </div>
      @if (eleveSoir) { <p class="aide">{{ 'garderie.enfant_choisi' | translate }} <b>{{ eleveSoir.nom_complet }}</b></p> }

      <div class="table-card">
        <table class="recap">
          <thead>
            <tr><th>{{ 'garderie.enfant' | translate }}</th><th>{{ 'garderie.heure_depart' | translate }}</th>
                <th class="ta-r">{{ 'garderie.tranches' | translate }}</th>
                <th class="ta-r">{{ 'garderie.montant' | translate }}</th><th></th></tr>
          </thead>
          <tbody>
            @for (s of soirs(); track s.id) {
              <tr>
                <td><div class="bold">{{ s.nom_complet }}</div><div class="sous">{{ s.classe }}</div></td>
                <td class="mono">{{ s.heure_depart }}</td>
                <td class="ta-r mono">{{ s.tranches }}</td>
                <td class="ta-r mono bold">{{ s.montant | number:'1.0-0' }}</td>
                <td class="ta-r"><p-button icon="pi pi-times" severity="danger" [text]="true" size="small"
                                           (onClick)="retirerSoir(s)" /></td>
              </tr>
            } @empty {
              <tr><td colspan="5" class="vide">{{ 'garderie.aucun_soir' | translate }}</td></tr>
            }
          </tbody>
        </table>
      </div>
      <p class="aide">{{ 'garderie.soir_encaisser' | translate }}</p>
    }

    @if (onglet() === 'reprise') {
      <p class="aide">{{ 'garderie.reprise_aide' | translate }}</p>
      <div class="liste">
        @for (l of aReprendre(); track l.paiement) {
          <div class="ligne">
            <div class="nom">
              <div class="bold">{{ l.nom_complet }}</div>
              <div class="sous">{{ l.no_piece }} · {{ l.date | date:'dd/MM/yyyy' }}{{ l.observations ? ' · ' + l.observations : '' }}</div>
            </div>
            <div class="reprise-actions">
              <label class="champ">
                <span>{{ 'garderie.montant' | translate }}</span>
                <input type="number" min="1" [max]="l.divers" [(ngModel)]="l.montant" />
              </label>
              <label class="champ">
                <span>{{ 'garderie.mois' | translate }}</span>
                <select [(ngModel)]="l.mois">
                  @for (m of moisOptions; track m) { <option [ngValue]="m">{{ nomMois(m) }}</option> }
                </select>
              </label>
              <p-button size="small" icon="pi pi-check" [label]="'garderie.reclasser' | translate"
                        [loading]="saving()" (onClick)="reclasser(l)" />
            </div>
          </div>
        }
      </div>
    }

    <div class="filtres" [hidden]="onglet() === 'reprise'">
      @if (onglet() === 'appel') {
        <label class="champ">
          <span>{{ 'garderie.date' | translate }}</span>
          <input type="date" [max]="aujourdhui" [ngModel]="date()" (ngModelChange)="changerDate($event)" />
        </label>
      } @else {
        <label class="champ">
          <span>{{ 'garderie.mois' | translate }}</span>
          <select [ngModel]="mois()" (ngModelChange)="mois.set(+$event); chargerRecap()">
            @for (m of moisOptions; track m) {
              <option [ngValue]="m">{{ nomMois(m) }}</option>
            }
          </select>
        </label>
      }
      <label class="champ">
        <span>{{ 'garderie.classe' | translate }}</span>
        <select [ngModel]="classe()" (ngModelChange)="classe.set($event); recharger()">
          <option value="">{{ 'garderie.toutes_classes' | translate }}</option>
          @for (c of classes(); track c.id) {
            <option [value]="c.id">{{ c.nom }}</option>
          }
        </select>
      </label>
    </div>

    @if (erreur()) {
      <div class="alerte" role="alert">{{ erreur() }}</div>
    }

    @if (onglet() === 'appel' && !erreur()) {
      @if (!enfants().length && !loading()) {
        <div class="vide">
          {{ 'garderie.aucun_enfant' | translate }}
          <a routerLink="/parametres">{{ 'garderie.aller_parametres' | translate }}</a>
        </div>
      } @else {
        <div class="resume">
          <span>{{ 'garderie.presents' | translate:{ n: nbPresents() } }}</span>
          <span class="mono">{{ totalJour() | number:'1.0-0' }} FCFA</span>
          <span class="espace"></span>
          <p-button size="small" [outlined]="true" severity="secondary"
                    [label]="'garderie.tous_journee' | translate" (onClick)="tousEn('JOURNEE')" />
          <p-button size="small" [outlined]="true" severity="secondary"
                    [label]="'garderie.tous_absents' | translate" (onClick)="tousEn(null)" />
        </div>
        <div class="liste">
          @for (e of enfants(); track e.eleve) {
            <div class="ligne" [class.grise]="e.hors_periode">
              <div class="nom">
                <div class="bold">{{ e.nom_complet }}</div>
                <div class="sous">{{ e.classe || e.section }}{{ e.matricule ? ' · ' + e.matricule : '' }}</div>
              </div>
              <div class="choix" role="radiogroup" [attr.aria-label]="e.nom_complet">
                <button type="button" role="radio" [attr.aria-checked]="!e.formule"
                        [class.actif]="!e.formule" (click)="choisir(e, null)">
                  {{ 'garderie.absent' | translate }}</button>
                @if (e.tarif_demi_journee > 0) {
                  <button type="button" role="radio" [attr.aria-checked]="e.formule === 'DEMI_JOURNEE'"
                          [disabled]="e.hors_periode" [class.actif]="e.formule === 'DEMI_JOURNEE'"
                          (click)="choisir(e, 'DEMI_JOURNEE')">
                    ½ {{ 'garderie.journee' | translate }}
                    <small>{{ e.tarif_demi_journee | number:'1.0-0' }}</small></button>
                }
                @if (e.tarif_journee > 0) {
                  <button type="button" role="radio" [attr.aria-checked]="e.formule === 'JOURNEE'"
                          [disabled]="e.hors_periode" [class.actif]="e.formule === 'JOURNEE'"
                          (click)="choisir(e, 'JOURNEE')">
                    {{ 'garderie.journee' | translate }}
                    <small>{{ e.tarif_journee | number:'1.0-0' }}</small></button>
                }
              </div>
            </div>
          }
        </div>
        <div class="actions">
          @if (modifie()) { <span class="sous">{{ 'garderie.non_enregistre' | translate }}</span> }
          <p-button icon="pi pi-check" severity="success" [label]="'garderie.enregistrer' | translate"
                    [loading]="saving()" [disabled]="!modifie()" (onClick)="enregistrer()" />
        </div>
      }
    }

    @if (onglet() === 'recap' && !erreur()) {
      <div class="table-card">
        <table class="recap">
          <thead>
            <tr>
              <th>{{ 'garderie.enfant' | translate }}</th>
              <th class="ta-r">½ {{ 'garderie.journee' | translate }}</th>
              <th class="ta-r">{{ 'garderie.journee' | translate }}</th>
              <th class="ta-r">{{ 'garderie.du' | translate }}</th>
              <th class="ta-r">{{ 'garderie.verse' | translate }}</th>
              <th class="ta-r">{{ 'garderie.reste' | translate }}</th>
            </tr>
          </thead>
          <tbody>
            @for (l of recap(); track l.eleve) {
              <tr>
                <td><div class="bold">{{ l.nom_complet }}</div><div class="sous">{{ l.classe }}</div></td>
                <td class="ta-r mono">{{ l.demi }}</td>
                <td class="ta-r mono">{{ l.journee }}</td>
                <td class="ta-r mono">{{ l.du | number:'1.0-0' }}</td>
                <td class="ta-r mono">{{ l.paye | number:'1.0-0' }}</td>
                <td class="ta-r mono bold" [class.rouge]="l.reste > 0">{{ l.reste | number:'1.0-0' }}</td>
              </tr>
            } @empty {
              <tr><td colspan="6" class="vide">{{ 'garderie.aucun_enfant' | translate }}</td></tr>
            }
          </tbody>
          @if (recap().length) {
            <tfoot>
              <tr>
                <td colspan="3" class="bold">{{ 'garderie.total' | translate }}</td>
                <td class="ta-r mono bold">{{ recapTotaux().du | number:'1.0-0' }}</td>
                <td class="ta-r mono bold">{{ recapTotaux().paye | number:'1.0-0' }}</td>
                <td class="ta-r mono bold rouge">{{ recapTotaux().reste | number:'1.0-0' }}</td>
              </tr>
            </tfoot>
          }
        </table>
      </div>
      <p class="aide">{{ 'garderie.aide_encaisser' | translate }}
        <a routerLink="/paiements">{{ 'garderie.aller_paiements' | translate }}</a></p>
    }
  `,
  styles: [`
    .page-header { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; flex-wrap:wrap; margin-bottom:16px; }
    .page-title { font-size:20px; font-weight:600; color:var(--text); margin:0; }
    .page-sub { font-size:12px; color:var(--text-3); }
    .onglets { display:flex; gap:6px; }
    .onglets button, .choix button { border:1px solid var(--border); background:var(--surface); color:var(--text-2);
      border-radius:8px; padding:8px 14px; font-size:13px; cursor:pointer; min-height:40px; }
    .onglets button.actif { background:#00d4aa; border-color:#00d4aa; color:#06281f; font-weight:600; }
    .filtres { display:flex; gap:12px; flex-wrap:wrap; margin-bottom:14px; }
    .champ { display:flex; flex-direction:column; gap:4px; font-size:11px; color:var(--text-2); text-transform:uppercase; letter-spacing:.4px; }
    .champ input, .champ select { padding:8px 10px; border:1px solid var(--border); border-radius:8px; background:var(--surface);
      color:var(--text); font-size:14px; min-width:180px; }
    .alerte { padding:10px 14px; border:1px solid #ef4444; border-radius:8px; color:#ef4444; margin-bottom:12px; }
    .vide { padding:30px; text-align:center; color:var(--text-3); }
    .vide a, .aide a { color:#0099ff; margin-left:6px; }
    .resume { display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:10px; font-size:13px; color:var(--text-2); }
    .espace { flex:1; }
    .liste { display:flex; flex-direction:column; gap:6px; }
    .ligne { display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap;
      background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:10px 12px; }
    .ligne.grise { opacity:.55; }
    .choix { display:flex; gap:6px; flex-wrap:wrap; }
    .choix button { display:flex; flex-direction:column; align-items:center; min-width:92px; }
    .choix button small { font-size:11px; color:inherit; opacity:.8; }
    .choix button.actif { background:#0099ff; border-color:#0099ff; color:#fff; font-weight:600; }
    .choix button:first-child.actif { background:var(--surface-2); border-color:var(--text-3); color:var(--text); }
    .choix button:disabled { cursor:not-allowed; }
    .actions { display:flex; justify-content:flex-end; align-items:center; gap:12px; margin-top:14px; position:sticky; bottom:0;
      background:var(--bg, transparent); padding:8px 0; }
    .table-card { background:var(--surface); border:1px solid var(--border); border-radius:12px; overflow-x:auto; }
    .recap { width:100%; border-collapse:collapse; }
    .recap th { text-align:left; font-size:11px; color:var(--text-3); padding:10px; border-bottom:1px solid var(--border); }
    .recap td { padding:8px 10px; border-bottom:1px solid var(--surface-2); font-size:13px; color:var(--text-2); }
    .recap tfoot td { border-top:1px solid var(--border); }
    .ta-r { text-align:right; }
    .mono { font-family:monospace; }
    .bold { font-weight:600; color:var(--text); }
    .sous { font-size:11px; color:var(--text-3); }
    .rouge { color:#ef4444; }
    .aide { font-size:12px; color:var(--text-3); margin-top:10px; }
    .reprise-actions { display:flex; align-items:flex-end; gap:8px; flex-wrap:wrap; }
    .suggestions { position:relative; }
    .suggestions button { display:block; width:100%; text-align:left; padding:6px 10px; font-size:13px;
      background:var(--surface); border:1px solid var(--border); border-top:0; color:var(--text); cursor:pointer; }
    .reprise-actions .champ input, .reprise-actions .champ select { min-width:110px; }
  `],
})
export class GarderieComponent implements OnInit {
  private api = inject(ApiService);
  private eleves = inject(ElevesService);
  private msg = inject(MessageService);
  private translate = inject(TranslateService);

  readonly aujourdhui = this.isoLocal(new Date());
  readonly moisOptions = [9, 10, 11, 12, 1, 2, 3, 4, 5, 6, 7, 8];

  onglet = signal<'appel' | 'recap' | 'reprise' | 'soir'>('appel');
  // ── Garde du soir ──
  gardeSoir = signal<{ actif: boolean; limite: string; facturation_a: string; tarif: number }>(
    { actif: false, limite: '', facturation_a: '', tarif: 0 });
  soirs = signal<SoirGarde[]>([]);
  suggestions = signal<any[]>([]);
  rechercheSoir = '';
  heureSoir = '';
  eleveSoir: any = null;
  date = signal(this.aujourdhui);
  mois = signal(new Date().getMonth() + 1);
  classe = signal('');
  classes = signal<{ id: string; nom: string }[]>([]);
  enfants = signal<EnfantAppel[]>([]);
  recap = signal<LigneRecap[]>([]);
  recapTotaux = signal({ du: 0, paye: 0, reste: 0 });
  loading = signal(false);
  saving = signal(false);
  erreur = signal('');
  /** Formules chargées du serveur, pour savoir ce que l'utilisateur a changé. */
  private origine = new Map<string, Formule>();
  private version = signal(0);

  nbPresents = computed(() => this.enfants().filter(e => e.formule).length);
  totalJour = computed(() => this.enfants().reduce((a, e) =>
    a + (e.formule === 'JOURNEE' ? e.tarif_journee : e.formule === 'DEMI_JOURNEE' ? e.tarif_demi_journee : 0), 0));
  modifie = computed(() => {
    this.version();
    return this.enfants().some(e => (this.origine.get(e.eleve) ?? null) !== e.formule);
  });

  aReprendre = signal<(LigneReprise & { montant: number; mois: number })[]>([]);

  chargerReprise() {
    this.api.get<LigneReprise[]>('/eleves/garderie/reprise/').subscribe({
      next: lignes => this.aReprendre.set(lignes.map(l => ({ ...l, montant: l.divers, mois: l.mois_propose || this.mois() }))),
      error: () => this.aReprendre.set([]),
    });
  }

  reclasser(l: LigneReprise & { montant: number; mois: number }) {
    this.saving.set(true);
    this.api.post<any>('/eleves/garderie/reprise/', { paiement: l.paiement, mois: l.mois, montant: l.montant }).subscribe({
      next: () => {
        this.saving.set(false);
        this.msg.add({ severity: 'success', summary: this.translate.instant('garderie.reclasse'), detail: l.no_piece });
        this.chargerReprise();
      },
      error: err => {
        this.saving.set(false);
        this.msg.add({ severity: 'error', summary: this.translate.instant('common.erreur'), detail: this.message(err) });
      },
    });
  }

  ouvrirSoir() {
    this.onglet.set('soir');
    this.chargerSoir();
  }

  /** Réglages + soirs saisis pour la date choisie. */
  chargerSoir() {
    this.api.get<any>('/eleves/garde-soir/', { date: this.date() }).subscribe({
      next: r => {
        this.gardeSoir.set({ actif: r.actif, limite: r.limite, facturation_a: r.facturation_a, tarif: r.tarif });
        this.soirs.set(r.soirs || []);
      },
      error: err => this.erreur.set(this.message(err)),
    });
  }

  chercherEleve(q: string) {
    this.eleveSoir = null;
    if ((q || '').trim().length < 2) { this.suggestions.set([]); return; }
    this.eleves.searchEleves(q.trim()).subscribe({
      next: r => this.suggestions.set((r as any[]).slice(0, 8)),
      error: () => this.suggestions.set([]),
    });
  }

  choisirEleve(e: any) {
    this.eleveSoir = e;
    this.rechercheSoir = e.nom_complet;
    this.suggestions.set([]);
  }

  enregistrerSoir() {
    if (!this.eleveSoir || !this.heureSoir) return this.avertir('garderie.heure_requise');
    this.saving.set(true);
    this.api.post<any>('/eleves/garde-soir/', {
      eleve: this.eleveSoir.id, date: this.date(), heure_depart: this.heureSoir }).subscribe({
      next: r => {
        this.saving.set(false);
        this.msg.add({ severity: 'success', summary: this.translate.instant('garderie.soir_enregistre'),
                       detail: `${this.eleveSoir.nom_complet} — ${r.montant} FCFA` });
        this.eleveSoir = null;
        this.rechercheSoir = '';
        this.chargerSoir();
      },
      error: err => {
        this.saving.set(false);
        this.msg.add({ severity: 'warn', summary: this.translate.instant('common.attention'), detail: this.message(err) });
        this.chargerSoir();
      },
    });
  }

  retirerSoir(s: SoirGarde) {
    this.api.delete<void>(`/eleves/garde-soir/?id=${s.id}`).subscribe({
      next: () => this.chargerSoir(),
      error: err => this.msg.add({ severity: 'error', summary: this.message(err) }),
    });
  }

  private avertir(cle: string) {
    this.msg.add({ severity: 'warn', summary: this.translate.instant(cle) });
  }

  ngOnInit() {
    this.chargerSoir();
    this.chargerReprise();
    this.eleves.getClasses().subscribe({
      next: res => this.classes.set((res as any).results || res || []),
      error: () => {},
    });
    this.chargerAppel();
  }

  recharger() {
    if (this.onglet() === 'appel') this.chargerAppel();
    else this.chargerRecap();
  }

  changerDate(valeur: string) {
    if (this.modifie() && !confirm(this.translate.instant('garderie.confirmer_abandon'))) {
      this.version.update(v => v + 1);
      return;
    }
    this.date.set(valeur);
    this.chargerAppel();
  }

  chargerAppel() {
    this.loading.set(true);
    this.erreur.set('');
    this.api.get<{ enfants: EnfantAppel[] }>('/eleves/garderie/appel/',
      { date: this.date(), classe: this.classe() || undefined }).subscribe({
      next: r => {
        this.origine = new Map(r.enfants.map(e => [e.eleve, e.formule]));
        this.enfants.set(r.enfants);
        this.loading.set(false);
      },
      error: err => { this.loading.set(false); this.enfants.set([]); this.erreur.set(this.message(err)); },
    });
  }

  choisir(e: EnfantAppel, formule: Formule) {
    this.enfants.update(liste => liste.map(x => x.eleve === e.eleve ? { ...x, formule } : x));
  }

  tousEn(formule: Formule) {
    this.enfants.update(liste => liste.map(x => {
      if (x.hors_periode) return x;
      const possible = formule !== 'JOURNEE' || x.tarif_journee > 0;
      return possible ? { ...x, formule } : x;
    }));
  }

  enregistrer() {
    const presences = this.enfants()
      .filter(e => (this.origine.get(e.eleve) ?? null) !== e.formule)
      .map(e => ({ eleve: e.eleve, formule: e.formule }));
    this.saving.set(true);
    this.api.post<{ ajoutes: number; modifies: number; retires: number }>('/eleves/garderie/appel/',
      { date: this.date(), presences }).subscribe({
      next: r => {
        this.saving.set(false);
        this.msg.add({ severity: 'success', summary: this.translate.instant('garderie.enregistre'),
                       detail: this.translate.instant('garderie.bilan', r) });
        this.chargerAppel();
      },
      error: err => {
        this.saving.set(false);
        this.msg.add({ severity: 'error', summary: this.translate.instant('common.erreur'), detail: this.message(err) });
      },
    });
  }

  ouvrirRecap() {
    this.onglet.set('recap');
    this.chargerRecap();
  }

  chargerRecap() {
    this.erreur.set('');
    this.api.get<{ enfants: LigneRecap[]; totaux: { du: number; paye: number; reste: number } }>(
      '/eleves/garderie/recap/', { mois: this.mois(), classe: this.classe() || undefined }).subscribe({
      next: r => { this.recap.set(r.enfants); this.recapTotaux.set(r.totaux); },
      error: err => { this.recap.set([]); this.erreur.set(this.message(err)); },
    });
  }

  nomMois(m: number): string {
    const nom = new Date(2000, m - 1, 1).toLocaleDateString(this.translate.currentLang || 'fr', { month: 'long' });
    return nom.charAt(0).toUpperCase() + nom.slice(1);
  }

  private message(err: any): string {
    return err?.error?.error || this.translate.instant('common.erreur');
  }

  private isoLocal(d: Date): string {
    const p = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
  }
}
