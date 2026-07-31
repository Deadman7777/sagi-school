import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { ElevesService } from './eleves.service';

/**
 * `getOrganismes()` doit TOUJOURS rendre un tableau.
 *
 * DRF pagine par défaut (PAGE_SIZE 500) : la route rend `{count, results}` et
 * non une liste. Les trois appelants faisaient `.filter()` ou `.find()` dessus
 * et levaient une `TypeError: o.filter is not a function` non rattrapée — le
 * sélecteur « Payé par » de l'écran de saisie restait vide en permanence, et la
 * console crachait à chaque ouverture de la page Paiements.
 *
 * La normalisation vit dans le service, pas chez les appelants : corriger les
 * trois laisserait le quatrième retomber dedans le jour où il sera écrit.
 */
describe('ElevesService — organismes payeurs', () => {
  let svc: ElevesService;
  let http: HttpTestingController;

  const organisme = { id: 'o1', nom: 'État du Sénégal', actif: true };

  beforeEach(() => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      providers: [ElevesService, provideHttpClient(), provideHttpClientTesting()],
    });
    svc = TestBed.inject(ElevesService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  const repondre = (corps: Record<string, unknown> | unknown[] | null) => {
    const req = http.expectOne(r => r.url.endsWith('/eleves/organismes/'));
    req.flush(corps as never);
  };

  it('déplie une réponse paginée', () => {
    let recu: unknown;
    svc.getOrganismes().subscribe(r => (recu = r));

    repondre({ count: 1, next: null, previous: null, results: [organisme] });

    expect(recu).toEqual([organisme]);
  });

  it('laisse passer un tableau brut', () => {
    let recu: unknown;
    svc.getOrganismes().subscribe(r => (recu = r));

    repondre([organisme]);

    expect(recu).toEqual([organisme]);
  });

  it('rend un tableau vide plutôt que null', () => {
    let recu: unknown;
    svc.getOrganismes().subscribe(r => (recu = r));

    repondre(null);

    expect(recu).toEqual([]);
  });

  it('le résultat supporte .filter() — le geste qui plantait', () => {
    let recu: { actif: boolean }[] = [];
    svc.getOrganismes().subscribe(r => (recu = r));

    repondre({ count: 2, next: null, previous: null,
               results: [organisme, { id: 'o2', nom: 'ONG', actif: false }] });

    expect(() => recu.filter(o => o.actif)).not.toThrow();
    expect(recu.filter(o => o.actif).length).toBe(1);
  });
});
