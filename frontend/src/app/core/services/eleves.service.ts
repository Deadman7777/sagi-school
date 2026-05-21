import { Injectable } from '@angular/core';
import { ApiService } from './api.service';
import { Eleve, Section, PaginatedResponse } from '../models/eleve.model';

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

  telechargerCertificat(eleveId: string, nomComplet: string): Promise<void> {
    const token    = localStorage.getItem('access_token') || '';
    const tenantId = localStorage.getItem('tenant_id')    || '';
    const base = this.api.baseUrl.replace(/\/api$/, '');
    return fetch(`${base}/api/eleves/${eleveId}/certificat/`, {
      headers: { 'Authorization': `Bearer ${token}`, 'X-Tenant-ID': tenantId }
    })
    .then(r => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.blob();
    })
    .then(blob => {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `certificat_${nomComplet.replace(/ /g, '_')}.pdf`;
      a.click();
      URL.revokeObjectURL(a.href);
    });
  }

  getSections() {
    return this.api.get<PaginatedResponse<Section>>('/eleves/sections/');
  }
}
