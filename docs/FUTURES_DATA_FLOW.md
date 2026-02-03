# Futures Data Flow

This document explains how futures data flows through the Futures Dashboard, from fetching raw order data from Robinhood to displaying positions and P&L.

**This documentation is based on actual code review as of 2026-01-31.**

## Overview

The futures data pipeline is **simpler than options** - no service layer, direct database operations:

1. **Fetch** - Get futures orders from Robinhood API
2. **Store** - Save raw orders to database
3. **Enrich** - Fetch symbols for contract IDs via quotes API
4. **Rebuild** - Pair open/close orders into positions
5. **Calculate** - Sum P&L (already provided by Robinhood)
6. **Display** - Serve data to frontend via API

**Key Difference**: Robinhood provides **realized P&L directly in the API** - we don't calculate it ourselves like we do for options.

## 1. Data Fetching

**File**: `futures/data_fetcher.py` (FuturesDataFetcher class)

### Futures Account Discovery
```python
account_id = r.get_futures_account_id()
```

First, we discover the futures account ID. Futures trading requires a separate account approval.

### API Call
```python
all_orders = r.get_all_futures_orders(account_id=account_id)
```

This fetches **all futures orders** (no date filtering) from Robinhood with automatic pagination.

### What We Get
Each order from the API contains:
- **Order ID** (`orderId`) - Used for deduplication
- **Account ID** (`accountId`) - Futures account
- **Order Legs** (`orderLegs[]`) with:
  - Contract ID (`contractId`) - e.g., "de9cf980-f53a-4e00-8d23-..."
  - Order side (`orderSide`) - "BUY" or "SELL"
  - Average price (`averagePrice`) - Execution price
- **Order State** (`orderState`) - "FILLED", "PARTIALLY_FILLED_REST_CANCELLED", "CANCELED", etc.
- **Quantity** (`quantity` and `filledQuantity`)
- **Position Effect** (`positionEffectAtPlacementTime`) - "OPENING" or "CLOSING"
- **Realized P&L** (`realizedPnl`) - **Critical!** Contains:
  - `realizedPnl.realizedPnl.amount` - P&L including fees
  - `realizedPnl.realizedPnlWithoutFees.amount` - P&L before fees
- **Fees** (`totalFee`, `totalCommission`, `totalGoldSavings`)
- **Executions** (`orderExecutions[]`) with `eventTime` for trade date
- **Timestamps** (`createdAt`, `updatedAt`)
- **Symbol info** (`symbol`, `displaySymbol`) - Often empty, need enrichment

### Double-Nested P&L Structure
```python
# Robinhood's complex nested structure:
order['realizedPnl']['realizedPnl']['amount']  # P&L with fees
order['realizedPnl']['realizedPnlWithoutFees']['amount']  # P&L without fees

# We extract using helper:
def get_amount(field):
    if isinstance(field, dict) and 'amount' in field:
        return float(field['amount'])
    return 0.0
```

### Filtering
We store **filled and partially filled orders**:
```python
filled_orders = [
    order for order in all_orders
    if order.get('orderState') in ['FILLED', 'PARTIALLY_FILLED_REST_CANCELLED']
    and int(order.get('filledQuantity', 0)) > 0
]
```

Partial fills are real executions and have P&L, so we include them.

## 2. Database Storage

**File**: `futures/database.py` (FuturesDatabase class)

### Futures Orders Table
```sql
CREATE TABLE futures_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id TEXT UNIQUE,           -- Deduplication key
    account_id TEXT,                -- Futures account ID
    contract_id TEXT,               -- From orderLegs[0]
    symbol TEXT,                    -- e.g., "/ESH26:XCME" (needs enrichment)
    display_symbol TEXT,            -- e.g., "/ESH26" (needs enrichment)
    order_side TEXT,                -- "BUY" or "SELL"
    quantity INTEGER,               -- Total quantity
    filled_quantity INTEGER,        -- Actually filled
    order_type TEXT,                -- "MARKET", "LIMIT", etc.
    order_state TEXT,               -- "FILLED", "CANCELED", etc.
    average_price REAL,             -- Execution price
    position_effect TEXT,           -- "OPENING" or "CLOSING"
    realized_pnl REAL,              -- P&L with fees (from API)
    realized_pnl_without_fees REAL, -- P&L before fees (from API)
    total_fee REAL,                 -- Fees charged
    total_commission REAL,          -- Commission component
    total_gold_savings REAL,        -- Gold discount
    created_at TEXT,                -- Order creation timestamp
    updated_at TEXT,                -- Last update timestamp
    trade_date TEXT,                -- Execution date in ET (calculated)
    execution_time TEXT,            -- Execution timestamp
    raw_data TEXT,                  -- Full JSON for debugging
    fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### Trade Date Calculation
Convert UTC execution time to Eastern Time to get correct trade date:
```python
dt_utc = datetime.fromisoformat(execution_time.replace('Z', '+00:00'))
eastern = pytz.timezone('America/New_York')
dt_eastern = dt_utc.astimezone(eastern)
trade_date = dt_eastern.strftime('%Y-%m-%d')
```

This ensures overnight trades are assigned to the correct trading day.

### Deduplication
```python
INSERT OR IGNORE INTO futures_orders (order_id, ...)
```

The `order_id` from Robinhood is unique - refetching all data won't create duplicates.

## 3. Symbol Enrichment

**File**: `futures/data_fetcher.py` → `enrich_contract_symbols()`

### The Problem
Robinhood futures orders often don't include `symbol` or `displaySymbol` fields. We only get `contract_id`.

### The Solution
Query the quotes API to map contract IDs to symbols:

```python
# Find contracts missing symbols
contracts_to_enrich = db.query('''
    SELECT DISTINCT contract_id FROM futures_orders
    WHERE (symbol IS NULL OR symbol = '')
''')

# For each contract, fetch symbol from quotes API
for contract_id in contracts_to_enrich:
    url = f"https://api.robinhood.com/marketdata/futures/quotes/v1/?ids={contract_id}"
    response = r.helper.request_get(url)

    quote_data = response['data'][0]['data']
    symbol = quote_data['symbol']  # e.g., "/ESH26:XCME"
    display_symbol = symbol.split(':')[0]  # e.g., "/ESH26"

    # Update database
    UPDATE futures_orders
    SET symbol = ?, display_symbol = ?
    WHERE contract_id = ?
```

### Symbol Format Examples
- **symbol**: `/ESH26:XCME` (full symbol with exchange)
- **display_symbol**: `/ESH26` (friendly name)
- `/ES` = E-mini S&P 500 futures
- `H26` = March 2026 expiration (H=March, 26=2026)
- `XCME` = Chicago Mercantile Exchange

## 4. Position Rebuilding

**File**: `futures/database.py` → `rebuild_positions()`

Positions are paired opening and closing orders for the same contract.

### Pairing Logic

**Position Key**: Simply `contract_id` (each contract is unique)

```python
# Group all orders by contract_id
positions = {}
for order in orders:
    contract_id = order['contract_id']

    if contract_id not in positions:
        positions[contract_id] = {
            'contract_id': contract_id,
            'symbol': order['symbol'],
            'display_symbol': order['display_symbol'],
            'open_orders': [],
            'close_orders': []
        }

    if order['position_effect'] == 'OPENING':
        positions[contract_id]['open_orders'].append(order)
    elif order['position_effect'] == 'CLOSING':
        positions[contract_id]['close_orders'].append(order)
```

### Open Orders Aggregation
```python
total_qty = sum(o['quantity'] for o in open_orders)
avg_open_price = sum(o['price'] * o['quantity'] for o in open_orders) / total_qty
open_date = min(o['date'] for o in open_orders)  # Earliest open
```

### Close Orders Aggregation
```python
if close_orders:
    avg_close_price = sum(o['price'] * o['quantity'] for o in close_orders) / total_qty
    close_date = max(o['date'] for o in close_orders)  # Latest close

    # Sum P&L from all closing orders
    realized_pnl = sum(o['pnl'] for o in close_orders)
    realized_pnl_no_fees = sum(o['pnl_no_fees'] for o in close_orders)
    total_fees = sum(o['fees'] for o in close_orders)

    status = 'closed'
else:
    status = 'open'
```

### Positions Table
```sql
CREATE TABLE futures_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_key TEXT UNIQUE,       -- "{contract_id}_{open_date}"
    contract_id TEXT,
    symbol TEXT,                    -- "/ESH26:XCME"
    display_symbol TEXT,            -- "/ESH26"
    open_date TEXT,
    close_date TEXT,
    quantity INTEGER,
    open_price REAL,                -- Weighted average
    close_price REAL,               -- Weighted average
    open_value REAL,                -- Not currently used
    close_value REAL,               -- Not currently used
    realized_pnl REAL,              -- Sum from API
    realized_pnl_without_fees REAL, -- Sum from API
    total_fees REAL,                -- Sum of fees
    status TEXT,                    -- 'open' or 'closed'
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**Full Rebuild**: Like options, positions table is completely wiped and rebuilt:
```python
cursor.execute('DELETE FROM futures_positions')
# Then INSERT all new positions
```

## 5. P&L Calculation

**Key Difference**: We **don't calculate P&L** - Robinhood provides it!

### Realized P&L (Direct from API)
```python
# For each closing order, Robinhood provides:
realized_pnl = order['realizedPnl']['realizedPnl']['amount']
realized_pnl_without_fees = order['realizedPnl']['realizedPnlWithoutFees']['amount']
total_fee = order['totalFee']['amount']
```

### Position P&L (Sum of Closing Orders)
```python
# Sum all closing orders for the position
realized_pnl = sum(order['realized_pnl'] for order in close_orders)
realized_pnl_no_fees = sum(order['realized_pnl_without_fees'] for order in close_orders)
total_fees = sum(order['total_fee'] for order in close_orders)
```

### Daily P&L (Direct Sum)
```sql
SELECT
    trade_date,
    SUM(realized_pnl) as total_pnl,
    SUM(realized_pnl_without_fees) as total_pnl_no_fees,
    SUM(total_fee) as total_fees,
    COUNT(*) as order_count
FROM futures_orders
WHERE order_state IN ('FILLED', 'PARTIALLY_FILLED_REST_CANCELLED')
  AND trade_date IS NOT NULL
GROUP BY trade_date
```

**This matches Robinhood's Purchase and Sale Summary exactly.**

### Why This Is Simpler Than Options

**Options**: We calculate P&L from price differences:
```python
pnl = (close_price - open_price) * quantity * 100
```

**Futures**: Robinhood calculates and provides P&L:
```python
pnl = order['realizedPnl']['realizedPnl']['amount']  # Done!
```

Robinhood handles:
- Contract multipliers (varies by contract)
- Tick sizes
- Mark-to-market settlement
- Overnight funding
- All fees and commissions

## 6. Data Display

**File**: `futures/data_fetcher.py` → `get_processed_data()`

### Closed Positions Query

**Special handling**: Instead of using `futures_positions` table, we query orders directly:

```sql
SELECT *
FROM futures_orders
WHERE order_state IN ('FILLED', 'PARTIALLY_FILLED_REST_CANCELLED')
  AND realized_pnl_without_fees != 0
ORDER BY execution_time DESC
```

**Why?**
- Closing orders have the actual P&L
- We want one row per closing execution (not paired positions)
- Matches how Robinhood displays it

### Open Positions Query
```sql
SELECT * FROM futures_positions WHERE status = 'open'
```

### Summary Statistics
```python
daily_pnl = db.get_daily_pnl()

total_pnl = sum(day['pnl'] for day in daily_pnl.values())
total_fees = sum(day['fees'] for day in daily_pnl.values())
total_pnl_no_fees = sum(day['pnl_no_fees'] for day in daily_pnl.values())
num_trading_days = len(daily_pnl)
```

## Complete Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                  Robinhood Futures API                          │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               │ r.get_futures_account_id()
                               │ r.get_all_futures_orders(account_id)
                               v
                        [All Futures Orders]
                     (includes P&L from Robinhood!)
                               │
                               │ Filter: FILLED or PARTIALLY_FILLED
                               │ (FuturesDataFetcher)
                               v
                        [Filled Orders Only]
                               │
                               │ database.insert_orders()
                               │ INSERT OR IGNORE (dedup by order_id)
                               │ Extract trade_date from execution_time (ET)
                               v
┌──────────────────────────────────────────────────────────────────┐
│                   futures_orders table                           │
│  (Raw orders with P&L, fees, contract_id, timestamps)           │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               │ Check: symbol IS NULL?
                               v
                        ┌──────────────┐
                        │ Need symbols?│
                        └──────┬───────┘
                               │ YES
                               v
                    enrich_contract_symbols()
                               │
                               │ For each contract_id:
                               │ GET quotes API
                               │ Extract symbol and display_symbol
                               │ UPDATE futures_orders
                               v
┌──────────────────────────────────────────────────────────────────┐
│              futures_orders (enriched with symbols)              │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               │ database.rebuild_positions()
                               │
                               v
                    Group by contract_id
                               │
                               ├─> OPENING orders → open_orders[]
                               └─> CLOSING orders → close_orders[]
                               │
                               v
                    For each contract:
                               │
                               ├─> Calculate weighted avg prices
                               ├─> Sum quantities
                               ├─> Sum realized_pnl from closes
                               ├─> Sum fees from closes
                               └─> Determine status (open/closed)
                               │
                               v
                    DELETE FROM futures_positions
                    INSERT new positions
                               │
                               v
┌──────────────────────────────────────────────────────────────────┐
│                  futures_positions table                         │
│  (Paired positions with aggregated P&L from API)                │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               │ API Requests
                               v
┌──────────────────────────────────────────────────────────────────┐
│           FuturesDataFetcher.get_processed_data()                │
│                                                                  │
│  Closed Positions:                                              │
│  └─> Query futures_orders WHERE realized_pnl_without_fees != 0 │
│                                                                  │
│  Open Positions:                                                │
│  └─> Query futures_positions WHERE status='open'               │
│                                                                  │
│  Daily P&L:                                                     │
│  └─> SUM(realized_pnl) GROUP BY trade_date                     │
│                                                                  │
│  Summary:                                                       │
│  └─> Sum all daily P&L, fees, count days                       │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               v
                        [JSON API Response]
                               │
                               v
                        [Frontend Display]
```

## Key Implementation Details

### 1. No Service Layer

Unlike options, futures uses direct database operations:
- **FuturesDatabase** - Handles storage AND business logic
- **FuturesDataFetcher** - Only orchestrates fetching and enrichment
- No separate services for classification or calculation

**Benefit**: Simpler codebase, P&L comes from API anyway
**Trade-off**: Less separation of concerns

### 2. P&L Source of Truth

**Robinhood calculates everything**:
- Contract multipliers
- Tick values
- Settlement prices
- Mark-to-market adjustments
- All fees (commission, exchange, regulatory)

We just **sum and display** their numbers.

### 3. Symbol Enrichment is Critical

Contract IDs like `"de9cf980-f53a-4e00-8d23-..."` are not user-friendly.

We **must** enrich with symbols (`/ESH26`) for display.

**Enrichment process**:
1. Find contracts missing symbols
2. Query quotes API for each contract_id
3. Extract `symbol` and `display_symbol`
4. Update database
5. Rate limit (0.3s between requests)

### 4. Trade Date vs Timestamps

**created_at**: When order was placed (could be after hours)
**execution_time**: When order actually filled
**trade_date**: Execution time converted to Eastern Time date

```python
# Why Eastern Time?
# Futures market operates on ET
# Overnight trades need correct trading day assignment
# Example: Fill at 2:00 AM UTC → 9:00 PM ET previous day
```

### 5. Closed Positions Query Strategy

We query **orders directly**, not positions table:

```sql
WHERE realized_pnl_without_fees != 0
```

**Why?**
- Only closing orders have non-zero P&L
- Shows each execution separately (not aggregated)
- Matches Robinhood's display
- Simpler than pairing opens/closes for display

### 6. Partial Fills

```python
if order_state in ['FILLED', 'PARTIALLY_FILLED_REST_CANCELLED']:
    # Include both!
```

Partial fills are real trades with real P&L - we must include them.

### 7. Full Data Fetch Strategy

Like options, we fetch **all orders every time**:
```python
all_orders = r.get_all_futures_orders(account_id=account_id)
```

No date filtering, no incremental updates.

**Deduplication** at insert handles duplicates:
```sql
INSERT OR IGNORE INTO futures_orders (order_id, ...)
```

## Files Involved

| File | Purpose | Key Functions |
|------|---------|---------------|
| `futures/data_fetcher.py` | Fetch and orchestrate | FuturesDataFetcher, enrich_contract_symbols() |
| `futures/database.py` | Database operations | FuturesDatabase, rebuild_positions() |
| `futures/futures_web.py` | Flask API endpoints | /api/futures, /api/update, /api/daily-summary |

**Note**: No models, no services - simpler architecture than options.

## Example Flow

Let's trace a single futures trade:

### 1. Execute Trade on Robinhood
```
Buy 1 /ESH26 (E-mini S&P 500 March 2026)
Execution: $5,875.25
Timestamp: 2026-01-15 14:30:00 UTC (9:30 AM ET)
```

### 2. API Returns Order (filled)
```json
{
  "orderId": "abc123-def456-ghi789",
  "accountId": "futures-account-123",
  "orderState": "FILLED",
  "quantity": "1",
  "filledQuantity": "1",
  "positionEffectAtPlacementTime": "OPENING",
  "orderLegs": [{
    "contractId": "de9cf980-f53a-4e00-8d23-abc123",
    "orderSide": "BUY",
    "averagePrice": "5875.25"
  }],
  "orderExecutions": [{
    "eventTime": "2026-01-15T14:30:00.000Z"
  }],
  "realizedPnl": {
    "realizedPnl": { "amount": "0.00" },
    "realizedPnlWithoutFees": { "amount": "0.00" }
  },
  "totalFee": { "amount": "2.12" },
  "symbol": "",
  "displaySymbol": "",
  "createdAt": "2026-01-15T14:29:55.123Z",
  "updatedAt": "2026-01-15T14:30:00.456Z"
}
```

### 3. Stored in futures_orders Table
```python
# Calculate trade_date from execution_time
dt_utc = datetime.fromisoformat('2026-01-15T14:30:00.000Z')
dt_eastern = dt_utc.astimezone(pytz.timezone('America/New_York'))
trade_date = '2026-01-15'  # 9:30 AM ET

INSERT OR IGNORE INTO futures_orders (
  order_id = 'abc123-def456-ghi789',
  account_id = 'futures-account-123',
  contract_id = 'de9cf980-f53a-4e00-8d23-abc123',
  symbol = '',  # Empty, needs enrichment
  display_symbol = '',
  order_side = 'BUY',
  quantity = 1,
  filled_quantity = 1,
  order_type = 'MARKET',
  order_state = 'FILLED',
  average_price = 5875.25,
  position_effect = 'OPENING',
  realized_pnl = 0.00,
  realized_pnl_without_fees = 0.00,
  total_fee = 2.12,
  trade_date = '2026-01-15',
  execution_time = '2026-01-15T14:30:00.000Z',
  ...
)
```

### 4. Symbol Enrichment
```python
# Query quotes API
url = "https://api.robinhood.com/marketdata/futures/quotes/v1/?ids=de9cf980-f53a-4e00-8d23-abc123"
response = r.helper.request_get(url)

# Extract symbol
quote_data = response['data'][0]['data']
symbol = "/ESH26:XCME"
display_symbol = "/ESH26"

# Update database
UPDATE futures_orders
SET symbol = '/ESH26:XCME', display_symbol = '/ESH26'
WHERE contract_id = 'de9cf980-f53a-4e00-8d23-abc123'
```

### 5. Position Created
```python
# rebuild_positions() groups by contract_id

position_key = "de9cf980-f53a-4e00-8d23-abc123_2026-01-15T14:30:00.000Z"

INSERT INTO futures_positions (
  position_key = position_key,
  contract_id = 'de9cf980-f53a-4e00-8d23-abc123',
  symbol = '/ESH26:XCME',
  display_symbol = '/ESH26',
  open_date = '2026-01-15T14:30:00.000Z',
  close_date = NULL,
  quantity = 1,
  open_price = 5875.25,
  close_price = NULL,
  realized_pnl = NULL,
  realized_pnl_without_fees = NULL,
  total_fees = NULL,
  status = 'open'
)
```

### 6. Later: Close the Position
```
Sell 1 /ESH26
Execution: $5,900.50
Timestamp: 2026-01-20 15:45:00 UTC (10:45 AM ET)
P&L: +$1,262.50 (before fees)
Fees: $2.12
Net P&L: +$1,260.38
```

### 7. Closing Order from API
```json
{
  "orderId": "xyz789-abc123-def456",
  "accountId": "futures-account-123",
  "orderState": "FILLED",
  "quantity": "1",
  "filledQuantity": "1",
  "positionEffectAtPlacementTime": "CLOSING",
  "orderLegs": [{
    "contractId": "de9cf980-f53a-4e00-8d23-abc123",
    "orderSide": "SELL",
    "averagePrice": "5900.50"
  }],
  "orderExecutions": [{
    "eventTime": "2026-01-20T15:45:00.000Z"
  }],
  "realizedPnl": {
    "realizedPnl": { "amount": "1260.38" },
    "realizedPnlWithoutFees": { "amount": "1262.50" }
  },
  "totalFee": { "amount": "2.12" },
  "symbol": "/ESH26:XCME",
  "displaySymbol": "/ESH26"
}
```

### 8. Closing Order Stored & Position Rebuilt
```python
# Insert closing order
INSERT INTO futures_orders (
  order_id = 'xyz789-abc123-def456',
  position_effect = 'CLOSING',
  realized_pnl = 1260.38,  # From API!
  realized_pnl_without_fees = 1262.50,
  total_fee = 2.12,
  ...
)

# Rebuild positions
# Same contract_id now has both open and close orders

UPDATE futures_positions SET
  close_date = '2026-01-20T15:45:00.000Z',
  close_price = 5900.50,
  realized_pnl = 1260.38,  # Sum of closing orders
  realized_pnl_without_fees = 1262.50,
  total_fees = 2.12,
  status = 'closed'
WHERE contract_id = 'de9cf980-f53a-4e00-8d23-abc123'
```

### 9. Daily P&L Query
```sql
SELECT
    trade_date,
    SUM(realized_pnl) as total_pnl
FROM futures_orders
WHERE trade_date = '2026-01-20'
GROUP BY trade_date

-- Result: trade_date='2026-01-20', total_pnl=1260.38
```

### 10. Frontend Display
```json
{
  "closed_positions": [{
    "order_id": "xyz789-abc123-def456",
    "symbol": "/ESH26",
    "close_price": 5900.50,
    "quantity": 1,
    "realized_pnl": 1260.38,
    "realized_pnl_without_fees": 1262.50,
    "total_fee": 2.12,
    "trade_date": "2026-01-20"
  }],
  "daily_pnl": {
    "2026-01-20": {
      "pnl": 1260.38,
      "pnl_no_fees": 1262.50,
      "fees": 2.12,
      "count": 1
    }
  },
  "summary": {
    "total_pnl": 1260.38,
    "total_pnl_without_fees": 1262.50,
    "total_fees": 2.12,
    "num_orders": 2,
    "num_trading_days": 1
  }
}
```

## Testing the Data Flow

### Manual Verification

```bash
# Check database contents
python -c "
from futures.database import FuturesDatabase
db = FuturesDatabase('futures.db')

# Get all orders
orders = db.get_all_orders()
print(f'Total orders: {len(orders)}')

# Get positions
open_pos = db.get_positions_by_status('open')
closed_pos = db.get_positions_by_status('closed')
print(f'Open: {len(open_pos)}, Closed: {len(closed_pos)}')

# Get daily P&L
daily_pnl = db.get_daily_pnl()
total = sum(day['pnl'] for day in daily_pnl.values())
print(f'Total P&L: \${total:.2f}')
"

# Check for missing symbols
python -c "
import sqlite3
conn = sqlite3.connect('futures.db')
cursor = conn.cursor()
cursor.execute('''
    SELECT COUNT(*)
    FROM futures_orders
    WHERE symbol IS NULL OR symbol = \"\"
''')
print(f'Orders missing symbols: {cursor.fetchone()[0]}')
conn.close()
"
```

### Debugging Queries

```sql
-- Check order distribution
SELECT order_state, position_effect, COUNT(*)
FROM futures_orders
GROUP BY order_state, position_effect;

-- Check P&L totals
SELECT
    SUM(realized_pnl) as total_pnl,
    SUM(realized_pnl_without_fees) as pnl_before_fees,
    SUM(total_fee) as total_fees,
    COUNT(*) as closing_orders
FROM futures_orders
WHERE realized_pnl_without_fees != 0;

-- Find contracts without symbols
SELECT contract_id, COUNT(*)
FROM futures_orders
WHERE symbol IS NULL OR symbol = ''
GROUP BY contract_id;

-- Daily P&L breakdown
SELECT trade_date,
       SUM(realized_pnl) as pnl,
       COUNT(*) as trades
FROM futures_orders
WHERE trade_date IS NOT NULL
GROUP BY trade_date
ORDER BY trade_date DESC
LIMIT 10;
```

## Common Issues

### Issue: Missing symbols (contract_id but no display_symbol)
**Cause**: Robinhood API doesn't always include symbol in order response
**Detection**: `symbol IS NULL OR symbol = ''`
**Solution**: Run `enrich_contract_symbols()` - queries quotes API
**Note**: Automatic on every data refresh

### Issue: P&L doesn't match Robinhood
**Cause**: Unlikely - we use Robinhood's P&L directly
**Debugging**:
- Check `realized_pnl` vs `realized_pnl_without_fees`
- Verify all closing orders have P&L != 0
- Compare to Robinhood's Purchase & Sale Summary
**Most likely**: Missing orders - refetch all data

### Issue: Wrong trade dates
**Cause**: Timezone conversion issue
**Check**: Ensure `pytz` is installed
**Verify**:
```python
execution_time = '2026-01-15T14:30:00.000Z'  # UTC
# Should convert to '2026-01-15' in ET (9:30 AM)
# Not '2026-01-16' or wrong date
```

### Issue: Partial fills not showing
**Cause**: Filtering out `PARTIALLY_FILLED_REST_CANCELLED`
**Solution**: We include them - they have real P&L
**Check**:
```sql
SELECT order_state, COUNT(*)
FROM futures_orders
WHERE order_state LIKE '%PARTIAL%'
```

### Issue: Positions not rebuilding
**Cause**: Database locked or error in rebuild
**Manual rebuild**:
```python
from futures.database import FuturesDatabase
db = FuturesDatabase()
db.rebuild_positions()
```

## Differences from Options

| Aspect | Options | Futures |
|--------|---------|---------|
| **P&L Calculation** | We calculate from price diff | Robinhood provides |
| **Architecture** | Service layer | Direct database |
| **Symbol Lookup** | In legs[] | Needs enrichment |
| **Position Pairing** | Complex option_key | Simple contract_id |
| **Status Types** | open/closed/expired/orphaned | open/closed |
| **Spreads** | Skipped | N/A (auto-handled) |
| **Fees** | Not tracked separately | Separate from P&L |
| **Date Field** | close_date | trade_date (ET) |

## Future Enhancements

### 1. Real-time Position Tracking
- Fetch current futures quotes
- Calculate unrealized P&L for open positions
- Mark-to-market updates

### 2. Contract Information Cache
- Store contract specs (multiplier, tick size, expiration)
- Avoid repeated quotes API calls
- Faster symbol enrichment

### 3. Advanced Analytics
- Win rate by contract type
- Average hold time
- Best trading hours
- Slippage analysis

### 4. Position Sizing Metrics
- Margin usage
- Risk per trade
- Maximum drawdown
- Sharpe ratio

---

**Last Updated**: 2026-01-31
**Reviewed Code**: futures/data_fetcher.py, futures/database.py, futures/futures_web.py
**Documentation Status**: ✅ Verified against actual implementation
