/**
 * PositionTable Component - Reusable component for displaying position tables
 */
class PositionTable {
    /**
     * Create a position table
     * @param {Object} options - Configuration options
     * @param {HTMLElement|string} options.container - Container element or selector
     * @param {string} options.type - Table type: 'open', 'closed', 'expired', 'orders'
     * @param {Array} options.columns - Column definitions
     * @param {boolean} options.sortable - Whether table is sortable
     */
    constructor(options = {}) {
        this.container = typeof options.container === 'string' 
            ? document.querySelector(options.container) 
            : options.container;
        this.type = options.type || 'open';
        this.columns = options.columns || this._getDefaultColumns();
        this.sortable = options.sortable !== false;
        this.data = [];
        this.filteredData = [];
        this.sortConfig = { key: null, direction: 'asc' };
        
        if (!this.container) {
            console.error('PositionTable: Container not found');
        }
    }

    /**
     * Set table data
     * @param {Array} data - Array of position/order objects
     */
    setData(data) {
        this.data = data || [];
        this.filteredData = [...this.data];
        this.render();
    }

    /**
     * Apply filters to the table data
     * @param {Object} filters - Filter criteria
     */
    applyFilters(filters) {
        this.filteredData = this.data.filter(item => {
            return this._matchesFilters(item, filters);
        });
        this.render();
    }

    /**
     * Sort table by column
     * @param {string} key - Column key to sort by
     */
    sortBy(key) {
        if (this.sortConfig.key === key) {
            // Toggle direction if same column
            this.sortConfig.direction = this.sortConfig.direction === 'asc' ? 'desc' : 'asc';
        } else {
            this.sortConfig.key = key;
            this.sortConfig.direction = 'asc';
        }

        this.filteredData.sort((a, b) => {
            const aVal = this._getNestedValue(a, key);
            const bVal = this._getNestedValue(b, key);
            
            // Handle null/undefined values
            if (aVal === null || aVal === undefined) return 1;
            if (bVal === null || bVal === undefined) return -1;
            
            let comparison = 0;
            if (typeof aVal === 'number' && typeof bVal === 'number') {
                comparison = aVal - bVal;
            } else {
                comparison = String(aVal).localeCompare(String(bVal));
            }
            
            return this.sortConfig.direction === 'asc' ? comparison : -comparison;
        });

        this.render();
    }

    /**
     * Render the table
     */
    render() {
        if (!this.container) return;

        // Check if container is already a table element
        if (this.container.tagName === 'TABLE') {
            this._renderIntoExistingTable();
        } else {
            // Create new table structure
            const html = `
                <div class="table-container">
                    ${this._renderTable()}
                </div>
            `;
            this.container.innerHTML = html;
        }
        
        this._attachEventListeners();
    }

    /**
     * Render data into existing table element
     * @private
     */
    _renderIntoExistingTable() {
        if (this.filteredData.length === 0) {
            // Show no data message in tbody
            const tbody = this.container.querySelector('tbody');
            if (tbody) {
                tbody.innerHTML = '<tr><td colspan="100%" class="no-data">No data available</td></tr>';
            }
            return;
        }

        // Update tbody with new data
        const tbody = this.container.querySelector('tbody');
        if (tbody) {
            tbody.innerHTML = this.filteredData.map(item => this._renderRow(item)).join('');
        }

        // Update thead with sortable indicators if needed
        const headers = this.container.querySelectorAll('th[data-sort]');
        headers.forEach(th => {
            const sortKey = th.getAttribute('data-sort');
            if (sortKey) {
                // Add sort icon
                const existingIcon = th.querySelector('.sort-icon');
                if (existingIcon) {
                    existingIcon.remove();
                }
                
                const icon = document.createElement('span');
                icon.className = 'sort-icon';
                icon.innerHTML = this._getSortIcon(sortKey);
                th.appendChild(icon);
            }
        });
    }

    /**
     * Get default columns based on table type
     * @private
     * @returns {Array} Column definitions
     */
    _getDefaultColumns() {
        const baseColumns = [
            { key: 'symbol', label: 'Symbol', sortable: true },
            { key: 'strategy', label: 'Strategy', sortable: true },
            { key: 'direction', label: 'Direction', sortable: true },
            { key: 'option_type', label: 'Type', sortable: true },
            { key: 'strike_price', label: 'Strike', sortable: true },
            { key: 'expiration_date', label: 'Expiration', sortable: true, type: 'date' }
        ];

        switch (this.type) {
            case 'open':
                return [
                    ...baseColumns,
                    { key: 'quantity', label: 'Qty', sortable: true, type: 'number' },
                    { key: 'open_premium', label: 'Premium', sortable: true, type: 'currency' },
                    { key: 'open_date', label: 'Opened', sortable: true, type: 'date' }
                ];
            
            case 'closed':
            case 'expired':
                return [
                    ...baseColumns,
                    { key: 'quantity', label: 'Qty', sortable: true, type: 'number' },
                    { key: 'net_credit', label: 'P&L', sortable: true, type: 'pnl' },
                    { key: 'open_date', label: 'Opened', sortable: true, type: 'date' },
                    { key: 'close_date', label: 'Closed', sortable: true, type: 'date' }
                ];
            
            case 'orders':
                return [
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
                ];
            
            default:
                return baseColumns;
        }
    }

    /**
     * Render the table HTML
     * @private
     * @returns {string} Table HTML
     */
    _renderTable() {
        if (this.filteredData.length === 0) {
            return `<div class="no-data">No data available</div>`;
        }

        return `
            <table class="data-table">
                <thead>
                    <tr>
                        ${this.columns.map(col => this._renderHeaderCell(col)).join('')}
                    </tr>
                </thead>
                <tbody>
                    ${this.filteredData.map(item => this._renderRow(item)).join('')}
                </tbody>
            </table>
        `;
    }

    /**
     * Render header cell
     * @private
     * @param {Object} column - Column definition
     * @returns {string} Header cell HTML
     */
    _renderHeaderCell(column) {
        const sortIcon = this._getSortIcon(column.key);
        const clickable = column.sortable !== false ? 'sortable' : '';
        
        return `
            <th class="${clickable}" data-sort="${column.key}">
                ${column.label}
                ${sortIcon}
            </th>
        `;
    }

    /**
     * Render data row
     * @private
     * @param {Object} item - Data item
     * @returns {string} Row HTML
     */
    _renderRow(item) {
        return `
            <tr>
                ${this.columns.map(col => this._renderCell(item, col)).join('')}
            </tr>
        `;
    }

    /**
     * Render individual cell
     * @private
     * @param {Object} item - Data item
     * @param {Object} column - Column definition
     * @returns {string} Cell HTML
     */
    _renderCell(item, column) {
        const value = this._getNestedValue(item, column.key);
        const formattedValue = this._formatValue(value, column.type);
        const className = this._getCellClass(value, column.type);
        
        return `<td class="${className}">${formattedValue}</td>`;
    }

    /**
     * Format value based on column type
     * @private
     * @param {*} value - Raw value
     * @param {string} type - Column type
     * @returns {string} Formatted value
     */
    _formatValue(value, type) {
        if (value === null || value === undefined) return '';
        
        switch (type) {
            case 'currency':
                return `$${Number(value).toFixed(2)}`;
            
            case 'pnl':
                const num = Number(value);
                const sign = num >= 0 ? '+' : '';
                return `${sign}$${num.toFixed(2)}`;
            
            case 'number':
                return Number(value).toString();
            
            case 'date':
                return new Date(value).toLocaleDateString();
            
            case 'datetime':
                return new Date(value).toLocaleString();
            
            default:
                return String(value);
        }
    }

    /**
     * Get CSS class for cell based on value and type
     * @private
     * @param {*} value - Cell value
     * @param {string} type - Column type
     * @returns {string} CSS class
     */
    _getCellClass(value, type) {
        if (type === 'pnl') {
            return Number(value) >= 0 ? 'profit' : 'loss';
        }
        return '';
    }

    /**
     * Get sort icon for column
     * @private
     * @param {string} key - Column key
     * @returns {string} Sort icon HTML
     */
    _getSortIcon(key) {
        if (this.sortConfig.key !== key) return '↕️';
        return this.sortConfig.direction === 'asc' ? '↑' : '↓';
    }

    /**
     * Get nested object value by key path
     * @private
     * @param {Object} obj - Object to get value from
     * @param {string} path - Dot-notation path
     * @returns {*} Value at path
     */
    _getNestedValue(obj, path) {
        return path.split('.').reduce((current, key) => current?.[key], obj);
    }

    /**
     * Check if item matches filter criteria
     * @private
     * @param {Object} item - Data item
     * @param {Object} filters - Filter criteria
     * @returns {boolean} Whether item matches filters
     */
    _matchesFilters(item, filters) {
        for (const [key, value] of Object.entries(filters)) {
            if (!value) continue;
            
            const itemValue = this._getNestedValue(item, key);
            
            if (key.includes('date') && value.start && value.end) {
                const itemDate = new Date(itemValue);
                const startDate = new Date(value.start);
                const endDate = new Date(value.end);
                
                if (itemDate < startDate || itemDate > endDate) {
                    return false;
                }
            } else if (Array.isArray(value)) {
                if (!value.includes(itemValue)) {
                    return false;
                }
            } else if (String(itemValue).toLowerCase().indexOf(String(value).toLowerCase()) === -1) {
                return false;
            }
        }
        
        return true;
    }

    /**
     * Attach event listeners
     * @private
     */
    _attachEventListeners() {
        if (!this.sortable) return;
        
        // Look for both .sortable class and [data-sort] attribute  
        const headers = this.container.querySelectorAll('th.sortable, th[data-sort]');
        headers.forEach(header => {
            header.addEventListener('click', (e) => {
                const sortKey = e.target.dataset.sort || e.target.getAttribute('data-sort');
                if (sortKey) {
                    this.sortBy(sortKey);
                }
            });
        });
    }
}

// Export to global scope
window.PositionTable = PositionTable;