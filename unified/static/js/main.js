/**
 * The unified dashboard.
 *
 * Holds no asset knowledge of its own: it asks the server which assets exist,
 * tells AssetConfig which one is selected, and lets the shared components
 * render. Switching asset or account re-fetches and re-renders the same views.
 */
(function () {
    'use strict';

    const state = {
        assetType: null,
        account: null,
        data: null,
        assets: [],
        accounts: []
    };

    const els = {};

    function cache() {
        els.loading = document.getElementById('loadingIndicator');
        els.error = document.getElementById('errorMessage');
        els.content = document.getElementById('dashboardContent');
        els.assetSwitcher = document.getElementById('assetSwitcher');
        els.accountSelect = document.getElementById('accountSelect');
        els.summary = document.getElementById('summary');
        els.openPositions = document.getElementById('openPositions');
        els.closedPositions = document.getElementById('closedPositions');
        els.allOrders = document.getElementById('allOrders');
    }

    function showLoading(message) {
        els.loading.textContent = message || 'Loading...';
        els.loading.style.display = 'block';
        els.error.style.display = 'none';
        els.content.style.display = 'none';
    }

    function showError(message) {
        els.error.textContent = message;
        els.error.style.display = 'block';
        els.loading.style.display = 'none';
    }

    function showContent() {
        els.loading.style.display = 'none';
        els.error.style.display = 'none';
        els.content.style.display = 'block';
    }

    /** Accounts the stored data knows about, for the account switcher. */
    async function loadAccounts() {
        const response = await fetch('/api/accounts');
        const payload = await response.json();
        if (!payload.success) throw new Error(payload.error || 'Failed to list accounts');
        return payload;
    }

    function renderAccountSwitcher(accounts) {
        const options = ['<option value="">All accounts</option>'];
        accounts.forEach(account => {
            options.push(`<option value="${account}">${account}</option>`);
        });
        els.accountSelect.innerHTML = options.join('');
        els.accountSelect.value = state.account || '';

        // Nothing to choose between until orders record an account
        els.accountSelect.disabled = accounts.length === 0;
        els.accountSelect.title = accounts.length === 0
            ? 'No accounts recorded yet; refresh an asset to record one'
            : '';
    }

    /** Which assets the server serves, and their labels. */
    async function loadAssets() {
        const response = await fetch('/api/assets');
        const payload = await response.json();
        if (!payload.success) throw new Error(payload.error || 'Failed to list assets');
        return payload.assets;
    }

    function renderAssetSwitcher() {
        els.assetSwitcher.innerHTML = state.assets.map(asset => `
            <button type="button" class="asset-button${asset.asset_type === state.assetType ? ' active' : ''}"
                    data-asset-type="${asset.asset_type}">${asset.label}</button>
        `).join('');

        els.assetSwitcher.querySelectorAll('.asset-button').forEach(button => {
            button.addEventListener('click', () => selectAsset(button.dataset.assetType));
        });
    }

    async function selectAsset(assetType) {
        if (assetType === state.assetType) return;
        state.assetType = assetType;
        window.AssetConfig.setAssetType(assetType);
        renderAssetSwitcher();
        await loadAndRender();
    }

    async function selectAccount(account) {
        state.account = account || null;
        window.AssetConfig.setAccount(state.account);
        await loadAndRender();
    }

    /** Fetch the selected asset and account, then render every view. */
    async function loadAndRender() {
        showLoading(`Loading ${state.assetType}...`);

        try {
            state.data = await window.ApiService.fetchData();
            render();
            showContent();
        } catch (error) {
            console.error('Failed to load data:', error);
            showError(`Could not load ${state.assetType}: ${error.message}`);
        }
    }

    function render() {
        renderSummary();
        renderPositions();
        renderOrders();
        renderBySymbol();
        refreshCalendarIfOpen();
    }

    function renderSummary() {
        window.DataManager.data = state.data;
        const stats = window.DataManager.getSummaryStats();
        if (!stats || typeof window.SummaryPanel === 'undefined') return;

        els.summary.innerHTML = '';
        window.SummaryPanel.render(els.summary, stats);
    }

    function positionTable(container, type) {
        return new window.PositionTable({
            container,
            type,
            assetType: state.assetType
        });
    }

    function renderPositions() {
        // Tables are rebuilt on every switch: their columns belong to the asset
        positionTable(els.openPositions, 'open').setData(state.data.open_positions || []);

        const closed = [
            ...(state.data.closed_positions || []),
            ...(state.data.expired_positions || [])
        ];
        positionTable(els.closedPositions, 'closed').setData(closed);
    }

    function renderOrders() {
        positionTable(els.allOrders, 'orders').setData(state.data.all_orders || []);
    }

    function renderBySymbol() {
        if (!window.bySymbolView) {
            window.bySymbolView = new window.BySymbolView({ assetType: state.assetType });
            window.BySymbolView.setupUi();
        }
        window.bySymbolView.assetType = state.assetType;
        window.bySymbolView.render(state.data);
    }

    function refreshCalendarIfOpen() {
        if (window.calendarManagerInstance) {
            window.calendarManagerInstance.assetType = state.assetType;
            window.calendarManagerInstance.refreshCalendar();
        }
    }

    function switchTab(name) {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

        const tab = document.querySelector(`[data-tab="${name}"]`);
        const content = document.getElementById(name);
        if (tab) tab.classList.add('active');
        if (content) content.classList.add('active');

        if (name === 'calendar') {
            if (!window.calendarManagerInstance) {
                window.calendarManagerInstance = new window.CalendarManager({
                    assetType: state.assetType
                });
                window.calendarManagerInstance.initCalendar();
            } else {
                window.calendarManagerInstance.refreshCalendar();
            }
        }
    }

    async function start() {
        cache();
        showLoading('Loading...');

        try {
            state.assets = await loadAssets();
            const accounts = await loadAccounts();
            state.accounts = accounts.accounts;
            renderAccountSwitcher(state.accounts);
        } catch (error) {
            showError(`Could not reach the server: ${error.message}`);
            return;
        }

        if (state.assets.length === 0) {
            showError('No asset types are configured.');
            return;
        }

        document.querySelectorAll('.tab').forEach(tab => {
            tab.addEventListener('click', () => switchTab(tab.dataset.tab));
        });

        els.accountSelect.addEventListener('change', () => selectAccount(els.accountSelect.value));

        state.assetType = state.assets[0].asset_type;
        window.AssetConfig.setAssetType(state.assetType);
        renderAssetSwitcher();
        await loadAndRender();
    }

    window.unifiedDashboard = {
        state, selectAsset, selectAccount, switchTab, start,
        renderAccountSwitcher, loadAccounts
    };

    document.addEventListener('DOMContentLoaded', start);
})();
