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
  // Part réglée sur le reliquat d'un exercice antérieur : encaissée, mais
  // hors produits de l'année (elle solde une créance reportée).
  montant_reliquat?:   number;
  mois_regles?:        number[];
  services_regles?:    { nom: string; montant: number; nature?: string; cle?: string; service?: string }[];
  mode_paiement: string;
  // Ventilation multi-mode : un même règlement réparti sur plusieurs moyens.
  modes_reglement?: { mode: string; montant: number }[];
  /** Chèque(s) reçu(s), inscrits au registre des chèques. */
  cheques?: { numero: string; banque: string; tireur: string; date_emission: string; montant?: number }[];
  reference_groupe?: string;
  observations?: string;
  // Qui règle. null/absent = la famille. Renseigné = l'organisme verse la part
  // qu'il prend en charge : le versement solde SA créance, pas celle de la
  // famille, et l'alerte de l'élève n'en tient pas compte.
  organisme?: string | null;
  // Caisse qui reçoit les espèces (garderie, cantine…). null = caisse principale.
  caisse?: string | null;
  // Part du règlement qui porte sur des services extra : elle va au compte de
  // produits divers (758) et non au 706 du service éducatif.
  part_accessoire?: number;
  // Qui a reçu l'argent (receveur du transport…). null = la personne qui saisit.
  receveur?: string | null;
  receveur_nom?: string;
  caisse_nom?: string;
  organisme_nom?: string;
  total?: number;
  statut?: 'ACTIF' | 'ANNULE';
}

export type StatutCheque = 'EN_PORTEFEUILLE' | 'REMIS' | 'ENCAISSE' | 'IMPAYE' | 'ANNULE';

export interface ChequeRecu {
  id: string;
  numero: string;
  banque: string;
  tireur: string;
  date_emission: string | null;
  date_reception: string;
  montant: number;
  montant_affecte: number;
  statut: StatutCheque;
  compte_reception: string;
  recus: { paiement: string; no_piece: string; eleve: string; montant: number; statut: string }[];
  recu_par_nom: string;
  date_remise: string | null;
  bordereau: string;
  no_piece_remise: string;
  remis_par_nom: string;
  date_encaissement: string | null;
  encaisse_par_nom: string;
  date_impaye: string | null;
  motif_impaye: string;
  impaye_par_nom: string;
  observations: string;
  exercice_nom: string;
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

  /** « Mon cahier de notes mensuel » ; sans paramètre, le mois en cours. */
  getCahierMensuel(annee?: number, mois?: number) {
    return this.api.get<any>('/paiements/cahier-mensuel/', annee && mois ? { annee, mois } : {});
  }

  /** Les seuls totaux du mois en cours (bandeau de rappel), sans les lignes. */
  getResumeCahierMensuel() {
    return this.api.get<any>('/paiements/cahier-mensuel/', { resume: 1 });
  }

  getRecu(id: string) {
    return this.api.get<any>(`/paiements/paiements/${id}/recu/`);
  }

  /** Téléchargement PDF via Angular HttpClient (intercepteur auth inclus). */
  telechargerRecuPdf(id: string, format: string = 'A5') {
    // NB : param 'taille' et non 'format' ('format' est réservé par DRF → Http404)
    return this.api.getBlob(`/paiements/paiements/${id}/recu-pdf/`, { taille: format });
  }

  annulerPaiement(id: string) {
    return this.api.post<any>(`/paiements/paiements/${id}/annuler/`, {});
  }

  modifierPaiement(id: string, data: Partial<Paiement>) {
    return this.api.post<any>(`/paiements/paiements/${id}/modifier/`, data);
  }

  // — Registre des chèques —
  getCheques(params?: Record<string, string>) {
    return this.api.get<{ results: ChequeRecu[]; totaux: Record<string, { nb: number; montant: number }> }>(
      '/paiements/cheques/', params);
  }
  completerCheque(id: string, data: Partial<ChequeRecu>) {
    return this.api.patch<ChequeRecu>(`/paiements/cheques/${id}/`, data);
  }
  remettreCheques(ids: string[], date: string, bordereau: string) {
    return this.api.post<{ no_piece: string; nb: number; total: number }>(
      '/paiements/cheques/remettre/', { ids, date, bordereau });
  }
  encaisserCheques(ids: string[], date: string) {
    return this.api.post<{ nb: number }>('/paiements/cheques/encaisser/', { ids, date });
  }
  declarerChequeImpaye(id: string, date: string, motif: string) {
    return this.api.post<{ no_piece_retour: string;
                           recus_annules: { no_piece: string; eleve: string; montant: number }[];
                           autres_modes: { no_piece: string; eleve: string; montant: number }[] }>(
      `/paiements/cheques/${id}/impaye/`, { date, motif });
  }

  getExerciceActif() {
    return this.api.get<any>('/paiements/exercices/');
  }
}
