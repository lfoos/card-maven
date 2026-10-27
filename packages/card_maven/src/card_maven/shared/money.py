"""Money as integer minor units plus an ISO 4217 currency code. Floats are never used."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from functools import total_ordering

from card_maven.shared.errors import InvalidInputError

_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")

# Minor-unit exponents for currencies that differ from the default of 2.
_EXPONENTS: dict[str, int] = {"JPY": 0, "KRW": 0}
_DEFAULT_EXPONENT = 2


def currency_exponent(currency: str) -> int:
    return _EXPONENTS.get(currency, _DEFAULT_EXPONENT)


@total_ordering
@dataclass(frozen=True, slots=True)
class Money:
    amount_minor: int
    currency: str

    def __post_init__(self) -> None:
        # bool is a subclass of int; reject it explicitly.
        if isinstance(self.amount_minor, bool) or not isinstance(self.amount_minor, int):
            raise InvalidInputError("amount_minor must be an integer", field="amount_minor")
        if not isinstance(self.currency, str) or not _CURRENCY_RE.match(self.currency):
            raise InvalidInputError(
                "currency must be a 3-letter uppercase ISO 4217 code", field="currency"
            )

    @classmethod
    def from_decimal(cls, amount: Decimal | str | int, currency: str) -> Money:
        """Build from a major-unit amount, e.g. ``Money.from_decimal("12.34", "USD")``.

        Rounds half-to-even when the input has more precision than the currency.
        """
        try:
            value = Decimal(amount)
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise InvalidInputError(f"not a decimal amount: {amount!r}", field="amount") from exc
        if not value.is_finite():
            raise InvalidInputError("amount must be finite", field="amount")
        exponent = currency_exponent(currency)
        minor = (value * (Decimal(10) ** exponent)).quantize(Decimal(1), rounding=ROUND_HALF_EVEN)
        return cls(int(minor), currency)

    def to_decimal(self) -> Decimal:
        exponent = currency_exponent(self.currency)
        return Decimal(self.amount_minor).scaleb(-exponent)

    @property
    def is_negative(self) -> bool:
        return self.amount_minor < 0

    def _require_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise InvalidInputError(
                f"currency mismatch: {self.currency} vs {other.currency}", field="currency"
            )

    def __add__(self, other: object) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same_currency(other)
        return Money(self.amount_minor + other.amount_minor, self.currency)

    def __sub__(self, other: object) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same_currency(other)
        return Money(self.amount_minor - other.amount_minor, self.currency)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Money):
            return NotImplemented
        self._require_same_currency(other)
        return self.amount_minor < other.amount_minor

    def __str__(self) -> str:
        exponent = currency_exponent(self.currency)
        return f"{self.to_decimal():.{exponent}f} {self.currency}"
