import { Injectable, inject } from '@angular/core';
import { ApiService, ParamsRecord } from './api.service';

export interface Prospect {
  id: string;
  etablissement: string;
  type_organisation: string;
  ville: string;
  telephone: string;
  email: string;
  contact_nom: string;
  contact_fonction: string;
  contact_telephone: string;
  nb_eleves: number | null;
  statut: string;
  statut_libelle: string;
  source: string;
  relance_le: string | null;
  relance_en_retard: boolean;
  anciennete_jours: number;
  nb_interactions: number | null;
  cree_le: string;
  /** Présents uniquement sur la fiche détaillée (GET /prospects/{id}/). */
  interactions?: Interaction[];
  conversations?: ConversationSama[];
  devis?: Devis[];
  donnees_brutes?: Record<string, string>;
  [autre: string]: any;
}

export interface Interaction {
  id: string;
  date: string;
  canal: string;
  canal_libelle: string;
  resume: string;
  auteur: string;
}

/** Un échange avec l'assistant SAMA, tel qu'il s'est déroulé sur le site.
 *  Le résumé du diagnostic est rédigé par le serveur d'après ce que SAMA a
 *  retenu ; ceci est ce que le visiteur a réellement écrit. */
export interface ConversationSama {
  id: string;
  date: string;
  messages: { role: 'user' | 'assistant'; contenu: string }[];
}

/** Une proposition chiffrée. Les montants viennent du catalogue serveur :
 *  l'écran les affiche, il ne les calcule jamais. */
export interface Devis {
  id: string;
  numero: string;
  etablissement: string;
  type_licence: string;
  cycle: string;
  mois: number;
  montant_net: number;
  montant_total: number;
  statut: 'BROUILLON' | 'VALIDE' | 'ENVOYE' | 'ACCEPTE' | 'REFUSE';
  statut_libelle: string;
  date_emission: string;
  date_validite: string;
  expire: boolean;
  modifiable: boolean;
  [autre: string]: any;
}

export interface LigneCatalogue {
  code: string;
  libelle: string;
  prix_mensuel: number;
  modules: { nom: string; detail: string }[];
}

export interface Catalogue {
  reference: string;
  validite_devis_jours: number;
  taux_remise_annuelle: number;
  moyens_paiement: string[];
  licences: LigneCatalogue[];
  cycles: { code: string; libelle: string }[];
}

export interface StatsProspects {
  total: number;
  par_statut: { statut: string; libelle: string; nombre: number }[];
  nouveaux: number;
  en_cours: number;
  gagnes: number;
  taux_conversion: number;
  a_relancer: number;
  en_retard: number;
  recus_30j: number;
  jamais_contactes: number;
}

@Injectable({ providedIn: 'root' })
export class ProspectsService {
  private api = inject(ApiService);

  liste(filtres?: ParamsRecord) { return this.api.get<Prospect[]>('/prospects/', filtres); }
  fiche(id: string)             { return this.api.get<Prospect>(`/prospects/${id}/`); }
  stats()                       { return this.api.get<StatsProspects>('/prospects/stats/'); }
  referentiels()                { return this.api.get<any>('/prospects/referentiels/'); }

  creer(data: any)              { return this.api.post<Prospect>('/prospects/', data); }
  modifier(id: string, data: any) { return this.api.patch<Prospect>(`/prospects/${id}/`, data); }
  supprimer(id: string)         { return this.api.delete<void>(`/prospects/${id}/`); }

  consigner(id: string, echange: { canal: string; resume: string; date?: string;
                                   relance_le?: string | null }) {
    return this.api.post<Prospect>(`/prospects/${id}/interaction/`, echange);
  }

  // ── Devis ────────────────────────────────────────────────────────────
  // La grille tarifaire est servie par le serveur, jamais recopiée ici :
  // c'est elle qui chiffre les devis, et deux sources divergeraient sur une
  // pièce signée.
  catalogue() { return this.api.get<Catalogue>('/licences/catalogue/'); }

  etablirDevis(data: {
    prospect: string; type_licence: string; cycle: string; mois: number;
    frais_installation?: number; prestations?: string;
    montant_prestations?: number; observations?: string;
  }) {
    return this.api.post<Devis>('/devis/', data);
  }

  modifierDevis(id: string, data: any) { return this.api.patch<Devis>(`/devis/${id}/`, data); }
  supprimerDevis(id: string)           { return this.api.delete<void>(`/devis/${id}/`); }
  validerDevis(id: string)             { return this.api.post<Devis>(`/devis/${id}/valider/`, {}); }
  envoyerDevis(id: string)             { return this.api.post<Devis>(`/devis/${id}/envoyer/`, {}); }

  trancherDevis(id: string, reponse: 'ACCEPTE' | 'REFUSE', motif = '') {
    return this.api.post<Devis>(`/devis/${id}/trancher/`, { reponse, motif });
  }

  pdfDevis(id: string) { return this.api.getBlob(`/devis/${id}/pdf/`); }
}
