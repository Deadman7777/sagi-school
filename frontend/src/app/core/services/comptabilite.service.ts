import { Injectable, inject } from '@angular/core';
import { ApiService } from './api.service';

@Injectable({ providedIn: 'root' })
export class ComptabiliteService {
  private api = inject(ApiService);

  getJournal(params?: Record<string, string>) { return this.api.get<any[]>('/comptabilite/journal/', params); }
  getGrandLivre()     { return this.api.get<any[]>('/comptabilite/grand-livre/'); }
  getBalance()        { return this.api.get<any>('/comptabilite/balance/'); }
  getCompteResultat() { return this.api.get<any>('/comptabilite/compte-resultat/'); }
  getBilan()          { return this.api.get<any>('/comptabilite/bilan/'); }
  getTableauFlux()    { return this.api.get<any>('/comptabilite/tableau-flux/'); }
  getHistorique()     { return this.api.get<any>('/comptabilite/historique/'); }
  getNotesAnnexes()   { return this.api.get<any>('/comptabilite/notes-annexes/'); }
  getCharges()        { return this.api.get<any[]>('/comptabilite/charges/'); }
  creerCharge(data: any)      { return this.api.post<any>('/comptabilite/charges/', data); }
  supprimerCharge(id: string) { return this.api.delete(`/comptabilite/charges/${id}/`); }
  exportPDF(type: string)     { return this.api.get<Blob>(`/comptabilite/export-pdf/${type}/`); }

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
}
