import { Injectable } from '@angular/core';
import { ApiService } from './api.service';

@Injectable({ providedIn: 'root' })
export class AcademiqueService {
  constructor(private api: ApiService) {}

  getNiveaux()          { return this.api.get<any>('/academique/niveaux/'); }
  getClasses(params?: any) { return this.api.get<any>('/academique/classes/', params); }
  getMatieres(params?: any){ return this.api.get<any>('/academique/matieres/', params); }
  getTypesEval()        { return this.api.get<any>('/academique/types-eval/'); }
  getEvaluations(params?: any) { return this.api.get<any>('/academique/evaluations/', params); }
  getNotes(params?: any){ return this.api.get<any>('/academique/notes/', params); }

  creerNiveau(data: any)     { return this.api.post<any>('/academique/niveaux/', data); }
  creerClasse(data: any)     { return this.api.post<any>('/academique/classes/', data); }
  creerMatiere(data: any)    { return this.api.post<any>('/academique/matieres/', data); }
  creerTypeEval(data: any)   { return this.api.post<any>('/academique/types-eval/', data); }
  creerEvaluation(data: any) { return this.api.post<any>('/academique/evaluations/', data); }
  creerNote(data: any)       { return this.api.post<any>('/academique/notes/', data); }
  modifierNote(id: string, data: any) { return this.api.patch<any>(`/academique/notes/${id}/`, data); }
  bulkSaveNotes(notes: any[]) { return this.api.post<any>('/academique/notes/bulk_save/', { notes }); }

  modifierClasse(id: string, data: any)   { return this.api.patch<any>(`/academique/classes/${id}/`, data); }
  supprimerClasse(id: string)             { return this.api.delete<any>(`/academique/classes/${id}/`); }
  modifierMatiere(id: string, data: any)  { return this.api.patch<any>(`/academique/matieres/${id}/`, data); }
  supprimerMatiere(id: string)            { return this.api.delete<any>(`/academique/matieres/${id}/`); }
  modifierTypeEval(id: string, data: any) { return this.api.patch<any>(`/academique/types-eval/${id}/`, data); }
  supprimerTypeEval(id: string)           { return this.api.delete<any>(`/academique/types-eval/${id}/`); }

  calculerMoyennes(data: any){ return this.api.post<any>('/academique/calculer/', data); }
  getBulletin(eleveId: string, trimestre: string, annee: string) {
    return this.api.get<any>(`/academique/bulletin/${eleveId}/${trimestre}/`, { annee });
  }
  getBulletinPdf(eleveId: string, trimestre: string, annee: string) {
    return this.api.getBlob(`/academique/bulletin-pdf/${eleveId}/${trimestre}/?annee=${annee}`);
  }
  getElevesPourClasse(classeId: string) {
    return this.api.get<any[]>(`/academique/classes/${classeId}/eleves/`);
  }

  getAnalysePerformance() {
    return this.api.get<any>('/academique/analyse/');
  }

  getHistoriqueBulletins(params?: any) {
    return this.api.get<any>('/academique/historique-bulletins/', params);
  }
}
