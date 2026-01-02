"""
P&L Summary Model

Data model representing profit and loss summaries.
"""

from dataclasses import dataclass
from typing import Dict, List
from models.position import Position


@dataclass
class PnLSummary:
    """Represents a P&L summary with breakdown by status"""
    
    # P&L by status
    closed_pnl: float = 0.0
    expired_pnl: float = 0.0
    open_value: float = 0.0
    
    # Position counts
    open_count: int = 0
    closed_count: int = 0
    expired_count: int = 0
    
    @property
    def total_pnl(self) -> float:
        """Calculate total realized P&L (closed + expired)"""
        return self.closed_pnl + self.expired_pnl
    
    @property
    def total_positions(self) -> int:
        """Calculate total number of positions"""
        return self.open_count + self.closed_count + self.expired_count
    
    @property
    def is_profitable(self) -> bool:
        """Check if overall P&L is profitable"""
        return self.total_pnl > 0
    
    def to_dict(self) -> dict:
        """Convert summary to dictionary for API responses"""
        return {
            'closed_pnl': round(self.closed_pnl, 2),
            'expired_pnl': round(self.expired_pnl, 2),
            'total_pnl': round(self.total_pnl, 2),
            'open_value': round(abs(self.open_value), 2),
            'open_count': self.open_count,
            'closed_count': self.closed_count,
            'expired_count': self.expired_count,
            'total_positions': self.total_positions
        }
    
    @classmethod
    def from_positions(cls, positions: List[Position]) -> 'PnLSummary':
        """Create P&L summary from a list of positions"""
        summary = cls()
        
        for position in positions:
            if position.is_open:
                summary.open_count += 1
                if position.open_premium:
                    summary.open_value += position.open_premium
            elif position.is_closed:
                summary.closed_count += 1
                if position.net_credit:
                    summary.closed_pnl += position.net_credit
            elif position.is_expired:
                summary.expired_count += 1
                if position.net_credit:
                    summary.expired_pnl += position.net_credit
        
        return summary


@dataclass
class DailyPnLSummary:
    """Represents daily P&L data for calendar view"""
    
    date: str
    pnl: float
    position_count: int
    details: str = ""
    
    @property
    def is_profitable(self) -> bool:
        """Check if this day was profitable"""
        return self.pnl > 0
    
    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            'date': self.date,
            'pnl': round(self.pnl, 2),
            'count': self.position_count,
            'details': self.details
        }