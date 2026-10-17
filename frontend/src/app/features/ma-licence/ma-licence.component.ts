import { Component, OnInit, effect, inject, signal, untracked } from '@angular/core';
import { CommonModule } from '@angular/common';
import { LicencesService } from '../../core/services/licences.service';
import { AuthService } from '../../core/services/auth.service';
import { LicenceCompteurService } from '../../core/services/licence-compteur.service';
import { ButtonModule } from 'primeng/button';
import { TranslateModule } from '@ngx-translate/core';

/** Coordonnées support HADY GESMAN — à modifier ici uniquement. */
const SUPPORT_EMAIL  = 'hadygesman@gmail.com';
const SUPPORT_PHONES = ['+221 70 328 61 51', '+221 78 429 78 30'];

@Component({
  selector: 'app-ma-licence',
  standalone: true,
  imports: [CommonModule, ButtonModule, TranslateModule],
  template: `
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
        <p-button label="Renouveler maintenant" icon="pi pi-credit-card"
                  [severity]="compteur.niveau() === 'ok' ? 'secondary' : 'warn'"
                  (onClick)="compteur.ouvrirRenouvellement()" />
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
        <p-button label="Renouveler maintenant" severity="warn"
                  (onClick)="compteur.ouvrirRenouvellement()" />
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
  `]
})
export class MaLicenceComponent implements OnInit {
  licence = signal<any>(null);
  loading = signal(true);

  compteur = inject(LicenceCompteurService);
  /** Jours restants en temps réel (même calcul que le badge de la barre du haut). */
  jours(): number {
    const j = this.compteur.joursRestants();
    return j === null ? (this.licence()?.jours_restants || 0) : Math.max(j, 0);
  }

  supportEmail  = SUPPORT_EMAIL;
  supportPhones = SUPPORT_PHONES.map(t => ({ label: t, href: 'tel:' + t.replace(/\s/g, '') }));

  constructor(
    private licencesService: LicencesService,
    public auth: AuthService,
  ) {
    // Renouvellement constaté par le compteur : la fiche se relit.
    effect(() => {
      const fin = this.compteur.alerte()?.date_fin;
      const affichee = untracked(() => this.licence()?.date_fin);
      if (fin && affichee && fin !== affichee) untracked(() => this.charger());
    });
  }

  ngOnInit() {
    this.compteur.demarrer();
    this.charger();
  }

  private charger() {
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
}
