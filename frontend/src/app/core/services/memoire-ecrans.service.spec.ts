import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { AuthService } from './auth.service';
import { MemoireEcransService } from './memoire-ecrans.service';

describe('MemoireEcransService', () => {
  let memoire: MemoireEcransService;
  let auth: AuthService;
  const user = { id: 'u1', nom: 'Dir', email: 'd@x.sn', role: 'SUPER_ADMIN' as const };

  const emissions = <T>(url: string, frais: T): T[] => {
    const vus: T[] = [];
    memoire.avecMemoire(url, undefined, of(frais)).subscribe(v => vus.push(v));
    return vus;
  };

  beforeEach(() => {
    localStorage.clear();
    TestBed.resetTestingModule();
    auth = TestBed.inject(AuthService);
    auth.currentUser.set(user);
    memoire = TestBed.inject(MemoireEcransService);
  });

  it('premier passage : la réponse fraîche seulement', () => {
    expect(emissions('/k/', 1)).toEqual([1]);
  });

  it('passage suivant : la réponse connue, puis la fraîche', () => {
    emissions('/k/', 1);
    expect(emissions('/k/', 2)).toEqual([1, 2]);
    expect(emissions('/k/', 3)).toEqual([2, 3]);
  });

  it("une autre école ne voit pas les chiffres de la précédente", () => {
    emissions('/k/', 1);
    auth.switchTenant('t2', 'Autre école');
    expect(emissions('/k/', 9)).toEqual([9]);
  });

  it('vidée à la déconnexion', () => {
    emissions('/k/', 1);
    auth.currentUser.set(null);
    TestBed.tick();
    auth.currentUser.set(user);
    expect(emissions('/k/', 2)).toEqual([2]);
  });

  it('oublie la plus ancienne au-delà du plafond', () => {
    for (let i = 0; i <= MemoireEcransService.MAX; i++) memoire.ecrire(`/u${i}/`, undefined, i);
    expect(memoire.lire('/u0/')).toBeUndefined();
    expect(memoire.lire(`/u${MemoireEcransService.MAX}/`)).toBe(MemoireEcransService.MAX);
  });
});
