import robin_stocks.robinhood as r
import datetime
import traceback
import json
import os
from typing import Dict, List, Optional
from futures.database import FuturesDatabase

class FuturesDataFetcher:
    def __init__(self, db_path: str = "futures.db", config_path: str = "config.json"):
        self.db = FuturesDatabase(db_path)
        self.config = self.load_config(config_path)
        self.futures_account_id = None

    def load_config(self, config_path: str) -> Dict:
        """Load configuration from JSON file with fallback defaults"""
        default_config = {
            "data_fetching": {
                "default_start_date": "2024-01-01",
                "default_days_back": 60,
                "full_refresh_days_back": 90,
                "use_start_of_year": True,
                "incremental_buffer_days": 1
            }
        }

        try:
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    # Merge with defaults to ensure all keys exist
                    for key in default_config["data_fetching"]:
                        if key not in config.get("data_fetching", {}):
                            config.setdefault("data_fetching", {})[key] = default_config["data_fetching"][key]
                    return config
            else:
                print(f"Config file {config_path} not found, using defaults")
                return default_config
        except Exception as e:
            print(f"Error loading config file {config_path}: {e}, using defaults")
            return default_config

    def login_robinhood(self, username: str = None, password: str = None) -> bool:
        """Login to Robinhood with terminal-based credential handling"""
        try:
            # Try to login with saved credentials first
            r.login()
            return True
        except Exception as e:
            # If login fails, prompt for credentials in terminal
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

    def get_futures_account_id(self) -> Optional[str]:
        """Discover and cache the futures account ID"""
        if self.futures_account_id:
            return self.futures_account_id

        try:
            # Use robin_stocks to get futures account ID
            account_id = r.get_futures_account_id()

            if account_id:
                self.futures_account_id = account_id
                print(f"Found futures account: {account_id}")
                return account_id
            else:
                print("No futures account found")
                return None

        except Exception as e:
            print(f"Error getting futures account ID: {e}")
            return None

    def fetch_futures_orders(self, force_full_refresh: bool = False) -> Dict:
        """Fetch futures orders with incremental updates"""
        try:
            # Get futures account ID
            account_id = self.get_futures_account_id()
            if not account_id:
                return {
                    'success': False,
                    'error': 'No futures account found. You may not have a futures trading account enabled.'
                }

            print(f"Fetching futures orders for account {account_id}")

            # Use robin_stocks to get ALL orders (needed for accurate P&L calculation)
            # NOTE: calculate_total_futures_pnl needs all order states, not just filled
            all_orders = r.get_all_futures_orders(account_id=account_id)

            if not isinstance(all_orders, list):
                raise ValueError(f"Expected list of orders, got {type(all_orders)}")

            print(f"Found {len(all_orders)} total futures orders from API")

            # Filter for filled orders to store in database
            filled_orders = [order for order in all_orders if order.get('orderState') == 'FILLED']
            print(f"Found {len(filled_orders)} filled orders")

            # Get last order date from database to see if we have new orders
            last_order_date = self.db.get_last_order_date()
            if last_order_date:
                print(f"Last order in database: {last_order_date}")
            else:
                print("No existing orders in database - first fetch")

            # Insert filled orders into database (INSERT OR IGNORE handles deduplication)
            inserted_count = self.db.insert_orders(filled_orders)
            print(f"Inserted {inserted_count} new orders (duplicates skipped)")

            # Rebuild positions table
            self.db.rebuild_positions()
            print("Rebuilt positions table")

            return {
                'success': True,
                'orders_fetched': len(all_orders),
                'orders_inserted': inserted_count,
                'message': f"Successfully updated database with {inserted_count} new orders"
            }

        except Exception as e:
            print(f"Error fetching futures orders: {str(e)}")
            print(traceback.format_exc())
            return {
                'success': False,
                'error': 'Failed to fetch futures orders from Robinhood',
                'traceback': traceback.format_exc()
            }

    def get_processed_data(self) -> Dict:
        """Get processed data from database"""
        try:
            # Get data directly from database
            all_orders = self.db.get_all_orders()
            open_positions = self.db.get_positions_by_status('open')
            closed_positions = self.db.get_positions_by_status('closed')

            # Calculate P&L summary using our simplified database method
            # This sums realized_pnl directly from the database
            daily_pnl = self.db.get_daily_pnl()

            # Calculate totals
            total_pnl = sum(day['pnl'] for day in daily_pnl.values())
            total_fees = sum(day['fees'] for day in daily_pnl.values())
            total_pnl_no_fees = sum(day['pnl_no_fees'] for day in daily_pnl.values())
            num_trading_days = len(daily_pnl)

            # Get filled orders count
            filled_orders = [o for o in all_orders if o.get('order_state') == 'FILLED']

            pnl_summary = {
                'total_pnl': round(total_pnl, 2),
                'total_pnl_without_fees': round(total_pnl_no_fees, 2),
                'total_fees': round(total_fees, 2),
                'num_orders': len(filled_orders),
                'num_trading_days': num_trading_days
            }

            print(f"P&L Summary: Total=${pnl_summary['total_pnl']:.2f}, Orders={pnl_summary['num_orders']}, Days={num_trading_days}")

            return {
                'open_positions': open_positions,
                'closed_positions': closed_positions,
                'all_orders': all_orders,
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

    def update_data(self, username: str = None, password: str = None, force_full_refresh: bool = False) -> Dict:
        """Update the database with latest data"""
        # Login first
        if not self.login_robinhood(username, password):
            return {
                'success': False,
                'error': 'Failed to login to Robinhood'
            }

        # Fetch and process data
        fetch_result = self.fetch_futures_orders(force_full_refresh=force_full_refresh)

        if fetch_result['success']:
            # Return processed data
            return self.get_processed_data()
        else:
            return fetch_result
