import gettext
from decimal import Decimal, InvalidOperation

import beancount.core.amount as amt
from rich.text import Text
from textual.app import ComposeResult, RenderResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, Digits, Input, Static

import beanzero.budget.spec as spec
from beanzero.budget.budget import MonthlyTotals
from beanzero.tui.interface import BeanZeroAppInterface

_ = gettext.gettext

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


class HeldRow(Widget):
    assigned: reactive[amt.Amount | None] = reactive(None, recompose=True)
    editing_assigned: reactive[bool] = reactive(False, init=False)

    BINDINGS = [
        Binding(
            "enter",
            "edit_assigned()",
            _("Assign"),
            tooltip=_("Edit amount held for next month."),
        ),
        Binding(
            "=",
            "edit_assigned('=')",
            _("Set assigned"),
            tooltip=_("Set amount held for next month."),
        ),
        Binding(
            "+",
            "edit_assigned('+')",
            _("Assign more"),
            tooltip=_("Increase amount held for next month."),
        ),
        Binding(
            "-",
            "edit_assigned('-')",
            _("Assign less"),
            tooltip=_("Decrease amount held for next month."),
        ),
    ]

    def __init__(self, **kwargs):
        self.can_focus = True
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield Static(
            _("Held for next month"), classes="category-table--held-description"
        )
        input = Input(classes="category-table--held-assigned", select_on_focus=False)
        input.styles.display = "none"
        yield input
        static = Static(
            self.app.spec.format_currency(self.assigned or self.app.spec.zero),
            classes="category-table--held-assigned",
        )
        if self.assigned is None or self.assigned == self.app.spec.zero:
            static.add_class("zero")
        yield static

    def on_mount(self):
        self.watch(self.app, "current_totals", self.app_watch_current_totals)

    def app_watch_current_totals(self, new: MonthlyTotals | None):
        if new is None:
            return
        else:
            self.assigned = new.holding

    async def watch_editing_assigned(self, on):
        #  if we're enabling editing, then focus the input box
        if on:
            self.query_one(
                "Input.category-table--held-assigned"
            ).styles.display = "block"
            self.query_one(
                "Static.category-table--held-assigned"
            ).styles.display = "none"
            self.add_class("editing")
            self.query_one(Input).focus()

        # otherwise extract the value and return to display
        else:
            self.query_one(
                "Input.category-table--held-assigned"
            ).styles.display = "none"
            self.query_one(
                "Static.category-table--held-assigned"
            ).styles.display = "block"

            new_input = self.query_one(Input).value
            if new_input != "":
                try:
                    if new_input.startswith("+") or new_input.startswith("-"):
                        new_value = self.app.current_totals.holding.number + Decimal(
                            new_input
                        )
                    elif new_input.startswith("="):
                        new_value = Decimal(new_input[1:])
                    else:
                        new_value = Decimal(new_input)
                    new_assigned = amt.Amount(new_value, self.app.spec.currency)

                    if not self.app.spec.is_amount_suitable_precision(new_assigned):
                        self.app.notify(
                            f"Amount {new_assigned} is too high precision for this budget",
                            title="Assignment unchanged",
                            severity="warning",
                        )
                    else:
                        self.app.action_set_held(new_assigned)

                except InvalidOperation:
                    self.app.notify(
                        f"Couldn't parse '{new_input}'",
                        title="Assignment unchanged",
                        severity="warning",
                    )

            await self.recompose()
            self.focus()
            self.remove_class("editing")

    def on_descendant_blur(self, event):
        self.editing_assigned = False

    def on_input_submitted(self, event):
        self.editing_assigned = False

    def action_edit_assigned(self, prepend: str | None = None):
        if prepend is not None:
            self.query_one(Input).value = prepend
        self.editing_assigned = True


class CategoryRow(Widget):
    app: BeanZeroAppInterface
    name: reactive[str] = reactive("", recompose=True)
    assigned: reactive[amt.Amount | None] = reactive(None, recompose=True)
    spending: reactive[amt.Amount | None] = reactive(None, recompose=True)
    balance: reactive[amt.Amount | None] = reactive(None, recompose=True)

    editing_assigned: reactive[bool] = reactive(False, init=False)

    BINDINGS = [
        Binding(
            "enter",
            "edit_assigned()",
            _("Assign"),
            tooltip=_("Edit amount assigned to category."),
        ),
        Binding(
            "=",
            "edit_assigned('=')",
            _("Set assigned"),
            tooltip=_("Set amount assigned to category."),
        ),
        Binding(
            "+",
            "edit_assigned('+')",
            _("Assign more"),
            tooltip=_("Increase amount assigned to category."),
        ),
        Binding(
            "-",
            "edit_assigned('-')",
            _("Assign less"),
            tooltip=_("Decrease amount assigned to category."),
        ),
    ]

    def __init__(self, category_key, **kwargs):
        self.can_focus = True
        self.category_key = category_key
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield Static(self.name, classes="category-table--col-name")
        input = Input(classes="category-table--col-assigned", select_on_focus=False)
        input.styles.display = "none"
        yield input
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

    async def watch_editing_assigned(self, on):
        #  if we're enabling editing, then focus the input box
        if on:
            self.query_one(
                "Input.category-table--col-assigned"
            ).styles.display = "block"
            self.query_one(
                "Amount.category-table--col-assigned"
            ).styles.display = "none"
            self.add_class("editing")
            self.query_one(Input).focus()

        # otherwise extract the value and return to display
        else:
            self.query_one("Input.category-table--col-assigned").styles.display = "none"
            self.query_one(
                "Amount.category-table--col-assigned"
            ).styles.display = "block"

            new_input = self.query_one(Input).value
            if new_input != "":
                try:
                    if new_input.startswith("+") or new_input.startswith("-"):
                        new_value = self.app.current_totals.assigning[
                            self.category_key
                        ].number + Decimal(new_input)
                    elif new_input.startswith("="):
                        new_value = Decimal(new_input[1:])
                    else:
                        new_value = Decimal(new_input)
                    new_assigned = amt.Amount(new_value, self.app.spec.currency)

                    if not self.app.spec.is_amount_suitable_precision(new_assigned):
                        self.app.notify(
                            f"Amount {new_assigned} is too high precision for this budget",
                            title="Assignment unchanged",
                            severity="warning",
                        )
                    else:
                        self.app.action_set_assigned(self.category_key, new_assigned)

                except InvalidOperation:
                    self.app.notify(
                        f"Couldn't parse '{new_input}'",
                        title="Assignment unchanged",
                        severity="warning",
                    )

            await self.recompose()
            self.focus()
            self.remove_class("editing")

    def on_descendant_blur(self, event):
        self.editing_assigned = False

    def on_input_submitted(self, event):
        self.editing_assigned = False

    def action_edit_assigned(self, prepend: str | None = None):
        if prepend is not None:
            self.query_one(Input).value = prepend
        self.editing_assigned = True


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
            yield CategoryRow(category.key)

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
        yield HeldRow()
        with Horizontal(id="column-titles"):
            yield Static(_("Name"), classes="category-table--col-name")
            yield Static(_("Assigned"), classes="category-table--col-assigned")
            yield Static(_("Spent"), classes="category-table--col-spending")
            yield Static(_("Balance"), classes="category-table--col-balance")
        with Vertical(id="categories"):
            for group in self.app.spec.groups:
                yield CategoryGroup(group)
