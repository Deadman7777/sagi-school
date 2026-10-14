import { ChangeDetectionStrategy, Component, effect, inject, input, output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { TagModule } from 'primeng/tag';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { TextareaModule } from 'primeng/textarea';
import { SelectModule } from 'primeng/select';
import { CheckboxModule } from 'primeng/checkbox';
import { TooltipModule } from 'primeng/tooltip';
import { ConfirmationService, MessageService } from 'primeng/api';
import { TranslateModule, TranslateService } from '@ngx-translate/core';

import { CommercialService, CourrielProposition, DocumentBibliotheque, Proposition }
  from '../../core/services/commercial.service';

type Severite = 'success' | 'info' | 'warn' | 'danger' | 'secondary' | 'contrast';

/**
 * Les propositions commerciales d'une fiche prospect (modèle HG-IDM-2026).
 *
 * On établit la proposition (préremplie depuis la fiche), on la personnalise,
 * on la relit en PDF, on la valide, puis « Envoyer » l'expédie par e-mail avec
 * les brochures et le catalogue choisis. Les montants viennent du serveur :
 * l'écran ne calcule rien.
 */
@Component({
  selector: 'app-propositions-prospect',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, FormsModule, ButtonModule, TagModule, DialogModule, InputTextModule,
            TextareaModule, SelectModule, CheckboxModule, TooltipModule, TranslateModule],
  template: `
    @if (prospectId()) {
      <div class="separator sep-hist">{{ 'commercial.propositions' | translate }}</div>
    }
    <p class="aide">{{ 'commercial.aide_propositions' | translate }}</p>

    @if (!liste().length) {
      <div class="vide">{{ 'commercial.aucune_proposition' | translate }}</div>
    }
    @for (p of liste(); track p.id) {
    <div class="ligne">
      <div class="gauche">
        <span class="mono ref">{{ p.reference }}@if (!prospectId()) { · {{ p.etablissement }} }</span>
        <span class="offre">{{ p.licence_libelle }} · {{ 'commercial.annuelle' | translate }}
          {{ p.total_annuel | number:'1.0-0' }} {{ 'common.fcfa' | translate }}</span>
        @if (p.formule_libelle) { <span class="offre">✔ {{ p.formule_libelle }}</span> }
        @if (p.erreur_envoi) { <span class="erreur">⚠ {{ p.erreur_envoi }}</span> }
      </div>
      <p-tag [value]="p.expiree ? ('commercial.expiree' | translate) : p.statut_libelle"
             [severity]="p.expiree ? 'danger' : severite(p.statut)" />
      <span class="actions">
        <p-button icon="pi pi-eye" [text]="true" size="small" (onClick)="voirPdf(p)"
                  [pTooltip]="'commercial.apercu_pdf' | translate" />
        @if (p.statut === 'BROUILLON') {
          <p-button icon="pi pi-pencil" [text]="true" size="small" (onClick)="ouvrirEdition(p)"
                    [pTooltip]="'commercial.personnaliser' | translate" />
          <p-button [label]="'commercial.valider' | translate" size="small" severity="success"
                    (onClick)="valider(p)" />
        }
        @if (p.statut === 'VALIDEE') {
          <p-button icon="pi pi-undo" [text]="true" size="small" (onClick)="rouvrir(p)"
                    [pTooltip]="'commercial.rouvrir' | translate" />
        }
        @if ((p.statut === 'VALIDEE' || p.statut === 'ENVOYEE') && !p.expiree) {
          <p-button [label]="(p.statut === 'ENVOYEE' ? 'commercial.renvoyer' : 'commercial.envoyer') | translate"
                    icon="pi pi-send" size="small" (onClick)="ouvrirEnvoi(p)" />
        }
        @if (p.statut === 'VALIDEE' || p.statut === 'ENVOYEE') {
          <p-button icon="pi pi-check-square" [text]="true" size="small" (onClick)="ouvrirReponse(p)"
                    [pTooltip]="'commercial.reponse_client' | translate" />
        }
        @if (p.statut !== 'BROUILLON') {
          <p-button icon="pi pi-copy" [text]="true" size="small" (onClick)="dupliquer(p)"
                    [pTooltip]="'commercial.dupliquer' | translate" />
        } @else {
          <p-button icon="pi pi-trash" [text]="true" size="small" severity="danger"
                    (onClick)="supprimer(p)" [pTooltip]="'common.supprimer' | translate" />
        }
      </span>
    </div>
    }

    @if (!prospectId()) {
      <div class="bloc-titre">{{ 'commercial.nouveau_client' | translate }}</div>
      <div class="champs">
        <label>{{ 'commercial.etablissement' | translate }} *
          <input pInputText [(ngModel)]="client.etablissement" /></label>
        <label>{{ 'commercial.ville' | translate }} <input pInputText [(ngModel)]="client.ville" /></label>
        <label>{{ 'commercial.contact_nom' | translate }} <input pInputText [(ngModel)]="client.contact_nom" /></label>
        <label>{{ 'commercial.telephones' | translate }} <input pInputText [(ngModel)]="client.telephone" /></label>
        <label>{{ 'commercial.email' | translate }} <input pInputText [(ngModel)]="client.email" /></label>
      </div>
      <p class="aide">{{ 'commercial.aide_nouveau_client' | translate }}</p>
    }
    <div class="nouvelle">
      <p-select [(ngModel)]="licenceNouvelle" [options]="licences" optionLabel="label"
                optionValue="value" appendTo="body" styleClass="select-licence" />
      <p-button [label]="'commercial.nouvelle' | translate" icon="pi pi-file-edit" size="small"
                [outlined]="true" [loading]="occupe()" (onClick)="etablir()" />
    </div>

    <!-- ── Personnaliser ─────────────────────────────────────────────── -->
    <p-dialog [visible]="editionVisible()" (visibleChange)="editionVisible.set($event)" [modal]="true" appendTo="body" [style]="{width:'860px'}"
              [breakpoints]="{'900px':'96vw'}" [header]="(edition()?.reference || '') + ' — ' + ('commercial.personnaliser' | translate)"
              [draggable]="false">
      @if (edition(); as e) {
      <div class="bloc-titre">{{ 'commercial.sec_client' | translate }}</div>
      <div class="champs">
        <label class="large">{{ 'commercial.etablissement' | translate }}
          <input pInputText [(ngModel)]="e.etablissement" /></label>
        <label class="large">{{ 'commercial.sous_titre' | translate }}
          <input pInputText [(ngModel)]="e.sous_titre" [placeholder]="'commercial.sous_titre_aide' | translate" /></label>
        <label class="large">{{ 'commercial.adresse' | translate }} <input pInputText [(ngModel)]="e.adresse" /></label>
        <label>{{ 'commercial.telephones' | translate }} <input pInputText [(ngModel)]="e.telephones" /></label>
        <label>{{ 'commercial.email' | translate }} <input pInputText [(ngModel)]="e.email" /></label>
        <label>{{ 'commercial.autres_contacts' | translate }} <input pInputText [(ngModel)]="e.autres_contacts" /></label>
        <label>{{ 'commercial.a_l_attention' | translate }} <input pInputText [(ngModel)]="e.a_l_attention" /></label>
        <label>{{ 'commercial.contact_nom' | translate }} <input pInputText [(ngModel)]="e.contact_nom" /></label>
      </div>

      <div class="bloc-titre">{{ 'commercial.sec_offre' | translate }}</div>
      <div class="champs">
        <label>{{ 'commercial.licence' | translate }}
          <p-select [(ngModel)]="e.type_licence" [options]="licences" optionLabel="label"
                    optionValue="value" appendTo="body" [fluid]="true" /></label>
        <label>{{ 'commercial.programme' | translate }} <input pInputText [(ngModel)]="e.programme" /></label>
        <label>{{ 'commercial.edition' | translate }} <input pInputText [(ngModel)]="e.edition" /></label>
        <label>{{ 'commercial.installation' | translate }}
          <input pInputText type="number" min="0" [(ngModel)]="e.frais_installation" /></label>
        <label>{{ 'commercial.remise_semestrielle' | translate }}
          <input pInputText type="number" min="0" max="99" step="0.5" [(ngModel)]="tauxSemestriel" /></label>
        <label>{{ 'commercial.remise_annuelle' | translate }}
          <input pInputText type="number" min="0" max="99" step="0.5" [(ngModel)]="tauxAnnuel" /></label>
        <label>{{ 'commercial.validite' | translate }}
          <input pInputText type="number" min="1" max="180" [(ngModel)]="e.validite_jours" /></label>
        <label class="case">
          <p-checkbox [(ngModel)]="e.migration_proposee" [binary]="true" inputId="migr" />
          <span>{{ 'commercial.migration_proposee' | translate }}</span></label>
        @if (e.migration_proposee) {
          <label>{{ 'commercial.migration' | translate }}
            <input pInputText type="number" min="0" [(ngModel)]="e.frais_migration" /></label>
        }
      </div>

      <div class="bloc-titre">{{ 'commercial.sec_texte' | translate }}</div>
      <label class="plein">{{ 'commercial.contexte' | translate }}
        <textarea pTextarea rows="5" [(ngModel)]="e.contexte"></textarea></label>
      <div class="champs">
        <label class="large">{{ 'commercial.besoins' | translate }}
          <textarea pTextarea rows="6" [(ngModel)]="besoinsTexte"></textarea></label>
        <label class="large">{{ 'commercial.resultats' | translate }}
          <textarea pTextarea rows="6" [(ngModel)]="resultatsTexte"></textarea></label>
      </div>
      <p class="aide">{{ 'commercial.une_ligne_par_point' | translate }}</p>

      <div class="bloc-titre">{{ 'commercial.sec_pieces' | translate }}</div>
      @if (!bibliotheque().length) {
        <p class="aide">{{ 'commercial.bibliotheque_vide' | translate }}</p>
      }
      @for (d of bibliotheque(); track d.id) {
        <label class="case">
          <p-checkbox [ngModel]="joints()" (ngModelChange)="joints.set($event)" [value]="d.id" [inputId]="'j-' + d.id" />
          <span>{{ d.titre }} <span class="discret">({{ d.categorie_libelle }}, {{ taille(d.taille) }})</span></span>
        </label>
      }

      @if (e.chiffrage; as c) {
      <div class="bloc-titre">{{ 'commercial.sec_montants' | translate }}</div>
      <table class="montants">
        <tr><th></th><th>{{ 'commercial.mensuelle' | translate }}</th>
            <th>{{ 'commercial.semestrielle' | translate }}</th><th>{{ 'commercial.annuelle' | translate }}</th></tr>
        <tr><td>{{ 'commercial.total_souscription' | translate }}</td>
            <td class="mono">{{ c.mensuelle.total | number:'1.0-0' }}</td>
            <td class="mono">{{ c.semestrielle.total | number:'1.0-0' }}</td>
            <td class="mono">{{ c.annuelle.total | number:'1.0-0' }}</td></tr>
        <tr><td>{{ 'commercial.equivalent_mensuel' | translate }}</td>
            <td class="mono">{{ c.mensuelle.equivalent | number:'1.0-0' }}</td>
            <td class="mono">{{ c.semestrielle.equivalent | number:'1.0-0' }}</td>
            <td class="mono">{{ c.annuelle.equivalent | number:'1.0-0' }}</td></tr>
      </table>
      <p class="aide">{{ 'commercial.montants_serveur' | translate }}</p>
      }
      }
      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler' | translate" [text]="true" (onClick)="editionVisible.set(false)" />
        <p-button [label]="'commercial.apercu_pdf' | translate" icon="pi pi-eye" [outlined]="true"
                  [loading]="occupe()" (onClick)="enregistrer(true)" />
        <p-button [label]="'common.enregistrer' | translate" icon="pi pi-check" [loading]="occupe()"
                  (onClick)="enregistrer(false)" />
      </ng-template>
    </p-dialog>

    <!-- ── Envoyer ───────────────────────────────────────────────────── -->
    <p-dialog [visible]="envoiVisible()" (visibleChange)="envoiVisible.set($event)" [modal]="true" appendTo="body" [style]="{width:'720px'}"
              [breakpoints]="{'760px':'96vw'}" [header]="'commercial.envoyer_titre' | translate:{ ref: envoiCible()?.reference }"
              [draggable]="false">
      @if (courriel(); as c) {
        @if (!c.smtp) { <div class="alerte">{{ 'commercial.smtp_absent' | translate }}</div> }
        <label class="plein">{{ 'commercial.destinataires' | translate }}
          <input pInputText [(ngModel)]="c.destinataires" [placeholder]="'commercial.destinataires_aide' | translate" /></label>
        <label class="plein">{{ 'commercial.sujet' | translate }} <input pInputText [(ngModel)]="c.sujet" /></label>
        <label class="plein">{{ 'commercial.message' | translate }}
          <textarea pTextarea rows="13" [(ngModel)]="c.corps"></textarea></label>
        <div class="bloc-titre">{{ 'commercial.pieces_jointes' | translate }}</div>
        <div class="case fixe">📄 {{ 'commercial.la_proposition' | translate }} ({{ envoiCible()?.reference }})</div>
        @for (d of bibliotheque(); track d.id) {
          <label class="case">
            <p-checkbox [ngModel]="joints()" (ngModelChange)="joints.set($event)" [value]="d.id" [inputId]="'e-' + d.id" />
            <span>{{ d.titre }} <span class="discret">({{ taille(d.taille) }})</span></span>
          </label>
        }
      }
      <ng-template pTemplate="footer">
        @if (courriel()?.whatsapp) {
          <p-button label="WhatsApp" icon="pi pi-whatsapp" severity="success" [outlined]="true"
                    (onClick)="ouvrirWhatsapp(courriel()!.whatsapp)" [pTooltip]="'commercial.whatsapp_aide' | translate" />
        }
        <p-button [label]="'common.annuler' | translate" [text]="true" (onClick)="envoiVisible.set(false)" />
        <p-button [label]="'commercial.envoyer_mail' | translate" icon="pi pi-send" [loading]="occupe()"
                  [disabled]="!courriel()?.smtp" (onClick)="envoyer()" />
      </ng-template>
    </p-dialog>

    <!-- ── Réponse du client ─────────────────────────────────────────── -->
    <p-dialog [visible]="reponseVisible()" (visibleChange)="reponseVisible.set($event)" [modal]="true" appendTo="body" [style]="{width:'480px'}"
              [header]="'commercial.reponse_client' | translate" [draggable]="false">
      <label class="plein">{{ 'commercial.decision' | translate }}
        <p-select [(ngModel)]="reponse.decision" [options]="decisions" optionLabel="label" optionValue="value"
                  appendTo="body" [fluid]="true" /></label>
      @if (reponse.decision === 'ACCEPTEE') {
        <label class="plein">{{ 'commercial.formule_choisie' | translate }}
          <p-select [(ngModel)]="reponse.formule" [options]="formules" optionLabel="label" optionValue="value"
                    appendTo="body" [fluid]="true" /></label>
        <label class="case">
          <p-checkbox [(ngModel)]="reponse.migration" [binary]="true" inputId="rep-migr" />
          <span>{{ 'commercial.avec_migration' | translate }}</span></label>
      }
      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler' | translate" [text]="true" (onClick)="reponseVisible.set(false)" />
        <p-button [label]="'common.enregistrer' | translate" [loading]="occupe()" (onClick)="repondre()" />
      </ng-template>
    </p-dialog>
  `,
  styles: [`
    .separator { font-size:12px; font-weight:600; color:#00d4aa; padding:8px 0 4px;
                 border-top:1px solid var(--border); margin-top:18px; }
    .aide { font-size:12px; color:var(--text-3); margin:2px 0 8px; }
    .vide { font-size:12px; color:var(--text-3); padding:6px 0; }
    .ligne { display:flex; align-items:center; gap:10px; padding:7px 0; border-bottom:1px solid var(--surface-2); flex-wrap:wrap; }
    .gauche { display:flex; flex-direction:column; flex:1; min-width:200px; }
    .ref { font-weight:600; }
    .offre { font-size:12px; color:var(--text-2); }
    .erreur { font-size:11.5px; color:#dc2626; }
    .actions { display:flex; align-items:center; gap:4px; flex-wrap:wrap; }
    .nouvelle { display:flex; justify-content:flex-end; gap:8px; margin-top:8px; flex-wrap:wrap; }
    :host ::ng-deep .select-licence { min-width:180px; }
    .bloc-titre { font-weight:700; font-size:12.5px; color:var(--text-1); margin:14px 0 6px;
                  padding-bottom:4px; border-bottom:2px solid #b98a2e; }
    .champs { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:10px 12px; }
    .champs > * { min-width:0; }
    .champs .large { grid-column:span 3; }
    .champs label, .plein { display:flex; flex-direction:column; gap:4px; font-size:12px; color:var(--text-2); }
    .plein { margin-bottom:10px; }
    .champs input, .plein input, .plein textarea, .champs textarea { width:100%; }
    .case { display:flex !important; flex-direction:row !important; align-items:center; gap:8px; font-size:13px;
            color:var(--text-1); margin:4px 0; }
    .case.fixe { color:var(--text-2); }
    .discret { color:var(--text-3); font-size:11.5px; }
    .alerte { background:#fef3c7; color:#92400e; border-radius:6px; padding:8px 10px; font-size:12.5px; margin-bottom:10px; }
    .montants { width:100%; border-collapse:collapse; font-size:12.5px; }
    .montants th, .montants td { padding:5px 8px; border-bottom:1px solid var(--surface-2); text-align:right; }
    .montants th:first-child, .montants td:first-child { text-align:left; }
    @media (max-width: 700px) {
      .champs { grid-template-columns:minmax(0, 1fr); }
      .champs .large { grid-column:span 1; }
    }
  `],
})
export class PropositionsProspectComponent {
  private service = inject(CommercialService);
  private msg = inject(MessageService);
  private confirm = inject(ConfirmationService);
  private translate = inject(TranslateService);

  /** Vide : vue d'ensemble de toutes les propositions, création pour un nouveau client. */
  prospectId = input<string | null>(null);
  /** Le statut du prospect et son historique ont changé : la fiche se recharge. */
  modifie = output<void>();

  liste = signal<Proposition[]>([]);
  bibliotheque = signal<DocumentBibliotheque[]>([]);
  occupe = signal(false);

  licences = [
    { label: 'Taxawu Daara', value: 'TAXAWU_DAARA' }, { label: 'Basic', value: 'BASIC' },
    { label: 'Pro', value: 'PRO' }, { label: 'Avancé', value: 'AVANCE' },
  ];
  licenceNouvelle = 'TAXAWU_DAARA';
  client = { etablissement: '', ville: '', contact_nom: '', telephone: '', email: '' };

  edition = signal<Proposition | null>(null);
  editionVisible = signal(false);
  besoinsTexte = '';
  resultatsTexte = '';
  tauxSemestriel = 8;
  tauxAnnuel = 10;
  joints = signal<string[]>([]);

  envoiCible = signal<Proposition | null>(null);
  courriel = signal<CourrielProposition | null>(null);
  envoiVisible = signal(false);

  reponseCible: Proposition | null = null;
  reponseVisible = signal(false);
  reponse: { decision: 'ACCEPTEE' | 'REFUSEE'; formule: string; migration: boolean } =
    { decision: 'ACCEPTEE', formule: 'ANNUELLE', migration: false };
  decisions: { label: string; value: string }[] = [];
  formules: { label: string; value: string }[] = [];

  constructor() {
    effect(() => { this.prospectId(); this.charger(); });
    const t = (k: string) => this.translate.instant(k);
    this.decisions = [{ label: t('commercial.acceptee'), value: 'ACCEPTEE' },
                      { label: t('commercial.refusee'), value: 'REFUSEE' }];
    this.formules = [
      { label: t('commercial.f_mensuelle'), value: 'MENSUELLE' },
      { label: t('commercial.f_semestrielle'), value: 'SEMESTRIELLE' },
      { label: t('commercial.f_annuelle'), value: 'ANNUELLE' },
      { label: t('commercial.f_annuelle_tranches'), value: 'ANNUELLE_TRANCHES' },
    ];
  }

  charger() {
    this.service.propositions(this.prospectId() || undefined).subscribe({ next: l => this.liste.set(l) });
    this.service.documents(true).subscribe({ next: d => this.bibliotheque.set(d) });
  }

  severite(statut: string): Severite {
    return ({ BROUILLON: 'warn', VALIDEE: 'info', ENVOYEE: 'contrast', ACCEPTEE: 'success',
              REFUSEE: 'danger' } as Record<string, Severite>)[statut] ?? 'secondary';
  }

  taille(octets: number): string {
    return octets > 1048576 ? `${(octets / 1048576).toFixed(1)} Mo` : `${Math.max(1, Math.round(octets / 1024))} Ko`;
  }

  private erreur(err: any) {
    this.occupe.set(false);
    this.msg.add({ severity: 'error', summary: this.translate.instant('common.erreur'),
                   detail: err?.error?.error || this.translate.instant('commercial.erreur') });
  }

  private ok(cle: string, params?: object) {
    this.msg.add({ severity: 'success', summary: this.translate.instant(cle, params) });
  }

  /** Remplace la ligne dans la liste, sans recharger. */
  private remplacer(p: Proposition) {
    this.liste.update(l => l.some(x => x.id === p.id) ? l.map(x => x.id === p.id ? p : x) : [p, ...l]);
  }

  etablir() {
    const id = this.prospectId();
    if (!id && !this.client.etablissement.trim()) {
      this.erreur({ error: { error: this.translate.instant('commercial.etablissement_requis') } });
      return;
    }
    this.occupe.set(true);
    const demande = id ? this.service.etablir(id, this.licenceNouvelle)
                       : this.service.etablirPourClient(this.client, this.licenceNouvelle);
    demande.subscribe({
      next: p => {
        this.occupe.set(false);
        this.client = { etablissement: '', ville: '', contact_nom: '', telephone: '', email: '' };
        this.remplacer(p); this.modifie.emit(); this.ouvrirEdition(p);
      },
      error: e => this.erreur(e),
    });
  }

  ouvrirEdition(p: Proposition) {
    this.service.proposition(p.id).subscribe({
      next: complet => {
        this.edition.set({ ...complet });
        this.besoinsTexte = (complet.besoins || []).join('\n');
        this.resultatsTexte = (complet.resultats || []).join('\n');
        this.tauxSemestriel = Math.round((complet.taux_semestriel || 0) * 1000) / 10;
        this.tauxAnnuel = Math.round((complet.taux_annuel || 0) * 1000) / 10;
        this.joints.set([...(complet.documents_joints || [])]);
        this.editionVisible.set(true);
      },
      error: e => this.erreur(e),
    });
  }

  enregistrer(apercu: boolean) {
    const e = this.edition();
    if (!e) return;
    this.occupe.set(true);
    this.service.modifier(e.id, {
      etablissement: e.etablissement, sous_titre: e.sous_titre, adresse: e.adresse,
      telephones: e.telephones, email: e.email, autres_contacts: e.autres_contacts,
      a_l_attention: e.a_l_attention, contact_nom: e.contact_nom, type_licence: e.type_licence,
      programme: e.programme, edition: e.edition, frais_installation: Number(e.frais_installation) || 0,
      frais_migration: Number(e.frais_migration) || 0, migration_proposee: !!e.migration_proposee,
      taux_semestriel: (Number(this.tauxSemestriel) || 0) / 100,
      taux_annuel: (Number(this.tauxAnnuel) || 0) / 100,
      validite_jours: Number(e.validite_jours) || 30, contexte: e.contexte,
      besoins: this.besoinsTexte.split('\n'), resultats: this.resultatsTexte.split('\n'),
      documents_joints: this.joints(),
    }).subscribe({
      next: p => {
        this.occupe.set(false);
        this.edition.set({ ...p });
        this.remplacer(p);
        if (apercu) this.voirPdf(p);
        else { this.editionVisible.set(false); this.ok('commercial.enregistree'); }
      },
      error: err => this.erreur(err),
    });
  }

  voirPdf(p: Proposition) {
    // L'API demande un jeton : le PDF est récupéré puis ouvert dans un onglet.
    this.service.pdf(p.id).subscribe({
      next: blob => {
        const url = URL.createObjectURL(blob);
        window.open(url, '_blank');
        setTimeout(() => URL.revokeObjectURL(url), 60_000);
      },
      error: e => this.erreur(e),
    });
  }

  valider(p: Proposition) {
    this.confirm.confirm({
      message: this.translate.instant('commercial.confirmer_validation', { ref: p.reference }),
      header: this.translate.instant('commercial.valider'),
      accept: () => this.service.valider(p.id).subscribe({
        next: v => { this.remplacer(v); this.ok('commercial.validee'); },
        error: e => this.erreur(e),
      }),
    });
  }

  rouvrir(p: Proposition) {
    this.service.rouvrir(p.id).subscribe({ next: v => this.remplacer(v), error: e => this.erreur(e) });
  }

  dupliquer(p: Proposition) {
    this.service.dupliquer(p.id).subscribe({
      next: c => { this.remplacer(c); this.ouvrirEdition(c); },
      error: e => this.erreur(e),
    });
  }

  supprimer(p: Proposition) {
    this.confirm.confirm({
      message: this.translate.instant('commercial.confirmer_suppression', { ref: p.reference }),
      header: this.translate.instant('common.supprimer'),
      accept: () => this.service.supprimer(p.id).subscribe({
        next: () => this.liste.update(l => l.filter(x => x.id !== p.id)),
        error: e => this.erreur(e),
      }),
    });
  }

  ouvrirEnvoi(p: Proposition) {
    this.envoiCible.set(p);
    this.courriel.set(null);
    this.service.proposition(p.id).subscribe({
      next: complet => this.joints.set([...(complet.documents_joints || [])]),
    });
    this.service.courriel(p.id).subscribe({
      next: c => { this.courriel.set({ ...c }); this.envoiVisible.set(true); },
      error: e => this.erreur(e),
    });
  }

  envoyer() {
    const p = this.envoiCible(), c = this.courriel();
    if (!p || !c) return;
    this.occupe.set(true);
    this.service.envoyer(p.id, { destinataires: c.destinataires, sujet: c.sujet, corps: c.corps,
                                 documents: this.joints() }).subscribe({
      next: r => {
        this.occupe.set(false);
        this.envoiVisible.set(false);
        this.remplacer(r);
        this.modifie.emit();
        this.ok('commercial.envoyee', { a: r.servis.join(', ') });
        if (r.whatsapp) {
          this.confirm.confirm({
            message: this.translate.instant('commercial.prevenir_whatsapp'),
            header: 'WhatsApp', acceptLabel: this.translate.instant('commercial.ouvrir_whatsapp'),
            rejectLabel: this.translate.instant('common.fermer'),
            accept: () => this.ouvrirWhatsapp(r.whatsapp),
          });
        }
      },
      error: e => { this.erreur(e); this.charger(); },
    });
  }

  ouvrirWhatsapp(lien: string) {
    window.open(lien, '_blank', 'noopener');
  }

  ouvrirReponse(p: Proposition) {
    this.reponseCible = p;
    this.reponse = { decision: 'ACCEPTEE', formule: 'ANNUELLE', migration: false };
    this.reponseVisible.set(true);
  }

  repondre() {
    const p = this.reponseCible;
    if (!p) return;
    this.occupe.set(true);
    const r = this.reponse;
    this.service.repondre(p.id, r.decision, r.decision === 'ACCEPTEE' ? r.formule : '',
                          r.decision === 'ACCEPTEE' ? r.migration : null).subscribe({
      next: v => { this.occupe.set(false); this.reponseVisible.set(false); this.remplacer(v); this.modifie.emit(); },
      error: e => this.erreur(e),
    });
  }
}
