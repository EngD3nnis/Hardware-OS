"""
Role-Based Access Control registry.

Permissions are string codes ("<resource>.<action>"). Roles are bundles of
permission codes. The mapping below is the single source of truth used to seed
the Role table (see `accounts` bootstrap) and to check access at the API layer.
"""
from __future__ import annotations


class Perm:
    """Canonical permission codes. Group by resource for readability."""

    # Branches / org
    BRANCH_VIEW = "branch.view"
    BRANCH_MANAGE = "branch.manage"

    # Users / roles
    USER_VIEW = "user.view"
    USER_MANAGE = "user.manage"
    ROLE_MANAGE = "role.manage"

    # Inventory
    PRODUCT_VIEW = "product.view"
    PRODUCT_MANAGE = "product.manage"
    PRICE_MANAGE = "price.manage"        # changing selling/cost prices
    STOCK_VIEW = "stock.view"
    STOCK_ADJUST = "stock.adjust"
    STOCK_TRANSFER = "stock.transfer"
    SUPPLIER_MANAGE = "supplier.manage"
    PURCHASE_MANAGE = "purchase.manage"

    # POS
    SALE_CREATE = "sale.create"
    SALE_VIEW = "sale.view"
    SALE_REFUND = "sale.refund"
    SALE_VOID = "sale.void"
    CUSTOMER_VIEW = "customer.view"
    CUSTOMER_MANAGE = "customer.manage"

    # Finance
    FINANCE_VIEW = "finance.view"
    FINANCE_MANAGE = "finance.manage"

    # Analytics / executive
    DASHBOARD_VIEW = "dashboard.view"
    ANALYTICS_VIEW = "analytics.view"
    AI_QUERY = "ai.query"

    # Audit
    AUDIT_VIEW = "audit.view"


class RoleSlug:
    SUPER_ADMIN = "super_admin"
    OWNER = "owner"
    BRANCH_MANAGER = "branch_manager"
    ACCOUNTANT = "accountant"
    CASHIER = "cashier"
    INVENTORY_OFFICER = "inventory_officer"
    SALES_STAFF = "sales_staff"


# Convenience bundles
_ALL = {getattr(Perm, n) for n in dir(Perm) if n.isupper()}

_INVENTORY_FULL = {
    Perm.PRODUCT_VIEW, Perm.PRODUCT_MANAGE, Perm.PRICE_MANAGE,
    Perm.STOCK_VIEW, Perm.STOCK_ADJUST, Perm.STOCK_TRANSFER,
    Perm.SUPPLIER_MANAGE, Perm.PURCHASE_MANAGE,
}

# slug -> (display name, hierarchy level, permission set)
ROLE_DEFINITIONS: dict[str, tuple[str, int, set[str]]] = {
    RoleSlug.SUPER_ADMIN: ("Super Admin", 100, set(_ALL)),
    RoleSlug.OWNER: (
        "Owner",
        90,
        _ALL - {Perm.ROLE_MANAGE},  # owner sees everything but role plumbing
    ),
    RoleSlug.BRANCH_MANAGER: (
        "Branch Manager",
        70,
        {
            Perm.BRANCH_VIEW, Perm.USER_VIEW, Perm.DASHBOARD_VIEW,
            Perm.ANALYTICS_VIEW, Perm.AI_QUERY, Perm.FINANCE_VIEW,
            Perm.SALE_CREATE, Perm.SALE_VIEW, Perm.SALE_REFUND, Perm.SALE_VOID,
            Perm.CUSTOMER_VIEW, Perm.CUSTOMER_MANAGE,
            *_INVENTORY_FULL,
        },
    ),
    RoleSlug.ACCOUNTANT: (
        "Accountant",
        60,
        {
            Perm.BRANCH_VIEW, Perm.FINANCE_VIEW, Perm.FINANCE_MANAGE,
            Perm.DASHBOARD_VIEW, Perm.ANALYTICS_VIEW, Perm.SALE_VIEW,
            Perm.STOCK_VIEW, Perm.PRODUCT_VIEW, Perm.AUDIT_VIEW, Perm.CUSTOMER_VIEW,
        },
    ),
    RoleSlug.INVENTORY_OFFICER: (
        "Inventory Officer",
        50,
        {Perm.BRANCH_VIEW, *_INVENTORY_FULL},
    ),
    RoleSlug.CASHIER: (
        "Cashier",
        40,
        {
            Perm.BRANCH_VIEW, Perm.SALE_CREATE, Perm.SALE_VIEW,
            Perm.PRODUCT_VIEW, Perm.STOCK_VIEW,
            Perm.CUSTOMER_VIEW, Perm.CUSTOMER_MANAGE,
        },
    ),
    RoleSlug.SALES_STAFF: (
        "Sales Staff",
        30,
        {
            Perm.BRANCH_VIEW, Perm.SALE_CREATE, Perm.PRODUCT_VIEW, Perm.STOCK_VIEW,
            Perm.CUSTOMER_VIEW, Perm.CUSTOMER_MANAGE,
        },
    ),
}
