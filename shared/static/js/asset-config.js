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
        },
        // Calendar: what the day shows and what its detail modal contains.
        // Transcribed from each dashboard as it behaved before they merged --
        // note the P&L field differs, which is why it is configuration.
        calendar: {
            pnlField: 'pnl',
            dayStates: false,
            detail: {
                title: 'Positions for {date} - {pnl} ({count} trades)',
                sources: ['positionsByDate'],
                header: null,
                sections: [
                    {
                        source: 'positionsByDate',
                        from: 'positions',
                        heading: '',
                        columns: [
                            { label: 'Symbol', key: 'symbol' },
                            { label: 'Strategy', key: 'strategy', empty: '-' },
                            { label: 'Strike', key: 'strike_price' },
                            { label: 'Type', key: 'option_type' },
                            { label: 'Quantity', key: 'quantity', format: 'number' },
                            { label: 'Open Price', key: 'open_price', format: 'currency' },
                            { label: 'Close Price', key: 'close_price', format: 'currency' },
                            { label: 'P&L', key: 'net_credit', format: 'pnl' }
                        ]
                    }
                ]
            }
        },
        // By-symbol view: where closed trades and orders live in this asset's
        // payload, and what its detail tables show
        bySymbol: {
            closedFrom: ['closed_positions', 'expired_positions'],
            symbolField: 'symbol',
            pnlField: 'net_credit',
            quantityField: 'quantity',
            unitLabel: 'contracts',
            ordersFrom: 'all_orders',
            orderSymbolField: 'symbol',
            orderDateField: 'created_at',
            closedColumns: [
                { label: 'Opened', key: 'open_date' },
                { label: 'Closed', key: 'close_date' },
                { label: 'Strike', key: 'strike_price' },
                { label: 'Type', key: 'option_type' },
                { label: 'Quantity', key: 'quantity' },
                { label: 'P&L', key: 'net_credit', format: 'signedPnl' }
            ],
            orderColumns: [
                { label: 'Date', key: 'created_at', format: 'date' },
                { label: 'Effect', key: 'position_effect' },
                { label: 'Strike', key: 'strike_price' },
                { label: 'Type', key: 'option_type' },
                { label: 'Quantity', key: 'quantity' },
                { label: 'Premium', key: 'premium', format: 'currency' }
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
        },
        calendar: {
            // Stocks shows P&L before fees, and colours a day that only opened
            // positions differently from one with nothing at all
            pnlField: 'pnl_no_fees',
            dayStates: true,
            detail: {
                title: 'Trading Summary - {date}',
                sources: ['dailySummary', 'positionsByDate'],
                header: {
                    source: 'dailySummary',
                    from: 'summary.totals',
                    pnlField: 'total_pnl',
                    countSource: 'positionsByDate',
                    countFrom: 'orders',
                    sumField: 'quantity',
                    sumLabel: 'shares'
                },
                sections: [
                    {
                        source: 'dailySummary',
                        from: 'summary.closed_positions',
                        heading: 'Closed Positions',
                        omitWhenEmpty: true,
                        spacerAfter: true,
                        columns: [
                            { label: 'Symbol', key: 'symbol', format: 'strong' },
                            { label: 'Quantity', key: 'quantity', format: 'number' },
                            { label: 'Avg Buy Price', key: 'avg_buy_price', format: 'currency' },
                            { label: 'Avg Sell Price', key: 'avg_sell_price', format: 'currency' },
                            { label: 'P&L', key: 'pnl', format: 'signedPnl' }
                        ]
                    },
                    {
                        source: 'dailySummary',
                        from: 'summary.opened_positions',
                        heading: 'Opened Positions',
                        omitWhenEmpty: true,
                        spacerAfter: true,
                        columns: [
                            { label: 'Symbol', key: 'symbol', format: 'strong' },
                            { label: 'Quantity', key: 'quantity', format: 'number' },
                            { label: 'Avg Buy Price', key: 'avg_buy_price', format: 'currency' }
                        ]
                    },
                    {
                        source: 'positionsByDate',
                        from: 'orders',
                        heading: 'Detailed Orders ({count} total)',
                        columns: [
                            { label: 'Symbol', key: 'symbol' },
                            { label: 'Time', key: 'execution_time', format: 'datetime' },
                            { label: 'Side', key: 'side', format: 'side' },
                            { label: 'Quantity', key: 'quantity', format: 'number' },
                            { label: 'Price', key: 'average_price', format: 'currency' },
                            { label: 'Total Amount', key: 'total_amount', format: 'currency' }
                        ]
                    }
                ]
            }
        },
        bySymbol: {
            closedFrom: ['closed_positions'],
            symbolField: 'symbol',
            pnlField: 'pnl',
            quantityField: 'quantity',
            unitLabel: 'shares',
            ordersFrom: 'all_orders',
            orderSymbolField: 'symbol',
            orderDateField: 'last_transaction_at',
            closedColumns: [
                { label: 'Buy Date', key: 'buy_date' },
                { label: 'Sell Date', key: 'sell_date' },
                { label: 'Quantity', key: 'quantity' },
                { label: 'Avg Buy Price', key: 'buy_price', format: 'currency' },
                { label: 'Avg Sell Price', key: 'sell_price', format: 'currency' },
                { label: 'P&L', key: 'pnl', format: 'signedPnl' }
            ],
            orderColumns: [
                { label: 'Date', key: 'last_transaction_at', format: 'date' },
                { label: 'Side', key: 'side', format: 'side' },
                { label: 'Quantity', key: 'quantity' },
                { label: 'Price', key: 'average_price', format: 'currency' },
                { label: 'Total', key: 'total_amount', format: 'currency' }
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
        },
        calendar: {
            pnlField: 'pnl_no_fees',
            dayStates: false,
            detail: {
                title: 'Trading Summary - {date}',
                sources: ['dailySummary', 'positionsByDate'],
                header: null,
                sections: [
                    {
                        source: 'dailySummary',
                        from: 'summary.contracts',
                        heading: 'Purchase and Sale Summary',
                        spacerAfter: true,
                        columns: [
                            { label: 'Symbol', key: 'symbol' },
                            { label: 'Total Qty Long', key: 'total_qty_long', format: 'number' },
                            { label: 'Total Qty Short', key: 'total_qty_short', format: 'number' },
                            { label: 'Gross P&L', key: 'gross_pnl', format: 'signedPnl' }
                        ],
                        totals: {
                            from: 'summary.totals',
                            columns: [
                                { literal: 'TOTALS' },
                                { key: 'total_qty_long', format: 'number' },
                                { key: 'total_qty_short', format: 'number' },
                                { key: 'gross_pnl', format: 'signedPnl' }
                            ]
                        }
                    },
                    {
                        source: 'positionsByDate',
                        from: 'orders',
                        heading: 'Detailed Orders ({count} total)',
                        columns: [
                            { label: 'Symbol', keys: ['symbol', 'contract_id'], format: 'fallback' },
                            { label: 'Time', key: 'execution_time', format: 'datetime' },
                            { label: 'Side', key: 'order_side', format: 'number' },
                            { label: 'Quantity', keys: ['filled_quantity', 'quantity'], format: 'fallback' },
                            { label: 'Price', key: 'average_price', format: 'currency' },
                            { label: 'Realized P&L', key: 'realized_pnl', format: 'signedPnl' }
                        ]
                    }
                ]
            }
        },
        bySymbol: {
            closedFrom: ['closed_positions'],
            symbolField: 'display_symbol',
            pnlField: 'realized_pnl',
            quantityField: 'quantity',
            unitLabel: 'contracts',
            ordersFrom: 'all_orders',
            orderSymbolField: 'display_symbol',
            orderDateField: 'execution_time',
            closedColumns: [
                { label: 'Closed', key: 'close_date' },
                { label: 'Side', key: 'order_side' },
                { label: 'Quantity', key: 'quantity' },
                { label: 'Price', key: 'close_price', format: 'currency' },
                { label: 'Fees', key: 'total_fee', format: 'currency' },
                { label: 'P&L', key: 'realized_pnl', format: 'signedPnl' }
            ],
            orderColumns: [
                { label: 'Date', key: 'execution_time', format: 'date' },
                { label: 'Side', key: 'order_side' },
                { label: 'Quantity', key: 'filled_quantity' },
                { label: 'Price', key: 'average_price', format: 'currency' },
                { label: 'P&L', key: 'realized_pnl', format: 'signedPnl' }
            ]
        }
    }
};


/**
 * The unified app serves every asset behind /api/<asset_type>/..., so its paths
 * are the same shape for all three and are generated rather than listed. The
 * standalone dashboards keep the paths in each config above.
 */
const UNIFIED_PATHS = {
    data: 'data',
    update: 'update',
    dailyPnl: 'daily-pnl',
    positionsByDate: 'positions/date/{date}',
    dailySummary: 'daily-summary/{date}',
    allTradingDates: 'all-trading-dates'
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
        // 'standalone' for a single-asset dashboard, 'unified' for the app that
        // serves every asset behind /api/<asset_type>/...
        this.routing = 'standalone';
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

    /**
     * Which app's URLs to build.
     * @param {string} routing - 'standalone' or 'unified'
     */
    setRouting(routing) {
        if (routing !== 'standalone' && routing !== 'unified') {
            throw new Error(`Unknown routing: ${routing}`);
        }
        this.routing = routing;
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

        // An asset that serves an endpoint nowhere serves it in either app, so
        // the standalone table stays the record of what exists
        if (!config.endpoints[name]) {
            throw new Error(`Asset ${config.assetType} has no endpoint: ${name}`);
        }

        let path = this.routing === 'unified'
            ? `/api/${config.assetType}/${UNIFIED_PATHS[name]}`
            : config.endpoints[name];

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

window.UNIFIED_PATHS = UNIFIED_PATHS;
window.ASSET_CONFIGS = ASSET_CONFIGS;
window.AssetConfig = new AssetConfigRegistry(ASSET_CONFIGS);
