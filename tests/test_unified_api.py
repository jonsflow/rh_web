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

@pytest.mark.parametrize('asset_type', ASSETS)
def test_daily_pnl_matches_the_standalone_dashboard(unified, asset_type):
    """The figure behind every calendar day, compared response to response."""
    mine = unified.get(f'/api/{asset_type}/daily-pnl')
    theirs = standalone(asset_type).get('/api/daily-pnl')

    assert mine.status_code == theirs.status_code == 200
    assert mine.get_json()['daily_pnl'] == theirs.get_json()['daily_pnl']


@pytest.mark.parametrize('asset_type', ASSETS)
def test_daily_pnl_honours_a_date_range_the_same_way(unified, asset_type):
    query = 'start_date=2026-01-01&end_date=2026-03-31'
    mine = unified.get(f'/api/{asset_type}/daily-pnl?{query}').get_json()
    theirs = standalone(asset_type).get(f'/api/daily-pnl?{query}').get_json()

    assert mine['daily_pnl'] == theirs['daily_pnl']


@pytest.mark.parametrize('asset_type', ASSETS)
def test_a_days_detail_matches_the_standalone_dashboard(unified, asset_type):
    """Whichever day has the most activity, so the comparison is not empty."""
    days = unified.get(f'/api/{asset_type}/daily-pnl').get_json()['daily_pnl']
    if not days:
        pytest.skip(f'no {asset_type} data stored locally')

    date = max(days, key=lambda d: days[d].get('count', 0))

    mine = unified.get(f'/api/{asset_type}/positions/date/{date}').get_json()
    theirs = standalone(asset_type).get(f'/api/positions/date/{date}').get_json()

    # options answers with positions, stocks and futures with orders
    key = 'positions' if 'positions' in theirs else 'orders'
    assert mine[key] == theirs[key]
    assert mine['date'] == theirs['date'] == date


@pytest.mark.parametrize('asset_type', ['stocks', 'futures'])
def test_a_daily_summary_matches_the_standalone_dashboard(unified, asset_type):
    days = unified.get(f'/api/{asset_type}/daily-pnl').get_json()['daily_pnl']
    if not days:
        pytest.skip(f'no {asset_type} data stored locally')

    date = max(days, key=lambda d: days[d].get('count', 0))

    mine = unified.get(f'/api/{asset_type}/daily-summary/{date}').get_json()
    theirs = standalone(asset_type).get(f'/api/daily-summary/{date}').get_json()

    assert mine['summary'] == theirs['summary']


def test_trading_dates_match_the_stocks_dashboard(unified):
    mine = unified.get('/api/stocks/all-trading-dates').get_json()
    theirs = standalone('stocks').get('/api/all-trading-dates').get_json()

    assert mine['dates'] == theirs['dates']


@pytest.mark.parametrize('asset_type', ['options', 'futures'])
def test_stored_data_matches_the_standalone_dashboard(unified, asset_type):
    """Positions and orders, for the assets whose data route reads only SQLite.

    Stocks is left out on purpose: its standalone data route fetches open
    positions live, which these tests must not do.
    """
    path = {'options': '/api/options', 'futures': '/api/futures'}[asset_type]

    mine = unified.get(f'/api/{asset_type}/data').get_json()
    theirs = standalone(asset_type).get(path).get_json()

    for key in ('open_positions', 'closed_positions', 'expired_positions', 'all_orders'):
        assert mine.get(key) == theirs.get(key), f'{asset_type} {key} differs'


# ---------- the route surface ----------

def test_an_unknown_asset_is_refused_rather_than_guessed(unified):
    for path in ('/api/crypto/data', '/api/crypto/daily-pnl',
                 '/api/crypto/positions/date/2026-03-02'):
        response = unified.get(path)
        assert response.status_code == 404, path
        assert 'crypto' in response.get_json()['error']


def test_an_endpoint_an_asset_does_not_serve_says_so(unified):
    """Rather than erroring inside a handler that has nothing to call."""
    assert unified.get('/api/options/daily-summary/2026-03-02').status_code == 404
    assert unified.get('/api/futures/all-trading-dates').status_code == 404


@pytest.mark.parametrize('asset_type', ASSETS)
def test_every_asset_serves_the_same_route_surface(unified, asset_type):
    """One set of routes covers all three; that is the point of the app."""
    for path in (f'/api/{asset_type}/data',
                 f'/api/{asset_type}/daily-pnl',
                 f'/api/{asset_type}/positions/date/2026-03-02'):
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
    assert unified.get('/api/journals').status_code == 200


def test_the_standalone_dashboards_are_untouched():
    """This app is built alongside them, not in place of them."""
    for asset_type, module in STANDALONE.items():
        client = standalone(asset_type)
        assert client.get('/').status_code == 200, f'{module} no longer renders'
        assert client.get('/api/daily-pnl').status_code == 200, f'{module} lost its routes'
