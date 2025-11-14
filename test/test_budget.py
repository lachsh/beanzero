import datetime

import beancount as b
import beancount.core.data as bd
import pytest

from beanzero.budget.budget import BudgetTransaction

from .conftest import AUD, ZERO


@pytest.fixture
def tx(*postings) -> bd.Transaction:
    return bd.Transaction(
        meta={},
        date=datetime.date.today(),
        flag="*",
        payee=None,
        narration=None,
        tags=frozenset(),
        links=frozenset(),
        postings=[],
    )


@pytest.mark.spec_file("sample-budget.yml")
class TestTransactionConversion:
    def test_simple_expense(self, spec, tx):
        bd.create_simple_posting(tx, "Expenses:Rent", b.D("200.00"), "AUD")
        bd.create_simple_posting(tx, "Assets:Checking", b.D("-200.00"), "AUD")
        btx = BudgetTransaction.from_beancount_tx(spec, tx)
        assert btx.flow == AUD("-200.00")
        assert btx.funding == ZERO
        assert btx.total_spending == AUD("-200.00")
        assert dict(btx.spending) == {"rent": AUD("-200.00")}

    def test_split_expense(self, spec, tx):
        bd.create_simple_posting(tx, "Expenses:Rent", b.D("120.00"), "AUD")
        bd.create_simple_posting(tx, "Expenses:Utilities", b.D("80.00"), "AUD")
        bd.create_simple_posting(tx, "Assets:Checking", b.D("-200.00"), "AUD")
        btx = BudgetTransaction.from_beancount_tx(spec, tx)
        assert btx.flow == AUD("-200.00")
        assert btx.funding == ZERO
        assert btx.total_spending == AUD("-200.00")
        assert dict(btx.spending) == {
            "rent": AUD("-120.00"),
            "utilities": AUD("-80.00"),
        }

    def test_simple_expense_refund(self, spec, tx):
        bd.create_simple_posting(tx, "Expenses:Rent", b.D("-200.00"), "AUD")
        bd.create_simple_posting(tx, "Assets:Checking", b.D("200.00"), "AUD")
        btx = BudgetTransaction.from_beancount_tx(spec, tx)
        assert btx.flow == AUD("200.00")
        assert btx.funding == ZERO
        assert btx.total_spending == AUD("200.00")
        assert dict(btx.spending) == {"rent": AUD("200.00")}

    def test_split_expense_with_negative(self, spec, tx):
        # TODO is this the functionality we actually want?
        bd.create_simple_posting(tx, "Income:Utility-Rebate", b.D("-50.00"), "AUD")
        bd.create_simple_posting(tx, "Expenses:Utilities", b.D("250.00"), "AUD")
        bd.create_simple_posting(tx, "Assets:Checking", b.D("-200.00"), "AUD")
        btx = BudgetTransaction.from_beancount_tx(spec, tx)
        assert btx.flow == AUD("-200.00")
        assert btx.funding == AUD("50.00")
        assert btx.total_spending == AUD("-250.00")
        assert dict(btx.spending) == {"utilities": AUD("-250.00")}

    def test_on_budget_transfer_is_skipped(self, spec, tx):
        bd.create_simple_posting(tx, "Assets:Savings", b.D("200.00"), "AUD")
        bd.create_simple_posting(tx, "Assets:Checking", b.D("-200.00"), "AUD")
        btx = BudgetTransaction.from_beancount_tx(spec, tx)
        assert btx is None

    def test_off_budget_transfer_is_skipped(self, spec, tx):
        bd.create_simple_posting(tx, "Assets:Off-Budget:Savings", b.D("200.00"), "AUD")
        bd.create_simple_posting(
            tx, "Assets:Off-Budget:Checking", b.D("-200.00"), "AUD"
        )
        btx = BudgetTransaction.from_beancount_tx(spec, tx)
        assert btx is None

    def test_transfer_and_expense(self, spec, tx):
        bd.create_simple_posting(tx, "Assets:Checking", b.D("-700.00"), "AUD")
        bd.create_simple_posting(tx, "Assets:Savings", b.D("500.00"), "AUD")
        bd.create_simple_posting(tx, "Assets:Investments", b.D("200.00"), "AUD")
        btx = BudgetTransaction.from_beancount_tx(spec, tx)
        assert btx.flow == AUD("-200.00")
        assert btx.funding == ZERO
        assert btx.total_spending == AUD("-200.00")
        assert dict(btx.spending) == {
            "investments": AUD("-200.00"),
        }

    def test_simple_income(self, spec, tx):
        bd.create_simple_posting(tx, "Assets:Checking", b.D("200.00"), "AUD")
        bd.create_simple_posting(tx, "Income:Salary", b.D("-200.00"), "AUD")
        btx = BudgetTransaction.from_beancount_tx(spec, tx)

        assert btx.flow == AUD("200.00")
        assert btx.funding == AUD("200.00")
        assert btx.total_spending == ZERO
        assert dict(btx.spending) == {}

    def test_split_income(self, spec, tx):
        bd.create_simple_posting(tx, "Assets:Checking", b.D("150.00"), "AUD")
        bd.create_simple_posting(tx, "Assets:Savings", b.D("30.00"), "AUD")
        bd.create_simple_posting(tx, "Expenses:Tax", b.D("20.00"), "AUD")
        bd.create_simple_posting(tx, "Income:Salary", b.D("-200.00"), "AUD")
        btx = BudgetTransaction.from_beancount_tx(spec, tx)

        assert btx.flow == AUD("180.00")
        assert btx.funding == AUD("180.00")
        assert btx.total_spending == ZERO
        assert dict(btx.spending) == {}

    def test_negative_income(self, spec, tx):
        bd.create_simple_posting(tx, "Assets:Checking", b.D("-200.00"), "AUD")
        bd.create_simple_posting(tx, "Income:Salary", b.D("200.00"), "AUD")

        # TODO probably want to implement a warnings system
        with pytest.raises(ValueError):
            btx = BudgetTransaction.from_beancount_tx(spec, tx)
