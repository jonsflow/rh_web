"""
Position Classifier Service

This service handles the logic for classifying positions as open, closed, or expired.
Separated from database layer to follow single responsibility principle.
"""

from typing import Dict
import datetime


class PositionClassifier:
    """Handles classification of position status"""
    
    @staticmethod
    def classify_position(position: Dict) -> str:
        """
        Determine the status of a position based on its properties.
        
        Args:
            position: Position dictionary with premiums, dates, etc.
            
        Returns:
            Position status: 'closed', 'expired', or 'open'
        """
        has_open_premium = position.get('open_premium') is not None
        has_close_premium = position.get('close_premium') is not None
        
        # If has both open and close orders - it was manually closed
        if has_open_premium and has_close_premium:
            return 'closed'
        
        # If only has open orders - check if expired
        elif has_open_premium:
            if PositionClassifier._is_expired(position):
                return 'expired'
            else:
                return 'open'
        
        # If only has close orders - orphaned closing order
        # These will be filtered out from display but marked as closed
        elif has_close_premium:
            return 'closed'
        
        # Default to open
        return 'open'
    
    @staticmethod
    def _is_expired(position: Dict) -> bool:
        """
        Check if a position has expired based on expiration date.
        
        Args:
            position: Position dictionary with expiration_date
            
        Returns:
            True if position has expired
        """
        expiration_date = position.get('expiration_date')
        if not expiration_date:
            return False
        
        try:
            exp_date = datetime.datetime.strptime(expiration_date, '%Y-%m-%d')
            return exp_date < datetime.datetime.now()
        except ValueError:
            # If date parsing fails, assume not expired
            return False
    
    @staticmethod
    def has_orphaned_close_orders(position: Dict) -> bool:
        """
        Check if position has close orders without corresponding open orders.
        
        These occur when:
        1. Opening was before our data collection period
        2. Part of a spread where legs got separated
        
        Args:
            position: Position dictionary
            
        Returns:
            True if position has closes but no opens
        """
        has_close = position.get('close_premium') is not None
        has_open = position.get('open_premium') is not None
        return has_close and not has_open
    
    @staticmethod
    def should_skip_spread(position: Dict) -> bool:
        """
        Determine if a spread position should be skipped from processing.
        
        Args:
            position: Position dictionary with strategy
            
        Returns:
            True if position is a spread that should be skipped
        """
        strategy = position.get('strategy', '')
        if not strategy:
            return False
        
        return '_spread' in strategy.lower()
    
    @staticmethod
    def has_orphaned_close_orders(position: Dict) -> bool:
        """
        Check if a position only has closing orders (no opening orders).
        
        These typically occur when the opening order was before our data range.
        
        Args:
            position: Position dictionary with premiums
            
        Returns:
            True if position only has close orders
        """
        has_open_premium = position.get('open_premium') is not None
        has_close_premium = position.get('close_premium') is not None
        
        return not has_open_premium and has_close_premium