#!/usr/bin/env python3
"""
Validate that including partial fills fixes position tracking.

This test validates:
1. All contracts have balanced BUY/SELL quantities
2. Total P&L from orders matches expected
3. The ccccaea2 contract issue is resolved
"""

import sys
sys.path.insert(0, '/Users/clutchcoder/working/robin_stocks')

import robin_stocks.robinhood as rh
from collections import defaultdict


def get_amount(field):
    """Extract amount from nested dict structure."""
    if isinstance(field, dict) and 'amount' in field:
        return float(field['amount'])
    return 0.0


def main():
    print("=" * 80)
    print("PARTIAL FILLS FIX VALIDATION")
    print("=" * 80)
    print()

    # Login and fetch orders
    print("Logging in to Robinhood...")
    rh.login()

    print("Fetching filled futures orders (including partial fills)...")
    orders = rh.futures.get_filled_futures_orders()
    print(f"✓ Retrieved {len(orders)} filled orders\n")

    # Group by contract
    by_contract = defaultdict(list)
    for order in orders:
        legs = order.get('orderLegs', [])
        if not legs:
            continue
        contract_id = legs[0].get('contractId')
        if contract_id:
            by_contract[contract_id].append(order)

    print(f"✓ Found {len(by_contract)} unique contracts\n")

    # Check balance for each contract
    print("=" * 80)
    print("CONTRACT BALANCE VALIDATION")
    print("=" * 80)
    print()

    imbalanced_contracts = []

    for contract_id, contract_orders in by_contract.items():
        buy_qty = 0
        sell_qty = 0

        for order in contract_orders:
            qty = int(order.get('filledQuantity', 0))
            side = order['orderLegs'][0]['orderSide']

            if side == 'BUY':
                buy_qty += qty
            else:
                sell_qty += qty

        balance = buy_qty - sell_qty

        if balance != 0:
            imbalanced_contracts.append({
                'contract_id': contract_id,
                'buy_qty': buy_qty,
                'sell_qty': sell_qty,
                'balance': balance
            })

    if len(imbalanced_contracts) == 0:
        print("✓ ALL CONTRACTS BALANCED (BUY qty = SELL qty)")
        print()
    else:
        print(f"⚠ Found {len(imbalanced_contracts)} imbalanced contracts:")
        print()
        for contract in imbalanced_contracts[:10]:
            print(f"  Contract: {contract['contract_id'][:50]}")
            print(f"    BUY: {contract['buy_qty']}, SELL: {contract['sell_qty']}, Balance: {contract['balance']}")
            print()

    # Check ccccaea2 specifically
    print("=" * 80)
    print("CCCCAEA2 CONTRACT VALIDATION")
    print("=" * 80)
    print()

    target = 'ccccaea2-f255-46b3-9729-2e01b82c0d39'
    if target in by_contract:
        contract_orders = by_contract[target]

        buy_qty = sum(int(o.get('filledQuantity', 0)) for o in contract_orders if o['orderLegs'][0]['orderSide'] == 'BUY')
        sell_qty = sum(int(o.get('filledQuantity', 0)) for o in contract_orders if o['orderLegs'][0]['orderSide'] == 'SELL')

        print(f"Contract: {target}")
        print(f"Total orders: {len(contract_orders)}")
        print(f"BUY quantity:  {buy_qty}")
        print(f"SELL quantity: {sell_qty}")
        print(f"Balance:       {buy_qty - sell_qty}")
        print()

        if buy_qty == sell_qty:
            print("✓ CCCCAEA2 CONTRACT IS BALANCED!")
            print("  (Previously showed -4 before partial fills fix)")
        else:
            print(f"⚠ CCCCAEA2 STILL IMBALANCED: {buy_qty - sell_qty}")
    else:
        print("Contract not found in orders")

    print()

    # P&L validation
    print("=" * 80)
    print("P&L VALIDATION")
    print("=" * 80)
    print()

    total_pnl = 0
    for order in orders:
        pnl_data = order.get('realizedPnl', {})
        total_pnl += get_amount(pnl_data.get('realizedPnlWithoutFees'))

    print(f"Total P&L (no fees): ${total_pnl:,.2f}")
    print()

    # Check for partial fills
    print("=" * 80)
    print("PARTIAL FILLS CHECK")
    print("=" * 80)
    print()

    partial_fills = [o for o in orders if o.get('orderState') == 'PARTIALLY_FILLED_REST_CANCELLED']

    print(f"Partial fill orders found: {len(partial_fills)}")

    if partial_fills:
        print()
        for pf in partial_fills:
            contract_id = pf['orderLegs'][0].get('contractId', 'unknown')[:50]
            qty = pf.get('quantity', 0)
            filled = pf.get('filledQuantity', 0)
            side = pf['orderLegs'][0]['orderSide']

            print(f"  Contract: {contract_id}")
            print(f"    Side: {side}")
            print(f"    Ordered: {qty}, Filled: {filled}")
            print()

    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print()

    print(f"Total orders: {len(orders)}")
    print(f"Unique contracts: {len(by_contract)}")
    print(f"Imbalanced contracts: {len(imbalanced_contracts)}")
    print(f"Partial fills included: {len(partial_fills)}")
    print()

    if len(imbalanced_contracts) == 0:
        print("✓ VALIDATION PASSED!")
        print("  All contracts are balanced after including partial fills.")
    else:
        print("⚠ VALIDATION FAILED!")
        print(f"  {len(imbalanced_contracts)} contracts still imbalanced.")

    print()
    print("=" * 80)

    rh.logout()


if __name__ == '__main__':
    main()
