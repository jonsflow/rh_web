"""
Unit tests for futures P&L helper functions.

These tests do not require authentication and can run in CI.
"""
import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def test_extract_futures_pnl_basic():
    """Test extracting P&L from a basic futures order structure."""
    try:
        from robin_stocks.robinhood.futures import extract_futures_pnl
    except ImportError:
        pytest.skip("robin_stocks futures module not available")

    # Mock order with nested P&L structure (as returned by Robinhood API)
    order = {
        'orderId': 'test-123',
        'realizedPnl': {
            'realizedPnl': {
                'amount': '-44.6',
                'currency': 'USD'
            },
            'realizedPnlWithoutFees': {
                'amount': '-41.5',
                'currency': 'USD'
            }
        },
        'totalFee': {
            'amount': '3.1',
            'currency': 'USD'
        },
        'totalCommission': {
            'amount': '2.5',
            'currency': 'USD'
        },
        'totalGoldSavings': {
            'amount': '1.25',
            'currency': 'USD'
        }
    }

    result = extract_futures_pnl(order)

    assert result['realized_pnl'] == -44.6
    assert result['realized_pnl_without_fees'] == -41.5
    assert result['total_fee'] == 3.1
    assert result['total_commission'] == 2.5
    assert result['total_gold_savings'] == 1.25


def test_extract_futures_pnl_empty_order():
    """Test extracting P&L from an empty/null order."""
    try:
        from robin_stocks.robinhood.futures import extract_futures_pnl
    except ImportError:
        pytest.skip("robin_stocks futures module not available")

    result = extract_futures_pnl(None)

    assert result['realized_pnl'] == 0.0
    assert result['realized_pnl_without_fees'] == 0.0
    assert result['total_fee'] == 0.0
    assert result['total_commission'] == 0.0
    assert result['total_gold_savings'] == 0.0


def test_extract_futures_pnl_cancelled_order():
    """Test extracting P&L from a cancelled order (no P&L data)."""
    try:
        from robin_stocks.robinhood.futures import extract_futures_pnl
    except ImportError:
        pytest.skip("robin_stocks futures module not available")

    order = {
        'orderId': 'test-456',
        'orderState': 'CANCELLED',
        # No realizedPnl, totalFee, etc.
    }

    result = extract_futures_pnl(order)

    assert result['realized_pnl'] == 0.0
    assert result['realized_pnl_without_fees'] == 0.0
    assert result['total_fee'] == 0.0
    assert result['total_commission'] == 0.0
    assert result['total_gold_savings'] == 0.0


def test_calculate_total_futures_pnl():
    """Test calculating aggregate P&L from multiple orders."""
    try:
        from robin_stocks.robinhood.futures import calculate_total_futures_pnl
    except ImportError:
        pytest.skip("robin_stocks futures module not available")

    orders = [
        {
            'realizedPnl': {
                'realizedPnl': {'amount': '100.00', 'currency': 'USD'},
                'realizedPnlWithoutFees': {'amount': '103.00', 'currency': 'USD'}
            },
            'totalFee': {'amount': '3.00', 'currency': 'USD'},
            'totalCommission': {'amount': '2.50', 'currency': 'USD'},
            'totalGoldSavings': {'amount': '1.25', 'currency': 'USD'}
        },
        {
            'realizedPnl': {
                'realizedPnl': {'amount': '-50.00', 'currency': 'USD'},
                'realizedPnlWithoutFees': {'amount': '-47.00', 'currency': 'USD'}
            },
            'totalFee': {'amount': '3.00', 'currency': 'USD'},
            'totalCommission': {'amount': '2.50', 'currency': 'USD'},
            'totalGoldSavings': {'amount': '1.25', 'currency': 'USD'}
        },
        {
            'orderState': 'CANCELLED'
            # No P&L data - should contribute 0
        }
    ]

    result = calculate_total_futures_pnl(orders)

    assert result['total_pnl'] == 50.0  # 100 + (-50) + 0
    assert result['total_pnl_without_fees'] == 56.0  # 103 + (-47) + 0
    assert result['total_fees'] == 6.0  # 3 + 3 + 0
    assert result['total_commissions'] == 5.0  # 2.5 + 2.5 + 0
    assert result['total_gold_savings'] == 2.5  # 1.25 + 1.25 + 0
    assert result['num_orders'] == 3


def test_calculate_total_futures_pnl_empty_list():
    """Test calculating P&L from empty order list."""
    try:
        from robin_stocks.robinhood.futures import calculate_total_futures_pnl
    except ImportError:
        pytest.skip("robin_stocks futures module not available")

    result = calculate_total_futures_pnl([])

    assert result['total_pnl'] == 0.0
    assert result['total_pnl_without_fees'] == 0.0
    assert result['total_fees'] == 0.0
    assert result['total_commissions'] == 0.0
    assert result['total_gold_savings'] == 0.0
    assert result['num_orders'] == 0


def test_extract_amount_helper():
    """Test the internal _extract_amount helper function."""
    try:
        from robin_stocks.robinhood.futures import _extract_amount
    except ImportError:
        pytest.skip("robin_stocks futures module not available")

    # Test nested amount object (Robinhood API format)
    assert _extract_amount({'amount': '123.45', 'currency': 'USD'}) == 123.45

    # Test string amount
    assert _extract_amount('100.50') == 100.50

    # Test numeric amount
    assert _extract_amount(50.25) == 50.25
    assert _extract_amount(100) == 100.0

    # Test None/empty
    assert _extract_amount(None) == 0.0
    assert _extract_amount('') == 0.0

    # Test invalid/unknown type
    assert _extract_amount({'invalid': 'structure'}) == 0.0
