import { Injectable, effect, inject } from '@angular/core';
import { Observable, concat, finalize, of, share, tap } from 'rxjs';

import { AuthService } from './auth.service';

/**
 * Dernière réponse connue de chaque écran, pour l'afficher aussitôt qu'on y
 * revient pendant que la vraie se recharge (14/10/2026 : « tu cliques un
 * module, à l'instant tu vois les données »).
 *
 * - En MÉMOIRE seulement : rien n'est écrit sur le disque d'un poste partagé,
 *   et tout disparaît au rechargement de la page.
 * - La clé porte l'utilisateur et l'école : un super admin qui change d'école
 *   ne voit jamais les chiffres de la précédente.
 * - Vidée à la déconnexion.
 *
 * À n'utiliser que pour de l'AFFICHAGE : une réponse servie de mémoire peut
 * avoir quelques secondes de retard, la fraîche la remplace dès qu'elle arrive.
 */
@Injectable({ providedIn: 'root' })
export class MemoireEcransService {
  /** Au-delà, la plus ancienne réponse est oubliée. */
  static readonly MAX = 120;

  private auth = inject(AuthService);
  private reponses = new Map<string, unknown>();
  /** Requêtes parties et pas encore revenues, par clé. */
  private enVol = new Map<string, Observable<unknown>>();

  constructor() {
    effect(() => { if (!this.auth.currentUser()) this.reponses.clear(); });
  }

  private cle(url: string, params?: object): string {
    return [this.auth.currentUser()?.id ?? '', this.auth.effectiveTenantId ?? '',
            url, JSON.stringify(params ?? {})].join('|');
  }

  lire<T>(url: string, params?: object): T | undefined {
    return this.reponses.get(this.cle(url, params)) as T | undefined;
  }

  ecrire(url: string, params: object | undefined, valeur: unknown) {
    const cle = this.cle(url, params);
    this.reponses.delete(cle);            // remise en fin : la plus récente
    this.reponses.set(cle, valeur);
    if (this.reponses.size > MemoireEcransService.MAX) {
      this.reponses.delete(this.reponses.keys().next().value!);
    }
  }

  /**
   * Émet la réponse connue (s'il y en a une), PUIS la fraîche, mémorisée au
   * passage. Avec forkJoin, préférer combineLatest : forkJoin ne garde que la
   * dernière émission et attendrait le serveur.
   */
  avecMemoire<T>(url: string, params: object | undefined, frais$: Observable<T>): Observable<T> {
    const connu = this.lire<T>(url, params);
    const frais = this.partage(url, params, frais$);
    return connu === undefined ? frais : concat(of(connu), frais);
  }

  /**
   * Deux écrans qui demandent la même chose au même moment se partagent UNE
   * requête : à l'ouverture du tableau de bord, les conseils fiscaux partaient
   * deux fois (carte et synthèse des modules), une seconde de calcul serveur
   * en double sur un poste qui traite une requête à la fois.
   */
  private partage<T>(url: string, params: object | undefined, frais$: Observable<T>): Observable<T> {
    const cle = this.cle(url, params);
    let vol = this.enVol.get(cle) as Observable<T> | undefined;
    if (!vol) {
      vol = frais$.pipe(
        tap(v => this.ecrire(url, params, v)),
        finalize(() => this.enVol.delete(cle)),
        share(),
      );
      this.enVol.set(cle, vol);
    }
    return vol;
  }
}
