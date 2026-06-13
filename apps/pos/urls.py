from rest_framework.routers import DefaultRouter

from apps.pos.views import CustomerViewSet, SaleViewSet

router = DefaultRouter()
router.register("customers", CustomerViewSet, basename="customer")
router.register("sales", SaleViewSet, basename="sale")

urlpatterns = router.urls
