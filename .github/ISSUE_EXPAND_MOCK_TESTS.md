# Expand Mock Test Coverage for Risk Manager - Add Stop Loss & Take Profit Tests with Price Streaming

## Current State
We have basic monkeypatch mock test coverage for the risk manager (see `tests/test_basic.py` and `tests/test_accounts.py`), but we lack comprehensive acceptance tests for our core trading features.

## Problem
The stop loss and take profit features (`trailing_stop`, `take_profit`) require realistic price movement over time to test properly. Currently, we can only test static scenarios.

## Proposed Solution
Implement acceptance-level tests with mock price/option data streaming that:

1. **Mock Price Streaming**: Simulate realistic price movement sequences during test execution
2. **Test Stop Loss Triggers**: Verify positions are closed when price drops below stop loss threshold
3. **Test Take Profit Triggers**: Verify positions are closed when price reaches profit target
4. **Test Trailing Stop Logic**: Verify highest price tracking and trigger point recalculation as prices move
5. **Test Edge Cases**:
   - Rapid price swings across triggers
   - Gapping down through stop loss
   - Price oscillating near trigger points

## Technical Approach

### Option A: Mock Data Streaming (Recommended)
- Create a mock price stream generator that yields sequential prices
- Monkeypatch `r.get_option_market_data_by_id()` to return prices from the stream
- Each test calls the market price update function multiple times to simulate time passage
- No real-time requirements, fully deterministic

### Option B: Real Market Data Playback
- Use recorded historical price data from test fixtures
- Replay actual market data sequences
- More realistic but requires maintaining data files

### Option C: Hybrid Approach
- Mock for common scenarios
- Real data for edge case validation

## Test Scenarios to Cover

```python
def test_stop_loss_triggers():
    # Position opened at $2.00
    # Stop loss at 50% = $1.00
    # Price sequence: $2.00 → $1.50 → $1.20 → $0.95 (triggers)
    # Expected: Order submitted to close

def test_trailing_stop_follows_price():
    # Position opened at $2.00, trailing stop 20%
    # Price: $2.00 → $3.00 → $2.50 → $2.35 (triggers)
    # Expected: Trigger price updates with new highs, closes below trigger

def test_take_profit_at_target():
    # Position opened at $1.00
    # Take profit at 50% = $1.50
    # Price: $1.00 → $1.25 → $1.55 (triggers)
    # Expected: Order submitted to close

def test_rapid_price_swing():
    # Test gapping through multiple thresholds in one update
    # Price: $2.00 → $0.50 (gaps through stop loss)
    # Expected: Correct trigger detection despite gap

def test_price_oscillation_near_trigger():
    # Test bouncing around trigger points
    # Price: $1.10 → $0.95 → $1.05 → $0.92 (triggers)
    # Expected: Only triggers once at actual cross
```

## Files to Create/Modify

- `tests/conftest.py` - Add price stream fixtures
- `tests/fixtures/mock_prices.py` - Price stream generators
- `tests/test_risk_manager_acceptance.py` - New acceptance tests
- `tests/fixtures/` - Test data fixtures (order data, price sequences)

## Implementation Steps

1. Create mock price stream generator utility
2. Add monkeypatch fixture for market data streaming
3. Write test cases for each stop loss/take profit scenario
4. Validate trailing stop state transitions
5. Test error conditions (API failures during streaming)

## Dependencies
- `pytest` (already in use)
- `monkeypatch` fixture (pytest built-in)
- No external data sources required

## Success Criteria
- All stop loss/take profit scenarios covered
- Tests run in < 2 seconds (no real market data)
- 100% deterministic (same results every run)
- Can run in CI/CD without credentials

## Related Issues
- Related to normalized database approach (CLAUDE.md TODO)
- Improves test coverage metrics
- Enables confident refactoring of risk management logic
