"""
Turning orders into positions.

Three services, one interface: rows in, Position objects out. No database, no
broker -- the orders are built here, which is only possible because the services
hold no SQL.

The cases worth pinning are the ones where the three assets genuinely differ:
futures is told its P&L, stocks matches FIFO across partial fills, and options
has to decide whether a position closed, expired, or cannot be valued at all.
"""

import json

import pytest

from unified.models import Position
from unified.services import SERVICES, futures_service, option_service, stock_service


def order(**fields):
    """An order row, with the fields a service reads defaulted."""
    row = {
        'account': 'ACC1', 'symbol': 'SLV', 'root_symbol': 'SLV',
        'state': 'filled', 'position_effect': 'open',
        'quantity': 1, 'price': 1.0, 'gross_amount': 100.0, 'fees': 0.0,
        'created_at': '2025-02-20T15:00:00Z', 'executed_at': '2025-02-20T15:00:00Z',
        'trade_date': '2025-02-20', 'contract_ids': json.dumps(['c1']),
    }
    row.update(fields)
    return row


# ---------------------------------------------------------------------------
# The interface
# ---------------------------------------------------------------------------

def test_every_asset_has_a_service():
    assert sorted(SERVICES) == ['futures', 'options', 'stocks']


@pytest.mark.parametrize('asset_type', ['options', 'stocks', 'futures'])
def test_every_service_answers_build_positions(asset_type):
    positions = SERVICES[asset_type].build_positions([])

    assert positions == []


@pytest.mark.parametrize('asset_type', ['options', 'stocks', 'futures'])
def test_every_service_returns_positions_of_its_own_asset(asset_type):
    positions = SERVICES[asset_type].build_positions([order()])

    for position in positions:
        assert isinstance(position, Position)
        assert position.asset_type == asset_type


@pytest.mark.parametrize('asset_type', ['options', 'stocks', 'futures'])
def test_no_service_touches_a_database(asset_type):
    """A service that knows where rows live cannot be swapped out on its own."""
    import inspect

    source = inspect.getsource(SERVICES[asset_type])
    assert 'sqlite3' not in source
    assert 'SELECT' not in source and 'INSERT' not in source


# ---------------------------------------------------------------------------
# Futures
# ---------------------------------------------------------------------------

FUTURES_OPEN = order(symbol='ESH5', root_symbol='ES', position_effect='open',
                     quantity=2, price=6000.0, gross_amount=None)
FUTURES_CLOSE = order(symbol='ESH5', root_symbol='ES', position_effect='close',
                      quantity=2, price=6010.0, gross_amount=None,
                      created_at='2025-02-24T15:00:00Z',
                      pnl=-19.14, pnl_no_fees=-6.35, fees=12.79)


def test_futures_sums_the_brokers_realized_pnl():
    """Nothing is calculated: the broker reports both figures per order."""
    position, = futures_service.build_positions([FUTURES_OPEN, FUTURES_CLOSE])

    assert position.status == 'closed'
    assert position.pnl == -19.14
    assert position.pnl_no_fees == -6.35
    assert position.fees == 12.79


def test_a_futures_position_averages_its_fills():
    position, = futures_service.build_positions([
        order(position_effect='open', quantity=1, price=6000.0),
        order(position_effect='open', quantity=3, price=6100.0),
    ])

    assert position.quantity == 4
    assert position.open_price == 6075.0


def test_an_open_futures_position_has_no_close_figures():
    position, = futures_service.build_positions([FUTURES_OPEN])

    assert position.status == 'open'
    assert position.close_date is None
    assert position.pnl is None


def test_a_futures_close_with_no_open_is_recorded_as_orphaned():
    """Its entry predates the window, but the broker still reported the P&L."""
    position, = futures_service.build_positions([FUTURES_CLOSE])

    assert position.status == 'orphaned'
    assert position.open_date is None
    assert position.open_price is None
    # Known, because it was reported rather than inferred
    assert position.pnl == -19.14


def test_a_futures_position_key_is_stable_across_rebuilds():
    first, = futures_service.build_positions([FUTURES_OPEN, FUTURES_CLOSE])
    again, = futures_service.build_positions([FUTURES_OPEN, FUTURES_CLOSE])

    assert first.position_key == again.position_key


# ---------------------------------------------------------------------------
# Stocks
# ---------------------------------------------------------------------------

def test_stocks_pnl_is_proceeds_minus_cost():
    position, = stock_service.build_positions([
        order(symbol='AAPL', order_id='b1', position_effect='open',
              quantity=10, price=220.0, gross_amount=2200.0),
        order(symbol='AAPL', order_id='s1', position_effect='close',
              quantity=10, price=225.0, gross_amount=2250.0,
              trade_date='2025-02-24'),
    ])

    assert position.open_value == 2200.0
    assert position.close_value == 2250.0
    assert position.pnl_no_fees == 50.0
    assert position.status == 'closed'


def test_stocks_fifo_splits_a_buy_across_two_sells():
    positions = stock_service.build_positions([
        order(symbol='AAPL', order_id='b1', position_effect='open',
              quantity=10, price=220.0, gross_amount=2200.0),
        order(symbol='AAPL', order_id='s1', position_effect='close',
              quantity=4, price=225.0, gross_amount=900.0),
        order(symbol='AAPL', order_id='s2', position_effect='close',
              quantity=6, price=230.0, gross_amount=1380.0),
    ])

    assert [p.quantity for p in positions] == [4, 6]
    # The buy contributes its cost in proportion to what each sell used
    assert [p.open_value for p in positions] == [880.0, 1320.0]
    assert [p.pnl_no_fees for p in positions] == [20.0, 60.0]


def test_stocks_fifo_fills_one_sell_from_two_buys():
    positions = stock_service.build_positions([
        order(symbol='AAPL', order_id='b1', position_effect='open',
              quantity=4, price=220.0, gross_amount=880.0),
        order(symbol='AAPL', order_id='b2', position_effect='open',
              quantity=6, price=230.0, gross_amount=1380.0),
        order(symbol='AAPL', order_id='s1', position_effect='close',
              quantity=10, price=240.0, gross_amount=2400.0),
    ])

    assert [p.quantity for p in positions] == [4, 6]
    assert [p.open_value for p in positions] == [880.0, 1380.0]
    assert round(sum(p.pnl_no_fees for p in positions), 2) == 140.0


def test_the_oldest_buy_is_matched_first():
    closed, held = stock_service.build_positions([
        order(symbol='AAPL', order_id='older', position_effect='open',
              quantity=1, price=100.0, gross_amount=100.0),
        order(symbol='AAPL', order_id='newer', position_effect='open',
              quantity=1, price=200.0, gross_amount=200.0),
        order(symbol='AAPL', order_id='sell', position_effect='close',
              quantity=1, price=300.0, gross_amount=300.0),
    ])

    # The older buy is the one that was sold; the newer one is still held
    assert closed.position_key == 'older|sell'
    assert closed.open_value == 100.0
    assert (held.position_key, held.status) == ('newer|', 'open')


def test_a_stock_position_key_names_both_fills():
    position, = stock_service.build_positions([
        order(symbol='AAPL', order_id='b1', position_effect='open',
              quantity=1, gross_amount=100.0),
        order(symbol='AAPL', order_id='s1', position_effect='close',
              quantity=1, gross_amount=110.0),
    ])

    assert position.position_key == 'b1|s1'


def test_shares_still_held_are_an_open_position():
    """An incomplete position is still a position. It just has no P&L yet."""
    position, = stock_service.build_positions([
        order(symbol='AAPL', order_id='b1', position_effect='open',
              quantity=10, price=220.0, gross_amount=2200.0),
    ])

    assert position.status == 'open'
    assert position.quantity == 10
    assert position.open_value == 2200.0
    assert position.close_date is None
    assert position.pnl is None


def test_a_partly_sold_buy_is_two_positions():
    """What was sold is closed, what is left is held."""
    closed, held = stock_service.build_positions([
        order(symbol='AAPL', order_id='b1', position_effect='open',
              quantity=10, price=220.0, gross_amount=2200.0),
        order(symbol='AAPL', order_id='s1', position_effect='close',
              quantity=4, price=225.0, gross_amount=900.0, trade_date='2025-02-24'),
    ])

    assert (closed.status, closed.quantity, closed.pnl) == ('closed', 4, 20.0)
    assert (held.status, held.quantity, held.pnl) == ('open', 6, None)
    assert held.open_value == 1320.0


def test_a_sale_with_no_purchase_in_range_is_orphaned():
    """Bought before the window we fetched, so the cost basis is not here."""
    position, = stock_service.build_positions([
        order(symbol='AAPL', order_id='s9', position_effect='close',
              quantity=5, price=10.0, gross_amount=50.0),
    ])

    assert position.status == 'orphaned'
    assert position.open_date is None
    assert position.pnl is None
    assert position.close_value == 50.0


def test_an_open_and_an_orphaned_position_have_distinct_keys():
    positions = stock_service.build_positions([
        order(symbol='AAPL', order_id='b1', position_effect='open',
              quantity=1, gross_amount=100.0),
        order(symbol='MSFT', order_id='s9', position_effect='close',
              quantity=1, gross_amount=50.0),
    ])

    assert sorted(p.position_key for p in positions) == ['b1|', '|s9']


# ---------------------------------------------------------------------------
# Neither service crosses an account
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('service', [stock_service, futures_service, option_service])
def test_pairing_never_crosses_an_account(service):
    """One account's shares cannot close another account's position, so the two
    orders become an open position and an orphaned one rather than a round trip."""
    positions = service.build_positions([
        order(account='ACC1', order_id='b1', position_effect='open',
              quantity=1, gross_amount=100.0, expiration_date='2099-01-01'),
        order(account='ACC2', order_id='s1', position_effect='close',
              quantity=1, gross_amount=200.0, expiration_date='2099-01-01'),
    ])

    assert len(positions) == 2
    assert {p.status for p in positions} == {'open', 'orphaned'}


@pytest.mark.parametrize('asset_type', ['options', 'stocks', 'futures'])
def test_an_incomplete_position_reports_no_pnl_of_its_own(asset_type):
    """Every asset records what it could not pair, with a null P&L rather than a
    guessed one -- except futures, which was told the figure."""
    positions = SERVICES[asset_type].build_positions([
        order(order_id='b1', position_effect='open', quantity=1,
              gross_amount=100.0, expiration_date='2099-01-01'),
    ])

    assert [p.status for p in positions] == ['open']
    assert positions[0].pnl is None


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------

OPTION_OPEN = order(position_effect='open', direction='credit', quantity=2,
                    price=0.85, gross_amount=170.0, expiration_date='2099-01-01',
                    strike_price='29.00', option_type='put', strategy='short_put')


def test_an_option_closed_by_orders_is_worth_the_price_it_moved():
    """Times the quantity, times a hundred shares a contract."""
    position, = option_service.build_positions([
        order(position_effect='open', direction='debit', quantity=2, price=1.00,
              gross_amount=200.0, expiration_date='2099-01-01'),
        order(position_effect='close', direction='debit', quantity=2, price=1.50,
              gross_amount=300.0, expiration_date='2099-01-01',
              created_at='2025-02-24T15:00:00Z'),
    ])

    assert position.status == 'closed'
    assert position.pnl_no_fees == 100.0


def test_a_credit_position_profits_when_the_price_falls():
    """It was sold to open, so the sign is the other way round."""
    position, = option_service.build_positions([
        order(position_effect='open', direction='credit', quantity=1, price=1.00,
              gross_amount=100.0, expiration_date='2099-01-01'),
        order(position_effect='close', direction='credit', quantity=1, price=0.40,
              gross_amount=40.0, expiration_date='2099-01-01',
              created_at='2025-02-24T15:00:00Z'),
    ])

    assert position.pnl_no_fees == 60.0


def test_an_expired_credit_position_keeps_its_premium():
    position, = option_service.build_positions([
        order(position_effect='open', direction='credit', quantity=1,
              gross_amount=170.0, expiration_date='2025-01-01'),
    ])

    assert position.status == 'expired'
    assert position.pnl_no_fees == 170.0
    assert position.close_date == '2025-01-01'
    assert position.close_price == 0.0


def test_an_expired_debit_position_loses_what_it_paid():
    position, = option_service.build_positions([
        order(position_effect='open', direction='debit', quantity=1,
              gross_amount=170.0, expiration_date='2025-01-01'),
    ])

    assert position.status == 'expired'
    assert position.pnl_no_fees == -170.0


def test_an_option_not_yet_expired_is_still_open():
    position, = option_service.build_positions([OPTION_OPEN])

    assert position.status == 'open'
    assert position.pnl is None


def test_an_orphaned_close_reports_no_pnl():
    """Its opening order predates the data, so any figure would be invented."""
    position, = option_service.build_positions([
        order(position_effect='close', direction='credit', quantity=1,
              gross_amount=90.0, expiration_date='2099-01-01'),
    ])

    assert position.status == 'orphaned'
    assert position.pnl is None
    assert position.pnl_no_fees is None


def test_a_spread_produces_no_position():
    """Valuing one at expiry needs to know which strikes finished in the money."""
    assert option_service.build_positions([
        order(position_effect='open', strategy='call_debit_spread'),
    ]) == []
    assert option_service.is_spread('call_debit_spread')
    assert not option_service.is_spread('short_put')


def test_options_fees_come_off_the_pnl():
    """The two figures differ by the fees, which options now records."""
    position, = option_service.build_positions([
        order(position_effect='open', direction='credit', quantity=1, price=1.00,
              gross_amount=100.0, fees=0.04, expiration_date='2099-01-01'),
        order(position_effect='close', direction='credit', quantity=1, price=0.40,
              gross_amount=40.0, fees=0.08, expiration_date='2099-01-01',
              created_at='2025-02-24T15:00:00Z'),
    ])

    assert position.pnl_no_fees == 60.0
    assert position.fees == 0.12
    assert position.pnl == 59.88


def test_two_contracts_on_one_symbol_are_two_positions():
    positions = option_service.build_positions([
        order(position_effect='open', contract_ids=json.dumps(['c1']),
              strike_price='29.00', expiration_date='2099-01-01'),
        order(position_effect='open', contract_ids=json.dumps(['c2']),
              strike_price='30.00', expiration_date='2099-01-01'),
    ])

    assert len(positions) == 2
