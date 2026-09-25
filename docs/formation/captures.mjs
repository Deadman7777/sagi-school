// Captures d'écran du guide de formation SAGI SCHOOL.
//
// Pré-requis : la démonstration tourne (voir README.md du dossier) —
//   backend  : python manage.py runserver 8765 --settings=config.settings.demo
//   frontend : npx ng serve --port 4300   (environment.ts pointe sur 8765)
//
// Usage : node captures.mjs [filtre]
//   sans filtre, toutes les captures ; avec, seulement celles dont le nom
//   contient le filtre (ex. `node captures.mjs eleves`).
//
// Chaque capture est une fonction : elle amène l'écran dans l'état voulu,
// en passant par l'interface ou, quand un clic serait fragile, par l'objet
// Angular du composant (`ng.getComponent`, disponible en mode développement).
import { mkdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import puppeteer from 'puppeteer-core';

const BASE = process.env.SAGI_URL || 'http://localhost:4300';
const CHROME = process.env.CHROME || '/usr/bin/google-chrome';
const SORTIE = new URL('./captures/', import.meta.url).pathname;
const BRUT = new URL('./captures/png/', import.meta.url).pathname;
const filtre = process.argv[2] || '';

mkdirSync(BRUT, { recursive: true });

const pause = (ms) => new Promise((r) => setTimeout(r, ms));

// ─── Aides ──────────────────────────────────────────────────────────────────
let page;

async function aller(route, attente = 1500) {
  await page.goto(BASE + route, { waitUntil: 'networkidle0' });
  await pause(attente);
}

/** Clique le premier élément cliquable dont le texte contient `texte`. */
async function cliquer(texte, selecteur = 'button, [role=tab], a, .tab-btn, label, li, span.p-tab') {
  const ok = await page.evaluate((t, s) => {
    const el = [...document.querySelectorAll(s)]
      .filter((x) => x.offsetParent !== null)
      .find((x) => x.textContent.replace(/\s+/g, ' ').trim().includes(t));
    if (el) { el.click(); return true; }
    return false;
  }, texte, selecteur);
  if (!ok) throw new Error(`Rien à cliquer : « ${texte} »`);
  await pause(1200);
}

/** Exécute `corps` avec le composant Angular de `selecteur` comme `c`. */
async function composant(selecteur, corps, ...args) {
  await page.evaluate((s, src, a) => {
    const c = window.ng.getComponent(document.querySelector(s));
    // eslint-disable-next-line no-new-func
    const r = new Function('c', 'args', src)(c, a);
    window.ng.applyChanges(c);
    return r;
  }, selecteur, corps, args);
  await pause(1500);
}

/** Fait défiler jusqu'à l'élément dont le texte contient `texte`. */
async function defiler(texte, selecteur = 'h2, h3, h4, .fc-title, .card-title, .section-title, div, span', decalage = 80) {
  await page.evaluate((t, s, d) => {
    const el = [...document.querySelectorAll(s)]
      .filter((x) => x.offsetParent !== null && x.children.length < 6)
      .find((x) => x.textContent.replace(/\s+/g, ' ').trim().startsWith(t));
    if (!el) return;
    el.scrollIntoView({ block: 'start' });
    let p = el.parentElement;
    while (p && p.scrollHeight <= p.clientHeight) p = p.parentElement;
    (p || document.scrollingElement).scrollBy(0, -d);
  }, texte, selecteur, decalage);
  await pause(600);
}

async function saisir(selecteur, valeur) {
  await page.click(selecteur, { clickCount: 3 });
  await page.type(selecteur, valeur);
  await pause(900);
}

async function photo(nom) {
  const png = `${BRUT}${nom}.png`;
  await page.screenshot({ path: png });
  // WebP : trois fois plus léger qu'un PNG pour une capture d'interface,
  // et le guide les embarque toutes dans un seul fichier HTML.
  execFileSync('python3', ['-c', `
from PIL import Image
Image.open('${png}').convert('RGB').save('${SORTIE}${nom}.webp', 'WEBP', quality=82, method=6)
`]);
  console.log('  ✓', nom);
}

// ─── Les captures ───────────────────────────────────────────────────────────
// L'ordre suit le guide. Le nom du fichier est celui que cite guide.html.
const CAPTURES = {
  'connexion': async () => {
    await aller('/login', 300);
    await page.evaluate(() => localStorage.clear());
    await aller('/login');
  },
  'tableau-de-bord': async () => { await aller('/dashboard', 2500); },
  'ma-licence': async () => { await aller('/ma-licence'); },

  'param-ecole': async () => { await aller('/parametres'); },
  'param-exercice': async () => { await aller('/parametres'); await cliquer('Exercice', '.tab-btn'); },
  'param-echeances': async () => { await aller('/parametres'); await cliquer('Échéances', '.tab-btn'); },
  'param-services': async () => { await aller('/parametres'); await cliquer('Services', '.tab-btn'); },
  'param-caisses': async () => { await aller('/parametres'); await cliquer('Caisses', '.tab-btn'); },
  'param-fiche': async () => { await aller('/parametres'); await cliquer('Fiche élève', '.tab-btn'); },
  'param-certificat': async () => { await aller('/parametres'); await cliquer('Certificat', '.tab-btn'); },
  'param-utilisateurs': async () => { await aller('/parametres'); await cliquer('Utilisateurs', '.tab-btn'); },
  'param-sauvegarde': async () => { await aller('/parametres'); await cliquer('Sauvegarde', '.tab-btn'); },
  'param-sante': async () => { await aller('/parametres'); await cliquer('Santé', '.tab-btn'); },
  'param-cloture': async () => { await aller('/parametres'); await cliquer('Clôture', '.tab-btn'); },

  'param-sections-cartes': async () => {
    await aller('/parametres'); await cliquer('Sections', '.tab-btn');
    await defiler('Une section par horaire', 'span, p, div', 30);
  },

  'eleves-liste': async () => { await aller('/eleves', 2500); },
  'eleves-nouveau': async () => { await aller('/eleves', 2500); await cliquer('Nouvel Élève'); },
  'eleves-fiche-situation': async () => {
    await aller('/eleves', 2500);
    await composant('app-eleves-liste',
      "c.voirFiche(c.eleves().find(e => e.nom_complet.endsWith('FALL') && e.section_nom !== 'Garderie'))");
    await defiler('Situation financière', 'div, h3, h4, span', 10);
  },
  'eleves-pec': async () => {
    await aller('/eleves', 2500);
    await composant('app-eleves-liste',
      "c.ouvrirPriseEnCharge(c.eleves().find(e => e.prise_en_charge === 'FRATRIE'))");
  },
  'eleves-onglet-pec': async () => { await aller('/eleves', 2500); await cliquer('Prise en charge'); },
  'eleves-organismes': async () => { await aller('/eleves', 2500); await cliquer('Organismes'); },
  'eleves-familles': async () => { await aller('/eleves', 2500); await cliquer('Familles'); },
  'eleves-famille-situation': async () => {
    await aller('/eleves', 2500); await cliquer('Familles');
    await composant('app-familles', "c.ouvrirSituation(c.familles().find(f => f.nom.includes('NDIAYE')))");
  },
  'eleves-famille-encaisser': async () => {
    await aller('/eleves', 2500); await cliquer('Familles');
    await composant('app-familles', "c.ouvrirSituation(c.familles().find(f => f.nom.includes('NDIAYE')))");
    await composant('app-familles', 'c.ouvrirEncaissement()');
    await composant('app-encaissement-groupe', 'c.toutEchu()');
  },
  'eleves-organisme-encaisser': async () => {
    await aller('/eleves', 2500); await cliquer('Organismes');
    await composant('app-eleves-liste', 'c.ouvrirEncaissementOrganisme(c.suiviOrg().lignes[0])');
    await composant('app-encaissement-groupe', 'c.montantVerse = 100000; c.repartir()');
  },
  'tableau-de-bord-modules': async () => {
    await aller('/dashboard', 3500);
    await defiler('🧩', 'h3', 20);
  },
  'eleves-famille-bareme': async () => {
    await aller('/eleves', 2500); await cliquer('Familles');
    await composant('app-familles', 'c.ouvrirBareme()');
  },

  'garderie-appel': async () => {
    await aller('/garderie');
    await composant('app-garderie', "c.changerDate('2026-06-10')");
  },
  'garderie-recap': async () => {
    await aller('/garderie');
    await composant('app-garderie', "c.date.set('2026-06-10'); c.mois.set(6); c.ouvrirRecap()");
  },
  'garderie-soir': async () => {
    await aller('/garderie');
    await composant('app-garderie', "c.date.set('2026-06-09'); c.mois.set(6); c.erreur.set(''); c.onglet.set('soir'); c.chargerSoir(); c.chargerRecap()");
  },

  'paiements-liste': async () => { await aller('/paiements', 2500); },
  'paiements-recherche': async () => {
    await aller('/paiements', 2500);
    await composant('app-paiements', "c.ouvrirDialog(); c.rechercheInput = 'NDIAYE'; c.onRechercheChange('NDIAYE')");
  },
  'paiements-formulaire': async () => {
    await aller('/paiements', 2500);
    await composant('app-paiements', "c.ouvrirDialog(); c.onRechercheChange('Sokhna FALL')");
    await composant('app-paiements', 'c.selectionnerEleve(c.elevesSuggestions()[0])');
  },
  'paiements-charges': async () => { await aller('/paiements', 2500); await cliquer('Charges', '.tab-btn'); },
  'paiements-cahier': async () => { await aller('/paiements', 2500); await cliquer('cahier', '.tab-btn'); },
  'paiements-proformas': async () => { await aller('/paiements', 2500); await cliquer('Proformas', '.tab-btn'); },

  'suivi-evolution': async () => { await aller('/suivi-mensuel', 2500); },
  'suivi-sections': async () => { await aller('/suivi-mensuel', 2500); await cliquer('Par section'); },
  'suivi-creances': async () => { await aller('/suivi-mensuel', 2500); await cliquer('Créances'); },
  'suivi-charges': async () => { await aller('/suivi-mensuel', 2500); await cliquer('Charges & Marge'); },

  'compta-journal': async () => { await aller('/comptabilite', 2500); },
  'compta-grand-livre': async () => { await aller('/comptabilite', 2000); await cliquer('Grand Livre', '.tab-btn'); },
  'compta-balance': async () => { await aller('/comptabilite', 2000); await cliquer('Balance', '.tab-btn'); },
  'compta-bilan': async () => { await aller('/comptabilite', 2000); await cliquer('ETAFI', '.tab-btn'); await pause(1500); },
  'compta-resultat': async () => {
    await aller('/comptabilite', 2000); await cliquer('ETAFI', '.tab-btn');
    await cliquer('Compte de Résultat', '.etafi-btn');
  },
  'compta-budget': async () => { await aller('/comptabilite', 2000); await cliquer('Budget', '.tab-btn'); },
  'compta-investissement': async () => { await aller('/comptabilite', 2000); await cliquer('Investissement', '.tab-btn'); },

  'fiscal-obligations': async () => { await aller('/fiscal', 2500); await cliquer('Obligations'); },
  'fiscal-conseils': async () => { await aller('/fiscal', 2500); await cliquer('Conseils'); },
  'fiscal-declarations': async () => { await aller('/fiscal', 2500); await cliquer('Déclarations sociales'); },

  'rh-employes': async () => { await aller('/rh', 2500); await defiler('👤 Employés', 'button', 20); },
  'rh-bulletins': async () => { await aller('/rh', 2000); await cliquer('Bulletins', '.tab-btn'); await defiler('👤 Employés', 'button', 20); },
  'rh-avances': async () => { await aller('/rh', 2000); await cliquer('Avances', '.tab-btn'); await defiler('👤 Employés', 'button', 20); },
  'rh-parametres': async () => { await aller('/rh', 2000); await cliquer('Paramètres', '.tab-btn'); await defiler('👤 Employés', 'button', 20); },

  'acad-parametrage': async () => { await aller('/academique', 2500); },
  'acad-notes': async () => {
    await aller('/academique', 2000); await cliquer('Saisie Notes', '.tab-btn');
    await composant('app-academique', "c.classeNotes = c.classes().find(k => k.nom === 'CM2').id; c.onClasseNotesChange()");
    await composant('app-academique', "c.matiereNotes = c.matieresNotes().find(m => m.nom === 'Mathématiques').id; c.onMatiereNotesChange()");
    await composant('app-academique', 'c.selectionnerEvaluation(c.evaluations()[0])');
  },
  'acad-resultats': async () => {
    await aller('/academique', 2000); await cliquer('Résultats', '.tab-btn');
    await composant('app-academique', "c.classeResultats = c.classes().find(k => k.nom === 'CM2').id; c.trimestreResultats = 'T1'; c.calculerMoyennes()");
    await pause(2500);
  },
  'acad-analyse': async () => { await aller('/academique', 2000); await cliquer('Analyse', '.tab-btn'); await pause(2000); },
  'acad-historique': async () => { await aller('/academique', 2000); await cliquer('Historique', '.tab-btn'); await pause(2000); },
  'acad-suivi': async () => {
    await aller('/academique', 2000); await cliquer('Suivi pédagogique', '.tab-btn');
    await composant('app-suivi-pedagogique', "c.classeId = c.classes().find(k => k.nom === 'CM2').id; c.onClasseChange()");
    await composant('app-suivi-pedagogique', 'c.eleveId = c.eleves()[2].id; c.charger()');
    await pause(1500);
  },

  'gmrf-tableau': async () => { await aller('/gmrf', 2500); },
  'gmrf-financements': async () => { await aller('/gmrf', 2000); await cliquer('Financements', 'button.tab'); },
  'gmrf-natt': async () => { await aller('/gmrf', 2000); await cliquer('NATT', 'button.tab'); },
  'gmrf-prets': async () => { await aller('/gmrf', 2000); await cliquer('Prêts', 'button.tab'); },

  'gouv-pilotage': async () => { await aller('/gouvernance', 2500); },
  'gouv-projets': async () => { await aller('/gouvernance', 2000); await cliquer('Projets', 'button.tab'); },
  'gouv-ressources': async () => { await aller('/gouvernance', 2000); await cliquer('Ressources', 'button.tab'); },
  'gouv-flux': async () => { await aller('/gouvernance', 2000); await cliquer('Flux internes', 'button.tab'); },
  'gouv-tracabilite': async () => { await aller('/gouvernance', 2000); await cliquer('Traçabilité', 'button.tab'); },
};

// ─── Exécution ──────────────────────────────────────────────────────────────
const navigateur = await puppeteer.launch({ executablePath: CHROME, headless: true,
  args: ['--no-sandbox', '--lang=fr-FR'] });
page = await navigateur.newPage();
await page.setViewport({ width: 1180, height: 738, deviceScaleFactor: 1.5 });

async function connecter() {
  await aller('/login', 500);
  await page.type('input[type=email]', 'directrice@lespalmiers.sn');
  await page.type('p-password input', 'Demo2026!');
  await page.click('p-button button');
  await page.waitForFunction(() => !location.pathname.includes('login'), { timeout: 20000 });
  await pause(1000);
}

const echecs = [];
for (const [nom, preparer] of Object.entries(CAPTURES)) {
  if (filtre && !nom.includes(filtre)) continue;
  try {
    if (nom !== 'connexion' && !(await page.evaluate(() => !!localStorage.getItem('access_token')).catch(() => false))) {
      await connecter();
    }
    await preparer();
    await photo(nom);
  } catch (e) {
    echecs.push(nom);
    console.log('  ✗', nom, '—', e.message);
  }
}
await navigateur.close();
if (echecs.length) { console.log(`\n${echecs.length} capture(s) en échec`); process.exit(1); }
