#!/bin/bash
# ============================================================
# HADY GESMAN — Setup Angular + PrimeNG
# Exécuter depuis : ~/Documents/hady-gesman/frontend/
# ============================================================

# ── ENVIRONMENTS ────────────────────────────────────────────
mkdir -p src/environments

cat > src/environments/environment.ts << 'EOF'
export const environment = {
  production: false,
  apiUrl: 'http://127.0.0.1:8765/api'
};
EOF

cat > src/environments/environment.prod.ts << 'EOF'
export const environment = {
  production: true,
  apiUrl: '/api'
};
EOF

# ── APP.CONFIG.TS ────────────────────────────────────────────
cat > src/app/app.config.ts << 'EOF'
import { ApplicationConfig, provideZoneChangeDetection } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { providePrimeNG } from 'primeng/config';
import Aura from '@primeuix/themes/aura';
import { routes } from './app.routes';
import { authInterceptor } from './core/interceptors/auth.interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes),
    provideHttpClient(withInterceptors([authInterceptor])),
    provideAnimationsAsync(),
    providePrimeNG({
      theme: {
        preset: Aura,
        options: {
          darkModeSelector: '.dark-mode',
          cssLayer: { name: 'primeng', order: 'tailwind-base, primeng, tailwind-utilities' }
        }
      }
    })
  ]
};
EOF

# ── APP.ROUTES.TS ────────────────────────────────────────────
cat > src/app/app.routes.ts << 'EOF'
import { Routes } from '@angular/router';
import { authGuard } from './core/guards/auth.guard';

export const routes: Routes = [
  {
    path: 'login',
    loadComponent: () => import('./features/auth/login/login.component').then(m => m.LoginComponent)
  },
  {
    path: '',
    loadComponent: () => import('./layout/shell/shell.component').then(m => m.ShellComponent),
    canActivate: [authGuard],
    children: [
      { path: '', redirectTo: 'dashboard', pathMatch: 'full' },
      {
        path: 'dashboard',
        loadComponent: () => import('./features/dashboard/dashboard.component').then(m => m.DashboardComponent)
      },
      {
        path: 'eleves',
        loadComponent: () => import('./features/eleves/liste/eleves-liste.component').then(m => m.ElevesListeComponent)
      },
      {
        path: 'paiements',
        loadComponent: () => import('./features/paiements/paiements.component').then(m => m.PaiementsComponent)
      },
      {
        path: 'comptabilite',
        loadComponent: () => import('./features/comptabilite/comptabilite.component').then(m => m.ComptabiliteComponent)
      },
      {
        path: 'licences',
        loadComponent: () => import('./features/licences/licences.component').then(m => m.LicencesComponent)
      },
    ]
  },
  { path: '**', redirectTo: '' }
];
EOF

# ── APP.COMPONENT ────────────────────────────────────────────
cat > src/app/app.component.ts << 'EOF'
import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet],
  template: '<router-outlet />'
})
export class AppComponent {}
EOF

# ── CORE : MODELS ────────────────────────────────────────────
mkdir -p src/app/core/{guards,interceptors,services,models}

cat > src/app/core/models/user.model.ts << 'EOF'
export interface User {
  id: string;
  nom: string;
  prenom: string;
  email: string;
  role: 'SUPER_ADMIN' | 'ADMIN_ECOLE' | 'COMPTABLE' | 'CAISSIER' | 'LECTURE';
  tenant?: string;
}

export interface AuthTokens {
  access: string;
  refresh: string;
}
EOF

cat > src/app/core/models/eleve.model.ts << 'EOF'
export interface Section {
  id: string;
  nom: string;
  frais_inscription: number;
  frais_mensualite: number;
  frais_uniforme: number;
  frais_fournitures: number;
  frais_yendu: number;
  total_annuel: number;
}

export interface Eleve {
  id: string;
  numero: number;
  nom_complet: string;
  genre: 'G' | 'F';
  section: string;
  section_nom: string;
  telephone_parent: string;
  date_inscription: string;
  statut: string;
  total_attendu: number;
  total_paye: number;
  reste_a_payer: number;
  niveau_alerte: 'OK' | 'ATTENTION' | 'URGENT';
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
EOF

# ── CORE : INTERCEPTOR ───────────────────────────────────────
cat > src/app/core/interceptors/auth.interceptor.ts << 'EOF'
import { HttpInterceptorFn } from '@angular/common/http';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const token    = localStorage.getItem('access_token');
  const tenantId = localStorage.getItem('tenant_id');

  let headers: Record<string, string> = {};
  if (token)    headers['Authorization'] = `Bearer ${token}`;
  if (tenantId) headers['X-Tenant-ID']   = tenantId;

  if (Object.keys(headers).length) {
    req = req.clone({ setHeaders: headers });
  }
  return next(req);
};
EOF

# ── CORE : GUARD ─────────────────────────────────────────────
cat > src/app/core/guards/auth.guard.ts << 'EOF'
import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

export const authGuard: CanActivateFn = () => {
  const router = inject(Router);
  if (localStorage.getItem('access_token')) return true;
  router.navigate(['/login']);
  return false;
};
EOF

# ── CORE : AUTH SERVICE ──────────────────────────────────────
cat > src/app/core/services/auth.service.ts << 'EOF'
import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { tap } from 'rxjs/operators';
import { environment } from '../../../environments/environment';
import { User, AuthTokens } from '../models/user.model';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private api = environment.apiUrl;
  currentUser = signal<User | null>(null);

  constructor(private http: HttpClient, private router: Router) {
    this.loadUserFromStorage();
  }

  login(email: string, password: string) {
    return this.http.post<AuthTokens & { user: User }>(`${this.api}/auth/login/`, { email, password })
      .pipe(tap(res => {
        localStorage.setItem('access_token',  res.access);
        localStorage.setItem('refresh_token', res.refresh);
        // Décode le JWT pour récupérer les infos user
        const payload = JSON.parse(atob(res.access.split('.')[1]));
        const user: User = { id: payload.user_id, nom: payload.nom, email, role: payload.role, tenant: payload.tenant_id };
        localStorage.setItem('user',      JSON.stringify(user));
        localStorage.setItem('tenant_id', payload.tenant_id || '');
        this.currentUser.set(user);
      }));
  }

  logout() {
    localStorage.clear();
    this.currentUser.set(null);
    this.router.navigate(['/login']);
  }

  private loadUserFromStorage() {
    const stored = localStorage.getItem('user');
    if (stored) this.currentUser.set(JSON.parse(stored));
  }

  get isLoggedIn(): boolean {
    return !!localStorage.getItem('access_token');
  }

  get isSuperAdmin(): boolean {
    return this.currentUser()?.role === 'SUPER_ADMIN';
  }
}
EOF

# ── CORE : API SERVICE ───────────────────────────────────────
cat > src/app/core/services/api.service.ts << 'EOF'
import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { environment } from '../../../environments/environment';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private base = environment.apiUrl;

  constructor(private http: HttpClient) {}

  get<T>(path: string, params?: Record<string, string>) {
    let httpParams = new HttpParams();
    if (params) Object.entries(params).forEach(([k, v]) => httpParams = httpParams.set(k, v));
    return this.http.get<T>(`${this.base}${path}`, { params: httpParams });
  }

  post<T>(path: string, body: any) {
    return this.http.post<T>(`${this.base}${path}`, body);
  }

  put<T>(path: string, body: any) {
    return this.http.put<T>(`${this.base}${path}`, body);
  }

  patch<T>(path: string, body: any) {
    return this.http.patch<T>(`${this.base}${path}`, body);
  }

  delete<T>(path: string) {
    return this.http.delete<T>(`${this.base}${path}`);
  }
}
EOF

# ── CORE : ELEVES SERVICE ────────────────────────────────────
cat > src/app/core/services/eleves.service.ts << 'EOF'
import { Injectable } from '@angular/core';
import { ApiService } from './api.service';
import { Eleve, Section, PaginatedResponse } from '../models/eleve.model';

@Injectable({ providedIn: 'root' })
export class ElevesService {
  constructor(private api: ApiService) {}

  getEleves(params?: Record<string, string>) {
    return this.api.get<PaginatedResponse<Eleve>>('/eleves/', params);
  }

  getEleve(id: string) {
    return this.api.get<Eleve>(`/eleves/${id}/`);
  }

  createEleve(data: Partial<Eleve>) {
    return this.api.post<Eleve>('/eleves/', data);
  }

  updateEleve(id: string, data: Partial<Eleve>) {
    return this.api.patch<Eleve>(`/eleves/${id}/`, data);
  }

  deleteEleve(id: string) {
    return this.api.delete(`/eleves/${id}/`);
  }

  getSections() {
    return this.api.get<PaginatedResponse<Section>>('/eleves/sections/');
  }
}
EOF

# ── LAYOUT : SHELL ───────────────────────────────────────────
mkdir -p src/app/layout/shell

cat > src/app/layout/shell/shell.component.ts << 'EOF'
import { Component, signal } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { CommonModule } from '@angular/common';
import { AuthService } from '../../core/services/auth.service';
import { ButtonModule } from 'primeng/button';
import { AvatarModule } from 'primeng/avatar';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';

interface NavItem {
  label: string;
  icon: string;
  route: string;
  roles?: string[];
}

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, CommonModule, ButtonModule, AvatarModule, ToastModule],
  providers: [MessageService],
  template: `
    <p-toast />
    <div class="shell">

      <!-- SIDEBAR -->
      <aside class="sidebar" [class.collapsed]="sidebarCollapsed()">
        <div class="logo-zone">
          <div class="logo-text" *ngIf="!sidebarCollapsed()">
            <span class="logo-main">HADY GESMAN</span>
            <span class="logo-sub">Gestion Scolaire</span>
          </div>
          <button class="collapse-btn" (click)="toggleSidebar()">
            {{ sidebarCollapsed() ? '→' : '←' }}
          </button>
        </div>

        <!-- Licence badge -->
        <div class="licence-badge" *ngIf="!sidebarCollapsed()">
          <div class="lb-status">✅ Licence PRO</div>
          <div class="lb-school">{{ auth.currentUser()?.nom || 'École' }}</div>
        </div>

        <!-- Navigation -->
        <nav class="nav">
          <div class="nav-section" *ngIf="!sidebarCollapsed()">
            <span class="nav-label">Principal</span>
          </div>
          <ng-container *ngFor="let item of navItems">
            <a class="nav-item"
               [routerLink]="item.route"
               routerLinkActive="active"
               [title]="item.label">
              <span class="nav-icon">{{ item.icon }}</span>
              <span class="nav-label-text" *ngIf="!sidebarCollapsed()">{{ item.label }}</span>
            </a>
          </ng-container>
        </nav>

        <!-- Footer user -->
        <div class="sidebar-footer" *ngIf="!sidebarCollapsed()">
          <p-avatar [label]="userInitials" styleClass="user-avatar" />
          <div class="user-info">
            <div class="user-name">{{ auth.currentUser()?.nom }}</div>
            <div class="user-role">{{ auth.currentUser()?.role }}</div>
          </div>
          <button class="logout-btn" (click)="auth.logout()" title="Déconnexion">⏻</button>
        </div>
      </aside>

      <!-- MAIN -->
      <div class="main">
        <header class="topbar">
          <div class="topbar-left">
            <span class="page-title">{{ currentPageTitle() }}</span>
          </div>
          <div class="topbar-right">
            <span class="badge-exercice">📅 2025-2026</span>
          </div>
        </header>
        <main class="content">
          <router-outlet />
        </main>
      </div>

    </div>
  `,
  styles: [`
    .shell { display: flex; height: 100vh; overflow: hidden; background: #0b0f1a; }

    /* SIDEBAR */
    .sidebar {
      width: 240px; min-width: 240px;
      background: #111827;
      border-right: 1px solid #1e2d45;
      display: flex; flex-direction: column;
      transition: width 0.2s, min-width 0.2s;
      overflow: hidden;
    }
    .sidebar.collapsed { width: 60px; min-width: 60px; }

    .logo-zone {
      display: flex; align-items: center; justify-content: space-between;
      padding: 18px 14px 14px;
      border-bottom: 1px solid #1e2d45;
    }
    .logo-main { display: block; font-size: 15px; font-weight: 700; color: #00d4aa; letter-spacing: 0.5px; }
    .logo-sub  { display: block; font-size: 10px; color: #64748b; text-transform: uppercase; letter-spacing: 1px; }
    .collapse-btn {
      background: transparent; border: 1px solid #1e2d45; color: #94a3b8;
      border-radius: 6px; padding: 4px 8px; cursor: pointer; font-size: 12px;
      flex-shrink: 0;
    }
    .collapse-btn:hover { border-color: #00d4aa; color: #00d4aa; }

    .licence-badge {
      margin: 10px 12px;
      background: #0f2010; border: 1px solid #2a5c2a;
      border-radius: 8px; padding: 8px 12px;
    }
    .lb-status { font-size: 11px; color: #10b981; font-weight: 600; }
    .lb-school { font-size: 11px; color: #94a3b8; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

    .nav { flex: 1; padding: 8px 0; overflow-y: auto; }
    .nav-section { padding: 10px 14px 4px; }
    .nav-label { font-size: 10px; color: #64748b; text-transform: uppercase; letter-spacing: 1.5px; }

    .nav-item {
      display: flex; align-items: center; gap: 10px;
      padding: 9px 14px; cursor: pointer;
      border-left: 3px solid transparent;
      color: #94a3b8; font-size: 13px;
      text-decoration: none;
      transition: all 0.15s;
    }
    .nav-item:hover { background: #1a2235; color: #e8f0fe; }
    .nav-item.active { background: rgba(0,212,170,0.08); border-left-color: #00d4aa; color: #00d4aa; font-weight: 500; }
    .nav-icon { font-size: 16px; width: 20px; text-align: center; flex-shrink: 0; }

    .sidebar-footer {
      display: flex; align-items: center; gap: 10px;
      padding: 14px; border-top: 1px solid #1e2d45;
    }
    ::ng-deep .user-avatar.p-avatar { background: linear-gradient(135deg, #00d4aa, #0099ff) !important; color: #000 !important; font-weight: 700 !important; width: 32px !important; height: 32px !important; font-size: 12px !important; }
    .user-info { flex: 1; overflow: hidden; }
    .user-name { font-size: 12px; font-weight: 600; color: #e8f0fe; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .user-role { font-size: 10px; color: #64748b; }
    .logout-btn { background: transparent; border: 1px solid #1e2d45; color: #64748b; border-radius: 6px; padding: 4px 8px; cursor: pointer; font-size: 14px; }
    .logout-btn:hover { border-color: #ef4444; color: #ef4444; }

    /* MAIN */
    .main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

    .topbar {
      height: 52px; background: #111827;
      border-bottom: 1px solid #1e2d45;
      display: flex; align-items: center; justify-content: space-between;
      padding: 0 24px; flex-shrink: 0;
    }
    .page-title { font-size: 18px; font-weight: 600; color: #e8f0fe; }
    .badge-exercice { font-size: 11px; padding: 3px 12px; border-radius: 20px; background: rgba(0,153,255,0.15); color: #0099ff; }

    .content { flex: 1; overflow-y: auto; padding: 24px; }
  `]
})
export class ShellComponent {
  sidebarCollapsed = signal(false);

  navItems: NavItem[] = [
    { label: 'Tableau de Bord', icon: '📊', route: '/dashboard' },
    { label: 'Élèves',          icon: '👥', route: '/eleves' },
    { label: 'Paiements',       icon: '💰', route: '/paiements' },
    { label: 'Comptabilité',    icon: '📒', route: '/comptabilite' },
    { label: 'Licences',        icon: '🔐', route: '/licences', roles: ['SUPER_ADMIN'] },
  ];

  constructor(public auth: AuthService) {}

  toggleSidebar() { this.sidebarCollapsed.update(v => !v); }

  get userInitials(): string {
    const nom = this.auth.currentUser()?.nom || 'U';
    return nom.substring(0, 2).toUpperCase();
  }

  currentPageTitle(): string {
    const titles: Record<string, string> = {
      '/dashboard':     'Tableau de Bord',
      '/eleves':        'Élèves & Paiements',
      '/paiements':     'Saisie des Recettes',
      '/comptabilite':  'Comptabilité',
      '/licences':      'Licences & Clients',
    };
    return titles[window.location.pathname] || 'HADY GESMAN';
  }
}
EOF

# ── FEATURE : LOGIN ──────────────────────────────────────────
mkdir -p src/app/features/auth/login

cat > src/app/features/auth/login/login.component.ts << 'EOF'
import { Component, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';
import { InputTextModule } from 'primeng/inputtext';
import { PasswordModule } from 'primeng/password';
import { ButtonModule } from 'primeng/button';
import { MessageModule } from 'primeng/message';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule, InputTextModule, PasswordModule, ButtonModule, MessageModule],
  template: `
    <div class="login-wrap">
      <div class="login-card">
        <div class="login-logo">
          <span class="logo-main">HADY GESMAN</span>
          <span class="logo-sub">Système de Gestion Scolaire</span>
        </div>

        <div class="form-group">
          <label>Email</label>
          <input pInputText [(ngModel)]="email" type="email" placeholder="admin@hadygesman.com" class="w-full" />
        </div>

        <div class="form-group">
          <label>Mot de passe</label>
          <p-password [(ngModel)]="password" [feedback]="false" [toggleMask]="true" styleClass="w-full" inputStyleClass="w-full" />
        </div>

        <p-message *ngIf="erreur()" severity="error" [text]="erreur()!" styleClass="w-full mb-3" />

        <p-button
          label="Se connecter"
          [loading]="loading()"
          (onClick)="login()"
          styleClass="w-full"
          severity="success" />
      </div>
    </div>
  `,
  styles: [`
    .login-wrap {
      min-height: 100vh; background: #0b0f1a;
      display: flex; align-items: center; justify-content: center;
    }
    .login-card {
      width: 400px; background: #111827;
      border: 1px solid #1e2d45; border-radius: 16px;
      padding: 36px 32px;
    }
    .login-logo { text-align: center; margin-bottom: 32px; }
    .logo-main { display: block; font-size: 22px; font-weight: 700; color: #00d4aa; }
    .logo-sub  { display: block; font-size: 12px; color: #64748b; margin-top: 4px; }
    .form-group { margin-bottom: 16px; }
    .form-group label { display: block; font-size: 12px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
    ::ng-deep .p-inputtext { background: #1a2235 !important; border-color: #2a3f5f !important; color: #e8f0fe !important; }
    ::ng-deep .p-inputtext:focus { border-color: #00d4aa !important; box-shadow: none !important; }
  `]
})
export class LoginComponent {
  email    = '';
  password = '';
  loading  = signal(false);
  erreur   = signal<string | null>(null);

  constructor(private auth: AuthService, private router: Router) {}

  login() {
    if (!this.email || !this.password) {
      this.erreur.set('Veuillez remplir tous les champs');
      return;
    }
    this.loading.set(true);
    this.erreur.set(null);
    this.auth.login(this.email, this.password).subscribe({
      next: () => this.router.navigate(['/']),
      error: () => {
        this.erreur.set('Email ou mot de passe incorrect');
        this.loading.set(false);
      }
    });
  }
}
EOF

# ── FEATURE : DASHBOARD ──────────────────────────────────────
mkdir -p src/app/features/dashboard

cat > src/app/features/dashboard/dashboard.component.ts << 'EOF'
import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiService } from '../../core/services/api.service';
import { CardModule } from 'primeng/card';
import { ProgressBarModule } from 'primeng/progressbar';
import { TagModule } from 'primeng/tag';

interface KPI {
  label: string;
  value: string;
  sub: string;
  color: string;
  icon: string;
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, CardModule, ProgressBarModule, TagModule],
  template: `
    <div class="dashboard">
      <!-- KPIs -->
      <div class="kpi-grid">
        <div class="kpi-card" *ngFor="let kpi of kpis" [style.--accent]="kpi.color">
          <div class="kpi-icon">{{ kpi.icon }}</div>
          <div class="kpi-label">{{ kpi.label }}</div>
          <div class="kpi-value" [style.color]="kpi.color">{{ kpi.value }}</div>
          <div class="kpi-sub">{{ kpi.sub }}</div>
        </div>
      </div>

      <!-- Alertes -->
      <div class="section-title">🚨 Alertes & Actions</div>
      <div class="alerts-grid">
        <div class="alert-card urgent">
          <div class="alert-count" style="color:#ef4444">{{ stats().urgent }}</div>
          <div class="alert-label">Élèves URGENT</div>
          <div class="alert-sub">Retard &gt; 60 jours</div>
        </div>
        <div class="alert-card attention">
          <div class="alert-count" style="color:#f59e0b">{{ stats().attention }}</div>
          <div class="alert-label">Élèves ATTENTION</div>
          <div class="alert-sub">Retard &gt; 30 jours</div>
        </div>
        <div class="alert-card ok">
          <div class="alert-count" style="color:#10b981">{{ stats().ok }}</div>
          <div class="alert-label">Élèves à jour</div>
          <div class="alert-sub">Paiements OK</div>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .dashboard { color: #e8f0fe; }
    .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 28px; }
    .kpi-card {
      background: #1e2d45; border: 1px solid #2a3f5f;
      border-top: 2px solid var(--accent, #00d4aa);
      border-radius: 12px; padding: 18px 20px;
      position: relative; transition: transform 0.2s;
    }
    .kpi-card:hover { transform: translateY(-2px); }
    .kpi-icon { position: absolute; top: 14px; right: 14px; font-size: 22px; opacity: 0.25; }
    .kpi-label { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; }
    .kpi-value { font-size: 26px; font-weight: 700; font-family: monospace; }
    .kpi-sub   { font-size: 11px; color: #64748b; margin-top: 4px; }

    .section-title { font-size: 16px; font-weight: 600; margin-bottom: 14px; }

    .alerts-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
    .alert-card {
      background: #1e2d45; border: 1px solid #2a3f5f;
      border-radius: 12px; padding: 20px; text-align: center;
    }
    .alert-count { font-size: 36px; font-weight: 700; font-family: monospace; }
    .alert-label { font-size: 13px; font-weight: 600; color: #e8f0fe; margin-top: 4px; }
    .alert-sub   { font-size: 11px; color: #64748b; margin-top: 2px; }
  `]
})
export class DashboardComponent implements OnInit {
  stats = signal({ urgent: 0, attention: 0, ok: 0 });

  kpis: KPI[] = [
    { label: 'Total Recettes',  value: '5 803 000', sub: 'FCFA · Exercice en cours', color: '#00d4aa', icon: '💰' },
    { label: 'Total Charges',   value: '4 005 000', sub: 'FCFA · Maîtrisées',        color: '#0099ff', icon: '💸' },
    { label: 'Résultat Net',    value: '1 798 000', sub: 'FCFA · Bénéfice ✅',       color: '#10b981', icon: '📈' },
    { label: 'Trésorerie',      value: '1 798 000', sub: 'FCFA · Suffisante ✅',     color: '#f59e0b', icon: '🏦' },
  ];

  constructor(private api: ApiService) {}

  ngOnInit() {
    // On récupère les élèves pour calculer les alertes
    this.api.get<any>('/eleves/').subscribe({
      next: (res) => {
        const eleves = res.results || [];
        this.stats.set({
          urgent:    eleves.filter((e: any) => e.niveau_alerte === 'URGENT').length,
          attention: eleves.filter((e: any) => e.niveau_alerte === 'ATTENTION').length,
          ok:        eleves.filter((e: any) => e.niveau_alerte === 'OK').length,
        });
      }
    });
  }
}
EOF

# ── FEATURE : ELEVES ─────────────────────────────────────────
mkdir -p src/app/features/eleves/liste

cat > src/app/features/eleves/liste/eleves-liste.component.ts << 'EOF'
import { Component, OnInit, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ElevesService } from '../../../core/services/eleves.service';
import { Eleve } from '../../../core/models/eleve.model';
import { TableModule } from 'primeng/table';
import { TagModule } from 'primeng/tag';
import { ButtonModule } from 'primeng/button';
import { InputTextModule } from 'primeng/inputtext';
import { DialogModule } from 'primeng/dialog';
import { DropdownModule } from 'primeng/dropdown';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';
import { ProgressBarModule } from 'primeng/progressbar';

@Component({
  selector: 'app-eleves-liste',
  standalone: true,
  imports: [CommonModule, FormsModule, TableModule, TagModule, ButtonModule,
            InputTextModule, DialogModule, DropdownModule, ToastModule, ProgressBarModule],
  providers: [MessageService],
  template: `
    <p-toast />

    <!-- Header -->
    <div class="page-header">
      <div>
        <h2 class="page-title">👥 Élèves & Paiements</h2>
        <span class="page-sub">{{ eleves().length }} élèves · Année 2025-2026</span>
      </div>
      <p-button label="+ Nouvel Élève" severity="success" (onClick)="ouvrirDialog()" />
    </div>

    <!-- Filtres -->
    <div class="filters-bar">
      <input pInputText [(ngModel)]="recherche" (input)="filtrer()"
             placeholder="🔍 Rechercher un élève..." class="search-input" />
      <p-dropdown [options]="filtresAlerte" [(ngModel)]="filtreAlerte"
                  (onChange)="filtrer()" placeholder="Toutes alertes"
                  optionLabel="label" optionValue="value" styleClass="filter-drop" />
    </div>

    <!-- Table -->
    <div class="table-card">
      <p-table [value]="elevesFiltres()" [loading]="loading()"
               [rowHover]="true" styleClass="p-datatable-sm"
               [paginator]="true" [rows]="20">
        <ng-template pTemplate="header">
          <tr>
            <th>N°</th>
            <th>Nom Complet</th>
            <th>Section</th>
            <th>Genre</th>
            <th>Total Attendu</th>
            <th>Payé</th>
            <th>Reste</th>
            <th>Alerte</th>
            <th>Actions</th>
          </tr>
        </ng-template>
        <ng-template pTemplate="body" let-eleve>
          <tr>
            <td class="mono">{{ eleve.numero }}</td>
            <td class="bold">{{ eleve.nom_complet }}</td>
            <td>{{ eleve.section_nom }}</td>
            <td>
              <p-tag [value]="eleve.genre === 'F' ? 'Fille' : 'Garçon'"
                     [severity]="eleve.genre === 'F' ? 'info' : 'success'" />
            </td>
            <td class="mono">{{ eleve.total_attendu | number }} FCFA</td>
            <td class="mono success">{{ eleve.total_paye | number }} FCFA</td>
            <td class="mono" [class.danger]="eleve.reste_a_payer > 0">
              {{ eleve.reste_a_payer | number }} FCFA
            </td>
            <td>
              <p-tag [value]="eleve.niveau_alerte"
                     [severity]="alerteSeverity(eleve.niveau_alerte)" />
            </td>
            <td>
              <p-button icon="pi pi-eye" [rounded]="true" [text]="true"
                        severity="info" (onClick)="voirEleve(eleve)" />
            </td>
          </tr>
        </ng-template>
        <ng-template pTemplate="emptymessage">
          <tr><td colspan="9" class="empty-msg">Aucun élève trouvé</td></tr>
        </ng-template>
      </p-table>
    </div>

    <!-- Dialog Nouvel Élève -->
    <p-dialog header="Nouvel Élève" [(visible)]="dialogVisible"
              [modal]="true" [style]="{width: '480px'}" [draggable]="false">
      <div class="form-grid">
        <div class="form-group full">
          <label>Nom Complet *</label>
          <input pInputText [(ngModel)]="nouvelEleve.nom_complet" class="w-full" />
        </div>
        <div class="form-group">
          <label>Section *</label>
          <p-dropdown [options]="sections()" [(ngModel)]="nouvelEleve.section"
                      optionLabel="nom" optionValue="id"
                      placeholder="Choisir..." styleClass="w-full" />
        </div>
        <div class="form-group">
          <label>Genre</label>
          <p-dropdown [options]="[{label:'Garçon', value:'G'},{label:'Fille', value:'F'}]"
                      [(ngModel)]="nouvelEleve.genre"
                      optionLabel="label" optionValue="value" styleClass="w-full" />
        </div>
        <div class="form-group full">
          <label>Téléphone Parent</label>
          <input pInputText [(ngModel)]="nouvelEleve.telephone_parent" class="w-full" placeholder="7X XXX XX XX" />
        </div>
      </div>
      <ng-template pTemplate="footer">
        <p-button label="Annuler" severity="secondary" (onClick)="dialogVisible = false" />
        <p-button label="Enregistrer" severity="success" [loading]="saving()" (onClick)="sauvegarder()" />
      </ng-template>
    </p-dialog>
  `,
  styles: [`
    .page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
    .page-title  { font-size: 20px; font-weight: 600; color: #e8f0fe; margin: 0 0 4px; }
    .page-sub    { font-size: 12px; color: #64748b; }

    .filters-bar { display: flex; gap: 12px; margin-bottom: 16px; }
    .search-input { flex: 1; }
    ::ng-deep .filter-drop { min-width: 180px; }

    .table-card { background: #1e2d45; border: 1px solid #2a3f5f; border-radius: 12px; overflow: hidden; }

    ::ng-deep .p-datatable .p-datatable-thead > tr > th {
      background: #111827 !important; color: #64748b !important;
      font-size: 11px !important; text-transform: uppercase !important;
      letter-spacing: 0.5px !important; border-color: #2a3f5f !important;
    }
    ::ng-deep .p-datatable .p-datatable-tbody > tr {
      background: #1e2d45 !important; color: #94a3b8 !important;
      border-bottom: 1px solid rgba(42,63,95,0.4) !important;
    }
    ::ng-deep .p-datatable .p-datatable-tbody > tr:hover {
      background: #1a2235 !important;
    }

    .mono    { font-family: monospace; font-size: 12px; }
    .bold    { font-weight: 600; color: #e8f0fe; }
    .success { color: #10b981; }
    .danger  { color: #ef4444; }
    .empty-msg { text-align: center; padding: 40px; color: #64748b; }

    .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
    .form-group { display: flex; flex-direction: column; gap: 6px; }
    .form-group.full { grid-column: 1 / -1; }
    .form-group label { font-size: 12px; color: #94a3b8; }
  `]
})
export class ElevesListeComponent implements OnInit {
  eleves        = signal<Eleve[]>([]);
  elevesFiltres = signal<Eleve[]>([]);
  sections      = signal<any[]>([]);
  loading       = signal(true);
  saving        = signal(false);
  dialogVisible = false;
  recherche     = '';
  filtreAlerte  = '';

  filtresAlerte = [
    { label: 'Toutes alertes', value: '' },
    { label: '🔴 URGENT',      value: 'URGENT' },
    { label: '🟡 ATTENTION',   value: 'ATTENTION' },
    { label: '✅ OK',          value: 'OK' },
  ];

  nouvelEleve: Partial<Eleve> = {};

  constructor(private elevesService: ElevesService, private msg: MessageService) {}

  ngOnInit() {
    this.chargerEleves();
    this.chargerSections();
  }

  chargerEleves() {
    this.loading.set(true);
    this.elevesService.getEleves().subscribe({
      next: res => {
        this.eleves.set(res.results);
        this.elevesFiltres.set(res.results);
        this.loading.set(false);
      },
      error: () => this.loading.set(false)
    });
  }

  chargerSections() {
    this.elevesService.getSections().subscribe({
      next: res => this.sections.set(res.results)
    });
  }

  filtrer() {
    let data = this.eleves();
    if (this.recherche) {
      data = data.filter(e => e.nom_complet.toLowerCase().includes(this.recherche.toLowerCase()));
    }
    if (this.filtreAlerte) {
      data = data.filter(e => e.niveau_alerte === this.filtreAlerte);
    }
    this.elevesFiltres.set(data);
  }

  alerteSeverity(alerte: string): 'danger' | 'warn' | 'success' {
    return alerte === 'URGENT' ? 'danger' : alerte === 'ATTENTION' ? 'warn' : 'success';
  }

  ouvrirDialog() {
    this.nouvelEleve = {};
    this.dialogVisible = true;
  }

  voirEleve(eleve: Eleve) {
    this.msg.add({ severity: 'info', summary: eleve.nom_complet,
                   detail: `Reste à payer: ${eleve.reste_a_payer.toLocaleString()} FCFA` });
  }

  sauvegarder() {
    if (!this.nouvelEleve.nom_complet) {
      this.msg.add({ severity: 'warn', summary: 'Champ requis', detail: 'Le nom est obligatoire' });
      return;
    }
    this.saving.set(true);
    this.elevesService.createEleve(this.nouvelEleve).subscribe({
      next: () => {
        this.msg.add({ severity: 'success', summary: 'Succès', detail: 'Élève ajouté ✅' });
        this.dialogVisible = false;
        this.saving.set(false);
        this.chargerEleves();
      },
      error: () => {
        this.msg.add({ severity: 'error', summary: 'Erreur', detail: 'Impossible d\'ajouter l\'élève' });
        this.saving.set(false);
      }
    });
  }
}
EOF

# ── FEATURES PLACEHOLDER ─────────────────────────────────────
for feature in paiements comptabilite licences; do
  mkdir -p src/app/features/$feature
  cat > src/app/features/$feature/$feature.component.ts << TSEOF
import { Component } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-$feature',
  standalone: true,
  imports: [CommonModule],
  template: \`
    <div style="color:#e8f0fe; padding: 40px; text-align:center">
      <div style="font-size:48px; margin-bottom:16px">🚧</div>
      <h2 style="color:#00d4aa">Module $(echo $feature | sed 's/.*/\u&/') en développement</h2>
      <p style="color:#64748b">Ce module sera disponible prochainement</p>
    </div>
  \`
})
export class $(echo $feature | sed 's/.*/\u&/')Component {}
TSEOF
done

# ── STYLES GLOBAUX ───────────────────────────────────────────
cat > src/styles.scss << 'EOF'
@import "primeng/resources/themes/lara-dark-teal/theme.css";
@import "primeng/resources/primeng.css";
@import "primeicons/primeicons.css";
@import "primeflex/primeflex.css";

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: 'Outfit', 'Segoe UI', sans-serif;
  background: #0b0f1a;
  color: #e8f0fe;
  font-size: 14px;
}

::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #2a3f5f; border-radius: 3px; }

.w-full { width: 100% !important; }
EOF

# ── PACKAGE.JSON — ajouter @primeuix/themes ──────────────────
npm install @primeuix/themes --save 2>/dev/null || true

echo ""
echo "✅ Setup Angular terminé !"
echo ""
echo "Lancez : ng serve"
echo "Ouvrez : http://localhost:4200"
