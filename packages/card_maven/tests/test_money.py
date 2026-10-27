from decimal import Decimal

import pytest

from card_maven.shared.errors import InvalidInputError
from card_maven.shared.money import Money


class TestConstruction:
    def test_valid(self) -> None:
        money = Money(1234, "USD")
        assert money.amount_minor == 1234
        assert money.currency == "USD"

    @pytest.mark.parametrize("currency", ["usd", "US", "USDX", "", "U$D"])
    def test_rejects_bad_currency(self, currency: str) -> None:
        with pytest.raises(InvalidInputError, match="currency"):
            Money(100, currency)

    @pytest.mark.parametrize("amount", [1.5, "100", True, None])
    def test_rejects_non_integer_amount(self, amount: object) -> None:
        with pytest.raises(InvalidInputError, match="integer"):
            Money(amount, "USD")  # type: ignore[arg-type]

    def test_negative_allowed_but_flagged(self) -> None:
        assert Money(-1, "USD").is_negative
        assert not Money(0, "USD").is_negative


class TestDecimalConversion:
    @pytest.mark.parametrize(
        ("amount", "currency", "minor"),
        [
            ("12.34", "USD", 1234),
            ("0.01", "USD", 1),
            (5, "USD", 500),
            ("1000", "JPY", 1000),
            ("0.125", "USD", 12),  # half-even rounds down to the even cent
            ("0.135", "USD", 14),  # half-even rounds up to the even cent
        ],
    )
    def test_from_decimal(self, amount: str | int, currency: str, minor: int) -> None:
        assert Money.from_decimal(amount, currency).amount_minor == minor

    @pytest.mark.parametrize("amount", ["abc", "NaN", "Infinity", ""])
    def test_from_decimal_rejects_garbage(self, amount: str) -> None:
        with pytest.raises(InvalidInputError):
            Money.from_decimal(amount, "USD")

    def test_round_trip(self) -> None:
        assert Money(1999, "USD").to_decimal() == Decimal("19.99")
        assert Money(500, "JPY").to_decimal() == Decimal("500")

    def test_str(self) -> None:
        assert str(Money(1999, "USD")) == "19.99 USD"
        assert str(Money(500, "JPY")) == "500 JPY"


class TestArithmetic:
    def test_add_and_subtract(self) -> None:
        assert Money(100, "USD") + Money(250, "USD") == Money(350, "USD")
        assert Money(100, "USD") - Money(250, "USD") == Money(-150, "USD")

    def test_currency_mismatch(self) -> None:
        with pytest.raises(InvalidInputError, match="mismatch"):
            _ = Money(100, "USD") + Money(100, "CAD")
        with pytest.raises(InvalidInputError, match="mismatch"):
            _ = Money(100, "USD") < Money(100, "CAD")

    def test_ordering(self) -> None:
        assert Money(100, "USD") < Money(101, "USD")
        assert max(Money(5, "USD"), Money(9, "USD")) == Money(9, "USD")

    def test_non_money_operands(self) -> None:
        with pytest.raises(TypeError):
            _ = Money(100, "USD") + 5  # type: ignore[operator]
        with pytest.raises(TypeError):
            _ = Money(100, "USD") - 5  # type: ignore[operator]
        with pytest.raises(TypeError):
            _ = Money(100, "USD") < 5  # type: ignore[operator]

    def test_immutable(self) -> None:
        money = Money(100, "USD")
        with pytest.raises(AttributeError):
            money.amount_minor = 5  # type: ignore[misc]
