// Render summary statistics using robin_stocks P&L calculations
function renderSummary() {
    const summary = document.getElementById('summary');

    // Use P&L summary from robin_stocks (calculated from raw orders)
    const pnlSummary = futuresData.summary || {
        total_pnl: 0,
        total_pnl_without_fees: 0,
        total_fees: 0,
        total_commissions: 0,
        total_gold_savings: 0,
        num_orders: 0
    };

    // Count positions
    const openCount = futuresData.open_positions.length;
    const closedCount = futuresData.closed_positions.length;

    // Simple HTML rendering for futures
    const pnlWithoutFeesFormatted = pnlSummary.total_pnl_without_fees.toFixed(2);
    const totalFeesAndCommissionsFormatted = pnlSummary.total_fees.toFixed(2);
    const totalPLFormatted = pnlSummary.total_pnl.toFixed(2);

    // Calculate win rate from closed positions
    let winningTrades = 0;
    let losingTrades = 0;
    futuresData.closed_positions.forEach(pos => {
        const pnl = pos.realized_pnl || 0;
        if (pnl > 0) winningTrades++;
        else if (pnl < 0) losingTrades++;
    });
    const totalTrades = winningTrades + losingTrades;
    const winRate = totalTrades > 0 ? ((winningTrades / totalTrades) * 100).toFixed(1) : 0;

    summary.innerHTML = `
        <div class="summary-card">
            <h3>P&L (Before Fees)</h3>
            <div class="value ${Number(pnlWithoutFeesFormatted) >= 0 ? 'profit' : 'loss'}">
                ${Number(pnlWithoutFeesFormatted) >= 0 ? '+' : ''}$${pnlWithoutFeesFormatted}
            </div>
        </div>
        <div class="summary-card">
            <h3>Fees & Commissions</h3>
            <div class="value loss">
                -$${totalFeesAndCommissionsFormatted}
            </div>
        </div>
        <div class="summary-card">
            <h3>Win Rate</h3>
            <div class="value ${Number(winRate) >= 50 ? 'profit' : 'loss'}">
                ${winRate}%
            </div>
        </div>
        <div class="summary-card">
            <h3>Filled Orders</h3>
            <div class="value">${pnlSummary.num_orders}</div>
        </div>
    `;
}

// Render open positions table with data attributes for sorting
function renderOpenPositions() {
    const tbody = document.querySelector('#openPositionsTable tbody');
    tbody.innerHTML = '';

    if (futuresData.open_positions.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="empty-message">No open positions found</td>
            </tr>
        `;
        return;
    }

    futuresData.open_positions.forEach(position => {
        const row = document.createElement('tr');

        // For open positions, we don't have current price to calculate unrealized P&L
        // TODO: Need to fetch current contract price to calculate unrealized P&L
        const unrealizedPnl = 0; // Placeholder until we implement current price fetching

        // Format dates to be more readable
        const formatDate = (dateStr) => {
            if (!dateStr) return '';
            const date = new Date(dateStr);
            return date.toLocaleString('en-US', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            });
        };

        row.innerHTML = `
            <td>${position.symbol || position.contract_id}</td>
            <td>${formatDate(position.open_date)}</td>
            <td>${position.quantity || ''}</td>
            <td>$${position.open_price ? position.open_price.toFixed(2) : '0.00'}</td>
            <td class="${unrealizedPnl >= 0 ? 'profit' : 'loss'}">
                ${unrealizedPnl >= 0 ? '+' : ''}$${unrealizedPnl.toFixed(2)}
            </td>
        `;

        // Add data attributes for sorting
        row.dataset.contractId = position.contract_id || '';
        row.dataset.openDate = position.open_date || '';
        row.dataset.quantity = parseInt(position.quantity || 0);
        row.dataset.openPrice = parseFloat(position.open_price || 0);
        row.dataset.unrealizedPnl = parseFloat(unrealizedPnl);

        tbody.appendChild(row);
    });
}

// Render closed positions table with data attributes for sorting
function renderClosedPositions() {
    const tbody = document.querySelector('#closedPositionsTable tbody');
    tbody.innerHTML = '';

    if (futuresData.closed_positions.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="empty-message">No closed positions found</td>
            </tr>
        `;
        return;
    }

    futuresData.closed_positions.forEach(position => {
        const row = document.createElement('tr');

        // Use realized_pnl_without_fees to match calendar display
        const realizedPnl = position.realized_pnl_without_fees || 0;
        const isProfitable = realizedPnl > 0;
        const pnlClass = isProfitable ? 'profit' : 'loss';

        // Format dates to be more readable
        const formatDate = (dateStr) => {
            if (!dateStr) return '';
            const date = new Date(dateStr);
            return date.toLocaleString('en-US', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            });
        };

        // Note: These are now closing orders directly, so we don't have open_date/open_price
        // We'll show the trade_date and close info
        row.innerHTML = `
            <td>${position.symbol || position.contract_id}</td>
            <td>${position.trade_date || ''}</td>
            <td>${formatDate(position.close_date)}</td>
            <td>${position.quantity || ''}</td>
            <td>-</td>
            <td>$${position.close_price ? position.close_price.toFixed(2) : '0.00'}</td>
            <td class="${pnlClass}">
                ${isProfitable ? '+' : ''}$${realizedPnl.toFixed(2)}
            </td>
        `;

        // Add data attributes for sorting
        row.dataset.contractId = position.contract_id || '';
        row.dataset.openDate = position.trade_date || '';
        row.dataset.closeDate = position.close_date || '';
        row.dataset.quantity = parseInt(position.quantity || 0);
        row.dataset.openPrice = 0;
        row.dataset.closePrice = parseFloat(position.close_price || 0);
        row.dataset.realizedPnl = parseFloat(realizedPnl);

        tbody.appendChild(row);
    });
}

// Removed renderExpiredPositions - futures don't have expired positions

// Render all orders table with data attributes for sorting
function renderAllOrders() {
    const tbody = document.querySelector('#allOrdersTable tbody');
    tbody.innerHTML = '';

    if (futuresData.all_orders.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="6" class="empty-message">No orders found</td>
            </tr>
        `;
        return;
    }

    futuresData.all_orders.forEach(order => {
        const row = document.createElement('tr');

        // Format dates to be more readable
        const formatDate = (dateStr) => {
            if (!dateStr) return '';
            const date = new Date(dateStr);
            return date.toLocaleString('en-US', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit'
            });
        };

        row.innerHTML = `
            <td>${order.symbol || order.contract_id}</td>
            <td>${formatDate(order.created_at)}</td>
            <td>${order.position_effect || ''}</td>
            <td>${order.order_side || ''}</td>
            <td>${order.filled_quantity || order.quantity || ''}</td>
            <td>$${order.average_price ? order.average_price.toFixed(2) : '0.00'}</td>
        `;

        // Add data attributes for sorting
        row.dataset.contractId = order.contract_id || '';
        row.dataset.date = order.created_at || '';
        row.dataset.positionEffect = order.position_effect || '';
        row.dataset.orderSide = order.order_side || '';
        row.dataset.quantity = parseFloat(order.filled_quantity || order.quantity || 0);
        row.dataset.price = parseFloat(order.average_price || 0);

        tbody.appendChild(row);
    });
}

// Helper function to populate filter dropdowns
function populateFilters() {
    // Get unique values
    const symbols = [...new Set(futuresData.all_orders.map(order => order.symbol || order.display_symbol))].filter(Boolean).sort();

    // Populate dropdowns
    populateFilterOptions('openSymbolFilter', symbols);
    populateFilterOptions('closedSymbolFilter', symbols);
    populateFilterOptions('allSymbolFilter', symbols);
    
    // Set default date range values - last 3 months
    setDefaultDateRanges();
    
    // Add event listeners
    setupFilterEventListeners();
}

// Helper to set default date ranges
function setDefaultDateRanges() {
    const today = new Date();
    const threeMonthsAgo = new Date();
    threeMonthsAgo.setMonth(today.getMonth() - 3);
    
    const todayStr = today.toISOString().split('T')[0];
    const threeMonthsAgoStr = threeMonthsAgo.toISOString().split('T')[0];
    
    // Set "from" date for all date filters (optional)
    document.getElementById('openDateFrom').value = threeMonthsAgoStr;
    document.getElementById('closedOpenDateFrom').value = threeMonthsAgoStr;
    document.getElementById('closedCloseDateFrom').value = '';
    document.getElementById('allDateFrom').value = threeMonthsAgoStr;
    
    // Set "to" date for all date filters
    document.getElementById('openDateTo').value = todayStr;
    document.getElementById('closedOpenDateTo').value = todayStr;
    document.getElementById('closedCloseDateTo').value = todayStr;
    document.getElementById('allDateTo').value = todayStr;
}

// Helper to populate a dropdown
function populateFilterOptions(filterId, options) {
    const filter = document.getElementById(filterId);
    
    // Keep the first "All" option
    const allOption = filter.options[0];
    filter.innerHTML = '';
    filter.appendChild(allOption);
    
    // Add options
    options.forEach(option => {
        if (option) {
            const optionEl = document.createElement('option');
            optionEl.value = option;
            optionEl.textContent = option;
            filter.appendChild(optionEl);
        }
    });
}