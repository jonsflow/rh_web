"""
Option positions.

The one asset whose P&L has to be inferred. Futures is told its realized P&L by
the broker and stocks is proceeds minus cost, but an option position can end
three ways, and which one it is decides how it is valued:

  closed    opened and closed by orders. Worth the price difference, times the
            quantity, times a hundred shares a contract, with the sign flipped
            for a credit position because selling profits when the price falls.
  expired   opened and never closed, past its expiration. Worth the premium:
            lost if it was paid, kept if it was collected.
  orphaned  closed with no opening order in range -- the open predates the fetch
            window. It cannot be valued at all, so it is not valued: reporting
            the close as profit would invent money that was never made.

Spreads are skipped rather than handled. Valuing one at expiry means knowing
which strikes finished in the money, which has never been built, so a multi-leg
order produces no position.
"""

import datetime
import json
from typing import Any, Dict, List, Optional

from unified.models import Position

ASSET_TYPE = 'options'

# A contract is a hundred shares
CONTRACT_MULTIPLIER = 100


def build_positions(orders: List[Dict[str, Any]]) -> List[Position]:
    """Pair opening and closing orders per contract."""
    grouped: Dict[str, Dict[str, Any]] = {}

    for order in orders:
        if is_spread(order.get('strategy')):
            continue

        key = _position_key(order)
        if key not in grouped:
            grouped[key] = {
                'position_key': key,
                'account': order.get('account'),
                'symbol': order.get('symbol'),
                'expiration_date': order.get('expiration_date'),
                'strike_price': order.get('strike_price'),
                'option_type': order.get('option_type'),
                'strategy': order.get('strategy'),
                'direction': order.get('direction'),
                'contract_ids': _contract_ids(order),
                'opens': [],
                'closes': [],
            }

        side = 'opens' if order.get('position_effect') == 'open' else 'closes'
        grouped[key][side].append(order)

    return [_position(group) for group in grouped.values()]


def is_spread(strategy: Optional[str]) -> bool:
    """A multi-leg strategy, which is not paired into a position."""
    return bool(strategy) and '_spread' in strategy.lower()


def _position_key(order: Dict[str, Any]) -> str:
    """What makes one contract in one account one position.

    The account is part of the key, not a filter applied afterwards: one
    account's opening order cannot be closed by another's, so there is no path
    through here that pairs across accounts.
    """
    return '_'.join(str(part) for part in (
        order.get('account'),
        order.get('symbol'),
        order.get('contract_ids'),
        order.get('expiration_date'),
        order.get('strike_price'),
    ))


def _contract_ids(order: Dict[str, Any]) -> List[str]:
    ids = order.get('contract_ids')
    if isinstance(ids, str):
        try:
            return json.loads(ids)
        except ValueError:
            return []
    return ids or []


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _position(group: Dict[str, Any]) -> Position:
    """One contract's orders, aggregated, classified and valued."""
    opens, closes = group['opens'], group['closes']

    position = Position(
        asset_type=ASSET_TYPE,
        position_key=group['position_key'],
        account=group['account'],
        symbol=group['symbol'],
        root_symbol=group['symbol'],
        expiration_date=group['expiration_date'],
        strike_price=group['strike_price'],
        option_type=group['option_type'],
        strategy=group['strategy'],
        direction=group['direction'],
        contract_ids=group['contract_ids'],
        quantity=0,
    )

    if opens:
        quantity = sum(_number(order, 'quantity') for order in opens)
        position.quantity = quantity
        position.open_date = min(order['created_at'] for order in opens)
        position.open_price = _weighted_price(opens, quantity)
        position.open_value = sum(_number(order, 'gross_amount') for order in opens)

    if closes:
        close_quantity = sum(_number(order, 'quantity') for order in closes)
        position.close_date = max(order['created_at'] for order in closes)
        position.close_price = _weighted_price(closes, close_quantity)
        position.close_value = sum(_number(order, 'gross_amount') for order in closes)

    position.fees = round(sum(_number(order, 'fees')
                              for order in opens + closes), 4)

    return _value(position, bool(opens), bool(closes))


def _value(position: Position, has_open: bool, has_close: bool) -> Position:
    """Decide what the position is, and what it came to."""
    # A close with no open cannot be valued: the premium paid to open it is not
    # in the data, so any figure would be invented
    if has_close and not has_open:
        position.status = 'orphaned'
        position.pnl = None
        position.pnl_no_fees = None
        return position

    if has_open and has_close:
        position.status = 'closed'
        position.pnl_no_fees = _closed_pnl(position)
    elif has_open and _is_expired(position.expiration_date):
        position.status = 'expired'
        position.pnl_no_fees = _expired_pnl(position)
        # It ended on its expiration date, worth nothing
        position.close_date = position.expiration_date
        position.close_price = 0.0
        position.close_value = 0.0
    else:
        position.status = 'open'
        position.pnl_no_fees = None

    if position.pnl_no_fees is None:
        position.pnl = None
    else:
        position.pnl_no_fees = round(position.pnl_no_fees, 2)
        position.pnl = round(position.pnl_no_fees - (position.fees or 0), 2)

    return position


def _closed_pnl(position: Position) -> Optional[float]:
    """What a position closed by orders came to, before fees."""
    if (position.open_price is None or position.close_price is None
            or not position.quantity):
        # Without both prices the premiums are what there is
        return (position.open_value or 0) + (position.close_value or 0)

    moved = (position.close_price - position.open_price) * position.quantity
    moved *= CONTRACT_MULTIPLIER

    # A credit position was sold to open, so it profits when the price falls
    return -moved if position.direction == 'credit' else moved


def _expired_pnl(position: Position) -> float:
    """What a position that expired worthless came to, before fees."""
    premium = position.open_value
    if not premium:
        return 0.0

    if position.direction == 'debit':
        # Paid for it, and it expired worthless
        return -abs(premium)
    if position.direction == 'credit':
        # Collected the premium and kept it
        return abs(premium)
    return 0.0


def _is_expired(expiration_date: Optional[str]) -> bool:
    if not expiration_date:
        return False
    try:
        expiry = datetime.datetime.strptime(expiration_date, '%Y-%m-%d')
    except ValueError:
        return False
    return expiry < datetime.datetime.now()


def _weighted_price(orders: List[Dict[str, Any]], quantity: float) -> Optional[float]:
    if not quantity:
        return None
    paid = sum(_number(order, 'price') * _number(order, 'quantity')
               for order in orders)
    return paid / quantity


def _number(order: Dict[str, Any], field: str) -> float:
    value = order.get(field)
    return float(value) if value is not None else 0.0
