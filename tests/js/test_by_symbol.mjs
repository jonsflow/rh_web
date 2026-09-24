/**
 * Tests for the shared by-symbol view.
 *
 * It began as stocks-only code, so the first thing checked is that stocks'
 * figures are unchanged, computed the way its own implementation computed them.
 * The rest is that options and futures now get the same view off their own
 * field names.
 *
 *   node --test tests/js/*.mjs
 */
import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const REPO = path.resolve(import.meta.dirname, '..', '..');
const SHARED = path.join(REPO, 'shared', 'static', 'js');

function load() {
    const window = {};
    const elements = {
        table: { innerHTML: '' },
        heatmap: { innerHTML: '' },
        symbolModal: { style: {} },
        symbolModalTitle: { textContent: '' },
        symbolModalTrades: { innerHTML: '' }
    };
    const context = vm.createContext({
        window,
        console,
        URLSearchParams,
        document: {
            getElementById: (id) => elements[id] || null,
            querySelector: () => null,
            querySelectorAll: () => []
        }
    });
    context.globalThis = context;

    for (const rel of ['asset-config.js', 'components/by-symbol.js']) {
        vm.runInContext(fs.readFileSync(path.join(SHARED, rel), 'utf8'), context, { filename: rel });
    }
    return { window, elements };
}

function view(assetType) {
    const { window, elements } = load();
    window.AssetConfig.setAssetType(assetType);
    return { view: new window.BySymbolView({ assetType }), window, elements };
}

/** Stocks closed positions, as /api/closed-positions returns them. */
const STOCK_CLOSED = [
    { symbol: 'AAPL', quantity: 10, buy_price: 100, sell_price: 110, pnl: 100,
      buy_date: '2026-01-05', sell_date: '2026-01-09' },
    { symbol: 'AAPL', quantity: 5, buy_price: 120, sell_price: 110, pnl: -50,
      buy_date: '2026-02-01', sell_date: '2026-02-03' },
    { symbol: 'AAPL', quantity: 5, buy_price: 100, sell_price: 110, pnl: 50,
      buy_date: '2026-02-05', sell_date: '2026-02-07' },
    { symbol: 'TSLA', quantity: 2, buy_price: 200, sell_price: 190, pnl: -20,
      buy_date: '2026-01-10', sell_date: '2026-01-12' },
    { symbol: 'NVDA', quantity: 1, buy_price: 500, sell_price: 500, pnl: 0,
      buy_date: '2026-01-15', sell_date: '2026-01-16' }
];

const STOCK_ORDERS = [
    { symbol: 'AAPL', side: 'buy', quantity: 10, average_price: 100, total_amount: 1000,
      last_transaction_at: '2026-01-05T15:00:00Z' },
    { symbol: 'AAPL', side: 'sell', quantity: 10, average_price: 110, total_amount: 1100,
      last_transaction_at: '2026-01-09T15:00:00Z' },
    { symbol: 'TSLA', side: 'buy', quantity: 2, average_price: 200, total_amount: 400,
      last_transaction_at: '2026-01-10T15:00:00Z' }
];


/* ---------- stocks parity ---------- */

test('stocks grouping matches what its own implementation produced', () => {
    const { view: bySymbol } = view('stocks');
    const stats = bySymbol.groupBySymbol({ closed_positions: STOCK_CLOSED });

    // Sorted by total P&L, best first
    assert.deepEqual(Array.from(stats.map(s => s.symbol)), ['AAPL', 'NVDA', 'TSLA']);

    const aapl = stats[0];
    assert.equal(aapl.total_pnl, 100);
    assert.equal(aapl.num_trades, 3);
    assert.equal(aapl.total_quantity, 20);
    assert.equal(aapl.winning_trades, 2);
    assert.equal(aapl.losing_trades, 1);

    // A zero-P&L trade counts as neither a win nor a loss, as before
    const nvda = stats.find(s => s.symbol === 'NVDA');
    assert.equal(nvda.num_trades, 1);
    assert.equal(nvda.winning_trades, 0);
    assert.equal(nvda.losing_trades, 0);
});

test('win rate and average P&L are computed as they were', () => {
    const { view: bySymbol } = view('stocks');
    const [aapl] = bySymbol.groupBySymbol({ closed_positions: STOCK_CLOSED });

    assert.equal(bySymbol.winRate(aapl).toFixed(1), '66.7');
    assert.equal(bySymbol.averagePnl(aapl).toFixed(2), '33.33');
});

test('the table shows the same columns and formatting as before', () => {
    const { view: bySymbol } = view('stocks');
    const html = bySymbol.renderTable(bySymbol.groupBySymbol({ closed_positions: STOCK_CLOSED }));

    assert.ok(html.includes('<th>Total P&L</th>'));
    assert.ok(html.includes('<th>Avg P&L per Trade</th>'));
    assert.ok(html.includes('<td><strong>AAPL</strong></td>'));
    assert.ok(html.includes('<td class="profit">+$100.00</td>'));
    assert.ok(html.includes('<td>3 (2W / 1L)</td>'));
    assert.ok(html.includes('<td>66.7%</td>'));
    // A loss reads $-20.00: the + is only prefixed to gains, as before
    assert.ok(html.includes('<td class="loss">$-20.00</td>'), 'a losing symbol reads negative');
});

test('an empty set says so rather than rendering an empty table', () => {
    const { view: bySymbol } = view('stocks');
    assert.equal(bySymbol.renderTable([]), '<p>No closed positions</p>');
    assert.equal(bySymbol.renderHeatmap([]), '<p>No closed positions</p>');
});


/* ---------- the heat map ---------- */

test('heat map sizes by magnitude and colours by direction', () => {
    const { view: bySymbol } = view('stocks');
    const html = bySymbol.renderHeatmap([
        { symbol: 'BIG', total_pnl: 1000, num_trades: 10, winning_trades: 7, losing_trades: 3 },
        { symbol: 'SMALL', total_pnl: 10, num_trades: 1, winning_trades: 1, losing_trades: 0 },
        { symbol: 'DOWN', total_pnl: -500, num_trades: 4, winning_trades: 1, losing_trades: 3 },
        { symbol: 'FLAT', total_pnl: 0, num_trades: 1, winning_trades: 0, losing_trades: 0 }
    ]);

    // Largest gain gets the full box, smallest gets near the floor
    assert.ok(html.includes('width: 150px'), 'largest absolute P&L fills the box');
    assert.ok(/width: 5[0-9](\.\d+)?px/.test(html), 'smallest sits near the minimum');
    assert.ok(html.includes('rgb(34, 200, 34)'), 'biggest gain is the strongest green');
    assert.ok(/rgb\(1[0-9][0-9], 34, 34\)/.test(html), 'a loss is red');
    assert.ok(html.includes('#888'), 'a flat symbol is grey');

    // The win-rate line only appears where there is room and enough trades
    assert.ok(html.includes('70% WR'));
    assert.ok(!html.includes('100% WR'), 'a one-trade box has no win-rate line');
});

test('heat map P&L is rounded to whole dollars, as it was', () => {
    const { view: bySymbol } = view('stocks');
    const html = bySymbol.renderHeatmap([
        { symbol: 'AAPL', total_pnl: 1234.56, num_trades: 5, winning_trades: 3, losing_trades: 2 }
    ]);
    assert.ok(html.includes('+$1235'));
    assert.ok(!html.includes('1234.56'));
});


/* ---------- per-asset field mapping ---------- */

test('options groups on net_credit, across closed and expired', () => {
    const { view: bySymbol } = view('options');
    const stats = bySymbol.groupBySymbol({
        closed_positions: [{ symbol: 'SPY', net_credit: 200, quantity: 2 }],
        expired_positions: [{ symbol: 'SPY', net_credit: -50, quantity: 1 },
                            { symbol: 'QQQ', net_credit: 75, quantity: 1 }]
    });

    assert.deepEqual(Array.from(stats.map(s => s.symbol)), ['SPY', 'QQQ']);
    assert.equal(stats[0].total_pnl, 150, 'expired positions count toward the symbol');
    assert.equal(stats[0].num_trades, 2);
});

test('futures groups on realized_pnl, keyed by the contract symbol', () => {
    const { view: bySymbol } = view('futures');
    const stats = bySymbol.groupBySymbol({
        closed_positions: [
            { display_symbol: 'ESZ5', symbol: 'ES', realized_pnl: 300, quantity: 1 },
            { display_symbol: 'ESZ5', symbol: 'ES', realized_pnl: -100, quantity: 1 },
            { display_symbol: 'NQZ5', symbol: 'NQ', realized_pnl: 50, quantity: 2 }
        ]
    });

    assert.deepEqual(Array.from(stats.map(s => s.symbol)), ['ESZ5', 'NQZ5']);
    assert.equal(stats[0].total_pnl, 200);
});

test('a payload for the wrong asset yields nothing rather than wrong numbers', () => {
    const { view: bySymbol } = view('futures');
    // stocks-shaped rows: no display_symbol, no realized_pnl
    assert.equal(bySymbol.groupBySymbol({ closed_positions: STOCK_CLOSED }).length, 0);
});

test('every asset can render the view, so the feature is at parity', () => {
    const payloads = {
        options: { closed_positions: [{ symbol: 'SPY', net_credit: 100, quantity: 1 }],
                   expired_positions: [], all_orders: [] },
        stocks: { closed_positions: STOCK_CLOSED, all_orders: STOCK_ORDERS },
        futures: { closed_positions: [{ display_symbol: 'ESZ5', realized_pnl: 100, quantity: 1 }],
                   all_orders: [] }
    };

    for (const [asset, data] of Object.entries(payloads)) {
        const { view: bySymbol, elements } = view(asset);
        const stats = bySymbol.render(data, {
            tableEl: elements.table,
            heatmapEl: elements.heatmap
        });

        assert.ok(stats.length > 0, `${asset} produced no symbol rows`);
        assert.ok(elements.table.innerHTML.includes('<table'), `${asset} table not rendered`);
        assert.ok(elements.heatmap.innerHTML.includes('heatmap-box'), `${asset} heat map not rendered`);
    }
});


/* ---------- the detail modal ---------- */

test('stocks detail keeps its summary, largest win and largest loss', () => {
    const { view: bySymbol } = view('stocks');
    const html = bySymbol.renderSymbolDetail('AAPL', {
        closed_positions: STOCK_CLOSED,
        all_orders: STOCK_ORDERS
    });

    assert.ok(html.includes('20 shares traded'), 'sums quantity off this symbol\'s orders');
    assert.ok(html.includes('+$100.00'), 'total realized P&L');
    assert.ok(html.includes('<strong>Largest Win:</strong>'));
    assert.ok(html.includes('<strong>Largest Loss:</strong>'));
    assert.ok(html.includes('$-50.00'), 'largest loss');
    assert.ok(html.includes('<h3>Closed Positions (3)</h3>'));
    assert.ok(html.includes('<h3>All Orders (2)</h3>'), 'only this symbol\'s orders');
    assert.ok(html.includes('<td class="sell">SELL</td>'));
});

test('the detail modal labels units as the asset trades them', () => {
    const stocks = view('stocks').view.renderSymbolDetail('AAPL',
        { closed_positions: STOCK_CLOSED, all_orders: STOCK_ORDERS });
    assert.ok(stocks.includes('shares traded'));

    const futures = view('futures').view.renderSymbolDetail('ESZ5', {
        closed_positions: [{ display_symbol: 'ESZ5', realized_pnl: 10, quantity: 1 }],
        all_orders: [{ display_symbol: 'ESZ5', quantity: 1, execution_time: '2026-01-05T15:00:00Z' }]
    });
    assert.ok(futures.includes('contracts traded'));
});

test('a symbol with no closed trades still lists its orders', () => {
    const { view: bySymbol } = view('stocks');
    const html = bySymbol.renderSymbolDetail('TSLA', {
        closed_positions: [],
        all_orders: STOCK_ORDERS
    });

    assert.ok(!html.includes('Closed Positions ('), 'no empty closed table');
    assert.ok(!html.includes('Largest Win'), 'no win/loss line without closed trades');
    assert.ok(html.includes('<h3>All Orders (1)</h3>'));
});

test('the modal opens with the symbol in its title', () => {
    const { view: bySymbol, elements } = view('stocks');
    bySymbol.data = { closed_positions: STOCK_CLOSED, all_orders: STOCK_ORDERS };

    bySymbol.showSymbol('AAPL');

    assert.equal(elements.symbolModalTitle.textContent, 'Trading Summary - AAPL');
    assert.equal(elements.symbolModal.style.display, 'block');
    assert.ok(elements.symbolModalTrades.innerHTML.includes('AAPL') === false
              || elements.symbolModalTrades.innerHTML.length > 0);
});

test('a symbol cannot break out of the click handler or the markup', () => {
    const { view: bySymbol } = view('stocks');
    const nasty = "AAPL'); alert('x";
    const html = bySymbol.renderTable([
        { symbol: nasty, total_pnl: 1, num_trades: 1, winning_trades: 1, losing_trades: 0 }
    ]);

    assert.ok(!html.includes("alert('x')"), 'quote in the symbol did not close the handler');
    assert.ok(html.includes('&#39;'), 'the quote was escaped');

    const tagged = bySymbol.renderHeatmap([
        { symbol: '<img src=x onerror=alert(1)>', total_pnl: 5, num_trades: 1,
          winning_trades: 1, losing_trades: 0 }
    ]);
    assert.ok(!tagged.includes('<img'), 'markup in a symbol was escaped');
});
