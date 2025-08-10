from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widget import Widget
from textual.widgets import Digits, Static


class Calendar(Widget):
    def compose(self) -> ComposeResult:
        yield Static("2025", id="year")
        for i in range(1, 13):
            yield Static(
                f"{i:02d}",
                classes="month"
                + (" odd " if i in [2, 4, 6, 7, 9, 11] else "")
                + (" active" if i == 8 else ""),
            )


class TbbSummary(Widget):
    def compose(self) -> ComposeResult:
        yield Static("From previous", classes="key")
        yield Static("32.46", classes="value")
        yield Static("Inflows", classes="key")
        yield Static("2168.74", classes="value")
        yield Static("Budgeted", classes="key")
        yield Static("995.34", classes="value")


class ToBeBudgeted(Widget):
    def compose(self) -> ComposeResult:
        yield Static("T\nB\nB", id="tbb-left")
        yield Digits("0.00", id="tbb")


class TopBar(Widget):
    def compose(self) -> ComposeResult:
        yield Calendar()
        yield TbbSummary()
        yield ToBeBudgeted()
