import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { MessageService } from 'primeng/api';
import { TranslateModule } from '@ngx-translate/core';

import { PaiementsComponent } from './paiements.component';

/**
 * Encaisser un acompte, et le dire juste.
 *
 * Le guichet ne savait pas prendre un versement partiel : le formulaire
 * proposait le tarif du mois et rien ne disait ce qu'il resterait dû. Une
 * famille qui donnait 35 000 sur les 65 000 du mois voyait le mois marqué payé
 * — alors que sa fiche continuait à réclamer 30 000. Les deux écrans se
 * contredisaient sur le même élève.
 *
 * Le cas rapporté, joué ici de bout en bout : mensualité 60 000, cantine
 * 8 000, transport 5 000 — soit 73 000 — dont 8 000 de prise en charge, donc
 * 65 000 réellement dus. La famille verse 35 000.
 *
 * L'invariant tenu par ces tests : le DÛ vient de l'échéancier et ne bouge
 * jamais, le VERSÉ vient du formulaire, et la somme des lignes du formulaire
 * égale toujours le montant versé — sans quoi le reçu et la comptabilité
 * raconteraient deux histoires.
 */
describe('Saisie de paiement — acompte et prise en charge', () => {
  let c: PaiementsComponent;

  /** Réponse de /saisie-paiement/ pour le cas rapporté. */
  const donnees = (moisJanvier: Partial<Record<string, unknown>> = {}) => ({
    exercice_id: 'ex-1',
    fees_bruts: { inscription: 100000, mensualite: 60000, uniforme: 0, fournitures: 0 },
    fees_nets:  { inscription: 100000, mensualite: 52000, uniforme: 0, fournitures: 0 },
    deja_paye:  { inscription: 0, mensualite: 0, uniforme: 0, fournitures: 0 },
    reste:      { inscription: 100000, mensualite: 65000, uniforme: 0, fournitures: 0 },
    pec: {
      libelle: 'Fondation', organisme: '',
      inscription: { brut: 100000, pec: 0,    net: 100000 },
      mensuel:     { brut: 73000,  pec: 8000, net: 65000 },
      annuel:      { brut: 830000, pec: 80000, net: 750000 },
    },
    services: [
      { id: 's1', nom: 'Cantine',   montant: 8000, periodicite: 'MENSUEL', mois_unique: null },
      { id: 's2', nom: 'Transport', montant: 5000, periodicite: 'MENSUEL', mois_unique: null },
    ],
    mois_ecole: [
      {
        num: 1, annee: 2026, label: 'Janvier', du: true, du_brut: 73000, pec: 8000,
        montant: 65000, verse: 0, reste: 65000, statut: 'IMPAYE', paye: false,
        echu: true, montant_saisi: false, ...moisJanvier,
      },
      {
        num: 2, annee: 2026, label: 'Février', du: true, du_brut: 73000, pec: 8000,
        montant: 65000, verse: 0, reste: 65000, statut: 'IMPAYE', paye: false,
        echu: false, montant_saisi: false,
      },
    ],
    reliquat: { annee: '', du: 0, paye: 0, restant: 0 },
    arrieres: { entree: { libelle: 'Inscription', reste: 0 }, mois: [], total: 0 },
    total_annuel_net: 750000, total_paye: 0, total_restant: 750000,
    total_restant_global: 750000, nb_paiements: 0,
  });

  /** Charge un élève dans le formulaire, comme le fait la sélection à l'écran. */
  const charger = (data: unknown) => {
    c.eleveSelectionne = { id: 'e-1', nom_complet: 'Awa NDIAYE' };
    c.saisieDonnees.set(data);
    // `appliquerAutoRemplissage` est privé : on passe par le chemin public qui
    // l'appelle, celui du bouton « Mensualité ».
    c.setTypePaiement('MENSUALITE');
  };

  beforeEach(() => {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [TranslateModule.forRoot()],
      providers: [MessageService, provideHttpClient(), provideHttpClientTesting()],
    });
    // Pas de detectChanges : ngOnInit déclencherait les appels de la page.
    c = TestBed.createComponent(PaiementsComponent).componentInstance;
  });

  // ── Ce que l'école réclame ────────────────────────────────────────────
  it('décompose le dû du mois : 73 000 réels, 8 000 pris en charge, 65 000 à payer', () => {
    charger(donnees());

    expect(c.duSaisie()).toEqual({ brut: 73000, pec: 8000, net: 65000, verse: 0, reste: 65000 });
  });

  it('propose par défaut ce qui reste dû sur le mois', () => {
    charger(donnees());

    expect(c.montantVerse).toBe(65000);
    expect(c.resteApresVersement()).toBe(0);
  });

  it('ventile le dû sur la mensualité et les services', () => {
    charger(donnees());

    expect(c.form.montant_mensualite).toBe(52000);
    expect(c.form.services.map(s => s.montant)).toEqual([8000, 5000]);
  });

  // ── Le versement partiel : le cas rapporté ────────────────────────────
  it('un versement de 35 000 laisse 30 000 dus', () => {
    charger(donnees());

    c.montantVerse = 35000;

    expect(c.resteApresVersement()).toBe(30000);
    expect(c.montantVerse).toBe(35000);
  });

  it('le dû ne bouge pas quand le versement change', () => {
    charger(donnees());
    const duAvant = c.duSaisie();

    c.montantVerse = 35000;

    expect(c.duSaisie()).toEqual(duAvant);
  });

  it("l'acompte va sur la scolarité avant les services", () => {
    charger(donnees());

    c.montantVerse = 35000;

    expect(c.form.montant_mensualite).toBe(35000);
    expect(c.form.services.map(s => s.montant)).toEqual([0, 0]);
  });

  it('la somme des lignes égale toujours le montant versé', () => {
    charger(donnees());

    for (const verse of [0, 1000, 35000, 52000, 60000, 65000]) {
      c.montantVerse = verse;
      expect(c.totalForm()).toBe(verse);
    }
  });

  // ── Reprendre un mois déjà entamé ─────────────────────────────────────
  it('un mois entamé ne réclame que son reste', () => {
    charger(donnees({ verse: 35000, reste: 30000, statut: 'PARTIEL' }));

    expect(c.duSaisie()).toEqual(
      { brut: 73000, pec: 8000, net: 65000, verse: 35000, reste: 30000 });
    expect(c.montantVerse).toBe(30000);
  });

  it('un mois soldé n\'est plus proposé — le suivant l\'est', () => {
    charger(donnees({ verse: 65000, reste: 0, statut: 'SOLDE', paye: true }));

    expect(c.form.mois_regles).toEqual([2]);
  });

  // ── L'avance : la famille donne plus que l'échéance ───────────────────
  it('un versement au-delà du dû est signalé comme une avance', () => {
    charger(donnees());

    c.montantVerse = 80000;

    expect(c.resteApresVersement()).toBe(-15000);
    expect(c.totalForm()).toBe(80000);
    // L'excédent reste sur la scolarité : ce n'est pas un produit divers.
    expect(c.form.montant_mensualite).toBe(67000);
  });

  it('deux mois cochés doublent le dû', () => {
    charger(donnees());

    c.toggleMois(2);

    expect(c.form.mois_regles).toEqual([1, 2]);
    expect(c.duSaisie().net).toBe(130000);
    expect(c.montantVerse).toBe(130000);
  });

  // ── Ce qui paie autre chose que l'échéance ────────────────────────────
  it("le reliquat d'une année antérieure ne solde pas l'échéance en cours", () => {
    const d = donnees();
    d.reliquat = { annee: '2025', du: 40000, paye: 0, restant: 40000 };
    charger(d);
    c.form.montant_reliquat = 40000;

    // La famille donne 35 000 de scolarité + 40 000 d'ardoise.
    c.montantVerse = 75000;

    expect(c.form.montant_mensualite).toBe(35000);
    expect(c.form.montant_reliquat).toBe(40000);
    // Le reste dû du mois ignore les 40 000 : ils règlent une autre dette.
    expect(c.resteApresVersement()).toBe(30000);
  });

  it("« divers » n'entame pas le dû de l'échéance", () => {
    charger(donnees());
    c.form.montant_divers = 5000;

    c.montantVerse = 40000;

    expect(c.form.montant_mensualite).toBe(35000);
    expect(c.resteApresVersement()).toBe(30000);
  });

  // ── Reliquat des frais d'entrée réclamé avec la mensualité ────────────
  // Il a d'abord été placé dans `montant_inscription`, champ que le mode
  // MENSUALITÉ n'affiche pas : le total dépassait la somme des lignes visibles
  // et le caissier ne pouvait ni le comprendre ni le corriger. Invisible chez
  // une école dont les inscriptions sont soldées, faux chez l'autre — d'où un
  // bug qui « marche pour une école, pas pour l'autre ».

  /** Ce que l'écran DONNE À VOIR et à corriger en mode mensualité. */
  const lignesVisibles = (c: PaiementsComponent) =>
    c.form.montant_mensualite
    + c.form.montant_divers
    + (c.reliquatEntree() > 0 ? c.form.montant_inscription : 0)
    + c.form.services.filter(s => s.inclus).reduce((t, s) => t + s.montant, 0);

  const avecReliquat = () => {
    const d = donnees();
    d.arrieres = { entree: { libelle: 'Inscription', reste: 85000 }, mois: [], total: 85000 };
    return d;
  };

  it("réclame le reliquat d'entrée avec la mensualité", () => {
    charger(avecReliquat());

    expect(c.reliquatEntree()).toBe(85000);
    expect(c.form.montant_inscription).toBe(85000);
    expect(c.duSaisie().reste).toBe(65000 + 85000);
  });

  it('le montant versé égale toujours la somme des lignes VISIBLES', () => {
    charger(avecReliquat());

    for (const verse of [0, 40000, 85000, 120000, 150000]) {
      c.montantVerse = verse;
      expect(lignesVisibles(c)).toBe(verse);
    }
  });

  it("sans reliquat, aucun montant ne dort dans un champ masqué", () => {
    charger(donnees());

    c.montantVerse = 35000;

    expect(c.form.montant_inscription).toBe(0);
    expect(lignesVisibles(c)).toBe(35000);
  });

  it("sert l'échéance du mois AVANT le reliquat", () => {
    // Le cas Mamy Daya : 123 000 remis pour « le mois + une part d'arriéré ».
    // Servir l'arriéré en premier écrivait 100 000 dessus et 23 000 sur le
    // mois — l'inverse de ce que le caissier venait de faire, et le mois
    // restait dû.
    charger(avecReliquat());

    c.montantVerse = 65000 + 50000;

    expect(c.form.montant_mensualite).toBe(52000);
    expect(c.form.services.map(s => s.montant)).toEqual([8000, 5000]);
    expect(c.form.montant_inscription).toBe(50000);
  });

  it("l'échéance réglée, le surplus va sur le reliquat", () => {
    charger(avecReliquat());

    c.montantVerse = 65000 + 85000;

    expect(c.form.montant_inscription).toBe(85000);
    expect(c.resteApresVersement()).toBe(0);
  });

  it("un versement inférieur à l'échéance ne touche pas au reliquat", () => {
    charger(avecReliquat());

    c.montantVerse = 40000;

    expect(c.form.montant_inscription).toBe(0);
    expect(c.form.montant_mensualite).toBe(40000);
  });

  it('le reliquat est isolé dans le bloc « dû »', () => {
    charger(avecReliquat());

    expect(c.reliquatSaisie()).toBe(85000);
    expect(c.libelleReliquat()).toBe('Inscription');
  });

  // ── Inscription ───────────────────────────────────────────────────────
  it("décompose aussi l'inscription", () => {
    const d = donnees();
    d.fees_nets.inscription = 60000;
    d.reste.inscription     = 60000;
    d.pec.inscription       = { brut: 100000, pec: 40000, net: 60000 };
    charger(d);

    c.setTypePaiement('INSCRIPTION');

    expect(c.duSaisie()).toEqual(
      { brut: 100000, pec: 40000, net: 60000, verse: 0, reste: 60000 });
    expect(c.form.montant_inscription).toBe(60000);
    expect(c.form.montant_mensualite).toBe(0);
  });

  it('un acompte sur les frais d\'entrée laisse le reste dû', () => {
    charger(donnees());
    c.setTypePaiement('INSCRIPTION');

    c.montantVerse = 30000;

    expect(c.form.montant_inscription).toBe(30000);
    expect(c.resteApresVersement()).toBe(70000);
  });
});
