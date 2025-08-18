import beancount.core.amount as amt
from rich.text import Text
from textual.app import ComposeResult, RenderResult
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, Digits, Static

import beanzero.budget.spec as spec
from beanzero.budget.budget import MonthlyTotals
from beanzero.tui.interface import BeanZeroAppInterface

PL_PILL_LEFT = "\ue0b6"
PL_PILL_RIGHT = "\ue0b4"


class AvailableBubble(Widget):
    can_focus = False

    amount = reactive("0.00")
    goal_progress: reactive[float | None] = reactive(None)

    def render(self) -> RenderResult:
        text = "$text"
        if self.amount == "0.00":
            bg = "$background-lighten-2"
            fg = None
            text = "$foreground-muted"
            sym = None
        elif self.amount.startswith("-"):
            bg = "$error"
            fg = "$error-lighten-3"
            sym = "!"
        elif self.goal_progress == 1.0 or (
            self.amount != "0.00" and self.goal_progress is None
        ):
            bg = "$success"
            fg = "$success-lighten-3"
            sym = "✔" if self.goal_progress == 1.0 else None
        elif self.goal_progress and self.goal_progress <= 1.0:
            bg = "$warning"
            fg = "$text-muted"
            sym = "⣴"
        else:
            raise ValueError

        bubble_markup = (
            f"[{bg}]{PL_PILL_LEFT}[/]"
            + (f"[{fg} on {bg}]{sym} [/]" if sym else "")
            + f"[{text} on {bg}]$amount[/]"
            + f"[{bg}]{PL_PILL_RIGHT}[/]"
        )

        return Content.from_markup(bubble_markup, amount=self.amount)

    def on_click(self):
        self.amount = "0.00"


class Amount(Widget):
    app: BeanZeroAppInterface

    amount: amt.Amount

    def __init__(self, amount: amt.Amount, **kwargs):
        self.amount = amount
        super().__init__(**kwargs)

    def render(self) -> RenderResult:
        if self.amount == self.app.spec.zero:
            self.add_class("zero")
        else:
            self.remove_class("zero")

        if self.amount is not None:
            return self.app.spec.format_currency(self.amount)
        else:
            return ""


class CategoryGroupHeader(Widget):
    app: BeanZeroAppInterface
    name: reactive[str] = reactive("", recompose=True)
    assigned: reactive[amt.Amount | None] = reactive(None, recompose=True)
    spending: reactive[amt.Amount | None] = reactive(None, recompose=True)
    balance: reactive[amt.Amount | None] = reactive(None, recompose=True)

    def compose(self) -> ComposeResult:
        yield Static(self.name, classes="category-table--col-name")
        yield Amount(
            (self.assigned or self.app.spec.zero),
            classes="category-table--col-assigned",
        )
        yield Amount(
            (self.spending or self.app.spec.zero),
            classes="category-table--col-spending",
        )
        yield Amount(
            (self.balance or self.app.spec.zero), classes="category-table--col-balance"
        )


class CategoryGroup(Widget):
    can_focus = True

    group: spec.CategoryGroup

    def __init__(self, group: spec.CategoryGroup, **kwargs):
        self.group = group
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield CategoryGroupHeader()

    def on_mount(self):
        self.watch(self.app, "current_totals", self.app_watch_current_totals)
        self.query_one(CategoryGroupHeader).name = self.group.name

    def app_watch_current_totals(self, new: MonthlyTotals | None):
        if new is None:
            return

        self.query_one(CategoryGroupHeader).assigned = new.group_assigned(self.group)
        self.query_one(CategoryGroupHeader).spending = new.group_spending(self.group)
        self.query_one(CategoryGroupHeader).balance = new.group_balance(self.group)


class CategoryTable(Widget):
    app: BeanZeroAppInterface

    def compose(self) -> ComposeResult:
        for group in self.app.spec.groups:
            yield CategoryGroup(group)
