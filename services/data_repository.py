"""
Data Repository Service

Pure data access layer that handles database operations without business logic.
This replaces direct database access from other parts of the application.
"""

import sqlite3
import json
from typing import Dict, List, Optional, Tuple
from models.position import Position
from models.option_order import OptionOrder
from models.pnl_summary import DailyPnLSummary


class DataRepository:
    """Handles all database operations for options data"""
    
    def __init__(self, db_path: str = "options.db"):
        self.db_path = db_path
    
    def get_last_order_date(self) -> Optional[str]:
        """Get the date of the most recent order in the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT MAX(created_at) FROM option_orders')
        result = cursor.fetchone()
        
        conn.close()
        return result[0] if result and result[0] else None
    
    def insert_orders(self, orders: List[Dict]) -> int:
        """Insert new orders into the database, returning count of inserted orders"""
        if not orders:
            return 0
            
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        inserted_count = 0
        for order in orders:
            try:
                # Extract relevant fields from the order
                robinhood_id = order.get('id', '')
                symbol = order.get('chain_symbol', '')
                created_at = order.get('created_at', '')
                
                # Process legs to extract option data
                legs = order.get('legs', [])
                if legs:
                    position_effect = legs[0].get('position_effect', '')
                    expiration_date = legs[0].get('expiration_date', '')
                    strike_price = '/'.join([f"{float(leg['strike_price']):.2f}" for leg in legs])
                    option_type = '/'.join([leg['option_type'] for leg in legs])
                    option_ids = json.dumps([leg['option'][-13:][:-1] for leg in legs])
                else:
                    position_effect = ''
                    expiration_date = ''
                    strike_price = ''
                    option_type = ''
                    option_ids = json.dumps([])
                
                price = float(order.get('price', 0)) if order.get('price') else None
                quantity = int(float(order.get('processed_quantity', 0))) if order.get('processed_quantity') else None
                premium = float(order.get('processed_premium', 0)) if order.get('processed_premium') else None
                strategy = order.get('opening_strategy') or order.get('closing_strategy', '')
                direction = order.get('direction', '')
                
                cursor.execute('''
                    INSERT OR IGNORE INTO option_orders 
                    (robinhood_id, symbol, created_at, position_effect, expiration_date, 
                     strike_price, price, quantity, premium, strategy, direction, 
                     option_type, option_ids, raw_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    robinhood_id, symbol, created_at, position_effect, expiration_date,
                    strike_price, price, quantity, premium, strategy, direction,
                    option_type, option_ids, json.dumps(order)
                ))
                
                if cursor.rowcount > 0:
                    inserted_count += 1
                    
            except Exception as e:
                print(f"Error inserting order {order.get('id', 'unknown')}: {str(e)}")
                continue
        
        conn.commit()
        conn.close()
        
        return inserted_count
    
    def get_all_raw_orders(self) -> List[Tuple]:
        """Get all orders from database as raw tuples for position building"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT option_ids, symbol, created_at, position_effect, expiration_date,
                   strike_price, price, quantity, premium, strategy, direction, option_type
            FROM option_orders
            ORDER BY created_at
        ''')
        
        orders = cursor.fetchall()
        conn.close()
        
        return orders
    
    def save_positions(self, positions: List[Position]) -> None:
        """Save processed positions to database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Clear existing positions
        cursor.execute('DELETE FROM positions')
        
        # Insert new positions
        for position in positions:
            cursor.execute('''
                INSERT OR REPLACE INTO positions 
                (option_key, symbol, open_date, close_date, expiration_date, strike_price,
                 quantity, open_price, close_price, open_premium, close_premium, net_credit,
                 strategy, direction, option_type, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                position.option_key, position.symbol, position.open_date, 
                position.close_date, position.expiration_date, position.strike_price,
                position.quantity, position.open_price, position.close_price,
                position.open_premium, position.close_premium, position.net_credit,
                position.strategy, position.direction, position.option_type,
                position.status
            ))
        
        conn.commit()
        conn.close()
    
    def get_positions_by_status(self, status: str) -> List[Position]:
        """Get positions filtered by status"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Filter out orphaned closing orders for all statuses
        cursor.execute('''
            SELECT option_key, symbol, open_date, close_date, expiration_date, strike_price,
                   quantity, open_price, close_price, open_premium, close_premium, net_credit,
                   strategy, direction, option_type, status
            FROM positions
            WHERE status = ? AND open_premium IS NOT NULL
            ORDER BY open_date DESC
        ''', (status,))
        
        columns = ['option_key', 'symbol', 'open_date', 'close_date', 'expiration_date', 
                  'strike_price', 'quantity', 'open_price', 'close_price', 'open_premium', 
                  'close_premium', 'net_credit', 'strategy', 'direction', 'option_type', 'status']
        
        results = []
        for row in cursor.fetchall():
            position_data = dict(zip(columns, row))
            results.append(Position.from_dict(position_data))
        
        conn.close()
        return results
    
    def get_all_orders_for_display(self) -> List[Dict]:
        """Get all orders formatted for display in the UI"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT symbol, created_at, position_effect, expiration_date, strike_price,
                   price, quantity, premium, strategy, direction, option_type, option_ids
            FROM option_orders
            ORDER BY created_at DESC
        ''')
        
        columns = ['symbol', 'created_at', 'position_effect', 'expiration_date', 
                  'strike_price', 'price', 'quantity', 'premium', 'strategy', 
                  'direction', 'option_type', 'option_ids']
        
        results = []
        for row in cursor.fetchall():
            order_dict = dict(zip(columns, row))
            # Parse option_ids back to list
            try:
                order_dict['option'] = json.loads(order_dict['option_ids'])
            except:
                order_dict['option'] = []
            del order_dict['option_ids']
            results.append(order_dict)
        
        conn.close()
        return results
    
    def get_daily_pnl_data(self, start_date: str = None, end_date: str = None) -> List[DailyPnLSummary]:
        """Get daily P&L summary data for calendar view"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = '''
            SELECT DATE(close_date) as day, 
                   SUM(CASE WHEN net_credit IS NOT NULL THEN net_credit ELSE 0 END) as daily_pnl,
                   COUNT(*) as position_count,
                   GROUP_CONCAT(symbol || ' (' || COALESCE(ROUND(net_credit, 2), 0) || ')') as position_details
            FROM positions 
            WHERE status IN ('closed', 'expired') AND close_date IS NOT NULL
        '''
        params = []
        
        if start_date:
            query += ' AND DATE(close_date) >= ?'
            params.append(start_date)
        if end_date:
            query += ' AND DATE(close_date) <= ?'
            params.append(end_date)
            
        query += ' GROUP BY DATE(close_date) ORDER BY close_date DESC'
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        daily_summaries = []
        for row in results:
            day, pnl, count, details = row
            daily_summaries.append(DailyPnLSummary(
                date=day,
                pnl=float(pnl) if pnl else 0.0,
                position_count=count,
                details=details if details else ''
            ))
        
        conn.close()
        return daily_summaries
    
    def get_positions_by_date(self, target_date: str) -> List[Position]:
        """Get all closed positions for a specific date"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT option_key, symbol, open_date, close_date, expiration_date, strike_price,
                   quantity, open_price, close_price, open_premium, close_premium, net_credit,
                   strategy, direction, option_type, status
            FROM positions
            WHERE status IN ('closed', 'expired') AND DATE(close_date) = ?
            ORDER BY close_date DESC
        ''', (target_date,))
        
        columns = ['option_key', 'symbol', 'open_date', 'close_date', 'expiration_date', 
                  'strike_price', 'quantity', 'open_price', 'close_price', 'open_premium', 
                  'close_premium', 'net_credit', 'strategy', 'direction', 'option_type', 'status']
        
        results = []
        for row in cursor.fetchall():
            position_data = dict(zip(columns, row))
            results.append(Position.from_dict(position_data))
        
        conn.close()
        return results