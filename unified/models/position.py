"""
A position, whatever asset it belongs to.

One round trip: what was opened, what closed it, and what that came to. The
figures carry one name each -- `pnl`, `open_value` -- rather than the three the
standalone apps use between them, and the fields only one asset has are nullable
rather than split into three models.
"""

import json
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Position:
    """One round trip in one account."""

    asset_type: str
    position_key: str
    symbol: str

    account: Optional[str] = None
    # Futures shows a contract month; the root is what the chain is on
    root_symbol: Optional[str] = None

    open_date: Optional[str] = None
    close_date: Optional[str] = None
    quantity: Optional[float] = None

    open_price: Optional[float] = None
    close_price: Optional[float] = None
    open_value: Optional[float] = None
    close_value: Optional[float] = None

    # Realized P&L. `pnl` is after fees, `pnl_no_fees` before; for an asset that
    # charges no per-fill fee the two agree.
    pnl: Optional[float] = None
    pnl_no_fees: Optional[float] = None
    fees: Optional[float] = None

    # 'open', 'closed', 'expired', or 'orphaned' -- a close whose opening order
    # predates the fetch window, which cannot be valued and is not shown
    status: str = 'open'

    # Options only
    expiration_date: Optional[str] = None
    strike_price: Optional[str] = None
    option_type: Optional[str] = None
    strategy: Optional[str] = None
    direction: Optional[str] = None

    # One id per leg for options, one for a futures contract, none for equities
    contract_ids: List[str] = field(default_factory=list)

    # ---------- what it is ----------

    @property
    def is_open(self) -> bool:
        return self.status == 'open'

    @property
    def is_closed(self) -> bool:
        return self.status == 'closed'

    @property
    def is_expired(self) -> bool:
        return self.status == 'expired'

    @property
    def is_orphaned(self) -> bool:
        """A close with no open. Its P&L cannot be known, so it is not shown."""
        return self.status == 'orphaned'

    @property
    def is_profitable(self) -> bool:
        return self.pnl is not None and self.pnl > 0

    # ---------- storage ----------

    def to_row(self) -> dict:
        """The unified positions columns."""
        return {
            'asset_type': self.asset_type,
            'account': self.account,
            'position_key': self.position_key,
            'symbol': self.symbol,
            'root_symbol': self.root_symbol,
            'open_date': self.open_date,
            'close_date': self.close_date,
            'quantity': self.quantity,
            'open_price': self.open_price,
            'close_price': self.close_price,
            'open_value': self.open_value,
            'close_value': self.close_value,
            'pnl': self.pnl,
            'pnl_no_fees': self.pnl_no_fees,
            'fees': self.fees,
            'status': self.status,
            'expiration_date': self.expiration_date,
            'strike_price': self.strike_price,
            'option_type': self.option_type,
            'strategy': self.strategy,
            'direction': self.direction,
            'contract_ids': json.dumps(self.contract_ids),
        }

    @classmethod
    def from_row(cls, row: dict) -> 'Position':
        """Back from a stored row. Unknown keys are ignored."""
        known = cls.__dataclass_fields__
        values = {key: value for key, value in dict(row).items() if key in known}

        stored_ids = values.get('contract_ids')
        if isinstance(stored_ids, str):
            try:
                values['contract_ids'] = json.loads(stored_ids)
            except ValueError:
                values['contract_ids'] = []

        return cls(**values)
