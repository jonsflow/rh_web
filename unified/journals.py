"""
Trade journal storage.

Notes attached to a trading day, an order or a position -- the only table in the
unified database holding something typed by hand rather than fetched from a
broker. It lives in unified.db alongside the orders and positions the notes are
about, and names its account under the same column name they do.

A fresh connection per operation, so it is safe to use from Flask's threads.
"""

import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

JOURNAL_TYPES = ('daily', 'order', 'position')

# Fields a caller is allowed to change after an entry exists
UPDATABLE_FIELDS = ('notes', 'tags', 'date')


class JournalsDatabase:
    def __init__(self, db_path: str = "unified.db"):
        self.db_path = db_path
        self.init_database()

    def _connect(self):
        """A fresh connection, rows addressable by column name."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_database(self):
        """Make sure the table exists.

        The schema lives in unified/database.py, which owns every table in the
        file. This asks for it rather than declaring a second copy.
        """
        from unified.database import UnifiedDatabase

        UnifiedDatabase(self.db_path)

    # ---------- writing ----------

    def create(self, entry: Dict[str, Any]) -> int:
        """Store a new entry and return its id.

        `journal_type`, `date` and `notes` are required. `asset_type`,
        `account` and `reference_id` are optional: a daily note that
        spans assets or accounts simply leaves them unset.
        """
        journal_type = entry.get('journal_type')
        if journal_type not in JOURNAL_TYPES:
            raise ValueError(
                f"journal_type must be one of {JOURNAL_TYPES}, got {journal_type!r}"
            )

        date = (entry.get('date') or '').strip()
        if not date:
            raise ValueError('date is required')

        notes = (entry.get('notes') or '').strip()
        if not notes:
            raise ValueError('notes cannot be empty')

        now = datetime.now().isoformat()

        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO journals
            (journal_type, asset_type, account, reference_id, date, notes,
             tags, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            journal_type,
            entry.get('asset_type'),
            entry.get('account'),
            entry.get('reference_id'),
            date,
            notes,
            entry.get('tags'),
            now,
            now,
        ))
        journal_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return journal_id

    def update(self, journal_id: int, updates: Dict[str, Any]) -> int:
        """Change an entry's notes, tags or date. Returns rows affected."""
        clauses = []
        params: List[Any] = []

        for field in UPDATABLE_FIELDS:
            if field in updates:
                value = updates[field]
                if field == 'notes' and not (value or '').strip():
                    raise ValueError('notes cannot be empty')
                clauses.append(f'{field} = ?')
                params.append(value.strip() if isinstance(value, str) else value)

        if not clauses:
            return 0

        clauses.append('updated_at = ?')
        params.append(datetime.now().isoformat())
        params.append(journal_id)

        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute(f"UPDATE journals SET {', '.join(clauses)} WHERE id = ?", tuple(params))
        changed = cursor.rowcount
        conn.commit()
        conn.close()
        return changed

    def delete(self, journal_id: int) -> int:
        """Remove an entry. Returns rows affected."""
        conn = self._connect()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM journals WHERE id = ?', (journal_id,))
        changed = cursor.rowcount
        conn.commit()
        conn.close()
        return changed

    # ---------- reading ----------

    def get(self, journal_id: int) -> Optional[Dict[str, Any]]:
        """One entry, or None."""
        conn = self._connect()
        row = conn.execute('SELECT * FROM journals WHERE id = ?', (journal_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def find(
        self,
        date: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        journal_type: Optional[str] = None,
        asset_type: Optional[str] = None,
        account: Optional[str] = None,
        reference_id: Optional[str] = None,
        search: Optional[str] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Entries matching every filter given, newest first.

        Filters combine, so a dashboard can ask for one day's notes for one
        asset and one account without the caller composing SQL.
        """
        clauses = []
        params: List[Any] = []

        if date:
            clauses.append('date = ?')
            params.append(date)
        if start_date:
            clauses.append('date >= ?')
            params.append(start_date)
        if end_date:
            clauses.append('date <= ?')
            params.append(end_date)
        if journal_type:
            clauses.append('journal_type = ?')
            params.append(journal_type)
        if asset_type:
            clauses.append('asset_type = ?')
            params.append(asset_type)
        if account:
            clauses.append('account = ?')
            params.append(account)
        if reference_id:
            clauses.append('reference_id = ?')
            params.append(reference_id)
        if search:
            clauses.append('(notes LIKE ? OR tags LIKE ?)')
            params.extend([f'%{search}%', f'%{search}%'])

        query = 'SELECT * FROM journals'
        if clauses:
            query += ' WHERE ' + ' AND '.join(clauses)
        query += ' ORDER BY date DESC, created_at DESC'

        if limit is not None:
            query += ' LIMIT ? OFFSET ?'
            params.extend([limit, offset])

        conn = self._connect()
        rows = conn.execute(query, tuple(params)).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def count_by_date(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        asset_type: Optional[str] = None,
        account: Optional[str] = None,
    ) -> Dict[str, int]:
        """How many entries each date has, for marking days in the calendar."""
        clauses = []
        params: List[Any] = []

        if start_date:
            clauses.append('date >= ?')
            params.append(start_date)
        if end_date:
            clauses.append('date <= ?')
            params.append(end_date)
        if asset_type:
            clauses.append('asset_type = ?')
            params.append(asset_type)
        if account:
            clauses.append('account = ?')
            params.append(account)

        query = 'SELECT date, COUNT(*) AS count FROM journals'
        if clauses:
            query += ' WHERE ' + ' AND '.join(clauses)
        query += ' GROUP BY date'

        conn = self._connect()
        rows = conn.execute(query, tuple(params)).fetchall()
        conn.close()
        return {row['date']: row['count'] for row in rows}
