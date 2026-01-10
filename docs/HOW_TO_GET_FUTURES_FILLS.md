OK go back to our project folder# How to Get Futures Fills from Robinhood

**Date:** 2026-01-10

---

## The Correct Way to Fetch Filled Orders

### Python Code
```python
import robin_stocks.robinhood as rh

# Login
rh.login()

# Get ALL filled orders (includes partial fills)
filled_orders = rh.futures.get_filled_futures_orders()

# This returns ALL actual executions:
# - Orders with state='FILLED' (fully filled)
# - Orders with state='PARTIALLY_FILLED_REST_CANCELLED' (partially filled)
```

---

## Why Include Partial Fills?

### What is a Partial Fill?

When you place an order for 5 contracts but only 4 fill before you cancel:
- **4 contracts were ACTUALLY bought/sold** (real executions)
- Order state becomes `PARTIALLY_FILLED_REST_CANCELLED`
- `filledQuantity = 4` (the part that executed)
- `quantity = 5` (what you originally ordered)

### Why It Matters

**If you only fetch `FILLED` orders, you MISS these real executions.**

Example we found:
- 1 order: BUY 5 contracts, only 4 filled, then cancelled
- State: `PARTIALLY_FILLED_REST_CANCELLED`
- Result: We were missing 4 BUY contracts from our data
- This caused a -4 position imbalance (should have been flat)

---

## Order States Explained

### Include These (Actual Executions)
```
FILLED
  - Order fully executed
  - filledQuantity == quantity
  - Example: Ordered 5, filled 5

PARTIALLY_FILLED_REST_CANCELLED
  - Order partially executed, then cancelled
  - filledQuantity < quantity
  - Example: Ordered 5, filled 4, cancelled
  - The 4 filled contracts are REAL
```

### Exclude These (No Executions)
```
CANCELLED
  - Cancelled before ANY fills
  - filledQuantity = 0
  - No actual executions

REJECTED
  - Order rejected by broker
  - filledQuantity = 0
  - No actual executions
```

---

## Important Fields in Each Order

### Order Structure
```python
order = {
    'orderId': 'abc123...',
    'orderState': 'FILLED' or 'PARTIALLY_FILLED_REST_CANCELLED',

    # Quantities
    'quantity': 5,          # What you ORDERED
    'filledQuantity': 4,    # What ACTUALLY EXECUTED ← Use this!

    # Contract details
    'orderLegs': [{
        'orderSide': 'BUY' or 'SELL',
        'contractId': 'ccccaea2-f255-46b3-9729-2e01b82c0d39'
    }],

    # P&L
    'realizedPnl': {
        'realizedPnlWithoutFees': {
            'amount': '-8.75'  # P&L for this execution
        }
    },

    # Timing
    'createdAt': '2025-03-17T00:19:06.263704Z'
}
```

### Key Points
1. **Always use `filledQuantity`** (not `quantity`) for position tracking
2. **Check `orderState`** to include both FILLED and PARTIALLY_FILLED_REST_CANCELLED
3. **Verify `filledQuantity > 0`** to ensure actual executions occurred

---

## Calculating Position

### Simple Position Tracking
```python
def calculate_position(orders):
    position = 0

    for order in orders:
        # Use filledQuantity (what actually executed)
        filled_qty = int(order.get('filledQuantity', 0))
        side = order['orderLegs'][0]['orderSide']

        if side == 'BUY':
            position += filled_qty
        else:  # SELL
            position -= filled_qty

    return position

# position == 0 means FLAT (all closed)
# position > 0 means LONG
# position < 0 means SHORT
```

### Position by Contract
```python
from collections import defaultdict

def calculate_positions_by_contract(orders):
    positions = defaultdict(int)

    for order in orders:
        contract_id = order['orderLegs'][0]['contractId']
        filled_qty = int(order.get('filledQuantity', 0))
        side = order['orderLegs'][0]['orderSide']

        if side == 'BUY':
            positions[contract_id] += filled_qty
        else:
            positions[contract_id] -= filled_qty

    return dict(positions)

# Example output:
# {
#   'ccccaea2-...': 0,   # FLAT
#   'abc123-...': 2,     # LONG 2
#   'xyz789-...': -1     # SHORT 1
# }
```

---

## Our Discovery Process

### What We Did
1. **Found a problem:** Contract showing -4 position when it should be flat
2. **Checked the data:** BUY=662, SELL=666 (imbalance of -4)
3. **Fetched fresh data:** Same result from Robinhood API
4. **Checked ALL orders:** Found 1 PARTIALLY_FILLED_REST_CANCELLED order
5. **Analyzed the partial fill:** BUY 5 ordered, 4 filled
6. **Updated the code:** Include partial fills in `get_filled_futures_orders()`
7. **Validated:** BUY now=666, SELL=666, position=0 (FLAT ✓)

### The Numbers
```
Before fix:
  Total orders fetched: 1,210
  Order states: Only 'FILLED'
  Contract ccccaea2: BUY=662, SELL=666, Balance=-4

After fix:
  Total orders fetched: 1,211
  Order states: 'FILLED' + 'PARTIALLY_FILLED_REST_CANCELLED'
  Contract ccccaea2: BUY=666, SELL=666, Balance=0 ✓

Missing order:
  1 partial fill: BUY 5 ordered, 4 filled
  Those 4 contracts closed the gap!
```

---

## Validation

### Check Your Data
```python
import robin_stocks.robinhood as rh

rh.login()

# Get filled orders
orders = rh.futures.get_filled_futures_orders()

# Check for partial fills
partial_fills = [
    o for o in orders
    if o.get('orderState') == 'PARTIALLY_FILLED_REST_CANCELLED'
]

print(f"Total orders: {len(orders)}")
print(f"Partial fills: {len(partial_fills)}")

# Show partial fills
for pf in partial_fills:
    print(f"\nPartial fill:")
    print(f"  Contract: {pf['orderLegs'][0]['contractId']}")
    print(f"  Side: {pf['orderLegs'][0]['orderSide']}")
    print(f"  Ordered: {pf['quantity']}")
    print(f"  Filled: {pf['filledQuantity']}")
```

### Verify All Positions Are Flat
```python
from collections import defaultdict

# Calculate position by contract
positions = defaultdict(int)

for order in orders:
    contract_id = order['orderLegs'][0]['contractId']
    filled_qty = int(order.get('filledQuantity', 0))
    side = order['orderLegs'][0]['orderSide']

    if side == 'BUY':
        positions[contract_id] += filled_qty
    else:
        positions[contract_id] -= filled_qty

# Check for imbalances
imbalanced = {k: v for k, v in positions.items() if v != 0}

if not imbalanced:
    print("✓ All positions FLAT")
else:
    print(f"⚠ {len(imbalanced)} imbalanced contracts:")
    for contract_id, position in imbalanced.items():
        print(f"  {contract_id}: {position}")
```

---

## Summary

### The Rule
**To get accurate futures position and P&L data, you MUST include partially filled orders.**

### The Code
```python
import robin_stocks.robinhood as rh

rh.login()
filled_orders = rh.futures.get_filled_futures_orders()

# This now correctly includes:
# - All FILLED orders
# - All PARTIALLY_FILLED_REST_CANCELLED orders
```

### The Fields
```python
# For each order, use:
filled_qty = int(order['filledQuantity'])  # Not 'quantity'
side = order['orderLegs'][0]['orderSide']  # 'BUY' or 'SELL'
contract_id = order['orderLegs'][0]['contractId']
```

### The Math
```python
position = sum(BUY filledQuantity) - sum(SELL filledQuantity)

# position == 0  →  FLAT (all closed)
# position > 0   →  LONG
# position < 0   →  SHORT
```

---

## Files

**Updated code:**
- `/Users/clutchcoder/working/robin_stocks/robin_stocks/robinhood/futures.py`
  - Function: `get_filled_futures_orders()`

**Validation test:**
- `/Users/clutchcoder/working/rh_web/temp/validate_partial_fills_fix.py`

Run validation:
```bash
python temp/validate_partial_fills_fix.py
```
