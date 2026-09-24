/**
 * Data Manager - application state and data transformations.
 *
 * Field names come from AssetConfig, so the same summaries and filters are
 * produced for options, stocks and futures rather than only for options.
 */
class DataManager {
    constructor(config = null) {
        this.data = null;
        this.dailyPnlData = null;
        this.eventListeners = new Map();
        this._config = config;
    }

    get config() {
        return this._config || window.AssetConfig;
    }

    /**
     * Load positions and orders for the selected asset and account.
     * @param {Object} [options] - assetType and account overrides
     * @returns {Promise<void>}
     */
    async loadData(options = {}) {
        try {
            this.data = await window.ApiService.fetchData(options);
            this._notifyListeners('dataLoaded', this.data);
        } catch (error) {
            console.error('Failed to load data:', error);
            this._notifyListeners('dataError', error);
            throw error;
        }
    }

    /**
     * Refresh data from Robinhood
     * @param {boolean} forceRefresh - Force full refresh
     * @param {Object} [options] - assetType and account overrides
     * @returns {Promise<void>}
     */
    async refreshData(forceRefresh = false, options = {}) {
        try {
            this._notifyListeners('refreshStarted');
            
            // Update data via API
            await window.ApiService.updateData(forceRefresh, options);
            
            // Reload the updated data
            this.data = await window.ApiService.fetchData(options);
            
            this._notifyListeners('dataRefreshed', this.data);
        } catch (error) {
            console.error('Failed to refresh data:', error);
            this._notifyListeners('refreshError', error);
            throw error;
        }
    }

    /**
     * Load daily P&L data for calendar
     * @param {string} startDate - Start date
     * @param {string} endDate - End date
     * @returns {Promise<void>}
     */
    async loadDailyPnl(startDate = null, endDate = null) {
        try {
            const response = await window.ApiService.fetchDailyPnl(startDate, endDate);
            this.dailyPnlData = response.daily_pnl || {};
            this._notifyListeners('dailyPnlLoaded', this.dailyPnlData);
        } catch (error) {
            console.error('Failed to load daily P&L:', error);
            this._notifyListeners('dailyPnlError', error);
            throw error;
        }
    }

    /**
     * Get summary statistics for the loaded asset.
     * @returns {Object} Summary statistics
     */
    getSummaryStats() {
        if (!this.data) return null;

        const pnlField = this.config.field('pnl');
        const openValueField = this.config.field('openValue');

        const sumPnl = (positions) => (positions || [])
            .filter(position => position[pnlField] !== null && position[pnlField] !== undefined)
            .reduce((total, position) => total + position[pnlField], 0);

        // Calculate P&L breakdown
        const closedPL = sumPnl(this.data.closed_positions);
        const expiredPL = sumPnl(this.data.expired_positions);

        const totalPL = closedPL + expiredPL;

        // Calculate open value
        const openValue = (this.data.open_positions || []).reduce((total, position) => {
            return total + (position[openValueField] || 0);
        }, 0);

        // Count positions
        const openCount = (this.data.open_positions || []).length;
        const closedCount = (this.data.closed_positions || []).length;
        const expiredCount = (this.data.expired_positions || []).length;
        const totalTrades = openCount + closedCount + expiredCount;

        return {
            totalPL: totalPL,
            closedPL: closedPL,
            expiredPL: expiredPL,
            openValue: openValue,
            openCount: openCount,
            closedCount: closedCount,
            expiredCount: expiredCount,
            totalTrades: totalTrades
        };
    }

    /**
     * Get unique filter options from current data
     * @returns {Object} Facet values for this asset, plus the date range
     */
    getFilterOptions() {
        if (!this.data) return null;

        const allPositions = [
            ...(this.data.open_positions || []),
            ...(this.data.closed_positions || []),
            ...(this.data.expired_positions || [])
        ];

        // Unique values for each facet this asset offers, keyed by field name
        const facets = {};
        this.config.facets().forEach(field => {
            facets[field] = [...new Set(allPositions.map(p => p[field]).filter(Boolean))].sort();
        });

        const openDateField = this.config.field('openDate');
        const closeDateField = this.config.field('closeDate');

        // Get date ranges
        const allDates = allPositions
            .map(p => p[openDateField] || p[closeDateField])
            .filter(Boolean)
            .map(date => new Date(date))
            .sort((a, b) => a - b);

        const minDate = allDates.length > 0 ? allDates[0] : new Date();
        const maxDate = allDates.length > 0 ? allDates[allDates.length - 1] : new Date();

        return {
            // Unique values per facet field, e.g. facets.symbol, facets.option_type
            facets,
            dateRange: {
                min: minDate.toISOString().split('T')[0],
                max: maxDate.toISOString().split('T')[0]
            }
        };
    }

    /**
     * Subscribe to data events
     * @param {string} event - Event name
     * @param {Function} callback - Callback function
     */
    addEventListener(event, callback) {
        if (!this.eventListeners.has(event)) {
            this.eventListeners.set(event, []);
        }
        this.eventListeners.get(event).push(callback);
    }

    /**
     * Remove event listener
     * @param {string} event - Event name
     * @param {Function} callback - Callback function
     */
    removeEventListener(event, callback) {
        if (this.eventListeners.has(event)) {
            const callbacks = this.eventListeners.get(event);
            const index = callbacks.indexOf(callback);
            if (index > -1) {
                callbacks.splice(index, 1);
            }
        }
    }

    /**
     * Notify event listeners
     * @private
     * @param {string} event - Event name
     * @param {*} data - Event data
     */
    _notifyListeners(event, data = null) {
        if (this.eventListeners.has(event)) {
            this.eventListeners.get(event).forEach(callback => {
                try {
                    callback(data);
                } catch (error) {
                    console.error(`Error in event listener for ${event}:`, error);
                }
            });
        }
    }

    /**
     * Get the currently loaded positions and orders
     * @returns {Object|null} Current data
     */
    getData() {
        return this.data;
    }

    /**
     * Get current daily P&L data
     * @returns {Object|null} Current daily P&L data
     */
    getDailyPnlData() {
        return this.dailyPnlData;
    }
}

// Export as singleton
window.DataManagerClass = DataManager;
window.DataManager = new DataManager();