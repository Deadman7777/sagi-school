import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { Eleve } from '../models/eleve.model';
import { AuthService } from './auth.service';
import { ElevesService } from './eleves.service';

/**
 * La liste de l'écran Élèves est gardée en mémoire pour s'afficher aussitôt
 * au retour dans le module (14/10/2026). Elle ne doit jamais apparaître pour
 * une autre école, un autre exercice ni après la déconnexion.
 */
describe('ElevesService — dernière liste en mémoire', () => {
  let svc: ElevesService;
  let auth: AuthService;
  const liste = [{ id: 'e1', nom_complet: 'Awa DIOP' }] as Eleve[];
  const params = { leger: '1' };

  beforeEach(() => {
    localStorage.clear();
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [ElevesService, provideHttpClient(), provideHttpClientTesting()],
    });
    auth = TestBed.inject(AuthService);
    auth.currentUser.set({ id: 'u1', nom: 'Dir', email: 'd@x.sn', role: 'SUPER_ADMIN' });
    svc = TestBed.inject(ElevesService);
  });

  it('rend la liste du passage précédent', () => {
    svc.memoriserListe(params, liste);
    expect(svc.listeEnMemoire({ leger: '1' })).toBe(liste);
  });

  it("rien pour un autre exercice", () => {
    svc.memoriserListe(params, liste);
    expect(svc.listeEnMemoire({ leger: '1', exercice: 'ex2' })).toBeNull();
  });

  it("rien quand le super admin change d'école", () => {
    svc.memoriserListe(params, liste);
    auth.switchTenant('t2', 'Autre école');
    expect(svc.listeEnMemoire(params)).toBeNull();
  });

  it('rien après la déconnexion', () => {
    svc.memoriserListe(params, liste);
    auth.currentUser.set(null);
    TestBed.tick();
    auth.currentUser.set({ id: 'u1', nom: 'Dir', email: 'd@x.sn', role: 'SUPER_ADMIN' });
    expect(svc.listeEnMemoire(params)).toBeNull();
  });
});
