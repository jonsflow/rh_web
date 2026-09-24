"""
Tests for the frontend files shared between dashboards.

These files used to be copy-pasted per dashboard. One copy now lives in
shared/static/ and each app mounts it at /shared/static/...

Offline only: the app factories touch no API, and '/' is a bare template
render, so nothing here authenticates or hits the network.
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# Files hoisted out of the dashboards, as paths under shared/static/js/
SHARED_JS = [
    'asset-config.js',
    'calendar.js',
    'components/position-table.js',
    'components/summary-card.js',
    'services/api-service.js',
    'services/data-manager.js',
    'sorting.js',
]

# Dashboards that mount the shared blueprint, and their templates
MOUNTED = [
    ('portfolio.rh_web', 'portfolio/templates/index.html'),
    ('futures.futures_web', 'futures/templates/index.html'),
    ('stocks.stocks_web', 'stocks/templates/index.html'),
]

DASHBOARDS = ['portfolio', 'stocks', 'futures']


def _app(module_name):
    return __import__(module_name, fromlist=['app']).app


@pytest.mark.parametrize('rel', SHARED_JS)
def test_shared_file_exists_once(rel):
    """Exactly one copy on disk: shared/, never back inside a dashboard."""
    assert os.path.isfile(os.path.join(REPO, 'shared', 'static', 'js', rel))

    duplicates = [
        d for d in DASHBOARDS
        if os.path.isfile(os.path.join(REPO, d, 'static', 'js', rel))
    ]
    assert duplicates == [], (
        f'{rel} was copied back into {duplicates}; it belongs in shared/static/js/ only'
    )


@pytest.mark.parametrize('module_name,template', MOUNTED)
@pytest.mark.parametrize('rel', SHARED_JS)
def test_shared_file_is_served(module_name, template, rel):
    """Each mounting app serves the file, with the shared copy's bytes."""
    client = _app(module_name).test_client()
    response = client.get(f'/shared/static/js/{rel}')
    assert response.status_code == 200

    with open(os.path.join(REPO, 'shared', 'static', 'js', rel), 'rb') as handle:
        assert response.get_data() == handle.read()


@pytest.mark.parametrize('module_name,template', MOUNTED)
def test_every_script_tag_resolves(module_name, template):
    """No 404s: every script the rendered page asks for is actually served."""
    app = _app(module_name)
    client = app.test_client()

    index = client.get('/')
    assert index.status_code == 200

    local_srcs = [
        src for src in re.findall(r'<script src="([^"]+)"', index.get_data(as_text=True))
        if src.startswith('/')
    ]
    assert local_srcs, 'no local script tags found; template markup changed'

    for src in local_srcs:
        assert client.get(src).status_code == 200, f'{src} is not served'


@pytest.mark.parametrize('module_name,template', MOUNTED)
def test_templates_use_the_shared_path(module_name, template):
    """A hoisted file is requested from /shared/static/, never /static/."""
    with open(os.path.join(REPO, template)) as handle:
        markup = handle.read()

    for rel in SHARED_JS:
        assert f'/static/js/{rel}' not in markup.replace(f'/shared/static/js/{rel}', ''), (
            f'{template} still loads {rel} from the dashboard-local /static/js/'
        )


def test_every_page_declares_its_asset_type():
    """A page that loads the shared components must say which asset it is.

    Without it the components have no config to read and render nothing.
    """
    for _, template in MOUNTED:
        with open(os.path.join(REPO, template)) as handle:
            markup = handle.read()
        assert 'setAssetType(' in markup, f'{template} does not declare its asset type'
        assert 'asset-config.js' in markup, f'{template} does not load the asset config'
