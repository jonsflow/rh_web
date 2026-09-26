"""
The account dimension.

An account is a selection, not a filter: one account's figures are the only
figures that mean anything, and a read without a selection is a bad request
rather than a request for all of them.

One account has a different identifier per asset -- options and stocks use its
account number, futures a separate UUID -- so the registry records that mapping
and resolving one is a lookup rather than a branch on asset type. The identifiers
are rows, so a fourth asset needs no schema change.

Populating this needs the broker (the account list, and the futures account id),
which is a live call and the user's to run. Everything here reads what is stored.
"""

from typing import Any, Dict, List, Optional, Tuple

DB_PATH = 'unified.db'

# One name, on every table, for every asset. What it holds is the broker's own
# identifier for the account; the column name does not vary.
ACCOUNT_COLUMN = 'account'

# The tables an account scopes
ACCOUNT_TABLES = ('orders', 'positions', 'journals')


def account_filter(account: Optional[str],
                   column: str = ACCOUNT_COLUMN) -> Tuple[str, List[Any]]:
    """A WHERE fragment and its parameters for an account.

    Returns ('', []) when there is nothing to scope by, so a caller can build a
    query without knowing whether an account was selected.
    """
    if not account:
        return '', []
    return f'{column} = ?', [account]


class AccountRegistry:
    """The accounts available to select, and each asset's name for them."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.init_database()

    def _connect(self):
        from unified.database import UnifiedDatabase

        return UnifiedDatabase(self.db_path).connect()

    def init_database(self) -> None:
        """Ask for the schema, which unified/database.py owns."""
        from unified.database import UnifiedDatabase

        UnifiedDatabase(self.db_path)

    # ---------- writing ----------

    def register(self, account_key: str, label: str = None,
                 identifiers: Dict[str, str] = None) -> Dict[str, Any]:
        """Record an account, or fill in an identifier discovered later.

        Called after a live refresh, which is where these identifiers come from.
        Anything left out keeps whatever is already stored, so learning the
        futures id later does not erase the account number or the label. A stored
        label is only absent until one is given, and reads fall back to the key.
        """
        conn = self._connect()
        try:
            conn.execute('''
                INSERT INTO accounts (account_key, label)
                VALUES (?, ?)
                ON CONFLICT(account_key) DO UPDATE SET
                    label = COALESCE(excluded.label, accounts.label),
                    updated_at = CURRENT_TIMESTAMP
            ''', (account_key, label))

            for asset_type, identifier in (identifiers or {}).items():
                if not identifier:
                    continue
                conn.execute('''
                    INSERT INTO account_identifiers (account_key, asset_type, identifier)
                    VALUES (?, ?, ?)
                    ON CONFLICT(account_key, asset_type) DO UPDATE SET
                        identifier = excluded.identifier,
                        updated_at = CURRENT_TIMESTAMP
                ''', (account_key, asset_type, identifier))

            conn.commit()
        finally:
            conn.close()

        return self.get(account_key)

    # ---------- reading ----------

    def get(self, account_key: str) -> Optional[Dict[str, Any]]:
        """One account with every identifier recorded for it."""
        conn = self._connect()
        try:
            row = conn.execute('SELECT * FROM accounts WHERE account_key = ?',
                               (account_key,)).fetchone()
            if not row:
                return None

            return {
                'account_key': row['account_key'],
                'label': row['label'] or row['account_key'],
                'identifiers': self._identifiers(conn, account_key),
            }
        finally:
            conn.close()

    def list(self) -> List[Dict[str, Any]]:
        """Every account that can be selected, with its per-asset identifiers."""
        conn = self._connect()
        try:
            rows = conn.execute(
                'SELECT * FROM accounts ORDER BY label, account_key'
            ).fetchall()

            return [{
                'account_key': row['account_key'],
                'label': row['label'] or row['account_key'],
                'identifiers': self._identifiers(conn, row['account_key']),
            } for row in rows]
        finally:
            conn.close()

    def identifier_for(self, account_key: str, asset_type: str) -> Optional[str]:
        """What this asset calls the selected account.

        None means no identifier is recorded for that asset yet, so there is
        nothing of its to show -- which is different from showing everything.
        """
        conn = self._connect()
        try:
            row = conn.execute(
                'SELECT identifier FROM account_identifiers '
                'WHERE account_key = ? AND asset_type = ?',
                (account_key, asset_type),
            ).fetchone()
            return row['identifier'] if row else None
        finally:
            conn.close()

    def key_for(self, identifier: str, asset_type: str) -> Optional[str]:
        """The account a stored row belongs to, from the identifier on it."""
        conn = self._connect()
        try:
            row = conn.execute(
                'SELECT account_key FROM account_identifiers '
                'WHERE asset_type = ? AND identifier = ?',
                (asset_type, identifier),
            ).fetchone()
            return row['account_key'] if row else None
        finally:
            conn.close()

    @staticmethod
    def _identifiers(conn, account_key: str) -> Dict[str, str]:
        rows = conn.execute(
            'SELECT asset_type, identifier FROM account_identifiers '
            'WHERE account_key = ? ORDER BY asset_type',
            (account_key,),
        )
        return {row['asset_type']: row['identifier'] for row in rows}
