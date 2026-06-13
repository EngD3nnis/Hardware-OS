"""
Repository pattern base.

All ORM access goes through repositories. Services and views never touch
``Model.objects`` directly — this is the seam we cut when extracting a module
into its own microservice later.
"""
from __future__ import annotations

from typing import Generic, TypeVar
from uuid import UUID

from django.db.models import Model, QuerySet

from core.exceptions import NotFoundError

T = TypeVar("T", bound=Model)


class BaseRepository(Generic[T]):
    """Generic CRUD repository over a Django model."""

    model: type[T]

    def __init__(self, model: type[T] | None = None) -> None:
        if model is not None:
            self.model = model
        if not getattr(self, "model", None):
            raise ValueError("Repository requires a `model`.")

    # -- read ------------------------------------------------------------- #
    def get_queryset(self) -> QuerySet[T]:
        return self.model.objects.all()

    def all(self) -> QuerySet[T]:
        return self.get_queryset()

    def filter(self, **kwargs) -> QuerySet[T]:
        return self.get_queryset().filter(**kwargs)

    def get(self, **kwargs) -> T:
        obj = self.get_queryset().filter(**kwargs).first()
        if obj is None:
            raise NotFoundError(f"{self.model.__name__} not found.")
        return obj

    def get_by_id(self, pk: UUID | str) -> T:
        return self.get(pk=pk)

    def exists(self, **kwargs) -> bool:
        return self.get_queryset().filter(**kwargs).exists()

    # -- write ------------------------------------------------------------ #
    def create(self, **kwargs) -> T:
        obj = self.model(**kwargs)
        obj.full_clean(exclude=self._clean_exclude())
        obj.save()
        return obj

    def update(self, instance: T, **kwargs) -> T:
        for field, value in kwargs.items():
            setattr(instance, field, value)
        instance.full_clean(exclude=self._clean_exclude())
        instance.save()
        return instance

    def delete(self, instance: T) -> None:
        instance.delete()

    def _clean_exclude(self) -> list[str]:
        # Skip validation of audit/relation fields that services set explicitly.
        return ["created_by", "updated_by", "organization"]


class TenantRepository(BaseRepository[T]):
    """Repository pre-scoped to a single organization (tenant)."""

    def __init__(self, organization_id: UUID | str, model: type[T] | None = None):
        super().__init__(model)
        self.organization_id = organization_id

    def get_queryset(self) -> QuerySet[T]:
        return self.model.objects.filter(organization_id=self.organization_id)

    def create(self, **kwargs) -> T:
        kwargs.setdefault("organization_id", self.organization_id)
        return super().create(**kwargs)
