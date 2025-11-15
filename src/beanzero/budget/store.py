from __future__ import annotations

import json
import typing
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import beancount
import beancount.core.amount as amt
from attrs import define, field
from cattrs import Converter
from cattrs.cols import defaultdict_structure_factory, is_defaultdict

from beanzero.budget.spec import (
    BudgetSpec,
    CategoryKey,
    CategoryMap,
    Month,
    spec_converter,
)


@define
class AssignedAmounts:
    held: amt.Amount = field()
    categories: CategoryMap

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
    spec: BudgetSpec = field(init=False)

    @classmethod
    def load(cls, fp: typing.IO, spec: BudgetSpec) -> BudgetStore:
        data = json.load(fp)
        store = get_store_converter(spec).structure(data, cls)
        store.spec = spec
        return store

    def prune(self):
        # Delete empty months
        for months in list(self.assigned.keys()):
            if self.assigned[months] == AssignedAmounts(
                self.spec.zero, self.spec.category_map()
            ):
                del self.assigned[months]

    def save(self, path: Path, spec: BudgetSpec):
        # TODO sort on save & test roundtrips
        self.prune()

        # remove zeroes from the data to write
        write = self.copy()
        for amounts in write.assigned.values():
            for category in list(amounts.categories.keys()):
                if amounts.categories[category] == self.spec.zero:
                    del amounts.categories[category]
        data = get_store_converter(spec).unstructure(write)
        tempfile = path.parent / f"{path.name}.write"
        with tempfile.open("w") as write_f:
            json.dump(data, write_f, indent=2)
        tempfile.rename(path)


# we need a function rather than a global instance as the hooks need the
# currency-specific zero amt.Amount and category keys for a particular budget
def get_store_converter(spec: BudgetSpec) -> Converter:
    # build on spec_converter for built-in month etc conversion
    store_converter = spec_converter.copy()

    # register hooks for our funky defaultdicts
    store_converter.register_structure_hook(
        amt.Amount, lambda a, _: amt.Amount(Decimal(a), spec.zero.currency)
    )
    store_converter.register_unstructure_hook(amt.Amount, lambda a: str(a.number))
    store_converter.register_unstructure_hook(Month, lambda m: m.as_iso())

    @store_converter.register_structure_hook
    def structure_category(d, cls) -> CategoryMap:
        out = spec.category_map()
        out.update({k: amt.Amount(beancount.D(v), spec.currency) for k, v in d.items()})
        return out

    hook = defaultdict_structure_factory(
        defaultdict[Month, AssignedAmounts],
        store_converter,
        default_factory=lambda: AssignedAmounts(spec.zero, spec.category_map()),
    )
    store_converter.register_structure_hook_func(is_defaultdict, hook)

    return store_converter
