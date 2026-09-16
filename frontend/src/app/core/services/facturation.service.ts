import { Injectable, inject } from '@angular/core';
import { ApiService, ParamsRecord } from './api.service';

export type TypeDocument = 'PROFORMA' | 'FACTURE' | 'AVOIR';
export type StatutPaiement = 'A_PAYER' | 'PARTIELLE' | 'PAYEE' | null;

export interface LigneDocument {
  id?: string;
  designation: string;
  detail: string;
  quantite: number;
  unite: string;
  prix_unitaire: number;
  /** Calculé par le serveur. */
  montant?: number;
}

export interface Recu {
  id: string;
  numero: string;
  date: string;
  montant: number;
  mode: string;
  mode_libelle: string;
  reference: string;
  observations: string;
  annule: boolean;
  annule_motif: string;
  facture: string;
  facture_numero: string;
  client_nom: string;
}

/** Proforma, facture ou avoir. Tous les montants sont calculés par le serveur. */
export interface DocumentCommercial {
  id: string;
  type: TypeDocument;
  type_libelle: string;
  numero: string;
  statut: 'BROUILLON' | 'EMIS' | 'CONVERTI';
  statut_libelle: string;
  client_nom: string;
  objet: string;
  date_emission: string | null;
  date_echeance: string | null;
  date_validite: string | null;
  total_ht: number;
  montant_tva: number;
  total_ttc: number;
  statut_paiement: StatutPaiement;
  solde: number;
  en_retard: boolean;
  modifiable: boolean;
  prospect: string | null;
  tenant: string | null;
  /** Présents sur le détail uniquement. */
  lignes?: LigneDocument[];
  encaissements?: Recu[];
  derives?: { id: string; type: TypeDocument; numero: string; statut: string; total_ttc: number }[];
  [autre: string]: any;
}

export interface SyntheseFacturation {
  facture: number;
  encaisse: number;
  restant: number;
  nb_impayees: number;
  en_retard: number;
  nb_en_retard: number;
}

export interface EcoleCliente {
  id: string;
  nom: string;
  ville: string;
  licence_type: string | null;
  licence_fin: string | null;
}

@Injectable({ providedIn: 'root' })
export class FacturationService {
  private api = inject(ApiService);

  documents(filtres?: ParamsRecord) {
    return this.api.get<DocumentCommercial[]>('/facturation/documents/', filtres);
  }
  document(id: string) { return this.api.get<DocumentCommercial>(`/facturation/documents/${id}/`); }
  synthese()           { return this.api.get<SyntheseFacturation>('/facturation/documents/synthese/'); }
  clients()            { return this.api.get<EcoleCliente[]>('/facturation/documents/clients/'); }

  creer(data: Record<string, unknown>) {
    return this.api.post<DocumentCommercial>('/facturation/documents/', data);
  }
  modifier(id: string, data: Record<string, unknown>) {
    return this.api.patch<DocumentCommercial>(`/facturation/documents/${id}/`, data);
  }
  supprimer(id: string) { return this.api.delete<void>(`/facturation/documents/${id}/`); }
  emettre(id: string)   { return this.api.post<DocumentCommercial>(`/facturation/documents/${id}/emettre/`, {}); }
  convertir(id: string) { return this.api.post<DocumentCommercial>(`/facturation/documents/${id}/convertir/`, {}); }
  avoir(id: string, motif: string) {
    return this.api.post<DocumentCommercial>(`/facturation/documents/${id}/avoir/`, { motif });
  }
  encaisser(id: string, data: { montant: number; mode: string; date?: string; reference?: string; observations?: string }) {
    return this.api.post<{ recu: Recu; facture: DocumentCommercial }>(
      `/facturation/documents/${id}/encaisser/`, data);
  }
  pdf(id: string)       { return this.api.getBlob(`/facturation/documents/${id}/pdf/`); }

  annulerRecu(id: string, motif: string) {
    return this.api.post<Recu>(`/facturation/encaissements/${id}/annuler/`, { motif });
  }
  pdfRecu(id: string) { return this.api.getBlob(`/facturation/encaissements/${id}/pdf/`); }

  parametres()                               { return this.api.get<any>('/facturation/parametres/'); }
  modifierParametres(data: Record<string, unknown>) { return this.api.patch<any>('/facturation/parametres/', data); }
}
