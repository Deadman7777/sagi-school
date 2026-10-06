import { Injectable } from '@angular/core';

/** Imprimante vue par le poste (Electron). */
export interface Imprimante { nom: string; libelle: string; parDefaut: boolean; }

/** Imprimantes retenues pour ce poste : une pour les documents, une pour les tickets. */
export interface ReglagesImpression { document: string; ticket: string; }

/** Résultat d'une impression : `direct` = partie à l'imprimante sans fenêtre. */
export interface ResultatImpression { direct: boolean; imprimante?: string; }

export type TypeImpression = 'document' | 'ticket';

/** Formats d'un reçu (élève ou famille), tels que le serveur les accepte (?taille=). */
export const FORMATS_RECU = [
  { label: 'A5 (demi-A4)',      value: 'A5' },
  { label: 'A4 (page entière)', value: 'A4' },
  { label: 'A6 (quart de A4)',  value: 'A6' },
  { label: 'Letter (US)',       value: 'LETTER' },
  { label: 'Legal (US)',        value: 'LEGAL' },
  { label: '80 mm (thermique)', value: '80mm' },
  { label: '58 mm (thermique)', value: '58mm' },
];

/** Pont exposé par electron/preload.js (absent en cloud). */
interface PontElectron {
  listerImprimantes(): Promise<Imprimante[]>;
  reglagesImpression(): Promise<ReglagesImpression>;
  enregistrerImpression(r: ReglagesImpression): Promise<ReglagesImpression>;
  imprimerPdf(pdf: ArrayBuffer, opts: { type: TypeImpression; imprimante?: string; copies?: number })
    : Promise<{ ok: boolean; imprimante?: string; erreur?: string }>;
}

/**
 * Point unique d'impression des PDF de l'application.
 *
 * - App locale (Electron) : le PDF part directement à l'imprimante réglée pour
 *   le poste (Paramètres › Imprimantes), sans fenêtre ni téléchargement.
 * - Cloud (navigateur) : un site ne peut pas choisir l'imprimante ; on ouvre
 *   la fenêtre d'impression du navigateur sur le PDF, sans le télécharger.
 *
 * On teste la présence de `imprimerPdf` plutôt que le mode de build : une
 * ancienne coquille Electron (sans impression) retombe sur le navigateur.
 */
@Injectable({ providedIn: 'root' })
export class ImpressionService {

  private get pont(): PontElectron | null {
    const api = (window as any).electronAPI;
    return api && typeof api.imprimerPdf === 'function' ? api as PontElectron : null;
  }

  /** Vrai si le poste sait imprimer sans fenêtre (et lister ses imprimantes). */
  get directPossible(): boolean { return this.pont !== null; }

  /** Les formats de reçu 58/80 mm vont sur l'imprimante à tickets. */
  static typePourFormat(format: string): TypeImpression {
    return /^(58|80)mm$/i.test(format || '') ? 'ticket' : 'document';
  }

  async listerImprimantes(): Promise<Imprimante[]> {
    return this.pont ? this.pont.listerImprimantes() : [];
  }

  async reglages(): Promise<ReglagesImpression> {
    return this.pont ? this.pont.reglagesImpression() : { document: '', ticket: '' };
  }

  async enregistrerReglages(r: ReglagesImpression): Promise<ReglagesImpression> {
    if (!this.pont) throw new Error('Réglage des imprimantes disponible uniquement dans l\'application installée.');
    return this.pont.enregistrerImpression(r);
  }

  /**
   * Imprime un PDF. `imprimante` force une imprimante précise (sinon celle
   * réglée pour le type). Lève une erreur si l'impression échoue.
   */
  async imprimer(pdf: Blob, type: TypeImpression = 'document', imprimante?: string): Promise<ResultatImpression> {
    const pont = this.pont;
    if (pont) {
      const res = await pont.imprimerPdf(await pdf.arrayBuffer(), { type, imprimante });
      if (!res.ok) throw new Error(res.erreur || 'Impression impossible.');
      return { direct: true, imprimante: res.imprimante };
    }
    await this.imprimerViaNavigateur(pdf);
    return { direct: false };
  }

  /**
   * PDF minimal d'une page « SAGI SCHOOL — page de test », sans appel serveur :
   * A4 pour les documents, largeur 80 mm pour les tickets.
   */
  static pageDeTest(type: TypeImpression, imprimante: string): Blob {
    const [l, h] = type === 'ticket' ? [227, 113] : [595, 842];
    const y = h - 40;
    // Helvetica en WinAnsi : on retire accents et caractères hors ASCII.
    const ascii = (t: string) => t.normalize('NFD').replace(/[^\x20-\x7e]/g, '').replace(/[()\\]/g, '');
    const lignes = ['SAGI SCHOOL - page de test', `Imprimante : ${imprimante}`, new Date().toLocaleString('fr-FR')];
    const flux = 'BT /F1 10 Tf 12 ' + y + ' Td 14 TL '
      + lignes.map(t => `(${ascii(t)}) '`).join(' ') + ' ET';
    const objets = [
      '<< /Type /Catalog /Pages 2 0 R >>',
      '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${l} ${h}] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>`,
      `<< /Length ${flux.length} >>\nstream\n${flux}\nendstream`,
      '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>',
    ];
    let pdf = '%PDF-1.4\n';
    const positions: number[] = [];
    objets.forEach((o, i) => { positions.push(pdf.length); pdf += `${i + 1} 0 obj\n${o}\nendobj\n`; });
    const xref = pdf.length;
    pdf += `xref\n0 ${objets.length + 1}\n0000000000 65535 f \n`
         + positions.map(p => String(p).padStart(10, '0') + ' 00000 n \n').join('')
         + `trailer\n<< /Size ${objets.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
    return new Blob([pdf], { type: 'application/pdf' });
  }

  /** Cadre invisible + print() : la fenêtre d'impression s'ouvre sur le PDF. */
  private imprimerViaNavigateur(pdf: Blob): Promise<void> {
    const url = URL.createObjectURL(pdf.type === 'application/pdf' ? pdf : new Blob([pdf], { type: 'application/pdf' }));
    const cadre = document.createElement('iframe');
    cadre.style.cssText = 'position:fixed;right:0;bottom:0;width:0;height:0;border:0;visibility:hidden';
    cadre.src = url;
    // Le cadre doit vivre pendant que la fenêtre d'impression est ouverte :
    // on le retire bien plus tard.
    const nettoyer = () => { cadre.remove(); URL.revokeObjectURL(url); };
    return new Promise<void>(resolve => {
      cadre.onload = () => {
        try {
          cadre.contentWindow?.focus();
          cadre.contentWindow?.print();
        } catch {
          // Navigateur qui refuse d'imprimer un PDF en cadre (Firefox, Safari) :
          // on l'ouvre dans un onglet, l'utilisateur imprime avec Ctrl+P.
          window.open(url, '_blank');
        }
        setTimeout(nettoyer, 60_000);
        resolve();
      };
      document.body.appendChild(cadre);
    });
  }
}
