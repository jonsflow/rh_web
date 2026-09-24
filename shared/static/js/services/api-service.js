/**
 * API Service - all HTTP requests to the Flask backend.
 *
 * Every request carries the asset type and the account being viewed. Paths come
 * from AssetConfig rather than being written here, so the same service serves
 * options, stocks and futures, and switching either selection changes no code.
 *
 * The account parameter is sent as soon as an account is selected. Backends that
 * do not yet record an account ignore the parameter, so the frontend contract
 * does not change when they start honouring it.
 */
class ApiService {
    constructor(config = null) {
        this.baseUrl = '';  // Same origin
        this._config = config;
    }

    get config() {
        return this._config || window.AssetConfig;
    }

    /**
     * Build a URL for an endpoint, applying the account and any query params.
     * @param {string} name - endpoint key, e.g. 'dailyPnl'
     * @param {Object} [options]
     * @param {Object} [options.params] - path placeholders, e.g. {date}
     * @param {Object} [options.query] - query string values; null/undefined dropped
     * @param {string} [options.assetType] - overrides the current selection
     * @param {string} [options.account] - overrides the current account
     * @returns {string} URL
     */
    buildUrl(name, { params = {}, query = {}, assetType = null, account } = {}) {
        const path = this.config.url(name, params, assetType);

        const search = new URLSearchParams();
        const selectedAccount = account !== undefined ? account : this.config.account;
        if (selectedAccount) {
            search.append('account', selectedAccount);
        }
        Object.keys(query).forEach(key => {
            const value = query[key];
            if (value !== null && value !== undefined && value !== '') {
                search.append(key, value);
            }
        });

        const queryString = search.toString();
        return `${this.baseUrl}${path}${queryString ? '?' + queryString : ''}`;
    }

    /**
     * Fetch JSON, raising on a transport error or an error in the payload.
     * @private
     */
    async _request(url, init = undefined) {
        const response = await fetch(url, init);

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        if (data.error) {
            throw new Error(data.error);
        }

        return data;
    }

    /**
     * Fetch the positions and orders for an asset.
     * @param {Object} [options] - assetType and account overrides
     * @returns {Promise<Object>}
     */
    async fetchData(options = {}) {
        try {
            return await this._request(this.buildUrl('data', options));
        } catch (error) {
            console.error('Error fetching data:', error);
            throw error;
        }
    }

    /**
     * Refresh data from the broker.
     * @param {boolean} forceRefresh - Whether to force a full refresh
     * @param {Object} [options] - assetType and account overrides
     * @returns {Promise<Object>}
     */
    async updateData(forceRefresh = false, options = {}) {
        try {
            return await this._request(this.buildUrl('update', options), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ force_refresh: forceRefresh })
            });
        } catch (error) {
            console.error('Error updating data:', error);
            throw error;
        }
    }

    /**
     * Fetch daily P&L for the calendar.
     * @param {string} [startDate] - YYYY-MM-DD
     * @param {string} [endDate] - YYYY-MM-DD
     * @param {Object} [options] - assetType and account overrides
     * @returns {Promise<Object>}
     */
    async fetchDailyPnl(startDate = null, endDate = null, options = {}) {
        try {
            const url = this.buildUrl('dailyPnl', {
                ...options,
                query: { start_date: startDate, end_date: endDate }
            });
            return await this._request(url);
        } catch (error) {
            console.error('Error fetching daily P&L:', error);
            throw error;
        }
    }

    /**
     * Fetch positions for one date.
     * @param {string} date - YYYY-MM-DD
     * @param {Object} [options] - assetType and account overrides
     * @returns {Promise<Object>}
     */
    async fetchPositionsByDate(date, options = {}) {
        try {
            const url = this.buildUrl('positionsByDate', { ...options, params: { date } });
            return await this._request(url);
        } catch (error) {
            console.error('Error fetching positions by date:', error);
            throw error;
        }
    }

    /**
     * Fetch the summary for one date, where the asset serves one.
     * @param {string} date - YYYY-MM-DD
     * @param {Object} [options] - assetType and account overrides
     * @returns {Promise<Object>}
     */
    async fetchDailySummary(date, options = {}) {
        try {
            const url = this.buildUrl('dailySummary', { ...options, params: { date } });
            return await this._request(url);
        } catch (error) {
            console.error('Error fetching daily summary:', error);
            throw error;
        }
    }

    /**
     * Fetch every date that has trading activity, where the asset serves it.
     * @param {Object} [options] - assetType and account overrides
     * @returns {Promise<Object>}
     */
    async fetchAllTradingDates(options = {}) {
        try {
            return await this._request(this.buildUrl('allTradingDates', options));
        } catch (error) {
            console.error('Error fetching trading dates:', error);
            throw error;
        }
    }
}

window.ApiServiceClass = ApiService;
window.ApiService = new ApiService();
