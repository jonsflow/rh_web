"""
The unified database: one schema for every asset type.

The three dashboards each grew their own schema, so the same figure has three
names -- realized P&L is `net_credit` for options, `pnl` for stocks,
`realized_pnl` for futures -- and the unified app needed a translation layer to
read them. One schema removes the translation rather than configuring it.

Two tables carry everything: `orders` is what the broker filled, `positions` is
the round trips paired out of those orders. Both name the asset on every row, so
one query answers for one asset or for all of them, and both name the account.

Nothing here reads or writes options.db, stocks.db or futures.db. Those three
remain the control: they show known-good figures to compare a unified answer
against, and this module cannot reach them.
"""

import sqlite3
from typing import Any, Dict, List, Optional

DB_PATH = 'unified.db'

# The asset types the schema is built for. A new one needs no schema change:
# it is a value in the asset_type column.
ASSET_TYPES = ('options', 'stocks', 'futures')

# One broker fill. Columns an asset has no use for stay null: futures has no
# strike, options no contract_id.
ORDERS_SCHEMA = '''
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_type TEXT NOT NULL,
        account TEXT,
        order_id TEXT NOT NULL,

        symbol TEXT,
        root_symbol TEXT,

        side TEXT,
        position_effect TEXT,
        quantity REAL,
        filled_quantity REAL,
        price REAL,
        gross_amount REAL,
        fees REAL DEFAULT 0,

        pnl REAL,
        pnl_no_fees REAL,

        state TEXT,
        created_at TEXT,
        -- When the fill happened, which is what pairing orders by. Each broker
        -- names it differently: options has only created_at, stocks reports
        -- last_transaction_at, futures an execution event time.
        executed_at TEXT,
        trade_date TEXT,

        expiration_date TEXT,
        strike_price TEXT,
        option_type TEXT,
        strategy TEXT,
        direction TEXT,
        -- Always a JSON array: an option order has one id per leg, a futures
        -- order one, an equity order none. One shape, so a reader never has to
        -- know which asset it is looking at.
        contract_ids TEXT,

        raw_data TEXT,
        fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,

        UNIQUE(asset_type, order_id)
    )
'''

# One round trip, paired out of the orders above. An open position has a null
# close_date and null close figures.
POSITIONS_SCHEMA = '''
    CREATE TABLE IF NOT EXISTS positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_type TEXT NOT NULL,
        account TEXT,
        position_key TEXT NOT NULL,

        symbol TEXT,
        root_symbol TEXT,

        open_date TEXT,
        close_date TEXT,
        quantity REAL,

        open_price REAL,
        close_price REAL,
        open_value REAL,
        close_value REAL,

        pnl REAL,
        pnl_no_fees REAL,
        fees REAL DEFAULT 0,

        status TEXT,

        expiration_date TEXT,
        strike_price TEXT,
        option_type TEXT,
        strategy TEXT,
        direction TEXT,
        contract_ids TEXT,

        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

        UNIQUE(asset_type, position_key)
    )
'''

# Journals already keyed themselves by asset and account, so they move across as
# they are, with account_number renamed to the column name every table here uses.
JOURNALS_SCHEMA = '''
    CREATE TABLE IF NOT EXISTS journals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        journal_type TEXT NOT NULL,
        asset_type TEXT,
        account TEXT,
        reference_id TEXT,
        date TEXT NOT NULL,
        notes TEXT NOT NULL,
        tags TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
'''

# Every read the dashboards make is scoped by asset, and then by a date, a
# symbol, a status or an account, so those are the indexes.
INDEXES = (
    'CREATE INDEX IF NOT EXISTS idx_orders_asset ON orders(asset_type)',
    'CREATE INDEX IF NOT EXISTS idx_orders_asset_account ON orders(asset_type, account)',
    'CREATE INDEX IF NOT EXISTS idx_orders_asset_trade_date ON orders(asset_type, trade_date)',
    'CREATE INDEX IF NOT EXISTS idx_orders_asset_symbol ON orders(asset_type, symbol)',
    'CREATE INDEX IF NOT EXISTS idx_orders_order_id ON orders(order_id)',

    'CREATE INDEX IF NOT EXISTS idx_positions_asset ON positions(asset_type)',
    'CREATE INDEX IF NOT EXISTS idx_positions_asset_account ON positions(asset_type, account)',
    'CREATE INDEX IF NOT EXISTS idx_positions_asset_status ON positions(asset_type, status)',
    'CREATE INDEX IF NOT EXISTS idx_positions_asset_close_date ON positions(asset_type, close_date)',
    'CREATE INDEX IF NOT EXISTS idx_positions_asset_symbol ON positions(asset_type, symbol)',

    'CREATE INDEX IF NOT EXISTS idx_journals_date ON journals(date)',
    'CREATE INDEX IF NOT EXISTS idx_journals_type ON journals(journal_type)',
    'CREATE INDEX IF NOT EXISTS idx_journals_asset ON journals(asset_type)',
    'CREATE INDEX IF NOT EXISTS idx_journals_account ON journals(account)',
    'CREATE INDEX IF NOT EXISTS idx_journals_reference ON journals(asset_type, reference_id)',

    'CREATE INDEX IF NOT EXISTS idx_identifiers_asset ON account_identifiers(asset_type, identifier)',
)

# One account, and the identifier each asset's API knows it by. Kept as rows
# rather than a column per asset, so a fourth asset needs no schema change and
# resolving an identifier is a lookup rather than a branch.
ACCOUNTS_SCHEMA = '''
    CREATE TABLE IF NOT EXISTS accounts (
        account_key TEXT PRIMARY KEY,
        label TEXT,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
'''

ACCOUNT_IDENTIFIERS_SCHEMA = '''
    CREATE TABLE IF NOT EXISTS account_identifiers (
        account_key TEXT NOT NULL,
        asset_type TEXT NOT NULL,
        identifier TEXT,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,

        PRIMARY KEY (account_key, asset_type)
    )
'''

TABLES = {
    'orders': ORDERS_SCHEMA,
    'positions': POSITIONS_SCHEMA,
    'journals': JOURNALS_SCHEMA,
    'accounts': ACCOUNTS_SCHEMA,
    'account_identifiers': ACCOUNT_IDENTIFIERS_SCHEMA,
}


class UnifiedDatabase:
    """The one database the unified app reads."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.init_database()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_database(self) -> None:
        """Create the schema. Safe to call on every start."""
        conn = self.connect()
        try:
            for schema in TABLES.values():
                conn.execute(schema)
            for index in INDEXES:
                conn.execute(index)
            conn.commit()
        finally:
            conn.close()

    # ---------- what is in there ----------

    def tables(self) -> List[str]:
        conn = self.connect()
        try:
            rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
            return [row[0] for row in rows]
        finally:
            conn.close()

    def columns(self, table: str) -> List[str]:
        conn = self.connect()
        try:
            return [row[1] for row in conn.execute(f'PRAGMA table_info({table})')]
        finally:
            conn.close()

    # ---------- writing ----------

    def insert_orders(self, asset_type: str, rows: List[Dict[str, Any]]) -> int:
        """Store orders, skipping any already held.

        An order the broker has already given us is not written again, so a sync
        that overlaps a previous one costs nothing and changes nothing.
        """
        return self._insert('orders', asset_type, rows, 'INSERT OR IGNORE')

    def insert_positions(self, asset_type: str, rows: List[Dict[str, Any]]) -> int:
        """Store positions, replacing any already held.

        Pairing is a rebuild rather than an accumulation: the same orders always
        produce the same positions, and a position's figures change as it is
        added to, so the newest answer wins.
        """
        return self._insert('positions', asset_type, rows, 'INSERT OR REPLACE')

    def _insert(self, table: str, asset_type: str, rows: List[Dict[str, Any]],
                verb: str) -> int:
        """Write rows whose keys are already this table's column names."""
        if not rows:
            return 0

        columns = self.columns(table)
        written = 0

        conn = self.connect()
        try:
            for row in rows:
                stored = {key: value for key, value in dict(row).items()
                          if key in columns}
                stored['asset_type'] = asset_type

                names = ', '.join(stored)
                placeholders = ', '.join('?' for _ in stored)
                cursor = conn.execute(
                    f'{verb} INTO {table} ({names}) VALUES ({placeholders})',
                    list(stored.values()),
                )
                written += cursor.rowcount
            conn.commit()
        finally:
            conn.close()

        return written

    def clear_positions(self, asset_type: str) -> int:
        """Drop one asset's positions, before its pairing is rebuilt.

        Scoped to the asset: rebuilding options must not disturb futures.
        """
        conn = self.connect()
        try:
            cursor = conn.execute('DELETE FROM positions WHERE asset_type = ?',
                                  (asset_type,))
            conn.commit()
            return cursor.rowcount
        finally:
            conn.close()

    # ---------- reading ----------

    def orders(self, asset_type: str, account: Optional[str] = None,
               state: Optional[str] = 'filled') -> List[Dict[str, Any]]:
        """The orders a service pairs, oldest fill first.

        Ordered by `executed_at`, which is when the fill happened rather than
        when the order was placed -- FIFO pairing depends on the difference.
        """
        query = 'SELECT * FROM orders WHERE asset_type = ?'
        params: List[Any] = [asset_type]

        if account:
            query += ' AND account = ?'
            params.append(account)
        if state:
            query += ' AND state = ?'
            params.append(state)

        query += ' ORDER BY account, symbol, executed_at, id'

        conn = self.connect()
        try:
            return [dict(row) for row in conn.execute(query, params)]
        finally:
            conn.close()

    def positions(self, asset_type: str, account: Optional[str] = None,
                  status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Stored positions for one asset, newest first."""
        query = 'SELECT * FROM positions WHERE asset_type = ?'
        params: List[Any] = [asset_type]

        if account:
            query += ' AND account = ?'
            params.append(account)
        if status:
            query += ' AND status = ?'
            params.append(status)

        query += ' ORDER BY open_date DESC, id DESC'

        conn = self.connect()
        try:
            return [dict(row) for row in conn.execute(query, params)]
        finally:
            conn.close()

    def watermark(self, asset_type: str, account: Optional[str] = None) -> Optional[str]:
        """The latest order already held, which is where the next fetch starts.

        Per asset and per account, both: one database holds every asset now, and
        without the account a first fetch for a second account would start from
        the first account's latest order and silently skip everything older.
        """
        query = 'SELECT MAX(created_at) FROM orders WHERE asset_type = ?'
        params: List[Any] = [asset_type]

        if account:
            query += ' AND account = ?'
            params.append(account)

        conn = self.connect()
        try:
            return conn.execute(query, params).fetchone()[0]
        finally:
            conn.close()

    def accounts_for(self, asset_type: str) -> List[str]:
        """Which accounts appear in one asset's stored orders."""
        conn = self.connect()
        try:
            rows = conn.execute(
                'SELECT DISTINCT account FROM orders '
                'WHERE asset_type = ? AND account IS NOT NULL AND account != "" '
                'ORDER BY account',
                (asset_type,),
            )
            return [row[0] for row in rows]
        finally:
            conn.close()

    def row_counts(self, table: str = 'orders') -> Dict[Optional[str], int]:
        """How many rows each asset has, for checking an import against the originals."""
        conn = self.connect()
        try:
            rows = conn.execute(
                f'SELECT asset_type, COUNT(*) FROM {table} GROUP BY asset_type'
            )
            return {row[0]: row[1] for row in rows}
        finally:
            conn.close()
