export interface Section {
  id: string;
  nom: string;
  frais_inscription: number;
  frais_mensualite: number;
  frais_uniforme: number;
  frais_fournitures: number;
  frais_yendu: number;
  total_annuel: number;
}

export interface Eleve {
  id: string;
  numero: number;
  matricule: string;
  nom_complet: string;
  genre: 'G' | 'F';
  section: string;
  section_nom: string;
  date_naissance: string;
  lieu_naissance: string;
  nom_pere: string;
  telephone_pere: string;
  nom_mere: string;
  telephone_mere: string;
  date_inscription: string;
  statut: string;
  total_attendu: number;
  total_paye: number;
  reste_a_payer: number;
  niveau_alerte: 'OK' | 'ATTENTION' | 'URGENT';
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
