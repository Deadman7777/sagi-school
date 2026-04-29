import { Injectable } from '@angular/core';
import { ApiService } from './api.service';

@Injectable({ providedIn: 'root' })
export class RhService {
  constructor(private api: ApiService) {}
  getStats()    { return this.api.get<any>('/rh/stats/'); }
  getEmployes(params?: any) { return this.api.get<any>('/rh/employes/', params); }
  creerEmploye(data: any)   { return this.api.post<any>('/rh/employes/', data); }
  modifierEmploye(id: string, data: any) { return this.api.patch<any>(`/rh/employes/${id}/`, data); }
  getPaies(params?: any)    { return this.api.get<any>('/rh/paies/', params); }
  creerPaie(data: any)      { return this.api.post<any>('/rh/paies/', data); }
}
