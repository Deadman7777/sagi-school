import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { MessageService } from 'primeng/api';
import { TranslateModule } from '@ngx-translate/core';

import { PaiementsComponent } from './paiements.component';

/**
 * Scolarité et transport sur deux reçus (installation du 08/10/2026).
 *
 * Scolarité 140 000 / mois, transport 30 000 / mois. L'école fait deux reçus.
 * L'invariant : reçu de scolarité + reçu de services = ce qu'aurait encaissé
 * un reçu unique. Séparer change la façon d'encaisser, pas le dû.
 */
describe('Reçus séparés — scolarité et services', () => {
  let c: PaiementsComponent;

  const donnees = (octobre: Record<string, unknown> = {}, separes = true) => ({
    exercice_id: 'ex-1',
    recus_services_separes: separes,
    fees_bruts: { inscription: 0, mensualite: 140000, uniforme: 0, fournitures: 0 },
    fees_nets:  { inscription: 0, mensualite: 140000, uniforme: 0, fournitures: 0 },
    deja_paye:  { inscription: 0, mensualite: 0, uniforme: 0, fournitures: 0 },
    reste:      { inscription: 0, mensualite: 0, uniforme: 0, fournitures: 0 },
    services: [{ id: 'tr', nom: 'Transport', montant: 30000, periodicite: 'MENSUEL', mois_unique: null }],
    adhesions: [],
    mois_ecole: [{
      num: 10, annee: 2026, label: 'Octobre', du: true, du_brut: 170000, pec: 0,
      montant: 170000, verse: 0, reste: 170000, statut: 'IMPAYE', paye: false,
      echu: true, montant_saisi: false, services: { tr: 30000 },
      reste_services: { tr: 30000 }, reste_scolarite: 140000, ...octobre,
    }],
    reliquat: { annee: '', du: 0, paye: 0, restant: 0 },
    arrieres: { entree: { libelle: 'Inscription', reste: 0 }, mois: [], total: 0 },
  });

  const charger = (data: unknown, type: 'MENSUALITE' | 'SERVICES') => {
    c.eleveSelectionne = { id: 'e-1', nom_complet: 'Awa NDIAYE' };
    c.saisieDonnees.set(data);
    c.setTypePaiement(type);
  };

  beforeEach(() => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [TranslateModule.forRoot()],
      providers: [MessageService, provideHttpClient(), provideHttpClientTesting(), provideRouter([])],
    });
    c = TestBed.createComponent(PaiementsComponent).componentInstance;
  });

  it('le reçu de scolarité ne propose que la scolarité', () => {
    charger(donnees(), 'MENSUALITE');
    expect(c.form.services).toEqual([]);
    expect(c.duSaisie().reste).toBe(140000);
    expect(c.montantVerse).toBe(140000);
    expect(c.form.montant_mensualite).toBe(140000);
  });

  it('le reçu de services ne propose que le transport', () => {
    charger(donnees(), 'SERVICES');
    expect(c.form.mois_regles).toEqual([10]);
    expect(c.form.montant_mensualite).toBe(0);
    expect(c.form.services.map(s => [s.nom, s.du, s.montant])).toEqual([['Transport', 30000, 30000]]);
    expect(c.duSaisie().reste).toBe(30000);
  });

  it('les deux reçus ensemble font le reçu unique', () => {
    charger(donnees(), 'MENSUALITE');
    const scolarite = c.montantVerse;
    charger(donnees(), 'SERVICES');
    const services = c.montantVerse;
    charger(donnees({}, false), 'MENSUALITE');
    expect(scolarite + services).toBe(c.montantVerse);
  });

  it('scolarité déjà réglée : le mois reste ouvert pour le seul transport', () => {
    const apres = { verse: 140000, reste: 30000, statut: 'PARTIEL', reste_scolarite: 0 };
    charger(donnees(apres), 'SERVICES');
    expect(c.form.mois_regles).toEqual([10]);
    expect(c.duSaisie().reste).toBe(30000);
    // Côté scolarité, octobre est soldé : rien n'est proposé.
    charger(donnees(apres), 'MENSUALITE');
    expect(c.statutMois(c.saisieDonnees().mois_ecole[0])).toBe('SOLDE');
    expect(c.form.mois_regles).toEqual([]);
  });

  it('un versement partiel de transport laisse le reste dû', () => {
    charger(donnees(), 'SERVICES');
    c.montantVerse = 20000;
    expect(c.form.services[0].montant).toBe(20000);
    expect(c.resteApresVersement()).toBe(10000);
  });
});
