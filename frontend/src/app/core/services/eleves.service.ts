import { Injectable } from '@angular/core';
import { ApiService } from './api.service';
import { Eleve, Section, PaginatedResponse } from '../models/eleve.model';

@Injectable({ providedIn: 'root' })
export class ElevesService {
  constructor(private api: ApiService) {}

  getEleves(params?: Record<string, string>) {
    return this.api.get<PaginatedResponse<Eleve>>('/eleves/liste', params);
  }

  getEleve(id: string) {
    return this.api.get<Eleve>(`/eleves/${id}/`);
  }

  createEleve(data: Partial<Eleve>) {
    return this.api.post<Eleve>('/eleves/', data);
  }

  updateEleve(id: string, data: Partial<Eleve>) {
    return this.api.patch<Eleve>(`/eleves/${id}/`, data);
  }

  deleteEleve(id: string) {
    return this.api.delete(`/eleves/${id}/`);
  }

  getSections() {
    return this.api.get<PaginatedResponse<Section>>('/eleves/sections/');
  }
}
