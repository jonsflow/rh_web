"""
Reading a figure out of a broker payload.

The three APIs disagree about how a number arrives: a float, a numeric string, an
object with an `amount`, a list of those, or absent. These helpers are what keep
that disagreement inside the models.
"""

from typing import Any, Optional


def to_float(value: Any) -> Optional[float]:
    """A number, or None when there isn't one.

    Absence stays absence: a missing price is not a price of zero.
    """
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        return to_float(value.get('amount'))
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def money(*values: Any) -> float:
    """Several fee-shaped fields added up, treating absence as nothing.

    Written for fields that arrive inconsistently even within one payload:
    options reports `regulatory_fees` as a numeric string and `sales_taxes` as an
    empty list when there are none.
    """
    total = 0.0
    for value in values:
        if isinstance(value, (list, tuple)):
            total += money(*value)
            continue
        amount = to_float(value)
        if amount is not None:
            total += amount
    return round(total, 4)
