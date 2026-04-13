export interface User {
  id: string;
  nom: string;
  prenom?: string;
  email: string;
  role: 'SUPER_ADMIN' | 'ADMIN_ECOLE' | 'COMPTABLE' | 'CAISSIER' | 'LECTURE';
  tenant?: string;
}

export interface AuthTokens {
  access: string;
  refresh: string;
}
