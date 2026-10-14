"""Le PDF de la proposition commerciale, au modèle HG-IDM-2026.

ReportLab et non xhtml2pdf : le bloc d'acceptation contient de VRAIS champs de
formulaire (boutons radio pour la formule et la migration, champs nom /
fonction / date) que le client remplit dans son lecteur PDF, comme sur la
proposition remise à l'Internat Daroul Mouminati. xhtml2pdf ne sait pas en
produire.

Tout le texte variable est échappé : un « & » ou un « < » dans le nom d'un
établissement casserait la mise en page de ReportLab.
"""
from io import BytesIO
from urllib.parse import quote
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, HRFlowable, Image,
                                KeepTogether, PageBreak, PageTemplate, Paragraph, Spacer,
                                Table, TableStyle)

from apps.licences import catalogue

from .messagerie import decoder_data_uri
from .models import ParametresFacturation
from .proposition import chiffrage, date_longue, francs, libelle_licence

BLEU = colors.HexColor('#15294B')
OR = colors.HexColor('#B98A2E')
GRIS_FOND = colors.HexColor('#EEF1F5')
GRIS_LIBELLE = colors.HexColor('#F2F4F7')
BORDURE = colors.HexColor('#D5DAE3')
TEXTE = colors.HexColor('#1F2937')
DISCRET = colors.HexColor('#6B7280')

LARGEUR_PAGE, HAUTEUR_PAGE = A4
MARGE = 57
LARGEUR = LARGEUR_PAGE - 2 * MARGE

S = {
    'titre': ParagraphStyle('titre', fontName='Helvetica-Bold', fontSize=24, leading=29,
                            textColor=BLEU, spaceAfter=4),
    'sous_titre': ParagraphStyle('sous_titre', fontName='Helvetica', fontSize=13, leading=17,
                                 textColor=OR),
    'petit': ParagraphStyle('petit', fontName='Helvetica', fontSize=8.5, leading=11,
                            textColor=DISCRET),
    'h1': ParagraphStyle('h1', fontName='Helvetica-Bold', fontSize=14, leading=18,
                         textColor=BLEU, spaceBefore=14, spaceAfter=3),
    'h2': ParagraphStyle('h2', fontName='Helvetica-Bold', fontSize=10.5, leading=14,
                         textColor=BLEU, spaceBefore=8, spaceAfter=3),
    'corps': ParagraphStyle('corps', fontName='Helvetica', fontSize=9.2, leading=13.2,
                            textColor=TEXTE, spaceAfter=5),
    'puce': ParagraphStyle('puce', fontName='Helvetica', fontSize=9.2, leading=13,
                           textColor=TEXTE, leftIndent=11, bulletIndent=0, spaceAfter=1.5),
    'note': ParagraphStyle('note', fontName='Helvetica', fontSize=7.8, leading=10.5,
                           textColor=DISCRET, spaceBefore=3, spaceAfter=6),
    'cell': ParagraphStyle('cell', fontName='Helvetica', fontSize=8.6, leading=11.6,
                           textColor=TEXTE),
    'cell_g': ParagraphStyle('cell_g', fontName='Helvetica-Bold', fontSize=8.6, leading=11.6,
                             textColor=TEXTE),
    'cell_d': ParagraphStyle('cell_d', fontName='Helvetica', fontSize=8.6, leading=11.6,
                             textColor=TEXTE, alignment=TA_RIGHT),
    'entete': ParagraphStyle('entete', fontName='Helvetica-Bold', fontSize=8.8, leading=11.6,
                             textColor=colors.white),
    'entete_d': ParagraphStyle('entete_d', fontName='Helvetica-Bold', fontSize=8.8, leading=11.6,
                               textColor=colors.white, alignment=TA_RIGHT),
    'total_d': ParagraphStyle('total_d', fontName='Helvetica-Bold', fontSize=9.5, leading=12,
                              textColor=colors.white, alignment=TA_RIGHT),
    'total': ParagraphStyle('total', fontName='Helvetica-Bold', fontSize=9.5, leading=12,
                            textColor=colors.white),
}


def e(texte):
    return escape(str(texte or ''))


def P(texte, style='cell'):
    return Paragraph(texte, S[style])


def h1(texte):
    return [P(e(texte), 'h1'), HRFlowable(width='100%', thickness=1.2, color=OR,
                                          spaceBefore=0, spaceAfter=7)]


def puces(lignes):
    return [Paragraph(e(l), S['puce'], bulletText='•') for l in lignes if str(l).strip()]


def encadre(texte):
    t = Table([[P(texte, 'corps')]], colWidths=[LARGEUR])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), GRIS_FOND),
        ('LINEBEFORE', (0, 0), (0, -1), 3, OR),
        ('LEFTPADDING', (0, 0), (-1, -1), 11), ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    return t


def tableau(lignes, largeurs, droite=(), total=False, colonne_claire=None):
    """Tableau à en-tête bleu, lignes séparées par un filet.

    `lignes[0]` est l'en-tête. `droite` : colonnes alignées à droite (montants).
    `total` : la dernière ligne est un total (fond bleu). `colonne_claire` :
    colonne mise en valeur (la formule annuelle).
    """
    corps = []
    for i, ligne in enumerate(lignes):
        rangee = []
        for j, valeur in enumerate(ligne):
            if isinstance(valeur, Flowable):
                rangee.append(valeur)
                continue
            if i == 0:
                style = 'entete_d' if j in droite else 'entete'
            elif total and i == len(lignes) - 1:
                style = 'total_d' if j in droite else 'total'
            else:
                style = 'cell_d' if j in droite else ('cell_g' if j == 0 else 'cell')
            rangee.append(P(valeur, style))
        corps.append(rangee)
    t = Table(corps, colWidths=[LARGEUR * l for l in largeurs], repeatRows=1)
    style = [
        ('BACKGROUND', (0, 0), (-1, 0), BLEU),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 1), (-1, -1), 0.5, BORDURE),
        ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 7), ('RIGHTPADDING', (0, 0), (-1, -1), 7),
    ]
    if colonne_claire is not None:
        fin = -2 if total else -1
        style.append(('BACKGROUND', (colonne_claire, 1), (colonne_claire, fin), GRIS_FOND))
    if total:
        style.append(('BACKGROUND', (0, -1), (-1, -1), BLEU))
    t.setStyle(TableStyle(style))
    return t


# ── Champs du formulaire (AcroForm) ─────────────────────────────────────────

class ChoixRadio(Flowable):
    """Une ligne « ◯ libellé » : bouton radio d'un groupe, filet en dessous."""

    def __init__(self, groupe, valeur, libelle, largeur=LARGEUR):
        super().__init__()
        self.groupe, self.valeur, self.libelle = groupe, valeur, libelle
        self.width, self.height = largeur, 19

    def draw(self):
        c = self.canv
        c.acroForm.radio(name=self.groupe, value=self.valeur, selected=False,
                         x=8, y=4, size=11, buttonStyle='circle', shape='circle',
                         borderColor=BLEU, fillColor=colors.white, textColor=BLEU,
                         borderWidth=1, forceBorder=True, relative=True,
                         tooltip=self.libelle)
        c.setFont('Helvetica', 8.9)
        c.setFillColor(TEXTE)
        c.drawString(27, 6.5, self.libelle)
        c.setStrokeColor(BORDURE)
        c.setLineWidth(0.5)
        c.line(0, 0, self.width, 0)


class ChampTexte(Flowable):
    """« Libellé : ________ » avec un champ texte à remplir."""

    def __init__(self, libelle, nom, largeur, valeur=''):
        super().__init__()
        self.libelle, self.nom, self.valeur = libelle, nom, valeur
        self.width, self.height = largeur, 20

    def draw(self):
        c = self.canv
        c.setFont('Helvetica', 8.6)
        c.setFillColor(TEXTE)
        c.drawString(0, 6, self.libelle)
        debut = c.stringWidth(self.libelle, 'Helvetica', 8.6) + 6
        c.acroForm.textfield(name=self.nom, tooltip=self.libelle, value=self.valeur,
                             x=debut, y=2, width=self.width - debut - 4, height=15,
                             borderStyle='underlined', borderColor=BLEU, borderWidth=0.8,
                             fillColor=colors.white, textColor=TEXTE, fontName='Helvetica',
                             fontSize=9, relative=True, forceBorder=True)


class BoutonCourriel(Flowable):
    """Le bouton « Envoyer ma réponse par e-mail » : un lien mailto prérempli."""

    def __init__(self, texte, url, largeur=200, hauteur=24):
        super().__init__()
        self.texte, self.url = texte, url
        self.width, self.height = largeur, hauteur

    def wrap(self, disponible_l, disponible_h):
        self._decalage = max((disponible_l - self.width) / 2, 0)
        return disponible_l, self.height

    def draw(self):
        c = self.canv
        x = self._decalage
        c.setFillColor(OR)
        c.roundRect(x, 0, self.width, self.height, 4, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont('Helvetica-Bold', 9.5)
        c.drawCentredString(x + self.width / 2, 8, self.texte)
        c.linkURL(self.url, (x, 0, x + self.width, self.height), relative=1, thickness=0)


# ── La page ─────────────────────────────────────────────────────────────────

def _decor(p):
    pied = f"Proposition {p.reference} · {p.etablissement} · Document confidentiel"

    def dessiner(c, doc):
        c.saveState()
        c.setFillColor(BLEU)
        c.rect(0, HAUTEUR_PAGE - 44, LARGEUR_PAGE, 44, stroke=0, fill=1)
        c.setFillColor(OR)
        c.rect(0, HAUTEUR_PAGE - 47, LARGEUR_PAGE, 3, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont('Helvetica-Bold', 11)
        c.drawString(MARGE, HAUTEUR_PAGE - 27, 'HADY GESMAN')
        c.setFont('Helvetica', 7.8)
        c.drawRightString(LARGEUR_PAGE - MARGE, HAUTEUR_PAGE - 26,
                          'Gestion · Technologie · Automatisation · Accompagnement')
        c.setStrokeColor(BORDURE)
        c.setLineWidth(0.6)
        c.line(MARGE, 42, LARGEUR_PAGE - MARGE, 42)
        c.setFillColor(DISCRET)
        c.setFont('Helvetica', 7.3)
        c.drawString(MARGE, 30, pied[:120])
        c.drawRightString(LARGEUR_PAGE - MARGE, 30, f'Page {doc.page}')
        c.restoreState()
    return dessiner


def _filigrane(c, doc):
    """« BROUILLON » en travers, dessiné APRÈS le contenu pour rester visible
    sur les tableaux à fond coloré : un brouillon qui fuit doit se reconnaître."""
    c.saveState()
    c.setFillColor(colors.HexColor('#DC2626'))
    c.setFillAlpha(0.13)
    c.setFont('Helvetica-Bold', 86)
    c.translate(LARGEUR_PAGE / 2, HAUTEUR_PAGE / 2)
    c.rotate(35)
    c.drawCentredString(0, 0, 'BROUILLON')
    c.restoreState()


def _cachet(params, largeur=150):
    decode = decoder_data_uri(params.cachet_signature)
    if not decode:
        return Spacer(1, 70)
    try:
        lecteur = ImageReader(BytesIO(decode[1]))
        l, h = lecteur.getSize()
    except Exception:
        return Spacer(1, 70)
    hauteur = largeur * h / l
    if hauteur > 95:
        hauteur, largeur = 95, 95 * l / h
    return Image(BytesIO(decode[1]), width=largeur, height=hauteur, mask='auto', hAlign='CENTER')


def rendre_pdf(p):
    params = ParametresFacturation.actuels()
    ch = chiffrage(p)
    licence = libelle_licence(p.type_licence)
    m, s6, a12 = ch['mensuelle'], ch['semestrielle'], ch['annuelle']
    inst, migr = ch['installation'], ch['migration']
    pct = lambda t: f"{t * 100:g} %"
    ts, ta = ch['taux_semestriel'], ch['taux_annuel']
    migration = p.migration_proposee and migr > 0
    inst_txt = f"{francs(inst)} FCFA" if inst else 'offert'
    prog = f" — {e(p.programme)}" if p.programme else ''

    histoire = []
    A = histoire.append

    # ── En-tête ──────────────────────────────────────────────────────────
    A(P('PROPOSITION COMMERCIALE', 'titre'))
    A(P(f"Licence <b>{e(licence)}</b>{prog}", 'sous_titre'))
    A(P(f"{e(p.etablissement)}{' · Édition ' + e(p.edition) if p.edition else ''}", 'petit'))
    A(Spacer(1, 12))

    client = f"<b>{e(p.etablissement.upper())}</b>"
    if p.sous_titre:
        client += f" — {e(p.sous_titre)}"
    contacts = []
    if p.telephones:
        contacts.append(f"Tél. : {e(p.telephones)}")
    ligne2 = ' · '.join(x for x in (f"E-mail : {e(p.email)}" if p.email else '',
                                          e(p.autres_contacts)) if x)
    if ligne2:
        contacts.append(ligne2)
    infos = [('Référence', e(p.reference)), ('Client', client)]
    if p.adresse:
        infos.append(('Adresse', e(p.adresse)))
    if contacts:
        infos.append(('Contacts', '<br/>'.join(contacts)))
    infos += [
        ("À l'attention de", e(p.a_l_attention or 'La Direction')),
        ('Programme / licence', f"{e(p.programme) + ' — ' if p.programme else ''}Licence {e(licence)}"),
        ("Date d'émission", date_longue(p.date_emission)),
        ('Validité', f"{p.validite_jours} jours à compter de la date d'émission, "
                          f"soit jusqu'au {date_longue(p.date_validite)}"),
    ]
    t = Table([[P(k, 'cell_g'), P(v)] for k, v in infos], colWidths=[LARGEUR * .25, LARGEUR * .75])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), GRIS_LIBELLE),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDURE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LEFTPADDING', (0, 0), (-1, -1), 9),
    ]))
    A(t)
    A(Spacer(1, 12))
    A(encadre(f"<b>Cadre de la proposition.</b> Le présent document ne se substitue pas au "
              f"Catalogue Officiel des Offres et Tarifs {e(p.edition)}. Il présente, de façon "
              f"claire et complète, les formules proposées, les montants correspondants et "
              f"les conditions de paiement, afin de faciliter la décision de la Direction. Le "
              f"périmètre sera confirmé et, le cas échéant, ajusté lors du "
              f"diagnostic initial."))

    essentiel = [['Point clé', "Ce qu'il faut retenir"],
                 ['Licence', f"Licence {e(licence)} : {francs(ch['prix_mensuel'])} FCFA / mois"]]
    if ts:
        essentiel.append(['Remise semestrielle', f"{pct(ts)} sur la licence pour tout paiement de 6 mois"])
    if ta:
        essentiel.append(['Remise annuelle', f"{pct(ta)} sur la licence pour tout paiement de 12 mois"])
    if inst:
        essentiel.append(['Installation + paramétrage + formation',
                          f"{francs(inst)} FCFA, <b>obligatoire</b>, paiement unique, quelle que soit la formule"])
    if migration:
        essentiel.append(['Migration des données',
                          f"{francs(migr)} FCFA, <b>optionnelle</b> (non obligatoire)"])
    essentiel.append(['Paiement annuel en 2 tranches',
                      "50 % à la souscription, 50 % après installation, paramétrage et "
                      "formation initiale"])
    A(KeepTogether([P("L'essentiel en un coup d'œil", 'h2'),
                    tableau(essentiel, [.34, .66])]))

    # ── 1. Compréhension du besoin ───────────────────────────────────────
    paragraphes = [P(e(x.strip()), 'corps') for x in (p.contexte or '').split('\n') if x.strip()]
    # Le titre ne reste jamais seul en bas de page : il part avec le début du texte.
    A(KeepTogether(h1('1. Compréhension du besoin') + [P('1.1 Contexte', 'h2')] + paragraphes[:1]))
    histoire.extend(paragraphes[1:])
    if p.besoins:
        A(KeepTogether([P('1.2 Besoins identifiés (préliminaires)', 'h2'),
                        P('Les points suivants sont des hypothèses de travail, à valider avec '
                          'la Direction lors du diagnostic :', 'corps')] + puces(p.besoins)))
    if p.resultats:
        A(KeepTogether([P('1.3 Résultats attendus', 'h2')] + puces(p.resultats)))

    # ── 2. Programme et licence ──────────────────────────────────────────
    titre2 = (f"2. {p.programme} et licence {licence}" if p.programme
              else f"2. La licence {licence}")
    bloc = h1(titre2)
    if p.programme:
        intro = (f"{e(p.etablissement)} est soumis au <b>{e(p.programme)}</b>, avec la "
                 f"<b>licence {e(licence)}</b>.")
    else:
        intro = f"La présente proposition porte sur la <b>licence {e(licence)}</b> de SAGI SCHOOL."
    bloc.append(P(intro + f" Le périmètre fonctionnel de la licence est celui défini dans "
                  f"le Catalogue Officiel {e(p.edition)} ; il sera présenté en démonstration et "
                  f"confirmé lors du diagnostic, de façon à correspondre au fonctionnement "
                  f"réel de l'établissement.", 'corps'))
    A(KeepTogether(bloc))
    lots = [['Lot', 'Contenu', 'Caractère'],
            [f"Lot 1<br/>Licence {e(licence)}",
             "Accès à la plateforme, comptes utilisateurs et rôles, utilisation de la "
             "licence pendant la durée souscrite.",
             'Abonnement (mensuel, semestriel ou annuel)'],
            ['Lot 2<br/>Installation, paramétrage et formation',
             "Installation de la plateforme, paramétrage de l'établissement et formation "
             "initiale des utilisateurs.",
             f"<b>Obligatoire</b>, paiement unique de {francs(inst)} FCFA" if inst else 'Offert']]
    if migration:
        lots.append(['Option<br/>Migration des données',
                     'Reprise des données existantes (listes, historiques) dans la plateforme.',
                     f"<b>Optionnelle</b>, {francs(migr)} FCFA"])
    A(tableau(lots, [.25, .42, .33]))

    # Ce que la licence ouvre réellement : lu dans le code, jamais recopié du
    # catalogue commercial (voir apps/assistant/perimetre.py).
    from .devis import modules_inclus
    modules = modules_inclus(p.type_licence)
    if modules:
        lignes = [['Module', 'Ce qu’il couvre']] + [[e(n), e(d)] for n, d in modules]
        A(KeepTogether([P(f"Modules ouverts par la licence {e(licence)}", 'h2'),
                        tableau(lignes, [.3, .7])]))

    # ── 3. Déploiement et accompagnement ─────────────────────────────────
    dep = [['Étape', 'Statut', 'Observations'],
           ['Diagnostic', 'Inclus', 'Audit et diagnostic initiaux gratuits, réalisés lors de la '
                                    'démonstration.'],
           ['Installation / paramétrage', 'Obligatoire',
            f"Compris dans le forfait unique de {francs(inst)} FCFA." if inst else 'Offert.'],
           ['Formation initiale des utilisateurs', 'Obligatoire',
            f"Comprise dans le forfait unique de {francs(inst)} FCFA." if inst else 'Offerte.']]
    if migration:
        dep.append(['Migration des données', 'Optionnelle',
                    f"{francs(migr)} FCFA, à votre convenance ; non comprise dans les totaux de base."])
    dep.append(['Suivi', 'Prévu', 'Suivi après mise en production, avec compte rendu, afin de '
                                     'sécuriser la prise en main.'])
    A(KeepTogether(h1('3. Déploiement et accompagnement') + [tableau(dep, [.3, .17, .53])]))

    # ── 4. Investissement ────────────────────────────────────────────────
    A(PageBreak())
    histoire.extend(h1('4. Investissement : les trois formules'))
    if inst:
        A(P(f"Quelle que soit la formule choisie, le forfait <b>Installation + Paramétrage + "
            f"Formation de {francs(inst)} FCFA est obligatoire</b> ; il est réglé <b>une seule "
            f"fois</b> (paiement unique). Les remises portent sur la licence.", 'corps'))
    pm = francs(ch['prix_mensuel'])
    remise = lambda t, montant: f"{pct(t)} = - {francs(montant)}" if t else 'Aucune'
    inv = [['', 'Mensuelle', 'Semestrielle (6 mois)', 'Annuelle (12 mois)'],
           [f"Licence {e(licence)}", f"{pm} / mois", f"{pm} x 6 = {francs(s6['licence'])}",
            f"{pm} x 12 = {francs(a12['licence'])}"],
           ['Remise', 'Aucune', remise(ts, s6['remise']), remise(ta, a12['remise'])],
           ['Licence après remise', f"{pm} / mois", francs(s6['net']), francs(a12['net'])],
           ['Équivalent mensuel', pm, francs(s6['equivalent']), francs(a12['equivalent'])],
           ['Installation + paramétrage + formation (unique, obligatoire)',
            francs(inst), francs(inst), francs(inst)],
           ['TOTAL à la souscription', francs(m['total']), francs(s6['total']), francs(a12['total'])]]
    A(tableau(inv, [.31, .19, .25, .25], droite=(1, 2, 3), total=True, colonne_claire=3))
    note = ("Montants en FCFA. Total à la souscription : mensuelle = 1er mois de licence + "
            "installation ; semestrielle = 6 mois de licence après remise + installation ; "
            "annuelle = 12 mois de licence après remise + installation (ou option en deux "
            "tranches ci-dessous).")
    if migration:
        note += f" La migration des données ({francs(migr)} FCFA, optionnelle) n'est pas incluse."
    A(P(note, 'note'))

    noms = {'MENSUELLE': 'Mensuelle', 'SEMESTRIELLE': 'Semestrielle', 'ANNUELLE': 'Annuelle'}
    if migration:
        comp = [['Formule', 'Sans migration', 'Avec migration (option)', 'Économie sur la licence']]
        comp += [[noms[x['formule']], francs(x['sans_migration']), francs(x['avec_migration']),
                  francs(x['economie']) if x['economie'] else '-'] for x in ch['sur_12_mois']]
        largeurs = [.28, .22, .26, .24]
    else:
        comp = [['Formule', 'Coût sur 12 mois', 'Économie sur la licence']]
        comp += [[noms[x['formule']], francs(x['sans_migration']),
                  francs(x['economie']) if x['economie'] else '-'] for x in ch['sur_12_mois']]
        largeurs = [.4, .3, .3]
    A(KeepTogether([P('Comparatif sur une année complète (12 mois)', 'h2'),
                    tableau(comp, largeurs, droite=tuple(range(1, len(comp[0]))))]))
    A(P(f"Calcul sur 12 mois : mensuelle = 12 x {pm} + {francs(inst)} ; semestrielle = 2 x "
        f"{francs(s6['net'])} + {francs(inst)} ; annuelle = {francs(a12['net'])} + {francs(inst)}. "
        f"Montants en FCFA.", 'note'))

    # ── 5. Modalités de paiement ─────────────────────────────────────────
    cal = [['Formule', 'À la souscription', 'Ensuite'],
           ['Mensuelle', f"{francs(m['total'])} FCFA (installation {francs(inst)} + 1er mois {pm})",
            f"{pm} FCFA par mois"],
           ['Semestrielle', f"{francs(s6['total'])} FCFA (installation {francs(inst)} + 6 mois "
                            f"{francs(s6['net'])})",
            f"{francs(s6['net'])} FCFA pour le semestre suivant"],
           ['Annuelle', f"{francs(a12['total'])} FCFA (installation {francs(inst)} + 12 mois "
                        f"{francs(a12['net'])}), en une fois ou en deux tranches",
            "Aucun autre paiement durant l'année"]]
    A(KeepTogether(h1('5. Modalités de paiement')
                   + [P('5.1 Calendrier de paiement par formule', 'h2'), tableau(cal, [.18, .5, .32])]))
    t1, t2 = ch['tranches']
    tr = [['Tranche', 'Échéance', 'Montant (FCFA)'],
          ['Tranche 1 — 50 %', 'À la souscription', francs(t1)],
          ['Tranche 2 — 50 %', "Après l'installation, le paramétrage et la formation "
                                   "initiale des utilisateurs", francs(t2)],
          ['TOTAL', '', francs(a12['total'])]]
    A(KeepTogether([
        P('5.2 Option annuelle : paiement en deux tranches', 'h2'),
        P('Si la formule annuelle est choisie, le règlement peut s’effectuer en deux '
          'tranches égales :', 'corps'),
        tableau(tr, [.22, .53, .25], droite=(2,), total=True),
        P("Ce dispositif permet à l'établissement de ne régler la seconde moitié "
          "qu'une fois la plateforme installée, paramétrée et les utilisateurs formés.",
          'note')]))
    points = []
    if inst:
        points.append(f"Le forfait Installation + Paramétrage + Formation ({francs(inst)} FCFA) "
                      f"est obligatoire pour toutes les formules et réglé une seule fois.")
    if migration:
        points.append(f"La migration des données ({francs(migr)} FCFA) est optionnelle : "
                      f"l'établissement est libre de la demander ou non.")
    if ts or ta:
        points.append(f"Les remises de {pct(ts)} (semestriel) et {pct(ta)} (annuel) s'appliquent "
                      f"à la licence ; elles correspondent aux conditions du catalogue pour ces "
                      f"durées de paiement.")
    points.append("Moyens de paiement acceptés : " + ', '.join(catalogue.MOYENS_PAIEMENT)
                  + f". Le détail figure au Catalogue Officiel des Offres et Tarifs {p.edition}.")
    A(KeepTogether([P('5.3 Points importants', 'h2')] + puces(points)))

    # ── 6. Calendrier prévisionnel ───────────────────────────────────────
    nous = f"HADY GESMAN et {e(p.etablissement)}"
    planning = [['Phase', 'Période', 'Responsable'],
                ['Préparation', 'Semaine 1 après signature', nous],
                ['Installation et paramétrage', 'Semaines 1 à 2', 'HADY GESMAN'],
                ['Formation initiale des utilisateurs', 'Semaine 2', 'HADY GESMAN'],
                ['Mise en production', 'Semaine 3', nous],
                ['Suivi initial', 'Après la mise en production', 'HADY GESMAN']]
    A(KeepTogether(h1('6. Calendrier prévisionnel') + [tableau(planning, [.34, .29, .37])]))

    # ── 7. Acceptation ───────────────────────────────────────────────────
    A(PageBreak())
    histoire.extend(h1('7. Acceptation'))
    A(P("La présente proposition est soumise aux conditions contractuelles applicables. Son "
        "acceptation sera formalisée par bon de commande, contrat ou document équivalent. Le "
        "client indique ci-dessous sa formule" + (" et son choix concernant la migration."
                                                  if migration else "."), 'corps'))
    A(encadre("<b>Formulaire interactif.</b> Cliquez sur la formule"
              + (" et sur l'option de migration souhaitées" if migration else " souhaitée")
              + ", renseignez le nom, la fonction et la date, puis enregistrez le fichier et "
                "renvoyez-le par e-mail en cliquant sur le bouton ci-dessous."))
    A(Spacer(1, 10))

    def barre(texte):
        t = Table([[P(texte, 'entete')]], colWidths=[LARGEUR])
        t.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), BLEU),
                               ('TOPPADDING', (0, 0), (-1, -1), 5),
                               ('BOTTOMPADDING', (0, 0), (-1, -1), 5)]))
        return t

    formules_lignes = [
        ('MENSUELLE', f"Formule mensuelle : {francs(m['total'])} FCFA à la souscription, puis "
                      f"{pm} FCFA / mois"),
        ('SEMESTRIELLE', f"Formule semestrielle : {francs(s6['total'])} FCFA à la souscription"),
        ('ANNUELLE', f"Formule annuelle, paiement en une fois : {francs(a12['total'])} FCFA"),
        ('ANNUELLE_TRANCHES', f"Formule annuelle, paiement en deux tranches : {francs(t1)} + "
                              f"{francs(t2)} FCFA"),
    ]
    A(barre('Formule choisie (cliquez pour sélectionner)'))
    for valeur, texte in formules_lignes:
        A(ChoixRadio('formule', valeur, texte.replace(' ', ' ')))
    if migration:
        A(Spacer(1, 8))
        A(barre(f"Migration des données (option, {francs(migr)} FCFA)"))
        A(ChoixRadio('migration', 'OUI', f"OUI, je souhaite la migration des données "
                                         f"(+ {francs(migr)} FCFA)".replace(' ', ' ')))
        A(ChoixRadio('migration', 'NON', 'NON, sans migration des données'))
    A(Spacer(1, 22))

    demi = LARGEUR / 2
    gauche = [P(f"Nom : {e(params.signataire_nom)}<br/>Fonction : {e(params.signataire_fonction)}"),
              Spacer(1, 6), _cachet(params)]
    droite = [ChampTexte('Nom :', 'client_nom', demi - 16),
              ChampTexte('Fonction :', 'client_fonction', demi - 16),
              Spacer(1, 6), P('Signature et cachet du client :', 'petit'), Spacer(1, 62)]
    signatures = Table(
        [[P(e((params.raison_sociale or 'HADY GESMAN').upper()), 'entete'),
          P(f"CLIENT — {e(p.etablissement.upper())}", 'entete')],
         [gauche, droite],
         [P(f"Date : {p.date_emission:%d / %m / %Y}"), ChampTexte('Date :', 'client_date', demi - 16)]],
        colWidths=[demi, demi])
    signatures.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BLEU),
        ('BOX', (0, 0), (-1, -1), 0.5, BORDURE), ('INNERGRID', (0, 1), (-1, -1), 0.5, BORDURE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
    ]))
    A(KeepTogether([signatures]))
    A(Spacer(1, 14))
    retour = params.email or 'hadygesman@gmail.com'
    sujet = quote(f"Acceptation de la proposition {p.reference} — {p.etablissement}")
    corps = quote("Bonjour,\n\nVeuillez trouver ci-joint la proposition complétée et signée.\n\n")
    A(BoutonCourriel('Envoyer ma réponse par e-mail',
                     f"mailto:{retour}?subject={sujet}&body={corps}"))

    tampon = BytesIO()
    doc = BaseDocTemplate(
        tampon, pagesize=A4, leftMargin=MARGE, rightMargin=MARGE, topMargin=78, bottomMargin=60,
        title=f"Proposition commerciale {p.reference} - {licence} - {p.etablissement}",
        author=params.raison_sociale or 'HADY GESMAN',
        subject=f"Proposition commerciale {p.reference}")
    cadre = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='corps')
    doc.addPageTemplates([PageTemplate(
        id='page', frames=[cadre], onPage=_decor(p),
        onPageEnd=_filigrane if p.statut == 'BROUILLON' else (lambda c, d: None))])
    doc.build(histoire)
    return tampon.getvalue()
