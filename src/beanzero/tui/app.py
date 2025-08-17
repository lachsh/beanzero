import argparse
from pathlib import Path

from textual.app import App, ComposeResult
from textual.reactive import reactive
from textual.widgets import Footer, Header

from beanzero.budget import Budget, BudgetSpec, Month
from beanzero.budget.budget import MonthlyTotals
from beanzero.tui.category import CategoryTable
from beanzero.tui.top_bar import TopBar


class BeanZeroApp(App):
    TITLE = "Bean0"
    CSS_PATH = "bean_zero.tcss"

    BINDINGS = [
        ("{", "change_month(-12)", "Previous year"),
        ("}", "change_month(12)", "Next year"),
        ("[", "change_month(-1)", "Previous month"),
        ("]", "change_month(1)", "Next month"),
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

    def compose(self) -> ComposeResult:
        yield Header()
        yield TopBar()
        # yield CategoryTable()
        yield Footer()
