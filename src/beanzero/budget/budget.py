from __future__ import annotations

import datetime
import functools
import operator
import os
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

import beancount.core.amount as amt
import beancount.core.data as beandata
import beancount.loader
from attrs import define

from beanzero.budget.core import BudgetTransaction, MonthlyTotals
from beanzero.budget.spec import (
    BudgetSpec,
    CategoryGroup,
    CategoryKey,
    CategoryMap,
    Month,
)
from beanzero.budget.store import BudgetStore, get_store_converter


class Budget:
    """Combines all data sources to calculate budget data.

    Loads the budget spec from the config file, the transaction data from the beancount
    ledger, and the stored budget amounts from the data JSON file.

    Iterates over months to calculate per-category and overall balances and totals.
    """

    def __init__(self, spec_path: Path | str):
        spec_path = Path(spec_path)
        old_cwd = os.getcwd()
        os.chdir(spec_path.parent)
        with spec_path.relative_to(spec_path.parent).open("r") as spec_f:
            self.spec = BudgetSpec.load(spec_f)
        os.chdir(old_cwd)

        # Load the beancount data, and convert and categorise transactions by month
        directives, errors, options = beancount.loader.load_file(self.spec.ledger)
        self.beancount_directives = directives

        self.monthly_transactions = defaultdict(list)

        for directive in directives:
            if isinstance(directive, beandata.Transaction):
                if tx := BudgetTransaction.from_beancount_tx(self.spec, directive):
                    self.monthly_transactions[tx.month].append(tx)

        # Load our budget data store
        if self.spec.storage.exists():
            with self.spec.storage.open("r") as storage_f:
                # we want to keep the store private and expose methods on Budget to ensure
                # we can re-run validation and refresh all the MonthlyTotals and so on as
                # required
                self._store = BudgetStore.load(storage_f, self.spec)
        else:
            self._store = get_store_converter(self.spec).structure(
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
        self, month: Month, category: CategoryKey, amount: amt.Amount, save: bool = True
    ):
        self._store.assigned[month].categories[category] = amount
        self.update_monthly_totals(from_month=month)
        if save:
            self._store.save(self.spec.storage, self.spec.zero)

    def update_held_amount(self, month: Month, amount: amt.Amount, save: bool = True):
        self._store.assigned[month].held = amount
        self.update_monthly_totals(from_month=month)
        if save:
            self._store.save(self.spec.storage, self.spec.zero)
