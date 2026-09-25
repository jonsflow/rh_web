"""
The account dimension.

Futures has always recorded its account. Options and stocks fetched without
naming one, so the broker answered for the primary account and the rows did not
say so. These tests cover the column, the filter, and the fact that rows already
stored are left exactly as they are.

Offline throughout: the fetchers' signatures are inspected, never called.
"""
import inspect
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared.accounts import (ACCOUNT_FIELD, accounts_in, account_filter,
                             ensure_account_column, migrate)


@pytest.fixture
def orders_db(tmp_path):
    """A table shaped like a stored orders table, before the column exists."""
    path = str(tmp_path / 'orders.db')
    conn = sqlite3.connect(path)
    conn.execute('CREATE TABLE stock_orders (id INTEGER PRIMARY KEY, symbol TEXT, quantity INTEGER)')
    conn.executemany('INSERT INTO stock_orders (symbol, quantity) VALUES (?, ?)',
                     [('AAPL', 10), ('TSLA', 5)])
    conn.commit()
    conn.close()
    return path


# ---------- the column ----------

def test_the_column_is_added_once(orders_db):
    assert ensure_account_column(orders_db, 'stock_orders') is True
    assert ensure_account_column(orders_db, 'stock_orders') is False, 'must be safe to re-run'

    conn = sqlite3.connect(orders_db)
    columns = [row[1] for row in conn.execute('PRAGMA table_info(stock_orders)')]
    conn.close()
    assert 'account_number' in columns


def test_adding_the_column_leaves_existing_rows_alone(orders_db):
    """No backfill: the rows are not rewritten and not guessed at."""
    ensure_account_column(orders_db, 'stock_orders')

    conn = sqlite3.connect(orders_db)
    rows = conn.execute('SELECT symbol, quantity, account_number FROM stock_orders '
                        'ORDER BY symbol').fetchall()
    conn.close()

    assert rows == [('AAPL', 10, None), ('TSLA', 5, None)]


def test_a_table_that_is_not_there_is_not_created(tmp_path):
    path = str(tmp_path / 'empty.db')
    sqlite3.connect(path).close()

    assert ensure_account_column(path, 'stock_orders') is False


def test_the_migration_covers_the_tables_that_need_it(tmp_path):
    """Every table holding orders or positions gains the column."""
    options = str(tmp_path / 'options.db')
    stocks = str(tmp_path / 'stocks.db')

    conn = sqlite3.connect(options)
    conn.execute('CREATE TABLE option_orders (id INTEGER PRIMARY KEY)')
    conn.execute('CREATE TABLE positions (id INTEGER PRIMARY KEY)')
    conn.commit()
    conn.close()

    conn = sqlite3.connect(stocks)
    conn.execute('CREATE TABLE stock_orders (id INTEGER PRIMARY KEY)')
    conn.commit()
    conn.close()

    added = migrate({'options.db': options, 'stocks.db': stocks})

    assert added == {
        f'{options}:option_orders': True,
        f'{options}:positions': True,
        f'{stocks}:stock_orders': True,
    }


# ---------- reading accounts back ----------

def test_accounts_come_from_the_rows_that_have_one(orders_db):
    ensure_account_column(orders_db, 'stock_orders')

    conn = sqlite3.connect(orders_db)
    conn.execute("INSERT INTO stock_orders (symbol, account_number) VALUES ('NVDA', 'ACCT2')")
    conn.execute("INSERT INTO stock_orders (symbol, account_number) VALUES ('AMD', 'ACCT1')")
    conn.execute("INSERT INTO stock_orders (symbol, account_number) VALUES ('MSFT', 'ACCT1')")
    conn.commit()
    conn.close()

    # Sorted, deduplicated, and the two null rows contribute nothing
    assert accounts_in(orders_db, 'stock_orders') == ['ACCT1', 'ACCT2']


def test_a_table_without_the_column_reports_no_accounts(orders_db):
    assert accounts_in(orders_db, 'stock_orders') == []


def test_no_account_selected_means_no_filter():
    """Which is how the dashboards behaved before they knew about accounts."""
    assert account_filter(None) == ('', [])
    assert account_filter('') == ('', [])

    clause, params = account_filter('ACCT1')
    assert clause == 'account_number = ?'
    assert params == ['ACCT1']


def test_each_asset_names_its_own_account_column():
    """Futures came with account_id from its API and keeps that name."""
    assert ACCOUNT_FIELD['options'] == 'account_number'
    assert ACCOUNT_FIELD['stocks'] == 'account_number'
    assert ACCOUNT_FIELD['futures'] == 'account_id'


# ---------- the fetchers ----------

def test_the_fetchers_can_be_told_which_account_to_fetch():
    """Without this argument the broker answers for the primary account."""
    from portfolio.data_fetcher import SmartDataFetcher
    from stocks.data_fetcher import StocksDataFetcher

    for fetcher, method in ((SmartDataFetcher, 'update_data'),
                            (SmartDataFetcher, 'fetch_option_orders'),
                            (StocksDataFetcher, 'update_data'),
                            (StocksDataFetcher, 'fetch_stock_orders')):
        signature = inspect.signature(getattr(fetcher, method))
        assert 'account_number' in signature.parameters, f'{fetcher.__name__}.{method}'
        assert signature.parameters['account_number'].default is None, (
            f'{fetcher.__name__}.{method} must default to the primary account'
        )


def test_the_broker_wrapper_accepts_the_account_we_pass():
    """The argument has to exist on the other side, or it is silently ignored."""
    import robin_stocks.robinhood as r

    for fn in (r.orders.get_all_option_orders, r.orders.get_all_stock_orders):
        assert 'account_number' in inspect.signature(fn).parameters, fn.__name__


def test_new_rows_are_stamped_with_the_account():
    """The insert names the column, so a fetched order records its account."""
    from portfolio.database import OptionsDatabase
    from stocks.database import StocksDatabase

    for db_class in (OptionsDatabase, StocksDatabase):
        signature = inspect.signature(db_class.insert_orders)
        assert 'account_number' in signature.parameters, db_class.__name__


# ---------- filtering the reads ----------

def test_reads_can_be_narrowed_to_one_account():
    from futures.database import FuturesDatabase
    from services.option_service import OptionService
    from stocks.database import StocksDatabase

    for callable_, name in (
        (FuturesDatabase.get_daily_pnl, 'futures daily P&L'),
        (FuturesDatabase.get_orders_by_trade_date, 'futures orders by date'),
        (StocksDatabase.get_orders_by_trade_date, 'stocks orders by date'),
        (OptionService.get_daily_pnl_summary, 'options daily P&L'),
        (StocksDatabase.get_daily_pnl, 'stocks daily P&L'),
        (StocksDatabase.get_closed_positions, 'stocks closed positions'),
    ):
        assert 'account' in inspect.signature(callable_).parameters, name


def test_filtering_futures_by_its_account_returns_the_same_figures():
    """Every stored futures order belongs to one account, so both agree."""
    from futures.database import FuturesDatabase

    db = FuturesDatabase('futures.db')
    accounts = accounts_in('futures.db', 'futures_orders', 'account_id')
    if not accounts:
        pytest.skip('no futures data stored locally')

    everything = db.get_daily_pnl()
    just_that_account = db.get_daily_pnl(account=accounts[0])

    assert just_that_account == everything


def test_filtering_by_an_account_with_no_rows_returns_nothing():
    """Not everything: an empty answer is the honest one."""
    from futures.database import FuturesDatabase

    assert FuturesDatabase('futures.db').get_daily_pnl(account='no-such-account') == {}


def test_rows_stored_before_the_column_belong_to_no_account():
    """They are not claimed for the primary account, because nothing recorded it."""
    from services.option_service import OptionService

    service = OptionService('options.db')
    everything = service.get_daily_pnl_summary()
    if not everything:
        pytest.skip('no options data stored locally')

    assert service.get_daily_pnl_summary(account='any-account') == {}, (
        'unstamped rows must not answer to an account'
    )


def test_stocks_pairs_buys_and_sells_within_one_account(tmp_path):
    """Two accounts' shares are not matched against each other.

    FIFO pairing decides which buy a sell closes. Pairing across accounts would
    invent trades that never happened and attribute P&L to the wrong one.
    """
    from stocks.database import StocksDatabase

    path = str(tmp_path / 'stocks.db')
    db = StocksDatabase(path)
    db.ensure_account_column()

    conn = sqlite3.connect(path)
    conn.executemany(
        'INSERT INTO stock_orders (order_id, symbol, side, quantity, average_price, '
        'total_amount, state, trade_date, last_transaction_at, account_number) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        [
            # Account A buys and sells: one real round trip, +$100
            ('1', 'AAPL', 'buy', 10, 100.0, 1000.0, 'filled', '2026-03-02', '2026-03-02T15:00:00Z', 'A'),
            ('2', 'AAPL', 'sell', 10, 110.0, 1100.0, 'filled', '2026-03-05', '2026-03-05T15:00:00Z', 'A'),
            # Account B only buys: nothing closed, no P&L
            ('3', 'AAPL', 'buy', 10, 200.0, 2000.0, 'filled', '2026-03-03', '2026-03-03T15:00:00Z', 'B'),
        ])
    conn.commit()
    conn.close()

    account_a = db.get_closed_positions('A')
    account_b = db.get_closed_positions('B')

    assert len(account_a) == 1
    assert account_a[0]['pnl'] == 100.0
    assert account_b == [], "account B's buy must not be closed by account A's sell"

    # And the daily view agrees
    assert db.get_daily_pnl(account='A')['2026-03-05']['pnl'] == 100.0
    assert db.get_daily_pnl(account='B') == {}
