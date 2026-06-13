"""Branch use-cases with audit + uniqueness enforcement."""
from __future__ import annotations

from uuid import UUID

from django.db import transaction

from apps.branches.models import Branch
from apps.branches.repositories import BranchRepository
from core.audit.context import get_context
from core.audit.services import AuditAction
from core.exceptions import ConflictError
from core.services import BaseService

_TRACKED = ["name", "code", "address", "city", "phone", "email", "is_active", "manager_id"]


class BranchService(BaseService):
    def __init__(self, organization_id: UUID | str):
        self.organization_id = organization_id
        self.repo = BranchRepository(organization_id)

    @transaction.atomic
    def create_branch(self, **data) -> Branch:
        if self.repo.get_by_code(data["code"]):
            raise ConflictError(f"Branch code '{data['code']}' already exists.")
        actor = self._actor()
        branch = self.repo.create(created_by=actor, updated_by=actor, **data)
        self.record_audit(action=AuditAction.CREATE, entity=branch, branch_id=str(branch.id))
        return branch

    @transaction.atomic
    def update_branch(self, branch_id: UUID | str, **data) -> Branch:
        branch = self.repo.get_by_id(branch_id)
        before = self.snapshot(branch, _TRACKED)
        if "code" in data and data["code"] != branch.code:
            if self.repo.get_by_code(data["code"]):
                raise ConflictError(f"Branch code '{data['code']}' already exists.")
        data["updated_by"] = self._actor()
        branch = self.repo.update(branch, **data)
        changes = self.diff_fields(before, self.snapshot(branch, _TRACKED))
        if changes:
            self.record_audit(
                action=AuditAction.UPDATE, entity=branch,
                changes=changes, branch_id=str(branch.id),
            )
        return branch

    @transaction.atomic
    def delete_branch(self, branch_id: UUID | str) -> None:
        branch = self.repo.get_by_id(branch_id)
        self.repo.delete(branch)
        self.record_audit(action=AuditAction.DELETE, entity=branch, branch_id=str(branch.id))

    @staticmethod
    def _actor():
        user = get_context().user
        return user if user and user.is_authenticated else None
