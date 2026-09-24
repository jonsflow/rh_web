"""
The shared calendar must keep showing each asset the figure it always showed.

The three dashboards had drifted: options put `pnl` on the day, stocks and
futures put `pnl_no_fees`. That difference now lives in asset-config.js rather
than in three copies of a calendar, which means a wrong entry there would
silently change displayed P&L. These tests read the config the browser reads and
check it against what each backend actually serves, from the real databases.

Offline: every route used here reads SQLite only.
"""
import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CONFIG_JS = os.path.join(REPO, 'shared', 'static', 'js', 'asset-config.js')

# asset type -> the app module that serves it
APPS = {
    'options': 'portfolio.rh_web',
    'stocks': 'stocks.stocks_web',
    'futures': 'futures.futures_web',
}


def calendar_pnl_fields():
    """The pnlField each asset declares, parsed from the browser config.

    Parsed rather than imported: this is the file the browser loads, so reading
    it here keeps the two from drifting apart.
    """
    with open(CONFIG_JS) as handle:
        source = handle.read()

    fields = {}
    for asset in APPS:
        # find this asset's block, then its calendar pnlField
        start = source.index(f'    {asset}: {{')
        block = source[start:]
        match = re.search(r"calendar:\s*\{.*?pnlField:\s*'([a-z_]+)'", block, re.DOTALL)
        assert match, f'no calendar pnlField for {asset}'
        fields[asset] = match.group(1)
    return fields


def daily_pnl(asset):
    app = __import__(APPS[asset], fromlist=['app']).app
    response = app.test_client().get('/api/daily-pnl')
    assert response.status_code == 200, f'{asset} daily-pnl returned {response.status_code}'
    return response.get_json().get('daily_pnl') or {}


@pytest.mark.parametrize('asset', sorted(APPS))
def test_calendar_field_is_served_for_every_day(asset):
    """The field the calendar reads exists on every day the backend returns.

    A missing field would render every day as $0.00 rather than fail.
    """
    field = calendar_pnl_fields()[asset]
    days = daily_pnl(asset)

    if not days:
        pytest.skip(f'no {asset} data stored locally')

    missing = [date for date, day in days.items() if day.get(field) is None]
    assert missing == [], (
        f'{asset} calendar reads {field}, absent on {len(missing)} day(s), '
        f'e.g. {missing[:3]}'
    )


@pytest.mark.parametrize('asset', sorted(APPS))
def test_calendar_field_matches_what_the_asset_always_showed(asset):
    """Pins the pre-merge choice: options gross, stocks and futures before fees.

    Kept as a literal so changing it is a deliberate edit to this test, not a
    side effect of editing the config.
    """
    expected = {'options': 'pnl', 'stocks': 'pnl_no_fees', 'futures': 'pnl_no_fees'}
    assert calendar_pnl_fields()[asset] == expected[asset]


def test_stocks_and_futures_report_fees_separately_from_pnl():
    """Why those two show pnl_no_fees at all: they serve both figures.

    If a backend stopped serving the pair, showing P&L before fees would be
    misleading rather than merely different.
    """
    for asset in ('stocks', 'futures'):
        days = daily_pnl(asset)
        if not days:
            pytest.skip(f'no {asset} data stored locally')
        day = next(iter(days.values()))
        assert 'pnl' in day and 'pnl_no_fees' in day, f'{asset} serves only one P&L figure'


def test_every_asset_serves_the_day_count_the_calendar_labels():
    """The label under the amount reads a count off the same payload."""
    for asset in sorted(APPS):
        days = daily_pnl(asset)
        if not days:
            continue
        day = next(iter(days.values()))
        assert 'count' in day, f'{asset} serves no count for the day label'
