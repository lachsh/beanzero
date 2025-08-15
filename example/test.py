import IPython

from beanzero.budget import *

if __name__ == "__main__":
    with open("./budget.yml", "r") as f:
        budget_spec = BudgetSpec.load(f)
    budget = Budget(budget_spec)

    IPython.embed()
