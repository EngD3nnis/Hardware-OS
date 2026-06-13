from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.serializers import (
    ChangePasswordSerializer,
    LoginSerializer,
    MFAConfirmSerializer,
    TokenPairSerializer,
    UserSerializer,
)
from apps.accounts.services import AuthService
from core.views import TenantContextMixin


class LoginView(APIView):
    """Authenticate and issue a JWT access/refresh pair."""

    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        data = LoginSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = AuthService().authenticate(
            email=data.validated_data["email"],
            password=data.validated_data["password"],
            mfa_code=data.validated_data.get("mfa_code") or None,
        )
        refresh = TokenPairSerializer.get_token(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSerializer(user).data,
            }
        )


class LogoutView(APIView):
    """Blacklist the supplied refresh token."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        token = request.data.get("refresh")
        if token:
            try:
                RefreshToken(token).blacklist()
            except Exception:  # already-invalid token — treat as logged out
                pass
        AuthService().logout(request.user)
        return Response(status=status.HTTP_205_RESET_CONTENT)


class MeView(TenantContextMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class ChangePasswordView(TenantContextMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = ChangePasswordSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        AuthService().change_password(
            request.user,
            current=data.validated_data["current_password"],
            new=data.validated_data["new_password"],
        )
        return Response({"detail": "Password updated."})


class MFAEnrollView(TenantContextMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        uri = AuthService().begin_mfa_enrollment(request.user)
        return Response({"provisioning_uri": uri})


class MFAConfirmView(TenantContextMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = MFAConfirmSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        AuthService().confirm_mfa(request.user, data.validated_data["code"])
        return Response({"detail": "MFA enabled."})
