/**
 * API Service - Handles all HTTP requests to the Flask backend
 * Centralizes API communication and provides a clean interface for frontend components
 */
class ApiService {
    constructor() {
        this.baseUrl = '';  // Same origin
    }

    /**
     * Fetch options data from the backend
     * @returns {Promise<Object>} Options data with positions and orders
     */
    async fetchOptionsData() {
        try {
            const response = await fetch(`${this.baseUrl}/api/options`);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            
            if (data.error) {
                throw new Error(data.error);
            }
            
            return data;
        } catch (error) {
            console.error('Error fetching options data:', error);
            throw error;
        }
    }

    /**
     * Update/refresh data from Robinhood
     * @param {boolean} forceRefresh - Whether to force full refresh
     * @returns {Promise<Object>} Updated options data
     */
    async updateData(forceRefresh = false) {
        try {
            const response = await fetch(`${this.baseUrl}/api/update`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    force_refresh: forceRefresh
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();

            if (data.error) {
                throw new Error(data.error);
            }

            return data;
        } catch (error) {
            console.error('Error updating data:', error);
            throw error;
        }
    }

    /**
     * Fetch daily P&L data for calendar view
     * @param {string} startDate - Start date (YYYY-MM-DD)
     * @param {string} endDate - End date (YYYY-MM-DD)
     * @returns {Promise<Object>} Daily P&L data
     */
    async fetchDailyPnl(startDate = null, endDate = null) {
        try {
            const params = new URLSearchParams();
            if (startDate) params.append('start_date', startDate);
            if (endDate) params.append('end_date', endDate);
            
            const url = `${this.baseUrl}/api/daily-pnl${params.toString() ? '?' + params.toString() : ''}`;
            const response = await fetch(url);

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();

            if (data.error) {
                throw new Error(data.error);
            }

            return data;
        } catch (error) {
            console.error('Error fetching daily P&L:', error);
            throw error;
        }
    }

    /**
     * Fetch positions for a specific date
     * @param {string} date - Date in YYYY-MM-DD format
     * @returns {Promise<Object>} Positions data for the date
     */
    async fetchPositionsByDate(date) {
        try {
            const response = await fetch(`${this.baseUrl}/api/positions/date/${date}`);

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();

            if (data.error) {
                throw new Error(data.error);
            }

            return data;
        } catch (error) {
            console.error('Error fetching positions by date:', error);
            throw error;
        }
    }
}

// Export as singleton
window.ApiService = new ApiService();