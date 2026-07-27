export interface Section {
  id: string;
  nom: string;
  frais_inscription: number;
  frais_mensualite: number;
  frais_uniforme: number;
  frais_fournitures: number;
  total_annuel: number;
}

export type PeriodiciteService = 'UNIQUE' | 'MENSUEL';

export interface Service {
  id: string;
  nom: string;
  montant: number;
  periodicite: PeriodiciteService;
  actif: boolean;
}

export type NiveauAlerte = 'A_JOUR' | 'OK' | 'ATTENTION' | 'URGENT' | 'CRITIQUE';
export type TypePEC = 'INSCRIPTION' | 'MENSUALITES' | 'TOTALE';

export interface Eleve {
  id: string;
  numero: number;
  matricule: string;
  // Matricule d'avant le rebasage au format promo — les carnets papier de
  // l'école restent exploitables.
  matricule_ancien: string;
  // Entrée dans l'établissement, figée à vie et recopiée à chaque
  // réinscription (date_inscription, elle, est repositionnée chaque année).
  annee_entree: string;
  date_entree: string | null;
  nom_complet: string;
  genre: 'G' | 'F';
  section: string;
  section_nom: string;
  classe: string;
  classe_nom: string;
  date_naissance: string;
  lieu_naissance: string;
  nom_pere: string;
  telephone_pere: string;
  nom_mere: string;
  telephone_mere: string;
  nom_tuteur: string;
  telephone_tuteur: string;
  lien_tuteur: string;
  etat_sante: 'SAIN' | 'SUIVI' | 'CHRONIQUE';
  observations_sante: string;
  date_inscription: string;
  date_inscription_jour_estime: boolean;
  date_inscription_libelle: string;
  // Daara (Taxawu Daara) : passager = durée convenue en mois depuis l'entrée
  regime: 'EXERCICE' | 'PASSAGER';
  nb_mois_passager: number | null;
  statut: string;
  // Prise en charge — motif
  prise_en_charge: string | null;
  obs_prise_en_charge: string;
  // Prise en charge — MONTANTS directs (priment sur les taux)
  pec_inscription: number;
  pec_mensualite: number;
  // Anciens taux (compat)
  type_pec: TypePEC | null;
  taux_pec_inscription: number;
  taux_pec_mensualite: number;
  taux_prise_en_charge: number;
  // Services optionnels (IDs de services auxquels l'élève est abonné)
  abonnements: string[];
  // Montants calculés (read-only depuis le backend)
  total_theorique: number;
  total_attendu: number;
  montant_pec_inscription: number;
  montant_pec_mensualite_mensuel: number;
  montant_pec_annuel: number;
  montant_services_annuel: number;
  total_paye: number;
  reste_a_payer: number;
  niveau_alerte: NiveauAlerte;
  // Dette des années antérieures — reportée automatiquement d'un exercice à
  // l'autre, ou saisie à la migration. Suivie à part du dû de l'année : le
  // niveau d'alerte ne juge que l'année en cours.
  reliquat_anterieur: number;
  reliquat_note: string;
  reliquat_paye: number;
  reliquat_restant: number;
  reliquat_origine_libelle: string;
  reste_a_payer_global: number;
}

/** Une ligne de la grille de saisie des impayés antérieurs (migration). */
export interface LigneImpayeAnterieur {
  eleve_id: string;
  matricule: string;
  nom_complet: string;
  section: string;
  montant: number;
  deja_paye: number;
  restant: number;
  note: string;
}

/** Une année de scolarité dans le parcours d'un élève. */
export interface AnneeParcours {
  eleve_id: string;
  annee: string;
  section: string;
  classe: string;
  statut: string;
  statut_libelle: string;
  fiche_creance: boolean;
  total_attendu: number;
  total_paye: number;
  reste: number;
  reliquat: number;
  reliquat_restant: number;
  du_global: number;
}

export interface ParcoursEleve {
  eleve_id: string;
  nom_complet: string;
  matricule: string;
  matricule_ancien: string;
  annee_entree: string;
  date_entree: string | null;
  annee_sortie: string;
  statut: string;
  statut_libelle: string;
  est_sorti: boolean;
  section: string;
  classe: string;
  nb_annees: number;
  annees: AnneeParcours[];
  total_attendu: number;
  total_paye: number;
  /** Dette d'aujourd'hui — surtout pas la somme des restes annuels. */
  du_actuel: number;
}

export interface AncienEleve {
  eleve_id: string;
  matricule: string;
  matricule_ancien: string;
  nom_complet: string;
  genre: string;
  annee_entree: string;
  date_entree: string | null;
  annee_sortie: string;
  statut: string;
  statut_libelle: string;
  derniere_classe: string;
  nb_annees: number;
  total_paye: number;
  solde_du: number;
}

export interface ResumeImpayesAnterieurs {
  exercice: string;
  nb_eleves: number;
  montant_total: number;
}

export interface PriseEnChargeStats {
  nb_total_eleves: number;
  nb_eleves_pec: number;
  nb_par_type: { type: TypePEC; libelle: string; nb: number }[];
  nb_par_motif: { motif: string; libelle: string; nb: number }[];
  financier: {
    recettes_theoriques_annuelles: number;
    recettes_reelles_attendues: number;
    perte_annuelle_pec: number;
    cout_mensuel_pec: number;
    cout_annuel_pec: number;
    mensualite_theorique_mensuelle: number;
    mensualite_reelle_mensuelle: number;
    ecart_mensuel: number;
  };
  detail: {
    eleve_id: string;
    nom_complet: string;
    section: string;
    motif: string;
    type_pec: TypePEC;
    taux_pec_inscription: number;
    taux_pec_mensualite: number;
    montant_pec_inscription: number;
    montant_pec_mensuel: number;
    montant_pec_annuel: number;
    total_theorique: number;
    total_attendu: number;
    total_paye: number;
    reste_a_payer: number;
    niveau_alerte: NiveauAlerte;
  }[];
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
