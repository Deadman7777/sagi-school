"""Rappels mensuels de paiement — qui relancer, et quand.

Une école ne relance pas au hasard : elle ouvre une fenêtre dans le mois (« à
partir du 1er, dernier délai le 10 ») et appelle les familles en retard. Le
système ne peut pas décider de ces dates à sa place — un daara qui collecte en
début de mois et un collège qui collecte à terme échu n'ont pas la même
fenêtre. Elles sont donc paramétrées par établissement.

Ce module ne notifie personne : il répond à « qui dois-je appeler
aujourd'hui, et combien me doit-il ». L'envoi effectif reste à l'école, qui
connaît ses familles — un SMS automatique envoyé au mauvais moment fait plus
de dégâts qu'un rappel oublié.
"""
import datetime


def fenetre_rappel(tenant, today=None):
    """État de la fenêtre de relance du mois en cours.

    Rend {actif, jour_debut, jour_limite, ouverte, depassee, jours_restants}.
    `ouverte` = on est dans la période de rappel ; `depassee` = le dernier
    délai est passé, les retards du mois sont désormais fermes.
    """
    today = today or datetime.date.today()
    actif = bool(getattr(tenant, 'rappel_actif', True))
    debut = int(getattr(tenant, 'rappel_jour_debut', 1) or 1)
    limite = int(getattr(tenant, 'rappel_jour_limite', 10) or 10)
    jour = today.day
    return {
        'actif':          actif,
        'jour_debut':     debut,
        'jour_limite':    limite,
        'ouverte':        actif and debut <= jour <= limite,
        'depassee':       actif and jour > limite,
        # Négatif avant l'ouverture (« dans 3 jours »), positif ensuite.
        'jours_restants': limite - jour,
    }


def eleves_a_rappeler(tenant, exercice, today=None, seuil=1.0):
    """Les élèves qui doivent quelque chose d'EXIGIBLE, avec de quoi les joindre.

    On ne relance que sur ce qui est réellement échu au sens du réglage de
    l'école (voir echeancier.date_exigibilite) : réclamer un mois pas encore
    exigible ferait passer l'établissement pour désorganisé auprès des
    familles, et décrédibiliserait les vrais rappels.

    Les sortants sont exclus — on ne relance pas une famille dont l'enfant a
    quitté l'établissement au titre de la scolarité de l'année.
    """
    from .echeancier import construire_echeancier, precharger
    from .models import Eleve
    from .parcours import STATUTS_SORTIE

    today = today or datetime.date.today()
    lignes = []
    qs = precharger(
        Eleve.objects.filter(tenant=tenant, exercice=exercice, fiche_creance=False)
        .exclude(statut__in=STATUTS_SORTIE))

    for eleve in qs:
        ech = construire_echeancier(eleve, today=today)
        synth = ech['synthese']
        # Net de ce que l'organisme n'a pas encore versé : sans cette nuance,
        # la famille d'un boursier reçoit un SMS pour la dette de l'État.
        if synth['total_exigible_famille'] < seuil:
            continue
        retard_mois = [l for l in ech['lignes'] if l['echu'] and l['reste'] > 0]
        lignes.append({
            'eleve_id':    str(eleve.id),
            'matricule':   eleve.matricule or '',
            'nom_complet': eleve.nom_complet,
            'classe':      eleve.classe.nom if eleve.classe_id else (
                           eleve.section.nom if eleve.section else ''),
            # Le tuteur d'abord : c'est lui qu'on appelle quand il est renseigné.
            'contact':     (eleve.telephone_tuteur or eleve.telephone_pere
                            or eleve.telephone_mere or ''),
            'contact_nom': (eleve.nom_tuteur or eleve.nom_pere
                            or eleve.nom_mere or ''),
            'nb_mois_retard':   len(retard_mois),
            'mois_retard':      [l['nom'] for l in retard_mois],
            'retards':          synth['retards_famille'],
            'impaye_anterieur': synth['impaye_anterieur'],
            'total_exigible':   synth['total_exigible_famille'],
        })

    lignes.sort(key=lambda l: l['total_exigible'], reverse=True)
    return {
        'fenetre':        fenetre_rappel(tenant, today),
        'lignes':         lignes,
        'nb':             len(lignes),
        'total_exigible': round(sum(l['total_exigible'] for l in lignes), 2),
    }


# ── Envoi des rappels ─────────────────────────────────────────────────────
MESSAGE_DEFAUT = ("{ecole} : la scolarite de {eleve} presente un solde de "
                  "{montant} FCFA. Merci de regulariser avant le {limite}.")


def composer_message(tenant, ligne, today=None):
    """Texte du rappel, gabarit de l'école ou message par défaut.

    Volontairement sans accents dans le défaut : beaucoup de passerelles SMS
    facturent au segment et un caractère accentué fait basculer le message en
    UCS-2, divisant la longueur utile par deux. Une école qui tient à ses
    accents garde la main via son propre gabarit.
    """
    today = today or datetime.date.today()
    gabarit = (getattr(tenant, 'rappel_message', '') or '').strip() or MESSAGE_DEFAUT
    valeurs = {
        'ecole':   tenant.nom,
        'eleve':   ligne['nom_complet'],
        'montant': f"{ligne['total_exigible']:,.0f}".replace(',', ' '),
        'mois':    f"{today.month:02d}/{today.year}",
        'limite':  f"{int(getattr(tenant, 'rappel_jour_limite', 10) or 10)}",
    }
    try:
        return gabarit.format(**valeurs)
    except (KeyError, IndexError):
        # Un gabarit fautif ne doit pas empêcher le rappel de partir : on
        # retombe sur le défaut plutôt que de planter en pleine campagne.
        return MESSAGE_DEFAUT.format(**valeurs)


def _envoyer_sms(tenant, destinataire, message, timeout=10):
    """Appelle la passerelle de l'école. Rend (succes, detail).

    Transport générique : URL, méthode et gabarit de corps viennent des
    paramètres. Aucun opérateur n'est imposé, et brancher un nouvel
    agrégateur ne demande pas de toucher au code.
    """
    import json as _json
    import urllib.error
    import urllib.request

    url = (getattr(tenant, 'sms_url', '') or '').strip()
    if not url:
        return False, 'Aucune URL de passerelle SMS configurée.'

    gabarit = getattr(tenant, 'sms_gabarit', None) or {}
    corps = {cle: str(val).replace('{destinataire}', destinataire)
                          .replace('{message}', message)
             for cle, val in gabarit.items()}
    entetes = {str(k): str(v) for k, v in (getattr(tenant, 'sms_entetes', None) or {}).items()}
    entetes.setdefault('Content-Type', 'application/json')

    try:
        if (getattr(tenant, 'sms_methode', 'POST') or 'POST').upper() == 'GET':
            from urllib.parse import urlencode
            requete = urllib.request.Request(
                f"{url}{'&' if '?' in url else '?'}{urlencode(corps)}",
                headers=entetes, method='GET')
        else:
            requete = urllib.request.Request(
                url, data=_json.dumps(corps).encode('utf-8'),
                headers=entetes, method='POST')
        with urllib.request.urlopen(requete, timeout=timeout) as reponse:
            return True, f"HTTP {reponse.status}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code} — {exc.read()[:200].decode('utf-8', 'replace')}"
    except Exception as exc:                      # réseau coupé, DNS, timeout…
        return False, f"{type(exc).__name__} : {exc}"


def envoyer_rappels(tenant, exercice, today=None, forcer=False):
    """Envoie le rappel du mois aux familles en retard. Idempotent.

    Trois protections, dans cet ordre — parce qu'un message parti par erreur à
    des centaines de familles ne se rattrape pas :

      1. la fenêtre de rappel doit être ouverte (sauf `forcer`) ;
      2. un élève déjà prévenu ce mois-ci est sauté, quoi qu'il arrive ;
      3. sans `sms_actif` ET sans passerelle configurée, tout est SIMULÉ :
         journalisé, rien n'est émis. C'est le défaut.

    Rend un compte rendu {envoyes, simules, echecs, ignores, lignes}.
    """
    from .models import RappelEnvoye

    today = today or datetime.date.today()
    periode = f"{today.year}-{today.month:02d}"
    fenetre = fenetre_rappel(tenant, today)

    if not forcer and not fenetre['ouverte']:
        return {'envoyes': 0, 'simules': 0, 'echecs': 0, 'ignores': 0,
                'lignes': [], 'fenetre': fenetre,
                'motif': "Hors de la fenêtre de rappel de l'école."}

    reel = bool(getattr(tenant, 'sms_actif', False)) and bool(
        (getattr(tenant, 'sms_url', '') or '').strip())

    deja = set(RappelEnvoye.objects.filter(
        tenant=tenant, periode=periode).values_list('eleve_id', flat=True))

    rapport = {'envoyes': 0, 'simules': 0, 'echecs': 0, 'ignores': 0,
               'lignes': [], 'fenetre': fenetre, 'reel': reel, 'periode': periode}

    for ligne in eleves_a_rappeler(tenant, exercice, today)['lignes']:
        if ligne['eleve_id'] in {str(i) for i in deja}:
            rapport['ignores'] += 1
            continue
        if not ligne['contact']:
            rapport['ignores'] += 1
            rapport['lignes'].append({**ligne, 'statut': 'SANS_CONTACT'})
            continue

        message = composer_message(tenant, ligne, today)
        if reel:
            succes, detail = _envoyer_sms(tenant, ligne['contact'], message)
            statut = 'ENVOYE' if succes else 'ECHEC'
        else:
            statut, detail = 'SIMULE', 'Mode simulation — aucun envoi réel.'

        # L'échec est tracé comme le succès : sans cela, une passerelle en
        # panne ferait retenter le même élève à chaque passage de la journée.
        RappelEnvoye.objects.create(
            tenant=tenant, eleve_id=ligne['eleve_id'], periode=periode,
            canal='SMS', destinataire=ligne['contact'], message=message,
            montant=ligne['total_exigible'], statut=statut, detail=detail[:500])

        rapport['envoyes' if statut == 'ENVOYE' else
                'simules' if statut == 'SIMULE' else 'echecs'] += 1
        rapport['lignes'].append({**ligne, 'statut': statut, 'detail': detail})

    return rapport
