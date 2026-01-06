#!/usr/bin/env python3
"""
Test script for Robinhood Futures API using pickle file authentication.

This demonstrates that the existing robin_stocks authentication (pickle file)
works perfectly for futures endpoints when the proper headers are included.
"""

import sys
sys.path.insert(0, '/Users/clutchcoder/working/robin_stocks')

import pickle
import requests
import json
from robin_stocks.robinhood import helper


def load_auth():
    """Load authentication from pickle file."""
    with open('/Users/clutchcoder/.tokens/robinhood.pickle', 'rb') as f:
        pickle_data = pickle.load(f)
    return pickle_data


def get_futures_contract(symbol, auth):
    """
    Get futures contract details by symbol.

    Args:
        symbol (str): Futures symbol (e.g., 'ESH26', 'NQM26')
        auth (dict): Authentication data from pickle file

    Returns:
        dict: Contract details including id, description, expiration, etc.
    """
    url = f'https://api.robinhood.com/arsenal/v1/futures/contracts/symbol/{symbol}'

    headers = {
        'Authorization': f"{auth['token_type']} {auth['access_token']}",
        'Accept': '*/*',
        'Rh-Contract-Protected': 'true',  # REQUIRED for futures!
        'X-Robinhood-API-Version': '1.431.4',
    }

    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()

    return response.json()['result']


def get_futures_quote(contract_id, auth):
    """
    Get real-time quote for a futures contract.

    Args:
        contract_id (str): Contract instrument ID
        auth (dict): Authentication data from pickle file

    Returns:
        dict: Quote data including bid, ask, last trade, etc.
    """
    url = f'https://api.robinhood.com/marketdata/futures/quotes/v1/?ids={contract_id}'

    headers = {
        'Authorization': f"{auth['token_type']} {auth['access_token']}",
        'Accept': '*/*',
        'Rh-Contract-Protected': 'true',  # REQUIRED for futures!
        'X-Robinhood-API-Version': '1.431.4',
    }

    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()

    return response.json()['data'][0]['data']


def get_futures_quote_by_symbol(symbol, auth):
    """
    Convenience function to get quote by symbol (combines contract lookup + quote).

    Args:
        symbol (str): Futures symbol (e.g., 'ESH26')
        auth (dict): Authentication data from pickle file

    Returns:
        tuple: (contract_data, quote_data)
    """
    contract = get_futures_contract(symbol, auth)
    quote = get_futures_quote(contract['id'], auth)
    return contract, quote


def get_futures_orders(account_id, auth):
    """
    Get historical futures orders from Robinhood Ceres API.

    Note: This retrieves the first 100 orders by default. Pagination is available
    but the correct parameter name for subsequent pages is currently unknown.
    The API returns a 'next' field but pageToken/pageStart parameters don't work.

    Args:
        account_id (str): Futures account ID (different from stock account ID)
        auth (dict): Authentication data from pickle file

    Returns:
        list: List of order dictionaries containing:
            - orderId: Unique order identifier
            - orderState: FILLED, CANCELLED, REJECTED, etc.
            - orderLegs: Array with contract details (contractId, orderSide, etc.)
            - quantity: Number of contracts
            - averagePrice: Execution price
            - realizedPnl: Nested object with P&L data
            - totalFee, totalCommission, totalGoldSavings: Fee breakdown
            - orderExecutions: Array of execution details
            - createdAt, updatedAt: Timestamps
    """
    headers = {
        'Authorization': f"{auth['token_type']} {auth['access_token']}",
        'Accept': '*/*',
        'Rh-Contract-Protected': 'true',  # REQUIRED for futures endpoints
    }

    # Get all order states for complete historical data
    order_states = ['FILLED', 'CANCELLED', 'REJECTED', 'VOIDED',
                   'PARTIALLY_FILLED_REST_CANCELLED', 'INACTIVE', 'FAILED']
    state_params = '&'.join([f'orderState={state}' for state in order_states])

    # contractType=OUTRIGHT specifies futures (vs EVENT_CONTRACT for prediction markets)
    url = f'https://api.robinhood.com/ceres/v1/accounts/{account_id}/orders?contractType=OUTRIGHT&{state_params}'

    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    data = response.json()

    return data.get('results', [])


def main():
    """Test futures API with various symbols and orders."""
    print("=" * 80)
    print("ROBINHOOD FUTURES API TEST")
    print("Using pickle file authentication")
    print("=" * 80)

    # Load authentication
    try:
        auth = load_auth()
        print("\n✓ Authentication loaded from pickle file")
    except Exception as e:
        print(f"\n✗ Failed to load authentication: {e}")
        return

    # Test symbols for quotes
    symbols = ['ESH26', 'NQH26', 'GCG26']

    for symbol in symbols:
        print(f"\n{'-' * 80}")
        print(f"Testing Quote: {symbol}")
        print('-' * 80)

        try:
            # Get contract and quote
            contract, quote = get_futures_quote_by_symbol(symbol, auth)

            # Display contract info
            print(f"\nContract Details:")
            print(f"  Symbol: {contract['displaySymbol']}")
            print(f"  Description: {contract['description']}")
            print(f"  Expiration: {contract['expiration']}")
            print(f"  Multiplier: {contract['multiplier']}")
            print(f"  Exchange: {contract['symbol'].split(':')[1]}")

            # Display quote
            print(f"\nCurrent Quote:")
            print(f"  Last Trade: ${quote['last_trade_price']}")
            print(f"  Bid: ${quote['bid_price']} x {quote['bid_size']}")
            print(f"  Ask: ${quote['ask_price']} x {quote['ask_size']}")
            print(f"  Status: {quote['state']}")
            print(f"  Updated: {quote['updated_at']}")

            print(f"\n✓ SUCCESS")

        except requests.HTTPError as e:
            print(f"\n✗ HTTP Error: {e}")
            print(f"  Status: {e.response.status_code}")
            print(f"  Response: {e.response.text[:200]}")
        except Exception as e:
            print(f"\n✗ Error: {e}")

    # Test futures orders
    print(f"\n{'=' * 80}")
    print("TESTING FUTURES ORDERS")
    print("=" * 80)

    futures_account_id = '67648f71-bfff-4ca8-8189-d6f4aa95bcfa'

    try:
        print(f"\nFetching orders for account: {futures_account_id}")
        orders = get_futures_orders(futures_account_id, auth)

        print(f"\n✓ Retrieved {len(orders)} total orders")

        # Helper function to safely extract numeric value from nested amount field
        def get_amount_value(field):
            if field is None:
                return 0.0
            if isinstance(field, (int, float)):
                return float(field)
            if isinstance(field, str):
                return float(field) if field else 0.0
            if isinstance(field, dict):
                # Nested structure like {'amount': '123.45', 'currency': 'USD'}
                amount = field.get('amount', 0)
                if isinstance(amount, str):
                    return float(amount) if amount else 0.0
                return float(amount) if amount else 0.0
            return 0.0

        # Calculate P&L - realizedPnl is nested: {realizedPnl: {amount: '...'}, realizedPnlWithoutFees: {amount: '...'}}
        total_pnl = sum(
            get_amount_value(order.get('realizedPnl', {}).get('realizedPnl'))
            for order in orders
        )
        total_pnl_no_fees = sum(
            get_amount_value(order.get('realizedPnl', {}).get('realizedPnlWithoutFees'))
            for order in orders
        )
        total_fees = sum(get_amount_value(order.get('totalFee')) for order in orders)
        total_commissions = sum(get_amount_value(order.get('totalCommission')) for order in orders)
        total_gold_savings = sum(get_amount_value(order.get('totalGoldSavings')) for order in orders)

        print(f"\nP&L Summary:")
        print(f"  Total Realized P&L: ${total_pnl:,.2f}")
        print(f"  P&L Without Fees: ${total_pnl_no_fees:,.2f}")
        print(f"  Total Fees: ${total_fees:,.2f}")
        print(f"  Total Commissions: ${total_commissions:,.2f}")
        print(f"  Total Gold Savings: ${total_gold_savings:,.2f}")

        # Count orders by state
        from collections import Counter
        state_counts = Counter(order.get('orderState') for order in orders)

        print(f"\nOrders by State:")
        for state, count in sorted(state_counts.items()):
            print(f"  {state}: {count}")

        # Show first 5 orders with key details
        print(f"\nFirst 5 Orders (Summary):")
        for i, order in enumerate(orders[:5], 1):
            pnl = get_amount_value(order.get('realizedPnl', {}).get('realizedPnl'))
            contract_id = order.get('orderLegs', [{}])[0].get('contractId', 'N/A')
            side = order.get('orderLegs', [{}])[0].get('orderSide', 'N/A')
            avg_price = order.get('averagePrice', 'N/A')

            print(f"\n  Order #{i}:")
            print(f"    Order ID: {order.get('orderId')}")
            print(f"    State: {order.get('orderState')}")
            print(f"    Side: {side}")
            print(f"    Quantity: {order.get('quantity')}")
            print(f"    Avg Price: {avg_price}")
            print(f"    Realized P&L: ${pnl:,.2f}")
            print(f"    Fees: ${get_amount_value(order.get('totalFee')):,.2f}")
            print(f"    Commission: ${get_amount_value(order.get('totalCommission')):,.2f}")
            print(f"    Gold Savings: ${get_amount_value(order.get('totalGoldSavings')):,.2f}")
            print(f"    Created: {order.get('createdAt', 'N/A')}")
            print(f"    Contract ID: {contract_id}")

    except requests.HTTPError as e:
        print(f"\n✗ HTTP Error: {e}")
        print(f"  Status: {e.response.status_code}")
        print(f"  Response: {e.response.text[:200]}")
    except Exception as e:
        print(f"\n✗ Error: {e}")

    print(f"\n{'=' * 80}")
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == '__main__':
    main()
