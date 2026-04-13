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
