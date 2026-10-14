import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { provideHttpClient } from '@angular/common/http';
import { TestBed } from '@angular/core/testing';

import { ApiService } from './api.service';

/**
 * Un filtre non renseigné ne doit JAMAIS partir dans l'URL.
 *
 * `Object.entries` conserve les clés dont la valeur vaut `undefined`, et
 * `HttpParams.set()` la convertit en chaîne : la requête partait en
 * `?q=undefined`, que le backend prenait pour un critère de recherche.
 * L'écran « Anciens élèves » de Shoumoul était vide en permanence alors que
 * l'API renvoyait bien les trois fiches.
 */
describe('ApiService — paramètres de requête', () => {
  let api: ApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    // Le TestBed peut rester instancié par un spec précédent en échec.
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [ApiService, provideHttpClient(), provideHttpClientTesting()],
    });
    api = TestBed.inject(ApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('ignore les valeurs undefined', () => {
    api.get('/eleves/anciens/', { q: undefined, statut: undefined }).subscribe();

    const req = http.expectOne(r => r.url.endsWith('/eleves/anciens/'));
    expect(req.request.params.has('q')).toBe(false);
    expect(req.request.params.has('statut')).toBe(false);
    req.flush({});
  });

  it('ignore null et la chaîne vide', () => {
    api.get('/x/', { a: null, b: '' }).subscribe();

    const req = http.expectOne(r => r.url.endsWith('/x/'));
    expect(req.request.params.keys().length).toBe(0);
    req.flush({});
  });

  it('conserve les valeurs renseignées, y compris 0 et false', () => {
    api.get('/x/', { q: 'Mame', page: 0, actif: false }).subscribe();

    const req = http.expectOne(r => r.url.endsWith('/x/'));
    expect(req.request.params.get('q')).toBe('Mame');
    expect(req.request.params.get('page')).toBe('0');
    expect(req.request.params.get('actif')).toBe('false');
    req.flush({});
  });

  it('n’envoie que le critère renseigné quand l’autre est vide', () => {
    api.get('/eleves/anciens/', { q: 'KANE', statut: undefined }).subscribe();

    const req = http.expectOne(r => r.url.endsWith('/eleves/anciens/'));
    expect(req.request.params.get('q')).toBe('KANE');
    expect(req.request.params.has('statut')).toBe(false);
    req.flush({});
  });
});

/**
 * `lire` : au retour sur un écran, la dernière réponse s'affiche aussitôt,
 * puis la fraîche la remplace (14/10/2026).
 */
describe('ApiService — lire (dernière réponse connue)', () => {
  let api: ApiService;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [ApiService, provideHttpClient(), provideHttpClientTesting()],
    });
    api = TestBed.inject(ApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('premier passage : attend le serveur', () => {
    const recus: unknown[] = [];
    api.lire('/rh/stats/').subscribe(v => recus.push(v));
    expect(recus).toEqual([]);
    http.expectOne(r => r.url.endsWith('/rh/stats/')).flush({ n: 1 });
    expect(recus).toEqual([{ n: 1 }]);
  });

  it('deuxième passage : la connue tout de suite, puis la fraîche', () => {
    api.lire('/rh/stats/').subscribe();
    http.expectOne(r => r.url.endsWith('/rh/stats/')).flush({ n: 1 });

    const recus: unknown[] = [];
    api.lire('/rh/stats/').subscribe(v => recus.push(v));
    expect(recus).toEqual([{ n: 1 }]);
    http.expectOne(r => r.url.endsWith('/rh/stats/')).flush({ n: 2 });
    expect(recus).toEqual([{ n: 1 }, { n: 2 }]);
  });

  it('des paramètres différents ne se mélangent pas ; les vides sont ignorés', () => {
    api.lire('/rh/bulletins/', { mois: '3', employe: undefined }).subscribe();
    http.expectOne(r => r.url.endsWith('/rh/bulletins/')).flush(['mars']);

    const avril: unknown[] = [];
    api.lire('/rh/bulletins/', { mois: '4' }).subscribe(v => avril.push(v));
    expect(avril).toEqual([]);
    http.expectOne(r => r.url.endsWith('/rh/bulletins/')).flush(['avril']);

    const mars: unknown[] = [];
    api.lire('/rh/bulletins/', { mois: '3' }).subscribe(v => mars.push(v));
    expect(mars).toEqual([['mars']]);
    http.expectOne(r => r.url.endsWith('/rh/bulletins/')).flush(['mars']);
  });
});
