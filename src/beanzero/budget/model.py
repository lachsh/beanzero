from __future__ import annotations

import datetime
import functools
import json
import operator
import typing
from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal
from functools import total_ordering
from pathlib import Path

import beancount.core.amount as amt
import beancount.core.data as beandata
import beancount.loader
import yaml
from attrs import define, field
from cattrs import Converter
from cattrs.cols import defaultdict_structure_factory
from slugify import slugify

budget_converter = Converter()


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


@budget_converter.register_structure_hook
def parse_month(val: str, _) -> Month:
    return Month.from_string(val)


@define(frozen=True)
class BeanAccountCollection:
    """Represents an aribtrary collection of Beancount accounts."""

    accounts: list[beandata.Account] = field(factory=list)

    def __contains__(self, account: str):
        # TODO support globs
        return account in self.accounts


@budget_converter.register_structure_hook
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
    def load(cls, fp: typing.TextIO):
        data = yaml.safe_load(fp)
        spec = budget_converter.structure(data, cls)
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


@define(frozen=True)
class BudgetTransaction:
    """The budget-relevant data corresponding to a single Beancount transaction.

    Spending represents money leaving the budget, and so should be usually negative.

    Governed by the equation flow(+/-) = funding(+) + spending(-)
    """

    date: datetime.date
    flow: amt.Amount
    spending: defaultdict[CategoryKey, amt.Amount]

    @functools.cached_property
    def total_spending(self) -> amt.Amount:
        return functools.reduce(
            amt.add,
            self.spending.values(),
            amt.Amount(Decimal("0"), self.flow.currency),
        )

    @functools.cached_property
    def funding(self) -> amt.Amount:
        return amt.sub(self.flow, self.total_spending)

    @functools.cached_property
    def month(self) -> Month:
        return Month.from_datetime(self.date)


class AssignedAmounts:
    held: amt.Amount = field()
    categories: defaultdict[CategoryKey, amt.Amount]

    @held.validator  # type: ignore
    def validate_held(self, attr, held):
        assert held.number >= 0, "Can't have negative held balance"


class BudgetStore:
    """Defines the aspects of the budget that are editable in the running program.

    This data is mutable, and loaded from and persisted to disk, in contrast to
    the read-only BudgetSpec.
    """

    assigned: defaultdict[Month, AssignedAmounts]


class Budget:
    """Combines all data sources to calculate budget data.

    Loads the budget spec from the config file, the transaction data from the beancount
    ledger, and the stored budget amounts from the data JSON file.

    Iterates over months to calculate per-category and overall balances and totals.
    """

    def convert_transaction(self, tx: beandata.Transaction) -> BudgetTransaction | None:
        # Scan through postings for overall budget flow
        flow = self.spec.zero
        budget_accounts = set()
        for posting in tx.postings:
            if self.spec.is_budget_acccount(posting.account):
                if posting.units is None:
                    raise ValueError("Null posting")
                budget_accounts.add(posting.account)
                flow = amt.add(flow, posting.units)

        # If there's no net budget inflow or outflow, then this transaction isn't
        # relevant to the budget
        if flow == self.spec.zero:
            return None

        # If there's flow, then calculate any spending
        spending = defaultdict(lambda: self.spec.zero)
        for posting in tx.postings:
            if cat := self.spec.get_account_category(posting.account):
                if cat in budget_accounts:
                    raise ValueError(
                        f"Account {cat} cannot be budget account and budget category"
                    )
                if posting.units is None:
                    raise ValueError("Null posting")

                spending[cat] = amt.sub(spending[cat], posting.units)

        return BudgetTransaction(tx.date, flow, spending)

    def aggregate_funding(self, txs: list[BudgetTransaction]):
        return functools.reduce(
            amt.add, map(operator.attrgetter("funding"), txs), self.spec.zero
        )

    def aggregate_spending(self, txs: list[BudgetTransaction]):
        spending = defaultdict(lambda: self.spec.zero)
        for tx in txs:
            for k, v in tx.spending.items():
                spending[k] = amt.add(spending[k], v)
        return spending

    @define
    class MonthlyTotals:
        """The relevant totals to calculate for a given month.

        Holding and budgeted amounts are usually positive.
        Funding is usually positive.
        Spending (including overspending) is usually negative.
        """

        # governing spec
        spec: BudgetSpec

        # global amounts
        previous_tba: amt.Amount
        previous_holding: amt.Amount
        previous_overspending: amt.Amount
        funding: amt.Amount
        holding: amt.Amount

        # per-category amounts
        carryover: defaultdict[CategoryKey, amt.Amount]
        spending: defaultdict[CategoryKey, amt.Amount]
        budgeting: defaultdict[CategoryKey, amt.Amount]

        @property
        def total_spending(self) -> amt.Amount:
            return functools.reduce(amt.add, self.spending.values(), self.spec.zero)

        @property
        def total_budgeting(self) -> amt.Amount:
            return functools.reduce(amt.add, self.budgeting.values(), self.spec.zero)

        @property
        def category_balances(self) -> defaultdict[CategoryKey, amt.Amount]:
            balances = defaultdict(lambda: self.spec.zero)
            for key in self.spec.all_category_keys:
                balances[key] = self.carryover[key]
                balances[key] = amt.add(balances[key], self.spending[key])
                balances[key] = amt.add(balances[key], self.budgeting[key])
            return balances

        @property
        def carryover_balances(self) -> defaultdict[CategoryKey, amt.Amount]:
            balances = self.category_balances.copy()
            for k, v in balances.items():
                if v.number and v.number < 0:
                    balances[k] = self.spec.zero

            return balances

        @property
        def overspending(self) -> amt.Amount:
            balances = self.category_balances
            neg_balances = [a for a in balances.values() if a.number < 0]
            overspending = functools.reduce(amt.add, neg_balances, self.spec.zero)
            return overspending

        @property
        def to_be_assigned(self) -> amt.Amount:
            tba = self.previous_tba
            tba = amt.add(tba, self.previous_holding)
            tba = amt.add(tba, self.previous_overspending)
            tba = amt.add(tba, self.funding)
            tba = amt.sub(tba, self.total_budgeting)
            tba = amt.sub(tba, self.holding)
            return tba

    def __init__(self, spec: BudgetSpec):
        self.spec = spec

        # Load the beancount data, and convert and categorise transactions by month
        directives, errors, options = beancount.loader.load_file(spec.ledger)
        self.beancount_directives = directives

        self.monthly_transactions = defaultdict(list)

        for directive in directives:
            if isinstance(directive, beandata.Transaction):
                if tx := self.convert_transaction(directive):
                    self.monthly_transactions[tx.month].append(tx)
        self.latest_month = max(self.monthly_transactions.keys()) + 1

        # Load amounts budgeted each month
        with self.spec.storage.open("rb") as storage_f:
            budgeting_data = json.load(storage_f)
            budget_converter.register_structure_hook(
                amt.Amount, lambda a, _: amt.Amount(Decimal(a), self.spec.zero.currency)
            )
            hook = defaultdict_structure_factory(
                defaultdict[CategoryKey, amt.Amount],
                budget_converter,
                default_factory=lambda: self.spec.zero,
            )
            budget_converter.register_structure_hook(
                defaultdict[CategoryKey, amt.Amount], hook
            )
            hook = defaultdict_structure_factory(
                defaultdict[Month, AssignedAmounts],
                budget_converter,
                default_factory=lambda: AssignedAmounts(
                    self.spec.zero, defaultdict(lambda: self.spec.zero)
                ),
            )
            budget_converter.register_structure_hook(
                defaultdict[Month, AssignedAmounts], hook
            )
            self.store = budget_converter.structure(budgeting_data, BudgetStore)

        # Calculate monthly totals from transaction and budgeting data
        self.monthly_totals: dict[Month, Budget.MonthlyTotals] = dict()

        self.monthly_totals[self.spec.start] = Budget.MonthlyTotals(
            spec=self.spec,
            previous_tba=self.spec.zero,
            previous_holding=self.spec.zero,
            previous_overspending=self.spec.zero,
            funding=self.aggregate_funding(self.monthly_transactions[self.spec.start]),
            holding=self.store.assigned[self.spec.start].held,
            carryover=defaultdict(lambda: self.spec.zero),
            spending=self.aggregate_spending(
                self.monthly_transactions[self.spec.start]
            ),
            budgeting=self.store.assigned[self.spec.start].categories,
        )

        month = self.spec.start + 1
        while month <= self.latest_month:
            prev = self.monthly_totals[month - 1]
            self.monthly_totals[month] = Budget.MonthlyTotals(
                spec=self.spec,
                previous_tba=prev.to_be_assigned,
                previous_holding=prev.holding,
                previous_overspending=prev.overspending,
                funding=self.aggregate_funding(self.monthly_transactions[month]),
                holding=self.store.assigned[month].held,
                carryover=prev.carryover_balances,
                spending=self.aggregate_spending(self.monthly_transactions[month]),
                budgeting=self.store.assigned[month].categories,
            )
            month += 1
