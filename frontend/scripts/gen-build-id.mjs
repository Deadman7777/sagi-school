// Génère src/build-id.ts avec un identifiant unique à chaque build.
// Sert au cache-busting des fichiers de traduction (i18n) : l'URL devient
// /assets/i18n/fr.json?v=<BUILD_ID>, ce qui force navigateurs et Cloudflare
// à recharger les traductions après chaque déploiement.
import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const id = Date.now().toString(36);
const out = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'build-id.ts');
writeFileSync(out, `// Généré automatiquement par scripts/gen-build-id.mjs — ne pas éditer.\nexport const BUILD_ID = '${id}';\n`);
console.log('build-id:', id);
