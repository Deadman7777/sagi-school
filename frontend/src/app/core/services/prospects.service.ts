import { Injectable, inject } from '@angular/core';
import { ApiService, ParamsRecord } from './api.service';

export interface Prospect {
  id: string;
  etablissement: string;
  type_organisation: string;
  ville: string;
  telephone: string;
  email: string;
  contact_nom: string;
  contact_fonction: string;
  contact_telephone: string;
  nb_eleves: number | null;
  statut: string;
  statut_libelle: string;
  source: string;
  relance_le: string | null;
  relance_en_retard: boolean;
  anciennete_jours: number;
  nb_interactions: number | null;
  cree_le: string;
  /** Présents uniquement sur la fiche détaillée (GET /prospects/{id}/). */
  interactions?: Interaction[];
  donnees_brutes?: Record<string, string>;
  [autre: string]: any;
}

export interface Interaction {
  id: string;
  date: string;
  canal: string;
  canal_libelle: string;
  resume: string;
  auteur: string;
}

export interface StatsProspects {
  total: number;
  par_statut: { statut: string; libelle: string; nombre: number }[];
  nouveaux: number;
  en_cours: number;
  gagnes: number;
  taux_conversion: number;
  a_relancer: number;
  en_retard: number;
  recus_30j: number;
  jamais_contactes: number;
}

@Injectable({ providedIn: 'root' })
export class ProspectsService {
  private api = inject(ApiService);

  liste(filtres?: ParamsRecord) { return this.api.get<Prospect[]>('/prospects/', filtres); }
  fiche(id: string)             { return this.api.get<Prospect>(`/prospects/${id}/`); }
  stats()                       { return this.api.get<StatsProspects>('/prospects/stats/'); }
  referentiels()                { return this.api.get<any>('/prospects/referentiels/'); }

  creer(data: any)              { return this.api.post<Prospect>('/prospects/', data); }
  modifier(id: string, data: any) { return this.api.patch<Prospect>(`/prospects/${id}/`, data); }
  supprimer(id: string)         { return this.api.delete<void>(`/prospects/${id}/`); }

  consigner(id: string, echange: { canal: string; resume: string; date?: string;
                                   relance_le?: string | null }) {
    return this.api.post<Prospect>(`/prospects/${id}/interaction/`, echange);
  }
}
