from pathlib import Path

import pytest


@pytest.fixture
def data_dir():
    path = Path(__file__).parent / "data"
    return path.resolve()
