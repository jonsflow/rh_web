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

    // Sub-tab switching (nested tabs)
    document.querySelectorAll('.sub-tab').forEach(tab => {
        tab.addEventListener('click', () => switchSubTab(tab.dataset.subtab));
    });

    // Date filter buttons
    document.getElementById('applyFilter').addEventListener('click', applyDateFilter);
    document.getElementById('clearFilter').addEventListener('click', clearDateFilter);

    // Symbol modal close button
    const symbolModalClose = document.getElementById('symbolModalClose');
    if (symbolModalClose) {
        symbolModalClose.addEventListener('click', () => {
            document.getElementById('symbolModal').style.display = 'none';
        });
    }

    // Close modal when clicking outside
    window.addEventListener('click', (event) => {
        const symbolModal = document.getElementById('symbolModal');
        if (event.target === symbolModal) {
            symbolModal.style.display = 'none';
        }
    });
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

function switchSubTab(subtabName) {
    // Update active sub-tab
    document.querySelectorAll('.sub-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.sub-tab-content').forEach(c => c.classList.remove('active'));

    document.querySelector(`[data-subtab="${subtabName}"]`).classList.add('active');
    document.getElementById(subtabName).classList.add('active');
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
    renderBySymbol(data.closed_positions || []);
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

function renderBySymbol(closedPositions) {
    // Group by symbol and calculate totals
    const symbolStats = {};

    closedPositions.forEach(pos => {
        const symbol = pos.symbol;
        if (!symbolStats[symbol]) {
            symbolStats[symbol] = {
                symbol: symbol,
                total_pnl: 0,
                total_quantity: 0,
                num_trades: 0,
                winning_trades: 0,
                losing_trades: 0
            };
        }

        symbolStats[symbol].total_pnl += pos.pnl;
        symbolStats[symbol].total_quantity += pos.quantity;
        symbolStats[symbol].num_trades += 1;

        if (pos.pnl > 0) {
            symbolStats[symbol].winning_trades += 1;
        } else if (pos.pnl < 0) {
            symbolStats[symbol].losing_trades += 1;
        }
    });

    // Convert to array and sort by total P&L (descending)
    const symbolArray = Object.values(symbolStats).sort((a, b) => b.total_pnl - a.total_pnl);

    // Render both heatmap and table views
    renderHeatmap(symbolArray);
    renderSymbolTable(symbolArray);
}

function renderHeatmap(symbolArray) {
    const heatmapDiv = document.getElementById('heatmap');

    if (symbolArray.length === 0) {
        heatmapDiv.innerHTML = '<p>No closed positions</p>';
        return;
    }

    // Find max absolute P&L for sizing
    const maxAbsPnl = Math.max(...symbolArray.map(s => Math.abs(s.total_pnl)));

    let html = '<div class="heatmap-container">';

    symbolArray.forEach(stat => {
        const pnl = stat.total_pnl;
        const absPnl = Math.abs(pnl);

        // Size: smaller range to fit on one page (50px to 150px)
        const minSize = 50;
        const maxSize = 150;
        const sizeRange = maxSize - minSize;
        // Use square root for better distribution
        const sizeFactor = Math.sqrt(absPnl / maxAbsPnl);
        const size = minSize + (sizeFactor * sizeRange);

        // Scale font sizes with box size (more aggressive scaling)
        const symbolSize = Math.max(0.6, size / 100); // Ticker scales with box
        const pnlSize = Math.max(0.7, size / 90);      // P&L scales with box
        const detailSize = Math.max(0.5, size / 140);  // Details scale with box

        // Color intensity based on P&L magnitude
        let backgroundColor, textColor;
        if (pnl > 0) {
            // Green for profit - darker green for higher profit
            const intensity = Math.min(absPnl / maxAbsPnl, 1);
            const greenValue = Math.floor(80 + intensity * 120); // 80-200
            backgroundColor = `rgb(34, ${greenValue}, 34)`;
            textColor = 'white';
        } else if (pnl < 0) {
            // Red for loss - darker red for higher loss
            const intensity = Math.min(absPnl / maxAbsPnl, 1);
            const redValue = Math.floor(80 + intensity * 120); // 80-200
            backgroundColor = `rgb(${redValue}, 34, 34)`;
            textColor = 'white';
        } else {
            backgroundColor = '#888';
            textColor = 'white';
        }

        const pnlSign = pnl >= 0 ? '+' : '';
        const winRate = stat.num_trades > 0 ? (stat.winning_trades / stat.num_trades * 100) : 0;

        // Only show win rate if box is big enough (>80px) and has 3+ trades
        const showWinRate = size > 80 && stat.num_trades >= 3;

        html += `
            <div class="heatmap-box" style="
                width: ${size}px;
                height: ${size}px;
                background-color: ${backgroundColor};
                color: ${textColor};
            " onclick="showSymbolTrades('${stat.symbol}')">
                <div class="heatmap-symbol" style="font-size: ${symbolSize}em;">${stat.symbol}</div>
                <div class="heatmap-pnl" style="font-size: ${pnlSize}em;">${pnlSign}$${pnl.toFixed(0)}</div>
                ${showWinRate ? `<div class="heatmap-trades" style="font-size: ${detailSize}em;">${stat.num_trades} trades</div>` : ''}
                ${showWinRate ? `<div class="heatmap-winrate" style="font-size: ${detailSize}em;">${winRate.toFixed(0)}% WR</div>` : ''}
            </div>
        `;
    });

    html += '</div>';
    heatmapDiv.innerHTML = html;
}

function renderSymbolTable(symbolArray) {
    const tableDiv = document.getElementById('table');

    if (symbolArray.length === 0) {
        tableDiv.innerHTML = '<p>No closed positions</p>';
        return;
    }

    let html = '<table class="positions-table">';
    html += '<thead><tr>';
    html += '<th>Symbol</th>';
    html += '<th>Total P&L</th>';
    html += '<th>Trades</th>';
    html += '<th>Win Rate</th>';
    html += '<th>Avg P&L per Trade</th>';
    html += '</tr></thead><tbody>';

    symbolArray.forEach(stat => {
        const pnlClass = stat.total_pnl >= 0 ? 'profit' : 'loss';
        const pnlSign = stat.total_pnl >= 0 ? '+' : '';
        const winRate = stat.num_trades > 0 ? (stat.winning_trades / stat.num_trades * 100) : 0;
        const avgPnl = stat.num_trades > 0 ? stat.total_pnl / stat.num_trades : 0;
        const avgPnlClass = avgPnl >= 0 ? 'profit' : 'loss';
        const avgPnlSign = avgPnl >= 0 ? '+' : '';

        html += `<tr onclick="showSymbolTrades('${stat.symbol}')" style="cursor: pointer;">`;
        html += `<td><strong>${stat.symbol}</strong></td>`;
        html += `<td class="${pnlClass}">${pnlSign}$${stat.total_pnl.toFixed(2)}</td>`;
        html += `<td>${stat.num_trades} (${stat.winning_trades}W / ${stat.losing_trades}L)</td>`;
        html += `<td>${winRate.toFixed(1)}%</td>`;
        html += `<td class="${avgPnlClass}">${avgPnlSign}$${avgPnl.toFixed(2)}</td>`;
        html += '</tr>';
    });

    html += '</tbody></table>';
    tableDiv.innerHTML = html;
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

function showSymbolTrades(symbol) {
    if (!stocksData || !stocksData.all_orders) return;

    // Get all orders for this symbol
    const symbolOrders = stocksData.all_orders
        .filter(order => order.symbol === symbol)
        .sort((a, b) => new Date(a.last_transaction_at) - new Date(b.last_transaction_at));

    if (symbolOrders.length === 0) {
        return;
    }

    // Get closed positions (FIFO-matched) for this symbol
    const closedPositions = stocksData.closed_positions ?
        stocksData.closed_positions.filter(pos => pos.symbol === symbol) : [];
    const totalPnl = closedPositions.reduce((sum, pos) => sum + pos.pnl, 0);

    // Calculate shares traded (total buy + sell volume)
    const sharesTraded = symbolOrders.reduce((sum, order) => sum + order.quantity, 0);

    // Find largest win and loss
    const largestWin = closedPositions.length > 0 ?
        Math.max(...closedPositions.map(p => p.pnl)) : 0;
    const largestLoss = closedPositions.length > 0 ?
        Math.min(...closedPositions.map(p => p.pnl)) : 0;

    // Set modal title
    const modalTitle = document.getElementById('symbolModalTitle');
    modalTitle.textContent = `Trading Summary - ${symbol}`;

    let html = '';

    // Summary section (styled like calendar modal)
    html += `
        <div style="margin-bottom: 20px; padding: 10px; background: #f5f5f5; border-radius: 4px;">
            <strong>Symbol Summary:</strong> ${sharesTraded} shares traded
            <br>
            <strong>Realized P&L:</strong>
            <span class="${totalPnl >= 0 ? 'profit' : 'loss'}">
                ${totalPnl >= 0 ? '+' : ''}$${totalPnl.toFixed(2)}
            </span>
    `;

    if (closedPositions.length > 0) {
        html += `
            <br>
            <strong>Largest Win:</strong>
            <span class="${largestWin >= 0 ? 'profit' : 'loss'}">
                ${largestWin >= 0 ? '+' : ''}$${largestWin.toFixed(2)}
            </span>
            &nbsp;&nbsp;
            <strong>Largest Loss:</strong>
            <span class="${largestLoss >= 0 ? 'profit' : 'loss'}">
                ${largestLoss >= 0 ? '+' : ''}$${largestLoss.toFixed(2)}
            </span>
        `;
    }

    html += '</div>';

    // Closed positions table (FIFO-matched trades)
    if (closedPositions.length > 0) {
        html += `
            <h3>Closed Positions (${closedPositions.length})</h3>
            <div style="max-height: 300px; overflow-y: auto; border: 1px solid #ddd; border-radius: 4px;">
                <table class="position-details-table">
                    <thead>
                        <tr>
                            <th>Buy Date</th>
                            <th>Sell Date</th>
                            <th>Quantity</th>
                            <th>Avg Buy Price</th>
                            <th>Avg Sell Price</th>
                            <th>P&L</th>
                        </tr>
                    </thead>
                    <tbody>
        `;

        closedPositions.forEach(pos => {
            const pnlClass = pos.pnl >= 0 ? 'profit' : 'loss';
            const pnlSign = pos.pnl >= 0 ? '+' : '';

            html += `
                <tr>
                    <td>${pos.buy_date}</td>
                    <td>${pos.sell_date}</td>
                    <td>${pos.quantity}</td>
                    <td>$${pos.buy_price.toFixed(2)}</td>
                    <td>$${pos.sell_price.toFixed(2)}</td>
                    <td class="${pnlClass}">${pnlSign}$${pos.pnl.toFixed(2)}</td>
                </tr>
            `;
        });

        html += `
                    </tbody>
                </table>
            </div>
            <br>
        `;
    }

    // All orders section - scrollable
    html += `
        <h3>All Orders (${symbolOrders.length})</h3>
        <div style="max-height: 300px; overflow-y: auto; border: 1px solid #ddd; border-radius: 4px;">
            <table class="position-details-table">
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Side</th>
                        <th>Quantity</th>
                        <th>Price</th>
                        <th>Total</th>
                    </tr>
                </thead>
                <tbody>
    `;

    symbolOrders.forEach(order => {
        const date = new Date(order.last_transaction_at).toLocaleDateString();
        const sideClass = order.side === 'buy' ? 'buy' : 'sell';

        html += `
            <tr>
                <td>${date}</td>
                <td class="${sideClass}">${order.side.toUpperCase()}</td>
                <td>${order.quantity}</td>
                <td>$${order.average_price.toFixed(2)}</td>
                <td>$${order.total_amount.toFixed(2)}</td>
            </tr>
        `;
    });

    html += `
                </tbody>
            </table>
        </div>
    `;

    // Show modal
    document.getElementById('symbolModalTrades').innerHTML = html;
    document.getElementById('symbolModal').style.display = 'block';
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
    renderBySymbol(filteredClosed);
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
