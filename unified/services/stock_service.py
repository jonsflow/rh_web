"""
Equity positions.

Shares have no position of their own to close, so buys are matched to sells
first-in-first-out. A buy larger than the sell is split: the matched part becomes
a closed position and the rest stays in the queue.

What is left in the queue at the end is still a position -- shares held, open,
with no P&L yet. And a sell that runs out of buys is a position too, orphaned:
its shares were bought before the fetch window, so what they cost is not in the
data and the gain cannot be known. Both are recorded rather than dropped; which
statuses count toward a P&L figure is the reader's decision, not this file's.

Matching happens within one account and one symbol -- both are part of the
grouping key, so crossing either is impossible rather than merely filtered out.
"""

from collections import defaultdict
from typing import Any, Dict, List

from unified.models import Position

ASSET_TYPE = 'stocks'


def build_positions(orders: List[Dict[str, Any]]) -> List[Position]:
    """Pair buys to sells, oldest buy first.

    `orders` is expected in fill order, which is what the database returns.
    """
    grouped = defaultdict(list)
    for order in orders:
        grouped[(order.get('account'), order.get('symbol'))].append(order)

    positions: List[Position] = []
    for (account, symbol), symbol_orders in grouped.items():
        positions.extend(_match(account, symbol, symbol_orders))

    return positions


def _match(account, symbol, orders: List[Dict[str, Any]]) -> List[Position]:
    """One account's fills in one symbol, paired FIFO."""
    queue: List[Dict[str, Any]] = []
    positions: List[Position] = []

    for order in orders:
        if order.get('position_effect') == 'open':
            queue.append({
                'order_id': order.get('order_id'),
                'quantity': _number(order, 'quantity'),
                'price': _number(order, 'price'),
                'value': _number(order, 'gross_amount'),
                'fees': _number(order, 'fees'),
                'date': order.get('trade_date'),
            })
            continue

        remaining = _number(order, 'quantity')
        sell_quantity = remaining
        if not sell_quantity:
            continue

        while remaining > 0 and queue:  # noqa: PLR1702
            buy = queue[0]
            matched = min(buy['quantity'], remaining)

            # Each side contributes the part of itself that this match used
            sold_share = matched / sell_quantity
            bought_share = matched / buy['quantity'] if buy['quantity'] else 0

            proceeds = _number(order, 'gross_amount') * sold_share
            cost = buy['value'] * bought_share
            fees = _number(order, 'fees') * sold_share + buy['fees'] * bought_share
            before_fees = proceeds - cost

            positions.append(Position(
                asset_type=ASSET_TYPE,
                # The two fills that make up this match. A buy split across two
                # sells gives two keys, and so does a sell filled from two buys.
                position_key=f"{buy['order_id']}|{order.get('order_id')}",
                account=account,
                symbol=symbol,
                root_symbol=symbol,
                quantity=matched,
                open_date=buy['date'],
                close_date=order.get('trade_date'),
                open_price=buy['price'],
                close_price=_number(order, 'price'),
                open_value=round(cost, 2),
                close_value=round(proceeds, 2),
                pnl=round(before_fees - fees, 2),
                pnl_no_fees=round(before_fees, 2),
                fees=round(fees, 2),
                status='closed',
            ))

            if buy['quantity'] <= remaining:
                remaining -= buy['quantity']
                queue.pop(0)
            else:
                # Partly used: what is left of the buy waits for the next sell
                buy['quantity'] -= remaining
                buy['value'] -= cost
                buy['fees'] -= buy['fees'] * bought_share
                remaining = 0

        if remaining > 0:
            # More sold than the data shows was bought: the opening fills are
            # older than the window we fetched, so the cost basis is not here
            positions.append(_orphaned(account, symbol, order, remaining,
                                       sell_quantity))

    # Whatever is left unsold is held, which is an open position
    positions.extend(_held(account, symbol, buy) for buy in queue)
    return positions


def _orphaned(account, symbol, order: Dict[str, Any], quantity: float,
              sell_quantity: float) -> Position:
    """A sale whose purchase is not in the data. Its gain cannot be known."""
    share = quantity / sell_quantity if sell_quantity else 0

    return Position(
        asset_type=ASSET_TYPE,
        position_key=f"|{order.get('order_id')}",
        account=account,
        symbol=symbol,
        root_symbol=symbol,
        quantity=quantity,
        close_date=order.get('trade_date'),
        close_price=_number(order, 'price'),
        close_value=round(_number(order, 'gross_amount') * share, 2),
        fees=round(_number(order, 'fees') * share, 2),
        pnl=None,
        pnl_no_fees=None,
        status='orphaned',
    )


def _held(account, symbol, buy: Dict[str, Any]) -> Position:
    """Shares still held. Worth what they cost until something closes them."""
    return Position(
        asset_type=ASSET_TYPE,
        position_key=f"{buy['order_id']}|",
        account=account,
        symbol=symbol,
        root_symbol=symbol,
        quantity=buy['quantity'],
        open_date=buy['date'],
        open_price=buy['price'],
        open_value=round(buy['value'], 2),
        fees=round(buy['fees'], 2),
        pnl=None,
        pnl_no_fees=None,
        status='open',
    )


def _number(order: Dict[str, Any], field: str) -> float:
    value = order.get(field)
    return float(value) if value is not None else 0.0
