import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { SelectModule } from 'primeng/select';
import { ApiService } from '../../core/services/api.service';
import { BoutonImprimerComponent } from '../../shared/bouton-imprimer.component';

interface Abonne {
  id: string; matricule: string; nom_complet: string; section: string; classe: string;
  contact: string; telephone: string; tarif: number; mois: string; nb_mois: number;
  du_annee: number; du_echu: number; paye: number; reste_echu: number; avance: number;
  statut: 'A_JOUR' | 'PARTIEL' | 'IMPAYE';
  dernier: { date_texte: string; no_piece: string; montant: number } | null;
}

interface Encaissement {
  date_texte: string; no_piece: string; eleve: string; classe: string; mois: string;
  montant: number; mode: string; receveur: string;
}

interface EtatService {
  id: string; nom: string; periodicite: string; tarif: number; actif: boolean;
  nb_abonnes: number; nb_a_jour: number; nb_en_retard: number;
  du_annee: number; du_echu: number; paye: number; reste_echu: number; encaisse: number;
  abonnes: Abonne[]; encaissements: Encaissement[];
  par_mode: { mode: string; montant: number }[];
  par_receveur: { nom: string; montant: number }[];
}

interface Etat {
  exercice: string; date: string; du: string | null; au: string | null;
  services: EtatService[];
  total: { nb_abonnes: number; nb_a_jour: number; nb_en_retard: number; du_annee: number;
           du_echu: number; paye: number; reste_echu: number; encaisse: number };
}

/**
 * Services optionnels (cantine, transport…) : qui les prend, dans quelle
 * classe, ce que chacun doit et a payé, et ce que chaque service a fait entrer
 * en caisse — par mode et par receveur. Mêmes chiffres en PDF et en Excel.
 */
@Component({
  selector: 'app-services-abonnes',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, DecimalPipe, ButtonModule, SelectModule, BoutonImprimerComponent],
  template: `
<div class="sa">
  <div class="sa-filtres">
    <p-select [options]="optionsServices()" [(ngModel)]="service" optionLabel="nom" optionValue="id"
              [showClear]="true" placeholder="Tous les services" appendTo="body" ariaLabel="Service"
              (onChange)="charger()" styleClass="sa-select" />
    <p-select [options]="sections()" [(ngModel)]="section" optionLabel="nom" optionValue="id"
              [showClear]="true" placeholder="Toutes les sections" appendTo="body" ariaLabel="Section"
              (onChange)="charger()" styleClass="sa-select" />
    <label class="sa-date">Encaissé du
      <input type="date" [(ngModel)]="du" (change)="charger()" /></label>
    <label class="sa-date">au
      <input type="date" [(ngModel)]="au" (change)="charger()" /></label>
    <label class="sa-case"><input type="checkbox" [(ngModel)]="retardSeulement" /> En retard seulement</label>
    <span class="sa-actions">
      <p-button label="PDF" icon="pi pi-file-pdf" size="small" severity="danger" [outlined]="true"
                [loading]="telechargement() === 'pdf'" (onClick)="telecharger('pdf')" />
      <app-bouton-imprimer [pdf]="pdfEtat" />
      <p-button label="Excel" icon="pi pi-file-excel" size="small" severity="success" [outlined]="true"
                [loading]="telechargement() === 'xlsx'" (onClick)="telecharger('xlsx')" />
    </span>
  </div>

  @if (erreur()) { <div class="sa-erreur" role="alert">{{ erreur() }}</div> }

  @if (etat(); as e) {
    <div class="sa-note">
      Arrêté au {{ e.date.split('-').reverse().join('/') }} · exercice {{ e.exercice }} ·
      {{ e.total.nb_abonnes }} abonnement(s), {{ e.total.nb_en_retard }} en retard ·
      reste à ce jour <strong>{{ e.total.reste_echu | number:'1.0-0' }} FCFA</strong> ·
      encaissé {{ e.du || e.au ? 'sur la période' : 'sur l\\'exercice' }}
      <strong>{{ e.total.encaisse | number:'1.0-0' }} FCFA</strong>
    </div>

    @for (s of e.services; track s.id) {
      <div class="sa-carte">
        <button type="button" class="sa-tete" [attr.aria-expanded]="ouvert(s.id)" (click)="basculer(s.id)">
          <span class="sa-nom">{{ ouvert(s.id) ? '▾' : '▸' }} {{ s.nom }}
            <span class="sa-tarif">{{ s.tarif | number:'1.0-0' }} F{{ s.periodicite === 'MENSUEL' ? ' / mois' : '' }}</span>
          </span>
          <span class="sa-chiffres">
            <span><strong>{{ s.nb_abonnes }}</strong> élève(s)</span>
            <span class="ok">{{ s.nb_a_jour }} à jour</span>
            @if (s.nb_en_retard) { <span class="retard">{{ s.nb_en_retard }} en retard</span> }
            <span>Payé <strong>{{ s.paye | number:'1.0-0' }}</strong></span>
            <span>Reste <strong class="retard">{{ s.reste_echu | number:'1.0-0' }}</strong></span>
            <span>Encaissé <strong>{{ s.encaisse | number:'1.0-0' }}</strong></span>
          </span>
        </button>

        @if (ouvert(s.id)) {
          <div class="sa-corps">
            <div class="table-wrap">
              <table class="tbl">
                <thead>
                  <tr>
                    <th scope="col">N°</th><th scope="col">Élève</th><th scope="col">Classe</th>
                    <th scope="col">Téléphone</th><th scope="col">Mois</th>
                    <th scope="col" class="tr">Dû à ce jour</th><th scope="col" class="tr">Payé</th>
                    <th scope="col" class="tr">Reste</th><th scope="col">Statut</th>
                    <th scope="col">Dernier règlement</th>
                  </tr>
                </thead>
                <tbody>
                  @for (a of abonnesFiltres(s); track a.id; let i = $index) {
                    <tr>
                      <td>{{ i + 1 }}</td>
                      <td class="gras">{{ a.nom_complet }} <span class="sub">{{ a.matricule }}</span></td>
                      <td>{{ a.classe || a.section || '—' }}</td>
                      <td>{{ a.telephone || '—' }}</td>
                      <td>{{ a.mois || '—' }}</td>
                      <td class="tr">{{ a.du_echu | number:'1.0-0' }}</td>
                      <td class="tr">{{ a.paye | number:'1.0-0' }}</td>
                      <td class="tr gras">{{ a.reste_echu | number:'1.0-0' }}</td>
                      <td><span class="chip" [class]="'chip chip-' + a.statut">{{ libelleStatut[a.statut] }}</span></td>
                      <td>@if (a.dernier) { {{ a.dernier.no_piece }} · {{ a.dernier.date_texte }} } @else { — }</td>
                    </tr>
                  } @empty {
                    <tr><td colspan="10" class="vide">Aucun abonné{{ retardSeulement ? ' en retard' : '' }}.</td></tr>
                  }
                </tbody>
              </table>
            </div>

            @if (s.encaissements.length) {
              <div class="sa-treso">
                <strong>Encaissements : {{ s.encaisse | number:'1.0-0' }} FCFA</strong>
                @for (m of s.par_mode; track m.mode) { <span class="mode-chip">{{ m.mode }} {{ m.montant | number:'1.0-0' }}</span> }
                <span class="sa-sep">Reçu par :</span>
                @for (r of s.par_receveur; track r.nom) { <span class="mode-chip">👤 {{ r.nom }} {{ r.montant | number:'1.0-0' }}</span> }
              </div>
              <div class="table-wrap">
                <table class="tbl">
                  <thead>
                    <tr>
                      <th scope="col">Date</th><th scope="col">Reçu</th><th scope="col">Élève</th>
                      <th scope="col">Classe</th><th scope="col">Mois</th>
                      <th scope="col" class="tr">Montant</th><th scope="col">Mode</th><th scope="col">Reçu par</th>
                    </tr>
                  </thead>
                  <tbody>
                    @for (l of s.encaissements; track l.no_piece + l.eleve) {
                      <tr>
                        <td>{{ l.date_texte }}</td><td class="mono">{{ l.no_piece }}</td><td>{{ l.eleve }}</td>
                        <td>{{ l.classe || '—' }}</td><td>{{ l.mois || '—' }}</td>
                        <td class="tr">{{ l.montant | number:'1.0-0' }}</td><td>{{ l.mode }}</td><td>{{ l.receveur }}</td>
                      </tr>
                    }
                  </tbody>
                </table>
              </div>
            }
          </div>
        }
      </div>
    } @empty {
      <div class="sa-note">Aucun service optionnel n'est paramétré (Paramètres → Services).</div>
    }
  } @else if (!erreur()) {
    <div class="sa-note">Calcul en cours…</div>
  }
</div>
`,
  styles: [`
    .sa { display:flex; flex-direction:column; gap:10px; }
    .sa-filtres { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
    :host ::ng-deep .sa-select { min-width:180px; }
    .sa-date { font-size:12px; color:var(--text-3); display:flex; align-items:center; gap:4px; }
    .sa-date input { background:var(--surface); color:var(--text); border:1px solid var(--border); border-radius:6px; padding:5px 6px; }
    .sa-case { font-size:12px; color:var(--text-2); display:flex; align-items:center; gap:4px; }
    .sa-actions { display:flex; gap:6px; margin-left:auto; }
    .sa-erreur { color:#dc2626; font-size:13px; }
    .sa-note { font-size:12px; color:var(--text-3); }
    .sa-carte { background:var(--surface); border:1px solid var(--border); border-radius:10px; }
    .sa-tete { width:100%; display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap;
               background:none; border:none; padding:10px 12px; cursor:pointer; color:var(--text); font-family:inherit; text-align:left; }
    .sa-tete:focus-visible { outline:2px solid #00d4aa; outline-offset:2px; }
    .sa-nom { font-weight:700; font-size:14px; }
    .sa-tarif { font-weight:400; font-size:12px; color:var(--text-3); margin-left:6px; }
    .sa-chiffres { display:flex; gap:12px; flex-wrap:wrap; font-size:12px; color:var(--text-2); }
    .ok { color:#16a34a; } .retard { color:#ea580c; }
    .sa-corps { padding:0 12px 12px; display:flex; flex-direction:column; gap:10px; }
    .sa-treso { display:flex; flex-wrap:wrap; gap:6px; align-items:center; font-size:12px; color:var(--text-2); }
    .sa-sep { margin-left:8px; color:var(--text-3); }
    .mode-chip { background:var(--surface-2); border-radius:10px; padding:2px 8px; font-size:11px; }
    .table-wrap { overflow-x:auto; }
    .tbl { width:100%; border-collapse:collapse; font-size:12.5px; }
    .tbl th { background:var(--surface-2); color:var(--text-3); font-size:11px; text-transform:uppercase; text-align:left; padding:6px 8px; white-space:nowrap; }
    .tbl th.tr { text-align:right; }
    .tbl td { padding:5px 8px; border-top:1px solid var(--border); color:var(--text-2); font-variant-numeric:tabular-nums; }
    .tr { text-align:right; }
    .gras { font-weight:600; color:var(--text); }
    .sub { font-weight:400; font-size:11px; color:var(--text-3); }
    .mono { font-family:monospace; }
    .vide { text-align:center; color:var(--text-3); }
    .chip { font-size:11px; padding:1px 8px; border-radius:10px; white-space:nowrap; }
    .chip-A_JOUR { background:rgba(22,163,74,.15); color:#16a34a; }
    .chip-PARTIEL { background:rgba(245,158,11,.15); color:#d97706; }
    .chip-IMPAYE { background:rgba(220,38,38,.15); color:#dc2626; }
  `],
})
export class ServicesAbonnesComponent implements OnInit {
  private api = inject(ApiService);

  etat = signal<Etat | null>(null);
  erreur = signal('');
  telechargement = signal<'' | 'pdf' | 'xlsx'>('');
  sections = signal<{ id: string; nom: string }[]>([]);
  private ouverts = signal<Set<string>>(new Set());
  /** Liste des services, gardée d'un filtrage à l'autre pour le sélecteur. */
  private tousServices = signal<{ id: string; nom: string }[]>([]);
  optionsServices = computed(() => this.tousServices());

  service: string | null = null;
  section: string | null = null;
  du = '';
  au = '';
  retardSeulement = false;

  readonly libelleStatut: Record<string, string> = { A_JOUR: 'À jour', PARTIEL: 'Partiel', IMPAYE: 'Impayé' };

  ngOnInit() {
    this.api.get<any>('/eleves/sections/').subscribe({
      next: r => this.sections.set((r?.results || r || []) as any[]),
    });
    this.charger();
  }

  private params(extra: Record<string, string> = {}): Record<string, string> {
    const p: Record<string, string> = { ...extra };
    if (this.service) p['service'] = this.service;
    if (this.section) p['section'] = this.section;
    if (this.du) p['du'] = this.du;
    if (this.au) p['au'] = this.au;
    return p;
  }

  charger() {
    this.erreur.set('');
    this.api.get<Etat>('/eleves/etat-services/', this.params()).subscribe({
      next: e => {
        this.etat.set(e);
        if (!this.service) this.tousServices.set(e.services.map(s => ({ id: s.id, nom: s.nom })));
        // Un seul service : on l'ouvre d'emblée.
        if (e.services.length === 1) this.ouverts.set(new Set([e.services[0].id]));
      },
      error: err => this.erreur.set(err?.error?.error || "Impossible de calculer l'état des services."),
    });
  }

  ouvert(id: string): boolean { return this.ouverts().has(id); }

  basculer(id: string) {
    this.ouverts.update(s => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  }

  abonnesFiltres(s: EtatService): Abonne[] {
    return this.retardSeulement ? s.abonnes.filter(a => a.statut !== 'A_JOUR') : s.abonnes;
  }

  /** Requête du PDF pour <app-bouton-imprimer>. */
  readonly pdfEtat = () => this.api.getBlob('/eleves/etat-services/', this.params({ export: 'pdf' }));

  telecharger(format: 'pdf' | 'xlsx') {
    const e = this.etat();
    this.telechargement.set(format);
    this.api.getBlob('/eleves/etat-services/', this.params({ export: format })).subscribe({
      next: blob => {
        const url = URL.createObjectURL(blob);
        const lien = document.createElement('a');
        lien.href = url;
        lien.download = `etat_services_${e?.exercice ?? ''}_${e?.date ?? ''}.${format}`;
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
