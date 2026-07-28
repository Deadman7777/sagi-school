import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { environment } from '../../../environments/environment';

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
}
