from rest_framework.routers import DefaultRouter
from .views import LicenceViewSet

router = DefaultRouter()
router.register('', LicenceViewSet)
urlpatterns = router.urls
