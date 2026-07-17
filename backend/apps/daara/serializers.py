from rest_framework import serializers

from .models import (Sourate, Subdivision, NiveauDaara, ParcoursNongo,
                     SuiviQuotidien, bornes_hizb, nb_versets_bornes)


class SourateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sourate
        fields = '__all__'


class SubdivisionSerializer(serializers.ModelSerializer):
    sourate_numero = serializers.IntegerField(source='sourate_debut.numero', read_only=True)
    sourate_nom_fr = serializers.CharField(source='sourate_debut.nom_fr', read_only=True)
    sourate_nom_ar = serializers.CharField(source='sourate_debut.nom_ar', read_only=True)

    class Meta:
        model = Subdivision
        fields = '__all__'


class NiveauDaaraSerializer(serializers.ModelSerializer):
    class Meta:
        model = NiveauDaara
        fields = '__all__'
        extra_kwargs = {'tenant': {'required': False, 'read_only': True}}


class ParcoursNongoSerializer(serializers.ModelSerializer):
    eleve_nom       = serializers.CharField(source='eleve.nom_complet', read_only=True)
    niveau_nom      = serializers.CharField(source='niveau.nom_fr', read_only=True)
    # Catégorie du niveau → le front bascule le suivi en mode alphabet (IDJIE).
    niveau_categorie = serializers.CharField(source='niveau.categorie', read_only=True)

    class Meta:
        model = ParcoursNongo
        fields = '__all__'
        extra_kwargs = {
            'tenant': {'required': False, 'read_only': True},
            'niveau': {'required': False, 'allow_null': True},
        }


class SuiviQuotidienSerializer(serializers.ModelSerializer):
    sourate_debut_nom = serializers.CharField(source='sourate_debut.nom_fr', read_only=True)
    sourate_fin_nom   = serializers.CharField(source='sourate_fin.nom_fr', read_only=True)
    # Nombre de versets couverts par l'entrée — quelle que soit la méthode de
    # saisie (les bornes sourate:verset sont dérivées à l'enregistrement en mode hizb).
    nb_versets        = serializers.SerializerMethodField()

    def get_nb_versets(self, obj):
        if not obj.sourate_debut_id or not obj.sourate_fin_id:
            return None
        return nb_versets_bornes(obj.parcours.riwaya,
                                 obj.sourate_debut.numero, obj.verset_debut,
                                 obj.sourate_fin.numero,   obj.verset_fin)

    class Meta:
        model = SuiviQuotidien
        fields = '__all__'
        extra_kwargs = {
            'tenant': {'required': False, 'read_only': True},
            'sourate_debut': {'required': False, 'allow_null': True},
            'sourate_fin': {'required': False, 'allow_null': True},
        }

    def validate(self, attrs):
        """Mode HIZB : bornes hizb requises, puis dérivation des bornes
        sourate:verset (riwaaya du parcours) pour que la progression reste
        exacte. Mode SOURATE : on nettoie les champs hizb."""
        mode = attrs.get('mode', getattr(self.instance, 'mode', 'SOURATE'))
        if mode != 'HIZB':
            attrs['hizb_debut'] = None
            attrs['hizb_fin']   = None
            return attrs

        h1 = attrs.get('hizb_debut', getattr(self.instance, 'hizb_debut', None))
        h2 = attrs.get('hizb_fin',   getattr(self.instance, 'hizb_fin',   None))
        if not h1 or not h2:
            raise serializers.ValidationError(
                {'hizb_debut': 'Hizb de début et de fin requis en saisie par hizb.'})
        h1, h2 = min(h1, h2), max(h1, h2)
        parcours = attrs.get('parcours') or (self.instance.parcours if self.instance else None)
        riwaya   = parcours.riwaya if parcours else 'HAFS'
        try:
            s_deb, v_deb, s_fin, v_fin = bornes_hizb(riwaya, h1, h2)
        except ValueError as e:
            raise serializers.ValidationError({'hizb_debut': str(e)})
        attrs.update(hizb_debut=h1, hizb_fin=h2,
                     sourate_debut=s_deb, verset_debut=v_deb,
                     sourate_fin=s_fin,   verset_fin=v_fin)
        return attrs
