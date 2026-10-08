"""État des services optionnels : qui les prend, ce qu'ils doivent, ce qu'ils
ont payé, et ce que chaque service a fait entrer en caisse.

Demandé à une installation (08/10/2026) : « 10 élèves prennent la cantine, 20
le transport — avec leur classe et le détail de leurs paiements », pour la
traçabilité et la trésorerie (le transport est encaissé par plusieurs
receveurs).

Le dû d'un service vient des MÊMES sources que l'échéancier, le guichet et
les proformas : `Eleve.abonnements_mensuels_du_mois` et le calendrier de
l'élève (`_mois_du_calendrier`, `mois_factures`). Le payé vient des lignes
itemisées des reçus (`Paiement.services_regles`), rapprochées du service par
leur id, ou par leur nom pour les reçus antérieurs à v1.62.0. Les frais
d'adhésion (kimono, droit d'inscription d'une activité) ont leur propre suivi
et ne sont comptés ici ni dans le dû ni dans le payé.
"""
import datetime
from collections import defaultdict

from apps.paiements.models import MODE_CHOICES, Paiement

from .echeancier import NATURES_HORS_MENSUALITE, construire_echeancier, precharger
from .familles import contact_effectif
from .models import Eleve, Service
from .parcours import STATUTS_SORTIE

LIBELLES_MODE = dict(MODE_CHOICES)
MOIS_COURTS = {1: 'Janv', 2: 'Févr', 3: 'Mars', 4: 'Avr', 5: 'Mai', 6: 'Juin',
               7: 'Juil', 8: 'Août', 9: 'Sept', 10: 'Oct', 11: 'Nov', 12: 'Déc'}


def _r(x):
    return round(float(x or 0), 2)


def _service_de_la_ligne(ligne, services, par_nom):
    """L'id du service qu'une ligne de reçu règle, ou None."""
    if ligne.get('nature') == 'ADHESION':
        return None
    sid = str(ligne.get('service') or '')
    if sid in services:
        return sid
    return par_nom.get((ligne.get('nom') or '').strip().lower())


def _parts_par_mode(p, montant):
    """Répartit `montant` (une ligne du reçu) sur les modes du reçu, au
    prorata : un reçu multi-mode n'a pas de mode « MIXTE » en caisse."""
    modes = [m for m in (p.modes_reglement or []) if float(m.get('montant') or 0) > 0]
    total = sum(float(m['montant']) for m in modes)
    if len(modes) <= 1 or total <= 0:
        mode = modes[0]['mode'] if modes else p.mode_paiement
        return {mode: montant}
    return {m['mode']: montant * float(m['montant']) / total for m in modes}


def etat_services(tenant, exercice, service_id=None, section_id=None, classe_id=None,
                  du=None, au=None, today=None):
    """{'services': [...], 'total': {...}} pour l'exercice.

    `du`/`au` bornent la liste des ENCAISSEMENTS (trésorerie d'une période) ;
    le dû, le payé et le reste de chaque abonné sont, eux, ceux de l'année à
    la date du jour.
    """
    today = today or datetime.date.today()
    services = {str(s.id): s for s in Service.objects.filter(tenant=tenant).order_by('nom')}
    par_nom = {s.nom.strip().lower(): sid for sid, s in services.items()}
    retenus = [sid for sid, s in services.items()
               if (not service_id or sid == str(service_id))]

    # ── Encaissements : toutes les lignes de service des reçus actifs ─────
    paye = defaultdict(float)                     # (eleve_id, sid) -> payé
    dernier = {}                                  # (eleve_id, sid) -> dernier règlement
    encaissements = defaultdict(list)             # sid -> lignes
    regles = (Paiement.objects.filter(tenant=tenant, exercice=exercice, statut='ACTIF')
              .exclude(services_regles=[])
              .select_related('eleve', 'eleve__section', 'eleve__classe', 'receveur', 'saisi_par')
              .order_by('date_paiement', 'no_piece'))
    for p in regles:
        for ligne in p.services_regles or []:
            sid = _service_de_la_ligne(ligne, services, par_nom)
            if sid is None or sid not in retenus:
                continue
            montant = float(ligne.get('montant') or 0)
            if montant <= 0:
                continue
            cle = (p.eleve_id, sid)
            paye[cle] += montant
            dernier[cle] = {'date': p.date_paiement.isoformat(), 'no_piece': p.no_piece,
                            'date_texte': p.date_paiement.strftime('%d/%m/%Y'),
                            'montant': _r(montant)}
            if (du and p.date_paiement < du) or (au and p.date_paiement > au):
                continue
            e = p.eleve
            encaissements[sid].append({
                'date':      p.date_paiement.isoformat(),
                'date_texte': p.date_paiement.strftime('%d/%m/%Y'),
                'no_piece':  p.no_piece,
                'eleve':     e.nom_complet,
                'classe':    e.classe.nom if e.classe_id else (e.section.nom if e.section_id else ''),
                'montant':   _r(montant),
                'mois':      ', '.join(MOIS_COURTS.get(int(m), str(m)) for m in (p.mois_regles or [])),
                'mode':      LIBELLES_MODE.get(p.mode_paiement, p.mode_paiement),
                'parts_mode': _parts_par_mode(p, montant),
                # Qui a l'argent : le receveur s'il est nommé, sinon la
                # personne qui a saisi le reçu.
                'receveur':  (p.receveur.nom if p.receveur_id
                              else (getattr(p.saisi_par, 'nom', '') or 'Non renseigné')),
            })

    # ── Abonnés présents ─────────────────────────────────────────────────
    eleves = (Eleve.objects.filter(tenant=tenant, exercice=exercice, fiche_creance=False,
                                   abonnements__service_id__in=retenus)
              .exclude(statut__in=STATUTS_SORTIE).distinct()
              .select_related('section', 'classe', 'famille')
              .prefetch_related('famille__responsables', 'abonnements__service'))
    if section_id:
        eleves = eleves.filter(section_id=section_id)
    if classe_id:
        eleves = eleves.filter(classe_id=classe_id)
    abonnes = defaultdict(list)
    for e in precharger(eleves):
        ech = construire_echeancier(e, today=today)
        echus = {l['mois'] for l in ech['lignes'] if l.get('echu')}
        factures = [l['mois'] for l in ech['lignes']]
        contact = contact_effectif(e)
        for ab in e.abonnements.all():
            sid = str(ab.service_id)
            if sid not in retenus:
                continue
            s = ab.service
            if s.periodicite == 'MENSUEL':
                mois = [m for m in factures
                        if e._mois_du_calendrier(m) and ab in e.abonnements_mensuels_du_mois(m)]
                du_annee = ab.prix * len(mois)
                du_echu = ab.prix * sum(1 for m in mois if m in echus)
            else:
                mois = [s.mois_unique] if s.mois_unique else []
                du_annee = ab.prix
                # Unique « à l'inscription » : dû dès l'entrée ; « mois X » :
                # dû quand ce mois est échu.
                du_echu = ab.prix if (not s.mois_unique or s.mois_unique in echus) else 0.0
            p = paye.get((e.id, sid), 0.0)
            reste = max(du_echu - p, 0.0)
            abonnes[sid].append({
                'id':          str(e.id),
                'matricule':   e.matricule or '',
                'nom_complet': e.nom_complet,
                'section':     e.section.nom if e.section_id else '',
                'classe':      e.classe.nom if e.classe_id else '',
                'contact':     contact.get('nom') or '',
                'telephone':   contact.get('telephone') or '',
                'tarif':       _r(ab.prix),
                # Tout le calendrier de l'élève : une ligne courte, pas neuf mois.
                'mois':        ("Toute l'année" if s.periodicite == 'MENSUEL' and mois
                                and len(mois) == len([m for m in factures if e._mois_du_calendrier(m)])
                                else ', '.join(MOIS_COURTS.get(m, str(m)) for m in mois)),
                'nb_mois':     len(mois),
                'du_annee':    _r(du_annee),
                'du_echu':     _r(du_echu),
                'paye':        _r(p),
                'reste_echu':  _r(reste),
                'avance':      _r(max(p - du_echu, 0.0)),
                'statut':      'A_JOUR' if reste < 0.5 else ('PARTIEL' if p > 0 else 'IMPAYE'),
                'dernier':     dernier.get((e.id, sid)),
            })

    resultat = []
    for sid in retenus:
        s = services[sid]
        liste = sorted(abonnes.get(sid, []), key=lambda a: (a['classe'] or a['section'], a['nom_complet']))
        if not liste and not encaissements.get(sid) and not s.actif:
            continue
        lignes = encaissements.get(sid, [])
        par_mode, par_receveur = defaultdict(float), defaultdict(float)
        for l in lignes:
            for mode, montant in l.pop('parts_mode').items():
                par_mode[mode] += montant
            par_receveur[l['receveur']] += l['montant']
        resultat.append({
            'id':           sid,
            'nom':          s.nom,
            'periodicite':  s.periodicite,
            'tarif':        _r(s.montant),
            'actif':        s.actif,
            'nb_abonnes':   len(liste),
            'nb_a_jour':    sum(1 for a in liste if a['statut'] == 'A_JOUR'),
            'nb_en_retard': sum(1 for a in liste if a['statut'] != 'A_JOUR'),
            'du_annee':     _r(sum(a['du_annee'] for a in liste)),
            'du_echu':      _r(sum(a['du_echu'] for a in liste)),
            'paye':         _r(sum(a['paye'] for a in liste)),
            'reste_echu':   _r(sum(a['reste_echu'] for a in liste)),
            'abonnes':      liste,
            'encaisse':     _r(sum(l['montant'] for l in lignes)),
            'par_mode':     [{'mode': LIBELLES_MODE.get(m, m), 'montant': _r(v)}
                             for m, v in sorted(par_mode.items(), key=lambda x: -x[1])],
            'par_receveur': [{'nom': n, 'montant': _r(v)}
                             for n, v in sorted(par_receveur.items(), key=lambda x: -x[1])],
            'encaissements': list(reversed(lignes)),
        })

    cles = ('nb_abonnes', 'nb_a_jour', 'nb_en_retard', 'du_annee', 'du_echu', 'paye',
            'reste_echu', 'encaisse')
    return {
        'exercice': exercice.annee_scolaire,
        'date':     today.isoformat(),
        'du':       du.isoformat() if du else None,
        'au':       au.isoformat() if au else None,
        'services': resultat,
        'total':    {k: _r(sum(s[k] for s in resultat)) if k not in ('nb_abonnes', 'nb_a_jour', 'nb_en_retard')
                     else sum(s[k] for s in resultat) for k in cles},
    }
