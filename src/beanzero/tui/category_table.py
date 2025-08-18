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

    amount: amt.Amount

    def __init__(self, amount: amt.Amount, **kwargs):
        self.amount = amount
        super().__init__(**kwargs)

    def render(self) -> RenderResult:
        text = "$text"
        fg = None
        sym = None

        if self.amount == self.app.spec.zero:
            bg = "$background-lighten-2"
            text = "$foreground-muted"
        elif self.amount < self.app.spec.zero:
            bg = "$error"
            fg = "$text"
            sym = "!"
        else:
            bg = "$success"
            fg = "$text"

        bubble_markup = (
            f"[{bg}]{PL_PILL_LEFT}[/]"
            + (f"[{fg} on {bg}]{sym} [/]" if sym else "")
            + f"[{text} on {bg}]$amount[/]"
            + f"[{bg}]{PL_PILL_RIGHT}[/]"
        )

        return Content.from_markup(
            bubble_markup, amount=self.app.spec.format_currency(self.amount)
        )


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


class CategoryRow(Widget):
    app: BeanZeroAppInterface
    name: reactive[str] = reactive("", recompose=True)
    assigned: reactive[amt.Amount | None] = reactive(None, recompose=True)
    spending: reactive[amt.Amount | None] = reactive(None, recompose=True)
    balance: reactive[amt.Amount | None] = reactive(None, recompose=True)

    def __init__(self, **kwargs):
        self.can_focus = True
        super().__init__(**kwargs)

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
        yield AvailableBubble(
            (self.balance or self.app.spec.zero), classes="category-table--col-balance"
        )


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
    group: spec.CategoryGroup

    def __init__(self, group: spec.CategoryGroup, **kwargs):
        self.group = group
        self.can_focus = True
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield CategoryGroupHeader()
        for category in self.group.categories:
            yield CategoryRow()

    def on_mount(self):
        self.watch(self.app, "current_totals", self.app_watch_current_totals)
        self.query_one(CategoryGroupHeader).name = self.group.name
        for category, widget in zip(self.group.categories, self.query(CategoryRow)):
            widget.name = category.name

    def app_watch_current_totals(self, new: MonthlyTotals | None):
        if new is None:
            return

        self.query_one(CategoryGroupHeader).assigned = new.group_assigned(self.group)
        self.query_one(CategoryGroupHeader).spending = new.group_spending(self.group)
        self.query_one(CategoryGroupHeader).balance = new.group_balance(self.group)

        for category, widget in zip(self.group.categories, self.query(CategoryRow)):
            widget.assigned = new.assigning[category.key]
            widget.spending = new.spending[category.key]
            widget.balance = new.category_balances[category.key]


class CategoryTable(Widget):
    app: BeanZeroAppInterface

    def compose(self) -> ComposeResult:
        for group in self.app.spec.groups:
            yield CategoryGroup(group)
