import { Injectable, inject } from '@angular/core';
import { ApiService } from './api.service';

@Injectable({ providedIn: 'root' })
export class ComptabiliteService {
  private api = inject(ApiService);

  // `exercice` (id) optionnel : permet de consulter/exporter une année clôturée.
  private exParams(exercice?: string, extra?: Record<string, string>): Record<string, string> | undefined {
    const p: Record<string, string> = { ...(extra || {}) };
    if (exercice) p['exercice'] = exercice;
    return Object.keys(p).length ? p : undefined;
  }

  // Liste de tous les exercices du tenant (actif + clôturés) pour le sélecteur.
  getExercices()      { return this.api.get<any>('/paiements/exercices/'); }

  getJournal(exercice?: string, source?: string) { return this.api.get<any[]>('/comptabilite/journal/', this.exParams(exercice, source ? { source } : undefined)); }
  getGrandLivre(exercice?: string)     { return this.api.get<any[]>('/comptabilite/grand-livre/', this.exParams(exercice)); }
  getBalance(exercice?: string)        { return this.api.get<any>('/comptabilite/balance/', this.exParams(exercice)); }
  getCompteResultat(exercice?: string) { return this.api.get<any>('/comptabilite/compte-resultat/', this.exParams(exercice)); }
  getBilan(exercice?: string)          { return this.api.get<any>('/comptabilite/bilan/', this.exParams(exercice)); }
  getTableauFlux(exercice?: string)    { return this.api.get<any>('/comptabilite/tableau-flux/', this.exParams(exercice)); }
  getHistorique()     { return this.api.get<any>('/comptabilite/historique/'); }
  getNotesAnnexes(exercice?: string)   { return this.api.get<any>('/comptabilite/notes-annexes/', this.exParams(exercice)); }
  getCharges()        { return this.api.get<any[]>('/comptabilite/charges/'); }
  creerCharge(data: any)      { return this.api.post<any>('/comptabilite/charges/', data); }
  supprimerCharge(id: string) { return this.api.delete(`/comptabilite/charges/${id}/`); }
  modifierCharge(id: string, data: any) { return this.api.put<any>(`/comptabilite/charges/${id}/`, data); }
  exportPDF(type: string, exercice?: string) { return this.api.getBlob(`/comptabilite/export-pdf/${type}/`, this.exParams(exercice)); }

  // Plan comptable paramétrable
  getPlanComptable(params?: Record<string, string>) { return this.api.get<any[]>('/comptabilite/plan-comptable/', params); }
  creerCompte(data: unknown)                { return this.api.post<any>('/comptabilite/plan-comptable/', data); }
  modifierCompte(no: string, data: unknown) { return this.api.put<any>(`/comptabilite/plan-comptable/${no}/`, data); }
  supprimerCompte(no: string)               { return this.api.delete(`/comptabilite/plan-comptable/${no}/`); }

  // Budget prévisionnel
  getBudget()                           { return this.api.get<any>('/comptabilite/budget/'); }
  sauvegarderBudgetLigne(data: unknown)            { return this.api.post<any>('/comptabilite/budget/', data); }
  supprimerBudgetLigne(id: string)                 { return this.api.delete(`/comptabilite/budget/${id}/`); }
  comptabiliserBudgetLigne(id: string, data: unknown) { return this.api.post<any>(`/comptabilite/budget/${id}/comptabiliser/`, data); }

  // Investissements / Immobilisations
  getImmobilisations()                       { return this.api.get<any>('/comptabilite/immobilisations/'); }
  creerImmobilisation(data: unknown)         { return this.api.post<any>('/comptabilite/immobilisations/', data); }
  modifierImmobilisation(id: string, data: unknown) { return this.api.put<any>(`/comptabilite/immobilisations/${id}/`, data); }
  supprimerImmobilisation(id: string)        { return this.api.delete(`/comptabilite/immobilisations/${id}/`); }
  amortirImmobilisation(id: string, data: unknown) { return this.api.post<any>(`/comptabilite/immobilisations/${id}/amortir/`, data); }
  reglerImmobilisation(id: string, data: unknown)  { return this.api.post<any>(`/comptabilite/immobilisations/${id}/regler/`, data); }
}
