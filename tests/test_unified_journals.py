"""
Trade journals in the unified database.

The store is the one the dashboards already used, moved into unified.db and
naming its account under the same column every other table uses. These tests are
about that move: the table is the schema's, the column is `account`, and nothing
reads journals.db.
"""

import pytest

from unified.database import UnifiedDatabase
from unified.journals import JournalsDatabase


@pytest.fixture
def journals(tmp_path):
    return JournalsDatabase(str(tmp_path / 'unified.db'))


def test_journals_live_in_the_unified_database(journals, tmp_path):
    assert journals.db_path == str(tmp_path / 'unified.db')
    assert 'journals' in UnifiedDatabase(journals.db_path).tables()


def test_the_account_column_is_named_like_every_other_table(journals):
    columns = UnifiedDatabase(journals.db_path).columns('journals')

    assert 'account' in columns
    assert 'account_number' not in columns


def test_a_note_on_a_day_is_stored_and_read_back(journals):
    journal_id = journals.create({
        'journal_type': 'daily',
        'date': '2025-02-24',
        'notes': 'Sold the SLV puts too early.',
        'asset_type': 'options',
        'account': 'ACC1',
    })

    entry = journals.get(journal_id)
    assert entry['notes'] == 'Sold the SLV puts too early.'
    assert entry['account'] == 'ACC1'
    assert entry['asset_type'] == 'options'


def test_a_note_can_span_assets_and_accounts(journals):
    """A daily note need not belong to one asset or one account."""
    journal_id = journals.create({
        'journal_type': 'daily', 'date': '2025-02-24', 'notes': 'Choppy open.',
    })

    entry = journals.get(journal_id)
    assert entry['asset_type'] is None
    assert entry['account'] is None


def test_notes_are_found_by_account(journals):
    journals.create({'journal_type': 'daily', 'date': '2025-02-24',
                     'notes': 'one', 'account': 'ACC1'})
    journals.create({'journal_type': 'daily', 'date': '2025-02-24',
                     'notes': 'two', 'account': 'ACC2'})

    assert len(journals.find(account='ACC1')) == 1
    assert len(journals.find()) == 2


def test_a_note_can_be_changed(journals):
    journal_id = journals.create({'journal_type': 'order', 'date': '2025-02-24',
                                  'notes': 'first', 'reference_id': 'o1'})

    assert journals.update(journal_id, {'notes': 'second'}) == 1
    assert journals.get(journal_id)['notes'] == 'second'


def test_a_note_needs_a_type_a_date_and_something_written(journals):
    with pytest.raises(ValueError):
        journals.create({'journal_type': 'invented', 'date': '2025-02-24', 'notes': 'x'})
    with pytest.raises(ValueError):
        journals.create({'journal_type': 'daily', 'date': '', 'notes': 'x'})
    with pytest.raises(ValueError):
        journals.create({'journal_type': 'daily', 'date': '2025-02-24', 'notes': '   '})


def test_counts_by_date_are_scoped_by_account(journals):
    journals.create({'journal_type': 'daily', 'date': '2025-02-24',
                     'notes': 'a', 'account': 'ACC1'})
    journals.create({'journal_type': 'daily', 'date': '2025-02-24',
                     'notes': 'b', 'account': 'ACC1'})
    journals.create({'journal_type': 'daily', 'date': '2025-02-25',
                     'notes': 'c', 'account': 'ACC2'})

    assert journals.count_by_date(account='ACC1') == {'2025-02-24': 2}
