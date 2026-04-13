from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import LoginView, UserViewSet

router = DefaultRouter()
router.register('users', UserViewSet, basename='user')

urlpatterns = [
    path('login/',   LoginView.as_view(),        name='login'),
    path('refresh/', TokenRefreshView.as_view(),  name='token_refresh'),
] + router.urls
