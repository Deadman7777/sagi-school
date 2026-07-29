import { Injectable } from '@angular/core';
import { ApiService } from './api.service';
import { Eleve, Section, Service, PaginatedResponse, PriseEnChargeStats,
         LigneImpayeAnterieur, ResumeImpayesAnterieurs,
         ParcoursEleve, AncienEleve, Echeancier, Organisme, Bourse,
         SuiviOrganisme } from '../models/eleve.model';

export interface LigneImport {
  ligne: number;
  nom_complet: string;
  section: string;
  statut: 'OK' | 'DOUBLON' | 'ERREUR';
  erreurs: string[];
  avertissements: string[];
  montant_reprise: number;
  impaye_anterieur: number;
}

export interface RapportImport {
  resume: {
    total: number; ok: number; doublons: number; erreurs: number;
    reprises: number; montant_reprise: number;
    impayes_anterieurs: number; montant_impaye_anterieur: number;
  };
  lignes: LigneImport[];
  // Renvoyés uniquement par l'import confirmé (confirmer=1), pas par l'analyse.
  crees?: number;
  reprises?: number;
  montant_reprise?: number;
  impayes_anterieurs?: number;
  montant_impaye_anterieur?: number;
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

  // Correction du « déjà payé » de reprise (données migrées)
  getReprise(eleveId: string) {
    return this.api.get<any>(`/eleves/${eleveId}/corriger-reprise/`);
  }
  corrigerReprise(eleveId: string, data: any) {
    return this.api.post<any>(`/eleves/${eleveId}/corriger-reprise/`, data);
  }

  fichePDF(eleveId: string) {
    return this.api.getBlob(`/eleves/${eleveId}/fiche-pdf/`);
  }

  // Dû mois par mois : un total ne dit rien à une famille qui règle au mois.
  getEcheancier(eleveId: string) {
    return this.api.get<Echeancier>(`/eleves/${eleveId}/echeancier/`);
  }

  /** Fixe le montant DÛ de certains mois — réduction sur un mois entamé,
   *  ou mois déjà réglé dans les frais d'inscription. Objet vide = tarif. */
  definirMontantsMois(eleveId: string, montants: Record<string, number>) {
    return this.api.post<Echeancier>(`/eleves/${eleveId}/montants-mois/`, { montants });
  }

  /** Corrige la répartition du payé par mois. Le total est verrouillé côté
   *  serveur sur ce qui a réellement été encaissé — on déplace, on ne crée pas. */
  corrigerImputation(eleveId: string, imputation: Record<string, number>) {
    return this.api.post<Echeancier>(`/eleves/${eleveId}/imputation/`, { imputation });
  }

  // Scolarité complète d'un enfant, toutes années confondues.
  getParcours(eleveId: string) {
    return this.api.get<ParcoursEleve>(`/eleves/${eleveId}/parcours/`);
  }
  parcoursPDF(eleveId: string) {
    return this.api.getBlob(`/eleves/${eleveId}/parcours-pdf/`);
  }

  /** Enregistre un ancien élève dont aucune fiche n'existe (diplômé d'avant
   *  la migration). Le matricule est calculé côté serveur sur sa promo réelle. */
  creerAncien(data: {
    nom_complet: string; genre?: string | null; date_naissance?: string;
    date_entree: string; date_sortie?: string; statut: string;
    nom_tuteur?: string; telephone_tuteur?: string;
  }) {
    return this.api.post<Eleve>('/eleves/ancien/', data);
  }

  /** Effectif par classe, sur le périmètre des élèves ACTIFS uniquement. */
  getEffectifsClasses() {
    return this.api.get<{
      exercice: string; total: number;
      classes: { classe_id: string | null; classe: string; section: string; nb: number }[];
    }>('/eleves/effectifs-classes/');
  }

  /** Liste nominative d'une classe, SANS donnée financière. */
  listeClassePDF(classeId?: string) {
    const q = classeId ? `?classe=${encodeURIComponent(classeId)}` : '';
    return this.api.getBlob(`/eleves/liste-classe-pdf/${q}`);
  }

  // ── Organismes payeurs et bourses ────────────────────────────────────
  getOrganismes()                    { return this.api.get<Organisme[]>('/eleves/organismes/'); }
  creerOrganisme(o: Partial<Organisme>)  { return this.api.post<Organisme>('/eleves/organismes/', o); }
  majOrganisme(id: string, o: Partial<Organisme>) {
    return this.api.patch<Organisme>(`/eleves/organismes/${id}/`, o);
  }
  supprimerOrganisme(id: string)     { return this.api.delete<void>(`/eleves/organismes/${id}/`); }

  /** Position financière de chaque organisme : couvert, reçu, dû. */
  getSuiviOrganismes() {
    return this.api.get<{ exercice: string; lignes: SuiviOrganisme[];
                          totaux: { nb_organismes: number; nb_boursiers: number;
                                    couvert: number; recu: number; reste: number } }>(
      '/eleves/organismes/suivi/');
  }

  getBourses(params?: { eleve?: string; organisme?: string }) {
    return this.api.get<Bourse[]>('/eleves/bourses/', params);
  }
  attribuerBourse(b: Partial<Bourse>) { return this.api.post<Bourse>('/eleves/bourses/', b); }
  majBourse(id: string, b: Partial<Bourse>) {
    return this.api.patch<Bourse>(`/eleves/bourses/${id}/`, b);
  }
  retirerBourse(id: string)          { return this.api.delete<void>(`/eleves/bourses/${id}/`); }

  // Base historique des sortis — indépendante de l'exercice actif.
  getAnciens(params?: { q?: string; statut?: string }) {
    return this.api.get<{ lignes: AncienEleve[]; nb: number; nb_diplomes: number;
                          total_du: number }>('/eleves/anciens/', params);
  }

  // Impayés antérieurs (migration) — saisie en lot d'un montant par élève.
  // Le backend passe l'à-nouveaux 411/890 et refuse ligne par ligne.
  getImpayesAnterieurs() {
    return this.api.get<{ exercice: string; resume: ResumeImpayesAnterieurs;
                          lignes: LigneImpayeAnterieur[] }>('/eleves/impayes-anterieurs/');
  }
  enregistrerImpayesAnterieurs(lignes: { eleve_id: string; montant: number; note?: string }[]) {
    return this.api.post<{ nb_appliques: number; nb_refuses: number;
                           refuses: { nom_complet?: string; motif: string }[];
                           resume: ResumeImpayesAnterieurs }>(
      '/eleves/impayes-anterieurs/', { lignes });
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
