import { Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { tap } from 'rxjs/operators';
import { environment } from '../../../environments/environment';
import { User, AuthTokens } from '../models/user.model';

const IMPERSONATE_ID_KEY  = 'impersonate_tenant_id';
const IMPERSONATE_NOM_KEY = 'impersonate_tenant_nom';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private api = environment.apiUrl;
  currentUser = signal<User | null>(null);

  // Pour le super_admin qui "se met dans la peau" d'une école
  impersonatedTenantId  = signal<string | null>(null);
  impersonatedTenantNom = signal<string | null>(null);

  constructor(private http: HttpClient, private router: Router) {
    this.loadUserFromStorage();
    this.loadImpersonationFromStorage();
  }

  login(email: string, password: string) {
    return this.http.post<AuthTokens & { user: User }>(`${this.api}/auth/login/`, { email, password })
      .pipe(tap(res => {
        localStorage.setItem('access_token',  res.access);
        localStorage.setItem('refresh_token', res.refresh);
        const payload = JSON.parse(atob(res.access.split('.')[1]));
        const user: User = {
          id: payload.user_id, nom: payload.nom, email,
          role: payload.role, tenant: payload.tenant_id,
          type_licence: payload.type_licence || null,
          modules: payload.modules || [],
        };
        localStorage.setItem('user',      JSON.stringify(user));
        localStorage.setItem('tenant_id', payload.tenant_id || '');
        this.currentUser.set(user);
        // Sécurité : un nouveau login annule toute impersonation antérieure
        this.exitTenant();
      }));
  }

  logout() {
    localStorage.clear();
    this.currentUser.set(null);
    this.impersonatedTenantId.set(null);
    this.impersonatedTenantNom.set(null);
    this.router.navigate(['/login']);
  }

  // ── Impersonation tenant (super_admin uniquement) ────────────────
  /**
   * Le super_admin se met dans la peau d'une école : toutes les
   * requêtes API porteront X-Tenant-ID = tenantId. À combiner avec
   * une navigation vers /dashboard pour entrer dans l'app école.
   */
  switchTenant(tenantId: string, tenantNom: string) {
    if (!this.isSuperAdmin) return;
    localStorage.setItem(IMPERSONATE_ID_KEY,  tenantId);
    localStorage.setItem(IMPERSONATE_NOM_KEY, tenantNom);
    this.impersonatedTenantId.set(tenantId);
    this.impersonatedTenantNom.set(tenantNom);
  }

  exitTenant() {
    localStorage.removeItem(IMPERSONATE_ID_KEY);
    localStorage.removeItem(IMPERSONATE_NOM_KEY);
    this.impersonatedTenantId.set(null);
    this.impersonatedTenantNom.set(null);
  }

  /** ID de tenant à envoyer dans X-Tenant-ID (impersonation > tenant user). */
  get effectiveTenantId(): string | null {
    return this.impersonatedTenantId() || localStorage.getItem('tenant_id') || null;
  }

  private loadUserFromStorage() {
    const stored = localStorage.getItem('user');
    if (stored) this.currentUser.set(JSON.parse(stored));
  }

  private loadImpersonationFromStorage() {
    const id  = localStorage.getItem(IMPERSONATE_ID_KEY);
    const nom = localStorage.getItem(IMPERSONATE_NOM_KEY);
    if (id)  this.impersonatedTenantId.set(id);
    if (nom) this.impersonatedTenantNom.set(nom);
  }

  get isLoggedIn(): boolean {
    return !!localStorage.getItem('access_token');
  }

  get isSuperAdmin(): boolean {
    return this.currentUser()?.role === 'SUPER_ADMIN';
  }
}
