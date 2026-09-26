"""
An option order, as the broker sends it.

The parse here is the one the options dashboard has always used: a spread's legs
collapse into one row, with the strikes and types joined into a single string,
because that is how a multi-leg order is stored.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from unified.models.fields import money, to_float


@dataclass
class OptionOrder:
    """One filled option order."""

    order_id: str
    symbol: str

    account: Optional[str] = None
    created_at: Optional[str] = None
    # 'open' or 'close'. Every asset reports this under the same two words.
    position_effect: str = ''
    # 'buy' or 'sell'. The leg carries it, and it tracks the position effect.
    side: str = ''
    state: Optional[str] = None

    expiration_date: str = ''
    # A spread's strikes joined: "17.00/20.00/39.00/36.00"
    strike_price: str = ''
    option_type: str = ''
    strategy: Optional[str] = None
    # 'debit' or 'credit'; it decides the sign of a P&L calculation
    direction: Optional[str] = None

    price: Optional[float] = None
    quantity: Optional[int] = None
    premium: Optional[float] = None
    # Contract and regulatory fees, which the payload reports separately
    fees: float = 0.0

    # One id per leg
    contract_ids: List[str] = field(default_factory=list)
    raw_data: Optional[str] = None

    # ---------- the parse ----------

    @classmethod
    def from_payload(cls, payload: Dict[str, Any], account: str = None) -> 'OptionOrder':
        """One broker payload, parsed.

        Only filled orders are fetched, so there is no state to interpret.
        """
        legs = payload.get('legs', [])
        if legs:
            position_effect = legs[0].get('position_effect', '')
            side = legs[0].get('side', '')
            expiration_date = legs[0].get('expiration_date', '')
            strike_price = '/'.join(f"{float(leg['strike_price']):.2f}" for leg in legs)
            option_type = '/'.join(leg['option_type'] for leg in legs)
            contract_ids = [leg['option'][-13:][:-1] for leg in legs]
        else:
            position_effect = ''
            side = ''
            expiration_date = ''
            strike_price = ''
            option_type = ''
            contract_ids = []

        return cls(
            order_id=payload.get('id', ''),
            symbol=payload.get('chain_symbol', ''),
            # The payload names the account, so a row says which one it is
            # whether or not the caller passed it
            account=account or payload.get('account_number'),
            created_at=payload.get('created_at', ''),
            position_effect=position_effect,
            side=side,
            state=(payload.get('state') or '').lower() or None,
            expiration_date=expiration_date,
            strike_price=strike_price,
            option_type=option_type,
            strategy=payload.get('opening_strategy') or payload.get('closing_strategy', ''),
            direction=payload.get('direction', ''),
            # A missing price stays null rather than becoming zero: zero is a
            # price, absence is not
            price=to_float(payload.get('price')),
            quantity=(int(float(payload['processed_quantity']))
                      if payload.get('processed_quantity') else None),
            premium=to_float(payload.get('processed_premium')),
            # sales_taxes arrives as an empty list when there are none
            fees=money(payload.get('contract_fees'),
                       payload.get('regulatory_fees'),
                       payload.get('sales_taxes')),
            contract_ids=contract_ids,
            raw_data=json.dumps(payload),
        )

    # ---------- what it is ----------

    @property
    def is_opening(self) -> bool:
        return self.position_effect == 'open'

    @property
    def is_closing(self) -> bool:
        return self.position_effect == 'close'

    @property
    def is_spread(self) -> bool:
        """A multi-leg order. These are not paired into positions."""
        return bool(self.strategy) and '_spread' in self.strategy.lower()

    # ---------- storage ----------

    def to_row(self) -> dict:
        """The unified orders columns."""
        return {
            'asset_type': 'options',
            'account': self.account,
            'order_id': self.order_id,
            'symbol': self.symbol,
            # The underlying, which for an option is what it is written on
            'root_symbol': self.symbol,
            'side': self.side or None,
            'position_effect': self.position_effect,
            'quantity': self.quantity,
            'filled_quantity': self.quantity,
            'price': self.price,
            'gross_amount': self.premium,
            'fees': self.fees,
            'pnl': None,
            'pnl_no_fees': None,
            'state': self.state,
            'created_at': self.created_at,
            'executed_at': self.created_at,
            'trade_date': self.created_at[:10] if self.created_at else None,
            'expiration_date': self.expiration_date,
            'strike_price': self.strike_price,
            'option_type': self.option_type,
            'strategy': self.strategy,
            'direction': self.direction,
            'contract_ids': json.dumps(self.contract_ids),
            'raw_data': self.raw_data,
        }
