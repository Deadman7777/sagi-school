// Valeur de repli suivie par git pour que `ng build` (sans le hook prebuild,
// ex. en CI) résolve l'import. Le script scripts/gen-build-id.mjs (prebuild /
// prebuild:cloud) la régénère à chaque build local pour le cache-busting i18n.
export const BUILD_ID = 'v1.11.0';
