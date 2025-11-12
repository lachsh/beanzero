import pytest

from beanzero.budget.spec import Month


class TestMonth:
    def test_valid_month_checking(self):
        Month(1, 2025)
        Month(12, 1999)
        with pytest.raises(ValueError):
            Month(0, 1765)
        with pytest.raises(ValueError):
            Month(13, 2023)
        with pytest.raises(ValueError):
            Month(-1, 2007)

    def test_month_parsing(self):
        assert Month.from_string("2025-11") == Month(11, 2025)
        with pytest.raises(ValueError):
            Month.from_string("2025-13")
        with pytest.raises(ValueError):
            Month.from_string("01")
        with pytest.raises(ValueError):
            Month.from_string("1999-")

    def test_month_adding(self):
        assert Month(1, 2025) + 3 == Month(4, 2025)
        assert Month(6, 2001) + 12 == Month(6, 2002)
        assert Month(12, 1999) + 1 == Month(1, 2000)

    def test_month_subtracting_int(self):
        assert Month(4, 2025) - 3 == Month(1, 2025)
        assert Month(6, 2002) - 12 == Month(6, 2001)
        assert Month(1, 2000) - 1 == Month(12, 1999)

    def test_month_subtracting_month(self):
        assert Month(4, 2025) - Month(1, 2025) == 3
        assert Month(1, 2025) - Month(4, 2025) == -3
        assert Month(6, 2002) - Month(6, 2001) == 12
        assert Month(6, 2001) - Month(6, 2002) == -12
        assert Month(4, 2024) - Month(10, 2020) == 42
        assert Month(1, 2000) - Month(12, 1999) == 1
        assert Month(12, 1999) - Month(1, 2000) == -1

    def test_month_inequalities(self):
        assert Month(12, 1999) < Month(1, 2000)
        assert Month(1, 1999) <= Month(1, 1999) >= Month(1, 1999)
        assert Month(10, 2000) > Month(9, 2000)

    def test_month_iso_roundtrip(self):
        m = Month(12, 1999)
        assert m.from_string(m.as_iso()) == m
