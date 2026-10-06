import { TestBed } from '@angular/core/testing';
import { MessageService } from 'primeng/api';
import { TranslateModule } from '@ngx-translate/core';
import { of, throwError } from 'rxjs';

import { BoutonImprimerComponent } from './bouton-imprimer.component';
import { ImpressionService } from '../core/services/impression.service';

describe('BoutonImprimerComponent', () => {
  const messages: any[] = [];
  const impressions: any[] = [];
  let echecImprimante = false;

  function creer(pdf: (arg?: any) => any, arg?: unknown, type?: 'ticket') {
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({
      imports: [BoutonImprimerComponent, TranslateModule.forRoot()],
      providers: [
        { provide: MessageService, useValue: { add: (m: any) => messages.push(m) } },
        { provide: ImpressionService, useValue: {
          imprimer: async (blob: Blob, t: string) => {
            if (echecImprimante) throw new Error('Imprimante hors ligne');
            impressions.push({ blob, t });
            return { direct: true, imprimante: 'XP-80' };
          } } },
      ],
    });
    const f = TestBed.createComponent(BoutonImprimerComponent);
    f.componentRef.setInput('pdf', pdf);
    if (arg !== undefined) f.componentRef.setInput('arg', arg);
    if (type) f.componentRef.setInput('type', type);
    f.detectChanges();
    return f;
  }

  beforeEach(() => { messages.length = 0; impressions.length = 0; echecImprimante = false; });

  it('ne demande le PDF qu\'au clic, avec son argument, et imprime', async () => {
    const appels: unknown[] = [];
    const blob = new Blob(['%PDF']);
    const f = creer(r => { appels.push(r); return of(blob); }, { id: 'R1' }, 'ticket');
    f.detectChanges();
    expect(appels).toEqual([]);                    // affichage : aucune requête
    await f.componentInstance.imprimer();
    expect(appels).toEqual([{ id: 'R1' }]);
    expect(impressions).toEqual([{ blob, t: 'ticket' }]);
    expect(messages[0].severity).toBe('success');
    expect(messages[0].detail).toBe('XP-80');
    expect(f.componentInstance.enCours()).toBe(false);
  });

  it('signale un PDF que le serveur n\'a pas pu produire', async () => {
    const f = creer(() => throwError(() => ({ status: 500 })));
    await f.componentInstance.imprimer();
    expect(impressions).toEqual([]);
    expect(messages[0].severity).toBe('error');
    expect(f.componentInstance.enCours()).toBe(false);
  });

  it('signale une imprimante en panne avec son message', async () => {
    echecImprimante = true;
    const f = creer(() => of(new Blob(['%PDF'])));
    await f.componentInstance.imprimer();
    expect(messages[0]).toMatchObject({ severity: 'error', detail: 'Imprimante hors ligne' });
  });
});
