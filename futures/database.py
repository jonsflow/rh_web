import sqlite3
import json
import datetime
from typing import Dict, List, Optional

class FuturesDatabase:
    def __init__(self, db_path: str = "futures.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize the SQLite database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create futures_orders table based on Robinhood Futures API structure
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS futures_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT UNIQUE,
                account_id TEXT,
                contract_id TEXT,
                symbol TEXT,
                display_symbol TEXT,
                order_side TEXT,
                quantity INTEGER,
                filled_quantity INTEGER,
                order_type TEXT,
                order_state TEXT,
                average_price REAL,
                position_effect TEXT,
                realized_pnl REAL,
                realized_pnl_without_fees REAL,
                total_fee REAL,
                total_commission REAL,
                total_gold_savings REAL,
                created_at TEXT,
                updated_at TEXT,
                trade_date TEXT,
                execution_time TEXT,
                raw_data TEXT,
                fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create futures_positions table (computed from orders)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS futures_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position_key TEXT UNIQUE,
                contract_id TEXT,
                symbol TEXT,
                display_symbol TEXT,
                open_date TEXT,
                close_date TEXT,
                quantity INTEGER,
                open_price REAL,
                close_price REAL,
                open_value REAL,
                close_value REAL,
                realized_pnl REAL,
                realized_pnl_without_fees REAL,
                total_fees REAL,
                status TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create indexes for faster queries
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_order_id ON futures_orders(order_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_symbol ON futures_orders(symbol)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON futures_orders(created_at)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_trade_date ON futures_orders(trade_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_order_state ON futures_orders(order_state)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_position_key ON futures_positions(position_key)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_status ON futures_positions(status)')

        conn.commit()
        conn.close()

    def get_last_order_date(self) -> Optional[str]:
        """Get the date of the most recent order in the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT MAX(created_at) FROM futures_orders')
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
                # Extract order fields from Robinhood Futures API structure
                order_id = order.get('orderId', '')
                account_id = order.get('accountId', '')

                # Extract contract info from first leg
                legs = order.get('orderLegs', [])
                if legs:
                    leg = legs[0]
                    contract_id = leg.get('contractId', '')
                    order_side = leg.get('orderSide', '')
                    average_price = float(leg.get('averagePrice', 0))
                else:
                    contract_id = ''
                    order_side = ''
                    average_price = 0.0

                # Symbol info (we'll need to fetch this from contract lookup)
                symbol = order.get('symbol', '')
                display_symbol = order.get('displaySymbol', '')

                quantity = int(order.get('quantity', 0))
                filled_quantity = int(order.get('filledQuantity', 0))
                order_type = order.get('orderType', '')
                order_state = order.get('orderState', '')
                position_effect = order.get('positionEffectAtPlacementTime', '')
                created_at = order.get('createdAt', '')
                updated_at = order.get('updatedAt', '')

                # Extract execution time from executions
                executions = order.get('orderExecutions', [])
                if executions:
                    execution_time = executions[0].get('eventTime', '')
                    # Convert to Eastern time to get the correct trade date
                    if execution_time:
                        from datetime import datetime
                        import pytz

                        dt_utc = datetime.fromisoformat(execution_time.replace('Z', '+00:00'))
                        eastern = pytz.timezone('America/New_York')
                        dt_eastern = dt_utc.astimezone(eastern)
                        trade_date = dt_eastern.strftime('%Y-%m-%d')
                    else:
                        trade_date = ''
                else:
                    trade_date = ''
                    execution_time = ''

                # Extract P&L and fees (note the double-nested structure!)
                def get_amount(field):
                    if isinstance(field, dict) and 'amount' in field:
                        return float(field['amount'])
                    return 0.0

                pnl_data = order.get('realizedPnl', {})
                realized_pnl = get_amount(pnl_data.get('realizedPnl'))
                realized_pnl_without_fees = get_amount(pnl_data.get('realizedPnlWithoutFees'))

                total_fee = get_amount(order.get('totalFee'))
                total_commission = get_amount(order.get('totalCommission'))
                total_gold_savings = get_amount(order.get('totalGoldSavings'))

                cursor.execute('''
                    INSERT OR IGNORE INTO futures_orders
                    (order_id, account_id, contract_id, symbol, display_symbol, order_side,
                     quantity, filled_quantity, order_type, order_state, average_price,
                     position_effect, realized_pnl, realized_pnl_without_fees, total_fee,
                     total_commission, total_gold_savings, created_at, updated_at, trade_date, execution_time, raw_data)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    order_id, account_id, contract_id, symbol, display_symbol, order_side,
                    quantity, filled_quantity, order_type, order_state, average_price,
                    position_effect, realized_pnl, realized_pnl_without_fees, total_fee,
                    total_commission, total_gold_savings, created_at, updated_at, trade_date, execution_time,
                    json.dumps(order)
                ))

                if cursor.rowcount > 0:
                    inserted_count += 1

            except Exception as e:
                print(f"Error inserting order {order.get('orderId', 'unknown')}: {str(e)}")
                continue

        conn.commit()
        conn.close()

        return inserted_count

    def get_all_orders(self) -> List[Dict]:
        """Get all orders from the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM futures_orders ORDER BY created_at DESC')
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]

        conn.close()

        return [dict(zip(columns, row)) for row in rows]

    def get_orders_by_state(self, state: str) -> List[Dict]:
        """Get orders filtered by order state"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM futures_orders WHERE order_state = ? ORDER BY created_at DESC', (state,))
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]

        conn.close()

        return [dict(zip(columns, row)) for row in rows]

    def rebuild_positions(self):
        """Rebuild the positions table from orders (pair opening and closing orders)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Clear existing positions
        cursor.execute('DELETE FROM futures_positions')

        # Get all filled orders grouped by contract
        cursor.execute('''
            SELECT contract_id, symbol, display_symbol, order_side, quantity, average_price,
                   position_effect, created_at, realized_pnl, realized_pnl_without_fees, total_fee
            FROM futures_orders
            WHERE order_state = 'FILLED'
            ORDER BY contract_id, created_at
        ''')

        orders = cursor.fetchall()

        # Group orders by contract to pair opens/closes
        positions = {}

        for order in orders:
            contract_id, symbol, display_symbol, order_side, qty, price, pos_effect, created_at, pnl, pnl_no_fees, fees = order

            key = contract_id

            if key not in positions:
                positions[key] = {
                    'contract_id': contract_id,
                    'symbol': symbol,
                    'display_symbol': display_symbol,
                    'open_orders': [],
                    'close_orders': []
                }

            order_data = {
                'side': order_side,
                'quantity': qty,
                'price': price,
                'date': created_at,
                'pnl': pnl,
                'pnl_no_fees': pnl_no_fees,
                'fees': fees
            }

            if pos_effect == 'OPENING':
                positions[key]['open_orders'].append(order_data)
            elif pos_effect == 'CLOSING':
                positions[key]['close_orders'].append(order_data)

        # Create position records
        for key, pos_data in positions.items():
            if pos_data['open_orders']:
                # Calculate averages for open orders
                total_qty = sum(o['quantity'] for o in pos_data['open_orders'])
                avg_open_price = sum(o['price'] * o['quantity'] for o in pos_data['open_orders']) / total_qty if total_qty > 0 else 0
                open_date = min(o['date'] for o in pos_data['open_orders'])

                # If there are close orders, mark as closed
                if pos_data['close_orders']:
                    avg_close_price = sum(o['price'] * o['quantity'] for o in pos_data['close_orders']) / total_qty if total_qty > 0 else 0
                    close_date = max(o['date'] for o in pos_data['close_orders'])
                    realized_pnl = sum(o['pnl'] for o in pos_data['close_orders'])
                    realized_pnl_no_fees = sum(o['pnl_no_fees'] for o in pos_data['close_orders'])
                    total_fees = sum(o['fees'] for o in pos_data['close_orders'])
                    status = 'closed'
                else:
                    avg_close_price = None
                    close_date = None
                    realized_pnl = None
                    realized_pnl_no_fees = None
                    total_fees = None
                    status = 'open'

                position_key = f"{pos_data['contract_id']}_{open_date}"

                cursor.execute('''
                    INSERT OR REPLACE INTO futures_positions
                    (position_key, contract_id, symbol, display_symbol, open_date, close_date,
                     quantity, open_price, close_price, realized_pnl, realized_pnl_without_fees,
                     total_fees, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    position_key, pos_data['contract_id'], pos_data['symbol'], pos_data['display_symbol'],
                    open_date, close_date, total_qty, avg_open_price, avg_close_price,
                    realized_pnl, realized_pnl_no_fees, total_fees, status
                ))

        conn.commit()
        conn.close()

    def get_all_positions(self) -> List[Dict]:
        """Get all positions from the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM futures_positions ORDER BY open_date DESC')
        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]

        conn.close()

        return [dict(zip(columns, row)) for row in rows]

    def get_positions_by_status(self, status: str) -> List[Dict]:
        """
        Get positions filtered by status.
        For 'closed' status, returns closing orders (where realized_pnl_without_fees != 0).
        For other statuses, uses the futures_positions table.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if status == 'closed':
            # For closed positions, return orders where realized_pnl_without_fees != 0
            # These are the closing orders that have actual P&L
            cursor.execute('''
                SELECT
                    order_id,
                    contract_id,
                    symbol,
                    display_symbol,
                    order_side,
                    position_effect,
                    filled_quantity as quantity,
                    average_price as close_price,
                    realized_pnl,
                    realized_pnl_without_fees,
                    total_fee,
                    created_at as close_date,
                    execution_time,
                    trade_date
                FROM futures_orders
                WHERE order_state = 'FILLED'
                AND realized_pnl_without_fees != 0
                ORDER BY COALESCE(execution_time, created_at) DESC
            ''')
        else:
            # For other statuses, use the positions table
            cursor.execute('SELECT * FROM futures_positions WHERE status = ? ORDER BY open_date DESC', (status,))

        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]

        conn.close()

        return [dict(zip(columns, row)) for row in rows]

    def get_daily_pnl(self, start_date: str = None, end_date: str = None) -> Dict[str, Dict]:
        """
        Get daily P&L summary grouped by trade_date.
        Simply sums realized_pnl from all orders for each date.
        This matches Robinhood's Purchase and Sale Summary report.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = '''
            SELECT
                trade_date,
                SUM(realized_pnl) as total_pnl,
                SUM(realized_pnl_without_fees) as total_pnl_no_fees,
                SUM(total_fee) as total_fees,
                COUNT(*) as order_count
            FROM futures_orders
            WHERE order_state = 'FILLED' AND trade_date IS NOT NULL
        '''
        params = []

        if start_date:
            query += ' AND trade_date >= ?'
            params.append(start_date)
        if end_date:
            query += ' AND trade_date <= ?'
            params.append(end_date)

        query += ' GROUP BY trade_date ORDER BY trade_date DESC'

        cursor.execute(query, params)
        rows = cursor.fetchall()

        conn.close()

        # Return as dictionary keyed by date
        result = {}
        for row in rows:
            trade_date, total_pnl, total_pnl_no_fees, total_fees, order_count = row
            result[trade_date] = {
                'pnl': round(total_pnl, 2) if total_pnl else 0,
                'pnl_no_fees': round(total_pnl_no_fees, 2) if total_pnl_no_fees else 0,
                'fees': round(total_fees, 2) if total_fees else 0,
                'count': order_count
            }

        return result

    def get_orders_by_trade_date(self, trade_date: str) -> List[Dict]:
        """Get all orders for a specific trade date"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM futures_orders
            WHERE trade_date = ? AND order_state = 'FILLED'
            ORDER BY execution_time
        ''', (trade_date,))

        rows = cursor.fetchall()
        columns = [description[0] for description in cursor.description]

        conn.close()

        return [dict(zip(columns, row)) for row in rows]
