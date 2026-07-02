from django.contrib import admin
from .models import (TypeFinancement, Financement, NattCycle,
                     NattCotisation, NattReception)

admin.site.register(TypeFinancement)
admin.site.register(Financement)
admin.site.register(NattCycle)
admin.site.register(NattCotisation)
admin.site.register(NattReception)
