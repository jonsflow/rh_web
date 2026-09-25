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

from typing import Any, Callable, Dict, Optional


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
        update: Callable[[bool], Dict[str, Any]],
        daily_pnl: Callable[[Optional[str], Optional[str]], Any],
        positions_by_date: Callable[[str], Dict[str, Any]],
        daily_summary: Optional[Callable[[str], Any]] = None,
        all_trading_dates: Optional[Callable[[], Any]] = None,
    ):
        self.asset_type = asset_type
        self.label = label
        self.data = data
        self.update = update
        self.daily_pnl = daily_pnl
        self.positions_by_date = positions_by_date
        self.daily_summary = daily_summary
        self.all_trading_dates = all_trading_dates

    def supports(self, operation: str) -> bool:
        return getattr(self, operation, None) is not None


def _options_handlers():
    from portfolio.data_fetcher import SmartDataFetcher

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

    def positions_by_date(date):
        positions = fetcher.option_service.get_positions_by_date(date)
        return {'date': date, 'positions': [p.to_dict() for p in positions]}

    return AssetHandlers(
        asset_type='options',
        label='Options',
        data=data,
        update=lambda force: fetcher.update_data(force_refresh=force),
        daily_pnl=lambda start, end: fetcher.option_service.get_daily_pnl_summary(start, end),
        positions_by_date=positions_by_date,
    )


def _stocks_handlers():
    from stocks.data_fetcher import StocksDataFetcher

    fetcher = StocksDataFetcher()

    def data():
        # Open positions are a live call, so the unified view reads what is
        # stored; the standalone dashboard fetches them separately and so can
        # this one, through its own endpoint
        return fetcher.get_processed_data(include_open_positions=False)

    def positions_by_date(date):
        return {'date': date, 'orders': fetcher.db.get_orders_by_trade_date(date)}

    return AssetHandlers(
        asset_type='stocks',
        label='Stocks',
        data=data,
        update=lambda force: fetcher.update_data(),
        daily_pnl=lambda start, end: fetcher.db.get_daily_pnl(start, end),
        positions_by_date=positions_by_date,
        daily_summary=lambda date: fetcher.db.get_daily_summary(date),
        all_trading_dates=lambda: fetcher.db.get_all_trading_dates(),
    )


def _futures_handlers():
    from futures.data_fetcher import FuturesDataFetcher

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

    def positions_by_date(date):
        return {'date': date, 'orders': fetcher.db.get_orders_by_trade_date(date)}

    return AssetHandlers(
        asset_type='futures',
        label='Futures',
        data=data,
        update=lambda force: fetcher.update_data(),
        daily_pnl=lambda start, end: fetcher.db.get_daily_pnl(start, end),
        positions_by_date=positions_by_date,
        daily_summary=lambda date: fetcher.db.get_daily_summary(date),
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
