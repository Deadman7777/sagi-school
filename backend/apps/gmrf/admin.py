from django.contrib import admin
from .models import (TypeFinancement, Financement, NattCycle,
                     NattCotisation, NattReception, Pret, PretEcheance)

admin.site.register(TypeFinancement)
admin.site.register(Financement)
admin.site.register(NattCycle)
admin.site.register(NattCotisation)
admin.site.register(NattReception)
admin.site.register(Pret)
admin.site.register(PretEcheance)
