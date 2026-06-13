from __future__ import annotations

from apps.accounts.models import LoginEvent, Role, User
from core.repositories import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def get_by_email(self, email: str) -> User | None:
        return self.model.objects.filter(email__iexact=email).first()

    def with_roles(self):
        return self.model.objects.prefetch_related("roles")


class RoleRepository(BaseRepository[Role]):
    model = Role

    def get_by_slug(self, slug: str) -> Role | None:
        return self.model.objects.filter(slug=slug).first()


class LoginEventRepository(BaseRepository[LoginEvent]):
    model = LoginEvent
