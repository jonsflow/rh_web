"""
The account dimension.

Every order belongs to an account. Futures has always recorded which one;
options and stocks fetched without naming an account, so the broker returned the
primary one and the rows did not say so.

This adds the column and the plumbing. Rows already stored keep a null account:
they are not rewritten, and a null reads as "account unknown" rather than as any
particular account. Anything fetched from here on is stamped.

Nothing in this module calls a broker.
"""

import sqlite3
from typing import Dict, List, Optional

# Column added to the order and position tables. Futures already carries
# account_id from the futures API and keeps that name.
ACCOUNT_COLUMN = 'account_number'

# table -> database file, for the tables that gain the column
ACCOUNT_TABLES = {
    'options.db': ('option_orders', 'positions'),
    'stocks.db': ('stock_orders',),
}

# What each asset calls its account column
ACCOUNT_FIELD = {
    'options': 'account_number',
    'stocks': 'account_number',
    'futures': 'account_id',
}


def column_names(conn: sqlite3.Connection, table: str) -> List[str]:
    return [row[1] for row in conn.execute(f'PRAGMA table_info({table})')]


def ensure_account_column(db_path: str, table: str, column: str = ACCOUNT_COLUMN) -> bool:
    """Add the account column to a table if it is not already there.

    Returns True if it was added. Safe to call on every start: SQLite has no
    "add column if not exists", so the columns are read first.
    """
    conn = sqlite3.connect(db_path)
    try:
        if table not in _tables(conn):
            return False
        if column in column_names(conn, table):
            return False

        conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} TEXT')
        conn.execute(
            f'CREATE INDEX IF NOT EXISTS idx_{table}_{column} ON {table}({column})'
        )
        conn.commit()
        return True
    finally:
        conn.close()


def _tables(conn: sqlite3.Connection) -> List[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return [row[0] for row in rows]


def migrate(db_paths: Optional[Dict[str, str]] = None) -> Dict[str, bool]:
    """Give every order and position table its account column.

    Additive only: no row is read or rewritten, so this cannot change a figure
    already on screen.
    """
    paths = db_paths or {name: name for name in ACCOUNT_TABLES}
    added = {}
    for db_name, tables in ACCOUNT_TABLES.items():
        db_path = paths.get(db_name, db_name)
        for table in tables:
            added[f'{db_path}:{table}'] = ensure_account_column(db_path, table)
    return added


def accounts_in(db_path: str, table: str, column: str = ACCOUNT_COLUMN) -> List[str]:
    """Which accounts appear in a table's stored rows.

    Reads what is there, so the switcher can be built without asking the broker.
    Rows stored before the column existed are null and are left out.
    """
    conn = sqlite3.connect(db_path)
    try:
        if table not in _tables(conn) or column not in column_names(conn, table):
            return []
        rows = conn.execute(
            f'SELECT DISTINCT {column} FROM {table} '
            f'WHERE {column} IS NOT NULL AND {column} != "" ORDER BY {column}'
        )
        return [row[0] for row in rows]
    finally:
        conn.close()


def account_filter(account: Optional[str], column: str = ACCOUNT_COLUMN):
    """A WHERE fragment and its parameters for an optional account filter.

    No account selected means every account, which is what the dashboards
    returned before they knew about accounts.

    Returns (clause, params); clause is '' when nothing should be filtered.
    """
    if not account:
        return '', []
    return f'{column} = ?', [account]
