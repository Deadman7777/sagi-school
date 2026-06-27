import { Injectable, inject } from '@angular/core';
import { ApiService } from './api.service';

@Injectable({ providedIn: 'root' })
export class DaaraService {
  private api = inject(ApiService);

  // Référence Coran
  getSourates()                 { return this.api.get<any[]>('/daara/sourates/'); }
  getSubdivisions(params?: any) { return this.api.get<any[]>('/daara/subdivisions/', params); }

  // Niveaux (IDJIE + étapes), configurables
  getNiveaux()                  { return this.api.get<any[]>('/daara/niveaux/'); }
  creerNiveau(data: any)        { return this.api.post<any>('/daara/niveaux/', data); }
  modifierNiveau(id: string, data: any) { return this.api.patch<any>(`/daara/niveaux/${id}/`, data); }
  supprimerNiveau(id: string)   { return this.api.delete<any>(`/daara/niveaux/${id}/`); }

  // Parcours du NONGO
  getParcours(params?: any)     { return this.api.get<any[]>('/daara/parcours/', params); }
  creerParcours(data: any)      { return this.api.post<any>('/daara/parcours/', data); }
  modifierParcours(id: string, data: any) { return this.api.patch<any>(`/daara/parcours/${id}/`, data); }
  supprimerParcours(id: string) { return this.api.delete<any>(`/daara/parcours/${id}/`); }

  // Suivi quotidien
  getSuivi(parcoursId: string)  { return this.api.get<any[]>('/daara/suivi/', { parcours: parcoursId }); }
  creerSuivi(data: any)         { return this.api.post<any>('/daara/suivi/', data); }
  supprimerSuivi(id: string)    { return this.api.delete<any>(`/daara/suivi/${id}/`); }

  // Progression calculée
  getProgression(parcoursId: string) { return this.api.get<any>('/daara/progression/', { parcours: parcoursId }); }

  // Rapport parent (PDF bilingue) — Phase 4
  getRapportPdf(parcoursId: string)  { return this.api.getBlob(`/daara/rapport-pdf/${parcoursId}/`); }
}
