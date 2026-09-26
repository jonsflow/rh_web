"""
Turning orders into positions.

One service per asset, each answering `build_positions(orders)` and nothing else.
They take rows and return Position objects: no SQL, no database handle, no file
path, so a calculation can be changed or replaced without touching a query, and
each is testable on a list of dicts.

They are in parity, not equal in size. Futures is handed its realized P&L by the
broker, so pairing is bookkeeping. Stocks P&L is proceeds minus cost. Options has
to be inferred -- a position can end by expiring, direction flips the sign, and a
close whose open predates the fetch window cannot be valued at all.
"""

from unified.services import futures_service, option_service, stock_service

# The sync looks a service up rather than branching on asset type
SERVICES = {
    'options': option_service,
    'stocks': stock_service,
    'futures': futures_service,
}

__all__ = ['SERVICES', 'option_service', 'stock_service', 'futures_service']
