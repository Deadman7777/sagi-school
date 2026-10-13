"""Reprise au registre des chèques déjà encaissés sur les exercices ouverts.

Ils ont été portés directement au 521 : ils entrent au registre avec
compte_reception='521', « à compléter » (numéro, banque, tireur inconnus).
Leur remise et leur encaissement ne passent aucune écriture."""
from decimal import Decimal

from django.db import migrations


def reprendre(apps, schema_editor):
    Paiement = apps.get_model('paiements', 'Paiement')
    ChequeRecu = apps.get_model('paiements', 'ChequeRecu')
    AffectationCheque = apps.get_model('paiements', 'AffectationCheque')
    champs = ('montant_inscription', 'montant_mensualite', 'montant_uniforme',
              'montant_fournitures', 'montant_cantine', 'montant_divers', 'montant_reliquat')
    qs = (Paiement.objects.filter(statut='ACTIF', exercice__cloture=False)
          .filter(mode_paiement__in=('CHEQUE', 'MIXTE')))
    for p in qs.iterator():
        if p.modes_reglement:
            part = sum(Decimal(str(l.get('montant') or 0)) for l in p.modes_reglement
                       if (l or {}).get('mode') == 'CHEQUE')
        elif p.mode_paiement == 'CHEQUE':
            part = sum(Decimal(str(getattr(p, c) or 0)) for c in champs)
        else:
            part = Decimal('0')
        if part <= 0:
            continue
        cheque = ChequeRecu.objects.create(
            tenant_id=p.tenant_id, exercice_id=p.exercice_id, date_reception=p.date_paiement,
            montant=part, compte_reception='521', recu_par_id=p.saisi_par_id,
            observations='Chèque reçu avant le registre — à compléter.')
        AffectationCheque.objects.create(tenant_id=p.tenant_id, cheque=cheque, paiement=p,
                                         montant=part)


class Migration(migrations.Migration):
    dependencies = [('paiements', '0021_registre_cheques')]
    operations = [migrations.RunPython(reprendre, migrations.RunPython.noop)]
