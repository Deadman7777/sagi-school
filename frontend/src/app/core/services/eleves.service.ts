import { Injectable } from '@angular/core';
import { ApiService } from './api.service';
import { Eleve, Section, PaginatedResponse, PriseEnChargeStats } from '../models/eleve.model';

@Injectable({ providedIn: 'root' })
export class ElevesService {
  constructor(private api: ApiService) {}

  getEleves(params?: Record<string, string>) {
    return this.api.get<PaginatedResponse<Eleve>>('/eleves/liste', { limit: '500', ...params });
  }

  getEleve(id: string) {
    return this.api.get<Eleve>(`/eleves/${id}/`);
  }

  createEleve(data: Partial<Eleve>) {
    return this.api.post<Eleve>('/eleves/', data);
  }

  updateEleve(id: string, data: Partial<Eleve>) {
    return this.api.patch<Eleve>(`/eleves/${id}/`, data);
  }

  deleteEleve(id: string) {
    return this.api.delete(`/eleves/${id}/`);
  }

  searchEleves(q: string) {
    return this.api.get<any[]>('/eleves/search/', { q });
  }

  getSaisiePaiement(eleveId: string) {
    return this.api.get<any>(`/eleves/${eleveId}/saisie-paiement/`);
  }

  telechargerCertificat(eleveId: string) {
    return this.api.getBlob(`/eleves/${eleveId}/certificat/`);
  }

  getPriseEnChargeStats() {
    return this.api.get<PriseEnChargeStats>('/eleves/prises-en-charge/stats/');
  }

  getSections() {
    return this.api.get<PaginatedResponse<Section>>('/eleves/sections/');
  }
}
