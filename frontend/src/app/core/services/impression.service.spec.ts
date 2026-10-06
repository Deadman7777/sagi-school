import { TestBed } from '@angular/core/testing';
import { ImpressionService } from './impression.service';

describe('ImpressionService', () => {
  afterEach(() => { delete (window as any).electronAPI; });

  it('envoie les reçus 58/80 mm à l\'imprimante à tickets, le reste aux documents', () => {
    expect(ImpressionService.typePourFormat('80mm')).toBe('ticket');
    expect(ImpressionService.typePourFormat('58MM')).toBe('ticket');
    for (const f of ['A4', 'A5', 'A6', 'LETTER', 'LEGAL', '']) {
      expect(ImpressionService.typePourFormat(f)).toBe('document');
    }
  });

  it('produit une page de test PDF dont la table xref pointe sur les objets', async () => {
    const pdf = await ImpressionService.pageDeTest('ticket', 'EPSON TM-T20 (été)').text();
    expect(pdf.startsWith('%PDF-1.4')).toBe(true);
    expect(pdf).toContain('/MediaBox [0 0 227 113]');
    expect(pdf).toContain('(Imprimante : EPSON TM-T20 ete)');
    const xref = Number(pdf.match(/startxref\n(\d+)/)![1]);
    expect(pdf.slice(xref, xref + 4)).toBe('xref');
    const offsets = [...pdf.matchAll(/^(\d{10}) 00000 n $/gm)].map(m => Number(m[1]));
    expect(offsets.length).toBe(5);
    offsets.forEach((o, i) => expect(pdf.slice(o, o + 8)).toBe(`${i + 1} 0 obj\n`));
    const longueur = Number(pdf.match(/\/Length (\d+)/)![1]);
    const debut = pdf.indexOf('>>\nstream\n') + '>>\nstream\n'.length;
    const flux = pdf.slice(debut, pdf.indexOf('\nendstream'));
    expect(flux.length).toBe(longueur);
  });

  it('passe par Electron quand le pont d\'impression existe', async () => {
    const appels: any[] = [];
    (window as any).electronAPI = {
      imprimerPdf: async (_pdf: ArrayBuffer, opts: any) => { appels.push(opts); return { ok: true, imprimante: 'XP-80' }; },
    };
    const svc = TestBed.inject(ImpressionService);
    expect(svc.directPossible).toBe(true);
    const res = await svc.imprimer(new Blob(['%PDF']), 'ticket');
    expect(res).toEqual({ direct: true, imprimante: 'XP-80' });
    expect(appels).toEqual([{ type: 'ticket', imprimante: undefined }]);
  });

  it('remonte l\'erreur de l\'imprimante au lieu de la taire', async () => {
    (window as any).electronAPI = { imprimerPdf: async () => ({ ok: false, erreur: 'Imprimante hors ligne' }) };
    const svc = TestBed.inject(ImpressionService);
    await expect(svc.imprimer(new Blob(['%PDF']))).rejects.toThrow('Imprimante hors ligne');
  });

  it('sans Electron (cloud), pas d\'impression directe', () => {
    (window as any).electronAPI = { getVersion: () => '1.0', isDesktop: true }; // ancienne coquille
    expect(TestBed.inject(ImpressionService).directPossible).toBe(false);
  });
});
