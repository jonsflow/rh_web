"""
Futures positions.

Orders on one contract in one account are one position: the opening fills set the
entry, the closing fills end it. Nothing here calculates P&L -- the broker reports
realized P&L per order, before and after fees, and this sums what it gave.

A contract closed with no opening order in range is recorded too, as orphaned:
the entry predates the window we fetched. Unlike options, its P&L is still known,
because the broker reported it rather than it having to be inferred from the entry
price. Which statuses count toward a P&L figure is the reader's decision.
"""

import json
from typing import Any, Dict, List

from unified.models import Position

ASSET_TYPE = 'futures'


def build_positions(orders: List[Dict[str, Any]]) -> List[Position]:
    """Pair opening and closing orders per contract."""
    grouped: Dict[tuple, Dict[str, Any]] = {}

    for order in orders:
        # Keyed by account as well as contract: one account's opening order
        # cannot be closed by another's, so they are separate positions
        key = (order.get('account'), _contract_id(order))

        if key not in grouped:
            grouped[key] = {
                'account': order.get('account'),
                'contract_id': _contract_id(order),
                'symbol': order.get('symbol'),
                'root_symbol': order.get('root_symbol'),
                'opens': [],
                'closes': [],
            }

        side = 'opens' if order.get('position_effect') == 'open' else 'closes'
        grouped[key][side].append(order)

    return [_position(group) for group in grouped.values()]


def _contract_id(order: Dict[str, Any]) -> str:
    """The contract this order is on. Stored as a list, as every asset's is."""
    ids = order.get('contract_ids')
    if isinstance(ids, str):
        try:
            ids = json.loads(ids)
        except ValueError:
            ids = []
    return (ids or [None])[0]


def _position(group: Dict[str, Any]) -> Position:
    """One contract's orders as a position."""
    opens, closes = group['opens'], group['closes']
    if not opens:
        return _orphaned(group)

    quantity = sum(_number(order, 'quantity') for order in opens)
    open_date = min(order['created_at'] for order in opens)

    position = Position(
        asset_type=ASSET_TYPE,
        # The contract and when it was opened, so re-running the pairing over the
        # same orders lands on the same position rather than a second one
        position_key=f"{group['contract_id']}_{open_date}",
        account=group['account'],
        contract_ids=[group['contract_id']] if group['contract_id'] else [],
        symbol=group['symbol'],
        root_symbol=group['root_symbol'],
        quantity=quantity,
        open_date=open_date,
        open_price=_weighted_price(opens, quantity),
        status='open',
    )

    if closes:
        position.status = 'closed'
        position.close_date = max(order['created_at'] for order in closes)
        position.close_price = _weighted_price(closes, quantity)
        # As reported, not as calculated
        position.pnl = round(sum(_number(order, 'pnl') for order in closes), 2)
        position.pnl_no_fees = round(sum(_number(order, 'pnl_no_fees')
                                        for order in closes), 2)
        position.fees = round(sum(_number(order, 'fees') for order in closes), 2)

    return position


def _orphaned(group: Dict[str, Any]) -> Position:
    """A contract closed with no opening order in range.

    The entry price is not in the data, so the position cannot say what it was
    entered at -- but the broker reported the realized P&L on the closing order,
    so that figure is known and is kept.
    """
    closes = group['closes']
    quantity = sum(_number(order, 'quantity') for order in closes)
    close_date = max(order['created_at'] for order in closes)

    return Position(
        asset_type=ASSET_TYPE,
        position_key=f"{group['contract_id']}_{close_date}",
        account=group['account'],
        contract_ids=[group['contract_id']] if group['contract_id'] else [],
        symbol=group['symbol'],
        root_symbol=group['root_symbol'],
        quantity=quantity,
        close_date=close_date,
        close_price=_weighted_price(closes, quantity),
        pnl=round(sum(_number(order, 'pnl') for order in closes), 2),
        pnl_no_fees=round(sum(_number(order, 'pnl_no_fees') for order in closes), 2),
        fees=round(sum(_number(order, 'fees') for order in closes), 2),
        status='orphaned',
    )


def _weighted_price(orders: List[Dict[str, Any]], quantity: float) -> float:
    """The average fill price, weighted by how much filled at each."""
    if not quantity:
        return 0.0
    paid = sum(_number(order, 'price') * _number(order, 'quantity')
               for order in orders)
    return paid / quantity


def _number(order: Dict[str, Any], field: str) -> float:
    value = order.get(field)
    return float(value) if value is not None else 0.0
