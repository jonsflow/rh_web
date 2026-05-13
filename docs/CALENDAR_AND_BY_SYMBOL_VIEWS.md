# Calendar and By-Symbol/By-Date API Endpoints

This document explains the calendar view and by-symbol/by-date API endpoints used across all three dashboards (Options, Stocks, Futures).

**This documentation is based on actual code review as of 2026-01-31.**

## Overview

All three dashboards provide:

1. **Calendar View** - Daily P&L calendar (server-side APIs)
2. **By-Symbol View** - Aggregated stats per symbol (client-side grouping)
3. **By-Date Details** - Drill-down for specific dates (server-side APIs)

### Server-Side Endpoints (API)

1. **GET /api/daily-pnl** - Get daily P&L summary for calendar rendering
2. **GET /api/positions/date/<date>** - Get detailed data for a specific date
3. **GET /api/daily-summary/<date>** - Get aggregated summary (stocks/futures only)

### Client-Side Functionality (No API)

**By-Symbol View** - The "by symbol" aggregation is done **entirely in JavaScript**:
- Uses data from main endpoints (`/api/stocks`, `/api/options`, `/api/futures`)
- Groups positions/orders by symbol client-side
- Calculates per-symbol stats (total P&L, win rate, avg P&L per trade)
- Renders heatmap and table
- No separate server-side API endpoint needed

The data returned differs based on the asset type and how P&L is calculated.

---

## Options Dashboard

**Port**: 3000
**Base URL**: http://localhost:3000

### 1. GET /api/daily-pnl

Returns daily P&L data for rendering the calendar view.

#### Endpoint
```
GET /api/daily-pnl?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
```

#### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| start_date | string | No | Filter: Include only dates >= this date |
| end_date | string | No | Filter: Include only dates <= this date |

#### Implementation
```python
# portfolio/rh_web.py
@app.route('/api/daily-pnl')
def get_daily_pnl():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    daily_summary = data_fetcher.option_service.get_daily_pnl_summary(start_date, end_date)

    return jsonify({
        'success': True,
        'daily_pnl': daily_summary
    })
```

#### Data Source
```python
# services/data_repository.py → get_daily_pnl_data()
SELECT DATE(close_date) as day,
       SUM(CASE WHEN net_credit IS NOT NULL THEN net_credit ELSE 0 END) as daily_pnl,
       COUNT(*) as position_count,
       GROUP_CONCAT(symbol || ' (' || ROUND(net_credit, 2) || ')') as position_details
FROM positions
WHERE status IN ('closed', 'expired') AND close_date IS NOT NULL
  [AND DATE(close_date) >= start_date]
  [AND DATE(close_date) <= end_date]
GROUP BY DATE(close_date)
ORDER BY close_date DESC
```

**Key Points**:
- P&L attributed to **close_date** (when position was closed or expired)
- Includes both **closed** and **expired** positions
- net_credit calculated by service layer (see OPTIONS_DATA_FLOW.md)
- position_details shows each position with its P&L

#### Response Format
```json
{
  "success": true,
  "daily_pnl": {
    "2026-01-30": {
      "date": "2026-01-30",
      "pnl": 350.00,
      "count": 3,
      "details": "AAPL (150.00), TSLA (200.00), SPY (0.00)"
    },
    "2026-01-29": {
      "date": "2026-01-29",
      "pnl": -125.50,
      "count": 2,
      "details": "NVDA (-100.00), AMD (-25.50)"
    }
  }
}
```

#### Response Fields
| Field | Type | Description |
|-------|------|-------------|
| date | string | Trading date (YYYY-MM-DD) |
| pnl | float | Total P&L for the day |
| count | int | Number of positions closed/expired |
| details | string | Comma-separated list of positions with P&L |

---

### 2. GET /api/positions/date/<date>

Returns detailed positions for a specific date (used when clicking a calendar date).

#### Endpoint
```
GET /api/positions/date/2026-01-30
```

#### Parameters
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| date | string | Yes | Date in YYYY-MM-DD format (path parameter) |

#### Implementation
```python
# portfolio/rh_web.py
@app.route('/api/positions/date/<date>')
def get_positions_by_date(date):
    positions = data_fetcher.option_service.get_positions_by_date(date)

    positions_data = [pos.to_dict() for pos in positions]

    return jsonify({
        'success': True,
        'date': date,
        'positions': positions_data
    })
```

#### Data Source
```python
# services/data_repository.py → get_positions_by_date()
SELECT option_key, symbol, open_date, close_date, expiration_date, strike_price,
       quantity, open_price, close_price, open_premium, close_premium, net_credit,
       strategy, direction, option_type, status
FROM positions
WHERE status IN ('closed', 'expired') AND DATE(close_date) = ?
ORDER BY close_date DESC
```

**Key Points**:
- Only positions **closed or expired** on this specific date
- Includes full position details (open/close prices, premiums, P&L)
- Ordered by close_date (most recent first)

#### Response Format
```json
{
  "success": true,
  "date": "2026-01-30",
  "positions": [
    {
      "option_key": "AAPL_abc123_2026-02-20_150.00",
      "symbol": "AAPL",
      "open_date": "2026-01-15T14:30:00Z",
      "close_date": "2026-01-30T10:15:00Z",
      "expiration_date": "2026-02-20",
      "strike_price": "150.00",
      "quantity": 1,
      "open_price": 2.50,
      "close_price": 4.00,
      "open_premium": 250.00,
      "close_premium": 400.00,
      "net_credit": 150.00,
      "strategy": "call",
      "direction": "debit",
      "option_type": "call",
      "status": "closed"
    },
    {
      "option_key": "TSLA_def456_2026-01-31_900.00",
      "symbol": "TSLA",
      "open_date": "2026-01-20T09:30:00Z",
      "close_date": "2026-01-30T15:45:00Z",
      "expiration_date": "2026-01-31",
      "strike_price": "900.00",
      "quantity": 2,
      "open_price": 5.00,
      "close_price": 6.00,
      "open_premium": 1000.00,
      "close_premium": 1200.00,
      "net_credit": 200.00,
      "strategy": "call",
      "direction": "debit",
      "option_type": "call",
      "status": "closed"
    }
  ]
}
```

#### Position Fields
| Field | Type | Description |
|-------|------|-------------|
| option_key | string | Unique position identifier |
| symbol | string | Underlying stock ticker |
| open_date | string | When position was opened (ISO timestamp) |
| close_date | string | When position was closed (ISO timestamp) |
| expiration_date | string | Option expiration date |
| strike_price | string | Strike price |
| quantity | int | Number of contracts |
| open_price | float | Average open price per contract |
| close_price | float | Average close price per contract |
| open_premium | float | Total premium paid/received on open |
| close_premium | float | Total premium paid/received on close |
| net_credit | float | **P&L for this position** |
| strategy | string | Option strategy (call, put, etc.) |
| direction | string | "debit" or "credit" |
| option_type | string | "call" or "put" |
| status | string | "closed" or "expired" |

---

## Stocks Dashboard

**Port**: 3002
**Base URL**: http://localhost:3002

### 1. GET /api/daily-pnl

Returns daily P&L data for calendar view.

#### Endpoint
```
GET /api/daily-pnl?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
```

#### Parameters
Same as options: start_date and end_date (optional)

#### Implementation
```python
# stocks/stocks_web.py
@app.route('/api/daily-pnl')
def get_daily_pnl():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    daily_pnl = data_fetcher.db.get_daily_pnl(start_date, end_date)

    return jsonify({
        'success': True,
        'daily_pnl': daily_pnl
    })
```

#### Data Source
```python
# stocks/database.py → get_daily_pnl()
# Uses FIFO-matched closed positions
closed_positions = self.get_closed_positions()

# Group by sell_date
for pos in closed_positions:
    sell_date = pos['sell_date']
    daily_pnl[sell_date]['pnl'] += pos['pnl']
    daily_pnl[sell_date]['count'] += 1
```

**Key Points**:
- P&L attributed to **sell_date** (when shares were sold)
- Uses **FIFO matching** - pairs buys with sells in order
- Only **properly paired** closed positions (no orphaned orders)
- Stocks typically have **no fees** (displayed as 0)

#### Response Format
```json
{
  "success": true,
  "daily_pnl": {
    "2026-01-30": {
      "pnl": 525.75,
      "fees": 0,
      "pnl_no_fees": 525.75,
      "count": 5
    },
    "2026-01-29": {
      "pnl": -150.25,
      "fees": 0,
      "pnl_no_fees": -150.25,
      "count": 3
    }
  }
}
```

#### Response Fields
| Field | Type | Description |
|-------|------|-------------|
| pnl | float | Total realized P&L for the day |
| fees | float | Total fees (always 0 for stocks) |
| pnl_no_fees | float | Same as pnl (no fees for stocks) |
| count | int | Number of closed positions |

**Note**: Unlike options, stocks response does NOT include position details string.

---

### 2. GET /api/positions/date/<date>

Returns all **orders** (not positions) for a specific date.

#### Endpoint
```
GET /api/positions/date/2026-01-30
```

#### Implementation
```python
# stocks/stocks_web.py
@app.route('/api/positions/date/<date>')
def get_positions_by_date(date):
    orders_on_date = data_fetcher.db.get_orders_by_trade_date(date)

    return jsonify({
        'success': True,
        'date': date,
        'orders': orders_on_date
    })
```

#### Data Source
```python
# stocks/database.py → get_orders_by_trade_date()
SELECT order_id, symbol, side, quantity, average_price,
       total_amount, fees, last_transaction_at
FROM stock_orders
WHERE trade_date = ? AND state = 'filled'
ORDER BY last_transaction_at
```

**Key Points**:
- Returns **individual orders**, not paired positions
- Includes **both buy and sell** orders for the date
- Ordered by execution time

#### Response Format
```json
{
  "success": true,
  "date": "2026-01-30",
  "orders": [
    {
      "order_id": "abc123",
      "symbol": "AAPL",
      "side": "sell",
      "quantity": 10,
      "average_price": 175.50,
      "total_amount": 1755.00,
      "fees": 0,
      "execution_time": "2026-01-30T14:30:25Z"
    },
    {
      "order_id": "def456",
      "symbol": "TSLA",
      "side": "buy",
      "quantity": 5,
      "average_price": 225.00,
      "total_amount": 1125.00,
      "fees": 0,
      "execution_time": "2026-01-30T10:15:42Z"
    }
  ]
}
```

#### Order Fields
| Field | Type | Description |
|-------|------|-------------|
| order_id | string | Robinhood order ID |
| symbol | string | Stock ticker |
| side | string | "buy" or "sell" |
| quantity | int | Number of shares |
| average_price | float | Execution price per share |
| total_amount | float | Total dollar amount |
| fees | float | Fees (usually 0) |
| execution_time | string | Order execution timestamp |

---

### 3. GET /api/daily-summary/<date>

Returns aggregated summary showing opened and closed positions by symbol.

#### Endpoint
```
GET /api/daily-summary/2026-01-30
```

#### Implementation
```python
# stocks/stocks_web.py
@app.route('/api/daily-summary/<date>')
def get_daily_summary(date):
    summary = data_fetcher.db.get_daily_summary(date)

    return jsonify({
        'success': True,
        'summary': summary
    })
```

#### Data Source
```python
# stocks/database.py → get_daily_summary()
# Groups closed positions by symbol for this date
closed_positions = self.get_closed_positions()

for pos in closed_positions:
    if pos['sell_date'] == trade_date:
        closed_data[symbol]['total_quantity'] += pos['quantity']
        closed_data[symbol]['total_cost'] += pos['cost']
        closed_data[symbol]['total_proceeds'] += pos['proceeds']
        closed_data[symbol]['total_pnl'] += pos['pnl']
```

**Key Points**:
- Aggregates by **symbol** (not individual positions)
- Shows **closed positions** (sold on this date)
- Calculates total quantity, cost, proceeds, P&L per symbol
- Also shows **opened positions** (bought but not sold yet)

#### Response Format
```json
{
  "success": true,
  "summary": {
    "date": "2026-01-30",
    "closed_positions": [
      {
        "symbol": "AAPL",
        "total_quantity": 20,
        "avg_buy_price": 170.25,
        "avg_sell_price": 175.50,
        "total_cost": 3405.00,
        "total_proceeds": 3510.00,
        "total_pnl": 105.00,
        "positions_count": 2
      },
      {
        "symbol": "TSLA",
        "total_quantity": 10,
        "avg_buy_price": 900.00,
        "avg_sell_price": 942.50,
        "total_cost": 9000.00,
        "total_proceeds": 9425.00,
        "total_pnl": 425.00,
        "positions_count": 1
      }
    ],
    "opened_positions": [
      {
        "symbol": "NVDA",
        "total_quantity": 5,
        "avg_buy_price": 520.00,
        "total_cost": 2600.00
      }
    ],
    "totals": {
      "total_closed_quantity": 30,
      "total_pnl": 530.00,
      "total_opened_quantity": 5,
      "total_opened_cost": 2600.00
    }
  }
}
```

#### Summary Fields

**Closed Positions**:
| Field | Type | Description |
|-------|------|-------------|
| symbol | string | Stock ticker |
| total_quantity | int | Total shares sold |
| avg_buy_price | float | Weighted average buy price |
| avg_sell_price | float | Weighted average sell price |
| total_cost | float | Total cost basis |
| total_proceeds | float | Total sale proceeds |
| total_pnl | float | Total P&L for this symbol |
| positions_count | int | Number of closed positions |

**Opened Positions**:
| Field | Type | Description |
|-------|------|-------------|
| symbol | string | Stock ticker |
| total_quantity | int | Total shares bought |
| avg_buy_price | float | Weighted average buy price |
| total_cost | float | Total cost basis |

---

## Futures Dashboard

**Port**: 3001
**Base URL**: http://localhost:3001

### 1. GET /api/daily-pnl

Returns daily P&L data for calendar view.

#### Endpoint
```
GET /api/daily-pnl?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
```

#### Parameters
Same as options and stocks: start_date and end_date (optional)

#### Implementation
```python
# futures/futures_web.py
@app.route('/api/daily-pnl')
def get_daily_pnl():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    daily_pnl = data_fetcher.db.get_daily_pnl(start_date, end_date)

    return jsonify({
        'success': True,
        'daily_pnl': daily_pnl
    })
```

#### Data Source
```python
# futures/database.py → get_daily_pnl()
SELECT
    trade_date,
    SUM(realized_pnl) as total_pnl,
    SUM(realized_pnl_without_fees) as total_pnl_no_fees,
    SUM(total_fee) as total_fees,
    COUNT(*) as order_count
FROM futures_orders
WHERE order_state IN ('FILLED', 'PARTIALLY_FILLED_REST_CANCELLED')
  AND trade_date IS NOT NULL
  [AND trade_date >= start_date]
  [AND trade_date <= end_date]
GROUP BY trade_date
ORDER BY trade_date DESC
```

**Key Points**:
- P&L attributed to **trade_date** (execution date in Eastern Time)
- Uses **realized_pnl from Robinhood** (not calculated)
- Sums **all orders** for the date (not positions)
- Includes **partial fills**
- Separates P&L with and without fees

#### Response Format
```json
{
  "success": true,
  "daily_pnl": {
    "2026-01-30": {
      "pnl": 1260.38,
      "pnl_no_fees": 1262.50,
      "fees": 2.12,
      "count": 3
    },
    "2026-01-29": {
      "pnl": -525.75,
      "pnl_no_fees": -523.63,
      "fees": 2.12,
      "count": 2
    }
  }
}
```

#### Response Fields
| Field | Type | Description |
|-------|------|-------------|
| pnl | float | Total P&L including fees |
| pnl_no_fees | float | Total P&L before fees |
| fees | float | Total fees charged |
| count | int | Number of filled orders |

**Important**: This matches **Robinhood's Purchase and Sale Summary** exactly.

---

### 2. GET /api/positions/date/<date>

Returns all **orders** for a specific trade date.

#### Endpoint
```
GET /api/positions/date/2026-01-30
```

#### Implementation
```python
# futures/futures_web.py
@app.route('/api/positions/date/<date>')
def get_positions_by_date(date):
    orders_on_date = data_fetcher.db.get_orders_by_trade_date(date)

    return jsonify({
        'success': True,
        'date': date,
        'orders': orders_on_date
    })
```

#### Data Source
```python
# futures/database.py → get_orders_by_trade_date()
SELECT * FROM futures_orders
WHERE trade_date = ?
  AND order_state IN ('FILLED', 'PARTIALLY_FILLED_REST_CANCELLED')
ORDER BY execution_time
```

**Key Points**:
- Returns **all orders** executed on this date
- Includes **opening and closing** orders
- Ordered by execution time

#### Response Format
```json
{
  "success": true,
  "date": "2026-01-30",
  "orders": [
    {
      "id": 1,
      "order_id": "abc123-def456",
      "account_id": "futures-123",
      "contract_id": "de9cf980-f53a-4e00-8d23",
      "symbol": "/ESH26:XCME",
      "display_symbol": "/ESH26",
      "order_side": "SELL",
      "quantity": 1,
      "filled_quantity": 1,
      "order_type": "MARKET",
      "order_state": "FILLED",
      "average_price": 5900.50,
      "position_effect": "CLOSING",
      "realized_pnl": 1260.38,
      "realized_pnl_without_fees": 1262.50,
      "total_fee": 2.12,
      "total_commission": 1.50,
      "total_gold_savings": 0.62,
      "created_at": "2026-01-30T15:45:00Z",
      "updated_at": "2026-01-30T15:45:01Z",
      "trade_date": "2026-01-30",
      "execution_time": "2026-01-30T15:45:00.123Z",
      "fetched_at": "2026-01-30T16:00:00Z"
    }
  ]
}
```

#### Order Fields
| Field | Type | Description |
|-------|------|-------------|
| order_id | string | Robinhood order ID |
| contract_id | string | Futures contract ID |
| symbol | string | Full symbol (e.g., "/ESH26:XCME") |
| display_symbol | string | Display name (e.g., "/ESH26") |
| order_side | string | "BUY" or "SELL" |
| quantity | int | Order quantity |
| filled_quantity | int | Actually filled quantity |
| order_state | string | "FILLED" or "PARTIALLY_FILLED_REST_CANCELLED" |
| average_price | float | Execution price |
| position_effect | string | "OPENING" or "CLOSING" |
| realized_pnl | float | **P&L with fees (from Robinhood)** |
| realized_pnl_without_fees | float | **P&L before fees** |
| total_fee | float | Total fees |
| trade_date | string | Trade date in ET |
| execution_time | string | Execution timestamp |

---

### 3. GET /api/daily-summary/<date>

Returns aggregated summary matching Robinhood's Purchase and Sale Summary.

#### Endpoint
```
GET /api/daily-summary/2026-01-30
```

#### Implementation
```python
# futures/futures_web.py
@app.route('/api/daily-summary/<date>')
def get_daily_summary(date):
    summary = data_fetcher.db.get_daily_summary(date)

    return jsonify({
        'success': True,
        'summary': summary
    })
```

#### Data Source
```python
# futures/database.py → get_daily_summary()
SELECT
    contract_id,
    symbol,
    display_symbol,
    SUM(CASE WHEN order_side = 'BUY' THEN filled_quantity ELSE 0 END) as total_qty_long,
    SUM(CASE WHEN order_side = 'SELL' THEN filled_quantity ELSE 0 END) as total_qty_short,
    SUM(realized_pnl) as gross_pnl,
    COUNT(*) as order_count
FROM futures_orders
WHERE trade_date = ? AND order_state IN ('FILLED', 'PARTIALLY_FILLED_REST_CANCELLED')
GROUP BY contract_id
```

**Key Points**:
- Aggregates by **contract** (not individual orders)
- Separates **long (BUY)** and **short (SELL)** quantities
- Sums **realized P&L** from Robinhood
- Matches Robinhood's official reporting format

#### Response Format
```json
{
  "success": true,
  "summary": {
    "date": "2026-01-30",
    "contracts": [
      {
        "contract_id": "de9cf980-f53a-4e00-8d23",
        "symbol": "/ESH26",
        "total_qty_long": 5,
        "total_qty_short": 5,
        "gross_pnl": 1260.38,
        "order_count": 10
      },
      {
        "contract_id": "ab1cd234-ef56-78gh-90ij",
        "symbol": "/NQH26",
        "total_qty_long": 2,
        "total_qty_short": 2,
        "gross_pnl": -350.25,
        "order_count": 4
      }
    ],
    "totals": {
      "total_qty_long": 7,
      "total_qty_short": 7,
      "gross_pnl": 910.13
    }
  }
}
```

#### Summary Fields

**Per Contract**:
| Field | Type | Description |
|-------|------|-------------|
| contract_id | string | Futures contract ID |
| symbol | string | Display symbol (e.g., "/ESH26") |
| total_qty_long | int | Total contracts bought (BUY) |
| total_qty_short | int | Total contracts sold (SELL) |
| gross_pnl | float | Total realized P&L |
| order_count | int | Number of orders |

**Totals**:
| Field | Type | Description |
|-------|------|-------------|
| total_qty_long | int | Sum of all long quantities |
| total_qty_short | int | Sum of all short quantities |
| gross_pnl | float | Sum of all P&L |

---

## Comparison Table

| Feature | Options | Stocks | Futures |
|---------|---------|--------|---------|
| **Daily P&L Date Field** | close_date | sell_date | trade_date |
| **P&L Source** | Calculated by us | Calculated (FIFO) | From Robinhood API |
| **Position Type** | Paired positions | FIFO pairs | Orders with P&L |
| **Fees Tracked** | No | No | Yes |
| **By-Date Returns** | Positions | Orders | Orders |
| **Includes Details** | Yes (position list) | No | No |
| **Daily Summary** | No separate endpoint | Yes (by symbol) | Yes (by contract) |
| **Supports Filters** | Yes (start/end date) | Yes | Yes |

## Frontend Usage Examples

### Options Calendar View
```javascript
// Fetch daily P&L for calendar
fetch('/api/daily-pnl?start_date=2026-01-01&end_date=2026-01-31')
  .then(res => res.json())
  .then(data => {
    // Render calendar with data.daily_pnl
    // Each date shows pnl and count
  });

// When user clicks a date, get positions
fetch('/api/positions/date/2026-01-15')
  .then(res => res.json())
  .then(data => {
    // Show modal with data.positions
    // Each position shows full details
  });
```

### Stocks Calendar View
```javascript
// Fetch daily P&L
fetch('/api/daily-pnl')
  .then(res => res.json())
  .then(data => {
    // Render calendar
  });

// Get orders for a date
fetch('/api/positions/date/2026-01-15')
  .then(res => res.json())
  .then(data => {
    // Show data.orders (buy/sell orders)
  });

// Get summary by symbol
fetch('/api/daily-summary/2026-01-15')
  .then(res => res.json())
  .then(data => {
    // Show data.summary.closed_positions
    // Show data.summary.opened_positions
  });
```

### Futures Calendar View
```javascript
// Fetch daily P&L
fetch('/api/daily-pnl')
  .then(res => res.json())
  .then(data => {
    // Render calendar
    // Show pnl_no_fees and fees separately
  });

// Get orders for a date
fetch('/api/positions/date/2026-01-15')
  .then(res => res.json())
  .then(data => {
    // Show data.orders with realized_pnl
  });

// Get summary by contract
fetch('/api/daily-summary/2026-01-15')
  .then(res => res.json())
  .then(data => {
    // Show data.summary.contracts
    // Display long/short quantities and P&L
  });
```

## Error Responses

All endpoints return errors in this format:
```json
{
  "error": "Failed to fetch daily PnL data"
}
```

HTTP status codes:
- **200** - Success
- **500** - Internal server error

## By-Symbol View (Client-Side Grouping)

The "by symbol" view does NOT use a separate API endpoint. It's implemented entirely client-side.

### How It Works

1. **Fetch Data** - Uses main endpoint to get all positions/orders
2. **Group by Symbol** - JavaScript groups data by symbol
3. **Calculate Stats** - Aggregates metrics per symbol
4. **Render** - Displays heatmap and table

### Stocks Dashboard

**File**: `stocks/static/js/main.js`

```javascript
// Fetch all closed positions
const closedPositions = stocksData.closed_positions;

// Group by symbol
const symbolStats = {};
closedPositions.forEach(pos => {
    const symbol = pos.symbol;
    if (!symbolStats[symbol]) {
        symbolStats[symbol] = {
            symbol: symbol,
            total_pnl: 0,
            total_quantity: 0,
            num_trades: 0,
            winning_trades: 0,
            losing_trades: 0
        };
    }

    symbolStats[symbol].total_pnl += pos.pnl;
    symbolStats[symbol].total_quantity += pos.quantity;
    symbolStats[symbol].num_trades += 1;

    if (pos.pnl > 0) symbolStats[symbol].winning_trades += 1;
    else if (pos.pnl < 0) symbolStats[symbol].losing_trades += 1;
});

// Convert to array and sort by P&L
const symbolArray = Object.values(symbolStats)
    .sort((a, b) => b.total_pnl - a.total_pnl);

// Render heatmap and table
renderHeatmap(symbolArray);
renderSymbolTable(symbolArray);
```

**Stats Calculated**:
- Total P&L per symbol
- Number of trades
- Winning vs losing trades
- Win rate percentage
- Average P&L per trade

**Display Components**:
1. **Heatmap** - Visual representation of P&L by symbol (size = volume, color = profit/loss)
2. **Table** - Detailed stats per symbol
3. **Click Symbol** → Opens modal showing all trades for that symbol

### Symbol Detail Modal

When clicking a symbol, shows:
```javascript
function showSymbolTrades(symbol) {
    // Filter all orders for this symbol
    const symbolOrders = stocksData.all_orders
        .filter(order => order.symbol === symbol);

    // Get FIFO-matched positions for this symbol
    const closedPositions = stocksData.closed_positions
        .filter(pos => pos.symbol === symbol);

    // Calculate stats
    const totalPnl = closedPositions.reduce((sum, pos) => sum + pos.pnl, 0);
    const sharesTraded = symbolOrders.reduce((sum, order) => sum + order.quantity, 0);

    // Render modal with orders and positions
}
```

**Modal Shows**:
- Symbol name and total P&L
- Number of shares traded
- All orders (buy/sell) chronologically
- All closed positions with P&L
- Largest win and loss

### Options Dashboard

**File**: `portfolio/static/js/filters.js`

Options uses **dropdown filters** to filter by symbol, not aggregated views:

```javascript
// Symbol filter dropdown
const symbolFilter = document.getElementById('closedSymbolFilter').value;

// Filter positions by symbol
const rows = document.querySelectorAll('.closed-positions-table tbody tr');
rows.forEach(row => {
    const symbol = row.dataset.symbol;
    const symbolMatch = !symbolFilter || symbol === symbolFilter;

    row.style.display = symbolMatch ? '' : 'none';
});
```

**No Aggregation** - Just filters the table to show only positions matching the selected symbol.

**Available Filters**:
- Symbol (dropdown populated from unique symbols)
- Strategy (call, put, iron_condor, etc.)
- Direction (debit, credit)
- Profit/Loss (profitable, unprofitable, all)
- Date range

### Futures Dashboard

**Similar to stocks** - Groups orders/positions by contract (display_symbol):

**File**: `futures/static/js/main.js`

```javascript
// Group by display_symbol (/ESH26, /NQH26, etc.)
const contractStats = {};
closedPositions.forEach(pos => {
    const symbol = pos.display_symbol;
    // ... similar grouping logic
});
```

**Stats Calculated**:
- Total P&L per contract
- Total P&L without fees
- Number of orders
- Total fees

## Data Flow for By-Symbol View

```
┌─────────────────────────────────────────────┐
│        Browser loads page                   │
└──────────────────┬──────────────────────────┘
                   │
                   v
         ┌─────────────────────┐
         │  Fetch main API     │
         │  /api/stocks        │
         │  /api/options       │
         │  /api/futures       │
         └──────────┬──────────┘
                    │
                    v
         ┌──────────────────────────┐
         │  JavaScript receives     │
         │  all positions/orders    │
         └──────────┬───────────────┘
                    │
                    v
         ┌──────────────────────────┐
         │  Group by symbol         │
         │  (client-side)           │
         │                          │
         │  for each position:      │
         │    add to symbolStats[]  │
         └──────────┬───────────────┘
                    │
                    v
         ┌──────────────────────────┐
         │  Calculate aggregates    │
         │  - total_pnl            │
         │  - num_trades           │
         │  - win_rate             │
         │  - avg_pnl_per_trade    │
         └──────────┬───────────────┘
                    │
                    v
         ┌──────────────────────────┐
         │  Render UI               │
         │  - Heatmap               │
         │  - Table                 │
         └──────────────────────────┘
```

**Key Point**: Zero additional API calls needed - all data already fetched.

## Testing

### Manual Testing

```bash
# Options
curl "http://localhost:3000/api/daily-pnl"
curl "http://localhost:3000/api/positions/date/2026-01-30"

# Stocks
curl "http://localhost:3002/api/daily-pnl?start_date=2026-01-01"
curl "http://localhost:3002/api/positions/date/2026-01-30"
curl "http://localhost:3002/api/daily-summary/2026-01-30"

# Futures
curl "http://localhost:3001/api/daily-pnl"
curl "http://localhost:3001/api/positions/date/2026-01-30"
curl "http://localhost:3001/api/daily-summary/2026-01-30"
```

### Testing with jq

```bash
# Get daily P&L and format nicely
curl -s "http://localhost:3000/api/daily-pnl" | jq '.daily_pnl'

# Get positions for a date
curl -s "http://localhost:3000/api/positions/date/2026-01-30" | jq '.positions[] | {symbol, net_credit, status}'

# Get futures summary
curl -s "http://localhost:3001/api/daily-summary/2026-01-30" | jq '.summary.totals'
```

### Testing By-Symbol View

Since by-symbol is client-side, test in browser:

1. Open dashboard in browser
2. Switch to "By Symbol" tab
3. Open browser console (F12)
4. Check `stocksData` or `optionsData` variable
5. Verify grouping logic:
```javascript
// In browser console
console.log(stocksData.closed_positions.length); // Total positions
const symbols = [...new Set(stocksData.closed_positions.map(p => p.symbol))];
console.log(symbols); // Unique symbols
```

---

**Last Updated**: 2026-01-31
**Reviewed Code**: portfolio/rh_web.py, stocks/stocks_web.py, futures/futures_web.py, database files, frontend JS files
**Documentation Status**: ✅ Verified against actual implementation
