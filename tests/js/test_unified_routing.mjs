/**
 * The shared config serves two apps: the standalone dashboards, whose paths are
 * what they have always been, and the unified app, where every asset sits
 * behind /api/<asset_type>/...
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

function load({ fetchImpl = null } = {}) {
    const window = {};
    const context = vm.createContext({
        window, console, URLSearchParams, fetch: fetchImpl,
        document: { querySelector: () => null, querySelectorAll: () => [] }
    });
    context.globalThis = context;
    for (const rel of ['asset-config.js', 'services/api-service.js']) {
        vm.runInContext(fs.readFileSync(path.join(SHARED, rel), 'utf8'), context, { filename: rel });
    }
    return window;
}

function recordingFetch() {
    const calls = [];
    const impl = async (url, init) => {
        calls.push({ url, init });
        return { ok: true, status: 200, json: async () => ({ success: true }) };
    };
    impl.calls = calls;
    return impl;
}

const ASSETS = ['options', 'stocks', 'futures'];


test('standalone routing keeps the paths each dashboard already serves', () => {
    const { AssetConfig } = load();

    AssetConfig.setAssetType('options');
    assert.equal(AssetConfig.url('data'), '/api/options');
    assert.equal(AssetConfig.url('dailyPnl'), '/api/daily-pnl');
    assert.equal(AssetConfig.url('positionsByDate', { date: '2026-03-02' }),
                 '/api/positions/date/2026-03-02');

    AssetConfig.setAssetType('stocks');
    assert.equal(AssetConfig.url('data'), '/api/stocks');
    assert.equal(AssetConfig.url('allTradingDates'), '/api/all-trading-dates');
});

test('unified routing puts every asset behind its own prefix', () => {
    const { AssetConfig } = load();
    AssetConfig.setRouting('unified');

    for (const asset of ASSETS) {
        AssetConfig.setAssetType(asset);
        assert.equal(AssetConfig.url('data'), `/api/${asset}/data`);
        assert.equal(AssetConfig.url('dailyPnl'), `/api/${asset}/daily-pnl`);
        assert.equal(AssetConfig.url('positionsByDate', { date: '2026-03-02' }),
                     `/api/${asset}/positions/date/2026-03-02`);
    }
});

test('the standalone dashboards are unaffected by the unified app existing', () => {
    // Two pages, two registries: one switching routing must not move the other
    const standalone = load().AssetConfig.setAssetType('futures');
    const unified = load().AssetConfig.setRouting('unified').setAssetType('futures');

    assert.equal(standalone.url('data'), '/api/futures');
    assert.equal(unified.url('data'), '/api/futures/data');
});

test('an unknown routing mode is refused', () => {
    const { AssetConfig } = load();
    assert.throws(() => AssetConfig.setRouting('sideways'), /Unknown routing/);
});

test('what an asset does not serve is unavailable in either app', () => {
    const { AssetConfig } = load();

    AssetConfig.setAssetType('futures');
    assert.throws(() => AssetConfig.url('allTradingDates'), /has no endpoint/);

    AssetConfig.setRouting('unified');
    assert.throws(() => AssetConfig.url('allTradingDates'), /has no endpoint/,
                  'the unified prefix must not invent an endpoint');

    AssetConfig.setAssetType('options');
    assert.throws(() => AssetConfig.url('dailySummary', { date: '2026-03-02' }), /has no endpoint/);
});

test('switching asset in the unified app changes only the prefix', async () => {
    const fetchImpl = recordingFetch();
    const { AssetConfig, ApiService } = load({ fetchImpl });
    AssetConfig.setRouting('unified').setAssetType('options');

    await ApiService.fetchData();
    AssetConfig.setAssetType('futures');
    await ApiService.fetchData();

    assert.deepEqual(Array.from(fetchImpl.calls.map(c => c.url)),
                     ['/api/options/data', '/api/futures/data']);
});

test('the account still rides along in the unified app', async () => {
    const fetchImpl = recordingFetch();
    const { AssetConfig, ApiService } = load({ fetchImpl });
    AssetConfig.setRouting('unified').setAssetType('stocks').setAccount('ROTH');

    await ApiService.fetchData();
    await ApiService.fetchDailyPnl('2026-01-01', '2026-03-31');
    await ApiService.fetchAllTradingDates();

    for (const call of fetchImpl.calls) {
        assert.match(call.url, /^\/api\/stocks\//, `${call.url} lost the asset prefix`);
        assert.match(call.url, /account=ROTH/, `${call.url} lost the account`);
    }
});

test('every endpoint an asset serves has a unified path', () => {
    const { AssetConfig, ASSET_CONFIGS, UNIFIED_PATHS } = load();
    AssetConfig.setRouting('unified');

    for (const asset of ASSETS) {
        for (const [name, standalonePath] of Object.entries(ASSET_CONFIGS[asset].endpoints)) {
            if (!standalonePath) continue;
            assert.ok(UNIFIED_PATHS[name],
                      `${asset} serves ${name} but the unified app has no path for it`);
        }
    }
});
