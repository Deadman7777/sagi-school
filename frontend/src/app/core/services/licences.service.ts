import { Injectable } from '@angular/core';
import { ApiService } from './api.service';

export interface NouvelleEcole {
  nom: string;
  ville: string;
  telephone: string;
  email: string;
  rccm: string;
  ninea: string;
  type_licence: string;
  mois_licence: number;
  annee_scolaire: string;
  date_debut: string;
  date_fin: string;
  code_etablissement: string;
}

@Injectable({ providedIn: 'root' })
export class LicencesService {
  constructor(private api: ApiService) {}

  getLicences()      { return this.api.get<any>('/licences/'); }
  getStatsGlobales() { return this.api.get<any>('/licences/stats_globales/'); }

  creerEcole(data: NouvelleEcole) {
    return this.api.post<any>('/licences/creer_ecole/', data);
  }

  renouveler(id: string, mois: number) {
    return this.api.post<any>(`/licences/${id}/renouveler/`, { mois });
  }

  verifierCle(cle: string) {
    return this.api.post<any>('/licences/verifier/', { cle_licence: cle });
  }

  suspendre(id: number)              { return this.api.post<any>(`/licences/${id}/suspendre/`, {}); }
  activer(id: number)                { return this.api.post<any>(`/licences/${id}/activer/`, {}); }
  changerType(id: number, type: string) { return this.api.post<any>(`/licences/${id}/changer_type/`, { type }); }
  supprimer(id: number)              { return this.api.delete<any>(`/licences/${id}/`); }

  getDetailsEcole(tenantId: string)  { return this.api.get<any>(`/tenants/${tenantId}/details/`); }
  updateDetailsEcole(tenantId: string, data: { tenant: any; exercice: any }) {
    return this.api.patch<any>(`/tenants/${tenantId}/details/`, data);
  }
}
