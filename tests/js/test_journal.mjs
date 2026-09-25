/**
 * Journal service, panel, and its place in the calendar.
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

/** A minimal element good enough for the panel's DOM use. */
function element(tag = 'div') {
    const el = {
        tag,
        innerHTML: '',
        value: '',
        textContent: '',
        dataset: {},
        children: [],
        style: {},
        listeners: {},
        appendChild(child) { this.children.push(child); return child; },
        addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); },
        click() { return Promise.all((this.listeners.click || []).map(fn => fn())); },
        querySelector() { return null; },
        querySelectorAll() { return []; }
    };
    return el;
}

/** Load the shared scripts with a fake window and a recording fetch. */
function load({ journals = [], counts = {}, failCreate = null } = {}) {
    const window = {};
    const calls = [];
    let nextId = journals.reduce((max, j) => Math.max(max, j.id), 0) + 1;
    const store = journals.map(j => ({ ...j }));

    const fetchImpl = async (url, init = {}) => {
        const method = (init.method || 'GET').toUpperCase();
        const body = init.body ? JSON.parse(init.body) : null;
        calls.push({ url, method, body });

        const json = (payload, ok = true, status = 200) => ({
            ok, status, json: async () => payload
        });

        if (url.startsWith('/api/journals/count-by-date')) {
            return json({ success: true, counts });
        }
        if (method === 'POST') {
            if (failCreate) return json({ error: failCreate }, false, 400);
            const created = { id: nextId++, ...body, created_at: '2026-03-02T10:00:00' };
            store.push(created);
            return json({ success: true, journal: created });
        }
        if (method === 'PUT') {
            const id = Number(url.split('/').pop());
            const found = store.find(j => j.id === id);
            Object.assign(found, body);
            return json({ success: true, journal: found });
        }
        if (method === 'DELETE') {
            const id = Number(url.split('/').pop());
            store.splice(store.findIndex(j => j.id === id), 1);
            return json({ success: true });
        }
        return json({ success: true, journals: store, count: store.length });
    };

    const context = vm.createContext({
        window, console, URLSearchParams, fetch: fetchImpl,
        document: { getElementById: () => null, querySelector: () => null,
                    querySelectorAll: () => [], createElement: () => element() }
    });
    context.globalThis = context;

    for (const rel of ['asset-config.js', 'services/journal-service.js',
                       'components/journal-panel.js']) {
        vm.runInContext(fs.readFileSync(path.join(SHARED, rel), 'utf8'), context, { filename: rel });
    }

    return { window, calls, store };
}


/* ---------- the service ---------- */

test('a new note is filed against the selected asset and account', async () => {
    const { window, calls } = load();
    window.AssetConfig.setAssetType('futures').setAccount('ACCT7');

    await window.JournalService.create({ date: '2026-03-02', notes: 'Cut it early.' });

    const post = calls.find(c => c.method === 'POST');
    assert.equal(post.body.asset_type, 'futures');
    assert.equal(post.body.account_number, 'ACCT7');
    assert.equal(post.body.journal_type, 'daily', 'a day note unless told otherwise');
});

test('a note about one trade carries its reference', async () => {
    const { window, calls } = load();
    window.AssetConfig.setAssetType('options');

    await window.JournalService.create({
        journal_type: 'position', date: '2026-03-02',
        notes: 'Rolled it out a week.', reference_id: 'pos-9'
    });

    const post = calls.find(c => c.method === 'POST');
    assert.equal(post.body.journal_type, 'position');
    assert.equal(post.body.reference_id, 'pos-9');
});

test('reading a day asks only for that asset and account', async () => {
    const { window, calls } = load();
    window.AssetConfig.setAssetType('stocks').setAccount('ROTH');

    await window.JournalService.list({ date: '2026-03-02' });

    const url = calls.at(-1).url;
    assert.match(url, /date=2026-03-02/);
    assert.match(url, /asset_type=stocks/);
    assert.match(url, /account=ROTH/);
});

test('a caller can ask across assets for a day that spans them', async () => {
    const { window, calls } = load();
    window.AssetConfig.setAssetType('stocks');

    await window.JournalService.list({ date: '2026-03-02', allAssets: true });

    assert.ok(!calls.at(-1).url.includes('asset_type='));
});

test('with no account selected, no account filter is sent', async () => {
    const { window, calls } = load();
    window.AssetConfig.setAssetType('options');

    await window.JournalService.list({ date: '2026-03-02' });

    assert.ok(!calls.at(-1).url.includes('account='));
});

test('a rejected write surfaces the reason it was rejected', async () => {
    const { window } = load({ failCreate: 'notes cannot be empty' });
    window.AssetConfig.setAssetType('options');

    await assert.rejects(
        () => window.JournalService.create({ date: '2026-03-02', notes: '  ' }),
        /notes cannot be empty/
    );
});


/* ---------- the panel ---------- */

function panelWith(entries) {
    const { window, calls, store } = load({ journals: entries });
    window.AssetConfig.setAssetType('options');
    return { panel: new window.JournalPanel(), window, calls, store };
}

test('an empty day says so rather than showing nothing', async () => {
    const { panel } = panelWith([]);
    await panel.load('2026-03-02');
    assert.ok(panel.render().includes('No notes for this day yet.'));
});

test('entries render with their text, type and tags', async () => {
    const { panel } = panelWith([{
        id: 1, journal_type: 'daily', asset_type: 'options', notes: 'Sized down.',
        tags: 'discipline, sizing', created_at: '2026-03-02T10:00:00'
    }]);

    await panel.load('2026-03-02');
    const html = panel.render();

    assert.ok(html.includes('Sized down.'));
    assert.ok(html.includes('<span class="journal-tag">discipline</span>'));
    assert.ok(html.includes('<span class="journal-tag">sizing</span>'));
    assert.ok(html.includes('journal-edit'));
    assert.ok(html.includes('journal-delete'));
});

test('a note is written, then shown, without reloading the page', async () => {
    const { panel, window, calls } = panelWith([]);
    const container = element();
    const notes = element('textarea');
    const tags = element('input');
    const error = element('span');
    const addButton = element('button');

    container.querySelector = (selector) => ({
        '.journal-add': addButton,
        '#journalNotes': notes,
        '#journalTags': tags,
        '#journalError': error
    }[selector] || null);

    await panel.load('2026-03-02');
    panel.mount(container);

    notes.value = 'Held through the gap.';
    tags.value = 'patience';
    await addButton.click();

    const post = calls.find(c => c.method === 'POST');
    assert.equal(post.body.notes, 'Held through the gap.');
    assert.equal(post.body.tags, 'patience');
    assert.equal(panel.entries.length, 1, 'the panel reloaded after writing');
});

test('an empty note is refused before it reaches the server', async () => {
    const { panel, calls } = panelWith([]);
    const container = element();
    const notes = element('textarea');
    const error = element('span');
    const addButton = element('button');

    container.querySelector = (selector) => ({
        '.journal-add': addButton, '#journalNotes': notes, '#journalError': error
    }[selector] || null);

    await panel.load('2026-03-02');
    panel.mount(container);

    notes.value = '   ';
    await addButton.click();

    assert.equal(error.textContent, 'Write something first.');
    assert.equal(calls.filter(c => c.method === 'POST').length, 0);
});

test('editing swaps the entry for a form holding its current text', async () => {
    const { panel } = panelWith([{
        id: 4, journal_type: 'daily', notes: 'First thought.', tags: 'a',
        created_at: '2026-03-02T10:00:00'
    }]);

    await panel.load('2026-03-02');
    panel.editingId = 4;
    const html = panel.render();

    assert.ok(html.includes('journal-entry-editing'));
    assert.ok(html.includes('First thought.'));
    assert.ok(html.includes('journal-save'));
});

test('deleting removes it from the day', async () => {
    const { panel, store } = panelWith([
        { id: 4, journal_type: 'daily', notes: 'One.', created_at: '2026-03-02T10:00:00' },
        { id: 5, journal_type: 'daily', notes: 'Two.', created_at: '2026-03-02T11:00:00' }
    ]);
    const container = element();
    const deleteButton = element('button');
    deleteButton.dataset.journalId = '4';
    container.querySelectorAll = (selector) =>
        selector === '.journal-delete' ? [deleteButton] : [];

    await panel.load('2026-03-02');
    panel.mount(container);
    await deleteButton.click();

    assert.equal(store.length, 1);
    assert.equal(panel.entries.length, 1);
    assert.equal(panel.entries[0].notes, 'Two.');
});

test('a note cannot inject markup into the panel', async () => {
    const { panel } = panelWith([{
        id: 1, journal_type: 'daily', notes: '<img src=x onerror=alert(1)>',
        tags: '<b>bold</b>', created_at: '2026-03-02T10:00:00'
    }]);

    await panel.load('2026-03-02');
    const html = panel.render();

    assert.ok(!html.includes('<img'));
    assert.ok(!html.includes('<b>bold'));
    assert.ok(html.includes('&lt;img'));
});

test('a failed load leaves the panel usable rather than broken', async () => {
    const { window } = load();
    window.AssetConfig.setAssetType('options');
    const panel = new window.JournalPanel({
        service: { list: async () => { throw new Error('offline'); } }
    });

    await panel.load('2026-03-02');

    assert.equal(panel.entries.length, 0);
    assert.ok(panel.render().includes('No notes for this day yet.'));
});


/* ---------- the calendar's use of it ---------- */

function calendarWith(counts) {
    const window = {};
    const context = vm.createContext({
        window, console, URLSearchParams,
        document: { getElementById: () => null, querySelector: () => null,
                    querySelectorAll: () => [], createElement: () => element() },
        fetch: async () => { throw new Error('should not fetch directly'); }
    });
    context.globalThis = context;
    for (const rel of ['asset-config.js', 'services/api-service.js', 'calendar.js']) {
        vm.runInContext(fs.readFileSync(path.join(SHARED, rel), 'utf8'), context, { filename: rel });
    }
    window.AssetConfig.setAssetType('options');

    const cal = new window.CalendarManager({
        assetType: 'options',
        api: {
            fetchDailyPnl: async () => ({
                success: true,
                daily_pnl: { '2026-03-02': { pnl: 100, count: 2 },
                             '2026-03-09': { pnl: -50, count: 1 } }
            })
        },
        journals: { countsByDate: async () => counts }
    });
    return { cal, window };
}

test('a day with notes carries a marker; a day without does not', async () => {
    const { cal } = calendarWith({ '2026-03-02': 2 });

    const events = await cal.buildEvents('2026-03-01', '2026-03-31');
    const byDate = Object.fromEntries(events.map(e => [e.id, e]));

    assert.equal(byDate['2026-03-02'].extendedProps.journals, 2);
    assert.equal(byDate['2026-03-09'].extendedProps.journals, 0);

    assert.ok(cal.renderEventContent({ event: byDate['2026-03-02'] }).html
                 .includes('pnl-journal-marker'));
    assert.ok(!cal.renderEventContent({ event: byDate['2026-03-09'] }).html
                 .includes('pnl-journal-marker'));
});

test('the calendar still draws when journal counts cannot be fetched', async () => {
    const { window } = calendarWith({});
    const cal = new window.CalendarManager({
        assetType: 'options',
        api: { fetchDailyPnl: async () => ({ success: true,
                 daily_pnl: { '2026-03-02': { pnl: 100, count: 2 } } }) },
        journals: { countsByDate: async () => { throw new Error('offline'); } }
    });

    const events = await cal.buildEvents('2026-03-01', '2026-03-31');

    assert.equal(events.length, 1, 'the day is still drawn');
    assert.equal(events[0].extendedProps.journals, 0);
});
