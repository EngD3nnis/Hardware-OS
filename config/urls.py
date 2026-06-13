"""Root URL configuration."""
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)

api_v1 = [
    path("auth/", include("apps.accounts.urls")),
    path("branches/", include("apps.branches.urls")),
    path("inventory/", include("apps.inventory.urls")),
    path("pos/", include("apps.pos.urls")),
    path("finance/", include("apps.finance.urls")),
    path("analytics/", include("apps.analytics.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    # API
    path("api/v1/", include((api_v1, "v1"))),
    # OpenAPI schema + docs (frontend & AI service consume this contract)
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
]
