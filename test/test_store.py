from collections import defaultdict

import beancount as b
import pytest

from beanzero.budget.spec import Month
from beanzero.budget.store import AssignedAmounts

from .conftest import AUD, ZERO


class TestAssignedAmounts:
    def test_cant_hold_negative(self):
        AssignedAmounts(b.Amount(b.D("10.00"), "AUD"), defaultdict())

        with pytest.raises(AssertionError):
            AssignedAmounts(b.Amount(b.D("-10.00"), "AUD"), defaultdict())


@pytest.mark.spec_file("sample-budget.yml")
@pytest.mark.store_file("sample-budget.json")
class TestBudgetStore:
    def test_loaded_months(self, store):
        assert list(store.assigned.keys()) == [
            Month(12, 2024),
            Month(1, 2025),
            Month(2, 2025),
        ]

    def test_loaded_values(self, store):
        values = store.assigned[Month(1, 2025)]
        assert values.held == ZERO
        assert values.categories["investments"] == AUD("200.00")
        assert values.categories["car"] == AUD("500.00")
        assert values.categories["hobbies"] == AUD("33.00")

    def test_adds_good_defaults_for_new_month(self, store, spec):
        assert store.assigned[Month(1, 1999)].held == ZERO
        assert store.assigned[Month(1, 1999)].categories == spec.category_map()
        store.assigned[Month(1, 1999)].categories["car"] = AUD("50.00")
        assert store.assigned[Month(1, 1999)].categories["car"] == AUD("50.00")
        with pytest.raises(KeyError):
            assert store.assigned[Month(1, 1999)].categories["non-existent"]

    # TODO do round trip testing that checks zero values aren't written
    @pytest.mark.xfail(
        reason="defaultdict->CategoryMap means zeroes are pruned only on write"
    )
    def test_prunes_zero_values(self, store):
        values = store.assigned[Month(1, 2025)]
        values.categories["new"] = ZERO
        store.prune()
        assert "new" not in values.categories.keys()

    def test_prunes_zero_months(self, store, spec):
        store.assigned[Month(1, 1999)] = AssignedAmounts(spec.zero, spec.category_map())
        store.prune()
        assert Month(1, 1999) not in store.assigned.keys()
