/**
 * Per-asset configuration.
 *
 * The shared components know nothing about options, stocks or futures. They ask
 * this file what a thing is called and where to get it, so one renderer serves
 * every asset and the same features appear across all of them.
 *
 * Two things every config carries:
 *   endpoints  - where the data lives, so switching asset is a config lookup
 *   fields     - what the payload calls P&L, symbol and the rest, since the
 *                three backends use different names for the same figure
 *
 * Endpoint paths are the ones each dashboard serves today. When the apps merge
 * behind /api/<asset_type>/..., these strings change here and nowhere else.
 */

const ASSET_CONFIGS = {
    options: {
        assetType: 'options',
        label: 'Options',
        endpoints: {
            data: '/api/options',
            update: '/api/update',
            dailyPnl: '/api/daily-pnl',
            positionsByDate: '/api/positions/date/{date}',
            dailySummary: null,
            allTradingDates: null
        },
        fields: {
            symbol: 'symbol',
            pnl: 'net_credit',
            openValue: 'open_premium',
            openDate: 'open_date',
            closeDate: 'close_date',
            quantity: 'quantity'
        },
        // Facets offered as filters, in the order they appear
        facets: ['symbol', 'strategy', 'direction', 'option_type'],
        columns: {
            base: [
                { key: 'symbol', label: 'Symbol', sortable: true },
                { key: 'strategy', label: 'Strategy', sortable: true },
                { key: 'direction', label: 'Direction', sortable: true },
                { key: 'option_type', label: 'Type', sortable: true },
                { key: 'strike_price', label: 'Strike', sortable: true },
                { key: 'expiration_date', label: 'Expiration', sortable: true, type: 'date' }
            ],
            open: [
                { key: 'quantity', label: 'Qty', sortable: true, type: 'number' },
                { key: 'open_premium', label: 'Premium', sortable: true, type: 'currency' },
                { key: 'open_date', label: 'Opened', sortable: true, type: 'date' }
            ],
            closed: [
                { key: 'quantity', label: 'Qty', sortable: true, type: 'number' },
                { key: 'net_credit', label: 'P&L', sortable: true, type: 'pnl' },
                { key: 'open_date', label: 'Opened', sortable: true, type: 'date' },
                { key: 'close_date', label: 'Closed', sortable: true, type: 'date' }
            ],
            orders: [
                { key: 'symbol', label: 'Symbol', sortable: true },
                { key: 'created_at', label: 'Date', sortable: true, type: 'datetime' },
                { key: 'position_effect', label: 'Effect', sortable: true },
                { key: 'strategy', label: 'Strategy', sortable: true },
                { key: 'direction', label: 'Direction', sortable: true },
                { key: 'option_type', label: 'Type', sortable: true },
                { key: 'strike_price', label: 'Strike', sortable: true },
                { key: 'expiration_date', label: 'Expiration', sortable: true, type: 'date' },
                { key: 'quantity', label: 'Qty', sortable: true, type: 'number' },
                { key: 'premium', label: 'Premium', sortable: true, type: 'currency' }
            ]
        }
    },

    stocks: {
        assetType: 'stocks',
        label: 'Stocks',
        endpoints: {
            data: '/api/stocks',
            update: '/api/update',
            dailyPnl: '/api/daily-pnl',
            positionsByDate: '/api/positions/date/{date}',
            dailySummary: '/api/daily-summary/{date}',
            allTradingDates: '/api/all-trading-dates'
        },
        fields: {
            symbol: 'symbol',
            pnl: 'pnl',
            openValue: 'cost',
            openDate: 'buy_date',
            closeDate: 'sell_date',
            quantity: 'quantity'
        },
        facets: ['symbol', 'side'],
        columns: {
            base: [
                { key: 'symbol', label: 'Symbol', sortable: true }
            ],
            open: [
                { key: 'quantity', label: 'Shares', sortable: true, type: 'number' },
                { key: 'average_price', label: 'Avg Cost', sortable: true, type: 'currency' },
                { key: 'cost', label: 'Cost Basis', sortable: true, type: 'currency' }
            ],
            closed: [
                { key: 'quantity', label: 'Shares', sortable: true, type: 'number' },
                { key: 'cost', label: 'Cost', sortable: true, type: 'currency' },
                { key: 'proceeds', label: 'Proceeds', sortable: true, type: 'currency' },
                { key: 'pnl', label: 'P&L', sortable: true, type: 'pnl' },
                { key: 'buy_date', label: 'Bought', sortable: true, type: 'date' },
                { key: 'sell_date', label: 'Sold', sortable: true, type: 'date' }
            ],
            orders: [
                { key: 'symbol', label: 'Symbol', sortable: true },
                { key: 'trade_date', label: 'Date', sortable: true, type: 'date' },
                { key: 'side', label: 'Side', sortable: true },
                { key: 'quantity', label: 'Shares', sortable: true, type: 'number' },
                { key: 'average_price', label: 'Price', sortable: true, type: 'currency' },
                { key: 'total_amount', label: 'Amount', sortable: true, type: 'currency' }
            ]
        }
    },

    futures: {
        assetType: 'futures',
        label: 'Futures',
        endpoints: {
            data: '/api/futures',
            update: '/api/update',
            dailyPnl: '/api/daily-pnl',
            positionsByDate: '/api/positions/date/{date}',
            dailySummary: '/api/daily-summary/{date}',
            allTradingDates: null
        },
        fields: {
            symbol: 'display_symbol',
            pnl: 'realized_pnl',
            openValue: 'open_value',
            openDate: 'open_date',
            closeDate: 'close_date',
            quantity: 'quantity'
        },
        facets: ['display_symbol'],
        columns: {
            base: [
                { key: 'display_symbol', label: 'Contract', sortable: true }
            ],
            open: [
                { key: 'quantity', label: 'Qty', sortable: true, type: 'number' },
                { key: 'open_price', label: 'Open Price', sortable: true, type: 'currency' },
                { key: 'open_value', label: 'Open Value', sortable: true, type: 'currency' },
                { key: 'open_date', label: 'Opened', sortable: true, type: 'date' }
            ],
            closed: [
                { key: 'quantity', label: 'Qty', sortable: true, type: 'number' },
                { key: 'realized_pnl', label: 'P&L', sortable: true, type: 'pnl' },
                { key: 'total_fees', label: 'Fees', sortable: true, type: 'currency' },
                { key: 'open_date', label: 'Opened', sortable: true, type: 'date' },
                { key: 'close_date', label: 'Closed', sortable: true, type: 'date' }
            ],
            orders: [
                { key: 'display_symbol', label: 'Contract', sortable: true },
                { key: 'created_at', label: 'Date', sortable: true, type: 'datetime' },
                { key: 'side', label: 'Side', sortable: true },
                { key: 'quantity', label: 'Qty', sortable: true, type: 'number' },
                { key: 'price', label: 'Price', sortable: true, type: 'currency' },
                { key: 'realized_pnl', label: 'P&L', sortable: true, type: 'pnl' }
            ]
        }
    }
};


class AssetConfigRegistry {
    constructor(configs) {
        this.configs = configs;
        // The asset the page is showing. A page serving one asset sets it once;
        // a page with an asset switcher sets it on each change.
        this.assetType = null;
        // The account being viewed. null means every account the backend
        // returns, which is what it returns today.
        this.account = null;
        this.listeners = [];
    }

    /** Asset types available, for building a switcher. */
    list() {
        return Object.keys(this.configs).map(key => ({
            assetType: key,
            label: this.configs[key].label
        }));
    }

    /**
     * Config for an asset type, or for the current selection when omitted.
     * @param {string} [assetType]
     */
    get(assetType = null) {
        const key = assetType || this.assetType;
        const config = this.configs[key];
        if (!config) {
            throw new Error(`No configuration for asset type: ${key}`);
        }
        return config;
    }

    /** Declare which asset this page is showing. */
    setAssetType(assetType) {
        this.get(assetType);  // throws on an unknown asset type
        this.assetType = assetType;
        this._notify();
        return this;
    }

    /** Set the account being viewed; null for all accounts. */
    setAccount(account) {
        this.account = account || null;
        this._notify();
        return this;
    }

    /** Field name this asset uses for a role, e.g. field('pnl'). */
    field(role, assetType = null) {
        const name = this.get(assetType).fields[role];
        if (!name) {
            throw new Error(`Asset ${assetType || this.assetType} has no field for role: ${role}`);
        }
        return name;
    }

    /** Read the value of a role off a record, e.g. value(position, 'pnl'). */
    value(record, role, assetType = null) {
        return record ? record[this.field(role, assetType)] : undefined;
    }

    /** Facet field names offered as filters. */
    facets(assetType = null) {
        return [...(this.get(assetType).facets || [])];
    }

    /**
     * Columns for a table, base columns first.
     * @param {string} type - 'open', 'closed', 'expired' or 'orders'
     */
    columns(type, assetType = null) {
        const columns = this.get(assetType).columns;
        if (type === 'orders') {
            return [...columns.orders];
        }
        // expired positions are closed positions that closed at expiry
        const tail = columns[type === 'expired' ? 'closed' : type];
        return tail ? [...columns.base, ...tail] : [...columns.base];
    }

    /**
     * Resolved URL for an endpoint, with the current account applied.
     * @param {string} name - key in the asset's endpoints
     * @param {Object} [params] - path placeholders, e.g. {date: '2026-09-01'}
     */
    url(name, params = {}, assetType = null) {
        const config = this.get(assetType);
        let path = config.endpoints[name];
        if (!path) {
            throw new Error(`Asset ${config.assetType} has no endpoint: ${name}`);
        }

        Object.keys(params).forEach(key => {
            path = path.replace(`{${key}}`, encodeURIComponent(params[key]));
        });

        const unresolved = path.match(/\{(\w+)\}/);
        if (unresolved) {
            throw new Error(`Endpoint ${name} is missing parameter: ${unresolved[1]}`);
        }

        return path;
    }

    /** True when this asset serves the named endpoint. */
    has(name, assetType = null) {
        return Boolean(this.get(assetType).endpoints[name]);
    }

    /** Called when the asset or account selection changes. */
    onChange(listener) {
        this.listeners.push(listener);
        return this;
    }

    _notify() {
        this.listeners.forEach(listener => {
            try {
                listener({ assetType: this.assetType, account: this.account });
            } catch (error) {
                console.error('AssetConfig listener failed:', error);
            }
        });
    }
}

window.ASSET_CONFIGS = ASSET_CONFIGS;
window.AssetConfig = new AssetConfigRegistry(ASSET_CONFIGS);
