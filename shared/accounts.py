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


# ---------------------------------------------------------------------------
# The accounts themselves
# ---------------------------------------------------------------------------
#
# One account is one account, but the broker names it differently per asset:
# options and stocks use its account_number, futures a separate UUID. Selecting
# an account and then switching asset only works if that mapping is recorded, so
# it is stored rather than guessed.
#
# Populating it needs the broker (the account list, and the futures account id),
# which is a live call and therefore the user's to run. Everything here reads
# what has been stored.


class AccountRegistry:
    """The accounts available to select, and each asset's name for them."""

    def __init__(self, db_path: str = "accounts.db"):
        self.db_path = db_path
        self.init_database()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_database(self):
        conn = self._connect()
        conn.execute('''
            CREATE TABLE IF NOT EXISTS accounts (
                account_key TEXT PRIMARY KEY,
                label TEXT,
                account_number TEXT,
                futures_account_id TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()

    def register(self, account_key: str, label: str = None,
                 account_number: str = None, futures_account_id: str = None):
        """Record an account, or fill in an identifier discovered later.

        Called after a live refresh, which is where these identifiers come from.
        Passing None for an identifier leaves whatever is already stored.
        """
        existing = self.get(account_key) or {}
        conn = self._connect()
        conn.execute('''
            INSERT INTO accounts (account_key, label, account_number, futures_account_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(account_key) DO UPDATE SET
                label = excluded.label,
                account_number = excluded.account_number,
                futures_account_id = excluded.futures_account_id,
                updated_at = CURRENT_TIMESTAMP
        ''', (
            account_key,
            label or existing.get('label') or account_key,
            account_number or existing.get('account_number'),
            futures_account_id or existing.get('futures_account_id'),
        ))
        conn.commit()
        conn.close()
        return self.get(account_key)

    def get(self, account_key: str) -> Optional[Dict[str, str]]:
        conn = self._connect()
        row = conn.execute('SELECT * FROM accounts WHERE account_key = ?',
                           (account_key,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def list(self) -> List[Dict[str, str]]:
        """Every account that can be selected, with its per-asset identifiers."""
        conn = self._connect()
        rows = conn.execute('SELECT * FROM accounts ORDER BY label, account_key').fetchall()
        conn.close()

        return [{
            'account_key': row['account_key'],
            'label': row['label'] or row['account_key'],
            'identifiers': {
                'options': row['account_number'],
                'stocks': row['account_number'],
                'futures': row['futures_account_id'],
            },
        } for row in rows]

    def identifier_for(self, account_key: str, asset_type: str) -> Optional[str]:
        """What this asset calls the selected account.

        None means this account has no identifier recorded for that asset yet,
        so there is nothing of its to show -- which is different from showing
        everything.
        """
        account = self.get(account_key)
        if not account:
            return None
        if asset_type == 'futures':
            return account.get('futures_account_id')
        return account.get('account_number')
