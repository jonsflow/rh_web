#!/usr/bin/env python3
"""
Test script for Robinhood Futures API using robin_stocks library.

This demonstrates the new futures functionality added to robin_stocks,
testing contract lookup, quotes, and historical orders.
"""

import robin_stocks.robinhood as rh
from collections import Counter


def test_futures_contracts():
    """Test futures contract lookup."""
    print("=" * 80)
    print("TEST 1: FUTURES CONTRACT LOOKUP")
    print("=" * 80)

    symbols = ['ESH26', 'NQH26', 'GCG26']

    for symbol in symbols:
        print(f"\n{'-' * 80}")
        print(f"Testing Contract: {symbol}")
        print('-' * 80)

        try:
            contract = rh.get_futures_contract(symbol)

            if contract:
                print(f"\n✓ Contract Retrieved:")
                print(f"  Symbol: {contract.get('displaySymbol')}")
                print(f"  Description: {contract.get('description')}")
                print(f"  Expiration: {contract.get('expiration')}")
                print(f"  Multiplier: {contract.get('multiplier')}")
                print(f"  Exchange: {contract.get('symbol', ':').split(':')[1] if ':' in contract.get('symbol', '') else 'N/A'}")
                print(f"  Contract ID: {contract.get('id')}")
                print(f"  Tradability: {contract.get('tradability')}")
                print(f"  State: {contract.get('state')}")
            else:
                print(f"\n✗ Failed to retrieve contract")

        except Exception as e:
            print(f"\n✗ Error: {e}")

    print(f"\n{'=' * 80}\n")


def test_futures_quotes():
    """Test futures real-time quotes."""
    print("=" * 80)
    print("TEST 2: FUTURES REAL-TIME QUOTES")
    print("=" * 80)

    symbols = ['ESH26', 'NQH26', 'GCG26']

    for symbol in symbols:
        print(f"\n{'-' * 80}")
        print(f"Testing Quote: {symbol}")
        print('-' * 80)

        try:
            quote = rh.get_futures_quote(symbol)

            if quote:
                print(f"\n✓ Quote Retrieved:")
                print(f"  Symbol: {quote.get('symbol')}")
                print(f"  Last Trade: ${quote.get('last_trade_price')}")
                print(f"  Bid: ${quote.get('bid_price')} x {quote.get('bid_size')}")
                print(f"  Ask: ${quote.get('ask_price')} x {quote.get('ask_size')}")
                print(f"  State: {quote.get('state')}")
                print(f"  Updated: {quote.get('updated_at')}")
            else:
                print(f"\n✗ Failed to retrieve quote")

        except Exception as e:
            print(f"\n✗ Error: {e}")

    print(f"\n{'=' * 80}\n")


def test_multiple_quotes():
    """Test getting multiple quotes at once."""
    print("=" * 80)
    print("TEST 3: MULTIPLE FUTURES QUOTES")
    print("=" * 80)

    symbols = ['ESH26', 'NQH26', 'GCG26']

    try:
        quotes = rh.get_futures_quotes(symbols)

        if quotes:
            print(f"\n✓ Retrieved {len(quotes)} quotes:\n")
            for quote in quotes:
                symbol = quote.get('symbol', 'Unknown')
                last = quote.get('last_trade_price', 'N/A')
                bid = quote.get('bid_price', 'N/A')
                ask = quote.get('ask_price', 'N/A')
                print(f"  {symbol}: Last=${last}, Bid=${bid}, Ask=${ask}")
        else:
            print(f"\n✗ Failed to retrieve quotes")

    except Exception as e:
        print(f"\n✗ Error: {e}")

    print(f"\n{'=' * 80}\n")


def test_futures_orders():
    """Test futures historical orders."""
    print("=" * 80)
    print("TEST 4: FUTURES HISTORICAL ORDERS")
    print("=" * 80)

    # Futures account ID (different from stock account)
    futures_account_id = '67648f71-bfff-4ca8-8189-d6f4aa95bcfa'

    try:
        print(f"\nFetching orders for account: {futures_account_id}\n")
        orders = rh.get_all_futures_orders(account_id=futures_account_id)

        if orders:
            print(f"✓ Retrieved {len(orders)} total orders\n")

            # Calculate P&L using library helper
            pnl_summary = rh.calculate_total_futures_pnl(orders)

            print("P&L Summary:")
            print(f"  Total Realized P&L: ${pnl_summary['total_pnl']:,.2f}")
            print(f"  P&L Without Fees: ${pnl_summary['total_pnl_without_fees']:,.2f}")
            print(f"  Total Fees: ${pnl_summary['total_fees']:,.2f}")
            print(f"  Total Commissions: ${pnl_summary['total_commissions']:,.2f}")
            print(f"  Total Gold Savings: ${pnl_summary['total_gold_savings']:,.2f}")

            # Count orders by state
            state_counts = Counter(order.get('orderState') for order in orders)

            print(f"\nOrders by State:")
            for state, count in sorted(state_counts.items()):
                print(f"  {state}: {count}")

            # Show first 5 orders
            print(f"\nFirst 5 Orders (Summary):")
            for i, order in enumerate(orders[:5], 1):
                pnl_data = rh.extract_futures_pnl(order)
                side = order.get('orderLegs', [{}])[0].get('orderSide', 'N/A')
                avg_price = order.get('averagePrice', 'N/A')

                print(f"\n  Order #{i}:")
                print(f"    Order ID: {order.get('orderId')}")
                print(f"    State: {order.get('orderState')}")
                print(f"    Side: {side}")
                print(f"    Quantity: {order.get('quantity')}")
                print(f"    Avg Price: {avg_price}")
                print(f"    Realized P&L: ${pnl_data['realized_pnl']:,.2f}")
                print(f"    Fees: ${pnl_data['total_fee']:,.2f}")
                print(f"    Commission: ${pnl_data['total_commission']:,.2f}")
                print(f"    Gold Savings: ${pnl_data['total_gold_savings']:,.2f}")
                print(f"    Created: {order.get('createdAt', 'N/A')}")

        else:
            print(f"\n✗ No orders retrieved (empty list)")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

    print(f"\n{'=' * 80}\n")


def test_filled_orders_only():
    """Test getting only filled futures orders."""
    print("=" * 80)
    print("TEST 5: FILLED FUTURES ORDERS ONLY")
    print("=" * 80)

    futures_account_id = '67648f71-bfff-4ca8-8189-d6f4aa95bcfa'

    try:
        print(f"\nFetching filled orders for account: {futures_account_id}\n")
        orders = rh.get_filled_futures_orders(account_id=futures_account_id)

        if orders:
            print(f"✓ Retrieved {len(orders)} filled orders\n")

            # Calculate P&L
            pnl_summary = rh.calculate_total_futures_pnl(orders)
            print(f"Total Realized P&L (Filled Only): ${pnl_summary['total_pnl']:,.2f}")

        else:
            print(f"\n✗ No filled orders found")

    except Exception as e:
        print(f"\n✗ Error: {e}")

    print(f"\n{'=' * 80}\n")


def main():
    """Run all futures API tests."""
    print("\n" + "=" * 80)
    print("ROBINHOOD FUTURES API TEST - robin_stocks Library")
    print("=" * 80)

    # Login to Robinhood using pickle file
    print("\nAttempting login with stored credentials...")
    try:
        import pickle
        import os

        pickle_path = os.path.expanduser('~/.tokens/robinhood.pickle')
        with open(pickle_path, 'rb') as f:
            auth_data = pickle.load(f)

        # Set the session manually using the stored token
        from robin_stocks.robinhood.helper import set_login_state, update_session
        update_session('Authorization', f"{auth_data['token_type']} {auth_data['access_token']}")
        set_login_state(True)

        print("✓ Using existing authentication session\n")
    except FileNotFoundError:
        print(f"✗ Authentication file not found at {pickle_path}")
        print("Please login first using rh.login(username, password)")
        return
    except Exception as e:
        print(f"✗ Authentication failed: {e}")
        print("Please run rh.login(username, password) first")
        return

    # Run all tests
    try:
        test_futures_contracts()
        test_futures_quotes()
        test_multiple_quotes()
        test_futures_orders()
        test_filled_orders_only()
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
    except Exception as e:
        print(f"\n\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()

    print("=" * 80)
    print("ALL TESTS COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    main()
