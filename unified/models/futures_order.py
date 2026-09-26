"""
A futures order, as the broker sends it.

Two quirks of this payload. Money arrives double-nested -- `realizedPnl` is an
object holding `realizedPnl`, which is an object holding `amount` -- and the
trade date has to be taken from the execution's event time converted to Eastern,
because a fill after 8pm UTC belongs to the next day in New York but the previous
one in the payload.

Futures is also the only asset where the broker reports realized P&L itself, so
nothing here is calculated: `pnl` is after fees and `pnl_no_fees` before, both as
given.
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

import pytz

from unified.models.fields import to_float

EASTERN = pytz.timezone('America/New_York')


@dataclass
class FuturesOrder:
    """One futures order."""

    order_id: str
    symbol: str

    account: Optional[str] = None
    # The contract month, which is what the dashboard shows
    display_symbol: Optional[str] = None
    contract_id: str = ''
    # 'BUY' or 'SELL', as the broker sends it
    order_side: str = ''
    # 'OPENING' or 'CLOSING', as the broker sends it
    position_effect: str = ''

    quantity: int = 0
    filled_quantity: int = 0
    average_price: float = 0.0

    realized_pnl: float = 0.0
    realized_pnl_without_fees: float = 0.0
    total_fee: float = 0.0

    order_state: str = ''
    created_at: Optional[str] = None
    execution_time: Optional[str] = None
    trade_date: Optional[str] = None
    raw_data: Optional[str] = None

    # ---------- the parse ----------

    @classmethod
    def from_payload(cls, payload: Dict[str, Any], account: str = None) -> 'FuturesOrder':
        """One broker payload, parsed."""
        legs = payload.get('orderLegs', [])
        if legs:
            leg = legs[0]
            contract_id = leg.get('contractId', '')
            order_side = leg.get('orderSide', '')
            average_price = float(leg.get('averagePrice', 0))
        else:
            contract_id = ''
            order_side = ''
            average_price = 0.0

        execution = cls._execution(payload)
        execution_time = execution.get('eventTime', '')
        pnl = payload.get('realizedPnl', {}) or {}

        return cls(
            order_id=payload.get('orderId', ''),
            symbol=payload.get('symbol', ''),
            # The broker names the account on the order itself
            account=account or payload.get('accountId', ''),
            display_symbol=payload.get('displaySymbol', ''),
            contract_id=contract_id,
            order_side=order_side,
            position_effect=payload.get('positionEffectAtPlacementTime', ''),
            quantity=int(payload.get('quantity', 0)),
            filled_quantity=int(payload.get('filledQuantity', 0)),
            average_price=average_price,
            realized_pnl=cls._amount(pnl.get('realizedPnl')),
            realized_pnl_without_fees=cls._amount(pnl.get('realizedPnlWithoutFees')),
            total_fee=cls._amount(payload.get('totalFee')),
            order_state=payload.get('orderState', ''),
            created_at=payload.get('createdAt', ''),
            execution_time=execution_time,
            trade_date=(cls._broker_trade_date(execution.get('tradeDate'))
                        or cls._eastern_trade_date(execution_time)),
            raw_data=json.dumps(payload),
        )

    @staticmethod
    def _amount(field: Any) -> float:
        """A money field, which the broker wraps in an object."""
        return to_float(field) or 0.0

    @staticmethod
    def _execution(payload: Dict[str, Any]) -> Dict[str, Any]:
        executions = payload.get('orderExecutions') or []
        return executions[0] if executions else {}

    @staticmethod
    def _broker_trade_date(trade_date: Any) -> Optional[str]:
        """The trading day the broker itself assigned, as year/month/day parts.

        Preferred over deriving one, because it is the exchange's answer rather
        than ours. Absent, the Eastern conversion below stands in.
        """
        if not isinstance(trade_date, dict):
            return None
        try:
            return '{year:04d}-{month:02d}-{day:02d}'.format(**trade_date)
        except (KeyError, ValueError, TypeError):
            return None

    @staticmethod
    def _eastern_trade_date(execution_time: Optional[str]) -> Optional[str]:
        """The trading day a fill belongs to, converted from UTC.

        A fill after 8pm Eastern is already tomorrow in UTC, so the date cannot
        be sliced off the timestamp.
        """
        if not execution_time:
            return ''

        dt_utc = datetime.fromisoformat(execution_time.replace('Z', '+00:00'))
        return dt_utc.astimezone(EASTERN).strftime('%Y-%m-%d')

    # ---------- what it is ----------

    @property
    def is_opening(self) -> bool:
        return self.position_effect.upper() == 'OPENING'

    @property
    def is_closing(self) -> bool:
        return self.position_effect.upper() == 'CLOSING'

    @property
    def is_filled(self) -> bool:
        return self.order_state.upper() == 'FILLED'

    # ---------- storage ----------

    def to_row(self) -> dict:
        """The unified orders columns."""
        return {
            'asset_type': 'futures',
            'account': self.account,
            'order_id': self.order_id,
            # The contract month is what gets shown; the root is what it is on
            'symbol': self.display_symbol or self.symbol,
            'root_symbol': self.symbol,
            'side': self.order_side.lower() or None,
            # Canonical, so pairing reads one vocabulary across every asset
            'position_effect': ('open' if self.is_opening
                                else 'close' if self.is_closing else ''),
            'quantity': self.quantity,
            'filled_quantity': self.filled_quantity,
            'price': self.average_price,
            'gross_amount': None,
            'fees': self.total_fee,
            # The only asset where the broker reports P&L itself
            'pnl': self.realized_pnl,
            'pnl_no_fees': self.realized_pnl_without_fees,
            'state': self.order_state.lower(),
            'created_at': self.created_at,
            'executed_at': self.execution_time or self.created_at,
            'trade_date': self.trade_date,
            'expiration_date': None,
            'strike_price': None,
            'option_type': None,
            'strategy': None,
            'direction': None,
            'contract_ids': json.dumps([self.contract_id] if self.contract_id else []),
            'raw_data': self.raw_data,
        }
