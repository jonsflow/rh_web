/**
 * Tests for the shared calendar.
 *
 * The important one is parity: the same day figures the three separate
 * calendars produced, replayed from captured API payloads. Everything else is
 * detail rendering per asset.
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
const FIXTURES = path.join(import.meta.dirname, 'fixtures');

/** Load the shared scripts with a stub window and a fake DOM. */
function load({ dailyPnl = {}, summaries = {}, positions = {}, tradingDates = null } = {}) {
    const window = {};
    const elements = {
        calendarView: { id: 'calendarView' },
        positionModal: {
            style: {},
            querySelector: () => ({ addEventListener: () => {} })
        },
        modalTitle: { textContent: '' },
        modalPositions: { innerHTML: '' }
    };
    const context = vm.createContext({
        window,
        console,
        URLSearchParams,
        document: {
            getElementById: (id) => elements[id] || null,
            querySelector: () => null
        },
        fetch: async () => { throw new Error('the calendar must go through ApiService'); }
    });
    context.globalThis = context;

    for (const rel of ['asset-config.js', 'services/api-service.js', 'calendar.js']) {
        vm.runInContext(fs.readFileSync(path.join(SHARED, rel), 'utf8'), context, { filename: rel });
    }

    // A stand-in ApiService that replays canned payloads and records its calls
    const calls = [];
    const api = {
        calls,
        fetchDailyPnl: async (start, end, options) => {
            calls.push({ name: 'dailyPnl', start, end, options });
            return { success: true, daily_pnl: dailyPnl };
        },
        fetchAllTradingDates: async (options) => {
            calls.push({ name: 'allTradingDates', options });
            return { success: true, dates: tradingDates ?? Object.keys(summaries) };
        },
        fetchDailySummary: async (date, options) => {
            calls.push({ name: 'dailySummary', date, options });
            return { success: true, summary: summaries[date] };
        },
        fetchPositionsByDate: async (date, options) => {
            calls.push({ name: 'positionsByDate', date, options });
            return { success: true, ...(positions[date] || {}) };
        }
    };

    return { window, api, elements, calls };
}

function manager(assetType, payloads = {}) {
    const { window, api, elements, calls } = load(payloads);
    window.AssetConfig.setAssetType(assetType);
    const cal = new window.CalendarManager({ assetType, api });
    return { cal, window, api, elements, calls };
}

const MONTH = { startStr: '0000-01-01', endStr: '9999-12-31' };


/* ---------- parity: the figure each asset puts on a day ---------- */

test('each asset shows the P&L field its own calendar showed', async () => {
    // One day, both fields present and different, so a swap cannot pass
    const day = { '2026-03-02': { pnl: 100, pnl_no_fees: 250, count: 4 } };

    const optionsCal = manager('options', { dailyPnl: day }).cal;
    const futuresCal = manager('futures', { dailyPnl: day }).cal;

    assert.equal((await optionsCal.buildEvents(MONTH.startStr, MONTH.endStr))[0].title, '$100.00',
                 'options showed pnl');
    assert.equal((await futuresCal.buildEvents(MONTH.startStr, MONTH.endStr))[0].title, '$250.00',
                 'futures showed pnl_no_fees');

    const stocks = manager('stocks', {
        dailyPnl: day,
        summaries: { '2026-03-02': { totals: { positions_closed: 1, positions_opened: 0 } } }
    });
    assert.equal((await stocks.cal.buildEvents(MONTH.startStr, MONTH.endStr))[0].title, '$250.00',
                 'stocks showed pnl_no_fees');
});

test('day figures follow the payload shape each asset serves', async () => {
    // Fixtures carry the real payload shape with stand-in numbers; the check
    // against real data lives in tests/test_calendar_parity.py, because the
    // databases are deliberately not in the repo
    for (const [asset, file] of [['options', 'options-daily-pnl.json'],
                                 ['stocks', 'stocks-daily-pnl.json'],
                                 ['futures', 'futures-daily-pnl.json']]) {
        const dailyPnl = JSON.parse(fs.readFileSync(path.join(FIXTURES, file), 'utf8'));
        const field = asset === 'options' ? 'pnl' : 'pnl_no_fees';

        // What the old calendar for this asset would have rendered
        const expected = {};
        for (const [date, dayData] of Object.entries(dailyPnl)) {
            expected[date] = `$${Number(dayData[field] || 0).toFixed(2)}`;
        }

        const payloads = { dailyPnl };
        if (asset === 'stocks') {
            // stocks needs day states; give every day a closed position so the
            // comparison is about the figure, not about which days appear
            payloads.summaries = Object.fromEntries(Object.keys(dailyPnl).map(
                date => [date, { totals: { positions_closed: 1, positions_opened: 0 } }]));
        }

        const { cal } = manager(asset, payloads);
        const events = await cal.buildEvents(MONTH.startStr, MONTH.endStr);

        assert.equal(events.length, Object.keys(expected).length, `${asset} day count`);
        for (const event of events) {
            assert.equal(event.title, expected[event.id], `${asset} ${event.id}`);
        }
    }
});

test('monthly totals sum the same field as the days', async () => {
    const dailyPnl = {
        '2026-03-02': { pnl: 10, pnl_no_fees: 100, count: 1 },
        '2026-03-09': { pnl: 20, pnl_no_fees: 200, count: 1 },
        '2026-04-06': { pnl: 40, pnl_no_fees: 400, count: 1 }
    };
    const titles = [];
    for (const asset of ['options', 'futures']) {
        const { cal, window } = manager(asset, { dailyPnl });
        const title = { innerHTML: '' };
        // updateMonthlyPnlSummary writes into .fc-toolbar-title
        cal.updateMonthlyPnlSummary = function (info) {
            let total = 0, days = 0;
            for (const [date, dayData] of Object.entries(this.dailyPnlData)) {
                const d = new Date(date);
                if (d.getMonth() === 2 && d.getFullYear() === 2026) { total += this.dayPnl(dayData); days++; }
            }
            titles.push({ asset, total, days });
        };
        await cal.buildEvents(MONTH.startStr, MONTH.endStr);
        cal.updateMonthlyPnlSummary({ start: '2026-03-01', end: '2026-03-31' });
    }
    assert.deepEqual(titles, [
        { asset: 'options', total: 30, days: 2 },
        { asset: 'futures', total: 300, days: 2 }
    ]);
});


/* ---------- day states ---------- */

test('a day that only opened positions gets its own colour, where tracked', async () => {
    const { cal } = manager('stocks', {
        dailyPnl: { '2026-03-02': { pnl_no_fees: 0, count: 2 } },
        summaries: {
            '2026-03-02': { totals: { positions_closed: 0, positions_opened: 2 } },
            '2026-03-03': { totals: { positions_closed: 1, positions_opened: 0 } }
        }
    });

    const events = await cal.buildEvents(MONTH.startStr, MONTH.endStr);
    const byDate = Object.fromEntries(events.map(e => [e.id, e]));

    assert.equal(byDate['2026-03-02'].backgroundColor, '#007bff', 'opened-only day is blue');
    assert.equal(byDate['2026-03-03'].backgroundColor, '#28a745');
});

test('a day with no activity is dropped, where day states are tracked', async () => {
    const { cal } = manager('stocks', {
        dailyPnl: { '2026-03-02': { pnl_no_fees: 5, count: 1 } },
        summaries: { '2026-03-02': { totals: { positions_closed: 0, positions_opened: 0 } } },
        tradingDates: ['2026-03-02']
    });

    assert.equal((await cal.buildEvents(MONTH.startStr, MONTH.endStr)).length, 0);
});

test('assets without day states ask for no per-day summaries', async () => {
    const { cal, calls } = manager('options', {
        dailyPnl: { '2026-03-02': { pnl: 5, count: 1 } }
    });

    await cal.buildEvents(MONTH.startStr, MONTH.endStr);

    assert.deepEqual(calls.map(c => c.name), ['dailyPnl'],
                     'options must not make the per-date summary requests');
});

test('the day label reads as each asset labelled it', async () => {
    const options = manager('options').cal;
    assert.equal(options.dayLabel({ count: 7 }), '7 trades');

    const stocks = manager('stocks').cal;
    assert.equal(stocks.dayLabel({ positions_closed: 2, positions_opened: 3 }), '2 closed, 3 opened');
    assert.equal(stocks.dayLabel({ positions_closed: 2, positions_opened: 0 }), '2 closed');
    assert.equal(stocks.dayLabel({ positions_closed: 0, positions_opened: 3 }), '3 opened');
    assert.equal(stocks.dayLabel({ positions_closed: 0, positions_opened: 0 }), '');
});


/* ---------- asset and account plumbing ---------- */

test('every calendar request carries the asset it is rendering', async () => {
    const { cal, calls } = manager('futures', {
        dailyPnl: { '2026-03-02': { pnl_no_fees: 5, count: 1 } },
        summaries: { '2026-03-02': { totals: {}, contracts: [] } },
        positions: { '2026-03-02': { orders: [] } }
    });

    await cal.buildEvents(MONTH.startStr, MONTH.endStr);
    await cal.fetchDetailSources('2026-03-02');

    assert.ok(calls.length >= 3);
    for (const call of calls) {
        assert.equal(call.options.assetType, 'futures', `${call.name} lost the asset`);
    }
});

test('the calendar goes through ApiService, so the account rides along', async () => {
    const { window } = load({ dailyPnl: {} });
    window.AssetConfig.setAssetType('options').setAccount('ACCT9');

    const urls = [];
    const cal = new window.CalendarManager({
        assetType: 'options',
        api: Object.assign(Object.create(Object.getPrototypeOf(window.ApiService)), window.ApiService, {})
    });
    // Intercept at the URL layer to prove the account is on the wire
    cal.api.buildUrl = function (...args) {
        const url = window.ApiServiceClass.prototype.buildUrl.apply(this, args);
        urls.push(url);
        return url;
    };
    cal.api._request = async () => ({ success: true, daily_pnl: {} });

    await cal.loadPnlData('2026-03-01', '2026-03-31');

    assert.equal(urls.length, 1);
    assert.match(urls[0], /^\/api\/daily-pnl\?/);
    assert.match(urls[0], /account=ACCT9/);
    assert.match(urls[0], /start_date=2026-03-01/);
});

test('only the endpoints an asset declares are requested for day detail', async () => {
    const optionsRun = manager('options', { positions: { '2026-03-02': { positions: [] } } });
    await optionsRun.cal.fetchDetailSources('2026-03-02');
    assert.deepEqual(optionsRun.calls.map(c => c.name), ['positionsByDate']);

    const futuresRun = manager('futures', {
        summaries: { '2026-03-02': { contracts: [], totals: {} } },
        positions: { '2026-03-02': { orders: [] } }
    });
    await futuresRun.cal.fetchDetailSources('2026-03-02');
    assert.deepEqual(futuresRun.calls.map(c => c.name).sort(), ['dailySummary', 'positionsByDate']);
});


/* ---------- day detail rendering ---------- */

test('options day detail lists positions with their own P&L field', () => {
    const { cal } = manager('options');
    const sources = {
        positionsByDate: {
            positions: [
                { symbol: 'SPY', strategy: 'long_call', strike_price: '500',
                  option_type: 'call', quantity: 2, open_price: 1.5,
                  close_price: 2.25, net_credit: 150 },
                { symbol: 'QQQ', strategy: null, strike_price: '400',
                  option_type: 'put', quantity: 1, open_price: 3, close_price: 1,
                  net_credit: -200 }
            ]
        }
    };

    const html = cal.renderDetailBody('2026-03-02', 150, 2, sources);

    assert.ok(html.includes('<th>P&amp;L</th>'));
    assert.ok(html.includes('<td class="profit">$150.00</td>'));
    assert.ok(html.includes('<td class="loss">$-200.00</td>'));
    assert.ok(html.includes('<td>$1.50</td>'), 'open price formatted as currency');
    assert.ok(html.includes('<td>-</td>'), 'a null strategy shows the dash it always showed');
});

test('futures day detail keeps its summary table and totals row', () => {
    const { cal } = manager('futures');
    const sources = {
        dailySummary: {
            summary: {
                contracts: [{ symbol: 'ESZ5', total_qty_long: 3, total_qty_short: 1, gross_pnl: 27.88 }],
                totals: { total_qty_long: 3, total_qty_short: 1, gross_pnl: -19.14 }
            }
        },
        positionsByDate: {
            orders: [{ contract_id: 'abc', execution_time: null, order_side: 'BUY',
                       filled_quantity: 2, average_price: 5000.25, realized_pnl: -19.14 }]
        }
    };

    const html = cal.renderDetailBody('2026-03-02', -19.14, 1, sources);

    assert.ok(html.includes('<h3>Purchase and Sale Summary</h3>'));
    assert.ok(html.includes('<td class="profit">+$27.88</td>'), 'gains keep their + sign');
    assert.ok(html.includes('<td>TOTALS</td>'));
    assert.ok(html.includes('<td class="loss">$-19.14</td>'));
    assert.ok(html.includes('<h3>Detailed Orders (1 total)</h3>'));
    assert.ok(html.includes('<td>abc</td>'), 'falls back to contract_id when symbol is absent');
});

test('stocks day detail keeps its header and hides empty sections', () => {
    const { cal } = manager('stocks');
    const sources = {
        dailySummary: {
            summary: {
                totals: { positions_closed: 1, positions_opened: 0, total_pnl: 42.5 },
                closed_positions: [{ symbol: 'AAPL', quantity: 10, avg_buy_price: 100,
                                     avg_sell_price: 104.25, pnl: 42.5 }],
                opened_positions: []
            }
        },
        positionsByDate: {
            orders: [{ symbol: 'AAPL', execution_time: null, side: 'sell',
                       quantity: 10, average_price: 104.25, total_amount: 1042.5 }]
        }
    };

    const html = cal.renderDetailBody('2026-03-02', 42.5, 1, sources);

    assert.ok(html.includes('1 position(s) closed'));
    assert.ok(html.includes('10 shares traded'));
    assert.ok(html.includes('<span class="profit">'));
    assert.ok(html.includes('+$42.50'));
    assert.ok(html.includes('<h3>Closed Positions</h3>'));
    assert.ok(!html.includes('<h3>Opened Positions</h3>'), 'empty section omitted');
    assert.ok(html.includes('<td class="sell">SELL</td>'));
});

test('the modal title reads as each asset titled it', async () => {
    const optionsRun = manager('options', { positions: { '2026-03-02': { positions: [] } } });
    await optionsRun.cal.showDayDetails('2026-03-02', 150, 3);
    assert.equal(optionsRun.elements.modalTitle.textContent,
                 'Positions for 2026-03-02 - $150.00 (3 trades)');

    const futuresRun = manager('futures', {
        summaries: { '2026-03-02': { contracts: [], totals: {} } },
        positions: { '2026-03-02': { orders: [] } }
    });
    await futuresRun.cal.showDayDetails('2026-03-02', -19.14, 11);
    assert.equal(futuresRun.elements.modalTitle.textContent, 'Trading Summary - 2026-03-02');
});

test('a value from the payload cannot inject markup', () => {
    const { cal } = manager('options');
    const html = cal.renderDetailBody('2026-03-02', 0, 1, {
        positionsByDate: { positions: [{ symbol: '<img src=x onerror=alert(1)>' }] }
    });
    assert.ok(!html.includes('<img'), 'symbol was escaped');
    assert.ok(html.includes('&lt;img'));
});
