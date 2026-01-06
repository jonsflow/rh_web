import sqlite3
import json
import datetime
import pandas as pd
from typing import Dict, List, Optional, Tuple
import os
from services.pnl_calculator import PnLCalculator
from services.position_classifier import PositionClassifier

class OptionsDatabase:
    def __init__(self, db_path: str = "options.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the SQLite database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create option_orders table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS option_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                robinhood_id TEXT UNIQUE,
                symbol TEXT,
                created_at TEXT,
                position_effect TEXT,
                expiration_date TEXT,
                strike_price TEXT,
                price REAL,
                quantity INTEGER,
                premium REAL,
                strategy TEXT,
                direction TEXT,
                option_type TEXT,
                option_ids TEXT,
                raw_data TEXT,
                fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create positions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                option_key TEXT UNIQUE,
                symbol TEXT,
                open_date TEXT,
                close_date TEXT,
                expiration_date TEXT,
                strike_price TEXT,
                quantity INTEGER,
                open_price REAL,
                close_price REAL,
                open_premium REAL,
                close_premium REAL,
                net_credit REAL,
                strategy TEXT,
                direction TEXT,
                option_type TEXT,
                status TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create index for faster queries
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_robinhood_id ON option_orders(robinhood_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_symbol ON option_orders(symbol)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON option_orders(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_option_key ON positions(option_key)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_status ON positions(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_close_date ON positions(close_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_status_close_date ON positions(status, close_date)')
        
        conn.commit()
        conn.close()
    
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
    
    def rebuild_positions(self):
        """Rebuild the positions table from option_orders using the service layer"""
        from services.option_service import OptionService
        
        # Use the service to handle all the complex position building logic
        option_service = OptionService(self.db_path)
        positions_processed = option_service.rebuild_all_positions()
        
        print(f"Rebuilt {positions_processed} positions using service layer")
    
    
    def get_positions_by_status(self, status: str) -> List[Dict]:
        """Get positions filtered by status"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # For open positions, filter out orphaned closing orders (positions with no open_premium)
        # This uses the same logic as PositionClassifier.has_orphaned_close_orders()
        if status == 'open':
            cursor.execute('''
                SELECT option_key, symbol, open_date, close_date, expiration_date, strike_price,
                       quantity, open_price, close_price, open_premium, close_premium, net_credit,
                       strategy, direction, option_type, status
                FROM positions
                WHERE status = ? AND open_premium IS NOT NULL
                ORDER BY open_date DESC
            ''', (status,))
        else:
            cursor.execute('''
                SELECT option_key, symbol, open_date, close_date, expiration_date, strike_price,
                       quantity, open_price, close_price, open_premium, close_premium, net_credit,
                       strategy, direction, option_type, status
                FROM positions
                WHERE status = ?
                ORDER BY open_date DESC
            ''', (status,))
        
        columns = ['option_key', 'symbol', 'open_date', 'close_date', 'expiration_date', 
                  'strike_price', 'quantity', 'open_price', 'close_price', 'open_premium', 
                  'close_premium', 'net_credit', 'strategy', 'direction', 'option_type', 'status']
        
        results = []
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
        
        conn.close()
        return results
    
    def get_all_orders(self) -> List[Dict]:
        """Get all orders from the database"""
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
    
    def get_daily_pnl_summary(self, start_date: str = None, end_date: str = None) -> Dict:
        """Get daily PnL summary with optional date filtering for calendar view"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # First, let's debug what we have in the database
        debug_query = '''
            SELECT status, COUNT(*), 
                   COUNT(CASE WHEN close_date IS NOT NULL THEN 1 END) as with_close_date,
                   COUNT(CASE WHEN net_credit IS NOT NULL THEN 1 END) as with_net_credit
            FROM positions 
            GROUP BY status
        '''
        cursor.execute(debug_query)
        debug_results = cursor.fetchall()
        print("Database debug info:")
        for row in debug_results:
            print(f"  Status: {row[0]}, Count: {row[1]}, With close_date: {row[2]}, With net_credit: {row[3]}")
        
        # Main query with better filtering
        query = '''
            SELECT DATE(close_date) as day, 
                   SUM(CASE WHEN net_credit IS NOT NULL THEN net_credit ELSE 0 END) as daily_pnl,
                   COUNT(*) as position_count,
                   GROUP_CONCAT(symbol || ' (' || COALESCE(ROUND(net_credit, 2), 0) || ')') as position_details,
                   MIN(close_date) as first_close_time,
                   MAX(close_date) as last_close_time
            FROM positions 
            WHERE status = 'closed' AND close_date IS NOT NULL
        '''
        params = []
        
        if start_date:
            query += ' AND DATE(close_date) >= ?'
            params.append(start_date)
        if end_date:
            query += ' AND DATE(close_date) <= ?'
            params.append(end_date)
            
        query += ' GROUP BY DATE(close_date) ORDER BY close_date DESC'
        
        print(f"Executing query with params: {params}")
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        daily_data = {}
        for row in results:
            day, pnl, count, details, first_time, last_time = row
            print(f"Date: {day}, PnL: {pnl}, Count: {count}, First: {first_time}, Last: {last_time}")
            daily_data[day] = {
                'pnl': round(float(pnl), 2) if pnl else 0,
                'count': count,
                'details': details if details else ''
            }
        
        print(f"Returning {len(daily_data)} days of data")
        conn.close()
        return daily_data
    
    def get_positions_by_date(self, target_date: str) -> List[Dict]:
        """Get all closed positions for a specific date"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT option_key, symbol, open_date, close_date, expiration_date, strike_price,
                   quantity, open_price, close_price, open_premium, close_premium, net_credit,
                   strategy, direction, option_type, status
            FROM positions
            WHERE status = 'closed' AND DATE(close_date) = ?
            ORDER BY close_date DESC
        ''', (target_date,))
        
        columns = ['option_key', 'symbol', 'open_date', 'close_date', 'expiration_date', 
                  'strike_price', 'quantity', 'open_price', 'close_price', 'open_premium', 
                  'close_premium', 'net_credit', 'strategy', 'direction', 'option_type', 'status']
        
        results = []
        for row in cursor.fetchall():
            results.append(dict(zip(columns, row)))
        
        conn.close()
        return results