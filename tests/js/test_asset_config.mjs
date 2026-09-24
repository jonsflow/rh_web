/**
 * Tests for the asset/account contract the shared frontend is built on.
 *
 * Node's built-in test runner, no dependencies, no network. The browser files
 * are plain scripts that assign onto `window`, so a stub window is enough.
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

/** Load the shared browser scripts into a fresh stubbed window. */
function loadShared({ fetchImpl = null } = {}) {
    const window = {};
    const context = vm.createContext({
        window,
        console,
        fetch: fetchImpl,
        URLSearchParams,
        document: { querySelector: () => null },
    });
    context.globalThis = context;

    for (const rel of ['asset-config.js', 'services/api-service.js',
                       'services/data-manager.js', 'components/position-table.js']) {
        vm.runInContext(fs.readFileSync(path.join(SHARED, rel), 'utf8'), context,
                        { filename: rel });
    }
    return window;
}

/** A fetch that records calls and replays canned JSON. */
function recordingFetch(payload = { ok: true }) {
    const calls = [];
    const impl = async (url, init) => {
        calls.push({ url, init });
        return { ok: true, status: 200, json: async () => payload };
    };
    impl.calls = calls;
    return impl;
}

const ASSETS = ['options', 'stocks', 'futures'];


test('every asset is configured, and can be listed for a switcher', () => {
    const { AssetConfig } = loadShared();
    // Array.from re-homes the sandbox's arrays into this realm, so deepEqual compares values
    assert.deepEqual(Array.from(AssetConfig.list().map(a => a.assetType)).sort(),
                     [...ASSETS].sort());
    for (const asset of AssetConfig.list()) {
        assert.ok(asset.label, `${asset.assetType} needs a label for the switcher`);
    }
});

test('an unknown asset type is rejected rather than silently empty', () => {
    const { AssetConfig } = loadShared();
    assert.throws(() => AssetConfig.setAssetType('crypto'), /No configuration for asset type/);
});

test('every asset maps the same field roles, so shared code never names a column', () => {
    const { AssetConfig } = loadShared();
    const roles = ['symbol', 'pnl', 'openValue', 'openDate', 'closeDate', 'quantity'];
    for (const asset of ASSETS) {
        for (const role of roles) {
            assert.ok(AssetConfig.field(role, asset),
                      `${asset} has no field for role ${role}`);
        }
    }
    // The point of the mapping: the three assets call P&L three different things
    assert.equal(AssetConfig.field('pnl', 'options'), 'net_credit');
    assert.equal(AssetConfig.field('pnl', 'stocks'), 'pnl');
    assert.equal(AssetConfig.field('pnl', 'futures'), 'realized_pnl');
});

test('every asset offers the same table types, for feature parity', () => {
    const { AssetConfig } = loadShared();
    for (const asset of ASSETS) {
        for (const type of ['open', 'closed', 'expired', 'orders']) {
            const columns = AssetConfig.columns(type, asset);
            assert.ok(columns.length > 0, `${asset} has no ${type} columns`);
            for (const column of columns) {
                assert.ok(column.key, `${asset} ${type} column missing key`);
                assert.ok(column.label, `${asset} ${type} column missing label`);
            }
        }
    }
});

test("every asset's closed table shows P&L, using that asset's own field", () => {
    const { AssetConfig } = loadShared();
    for (const asset of ASSETS) {
        const pnlField = AssetConfig.field('pnl', asset);
        const keys = AssetConfig.columns('closed', asset).map(c => c.key);
        assert.ok(keys.includes(pnlField),
                  `${asset} closed table does not show its P&L field ${pnlField}`);
    }
});

test('columns are copies, so one table cannot mutate another asset\'s config', () => {
    const { AssetConfig } = loadShared();
    AssetConfig.columns('open', 'options').push({ key: 'junk', label: 'Junk' });
    assert.ok(!AssetConfig.columns('open', 'options').some(c => c.key === 'junk'));
});

test('switching asset changes where requests go, with no code change', async () => {
    const fetchImpl = recordingFetch();
    const { AssetConfig, ApiService } = loadShared({ fetchImpl });

    AssetConfig.setAssetType('options');
    await ApiService.fetchData();
    assert.equal(fetchImpl.calls.at(-1).url, '/api/options');

    AssetConfig.setAssetType('futures');
    await ApiService.fetchData();
    assert.equal(fetchImpl.calls.at(-1).url, '/api/futures');

    AssetConfig.setAssetType('stocks');
    await ApiService.fetchData();
    assert.equal(fetchImpl.calls.at(-1).url, '/api/stocks');
});

test('one asset can be requested without changing the page selection', async () => {
    const fetchImpl = recordingFetch();
    const { AssetConfig, ApiService } = loadShared({ fetchImpl });

    AssetConfig.setAssetType('options');
    await ApiService.fetchData({ assetType: 'futures' });

    assert.equal(fetchImpl.calls.at(-1).url, '/api/futures');
    assert.equal(AssetConfig.assetType, 'options', 'selection must not be mutated');
});

test('selecting an account sends it on every request', async () => {
    const fetchImpl = recordingFetch();
    const { AssetConfig, ApiService } = loadShared({ fetchImpl });
    AssetConfig.setAssetType('options').setAccount('ACCT123');

    await ApiService.fetchData();
    await ApiService.fetchDailyPnl('2026-01-01', '2026-01-31');
    await ApiService.fetchPositionsByDate('2026-01-15');
    await ApiService.updateData(true);

    for (const call of fetchImpl.calls) {
        assert.match(call.url, /[?&]account=ACCT123\b/, `${call.url} lost the account`);
    }
});

test('no account selected means no account parameter, as the backend behaves today', async () => {
    const fetchImpl = recordingFetch();
    const { AssetConfig, ApiService } = loadShared({ fetchImpl });
    AssetConfig.setAssetType('options');

    await ApiService.fetchData();
    await ApiService.fetchDailyPnl();

    for (const call of fetchImpl.calls) {
        assert.ok(!call.url.includes('account='), `${call.url} sent an empty account`);
    }
    // and the no-date call stays a bare path, as before
    assert.equal(fetchImpl.calls.at(-1).url, '/api/daily-pnl');
});

test('switching account re-requests the same asset', async () => {
    const fetchImpl = recordingFetch();
    const { AssetConfig, ApiService } = loadShared({ fetchImpl });
    AssetConfig.setAssetType('futures');

    await ApiService.fetchData();
    AssetConfig.setAccount('ROTH');
    await ApiService.fetchData();

    assert.equal(fetchImpl.calls[0].url, '/api/futures');
    assert.equal(fetchImpl.calls[1].url, '/api/futures?account=ROTH');
});

test('a selection change notifies listeners, so a switcher can re-render', () => {
    const { AssetConfig } = loadShared();
    const seen = [];
    AssetConfig.onChange(state => seen.push({ ...state }));

    AssetConfig.setAssetType('stocks');
    AssetConfig.setAccount('IRA');

    assert.deepEqual(seen, [
        { assetType: 'stocks', account: null },
        { assetType: 'stocks', account: 'IRA' },
    ]);
});

test('date parameters land in the path, and are dropped when absent', async () => {
    const fetchImpl = recordingFetch();
    const { AssetConfig, ApiService } = loadShared({ fetchImpl });
    AssetConfig.setAssetType('options');

    await ApiService.fetchPositionsByDate('2026-01-15');
    assert.equal(fetchImpl.calls.at(-1).url, '/api/positions/date/2026-01-15');

    await ApiService.fetchDailyPnl('2026-01-01', null);
    assert.equal(fetchImpl.calls.at(-1).url, '/api/daily-pnl?start_date=2026-01-01');
});

test('an endpoint an asset does not serve fails loudly, not with a 404 fetch', () => {
    const { AssetConfig } = loadShared();
    assert.equal(AssetConfig.has('dailySummary', 'stocks'), true);
    assert.equal(AssetConfig.has('dailySummary', 'options'), false);
    assert.throws(() => AssetConfig.url('dailySummary', { date: '2026-01-01' }, 'options'),
                  /has no endpoint/);
});

test('a missing path parameter is caught instead of requesting a literal {date}', () => {
    const { AssetConfig } = loadShared();
    assert.throws(() => AssetConfig.url('positionsByDate', {}, 'options'),
                  /missing parameter: date/);
});

test('summary P&L is read through the asset\'s field, for each asset', async () => {
    for (const [asset, pnlField, openValueField] of [
        ['options', 'net_credit', 'open_premium'],
        ['stocks', 'pnl', 'cost'],
        ['futures', 'realized_pnl', 'open_value'],
    ]) {
        const payload = {
            open_positions: [{ [openValueField]: 100 }, { [openValueField]: 50 }],
            closed_positions: [{ [pnlField]: 30 }, { [pnlField]: -10 }],
            expired_positions: [{ [pnlField]: 5 }],
        };
        const { AssetConfig, DataManager } = loadShared({ fetchImpl: recordingFetch(payload) });
        AssetConfig.setAssetType(asset);

        await DataManager.loadData();
        const stats = DataManager.getSummaryStats();

        assert.equal(stats.closedPL, 20, `${asset} closed P&L`);
        assert.equal(stats.expiredPL, 5, `${asset} expired P&L`);
        assert.equal(stats.totalPL, 25, `${asset} total P&L`);
        assert.equal(stats.openValue, 150, `${asset} open value`);
        assert.equal(stats.totalTrades, 5, `${asset} trade count`);
    }
});

test('a null P&L is skipped rather than summed as zero-ish garbage', async () => {
    const payload = {
        open_positions: [],
        closed_positions: [{ net_credit: 40 }, { net_credit: null }, {}],
        expired_positions: [],
    };
    const { AssetConfig, DataManager } = loadShared({ fetchImpl: recordingFetch(payload) });
    AssetConfig.setAssetType('options');

    await DataManager.loadData();
    assert.equal(DataManager.getSummaryStats().closedPL, 40);
});

test('filter facets come from the asset, not from options field names', async () => {
    const payload = {
        open_positions: [{ symbol: 'SPY', option_type: 'call', strategy: 'long', direction: 'debit',
                           open_date: '2026-01-02', close_date: null }],
        closed_positions: [{ symbol: 'QQQ', option_type: 'put', strategy: 'long', direction: 'credit',
                             open_date: '2026-01-05', close_date: '2026-01-09' }],
        expired_positions: [],
    };
    const { AssetConfig, DataManager } = loadShared({ fetchImpl: recordingFetch(payload) });
    AssetConfig.setAssetType('options');

    await DataManager.loadData();
    const options = DataManager.getFilterOptions();

    assert.deepEqual(Array.from(options.facets.symbol), ['QQQ', 'SPY']);
    assert.deepEqual(Array.from(options.facets.option_type), ['call', 'put']);
    assert.equal(options.dateRange.min, '2026-01-02');
});

test('a table renders the columns its asset declares', () => {
    const window = loadShared();
    window.AssetConfig.setAssetType('futures');

    const container = { innerHTML: '', querySelectorAll: () => [] };
    const table = new window.PositionTable({ container, type: 'closed' });

    assert.deepEqual(table.columns.map(c => c.key),
                     window.AssetConfig.columns('closed', 'futures').map(c => c.key));
    assert.ok(table.columns.some(c => c.key === 'realized_pnl'),
              'futures table must show realized_pnl, not net_credit');
});

test('a table can be pinned to one asset while the page shows another', () => {
    const window = loadShared();
    window.AssetConfig.setAssetType('options');

    const container = { innerHTML: '', querySelectorAll: () => [] };
    const table = new window.PositionTable({ container, type: 'closed', assetType: 'stocks' });

    assert.ok(table.columns.some(c => c.key === 'pnl'));
    assert.ok(!table.columns.some(c => c.key === 'net_credit'));
});

test('explicit columns still override the asset config', () => {
    const window = loadShared();
    window.AssetConfig.setAssetType('options');

    const container = { innerHTML: '', querySelectorAll: () => [] };
    const columns = [{ key: 'only', label: 'Only' }];
    const table = new window.PositionTable({ container, type: 'closed', columns });

    assert.deepEqual(table.columns, columns);
});
