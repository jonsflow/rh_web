"""
The account registry.

One account, several names: options and stocks use its account number, futures a
separate UUID. The identifiers are rows rather than a column each, so resolving
one is a lookup and a fourth asset needs no schema change.
"""

import pytest

from unified.accounts import AccountRegistry, account_filter


@pytest.fixture
def registry(tmp_path):
    return AccountRegistry(str(tmp_path / 'unified.db'))


def test_an_account_is_recorded_with_every_identifier(registry):
    registry.register('primary', 'Standard', {
        'options': 'ACC1', 'stocks': 'ACC1', 'futures': 'uuid-9',
    })

    account = registry.get('primary')
    assert account['label'] == 'Standard'
    assert account['identifiers'] == {'futures': 'uuid-9', 'options': 'ACC1',
                                      'stocks': 'ACC1'}


def test_an_identifier_learned_later_does_not_erase_the_others(registry):
    """The futures id comes from a different broker call than the account number."""
    registry.register('primary', 'Standard', {'options': 'ACC1'})
    registry.register('primary', identifiers={'futures': 'uuid-9'})

    account = registry.get('primary')
    assert account['label'] == 'Standard'
    assert account['identifiers'] == {'futures': 'uuid-9', 'options': 'ACC1'}


def test_an_identifier_can_be_corrected(registry):
    registry.register('primary', identifiers={'futures': 'uuid-old'})
    registry.register('primary', identifiers={'futures': 'uuid-new'})

    assert registry.identifier_for('primary', 'futures') == 'uuid-new'


def test_an_account_with_no_label_reads_as_its_key(registry):
    registry.register('roth', identifiers={'options': 'ACC2'})
    assert registry.get('roth')['label'] == 'roth'


def test_an_asset_with_no_identifier_resolves_to_nothing(registry):
    """Which is different from resolving to every account."""
    registry.register('primary', 'Standard', {'options': 'ACC1'})

    assert registry.identifier_for('primary', 'futures') is None


def test_an_unknown_account_resolves_to_nothing(registry):
    assert registry.get('nobody') is None
    assert registry.identifier_for('nobody', 'options') is None


def test_a_stored_row_resolves_back_to_its_account(registry):
    """Rows carry the broker's identifier, so reading one back needs the reverse."""
    registry.register('primary', 'Standard', {'options': 'ACC1', 'futures': 'uuid-9'})

    assert registry.key_for('uuid-9', 'futures') == 'primary'
    assert registry.key_for('ACC1', 'options') == 'primary'
    assert registry.key_for('ACC1', 'futures') is None


def test_accounts_are_listed_by_label(registry):
    registry.register('b', 'Alpha', {'options': 'A'})
    registry.register('a', 'Beta', {'options': 'B'})

    assert [a['label'] for a in registry.list()] == ['Alpha', 'Beta']


def test_a_fourth_asset_needs_no_schema_change(registry):
    """The whole point of identifiers being rows."""
    registry.register('primary', 'Standard', {'crypto': 'wallet-1'})

    assert registry.identifier_for('primary', 'crypto') == 'wallet-1'


def test_no_account_selected_filters_nothing(registry):
    assert account_filter(None) == ('', [])
    assert account_filter('ACC1') == ('account = ?', ['ACC1'])


def test_the_registry_lives_in_the_unified_database(registry, tmp_path):
    """Not in an accounts.db of its own, and not in anyone else's file."""
    from unified.database import UnifiedDatabase

    assert registry.db_path == str(tmp_path / 'unified.db')
    assert 'accounts' in UnifiedDatabase(registry.db_path).tables()
