from collections import defaultdict

import beancount.core.amount as amt
from attrs import define, field

from beanzero.budget.spec import CategoryKey, Month


@define
class AssignedAmounts:
    held: amt.Amount = field()
    categories: defaultdict[CategoryKey, amt.Amount]

    @held.validator  # type: ignore
    def validate_held(self, attr, held):
        assert held.number >= 0, "Can't have negative held balance"


@define
class BudgetStore:
    """Defines the aspects of the budget that are editable in the running program.

    This data is mutable, and loaded from and persisted to disk, in contrast to
    the read-only BudgetSpec.
    """

    assigned: defaultdict[Month, AssignedAmounts]
