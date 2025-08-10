from textual.app import App, ComposeResult
from textual.widgets import Footer, Header

from beanzero.tui.top_bar import TopBar


class BeanZeroApp(App):
    TITLE = "Bean0"
    SUB_TITLE = "Zero-based budgeting for beancount"
    CSS_PATH = "bean_zero.tcss"

    def compose(self) -> ComposeResult:
        yield Header()
        yield TopBar()
        yield Footer()
