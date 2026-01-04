# Robinhood Futures API Discovery

**Date:** January 1, 2026
**Branch:** `feature/futures-api-discovery`
**Status:** Successfully Reverse Engineered ✅

---

## Overview

Robinhood launched futures trading in January 2025 through Robinhood Derivatives, LLC using CQG infrastructure. The futures API endpoints were undocumented and not included in the `robin_stocks` library. Through browser network traffic analysis, we successfully discovered the working API endpoints.

---

## Discovered Endpoints

### 1. Contract Lookup (Symbol → Contract Details)

**Endpoint:**
```
GET https://api.robinhood.com/arsenal/v1/futures/contracts/symbol/{SYMBOL}
```

**Example:**
```
GET https://api.robinhood.com/arsenal/v1/futures/contracts/symbol/ESH26
```

**Response:**
```json
{
  "result": {
    "id": "c60db22e-536d-43b4-9083-17717de8d217",
    "productId": "476e059e-79c2-4bd8-810a-af471f78abed",
    "symbol": "/ESH26:XCME",
    "displaySymbol": "/ESH26",
    "description": "E-mini Standard and Poor's 500 Stock Price Index Futures, Mar-26",
    "multiplier": "50",
    "expirationMmy": "202603",
    "expiration": "2026-03-20",
    "customerLastCloseDate": "2026-03-20",
    "tradability": "FUTURES_TRADABILITY_TRADABLE",
    "state": "FUTURES_STATE_ACTIVE",
    "settlementStartTime": "08:30",
    "firstTradeDate": "2024-05-01",
    "settlementDate": "2026-03-20"
  }
}
```

**Key Fields:**
- `id`: Contract/instrument ID (required for quotes)
- `symbol`: Full symbol with exchange (e.g., `/ESH26:XCME`)
- `displaySymbol`: Display-friendly symbol (e.g., `/ESH26`)
- `description`: Human-readable contract description
- `multiplier`: Contract size multiplier
- `expiration`: Contract expiration date
- `tradability`: Trading status
- `state`: Contract state (active, expired, etc.)

---

### 2. Futures Quotes (Real-time Market Data)

**Endpoint:**
```
GET https://api.robinhood.com/marketdata/futures/quotes/v1/?ids={CONTRACT_ID}
```

**Example:**
```
GET https://api.robinhood.com/marketdata/futures/quotes/v1/?ids=c60db22e-536d-43b4-9083-17717de8d217
```

**Response:**
```json
{
  "status": "SUCCESS",
  "data": [
    {
      "status": "SUCCESS",
      "data": {
        "ask_price": "6903.25",
        "ask_size": 9,
        "ask_venue_timestamp": "2026-01-01T19:53:09.159-05:00",
        "bid_price": "6903",
        "bid_size": 8,
        "bid_venue_timestamp": "2026-01-01T19:53:09.159-05:00",
        "last_trade_price": "6903",
        "last_trade_size": 1,
        "last_trade_venue_timestamp": "2026-01-01T19:53:02.906-05:00",
        "symbol": "/ESH26:XCME",
        "instrument_id": "c60db22e-536d-43b4-9083-17717de8d217",
        "state": "active",
        "updated_at": "2026-01-01T19:53:09.159-05:00",
        "out_of_band": false
      }
    }
  ]
}
```

**Key Fields:**
- `bid_price`, `bid_size`: Current bid
- `ask_price`, `ask_size`: Current ask
- `last_trade_price`, `last_trade_size`: Last trade execution
- `symbol`: Full contract symbol
- `state`: Market state (active, closed, etc.)
- `updated_at`: Timestamp of last update

---

### 3. Futures Orders (Historical Orders)

**Endpoint:**
```
GET https://api.robinhood.com/ceres/v1/accounts/{ACCOUNT_ID}/orders
```

**IMPORTANT**: Futures use a **separate account ID** from stocks/options. You must use the futures account ID, not your regular trading account ID.

**Required Parameters:**
- `contractType=OUTRIGHT` - Specifies futures contracts (vs EVENT_CONTRACT for prediction markets)
- `orderState` - Filter by order states (can specify multiple)

**Optional Parameters:**
- `pageSize` - Number of results per page (default/max: 100)

**Example:**
```
GET https://api.robinhood.com/ceres/v1/accounts/67648f71-bfff-4ca8-8189-d6f4aa95bcfa/orders?contractType=OUTRIGHT&orderState=FILLED&orderState=CANCELLED&pageSize=100
```

**Valid Order States:**
- `FILLED` - Completed orders
- `CANCELLED` - Cancelled orders
- `REJECTED` - Rejected orders
- `FAILED` - Failed orders
- `VOIDED` - Voided orders
- `PARTIALLY_FILLED_REST_CANCELLED` - Partially filled then cancelled
- `INACTIVE` - Inactive orders
- `ORDER_STATE_UNSPECIFIED` - Unspecified state

**Response:**
```json
{
  "results": [
    {
      "orderId": "685198a4-bf00-4f3c-aa5f-6d418de3659c",
      "accountId": "67648f71-bfff-4ca8-8189-d6f4aa95bcfa",
      "orderLegs": [
        {
          "id": "685198a4-a960-41a0-b95b-dba0c9f5b292",
          "legId": "A",
          "contractType": "OUTRIGHT",
          "contractId": "63204477-1715-45e6-893a-0c6a06397303",
          "ratioQuantity": 1,
          "orderSide": "SELL",
          "averagePrice": "2489"
        }
      ],
      "quantity": "5",
      "filledQuantity": "5",
      "orderType": "MARKET",
      "orderTrigger": "IMMEDIATE",
      "timeInForce": "GFD",
      "averagePrice": "2489",
      "orderState": "FILLED",
      "createdAt": "2025-06-17T16:32:36.006384Z",
      "updatedAt": "2025-06-17T16:32:36.621264Z",
      "orderExecutions": [
        {
          "id": "685198a4-15e8-4fef-ab7b-b47d3ae09998",
          "orderId": "685198a4-bf00-4f3c-aa5f-6d418de3659c",
          "accountId": "67648f71-bfff-4ca8-8189-d6f4aa95bcfa",
          "quantity": "-5",
          "pricePerContract": "2489",
          "eventTime": "2025-06-17T16:32:36.243Z",
          "masterId": "3812b208-9590-42cb-a998-c3ed34675924",
          "tradeDate": {
            "year": 2025,
            "month": 6,
            "day": 17
          }
        }
      ],
      "totalFee": {
        "amount": "3.1",
        "currency": "USD"
      },
      "fees": [
        {
          "feeTypeName": "Exchange Fees for Futures Trades",
          "feeAmount": {
            "amount": "0.1",
            "currency": "USD"
          }
        },
        {
          "feeTypeName": "NFA Trade Fee",
          "feeAmount": {
            "amount": "0.02",
            "currency": "USD"
          }
        },
        {
          "feeTypeName": "RHD Trade Commission",
          "feeAmount": {
            "amount": "0.5",
            "currency": "USD"
          }
        }
      ],
      "totalCommission": {
        "amount": "2.5",
        "currency": "USD"
      },
      "totalGoldSavings": {
        "amount": "1.25",
        "currency": "USD"
      },
      "positionEffectAtPlacementTime": "CLOSING",
      "realizedPnl": {
        "orderId": "",
        "realizedPnl": {
          "amount": "-44.6",
          "currency": "USD"
        },
        "realizedPnlWithoutFees": {
          "amount": "-41.5",
          "currency": "USD"
        }
      },
      "derivedState": "FILLED"
    }
  ],
  "next": "100"
}
```

**Key Fields:**
- `orderId`: Unique order identifier
- `accountId`: Futures account ID
- `orderLegs[]`: Array of order legs (for multi-leg strategies)
  - `contractId`: Futures contract instrument ID
  - `orderSide`: BUY or SELL
  - `averagePrice`: Execution price per contract
- `quantity`: Total number of contracts ordered
- `filledQuantity`: Number of contracts filled
- `orderState`: Current state (FILLED, CANCELLED, REJECTED, etc.)
- `orderType`: MARKET, LIMIT, STOP, etc.
- `timeInForce`: GFD (Good For Day), GTC, etc.
- `orderExecutions[]`: Array of execution details with timestamps
- `realizedPnl`: **Nested object** containing:
  - `realizedPnl.amount`: P&L with fees (string)
  - `realizedPnlWithoutFees.amount`: P&L before fees (string)
- `totalFee.amount`: Total fees (string)
- `totalCommission.amount`: Total commission (string)
- `totalGoldSavings.amount`: Robinhood Gold savings (string)
- `fees[]`: Detailed fee breakdown by type
- `positionEffectAtPlacementTime`: OPENING or CLOSING
- `createdAt`, `updatedAt`: ISO 8601 timestamps
- `next`: Pagination cursor (if more results exist)

**Important Notes:**
- All monetary amounts are returned as **nested objects** with `amount` and `currency` fields
- P&L data is **double-nested**: `order.realizedPnl.realizedPnl.amount`
- Default page size appears to be 100 orders
- ✅ **Pagination uses `cursor` parameter** (solved 1/3/2026)

**Pagination:**
```python
# Pagination using cursor parameter
all_orders = []
cursor = None

while True:
    url = f'https://api.robinhood.com/ceres/v1/accounts/{account_id}/orders?contractType=OUTRIGHT&orderState=FILLED&orderState=CANCELLED'
    if cursor:
        url += f'&cursor={cursor}'

    response = requests.get(url, headers=headers)
    data = response.json()

    results = data.get('results', [])
    if not results:
        break

    all_orders.extend(results)

    # Get next cursor
    cursor = data.get('next')
    if not cursor:
        break

print(f"Total orders retrieved: {len(all_orders)}")
```

---

## Required Headers

**Essential Headers:**
```
Authorization: Bearer {JWT_TOKEN}
Accept: */*
Rh-Contract-Protected: true
```

**Optional but Recommended:**
```
X-TimeZone-Id: America/Chicago
Accept-Encoding: gzip, deflate, br
Accept-Language: en-US,en;q=0.9
Origin: https://robinhood.com
Referer: https://robinhood.com/
```

---

## Authentication

### Current Status
- ✅ **Pickle File Auth**: Works perfectly for ALL futures endpoints!
- ✅ **Browser JWT Token**: Also works for futures API

### Requirements
The pickle file authentication (used by `robin_stocks` library) works for futures when you include the required header:

**Critical Header:**
```
Rh-Contract-Protected: true
```

Without this header, futures endpoints will return 401 Unauthorized. With it, standard pickle file authentication works perfectly for:
- Contract lookup (`/arsenal/v1/futures/contracts/`)
- Real-time quotes (`/marketdata/futures/quotes/`)
- Historical orders (`/ceres/v1/accounts/{id}/orders`)

### Account Separation
Futures trading uses a **separate account ID** from stocks/options. You'll need to:
1. Get your futures account ID (different from your regular trading account)
2. Use this account ID for orders and positions endpoints
3. Use the same authentication token with `Rh-Contract-Protected: true` header

---

## Tested Futures Symbols

| Symbol  | Name                          | Exchange | Contract ID                          | Status  |
|---------|-------------------------------|----------|--------------------------------------|---------|
| ESH26   | E-mini S&P 500 Mar-26        | CME      | c60db22e-536d-43b4-9083-17717de8d217 | ✅ Works |
| NQH26   | E-mini Nasdaq-100 Mar-26     | CME      | db985fd2-04ca-4fa6-8e4c-a4c049508de1 | ✅ Works |
| GCG26   | Gold Futures Feb-26          | COMEX    | 7890b890-3d98-438b-9ef8-32cb8023caf1 | ✅ Works |
| SILH26  | Micro Silver Futures Mar-26  | COMEX    | 365e3c43-661c-4ed6-a395-73847611a6d1 | ✅ Works |

---

## Complete Workflow Examples

### Example 1: Get Real-time Quote

```python
import requests
import pickle

# Load authentication from pickle file
with open('~/.tokens/robinhood.pickle', 'rb') as f:
    auth = pickle.load(f)

# Setup headers
headers = {
    'Authorization': f"{auth['token_type']} {auth['access_token']}",
    'Accept': '*/*',
    'Rh-Contract-Protected': 'true',  # REQUIRED!
}

# Step 1: Get contract details from symbol
symbol = 'ESH26'
contract_url = f'https://api.robinhood.com/arsenal/v1/futures/contracts/symbol/{symbol}'
contract_resp = requests.get(contract_url, headers=headers)
contract_data = contract_resp.json()
contract_id = contract_data['result']['id']

# Step 2: Get real-time quote
quote_url = f'https://api.robinhood.com/marketdata/futures/quotes/v1/?ids={contract_id}'
quote_resp = requests.get(quote_url, headers=headers)
quote_data = quote_resp.json()
quote = quote_data['data'][0]['data']

print(f"Symbol: {symbol}")
print(f"Last Price: ${quote['last_trade_price']}")
print(f"Bid: ${quote['bid_price']} x {quote['bid_size']}")
print(f"Ask: ${quote['ask_price']} x {quote['ask_size']}")
```

**Output:**
```
Symbol: ESH26
Last Price: $6907.5
Bid: $6907.25 x 19
Ask: $6907.75 x 24
```

### Example 2: Get Historical Orders

```python
import requests
import pickle

# Load authentication
with open('~/.tokens/robinhood.pickle', 'rb') as f:
    auth = pickle.load(f)

headers = {
    'Authorization': f"{auth['token_type']} {auth['access_token']}",
    'Accept': '*/*',
    'Rh-Contract-Protected': 'true',
}

# Your futures account ID (different from stock account!)
futures_account_id = '67648f71-bfff-4ca8-8189-d6f4aa95bcfa'

# Get all filled and cancelled orders
order_states = ['FILLED', 'CANCELLED', 'REJECTED', 'VOIDED']
state_params = '&'.join([f'orderState={s}' for s in order_states])
url = f'https://api.robinhood.com/ceres/v1/accounts/{futures_account_id}/orders?contractType=OUTRIGHT&{state_params}'

response = requests.get(url, headers=headers)
data = response.json()
orders = data.get('results', [])

# Helper to extract amount from nested structure
def get_amount(field):
    if isinstance(field, dict) and 'amount' in field:
        return float(field['amount'])
    return 0.0

# Calculate total P&L (note the double nesting!)
total_pnl = sum(
    get_amount(order.get('realizedPnl', {}).get('realizedPnl'))
    for order in orders
)
total_pnl_no_fees = sum(
    get_amount(order.get('realizedPnl', {}).get('realizedPnlWithoutFees'))
    for order in orders
)
total_fees = sum(get_amount(order.get('totalFee')) for order in orders)
total_commissions = sum(get_amount(order.get('totalCommission')) for order in orders)

print(f"Total Orders: {len(orders)}")
print(f"Total Realized P&L: ${total_pnl:,.2f}")
print(f"P&L Without Fees: ${total_pnl_no_fees:,.2f}")
print(f"Total Fees: ${total_fees:,.2f}")
print(f"Total Commissions: ${total_commissions:,.2f}")
```

---

## Endpoints NOT Found (404)

These endpoint patterns were tested but do NOT exist:

```
❌ https://api.robinhood.com/futures/
❌ https://api.robinhood.com/futures/orders/
❌ https://api.robinhood.com/futures/positions/
❌ https://api.robinhood.com/derivatives/orders/
❌ https://api.robinhood.com/derivatives/positions/
❌ https://api.robinhood.com/marketdata/futures/instruments/
❌ https://api.robinhood.com/instruments/futures/
❌ https://derivatives.robinhood.com/*
```

**Note:** Positions and orders endpoints for futures have not yet been discovered. They may:
- Not exist (futures data might be in regular `/orders/` and `/positions/`)
- Require a futures account to be visible
- Use a different URL pattern not yet tested

---

## Symbol Format

Futures symbols follow the format: `{ROOT}{MONTH_CODE}{YEAR}`

**Examples:**
- `ESH26` = E-mini S&P 500, March 2026
- `NQM26` = E-mini Nasdaq-100, June 2026
- `GCZ25` = Gold, December 2025

**Month Codes:**
- F = January
- G = February
- H = March
- J = April
- K = May
- M = June
- N = July
- Q = August
- U = September
- V = October
- X = November
- Z = December

**Common Roots:**
- `ES` = E-mini S&P 500
- `NQ` = E-mini Nasdaq-100
- `YM` = E-mini Dow Jones
- `RTY` = E-mini Russell 2000
- `GC` = Gold
- `SIL` = Micro Silver
- `CL` = Crude Oil
- `NG` = Natural Gas

---

## Known Limitations

1. ~~**Order Pagination**~~: ✅ **SOLVED** - Uses `cursor` parameter for pagination
2. ~~**Account ID Discovery**~~: ✅ **SOLVED** - Automatically discovers futures account via `accountType='FUTURES'` filter
3. ~~**Account Status**~~: ✅ **AVAILABLE** - Account status, number, Gold status via `/ceres/v1/accounts/`

None! All core functionality for futures trading data is available:
- ✅ Contract lookup by symbol
- ✅ Real-time quotes
- ✅ Historical orders with full pagination
- ✅ P&L extraction and calculation
- ✅ Account status information

**Optional endpoints not yet discovered** (not required for core functionality):
- Futures positions endpoint
- Historical price/candlestick data
- Contract search/listing
- Account balance/margin details

---

## Implementation Status

### ✅ Completed (robin_stocks v3.4.0+)
- [x] ✅ Discover futures orders endpoint
- [x] ✅ Verify pickle file authentication works with proper headers
- [x] ✅ **Solve pagination** - uses `cursor` parameter
- [x] ✅ Create `futures.py` module in robin_stocks
- [x] ✅ Implement `get_futures_contract(symbol)` function
- [x] ✅ Implement `get_futures_quote(symbol)` function
- [x] ✅ Implement `get_futures_quotes(symbols)` function for batch quotes
- [x] ✅ Implement `get_all_futures_orders(account_id)` function with pagination
- [x] ✅ Implement `get_filled_futures_orders(account_id)` function
- [x] ✅ Implement `extract_futures_pnl(order)` helper
- [x] ✅ Implement `calculate_total_futures_pnl(orders)` aggregation

### 🔄 In Progress / TODO
- [ ] Find futures positions endpoint (likely in ceres service)
- [ ] Find historical price data endpoint
- [ ] Discover contract search/listing endpoint
- [ ] Find method to programmatically get futures account ID

### 📋 Dashboard Development (rh_web)
- [ ] Create futures dashboard similar to options dashboard
- [ ] Display real-time futures quotes
- [ ] Show historical orders with P&L breakdown
- [ ] Show contract details and expiration dates
- [ ] Calculate aggregate P&L from orders
- [ ] Display positions if endpoint is found

---

## References

- **Robinhood Futures Announcement**: https://robinhood.com/us/en/about/futures/
- **CME Group Partnership**: https://www.cmegroup.com/media-room/press-releases/2025/1/29/
- **robin_stocks GitHub Issue #1612**: https://github.com/jmfernandes/robin_stocks/issues/1612
- **Unofficial Robinhood API Docs**: https://github.com/sanko/Robinhood

---

## Contributors

- Research & Discovery: Claude Code AI Assistant
- Browser Network Analysis: User
- Testing & Validation: Collaborative effort

---

**Last Updated:** January 1, 2026
