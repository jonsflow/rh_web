"""
Option Service

Main business service that orchestrates options data processing, P&L calculations,
and position management. This is the primary interface for the Flask application.
"""

from typing import Dict, List, Optional, Tuple
from models.position import Position
from models.pnl_summary import PnLSummary, DailyPnLSummary
from services.data_repository import DataRepository
from services.pnl_calculator import PnLCalculator
from services.position_classifier import PositionClassifier


class OptionService:
    """Main service for options data processing and business operations"""
    
    def __init__(self, db_path: str = "options.db"):
        self.repository = DataRepository(db_path)
        self.pnl_calculator = PnLCalculator()
        self.position_classifier = PositionClassifier()
    
    def process_raw_orders_to_positions(self, raw_orders: List[Tuple]) -> List[Position]:
        """
        Process raw order tuples into Position objects with P&L calculations.
        
        This replaces the complex logic that was in database.py rebuild_positions().
        """
        positions_dict = {}
        
        for order in raw_orders:
            option_ids, symbol, created_at, position_effect, expiration_date, strike_price, price, quantity, premium, strategy, direction, option_type = order
            
            # Skip spreads entirely for now - use service method for consistency
            if PnLCalculator.is_spread_strategy(strategy):
                continue
                
            # Create unique key for single options
            option_key = f"{symbol}_{option_ids}_{expiration_date}_{strike_price}"
            
            # Initialize position if not exists
            if option_key not in positions_dict:
                positions_dict[option_key] = {
                    'option_key': option_key,
                    'symbol': symbol,
                    'expiration_date': expiration_date,
                    'strike_price': strike_price,
                    'strategy': strategy,
                    'direction': direction,
                    'option_type': option_type,
                    'open_orders': [],
                    'close_orders': [],
                    'status': 'open'
                }
            
            # Add order to appropriate list
            position = positions_dict[option_key]
            
            if position_effect == 'open':
                position['open_orders'].append({
                    'date': created_at,
                    'price': price,
                    'quantity': quantity or 0,
                    'premium': premium
                })
            elif position_effect == 'close':
                position['close_orders'].append({
                    'date': created_at,
                    'price': price,
                    'quantity': quantity or 0,
                    'premium': premium
                })
        
        # Convert to Position objects with aggregated values
        positions = []
        for position_data in positions_dict.values():
            position = self._aggregate_position_data(position_data)
            positions.append(position)
        
        return positions
    
    def _aggregate_position_data(self, position_data: Dict) -> Position:
        """
        Convert raw position dictionary to Position object with aggregated values.
        """
        # Initialize all fields
        position_dict = {
            'option_key': position_data['option_key'],
            'symbol': position_data['symbol'],
            'expiration_date': position_data['expiration_date'],
            'strike_price': position_data['strike_price'],
            'strategy': position_data['strategy'],
            'direction': position_data['direction'],
            'option_type': position_data['option_type'],
            'open_date': None,
            'close_date': None,
            'quantity': 0,
            'open_price': None,
            'close_price': None,
            'open_premium': None,
            'close_premium': None,
            'net_credit': None,
            'status': 'open'
        }
        
        # Calculate open position aggregates
        open_orders = position_data.get('open_orders', [])
        if open_orders:
            total_open_quantity = sum(order['quantity'] for order in open_orders)
            total_open_premium = sum(order['premium'] or 0 for order in open_orders)
            
            # Calculate weighted average price
            weighted_price_sum = sum((order['price'] or 0) * order['quantity'] for order in open_orders)
            position_dict['open_price'] = weighted_price_sum / total_open_quantity if total_open_quantity > 0 else None
            position_dict['open_premium'] = total_open_premium
            position_dict['open_date'] = open_orders[0]['date']  # First open date
            position_dict['quantity'] = total_open_quantity
        
        # Calculate close position aggregates
        close_orders = position_data.get('close_orders', [])
        if close_orders:
            total_close_quantity = sum(order['quantity'] for order in close_orders)
            total_close_premium = sum(order['premium'] or 0 for order in close_orders)
            
            # Calculate weighted average price
            weighted_price_sum = sum((order['price'] or 0) * order['quantity'] for order in close_orders)
            position_dict['close_price'] = weighted_price_sum / total_close_quantity if total_close_quantity > 0 else None
            position_dict['close_premium'] = total_close_premium
            position_dict['close_date'] = close_orders[-1]['date']  # Last close date
        
        # Create Position object
        position = Position.from_dict(position_dict)
        
        # Skip orphaned close orders - we can't calculate accurate P&L without the open
        if PositionClassifier.has_orphaned_close_orders(position_dict):
            position.status = 'orphaned'
            position.net_credit = None
            return position
        
        # Determine status and calculate P&L using services
        position.status = PositionClassifier.classify_position(position_dict)
        
        if position.status == 'closed':
            position.net_credit = PnLCalculator.calculate_closed_position_pnl(position_dict)
        elif position.status == 'expired':
            position.net_credit = PnLCalculator.calculate_expired_position_pnl(position_dict)
            position.close_date = position.expiration_date
            position.close_price = 0.0
            position.close_premium = 0.0
        else:  # open
            position.net_credit = None
        
        return position
    
    def rebuild_all_positions(self) -> int:
        """
        Rebuild all positions from raw orders data.
        
        Returns:
            Number of positions processed
        """
        # Get raw orders from repository
        raw_orders = self.repository.get_all_raw_orders()
        
        # Process into Position objects
        positions = self.process_raw_orders_to_positions(raw_orders)
        
        # Save to database
        self.repository.save_positions(positions)
        
        return len(positions)
    
    def get_positions_by_status(self, status: str) -> List[Position]:
        """Get positions filtered by status"""
        return self.repository.get_positions_by_status(status)
    
    def get_all_positions(self) -> Dict[str, List[Position]]:
        """Get all positions grouped by status"""
        return {
            'open_positions': self.get_positions_by_status('open'),
            'closed_positions': self.get_positions_by_status('closed'),
            'expired_positions': self.get_positions_by_status('expired')
        }
    
    def get_pnl_summary(self) -> PnLSummary:
        """Get comprehensive P&L summary"""
        all_positions_data = self.get_all_positions()
        all_positions = []
        
        # Flatten all positions into single list
        for positions_list in all_positions_data.values():
            all_positions.extend(positions_list)
        
        return PnLSummary.from_positions(all_positions)
    
    def get_orders_for_display(self) -> List[Dict]:
        """Get all orders formatted for display"""
        return self.repository.get_all_orders_for_display()
    
    def get_daily_pnl_summary(self, start_date: str = None, end_date: str = None) -> Dict[str, Dict]:
        """Get daily P&L summary for calendar view"""
        daily_summaries = self.repository.get_daily_pnl_data(start_date, end_date)
        
        # Convert to dictionary format expected by frontend
        daily_data = {}
        for summary in daily_summaries:
            daily_data[summary.date] = summary.to_dict()
        
        return daily_data
    
    def get_positions_by_date(self, target_date: str) -> List[Position]:
        """Get all positions closed on a specific date"""
        return self.repository.get_positions_by_date(target_date)
    
    def get_processed_data_for_api(self) -> Dict:
        """
        Get processed data in the format expected by existing API endpoints.
        
        This maintains backward compatibility with existing frontend.
        """
        positions_data = self.get_all_positions()
        orders_data = self.get_orders_for_display()
        
        # Convert Position objects to dictionaries for API
        return {
            'open_positions': [pos.to_dict() for pos in positions_data['open_positions']],
            'closed_positions': [pos.to_dict() for pos in positions_data['closed_positions']], 
            'expired_positions': [pos.to_dict() for pos in positions_data['expired_positions']],
            'all_orders': orders_data
        }