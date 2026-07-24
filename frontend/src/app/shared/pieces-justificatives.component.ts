import { ChangeDetectionStrategy, Component, effect, inject, input, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { SelectModule } from 'primeng/select';
import { GouvernanceService } from '../core/services/gouvernance.service';

interface Piece {
  id: string; type_piece: string; type_piece_label: string;
  nom: string; taille: number; created_at?: string;
}

/**
 * Widget réutilisable de Gestion Électronique des Documents (GED).
 * Rattache des pièces justificatives à n'importe quel objet métier via son
 * couple (objet_type, objet_id). Utilisé sur les charges, les immobilisations
 * et les lignes de budget. L'objet doit déjà être enregistré (objet_id requis).
 */
@Component({
  selector: 'app-pieces-justificatives',
  imports: [DecimalPipe, FormsModule, SelectModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="pj">
      <div class="pj-add">
        <p-select [options]="typesPiece" [(ngModel)]="typeUpload" optionLabel="label"
                  optionValue="value" styleClass="w-full" appendTo="body" [style]="{flex:'1'}" />
        <label class="pj-btn" [class.disabled]="!objetId()">
          <input type="file" hidden (change)="onFichier($event)" [disabled]="!objetId()" />
          📎 Joindre
        </label>
      </div>

      @if (chargement()) {
        <p class="pj-empty">Chargement…</p>
      } @else if (pieces().length === 0) {
        <p class="pj-empty">Aucune pièce justificative.</p>
      } @else {
        <ul class="pj-list">
          @for (pc of pieces(); track pc.id) {
            <li class="pj-item">
              <span class="pj-type">{{ pc.type_piece_label }}</span>
              <span class="pj-nom" [title]="pc.nom">{{ pc.nom }}</span>
              <span class="pj-taille">{{ (pc.taille / 1024) | number:'1.0-0' }} Ko</span>
              <button type="button" class="pj-ic" (click)="telecharger(pc)" title="Télécharger">⬇</button>
              <button type="button" class="pj-ic danger" (click)="supprimer(pc)" title="Supprimer">✕</button>
            </li>
          }
        </ul>
      }
      @if (erreurMsg()) { <p class="pj-err">{{ erreurMsg() }}</p> }
    </div>
  `,
  styles: [`
    .pj { display:flex; flex-direction:column; gap:8px; }
    .pj-add { display:flex; gap:8px; align-items:stretch; }
    .pj-btn { display:flex; align-items:center; gap:6px; padding:6px 12px; background:#1565c0;
              color:#fff; border-radius:6px; cursor:pointer; font-size:13px; white-space:nowrap; }
    .pj-btn.disabled { opacity:.5; cursor:not-allowed; }
    .pj-empty { font-size:12px; color:var(--text-3); margin:2px 0; }
    .pj-err { font-size:12px; color:#f87171; margin:2px 0; }
    .pj-list { list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:4px; }
    .pj-item { display:flex; align-items:center; gap:8px; background:var(--surface); border:1px solid var(--border);
               border-radius:6px; padding:5px 8px; font-size:12px; }
    .pj-type { color:#4fc3f7; font-size:10px; text-transform:uppercase; letter-spacing:.5px; flex:none; }
    .pj-nom { color:var(--text); flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .pj-taille { color:var(--text-3); flex:none; font-family:monospace; }
    .pj-ic { background:transparent; border:none; color:var(--text-2); cursor:pointer; font-size:14px; padding:2px 4px; }
    .pj-ic.danger { color:#f87171; }
  `],
})
export class PiecesJustificativesComponent {
  /** Type d'objet (CHARGE, IMMOBILISATION, BUDGET…) et son UUID. */
  objetType = input<string>('');
  objetId   = input<string>('');

  private gouv = inject(GouvernanceService);

  pieces     = signal<Piece[]>([]);
  chargement = signal(false);
  erreurMsg  = signal('');
  typeUpload = 'FACTURE';
  typesPiece = [
    { label: 'Facture', value: 'FACTURE' }, { label: 'Devis', value: 'DEVIS' },
    { label: 'Bon de commande', value: 'BON_COMMANDE' }, { label: 'Bon de livraison', value: 'BON_LIVRAISON' },
    { label: 'Contrat', value: 'CONTRAT' }, { label: 'Convention', value: 'CONVENTION' },
    { label: 'Reçu', value: 'RECU' }, { label: 'Relevé bancaire', value: 'RELEVE' },
    { label: 'Photo', value: 'PHOTO' }, { label: 'PDF', value: 'PDF' },
    { label: 'Word', value: 'WORD' }, { label: 'Autre', value: 'AUTRE' },
  ];

  constructor() {
    // Recharge la liste dès que l'objet ciblé change.
    effect(() => {
      const id = this.objetId();
      const type = this.objetType();
      if (id && type) this.charger(id, type);
      else this.pieces.set([]);
    });
  }

  private charger(id: string, type: string) {
    this.chargement.set(true);
    this.gouv.getPieces(type, id).subscribe({
      next: d => { this.pieces.set((d || []) as Piece[]); this.chargement.set(false); },
      error: () => { this.chargement.set(false); },
    });
  }

  onFichier(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file || !this.objetId()) return;
    if (file.size > 4_400_000) {
      this.erreurMsg.set('Fichier trop volumineux (max ~4,5 Mo)'); input.value = ''; return;
    }
    this.erreurMsg.set('');
    const reader = new FileReader();
    reader.onload = () => {
      this.gouv.ajouterPiece({
        objet_type: this.objetType(), objet_id: this.objetId(),
        type_piece: this.typeUpload, nom: file.name, contenu: reader.result as string,
      }).subscribe({
        next: () => this.charger(this.objetId(), this.objetType()),
        error: (e) => this.erreurMsg.set(e?.error?.error || 'Ajout impossible'),
      });
    };
    reader.readAsDataURL(file);
    input.value = '';
  }

  telecharger(pc: Piece) {
    this.gouv.getPiece(pc.id).subscribe({
      next: (full: any) => {
        const a = document.createElement('a');
        a.href = full.contenu; a.download = pc.nom; a.click();
      },
      error: () => this.erreurMsg.set('Téléchargement impossible'),
    });
  }

  supprimer(pc: Piece) {
    if (!confirm(`Supprimer « ${pc.nom} » ?`)) return;
    this.gouv.supprimerPiece(pc.id).subscribe({
      next: () => this.charger(this.objetId(), this.objetType()),
      error: () => this.erreurMsg.set('Suppression impossible'),
    });
  }
}
