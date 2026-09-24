// Main JavaScript for Stocks Dashboard
let stocksData = null;
let currentFilter = { startDate: null, endDate: null };

// Load data on page load
document.addEventListener('DOMContentLoaded', () => {
    loadStocksData();
    setupEventListeners();
});

function setupEventListeners() {
    // Refresh button
    const refreshBtn = document.getElementById('refreshBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', refreshData);
    }

    // Tab switching
    document.querySelectorAll('.tab').forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });

    // Sub-tabs and the symbol modal are wired by the shared by-symbol view
    if (typeof window.BySymbolView !== 'undefined') {
        window.BySymbolView.setupUi();
    }

    // Date filter buttons
    document.getElementById('applyFilter').addEventListener('click', applyDateFilter);
    document.getElementById('clearFilter').addEventListener('click', clearDateFilter);

}

function switchTab(tabName) {
    // Update active tab
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
    document.getElementById(tabName).classList.add('active');

    // Initialize calendar if switching to calendar tab
    if (tabName === 'calendar') {
        if (!window.calendarManager) {
            window.calendarManager = new CalendarManager();
            window.calendarManager.initCalendar();
        }
    }
}


async function loadStocksData() {
    try {
        showLoading();

        // Fetch main data
        const response = await fetch('/api/stocks');
        const data = await response.json();

        if (data.error) {
            showError(data.error);
            return;
        }

        // Fetch open positions separately (requires login)
        try {
            const posResponse = await fetch('/api/open-positions');
            const posData = await posResponse.json();
            if (posData.success && posData.open_positions) {
                data.open_positions = posData.open_positions;
                // Update summary with unrealized P&L
                const unrealized_pnl = posData.open_positions.reduce((sum, pos) => sum + pos.unrealized_pnl, 0);
                data.summary.total_unrealized_pnl = unrealized_pnl;
                data.summary.num_open_positions = posData.open_positions.length;
            }
        } catch (e) {
            console.log('Could not fetch open positions:', e);
        }

        // Fetch closed positions
        try {
            const closedResponse = await fetch('/api/closed-positions');
            const closedData = await closedResponse.json();
            if (closedData.success && closedData.closed_positions) {
                data.closed_positions = closedData.closed_positions;
            }
        } catch (e) {
            console.log('Could not fetch closed positions:', e);
        }

        stocksData = data;
        renderDashboard(data);
        hideLoading();

    } catch (error) {
        console.error('Error loading stocks data:', error);
        showError('Failed to load stocks data');
    }
}

async function refreshData() {
    try {
        showLoading('Refreshing data from Robinhood...');

        const response = await fetch('/api/update', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const result = await response.json();

        if (result.error) {
            showError(result.error);
            return;
        }

        // Reload the data
        await loadStocksData();

        // Refresh calendar if visible
        if (window.calendarManager) {
            await window.calendarManager.refreshCalendar();
        }

    } catch (error) {
        console.error('Error refreshing data:', error);
        showError('Failed to refresh data');
    }
}

function renderDashboard(data) {
    renderSummary(data.summary, data.all_orders);
    renderOpenPositions(data.open_positions || []);
    renderClosedPositions(data.closed_positions || []);
    renderBySymbol(data.closed_positions || [], data.all_orders || []);
    renderOrders(data.all_orders);
}

function renderSummary(summary, orders = null) {
    const summaryDiv = document.getElementById('summary');
    const pnlClass = summary.total_pnl >= 0 ? 'profit' : 'loss';
    const pnlSign = summary.total_pnl >= 0 ? '+' : '';
    const unrealizedClass = summary.total_unrealized_pnl >= 0 ? 'profit' : 'loss';
    const unrealizedSign = summary.total_unrealized_pnl >= 0 ? '+' : '';

    summaryDiv.innerHTML = `
        <div class="summary-card">
            <h3>Realized P&L</h3>
            <div class="summary-value ${pnlClass}">${pnlSign}$${summary.total_pnl.toFixed(2)}</div>
        </div>
        <div class="summary-card">
            <h3>Unrealized P&L</h3>
            <div class="summary-value ${unrealizedClass}">${unrealizedSign}$${summary.total_unrealized_pnl.toFixed(2)}</div>
        </div>
        <div class="summary-card">
            <h3>Win Rate</h3>
            <div class="summary-value">${summary.win_rate}%</div>
            <div style="font-size: 0.8em; margin-top: 5px;">${summary.winning_trades}W / ${summary.losing_trades}L</div>
        </div>
        <div class="summary-card">
            <h3>Open Positions</h3>
            <div class="summary-value">${summary.num_open_positions}</div>
        </div>
        <div class="summary-card">
            <h3>Closed Positions</h3>
            <div class="summary-value">${summary.total_closed_positions}</div>
        </div>
        <div class="summary-card">
            <h3>Trading Days</h3>
            <div class="summary-value">${summary.num_trading_days} / ${summary.approx_market_days}</div>
        </div>
    `;

    // Set date filter values to first trade date and today
    if (orders && orders.length > 0) {
        const tradeDates = orders
            .map(o => o.trade_date)
            .filter(d => d)
            .sort();

        if (tradeDates.length > 0) {
            const firstDate = tradeDates[0];
            const today = new Date().toISOString().split('T')[0]; // Today's date in YYYY-MM-DD format

            const startDateInput = document.getElementById('startDate');
            const endDateInput = document.getElementById('endDate');

            // Only set if not already filtered
            if (startDateInput && !currentFilter.startDate) {
                startDateInput.value = firstDate;
            }
            if (endDateInput && !currentFilter.endDate) {
                endDateInput.value = today;
            }
        }
    }
}

function renderOpenPositions(positions) {
    const positionsDiv = document.getElementById('openPositions');

    let html = '<h2>Open Positions</h2>';

    if (positions.length === 0) {
        html += '<p>No open positions</p>';
    } else {
        html += '<table class="positions-table">';
        html += '<thead><tr>';
        html += '<th>Symbol</th>';
        html += '<th>Quantity</th>';
        html += '<th>Avg Buy Price</th>';
        html += '<th>Current Price</th>';
        html += '<th>Cost Basis</th>';
        html += '<th>Market Value</th>';
        html += '<th>Unrealized P&L</th>';
        html += '</tr></thead><tbody>';

        positions.forEach(pos => {
            const pnlClass = pos.unrealized_pnl >= 0 ? 'profit' : 'loss';
            const pnlSign = pos.unrealized_pnl >= 0 ? '+' : '';

            html += '<tr>';
            html += `<td><strong>${pos.symbol}</strong></td>`;
            html += `<td>${pos.quantity}</td>`;
            html += `<td>$${pos.average_buy_price.toFixed(2)}</td>`;
            html += `<td>$${pos.current_price.toFixed(2)}</td>`;
            html += `<td>$${pos.cost_basis.toFixed(2)}</td>`;
            html += `<td>$${pos.market_value.toFixed(2)}</td>`;
            html += `<td class="${pnlClass}">${pnlSign}$${pos.unrealized_pnl.toFixed(2)}</td>`;
            html += '</tr>';
        });

        html += '</tbody></table>';
    }

    positionsDiv.innerHTML = html;
}

function renderClosedPositions(positions) {
    const positionsDiv = document.getElementById('closedPositions');

    let html = '<h2>Closed Positions (FIFO Matched)</h2>';

    if (positions.length === 0) {
        html += '<p>No closed positions</p>';
    } else {
        html += '<table class="positions-table">';
        html += '<thead><tr>';
        html += '<th>Symbol</th>';
        html += '<th>Quantity</th>';
        html += '<th>Buy Date</th>';
        html += '<th>Sell Date</th>';
        html += '<th>Avg Buy Price</th>';
        html += '<th>Avg Sell Price</th>';
        html += '<th>P&L</th>';
        html += '</tr></thead><tbody>';

        positions.forEach(pos => {
            const pnlClass = pos.pnl >= 0 ? 'profit' : 'loss';
            const pnlSign = pos.pnl >= 0 ? '+' : '';

            html += '<tr>';
            html += `<td><strong>${pos.symbol}</strong></td>`;
            html += `<td>${pos.quantity}</td>`;
            html += `<td>${pos.buy_date}</td>`;
            html += `<td>${pos.sell_date}</td>`;
            html += `<td>$${pos.buy_price.toFixed(2)}</td>`;
            html += `<td>$${pos.sell_price.toFixed(2)}</td>`;
            html += `<td class="${pnlClass}">${pnlSign}$${pos.pnl.toFixed(2)}</td>`;
            html += '</tr>';
        });

        html += '</tbody></table>';
    }

    positionsDiv.innerHTML = html;
}

function renderBySymbol(closedPositions, orders = null) {
    // The shared view groups and renders; it reads field names from the asset
    // config, so options and futures get the same view from the same code
    if (!window.bySymbolView) {
        window.bySymbolView = new window.BySymbolView({ assetType: 'stocks' });
    }

    // Pass whatever is on screen, so the date filter reaches the view too
    window.bySymbolView.render({
        closed_positions: closedPositions || [],
        all_orders: orders || (stocksData && stocksData.all_orders) || []
    });
}

function renderOrders(orders) {
    const ordersDiv = document.getElementById('allOrders');

    let html = '<h2>All Stock Orders</h2>';
    html += '<table class="orders-table">';
    html += '<thead><tr>';
    html += '<th>Date</th>';
    html += '<th>Symbol</th>';
    html += '<th>Side</th>';
    html += '<th>Quantity</th>';
    html += '<th>Price</th>';
    html += '<th>Total</th>';
    html += '</tr></thead><tbody>';

    orders.forEach(order => {
        const date = new Date(order.last_transaction_at).toLocaleDateString();
        const sideClass = order.side === 'buy' ? 'buy' : 'sell';

        html += '<tr>';
        html += `<td>${date}</td>`;
        html += `<td>${order.symbol}</td>`;
        html += `<td class="${sideClass}">${order.side.toUpperCase()}</td>`;
        html += `<td>${order.quantity}</td>`;
        html += `<td>$${order.average_price.toFixed(2)}</td>`;
        html += `<td>$${order.total_amount.toFixed(2)}</td>`;
        html += '</tr>';
    });

    html += '</tbody></table>';
    ordersDiv.innerHTML = html;
}

function showLoading(message = 'Loading...') {
    document.getElementById('loadingIndicator').textContent = message;
    document.getElementById('loadingIndicator').style.display = 'block';
    document.getElementById('errorMessage').style.display = 'none';
    document.getElementById('dashboardContent').style.display = 'none';
}

function hideLoading() {
    document.getElementById('loadingIndicator').style.display = 'none';
    document.getElementById('dashboardContent').style.display = 'block';
}

function showError(message) {
    document.getElementById('errorMessage').textContent = message;
    document.getElementById('errorMessage').style.display = 'block';
    document.getElementById('loadingIndicator').style.display = 'none';
}

function applyDateFilter() {
    const startDate = document.getElementById('startDate').value;
    const endDate = document.getElementById('endDate').value;

    currentFilter.startDate = startDate || null;
    currentFilter.endDate = endDate || null;

    // Re-render with filtered data
    renderFilteredData();
}

function clearDateFilter() {
    currentFilter.startDate = null;
    currentFilter.endDate = null;

    // Re-render with all data (this will reset the date inputs to first/last trade dates)
    renderFilteredData();
}

function renderFilteredData() {
    if (!stocksData) return;

    // Filter closed positions
    const filteredClosed = filterByDateRange(
        stocksData.closed_positions || [],
        'sell_date'
    );

    // Filter all orders
    const filteredOrders = filterByDateRange(
        stocksData.all_orders || [],
        'trade_date'
    );

    // Calculate filtered summary stats
    const filteredSummary = calculateFilteredSummary(filteredClosed, filteredOrders);

    // Re-render with filtered data
    renderSummary(filteredSummary, filteredOrders);
    renderClosedPositions(filteredClosed);
    renderBySymbol(filteredClosed, filteredOrders);
    renderOrders(filteredOrders);
}

function filterByDateRange(items, dateField) {
    if (!currentFilter.startDate && !currentFilter.endDate) {
        return items;
    }

    return items.filter(item => {
        const itemDate = item[dateField];
        if (!itemDate) return false;

        if (currentFilter.startDate && itemDate < currentFilter.startDate) {
            return false;
        }
        if (currentFilter.endDate && itemDate > currentFilter.endDate) {
            return false;
        }
        return true;
    });
}

function calculateFilteredSummary(closedPositions, allOrders) {
    // Calculate stats from filtered data
    const totalPnl = closedPositions.reduce((sum, pos) => sum + pos.pnl, 0);
    const winningTrades = closedPositions.filter(pos => pos.pnl > 0).length;
    const losingTrades = closedPositions.filter(pos => pos.pnl < 0).length;
    const totalClosed = closedPositions.length;
    const winRate = totalClosed > 0 ? (winningTrades / totalClosed * 100) : 0;

    // Get unique trading dates from filtered orders
    const tradingDates = new Set(allOrders.map(o => o.trade_date).filter(d => d));
    const numTradingDays = tradingDates.size;

    // Keep original values for non-filtered fields
    const originalSummary = stocksData.summary;

    return {
        total_pnl: totalPnl,
        total_unrealized_pnl: originalSummary.total_unrealized_pnl,  // Not filtered
        total_fees: originalSummary.total_fees,
        num_orders: allOrders.length,
        num_open_positions: originalSummary.num_open_positions,  // Not filtered
        num_trading_days: numTradingDays,
        approx_market_days: originalSummary.approx_market_days,  // Keep original
        total_closed_positions: totalClosed,
        winning_trades: winningTrades,
        losing_trades: losingTrades,
        win_rate: Math.round(winRate * 10) / 10
    };
}
