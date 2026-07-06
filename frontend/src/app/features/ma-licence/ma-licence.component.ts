import { Component, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { LicencesService } from '../../core/services/licences.service';
import { AuthService } from '../../core/services/auth.service';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';
import { TranslateModule, TranslateService } from '@ngx-translate/core';

/** Coordonnées support HADY GESMAN — à modifier ici uniquement. */
const SUPPORT_EMAIL  = 'hadygesman@gmail.com';
const SUPPORT_PHONES = ['+221 77 123 45 67', '+221 78 987 65 43'];

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
          <div class="jours-val">{{ licence().jours_restants }}</div>
          <div class="jours-label">{{ 'ma_licence.jours_restants' | translate }}</div>
        </div>
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
            {{ licence().jours_restants }} {{ 'ma_licence.jours_restants' | translate }}
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
          <strong>{{ 'ma_licence.expiration_alerte' | translate:{ jours: licence().jours_restants } }}</strong>
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

    <!-- Aucune licence -->
    <div class="empty-state" *ngIf="!licence() && !loading()">
      <div style="font-size:48px">🔑</div>
      <div style="color:#64748b;margin-top:12px">{{ 'ma_licence.aucune_licence' | translate }}</div>
      <div style="color:#64748b;font-size:12px;margin-top:4px">{{ 'ma_licence.contacter_activer' | translate }}</div>
    </div>
  `,
  styles: [`
    .page-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:20px; }
    .page-title  { font-size:20px; font-weight:600; color:#e8f0fe; margin:0 0 4px; }
    .page-sub    { font-size:12px; color:#64748b; }
    .licence-wrap { max-width:700px; }
    .statut-card { display:flex; align-items:center; gap:20px; border:2px solid; border-radius:16px; padding:24px 28px; margin-bottom:16px; }
    .statut-card.active { border-color:#10b981; background:rgba(16,185,129,0.06); }
    .statut-card.expire { border-color:#ef4444; background:rgba(239,68,68,0.06); }
    .statut-icon { font-size:40px; }
    .statut-info { flex:1; }
    .statut-label { font-size:18px; font-weight:700; color:#e8f0fe; }
    .statut-type  { font-size:13px; color:#64748b; margin-top:2px; }
    .statut-jours { text-align:center; }
    .jours-val    { font-size:36px; font-weight:700; font-family:monospace; }
    .jours-label  { font-size:11px; color:#64748b; }
    .details-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin-bottom:16px; }
    .detail-card  { background:#1e2d45; border:1px solid #2a3f5f; border-radius:10px; padding:14px 16px; }
    .dc-label     { font-size:11px; color:#64748b; text-transform:uppercase; letter-spacing:1px; margin-bottom:6px; }
    .dc-value     { font-size:14px; font-weight:600; color:#e8f0fe; }
    .dc-value.cle { font-family:monospace; font-size:12px; color:#f0c040; letter-spacing:1px; word-break:break-all; }
    .mono         { font-family:monospace; }
    .progress-card { background:#1e2d45; border:1px solid #2a3f5f; border-radius:10px; padding:16px 18px; margin-bottom:16px; }
    .pc-header { display:flex; justify-content:space-between; font-size:12px; margin-bottom:10px; color:#94a3b8; }
    .progress-track { height:8px; background:#0b0f1a; border-radius:4px; overflow:hidden; }
    .progress-fill  { height:100%; border-radius:4px; transition:width 0.8s ease; }
    .pc-footer { display:flex; justify-content:space-between; font-size:11px; color:#64748b; margin-top:6px; font-family:monospace; }
    .alerte-banner { display:flex; align-items:center; gap:14px; background:rgba(245,158,11,0.08); border:1px solid rgba(245,158,11,0.3); border-radius:10px; padding:16px 18px; margin-bottom:16px; }
    .ab-icon { font-size:24px; flex-shrink:0; }
    .ab-text { flex:1; font-size:13px; color:#e8f0fe; }
    .ab-text div { font-size:12px; color:#94a3b8; margin-top:4px; }
    .contact-card { background:#1e2d45; border:1px solid #2a3f5f; border-radius:10px; padding:16px 18px; }
    .cc-title { font-size:13px; font-weight:600; color:#e8f0fe; margin-bottom:12px; }
    .cc-body  { display:flex; flex-direction:column; gap:8px; }
    .cc-row   { display:flex; justify-content:space-between; font-size:13px; padding:6px 0; border-bottom:1px solid rgba(42,63,95,0.3); }
    .cc-row:last-child { border-bottom:none; }
    .cc-row span:first-child { color:#64748b; }
    .cc-link  { color:#93c5fd; text-decoration:none; }
    .cc-link:hover { text-decoration:underline; }
    .cc-phones { display:flex; gap:14px; }
    .empty-state { text-align:center; padding:60px; }
    .rd-info  { font-size:13px; color:#94a3b8; margin:0 0 14px; }
    .renouv-info { background:rgba(11,15,26,0.4); border:1px solid #2a3f5f; border-radius:8px; padding:10px 14px; }
    .ri-row   { display:flex; justify-content:space-between; font-size:13px; padding:4px 0; }
    .ri-row span:first-child { color:#64748b; }
    .rd-field { margin-top:14px; display:flex; flex-direction:column; gap:6px; }
    .rd-field label { font-size:12px; color:#94a3b8; }
    .rd-textarea { width:100%; background:#0b0f1a; border:1px solid #2a3f5f; border-radius:8px; color:#e8f0fe; padding:10px 12px; font-size:13px; font-family:inherit; resize:vertical; }
    .rd-textarea:focus { outline:none; border-color:#3b82f6; }
    .rd-tel   { display:flex; align-items:center; gap:14px; font-size:13px; margin-top:14px; }
  `]
})
export class MaLicenceComponent implements OnInit {
  licence = signal<any>(null);
  loading = signal(true);

  renouvDialogVisible = false;
  messageRenouv       = '';
  envoiEnCours        = signal(false);

  supportEmail  = SUPPORT_EMAIL;
  supportPhones = SUPPORT_PHONES.map(t => ({ label: t, href: 'tel:' + t.replace(/\s/g, '') }));

  private translate = inject(TranslateService);

  constructor(
    private licencesService: LicencesService,
    public auth: AuthService,
    private msg: MessageService
  ) {}

  ngOnInit() {
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
    const j = this.licence()?.jours_restants || 0;
    return j <= 7 ? '#ef4444' : j <= 30 ? '#f59e0b' : '#10b981';
  }

  progressPct(): number {
    const j = this.licence()?.jours_restants || 0;
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
        if (res.envoye) {
          this.msg.add({
            severity: 'success',
            summary:  this.translate.instant('ma_licence.demande_envoyee'),
            detail:   this.translate.instant('ma_licence.contactera_24h')
          });
        } else {
          this.ouvrirMailto(res.sujet, res.corps);
        }
      },
      error: () => {
        this.envoiEnCours.set(false);
        this.renouvDialogVisible = false;
        this.ouvrirMailto();
      }
    });
  }

  /** SMTP indisponible (mode local) : ouvre le client mail, message pré-rempli. */
  private ouvrirMailto(sujet?: string, corps?: string) {
    const lic = this.licence();
    const s = sujet || `[SAGI SCHOOL] Demande de renouvellement — ${lic?.type || ''}`;
    const c = corps || [
      `Licence   : ${lic?.type} — ${lic?.cle_licence}`,
      `Expire le : ${lic?.date_fin} (${lic?.jours_restants} jours restants)`,
      '',
      this.messageRenouv.trim(),
    ].join('\n');
    window.location.href =
      `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent(s)}&body=${encodeURIComponent(c)}`;
    this.msg.add({
      severity: 'info',
      summary:  this.translate.instant('ma_licence.messagerie_titre'),
      detail:   this.translate.instant('ma_licence.messagerie_detail')
    });
  }
}
