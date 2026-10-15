"""Relance automatique des licences qui arrivent à échéance.

**Quatre paliers : J-7, J-3, J-1 et J0** (choix de la direction, 14/10/2026).
Un message à chaque palier, jamais deux fois le même pour une même échéance
(`RelanceLicence`, clé licence + date de fin + palier). Si la tâche planifiée
n'a pas tourné un jour, on n'envoie pas trois messages d'un coup : seul le
palier COURANT part (à J-2, celui de J-3 ; celui de J-7 est passé).

**Après un renouvellement**, la date de fin change : la clé change avec elle et
un nouveau cycle recommence de lui-même, sans rien remettre à zéro.

**Le courriel** part à l'adresse de l'école et à celles de ses administrateurs
actifs. Une école sans adresse est signalée dans l'écran Licences, où le
bouton WhatsApp ouvre le même message déjà rédigé.

Lancée chaque jour sur le cloud par `manage.py relancer_licences` (cron).
Coupée depuis l'écran Facturation (`ParametresFacturation.relances_auto`).
"""
from datetime import timedelta

from django.utils import timezone

from apps.licences import catalogue
from apps.prospects.messagerie import (EnvoiErreur, envoyer_courriel, lien_whatsapp,
                                       pieces_bibliotheque, signature_editeur)

from .models import Licence, RelanceLicence

PALIERS = RelanceLicence.PALIERS          # (7, 3, 1, 0)
FENETRE = max(PALIERS)


def palier_courant(jours):
    """Le palier dont relève une licence à `jours` de son échéance, ou None.

    7 → 7 ; 5 → 7 ; 3 → 3 ; 2 → 3 ; 1 → 1 ; 0 → 0 ; 8 ou -1 → None.
    """
    if jours is None or jours < 0 or jours > FENETRE:
        return None
    return min(p for p in PALIERS if p >= jours)


def _jours(licence, aujourdhui):
    return (licence.date_fin - aujourdhui).days


def destinataires(licence):
    """L'adresse de la fiche de l'école ; à défaut, celles de ses administrateurs actifs.

    Les identifiants de connexion des administrateurs sont souvent inventés
    (admin@ecole.sn) : on ne les sollicite que si la fiche n'a pas d'e-mail.
    """
    from apps.users.models import User
    if licence.tenant.email:
        return [licence.tenant.email]
    adresses = User.objects.filter(tenant=licence.tenant, actif=True, role='ADMIN_ECOLE') \
        .exclude(email='').values_list('email', flat=True)
    vues, liste = set(), []
    for a in adresses:
        if a and a.lower() not in vues:
            vues.add(a.lower())
            liste.append(a)
    return liste


def _quand(jours):
    if jours <= 0:
        return "expire aujourd'hui"
    if jours == 1:
        return 'expire demain'
    return f'expire dans {jours} jours'


def composer(licence, aujourdhui=None):
    """(sujet, corps, texte WhatsApp) personnalisés pour cette école."""
    from apps.prospects.models import ParametresFacturation
    from apps.prospects.proposition import date_longue, francs, libelle_licence

    aujourdhui = aujourdhui or timezone.localdate()
    jours = max(_jours(licence, aujourdhui), 0)
    params = ParametresFacturation.actuels()
    tenant = licence.tenant
    nom = (tenant.signataire or {}).get('nom') or ''
    appel = f"Bonjour {nom}," if nom else "Madame, Monsieur,"
    essai = licence.type == 'ESSAI'
    fin = date_longue(licence.date_fin)
    coupure = date_longue(licence.date_fin + timedelta(days=Licence.GRACE_JOURS))
    contacts = ' · '.join(x for x in (params.telephone, params.email) if x)

    if essai:
        sujet = f"Votre essai SAGI SCHOOL {_quand(jours)} — {tenant.nom}"
        offre = ["Pour continuer sans interruption, choisissez la licence adaptée à votre "
                 "établissement :"]
        for code, _ in Licence.TYPE_CHOICES:
            prix = catalogue.tarif_mensuel(code)
            if prix:
                offre.append(f"  - {libelle_licence(code)} : {francs(prix)} FCFA / mois")
        offre.append("Vos données saisies pendant l'essai sont conservées.")
        intro = (f"La période d'essai de SAGI SCHOOL pour {tenant.nom} {_quand(jours)} "
                 f"(fin le {fin}).")
    else:
        sujet = f"Votre licence SAGI SCHOOL {_quand(jours)} — {tenant.nom}"
        ch = catalogue.formules(catalogue.tarif_mensuel(licence.type),
                                catalogue.remise_semestrielle(), catalogue.remise_annuelle(), 0, 0)
        offre = [f"Renouvellement de la licence {libelle_licence(licence.type)} :",
                 f"  - 1 mois : {francs(ch['mensuelle']['net'])} FCFA",
                 f"  - 6 mois : {francs(ch['semestrielle']['net'])} FCFA "
                 f"(remise de {ch['taux_semestriel'] * 100:g} %)",
                 f"  - 12 mois : {francs(ch['annuelle']['net'])} FCFA "
                 f"(remise de {ch['taux_annuel'] * 100:g} %)"]
        intro = (f"La licence {libelle_licence(licence.type)} de SAGI SCHOOL pour {tenant.nom} "
                 f"{_quand(jours)} (fin le {fin}).")

    corps = '\n'.join([
        appel, '',
        intro,
        f"Sans renouvellement, l'accès aux modules sera limité à « Ma licence » et "
        f"« Paramètres » à partir du {coupure}.", '',
        *offre, '',
        "Pour renouveler : depuis SAGI SCHOOL, menu « Ma licence » → « Demander le "
        "renouvellement », ou répondez simplement à ce message.",
        "Moyens de paiement : " + ', '.join(catalogue.MOYENS_PAIEMENT) + '.',
        *([f"Coordonnées de paiement :\n{params.coordonnees_paiement}"]
          if params.coordonnees_paiement else []),
        '', f"Nous restons à votre disposition{' : ' + contacts if contacts else ''}.", '',
        'Cordialement,', '', signature_editeur(params),
    ])
    whatsapp = (f"{appel.rstrip(',')}, ici HADY GESMAN. {intro} Sans renouvellement, l'accès "
                f"sera limité à partir du {coupure}. Souhaitez-vous que nous procédions au "
                f"renouvellement ?")
    return sujet, corps, whatsapp


def whatsapp(licence, aujourdhui=None):
    return lien_whatsapp(licence.tenant.telephone, composer(licence, aujourdhui)[2])


def relancer(licence, aujourdhui=None, auteur='', simuler=False):
    """Envoie la relance du palier courant et la trace. Rend la RelanceLicence."""
    from apps.prospects.models import DocumentBibliotheque, ParametresFacturation

    aujourdhui = aujourdhui or timezone.localdate()
    jours = _jours(licence, aujourdhui)
    palier = palier_courant(jours)
    if palier is None:
        palier = 0 if jours < 0 else FENETRE
    sujet, corps, _ = composer(licence, aujourdhui)
    adresses = destinataires(licence)
    relance = RelanceLicence(licence=licence, date_fin=licence.date_fin, palier=palier,
                             destinataires=', '.join(adresses)[:500], sujet=sujet[:250],
                             message=corps, declenchee_par=auteur, simulee=simuler)
    if simuler:
        relance.succes = True
    else:
        # Fin d'essai : on joint le catalogue et les brochures, pour choisir.
        pieces = []
        if licence.type == 'ESSAI':
            pieces = pieces_bibliotheque(DocumentBibliotheque.objects.filter(
                actif=True, joindre_par_defaut=True))
        try:
            envoyer_courriel(sujet, corps, adresses, pieces,
                             reply_to=ParametresFacturation.actuels().email or None)
            relance.succes = True
        except EnvoiErreur as exc:
            relance.erreur = str(exc)[:1000]
    relance.save()
    return relance


def deja_relancee(licence, palier):
    return RelanceLicence.objects.filter(licence=licence, date_fin=licence.date_fin,
                                         palier=palier, succes=True, simulee=False).exists()


def licences_concernees(aujourdhui=None, depuis=0):
    """Licences dont l'échéance tombe dans [aujourd'hui + depuis, aujourd'hui + 7]."""
    aujourdhui = aujourdhui or timezone.localdate()
    return (Licence.objects.exclude(statut='SUSPENDUE')
            .filter(date_fin__gte=aujourdhui + timedelta(days=depuis),
                    date_fin__lte=aujourdhui + timedelta(days=FENETRE))
            .select_related('tenant').order_by('date_fin'))


def executer(aujourdhui=None, simuler=False):
    """La tâche quotidienne. Rend un rapport {envoyees, echecs, deja, motif}."""
    from apps.prospects.models import ParametresFacturation

    rapport = {'envoyees': [], 'echecs': [], 'deja': 0, 'motif': ''}
    if not ParametresFacturation.actuels().relances_auto and not simuler:
        rapport['motif'] = "Relances automatiques désactivées (écran Facturation)."
        return rapport
    aujourdhui = aujourdhui or timezone.localdate()
    for licence in licences_concernees(aujourdhui):
        palier = palier_courant(_jours(licence, aujourdhui))
        if palier is None:
            continue
        if deja_relancee(licence, palier):
            rapport['deja'] += 1
            continue
        r = relancer(licence, aujourdhui, simuler=simuler)
        (rapport['envoyees'] if r.succes else rapport['echecs']).append(
            f"{licence.tenant.nom} (J-{palier})" + ('' if r.succes else f" : {r.erreur}"))
    return rapport


def tableau(aujourdhui=None):
    """Pour l'écran Licences : les échéances proches (et les expirées en sursis)."""
    aujourdhui = aujourdhui or timezone.localdate()
    lignes = []
    for licence in licences_concernees(aujourdhui, depuis=-Licence.GRACE_JOURS):
        jours = _jours(licence, aujourdhui)
        envoyes = list(RelanceLicence.objects.filter(
            licence=licence, date_fin=licence.date_fin).order_by('-created_at')[:10])
        palier = palier_courant(jours)
        lignes.append({
            'licence': str(licence.id), 'ecole': licence.tenant.nom,
            'type': licence.type, 'date_fin': licence.date_fin, 'jours': jours,
            'palier': palier,
            'a_envoyer': palier is not None and not deja_relancee(licence, palier),
            'destinataires': destinataires(licence),
            'telephone': licence.tenant.telephone or '',
            'whatsapp': whatsapp(licence, aujourdhui),
            'relances': [{'palier': r.palier, 'le': r.created_at, 'succes': r.succes,
                          'simulee': r.simulee, 'erreur': r.erreur,
                          'destinataires': r.destinataires,
                          'par': r.declenchee_par or 'Automatique'} for r in envoyes],
        })
    return lignes
