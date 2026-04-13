import { Component, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';
import { LangueService } from '../../../core/services/langue.service';
import { TranslateModule } from '@ngx-translate/core';
import { InputTextModule } from 'primeng/inputtext';
import { PasswordModule } from 'primeng/password';
import { ButtonModule } from 'primeng/button';
import { MessageModule } from 'primeng/message';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [CommonModule, FormsModule, InputTextModule, PasswordModule,
            ButtonModule, MessageModule, TranslateModule],
  template: `
    <div class="login-wrap">
      <div class="login-card">

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

        <div class="login-logo">
          <span class="logo-main">{{ 'app.name' | translate }}</span>
          <span class="logo-sub">{{ 'app.by' | translate }}</span>
        </div>

        <div class="form-group">
          <label>{{ 'auth.email' | translate }}</label>
          <input pInputText [(ngModel)]="email" type="email"
                 [placeholder]="'auth.email' | translate" class="w-full" />
        </div>

        <div class="form-group">
          <label>{{ 'auth.password' | translate }}</label>
          <p-password [(ngModel)]="password" [feedback]="false"
                      [toggleMask]="true" styleClass="w-full" inputStyleClass="w-full" />
        </div>

        <p-message *ngIf="erreur()" severity="error"
                   [text]="'auth.error' | translate" styleClass="w-full mb-3" />

        <p-button [label]="'auth.login' | translate"
                  [loading]="loading()" (onClick)="login()"
                  styleClass="w-full" severity="success" />
      </div>
    </div>
  `,
  styles: [`
    .login-wrap { min-height:100vh; background:#0b0f1a; display:flex; align-items:center; justify-content:center; }
    .login-card { width:400px; background:#111827; border:1px solid #1e2d45; border-radius:16px; padding:36px 32px; }
    .langue-selector { display:flex; justify-content:flex-end; gap:6px; margin-bottom:20px; }
    .langue-btn { background:transparent; border:1px solid #1e2d45; border-radius:6px; padding:3px 8px; cursor:pointer; font-size:15px; }
    .langue-btn.active { border-color:#00d4aa; background:rgba(0,212,170,0.1); }
    .login-logo { text-align:center; margin-bottom:28px; }
    .logo-main { display:block; font-size:22px; font-weight:700; color:#00d4aa; }
    .logo-sub  { display:block; font-size:12px; color:#64748b; margin-top:4px; }
    .form-group { margin-bottom:16px; }
    .form-group label { display:block; font-size:12px; color:#94a3b8; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:6px; }
    ::ng-deep .p-inputtext { background:#1a2235 !important; border-color:#2a3f5f !important; color:#e8f0fe !important; }
    ::ng-deep .p-inputtext:focus { border-color:#00d4aa !important; box-shadow:none !important; }
    .w-full { width:100% !important; }
  `]
})
export class LoginComponent {
  email    = '';
  password = '';
  loading  = signal(false);
  erreur   = signal<string | null>(null);

  constructor(
    private auth: AuthService,
    private router: Router,
    public langue: LangueService
  ) {}

  login() {
    if (!this.email || !this.password) { this.erreur.set('empty'); return; }
    this.loading.set(true);
    this.erreur.set(null);
    this.auth.login(this.email, this.password).subscribe({
      next: () => this.router.navigate(['/']),
      error: () => { this.erreur.set('error'); this.loading.set(false); }
    });
  }
}
