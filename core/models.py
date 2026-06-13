"""
Shared model building blocks.

Every domain entity inherits from these so that timestamps, soft-delete,
UUID identity and tenant scoping are consistent across the whole platform.
"""
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet aware of soft deletion."""

    def alive(self) -> "SoftDeleteQuerySet":
        return self.filter(is_deleted=False)

    def dead(self) -> "SoftDeleteQuerySet":
        return self.filter(is_deleted=True)

    def delete(self):  # type: ignore[override]
        # Bulk soft-delete instead of physical removal.
        return super().update(is_deleted=True, deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()


class SoftDeleteManager(models.Manager):
    """Default manager that hides soft-deleted rows."""

    def get_queryset(self) -> SoftDeleteQuerySet:
        return SoftDeleteQuerySet(self.model, using=self._db).alive()


class TimeStampedModel(models.Model):
    """UUID primary key + created/updated audit timestamps."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ("-created_at",)


class BaseModel(TimeStampedModel):
    """
    Standard base for domain entities.

    Adds soft-delete + actor tracking. Two managers are exposed:
    ``objects`` (alive only) and ``all_objects`` (includes deleted) so audit
    and recovery flows can still reach soft-deleted rows.
    """

    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta(TimeStampedModel.Meta):
        abstract = True

    def delete(self, using=None, keep_parents=False):
        """Soft delete by default."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])

    def hard_delete(self, using=None, keep_parents=False):
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])


class TenantScopedModel(BaseModel):
    """
    Base for rows that belong to a tenant (Organization).

    Multi-tenant ready: repositories filter on ``organization`` so a single
    deployment can serve many companies without code changes.
    """

    organization = models.ForeignKey(
        "branches.Organization",
        on_delete=models.CASCADE,
        related_name="%(class)s_set",
        db_index=True,
    )

    class Meta(BaseModel.Meta):
        abstract = True
