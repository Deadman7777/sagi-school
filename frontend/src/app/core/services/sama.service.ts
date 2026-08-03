import { Injectable, inject, signal } from '@angular/core';
import { AuthService } from './auth.service';
import { environment } from '../../../environments/environment';

export interface MessageSama {
  role: 'user' | 'assistant';
  contenu: string;
}

/**
 * Le lien avec SAMA. La réponse arrive **au fil de l'eau** : le serveur pousse
 * le texte à mesure qu'il s'écrit, et l'interface l'affiche sans attendre.
 *
 * `fetch` plutôt que `HttpClient` : Angular ne restitue un corps de réponse
 * qu'une fois complet, ce qui ferait patienter l'utilisateur plusieurs secondes
 * devant un écran vide. Le lecteur de flux de `fetch` donne les octets dès
 * qu'ils arrivent.
 */
@Injectable({ providedIn: 'root' })
export class SamaService {
  private auth = inject(AuthService);

  /** null tant qu'on ne sait pas — le bouton reste caché d'ici là. */
  readonly disponible = signal<boolean | null>(null);
  readonly messages = signal<MessageSama[]>([]);
  readonly enCours = signal(false);
  readonly erreur = signal<string | null>(null);
  private conversationId: string | null = null;

  /** Interroge l'installation une fois : assistant configuré ou non. */
  async verifierDisponibilite() {
    if (this.disponible() !== null) return;
    try {
      const r = await fetch(`${environment.apiUrl}/assistant/conversations/etat/`,
                            { headers: this.entetes() });
      this.disponible.set(r.ok ? (await r.json()).disponible === true : false);
    } catch {
      this.disponible.set(false);
    }
  }

  /** Les en-têtes que l'intercepteur HTTP poserait — `fetch` le court-circuite.
   *  Oublier X-Tenant-ID casse la délégation d'un super-admin. */
  private entetes(): Record<string, string> {
    const e: Record<string, string> = { 'Content-Type': 'application/json' };
    const jeton = localStorage.getItem('access_token');
    if (jeton) e['Authorization'] = `Bearer ${jeton}`;
    const tenantId = this.auth.effectiveTenantId;
    if (tenantId && tenantId !== 'null') e['X-Tenant-ID'] = tenantId;
    return e;
  }

  nouvelleConversation() {
    this.conversationId = null;
    this.messages.set([]);
    this.erreur.set(null);
  }

  /** Envoie une question et remplit la réponse au fur et à mesure. */
  async envoyer(contenu: string) {
    if (this.enCours()) return;
    this.erreur.set(null);
    this.messages.update((m) => [...m, { role: 'user', contenu }]);
    this.enCours.set(true);

    // La réponse est ajoutée vide puis complétée : l'utilisateur voit le
    // curseur avancer plutôt qu'un écran figé.
    this.messages.update((m) => [...m, { role: 'assistant', contenu: '' }]);

    try {
      const reponse = await fetch(
        `${environment.apiUrl}/assistant/conversations/message/`,
        {
          method: 'POST',
          headers: this.entetes(),
          body: JSON.stringify({ contenu, conversation: this.conversationId }),
        },
      );

      if (!reponse.ok || !reponse.body) {
        throw new Error(`HTTP ${reponse.status}`);
      }

      const lecteur = reponse.body.getReader();
      const decodeur = new TextDecoder();
      let reste = '';

      for (;;) {
        const { done, value } = await lecteur.read();
        if (done) break;
        reste += decodeur.decode(value, { stream: true });

        // Un événement se termine par une ligne vide ; un morceau reçu peut
        // en contenir plusieurs, ou couper le dernier en deux.
        const parts = reste.split('\n\n');
        reste = parts.pop() ?? '';
        for (const part of parts) {
          const ligne = part.trim();
          if (!ligne.startsWith('data: ')) continue;
          this.appliquer(JSON.parse(ligne.slice(6)));
        }
      }
    } catch {
      this.erreur.set(
        "L'assistant n'a pas pu répondre. Vérifiez votre connexion, puis réessayez.",
      );
      // Retirer la bulle vide : mieux vaut aucune réponse qu'une réponse creuse.
      this.messages.update((m) =>
        m[m.length - 1]?.contenu === '' ? m.slice(0, -1) : m,
      );
    } finally {
      this.enCours.set(false);
    }
  }

  private appliquer(evt: Record<string, string | boolean>) {
    switch (evt['type']) {
      case 'debut':
        this.conversationId = evt['conversation'] as string;
        break;
      case 'texte':
        this.messages.update((m) => {
          const copie = [...m];
          const dernier = copie[copie.length - 1];
          copie[copie.length - 1] = {
            ...dernier,
            contenu: dernier.contenu + (evt['texte'] as string),
          };
          return copie;
        });
        break;
      case 'erreur':
        this.erreur.set(evt['message'] as string);
        this.messages.update((m) =>
          m[m.length - 1]?.contenu === '' ? m.slice(0, -1) : m,
        );
        break;
    }
  }
}
