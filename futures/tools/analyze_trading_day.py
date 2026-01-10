#!/usr/bin/env python3
"""
Analyze a trading day to match Robinhood's Purchase and Sale Summary report.

This script analyzes futures orders from a specific date to generate a summary
that matches Robinhood's daily trading report format:
- Total Qty Long (total BUY orders)
- Total Qty Short (total SELL orders)
- Gross P&L (sum of realized P&L)

We ignore position_effect field and rely on Robinhood's calculated realized_pnl.
"""

import sqlite3
import argparse
from datetime import datetime
from typing import List, Dict
from collections import defaultdict

def fetch_orders_for_date(db_path: str, target_date: str) -> List[Dict]:
    """Fetch all filled futures orders for a specific date."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Date must be in YYYY-MM-DD format
    pattern = f'{target_date}%'

    query = '''
        SELECT order_id, contract_id, symbol, display_symbol,
               order_side, position_effect, filled_quantity,
               average_price, realized_pnl, realized_pnl_without_fees,
               total_fee, execution_time, trade_date
        FROM futures_orders
        WHERE (execution_time LIKE ? OR created_at LIKE ?)
        AND order_state = 'FILLED'
        ORDER BY execution_time
    '''

    cursor.execute(query, (pattern, pattern))
    orders = cursor.fetchall()

    columns = ['order_id', 'contract_id', 'symbol', 'display_symbol',
               'order_side', 'position_effect', 'filled_quantity',
               'average_price', 'realized_pnl', 'realized_pnl_without_fees',
               'total_fee', 'execution_time', 'trade_date']

    results = []
    for order in orders:
        results.append(dict(zip(columns, order)))

    conn.close()
    return results


def analyze_trading_day(orders: List[Dict], target_date: str):
    """Analyze orders to match Robinhood's Purchase and Sale Summary format."""

    # Group by contract
    by_contract = defaultdict(list)
    for order in orders:
        contract_id = order['contract_id']
        by_contract[contract_id].append(order)

    print(f"\n{'='*120}")
    print(f"PURCHASE AND SALE SUMMARY - {target_date}")
    print(f"{'='*120}")
    print(f"Total Orders: {len(orders)} across {len(by_contract)} unique contracts")
    print(f"{'='*120}\n")

    # Summary table header (matching Robinhood format)
    print(f"{'Symbol':<15} {'Contract ID':<40} {'Total Qty Long':<16} {'Total Qty Short':<17} {'Gross P&L':<15}")
    print(f"{'-'*120}")

    overall_summary = []
    grand_total_pnl = 0
    grand_total_long = 0
    grand_total_short = 0

    # Analyze each contract
    for contract_id, contract_orders in by_contract.items():
        symbol = contract_orders[0]['display_symbol'] or contract_orders[0]['symbol']

        # Calculate totals
        total_qty_long = sum(o['filled_quantity'] for o in contract_orders if o['order_side'] == 'BUY')
        total_qty_short = sum(o['filled_quantity'] for o in contract_orders if o['order_side'] == 'SELL')

        # Sum realized P&L (Robinhood calculates this for us)
        gross_pnl = sum(o['realized_pnl'] for o in contract_orders if o['realized_pnl'] is not None)

        print(f"{symbol:<15} {contract_id:<40} {total_qty_long:<16} {total_qty_short:<17} ${gross_pnl:<14,.2f}")

        overall_summary.append({
            'symbol': symbol,
            'contract_id': contract_id,
            'total_qty_long': total_qty_long,
            'total_qty_short': total_qty_short,
            'gross_pnl': gross_pnl,
            'orders': contract_orders
        })

        grand_total_pnl += gross_pnl
        grand_total_long += total_qty_long
        grand_total_short += total_qty_short

    # Grand totals
    print(f"{'-'*120}")
    print(f"{'TOTALS':<15} {'':<40} {grand_total_long:<16} {grand_total_short:<17} ${grand_total_pnl:<14,.2f}")
    print(f"{'='*120}\n")

    # Detailed breakdown for each contract
    for summary in overall_summary:
        print(f"\n{'='*120}")
        print(f"DETAILED BREAKDOWN - {summary['symbol']} ({summary['contract_id']})")
        print(f"{'='*120}\n")

        print(f"{'#':<4} {'Time':<25} {'Side':<6} {'Qty':<5} {'Price':<15} {'P&L':<12} {'P&L (no fees)':<15} {'Fees':<10}")
        print(f"{'-'*120}")

        running_pnl = 0
        for i, order in enumerate(summary['orders'], 1):
            side = order['order_side']
            qty = order['filled_quantity']
            price = order['average_price']
            pnl = order['realized_pnl'] if order['realized_pnl'] else 0
            pnl_no_fees = order['realized_pnl_without_fees'] if order['realized_pnl_without_fees'] else 0
            fees = order['total_fee'] if order['total_fee'] else 0
            exec_time = order['execution_time']

            running_pnl += pnl

            print(f"{i:<4} {exec_time:<25} {side:<6} {qty:<5} ${price:<14,.2f} ${pnl:<11,.2f} ${pnl_no_fees:<14,.2f} ${fees:<9,.2f}")

        print(f"{'-'*120}")
        print(f"Total for {summary['symbol']}: {summary['total_qty_long']} Long, {summary['total_qty_short']} Short, P&L: ${summary['gross_pnl']:.2f}")


def main():
    parser = argparse.ArgumentParser(description='Analyze trading day patterns for futures')
    parser.add_argument('--date', '-d', required=True,
                        help='Date to analyze (YYYY-MM-DD format required)')
    parser.add_argument('--db', default='futures.db',
                        help='Path to futures database file. Default: futures.db')

    args = parser.parse_args()

    # Validate date format
    if len(args.date.split('-')) != 3:
        print("ERROR: Date must be in YYYY-MM-DD format (e.g., 2025-04-09)")
        return

    # Fetch orders
    orders = fetch_orders_for_date(args.db, args.date)

    if not orders:
        print(f"No orders found for {args.date}")
        return

    # Analyze
    analyze_trading_day(orders, args.date)


if __name__ == '__main__':
    main()
