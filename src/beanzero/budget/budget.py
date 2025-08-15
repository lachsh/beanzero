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
    CategoryKey,
    Month,
)
from beanzero.budget.store import BudgetStore


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
        self.latest_month = max(self.monthly_transactions.keys()) + 1

        # Load our budget data store
        with self.spec.storage.open("r") as storage_f:
            # we want to keep the store private and expose methods on Budget to ensure
            # we can re-run validation and refresh all the MonthlyTotals and so on as
            # required
            self._store = BudgetStore.load(storage_f, self.spec.zero)

        # Calculate monthly totals from transaction and budgeting data
        self.monthly_totals: dict[Month, MonthlyTotals] = dict()

        self.monthly_totals[self.spec.start] = MonthlyTotals(
            spec=self.spec,
            previous_tba=self.spec.zero,
            previous_holding=self.spec.zero,
            previous_overspending=self.spec.zero,
            funding=self.aggregate_funding(self.monthly_transactions[self.spec.start]),
            holding=self._store.assigned[self.spec.start].held,
            carryover=defaultdict(lambda: self.spec.zero),
            spending=self.aggregate_spending(
                self.monthly_transactions[self.spec.start]
            ),
            budgeting=self._store.assigned[self.spec.start].categories,
        )

        month = self.spec.start + 1
        while month <= self.latest_month:
            prev = self.monthly_totals[month - 1]
            self.monthly_totals[month] = MonthlyTotals(
                spec=self.spec,
                previous_tba=prev.to_be_assigned,
                previous_holding=prev.holding,
                previous_overspending=prev.overspending,
                funding=self.aggregate_funding(self.monthly_transactions[month]),
                holding=self._store.assigned[month].held,
                carryover=prev.carryover_balances,
                spending=self.aggregate_spending(self.monthly_transactions[month]),
                budgeting=self._store.assigned[month].categories,
            )
            month += 1

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
