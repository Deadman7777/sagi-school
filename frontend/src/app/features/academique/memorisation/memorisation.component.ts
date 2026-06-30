import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { TableModule } from 'primeng/table';
import { ButtonModule } from 'primeng/button';
import { DialogModule } from 'primeng/dialog';
import { InputTextModule } from 'primeng/inputtext';
import { InputNumberModule } from 'primeng/inputnumber';
import { SelectModule } from 'primeng/select';
import { CheckboxModule } from 'primeng/checkbox';
import { TagModule } from 'primeng/tag';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';
import { TranslateModule, TranslateService } from '@ngx-translate/core';

import { DaaraService } from '../../../core/services/daara.service';
import { ElevesService } from '../../../core/services/eleves.service';

@Component({
  selector: 'app-memorisation',
  standalone: true,
  imports: [CommonModule, FormsModule, TableModule, ButtonModule, DialogModule,
            InputTextModule, InputNumberModule, SelectModule, CheckboxModule,
            TagModule, ToastModule, TranslateModule],
  providers: [MessageService],
  template: `
    <p-toast />

    <!-- Sous-onglets -->
    <div class="sub-tabs">
      <button class="sub-tab" [class.active]="vue()==='parcours'" (click)="vue.set('parcours')">
        🧒 {{ 'daara.parcours' | translate }}
      </button>
      <button class="sub-tab" [class.active]="vue()==='niveaux'" (click)="vue.set('niveaux')">
        📶 {{ 'daara.niveaux' | translate }}
      </button>
      @if (parcoursActif()) {
        <button class="sub-tab" [class.active]="vue()==='suivi'" (click)="vue.set('suivi'); chargerSuivi()">
          📅 {{ 'daara.suivi' | translate }}
        </button>
        @if (!estIdjie()) {
          <button class="sub-tab" [class.active]="vue()==='progression'" (click)="vue.set('progression'); chargerProgression()">
            📈 {{ 'daara.progression' | translate }}
          </button>
        }
      }
    </div>

    @if (parcoursActif()) {
      <div class="nongo-bar">
        {{ 'daara.nongo_actif' | translate }} :
        <strong>{{ parcoursActif().eleve_nom }}</strong>
        · {{ parcoursActif().riwaya }} · {{ parcoursActif().niveau_nom || '—' }}
        <button class="link-btn" (click)="parcoursActif.set(null); vue.set('parcours')">✕</button>
      </div>
    }

    <!-- ════════════════ PARCOURS (NONGO) ════════════════ -->
    @if (vue()==='parcours') {
      <div class="toolbar">
        <p-button [label]="'daara.nouveau_parcours' | translate" severity="success"
                  icon="pi pi-plus" (onClick)="ouvrirParcours()" />
      </div>
      <p-table [value]="parcours()" styleClass="p-datatable-sm">
        <ng-template pTemplate="header">
          <tr>
            <th>{{ 'daara.nongo' | translate }}</th>
            <th>{{ 'daara.riwaya' | translate }}</th>
            <th>{{ 'daara.niveau' | translate }}</th>
            <th>{{ 'daara.statut' | translate }}</th>
            <th>{{ 'daara.date_debut' | translate }}</th>
            <th></th>
          </tr>
        </ng-template>
        <ng-template pTemplate="body" let-p>
          <tr>
            <td>{{ p.eleve_nom }}</td>
            <td>{{ p.riwaya }}</td>
            <td>{{ p.niveau_nom || '—' }}</td>
            <td><p-tag [value]="p.statut" [severity]="p.statut==='KHATMA' ? 'success' : (p.statut==='SORTI' ? 'warn' : 'info')" /></td>
            <td>{{ p.date_debut || '—' }}</td>
            <td class="actions">
              <button class="link-btn" (click)="ouvrirNongo(p)">📅 {{ 'daara.suivre' | translate }}</button>
              <button class="link-btn" (click)="ouvrirParcours(p)">✏️</button>
              <button class="link-btn danger" (click)="supprimerParcours(p)">🗑️</button>
            </td>
          </tr>
        </ng-template>
        <ng-template pTemplate="emptymessage">
          <tr><td colspan="6" class="empty">{{ 'daara.aucun_parcours' | translate }}</td></tr>
        </ng-template>
      </p-table>
    }

    <!-- ════════════════ NIVEAUX ════════════════ -->
    @if (vue()==='niveaux') {
      <div class="toolbar">
        <p-button [label]="'daara.nouveau_niveau' | translate" severity="success"
                  icon="pi pi-plus" (onClick)="ouvrirNiveau()" />
      </div>
      <p-table [value]="niveaux()" styleClass="p-datatable-sm">
        <ng-template pTemplate="header">
          <tr>
            <th>{{ 'daara.niveau' | translate }}</th>
            <th>الاسم</th>
            <th>{{ 'daara.categorie' | translate }}</th>
            <th>{{ 'daara.ordre' | translate }}</th>
            <th></th>
          </tr>
        </ng-template>
        <ng-template pTemplate="body" let-n>
          <tr>
            <td>{{ n.nom_fr }}</td>
            <td dir="rtl">{{ n.nom_ar }}</td>
            <td>{{ n.categorie }}</td>
            <td>{{ n.ordre }}</td>
            <td class="actions">
              <button class="link-btn" (click)="ouvrirNiveau(n)">✏️</button>
              <button class="link-btn danger" (click)="supprimerNiveau(n)">🗑️</button>
            </td>
          </tr>
        </ng-template>
        <ng-template pTemplate="emptymessage">
          <tr><td colspan="5" class="empty">{{ 'daara.aucun_niveau' | translate }}</td></tr>
        </ng-template>
      </p-table>
    }

    <!-- ════════════════ SUIVI QUOTIDIEN ════════════════ -->
    @if (vue()==='suivi' && parcoursActif() && estIdjie()) {
      <div class="card-form">
        <h4>{{ 'daara.idjie_titre' | translate }}</h4>
        <p class="idjie-hint">{{ 'daara.idjie_aide' | translate }}</p>
        <div class="grid">
          <div class="fg full">
            <label>{{ 'daara.idjie_niveau' | translate }}</label>
            <p-select appendTo="body" [options]="niveauIdjieOptions" [(ngModel)]="formIdjieNiveau"
                      optionLabel="label" optionValue="value" [showClear]="true"
                      [placeholder]="'daara.choisir' | translate" styleClass="w-full" />
          </div>
        </div>
        <p-button [label]="'common.enregistrer' | translate" severity="success"
                  [loading]="saving()" (onClick)="enregistrerNiveauIdjie()" />
      </div>
    }

    @if (vue()==='suivi' && parcoursActif() && !estIdjie()) {
      <div class="card-form">
        <h4>{{ 'daara.nouvelle_entree' | translate }}</h4>
        <div class="grid">
          <div class="fg">
            <label>{{ 'daara.date' | translate }}</label>
            <input pInputText type="date" [(ngModel)]="formSuivi.date" class="w-full" />
          </div>
          <div class="fg">
            <label>{{ 'daara.qualite' | translate }}</label>
            <p-select appendTo="body" [options]="qualiteOptions" [(ngModel)]="formSuivi.qualite"
                      optionLabel="label" optionValue="value" styleClass="w-full" />
          </div>
          <div class="fg">
            <label>{{ 'daara.sourate_debut' | translate }}</label>
            <p-select appendTo="body" [options]="sourates()" [(ngModel)]="formSuivi.sourate_debut"
                      optionLabel="label" optionValue="id" [filter]="true" filterBy="label"
                      [placeholder]="'daara.choisir' | translate" styleClass="w-full" />
          </div>
          <div class="fg sm">
            <label>{{ 'daara.verset' | translate }}</label>
            <p-inputNumber [(ngModel)]="formSuivi.verset_debut" [min]="1" styleClass="w-full" />
          </div>
          <div class="fg">
            <label>{{ 'daara.sourate_fin' | translate }}</label>
            <p-select appendTo="body" [options]="sourates()" [(ngModel)]="formSuivi.sourate_fin"
                      optionLabel="label" optionValue="id" [filter]="true" filterBy="label"
                      [placeholder]="'daara.choisir' | translate" styleClass="w-full" />
          </div>
          <div class="fg sm">
            <label>{{ 'daara.verset' | translate }}</label>
            <p-inputNumber [(ngModel)]="formSuivi.verset_fin" [min]="1" styleClass="w-full" />
          </div>
          <div class="fg check">
            <p-checkbox [(ngModel)]="formSuivi.present" [binary]="true" inputId="present" />
            <label for="present">{{ 'daara.present' | translate }}</label>
          </div>
          <div class="fg full">
            <label>{{ 'daara.observation' | translate }}</label>
            <input pInputText [(ngModel)]="formSuivi.observation" class="w-full" />
          </div>
        </div>
        <p-button [label]="'common.enregistrer' | translate" severity="success"
                  [loading]="saving()" (onClick)="enregistrerSuivi()" />
      </div>

      <p-table [value]="suivis()" styleClass="p-datatable-sm">
        <ng-template pTemplate="header">
          <tr>
            <th>{{ 'daara.date' | translate }}</th>
            <th>{{ 'daara.portion' | translate }}</th>
            <th>{{ 'daara.qualite' | translate }}</th>
            <th>{{ 'daara.present' | translate }}</th>
            <th>{{ 'daara.observation' | translate }}</th>
            <th></th>
          </tr>
        </ng-template>
        <ng-template pTemplate="body" let-s>
          <tr>
            <td>{{ s.date }}</td>
            <td>{{ s.sourate_debut_nom }} {{ s.verset_debut }} → {{ s.sourate_fin_nom }} {{ s.verset_fin }}</td>
            <td><p-tag [value]="s.qualite" [severity]="s.qualite==='BIEN' ? 'success' : (s.qualite==='A_REVOIR' ? 'danger' : 'warn')" /></td>
            <td>{{ s.present ? '✓' : '✗' }}</td>
            <td>{{ s.observation }}</td>
            <td><button class="link-btn danger" (click)="supprimerSuivi(s)">🗑️</button></td>
          </tr>
        </ng-template>
        <ng-template pTemplate="emptymessage">
          <tr><td colspan="6" class="empty">{{ 'daara.aucun_suivi' | translate }}</td></tr>
        </ng-template>
      </p-table>
    }

    <!-- ════════════════ PROGRESSION ════════════════ -->
    @if (vue()==='progression' && parcoursActif()) {
      @if (progression(); as pr) {
        <div class="prog-head">
          <div class="prog-pct">
            <div class="big">{{ pr.pct }}%</div>
            <div class="sub">{{ 'daara.memorise' | translate }}</div>
          </div>
          <div class="prog-info">
            <div>{{ pr.versets_memorises }} / {{ pr.total_versets }} {{ 'daara.versets' | translate }}</div>
            <div>{{ 'daara.hizb' | translate }} : {{ pr.hizb_complets }}/{{ pr.hizb_total }} · {{ 'daara.rub' | translate }} : {{ pr.rub_complets }}/{{ pr.rub_total }}</div>
            <div>{{ pr.nb_suivis }} {{ 'daara.entrees' | translate }} · {{ pr.riwaya }}</div>
          </div>
          <p-button [label]="'daara.export_parent' | translate" icon="pi pi-file-pdf"
                    severity="help" [loading]="exporting()" (onClick)="exporterPdf()" />
        </div>

        <h4>{{ 'daara.couverture_juz' | translate }}</h4>
        <div class="juz-grid">
          @for (j of pr.par_juz; track j.juz) {
            <div class="juz-cell" [style.background]="couleurJuz(j.pct)" [title]="'Juz ' + j.juz + ' : ' + j.pct + '%'">
              <span class="jn">{{ j.juz }}</span>
              <span class="jp">{{ j.pct }}%</span>
            </div>
          }
        </div>
      } @else {
        <div class="empty">{{ 'daara.chargement' | translate }}</div>
      }
    }

    <!-- ════════════════ DIALOG PARCOURS ════════════════ -->
    <p-dialog [header]="(editParcoursId ? 'daara.modifier_parcours' : 'daara.nouveau_parcours') | translate"
              [(visible)]="dialogParcours" [modal]="true" [style]="{width:'460px'}" [draggable]="false">
      <div class="grid">
        <div class="fg full">
          <label>{{ 'daara.nongo' | translate }} *</label>
          <p-select appendTo="body" [options]="eleves()" [(ngModel)]="formParcours.eleve"
                    optionLabel="nom_complet" optionValue="id" [filter]="true" filterBy="nom_complet"
                    [placeholder]="'daara.choisir' | translate" styleClass="w-full" [disabled]="!!editParcoursId" />
        </div>
        <div class="fg">
          <label>{{ 'daara.riwaya' | translate }} *</label>
          <p-select appendTo="body" [options]="riwayaOptions" [(ngModel)]="formParcours.riwaya"
                    optionLabel="label" optionValue="value" styleClass="w-full" />
        </div>
        <div class="fg">
          <label>{{ 'daara.niveau' | translate }}</label>
          <p-select appendTo="body" [options]="niveaux()" [(ngModel)]="formParcours.niveau"
                    optionLabel="nom_fr" optionValue="id" [showClear]="true"
                    [placeholder]="'daara.choisir' | translate" styleClass="w-full" />
        </div>
        <div class="fg full">
          <label>{{ 'daara.sens' | translate }}</label>
          <p-select appendTo="body" [options]="sensOptions" [(ngModel)]="formParcours.sens"
                    optionLabel="label" optionValue="value" styleClass="w-full" />
        </div>
        <div class="fg">
          <label>{{ 'daara.date_debut' | translate }}</label>
          <input pInputText type="date" [(ngModel)]="formParcours.date_debut" class="w-full" />
        </div>
        <div class="fg">
          <label>{{ 'daara.date_sortie' | translate }}</label>
          <input pInputText type="date" [(ngModel)]="formParcours.date_sortie" class="w-full" />
        </div>
        @if (editParcoursId) {
          <div class="fg full">
            <label>{{ 'daara.statut' | translate }}</label>
            <p-select appendTo="body" [options]="statutOptions" [(ngModel)]="formParcours.statut"
                      optionLabel="label" optionValue="value" styleClass="w-full" />
          </div>
        }
      </div>
      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler' | translate" severity="secondary" (onClick)="dialogParcours=false" />
        <p-button [label]="'common.enregistrer' | translate" severity="success" [loading]="saving()" (onClick)="enregistrerParcours()" />
      </ng-template>
    </p-dialog>

    <!-- ════════════════ DIALOG NIVEAU ════════════════ -->
    <p-dialog [header]="(editNiveauId ? 'daara.modifier_niveau' : 'daara.nouveau_niveau') | translate"
              [(visible)]="dialogNiveau" [modal]="true" [style]="{width:'420px'}" [draggable]="false">
      <div class="grid">
        <div class="fg full">
          <label>{{ 'daara.niveau' | translate }} (FR) *</label>
          <input pInputText [(ngModel)]="formNiveau.nom_fr" class="w-full" />
        </div>
        <div class="fg full">
          <label>الاسم (AR)</label>
          <input pInputText [(ngModel)]="formNiveau.nom_ar" class="w-full" dir="rtl" />
        </div>
        <div class="fg">
          <label>{{ 'daara.categorie' | translate }}</label>
          <p-select appendTo="body" [options]="categorieOptions" [(ngModel)]="formNiveau.categorie"
                    optionLabel="label" optionValue="value" styleClass="w-full" />
        </div>
        <div class="fg">
          <label>{{ 'daara.ordre' | translate }}</label>
          <p-inputNumber [(ngModel)]="formNiveau.ordre" [min]="0" styleClass="w-full" />
        </div>
      </div>
      <ng-template pTemplate="footer">
        <p-button [label]="'common.annuler' | translate" severity="secondary" (onClick)="dialogNiveau=false" />
        <p-button [label]="'common.enregistrer' | translate" severity="success" [loading]="saving()" (onClick)="enregistrerNiveau()" />
      </ng-template>
    </p-dialog>
  `,
  styles: [`
    .sub-tabs { display:flex; gap:6px; flex-wrap:wrap; margin-bottom:14px; }
    .sub-tab { background:#1e2d45; color:#cbd5e1; border:1px solid #2a3f5f; border-radius:8px;
               padding:8px 14px; cursor:pointer; font-size:13px; }
    .sub-tab.active { background:#00d4aa; color:#06281f; border-color:#00d4aa; font-weight:600; }
    .nongo-bar { background:#14321f; border:1px solid #1e5a3a; border-radius:8px; padding:8px 12px;
                 margin-bottom:12px; color:#a7f3d0; font-size:13px; }
    .toolbar { margin-bottom:12px; }
    .actions { display:flex; gap:6px; }
    .link-btn { background:none; border:none; color:#7dd3fc; cursor:pointer; font-size:13px; padding:2px 4px; }
    .link-btn.danger { color:#fca5a5; }
    .empty { text-align:center; color:#64748b; padding:18px; }
    .card-form { background:#16233a; border:1px solid #2a3f5f; border-radius:10px; padding:16px; margin-bottom:16px; }
    .card-form h4, h4 { color:#e8f0fe; margin:0 0 12px; font-size:14px; }
    .idjie-hint { color:#94a3b8; font-size:12px; margin:-6px 0 12px; }
    .grid { display:grid; grid-template-columns:repeat(2,1fr); gap:12px; margin-bottom:12px; }
    .fg { display:flex; flex-direction:column; gap:4px; }
    .fg.full { grid-column:1 / -1; }
    .fg.sm { max-width:120px; }
    .fg.check { flex-direction:row; align-items:center; gap:8px; }
    .fg label { font-size:12px; color:#94a3b8; }
    .w-full { width:100%; }
    .prog-head { display:flex; align-items:center; gap:24px; background:#16233a; border:1px solid #2a3f5f;
                 border-radius:10px; padding:18px; margin-bottom:16px; flex-wrap:wrap; }
    .prog-pct { text-align:center; }
    .prog-pct .big { font-size:34px; font-weight:700; color:#00d4aa; }
    .prog-pct .sub { font-size:12px; color:#94a3b8; }
    .prog-info { color:#cbd5e1; font-size:13px; display:flex; flex-direction:column; gap:4px; }
    .juz-grid { display:grid; grid-template-columns:repeat(10,1fr); gap:6px; }
    .juz-cell { border-radius:6px; padding:8px 4px; text-align:center; color:#06281f; font-size:11px;
                display:flex; flex-direction:column; }
    .juz-cell .jn { font-weight:700; }
    .juz-cell .jp { font-size:10px; opacity:.85; }
  `],
})
export class MemorisationComponent implements OnInit {
  private daara = inject(DaaraService);
  private elevesSrv = inject(ElevesService);
  private msg = inject(MessageService);
  private translate = inject(TranslateService);

  vue = signal<'parcours' | 'niveaux' | 'suivi' | 'progression'>('parcours');
  saving = signal(false);
  exporting = signal(false);

  sourates = signal<any[]>([]);
  niveaux  = signal<any[]>([]);
  parcours = signal<any[]>([]);
  eleves   = signal<any[]>([]);
  suivis   = signal<any[]>([]);
  parcoursActif = signal<any | null>(null);
  progression   = signal<any | null>(null);

  // Niveau IDJIE = apprentissage de l'alphabet : le suivi Coran (sourate/verset)
  // et la progression en versets/juz n'ont pas de sens, on suit juste le palier.
  estIdjie = computed(() => this.parcoursActif()?.niveau_categorie === 'IDJIE');
  niveauIdjieOptions = [
    { label: 'Débutant', value: 'DEBUTANT' },
    { label: 'Moyen',    value: 'MOYEN' },
    { label: 'Avancé',   value: 'AVANCE' },
  ];
  formIdjieNiveau: string | null = null;

  riwayaOptions = [{ label: 'Warsh', value: 'WARSH' }, { label: 'Hafs', value: 'HAFS' }];
  sensOptions = [
    { label: 'Depuis la fin (An-Nas → Al-Baqara)', value: 'FIN' },
    { label: 'Depuis le début (Al-Baqara → An-Nas)', value: 'DEBUT' },
  ];
  statutOptions = [
    { label: 'En cours', value: 'EN_COURS' },
    { label: 'Sorti', value: 'SORTI' },
    { label: 'Khatma (terminé)', value: 'KHATMA' },
  ];
  qualiteOptions = [
    { label: 'Bien', value: 'BIEN' },
    { label: 'Moyen', value: 'MOYEN' },
    { label: 'À revoir', value: 'A_REVOIR' },
  ];
  categorieOptions = [
    { label: 'Idjie (alphabet)', value: 'IDJIE' },
    { label: 'Mémorisation', value: 'MEMORISATION' },
    { label: 'Autre', value: 'AUTRE' },
  ];

  dialogParcours = false;
  dialogNiveau   = false;
  editParcoursId: string | null = null;
  editNiveauId: string | null = null;

  formParcours: any = {};
  formNiveau: any = {};
  formSuivi: any = {};

  ngOnInit() {
    this.daara.getSourates().subscribe(list => this.sourates.set(
      (list || []).map(s => ({ ...s, label: `${s.numero}. ${s.nom_fr} (${s.nom_ar})` }))
    ));
    this.chargerNiveaux();
    this.chargerParcours();
    this.elevesSrv.getEleves().subscribe(r => this.eleves.set(r?.results || []));
  }

  chargerNiveaux() { this.daara.getNiveaux().subscribe(l => this.niveaux.set(l || [])); }
  chargerParcours() { this.daara.getParcours().subscribe(l => this.parcours.set(l || [])); }

  // ── Parcours ──
  ouvrirParcours(p?: any) {
    this.editParcoursId = p?.id || null;
    this.formParcours = p
      ? { ...p }
      : { riwaya: 'WARSH', sens: 'FIN', statut: 'EN_COURS', date_debut: new Date().toISOString().split('T')[0] };
    this.dialogParcours = true;
  }
  enregistrerParcours() {
    if (!this.formParcours.eleve) {
      this.msg.add({ severity: 'warn', summary: this.translate.instant('common.requis'),
                     detail: this.translate.instant('daara.nongo_requis') });
      return;
    }
    this.saving.set(true);
    const obs = this.editParcoursId
      ? this.daara.modifierParcours(this.editParcoursId, this.formParcours)
      : this.daara.creerParcours(this.formParcours);
    obs.subscribe({
      next: () => { this.saving.set(false); this.dialogParcours = false; this.chargerParcours(); },
      error: () => { this.saving.set(false); this.erreur(); },
    });
  }
  supprimerParcours(p: any) {
    this.daara.supprimerParcours(p.id).subscribe(() => this.chargerParcours());
  }
  ouvrirNongo(p: any) { this.parcoursActif.set(p); this.vue.set('suivi'); this.chargerSuivi(); }

  // ── Niveaux ──
  ouvrirNiveau(n?: any) {
    this.editNiveauId = n?.id || null;
    this.formNiveau = n ? { ...n } : { categorie: 'MEMORISATION', ordre: 0 };
    this.dialogNiveau = true;
  }
  enregistrerNiveau() {
    if (!this.formNiveau.nom_fr) {
      this.msg.add({ severity: 'warn', summary: this.translate.instant('common.requis'),
                     detail: this.translate.instant('daara.niveau_requis') });
      return;
    }
    this.saving.set(true);
    const obs = this.editNiveauId
      ? this.daara.modifierNiveau(this.editNiveauId, this.formNiveau)
      : this.daara.creerNiveau(this.formNiveau);
    obs.subscribe({
      next: () => { this.saving.set(false); this.dialogNiveau = false; this.chargerNiveaux(); },
      error: () => { this.saving.set(false); this.erreur(); },
    });
  }
  supprimerNiveau(n: any) { this.daara.supprimerNiveau(n.id).subscribe(() => this.chargerNiveaux()); }

  // ── Suivi ──
  chargerSuivi() {
    const p = this.parcoursActif();
    if (!p) return;
    // Parcours IDJIE : on ne suit que le palier alphabet, pas le suivi Coran.
    if (this.estIdjie()) {
      this.formIdjieNiveau = p.niveau_idjie || null;
      return;
    }
    this.formSuivi = { date: new Date().toISOString().split('T')[0], qualite: 'MOYEN',
                       verset_debut: 1, verset_fin: 1, present: true, observation: '' };
    this.daara.getSuivi(p.id).subscribe(l => this.suivis.set(l || []));
  }

  enregistrerNiveauIdjie() {
    const p = this.parcoursActif();
    if (!p) return;
    this.saving.set(true);
    this.daara.modifierParcours(p.id, { niveau_idjie: this.formIdjieNiveau }).subscribe({
      next: (maj) => {
        this.saving.set(false);
        // Refléter le nouveau palier dans le parcours actif et la liste.
        this.parcoursActif.set({ ...p, niveau_idjie: this.formIdjieNiveau });
        this.chargerParcours();
        this.msg.add({ severity: 'success', summary: this.translate.instant('common.succes'),
                       detail: this.translate.instant('daara.idjie_enregistre') });
      },
      error: () => { this.saving.set(false); this.erreur(); },
    });
  }
  enregistrerSuivi() {
    const p = this.parcoursActif();
    if (!p) return;
    this.saving.set(true);
    this.daara.creerSuivi({ ...this.formSuivi, parcours: p.id }).subscribe({
      next: () => { this.saving.set(false); this.chargerSuivi(); },
      error: () => { this.saving.set(false); this.erreur(); },
    });
  }
  supprimerSuivi(s: any) { this.daara.supprimerSuivi(s.id).subscribe(() => this.chargerSuivi()); }

  // ── Progression ──
  chargerProgression() {
    const p = this.parcoursActif();
    if (!p) return;
    this.progression.set(null);
    this.daara.getProgression(p.id).subscribe(pr => this.progression.set(pr));
  }
  couleurJuz(pct: number): string {
    if (pct >= 100) return '#00d4aa';
    if (pct > 0)    return `rgba(0,212,170,${0.25 + 0.6 * pct / 100})`;
    return '#1e2d45';
  }
  exporterPdf() {
    const p = this.parcoursActif();
    if (!p) return;
    this.exporting.set(true);
    this.daara.getRapportPdf(p.id).subscribe({
      next: (blob: Blob) => {
        this.exporting.set(false);
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = `rapport_${p.eleve_nom || 'nongo'}.pdf`; a.click();
        URL.revokeObjectURL(url);
      },
      error: () => { this.exporting.set(false); this.erreur(); },
    });
  }

  private erreur() {
    this.msg.add({ severity: 'error', summary: this.translate.instant('common.erreur'),
                   detail: this.translate.instant('daara.erreur_action') });
  }
}
