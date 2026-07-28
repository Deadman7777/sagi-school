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
    from .echeancier import construire_echeancier
    from .models import Eleve
    from .parcours import STATUTS_SORTIE

    today = today or datetime.date.today()
    lignes = []
    qs = (Eleve.objects.filter(tenant=tenant, exercice=exercice, fiche_creance=False)
          .exclude(statut__in=STATUTS_SORTIE)
          .select_related('section', 'classe')
          .prefetch_related('abonnements__service'))

    for eleve in qs:
        ech = construire_echeancier(eleve, today=today)
        synth = ech['synthese']
        if synth['total_anterieurs'] < seuil:
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
            'retards':          synth['retards'],
            'impaye_anterieur': synth['impaye_anterieur'],
            'total_exigible':   synth['total_anterieurs'],
        })

    lignes.sort(key=lambda l: l['total_exigible'], reverse=True)
    return {
        'fenetre':        fenetre_rappel(tenant, today),
        'lignes':         lignes,
        'nb':             len(lignes),
        'total_exigible': round(sum(l['total_exigible'] for l in lignes), 2),
    }
