import { Injectable, inject } from '@angular/core';
import { ApiService } from './api.service';

@Injectable({ providedIn: 'root' })
export class GmrfService {
  private api = inject(ApiService);

  // Tableau de bord décisionnel
  getDashboard() { return this.api.get<any>('/gmrf/dashboard/'); }
  getAnalyse()   { return this.api.get<any>('/gmrf/analyse/'); }

  // Types de financement (paramétrables)
  getTypes()                        { return this.api.get<any[]>('/gmrf/types/'); }
  creerType(data: any)              { return this.api.post<any>('/gmrf/types/', data); }
  modifierType(id: string, data: any) { return this.api.patch<any>(`/gmrf/types/${id}/`, data); }
  supprimerType(id: string)         { return this.api.delete<any>(`/gmrf/types/${id}/`); }

  // Financements simples (dons, subventions, partenariats, revenus…)
  getFinancements(params?: any)     { return this.api.get<any>('/gmrf/financements/', params); }
  creerFinancement(data: any)       { return this.api.post<any>('/gmrf/financements/', data); }
  actionFinancement(id: string, data: any) { return this.api.patch<any>(`/gmrf/financements/${id}/`, data); }

  // NATT / Tontine
  getCycles()                       { return this.api.get<any[]>('/gmrf/natt/'); }
  getCycle(id: string)              { return this.api.get<any>(`/gmrf/natt/${id}/`); }
  creerCycle(data: any)             { return this.api.post<any>('/gmrf/natt/', data); }
  recevoirCagnotte(cycleId: string, data: any) { return this.api.post<any>(`/gmrf/natt/${cycleId}/reception/`, data); }
  actionCotisation(id: string, data: any)      { return this.api.patch<any>(`/gmrf/cotisations/${id}/`, data); }

  // Prêts
  getPrets()                        { return this.api.get<any>('/gmrf/prets/'); }
  getPret(id: string)               { return this.api.get<any>(`/gmrf/prets/${id}/`); }
  creerPret(data: any)              { return this.api.post<any>('/gmrf/prets/', data); }
  simulerAmortissement(data: any)   { return this.api.post<any>('/gmrf/prets/', { ...data, action: 'simuler' }); }
  actionEcheance(id: string, data: any) { return this.api.patch<any>(`/gmrf/echeances/${id}/`, data); }

  // PDF
  getPretPdf(id: string)            { return this.api.getBlob(`/gmrf/prets/${id}/pdf/`); }
  getNattPdf(id: string)            { return this.api.getBlob(`/gmrf/natt/${id}/pdf/`); }

  // Documents joints
  ajouterDocument(type: string, id: string, doc: any) { return this.api.post<any>(`/gmrf/documents/${type}/${id}/`, doc); }
  supprimerDocument(type: string, id: string, index: number) { return this.api.delete<any>(`/gmrf/documents/${type}/${id}/?index=${index}`); }
}
