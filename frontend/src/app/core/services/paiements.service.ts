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
    return this.api.get<any>('/paiements/paiements', params);
  }

  creerPaiement(data: Partial<Paiement>) {
    return this.api.post<Paiement>('/paiements/', data);
  }

  getStats() {
    return this.api.get<any>('/paiements/stats/');
  }

  getRecu(id: string) {
    return this.api.get<any>(`/paiements/${id}/recu/`);
  }

  getExerciceActif() {
    return this.api.get<any>('/paiements/exercices/');
  }
}
