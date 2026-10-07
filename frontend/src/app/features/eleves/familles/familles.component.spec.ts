import { TestBed } from '@angular/core/testing';
import { TranslateModule } from '@ngx-translate/core';
import { of } from 'rxjs';

import { FamillesComponent } from './familles.component';
import { ElevesService } from '../../../core/services/eleves.service';
import { ImpressionService } from '../../../core/services/impression.service';

describe('FamillesComponent — saisie d\'une famille', () => {
  const envois: any[] = [];

  function creer() {
    envois.length = 0;
    TestBed.configureTestingModule({
      imports: [FamillesComponent, TranslateModule.forRoot()],
      providers: [
        { provide: ElevesService, useValue: {
          getFamilles: () => of([]),
          creerFamille: (f: any) => { envois.push(f); return of({ ...f, id: 'f1', fiches_completees: 0 }); },
        } },
        { provide: ImpressionService, useValue: {} },
      ],
    });
    const f = TestBed.createComponent(FamillesComponent);
    f.detectChanges();
    return f;
  }

  it('propose le père et la mère d\'emblée, puis un tuteur', () => {
    const c = creer().componentInstance;
    c.ouvrirDialog();
    expect(c.responsables().map(r => r.lien)).toEqual(['PERE', 'MERE']);
    expect(c.responsables().map(r => r.principal)).toEqual([true, false]);
    c.ajouterResponsable();
    expect(c.responsables()[2].lien).toBe('TUTEUR');
  });

  it('affiche tous les champs du parent, comme sur la fiche élève', async () => {
    const f = creer();
    f.componentInstance.ouvrirDialog();
    f.detectChanges();
    await f.whenStable();
    const ids = [...document.querySelectorAll('.carte-responsable input[id]')].map(e => e.id);
    for (const champ of ['resp-nom-0', 'resp-tel-0', 'resp-tel2-0', 'resp-prof-0', 'resp-res-0', 'resp-mail-0']) {
      expect(ids).toContain(champ);
    }
    expect(document.querySelectorAll('.carte-responsable').length).toBe(2);
    expect(document.getElementById('fam-urg-tel')).not.toBeNull();
  });

  it('envoie les coordonnées complètes et laisse de côté la carte vide', () => {
    const c = creer().componentInstance;
    c.ouvrirDialog();
    c.form.nom = 'Famille DIOP';
    c.form.contact_urgence_telephone = '781112233';
    Object.assign(c.responsables()[1], { nom: 'Fatou FALL', telephone: '770000011',
                                         profession: 'Enseignante', residence: 'Rufisque' });
    c.enregistrer();
    expect(envois.length).toBe(1);
    expect(envois[0].contact_urgence_telephone).toBe('781112233');
    expect(envois[0].responsables).toHaveLength(1);
    expect(envois[0].responsables[0]).toMatchObject({ lien: 'MERE', profession: 'Enseignante',
                                                      residence: 'Rufisque' });
  });
});
