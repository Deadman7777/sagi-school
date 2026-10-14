import { Injectable, inject } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { environment } from '../../../environments/environment';
import { MemoireEcransService } from './memoire-ecrans.service';

/** Un filtre non renseigné est légitime : on l'accepte, puis on l'ignore. */
export type ParamsRecord = Record<string, string | number | boolean | null | undefined>;

function toHttpParams(params?: ParamsRecord): HttpParams {
  let httpParams = new HttpParams();
  if (!params) return httpParams;
  for (const [cle, valeur] of Object.entries(params)) {
    if (valeur === undefined || valeur === null || valeur === '') continue;
    httpParams = httpParams.set(cle, String(valeur));
  }
  return httpParams;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private base = environment.apiUrl;
  get baseUrl(): string { return this.base; }

  private memoire = inject(MemoireEcransService);

  constructor(private http: HttpClient) {}

  /**
   * Les paramètres absents sont IGNORÉS, ils ne partent pas dans l'URL.
   *
   * `Object.entries` conserve les clés dont la valeur vaut `undefined`, et
   * `HttpParams.set()` la convertit en chaîne : un filtre non renseigné
   * partait littéralement en `?q=undefined`, que le backend prenait pour un
   * critère de recherche. L'écran « Anciens élèves » était vide en permanence.
   */
  get<T>(path: string, params?: ParamsRecord) {
    return this.http.get<T>(`${this.base}${path}`, { params: toHttpParams(params) });
  }

  /**
   * Comme `get`, mais émet d'abord la dernière réponse connue de cet écran
   * (même chemin, mêmes paramètres), PUIS la fraîche : on revient sur un
   * module, les données sont là tout de suite (voir MemoireEcransService).
   *
   * Réservé à l'AFFICHAGE d'une liste, d'un tableau de bord, d'un état. Jamais
   * pour pré-remplir un formulaire (la fraîche écraserait la saisie), ni
   * derrière firstValueFrom/take(1) (on n'aurait que la vieille réponse), ni
   * dans un forkJoin (il attendrait quand même le serveur : combineLatest).
   */
  lire<T>(path: string, params?: ParamsRecord) {
    const cles = toHttpParams(params);
    const propres = Object.fromEntries(cles.keys().sort().map(k => [k, cles.get(k)]));
    return this.memoire.avecMemoire<T>(path, propres, this.get<T>(path, params));
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

  getBlob(path: string, params?: ParamsRecord) {
    return this.http.get(`${this.base}${path}`,
                         { responseType: 'blob', params: toHttpParams(params) });
  }
  /** Comme getBlob, mais rend la réponse entière : certains PDF portent une
   *  information dans leurs en-têtes (combien d'élèves sont restés de côté). */
  getBlobReponse(path: string, params?: ParamsRecord) {
    return this.http.get(`${this.base}${path}`,
                         { responseType: 'blob', observe: 'response',
                           params: toHttpParams(params) });
  }
}
