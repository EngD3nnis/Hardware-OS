from __future__ import annotations

from uuid import UUID

from apps.branches.models import Branch, Organization
from core.repositories import BaseRepository, TenantRepository


class OrganizationRepository(BaseRepository[Organization]):
    model = Organization

    def get_by_slug(self, slug: str) -> Organization | None:
        return self.model.objects.filter(slug=slug).first()


class BranchRepository(TenantRepository[Branch]):
    model = Branch

    def __init__(self, organization_id: UUID | str):
        super().__init__(organization_id, Branch)

    def active(self):
        return self.get_queryset().filter(is_active=True)

    def get_by_code(self, code: str) -> Branch | None:
        return self.get_queryset().filter(code=code).first()
