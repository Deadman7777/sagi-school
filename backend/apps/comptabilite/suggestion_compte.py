"""Compte de charge (6xx) déduit du libellé d'une dépense.

Source UNIQUE de la suggestion : le formulaire « Nouvelle charge » l'interroge
à chaque frappe, l'import Excel des charges l'applique ligne par ligne. Il y
avait deux tables de mots-clés (écran et import) qui ne classaient déjà plus
les mêmes libellés au même compte.

Les gestionnaires ne sont pas comptables : « facture SDE », « salaire
gardien », « sac de riz cantine » doivent tomber d'eux-mêmes sur le bon compte.
Un libellé qui n'est pas compris part en 658 « Charges diverses » — jamais
sur un compte arbitraire (le formulaire proposait 661 Salaires par défaut :
une facture d'eau non reconnue devenait une charge de personnel).

L'ORDRE COMPTE : la première règle qui reconnaît le libellé l'emporte. Les
règles précises passent avant les générales — « salaire du gardien » est un
salaire (661) avant d'être du gardiennage (621), « eau minérale » est une
denrée (604) avant d'être la facture d'eau (6051).
"""
import re
import unicodedata

COMPTE_DEFAUT = '658'
LIBELLE_DEFAUT = 'Charges diverses'

# (motif sur le libellé normalisé en minuscules sans accents, compte)
REGLES = [
    # ── Personnel : avant tout le reste (« salaire gardien », « prime tata »)
    (r'\bipres\b|retraite', '662'),
    (r'\bcss\b|securite sociale|cotisations? (sociales?|patronales?)|\batmp\b|accident du travail', '6641'),
    (r'\bcfce\b|contribution forfaitaire', '6413'),
    (r'indemnites?|\bprimes?\b|gratifications?|heures? sup', '663'),
    (r'salaires?|\bpaie\b|appointements?|remunerations?|motivations?|oustaz|ustaz|\btata\b', '661'),
    # ── Banque, finance, impôts
    (r'agios|frais (de )?(tenue de )?compte|frais bancaires?|frais (de )?banque|commissions? bancaires?'
     r'|frais (de )?(retrait|virement|transfert)|frais wave|frais orange money', '631'),
    (r'interets?|emprunts?|\bprets?\b|echeance (de )?credit', '671'),
    (r'timbres? fiscal|enregistrement|droits? d', '645'),
    (r'impots?|taxes?|patente|contribution (fonciere|des patentes)|\bcel\b|vignette|\bdgid\b', '641'),
    # ── Énergie et fluides (avant les denrées : « eau » seule = facture)
    (r'eau minerale|bouteilles? d.?eau|kirene|pack d.?eau', '604'),
    # Produits d'hygiène : « eau de javel » n'est pas la facture d'eau.
    (r'savon|detergent|javel|balais?|serpilli|eponges?|produits? d.?entretien|linge|draps?', '605'),
    (r'electricite|senelec|woyofal|courant|compteur|groupe electrogene', '6052'),
    (r'\beaux?\b|\bsde\b|sen ?.?eau|facture d.?eau|forage', '6051'),
    (r'carburant|essence|gasoil|gazole|\bgaz\b|charbon|bois de chauffe', '605'),
    # ── Loyer et locaux
    (r'loyers?|locations?|\bbail\b|caution (du )?local', '622'),
    (r'entretien|reparations?|maintenance|depannage|plomb(erie|ier)|electricien|peinture|menuis(erie|ier)'
     r'|macon(nerie)?|carrelage|toiture|vidange|climatis|nettoyage|desinfect|debouchage', '624'),
    (r'gardien(nage)?|vigiles?|surveillance|securite|sous.?traitance|prestataire|prestation', '621'),
    (r'assurances?', '625'),
    # ── Alimentation, cantine, internat
    (r'restauration|cantine|repas|dejeuner|diner|gouter|petit.?dejeuner|ravitaillement|intendance'
     r'|denrees?|\briz\b|huile|sucre|\blait\b|\bpain\b|boulangerie|viandes?|poissons?|poulets?'
     r'|legumes?|oignons?|pommes? de terre|condiments?|\bmarche\b|epicerie|boutique|\bcafe\b|\bthe\b', '604'),
    # ── Fournitures et petit matériel
    (r'craies?|cahiers?|stylos?|bics?|crayons?|papier|rames?|marqueurs?|feutres?|ardoises?|registres?'
     r'|fournitures?|photocopies?|impressions?|imprimerie|encre|cartouches?|toner|agrafes?|classeurs?'
     r'|livres?|manuels?|materiel|matelas|nattes?|tapis|moquette|chaises?|tables?|bancs?|ventilateurs?'
     r'|congelateur|frigo|refrigerateur|ustensiles?|marmites?|seaux?|tableaux?', '6054'),
    (r'marchandises?|uniformes?|tenues?|tissus?|blouses?|kimonos?|t.?shirts?', '601'),
    # ── Communication
    (r'telephone|internet|wifi|forfait|credit (telephonique|d.?appel)|\borange\b|\bfree\b|\bexpresso\b'
     r'|sonatel|connexion|\bsms\b|recharge', '628'),
    (r'publicite|flyers?|affiches?|banderoles?|kakemono|sponsor|annonces?|radio|facebook|reseaux sociaux', '627'),
    (r'etudes?|recherches?|documentation|abonnement|journaux|consultant|conseil|expert.?comptable|audit', '626'),
    # ── Transport, missions
    (r'transports?|\bbus\b|\bcars?\b|navette|taxi|clando|tiak|moto|jakarta|deplacements? (des )?eleves'
     r'|demenagement|livraison|fret|peage|rapido', '618'),
    (r'missions?|voyages?|receptions?|hotel|hebergement|restaurant|ceremonie|fete|kermesse'
     r'|deplacements?|per.?diem', '635'),
    (r'formations?|seminaires?|ateliers?|renforcement de capacite', '633'),
    # ── Divers identifiés
    (r'sante|pharmacie|medicaments?|medecin|infirmerie|trousse|\bsoins?\b', '658'),
    (r'dons?|aumones?|sadaqa|zakat|cotisation (association|amicale)', '658'),
]
_REGLES = [(re.compile(motif), compte) for motif, compte in REGLES]


def normaliser(libelle):
    txt = unicodedata.normalize('NFKD', str(libelle or '')).encode('ascii', 'ignore').decode()
    return ' '.join(txt.lower().split()) + ' '


def suggerer(libelle, comptes_disponibles=None):
    """Compte de charge pour ce libellé.

    `comptes_disponibles` : comptes du plan de l'école. Quand le compte précis
    n'y figure pas (6051 absent, 605 présent), on remonte au parent le plus
    proche qui existe ; sinon la règle est ignorée et la suivante tentée.

    Retourne {'compte', 'reconnu', 'mot'} — `mot` est le passage du libellé
    qui a décidé, pour que l'écran puisse dire POURQUOI ce compte.
    """
    texte = normaliser(libelle)
    if texte.strip():
        for motif, compte in _REGLES:
            trouve = motif.search(texte)
            if not trouve:
                continue
            cible = _dans_le_plan(compte, comptes_disponibles)
            if cible:
                return {'compte': cible, 'reconnu': True, 'mot': trouve.group(0).strip()}
    return {'compte': _dans_le_plan(COMPTE_DEFAUT, comptes_disponibles) or COMPTE_DEFAUT,
            'reconnu': False, 'mot': ''}


def _dans_le_plan(compte, comptes_disponibles):
    if comptes_disponibles is None:
        return compte
    for n in range(len(compte), 1, -1):
        if compte[:n] in comptes_disponibles:
            return compte[:n]
    return None
