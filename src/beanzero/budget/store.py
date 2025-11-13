from __future__ import annotations

import json
import typing
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import beancount.core.amount as amt
from attrs import define, field
from cattrs import Converter
from cattrs.cols import defaultdict_structure_factory, is_defaultdict

from beanzero.budget.spec import CategoryKey, Month, spec_converter


@define
class AssignedAmounts:
    held: amt.Amount = field()
    categories: defaultdict[CategoryKey, amt.Amount]

    # TODO get a `spec` object and ensure all categories always exist?

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

    @classmethod
    def load(cls, fp: typing.IO, zero_val: amt.Amount) -> BudgetStore:
        data = json.load(fp)
        store = get_store_converter(zero_val).structure(data, cls)
        return store

    def prune(self):
        # Delete empty category amounts
        for amounts in self.assigned.values():
            for category in list(amounts.categories.keys()):
                if amounts.categories[category] == amounts.categories.default_factory():
                    del amounts.categories[category]

        # Delete empty months
        for months in list(self.assigned.keys()):
            if self.assigned[months] == self.assigned.default_factory():
                del self.assigned[months]

    def save(self, path: Path, zero_val: amt.Amount):
        # TODO sort on save & test roundtrips
        self.prune()
        data = get_store_converter(zero_val).unstructure(self)
        tempfile = path.parent / f"{path.name}.write"
        with tempfile.open("w") as write_f:
            json.dump(data, write_f, indent=2)
        tempfile.rename(path)


# we need a function rather than a global instance as the hooks need the
# currency-specific zero amt.Amount for a particular budget
def get_store_converter(zero_val: amt.Amount) -> Converter:
    # build on spec_converter for built-in month etc conversion
    store_converter = spec_converter.copy()

    # register hooks for our funky defaultdicts
    store_converter.register_structure_hook(
        amt.Amount, lambda a, _: amt.Amount(Decimal(a), zero_val.currency)
    )
    store_converter.register_unstructure_hook(amt.Amount, lambda a: str(a.number))
    store_converter.register_unstructure_hook(Month, lambda m: m.as_iso())

    hook = defaultdict_structure_factory(
        defaultdict[CategoryKey, amt.Amount],
        store_converter,
        default_factory=lambda: zero_val,
    )

    store_converter.register_structure_hook_func(is_defaultdict, hook)

    hook = defaultdict_structure_factory(
        defaultdict[Month, AssignedAmounts],
        store_converter,
        default_factory=lambda: AssignedAmounts(
            zero_val, defaultdict(lambda: zero_val)
        ),
    )
    store_converter.register_structure_hook_func(is_defaultdict, hook)

    return store_converter
