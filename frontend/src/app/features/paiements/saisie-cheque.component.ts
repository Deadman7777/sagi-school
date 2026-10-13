import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { InputTextModule } from 'primeng/inputtext';

/** Détails d'un chèque reçu, inscrits au registre des chèques à l'encaissement. */
export interface DetailCheque {
  numero: string;
  banque: string;
  tireur: string;
  date_emission: string;
}

export function chequeVide(): DetailCheque {
  return { numero: '', banque: '', tireur: '', date_emission: '' };
}

/** Banques courantes au Sénégal — simple suggestion, la saisie reste libre. */
const BANQUES = ['CBAO', 'Société Générale (SGBS)', 'BICIS', 'Ecobank', 'Bank of Africa (BOA)',
  'Banque Atlantique', 'BHS', 'BIS', 'LBA (ex-CNCAS)', 'Orabank', 'UBA', 'Coris Bank',
  'BNDE', 'CBI', 'BSIC', 'Banque Islamique du Sénégal', 'Citibank', 'La Poste (CCP)'];

@Component({
  selector: 'app-saisie-cheque',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, InputTextModule],
  template: `
    <div class="bloc-cheque">
      <div class="bc-titre">🧾 Détails du chèque <span class="bc-aide">— suivi jusqu'à l'encaissement</span></div>
      <div class="bc-grille">
        <div>
          <label for="chq-numero">N° du chèque *</label>
          <input pInputText id="chq-numero" [(ngModel)]="cheque().numero" class="w-full" />
        </div>
        <div>
          <label for="chq-banque">Banque *</label>
          <input pInputText id="chq-banque" [(ngModel)]="cheque().banque" class="w-full" list="chq-banques" />
          <datalist id="chq-banques">
            @for (b of banques; track b) { <option [value]="b"></option> }
          </datalist>
        </div>
        <div>
          <label for="chq-tireur">Tireur (titulaire du compte)</label>
          <input pInputText id="chq-tireur" [(ngModel)]="cheque().tireur" class="w-full" />
        </div>
        <div>
          <label for="chq-date">Date d'émission</label>
          <input pInputText id="chq-date" type="date" [(ngModel)]="cheque().date_emission" class="w-full" />
        </div>
      </div>
    </div>
  `,
  styles: [`
    .bloc-cheque { margin-top:10px; padding:10px 12px; border:1px dashed var(--border); border-radius:8px; }
    .bc-titre { font-size:13px; font-weight:600; margin-bottom:8px; }
    .bc-aide { font-weight:400; color:var(--text-3); font-size:12px; }
    .bc-grille { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
    .bc-grille label { display:block; font-size:12px; color:var(--text-2); margin-bottom:3px; }
  `],
})
export class SaisieChequeComponent {
  readonly cheque = input.required<DetailCheque>();
  banques = BANQUES;
}
