export interface User {
  id: string;
  nom: string;
  prenom?: string;
  email: string;
  role: 'SUPER_ADMIN' | 'ADMIN_ECOLE' | 'ADMIN_RH' | 'ADMIN_COMPTABLE' | 'ADMIN_SCOLARITE' | 'LECTEUR';
  tenant?: string;
  type_licence?: string;
  modules?: string[];
  /** Vrai quand l'école a choisi les modules de CET utilisateur. */
  modules_perso?: boolean;
}

export interface AuthTokens {
  access: string;
  refresh: string;
}
