"""
P&L Calculator Service

This service handles all profit and loss calculations for options positions.
Separated from database layer to follow single responsibility principle.
"""

from typing import Dict, Optional
import datetime


class PnLCalculator:
    """Handles P&L calculations for different types of option positions"""
    
    @staticmethod
    def calculate_closed_position_pnl(position: Dict) -> Optional[float]:
        """
        Calculate P&L for positions that were manually closed.
        
        Args:
            position: Position dictionary with open/close prices and quantities
            
        Returns:
            P&L value or None if calculation not possible
        """
        if not all([
            position.get('open_price') is not None,
            position.get('close_price') is not None,
            position.get('quantity') is not None,
            position.get('quantity', 0) > 0
        ]):
            # Fallback to premium calculation if prices are missing
            return PnLCalculator._calculate_premium_pnl(position)
        
        price_diff = position['close_price'] - position['open_price']
        quantity = position['quantity']
        direction = position.get('direction', '')
        
        if direction == 'debit':
            # Debit strategies: buying options (long positions)
            # Profit when close_price > open_price
            return price_diff * quantity * 100
        elif direction == 'credit':
            # Credit strategies: selling options (short positions)  
            # Profit when close_price < open_price
            return -price_diff * quantity * 100
        else:
            # Default to debit behavior for unknown directions
            return price_diff * quantity * 100
    
    @staticmethod
    def calculate_expired_position_pnl(position: Dict) -> float:
        """
        Calculate P&L for positions that expired without being closed.
        
        For single options only - spreads require closing price logic.
        
        Args:
            position: Position dictionary with direction and open_premium
            
        Returns:
            P&L value (negative for losses, positive for gains)
        """
        open_premium = position.get('open_premium', 0)
        if not open_premium:
            return 0.0
        
        direction = position.get('direction', '')
        
        if direction == 'debit':
            # Debit positions: you paid premium, expired worthless = loss
            return -abs(open_premium)
        elif direction == 'credit':
            # Credit positions: you received premium, expired worthless = profit
            return abs(open_premium)
        else:
            # Fallback for unknown direction
            return 0.0
    
    @staticmethod
    def _calculate_premium_pnl(position: Dict) -> float:
        """
        Fallback P&L calculation using premiums when prices are missing.
        
        Args:
            position: Position dictionary with open and close premiums
            
        Returns:
            P&L based on premium difference
        """
        open_premium = position.get('open_premium', 0) or 0
        close_premium = position.get('close_premium', 0) or 0
        return open_premium + close_premium
    
    @staticmethod
    def is_spread_strategy(strategy: str) -> bool:
        """
        Check if a strategy is a spread (complex multi-leg position).
        
        Args:
            strategy: Strategy name
            
        Returns:
            True if strategy is a spread
        """
        if not strategy:
            return False
        return '_spread' in strategy.lower()
    
    @staticmethod
    def should_skip_spread_pnl() -> bool:
        """
        Determine if spread P&L calculations should be skipped.
        
        Currently we skip spreads because they require closing price logic
        to determine if strikes were in/out of the money at expiration.
        
        Returns:
            True if spreads should be skipped
        """
        return True  # TODO: Implement proper spread expiration logic