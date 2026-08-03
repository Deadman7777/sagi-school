import {
  ChangeDetectionStrategy, Component, ElementRef, effect,
  inject, signal, viewChild,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { SamaService } from '../../core/services/sama.service';

/**
 * SAMA, joignable depuis n'importe quel écran.
 *
 * Un panneau latéral, pas une page : quelqu'un qui bute sur la saisie d'une
 * charge a besoin d'aide *sans quitter* son écran. L'envoyer sur une autre
 * page lui fait perdre ce qu'il était en train de faire — et c'est précisément
 * le moment où il abandonne et téléphone au support.
 */
@Component({
  selector: 'app-sama-panneau',
  imports: [FormsModule],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (sama.disponible()) {
    <button class="sama-fab" (click)="basculer()"
            [attr.aria-expanded]="ouvert()"
            aria-controls="sama-panneau"
            [attr.aria-label]="ouvert() ? 'Fermer l\\'assistant SAMA' : 'Ouvrir l\\'assistant SAMA'">
      @if (ouvert()) { <span aria-hidden="true">✕</span> }
      @else { <span aria-hidden="true">✨</span> }
    </button>

    @if (ouvert()) {
      <aside class="sama" id="sama-panneau" role="complementary" aria-label="Assistant SAMA">
        <header class="sama-tete">
          <div>
            <b>SAMA</b>
            <span>Assistant HADY GESMAN</span>
          </div>
          <button class="sama-neuf" (click)="recommencer()"
                  title="Nouvelle conversation">↻</button>
        </header>

        <div class="sama-fil" #fil aria-live="polite" aria-atomic="false">
          @if (sama.messages().length === 0) {
            <div class="sama-accueil">
              <p>Bonjour. Je suis <b>SAMA</b>, votre conseiller HADY GESMAN.</p>
              <p class="sama-aide">Posez-moi une question sur votre gestion,
                votre comptabilité, votre fiscalité — ou demandez-moi un
                document.</p>
              <div class="sama-pistes">
                @for (p of pistes; track p) {
                  <button (click)="poser(p)">{{ p }}</button>
                }
              </div>
            </div>
          }

          @for (m of sama.messages(); track $index) {
            <div class="sama-bulle" [class.moi]="m.role === 'user'">
              @if (m.contenu) {
                <div class="sama-texte">{{ m.contenu }}</div>
              } @else {
                <div class="sama-points" aria-label="SAMA rédige sa réponse">
                  <span></span><span></span><span></span>
                </div>
              }
            </div>
          }

          @if (sama.erreur(); as err) {
            <div class="sama-erreur" role="alert">{{ err }}</div>
          }
        </div>

        <form class="sama-saisie" (ngSubmit)="envoyer()">
          <label class="sr-only" for="sama-champ">Votre question</label>
          <textarea id="sama-champ" [(ngModel)]="brouillon" name="brouillon"
                    rows="1" placeholder="Écrivez votre question…"
                    (keydown.enter)="surEntree($event)"
                    [disabled]="sama.enCours()"></textarea>
          <button type="submit" [disabled]="sama.enCours() || !brouillon.trim()"
                  aria-label="Envoyer">➤</button>
        </form>

        <p class="sama-pied">
          SAMA peut se tromper. Ses réponses fiscales et comptables sont une
          assistance informative, pas un avis juridique.
        </p>
      </aside>
    }
    }
  `,
  styles: [`
    .sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px;
               overflow:hidden; clip:rect(0 0 0 0); white-space:nowrap; border:0; }

    .sama-fab {
      position:fixed; right:22px; bottom:22px; z-index:1200;
      width:52px; height:52px; border-radius:50%; border:none; cursor:pointer;
      background:var(--primary, #0B5E4A); color:#fff; font-size:20px;
      box-shadow:0 6px 20px rgba(0,0,0,.28);
      transition:transform .15s ease, box-shadow .15s ease;
    }
    .sama-fab:hover { transform:translateY(-2px); box-shadow:0 9px 26px rgba(0,0,0,.34); }
    .sama-fab:focus-visible { outline:3px solid var(--primary, #0B5E4A); outline-offset:3px; }

    .sama {
      position:fixed; right:0; top:0; bottom:0; z-index:1190;
      width:min(430px, 100vw); display:flex; flex-direction:column;
      background:var(--surface, #fff); border-left:1px solid var(--border, #e2e6e3);
      box-shadow:-14px 0 40px rgba(0,0,0,.14);
    }

    .sama-tete {
      display:flex; align-items:center; justify-content:space-between;
      gap:10px; padding:14px 58px 14px 18px;
      border-bottom:1px solid var(--border, #e2e6e3);
    }
    .sama-tete b { display:block; font-size:15px; letter-spacing:.02em; }
    .sama-tete span { font-size:11.5px; color:var(--text-2, #6b7a73); }
    .sama-neuf { background:none; border:none; cursor:pointer; font-size:17px;
                 color:var(--text-2, #6b7a73); padding:6px 8px; border-radius:6px; }
    .sama-neuf:hover { background:var(--surface-hover, #f1f4f2); }

    .sama-fil { flex:1; overflow-y:auto; padding:16px; display:flex;
                flex-direction:column; gap:12px; }

    .sama-accueil { font-size:14px; line-height:1.6; color:var(--text-2, #6b7a73); }
    .sama-accueil b { color:var(--text, #16211e); }
    .sama-aide { margin-top:8px; }
    .sama-pistes { display:flex; flex-direction:column; gap:7px; margin-top:16px; }
    .sama-pistes button {
      text-align:left; font-size:13px; padding:9px 12px; cursor:pointer;
      background:var(--surface-2, #f6f8f7); color:var(--text, #16211e);
      border:1px solid var(--border, #e2e6e3); border-radius:9px;
      transition:border-color .12s ease;
    }
    .sama-pistes button:hover { border-color:var(--primary, #0B5E4A); }

    .sama-bulle { max-width:88%; }
    .sama-bulle.moi { align-self:flex-end; }
    .sama-texte {
      font-size:14px; line-height:1.62; padding:10px 13px; border-radius:12px;
      background:var(--surface-2, #f6f8f7); color:var(--text, #16211e);
      /* La réponse arrive en texte brut : les retours à la ligne comptent. */
      white-space:pre-wrap; overflow-wrap:anywhere;
    }
    .moi .sama-texte { background:var(--primary, #0B5E4A); color:#fff; }

    .sama-points { display:flex; gap:4px; padding:12px 13px; }
    .sama-points span {
      width:6px; height:6px; border-radius:50%; background:var(--text-2, #6b7a73);
      animation:sama-pulse 1.2s infinite ease-in-out;
    }
    .sama-points span:nth-child(2) { animation-delay:.18s; }
    .sama-points span:nth-child(3) { animation-delay:.36s; }
    @keyframes sama-pulse { 0%,80%,100% { opacity:.25; } 40% { opacity:1; } }

    .sama-erreur {
      font-size:13px; line-height:1.55; padding:10px 12px; border-radius:9px;
      background:#FBEAE7; color:#9E2F23; border:1px solid #F0C4BC;
    }

    .sama-saisie {
      display:flex; gap:8px; align-items:flex-end; padding:12px 14px;
      border-top:1px solid var(--border, #e2e6e3);
    }
    .sama-saisie textarea {
      flex:1; resize:none; max-height:140px; font:inherit; font-size:14px;
      padding:9px 12px; border-radius:10px; color:var(--text, #16211e);
      border:1px solid var(--border, #e2e6e3); background:var(--surface, #fff);
    }
    .sama-saisie textarea:focus-visible { outline:2px solid var(--primary, #0B5E4A);
                                          outline-offset:1px; }
    .sama-saisie button {
      width:38px; height:38px; border-radius:10px; border:none; cursor:pointer;
      background:var(--primary, #0B5E4A); color:#fff; font-size:15px;
    }
    .sama-saisie button:disabled { opacity:.4; cursor:default; }

    .sama-pied { margin:0; padding:0 14px 12px; font-size:10.5px; line-height:1.5;
                 color:var(--text-3, #93a29b); }

    @media (prefers-reduced-motion: reduce) {
      .sama-fab, .sama-points span { transition:none; animation:none; }
    }
  `],
})
export class SamaPanneauComponent {
  sama = inject(SamaService);

  ouvert = signal(false);
  brouillon = '';

  private fil = viewChild<ElementRef<HTMLElement>>('fil');

  readonly pistes = [
    'Comment enregistrer un paiement partiel ?',
    'Quelles sont mes obligations fiscales cette année ?',
    'Prépare-moi un devis pour une licence Pro',
  ];

  constructor() {
    this.sama.verifierDisponibilite();

    // Suivre le texte pendant qu'il s'écrit : sans cela, la réponse défile
    // hors de l'écran et l'utilisateur croit qu'il ne se passe rien.
    effect(() => {
      this.sama.messages();
      queueMicrotask(() => {
        const el = this.fil()?.nativeElement;
        if (el) el.scrollTop = el.scrollHeight;
      });
    });
  }

  basculer() { this.ouvert.update((o) => !o); }

  recommencer() {
    this.sama.nouvelleConversation();
    this.brouillon = '';
  }

  poser(question: string) {
    this.brouillon = question;
    this.envoyer();
  }

  /** Entrée envoie, Maj+Entrée passe à la ligne — l'usage d'une messagerie. */
  surEntree(evt: Event) {
    const e = evt as KeyboardEvent;
    if (e.shiftKey) return;
    e.preventDefault();
    this.envoyer();
  }

  envoyer() {
    const texte = this.brouillon.trim();
    if (!texte || this.sama.enCours()) return;
    this.brouillon = '';
    this.sama.envoyer(texte);
  }
}
