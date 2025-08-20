import argparse
import gettext
from pathlib import Path

import beancount.core.amount as amt
from textual.app import App, ComposeResult
from textual.reactive import reactive
from textual.widgets import Footer, Header

from beanzero.budget import Budget, BudgetSpec, Month
from beanzero.budget.budget import MonthlyTotals
from beanzero.budget.spec import CategoryKey
from beanzero.tui.category_table import CategoryTable
from beanzero.tui.top_bar import TopBar

_ = gettext.gettext


class BeanZeroApp(App):
    TITLE = "Bean0"
    CSS_PATH = "bean_zero.tcss"

    BINDINGS = [
        ("{", "change_month(-12)", _("Previous year")),
        ("}", "change_month(12)", _("Next year")),
        ("[", "change_month(-1)", _("Previous month")),
        ("]", "change_month(1)", _("Next month")),
    ]

    budget: Budget
    spec: BudgetSpec

    current_month: reactive[Month] = reactive(Month.now())
    current_totals: reactive[MonthlyTotals | None] = reactive(None)

    def __init__(self):
        super().__init__()
        parser = argparse.ArgumentParser()
        parser.add_argument("config_file", type=Path)
        args = parser.parse_args()
        self.budget = Budget(args.config_file)
        self.spec = self.budget.spec
        name = self.spec.name or args.config_file.stem
        self.sub_title = f"{name} [{self.spec.currency}]"
        if self.spec.theme:
            self.theme = self.spec.theme

    def validate_current_month(self, new: Month):
        if new < self.budget.ledger_start_month:
            return self.budget.ledger_start_month
        elif new > self.budget.latest_month:
            return self.budget.latest_month
        else:
            return new

    def watch_current_month(self, new: Month):
        self.current_totals = self.budget.monthly_totals[new]

    def action_change_month(self, delta: int):
        self.current_month += delta

    def action_set_month(self, new: int):
        self.current_month = Month(new, self.current_month.year)

    def action_set_assigned(self, key: CategoryKey, new_amount: amt.Amount):
        self.budget.update_assigned_amount(self.current_month, key, new_amount)
        self.current_totals = self.budget.monthly_totals[self.current_month]
        # just make sure we refresh everything
        self.mutate_reactive(BeanZeroApp.current_totals)
        self.mutate_reactive(BeanZeroApp.current_month)

    def compose(self) -> ComposeResult:
        yield Header()
        yield TopBar()
        yield CategoryTable()
        yield Footer()
