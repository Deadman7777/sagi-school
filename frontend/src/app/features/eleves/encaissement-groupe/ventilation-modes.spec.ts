import { ventilerSurReglements } from './ventilation-modes';

describe('ventilerSurReglements', () => {
  const parMode = (r: ReturnType<typeof ventilerSurReglements>, totaux: number[]) => {
    const t: Record<string, number> = {};
    r.forEach((x, i) => {
      const lignes = x.modes_reglement.length ? x.modes_reglement : [{ mode: x.mode_paiement, montant: totaux[i] }];
      lignes.forEach(l => t[l.mode] = (t[l.mode] || 0) + l.montant);
    });
    return t;
  };

  it('un seul moyen : chaque règlement en mode simple', () => {
    const r = ventilerSurReglements([25000, 25000], [{ mode: 'WAVE', montant: 50000 }]);
    expect(r).toEqual([{ mode_paiement: 'WAVE', modes_reglement: [] },
                       { mode_paiement: 'WAVE', modes_reglement: [] }]);
  });

  it('remplit dans l\'ordre : seul le règlement à cheval devient multi-mode', () => {
    const totaux = [40000, 35000, 25000];
    const r = ventilerSurReglements(totaux, [{ mode: 'ESPECE', montant: 60000 },
                                             { mode: 'WAVE', montant: 40000 }]);
    expect(r[0]).toEqual({ mode_paiement: 'ESPECE', modes_reglement: [] });
    expect(r[1]).toEqual({ mode_paiement: 'MIXTE', modes_reglement: [
      { mode: 'ESPECE', montant: 20000 }, { mode: 'WAVE', montant: 15000 }] });
    expect(r[2]).toEqual({ mode_paiement: 'WAVE', modes_reglement: [] });
    // Le total par moyen est exactement celui saisi : c'est ce que voient la caisse et Wave.
    expect(parMode(r, totaux)).toEqual({ ESPECE: 60000, WAVE: 40000 });
  });

  it('chaque règlement multi-mode couvre exactement son total', () => {
    const totaux = [10000.5, 7000, 3000];
    const r = ventilerSurReglements(totaux, [{ mode: 'ESPECE', montant: 5000.25 },
                                             { mode: 'WAVE', montant: 5000.25 },
                                             { mode: 'ORANGE_MONEY', montant: 10000 }]);
    r.forEach((x, i) => {
      if (x.modes_reglement.length) {
        expect(x.modes_reglement.reduce((t, m) => t + m.montant, 0)).toBeCloseTo(totaux[i], 2);
      }
    });
  });

  it('refuse une ventilation incomplète ou sans moyen : rien n\'est encaissé', () => {
    expect(() => ventilerSurReglements([25000], [{ mode: 'ESPECE', montant: 20000 }])).toThrow();
    expect(() => ventilerSurReglements([25000], [{ mode: '', montant: 25000 }])).toThrow();
    expect(() => ventilerSurReglements([25000], [{ mode: 'ESPECE', montant: 30000 },
                                                 { mode: 'WAVE', montant: -5000 }])).toThrow();
  });
});
