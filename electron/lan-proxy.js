/**
 * Répartiteur multi-processus pour le mode réseau (multiposte).
 *
 * POURQUOI CE FICHIER EXISTE
 * --------------------------
 * Django est servi par waitress, qui est multi-thread mais MONO-PROCESSUS.
 * Or chaque écran lourd de SAGI SCHOOL coûte 1 à 2 secondes de calcul Python
 * pur — le dû, les alertes et les totaux de chaque fiche sont recomposés à
 * l'affichage, jamais stockés. Le GIL de Python sérialise ces calculs : les
 * threads de waitress attendent les uns derrière les autres.
 *
 * Mesuré sur 1 400 apprenants et 9 516 règlements, 15 postes faisant une
 * action toutes les 5 secondes :
 *
 *     1 processus  ·  médiane 6,3 s  ·  90e centile 29,3 s
 *     4 processus  ·  médiane 0,7 s  ·  90e centile  4,8 s
 *
 * Changer de base n'y fait rien (PostgreSQL est même ressorti pire au 90e
 * centile) : le goulot est le processeur, pas le stockage. Seule la
 * répartition sur plusieurs processus le lève.
 *
 * COMMENT
 * -------
 * On lance N processus waitress sur des ports internes, en écoute sur la
 * seule boucle locale — ils ne sont JAMAIS exposés au réseau. Devant eux, ce
 * répartiteur écoute le port public et distribue les requêtes à tour de rôle.
 *
 *     poste du réseau ──▶ :8765 (répartiteur) ──┬──▶ 127.0.0.1:8771 waitress
 *                                               ├──▶ 127.0.0.1:8772 waitress
 *                                               ├──▶ 127.0.0.1:8773 waitress
 *                                               └──▶ 127.0.0.1:8774 waitress
 *
 * Le corps des requêtes et des réponses est acheminé en flux, sans mise en
 * mémoire : un export PDF de plusieurs méga-octets traverse sans gonfler la
 * consommation du répartiteur.
 */
const http = require('http');
const os = require('os');

/** Port interne du n-ième processus de travail. */
function portInterne(portPublic, index) {
  return portPublic + 6 + index;   // 8765 → 8771, 8772, …
}

/**
 * Combien de processus lancer.
 *
 * Un processus par cœur moins un (on laisse de quoi respirer à PostgreSQL et
 * à l'interface), borné entre 2 et 4. Au-delà de 4, la mémoire consommée —
 * chaque processus porte sa propre copie de Django — coûte plus que le gain.
 */
function nombreDeProcessus() {
  const coeurs = os.cpus()?.length || 2;
  return Math.max(2, Math.min(4, coeurs - 1));
}

/**
 * Démarre le répartiteur.
 *
 * @param {object} options
 * @param {number} options.portPublic  port exposé (8765)
 * @param {string} options.hote        '0.0.0.0' en mode réseau, sinon '127.0.0.1'
 * @param {number} options.nbProcessus nombre de processus de travail
 * @param {function} options.log
 * @returns {Promise<import('http').Server>}
 */
function demarrerRepartiteur({ portPublic, hote, nbProcessus, log = console.log }) {
  const cibles = Array.from({ length: nbProcessus },
                            (_, i) => portInterne(portPublic, i));

  // Une connexion gardée ouverte par cible : on évite de rouvrir un socket
  // TCP à chaque clic, ce qui se voit sur un réseau d'école.
  const agent = new http.Agent({ keepAlive: true, maxSockets: 64 });

  let prochain = 0;

  const serveur = http.createServer((req, res) => {
    const port = cibles[prochain];
    prochain = (prochain + 1) % cibles.length;

    const relais = http.request(
      {
        host: '127.0.0.1',
        port,
        method: req.method,
        path: req.url,
        headers: req.headers,
        agent,
      },
      (reponse) => {
        res.writeHead(reponse.statusCode || 502, reponse.headers);
        reponse.pipe(res);
      }
    );

    relais.on('error', (err) => {
      log(`[Répartiteur] processus :${port} injoignable — ${err.message}`);
      if (!res.headersSent) {
        res.writeHead(503, { 'Content-Type': 'application/json; charset=utf-8' });
      }
      res.end(JSON.stringify({
        error: "Le serveur de l'établissement n'a pas répondu. "
             + 'Réessayez dans quelques secondes ; si cela persiste, '
             + 'redémarrez SAGI SCHOOL sur le poste serveur.',
      }));
    });

    // Un client qui abandonne (onglet fermé, F5) ne doit pas laisser une
    // requête en vol côté Django.
    req.on('aborted', () => relais.destroy());

    req.pipe(relais);
  });

  return new Promise((resolve, reject) => {
    serveur.once('error', reject);
    serveur.listen(portPublic, hote, () => {
      log(`[Répartiteur] écoute sur ${hote}:${portPublic} → `
          + `${cibles.length} processus (${cibles.join(', ')})`);
      resolve(serveur);
    });
  });
}

/** Attend qu'un port interne réponde. Rend true dès qu'il est prêt. */
function attendrePort(port, essais = 60) {
  return new Promise((resolve) => {
    let reste = essais;
    const tenter = () => {
      const requete = http.get(
        { host: '127.0.0.1', port, path: '/api/health/', timeout: 2000 },
        (res) => { res.resume(); resolve(true); }
      );
      requete.on('error', () => {
        if (--reste <= 0) return resolve(false);
        setTimeout(tenter, 1000);
      });
      requete.on('timeout', () => requete.destroy());
    };
    tenter();
  });
}

module.exports = { demarrerRepartiteur, portInterne, nombreDeProcessus, attendrePort };
