from rich.text import Text
from textual.app import ComposeResult, RenderResult
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import DataTable, Digits, Static

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
    can_focus = False

    amount = reactive("0.00")

    def render(self) -> RenderResult:
        if self.amount == "0.00":
            self.add_class("zero")
        else:
            self.remove_class("zero")

        return self.amount

    def on_click(self):
        self.amount = "0.00"


class CategoryTable(Widget):
    def compose(self) -> ComposeResult:
        with Horizontal(classes="category-group"):
            yield Static("Core expenses")
            budgeted = Amount()
            budgeted.amount = "1234.34"
            yield budgeted
            activity = Amount()
            activity.amount = "-456.23"
            yield activity
            bubble = Amount()
            bubble.amount = "3245.23"
            yield bubble

        for i in range(7):
            with Horizontal():
                yield Static("Rent")
                budgeted = Amount()
                budgeted.amount = "1234.34"
                yield budgeted
                activity = Amount()
                activity.amount = "-456.23"
                yield activity
                bubble = AvailableBubble()
                bubble.amount = f"{(i - 2) * 567:0.2f}"
                if i == 3:
                    bubble.goal_progress = 0.5
                if i == 5:
                    bubble.goal_progress = 1.0
                yield bubble
