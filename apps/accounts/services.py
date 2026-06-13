"""Account use-cases: authentication, login auditing, MFA scaffolding."""
from __future__ import annotations

import pyotp
from django.contrib.auth import authenticate
from django.db import transaction

from apps.accounts.models import LoginEvent, User
from apps.accounts.repositories import UserRepository
from core.audit.context import get_context
from core.audit.services import AuditAction
from core.exceptions import PermissionDeniedError, ValidationError
from core.services import BaseService


class AuthService(BaseService):
    def __init__(self) -> None:
        self.users = UserRepository()

    def authenticate(self, *, email: str, password: str, mfa_code: str | None = None) -> User:
        """Validate credentials (+ MFA when enabled) and record the attempt."""
        ctx = get_context()
        user = authenticate(username=email, password=password)

        if user is None or not user.is_active:
            self._log_login(user=None, email=email, ok=False)
            self.record_audit(
                action=AuditAction.LOGIN_FAILED,
                entity_type="User",
                entity_id="",
                metadata={"email": email},
            )
            raise PermissionDeniedError("Invalid email or password.")

        if user.mfa_enabled:
            if not mfa_code:
                raise ValidationError("MFA code required.")
            if not self.verify_mfa(user, mfa_code):
                self._log_login(user=user, email=email, ok=False)
                raise PermissionDeniedError("Invalid MFA code.")

        self._log_login(user=user, email=email, ok=True)
        self.record_audit(action=AuditAction.LOGIN, entity=user)
        return user

    def logout(self, user: User) -> None:
        self.record_audit(action=AuditAction.LOGOUT, entity=user)

    # -- MFA (TOTP) ------------------------------------------------------- #
    @transaction.atomic
    def begin_mfa_enrollment(self, user: User) -> str:
        """Generate a TOTP secret and return a provisioning URI for a QR code."""
        secret = pyotp.random_base32()
        user.mfa_secret = secret
        user.save(update_fields=["mfa_secret", "updated_at"])
        return pyotp.totp.TOTP(secret).provisioning_uri(
            name=user.email, issuer_name="HardwareOS"
        )

    @transaction.atomic
    def confirm_mfa(self, user: User, code: str) -> None:
        if not self.verify_mfa(user, code):
            raise ValidationError("Invalid MFA code.")
        user.mfa_enabled = True
        user.save(update_fields=["mfa_enabled", "updated_at"])
        self.record_audit(action=AuditAction.UPDATE, entity=user, changes={"mfa": "enabled"})

    @staticmethod
    def verify_mfa(user: User, code: str) -> bool:
        if not user.mfa_secret:
            return False
        return pyotp.TOTP(user.mfa_secret).verify(code, valid_window=1)

    def change_password(self, user: User, *, current: str, new: str) -> None:
        if not user.check_password(current):
            raise ValidationError("Current password is incorrect.")
        user.set_password(new)
        user.save(update_fields=["password", "updated_at"])
        self.record_audit(action=AuditAction.UPDATE, entity=user, changes={"password": "changed"})

    # -- internals -------------------------------------------------------- #
    def _log_login(self, *, user, email: str, ok: bool) -> None:
        ctx = get_context()
        LoginEvent.objects.create(
            user=user,
            email_attempted=email,
            successful=ok,
            ip_address=ctx.ip_address,
            user_agent=ctx.user_agent,
        )
