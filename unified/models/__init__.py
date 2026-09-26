"""
The unified app's own models.

One order model per asset type, each owning the parse of its broker payload, and
one Position shared by all of them. The parse is the only thing that differs per
asset, so it is the only thing with three implementations; everything downstream
sees one interface.
"""

from unified.models.position import Position
from unified.models.option_order import OptionOrder
from unified.models.stock_order import StockOrder
from unified.models.futures_order import FuturesOrder

# The sync looks a model up rather than branching on asset type
MODELS = {
    'options': OptionOrder,
    'stocks': StockOrder,
    'futures': FuturesOrder,
}

__all__ = ['Position', 'OptionOrder', 'StockOrder', 'FuturesOrder', 'MODELS']
