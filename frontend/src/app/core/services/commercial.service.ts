import { Injectable, inject } from '@angular/core';

import { ApiService } from './api.service';

/** Une formule chiffrée par le serveur (jamais recalculée à l'écran). */
export interface FormuleChiffree {
  licence: number; remise: number; net: number; equivalent: number; total: number;
}

export interface Chiffrage {
  prix_mensuel: number; installation: number; migration: number;
  taux_semestriel: number; taux_annuel: number;
  mensuelle: FormuleChiffree; semestrielle: FormuleChiffree; annuelle: FormuleChiffree;
  tranches: number[];
  sur_12_mois: { formule: string; sans_migration: number; avec_migration: number; economie: number }[];
}

export interface Proposition {
  id: string; reference: string; prospect: string | null; etablissement: string;
  type_licence: string; licence_libelle: string;
  statut: 'BROUILLON' | 'VALIDEE' | 'ENVOYEE' | 'ACCEPTEE' | 'REFUSEE'; statut_libelle: string;
  date_emission: string; date_validite: string; expiree: boolean; modifiable: boolean;
  total_annuel: number; envoyee_le: string | null; envoyee_a: string; erreur_envoi: string;
  formule_choisie: string; formule_libelle: string; migration_choisie: boolean | null;
  // Fiche complète
  sous_titre?: string; adresse?: string; telephones?: string; email?: string;
  autres_contacts?: string; a_l_attention?: string; contact_nom?: string;
  programme?: string; edition?: string; contexte?: string;
  besoins?: string[]; resultats?: string[];
  prix_mensuel?: number; taux_semestriel?: number; taux_annuel?: number;
  frais_installation?: number; frais_migration?: number; migration_proposee?: boolean;
  validite_jours?: number; documents_joints?: string[]; chiffrage?: Chiffrage;
}

export interface CourrielProposition {
  sujet: string; corps: string; destinataires: string; whatsapp: string; smtp: boolean;
}

export interface DocumentBibliotheque {
  id: string; titre: string; categorie: 'BROCHURE' | 'CATALOGUE' | 'AUTRE';
  categorie_libelle: string; description: string; nom_fichier: string; taille: number;
  joindre_par_defaut: boolean; actif: boolean; ordre: number; created_at: string;
}

@Injectable({ providedIn: 'root' })
export class CommercialService {
  private api = inject(ApiService);

  // ── Propositions ─────────────────────────────────────────────────────
  propositions(prospect?: string) {
    return this.api.get<Proposition[]>('/commercial/propositions/', { prospect });
  }
  proposition(id: string) { return this.api.get<Proposition>(`/commercial/propositions/${id}/`); }
  etablir(prospect: string, type_licence: string) {
    return this.api.post<Proposition>('/commercial/propositions/', { prospect, type_licence });
  }
  /** Pour un client sans fiche : la fiche prospect est créée (ou retrouvée) au passage. */
  etablirPourClient(client: { etablissement: string; ville?: string; telephone?: string;
                              email?: string; contact_nom?: string }, type_licence: string) {
    return this.api.post<Proposition>('/commercial/propositions/', { ...client, type_licence });
  }
  modifier(id: string, data: Partial<Proposition>) {
    return this.api.patch<Proposition>(`/commercial/propositions/${id}/`, data);
  }
  supprimer(id: string) { return this.api.delete<void>(`/commercial/propositions/${id}/`); }
  valider(id: string)   { return this.api.post<Proposition>(`/commercial/propositions/${id}/valider/`, {}); }
  rouvrir(id: string)   { return this.api.post<Proposition>(`/commercial/propositions/${id}/rouvrir/`, {}); }
  dupliquer(id: string) { return this.api.post<Proposition>(`/commercial/propositions/${id}/dupliquer/`, {}); }
  courriel(id: string)  { return this.api.get<CourrielProposition>(`/commercial/propositions/${id}/courriel/`); }
  envoyer(id: string, data: { destinataires: string; sujet: string; corps: string; documents: string[] }) {
    return this.api.post<Proposition & { servis: string[]; whatsapp: string }>(
      `/commercial/propositions/${id}/envoyer/`, data);
  }
  repondre(id: string, decision: 'ACCEPTEE' | 'REFUSEE', formule = '', migration: boolean | null = null) {
    return this.api.post<Proposition>(`/commercial/propositions/${id}/repondre/`,
                                      { decision, formule, migration });
  }
  pdf(id: string) { return this.api.getBlob(`/commercial/propositions/${id}/pdf/`); }

  // ── Bibliothèque ─────────────────────────────────────────────────────
  documents(actifs = false) {
    return this.api.get<DocumentBibliotheque[]>('/commercial/bibliotheque/', actifs ? { actifs: 1 } : {});
  }
  deposer(data: { titre: string; categorie: string; nom_fichier: string; contenu: string;
                  description?: string; joindre_par_defaut?: boolean }) {
    return this.api.post<DocumentBibliotheque>('/commercial/bibliotheque/', data);
  }
  modifierDocument(id: string, data: Partial<DocumentBibliotheque>) {
    return this.api.patch<DocumentBibliotheque>(`/commercial/bibliotheque/${id}/`, data);
  }
  supprimerDocument(id: string) { return this.api.delete<DocumentBibliotheque | null>(`/commercial/bibliotheque/${id}/`); }
  fichier(id: string) { return this.api.getBlob(`/commercial/bibliotheque/${id}/fichier/`); }
}
