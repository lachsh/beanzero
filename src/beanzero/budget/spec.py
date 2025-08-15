from __future__ import annotations

import datetime
import typing
from decimal import Decimal
from functools import total_ordering
from pathlib import Path

import beancount.core.amount as amt
import beancount.core.data as beandata
import yaml
from attrs import define, field
from cattrs import Converter
from slugify import slugify

spec_converter = Converter()


@total_ordering
@define(frozen=True)
class Month:
    """Represents a month of a given year."""

    month: int = field()
    year: int = field()

    @month.validator  # type: ignore
    def check_month(self, attribute, month: int):
        if not 1 <= month <= 12:
            raise ValueError("Month must be between 1 and 12")

    @classmethod
    def from_datetime(cls, in_datetime: datetime.datetime | datetime.date):
        return Month(in_datetime.month, in_datetime.year)

    @classmethod
    def from_string(cls, string: str):
        dt = datetime.datetime.strptime(string, "%Y-%m")
        return cls(dt.month, dt.year)

    @classmethod
    def now(cls):
        now = datetime.datetime.today()
        return Month(now.month, now.year)

    def __add__(self, months: int) -> Month:
        new_month = self.month + months
        new_year = self.year
        if new_month > 12 or new_month < 0:
            new_year += new_month // 12
            new_month = new_month % 12
        return Month(new_month, new_year)

    def __sub__(self, other: int | Month) -> int | Month:
        if isinstance(other, int):
            return self + (-other)
        elif isinstance(other, Month):
            return 12 * (self.year - other.year) + self.month - other.month
        else:
            raise ValueError

    def __lt__(self, other: Month) -> bool:
        return self.year < other.year or (
            self.year == other.year and self.month < other.month
        )

    def start_datetime(self):
        return datetime.datetime(year=self.year, month=self.month, day=1)

    def end_datetime(self):
        next_month = self + 1
        return datetime.datetime(
            year=next_month.year, month=next_month.month, day=1
        ) - datetime.timedelta(microseconds=1)

    def __str__(self):
        return self.start_datetime().strftime("%B %Y")


@spec_converter.register_structure_hook
def parse_month(val: str, _) -> Month:
    return Month.from_string(val)


@define(frozen=True)
class BeanAccountCollection:
    """Represents an aribtrary collection of Beancount accounts."""

    accounts: list[beandata.Account] = field(factory=list)

    def __contains__(self, account: str):
        # TODO support globs
        return account in self.accounts


@spec_converter.register_structure_hook
def to_account_collection(val: str | list[str] | None, _) -> BeanAccountCollection:
    if val is None:
        return BeanAccountCollection([])
    elif isinstance(val, str):
        return BeanAccountCollection([val])
    elif isinstance(val, list):
        return BeanAccountCollection(val)


CategoryKey = str


@define(frozen=True)
class Category:
    """Represents a single budget ('spending') category."""

    name: str
    accounts: BeanAccountCollection = field(factory=BeanAccountCollection)
    key: CategoryKey = field(init=False)

    def __attrs_post_init__(self):
        object.__setattr__(self, "key", slugify(self.name))  # TODO allow specifying


@define(frozen=True)
class CategoryGroup:
    """Represents a named group of budget categories."""

    name: str
    categories: list[Category]


@define(frozen=True)
class BudgetSpec:
    """Defines the accounts, categories, and other metadata for a budget.

    Does not contain any actual transaction or budget data itself, just the structure.

    This is loaded from a config file, and is immutable while the program is running.
    """

    name: str
    ledger: Path = field()
    storage: Path = field()
    currency: beandata.Currency
    start: Month
    accounts: BeanAccountCollection
    groups: list[CategoryGroup] = field()

    @classmethod
    def load(cls, fp: typing.IO):
        data = yaml.safe_load(fp)
        spec = spec_converter.structure(data, cls)
        return spec

    @ledger.validator  # type: ignore
    def check_ledger(self, _, ledger):
        assert self.ledger.exists()

    @storage.validator  # type: ignore
    def check_storage(self, _, ledger):
        assert self.storage.exists()

    @groups.validator  # type: ignore
    def check_groups(self, _, groups: list[CategoryGroup]):
        # ensure we have unique category keys
        keys = set()
        for group in groups:
            for category in group.categories:
                if category.key in keys:
                    raise ValueError(f"Duplicate category key {category.key}")
                keys.add(category.key)

    @property
    def zero(self):
        return amt.Amount(Decimal("0"), self.currency)

    @property
    def all_category_keys(self):
        return [c.key for g in self.groups for c in g.categories]

    # @functools.cache
    def is_budget_acccount(self, beancount_account: str) -> bool:
        return beancount_account in self.accounts

    # @functools.cache
    def get_account_category(self, beancount_account: str) -> CategoryKey | None:
        found_category_key: CategoryKey | None = None

        for group in self.groups:
            for category in group.categories:
                if beancount_account in category.accounts:
                    if found_category_key is None:
                        found_category_key = category.key
                    else:
                        raise ValueError(
                            f"Account {beancount_account} fits in multiple categories: {found_category_key} and {category.key}"
                        )

        return found_category_key
