import { Injectable } from '@angular/core';
import { ApiService } from './api.service';

export interface NouvelleEcole {
  nom: string;
  ville: string;
  telephone: string;
  email: string;
  rccm: string;
  ninea: string;
  type_licence: string;
  mois_licence: number;
  cycle: string;            // 'MENSUEL' | 'ANNUEL'
  annee_scolaire: string;
  date_debut: string;
  date_fin: string;
  code_etablissement: string;
}

export interface LigneRelance {
  licence: string; ecole: string; type: string; date_fin: string; jours: number;
  palier: number | null; a_envoyer: boolean; destinataires: string[]; telephone: string;
  whatsapp: string;
  relances: { palier: number; le: string; succes: boolean; simulee: boolean; erreur: string;
              destinataires: string; par: string }[];
}

export interface RelancesLicences { lignes: LigneRelance[]; relances_auto: boolean; smtp: boolean; }

export interface FormuleRenouvellement {
  type: string; mois: number; moyen_paiement?: string; reference_paiement?: string;
}

export interface OffreRenouvellement {
  type: string; libelle: string;
  formules: { mois: number; libelle: string; montant: number; remise: number }[];
}

/** Voir apps/licences/alertes.py : un seul calcul, côté serveur. */
export interface AlerteLicence {
  licence: string | null; type: string; statut: string;
  date_fin: string; date_fin_longue: string; date_coupure: string;
  jours: number; grace_jours: number;
  phase: 'NORMAL' | 'ECHEANCE' | 'EXPIREE' | 'COUPEE' | 'AUCUNE';
  niveau: 'ok' | 'attention' | 'urgent' | 'critique' | 'expiree';
  palier: number | 'EXP' | null; paliers: number[];
  alerte: boolean; prioritaire: boolean; cle_rappel: string;
  badge: number | '!' | null;
  titre: string; texte: string;
  acces_expire: boolean; modules: string[];
  offres: OffreRenouvellement[];
  paiement: { lien: string; coordonnees: string; moyens: string[]; telephone: string; email: string };
  demande_en_attente: { id: string; le: string; mois: number | null; montant: number | null;
                        type: string; reference_paiement: string } | null;
}

@Injectable({ providedIn: 'root' })
export class LicencesService {
  constructor(private api: ApiService) {}

  getLicences()      { return this.api.lire<any>('/licences/'); }
  /** La grille tarifaire officielle — voir apps/licences/catalogue.py. */
  getCatalogue()     { return this.api.lire<any>('/licences/catalogue/'); }
  getStatsGlobales() { return this.api.lire<any>('/licences/stats_globales/'); }

  creerEcole(data: NouvelleEcole) {
    return this.api.post<any>('/licences/creer_ecole/', data);
  }

  renouveler(id: string, mois: number) {
    return this.api.post<any>(`/licences/${id}/renouveler/`, { mois });
  }

  /** Toutes les demandes reçues (super admin), y compris celles dont le courriel a échoué. */
  getDemandesRenouvellement() { return this.api.lire<any[]>('/licences/demandes-renouvellement/'); }
  traiterDemande(id: string)  { return this.api.post<any>(`/licences/demandes-renouvellement/${id}/traiter/`, {}); }

  /** Échéances dans 7 jours ou moins : relances faites, à faire, lien WhatsApp. */
  getRelances()              { return this.api.get<RelancesLicences>('/licences/relances/'); }
  relancer(id: string)       { return this.api.post<{ succes: boolean; destinataires: string }>(`/licences/${id}/relancer/`, {}); }
  /** Interrupteur des relances automatiques (réglage de facturation HADY GESMAN). */
  activerRelances(actif: boolean) { return this.api.patch<any>('/facturation/parametres/', { relances_auto: actif }); }

  demanderRenouvellement(id: string, message: string, formule: FormuleRenouvellement | null = null) {
    return this.api.post<any>(`/licences/${id}/demander_renouvellement/`, { message, ...(formule || {}) });
  }

  /** L'alerte de fin de licence de l'école (apps/licences/alertes.py). `actualiser` relit le cloud. */
  getAlerte(actualiser = false) {
    return this.api.get<AlerteLicence>('/licences/alerte/', { actualiser: actualiser ? 1 : undefined });
  }

  /** Paiement reçu : prolonge la licence de la formule demandée (super admin). */
  confirmerDemande(id: string, mois?: number) {
    return this.api.post<any>(`/licences/demandes-renouvellement/${id}/confirmer/`, mois ? { mois } : {});
  }

  verifierCle(cle: string) {
    return this.api.post<any>('/licences/verifier/', { cle_licence: cle });
  }

  suspendre(id: number)              { return this.api.post<any>(`/licences/${id}/suspendre/`, {}); }
  activer(id: number)                { return this.api.post<any>(`/licences/${id}/activer/`, {}); }
  changerType(id: number, type: string) { return this.api.post<any>(`/licences/${id}/changer_type/`, { type }); }
  /** Supprime DÉFINITIVEMENT l'école et toutes ses données : le nom exact sert de confirmation. */
  supprimer(id: string, confirmation: string) {
    return this.api.delete<any>(`/licences/${id}/?confirmation=${encodeURIComponent(confirmation)}`);
  }

  getDetailsEcole(tenantId: string)  { return this.api.get<any>(`/tenants/${tenantId}/details/`); }
  updateDetailsEcole(tenantId: string, data: { tenant: any; exercice: any }) {
    return this.api.patch<any>(`/tenants/${tenantId}/details/`, data);
  }
}
