import pytest

from beanzero.budget.budget import Budget
from beanzero.budget.spec import Month

from .conftest import AUD, ZERO


@pytest.mark.spec_file("sample-budget.yml")
class TestBudgetIntegration:
    def test_budget_loads(self, budget):
        assert isinstance(budget, Budget)

    def test_budget_months(self, budget):
        assert budget.ledger_start_month == Month(12, 2024)
        assert budget.latest_budget_month == Month(2, 2025)
        assert budget.latest_month == Month.now() + 1

    def test_monthly_totals(self, budget):
        jan = budget.monthly_totals[Month(1, 2025)]
        assert jan.total_spending == AUD("-1678")
        assert jan.total_assigning == AUD("1839.78")
        assert jan.category_balances == {
            "rent": AUD("50"),
            "utilities": AUD("-20"),
            "car": AUD("20"),
            "eating-out": AUD("55"),
            "hobbies": ZERO,
            "investments": ZERO,
            "rainy-day-fund": AUD("456.78"),
        }
        assert jan.to_be_assigned == AUD("260.22")

        feb = budget.monthly_totals[Month(2, 2025)]
        assert feb.total_spending == ZERO
        assert feb.total_assigning == AUD("0.20")
        assert feb.category_balances == {
            "rent": AUD("50"),
            "utilities": ZERO,
            "car": AUD("45.20"),
            "eating-out": AUD("55"),
            "hobbies": AUD("30.20"),
            "investments": ZERO,
            "rainy-day-fund": AUD("401.58"),
        }
        assert feb.to_be_assigned == AUD("240.02")

    def test_assigned_changes_propagate(self, budget):
        budget.update_assigned_amount(
            Month(12, 2024), "investments", AUD("100"), save=False
        )
        assert budget.monthly_totals[Month(12, 2024)].category_balances[
            "investments"
        ] == AUD("100")
        assert budget.monthly_totals[Month(1, 2025)].category_balances[
            "investments"
        ] == AUD("100")
        assert budget.monthly_totals[Month(2, 2025)].category_balances[
            "investments"
        ] == AUD("100")

    def test_held_changes_propagate(self, budget):
        budget.update_held_amount(Month(1, 2025), AUD("99.95"), save=False)
        assert budget.monthly_totals[Month(1, 2025)].holding == AUD("99.95")
        assert budget.monthly_totals[Month(1, 2025)].to_be_assigned == AUD("160.27")
        assert budget.monthly_totals[Month(2, 2025)].holding == ZERO
        assert budget.monthly_totals[Month(2, 2025)].to_be_assigned == AUD("240.02")
