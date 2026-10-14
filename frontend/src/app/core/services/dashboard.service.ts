import { Injectable, inject } from '@angular/core';
import { ApiService } from './api.service';
import { MemoireEcransService } from './memoire-ecrans.service';

export interface PilotageMois {
  libelle_mois: string; annee: number; mois: number;
  periode: 'PASSE' | 'EN_COURS' | 'A_VENIR'; jours_restants: number;
  attendu: number; encaisse: number; reste_a_encaisser: number;
  charges_prevues: number; charges_payees: number; charges_a_payer: number;
  solde_previsionnel: number; solde_constate: number; taux: number;
  nb_payes: number; nb_partiels: number; nb_impayes: number;
  nb_charges_non_payees: number; nb_depassements: number; entrees_caisse: number;
}

export interface DashboardKPI {
  mis_a_jour?: string;
  pilotage?: PilotageMois;
  exercice: { annee_scolaire: string; date_debut: string; date_fin: string; } | null;
  kpis: { 
  total_recettes: number; 
  total_charges: number; 
  resultat_net: number; 
  tresorerie: number;
  total_attendu: number;
  total_impayes: number;
  taux_recouvrement: number;
  impayes_sortants: number;
  nb_sortants_debiteurs: number;
};
  eleves: {
    total: number; critique: number; urgent: number; attention: number; ok: number; a_jour: number;
    inscrits: number; abandonnes: number; transferes: number; diplomes: number;
    garcons: number; filles: number;
  };
  prises_en_charge?: { total: number; categories: { categorie: string; nb: number; }[]; };
  modes_paiement: { mode_paiement: string; nb: number; total: number; }[];
  recettes_mensuelles: { mois: string; total: number; }[];
}

export interface CanalTresorerie {
  canal: string; libelle: string; compte: string; nb: number;
  solde_initial: number; encaissements: number; decaissements: number; solde: number;
  encaissements_eleves: number; autres_entrees: number;
}

export interface TresorerieCanaux {
  exercice: string;
  canaux: CanalTresorerie[];
  totaux: { solde_initial: number; encaissements: number; autres_entrees: number; decaissements: number; solde: number; };
}

export interface DashboardSuperAdmin {
  ecoles: { total: number; actives: number; expirees: number; essai: number; nouvelles_ce_mois: number; };
  finances: { revenus_annuels: number; revenus_mensuels: number; };
  alertes_expiration: { ecole: string; jours_restants: number; date_fin: string; type: string; }[];
}

@Injectable({ providedIn: 'root' })
export class DashboardService {
  private memoire = inject(MemoireEcransService);
  constructor(private api: ApiService) {}

  // Tableau de bord : chaque lecture rend d'abord les chiffres du passage
  // précédent, puis les frais (deux émissions — voir MemoireEcransService).
  private lire<T>(url: string) { return this.memoire.avecMemoire(url, undefined, this.api.get<T>(url)); }

  getKPIs()              { return this.lire<DashboardKPI>('/dashboard/kpis/'); }
  getAlertes()           { return this.lire<any[]>('/dashboard/alertes/'); }
  getSuperAdmin()        { return this.lire<DashboardSuperAdmin>('/dashboard/superadmin/'); }
  getTresorerieCanaux()  { return this.lire<TresorerieCanaux>('/dashboard/tresorerie-canaux/'); }
  getAuditLog()          { return this.lire<any[]>('/dashboard/audit-log/'); }
  getConseils()          { return this.lire<any>('/fiscal/conseils/'); }
}
