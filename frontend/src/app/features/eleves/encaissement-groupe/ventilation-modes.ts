/** Une ligne de ventilation saisie : tant par tel moyen. */
export interface LigneMode { mode: string; montant: number; }

/** Ce qu'on envoie à l'API paiements pour UN règlement. */
export interface ModeReglement {
  mode_paiement: string;
  modes_reglement: LigneMode[];
}

/**
 * Répartit les moyens de paiement d'un versement de famille sur ses règlements.
 *
 * Un versement de famille devient un règlement par élève (et par groupe de
 * postes) ; l'argent, lui, arrive en bloc : « 100 000 en espèces et 50 000 par
 * Wave ». On remplit les règlements DANS L'ORDRE avec le premier moyen, puis le
 * suivant : chaque règlement reste en un seul moyen, sauf celui qui tombe à
 * cheval sur deux (il devient multi-mode). Le total par moyen sur l'ensemble
 * des règlements est exactement celui saisi — c'est ce que la caisse et le
 * compte Wave verront.
 *
 * Lève une erreur si la ventilation ne couvre pas exactement les règlements.
 */
export function ventilerSurReglements(totaux: number[], modes: LigneMode[]): ModeReglement[] {
  // En centimes : 0,1 + 0,2 ne doit pas laisser 0,0000001 sur un mode.
  const c = (x: number) => Math.round((Number(x) || 0) * 100);
  const restes = modes.map(m => ({ mode: m.mode, reste: c(m.montant) }));
  const sommeModes = restes.reduce((t, m) => t + m.reste, 0);
  const sommeReglements = totaux.reduce((t, x) => t + c(x), 0);
  if (restes.some(m => !m.mode || m.reste <= 0) || sommeModes !== sommeReglements) {
    throw new Error('ventilation');
  }

  let i = 0;
  return totaux.map(total => {
    let aCouvrir = c(total);
    const parts: LigneMode[] = [];
    while (aCouvrir > 0) {
      while (restes[i].reste === 0) i++;
      const pris = Math.min(aCouvrir, restes[i].reste);
      const deja = parts.find(p => p.mode === restes[i].mode);
      if (deja) deja.montant = (Math.round(deja.montant * 100) + pris) / 100;
      else parts.push({ mode: restes[i].mode, montant: pris / 100 });
      restes[i].reste -= pris;
      aCouvrir -= pris;
    }
    if (parts.length <= 1) {
      return { mode_paiement: parts[0]?.mode ?? restes[Math.min(i, restes.length - 1)].mode,
               modes_reglement: [] };
    }
    return { mode_paiement: 'MIXTE', modes_reglement: parts };
  });
}
