"""
The unified schema.

Two things are worth holding still: the schema is one shape for every asset, and
creating it cannot reach the three original databases. Those three are the
control -- they show the figures a unified answer is checked against -- so a test
that they are untouched is the point of this file as much as the columns are.
"""

import os
import sqlite3

import pytest

from unified.database import ASSET_TYPES, UnifiedDatabase

ORIGINALS = ('options.db', 'stocks.db', 'futures.db')

# The names every asset reports a figure under. No asset keeps its own name for
# one of these: that is what the schema is for.
CANONICAL = ('asset_type', 'account', 'symbol', 'quantity', 'pnl', 'pnl_no_fees', 'fees')


@pytest.fixture
def db(tmp_path):
    return UnifiedDatabase(str(tmp_path / 'unified.db'))


def test_the_schema_is_orders_positions_journals_and_the_accounts(db):
    assert db.tables() == ['account_identifiers', 'accounts', 'journals',
                           'orders', 'positions']


@pytest.mark.parametrize('table', ['orders', 'positions'])
def test_every_row_names_its_asset_and_reports_canonical_figures(db, table):
    columns = db.columns(table)
    for name in CANONICAL:
        assert name in columns, f'{table} has no {name} column'


def test_the_figures_that_used_to_differ_per_asset_are_gone(db):
    """net_credit, realized_pnl and realized_pnl_without_fees were three names
    for one figure. The unified schema calls it pnl."""
    stale = {'net_credit', 'realized_pnl', 'realized_pnl_without_fees',
             'premium', 'total_amount', 'cost', 'buy_date', 'sell_date',
             'display_symbol', 'account_number', 'account_id', 'contract_id',
             'last_transaction_at'}
    for table in ('orders', 'positions'):
        assert not stale & set(db.columns(table))


def test_journals_move_across_keyed_by_asset_and_account(db):
    columns = db.columns('journals')
    assert {'journal_type', 'asset_type', 'account', 'reference_id',
            'date', 'notes', 'tags'} <= set(columns)


def test_an_order_is_unique_per_asset_not_globally(db):
    """Two assets may use the same broker id; one asset may not repeat one."""
    conn = db.connect()
    conn.execute("INSERT INTO orders (asset_type, order_id) VALUES ('options', 'ABC')")
    conn.execute("INSERT INTO orders (asset_type, order_id) VALUES ('stocks', 'ABC')")
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO orders (asset_type, order_id) VALUES ('options', 'ABC')")
    conn.close()


def test_a_position_is_unique_per_asset_not_globally(db):
    conn = db.connect()
    conn.execute("INSERT INTO positions (asset_type, position_key) VALUES ('options', 'K')")
    conn.execute("INSERT INTO positions (asset_type, position_key) VALUES ('futures', 'K')")
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO positions (asset_type, position_key) VALUES ('options', 'K')")
    conn.close()


def test_a_multi_leg_strike_survives(db):
    """Options store a spread's strikes as one string, so strike_price is text."""
    conn = db.connect()
    conn.execute("INSERT INTO positions (asset_type, position_key, strike_price) "
                 "VALUES ('options', 'K', '17.00/20.00/39.00/36.00')")
    conn.commit()
    stored = conn.execute('SELECT strike_price FROM positions').fetchone()[0]
    conn.close()
    assert stored == '17.00/20.00/39.00/36.00'


def test_creating_the_schema_twice_changes_nothing(db):
    conn = db.connect()
    conn.execute("INSERT INTO orders (asset_type, order_id) VALUES ('options', 'ABC')")
    conn.commit()
    conn.close()

    db.init_database()

    assert db.row_counts() == {'options': 1}


def test_row_counts_are_per_asset(db):
    conn = db.connect()
    for asset in ASSET_TYPES:
        conn.execute('INSERT INTO orders (asset_type, order_id) VALUES (?, ?)',
                     (asset, f'{asset}-1'))
    conn.commit()
    conn.close()

    assert db.row_counts() == {asset: 1 for asset in ASSET_TYPES}


def test_the_schema_module_cannot_reach_the_original_databases(tmp_path):
    """The three originals are the control. Creating the unified schema does not
    open them, let alone write to them."""
    before = {name: os.stat(name).st_mtime_ns for name in ORIGINALS if os.path.exists(name)}

    UnifiedDatabase(str(tmp_path / 'unified.db'))

    after = {name: os.stat(name).st_mtime_ns for name in before}
    assert after == before


def test_no_original_database_is_named_in_the_module():
    import unified.database as module

    with open(module.__file__.replace('.pyc', '.py')) as handle:
        source = handle.read()

    for name in ORIGINALS:
        assert f"'{name}'" not in source and f'"{name}"' not in source


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------

ORDER = {'order_id': 'o1', 'symbol': 'SLV', 'account': 'ACC1', 'state': 'filled',
         'created_at': '2025-02-24T15:00:00Z', 'executed_at': '2025-02-24T15:00:01Z',
         'trade_date': '2025-02-24', 'quantity': 2, 'pnl': 12.5}


def test_rows_land_under_canonical_names(db):
    assert db.insert_orders('options', [ORDER]) == 1

    stored, = db.orders('options')
    assert stored['asset_type'] == 'options'
    assert stored['order_id'] == 'o1'
    assert stored['pnl'] == 12.5


def test_a_row_carries_its_asset_type_even_if_the_caller_left_it_out(db):
    db.insert_orders('futures', [{'order_id': 'f1', 'state': 'filled'}])
    assert db.row_counts() == {'futures': 1}


def test_a_key_the_table_has_no_column_for_is_dropped(db):
    """A model may carry more than the table does; the write must not fail on it."""
    assert db.insert_orders('options', [dict(ORDER, invented='nonsense')]) == 1


def test_inserting_the_same_order_twice_leaves_one_row(db):
    db.insert_orders('options', [ORDER])

    assert db.insert_orders('options', [ORDER]) == 0
    assert len(db.orders('options')) == 1


def test_two_assets_may_share_a_broker_id(db):
    db.insert_orders('options', [ORDER])
    db.insert_orders('stocks', [ORDER])

    assert db.row_counts() == {'options': 1, 'stocks': 1}


def test_orders_are_returned_in_fill_order(db):
    """FIFO pairs in the order fills happened, not the order they were placed."""
    db.insert_orders('stocks', [
        {'order_id': 'late-placed', 'symbol': 'AAPL', 'state': 'filled',
         'created_at': '2025-02-24T09:00:00Z', 'executed_at': '2025-02-24T15:00:00Z'},
        {'order_id': 'early-filled', 'symbol': 'AAPL', 'state': 'filled',
         'created_at': '2025-02-24T10:00:00Z', 'executed_at': '2025-02-24T10:00:05Z'},
    ])

    assert [row['order_id'] for row in db.orders('stocks')] == ['early-filled',
                                                               'late-placed']


def test_only_filled_orders_are_paired(db):
    db.insert_orders('stocks', [dict(ORDER, order_id='x', state='cancelled')])

    assert db.orders('stocks') == []
    assert db.orders('stocks', state=None)


def test_orders_can_be_scoped_to_one_account(db):
    db.insert_orders('options', [ORDER, dict(ORDER, order_id='o2', account='ACC2')])

    assert len(db.orders('options', account='ACC1')) == 1
    assert len(db.orders('options')) == 2


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------

POSITION = {'position_key': 'k1', 'symbol': 'SLV', 'account': 'ACC1',
            'status': 'closed', 'pnl': 170.0, 'open_date': '2025-02-01'}


def test_a_rebuilt_position_replaces_the_one_before_it(db):
    """The same orders always produce the same position, with newer figures."""
    db.insert_positions('options', [POSITION])
    db.insert_positions('options', [dict(POSITION, pnl=200.0)])

    stored, = db.positions('options')
    assert stored['pnl'] == 200.0


def test_clearing_one_assets_positions_leaves_the_others(db):
    db.insert_positions('options', [POSITION])
    db.insert_positions('futures', [dict(POSITION, position_key='f1')])

    assert db.clear_positions('options') == 1
    assert db.positions('options') == []
    assert len(db.positions('futures')) == 1


def test_positions_can_be_scoped_by_status(db):
    db.insert_positions('options', [POSITION,
                                    dict(POSITION, position_key='k2', status='open')])

    assert len(db.positions('options', status='open')) == 1


# ---------------------------------------------------------------------------
# The watermark
# ---------------------------------------------------------------------------

def test_an_empty_table_has_no_watermark(db):
    assert db.watermark('options') is None


def test_the_watermark_is_the_latest_order_for_that_asset(db):
    db.insert_orders('options', [ORDER, dict(ORDER, order_id='o2',
                                             created_at='2025-03-01T00:00:00Z')])
    db.insert_orders('stocks', [dict(ORDER, created_at='2024-01-01T00:00:00Z')])

    assert db.watermark('options') == '2025-03-01T00:00:00Z'
    assert db.watermark('stocks') == '2024-01-01T00:00:00Z'


def test_the_watermark_is_per_account(db):
    """Otherwise a second account's first fetch starts from the first
    account's latest order and skips everything older."""
    db.insert_orders('options', [ORDER])

    assert db.watermark('options', account='ACC1') == '2025-02-24T15:00:00Z'
    assert db.watermark('options', account='ACC2') is None


def test_the_accounts_in_an_assets_orders_are_reported(db):
    db.insert_orders('options', [ORDER, dict(ORDER, order_id='o2', account='ACC2'),
                                 dict(ORDER, order_id='o3', account=None)])

    assert db.accounts_for('options') == ['ACC1', 'ACC2']
