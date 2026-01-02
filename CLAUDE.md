# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Running the Application
```bash
python rh_web.py
```
The application runs on localhost:5000.

### Dependencies
```bash
pip install flask robin-stocks pandas
```

No package.json exists - this is a Python Flask application.

## Architecture

This repository contains two Flask-based web applications:
- Portfolio Dashboard (`rh_web.py`): dashboard for viewing/analyzing Robinhood options orders and positions.
- Risk Manager Web (`risk_manager_web.py`): multi-account long-options risk management with simulation/live order flows.

Below focuses on the Portfolio Dashboard. See `ARCHITECTURE.md` and `README.md` for Risk Manager Web.

### Modular Architecture (Refactored)

The portfolio dashboard has been refactored into a modern modular architecture combining the reliability of legacy code with modern component design.

**Backend (Service Layer Architecture):**
- **Flask Routes** (`rh_web.py`): API endpoints (`/api/options`, `/api/daily-pnl`, `/api/update`)
- **Service Layer**: 
  - `OptionService`: Main business orchestration and position management
  - `PnLCalculator`: Accurate P&L calculations with spread handling
  - `PositionClassifier`: Position status determination (open/closed/expired)
  - `DataRepository`: Pure data access layer for SQLite operations
- **Data Models**: `Position`, `OptionOrder`, `PnLSummary` classes
- **Database** (`OptionsDatabase`): Normalized SQLite with incremental data collection

**Frontend (Hybrid Modular + Legacy):**
- **New Modular Components**:
  - `services/api-service.js`: Centralized HTTP request handling
  - `components/summary-card.js`: Reusable summary statistics cards
  - `components/position-table.js`: Enhanced table rendering with sorting
- **Legacy Files** (maintained for compatibility):
  - `main.js`: Core functionality, enhanced with modular fallbacks
  - `rendering.js`: Updated to use new components where available
  - `calendar.js`: Calendar view functionality
  - `filters.js` & `sorting.js`: Advanced filtering and table sorting

**Templates:**
- `templates/index.html`: Main dashboard with hybrid script loading
- `templates/login.html`: Authentication page

**Architecture Benefits:**
- ✅ Zero-downtime migration with fallback safety
- ✅ Enhanced error handling and maintainability  
- ✅ Modular, testable component architecture
- ✅ Accurate P&L calculations (orphaned order filtering)
- ✅ Backward compatibility with existing functionality

### Data Flow

1. **Authentication**: Users log in with Robinhood credentials via `/login`
2. **Data Fetching**: 
   - Frontend: `ApiService.fetchOptionsData()` → `/api/options`
   - Backend: `OptionService.get_processed_data_for_api()`
3. **Data Processing**: 
   - Raw orders → `PositionClassifier` → Position objects
   - P&L calculations via `PnLCalculator` with orphaned order filtering
   - Normalized data storage in SQLite via `DataRepository`
4. **Frontend Rendering**: 
   - `SummaryPanel` renders P&L statistics using `SummaryCard` components
   - `PositionTable` handles enhanced table rendering with sorting
   - Legacy rendering functions provide fallback compatibility

### Key Data Processing Logic

**Modern Service Layer Approach:**
- **OptionService**: Orchestrates data processing through specialized services
- **DataRepository**: Handles SQLite operations with normalized schema
- **PnLCalculator**: Accurate calculations with orphaned order filtering
- **PositionClassifier**: Determines position status based on business rules
- **Incremental Data Collection**: Smart fetching to minimize API calls

**P&L Accuracy Improvements:**
- Filters out orphaned close orders (13 positions excluded)
- Handles debit/credit expiration logic correctly
- Accurate totals: Closed $7,241.62, Expired -$19,452.00, Total -$12,210.38

### Frontend Architecture (Portfolio Dashboard)

**Hybrid Modular + Legacy Design:**
- **Component-Based**: Reusable `SummaryCard` and `PositionTable` components
- **Service Layer**: Centralized API handling via `ApiService`
- **Fallback Safety**: Graceful degradation to legacy code if components fail
- **Progressive Enhancement**: Modern features layered on proven foundation
- **Tab-based Interface**: Switch between different views of option data
- **Enhanced Filtering**: Advanced capabilities including date ranges
- **Responsive Design**: Mobile and desktop compatible

### Security Considerations

- Robinhood credentials are only used for authentication, not stored
- Flask debug mode is enabled (should be disabled in production)
- No explicit session management or CSRF protection implemented

## Architecture Implementation Status

✅ **COMPLETED: Normalized Database Approach**

The application now uses a normalized SQLite database with incremental data collection, eliminating the inefficient API usage and duplicate data processing.

### Database Schema
```sql
-- Store individual option orders (from Robinhood API)
CREATE TABLE option_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    robinhood_id TEXT UNIQUE,  -- Unique identifier from RH API
    symbol TEXT,
    created_at TEXT,
    position_effect TEXT,  -- 'open' or 'close'
    expiration_date TEXT,
    strike_price TEXT,
    price REAL,
    quantity INTEGER,
    premium REAL,
    strategy TEXT,
    direction TEXT,
    option_type TEXT,
    option_ids TEXT,  -- JSON array of option IDs
    raw_data TEXT,    -- Full JSON for reference
    fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Store computed positions (paired open/close orders)
CREATE TABLE positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    option_key TEXT UNIQUE,  -- Unique identifier for position
    symbol TEXT,
    open_date TEXT,
    close_date TEXT,
    expiration_date TEXT,
    strike_price TEXT,
    quantity INTEGER,
    open_price REAL,
    close_price REAL,
    open_premium REAL,
    close_premium REAL,
    net_credit REAL,
    strategy TEXT,
    direction TEXT,
    option_type TEXT,
    status TEXT,  -- 'open', 'closed', 'expired'
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### Implementation Benefits ✅ ACHIEVED
- ✅ **Incremental Updates**: Only fetch new orders since last update
- ✅ **Efficient Storage**: No duplicate data across requests
- ✅ **Server-side Processing**: Complex JSON processing moved to service layer
- ✅ **Better Performance**: Pre-computed positions served instantly
- ✅ **Historical Tracking**: Full order history with position evolution
- ✅ **Accurate P&L**: Orphaned order filtering and proper expiration handling

### Smart Fetch Strategy ✅ IMPLEMENTED
- ✅ **Initial**: Configurable start date (Jan 1st by default)
- ✅ **Update**: Only fetch orders since last stored order with buffer
- ✅ **Deduplication**: Uses robinhood_id as unique constraint
- ✅ **Position Recomputation**: Service layer rebuilds positions efficiently

### Modular Frontend Migration ✅ COMPLETED
- ✅ **Zero-downtime**: Incremental migration with fallback safety
- ✅ **ApiService**: Centralized HTTP handling with error management
- ✅ **SummaryCard**: Reusable, configurable summary components
- ✅ **PositionTable**: Enhanced table rendering with sorting
- ✅ **Hybrid Architecture**: Modern components + legacy compatibility
