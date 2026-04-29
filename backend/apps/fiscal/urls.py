from django.urls import path
from .views import DeclarationsFiscalesView

urlpatterns = [
    path('declarations/', DeclarationsFiscalesView.as_view()),
]
