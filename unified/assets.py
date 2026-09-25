"""
What each asset type can do, in one place.

The three dashboards each wired their own routes to their own fetcher. This
registry names the same operations for every asset, so the unified app serves
/api/<asset_type>/... with one set of routes instead of three near-identical
sets.

Nothing is reimplemented here: every handler calls the same fetcher and service
the standalone dashboard calls, so the numbers are the numbers those dashboards
already produce.
"""

from typing import Any, Callable, Dict, List, Optional


class AssetHandlers:
    """The operations one asset type supports.

    An operation left as None is one that asset does not serve -- futures has
    no all-trading-dates endpoint, options no daily summary -- and the routes
    answer 404 for it rather than failing inside a handler.
    """

    def __init__(
        self,
        asset_type: str,
        label: str,
        data: Callable[[], Dict[str, Any]],
        update: Callable[..., Dict[str, Any]],
        daily_pnl: Callable[..., Any],
        positions_by_date: Callable[..., Dict[str, Any]],
        daily_summary: Optional[Callable[..., Any]] = None,
        all_trading_dates: Optional[Callable[[], Any]] = None,
        accounts: Optional[Callable[[], List[str]]] = None,
    ):
        self.asset_type = asset_type
        self.label = label
        self.data = data
        self.update = update
        self.daily_pnl = daily_pnl
        self.positions_by_date = positions_by_date
        self.daily_summary = daily_summary
        self.all_trading_dates = all_trading_dates
        self.accounts = accounts

    def supports(self, operation: str) -> bool:
        return getattr(self, operation, None) is not None


def _options_handlers():
    from portfolio.data_fetcher import SmartDataFetcher
    from shared.accounts import accounts_in

    fetcher = SmartDataFetcher()

    def data():
        result = fetcher.get_processed_data()
        if 'error' in result:
            return result
        # The shape the options dashboard has always returned
        return {
            'open_positions': result['open_positions'],
            'closed_positions': result['closed_positions'],
            'expired_positions': result['expired_positions'],
            'all_orders': result['all_orders'],
        }

    def positions_by_date(date, account=None):
        positions = fetcher.option_service.get_positions_by_date(date)
        rows = [p.to_dict() for p in positions]
        if account:
            rows = [row for row in rows if row.get('account_number') == account]
        return {'date': date, 'positions': rows}

    return AssetHandlers(
        asset_type='options',
        label='Options',
        data=data,
        update=lambda force, account=None:
            fetcher.update_data(force_full_refresh=force, account_number=account),
        daily_pnl=lambda start, end, account=None:
            fetcher.option_service.get_daily_pnl_summary(start, end, account),
        positions_by_date=positions_by_date,
        accounts=lambda: accounts_in(fetcher.db.db_path, 'option_orders'),
    )


def _stocks_handlers():
    from stocks.data_fetcher import StocksDataFetcher
    from shared.accounts import accounts_in

    fetcher = StocksDataFetcher()

    def data():
        # Open positions are a live call, so the unified view reads what is
        # stored; the standalone dashboard fetches them separately and so can
        # this one, through its own endpoint
        return fetcher.get_processed_data(include_open_positions=False)

    def positions_by_date(date, account=None):
        return {'date': date, 'orders': fetcher.db.get_orders_by_trade_date(date, account)}

    return AssetHandlers(
        asset_type='stocks',
        label='Stocks',
        data=data,
        update=lambda force, account=None: fetcher.update_data(account_number=account),
        daily_pnl=lambda start, end, account=None: fetcher.db.get_daily_pnl(start, end, account),
        positions_by_date=positions_by_date,
        daily_summary=lambda date, account=None: fetcher.db.get_daily_summary(date),
        all_trading_dates=lambda: fetcher.db.get_all_trading_dates(),
        accounts=lambda: accounts_in(fetcher.db.db_path, 'stock_orders'),
    )


def _futures_handlers():
    from futures.data_fetcher import FuturesDataFetcher
    from shared.accounts import accounts_in

    fetcher = FuturesDataFetcher()

    def data():
        result = fetcher.get_processed_data()
        if 'error' in result:
            return result
        return {
            'open_positions': result['open_positions'],
            'closed_positions': result['closed_positions'],
            'all_orders': result['all_orders'],
            'summary': result['summary'],
        }

    def positions_by_date(date, account=None):
        return {'date': date, 'orders': fetcher.db.get_orders_by_trade_date(date, account)}

    return AssetHandlers(
        asset_type='futures',
        label='Futures',
        data=data,
        # Futures resolves its own account from the broker
        update=lambda force, account=None: fetcher.update_data(),
        daily_pnl=lambda start, end, account=None: fetcher.db.get_daily_pnl(start, end, account),
        positions_by_date=positions_by_date,
        daily_summary=lambda date, account=None: fetcher.db.get_daily_summary(date),
        # Futures has recorded its account since it was built
        accounts=lambda: accounts_in(fetcher.db.db_path, 'futures_orders', 'account_id'),
    )


# Built on first use: constructing a fetcher opens its database, and a dashboard
# for one asset should not be held up by another asset's file
_BUILDERS = {
    'options': _options_handlers,
    'stocks': _stocks_handlers,
    'futures': _futures_handlers,
}

_CACHE: Dict[str, AssetHandlers] = {}


def asset_types():
    """Every asset type the unified app serves."""
    return list(_BUILDERS)


def get_handlers(asset_type: str) -> Optional[AssetHandlers]:
    """Handlers for one asset type, or None if it is not one we serve."""
    if asset_type not in _BUILDERS:
        return None
    if asset_type not in _CACHE:
        _CACHE[asset_type] = _BUILDERS[asset_type]()
    return _CACHE[asset_type]


def reset():
    """Drop the cached handlers. For tests."""
    _CACHE.clear()


def all_accounts() -> Dict[str, List[str]]:
    """Which accounts appear in each asset's stored rows.

    Read from what is stored rather than from the broker, so the switcher can
    be built without a live call. An asset whose rows predate the account
    column contributes nothing, and the view falls back to every account.
    """
    found = {}
    for asset_type in asset_types():
        handlers = get_handlers(asset_type)
        found[asset_type] = handlers.accounts() if handlers.supports('accounts') else []
    return found
