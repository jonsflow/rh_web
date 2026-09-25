"""
The unified app must answer with what the standalone dashboards answer.

It serves /api/<asset_type>/... from the same fetchers and services the three
dashboards use, so every response here is compared against the dashboard that
owns that asset. Anything that differs is a regression, not a design choice.

Offline: only the read paths are exercised, and those read SQLite. The update
route is checked for its shape, never called.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# asset type -> (standalone module, its path for the same thing)
STANDALONE = {
    'options': 'portfolio.rh_web',
    'stocks': 'stocks.stocks_web',
    'futures': 'futures.futures_web',
}

ASSETS = sorted(STANDALONE)


@pytest.fixture(scope='module')
def unified():
    from unified.unified_web import app
    return app.test_client()


def standalone(asset_type):
    return __import__(STANDALONE[asset_type], fromlist=['app']).app.test_client()


# ---------- the asset index ----------

def test_the_app_lists_the_assets_it_serves(unified):
    payload = unified.get('/api/assets').get_json()

    assert payload['success']
    assert sorted(a['asset_type'] for a in payload['assets']) == ASSETS
    for asset in payload['assets']:
        assert asset['label'], f"{asset['asset_type']} has no label for the switcher"


def test_the_index_says_which_endpoints_each_asset_supports(unified):
    """The page builds its views from this, so it must be accurate."""
    assets = {a['asset_type']: a for a in unified.get('/api/assets').get_json()['assets']}

    assert assets['stocks']['all_trading_dates'] is True
    assert assets['futures']['all_trading_dates'] is False
    assert assets['options']['daily_summary'] is False
    assert assets['futures']['daily_summary'] is True


# ---------- parity with the standalone dashboards ----------
#
# The unified app answers for one selected account. A standalone dashboard shows
# whatever it fetched, which was the primary account, unlabelled. So parity holds
# for an asset whose rows record their account -- futures -- and for the others it
# holds once they have been refreshed with an account selected. Until then their
# rows belong to no account, and this app says so rather than claiming them.


def _futures_account(unified, registered):
    accounts = {a['account_key']: a for a in unified.get('/api/accounts').get_json()['accounts']}
    return accounts['ACCT1']['identifiers']['futures']


def test_futures_daily_pnl_matches_its_standalone_dashboard(unified, registered):
    if not _futures_account(unified, registered):
        pytest.skip('no futures account recorded locally')

    mine = unified.get('/api/futures/daily-pnl?account=ACCT1')
    theirs = standalone('futures').get('/api/daily-pnl')

    assert mine.status_code == theirs.status_code == 200
    assert mine.get_json()['daily_pnl'] == theirs.get_json()['daily_pnl']


def test_futures_daily_pnl_honours_a_date_range_the_same_way(unified, registered):
    if not _futures_account(unified, registered):
        pytest.skip('no futures account recorded locally')

    query = 'start_date=2026-01-01&end_date=2026-03-31'
    mine = unified.get(f'/api/futures/daily-pnl?account=ACCT1&{query}').get_json()
    theirs = standalone('futures').get(f'/api/daily-pnl?{query}').get_json()

    assert mine['daily_pnl'] == theirs['daily_pnl']


def test_a_futures_days_detail_matches_its_standalone_dashboard(unified, registered):
    if not _futures_account(unified, registered):
        pytest.skip('no futures account recorded locally')

    days = unified.get('/api/futures/daily-pnl?account=ACCT1').get_json()['daily_pnl']
    if not days:
        pytest.skip('no futures data stored locally')

    date = max(days, key=lambda d: days[d].get('count', 0))

    mine = unified.get(f'/api/futures/positions/date/{date}?account=ACCT1').get_json()
    theirs = standalone('futures').get(f'/api/positions/date/{date}').get_json()

    assert mine['orders'] == theirs['orders']
    assert mine['date'] == theirs['date'] == date


def test_futures_stored_data_matches_its_standalone_dashboard(unified, registered):
    if not _futures_account(unified, registered):
        pytest.skip('no futures account recorded locally')

    mine = unified.get('/api/futures/data?account=ACCT1').get_json()
    theirs = standalone('futures').get('/api/futures').get_json()

    for key in ('open_positions', 'closed_positions', 'all_orders'):
        assert mine.get(key) == theirs.get(key), f'futures {key} differs'


def test_a_futures_daily_summary_matches_its_standalone_dashboard(unified, registered):
    if not _futures_account(unified, registered):
        pytest.skip('no futures account recorded locally')

    days = unified.get('/api/futures/daily-pnl?account=ACCT1').get_json()['daily_pnl']
    date = max(days, key=lambda d: days[d].get('count', 0))

    mine = unified.get(f'/api/futures/daily-summary/{date}?account=ACCT1').get_json()
    theirs = standalone('futures').get(f'/api/daily-summary/{date}').get_json()

    assert mine['summary'] == theirs['summary']


def test_trading_dates_match_the_stocks_dashboard(unified, registered):
    """Dates are not account-scoped in storage yet, so these still agree."""
    mine = unified.get('/api/stocks/all-trading-dates?account=ACCT1').get_json()
    theirs = standalone('stocks').get('/api/all-trading-dates').get_json()

    assert mine['dates'] == theirs['dates']


@pytest.mark.parametrize('asset_type', ['options', 'stocks'])
def test_assets_whose_rows_predate_the_account_show_none_of_them(unified, registered, asset_type):
    """The honest answer while no row records an account.

    These rows came from the primary account, but nothing recorded that, so no
    account can claim them. Refreshing with an account selected is what fills
    this in; nothing here guesses.
    """
    days = unified.get(f'/api/{asset_type}/daily-pnl?account=ACCT1').get_json()['daily_pnl']
    assert days == {}

    # And the standalone dashboard still shows them, unchanged
    theirs = standalone(asset_type).get('/api/daily-pnl').get_json()['daily_pnl']
    assert len(theirs) > 0


# ---------- the route surface ----------

def test_an_unknown_asset_is_refused_rather_than_guessed(unified, registered):
    for path in ('/api/crypto/data?account=ACCT1', '/api/crypto/daily-pnl?account=ACCT1',
                 '/api/crypto/positions/date/2026-03-02?account=ACCT1'):
        response = unified.get(path)
        assert response.status_code == 404, path
        assert 'crypto' in response.get_json()['error']


def test_an_endpoint_an_asset_does_not_serve_says_so(unified, registered):
    """Rather than erroring inside a handler that has nothing to call."""
    assert unified.get('/api/options/daily-summary/2026-03-02?account=ACCT1').status_code == 404
    assert unified.get('/api/futures/all-trading-dates?account=ACCT1').status_code == 404


@pytest.mark.parametrize('asset_type', ['options', 'stocks'])
def test_every_asset_serves_the_same_route_surface(unified, registered, asset_type):
    """One set of routes covers all three; that is the point of the app.

    Futures is checked separately because its account identifier depends on what
    is stored locally.
    """
    for path in (f'/api/{asset_type}/data?account=ACCT1',
                 f'/api/{asset_type}/daily-pnl?account=ACCT1',
                 f'/api/{asset_type}/positions/date/2026-03-02?account=ACCT1'):
        assert unified.get(path).status_code == 200, path


def test_the_update_route_exists_for_every_asset_without_being_called():
    """Updating hits the broker, so this checks the rule, not the response."""
    from unified.unified_web import app

    rules = {str(r): r for r in app.url_map.iter_rules()}
    update = rules.get('/api/<asset_type>/update')

    assert update is not None
    assert 'POST' in update.methods
    assert 'GET' not in update.methods, 'refreshing must not happen on a page load'


def test_the_journal_is_served_here_too(unified):
    # Journals are not account-scoped reads; the route needs no selection
    assert unified.get('/api/journals').status_code == 200


def test_the_standalone_dashboards_are_untouched():
    """This app is built alongside them, not in place of them."""
    for asset_type, module in STANDALONE.items():
        client = standalone(asset_type)
        assert client.get('/').status_code == 200, f'{module} no longer renders'
        assert client.get('/api/daily-pnl').status_code == 200, f'{module} lost its routes'


# ---------- the account dimension ----------
#
# An account is a selection, not a filter. One account's figures are the only
# figures that mean anything, so there is no request for every account and no
# total across them.


@pytest.fixture
def registered(tmp_path):
    """A registry holding one account with identifiers for every asset."""
    import unified.unified_web as web
    from shared.accounts import AccountRegistry, accounts_in

    original = web._registry
    registry = AccountRegistry(str(tmp_path / 'accounts.db'))

    futures_ids = accounts_in('futures.db', 'futures_orders', 'account_id')
    registry.register('ACCT1', label='Standard (...CCT1)', account_number='ACCT1',
                      futures_account_id=futures_ids[0] if futures_ids else None)
    registry.register('OPTONLY', label='Options only', account_number='OPTONLY')

    web._registry = registry
    yield registry
    web._registry = original


def test_the_app_lists_the_accounts_that_can_be_selected(unified, registered):
    payload = unified.get('/api/accounts').get_json()

    assert payload['success']
    keys = [a['account_key'] for a in payload['accounts']]
    assert sorted(keys) == ['ACCT1', 'OPTONLY']

    for account in payload['accounts']:
        assert account['label'], 'the switcher needs something to show'
        # One account, named differently per asset
        assert sorted(account['identifiers']) == ASSETS


def test_one_account_carries_a_different_identifier_per_asset(unified, registered):
    """Options and stocks use the account number, futures its own UUID."""
    accounts = {a['account_key']: a for a in unified.get('/api/accounts').get_json()['accounts']}
    identifiers = accounts['ACCT1']['identifiers']

    assert identifiers['options'] == identifiers['stocks'] == 'ACCT1'
    if identifiers['futures'] is not None:
        assert identifiers['futures'] != 'ACCT1', 'futures is named separately'


@pytest.mark.parametrize('asset_type', ASSETS)
def test_a_read_without_an_account_is_a_bad_request(unified, registered, asset_type):
    """Not a total across accounts, and not everything: a request for nothing."""
    for path in (f'/api/{asset_type}/data',
                 f'/api/{asset_type}/daily-pnl',
                 f'/api/{asset_type}/positions/date/2026-03-02'):
        response = unified.get(path)
        assert response.status_code == 400, path
        assert 'account' in response.get_json()['error'].lower()


def test_the_bad_request_says_which_accounts_there_are(unified, registered):
    """So the page can recover rather than only reporting a failure."""
    payload = unified.get('/api/options/daily-pnl').get_json()
    assert [a['account_key'] for a in payload['accounts']] == ['OPTONLY', 'ACCT1'] or \
           sorted(a['account_key'] for a in payload['accounts']) == ['ACCT1', 'OPTONLY']


def test_an_account_with_no_identifier_for_an_asset_has_nothing_to_show(unified, registered):
    """Different from showing everything, and different from showing zero."""
    response = unified.get('/api/futures/daily-pnl?account=OPTONLY')

    assert response.status_code == 404
    assert 'futures' in response.get_json()['error']


def test_an_unregistered_account_is_refused(unified, registered):
    response = unified.get('/api/options/daily-pnl?account=NOPE')
    assert response.status_code == 404


def test_reads_are_scoped_to_the_selected_account(unified, registered):
    """Futures records its account, so this compares against the real rows."""
    accounts = {a['account_key']: a for a in unified.get('/api/accounts').get_json()['accounts']}
    futures_id = accounts['ACCT1']['identifiers']['futures']
    if not futures_id:
        pytest.skip('no futures account recorded locally')

    from futures.database import FuturesDatabase

    mine = unified.get('/api/futures/daily-pnl?account=ACCT1').get_json()['daily_pnl']
    direct = FuturesDatabase('futures.db').get_daily_pnl(account=futures_id)

    assert mine == direct


def test_rows_with_no_account_are_not_claimed_by_the_selected_one(unified, registered):
    """Options rows predate the column, so this account has none of them."""
    payload = unified.get('/api/options/data?account=ACCT1').get_json()

    for key in ('open_positions', 'closed_positions', 'expired_positions', 'all_orders'):
        assert payload.get(key) == [], f'{key} claimed rows with no account'


def test_a_summary_computed_over_every_row_is_not_shown_as_an_accounts(unified, registered):
    """A fetcher's summary block spans all rows, so it is not this account's."""
    payload = unified.get('/api/futures/data?account=ACCT1').get_json()
    assert payload.get('summary') is None


def test_refreshing_requires_the_account_being_refreshed():
    """The account is what makes the broker answer for it rather than the primary."""
    from unified.unified_web import app

    rules = {str(r): r for r in app.url_map.iter_rules()}
    assert 'GET' not in rules['/api/<asset_type>/update'].methods

    client = app.test_client()
    assert client.post('/api/options/update', json={}).status_code == 400


def test_the_standalone_dashboards_need_no_account():
    """They show one account's data because that is all they ever fetched."""
    for asset_type in ASSETS:
        client = standalone(asset_type)
        assert client.get('/api/daily-pnl').status_code == 200
