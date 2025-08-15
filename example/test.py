import IPython

from beanzero.budget import *

if __name__ == "__main__":
    budget = Budget("./budget.yml")
    IPython.embed()
