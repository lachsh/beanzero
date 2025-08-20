from __future__ import annotations

import datetime
import functools
import operator
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import beancount.core.amount as amt
import beancount.core.data as beandata
import beancount.loader
from attrs import define

from beanzero.budget.spec import (
    BudgetSpec,
    CategoryGroup,
    CategoryKey,
    Month,
)
from beanzero.budget.store import BudgetStore, get_store_converter


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


@define(frozen=True)
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
    assigning: defaultdict[CategoryKey, amt.Amount]

    @staticmethod
    def aggregate_funding(spec: BudgetSpec, txs: list[BudgetTransaction]):
        return functools.reduce(
            amt.add, map(operator.attrgetter("funding"), txs), spec.zero
        )

    @staticmethod
    def aggregate_spending(spec: BudgetSpec, txs: list[BudgetTransaction]):
        spending = defaultdict(lambda: spec.zero)
        for tx in txs:
            for k, v in tx.spending.items():
                spending[k] = amt.add(spending[k], v)
        return spending

    @classmethod
    def from_transactions(
        cls,
        spec: BudgetSpec,
        txs: list[BudgetTransaction],
        holding: amt.Amount,
        assigning: defaultdict[CategoryKey, amt.Amount],
        prev_month: MonthlyTotals | None = None,
    ) -> MonthlyTotals:
        if prev_month is None:
            previous_tba = spec.zero
            previous_holding = spec.zero
            previous_overspending = spec.zero
            carryover = defaultdict(lambda: spec.zero)
        else:
            previous_tba = prev_month.to_be_assigned
            previous_holding = prev_month.holding
            previous_overspending = prev_month.overspending
            carryover = prev_month.carryover_balances
        return MonthlyTotals(
            spec,
            previous_tba,
            previous_holding,
            previous_overspending,
            cls.aggregate_funding(spec, txs),
            holding,
            carryover,
            cls.aggregate_spending(spec, txs),
            assigning,
        )

    @property
    def total_spending(self) -> amt.Amount:
        return functools.reduce(amt.add, self.spending.values(), self.spec.zero)

    @property
    def total_assigning(self) -> amt.Amount:
        return functools.reduce(amt.add, self.assigning.values(), self.spec.zero)

    @property
    def category_balances(self) -> defaultdict[CategoryKey, amt.Amount]:
        balances = defaultdict(lambda: self.spec.zero)
        for key in self.spec.all_category_keys:
            balances[key] = self.carryover[key]
            balances[key] = amt.add(balances[key], self.spending[key])
            balances[key] = amt.add(balances[key], self.assigning[key])
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
        neg_balances = [a for a in balances.values() if a.number < 0]  # type: ignore
        overspending = functools.reduce(amt.add, neg_balances, self.spec.zero)
        return overspending

    @property
    def to_be_assigned(self) -> amt.Amount:
        tba = self.previous_tba
        tba = amt.add(tba, self.previous_holding)
        tba = amt.add(tba, self.previous_overspending)
        tba = amt.add(tba, self.funding)
        tba = amt.sub(tba, self.total_assigning)
        tba = amt.sub(tba, self.holding)
        return tba

    def group_assigned(self, group: CategoryGroup) -> amt.Amount:
        amounts = [self.assigning[cat.key] for cat in group.categories]
        return functools.reduce(amt.add, amounts, self.spec.zero)

    def group_spending(self, group: CategoryGroup) -> amt.Amount:
        amounts = [self.spending[cat.key] for cat in group.categories]
        return functools.reduce(amt.add, amounts, self.spec.zero)

    def group_balance(self, group: CategoryGroup) -> amt.Amount:
        amounts = [self.category_balances[cat.key] for cat in group.categories]
        return functools.reduce(amt.add, amounts, self.spec.zero)


class Budget:
    """Combines all data sources to calculate budget data.

    Loads the budget spec from the config file, the transaction data from the beancount
    ledger, and the stored budget amounts from the data JSON file.

    Iterates over months to calculate per-category and overall balances and totals.
    """

    def __init__(self, spec_path: Path | str):
        spec_path = Path(spec_path)
        with spec_path.open("r") as spec_f:
            self.spec = BudgetSpec.load(spec_f)

        # Load the beancount data, and convert and categorise transactions by month
        directives, errors, options = beancount.loader.load_file(self.spec.ledger)
        self.beancount_directives = directives

        self.monthly_transactions = defaultdict(list)

        for directive in directives:
            if isinstance(directive, beandata.Transaction):
                if tx := self.convert_transaction(directive):
                    self.monthly_transactions[tx.month].append(tx)

        # Load our budget data store
        if self.spec.storage.exists():
            with self.spec.storage.open("r") as storage_f:
                # we want to keep the store private and expose methods on Budget to ensure
                # we can re-run validation and refresh all the MonthlyTotals and so on as
                # required
                self._store = BudgetStore.load(storage_f, self.spec.zero)
        else:
            self._store = get_store_converter(self.spec.zero).structure(
                dict(assigned=dict()), BudgetStore
            )

        for month, assignments in self._store.assigned.items():
            for cat in assignments.categories.keys():
                if cat not in self.spec.all_category_keys:
                    raise ValueError(
                        f"Budgeted amount for non-existent category '{cat}' found in {month}"
                    )

        # Calculate monthly totals from transaction and budgeting data
        self.monthly_totals: dict[Month, MonthlyTotals] = dict()
        self.update_monthly_totals()

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

        btx = BudgetTransaction(tx.date, flow, spending)
        if btx.funding < self.spec.zero:
            raise ValueError(f"Negative funding for transaction {tx}")

        return btx

    @property
    def ledger_start_month(self):
        return min(self.monthly_transactions.keys())

    @property
    def latest_budget_month(self):
        self._store.prune()
        if len(self._store.assigned) > 0:
            return max(self._store.assigned.keys())
        else:
            return Month.now()

    @property
    def latest_month(self):
        return max(
            Month.now() + 1,
            self.latest_budget_month + 1,
            max(self.monthly_transactions.keys()),
        )

    def update_monthly_totals(self, from_month: Month | None = None):
        month = from_month or self.ledger_start_month
        while month <= self.latest_month:
            if month == self.ledger_start_month:
                self.monthly_totals[month] = MonthlyTotals.from_transactions(
                    self.spec,
                    self.monthly_transactions[self.ledger_start_month],
                    self._store.assigned[self.ledger_start_month].held,
                    self._store.assigned[self.ledger_start_month].categories,
                )
            else:
                self.monthly_totals[month] = MonthlyTotals.from_transactions(
                    self.spec,
                    self.monthly_transactions[month],
                    self._store.assigned[month].held,
                    self._store.assigned[month].categories,
                    prev_month=self.monthly_totals[month - 1],
                )
            month += 1

    def update_assigned_amount(
        self, month: Month, category: CategoryKey, amount: amt.Amount
    ):
        self._store.assigned[month].categories[category] = amount
        self.update_monthly_totals(from_month=month)
        self._store.save(self.spec.storage, self.spec.zero)
