import { ChangeDetectionStrategy, Component, computed, effect, inject, signal, untracked } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { LicenceCompteurService } from '../../core/services/licence-compteur.service';
import { LicencesService } from '../../core/services/licences.service';

/** Seul numéro HADY GESMAN associé à un compte WhatsApp. */
const SUPPORT_WHATSAPP = '221784297830';

/**
 * « Renouveler maintenant » : formule chiffrée par le serveur, paiement en
 * ligne (lien Wave / Orange Money réglé par HADY GESMAN) ou coordonnées de
 * paiement, puis « J'ai payé » qui enregistre la demande avec la référence.
 *
 * La licence n'est prolongée qu'à la confirmation par HADY GESMAN ; l'écran
 * le constate de lui-même (LicenceCompteurService relit l'alerte toutes les
 * 5 minutes tant qu'un paiement attend), ou tout de suite par « Actualiser ».
 */
@Component({
  selector: 'app-renouveler-licence',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DecimalPipe, FormsModule, ButtonModule, DialogModule],
  template: `
    <p-dialog header="Renouveler ma licence" [visible]="compteur.renouvellementVisible()"
              (visibleChange)="compteur.renouvellementVisible.set($event)"
              [modal]="true" [draggable]="false" [style]="{ width: '540px', maxWidth: '95vw' }">
      @if (alerte(); as a) {
        <p class="rl-echeance">
          Échéance : <strong>{{ a.date_fin_longue }}</strong>
          @if (a.jours >= 0) { — {{ a.jours === 0 ? "aujourd'hui" : a.jours + ' jour(s) restant(s)' }} }
          @else { — <span class="rl-rouge">expirée</span> }
        </p>

        @if (a.demande_en_attente; as d) {
          <div class="rl-attente" role="status">
            <strong>Paiement déclaré, en attente de confirmation.</strong>
            @if (d.mois) { {{ d.mois }} mois — {{ d.montant | number:'1.0-0' }} FCFA. }
            @if (d.reference_paiement) { Réf. {{ d.reference_paiement }}. }
            La licence sera prolongée dès que HADY GESMAN aura confirmé la réception.
            <p-button label="Actualiser le statut" icon="pi pi-refresh" size="small" [text]="true"
                      [loading]="actualisation()" (onClick)="actualiser()" />
          </div>
        }

        @if (etape() === 'choix') {
          @if (a.offres.length > 1) {
            <label class="rl-label" for="rl-type">Licence</label>
            <select id="rl-type" class="rl-select" [ngModel]="type()" (ngModelChange)="type.set($event)">
              @for (o of a.offres; track o.type) { <option [value]="o.type">{{ o.libelle }}</option> }
            </select>
          }
          <fieldset class="rl-formules">
            <legend class="rl-label">Durée</legend>
            @for (f of offre()?.formules ?? []; track f.mois) {
              <label class="rl-formule" [class.choisie]="mois() === f.mois">
                <input type="radio" name="rl-mois" [value]="f.mois" [checked]="mois() === f.mois"
                       (change)="mois.set(f.mois)" />
                <span class="rl-duree">{{ f.libelle }}</span>
                <span class="rl-montant">{{ f.montant | number:'1.0-0' }} FCFA</span>
                @if (f.remise) { <span class="rl-remise">− {{ f.remise | number:'1.0-0' }}</span> }
              </label>
            }
          </fieldset>

          <div class="rl-payer">
            @if (a.paiement.lien) {
              <a class="rl-btn-payer" [href]="a.paiement.lien" target="_blank" rel="noopener">
                💳 Payer {{ montant() | number:'1.0-0' }} FCFA en ligne
              </a>
              <small class="rl-aide">Wave, Orange Money… La page de paiement s'ouvre dans votre navigateur.</small>
            }
            @if (a.paiement.coordonnees) {
              <div class="rl-coord"><strong>Coordonnées de paiement</strong><pre>{{ a.paiement.coordonnees }}</pre></div>
            }
            @if (!a.paiement.lien && !a.paiement.coordonnees) {
              <p class="rl-aide">Moyens acceptés : {{ a.paiement.moyens.join(', ') }}.
                @if (a.paiement.telephone) { Contact : {{ a.paiement.telephone }}. }</p>
            }
          </div>
        } @else if (etape() === 'declarer') {
          <p class="rl-aide">Indiquez comment vous avez payé : HADY GESMAN confirme la réception, puis
            la licence est prolongée automatiquement.</p>
          <label class="rl-label" for="rl-moyen">Moyen de paiement</label>
          <select id="rl-moyen" class="rl-select" [ngModel]="moyen()" (ngModelChange)="moyen.set($event)">
            @for (m of a.paiement.moyens; track m) { <option [value]="m">{{ m }}</option> }
          </select>
          <label class="rl-label" for="rl-ref">Référence de la transaction (facultatif)</label>
          <input id="rl-ref" class="rl-select" [ngModel]="reference()" (ngModelChange)="reference.set($event)"
                 placeholder="ex. identifiant Wave / Orange Money" maxlength="120" />
          <label class="rl-label" for="rl-msg">Message (facultatif)</label>
          <textarea id="rl-msg" class="rl-select" rows="2" [ngModel]="message()"
                    (ngModelChange)="message.set($event)"></textarea>
        } @else if (etape() === 'envoyee') {
          <div class="rl-ok" role="status">
            ✅ <strong>Demande transmise à HADY GESMAN.</strong> Votre licence sera prolongée dès la
            confirmation du paiement ; cet écran se mettra à jour de lui-même.
          </div>
        } @else {
          <div class="rl-attente" role="alert">
            Votre demande est <strong>enregistrée</strong> mais n'a pas pu être transmise
            automatiquement. Envoyez-la en un clic :
            <a class="rl-btn-payer rl-wa" [href]="lienWhatsapp()" target="_blank" rel="noopener">💬 Envoyer par WhatsApp</a>
          </div>
        }
      }
      <ng-template #footer>
        @switch (etape()) {
          @case ('choix') {
            <p-button label="Plus tard" severity="secondary" [text]="true" (onClick)="fermer()" />
            <p-button label="J'ai payé — prévenir HADY GESMAN" icon="pi pi-check" [disabled]="!montant()"
                      (onClick)="etape.set('declarer')" />
          }
          @case ('declarer') {
            <p-button label="Retour" severity="secondary" [text]="true" (onClick)="etape.set('choix')" />
            <p-button label="Envoyer" icon="pi pi-send" [loading]="envoi()" (onClick)="envoyer()" />
          }
          @default { <p-button label="Fermer" (onClick)="fermer()" /> }
        }
      </ng-template>
    </p-dialog>
  `,
  styles: [`
    .rl-echeance { margin:0 0 12px; font-size:14px; color:var(--text); }
    .rl-rouge { color:#dc2626; font-weight:700; }
    .rl-label { display:block; font-size:12px; color:var(--text-2); margin:12px 0 6px; }
    .rl-select { width:100%; background:var(--bg); border:1px solid var(--border); border-radius:8px; color:var(--text); padding:9px 12px; font:inherit; font-size:14px; }
    .rl-formules { border:none; margin:0; padding:0; display:flex; flex-direction:column; gap:8px; }
    .rl-formule { display:flex; align-items:center; gap:10px; padding:10px 14px; border:1px solid var(--border); border-radius:10px; cursor:pointer; }
    .rl-formule.choisie { border-color:#00a884; background:rgba(0,168,132,.08); }
    .rl-formule:focus-within { outline:2px solid #00a884; outline-offset:1px; }
    .rl-duree { flex:1; font-weight:600; color:var(--text); }
    .rl-montant { font-variant-numeric:tabular-nums; font-weight:700; color:var(--text); }
    .rl-remise { font-size:12px; color:#047857; }
    .rl-payer { margin-top:16px; display:flex; flex-direction:column; gap:8px; }
    .rl-btn-payer { display:block; text-align:center; padding:12px 16px; border-radius:10px; background:#047857; color:#fff; font-weight:700; text-decoration:none; }
    .rl-btn-payer:hover, .rl-btn-payer:focus-visible { background:#065f46; outline:2px solid #065f46; outline-offset:2px; }
    .rl-wa { margin-top:10px; background:#128c3e; }
    .rl-aide { font-size:12px; color:var(--text-2); margin:0; }
    .rl-coord pre { white-space:pre-wrap; font:inherit; font-size:13px; margin:6px 0 0; color:var(--text); }
    .rl-coord { border:1px dashed var(--border); border-radius:8px; padding:10px 12px; font-size:13px; color:var(--text); }
    .rl-attente { background:rgba(234,179,8,.12); border:1px solid #ca8a04; border-radius:10px; padding:10px 14px; font-size:13px; color:var(--text); margin-bottom:12px; }
    .rl-ok { background:rgba(16,185,129,.1); border:1px solid #059669; border-radius:10px; padding:12px 14px; font-size:13px; color:var(--text); }
  `],
})
export class RenouvelerLicenceComponent {
  compteur = inject(LicenceCompteurService);
  private licences = inject(LicencesService);

  alerte = this.compteur.alerte;
  etape = signal<'choix' | 'declarer' | 'envoyee' | 'secours'>('choix');
  type = signal('');
  mois = signal(12);
  moyen = signal('Wave');
  reference = signal('');
  message = signal('');
  envoi = signal(false);
  actualisation = signal(false);
  private texteSecours = '';

  offre = computed(() => {
    const offres = this.alerte()?.offres ?? [];
    return offres.find(o => o.type === this.type()) ?? offres[0] ?? null;
  });
  montant = computed(() => this.offre()?.formules.find(f => f.mois === this.mois())?.montant ?? 0);

  constructor() {
    // À chaque ouverture (et seulement là) : on repart du choix. L'alerte est
    // lue sans dépendance : sa relecture après l'envoi ne doit pas ramener
    // l'écran au choix et masquer la confirmation.
    effect(() => {
      if (!this.compteur.renouvellementVisible()) return;
      const a = untracked(() => this.compteur.alerte());
      this.etape.set('choix');
      this.type.set(a?.offres[0]?.type ?? '');
    });
  }

  fermer() {
    this.compteur.renouvellementVisible.set(false);
  }

  actualiser() {
    this.actualisation.set(true);
    this.compteur.charger(true, () => this.actualisation.set(false));
  }

  envoyer() {
    const a = this.alerte();
    const o = this.offre();
    if (!a?.licence || !o) return;
    this.envoi.set(true);
    this.licences.demanderRenouvellement(a.licence, this.message().trim(), {
      type: o.type, mois: this.mois(), moyen_paiement: this.moyen(),
      reference_paiement: this.reference().trim(),
    }).subscribe({
      next: res => {
        this.envoi.set(false);
        this.texteSecours = res?.corps || '';
        this.etape.set(res?.recue ? 'envoyee' : 'secours');
        this.compteur.charger();
      },
      error: () => {
        this.envoi.set(false);
        this.texteSecours = [
          'Demande de renouvellement SAGI SCHOOL',
          `Licence : ${o.libelle} — ${this.mois()} mois — ${this.montant()} FCFA`,
          `Paiement : ${this.moyen()} ${this.reference()}`.trim(),
          this.message().trim(),
        ].join('\n');
        this.etape.set('secours');
      },
    });
  }

  lienWhatsapp(): string {
    return `https://wa.me/${SUPPORT_WHATSAPP}?text=${encodeURIComponent(this.texteSecours)}`;
  }
}
