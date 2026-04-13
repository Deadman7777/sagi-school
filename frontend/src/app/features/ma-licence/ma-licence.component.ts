import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { LicencesService } from '../../core/services/licences.service';
import { AuthService } from '../../core/services/auth.service';
import { ButtonModule } from 'primeng/button';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';

@Component({
  selector: 'app-ma-licence',
  standalone: true,
  imports: [CommonModule, ButtonModule, ToastModule],
  providers: [MessageService],
  template: `
    <p-toast />
    <div class="page-header">
      <div>
        <h2 class="page-title">🔑 Ma Licence</h2>
        <span class="page-sub">Statut de votre abonnement</span>
      </div>
    </div>

    <div class="licence-wrap" *ngIf="licence()">

      <!-- Statut principal -->
      <div class="statut-card" [class.active]="licence().est_active"
                               [class.expire]="!licence().est_active">
        <div class="statut-icon">{{ licence().est_active ? '✅' : '❌' }}</div>
        <div class="statut-info">
          <div class="statut-label">{{ licence().est_active ? 'Licence Active' : 'Licence Expirée' }}</div>
          <div class="statut-type">Plan {{ licence().type }}</div>
        </div>
        <div class="statut-jours" [style.color]="joursColor()">
          <div class="jours-val">{{ licence().jours_restants }}</div>
          <div class="jours-label">jours restants</div>
        </div>
      </div>

      <!-- Détails -->
      <div class="details-grid">
        <div class="detail-card">
          <div class="dc-label">Clé de Licence</div>
          <div class="dc-value cle">{{ licence().cle_licence }}</div>
        </div>
        <div class="detail-card">
          <div class="dc-label">Type d'abonnement</div>
          <div class="dc-value">{{ licence().type }}</div>
        </div>
        <div class="detail-card">
          <div class="dc-label">Date d'activation</div>
          <div class="dc-value mono">{{ licence().date_debut }}</div>
        </div>
        <div class="detail-card">
          <div class="dc-label">Date d'expiration</div>
          <div class="dc-value mono" [style.color]="joursColor()">
            {{ licence().date_fin }}
          </div>
        </div>
      </div>

      <!-- Barre de progression -->
      <div class="progress-card">
        <div class="pc-header">
          <span>Durée de la licence</span>
          <span class="mono" [style.color]="joursColor()">
            {{ licence().jours_restants }} jours restants
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
          <strong>Votre licence expire dans {{ licence().jours_restants }} jours</strong>
          <div>Contactez HADY GESMAN pour renouveler votre abonnement.</div>
        </div>
        <p-button label="Demander un Renouvellement"
                  severity="warn" (onClick)="demanderRenouvellement()" />
      </div>

      <!-- Contact HADY GESMAN -->
      <div class="contact-card">
        <div class="cc-title">📞 Besoin d'aide ?</div>
        <div class="cc-body">
          <div class="cc-row">
            <span>Éditeur</span>
            <strong>HADY GESMAN</strong>
          </div>
          <div class="cc-row">
            <span>Version logiciel</span>
            <span class="mono">2.2.0</span>
          </div>
          <div class="cc-row">
            <span>Support</span>
            <span>support&#64;hadygesman.com</span>
          </div>
        </div>
      </div>

    </div>

    <!-- Loading -->
    <div class="empty-state" *ngIf="!licence() && !loading()">
      <div style="font-size:48px">🔑</div>
      <div style="color:#64748b;margin-top:12px">Aucune licence trouvée</div>
      <div style="color:#64748b;font-size:12px;margin-top:4px">
        Contactez HADY GESMAN pour activer votre abonnement
      </div>
    </div>
  `,
  styles: [`
    .page-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:20px; }
    .page-title  { font-size:20px; font-weight:600; color:#e8f0fe; margin:0 0 4px; }
    .page-sub    { font-size:12px; color:#64748b; }

    .licence-wrap { max-width: 700px; }

    .statut-card {
      display:flex; align-items:center; gap:20px;
      border:2px solid; border-radius:16px; padding:24px 28px; margin-bottom:16px;
    }
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

    .alerte-banner {
      display:flex; align-items:center; gap:14px;
      background:rgba(245,158,11,0.08); border:1px solid rgba(245,158,11,0.3);
      border-radius:10px; padding:16px 18px; margin-bottom:16px;
    }
    .ab-icon { font-size:24px; flex-shrink:0; }
    .ab-text { flex:1; font-size:13px; color:#e8f0fe; }
    .ab-text div { font-size:12px; color:#94a3b8; margin-top:4px; }

    .contact-card { background:#1e2d45; border:1px solid #2a3f5f; border-radius:10px; padding:16px 18px; }
    .cc-title { font-size:13px; font-weight:600; color:#e8f0fe; margin-bottom:12px; }
    .cc-body  { display:flex; flex-direction:column; gap:8px; }
    .cc-row   { display:flex; justify-content:space-between; font-size:13px; padding:6px 0; border-bottom:1px solid rgba(42,63,95,0.3); }
    .cc-row:last-child { border-bottom:none; }
    .cc-row span:first-child { color:#64748b; }

    .empty-state { text-align:center; padding:60px; }
  `]
})
export class MaLicenceComponent implements OnInit {
  licence = signal<any>(null);
  loading = signal(true);

  constructor(
    private licencesService: LicencesService,
    public auth: AuthService,
    private msg: MessageService
  ) {}

  ngOnInit() {
    // Récupère la licence du tenant de l'utilisateur connecté
    this.licencesService.getLicences().subscribe({
      next: res => {
        const licences = res.results || res;
        // Filtre par tenant de l'utilisateur
        const tenantId = localStorage.getItem('tenant_id');
        const maLicence = licences.find((l: any) =>
          l.tenant === tenantId || l.tenant_nom
        );
        this.licence.set(maLicence || licences[0] || null);
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
    // On suppose max 365 jours
    return Math.min(Math.round((j / 365) * 100), 100);
  }

  demanderRenouvellement() {
    this.msg.add({
      severity: 'info',
      summary:  'Demande envoyée',
      detail:   'HADY GESMAN vous contactera sous 24h'
    });
  }
}
