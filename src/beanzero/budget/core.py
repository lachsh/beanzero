from __future__ import annotations

import datetime
import functools
import operator
from decimal import Decimal

import beancount.core.amount as amt
import beancount.core.data as beandata
from attrs import define

from beanzero.budget.spec import BudgetSpec, CategoryGroup, CategoryMap, Month


@define(frozen=True)
class BudgetTransaction:
    """The budget-relevant data corresponding to a single Beancount transaction.

    Spending represents money leaving the budget, and so should be usually negative.

    Governed by the equation flow(+/-) = funding(+) + spending(-)
    """

    date: datetime.date
    flow: amt.Amount
    spending: CategoryMap

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

    @classmethod
    def from_beancount_tx(
        cls, spec: BudgetSpec, tx: beandata.Transaction
    ) -> BudgetTransaction | None:
        # Scan through postings for overall budget flow
        flow = spec.zero
        budget_accounts = set()
        for posting in tx.postings:
            if spec.is_budget_acccount(posting.account):
                if posting.units is None:
                    raise ValueError("Null posting")
                budget_accounts.add(posting.account)
                flow = amt.add(flow, posting.units)

        # If there's no net budget inflow or outflow, then this transaction isn't
        # relevant to the budget
        if flow == spec.zero:
            return None

        # If there's flow, then calculate any spending
        spending = spec.category_map()
        for posting in tx.postings:
            if cat := spec.get_account_category(posting.account):
                if cat in budget_accounts:
                    raise ValueError(
                        f"Account {cat} cannot be budget account and budget category"
                    )
                if posting.units is None:
                    raise ValueError("Null posting")

                spending[cat] = amt.sub(spending[cat], posting.units)

        btx = BudgetTransaction(tx.date, flow, spending)
        if btx.funding < spec.zero:
            raise ValueError(f"Negative funding for transaction {tx}")

        return btx


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
    previous_carryover: CategoryMap
    spending: CategoryMap
    assigning: CategoryMap

    @staticmethod
    def aggregate_funding(spec: BudgetSpec, txs: list[BudgetTransaction]):
        return functools.reduce(
            amt.add, map(operator.attrgetter("funding"), txs), spec.zero
        )

    @staticmethod
    def aggregate_spending(spec: BudgetSpec, txs: list[BudgetTransaction]):
        spending = spec.category_map()
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
        assigning: CategoryMap,
        prev_month: MonthlyTotals | None = None,
    ) -> MonthlyTotals:
        if prev_month is None:
            previous_tba = spec.zero
            previous_holding = spec.zero
            previous_overspending = spec.zero
            carryover = spec.category_map()
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
    def category_balances(self) -> CategoryMap:
        balances = self.spec.category_map()
        for key in self.spec.all_category_keys:
            balances[key] = self.previous_carryover[key]
            balances[key] = amt.add(balances[key], self.spending[key])
            balances[key] = amt.add(balances[key], self.assigning[key])
        return balances

    @property
    def carryover_balances(self) -> CategoryMap:
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
