import { TestBed } from '@angular/core/testing';
import { signal } from '@angular/core';
import { of } from 'rxjs';

import { AuthService } from './auth.service';
import { LicenceCompteurService } from './licence-compteur.service';
import { AlerteLicence, LicencesService } from './licences.service';

/**
 * Alertes de fin de licence : rappel une fois par palier et par connexion,
 * badge sur l'icône, modules rendus sans reconnexion après renouvellement.
 */
describe('LicenceCompteurService', () => {
  const base: AlerteLicence = {
    licence: 'L1', type: 'PRO', statut: 'ACTIVE', date_fin: '2026-10-18',
    date_fin_longue: '18 octobre 2026', date_coupure: '2026-10-26', jours: 1, grace_jours: 7,
    phase: 'ECHEANCE', niveau: 'critique', palier: 1, paliers: [7, 3, 1, 0], alerte: true,
    prioritaire: false, cle_rappel: '2026-10-18:1', badge: 1, titre: 'Votre licence expire demain',
    texte: '', acces_expire: false, modules: ['/dashboard', '/ma-licence', '/parametres'],
    offres: [], paiement: { lien: '', coordonnees: '', moyens: [], telephone: '', email: '' },
    demande_en_attente: null,
  };
  let reponse: AlerteLicence;
  let user: ReturnType<typeof signal<any>>;

  function creer() {
    TestBed.resetTestingModule();
    user = signal<any>({ role: 'ADMIN_ECOLE', modules: ['/ma-licence', '/parametres'] });
    TestBed.configureTestingModule({
      providers: [
        { provide: LicencesService, useValue: { getAlerte: () => of(reponse) } },
        { provide: AuthService, useValue: { currentUser: user, impersonatedTenantId: () => null } },
      ],
    });
    return TestBed.inject(LicenceCompteurService);
  }

  beforeEach(() => {
    sessionStorage.clear();
    localStorage.setItem('refresh_token', 'jeton-de-la-connexion-1');
    reponse = { ...base };
  });

  it('rappel affiché une seule fois par palier et par connexion', () => {
    let s = creer();
    s.charger();
    expect(s.rappelVisible()).toBe(true);
    s.fermerRappel();
    s.charger();
    expect(s.rappelVisible()).toBe(false);

    // Palier suivant (jour J) : le rappel revient.
    reponse = { ...base, jours: 0, palier: 0, cle_rappel: '2026-10-18:0', badge: '!' };
    s.charger();
    expect(s.rappelVisible()).toBe(true);

    // Nouvelle connexion : le rappel revient aussi.
    s.fermerRappel();
    localStorage.setItem('refresh_token', 'jeton-de-la-connexion-2');
    s = creer();
    s.charger();
    expect(s.rappelVisible()).toBe(true);
  });

  it("badge de l'icône : nombre de jours, puis signal, puis effacé", () => {
    const nav: any = navigator;
    nav.setAppBadge = vi.fn();
    nav.clearAppBadge = vi.fn();
    const s = creer();
    s.charger();
    expect(nav.setAppBadge).toHaveBeenLastCalledWith(1);
    reponse = { ...base, badge: '!' };
    s.charger();
    expect(nav.setAppBadge).toHaveBeenLastCalledWith();
    reponse = { ...base, alerte: false, badge: null, phase: 'NORMAL' };
    s.charger();
    expect(nav.clearAppBadge).toHaveBeenCalled();
  });

  it('renouvellement constaté : modules rendus, alertes fermées, message', () => {
    reponse = { ...base, date_fin: '2026-10-10', phase: 'COUPEE', prioritaire: true,
                modules: ['/ma-licence', '/parametres'] };
    const s = creer();
    s.charger();
    s.ouvrirRenouvellement();
    reponse = { ...base, date_fin: '2027-10-18', date_fin_longue: '18 octobre 2027',
                alerte: false, phase: 'NORMAL', badge: null };
    s.charger();
    expect(s.renouvellementVisible()).toBe(false);
    expect(s.renouvellee()).toContain('18 octobre 2027');
    expect(user().modules).toEqual(['/dashboard', '/ma-licence', '/parametres']);
  });
});
