import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { ApiService } from '../../core/services/api.service';

type Choix = 'PASSE' | 'REDOUBLE' | 'DIPLOME' | 'TRANSFERE' | 'ABANDONNE' | 'IGNORER';

interface Proposition { decision: 'PASSE' | 'REDOUBLE' | 'SORT' | 'IGNORER'; section_id: string | null; motif: string; }

interface LignePassage {
  id: string; matricule: string; nom_complet: string; section_id: string | null; section: string;
  classe: string; regime: string; proposition: Proposition;
  /** Fiche déjà présente sur le nouvel exercice ; `passe` : décidée par cet assistant
   *  (sinon simple report des impayés dans la même section). */
  deja: { fiche_id: string; section_id: string | null; section: string; redoublant: boolean;
          passe: boolean; creance: boolean; reliquat: number } | null;
}

interface SectionPassage {
  id: string; nom: string; ordre: number; progression: boolean; derniere: boolean;
  suivante_id: string | null; suivante: string;
}

interface Apercu {
  source: { id: string; annee: string; cloture: boolean };
  cible: { id: string; annee: string };
  ordre_a_configurer: boolean;
  sections: SectionPassage[];
  eleves: LignePassage[];
}

interface Rapport {
  passes: number; redoublants: number; sortis: number; ignores: number;
  creees: number; mises_a_jour: number; nb_erreurs: number;
  erreurs: { eleve_id: string; nom_complet?: string; erreur: string }[];
}

interface Decision { choix: Choix; section_id: string | null; }

interface Groupe { section: SectionPassage | null; nom: string; eleves: LignePassage[]; }

const SORTIES: Choix[] = ['DIPLOME', 'TRANSFERE', 'ABANDONNE'];

/**
 * Passage de fin d'année : après la clôture, chaque élève présent passe dans
 * la section suivante, redouble ou sort. Par défaut tout le monde passe ; la
 * direction coche les redoublants et les sorties, élève par élève ou par
 * section. Les fiches du nouvel exercice sont créées avec l'identité de
 * l'élève (matricule, famille, parents…). Rejouable.
 */
@Component({
  selector: 'app-passage-annee',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, ButtonModule],
  template: `
<div class="form-card">
  <div class="fc-title">🎓 Passage de fin d'année
    @if (apercu(); as a) { <span class="pa-annees">{{ a.source.annee }} → {{ a.cible.annee }}</span> }
  </div>
  <p class="pa-aide">
    Par défaut, chaque élève passe dans la section suivante (ordre des sections). Cochez les
    redoublants et les sorties, puis validez : les fiches du nouvel exercice sont créées avec
    l'identité de chaque élève — matricule, famille, parents, santé, prise en charge. Les élèves
    qui ont une dette la gardent. Vous pouvez revenir ici et valider à nouveau : rien n'est dupliqué.
  </p>

  @if (erreur()) {
    <div class="pa-info" role="status">{{ erreur() }}</div>
  }

  @if (apercu(); as a) {
    @if (a.ordre_a_configurer) {
      <div class="pa-alerte" role="alert">
        ⚠️ Toutes vos sections ont le même ordre : impossible de savoir laquelle suit laquelle.
        Réglez « Ordre d'affichage » dans l'onglet Sections (CI = 1, CP = 2…), puis revenez ici.
      </div>
    }

    <div class="pa-compteurs" aria-live="polite">
      <span class="cpt cpt-passe">{{ compte().PASSE }} passent</span>
      <span class="cpt cpt-redouble">{{ compte().REDOUBLE }} redoublent</span>
      <span class="cpt cpt-sort">{{ compte().SORT }} sortent</span>
      @if (compte().IGNORER) { <span class="cpt">{{ compte().IGNORER }} laissés de côté</span> }
      @if (compte().A_CHOISIR) { <span class="cpt cpt-alerte">{{ compte().A_CHOISIR }} section(s) à choisir</span> }
      <input class="pa-recherche" type="search" placeholder="Rechercher un élève…"
             aria-label="Rechercher un élève" [ngModel]="recherche()" (ngModelChange)="recherche.set($event)" />
    </div>

    @for (g of groupes(); track g.nom) {
      <section class="pa-groupe">
        <div class="pa-groupe-tete">
          <div>
            <strong>{{ g.nom }}</strong>
            @if (g.section; as s) {
              <span class="pa-fleche">
                @if (!s.progression) { → reste en {{ s.nom }} }
                @else if (s.derniere) { → fin de cycle (diplômés) }
                @else if (s.suivante) { → {{ s.suivante }} }
                @else { → section à choisir }
              </span>
            }
            <span class="pa-nb">{{ g.eleves.length }} élève(s)</span>
          </div>
          <div class="pa-lot">
            <label class="sr-only" [attr.for]="'lot-' + g.nom">Décision pour toute la section {{ g.nom }}</label>
            <select [id]="'lot-' + g.nom" #lot (change)="appliquerLot(g, $any(lot.value)); lot.value = ''">
              <option value="">Toute la section…</option>
              <option value="PASSE">Passent</option>
              <option value="RESTE">Restent dans leur section (garderie, internat…)</option>
              <option value="REDOUBLE">Redoublent</option>
              <option value="DIPLOME">Diplômés</option>
              <option value="IGNORER">Ne rien faire</option>
            </select>
            <label class="sr-only" [attr.for]="'lot-sec-' + g.nom">Section d'arrivée pour toute la section {{ g.nom }}</label>
            <select [id]="'lot-sec-' + g.nom" #lotSec (change)="appliquerSectionLot(g, lotSec.value); lotSec.value = ''">
              <option value="">Envoyer toute la section en…</option>
              @for (s of a.sections; track s.id) { <option [value]="s.id">{{ s.nom }}</option> }
            </select>
          </div>
        </div>
        <div class="table-wrap">
          <table class="tbl">
            <thead>
              <tr>
                <th scope="col">Élève</th><th scope="col">Classe</th>
                <th scope="col">Décision</th><th scope="col">Section {{ a.cible.annee }}</th>
                <th scope="col">Déjà fait</th>
              </tr>
            </thead>
            <tbody>
              @for (e of g.eleves; track e.id) {
                <tr [class.a-choisir]="aChoisir(e.id)">
                  <td class="gras">{{ e.nom_complet }}<div class="petit">{{ e.matricule }}</div></td>
                  <td>{{ e.classe || '—' }}</td>
                  <td>
                    <select [attr.aria-label]="'Décision pour ' + e.nom_complet"
                            [ngModel]="decision(e.id).choix" (ngModelChange)="choisir(e, $event)">
                      <option value="PASSE">Passe</option>
                      <option value="REDOUBLE">Redouble</option>
                      <option value="DIPLOME">Sort — diplômé</option>
                      <option value="TRANSFERE">Sort — transféré</option>
                      <option value="ABANDONNE">Sort — abandon</option>
                      <option value="IGNORER">Ne rien faire</option>
                    </select>
                  </td>
                  <td>
                    @switch (decision(e.id).choix) {
                      @case ('PASSE') {
                        <select [attr.aria-label]="'Section d\\'arrivée de ' + e.nom_complet"
                                [ngModel]="decision(e.id).section_id ?? ''"
                                (ngModelChange)="choisirSection(e.id, $event)">
                          <option value="">— à choisir —</option>
                          @for (s of a.sections; track s.id) { <option [value]="s.id">{{ s.nom }}</option> }
                        </select>
                      }
                      @case ('REDOUBLE') { {{ e.section }} <span class="tag">redoublant</span> }
                      @case ('IGNORER') { <span class="petit">non réinscrit</span> }
                      @default { <span class="petit">quitte l'établissement</span> }
                    }
                  </td>
                  <td>
                    @if (e.deja; as d) {
                      @if (d.passe) {
                        <span class="tag tag-ok">{{ d.section }}{{ d.redoublant ? ' (red.)' : '' }}</span>
                      } @else if (d.creance) {
                        <span class="tag">créance</span>
                      } @else {
                        <span class="petit">pas encore</span>
                      }
                      @if (d.reliquat) { <div class="petit">dette reportée {{ d.reliquat.toLocaleString('fr-FR') }}</div> }
                    } @else { <span class="petit">—</span> }
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </section>
    } @empty {
      <div class="pa-info">Aucun élève présent sur {{ a.source.annee }}.</div>
    }

    @if (rapport(); as r) {
      <div class="pa-rapport" role="status">
        ✅ {{ r.passes }} passent, {{ r.redoublants }} redoublent, {{ r.sortis }} sortent
        ({{ r.creees }} fiche(s) créée(s), {{ r.mises_a_jour }} mise(s) à jour).
        @if (r.nb_erreurs) {
          <div class="pa-erreurs">
            {{ r.nb_erreurs }} élève(s) non traité(s) :
            <ul>@for (x of r.erreurs; track x.eleve_id) { <li>{{ x.nom_complet || x.eleve_id }} — {{ x.erreur }}</li> }</ul>
          </div>
        }
      </div>
    }

    <div class="form-actions pa-actions">
      @if (compte().A_CHOISIR) {
        <span class="pa-bloque">Choisissez la section d'arrivée des {{ compte().A_CHOISIR }} élève(s) surligné(s).</span>
      }
      <p-button label="Valider le passage" icon="pi pi-check" [loading]="enCours()"
                [disabled]="!!compte().A_CHOISIR || !a.eleves.length" (onClick)="valider()" />
    </div>
  }
</div>
`,
  styles: [`
    .pa-annees { margin-left:8px; font-size:13px; color:#00d4aa; font-weight:600; }
    .pa-aide { font-size:12px; color:var(--text-3); margin:0 0 14px; line-height:1.6; }
    .pa-info { font-size:13px; color:var(--text-2); padding:12px; border:1px dashed var(--border); border-radius:8px; }
    .pa-alerte { background:rgba(234,88,12,.12); border:1px solid #ea580c; color:var(--text); padding:10px 14px; border-radius:8px; font-size:13px; margin-bottom:12px; }
    .pa-compteurs { display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-bottom:12px; }
    .cpt { font-size:12px; font-weight:600; padding:4px 10px; border-radius:12px; background:var(--surface-2); color:var(--text-2); }
    .cpt-passe { background:rgba(5,150,105,.15); color:#059669; }
    .cpt-redouble { background:rgba(234,88,12,.15); color:#ea580c; }
    .cpt-sort { background:rgba(3,105,161,.15); color:#0369a1; }
    .cpt-alerte { background:rgba(220,38,38,.15); color:#dc2626; }
    .pa-recherche { margin-left:auto; flex:1 1 200px; max-width:280px; background:var(--surface); border:1px solid var(--border); color:var(--text); border-radius:8px; padding:6px 10px; font-size:13px; }
    .pa-groupe { margin-bottom:14px; }
    .pa-groupe-tete { display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:6px; font-size:13px; color:var(--text); }
    .pa-fleche { margin-left:6px; color:#00d4aa; }
    .pa-nb { margin-left:8px; font-size:12px; color:var(--text-3); }
    .pa-lot { display:flex; gap:6px; flex-wrap:wrap; }
    select { background:var(--surface); border:1px solid var(--border); color:var(--text); border-radius:6px; padding:5px 8px; font-size:12px; font-family:inherit; }
    select:focus-visible, .pa-recherche:focus-visible { outline:2px solid #00d4aa; outline-offset:1px; }
    .table-wrap { overflow-x:auto; border:1px solid var(--border); border-radius:8px; }
    .tbl { width:100%; border-collapse:collapse; font-size:13px; }
    .tbl th { background:var(--surface-2); color:var(--text-3); font-size:11px; text-transform:uppercase; text-align:left; padding:7px 10px; white-space:nowrap; }
    .tbl td { padding:6px 10px; border-top:1px solid var(--border); color:var(--text-2); vertical-align:middle; }
    tr.a-choisir td { background:rgba(220,38,38,.08); }
    .gras { font-weight:600; color:var(--text); }
    .petit { font-size:11px; color:var(--text-3); }
    .tag { display:inline-block; font-size:11px; padding:1px 7px; border-radius:8px; background:var(--surface-2); color:var(--text-2); }
    .tag-ok { background:rgba(5,150,105,.15); color:#059669; }
    .pa-rapport { margin-top:10px; padding:10px 14px; border-radius:8px; border:1px solid #059669; background:rgba(5,150,105,.08); font-size:13px; color:var(--text); }
    .pa-erreurs { margin-top:6px; color:#dc2626; }
    .pa-erreurs ul { margin:4px 0 0 18px; padding:0; }
    .pa-actions { gap:12px; align-items:center; }
    .pa-bloque { font-size:12px; color:#dc2626; }
    .sr-only { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; }
  `],
})
export class PassageAnneeComponent implements OnInit {
  private api = inject(ApiService);

  apercu    = signal<Apercu | null>(null);
  erreur    = signal('');
  enCours   = signal(false);
  rapport   = signal<Rapport | null>(null);
  recherche = signal('');
  decisions = signal<Record<string, Decision>>({});

  groupes = computed<Groupe[]>(() => {
    const a = this.apercu();
    if (!a) return [];
    const q = this.normaliser(this.recherche());
    const sections = new Map(a.sections.map(s => [s.id, s]));
    const groupes = new Map<string, Groupe>();
    for (const e of a.eleves) {
      if (q && !this.normaliser(`${e.nom_complet} ${e.matricule} ${e.classe}`).includes(q)) continue;
      const cle = e.section_id ?? '';
      if (!groupes.has(cle)) {
        groupes.set(cle, { section: sections.get(cle) ?? null, nom: e.section || 'Sans section', eleves: [] });
      }
      groupes.get(cle)!.eleves.push(e);
    }
    return [...groupes.values()];
  });

  compte = computed(() => {
    const c = { PASSE: 0, REDOUBLE: 0, SORT: 0, IGNORER: 0, A_CHOISIR: 0 };
    for (const d of Object.values(this.decisions())) {
      if (d.choix === 'PASSE') { c.PASSE++; if (!d.section_id) c.A_CHOISIR++; }
      else if (d.choix === 'REDOUBLE') c.REDOUBLE++;
      else if (d.choix === 'IGNORER') c.IGNORER++;
      else c.SORT++;
    }
    return c;
  });

  ngOnInit() { this.charger(); }

  charger() {
    this.api.get<Apercu>('/paiements/passage-annee/').subscribe({
      next: a => {
        this.apercu.set(a);
        this.erreur.set('');
        this.decisions.set(Object.fromEntries(a.eleves.map(e => [e.id, this.initiale(e)])));
      },
      error: err => {
        this.apercu.set(null);
        this.erreur.set(err?.error?.error || 'Impossible de charger le passage de fin d\'année.');
      },
    });
  }

  /** Ce qui a déjà été décidé ici fait foi ; sinon la proposition du serveur. */
  private initiale(e: LignePassage): Decision {
    if (e.deja?.passe && !e.deja.creance) {
      return e.deja.redoublant ? { choix: 'REDOUBLE', section_id: e.section_id }
                               : { choix: 'PASSE', section_id: e.deja.section_id };
    }
    const p = e.proposition;
    if (p.decision === 'SORT') return { choix: (p.motif || 'DIPLOME') as Choix, section_id: null };
    return { choix: p.decision, section_id: p.section_id };
  }

  decision(id: string): Decision {
    return this.decisions()[id] ?? { choix: 'IGNORER', section_id: null };
  }

  aChoisir(id: string): boolean {
    const d = this.decision(id);
    return d.choix === 'PASSE' && !d.section_id;
  }

  choisir(e: LignePassage, choix: Choix) {
    const avant = this.decision(e.id);
    const section_id = choix === 'PASSE'
      ? (avant.section_id ?? (e.proposition.decision === 'PASSE' ? e.proposition.section_id : null))
      : null;
    this.decisions.update(d => ({ ...d, [e.id]: { choix, section_id } }));
  }

  choisirSection(id: string, section_id: string) {
    this.decisions.update(d => ({ ...d, [id]: { choix: 'PASSE', section_id: section_id || null } }));
  }

  appliquerLot(g: Groupe, choix: Choix | 'RESTE' | '') {
    if (!choix) return;
    if (choix === 'RESTE') {
      // Une formule (garderie, internat) n'est pas une classe : on reconduit.
      this.appliquerSectionLot(g, g.section?.id ?? '');
      return;
    }
    for (const e of g.eleves) this.choisir(e, choix);
  }

  appliquerSectionLot(g: Groupe, section_id: string) {
    if (!section_id) return;
    this.decisions.update(d => {
      const n = { ...d };
      for (const e of g.eleves) n[e.id] = { choix: 'PASSE', section_id };
      return n;
    });
  }

  valider() {
    const a = this.apercu();
    if (!a) return;
    const c = this.compte();
    if (!confirm(`Passage ${a.source.annee} → ${a.cible.annee} :\n\n` +
                 `${c.PASSE} élève(s) passent, ${c.REDOUBLE} redoublent, ${c.SORT} sortent` +
                 (c.IGNORER ? `, ${c.IGNORER} laissé(s) de côté` : '') + '.\n\nValider ?')) return;

    const decisions = Object.entries(this.decisions()).map(([eleve_id, d]) => (
      SORTIES.includes(d.choix)
        ? { eleve_id, decision: 'SORT', motif: d.choix }
        : { eleve_id, decision: d.choix, section_id: d.section_id }));

    this.enCours.set(true);
    this.api.post<Rapport>('/paiements/passage-annee/', { source: a.source.id, decisions }).subscribe({
      next: r => { this.rapport.set(r); this.enCours.set(false); this.charger(); },
      error: err => {
        this.enCours.set(false);
        this.erreur.set(err?.error?.error || 'Le passage n\'a pas pu être appliqué.');
      },
    });
  }

  private normaliser(t: string): string {
    return (t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
  }
}
