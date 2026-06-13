from rest_framework.routers import DefaultRouter

from apps.finance.views import (
    ExpenseCategoryViewSet,
    ExpenseViewSet,
    FinanceReportViewSet,
)

router = DefaultRouter()
router.register("expense-categories", ExpenseCategoryViewSet, basename="expense-category")
router.register("expenses", ExpenseViewSet, basename="expense")
router.register("reports", FinanceReportViewSet, basename="finance-report")

urlpatterns = router.urls
