"""
A stock order, as the broker sends it.

Two things about this payload. The symbol is not in it -- the broker returns an
instrument id and the symbol comes from a separate lookup -- so the broker
resolves it and puts it on the payload before the model sees it. And the fill
time lives in `last_transaction_at` rather than `created_at`, which matters
because FIFO pairs buys to sells in fill order.
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from unified.models.fields import money, to_float


@dataclass
class StockOrder:
    """One filled equity order."""

    order_id: str
    symbol: str

    account: Optional[str] = None
    # 'buy' or 'sell'
    side: str = ''
    quantity: float = 0.0
    average_price: float = 0.0
    total_amount: float = 0.0
    fees: float = 0.0
    state: Optional[str] = None
    created_at: Optional[str] = None
    last_transaction_at: Optional[str] = None
    trade_date: Optional[str] = None
    raw_data: Optional[str] = None

    # ---------- the parse ----------

    @classmethod
    def from_payload(cls, payload: Dict[str, Any], account: str = None) -> 'StockOrder':
        """One broker payload, parsed.

        `symbol` is expected on the payload, resolved from its instrument id by
        the broker, and falls back to UNKNOWN exactly as the lookup does.
        """
        return cls(
            order_id=payload.get('id') or payload.get('order_id') or '',
            symbol=payload.get('symbol') or 'UNKNOWN',
            account=account,
            side=payload.get('side', ''),
            quantity=float(payload.get('cumulative_quantity')
                           or payload.get('quantity') or 0),
            average_price=to_float(payload.get('average_price')) or 0.0,
            total_amount=cls._amount(payload),
            # Equity fees are reported in pieces, and they are not always zero
            fees=money(payload.get('fees'), payload.get('sec_fees'),
                       payload.get('taf_fees'), payload.get('cat_fees'),
                       payload.get('sales_taxes')),
            state=(payload.get('state') or '').lower() or None,
            created_at=payload.get('created_at'),
            last_transaction_at=payload.get('last_transaction_at'),
            trade_date=cls._trade_date(payload),
            raw_data=json.dumps(payload),
        )

    @staticmethod
    def _amount(payload: Dict[str, Any]) -> float:
        """What the fill came to. The broker nests it under an amount key."""
        return (to_float(payload.get('executed_notional'))
                or to_float(payload.get('total_amount')) or 0.0)

    @staticmethod
    def _trade_date(payload: Dict[str, Any]) -> Optional[str]:
        """The execution's own date, falling back to the transaction timestamp."""
        if payload.get('trade_date'):
            return payload['trade_date']

        executions = payload.get('executions', [])
        if executions and executions[0].get('trade_execution_date'):
            return executions[0]['trade_execution_date']

        last_transaction = payload.get('last_transaction_at') or ''
        return last_transaction.split('T')[0] if last_transaction else None

    # ---------- what it is ----------

    @property
    def is_opening(self) -> bool:
        """A buy opens.

        The payload has a `position_effect` field, but it is null on the large
        majority of orders, so the side is what can actually be relied on.
        """
        return self.side == 'buy'

    @property
    def is_closing(self) -> bool:
        return self.side == 'sell'

    # ---------- storage ----------

    def to_row(self) -> dict:
        """The unified orders columns."""
        return {
            'asset_type': 'stocks',
            'account': self.account,
            'order_id': self.order_id,
            'symbol': self.symbol,
            'root_symbol': self.symbol,
            'side': self.side,
            # Canonical, so pairing reads one vocabulary across every asset
            'position_effect': 'open' if self.is_opening else 'close',
            'quantity': self.quantity,
            'filled_quantity': self.quantity,
            'price': self.average_price,
            'gross_amount': self.total_amount,
            'fees': self.fees,
            'pnl': None,
            'pnl_no_fees': None,
            'state': self.state,
            'created_at': self.created_at,
            # FIFO orders by the fill, not by when the order was placed
            'executed_at': self.last_transaction_at or self.created_at,
            'trade_date': self.trade_date,
            'expiration_date': None,
            'strike_price': None,
            'option_type': None,
            'strategy': None,
            'direction': None,
            'contract_ids': json.dumps([]),
            'raw_data': self.raw_data,
        }
