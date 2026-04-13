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
  nom_complet: string;
  genre: 'G' | 'F';
  section: string;
  section_nom: string;
  telephone_parent: string;
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
