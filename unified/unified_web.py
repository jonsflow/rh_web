"""
One dashboard across every asset type.

Serves /api/<asset_type>/... from the registry in unified/assets.py, so a single
set of routes covers options, stocks and futures. The three standalone
dashboards are untouched and keep running as they did; this is built alongside
them on the same services.

    python -m unified.unified_web
"""

import traceback

from flask import Flask, jsonify, render_template, request, send_from_directory

from shared.journals_api import journals_blueprint
from shared.web_assets import shared_static_blueprint
from unified.assets import asset_types, get_handlers

app = Flask(__name__, static_url_path='/static', static_folder='static',
            template_folder='templates')


@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)


# Frontend files shared with the standalone dashboards
app.register_blueprint(shared_static_blueprint())

# Trade journal, shared by every dashboard
app.register_blueprint(journals_blueprint())


def _handlers_or_404(asset_type):
    """The handlers for an asset, or a 404 response to return instead."""
    handlers = get_handlers(asset_type)
    if handlers is None:
        return None, (jsonify({'error': f'Unknown asset type: {asset_type}'}), 404)
    return handlers, None


def _failed(operation, error):
    """Log the detail, tell the caller what failed."""
    print(f"{operation} error: {error}")
    print(traceback.format_exc())
    return jsonify({'error': f'Failed to {operation}'}), 500


@app.route('/')
def index():
    """Render the main page."""
    return render_template('index.html')


@app.route('/api/assets')
def list_assets():
    """The asset types this app serves, and what each one supports.

    The page builds its switcher from this rather than hard-coding the list.
    """
    assets = []
    for asset_type in asset_types():
        handlers = get_handlers(asset_type)
        assets.append({
            'asset_type': asset_type,
            'label': handlers.label,
            'daily_summary': handlers.supports('daily_summary'),
            'all_trading_dates': handlers.supports('all_trading_dates'),
        })
    return jsonify({'success': True, 'assets': assets})


@app.route('/api/<asset_type>/data')
def get_data(asset_type):
    """Positions and orders for one asset."""
    handlers, missing = _handlers_or_404(asset_type)
    if missing:
        return missing

    try:
        result = handlers.data()
        if result and result.get('error'):
            return jsonify({'error': result.get('message', 'Failed to fetch data')}), 500
        return jsonify(result)
    except Exception as error:
        return _failed(f'fetch {asset_type} data', error)


@app.route('/api/<asset_type>/update', methods=['POST'])
def update_data(asset_type):
    """Refresh one asset's data from the broker."""
    handlers, missing = _handlers_or_404(asset_type)
    if missing:
        return missing

    payload = request.get_json(silent=True) or {}
    try:
        result = handlers.update(bool(payload.get('force_refresh')))
        if result and result.get('error'):
            return jsonify({'error': result.get('message', 'Failed to update')}), 500
        return jsonify(result if result is not None else {'success': True})
    except Exception as error:
        return _failed(f'update {asset_type} data', error)


@app.route('/api/<asset_type>/daily-pnl')
def get_daily_pnl(asset_type):
    """Daily P&L for the calendar."""
    handlers, missing = _handlers_or_404(asset_type)
    if missing:
        return missing

    try:
        daily = handlers.daily_pnl(request.args.get('start_date'), request.args.get('end_date'))
        return jsonify({'success': True, 'daily_pnl': daily})
    except Exception as error:
        return _failed(f'fetch {asset_type} daily P&L', error)


@app.route('/api/<asset_type>/positions/date/<date>')
def get_positions_by_date(asset_type, date):
    """What happened on one date.

    Options answers with positions, stocks and futures with orders -- the same
    shapes their own dashboards return.
    """
    handlers, missing = _handlers_or_404(asset_type)
    if missing:
        return missing

    try:
        result = handlers.positions_by_date(date)
        return jsonify({'success': True, **result})
    except Exception as error:
        return _failed(f'fetch {asset_type} positions for {date}', error)


@app.route('/api/<asset_type>/daily-summary/<date>')
def get_daily_summary(asset_type, date):
    """One date's summary, for assets that produce one."""
    handlers, missing = _handlers_or_404(asset_type)
    if missing:
        return missing

    if not handlers.supports('daily_summary'):
        return jsonify({'error': f'{asset_type} has no daily summary'}), 404

    try:
        return jsonify({'success': True, 'summary': handlers.daily_summary(date)})
    except Exception as error:
        return _failed(f'fetch {asset_type} summary for {date}', error)


@app.route('/api/<asset_type>/all-trading-dates')
def get_all_trading_dates(asset_type):
    """Every date with activity, for assets that track it."""
    handlers, missing = _handlers_or_404(asset_type)
    if missing:
        return missing

    if not handlers.supports('all_trading_dates'):
        return jsonify({'error': f'{asset_type} has no trading-date index'}), 404

    try:
        return jsonify({'success': True, 'dates': handlers.all_trading_dates()})
    except Exception as error:
        return _failed(f'fetch {asset_type} trading dates', error)


if __name__ == '__main__':
    app.run(debug=True, port=5004)
