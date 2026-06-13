from rest_framework.routers import DefaultRouter

from apps.inventory.views import (
    CategoryViewSet,
    ProductViewSet,
    StockViewSet,
    SupplierViewSet,
)

router = DefaultRouter()
router.register("categories", CategoryViewSet, basename="category")
router.register("suppliers", SupplierViewSet, basename="supplier")
router.register("products", ProductViewSet, basename="product")
router.register("stock", StockViewSet, basename="stock")

urlpatterns = router.urls
