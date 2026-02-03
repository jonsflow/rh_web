# Options Data Flow

This document explains how options data flows through the Portfolio Dashboard, from fetching raw order data from Robinhood to calculating positions and P&L.

**This documentation is based on actual code review as of 2026-01-31.**

## Overview

The data pipeline uses a **service layer architecture** with these stages:

1. **Fetch** - Get option orders from Robinhood API
2. **Store** - Save raw orders to database
3. **Rebuild** - Process all orders into positions via service layer
4. **Classify** - Determine position status (open/closed/expired)
5. **Calculate** - Compute P&L for each position
6. **Filter** - Remove orphaned close orders
7. **Display** - Serve data to frontend via API

## 1. Data Fetching

**File**: `portfolio/data_fetcher.py` (SmartDataFetcher class)

### API Call
```python
all_orders = r.orders.get_all_option_orders()
```

This fetches **all historical option orders** from Robinhood with automatic pagination. No date filters - we get everything every time.

### What We Get
Each order from the API contains:
- Order ID (`id`) - Used as `robinhood_id` for deduplication
- Symbol (`chain_symbol`) - Underlying stock ticker
- Legs array with:
  - Position effect (`open` or `close`)
  - Expiration date
  - Strike price (can be multi-leg for spreads)
  - Option type (`call` or `put`)
  - Option ID (Robinhood instrument ID)
- Strategy (`opening_strategy` or `closing_strategy`)
- Direction (`debit` or `credit`)
- Price (`price`) - Price per contract
- Quantity (`processed_quantity`)
- Premium (`processed_premium`) - Total dollar amount
- Timestamps (`created_at`)

### Filtering
We only keep **filled orders**:
```python
filled_orders = [order for order in all_orders if order.get('state') == 'filled']
```

Cancelled, pending, or rejected orders are ignored.

## 2. Database Storage

**Files**: `portfolio/database.py` (OptionsDatabase) and `services/data_repository.py` (DataRepository)

### Option Orders Table
Raw orders are stored in the `option_orders` table:

```sql
CREATE TABLE option_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    robinhood_id TEXT UNIQUE,       -- Deduplication key
    symbol TEXT,                    -- chain_symbol from API
    created_at TEXT,
    position_effect TEXT,            -- 'open' or 'close' (from legs[0])
    expiration_date TEXT,            -- From legs[0]
    strike_price TEXT,               -- Combined for spreads: "100.00/105.00"
    price REAL,                      -- Price per contract
    quantity INTEGER,
    premium REAL,                    -- processed_premium from API
    strategy TEXT,                   -- opening_strategy or closing_strategy
    direction TEXT,                  -- 'debit' or 'credit'
    option_type TEXT,                -- Combined for spreads: "call/call"
    option_ids TEXT,                 -- JSON array of Robinhood instrument IDs
    raw_data TEXT,                   -- Full JSON for debugging
    fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**Deduplication**:
```python
INSERT OR IGNORE INTO option_orders (robinhood_id, ...)
```
The `robinhood_id` (order ID from Robinhood) is unique, so re-fetching all data won't create duplicates.

## 3. Position Rebuilding (Service Layer)

**Files**: `services/option_service.py` (OptionService) and `services/data_repository.py`

After storing raw orders, we completely rebuild all positions from scratch using the service layer.

### Rebuild Trigger
```python
# In portfolio/database.py
def rebuild_positions(self):
    option_service = OptionService(self.db_path)
    positions_processed = option_service.rebuild_all_positions()
```

The database delegates to the service layer for all business logic.

### Position Grouping Logic

**File**: `services/option_service.py` → `process_raw_orders_to_positions()`

Orders are grouped by a unique **option_key**:
```python
option_key = f"{symbol}_{option_ids}_{expiration_date}_{strike_price}"
```

Example: `AAPL_abc123def456_2026-02-20_150.00`

**Important**: Spread strategies are **completely skipped**:
```python
if PnLCalculator.is_spread_strategy(strategy):
    continue  # Skip spreads entirely
```

### Order Aggregation

For each option_key:
1. **Collect all open orders** into `open_orders[]` list
2. **Collect all close orders** into `close_orders[]` list
3. **Aggregate** into position using `_aggregate_position_data()`

#### Open Orders Aggregation:
```python
total_open_quantity = sum(order['quantity'] for order in open_orders)
total_open_premium = sum(order['premium'] for order in open_orders)
weighted_price_sum = sum(price * quantity for order in open_orders)
open_price = weighted_price_sum / total_open_quantity  # Weighted average
open_date = open_orders[0]['date']  # First open date
```

#### Close Orders Aggregation:
```python
total_close_quantity = sum(order['quantity'] for order in close_orders)
total_close_premium = sum(order['premium'] for order in close_orders)
weighted_price_sum = sum(price * quantity for order in close_orders)
close_price = weighted_price_sum / total_close_quantity  # Weighted average
close_date = close_orders[-1]['date']  # Last close date
```

### Positions Table

Positions are stored after processing by the service layer:

```sql
CREATE TABLE positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    option_key TEXT UNIQUE,
    symbol TEXT,
    open_date TEXT,                  -- First open order date
    close_date TEXT,                 -- Last close order date (or expiration for expired)
    expiration_date TEXT,
    strike_price TEXT,
    quantity INTEGER,                -- Total quantity
    open_price REAL,                 -- Weighted average price per contract (open)
    close_price REAL,                -- Weighted average price per contract (close)
    open_premium REAL,               -- Total premium paid/received on open
    close_premium REAL,              -- Total premium paid/received on close
    net_credit REAL,                 -- P&L (calculated by service layer)
    strategy TEXT,
    direction TEXT,
    option_type TEXT,
    status TEXT,                     -- 'open', 'closed', 'expired', 'orphaned'
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**Full Rebuild**: Every data refresh completely deletes and rebuilds this table:
```python
# In services/data_repository.py
def save_positions(self, positions):
    cursor.execute('DELETE FROM positions')  # Full wipe
    # Then INSERT all new positions
```

## 4. Position Classification

**File**: `services/position_classifier.py` (PositionClassifier class)

### Classification Logic

**Method**: `classify_position(position)` returns status string

```python
has_open_premium = position.get('open_premium') is not None
has_close_premium = position.get('close_premium') is not None

# If has both open and close orders - manually closed
if has_open_premium and has_close_premium:
    return 'closed'

# If only has open orders - check if expired
elif has_open_premium:
    if _is_expired(position):
        return 'expired'
    else:
        return 'open'

# If only has close orders - orphaned closing order
elif has_close_premium:
    return 'closed'  # Marked closed but filtered later

# Default
return 'open'
```

### Status Types

1. **Closed** - Has both `open_premium` AND `close_premium`
   - Position was manually closed before expiration
   - P&L calculated from price difference

2. **Expired** - Has `open_premium` only, expiration date has passed
   ```python
   exp_date = datetime.strptime(expiration_date, '%Y-%m-%d')
   return exp_date < datetime.now()
   ```
   - Position expired worthless (or in the money, see P&L section)
   - `close_date` set to `expiration_date`
   - `close_price` and `close_premium` set to 0.0

3. **Open** - Has `open_premium` only, not yet expired
   - Position still active
   - No P&L calculated yet

4. **Orphaned** (special case)
   - Has `close_premium` but NO `open_premium`
   - Open order was before our data collection period started
   - **Status set to 'orphaned' by service layer**
   - **net_credit set to None**
   - **Filtered out from all queries** (WHERE open_premium IS NOT NULL)

## 5. P&L Calculation

**File**: `services/pnl_calculator.py` (PnLCalculator class)

P&L is calculated in the service layer after classification.

### Closed Positions

**Method**: `calculate_closed_position_pnl(position)` → float

Primary calculation using price differences:

```python
price_diff = close_price - open_price
quantity = position['quantity']
direction = position['direction']

if direction == 'debit':
    # Long positions: profit when price increases
    pnl = price_diff * quantity * 100
elif direction == 'credit':
    # Short positions: profit when price decreases
    pnl = -price_diff * quantity * 100
```

**Debit (Long)** - Bought options:
- Paid `open_price` per contract
- Sold for `close_price` per contract
- P&L = (close - open) × quantity × 100
- Example: Bought at $2.00, sold at $3.50 = ($3.50 - $2.00) × 1 × 100 = **$150 profit**

**Credit (Short)** - Sold options:
- Received `open_price` per contract
- Bought back at `close_price` per contract
- P&L = -(close - open) × quantity × 100
- Example: Sold at $2.00, bought back at $0.50 = -($0.50 - $2.00) × 1 × 100 = **$150 profit**

**Fallback** if prices missing:
```python
return open_premium + close_premium
```
Note: Premiums are already signed (credits positive, debits negative).

### Expired Positions

**Method**: `calculate_expired_position_pnl(position)` → float

```python
open_premium = position.get('open_premium', 0)
direction = position['direction']

if direction == 'debit':
    # You paid premium, expired worthless = loss
    return -abs(open_premium)
elif direction == 'credit':
    # You received premium, expired worthless = profit
    return abs(open_premium)
```

**Debit Expired** - You paid money, option expired worthless:
- P&L = -|open_premium|
- Example: Paid $250 premium → **-$250 loss**

**Credit Expired** - You received money, option expired worthless:
- P&L = |open_premium|
- Example: Received $250 premium → **$250 profit**

**Note**: This assumes options expired out of the money. ITM expiration handling is a TODO.

### Open Positions

Open positions have `net_credit = None` (no realized P&L calculated).

### Spread Strategies

**Spreads are completely skipped**:
```python
if PnLCalculator.is_spread_strategy(strategy):
    continue  # Not processed
```

Strategy is a spread if `'_spread' in strategy.lower()`.

### Orphaned Order Handling

Orphaned positions (close without open) are handled in the service layer:

```python
# In services/option_service.py
if PositionClassifier.has_orphaned_close_orders(position_dict):
    position.status = 'orphaned'
    position.net_credit = None  # No P&L
    return position
```

These are filtered out from all database queries:
```sql
WHERE status = ? AND open_premium IS NOT NULL
```

## 6. Summary Aggregation

**Files**: `services/option_service.py`, `models/pnl_summary.py`

### Overall P&L Summary

**Method**: `OptionService.get_pnl_summary()` → PnLSummary

```python
all_positions = get_all_positions()  # Gets open, closed, expired
return PnLSummary.from_positions(all_positions)
```

**PnLSummary calculates**:
```python
for position in positions:
    if position.is_open:
        summary.open_count += 1
        summary.open_value += position.open_premium
    elif position.is_closed:
        summary.closed_count += 1
        summary.closed_pnl += position.net_credit
    elif position.is_expired:
        summary.expired_count += 1
        summary.expired_pnl += position.net_credit

# Computed properties
total_pnl = closed_pnl + expired_pnl
total_positions = open_count + closed_count + expired_count
```

**API Response**:
```json
{
  "closed_pnl": 1250.00,
  "expired_pnl": -300.00,
  "total_pnl": 950.00,
  "open_value": 500.00,
  "open_count": 5,
  "closed_count": 48,
  "expired_count": 12,
  "total_positions": 65
}
```

### Daily P&L Breakdown (Calendar View)

**Method**: `DataRepository.get_daily_pnl_data(start_date, end_date)` → List[DailyPnLSummary]

**SQL Query**:
```sql
SELECT DATE(close_date) as day,
       SUM(CASE WHEN net_credit IS NOT NULL THEN net_credit ELSE 0 END) as daily_pnl,
       COUNT(*) as position_count,
       GROUP_CONCAT(symbol || ' (' || ROUND(net_credit, 2) || ')') as position_details
FROM positions
WHERE status IN ('closed', 'expired') AND close_date IS NOT NULL
GROUP BY DATE(close_date)
ORDER BY close_date DESC
```

**Returns** one DailyPnLSummary per date:
```python
{
  'date': '2026-01-30',
  'pnl': 350.00,
  'count': 3,
  'details': 'AAPL (150.00), TSLA (200.00), SPY (0.00)'
}
```

## Complete Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                       Robinhood API                              │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               │ r.orders.get_all_option_orders()
                               │ (all historical orders, paginated)
                               v
                        [Raw API Orders]
                               │
                               │ Filter: state == 'filled'
                               │ (SmartDataFetcher)
                               v
                        [Filled Orders Only]
                               │
                               │ database.insert_orders()
                               │ INSERT OR IGNORE (dedup by robinhood_id)
                               v
┌──────────────────────────────────────────────────────────────────┐
│                   option_orders table                            │
│  (Raw orders stored with legs, premiums, timestamps)             │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               │ database.rebuild_positions()
                               │ ↓ delegates to service layer
                               v
┌──────────────────────────────────────────────────────────────────┐
│                   OptionService Layer                            │
│                                                                  │
│  1. DataRepository.get_all_raw_orders()                         │
│     └─> Returns tuples ordered by created_at                    │
│                                                                  │
│  2. process_raw_orders_to_positions()                           │
│     ├─> Skip spreads: if is_spread_strategy() continue          │
│     ├─> Group by option_key: {symbol}_{ids}_{exp}_{strike}     │
│     ├─> Collect open_orders[] and close_orders[]               │
│     └─> Process each position:                                  │
│                                                                  │
│  3. _aggregate_position_data()                                  │
│     ├─> Calculate weighted avg prices                           │
│     ├─> Sum premiums                                             │
│     ├─> PositionClassifier.classify_position()                  │
│     │   ├─> 'closed' if has open+close premiums                │
│     │   ├─> 'expired' if only open, past expiration            │
│     │   ├─> 'open' if only open, not expired                   │
│     │   └─> Mark orphaned if only close premium                │
│     │                                                            │
│     ├─> PnLCalculator.calculate_*_pnl()                         │
│     │   ├─> Closed: price_diff * qty * 100 (signed by dir)    │
│     │   └─> Expired: ±open_premium (signed by direction)       │
│     │                                                            │
│     └─> Return Position object with net_credit                  │
│                                                                  │
│  4. DataRepository.save_positions()                             │
│     ├─> DELETE FROM positions (full wipe)                       │
│     └─> INSERT all new positions                                │
└──────────────────────────────┬──────────────────────────────────┘
                               v
┌──────────────────────────────────────────────────────────────────┐
│                     positions table                              │
│  (Aggregated positions with status, P&L, averages)              │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               │ API Requests
                               v
┌──────────────────────────────────────────────────────────────────┐
│              OptionService.get_processed_data_for_api()         │
│                                                                  │
│  DataRepository queries with filters:                           │
│  ├─> WHERE status='open' AND open_premium IS NOT NULL          │
│  ├─> WHERE status='closed' AND open_premium IS NOT NULL        │
│  └─> WHERE status='expired' AND open_premium IS NOT NULL       │
│                                                                  │
│  (Orphaned positions filtered out automatically)                │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               v
                    [Position Lists + Orders]
                               │
                               │ Convert Position objects → dicts
                               v
                        [JSON API Response]
                               │
                               v
                        [Frontend Display]
```

### Key Points

1. **Service Layer Architecture**: Business logic moved out of database.py into separate services
2. **Full Rebuild**: Positions table completely recreated on every data fetch
3. **Orphaned Filtering**: Positions without open orders filtered via `WHERE open_premium IS NOT NULL`
4. **Spread Handling**: Spread strategies completely skipped during processing
5. **Weighted Averages**: Prices calculated as weighted averages when multiple orders exist
6. **Status-Based P&L**: Different calculation methods for closed vs expired positions

## Key Implementation Details

### 1. Service Layer Separation

Business logic is separated from data access:

- **DataRepository**: Pure database operations (queries, inserts)
- **OptionService**: Business orchestration and position processing
- **PnLCalculator**: P&L calculation algorithms
- **PositionClassifier**: Status determination logic
- **Database**: Only handles table creation and delegates to services

This follows the **Single Responsibility Principle** and makes testing easier.

### 2. Option Key Format

Positions are grouped by option_key which includes the option instrument IDs:

```python
option_key = f"{symbol}_{option_ids}_{expiration_date}_{strike_price}"
```

Example: `AAPL_abc123def456_2026-02-20_150.00`

The `option_ids` is extracted from each leg:
```python
option_ids = json.dumps([leg['option'][-13:][:-1] for leg in legs])
```

### 3. Data Fetch Strategy: Full Fetch + Deduplication

We fetch **all historical orders** every time:
```python
all_orders = r.orders.get_all_option_orders()  # No date filter
```

Deduplication happens at insert:
```sql
INSERT OR IGNORE INTO option_orders (robinhood_id, ...)
```

This is simple and ensures we never miss orders, at the cost of API calls. The robin_stocks library handles pagination automatically.

### 4. Full Position Rebuild

Every data refresh **completely rebuilds** the positions table:

1. DataRepository.get_all_raw_orders() - Read all orders
2. OptionService.process_raw_orders_to_positions() - Process in memory
3. DataRepository.save_positions() - DELETE all, INSERT all

```python
def save_positions(self, positions):
    cursor.execute('DELETE FROM positions')  # Full wipe
    for position in positions:
        cursor.execute('INSERT OR REPLACE INTO positions ...')
```

This ensures consistency: positions always match the raw orders data.

### 5. Weighted Average Pricing

When multiple orders exist for the same position:

```python
total_quantity = sum(order['quantity'] for order in orders)
weighted_sum = sum(order['price'] * order['quantity'] for order in orders)
average_price = weighted_sum / total_quantity
```

Example: Buy 2 @ $1.50, buy 3 @ $2.00 = (2×1.50 + 3×2.00) / 5 = **$1.80 avg**

### 6. Spread Strategy Handling

Spreads are **completely skipped** during position processing:

```python
if PnLCalculator.is_spread_strategy(strategy):
    continue  # Skip entirely
```

A strategy is a spread if `'_spread' in strategy.lower()`.

**Reason**: Spread P&L requires understanding which legs are ITM/OTM at expiration, not yet implemented.

### 7. Orphaned Order Filtering

Positions can have close orders without corresponding open orders (open was before data collection started).

**Detection**:
```python
has_close = close_premium is not None
has_open = open_premium is not None
is_orphaned = has_close and not has_open
```

**Handling**:
- Status set to `'orphaned'`
- net_credit set to `None`
- Filtered from all queries: `WHERE open_premium IS NOT NULL`

### 8. Premium vs Price

- **Price**: Price per contract (e.g., $2.50)
- **Premium**: Total dollar amount (e.g., $250.00)
- **Relationship**: `premium = price × quantity × 100`

Robinhood API returns both `price` and `processed_premium`. We store both for accuracy.

## Files Involved

| File | Purpose | Key Classes/Functions |
|------|---------|----------------------|
| `portfolio/data_fetcher.py` | Fetch orders from Robinhood API | SmartDataFetcher, fetch_option_orders() |
| `portfolio/database.py` | Initialize tables, delegate to services | OptionsDatabase, init_database(), rebuild_positions() |
| `services/option_service.py` | **Main business orchestration** | OptionService, process_raw_orders_to_positions() |
| `services/position_classifier.py` | Classify position status | PositionClassifier.classify_position() |
| `services/pnl_calculator.py` | Calculate P&L | PnLCalculator.calculate_closed/expired_pnl() |
| `services/data_repository.py` | **Pure data access layer** | DataRepository, get/save operations |
| `models/option_order.py` | Option order data model | OptionOrder dataclass |
| `models/position.py` | Position data model | Position dataclass with to_dict/from_dict |
| `models/pnl_summary.py` | P&L summary models | PnLSummary, DailyPnLSummary |
| `portfolio/rh_web.py` | Flask API endpoints | /api/options, /api/daily-pnl, /api/update |

## Example Flow

Let's trace a single credit spread trade through the entire system:

### 1. Place Trade on Robinhood
```
Sell AAPL 150 Call expiring 2026-02-20
Price: $2.50 per contract
Quantity: 1 contract
Direction: credit (selling)
Total Credit Received: $250 ($2.50 × 1 × 100)
```

### 2. API Returns Order (filled)
```json
{
  "id": "abc123def456",
  "state": "filled",
  "chain_symbol": "AAPL",
  "legs": [{
    "position_effect": "open",
    "expiration_date": "2026-02-20",
    "strike_price": "150.00",
    "option_type": "call",
    "option": "https://...../instruments/xyz789abc123/"
  }],
  "opening_strategy": "call",
  "direction": "credit",
  "processed_quantity": "1",
  "price": "2.50",
  "processed_premium": "250.00",
  "created_at": "2026-01-15T14:30:00Z"
}
```

### 3. Stored in option_orders Table
```python
# DataRepository.insert_orders()
INSERT OR IGNORE INTO option_orders (
  robinhood_id = 'abc123def456',
  symbol = 'AAPL',
  position_effect = 'open',      # From legs[0]
  expiration_date = '2026-02-20',
  strike_price = '150.00',
  price = 2.50,
  quantity = 1,
  premium = 250.00,
  strategy = 'call',
  direction = 'credit',
  option_type = 'call',
  option_ids = '["xyz789abc123"]',
  created_at = '2026-01-15T14:30:00Z',
  ...
)
```

### 4. Position Built by Service Layer
```python
# OptionService.process_raw_orders_to_positions()

option_key = "AAPL_xyz789abc123_2026-02-20_150.00"

# Group orders by option_key
position_data = {
  'option_key': option_key,
  'symbol': 'AAPL',
  'expiration_date': '2026-02-20',
  'strike_price': '150.00',
  'strategy': 'call',
  'direction': 'credit',
  'option_type': 'call',
  'open_orders': [
    {'date': '2026-01-15T14:30:00Z', 'price': 2.50, 'quantity': 1, 'premium': 250.00}
  ],
  'close_orders': []
}

# Aggregate
position = _aggregate_position_data(position_data)
# Result:
# open_date = '2026-01-15T14:30:00Z'
# open_price = 2.50
# open_premium = 250.00
# quantity = 1
# close_date = None
# close_price = None
# close_premium = None

# Classify
status = PositionClassifier.classify_position(position)
# has_open_premium=True, has_close_premium=False, not_expired=True
# → status = 'open'

# Calculate P&L
# Status is 'open', so net_credit = None
```

### 5. Saved to positions Table
```python
# DataRepository.save_positions()
DELETE FROM positions;  # Full rebuild

INSERT INTO positions (
  option_key = 'AAPL_xyz789abc123_2026-02-20_150.00',
  symbol = 'AAPL',
  open_date = '2026-01-15T14:30:00Z',
  close_date = NULL,
  expiration_date = '2026-02-20',
  strike_price = '150.00',
  quantity = 1,
  open_price = 2.50,
  close_price = NULL,
  open_premium = 250.00,
  close_premium = NULL,
  net_credit = NULL,
  strategy = 'call',
  direction = 'credit',
  option_type = 'call',
  status = 'open'
)
```

### 6. Later: Close the Trade on Robinhood
```
Buy back AAPL 150 Call
Price: $1.00 per contract
Quantity: 1 contract
Total Debit Paid: $100
```

### 7. New Close Order from API
```json
{
  "id": "xyz456def789",
  "state": "filled",
  "chain_symbol": "AAPL",
  "legs": [{
    "position_effect": "close",
    "expiration_date": "2026-02-20",
    "strike_price": "150.00",
    "option_type": "call",
    "option": "https://...../instruments/xyz789abc123/"
  }],
  "closing_strategy": "call",
  "direction": "debit",
  "processed_quantity": "1",
  "price": "1.00",
  "processed_premium": "100.00",
  "created_at": "2026-01-20T10:15:00Z"
}
```

### 8. Close Order Stored & Positions Rebuilt
```python
# New order inserted with position_effect='close'
# Full rebuild triggered

# During rebuild, same option_key now has:
position_data = {
  'option_key': 'AAPL_xyz789abc123_2026-02-20_150.00',
  'open_orders': [
    {'date': '2026-01-15...', 'price': 2.50, 'quantity': 1, 'premium': 250.00}
  ],
  'close_orders': [
    {'date': '2026-01-20...', 'price': 1.00, 'quantity': 1, 'premium': 100.00}
  ]
}

# Aggregated:
# open_price = 2.50, close_price = 1.00
# open_premium = 250.00, close_premium = 100.00

# Classified:
# has_open_premium=True, has_close_premium=True
# → status = 'closed'

# P&L Calculated (credit position):
price_diff = 1.00 - 2.50 = -1.50
pnl = -(price_diff) * 1 * 100 = -(-1.50) * 100 = $150.00

# Position saved with:
# status = 'closed'
# net_credit = 150.00
# close_date = '2026-01-20T10:15:00Z'
```

### 9. Daily P&L Query
```sql
SELECT DATE('2026-01-20') as day,
       SUM(net_credit) as daily_pnl,
       COUNT(*) as position_count
FROM positions
WHERE status IN ('closed', 'expired')
  AND DATE(close_date) = '2026-01-20'

-- Result: day='2026-01-20', pnl=150.00, count=1
```

### 10. Frontend Display
```json
{
  "closed_positions": [{
    "symbol": "AAPL",
    "strike_price": "150.00",
    "expiration_date": "2026-02-20",
    "strategy": "call",
    "direction": "credit",
    "open_price": 2.50,
    "close_price": 1.00,
    "net_credit": 150.00,
    "status": "closed"
  }],
  "daily_pnl": {
    "2026-01-20": {
      "pnl": 150.00,
      "count": 1
    }
  }
}
```

## Testing the Data Flow

### Unit Tests
```bash
# Run service layer tests
pytest tests/test_pnl_calculator.py
pytest tests/test_position_classifier.py
pytest tests/test_option_service.py

# Test data repository
pytest tests/test_data_repository.py
```

### Manual Verification

```bash
# Check database contents
python -c "
from services.option_service import OptionService
service = OptionService('options.db')

# Get all positions
positions_data = service.get_all_positions()
print(f'Open: {len(positions_data[\"open_positions\"])}')
print(f'Closed: {len(positions_data[\"closed_positions\"])}')
print(f'Expired: {len(positions_data[\"expired_positions\"])}')

# Get P&L summary
summary = service.get_pnl_summary()
print(f'Total P&L: \${summary.total_pnl:.2f}')
print(f'Closed P&L: \${summary.closed_pnl:.2f}')
print(f'Expired P&L: \${summary.expired_pnl:.2f}')
"

# Check for orphaned positions
python -c "
import sqlite3
conn = sqlite3.connect('options.db')
cursor = conn.cursor()
cursor.execute('''
    SELECT COUNT(*), status
    FROM positions
    WHERE open_premium IS NULL
    GROUP BY status
''')
print('Orphaned positions (should be 0 after filtering):')
for row in cursor.fetchall():
    print(f'  {row[1]}: {row[0]}')
conn.close()
"
```

### Debugging Queries

```sql
-- Check raw orders
SELECT COUNT(*), position_effect FROM option_orders GROUP BY position_effect;

-- Check position distribution
SELECT status, COUNT(*),
       SUM(CASE WHEN net_credit IS NOT NULL THEN net_credit ELSE 0 END) as total_pnl
FROM positions
GROUP BY status;

-- Find orphaned positions
SELECT * FROM positions WHERE open_premium IS NULL;

-- Check daily P&L
SELECT DATE(close_date) as day, SUM(net_credit) as pnl, COUNT(*) as count
FROM positions
WHERE status IN ('closed', 'expired')
GROUP BY DATE(close_date)
ORDER BY day DESC
LIMIT 10;
```

## Common Issues

### Issue: Missing P&L for old positions
**Cause**: Open orders placed before we started collecting data
**Detection**: Position has `close_premium` but no `open_premium`
**Solution**: Automatically marked as `status='orphaned'` and filtered via `WHERE open_premium IS NOT NULL`
**Impact**: These positions don't affect P&L calculations

### Issue: Spread strategies not showing up
**Cause**: Spreads are completely skipped during processing
**Detection**: Check strategy field for `'_spread'` suffix
**Solution**: This is by design - spread P&L calculation requires ITM/OTM logic not yet implemented
**Workaround**: Manually track spreads separately

### Issue: Duplicate positions with same strikes
**Cause**: Different option_ids (different trade dates or adjustments)
**Detection**: Same symbol/strike/expiration but different option_key
**Solution**: This is correct - each unique option instrument ID creates a separate position
**Example**: Rolling a position creates two separate positions

### Issue: P&L doesn't match Robinhood
**Cause**: Missing orders, orphaned closes, or spread handling
**Debugging**:
```python
# Check for orphaned positions
service = OptionService()
positions = service.repository.get_positions_by_status('closed')
orphaned = [p for p in positions if p.open_premium is None]
print(f'Found {len(orphaned)} orphaned positions')

# Verify order count matches Robinhood
orders = service.repository.get_all_raw_orders()
print(f'Total orders in DB: {len(orders)}')
```

### Issue: Positions not updating after refresh
**Cause**: Data fetch or rebuild failed
**Check logs**: Look for errors in `fetch_option_orders()` or `rebuild_all_positions()`
**Manual rebuild**:
```python
from services.option_service import OptionService
service = OptionService()
count = service.rebuild_all_positions()
print(f'Rebuilt {count} positions')
```

## Architecture Patterns Used

### 1. Service Layer Pattern
Business logic separated from data access:
- **DataRepository**: Pure CRUD operations
- **OptionService**: Orchestrates business workflows
- **Calculators/Classifiers**: Specialized algorithms

**Benefit**: Easy to test, modify, and extend

### 2. Repository Pattern
DataRepository provides abstract interface to database:
- Hide SQL details from business logic
- Consistent API for data access
- Easy to swap database implementation

### 3. Data Model Objects
Using dataclasses for type safety and structure:
- **Position**: Rich domain object with properties
- **OptionOrder**: Raw order representation
- **PnLSummary**: Computed summary data

**Benefit**: IntelliSense support, type checking, cleaner code

### 4. Full Rebuild Strategy
Instead of complex incremental updates:
- Fetch all orders (deduped at insert)
- Delete all positions
- Rebuild all from scratch

**Benefit**: Simple, consistent, no sync issues
**Trade-off**: More processing, but acceptable for current scale

### 5. Query-Time Filtering
Orphaned positions stored but filtered at query time:
- Stored with `open_premium IS NULL`
- Every query includes `WHERE open_premium IS NOT NULL`

**Benefit**: Can debug orphaned data, filtering is explicit

## Future Enhancements

### 1. Spread Strategy Support
Currently skipped - requires:
- ITM/OTM detection at expiration
- Per-leg P&L calculation
- Understanding of spread mechanics (max profit/loss)

### 2. Unrealized P&L for Open Positions
Requires:
- Fetching current option prices
- Calculating mark-to-market value
- Real-time updates during market hours

### 3. Incremental Position Updates
Instead of full rebuild:
- Track which orders are new
- Only recompute affected positions
- Keep existing positions unchanged

### 4. Trade Analysis
- Win rate by strategy type
- Average hold time
- Best/worst performing symbols
- Time-of-day analysis

---

**Last Updated**: 2026-01-31
**Reviewed Code**: All service layer files, database.py, data_fetcher.py, models
**Documentation Status**: ✅ Verified against actual implementation
