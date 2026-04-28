import { Injectable } from '@angular/core';
import { ApiService } from './api.service';

@Injectable({ providedIn: 'root' })
export class ComptabiliteService {
  constructor(private api: ApiService) {}
  getJournal()        { return this.api.get<any[]>('/comptabilite/journal/'); }
  getGrandLivre()     { return this.api.get<any[]>('/comptabilite/grand-livre/'); }
  getBalance()        { return this.api.get<any>('/comptabilite/balance/'); }
  getCompteResultat() { return this.api.get<any>('/comptabilite/compte-resultat/'); }
  getBilan()          { return this.api.get<any>('/comptabilite/bilan/'); }
  getTableauFlux()    { return this.api.get<any>('/comptabilite/tableau-flux/'); }
  getHistorique()     { return this.api.get<any>('/comptabilite/historique/'); }
  getCharges()        { return this.api.get<any[]>('/comptabilite/charges/'); }
  creerCharge(data: any) { return this.api.post<any>('/comptabilite/charges/', data); }
  supprimerCharge(id: string) { return this.api.delete(`/comptabilite/charges/${id}/`); }
  exportPDF(type: string) {
    return this.api.get<Blob>(`/comptabilite/export-pdf/${type}/`);
  }
}