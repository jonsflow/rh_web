"""
Trade journal: storage and routes.

Every test runs against a temporary database, so nothing here touches
journals.db or any broker.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from shared.journals import JournalsDatabase
from shared.journals_api import journals_blueprint


@pytest.fixture
def db(tmp_path):
    return JournalsDatabase(str(tmp_path / 'journals.db'))


@pytest.fixture
def client(tmp_path):
    """A bare Flask app with only the journal routes mounted."""
    from flask import Flask
    import shared.journals_api as api

    api._db = None  # the module caches one database per process
    app = Flask(__name__)
    app.register_blueprint(journals_blueprint(str(tmp_path / 'journals.db')))
    return app.test_client()


def entry(**overrides):
    base = {
        'journal_type': 'daily',
        'date': '2026-03-02',
        'notes': 'Sized down after two losses.',
    }
    base.update(overrides)
    return base


# ---------- storage ----------

def test_create_then_read_back(db):
    journal_id = db.create(entry(tags='discipline,sizing'))
    stored = db.get(journal_id)

    assert stored['notes'] == 'Sized down after two losses.'
    assert stored['journal_type'] == 'daily'
    assert stored['date'] == '2026-03-02'
    assert stored['tags'] == 'discipline,sizing'
    assert stored['created_at'] and stored['updated_at']


def test_an_entry_can_name_its_asset_account_and_trade(db):
    """The dimensions that make an entry findable from where it was written."""
    journal_id = db.create(entry(
        journal_type='position',
        asset_type='options',
        account_number='ACCT1',
        reference_id='pos-123',
    ))
    stored = db.get(journal_id)

    assert stored['asset_type'] == 'options'
    assert stored['account_number'] == 'ACCT1'
    assert stored['reference_id'] == 'pos-123'


def test_a_daily_note_needs_no_asset_or_account(db):
    """A note about the day itself spans every asset and account."""
    stored = db.get(db.create(entry()))

    assert stored['asset_type'] is None
    assert stored['account_number'] is None
    assert stored['reference_id'] is None


@pytest.mark.parametrize('bad', [
    {'journal_type': 'musing'},
    {'journal_type': None},
])
def test_an_unknown_type_is_refused(db, bad):
    with pytest.raises(ValueError, match='journal_type'):
        db.create(entry(**bad))


@pytest.mark.parametrize('bad', ['', '   ', None])
def test_an_empty_note_is_refused(db, bad):
    with pytest.raises(ValueError, match='notes'):
        db.create(entry(notes=bad))


def test_a_missing_date_is_refused(db):
    with pytest.raises(ValueError, match='date'):
        db.create(entry(date=''))


def test_editing_changes_the_note_and_stamps_it(db):
    journal_id = db.create(entry())
    before = db.get(journal_id)

    assert db.update(journal_id, {'notes': 'Revised: it was three losses.'}) == 1

    after = db.get(journal_id)
    assert after['notes'] == 'Revised: it was three losses.'
    assert after['created_at'] == before['created_at']
    assert after['updated_at'] >= before['updated_at']


def test_editing_cannot_blank_a_note(db):
    journal_id = db.create(entry())
    with pytest.raises(ValueError, match='notes'):
        db.update(journal_id, {'notes': '  '})
    assert db.get(journal_id)['notes'] == 'Sized down after two losses.'


def test_editing_ignores_fields_that_are_not_the_writers_to_change(db):
    """Type, asset, account and reference identify the entry; they are fixed."""
    journal_id = db.create(entry(asset_type='options'))

    db.update(journal_id, {'asset_type': 'futures', 'journal_type': 'order',
                           'notes': 'still options'})

    stored = db.get(journal_id)
    assert stored['asset_type'] == 'options'
    assert stored['journal_type'] == 'daily'
    assert stored['notes'] == 'still options'


def test_deleting_removes_it(db):
    journal_id = db.create(entry())
    assert db.delete(journal_id) == 1
    assert db.get(journal_id) is None
    assert db.delete(journal_id) == 0


# ---------- finding ----------

def test_filters_combine(db):
    db.create(entry(date='2026-03-02', asset_type='options', account_number='A', notes='one'))
    db.create(entry(date='2026-03-02', asset_type='futures', account_number='A', notes='two'))
    db.create(entry(date='2026-03-02', asset_type='options', account_number='B', notes='three'))
    db.create(entry(date='2026-03-09', asset_type='options', account_number='A', notes='four'))

    found = db.find(date='2026-03-02', asset_type='options', account_number='A')

    assert [e['notes'] for e in found] == ['one']


def test_a_day_returns_every_asset_when_none_is_named(db):
    db.create(entry(date='2026-03-02', asset_type='options', notes='one'))
    db.create(entry(date='2026-03-02', asset_type='futures', notes='two'))
    db.create(entry(date='2026-03-03', notes='other day'))

    assert len(db.find(date='2026-03-02')) == 2


def test_a_date_range_is_inclusive(db):
    for date in ('2026-03-01', '2026-03-05', '2026-03-10', '2026-03-15'):
        db.create(entry(date=date))

    found = db.find(start_date='2026-03-05', end_date='2026-03-10')
    assert sorted(e['date'] for e in found) == ['2026-03-05', '2026-03-10']


def test_entries_come_back_newest_first(db):
    db.create(entry(date='2026-03-01', notes='older'))
    db.create(entry(date='2026-03-09', notes='newer'))

    assert [e['notes'] for e in db.find()] == ['newer', 'older']


def test_search_covers_notes_and_tags(db):
    db.create(entry(notes='Held through the gap', tags='patience'))
    db.create(entry(notes='Cut it early', tags='gap,risk'))
    db.create(entry(notes='Nothing relevant', tags='misc'))

    assert len(db.find(search='gap')) == 2


def test_notes_for_one_trade_are_findable_from_that_trade(db):
    db.create(entry(journal_type='order', asset_type='futures', reference_id='ord-1', notes='a'))
    db.create(entry(journal_type='order', asset_type='futures', reference_id='ord-2', notes='b'))

    found = db.find(asset_type='futures', reference_id='ord-1')
    assert [e['notes'] for e in found] == ['a']


def test_counts_per_date_drive_the_calendar_markers(db):
    db.create(entry(date='2026-03-02', asset_type='options'))
    db.create(entry(date='2026-03-02', asset_type='options'))
    db.create(entry(date='2026-03-02', asset_type='futures'))
    db.create(entry(date='2026-03-09', asset_type='options'))

    assert db.count_by_date() == {'2026-03-02': 3, '2026-03-09': 1}
    assert db.count_by_date(asset_type='options') == {'2026-03-02': 2, '2026-03-09': 1}
    assert db.count_by_date(start_date='2026-03-05') == {'2026-03-09': 1}


def test_a_quote_in_a_note_is_stored_not_interpreted(db):
    """Notes are typed by hand; SQL must come from the query, not the text."""
    nasty = "'; DROP TABLE journals; --"
    journal_id = db.create(entry(notes=nasty))

    assert db.get(journal_id)['notes'] == nasty
    assert len(db.find()) == 1  # the table is still there


# ---------- routes ----------

def test_the_round_trip_through_the_api(client):
    created = client.post('/api/journals', json=entry(tags='sizing'))
    assert created.status_code == 201
    journal = created.get_json()['journal']
    assert journal['notes'] == 'Sized down after two losses.'

    listed = client.get('/api/journals?date=2026-03-02').get_json()
    assert listed['count'] == 1

    edited = client.put(f"/api/journals/{journal['id']}", json={'notes': 'Revised.'})
    assert edited.status_code == 200
    assert edited.get_json()['journal']['notes'] == 'Revised.'

    removed = client.delete(f"/api/journals/{journal['id']}")
    assert removed.status_code == 200
    assert client.get('/api/journals').get_json()['count'] == 0


def test_the_api_rejects_a_bad_entry_with_a_reason(client):
    response = client.post('/api/journals', json=entry(notes=''))
    assert response.status_code == 400
    assert 'notes' in response.get_json()['error']


def test_the_api_reports_a_missing_entry_rather_than_failing(client):
    assert client.get('/api/journals/999').status_code == 404
    assert client.put('/api/journals/999', json={'notes': 'x'}).status_code == 404
    assert client.delete('/api/journals/999').status_code == 404


def test_the_api_filters_by_asset_and_account(client):
    client.post('/api/journals', json=entry(asset_type='options', account_number='A', notes='one'))
    client.post('/api/journals', json=entry(asset_type='futures', account_number='A', notes='two'))
    client.post('/api/journals', json=entry(asset_type='options', account_number='B', notes='three'))

    both = client.get('/api/journals?asset_type=options&account=A').get_json()
    assert [e['notes'] for e in both['journals']] == ['one']


def test_the_api_serves_counts_for_the_calendar(client):
    client.post('/api/journals', json=entry(date='2026-03-02'))
    client.post('/api/journals', json=entry(date='2026-03-02'))
    client.post('/api/journals', json=entry(date='2026-03-09'))

    counts = client.get('/api/journals/count-by-date').get_json()['counts']
    assert counts == {'2026-03-02': 2, '2026-03-09': 1}


def test_every_dashboard_serves_the_journal_routes():
    """Journals are shared, so all three apps mount them."""
    for module in ('portfolio.rh_web', 'stocks.stocks_web', 'futures.futures_web'):
        app = __import__(module, fromlist=['app']).app
        rules = {str(rule) for rule in app.url_map.iter_rules()}
        assert '/api/journals' in rules, f'{module} does not serve journals'
        assert '/api/journals/count-by-date' in rules, f'{module} has no calendar counts'
