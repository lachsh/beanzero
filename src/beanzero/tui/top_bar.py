import gettext
import typing

import beancount.core.amount as amt
from textual.app import App, ComposeResult, RenderResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Digits, Static

from beanzero.budget import Month, MonthlyTotals
from beanzero.tui.interface import BeanZeroAppInterface

_ = gettext.gettext


class Calendar(Widget):
    app: BeanZeroAppInterface

    class CalendarMonth(Widget):
        app: BeanZeroAppInterface

        def __init__(self, month: int):
            super().__init__()
            self.month = month

        def render(self) -> RenderResult:
            if self.month in [1, 3, 5, 8, 10, 12]:
                self.add_class("odd")
            return self.app.spec.text_locale.months["format"]["abbreviated"][self.month]

        def on_click(self):
            self.app.action_set_month(self.month)  # type: ignore

    def on_mount(self):
        self.watch(self.app, "current_month", self.app_watch_current_month)

    def app_watch_current_month(self, new):
        self.query_one("#year", Static).update(str(new.year))
        months = self.query(self.CalendarMonth)
        for i, month in enumerate(months):
            month.remove_class("active")

            if (
                Month(i + 1, new.year) > self.app.budget.latest_month
                or Month(i + 1, new.year) < self.app.budget.ledger_start_month
            ):
                month.disabled = True
            else:
                month.disabled = False

            if new.year == Month.now().year and i + 1 == Month.now().month:
                month.add_class("current")
            else:
                month.remove_class("current")

        months[new.month - 1].add_class("active")

    def compose(self) -> ComposeResult:
        yield Static("YYYY", id="year")
        for i in range(1, 13):
            yield self.CalendarMonth(i)


class TbaSummary(Widget):
    app: BeanZeroAppInterface

    def on_mount(self):
        self.watch(self.app, "current_totals", self.app_watch_current_totals)

    def app_watch_current_totals(self, new: MonthlyTotals | None):
        if new is None:
            return
        new_previous = amt.add(
            amt.add(new.previous_tba, new.previous_holding), new.previous_overspending
        )
        self.query_one("#previous", Static).update(
            self.app.spec.format_currency(new_previous)
        )
        self.query_one("#funded", Static).update(
            self.app.spec.format_currency(new.funding)
        )
        self.query_one("#assigned", Static).update(
            self.app.spec.format_currency(-new.total_assigning)
        )

    def compose(self) -> ComposeResult:
        yield Static(_("From previous"), classes="key")
        yield Static("...", classes="value", id="previous")
        yield Static(_("Funded"), classes="key")
        yield Static("...", classes="value", id="funded")
        yield Static(_("Assigned"), classes="key")
        yield Static("...", classes="value", id="assigned")


class ToBeAssigned(Widget):
    app: BeanZeroAppInterface

    def on_mount(self):
        self.watch(self.app, "current_totals", self.app_watch_current_totals)

    def app_watch_current_totals(self, new: MonthlyTotals | None):
        if new is None:
            return
        tba = new.to_be_assigned
        if tba < self.app.spec.zero:
            self.add_class("negative")
        else:
            self.remove_class("negative")
        digits = self.query_one("#tba-digits", Digits)
        digits.update(
            self.app.spec.format_currency(new.to_be_assigned, symbol_override=False)
        )

    def compose(self) -> ComposeResult:
        yield Static(_("TBA"), id="tba-left-label")
        yield Digits("...", id="tba-digits")


class TopBar(Widget):
    def compose(self) -> ComposeResult:
        yield Calendar()
        yield TbaSummary()
        yield ToBeAssigned(classes="negative")
