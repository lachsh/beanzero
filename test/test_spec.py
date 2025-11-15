from decimal import Decimal

import beancount as b
import beancount.core.amount as amt
import pytest

from beanzero.budget.spec import CategoryMap, Month

from .conftest import AUD, ZERO


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


@pytest.mark.spec_file("sample-budget.yml")
class TestNormalBudgetSpec:
    def test_spec_name(self, spec):
        assert spec.name == "Personal Budget"

    def test_spec_theme(self, spec):
        assert spec.theme == "nord"

    def test_spec_currency(self, spec):
        assert spec.currency == "AUD"

    def test_spec_locale(self, spec):
        assert spec.locale == "en_AU"

    def test_ledger_is_found_relative(self, spec, data_dir):
        assert spec.ledger.resolve() == data_dir / "sample-budget.bean"

    def test_zero_matches_currency(self, spec):
        assert spec.zero == amt.Amount(Decimal("0"), "AUD")

    def test_basic_account_to_category(self, spec):
        assert spec.get_account_category("Expenses:Rent") == "rent"
        assert spec.get_account_category("Expenses:Car:Petrol") == "car"
        assert spec.get_account_category("Assets:Investments") == "investments"
        assert spec.get_account_category("Assets:Savings") is None
        assert spec.get_account_category("Expenses:Off-Budget") is None

    def test_all_category_keys(self, spec):
        assert spec.all_category_keys == [
            "rent",
            "utilities",
            "car",
            "eating-out",
            "hobbies",
            "investments",
            "rainy-day-fund",
        ]

    def test_loaded_groups(self, spec):
        assert len(spec.groups) == 3
        necessary = spec.groups[0]
        assert necessary.name == "Necessary expenses"
        assert len(necessary.categories) == 3
        assert necessary.categories[0].name == "Rent"

    def test_suitable_precision(self, spec):
        assert spec.is_amount_suitable_precision(amt.Amount(Decimal("1000.12"), "AUD"))
        assert not spec.is_amount_suitable_precision(
            amt.Amount(Decimal("999.999"), "AUD")
        )

    def test_currency_formatting(self, spec):
        assert (
            spec.format_currency(amt.Amount(Decimal("1123.45"), "AUD")) == "$1,123.45"
        )
        assert (
            spec.format_currency(amt.Amount(Decimal("-1123.45"), "AUD")) == "-$1,123.45"
        )


@pytest.mark.spec_file("sample-budget.yml")
class TestCategoryMap:
    def test_keys_match_categories(self, spec):
        m = spec.category_map()
        assert m.keys() == set(spec.all_category_keys)

    def test_initialise_values_to_zero(self, spec):
        for v in spec.category_map().values():
            assert v == ZERO

    def test_sets_initial_values(self, spec):
        m = CategoryMap.with_values(
            spec, {"car": AUD("200"), "investments": AUD("100")}
        )
        assert m["car"] == AUD("200")
        assert m["investments"] == AUD("100")
        assert m["hobbies"] == ZERO

    def test_reject_bad_keys_on_init(self, spec):
        with pytest.raises(KeyError):
            CategoryMap.with_values(spec, {"car": AUD("200"), "fake": AUD("100")})

    def test_reject_bad_keys_get_and_set(self, spec):
        with pytest.raises(KeyError):
            spec.category_map()["not-real"]

        with pytest.raises(KeyError):
            spec.category_map()["not-real"] = AUD("20")

    def test_reject_wrong_type(self, spec):
        with pytest.raises(ValueError):
            spec.category_map()["car"] = b.D("20")

    def test_reject_bad_currency(self, spec):
        with pytest.raises(ValueError):
            spec.category_map()["car"] = b.Amount(b.D("20"), "EUR")
