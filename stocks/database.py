import sqlite3
import json
import datetime
from typing import Dict, List, Optional

class StocksDatabase:
    def __init__(self, db_path: str = "stocks.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize the SQLite database with required tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create stock_orders table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stock_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT UNIQUE,
                symbol TEXT,
                side TEXT,
                quantity REAL,
                average_price REAL,
                total_amount REAL,
                fees REAL DEFAULT 0,
                state TEXT,
                created_at TEXT,
                last_transaction_at TEXT,
                trade_date TEXT,
                raw_data TEXT,
                fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_order_id ON stock_orders(order_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_symbol ON stock_orders(symbol)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_trade_date ON stock_orders(trade_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_state ON stock_orders(state)')

        conn.commit()
        conn.close()

    def get_last_order_date(self) -> Optional[str]:
        """Get the date of the most recent order in the database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('SELECT MAX(created_at) FROM stock_orders')
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
                cursor.execute('''
                    INSERT OR IGNORE INTO stock_orders (
                        order_id, symbol, side, quantity, average_price,
                        total_amount, fees, state, created_at, last_transaction_at,
                        trade_date, raw_data
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    order.get('order_id'),
                    order.get('symbol'),
                    order.get('side'),
                    float(order.get('quantity', 0)),
                    float(order.get('average_price', 0)),
                    float(order.get('total_amount', 0)),
                    float(order.get('fees', 0)),
                    order.get('state'),
                    order.get('created_at'),
                    order.get('last_transaction_at'),
                    order.get('trade_date'),
                    json.dumps(order.get('raw_data', {}))
                ))
                if cursor.rowcount > 0:
                    inserted_count += 1
            except Exception as e:
                print(f"Error inserting order {order.get('order_id')}: {e}")

        conn.commit()
        conn.close()
        return inserted_count

    def get_all_orders(self) -> List[Dict]:
        """Get all orders from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT order_id, symbol, side, quantity, average_price,
                   total_amount, fees, state, created_at, last_transaction_at, trade_date
            FROM stock_orders
            WHERE state = 'filled'
            ORDER BY last_transaction_at DESC
        ''')

        orders = []
        for row in cursor.fetchall():
            orders.append({
                'order_id': row[0],
                'symbol': row[1],
                'side': row[2],
                'quantity': row[3],
                'average_price': row[4],
                'total_amount': row[5],
                'fees': row[6],
                'state': row[7],
                'created_at': row[8],
                'last_transaction_at': row[9],
                'trade_date': row[10]
            })

        conn.close()
        return orders

    def get_closed_positions(self) -> List[Dict]:
        """
        Get all closed positions with FIFO P&L calculation.
        Returns list of closed position pairs.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get all orders by symbol
        cursor.execute('''
            SELECT symbol, side, quantity, total_amount, average_price, trade_date, last_transaction_at
            FROM stock_orders
            WHERE state = 'filled'
            ORDER BY symbol, last_transaction_at
        ''')

        # Group by symbol
        from collections import defaultdict
        symbol_orders = defaultdict(list)

        for row in cursor.fetchall():
            symbol, side, qty, total, avg_price, date, timestamp = row
            symbol_orders[symbol].append({
                'side': side,
                'quantity': float(qty or 0),
                'total_amount': float(total or 0),
                'average_price': float(avg_price or 0),
                'trade_date': date,
                'timestamp': timestamp
            })

        conn.close()

        # Calculate closed positions using FIFO
        closed_positions = []

        for symbol, orders in symbol_orders.items():
            buy_queue = []  # FIFO queue of buys

            for order in orders:
                if order['side'] == 'buy':
                    # Add to buy queue
                    buy_queue.append({
                        'quantity': order['quantity'],
                        'price': order['average_price'],
                        'cost': order['total_amount'],
                        'date': order['trade_date']
                    })
                else:  # sell
                    sell_qty = order['quantity']
                    sell_proceeds = order['total_amount']
                    sell_price = order['average_price']
                    sell_date = order['trade_date']

                    # Match against buy queue (FIFO)
                    while sell_qty > 0 and buy_queue:
                        buy = buy_queue[0]

                        matched_qty = min(buy['quantity'], sell_qty)
                        portion = matched_qty / order['quantity']
                        matched_proceeds = sell_proceeds * portion
                        matched_cost = (matched_qty / buy['quantity']) * buy['cost']

                        # Create closed position record
                        closed_positions.append({
                            'symbol': symbol,
                            'quantity': matched_qty,
                            'buy_price': buy['price'],
                            'sell_price': sell_price,
                            'buy_date': buy['date'],
                            'sell_date': sell_date,
                            'cost': round(matched_cost, 2),
                            'proceeds': round(matched_proceeds, 2),
                            'pnl': round(matched_proceeds - matched_cost, 2)
                        })

                        if buy['quantity'] <= sell_qty:
                            # Fully use this buy
                            sell_qty -= buy['quantity']
                            buy_queue.pop(0)
                        else:
                            # Partially use this buy
                            buy['quantity'] -= sell_qty
                            buy['cost'] -= matched_cost
                            sell_qty = 0

        return closed_positions

    def get_total_realized_pnl(self) -> float:
        """Get total realized P&L from closed positions"""
        closed = self.get_closed_positions()
        return sum(pos['pnl'] for pos in closed)

    def get_daily_pnl(self, start_date=None, end_date=None) -> Dict:
        """
        Get daily realized P&L summary.
        Only counts P&L from properly FIFO-matched closed positions.
        P&L is attributed to the sell date.
        """
        # Get all closed positions (FIFO matched)
        closed_positions = self.get_closed_positions()

        # Group by sell_date
        daily_pnl = {}
        for pos in closed_positions:
            sell_date = pos['sell_date']

            # Apply date filters if provided
            if start_date and sell_date < start_date:
                continue
            if end_date and sell_date > end_date:
                continue

            if sell_date not in daily_pnl:
                daily_pnl[sell_date] = {
                    'pnl': 0,
                    'fees': 0,
                    'pnl_no_fees': 0,
                    'count': 0
                }

            daily_pnl[sell_date]['pnl'] += pos['pnl']
            daily_pnl[sell_date]['count'] += 1

        # Round all values
        for date in daily_pnl:
            daily_pnl[date]['pnl'] = round(daily_pnl[date]['pnl'], 2)
            daily_pnl[date]['pnl_no_fees'] = round(daily_pnl[date]['pnl'], 2)  # stocks have no fees

        return daily_pnl

    def get_all_trading_dates(self) -> List[str]:
        """Get all unique trading dates with activity"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT DISTINCT trade_date
            FROM stock_orders
            WHERE state = 'filled' AND trade_date IS NOT NULL
            ORDER BY trade_date
        ''')

        dates = [row[0] for row in cursor.fetchall()]

        conn.close()
        return dates

    def get_orders_by_trade_date(self, trade_date: str) -> List[Dict]:
        """Get all orders for a specific trade date"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT order_id, symbol, side, quantity, average_price,
                   total_amount, fees, last_transaction_at
            FROM stock_orders
            WHERE trade_date = ? AND state = 'filled'
            ORDER BY last_transaction_at
        ''', (trade_date,))

        orders = []
        for row in cursor.fetchall():
            orders.append({
                'order_id': row[0],
                'symbol': row[1],
                'side': row[2],
                'quantity': row[3],
                'average_price': row[4],
                'total_amount': row[5],
                'fees': row[6],
                'execution_time': row[7]
            })

        conn.close()
        return orders

    def get_daily_summary(self, trade_date: str) -> Dict:
        """
        Get daily summary showing both opened and closed positions for this date.
        Closed positions show buy/sell prices with P&L.
        Opened positions show buy price only (no P&L since not closed yet).
        """
        from collections import defaultdict

        # Get all closed positions that were sold on this date
        closed_positions = self.get_closed_positions()

        # Group closed positions by symbol
        closed_data = defaultdict(lambda: {
            'total_quantity': 0,
            'total_cost': 0,
            'total_proceeds': 0,
            'total_pnl': 0,
            'positions_count': 0
        })

        for pos in closed_positions:
            if pos['sell_date'] == trade_date:
                symbol = pos['symbol']
                closed_data[symbol]['total_quantity'] += pos['quantity']
                closed_data[symbol]['total_cost'] += pos['cost']
                closed_data[symbol]['total_proceeds'] += pos['proceeds']
                closed_data[symbol]['total_pnl'] += pos['pnl']
                closed_data[symbol]['positions_count'] += 1

        # Build closed positions list
        closed_symbols = []
        total_closed_quantity = 0
        total_pnl = 0

        for symbol in sorted(closed_data.keys()):
            data = closed_data[symbol]
            quantity = data['total_quantity']
            avg_buy_price = data['total_cost'] / quantity if quantity > 0 else 0
            avg_sell_price = data['total_proceeds'] / quantity if quantity > 0 else 0

            closed_symbols.append({
                'symbol': symbol,
                'quantity': quantity,
                'avg_buy_price': round(avg_buy_price, 2),
                'avg_sell_price': round(avg_sell_price, 2),
                'pnl': round(data['total_pnl'], 2)
            })

            total_closed_quantity += quantity
            total_pnl += data['total_pnl']

        # Get opened positions (buy orders on this date that weren't immediately sold)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT symbol, quantity, average_price
            FROM stock_orders
            WHERE trade_date = ? AND state = 'filled' AND side = 'buy'
            ORDER BY symbol
        ''', (trade_date,))

        # Group opened positions by symbol
        opened_data = defaultdict(lambda: {
            'total_quantity': 0,
            'total_cost': 0
        })

        for row in cursor.fetchall():
            symbol, quantity, avg_price = row
            opened_data[symbol]['total_quantity'] += float(quantity or 0)
            opened_data[symbol]['total_cost'] += float(quantity or 0) * float(avg_price or 0)

        conn.close()

        # Build opened positions list
        opened_symbols = []
        total_opened_quantity = 0

        for symbol in sorted(opened_data.keys()):
            data = opened_data[symbol]
            quantity = data['total_quantity']
            avg_buy_price = data['total_cost'] / quantity if quantity > 0 else 0

            opened_symbols.append({
                'symbol': symbol,
                'quantity': quantity,
                'avg_buy_price': round(avg_buy_price, 2)
            })

            total_opened_quantity += quantity

        return {
            'date': trade_date,
            'closed_positions': closed_symbols,
            'opened_positions': opened_symbols,
            'totals': {
                'positions_closed': len(closed_symbols),
                'positions_opened': len(opened_symbols),
                'total_closed_quantity': total_closed_quantity,
                'total_opened_quantity': total_opened_quantity,
                'total_pnl': round(total_pnl, 2)
            }
        }
