"""
The unified app's order models.

Each model owns the parse of one broker payload and answers the same interface,
so the sync never branches on asset type. These tests pin the parse -- payload in,
row out -- and the interface itself: same methods, same column names, one
vocabulary for whether an order opens or closes.

No database, no broker, no stored data. The payloads are written from the fields
the parse reads.
"""

import json

import pytest

from unified.database import UnifiedDatabase
from unified.models import MODELS, FuturesOrder, OptionOrder, Position, StockOrder


# ---------------------------------------------------------------------------
# Payloads, in the shape each broker endpoint returns
# ---------------------------------------------------------------------------

OPTION_PAYLOAD = {
    'id': 'opt-1',
    'chain_symbol': 'SLV',
    'account_number': 'ACC-OPT',
    'state': 'filled',
    'created_at': '2025-02-24T15:04:05.000000Z',
    'contract_fees': '0',
    'regulatory_fees': '0.04',
    # Reported as an empty list when there are none
    'sales_taxes': [],
    'direction': 'credit',
    'price': '0.85',
    'processed_quantity': '2.00000',
    'processed_premium': '170.00',
    'opening_strategy': 'short_put',
    'closing_strategy': None,
    'legs': [{
        'position_effect': 'open',
        'side': 'sell',
        'expiration_date': '2025-03-21',
        'strike_price': '29.0000',
        'option_type': 'put',
        'option': 'https://api.robinhood.com/options/instruments/aaaabbbbcccc/',
    }],
}

SPREAD_PAYLOAD = dict(OPTION_PAYLOAD, id='opt-2', opening_strategy='call_debit_spread',
                      direction='debit', legs=[
    {'position_effect': 'open', 'side': 'buy', 'expiration_date': '2025-03-21',
     'strike_price': '17.0000', 'option_type': 'call',
     'option': 'https://api.robinhood.com/options/instruments/111122223333/'},
    {'position_effect': 'open', 'side': 'sell', 'expiration_date': '2025-03-21',
     'strike_price': '20.0000', 'option_type': 'call',
     'option': 'https://api.robinhood.com/options/instruments/444455556666/'},
])

STOCK_PAYLOAD = {
    'id': 'stk-1',
    # Resolved by the broker from instrument_id before the model sees it
    'symbol': 'AAPL',
    'side': 'buy',
    'cumulative_quantity': '10.00000000',
    'average_price': '221.4500',
    'executed_notional': {'amount': '2214.50', 'currency': 'USD'},
    'fees': '0.03',
    'sec_fees': '0.01',
    'taf_fees': '0.00',
    'cat_fees': '0.00',
    'sales_taxes': '0.00',
    # Null on the large majority of real orders, so it is not relied on
    'position_effect': None,
    'state': 'FILLED',
    'created_at': '2025-02-24T14:30:00.000000Z',
    'last_transaction_at': '2025-02-24T14:31:02.000000Z',
    'executions': [{'trade_execution_date': '2025-02-24'}],
}

FUTURES_PAYLOAD = {
    'orderId': 'fut-1',
    'accountId': '67648f71-bfff-4ca8-8189-d6f4aa95bcfa',
    'symbol': 'ES',
    'displaySymbol': 'ESH5',
    'quantity': 1,
    'filledQuantity': 1,
    'orderType': 'LIMIT',
    'orderState': 'FILLED',
    'positionEffectAtPlacementTime': 'CLOSING',
    'createdAt': '2025-02-25T01:29:00Z',
    'orderLegs': [{
        'contractId': 'contract-es-h5',
        'orderSide': 'SELL',
        'averagePrice': 6013.25,
    }],
    # Money arrives double-nested
    'realizedPnl': {
        'realizedPnl': {'amount': -19.14, 'currency': 'USD'},
        'realizedPnlWithoutFees': {'amount': -6.35, 'currency': 'USD'},
    },
    'totalFee': {'amount': 12.79, 'currency': 'USD'},
    # 8:30pm Eastern on the 24th, already the 25th in UTC
    'orderExecutions': [{
        'eventTime': '2025-02-25T01:30:00Z',
        # The broker's own trading day, in parts
        'tradeDate': {'year': 2025, 'month': 2, 'day': 24},
    }],
}

PAYLOADS = {
    'options': OPTION_PAYLOAD,
    'stocks': STOCK_PAYLOAD,
    'futures': FUTURES_PAYLOAD,
}


# ---------------------------------------------------------------------------
# The interface every model answers
# ---------------------------------------------------------------------------

def test_every_asset_has_a_model():
    assert sorted(MODELS) == ['futures', 'options', 'stocks']


@pytest.mark.parametrize('asset_type', ['options', 'stocks', 'futures'])
def test_every_model_answers_the_same_interface(asset_type):
    order = MODELS[asset_type].from_payload(PAYLOADS[asset_type], account='acct-1')

    assert order.to_row()['asset_type'] == asset_type
    assert isinstance(order.is_opening, bool)
    assert isinstance(order.is_closing, bool)


@pytest.mark.parametrize('asset_type', ['options', 'stocks', 'futures'])
def test_a_row_uses_only_unified_column_names(asset_type, tmp_path):
    """A row is written straight into the orders table, so its keys are that
    table's columns and nothing else."""
    columns = set(UnifiedDatabase(str(tmp_path / 'u.db')).columns('orders'))
    row = MODELS[asset_type].from_payload(PAYLOADS[asset_type]).to_row()

    assert set(row) <= columns
    # Nothing carries a broker's own name for a figure
    assert not {'net_credit', 'realized_pnl', 'display_symbol', 'premium',
                'total_amount', 'average_price', 'open_premium',
                'contract_id', 'last_transaction_at'} & set(row)


@pytest.mark.parametrize('asset_type', ['options', 'stocks', 'futures'])
def test_every_row_names_its_account(asset_type):
    row = MODELS[asset_type].from_payload(PAYLOADS[asset_type], account='acct-1').to_row()
    assert row['account'] == 'acct-1'


def test_opening_and_closing_read_the_same_whatever_the_broker_calls_them():
    """Options says 'open', futures says 'OPENING', stocks says 'buy'. Past the
    model there is one vocabulary."""
    opened = [
        OptionOrder.from_payload(OPTION_PAYLOAD),
        StockOrder.from_payload(STOCK_PAYLOAD),
        FuturesOrder.from_payload(dict(FUTURES_PAYLOAD,
                                       positionEffectAtPlacementTime='OPENING')),
    ]

    for order in opened:
        assert order.is_opening and not order.is_closing
        assert order.to_row()['position_effect'] == 'open'


def test_a_closing_order_reads_as_closing_for_every_asset():
    closed = [
        OptionOrder.from_payload(dict(
            OPTION_PAYLOAD, legs=[dict(OPTION_PAYLOAD['legs'][0], position_effect='close')])),
        StockOrder.from_payload(dict(STOCK_PAYLOAD, side='sell')),
        FuturesOrder.from_payload(FUTURES_PAYLOAD),
    ]

    for order in closed:
        assert order.is_closing and not order.is_opening
        assert order.to_row()['position_effect'] == 'close'


@pytest.mark.parametrize('asset_type', ['options', 'stocks', 'futures'])
def test_the_payload_is_kept_verbatim(asset_type):
    """The row carries what the API returned, so anything can be re-derived."""
    row = MODELS[asset_type].from_payload(PAYLOADS[asset_type]).to_row()
    assert json.loads(row['raw_data']) == PAYLOADS[asset_type]


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------

def test_an_option_payload_parses_to_its_row():
    row = OptionOrder.from_payload(OPTION_PAYLOAD, account='acct-1').to_row()

    assert row['order_id'] == 'opt-1'
    assert row['symbol'] == 'SLV'
    assert row['position_effect'] == 'open'
    assert row['expiration_date'] == '2025-03-21'
    assert row['strike_price'] == '29.00'
    assert row['option_type'] == 'put'
    assert row['strategy'] == 'short_put'
    assert row['direction'] == 'credit'
    assert row['price'] == 0.85
    assert row['quantity'] == 2
    assert row['gross_amount'] == 170.00
    assert row['trade_date'] == '2025-02-24'
    assert json.loads(row['contract_ids']) == ['aaaabbbbcccc']
    assert row['side'] == 'sell'
    assert row['state'] == 'filled'
    assert row['root_symbol'] == 'SLV'


def test_a_spread_joins_its_strikes_and_types():
    """A multi-leg order is one row, its legs collapsed into one string each."""
    order = OptionOrder.from_payload(SPREAD_PAYLOAD)

    assert order.strike_price == '17.00/20.00'
    assert order.option_type == 'call/call'
    assert order.contract_ids == ['111122223333', '444455556666']
    assert order.is_spread


def test_a_single_option_is_not_a_spread():
    assert not OptionOrder.from_payload(OPTION_PAYLOAD).is_spread


def test_a_missing_price_stays_null_rather_than_zero():
    """Zero is a price. Absence is not, and must not be recorded as one."""
    order = OptionOrder.from_payload(dict(OPTION_PAYLOAD, price=None,
                                          processed_quantity=None,
                                          processed_premium=None))

    assert order.price is None
    assert order.quantity is None
    assert order.premium is None


def test_an_option_order_with_no_legs_parses():
    order = OptionOrder.from_payload(dict(OPTION_PAYLOAD, legs=[]))

    assert order.strike_price == ''
    assert order.option_type == ''
    assert order.contract_ids == []


def test_a_closing_strategy_is_used_when_there_is_no_opening_one():
    order = OptionOrder.from_payload(dict(OPTION_PAYLOAD, opening_strategy=None,
                                          closing_strategy='short_put'))
    assert order.strategy == 'short_put'


# ---------------------------------------------------------------------------
# Stocks
# ---------------------------------------------------------------------------

def test_a_stock_payload_parses_to_its_row():
    row = StockOrder.from_payload(STOCK_PAYLOAD, account='acct-1').to_row()

    assert row['order_id'] == 'stk-1'
    assert row['symbol'] == 'AAPL'
    assert row['root_symbol'] == 'AAPL'
    assert row['side'] == 'buy'
    assert row['quantity'] == 10.0
    assert row['price'] == 221.45
    assert row['gross_amount'] == 2214.50
    # fees plus sec_fees, which the payload reports separately
    assert row['fees'] == 0.04
    assert row['state'] == 'filled'
    assert row['trade_date'] == '2025-02-24'


def test_a_stock_order_is_ordered_by_its_fill_not_its_placement():
    """FIFO pairs buys to sells in fill order, and the two timestamps differ."""
    row = StockOrder.from_payload(STOCK_PAYLOAD).to_row()

    assert row['created_at'] == '2025-02-24T14:30:00.000000Z'
    assert row['executed_at'] == '2025-02-24T14:31:02.000000Z'


def test_a_stock_trade_date_falls_back_to_the_transaction_timestamp():
    row = StockOrder.from_payload(dict(STOCK_PAYLOAD, executions=[])).to_row()
    assert row['trade_date'] == '2025-02-24'


def test_a_stock_with_no_resolved_symbol_is_marked_unknown():
    """The symbol comes from an instrument lookup, which can fail."""
    order = StockOrder.from_payload({k: v for k, v in STOCK_PAYLOAD.items()
                                     if k != 'symbol'})
    assert order.symbol == 'UNKNOWN'


# ---------------------------------------------------------------------------
# Futures
# ---------------------------------------------------------------------------

def test_a_futures_payload_reads_its_nested_pnl():
    """realizedPnl holds realizedPnl holds amount."""
    row = FuturesOrder.from_payload(FUTURES_PAYLOAD).to_row()

    assert row['pnl'] == -19.14
    assert row['pnl_no_fees'] == -6.35
    assert row['fees'] == 12.79


def test_the_after_fees_figure_is_the_one_called_pnl():
    """The two differ by the fees, and the calendar shows the after-fees one."""
    row = FuturesOrder.from_payload(FUTURES_PAYLOAD).to_row()

    assert round(row['pnl_no_fees'] - row['fees'], 2) == row['pnl']


def test_a_futures_trade_date_is_eastern_not_utc():
    """A fill at 8:30pm Eastern is already tomorrow in UTC. It belongs to today."""
    row = FuturesOrder.from_payload(FUTURES_PAYLOAD).to_row()

    assert row['created_at'] == '2025-02-25T01:29:00Z'
    assert row['trade_date'] == '2025-02-24'


def test_every_asset_reports_its_fees():
    """Only futures reported a fee figure before. All three payloads carry one."""
    assert OptionOrder.from_payload(OPTION_PAYLOAD).to_row()['fees'] == 0.04
    assert StockOrder.from_payload(STOCK_PAYLOAD).to_row()['fees'] == 0.04
    assert FuturesOrder.from_payload(FUTURES_PAYLOAD).to_row()['fees'] == 12.79


def test_an_options_fee_survives_a_sales_tax_reported_as_a_list():
    """sales_taxes is [] when there are none, and a number when there are."""
    assert OptionOrder.from_payload(OPTION_PAYLOAD).fees == 0.04
    assert OptionOrder.from_payload(dict(OPTION_PAYLOAD, sales_taxes='0.25')).fees == 0.29


def test_an_option_order_names_its_own_account():
    """The payload carries account_number, so a row says which account it is
    whatever the caller passed."""
    assert OptionOrder.from_payload(OPTION_PAYLOAD).account == 'ACC-OPT'
    assert OptionOrder.from_payload(OPTION_PAYLOAD, account='chosen').account == 'chosen'


def test_a_stock_effect_is_taken_from_the_side_not_the_null_field():
    """position_effect is null on most real equity orders."""
    row = StockOrder.from_payload(STOCK_PAYLOAD).to_row()

    assert STOCK_PAYLOAD['position_effect'] is None
    assert row['position_effect'] == 'open'


def test_a_futures_trade_date_prefers_the_brokers_own():
    """The exchange's trading day beats one we derive, and they agree."""
    row = FuturesOrder.from_payload(FUTURES_PAYLOAD).to_row()
    assert row['trade_date'] == '2025-02-24'

    without = dict(FUTURES_PAYLOAD,
                   orderExecutions=[{'eventTime': '2025-02-25T01:30:00Z'}])
    assert FuturesOrder.from_payload(without).to_row()['trade_date'] == '2025-02-24'


@pytest.mark.parametrize('asset_type,expected', [
    ('options', ['aaaabbbbcccc']), ('stocks', []), ('futures', ['contract-es-h5']),
])
def test_contract_ids_are_always_a_list(asset_type, expected):
    """One leg, one contract, or none -- the column holds the same shape."""
    row = MODELS[asset_type].from_payload(PAYLOADS[asset_type]).to_row()
    assert json.loads(row['contract_ids']) == expected


@pytest.mark.parametrize('asset_type', ['options', 'stocks', 'futures'])
def test_every_row_names_its_underlying(asset_type):
    row = MODELS[asset_type].from_payload(PAYLOADS[asset_type]).to_row()
    assert row['root_symbol']


@pytest.mark.parametrize('asset_type', ['options', 'stocks', 'futures'])
def test_every_row_reports_its_state_in_one_casing(asset_type):
    """The broker says FILLED or filled depending on which one you ask."""
    row = MODELS[asset_type].from_payload(PAYLOADS[asset_type]).to_row()
    assert row['state'] == 'filled'


@pytest.mark.parametrize('asset_type', ['options', 'stocks', 'futures'])
def test_every_row_reports_its_side_in_one_casing(asset_type):
    row = MODELS[asset_type].from_payload(PAYLOADS[asset_type]).to_row()
    assert row['side'] in ('buy', 'sell')


def test_a_futures_order_carries_both_its_symbols():
    row = FuturesOrder.from_payload(FUTURES_PAYLOAD).to_row()

    assert row['symbol'] == 'ESH5'
    assert row['root_symbol'] == 'ES'


def test_a_futures_order_takes_its_account_from_the_payload():
    """Futures has always recorded which account an order belongs to."""
    order = FuturesOrder.from_payload(FUTURES_PAYLOAD)
    assert order.account == '67648f71-bfff-4ca8-8189-d6f4aa95bcfa'


def test_a_futures_order_with_no_legs_parses():
    order = FuturesOrder.from_payload(dict(FUTURES_PAYLOAD, orderLegs=[]))

    assert order.contract_id == ''
    assert order.average_price == 0.0


def test_a_futures_order_with_no_pnl_reports_zero():
    """An opening order has no realized P&L yet."""
    order = FuturesOrder.from_payload(dict(FUTURES_PAYLOAD, realizedPnl={},
                                           positionEffectAtPlacementTime='OPENING'))

    assert order.realized_pnl == 0.0
    assert order.total_fee == 12.79


# ---------------------------------------------------------------------------
# Position
# ---------------------------------------------------------------------------

def test_a_position_row_uses_only_unified_column_names(tmp_path):
    columns = set(UnifiedDatabase(str(tmp_path / 'u.db')).columns('positions'))
    row = Position(asset_type='futures', position_key='k', symbol='ESH5').to_row()

    assert set(row) <= columns


def test_a_position_survives_a_round_trip_through_a_row():
    position = Position(asset_type='options', position_key='k', symbol='SLV',
                        pnl=170.0, status='expired', direction='credit',
                        contract_ids=['aaaabbbbcccc'])

    assert Position.from_row(position.to_row()) == position


def test_a_stored_row_with_extra_columns_still_loads():
    """A row read back carries id and updated_at, which are the table's, not ours."""
    row = dict(Position(asset_type='options', position_key='k', symbol='SLV').to_row(),
               id=7, updated_at='2025-02-24')

    assert Position.from_row(row).symbol == 'SLV'


def test_a_position_says_what_it_is():
    assert Position(asset_type='options', position_key='k', symbol='S',
                    status='closed', pnl=1.0).is_profitable
    assert Position(asset_type='options', position_key='k', symbol='S',
                    status='orphaned').is_orphaned
    assert not Position(asset_type='options', position_key='k', symbol='S',
                        status='orphaned', pnl=None).is_profitable
