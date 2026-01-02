"""
Option Order Model

Data model representing a single option order from Robinhood.
"""

from dataclasses import dataclass
from typing import Optional, List


@dataclass
class OptionOrder:
    """Represents a single option order"""
    
    # Identifiers
    robinhood_id: str
    option_ids: List[str]
    
    # Basic info
    symbol: str
    created_at: str
    position_effect: str  # 'open' or 'close'
    
    # Option details
    expiration_date: str
    strike_price: str  # Combined for spreads: "100.00/105.00"
    option_type: str   # Combined for spreads: "call/call"
    strategy: Optional[str] = None
    direction: Optional[str] = None  # 'debit' or 'credit'
    
    # Trade details
    price: Optional[float] = None
    quantity: Optional[int] = None
    premium: Optional[float] = None
    
    # Metadata
    raw_data: Optional[str] = None  # Full JSON for reference
    fetched_at: Optional[str] = None
    
    @property
    def is_opening_order(self) -> bool:
        """Check if this is an opening order"""
        return self.position_effect == 'open'
    
    @property
    def is_closing_order(self) -> bool:
        """Check if this is a closing order"""
        return self.position_effect == 'close'
    
    @property
    def is_spread(self) -> bool:
        """Check if this order is for a spread strategy"""
        return self.strategy and '_spread' in self.strategy.lower()
    
    def to_dict(self) -> dict:
        """Convert order to dictionary for API responses"""
        return {
            'robinhood_id': self.robinhood_id,
            'symbol': self.symbol,
            'created_at': self.created_at,
            'position_effect': self.position_effect,
            'expiration_date': self.expiration_date,
            'strike_price': self.strike_price,
            'option_type': self.option_type,
            'strategy': self.strategy,
            'direction': self.direction,
            'price': self.price,
            'quantity': self.quantity,
            'premium': self.premium,
            'option_ids': self.option_ids
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'OptionOrder':
        """Create order from dictionary data"""
        return cls(
            robinhood_id=data.get('robinhood_id', ''),
            option_ids=data.get('option_ids', []),
            symbol=data.get('symbol', ''),
            created_at=data.get('created_at', ''),
            position_effect=data.get('position_effect', ''),
            expiration_date=data.get('expiration_date', ''),
            strike_price=data.get('strike_price', ''),
            option_type=data.get('option_type', ''),
            strategy=data.get('strategy'),
            direction=data.get('direction'),
            price=data.get('price'),
            quantity=data.get('quantity'),
            premium=data.get('premium'),
            raw_data=data.get('raw_data'),
            fetched_at=data.get('fetched_at')
        )