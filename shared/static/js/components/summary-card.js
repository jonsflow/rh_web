/**
 * SummaryCard Component - Reusable component for displaying summary statistics
 */
class SummaryCard {
    /**
     * Create a summary card
     * @param {Object} options - Configuration options
     * @param {string} options.title - Card title
     * @param {number} options.value - Numeric value to display
     * @param {string} options.type - Card type: 'pnl', 'count', 'value'
     * @param {string} options.className - Additional CSS classes
     */
    constructor(options = {}) {
        this.title = options.title || '';
        this.value = options.value || 0;
        this.type = options.type || 'count';
        this.className = options.className || '';
    }

    /**
     * Render the summary card HTML
     * @returns {string} HTML string for the card
     */
    render() {
        const formattedValue = this._formatValue();
        const valueClass = this._getValueClass();
        
        return `
            <div class="summary-card ${this.className}">
                <h3>${this.title}</h3>
                <div class="value ${valueClass}">
                    ${formattedValue}
                </div>
            </div>
        `;
    }

    /**
     * Update card with new value
     * @param {number} newValue - New value to display
     */
    updateValue(newValue) {
        this.value = newValue;
    }

    /**
     * Format the value for display based on card type
     * @private
     * @returns {string} Formatted value string
     */
    _formatValue() {
        switch (this.type) {
            case 'pnl':
                const formatted = Math.abs(this.value).toFixed(2);
                const sign = this.value >= 0 ? '+' : '';
                return `${sign}$${this.value.toFixed(2)}`;
            
            case 'value':
                return `$${this.value.toFixed(2)}`;
            
            case 'count':
            default:
                return this.value.toString();
        }
    }

    /**
     * Get CSS class for value styling based on card type and value
     * @private
     * @returns {string} CSS class name
     */
    _getValueClass() {
        if (this.type === 'pnl') {
            return this.value >= 0 ? 'profit' : 'loss';
        }
        return '';
    }

    /**
     * Create and render a summary card to a container
     * @param {string|HTMLElement} container - Container selector or element
     * @param {Object} options - Card configuration options
     * @returns {SummaryCard} The created card instance
     */
    static renderTo(container, options) {
        const card = new SummaryCard(options);
        const element = typeof container === 'string' ? document.querySelector(container) : container;
        
        if (element) {
            element.innerHTML = card.render();
        } else {
            console.error('SummaryCard: Container not found:', container);
        }
        
        return card;
    }
}

/**
 * SummaryPanel - Collection of summary cards
 */
class SummaryPanel {
    constructor(container) {
        this.container = typeof container === 'string' ? document.querySelector(container) : container;
        this.cards = [];
    }

    /**
     * Add a summary card to the panel
     * @param {Object} options - Card configuration options
     */
    addCard(options) {
        const card = new SummaryCard(options);
        this.cards.push(card);
        return card;
    }

    /**
     * Render all cards in the panel
     */
    render() {
        if (!this.container) {
            console.error('SummaryPanel: Container not found');
            return;
        }

        const html = this.cards.map(card => card.render()).join('');
        this.container.innerHTML = html;
    }

    /**
     * Update panel with new summary statistics
     * @param {Object} stats - Summary statistics object
     */
    updateStats(stats) {
        if (!stats) return;

        // Clear existing cards and recreate with new data
        this.cards = [];

        // Add cards in the desired order
        this.addCard({
            title: 'Total P&L',
            value: stats.totalPL,
            type: 'pnl'
        });

        this.addCard({
            title: 'Closed P&L', 
            value: stats.closedPL,
            type: 'pnl'
        });

        this.addCard({
            title: 'Expired P&L',
            value: stats.expiredPL,
            type: 'pnl'
        });

        this.addCard({
            title: 'Total Trades',
            value: stats.totalTrades,
            type: 'count'
        });

        this.addCard({
            title: 'Open Positions',
            value: stats.openCount,
            type: 'count'
        });

        this.addCard({
            title: 'Open Value',
            value: stats.openValue,
            type: 'value'
        });

        this.render();
    }
}

// Export to global scope
window.SummaryCard = SummaryCard;
window.SummaryPanel = SummaryPanel;