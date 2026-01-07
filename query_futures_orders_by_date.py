#!/usr/bin/env python3
"""
Query futures orders from the futures database by date.
Usage: python query_futures_orders_by_date.py [--date YYYY-MM-DD]
"""

import sqlite3
import argparse
from datetime import datetime
from typing import List, Dict
import json

def query_futures_orders_by_date(db_path: str, target_date: str) -> List[Dict]:
    """
    Query futures orders for a specific date.

    Args:
        db_path: Path to the SQLite database
        target_date: Date in format YYYY-MM-DD (e.g., '2025-06-17')

    Returns:
        List of order dictionaries
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Date must be in YYYY-MM-DD format
    pattern = f'{target_date}%'
    print(f"Searching for futures orders on {target_date}")

    # First, show sample dates to understand the format
    cursor.execute("SELECT created_at, execution_time FROM futures_orders LIMIT 5")
    sample_dates = cursor.fetchall()
    print("\nSample dates from futures database:")
    for date in sample_dates:
        print(f"  Created: {date[0]}, Execution: {date[1]}")

    # Query for futures orders on the target date
    # We'll check both created_at and execution_time
    # Note: order_state is stored as 'FILLED' (uppercase)
    query = '''
        SELECT order_id, account_id, contract_id, symbol, display_symbol,
               order_side, quantity, filled_quantity, order_type, order_state,
               average_price, position_effect, realized_pnl, realized_pnl_without_fees,
               total_fee, total_commission, total_gold_savings,
               created_at, updated_at, trade_date, execution_time
        FROM futures_orders
        WHERE (created_at LIKE ? OR execution_time LIKE ? OR trade_date LIKE ?)
        AND order_state = 'FILLED'
        ORDER BY COALESCE(execution_time, created_at)
    '''

    cursor.execute(query, (pattern, pattern, pattern))
    orders = cursor.fetchall()

    columns = ['order_id', 'account_id', 'contract_id', 'symbol', 'display_symbol',
               'order_side', 'quantity', 'filled_quantity', 'order_type', 'order_state',
               'average_price', 'position_effect', 'realized_pnl', 'realized_pnl_without_fees',
               'total_fee', 'total_commission', 'total_gold_savings',
               'created_at', 'updated_at', 'trade_date', 'execution_time']

    results = []
    for order in orders:
        results.append(dict(zip(columns, order)))

    conn.close()
    return results


def display_futures_orders(orders: List[Dict]):
    """Display futures orders in a readable format."""
    print(f"\n{'='*80}")
    print(f"FUTURES ORDERS FOUND: {len(orders)}")
    print(f"{'='*80}\n")

    if not orders:
        print("No futures orders found for this date.")
        return

    for i, order in enumerate(orders, 1):
        print(f"\nOrder #{i}:")
        print(f"  {'Order ID':25s}: {order['order_id']}")
        print(f"  {'Contract ID':25s}: {order['contract_id']}")
        print(f"  {'Symbol':25s}: {order['display_symbol']} ({order['symbol']})")
        print(f"  {'Side':25s}: {order['order_side']}")
        print(f"  {'Position Effect':25s}: {order['position_effect']}")
        print(f"  {'Quantity':25s}: {order['filled_quantity']} / {order['quantity']}")
        print(f"  {'Order Type':25s}: {order['order_type']}")
        print(f"  {'Avg Price':25s}: ${order['average_price']:,.2f}" if order['average_price'] else f"  {'Avg Price':25s}: N/A")
        print(f"  {'Realized P&L':25s}: ${order['realized_pnl']:,.2f}" if order['realized_pnl'] else f"  {'Realized P&L':25s}: N/A")
        print(f"  {'P&L (no fees)':25s}: ${order['realized_pnl_without_fees']:,.2f}" if order['realized_pnl_without_fees'] else f"  {'P&L (no fees)':25s}: N/A")
        print(f"  {'Total Fees':25s}: ${order['total_fee']:,.2f}" if order['total_fee'] else f"  {'Total Fees':25s}: N/A")
        print(f"  {'Created At':25s}: {order['created_at']}")
        print(f"  {'Execution Time':25s}: {order['execution_time']}")
        print(f"  {'Trade Date':25s}: {order['trade_date']}")


def main():
    parser = argparse.ArgumentParser(description='Query futures orders by date')
    parser.add_argument('--date', '-d', required=True,
                        help='Date to query (YYYY-MM-DD format required, e.g., 2025-06-17)')
    parser.add_argument('--db', default='futures.db',
                        help='Path to futures database file. Default: futures.db')

    args = parser.parse_args()

    # Validate date format
    if len(args.date.split('-')) != 3:
        print("ERROR: Date must be in YYYY-MM-DD format (e.g., 2025-06-17)")
        return

    # Query orders
    orders = query_futures_orders_by_date(args.db, args.date)

    # Display results
    display_futures_orders(orders)

    # Print summary by symbol and position effect
    if orders:
        print(f"\n{'='*80}")
        print("SUMMARY BY SYMBOL")
        print(f"{'='*80}")

        symbol_summary = {}
        for order in orders:
            symbol = order['display_symbol']
            if symbol not in symbol_summary:
                symbol_summary[symbol] = {
                    'buy_open': 0,
                    'buy_close': 0,
                    'sell_open': 0,
                    'sell_close': 0,
                    'total_pnl': 0,
                    'total_fees': 0
                }

            # position_effect is 'OPENING' or 'CLOSING' (uppercase)
            side = order['order_side'].lower()  # 'BUY' or 'SELL' -> lowercase
            effect = 'open' if order['position_effect'] == 'OPENING' else 'close'
            key = f"{side}_{effect}"
            symbol_summary[symbol][key] += order['filled_quantity']

            if order['realized_pnl']:
                symbol_summary[symbol]['total_pnl'] += order['realized_pnl']
            if order['total_fee']:
                symbol_summary[symbol]['total_fees'] += order['total_fee']

        for symbol, stats in symbol_summary.items():
            print(f"\n{symbol}:")
            print(f"  Buy to Open:   {stats['buy_open']} contracts")
            print(f"  Sell to Close: {stats['sell_close']} contracts")
            print(f"  Sell to Open:  {stats['sell_open']} contracts")
            print(f"  Buy to Close:  {stats['buy_close']} contracts")
            print(f"  Total P&L:     ${stats['total_pnl']:,.2f}")
            print(f"  Total Fees:    ${stats['total_fees']:,.2f}")


if __name__ == '__main__':
    main()
