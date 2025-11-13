import os
from pathlib import Path

import beancount as b
import pytest

from beanzero.budget.spec import BudgetSpec
from beanzero.budget.store import BudgetStore


def AUD(amount_str):
    return b.Amount(b.D(amount_str), "AUD")


ZERO = AUD("0.00")


@pytest.fixture
def data_dir():
    path = Path(__file__).parent / "data"
    return path.resolve()


@pytest.fixture
def spec(request, data_dir):
    filename = request.node.get_closest_marker("spec_file").args[0]
    cwd = os.getcwd()
    os.chdir(data_dir)
    with Path(filename).open("r") as spec_f:
        spec = BudgetSpec.load(spec_f)
    os.chdir(cwd)
    return spec


@pytest.fixture
def store(request, data_dir):
    filename = request.node.get_closest_marker("store_file").args[0]
    cwd = os.getcwd()
    os.chdir(data_dir)
    with Path(filename).open("r") as spec_f:
        store = BudgetStore.load(spec_f, ZERO)
    os.chdir(cwd)
    return store
