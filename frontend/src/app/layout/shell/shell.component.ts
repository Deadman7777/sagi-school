import { Component, signal } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { CommonModule } from '@angular/common';
import { AuthService } from '../../core/services/auth.service';
import { LangueService } from '../../core/services/langue.service';
import { AvatarModule } from 'primeng/avatar';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';
import { TranslateModule } from '@ngx-translate/core';

interface NavSection {
  labelKey: string;
  items: NavItem[];
}
interface NavItem {
  labelKey: string;
  icon: string;
  route: string;
}

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, CommonModule,
            AvatarModule, ToastModule, TranslateModule],
  providers: [MessageService],
  template: `
    <p-toast />
    <div class="shell">
      <aside class="sidebar" [class.collapsed]="collapsed()">

        <div class="logo-zone">
          <div class="logo-text" *ngIf="!collapsed()">
            <span class="logo-main">{{ 'app.name' | translate }}</span>
            <span class="logo-sub">{{ 'app.by' | translate }}</span>
          </div>
          <button class="collapse-btn" (click)="collapsed.update(v => !v)">
            {{ collapsed() ? '→' : '←' }}
          </button>
        </div>

        <div class="role-badge" *ngIf="!collapsed()">
          <ng-container *ngIf="isSuperAdmin()">
            <div class="rb-status gold">👑 HADY GESMAN</div>
            <div class="rb-sub">{{ roleLabel() }}</div>
          </ng-container>
          <ng-container *ngIf="!isSuperAdmin()">
            <div class="rb-status green">🏫 {{ auth.currentUser()?.nom }}</div>
            <div class="rb-sub">{{ roleLabel() }}</div>
          </ng-container>
        </div>

        <nav class="nav">
          <ng-container *ngFor="let section of navSectionsFiltrees()">
            <div class="nav-section-label" *ngIf="!collapsed()">
              {{ section.labelKey | translate }}
            </div>
            <ng-container *ngFor="let item of section.items">
              <a class="nav-item" [routerLink]="item.route"
                 routerLinkActive="active" [title]="item.labelKey | translate">
                <span class="nav-icon">{{ item.icon }}</span>
                <span *ngIf="!collapsed()">{{ item.labelKey | translate }}</span>
              </a>
            </ng-container>
          </ng-container>
        </nav>

        <div class="sidebar-footer" *ngIf="!collapsed()">
          <p-avatar [label]="initials()" styleClass="user-avatar" />
          <div class="user-info">
            <div class="user-name">{{ auth.currentUser()?.nom }}</div>
            <div class="user-role">{{ roleLabel() }}</div>
          </div>
          <button class="logout-btn" (click)="auth.logout()"
                  [title]="'auth.logout' | translate">⏻</button>
        </div>

      </aside>

      <div class="main">
        <header class="topbar">
          <span class="page-title">{{ pageTitle() | translate }}</span>
          <div class="topbar-right">
            <!-- Sélecteur de langue -->
            <div class="langue-selector">
              <button class="langue-btn"
                      *ngFor="let l of langue.langues"
                      [class.active]="langue.langueActuelle() === l.code"
                      (click)="langue.changerLangue(l.code)"
                      [title]="l.label">
                {{ l.flag }}
              </button>
            </div>
            <span class="badge-gold" *ngIf="isSuperAdmin()">👑 Super Admin</span>
            <span class="badge-blue" *ngIf="!isSuperAdmin()">📅 2025-2026</span>
          </div>
        </header>
        <main class="content">
          <router-outlet />
        </main>
      </div>
    </div>
  `,
  styles: [`
    .shell { display:flex; height:100vh; overflow:hidden; background:#0b0f1a; }
    .sidebar { width:240px; min-width:240px; background:#111827; border-right:1px solid #1e2d45; display:flex; flex-direction:column; transition:width 0.2s, min-width 0.2s; overflow:hidden; }
    .sidebar.collapsed { width:60px; min-width:60px; }
    .logo-zone { display:flex; align-items:center; justify-content:space-between; padding:18px 14px 14px; border-bottom:1px solid #1e2d45; }
    .logo-main { display:block; font-size:15px; font-weight:700; color:#00d4aa; }
    .logo-sub  { display:block; font-size:10px; color:#64748b; text-transform:uppercase; letter-spacing:1px; }
    .collapse-btn { background:transparent; border:1px solid #1e2d45; color:#94a3b8; border-radius:6px; padding:4px 8px; cursor:pointer; font-size:12px; flex-shrink:0; }
    .collapse-btn:hover { border-color:#00d4aa; color:#00d4aa; }
    .role-badge { margin:10px 12px; background:#0f1a2e; border:1px solid #1e2d45; border-radius:8px; padding:8px 12px; }
    .rb-status { font-size:12px; font-weight:600; }
    .rb-status.gold  { color:#f0c040; }
    .rb-status.green { color:#10b981; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .rb-sub { font-size:10px; color:#64748b; margin-top:2px; }
    .nav { flex:1; padding:8px 0; overflow-y:auto; }
    .nav-section-label { font-size:10px; color:#64748b; text-transform:uppercase; letter-spacing:1.5px; padding:10px 14px 4px; }
    .nav-item { display:flex; align-items:center; gap:10px; padding:9px 14px; cursor:pointer; border-left:3px solid transparent; color:#94a3b8; font-size:13px; text-decoration:none; transition:all 0.15s; }
    .nav-item:hover { background:#1a2235; color:#e8f0fe; }
    .nav-item.active { background:rgba(0,212,170,0.08); border-left-color:#00d4aa; color:#00d4aa; font-weight:500; }
    .nav-icon { font-size:16px; width:20px; text-align:center; flex-shrink:0; }
    .sidebar-footer { display:flex; align-items:center; gap:10px; padding:14px; border-top:1px solid #1e2d45; }
    ::ng-deep .user-avatar.p-avatar { background:linear-gradient(135deg,#00d4aa,#0099ff) !important; color:#000 !important; font-weight:700 !important; width:32px !important; height:32px !important; font-size:12px !important; }
    .user-info { flex:1; overflow:hidden; }
    .user-name { font-size:12px; font-weight:600; color:#e8f0fe; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
    .user-role { font-size:10px; color:#64748b; }
    .logout-btn { background:transparent; border:1px solid #1e2d45; color:#64748b; border-radius:6px; padding:4px 8px; cursor:pointer; font-size:14px; }
    .logout-btn:hover { border-color:#ef4444; color:#ef4444; }
    .main { flex:1; display:flex; flex-direction:column; overflow:hidden; }
    .topbar { height:52px; background:#111827; border-bottom:1px solid #1e2d45; display:flex; align-items:center; justify-content:space-between; padding:0 24px; flex-shrink:0; }
    .page-title { font-size:18px; font-weight:600; color:#e8f0fe; }
    .topbar-right { display:flex; gap:8px; align-items:center; }
    .badge-gold { font-size:11px; padding:3px 12px; border-radius:20px; background:rgba(240,192,64,0.15); color:#f0c040; }
    .badge-blue { font-size:11px; padding:3px 12px; border-radius:20px; background:rgba(0,153,255,0.15); color:#0099ff; }
    .langue-selector { display:flex; gap:4px; }
    .langue-btn { background:transparent; border:1px solid #1e2d45; border-radius:6px; padding:3px 7px; cursor:pointer; font-size:14px; transition:all 0.15s; }
    .langue-btn:hover  { border-color:#2a3f5f; }
    .langue-btn.active { border-color:#00d4aa; background:rgba(0,212,170,0.1); }
    .content { flex:1; overflow-y:auto; padding:24px; }
    [dir="rtl"] .sidebar { border-right:none; border-left:1px solid #1e2d45; }
    [dir="rtl"] .nav-item { border-left:none; border-right:3px solid transparent; }
    [dir="rtl"] .nav-item.active { border-right-color:#00d4aa; }
  `]
})
export class ShellComponent {
  collapsed = signal(false);

  navSuperAdmin: NavSection[] = [
    { labelKey: 'nav.principal', items: [
      { labelKey: 'nav.dashboard', icon: '📊', route: '/dashboard' },
      { labelKey: 'nav.licences', icon: '🔐', route: '/licences' },
    ]}
  ];

  navEcole: NavSection[] = [
    { labelKey: 'nav.principal', items: [
      { labelKey: 'nav.dashboard',    icon: '📊', route: '/dashboard' },
      { labelKey: 'nav.eleves',       icon: '👥', route: '/eleves' },
      { labelKey: 'nav.paiements',    icon: '💰', route: '/paiements' },
    ]},
    { labelKey: 'nav.comptabilite_section', items: [
      { labelKey: 'nav.comptabilite', icon: '📒', route: '/comptabilite' },
      { labelKey: 'nav.fiscal',       icon: '📋', route: '/fiscal' },
      { labelKey: 'nav.rh', icon: '👥', route: '/rh' },
      { labelKey: 'nav.suivi',        icon: '📅', route: '/suivi-mensuel' },
    ]},
    { labelKey: 'nav.systeme', items: [
      { labelKey: 'nav.ma_licence',   icon: '🔑', route: '/ma-licence' },
      { labelKey: 'nav.parametres',   icon: '⚙️', route: '/parametres' },
    ]}
  ];

  constructor(public auth: AuthService, public langue: LangueService) {}

  isSuperAdmin() { return this.auth.currentUser()?.role === 'SUPER_ADMIN'; }
  navSectionsFiltrees() { return this.isSuperAdmin() ? this.navSuperAdmin : this.navEcole; }

  roleLabel(): string {
    const labels: Record<string, string> = {
      'SUPER_ADMIN': 'Super Admin', 'ADMIN_ECOLE': 'Admin École',
      'COMPTABLE': 'Comptable', 'CAISSIER': 'Caissier', 'LECTURE': 'Lecture seule',
    };
    return labels[this.auth.currentUser()?.role || ''] || '';
  }

  initials(): string { return (this.auth.currentUser()?.nom || 'U').substring(0, 2).toUpperCase(); }

  pageTitle(): string {
    const titles: Record<string, string> = {
      '/dashboard':    this.isSuperAdmin() ? 'nav.dashboard' : 'nav.dashboard',
      '/eleves':       'nav.eleves',
      '/paiements':    'nav.paiements',
      '/comptabilite': 'nav.comptabilite',
      '/rh': 'nav.rh',
      '/fiscal':       'nav.fiscal',
      '/suivi-mensuel': 'nav.suivi',
      '/licences':     'nav.licences',
      '/ma-licence':   'nav.ma_licence',
      '/parametres':   'nav.parametres',
    };
    return titles[window.location.pathname] || 'app.name';
  }
}
