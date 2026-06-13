from rest_framework.routers import DefaultRouter

from apps.analytics.views import DashboardViewSet

router = DefaultRouter()
router.register("dashboard", DashboardViewSet, basename="dashboard")

urlpatterns = router.urls
