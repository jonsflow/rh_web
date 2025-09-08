/**
 * Data Manager - Handles application state and data transformations
 * Provides a clean interface between API data and UI components
 */
class DataManager {
    constructor() {
        this.optionsData = null;
        this.dailyPnlData = null;
        this.eventListeners = new Map();
    }

    /**
     * Load initial options data
     * @returns {Promise<void>}
     */
    async loadOptionsData() {
        try {
            this.optionsData = await window.ApiService.fetchOptionsData();
            this._notifyListeners('dataLoaded', this.optionsData);
        } catch (error) {
            console.error('Failed to load options data:', error);
            this._notifyListeners('dataError', error);
            throw error;
        }
    }

    /**
     * Refresh data from Robinhood
     * @param {boolean} forceRefresh - Force full refresh
     * @returns {Promise<void>}
     */
    async refreshData(forceRefresh = false) {
        try {
            this._notifyListeners('refreshStarted');
            
            // Update data via API
            await window.ApiService.updateData(forceRefresh);
            
            // Reload the updated data
            this.optionsData = await window.ApiService.fetchOptionsData();
            
            this._notifyListeners('dataRefreshed', this.optionsData);
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
     * Get summary statistics from current options data
     * @returns {Object} Summary statistics
     */
    getSummaryStats() {
        if (!this.optionsData) return null;

        // Calculate P&L breakdown
        const closedPL = this.optionsData.closed_positions
            .filter(position => position.net_credit !== null && position.net_credit !== undefined)
            .reduce((total, position) => total + position.net_credit, 0);
        
        const expiredPL = this.optionsData.expired_positions
            .filter(position => position.net_credit !== null && position.net_credit !== undefined)
            .reduce((total, position) => total + position.net_credit, 0);

        const totalPL = closedPL + expiredPL;

        // Calculate open value
        const openValue = this.optionsData.open_positions.reduce((total, position) => {
            return total + (position.open_premium || 0);
        }, 0);

        // Count positions
        const openCount = this.optionsData.open_positions.length;
        const closedCount = this.optionsData.closed_positions.length;
        const expiredCount = this.optionsData.expired_positions.length;
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
     * @returns {Object} Filter options for symbols, strategies, etc.
     */
    getFilterOptions() {
        if (!this.optionsData) return null;

        const allPositions = [
            ...this.optionsData.open_positions,
            ...this.optionsData.closed_positions,
            ...this.optionsData.expired_positions
        ];

        // Extract unique values for filters
        const symbols = [...new Set(allPositions.map(p => p.symbol).filter(Boolean))].sort();
        const strategies = [...new Set(allPositions.map(p => p.strategy).filter(Boolean))].sort();
        const directions = [...new Set(allPositions.map(p => p.direction).filter(Boolean))].sort();
        const optionTypes = [...new Set(allPositions.map(p => p.option_type).filter(Boolean))].sort();

        // Get date ranges
        const allDates = allPositions
            .map(p => p.open_date || p.close_date)
            .filter(Boolean)
            .map(date => new Date(date))
            .sort((a, b) => a - b);

        const minDate = allDates.length > 0 ? allDates[0] : new Date();
        const maxDate = allDates.length > 0 ? allDates[allDates.length - 1] : new Date();

        return {
            symbols,
            strategies,
            directions,
            optionTypes,
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
     * Get current options data
     * @returns {Object|null} Current options data
     */
    getOptionsData() {
        return this.optionsData;
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
window.DataManager = new DataManager();