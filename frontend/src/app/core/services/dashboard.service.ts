import { Injectable } from '@angular/core';
import { ApiService } from './api.service';

export interface DashboardKPI {
  exercice: { annee_scolaire: string; date_debut: string; date_fin: string; } | null;
  kpis: { total_recettes: number; total_charges: number; resultat_net: number; tresorerie: number; };
  eleves: { total: number; urgent: number; attention: number; ok: number; };
  modes_paiement: { mode_paiement: string; nb: number; total: number; }[];
  recettes_mensuelles: { mois: string; total: number; }[];
}

export interface DashboardSuperAdmin {
  ecoles: { total: number; actives: number; expirees: number; essai: number; nouvelles_ce_mois: number; };
  finances: { revenus_annuels: number; revenus_mensuels: number; };
  alertes_expiration: { ecole: string; jours_restants: number; date_fin: string; type: string; }[];
}

@Injectable({ providedIn: 'root' })
export class DashboardService {
  constructor(private api: ApiService) {}
  getKPIs()        { return this.api.get<DashboardKPI>('/dashboard/kpis/'); }
  getAlertes()     { return this.api.get<any[]>('/dashboard/alertes/'); }
  getSuperAdmin()  { return this.api.get<DashboardSuperAdmin>('/dashboard/superadmin/'); }
}
