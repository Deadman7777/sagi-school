import { Injectable, inject } from '@angular/core';
import { ApiService } from './api.service';

export interface RhStats {
  total_employes: number;
  actifs: number;
  enseignants: number;
  administration: number;
  appui: number;
  masse_salariale: number;
  ipres_patronal: number;
  css_patronal: number;
}

export interface Employe {
  id: string;
  matricule: string;
  nom_complet: string;
  type_employe: string;
  poste: string;
  type_contrat: string;
  date_embauche: string;
  date_fin_contrat?: string;
  salaire_base: number;
  salaire_net: number;
  telephone: string;
  email: string;
  statut: string;
  niveau_enseignement: string;
  nb_enfants: number;
  situation_matrimoniale: string;
  est_cadre: boolean;
  mode_paiement: string;
  numero_compte: string;
}

export interface BulletinPaie {
  id: string;
  employe: string;
  employe_nom: string;
  employe_matricule: string;
  employe_poste: string;
  employe_niveau: string;
  periode: string;
  mois: number;
  annee: number;
  parametres_fiscaux: string;
  salaire_base: number;
  nb_heures_sup: number;
  heures_sup_montant: number;
  indemnite_sujetion: number;
  indemnite_logement: number;
  allocation_salaire_unique: number;
  prime_transport: number;
  primes_diverses: number;
  avantages_nature: number;
  salaire_brut: number;
  ipres_general_salarie: number;
  ipres_cadre_salarie: number;
  ir_retenu: number;
  avance_sur_salaire: number;
  opposition_saisie: number;
  autres_retenues: number;
  total_retenues_salariales: number;
  ipres_general_patronal: number;
  ipres_cadre_patronal: number;
  css_prestations_familiales: number;
  atmp: number;
  cfce: number;
  total_charges_patronales: number;
  net_a_payer: number;
  cout_total_employeur: number;
  statut: 'BROUILLON' | 'VALIDE' | 'PAYE';
  mode_paiement_effectif: string;
  date_validation?: string;
  date_paiement?: string;
}

export interface AvanceSalaire {
  id: string;
  employe: string;
  employe_nom: string;
  montant: number;
  date_avance: string;
  mode_paiement: string;
  no_piece: string;
  statut: 'EN_ATTENTE' | 'IMPUTE' | 'ANNULE';
  observations: string;
}

export interface ParametresFiscaux {
  id: string;
  annee: number;
  taux_ipres_general_salarie: number;
  taux_ipres_general_patronal: number;
  plafond_ipres_general: number;
  taux_ipres_cadre_salarie: number;
  taux_ipres_cadre_patronal: number;
  plafond_ipres_cadre: number;
  taux_css_prestations_familiales: number;
  plafond_css: number;
  taux_atmp: number;
  taux_cfce: number;
  prime_transport: number;
  allocation_salaire_unique_base: number;
  allocation_par_enfant: number;
  plafond_allocation: number;
  tranches_ir: { min: number; max: number | null; taux: number }[];
}

@Injectable({ providedIn: 'root' })
export class RhService {
  private api = inject(ApiService);

  // — Statistiques —
  getStats() { return this.api.get<RhStats>('/rh/stats/'); }

  // — Employés —
  getEmployes(params?: Record<string, string>) { return this.api.get<any>('/rh/employes/', params); }
  creerEmploye(data: Partial<Employe>)         { return this.api.post<Employe>('/rh/employes/', data); }
  modifierEmploye(id: string, data: Partial<Employe>) { return this.api.patch<Employe>(`/rh/employes/${id}/`, data); }

  // — Bulletins SYSCOHADA —
  getBulletins(params?: Record<string, string>) { return this.api.get<any>('/rh/bulletins/', params); }
  creerBulletin(data: unknown)                  { return this.api.post<BulletinPaie>('/rh/bulletins/', data); }
  calculerBulletin(data: unknown)               { return this.api.post<any>('/rh/bulletins/calculer/', data); }
  validerBulletin(id: string)                   { return this.api.post<BulletinPaie>(`/rh/bulletins/${id}/valider/`, {}); }
  payerBulletin(id: string, mode?: string)      { return this.api.post<BulletinPaie>(`/rh/bulletins/${id}/payer/`, mode ? { mode_paiement_effectif: mode } : {}); }
  telechargerPdf(id: string)                    { return this.api.getBlob(`/rh/bulletins/${id}/pdf/`); }

  // — Avances —
  getAvances(params?: Record<string, string>)              { return this.api.get<any>('/rh/avances/', params); }
  creerAvance(employeId: string, data: unknown)            { return this.api.post<AvanceSalaire>(`/rh/employes/${employeId}/avance/`, data); }
  annulerAvance(id: string)                                { return this.api.patch<AvanceSalaire>(`/rh/avances/${id}/`, { statut: 'ANNULE' }); }

  // — Paramètres fiscaux —
  getParametresFiscaux()                                   { return this.api.get<ParametresFiscaux[]>('/rh/parametres-fiscaux/'); }
  updateParametresFiscaux(annee: number, data: Partial<ParametresFiscaux>) {
    return this.api.put<ParametresFiscaux>(`/rh/parametres-fiscaux/${annee}/`, data);
  }

  // — Historique Paie (legacy) —
  getPaies(params?: Record<string, string>) { return this.api.get<any>('/rh/paies/', params); }
  creerPaie(data: unknown)                  { return this.api.post<any>('/rh/paies/', data); }
}
