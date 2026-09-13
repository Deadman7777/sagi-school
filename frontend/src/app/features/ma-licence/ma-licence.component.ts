import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { LicencesService } from '../../core/services/licences.service';
import { AuthService } from '../../core/services/auth.service';
import { LicenceCompteurService } from '../../core/services/licence-compteur.service';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';
import { TranslateModule, TranslateService } from '@ngx-translate/core';

/** Coordonnées support HADY GESMAN — à modifier ici uniquement. */
const SUPPORT_EMAIL  = 'hadygesman@gmail.com';
const SUPPORT_PHONES = ['+221 70 328 61 51', '+221 78 429 78 30'];
/** Seul numéro associé à un compte WhatsApp. */
const SUPPORT_WHATSAPP = '221784297830';

@Component({
  selector: 'app-ma-licence',
  standalone: true,
  imports: [CommonModule, FormsModule, ButtonModule, DialogModule, ToastModule, TranslateModule],
  providers: [MessageService],
  template: `
    <p-toast />
    <div class="page-header">
      <div>
        <h2 class="page-title">🔑 {{ 'ma_licence.title' | translate }}</h2>
        <span class="page-sub">{{ 'ma_licence.subtitle' | translate }}</span>
      </div>
    </div>

    <div class="licence-wrap" *ngIf="licence()">

      <!-- Statut principal -->
      <div class="statut-card" [class.active]="licence().est_active"
                               [class.expire]="!licence().est_active">
        <div class="statut-icon">{{ licence().est_active ? '✅' : '❌' }}</div>
        <div class="statut-info">
          <div class="statut-label">
            {{ (licence().est_active ? 'ma_licence.licence_active' : 'ma_licence.licence_expiree') | translate }}
          </div>
          <div class="statut-type">{{ 'ma_licence.plan' | translate }} {{ licence().type }}</div>
        </div>
        <div class="statut-jours" [style.color]="joursColor()">
          <div class="jours-val">{{ jours() }}</div>
          <div class="jours-label">{{ 'ma_licence.jours_restants' | translate }}</div>
        </div>
      </div>

      <!-- Rappel de paiement de l'abonnement : compte à rebours en temps réel. -->
      <div class="compteur" [class]="'compteur cpt-' + compteur.niveau()" role="status">
        <div class="cpt-jours">
          @if (compteur.niveau() === 'expiree') { <span class="cpt-val">Expirée</span> }
          @else { <span class="cpt-val">J-{{ jours() }}</span> }
        </div>
        <div class="cpt-texte">
          @switch (compteur.niveau()) {
            @case ('expiree')  { <strong>Votre abonnement est expiré.</strong> L'accès aux modules sera coupé après 7 jours de grâce. }
            @case ('critique') { <strong>Plus que {{ jours() }} jour(s) :</strong> renouvelez maintenant pour éviter toute interruption. }
            @case ('urgent')   { <strong>Échéance dans {{ jours() }} jours.</strong> Pensez à préparer le règlement de l'abonnement. }
            @case ('attention'){ <strong>Échéance dans {{ jours() }} jours.</strong> Le renouvellement peut être demandé dès aujourd'hui. }
            @default           { Abonnement à jour — échéance le <strong>{{ licence().date_fin }}</strong>. }
          }
        </div>
        <p-button [label]="'ma_licence.demander_renouv' | translate" icon="pi pi-refresh"
                  [severity]="compteur.niveau() === 'ok' ? 'secondary' : 'warn'"
                  (onClick)="demanderRenouvellement()" />
      </div>

      <!-- Détails -->
      <div class="details-grid">
        <div class="detail-card">
          <div class="dc-label">{{ 'ma_licence.cle_licence' | translate }}</div>
          <div class="dc-value cle">{{ licence().cle_licence }}</div>
        </div>
        <div class="detail-card">
          <div class="dc-label">{{ 'ma_licence.type_abonnement' | translate }}</div>
          <div class="dc-value">{{ licence().type }}</div>
        </div>
        <div class="detail-card">
          <div class="dc-label">{{ 'ma_licence.date_activation' | translate }}</div>
          <div class="dc-value mono">{{ licence().date_debut }}</div>
        </div>
        <div class="detail-card">
          <div class="dc-label">{{ 'ma_licence.date_expiration' | translate }}</div>
          <div class="dc-value mono" [style.color]="joursColor()">{{ licence().date_fin }}</div>
        </div>
      </div>

      <!-- Barre de progression -->
      <div class="progress-card">
        <div class="pc-header">
          <span>{{ 'ma_licence.duree_licence' | translate }}</span>
          <span class="mono" [style.color]="joursColor()">
            {{ jours() }} {{ 'ma_licence.jours_restants' | translate }}
          </span>
        </div>
        <div class="progress-track">
          <div class="progress-fill"
               [style.width]="progressPct() + '%'"
               [style.background]="joursColor()">
          </div>
        </div>
        <div class="pc-footer">
          <span>{{ licence().date_debut }}</span>
          <span>{{ licence().date_fin }}</span>
        </div>
      </div>

      <!-- Alerte expiration -->
      <div class="alerte-banner" *ngIf="licence().jours_restants <= 30">
        <div class="ab-icon">⚠️</div>
        <div class="ab-text">
          <strong>{{ licence().jours_restants > 0
              ? ('ma_licence.expiration_alerte' | translate:{ jours: licence().jours_restants })
              : ('ma_licence.expiree_alerte'    | translate) }}</strong>
          <div>{{ 'ma_licence.contacter_renouveler' | translate }}</div>
        </div>
        <p-button [label]="'ma_licence.demander_renouv' | translate"
                  severity="warn" (onClick)="demanderRenouvellement()" />
      </div>

      <!-- Contact -->
      <div class="contact-card">
        <div class="cc-title">📞 {{ 'ma_licence.besoin_aide' | translate }}</div>
        <div class="cc-body">
          <div class="cc-row">
            <span>{{ 'ma_licence.editeur' | translate }}</span>
            <strong>HADY GESMAN</strong>
          </div>
          <div class="cc-row">
            <span>{{ 'ma_licence.version' | translate }}</span>
            <span class="mono">2.2.0</span>
          </div>
          <div class="cc-row">
            <span>{{ 'ma_licence.support' | translate }}</span>
            <a class="cc-link" [href]="'mailto:' + supportEmail">{{ supportEmail }}</a>
          </div>
          <div class="cc-row">
            <span>{{ 'ma_licence.telephone' | translate }}</span>
            <span class="cc-phones">
              <a class="cc-link mono" *ngFor="let tel of supportPhones" [href]="tel.href">{{ tel.label }}</a>
            </span>
          </div>
        </div>
      </div>

    </div>

    <!-- Dialog demande de renouvellement -->
    <p-dialog [header]="'🔄 ' + ('ma_licence.renouv_dialog_titre' | translate)"
              [(visible)]="renouvDialogVisible" [modal]="true"
              [style]="{width:'440px'}" [draggable]="false">
      <div *ngIf="licence()">
        <p class="rd-info">{{ 'ma_licence.renouv_dialog_info' | translate }}</p>
        <div class="renouv-info">
          <div class="ri-row"><span>{{ 'ma_licence.type_abonnement' | translate }}</span><strong>{{ licence().type }}</strong></div>
          <div class="ri-row"><span>{{ 'ma_licence.date_expiration' | translate }}</span><span class="mono" [style.color]="joursColor()">{{ licence().date_fin }}</span></div>
        </div>
        <div class="rd-field">
          <label for="renouv-message">{{ 'ma_licence.message_optionnel' | translate }}</label>
          <textarea id="renouv-message" rows="4" class="rd-textarea" [(ngModel)]="messageRenouv"
                    [placeholder]="'ma_licence.message_placeholder' | translate"></textarea>
        </div>
        <div class="rd-tel">
          📞
          <a class="cc-link mono" *ngFor="let tel of supportPhones" [href]="tel.href">{{ tel.label }}</a>
        </div>
      </div>
      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler' | translate" severity="secondary"
                  (onClick)="renouvDialogVisible = false" />
        <p-button [label]="'ma_licence.envoyer_demande' | translate" severity="warn"
                  [loading]="envoiEnCours()" (onClick)="envoyerDemande()" />
      </ng-template>
    </p-dialog>

    <!-- Résultat d'une demande qui n'a pas pu être transmise automatiquement :
         on ne prétend jamais « envoyé » ; on donne des moyens qui marchent. -->
    <p-dialog header="📨 Transmettre votre demande" [(visible)]="secoursVisible" [modal]="true"
              [style]="{ width: '480px', maxWidth: '95vw' }" [draggable]="false">
      <p class="rd-info">
        Votre demande est <strong>enregistrée</strong>, mais elle n'a pas pu être transmise
        automatiquement à HADY GESMAN (connexion ou messagerie indisponible).
        Envoyez-la en un clic :
      </p>
      <div class="secours">
        <a class="sec-btn sec-wa" [href]="lienWhatsapp()" target="_blank" rel="noopener">💬 Envoyer par WhatsApp</a>
        @for (tel of supportPhones; track tel.href) {
          <a class="sec-btn" [href]="tel.href">📞 Appeler le {{ tel.label }}</a>
        }
        <button type="button" class="sec-btn" (click)="copierDemande()">📋 Copier le message</button>
        <a class="sec-btn" [href]="lienMail()">✉️ Ouvrir ma messagerie</a>
      </div>
      @if (erreurEnvoi()) {
        <details class="sec-detail"><summary>Détail technique</summary>{{ erreurEnvoi() }}</details>
      }
    </p-dialog>

    <!-- Aucune licence -->
    <div class="empty-state" *ngIf="!licence() && !loading()">
      <div style="font-size:48px">🔑</div>
      <div style="color:var(--text-3);margin-top:12px">{{ 'ma_licence.aucune_licence' | translate }}</div>
      <div style="color:var(--text-3);font-size:12px;margin-top:4px">{{ 'ma_licence.contacter_activer' | translate }}</div>
    </div>
  `,
  styles: [`
    .page-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:20px; }
    .page-title  { font-size:20px; font-weight:600; color:var(--text); margin:0 0 4px; }
    .page-sub    { font-size:12px; color:var(--text-3); }
    .licence-wrap { max-width:700px; }
    .statut-card { display:flex; align-items:center; gap:20px; border:2px solid; border-radius:16px; padding:24px 28px; margin-bottom:16px; }
    .statut-card.active { border-color:#10b981; background:rgba(16,185,129,0.06); }
    .statut-card.expire { border-color:#ef4444; background:rgba(239,68,68,0.06); }
    .statut-icon { font-size:40px; }
    .statut-info { flex:1; }
    .statut-label { font-size:18px; font-weight:700; color:var(--text); }
    .statut-type  { font-size:13px; color:var(--text-3); margin-top:2px; }
    .statut-jours { text-align:center; }
    .jours-val    { font-size:36px; font-weight:700; font-family:monospace; }
    .jours-label  { font-size:11px; color:var(--text-3); }
    .details-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:16px; }
    .detail-card  { background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:14px 16px; }
    .dc-label     { font-size:11px; color:var(--text-3); text-transform:uppercase; letter-spacing:1px; margin-bottom:6px; }
    .dc-value     { font-size:14px; font-weight:600; color:var(--text); }
    .dc-value.cle { font-family:monospace; font-size:12px; color:#f0c040; letter-spacing:1px; word-break:break-all; }
    .mono         { font-family:monospace; }
    .progress-card { background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:16px 18px; margin-bottom:16px; }
    .pc-header { display:flex; justify-content:space-between; font-size:12px; margin-bottom:10px; color:var(--text-2); }
    .progress-track { height:8px; background:var(--bg); border-radius:4px; overflow:hidden; }
    .progress-fill  { height:100%; border-radius:4px; transition:width 0.8s ease; }
    .pc-footer { display:flex; justify-content:space-between; font-size:11px; color:var(--text-3); margin-top:6px; font-family:monospace; }
    .alerte-banner { display:flex; align-items:center; gap:14px; background:rgba(245,158,11,0.08); border:1px solid rgba(245,158,11,0.3); border-radius:10px; padding:16px 18px; margin-bottom:16px; }
    .ab-icon { font-size:24px; flex-shrink:0; }
    .ab-text { flex:1; font-size:13px; color:var(--text); }
    .ab-text div { font-size:12px; color:var(--text-2); margin-top:4px; }
    .contact-card { background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:16px 18px; }
    .cc-title { font-size:13px; font-weight:600; color:var(--text); margin-bottom:12px; }
    .cc-body  { display:flex; flex-direction:column; gap:8px; }
    .cc-row   { display:flex; justify-content:space-between; font-size:13px; padding:6px 0; border-bottom:1px solid rgba(42,63,95,0.3); }
    .cc-row:last-child { border-bottom:none; }
    .cc-row span:first-child { color:var(--text-3); }
    .cc-link  { color:#93c5fd; text-decoration:none; }
    .cc-link:hover { text-decoration:underline; }
    .cc-phones { display:flex; gap:14px; }
    .empty-state { text-align:center; padding:60px; }
    .rd-info  { font-size:13px; color:var(--text-2); margin:0 0 14px; }
    .renouv-info { background:rgba(11,15,26,0.4); border:1px solid var(--border); border-radius:8px; padding:10px 14px; }
    .ri-row   { display:flex; justify-content:space-between; font-size:13px; padding:4px 0; }
    .ri-row span:first-child { color:var(--text-3); }
    .rd-field { margin-top:14px; display:flex; flex-direction:column; gap:6px; }
    .rd-field label { font-size:12px; color:var(--text-2); }
    .rd-textarea { width:100%; background:var(--bg); border:1px solid var(--border); border-radius:8px; color:var(--text); padding:10px 12px; font-size:13px; font-family:inherit; resize:vertical; }
    .rd-textarea:focus { outline:none; border-color:#3b82f6; }
    .rd-tel   { display:flex; align-items:center; gap:14px; font-size:13px; margin-top:14px; }
    .compteur { display:flex; align-items:center; gap:16px; flex-wrap:wrap; border:1px solid; border-radius:12px; padding:14px 18px; margin-bottom:16px; }
    .cpt-jours { min-width:90px; text-align:center; }
    .cpt-val  { font-size:28px; font-weight:800; font-variant-numeric:tabular-nums; }
    .cpt-texte { flex:1 1 220px; font-size:13px; color:var(--text); line-height:1.5; }
    .cpt-ok        { background:rgba(16,185,129,.08); border-color:rgba(16,185,129,.4); }
    .cpt-ok .cpt-val { color:#059669; }
    .cpt-attention { background:rgba(234,179,8,.12); border-color:#ca8a04; }
    .cpt-attention .cpt-val { color:#a16207; }
    .cpt-urgent    { background:rgba(234,88,12,.12); border-color:#ea580c; }
    .cpt-urgent .cpt-val { color:#c2410c; }
    .cpt-critique, .cpt-expiree { background:rgba(220,38,38,.12); border-color:#dc2626; }
    .cpt-critique .cpt-val, .cpt-expiree .cpt-val { color:#dc2626; }
    .secours  { display:flex; flex-direction:column; gap:8px; }
    .sec-btn  { display:block; text-align:left; padding:10px 14px; border-radius:8px; border:1px solid var(--border); background:var(--surface); color:var(--text); font-size:14px; text-decoration:none; cursor:pointer; font-family:inherit; }
    .sec-btn:hover, .sec-btn:focus-visible { border-color:#00d4aa; outline:none; }
    .sec-wa   { background:#128c3e; border-color:#128c3e; color:#fff; font-weight:600; }
    .sec-detail { margin-top:12px; font-size:11px; color:var(--text-3); word-break:break-word; }
  `]
})
export class MaLicenceComponent implements OnInit {
  licence = signal<any>(null);
  loading = signal(true);

  renouvDialogVisible = false;
  messageRenouv       = '';
  envoiEnCours        = signal(false);

  compteur = inject(LicenceCompteurService);
  /** Jours restants en temps réel (même calcul que le badge de la barre du haut). */
  jours(): number {
    const j = this.compteur.joursRestants();
    return j === null ? (this.licence()?.jours_restants || 0) : Math.max(j, 0);
  }

  secoursVisible = false;
  erreurEnvoi    = signal('');
  private texteDemande = { sujet: '', corps: '' };

  supportEmail  = SUPPORT_EMAIL;
  supportPhones = SUPPORT_PHONES.map(t => ({ label: t, href: 'tel:' + t.replace(/\s/g, '') }));

  private translate = inject(TranslateService);

  constructor(
    private licencesService: LicencesService,
    public auth: AuthService,
    private msg: MessageService
  ) {}

  ngOnInit() {
    this.compteur.demarrer();
    this.licencesService.getLicences().subscribe({
      next: res => {
        const licences = res.results || res;
        // Tenant effectif : école impersonée (super_admin) sinon tenant du user.
        // L'API /licences/ renvoie TOUTES les licences au super_admin → on doit
        // filtrer sur l'ID exact, sinon on affiche par erreur la 1ʳᵉ école.
        const tenantId = this.auth.effectiveTenantId;
        const maLicence = tenantId
          ? licences.find((l: any) => l.tenant === tenantId)
          : null;
        this.licence.set(maLicence || (licences.length === 1 ? licences[0] : null));
        this.loading.set(false);
      },
      error: () => this.loading.set(false)
    });
  }

  joursColor(): string {
    const j = this.jours();
    return j <= 7 ? '#ef4444' : j <= 30 ? '#f59e0b' : '#10b981';
  }

  progressPct(): number {
    const j = this.jours();
    return Math.min(Math.round((j / 365) * 100), 100);
  }

  demanderRenouvellement() {
    this.renouvDialogVisible = true;
  }

  envoyerDemande() {
    const lic = this.licence();
    if (!lic) return;
    this.envoiEnCours.set(true);
    this.licencesService.demanderRenouvellement(lic.id, this.messageRenouv.trim()).subscribe({
      next: res => {
        this.envoiEnCours.set(false);
        this.renouvDialogVisible = false;
        if (res.recue ?? res.envoye) {
          this.msg.add({
            severity: 'success', life: 7000,
            summary:  this.translate.instant('ma_licence.demande_envoyee'),
            detail:   this.translate.instant('ma_licence.contactera_24h'),
          });
          this.messageRenouv = '';
        } else {
          this.ouvrirSecours(res.sujet, res.corps, res.erreur);
        }
      },
      error: err => {
        this.envoiEnCours.set(false);
        this.renouvDialogVisible = false;
        this.ouvrirSecours(undefined, undefined, err?.message || 'Serveur injoignable');
      },
    });
  }

  /** La demande n'a pas atteint HADY GESMAN : proposer des canaux qui marchent. */
  private ouvrirSecours(sujet?: string, corps?: string, erreur?: string) {
    const lic = this.licence();
    this.texteDemande = {
      sujet: sujet || `[SAGI SCHOOL] Demande de renouvellement — ${lic?.type || ''}`,
      corps: corps || [
        'Demande de renouvellement de licence SAGI SCHOOL',
        `Licence   : ${lic?.type} — ${lic?.cle_licence}`,
        `Expire le : ${lic?.date_fin} (${this.jours()} jours restants)`,
        '', this.messageRenouv.trim(),
      ].join('\n'),
    };
    this.erreurEnvoi.set(erreur || '');
    this.secoursVisible = true;
  }

  lienWhatsapp(): string {
    return `https://wa.me/${SUPPORT_WHATSAPP}?text=${encodeURIComponent(this.texteDemande.corps)}`;
  }

  lienMail(): string {
    return `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent(this.texteDemande.sujet)}`
         + `&body=${encodeURIComponent(this.texteDemande.corps)}`;
  }

  copierDemande() {
    navigator.clipboard?.writeText(this.texteDemande.corps).then(
      () => this.msg.add({ severity: 'info', summary: 'Copié', detail: 'Collez le message dans WhatsApp ou un e-mail.' }),
      () => this.msg.add({ severity: 'warn', summary: 'Copie impossible', detail: 'Sélectionnez le texte manuellement.' }),
    );
  }
}
