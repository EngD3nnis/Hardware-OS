from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.views import (
    ChangePasswordView,
    LoginView,
    LogoutView,
    MeView,
    MFAConfirmView,
    MFAEnrollView,
)

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("refresh/", TokenRefreshView.as_view(), name="token-refresh"),
    path("me/", MeView.as_view(), name="me"),
    path("password/change/", ChangePasswordView.as_view(), name="password-change"),
    path("mfa/enroll/", MFAEnrollView.as_view(), name="mfa-enroll"),
    path("mfa/confirm/", MFAConfirmView.as_view(), name="mfa-confirm"),
]
