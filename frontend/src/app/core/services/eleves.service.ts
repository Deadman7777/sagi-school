import { Injectable } from '@angular/core';
import { ApiService } from './api.service';
import { Eleve, Section, Service, PaginatedResponse, PriseEnChargeStats } from '../models/eleve.model';

export interface LigneImport {
  ligne: number;
  nom_complet: string;
  section: string;
  statut: 'OK' | 'DOUBLON' | 'ERREUR';
  erreurs: string[];
  avertissements: string[];
}

export interface RapportImport {
  resume: { total: number; ok: number; doublons: number; erreurs: number };
  lignes: LigneImport[];
  crees?: number;
}

@Injectable({ providedIn: 'root' })
export class ElevesService {
  constructor(private api: ApiService) {}

  getEleves(params?: Record<string, string>) {
    return this.api.get<PaginatedResponse<Eleve>>('/eleves/liste', { limit: '500', ...params });
  }

  // Liste des exercices (actif + clôturés) pour consulter une année passée.
  getExercices() {
    return this.api.get<any>('/paiements/exercices/');
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

  exporterListePDF(params?: Record<string, string>) {
    return this.api.getBlob('/eleves/export-pdf/', params);
  }

  telechargerTemplateImport() {
    return this.api.getBlob('/eleves/import-template/');
  }

  // confirmer=false : analyse seule (rapport) ; true : création des lignes OK
  importerExcel(fichier: File, confirmer: boolean) {
    const form = new FormData();
    form.append('fichier', fichier);
    if (confirmer) form.append('confirmer', '1');
    return this.api.post<RapportImport>('/eleves/import-excel/', form);
  }

  situationPDF(eleveId: string) {
    return this.api.getBlob(`/eleves/${eleveId}/situation-pdf/`);
  }

  fichePDF(eleveId: string) {
    return this.api.getBlob(`/eleves/${eleveId}/fiche-pdf/`);
  }

  getSections() {
    return this.api.get<PaginatedResponse<Section>>('/eleves/sections/');
  }

  getServices() {
    return this.api.get<PaginatedResponse<Service>>('/eleves/services/');
  }

  getClasses() {
    return this.api.get<any>('/academique/classes/');
  }
}
