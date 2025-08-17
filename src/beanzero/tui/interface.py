from textual.app import App

from beanzero.budget import Budget, BudgetSpec, Month, MonthlyTotals


# for better type hinting of self.app without circular imports
class BeanZeroAppInterface(App):
    budget: Budget
    spec: BudgetSpec
    current_month: Month
    current_totals: MonthlyTotals | None
