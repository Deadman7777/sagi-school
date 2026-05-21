import { Injectable } from '@angular/core';
import { ApiService } from './api.service';

export interface Paiement {
  id?: string;
  eleve: string;
  eleve_nom?: string;
  exercice: string;
  no_piece?: string;
  date_paiement?: string;
  montant_inscription: number;
  montant_mensualite:  number;
  montant_uniforme:    number;
  montant_fournitures: number;
  montant_cantine:     number;
  montant_divers:      number;
  mode_paiement: string;
  observations?: string;
  total?: number;
}

@Injectable({ providedIn: 'root' })
export class PaiementsService {
  constructor(private api: ApiService) {}

  getPaiements(params?: Record<string, string>) {
    return this.api.get<any>('/paiements/paiements/', params);
  }

  creerPaiement(data: Partial<Paiement>) {
    return this.api.post<Paiement>('/paiements/paiements/', data);
  }

  getStats() {
    return this.api.get<any>('/paiements/stats/');
  }

  getRecu(id: string) {
    return this.api.get<any>(`/paiements/paiements/${id}/recu/`);
  }

  telechargerRecuPdf(id: string, noPiece: string): Promise<void> {
    const token    = localStorage.getItem('access_token') || '';
    const tenantId = localStorage.getItem('tenant_id')    || '';
    const base = this.api.baseUrl.replace(/\/api$/, '');
    return fetch(`${base}/api/paiements/paiements/${id}/recu-pdf/`, {
      headers: { 'Authorization': `Bearer ${token}`, 'X-Tenant-ID': tenantId }
    })
    .then(r => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.blob();
    })
    .then(blob => {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `recu_${noPiece}.pdf`;
      a.click();
      URL.revokeObjectURL(a.href);
    });
  }

  getExerciceActif() {
    return this.api.get<any>('/paiements/exercices/');
  }
}
