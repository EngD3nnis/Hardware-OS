"""
Idempotent bootstrap: seed RBAC roles, a demo organization + branch, and an
owner account. Safe to run multiple times.

    python manage.py bootstrap --email owner@demo.co --password 'Str0ngPass!23'
"""
from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import Role, User
from apps.branches.models import Branch, Organization
from apps.inventory.models import Category, Product
from core.rbac import ROLE_DEFINITIONS, RoleSlug


class Command(BaseCommand):
    help = "Seed roles, a demo organization, branch and owner account."

    def add_arguments(self, parser):
        parser.add_argument("--email", default="owner@hardwareos.local")
        parser.add_argument("--password", default="ChangeMe!2026")
        parser.add_argument("--org", default="Demo Hardware Co")
        parser.add_argument("--demo-data", action="store_true", help="Also seed sample products.")

    @transaction.atomic
    def handle(self, *args, **opts):
        roles = self._seed_roles()
        org = self._seed_org(opts["org"])
        branch = self._seed_branch(org)
        owner = self._seed_owner(opts["email"], opts["password"], org, branch, roles)
        if opts["demo_data"]:
            self._seed_products(org)

        self.stdout.write(self.style.SUCCESS("Bootstrap complete."))
        self.stdout.write(f"  Organization: {org.name} ({org.id})")
        self.stdout.write(f"  Branch:       {branch.name} ({branch.code})")
        self.stdout.write(f"  Owner login:  {owner.email}")

    def _seed_roles(self) -> dict[str, Role]:
        result: dict[str, Role] = {}
        for slug, (name, level, perms) in ROLE_DEFINITIONS.items():
            role, _ = Role.objects.update_or_create(
                slug=slug,
                defaults={
                    "name": name,
                    "level": level,
                    "permissions": sorted(perms),
                    "is_system": True,
                },
            )
            result[slug] = role
        self.stdout.write(f"  Seeded {len(result)} roles.")
        return result

    def _seed_org(self, name: str) -> Organization:
        org, _ = Organization.objects.get_or_create(
            slug="demo-hardware", defaults={"name": name}
        )
        return org

    def _seed_branch(self, org: Organization) -> Branch:
        branch, _ = Branch.objects.get_or_create(
            organization=org, code="HQ",
            defaults={"name": "Head Office", "city": "Nairobi", "is_active": True},
        )
        return branch

    def _seed_owner(self, email, password, org, branch, roles) -> User:
        user, created = User.objects.get_or_create(
            email=email.lower(),
            defaults={
                "first_name": "System", "last_name": "Owner",
                "organization": org, "branch": branch,
                "is_staff": True, "is_superuser": True, "is_active": True,
            },
        )
        if created:
            user.set_password(password)
            user.save()
        user.roles.add(roles[RoleSlug.OWNER], roles[RoleSlug.SUPER_ADMIN])
        return user

    def _seed_products(self, org: Organization) -> None:
        cement, _ = Category.objects.get_or_create(
            organization=org, slug="cement", defaults={"name": "Cement"}
        )
        roofing, _ = Category.objects.get_or_create(
            organization=org, slug="roofing", defaults={"name": "Roofing Sheets"}
        )
        samples = [
            ("CEM-50", "Cement 50kg Bag", cement, "bag", "650", "780", "20"),
            ("ROOF-30", "Roofing Sheet 3m", roofing, "pcs", "850", "1100", "15"),
            ("NAIL-1", "Nails 1kg", cement, "kg", "120", "180", "30"),
        ]
        for sku, name, cat, unit, cost, sell, reorder in samples:
            Product.objects.get_or_create(
                organization=org, sku=sku,
                defaults={
                    "name": name, "category": cat, "unit": unit,
                    "cost_price": Decimal(cost), "selling_price": Decimal(sell),
                    "reorder_level": Decimal(reorder),
                },
            )
        self.stdout.write("  Seeded sample products.")
