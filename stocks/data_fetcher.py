import robin_stocks.robinhood as r
import datetime
import traceback
from typing import Dict, List, Optional
from stocks.database import StocksDatabase

class StocksDataFetcher:
    def __init__(self, db_path: str = "stocks.db"):
        self.db = StocksDatabase(db_path)

    def login_robinhood(self, username: str = None, password: str = None) -> bool:
        """Login to Robinhood"""
        try:
            # Try to login with saved credentials first
            r.login()
            return True
        except Exception as e:
            # If login fails, prompt for credentials
            if not username or not password:
                import getpass
                print("Robinhood login required:")
                username = input("Enter your username: ")
                password = getpass.getpass("Enter your password: ")

            try:
                r.login(username, password)
                return True
            except Exception as login_error:
                print(f"Login failed: {str(login_error)}")
                return False

    def fetch_stock_orders(self) -> Dict:
        """Fetch stock orders from Robinhood"""
        try:
            print("Fetching stock orders from Robinhood...")

            # Get all stock orders
            all_orders = r.get_all_stock_orders()

            if not isinstance(all_orders, list):
                raise ValueError(f"Expected list of orders, got {type(all_orders)}")

            print(f"Found {len(all_orders)} total stock orders from API")

            # Filter for filled orders only
            filled_orders = [
                order for order in all_orders
                if order.get('state') == 'filled'
                and float(order.get('cumulative_quantity', 0)) > 0
            ]
            print(f"Found {len(filled_orders)} filled orders")

            # First, collect all unique instrument IDs and fetch their symbols
            print("Fetching instrument symbols...")
            instrument_ids = list(set(order.get('instrument_id') for order in filled_orders if order.get('instrument_id')))
            print(f"Found {len(instrument_ids)} unique instruments")

            # Build cache of instrument_id -> symbol
            instrument_cache = {}
            for i, inst_id in enumerate(instrument_ids):
                try:
                    url = f'https://api.robinhood.com/instruments/{inst_id}/'
                    instrument = r.get_instrument_by_url(url)
                    instrument_cache[inst_id] = instrument.get('symbol', 'UNKNOWN')

                    if (i + 1) % 10 == 0:
                        print(f"  Fetched {i + 1}/{len(instrument_ids)} symbols...")
                except Exception as e:
                    print(f"  Error fetching instrument {inst_id}: {e}")
                    instrument_cache[inst_id] = 'UNKNOWN'

            print(f"Fetched all {len(instrument_cache)} symbols")

            # Now process all orders using the cache
            print("Processing orders...")
            processed_orders = []
            for order in filled_orders:
                try:
                    # Get symbol from cache
                    instrument_id = order.get('instrument_id')
                    symbol = instrument_cache.get(instrument_id, 'UNKNOWN')

                    # Get trade date from execution, with fallback to last_transaction_at
                    trade_date = None

                    # Try to get from executions first (more accurate)
                    executions = order.get('executions', [])
                    if executions and executions[0].get('trade_execution_date'):
                        trade_date = executions[0].get('trade_execution_date')

                    # Fallback to extracting from last_transaction_at
                    if not trade_date:
                        last_transaction = order.get('last_transaction_at', '')
                        trade_date = last_transaction.split('T')[0] if last_transaction else None

                    processed_orders.append({
                        'order_id': order.get('id'),
                        'symbol': symbol,
                        'side': order.get('side'),  # 'buy' or 'sell'
                        'quantity': float(order.get('cumulative_quantity', 0)),
                        'average_price': float(order.get('average_price', 0)),
                        'total_amount': float(order.get('executed_notional', {}).get('amount', 0)),
                        'fees': float(order.get('fees', 0)),
                        'state': order.get('state'),
                        'created_at': order.get('created_at'),
                        'last_transaction_at': order.get('last_transaction_at'),
                        'trade_date': trade_date,
                        'raw_data': order
                    })
                except Exception as e:
                    print(f"Error processing order {order.get('id')}: {e}")
                    continue

            print(f"Processed all {len(processed_orders)} orders")

            # Insert into database
            inserted_count = self.db.insert_orders(processed_orders)
            print(f"Inserted {inserted_count} new orders (duplicates skipped)")

            return {
                'success': True,
                'orders_fetched': len(all_orders),
                'orders_inserted': inserted_count,
                'message': f"Successfully updated database with {inserted_count} new orders"
            }

        except Exception as e:
            print(f"Error fetching stock orders: {str(e)}")
            print(traceback.format_exc())
            return {
                'success': False,
                'error': 'Failed to fetch stock orders from Robinhood',
                'traceback': traceback.format_exc()
            }

    def get_open_positions(self) -> List[Dict]:
        """Get current open positions from Robinhood"""
        try:
            open_positions = r.get_open_stock_positions()

            if not open_positions:
                return []

            # Get current quotes for unrealized P&L
            positions_with_pnl = []
            for pos in open_positions:
                symbol = pos.get('symbol')
                quantity = float(pos.get('quantity', 0))
                avg_buy_price = float(pos.get('average_buy_price', 0))

                # Get current price
                try:
                    quote = r.get_stock_quote_by_symbol(symbol)
                    current_price = float(quote.get('last_trade_price', 0))
                except:
                    current_price = 0

                cost_basis = quantity * avg_buy_price
                market_value = quantity * current_price
                unrealized_pnl = market_value - cost_basis

                positions_with_pnl.append({
                    'symbol': symbol,
                    'quantity': quantity,
                    'average_buy_price': avg_buy_price,
                    'current_price': current_price,
                    'cost_basis': round(cost_basis, 2),
                    'market_value': round(market_value, 2),
                    'unrealized_pnl': round(unrealized_pnl, 2),
                    'created_at': pos.get('created_at'),
                    'updated_at': pos.get('updated_at')
                })

            return positions_with_pnl

        except Exception as e:
            print(f"Error getting open positions: {str(e)}")
            return []

    def get_processed_data(self, include_open_positions: bool = True) -> Dict:
        """Get processed data from database"""
        try:
            # Get all orders
            all_orders = self.db.get_all_orders()

            # Get open positions from Robinhood (only if logged in)
            open_positions = []
            if include_open_positions:
                try:
                    open_positions = self.get_open_positions()
                except Exception as e:
                    print(f"Could not fetch open positions (may not be logged in): {e}")
                    open_positions = []

            # Calculate P&L summary from CLOSED POSITIONS (FIFO matched)
            closed_positions = self.db.get_closed_positions()
            total_pnl = sum(pos['pnl'] for pos in closed_positions)

            # Calculate win rate
            winning_trades = sum(1 for pos in closed_positions if pos['pnl'] > 0)
            losing_trades = sum(1 for pos in closed_positions if pos['pnl'] < 0)
            breakeven_trades = sum(1 for pos in closed_positions if pos['pnl'] == 0)
            total_closed = len(closed_positions)
            win_rate = (winning_trades / total_closed * 100) if total_closed > 0 else 0

            # Also get daily breakdown and fees
            daily_pnl = self.db.get_daily_pnl()
            total_fees = sum(day['fees'] for day in daily_pnl.values())

            # Get total trading days (all days with any orders, not just closed positions)
            all_trading_dates = self.db.get_all_trading_dates()
            num_trading_days = len(all_trading_dates)

            # Calculate total possible trading days since first trade
            if all_trading_dates:
                from datetime import datetime
                first_trade_date = datetime.strptime(all_trading_dates[0], '%Y-%m-%d')
                last_trade_date = datetime.strptime(all_trading_dates[-1], '%Y-%m-%d')
                years_trading = (last_trade_date - first_trade_date).days / 365.25
                approx_market_days = int(years_trading * 252)  # ~252 trading days per year
            else:
                approx_market_days = 0

            # Calculate unrealized P&L from open positions
            total_unrealized_pnl = sum(pos['unrealized_pnl'] for pos in open_positions)

            pnl_summary = {
                'total_pnl': round(total_pnl, 2),
                'total_unrealized_pnl': round(total_unrealized_pnl, 2),
                'total_fees': round(total_fees, 2),
                'num_orders': len(all_orders),
                'num_open_positions': len(open_positions),
                'num_trading_days': num_trading_days,
                'approx_market_days': approx_market_days,
                'total_closed_positions': total_closed,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'win_rate': round(win_rate, 1)
            }

            print(f"P&L Summary: Total=${pnl_summary['total_pnl']:.2f}, Unrealized=${pnl_summary['total_unrealized_pnl']:.2f}, Orders={pnl_summary['num_orders']}, Days={num_trading_days}")

            return {
                'all_orders': all_orders,
                'open_positions': open_positions,
                'summary': pnl_summary
            }

        except Exception as e:
            print(f"Error getting processed data: {str(e)}")
            print(traceback.format_exc())
            return {
                'error': True,
                'message': 'Failed to retrieve processed data from database',
                'traceback': traceback.format_exc()
            }

    def update_data(self, username: str = None, password: str = None) -> Dict:
        """Update the database with latest data"""
        # Login first
        if not self.login_robinhood(username, password):
            return {
                'success': False,
                'error': 'Failed to login to Robinhood'
            }

        # Fetch and process data
        fetch_result = self.fetch_stock_orders()

        if fetch_result['success']:
            # Return processed data
            return self.get_processed_data()
        else:
            return fetch_result
