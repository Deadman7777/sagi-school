"""Libellés des documents pédagogiques : bulletin du programme arabe et fiche
pédagogique (français ou arabe).

Tout texte arabe destiné au PDF passe par shape_ar (voir core.arabe) : sans
cela, les lettres s'impriment détachées et dans le mauvais sens.
"""
from core.arabe import POLICE_ARABE, POLICE_LATINE, shape_ar

_ORDINAUX_M = ['الأول', 'الثاني', 'الثالث', 'الرابع', 'الخامس', 'السادس',
               'السابع', 'الثامن', 'التاسع', 'العاشر', 'الحادي عشر', 'الثاني عشر']
_ORDINAUX_F = ['الأولى', 'الثانية', 'الثالثة', 'الرابعة', 'الخامسة', 'السادسة',
               'السابعة', 'الثامنة', 'التاسعة', 'العاشرة', 'الحادية عشرة', 'الثانية عشرة']

APPRECIATIONS_AR = {
    'Excellent':        'ممتاز',
    'Très Bien':        'حسن جدا',
    'Bien':             'حسن',
    'Assez Bien':       'مستحسن',
    'Passable':         'مقبول',
    'Insuffisant':      'غير كاف',
    'Très Insuffisant': 'ضعيف جدا',
    'Absent':           'غائب',
}

DECISIONS_AR = {
    'Admis(e) avec félicitations — Passage en classe supérieure':
        'ناجح مع التهنئة — ينتقل إلى القسم الأعلى',
    'Admis(e) avec encouragements — Passage en classe supérieure':
        'ناجح مع التشجيع — ينتقل إلى القسم الأعلى',
    'Admis(e) — Passage en classe supérieure': 'ناجح — ينتقل إلى القسم الأعلى',
    'Ajourné(e) — Décision soumise au Conseil de Classe': 'مؤجل — القرار لمجلس القسم',
    'Redoublement recommandé par le Conseil de Classe': 'يوصي مجلس القسم بإعادة السنة',
    'Félicitations du Conseil de Classe': 'تهنئة مجلس القسم',
    'Encouragements du Conseil de Classe': 'تشجيع مجلس القسم',
    'Compliments du Conseil de Classe': 'تنويه مجلس القسم',
    'Résultats satisfaisants': 'نتائج مرضية',
    'Avertissement de travail': 'إنذار في العمل',
    'Blâme de travail — Soutien scolaire recommandé': 'توبيخ في العمل — يُنصح بالدعم المدرسي',
}

# Types d'évaluation courants, quand l'école n'a pas saisi le libellé arabe
_TYPES_EVAL_AR = [('devoir', 'فرض'), ('composition', 'امتحان'), ('examen', 'امتحان'),
                  ('interro', 'استجواب'), ('contr', 'مراقبة'), ('oral', 'شفهي'),
                  ('tp', 'أعمال تطبيقية')]


def libelle_periode(tenant, code, langue='fr'):
    """'T2' → « Trimestre 2 » ou « الثلاثي الثاني », selon le découpage de l'école."""
    n = int(''.join(ch for ch in (code or '') if ch.isdigit()) or 0)
    type_ = getattr(tenant, 'periode_scolaire', 'TRIMESTRE') or 'TRIMESTRE'
    if langue == 'ar':
        if not 1 <= n <= 12:
            return code
        if type_ == 'SEMESTRE':
            return f'الفصل الدراسي {_ORDINAUX_M[n - 1]}'
        if type_ == 'PERIODE':
            return f'الفترة {_ORDINAUX_F[n - 1]}'
        return f'الثلاثي {_ORDINAUX_M[n - 1]}'
    mot = {'SEMESTRE': 'Semestre', 'PERIODE': 'Période'}.get(type_, 'Trimestre')
    return f'{mot} {n}' if n else code


def nom_type_eval_ar(nom, nom_ar=''):
    if nom_ar:
        return nom_ar
    bas = (nom or '').lower()
    for debut, ar in _TYPES_EVAL_AR:
        if bas.startswith(debut):
            return ar
    return nom


def contexte_bulletin_ar(context, tenant, lignes):
    """Complète le contexte du bulletin PDF pour le gabarit arabe (de droite à gauche)."""
    from .models import TypeEvaluation
    noms_ar = dict(TypeEvaluation.objects.filter(tenant=tenant).values_list('nom', 'nom_ar'))

    colonnes = []
    for col in context['eval_columns']:
        tnom, idx = col['key']
        libelle = nom_type_eval_ar(tnom, noms_ar.get(tnom, ''))
        if col['label'] != tnom:          # plusieurs évaluations du même type
            libelle = f'{libelle} {idx}'
        colonnes.append({**col, 'label': shape_ar(libelle)})

    matieres = []
    for m in context['matieres']:
        matieres.append({**m,
                         'nom': shape_ar(m['nom']),
                         'appreciation': shape_ar(APPRECIATIONS_AR.get(m['appreciation'], m['appreciation'])),
                         'notes_cells_rtl': list(reversed(m['notes_cells']))})

    t = {k: shape_ar(v) for k, v in {
        'republique':  'جمهورية السنغال',
        'devise':      'شعب واحد — هدف واحد — إيمان واحد',
        'annee':       'السنة الدراسية',
        'autorisation': 'رقم رخصة الفتح',
        'titre':       'كشف النقاط',
        'programme':   'البرنامج العربي',
        'nom':         'الاسم واللقب',
        'classe':      'القسم',
        'matricule':   'رقم التسجيل',
        'naissance':   'تاريخ الازدياد',
        'rang':        'الرتبة',
        'moy_generale': 'المعدل العام',
        'moy_classe':  'معدل القسم',
        'plus_haute':  'أعلى معدل',
        'plus_basse':  'أدنى معدل',
        'matiere':     'المادة',
        'coef':        'المعامل',
        'notes':       'النقاط',
        'moyenne':     'المعدل',
        'points':      'المجموع',
        'appreciation': 'التقدير',
        'total':       'المجموع العام',
        'decision':    'قرار مجلس القسم',
        'mention':     'ملاحظة مجلس القسم',
        'prof':        'الأستاذ الرئيسي',
        'directeur':   'المدير',
        'cachet':      'الختم',
    }.items()}

    stats = context['stats']
    return {
        **context,
        't':                t,
        'periode_ar':       shape_ar(libelle_periode(tenant, context['trimestre'], 'ar')),
        'rang_ar':          shape_ar(f"{context['eleve']['rang']} من {stats['nb_eleves']}"),
        'eval_columns_rtl': list(reversed(colonnes)),
        'matieres':         matieres,
        'appreciation_generale': shape_ar(APPRECIATIONS_AR.get(context['appreciation_generale'],
                                                               context['appreciation_generale'])),
        'decision':         shape_ar(DECISIONS_AR.get(context['decision'], context['decision'])),
        'font_ar':          POLICE_ARABE,
    }


# ── Fiche pédagogique ─────────────────────────────────────────────────────

_FICHE = {
    'fr': {
        'titre': 'FICHE DE SUIVI PÉDAGOGIQUE', 'programme_FR': 'Programme français',
        'programme_AR': 'Programme arabe', 'eleve': 'Élève', 'classe': 'Classe',
        'annee': 'Année scolaire', 'matricule': 'Matricule',
        'evolution': 'Évolution des résultats', 'periode': 'Période', 'moyenne': 'Moyenne',
        'rang': 'Rang', 'moy_classe': 'Moy. classe', 'matieres': 'Résultats par matière',
        'matiere': 'Matière', 'coef': 'Coef.', 'derniere': 'Dernière /20',
        'ecart': 'Évolution', 'lecture': 'Lecture', 'forts': 'Points forts',
        'faibles': 'Points faibles', 'ameliorer': "Points d'amélioration",
        'recommandations': 'Recommandations', 'observations': "Observations de l'équipe pédagogique",
        'aucun': 'Aucun', 'directeur': 'Le Directeur', 'enseignant': "L'enseignant(e)",
        'parent': 'Le parent / tuteur', 'edite': 'Éditée le',
        'FORT': 'Point fort', 'FAIBLE': 'Point faible', 'MOYEN': 'Correct',
        'BAISSE': 'en baisse', 'SOUS_CLASSE': 'sous la moyenne de la classe', 'PROGRES': 'en progrès',
        'rec_faibles': 'Un soutien est recommandé en : {}.',
        'rec_baisse': 'Surveiller la baisse constatée en : {}.',
        'rec_sous_classe': 'Rattraper le niveau de la classe en : {}.',
        'rec_forts': 'Valoriser et entretenir les acquis en : {}.',
        'rec_hausse_gen': 'Progression générale de {} points : à encourager.',
        'rec_baisse_gen': "Baisse générale de {} points : un entretien avec la famille est conseillé.",
        'rec_regulier': 'Résultats réguliers : maintenir les efforts.',
        'aucune_note': 'Aucune note calculée pour cette année scolaire.',
    },
    'ar': {
        'titre': 'بطاقة المتابعة التربوية', 'programme_FR': 'البرنامج الفرنسي',
        'programme_AR': 'البرنامج العربي', 'eleve': 'التلميذ', 'classe': 'القسم',
        'annee': 'السنة الدراسية', 'matricule': 'رقم التسجيل',
        'evolution': 'تطور النتائج', 'periode': 'الفترة', 'moyenne': 'المعدل',
        'rang': 'الرتبة', 'moy_classe': 'معدل القسم', 'matieres': 'النتائج حسب المادة',
        'matiere': 'المادة', 'coef': 'المعامل', 'derniere': 'آخر معدل /20',
        'ecart': 'التطور', 'lecture': 'القراءة', 'forts': 'نقاط القوة',
        'faibles': 'نقاط الضعف', 'ameliorer': 'نقاط تحتاج إلى تحسين',
        'recommandations': 'التوصيات', 'observations': 'ملاحظات الفريق التربوي',
        'aucun': 'لا شيء', 'directeur': 'المدير', 'enseignant': 'المعلم',
        'parent': 'الولي', 'edite': 'حُررت في',
        'FORT': 'نقطة قوة', 'FAIBLE': 'نقطة ضعف', 'MOYEN': 'مقبول',
        'BAISSE': 'في تراجع', 'SOUS_CLASSE': 'دون معدل القسم', 'PROGRES': 'في تقدم',
        'rec_faibles': 'يوصى بالدعم في: {}.',
        'rec_baisse': 'متابعة التراجع الملاحظ في: {}.',
        'rec_sous_classe': 'اللحاق بمستوى القسم في: {}.',
        'rec_forts': 'تثمين المكتسبات والمحافظة عليها في: {}.',
        'rec_hausse_gen': 'تقدم عام بـ {} نقطة: يستحق التشجيع.',
        'rec_baisse_gen': 'تراجع عام بـ {} نقطة: يُنصح بلقاء مع الأسرة.',
        'rec_regulier': 'نتائج منتظمة: مواصلة الجهود.',
        'aucune_note': 'لا توجد نقاط محسوبة لهذه السنة الدراسية.',
    },
}


def recommandations(fiche, langue):
    """Rédige les recommandations décidées par resultats.recommandations."""
    t = _FICHE[langue]
    sep = '، ' if langue == 'ar' else ', '
    textes = []
    for r in fiche['recommandations']:
        modele = t['rec_' + r['code']]
        if 'noms' in r:
            textes.append(modele.format(sep.join(r['noms'])))
        elif r['code'] == 'hausse_gen':
            textes.append(modele.format(f"+{r['n']:g}"))
        elif 'n' in r:
            textes.append(modele.format(f"{r['n']:g}"))
        else:
            textes.append(modele)
    return textes


def contexte_fiche(fiche, tenant, eleve, classe_nom, langue):
    """Contexte du PDF de la fiche pédagogique, textes déjà traduits (et formés en arabe)."""
    ar = langue == 'ar'
    f = shape_ar if ar else (lambda x: x)
    t = {k: f(v) for k, v in _FICHE[langue].items()}
    sep = '، ' if ar else ', '

    def fmt(v):
        return '—' if v is None else f'{v:g}'

    periodes = [{
        'libelle':    f(libelle_periode(tenant, p['code'], langue)),
        'moyenne':    fmt(p['moyenne']),
        'rang':       (f(f"{p['rang']} من {p['effectif']}") if ar
                       else f"{p['rang']}{'er' if p['rang'] == 1 else 'e'} / {p['effectif']}"),
        'moy_classe': fmt(p['moy_classe']),
    } for p in fiche['periodes']]
    codes = [p['code'] for p in fiche['periodes']]
    entetes_periodes = [f(libelle_periode(tenant, c, langue)) for c in codes]

    matieres = []
    for m in fiche['matieres']:
        lecture = _FICHE[langue][m['statut']]
        details = [_FICHE[langue][r] for r in m['a_ameliorer']]
        if m['en_progres']:
            details.append(_FICHE[langue]['PROGRES'])
        if details:
            lecture = f"{lecture} ({sep.join(details)})"
        notes = [fmt(m['par_periode'].get(c)) for c in codes]
        evo = m['evolution']
        matieres.append({
            'nom':        f(m['nom']),
            'coef':       fmt(m['coefficient']),
            'notes':      list(reversed(notes)) if ar else notes,
            'derniere':   fmt(m['derniere']),
            'moy_classe': fmt(m['moy_classe']),
            'evolution':  '—' if evo is None else (f'+{evo:g}' if evo > 0 else f'{evo:g}'),
            'statut':     m['statut'],
            'lecture':    f(lecture),
        })

    def liste(noms):
        return f(sep.join(noms)) if noms else t['aucun']

    return {
        'ar':               ar,
        't':                t,
        'tenant':           tenant,
        'eleve':            eleve,
        'eleve_nom':        f(eleve.nom_complet),
        'classe':           f(classe_nom),
        'annee':            fiche['annee'],
        'programme':        t['programme_' + fiche['programme']],
        'periodes':         periodes,
        'entetes_periodes': list(reversed(entetes_periodes)) if ar else entetes_periodes,
        'matieres':         matieres,
        'forts':            liste(fiche['points_forts']),
        'faibles':          liste(fiche['points_faibles']),
        'ameliorer':        liste([a['nom'] for a in fiche['a_ameliorer']]),
        'recommandations':  [f(r) for r in recommandations(fiche, langue)],
        'font_ar':          POLICE_ARABE,
        'font_body':        POLICE_LATINE,
    }
