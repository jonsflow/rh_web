"""
Position Model

Data model representing an options position with all its attributes.
"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime


@dataclass
class Position:
    """Represents an options position"""
    
    # Identifiers
    option_key: str
    symbol: str
    
    # Dates
    open_date: Optional[str] = None
    close_date: Optional[str] = None
    expiration_date: Optional[str] = None
    
    # Option details
    strike_price: Optional[str] = None
    option_type: Optional[str] = None
    strategy: Optional[str] = None
    direction: Optional[str] = None
    
    # Quantities and prices
    quantity: Optional[int] = None
    open_price: Optional[float] = None
    close_price: Optional[float] = None
    
    # Premiums and P&L
    open_premium: Optional[float] = None
    close_premium: Optional[float] = None
    net_credit: Optional[float] = None
    
    # Status
    status: str = 'open'  # 'open', 'closed', 'expired'
    
    @property
    def is_spread(self) -> bool:
        """Check if this position is a spread strategy"""
        return self.strategy and '_spread' in self.strategy.lower()
    
    @property
    def is_profitable(self) -> bool:
        """Check if this position is profitable"""
        return self.net_credit is not None and self.net_credit > 0
    
    @property
    def is_closed(self) -> bool:
        """Check if this position is closed"""
        return self.status == 'closed'
    
    @property
    def is_expired(self) -> bool:
        """Check if this position is expired"""
        return self.status == 'expired'
    
    @property
    def is_open(self) -> bool:
        """Check if this position is open"""
        return self.status == 'open'
    
    def to_dict(self) -> dict:
        """Convert position to dictionary for API responses"""
        return {
            'option_key': self.option_key,
            'symbol': self.symbol,
            'open_date': self.open_date,
            'close_date': self.close_date,
            'expiration_date': self.expiration_date,
            'strike_price': self.strike_price,
            'option_type': self.option_type,
            'strategy': self.strategy,
            'direction': self.direction,
            'quantity': self.quantity,
            'open_price': self.open_price,
            'close_price': self.close_price,
            'open_premium': self.open_premium,
            'close_premium': self.close_premium,
            'net_credit': self.net_credit,
            'status': self.status
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'Position':
        """Create position from dictionary data"""
        return cls(
            option_key=data.get('option_key', ''),
            symbol=data.get('symbol', ''),
            open_date=data.get('open_date'),
            close_date=data.get('close_date'),
            expiration_date=data.get('expiration_date'),
            strike_price=data.get('strike_price'),
            option_type=data.get('option_type'),
            strategy=data.get('strategy'),
            direction=data.get('direction'),
            quantity=data.get('quantity'),
            open_price=data.get('open_price'),
            close_price=data.get('close_price'),
            open_premium=data.get('open_premium'),
            close_premium=data.get('close_premium'),
            net_credit=data.get('net_credit'),
            status=data.get('status', 'open')
        )