import { Injectable, inject } from '@angular/core';
import { ApiService } from './api.service';

/** Socle Gouvernance financière (Lot 0) : projets (dimension analytique) + GED. */
@Injectable({ providedIn: 'root' })
export class GouvernanceService {
  private api = inject(ApiService);

  // Tableau de bord consolidé (Lot 6)
  getDashboard()                { return this.api.get<any>('/gouvernance/dashboard/'); }

  // Projets
  getProjets(actifs = false) {
    return this.api.get<any[]>('/gouvernance/projets/', actifs ? { actifs: '1' } : undefined);
  }
  getProjet(id: string)          { return this.api.get<any>(`/gouvernance/projets/${id}/`); }
  creerProjet(data: any)         { return this.api.post<any>('/gouvernance/projets/', data); }
  modifierProjet(id: string, data: any) { return this.api.patch<any>(`/gouvernance/projets/${id}/`, data); }
  supprimerProjet(id: string)    { return this.api.delete<any>(`/gouvernance/projets/${id}/`); }

  // GED — pièces justificatives (rattachement polymorphe objet_type/objet_id)
  getPieces(objetType: string, objetId: string) {
    return this.api.get<any[]>('/gouvernance/pieces/', { objet_type: objetType, objet_id: objetId });
  }
  getPiece(id: string)           { return this.api.get<any>(`/gouvernance/pieces/${id}/`); }
  ajouterPiece(data: any)        { return this.api.post<any>('/gouvernance/pieces/', data); }
  supprimerPiece(id: string)     { return this.api.delete<any>(`/gouvernance/pieces/${id}/`); }

  // Flux internes de trésorerie (Lot 1)
  getCanaux()                    { return this.api.get<any>('/gouvernance/canaux/'); }
  getTransferts()                { return this.api.get<any[]>('/gouvernance/transferts/'); }
  creerTransfert(data: any)      { return this.api.post<any>('/gouvernance/transferts/', data); }
  annulerTransfert(id: string)   { return this.api.delete<any>(`/gouvernance/transferts/${id}/`); }

  // Ressources unifiées + affectations (Lot 2)
  getRessources()               { return this.api.get<any[]>('/gouvernance/ressources/'); }
  creerRessource(data: any)     { return this.api.post<any>('/gouvernance/ressources/', data); }
  modifierRessource(id: string, data: any) { return this.api.patch<any>(`/gouvernance/ressources/${id}/`, data); }
  supprimerRessource(id: string) { return this.api.delete<any>(`/gouvernance/ressources/${id}/`); }
  getTracabilite(id: string)    { return this.api.get<any>(`/gouvernance/ressources/${id}/tracabilite/`); }
  getTracabiliteGlobale()       { return this.api.get<any>('/gouvernance/tracabilite/'); }
  getProjetTracabilite(id: string) { return this.api.get<any>(`/gouvernance/projets/${id}/tracabilite/`); }
  getAffectations(ressourceId: string) { return this.api.get<any[]>('/gouvernance/affectations/', { ressource_id: ressourceId }); }
  creerAffectation(data: any)   { return this.api.post<any>('/gouvernance/affectations/', data); }
  supprimerAffectation(id: string) { return this.api.delete<any>(`/gouvernance/affectations/${id}/`); }

  // Provisions SYSCOHADA (Lot 4)
  getProvisions()               { return this.api.get<any[]>('/gouvernance/provisions/'); }
  creerProvision(data: any)     { return this.api.post<any>('/gouvernance/provisions/', data); }
  reprendreProvision(id: string, montant: number) { return this.api.post<any>(`/gouvernance/provisions/${id}/reprise/`, { montant }); }
  annulerProvision(id: string)  { return this.api.delete<any>(`/gouvernance/provisions/${id}/`); }

  // Rapprochement bancaire (Lot 5)
  getComptesBancaires()         { return this.api.get<any[]>('/gouvernance/comptes-bancaires/'); }
  creerCompteBancaire(data: any) { return this.api.post<any>('/gouvernance/comptes-bancaires/', data); }
  getRapprochements()           { return this.api.get<any[]>('/gouvernance/rapprochements/'); }
  getRapprochement(id: string)  { return this.api.get<any>(`/gouvernance/rapprochements/${id}/`); }
  creerRapprochement(data: any) { return this.api.post<any>('/gouvernance/rapprochements/', data); }
  supprimerRapprochement(id: string) { return this.api.delete<any>(`/gouvernance/rapprochements/${id}/`); }
  rapprochementAuto(id: string) { return this.api.post<any>(`/gouvernance/rapprochements/${id}/auto/`, {}); }
  validerRapprochement(id: string) { return this.api.post<any>(`/gouvernance/rapprochements/${id}/valider/`, {}); }
  ajouterLigneReleve(id: string, data: any) { return this.api.post<any>(`/gouvernance/rapprochements/${id}/lignes/`, data); }
  supprimerLigneReleve(id: string, lid: string) { return this.api.delete<any>(`/gouvernance/rapprochements/${id}/lignes/${lid}/`); }
  regulariserLigne(id: string, lid: string, compte_contrepartie: string) { return this.api.post<any>(`/gouvernance/rapprochements/${id}/lignes/${lid}/regulariser/`, { compte_contrepartie }); }
}
