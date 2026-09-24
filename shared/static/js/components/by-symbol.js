/**
 * By-symbol view: P&L grouped by underlying, as a table and a heat map, with a
 * per-symbol detail modal.
 *
 * Built for stocks first; this is the shared version, so options and futures
 * get the same feature rather than a second and third implementation. What each
 * asset calls its symbol, its P&L and its orders comes from the asset's
 * `bySymbol` block in asset-config.js.
 */

const HEATMAP = {
    minSize: 50,
    maxSize: 150,
    // A box needs to be this big, with this many trades, before it has room
    // for the win-rate line
    winRateMinSize: 80,
    winRateMinTrades: 3
};

function money2(value) {
    const amount = Number(value || 0);
    return `${amount >= 0 ? '+' : ''}$${amount.toFixed(2)}`;
}

function pnlClass2(value) {
    return Number(value || 0) >= 0 ? 'profit' : 'loss';
}

function escapeHtml2(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

/** Safe inside a single-quoted HTML attribute, for the click handlers. */
function escapeAttr(value) {
    return escapeHtml2(value).replace(/'/g, '&#39;');
}


class BySymbolView {
    /**
     * @param {Object} [options]
     * @param {string} [options.assetType] - defaults to the current selection
     * @param {Object} [options.config] - AssetConfig, for tests
     */
    constructor(options = {}) {
        this.assetType = options.assetType || null;
        this._config = options.config || null;
        this.data = null;
    }

    get config() {
        return this._config || window.AssetConfig;
    }

    /** This asset's by-symbol settings. */
    get settings() {
        return this.config.get(this.assetType).bySymbol;
    }

    /** Closed trades for this asset, from wherever its payload keeps them. */
    closedTrades(data) {
        const trades = [];
        for (const key of this.settings.closedFrom) {
            const rows = (data || {})[key];
            if (Array.isArray(rows)) trades.push(...rows);
        }
        return trades;
    }

    /**
     * Group closed trades by symbol.
     * @returns {Array} one row per symbol, best total P&L first
     */
    groupBySymbol(data) {
        const { symbolField, pnlField, quantityField } = this.settings;
        const bySymbol = {};

        for (const trade of this.closedTrades(data)) {
            const symbol = trade[symbolField];
            if (!symbol) continue;

            if (!bySymbol[symbol]) {
                bySymbol[symbol] = {
                    symbol,
                    total_pnl: 0,
                    total_quantity: 0,
                    num_trades: 0,
                    winning_trades: 0,
                    losing_trades: 0
                };
            }

            const pnl = Number(trade[pnlField]) || 0;
            const stat = bySymbol[symbol];
            stat.total_pnl += pnl;
            stat.total_quantity += Number(trade[quantityField]) || 0;
            stat.num_trades += 1;
            if (pnl > 0) stat.winning_trades += 1;
            else if (pnl < 0) stat.losing_trades += 1;
        }

        return Object.values(bySymbol).sort((a, b) => b.total_pnl - a.total_pnl);
    }

    winRate(stat) {
        return stat.num_trades > 0 ? (stat.winning_trades / stat.num_trades * 100) : 0;
    }

    averagePnl(stat) {
        return stat.num_trades > 0 ? stat.total_pnl / stat.num_trades : 0;
    }

    /** The table view. */
    renderTable(stats) {
        if (stats.length === 0) return '<p>No closed positions</p>';

        const rows = stats.map(stat => {
            const average = this.averagePnl(stat);
            return `<tr onclick="showSymbolTrades('${escapeAttr(stat.symbol)}')" style="cursor: pointer;">`
                 + `<td><strong>${escapeHtml2(stat.symbol)}</strong></td>`
                 + `<td class="${pnlClass2(stat.total_pnl)}">${money2(stat.total_pnl)}</td>`
                 + `<td>${stat.num_trades} (${stat.winning_trades}W / ${stat.losing_trades}L)</td>`
                 + `<td>${this.winRate(stat).toFixed(1)}%</td>`
                 + `<td class="${pnlClass2(average)}">${money2(average)}</td>`
                 + '</tr>';
        }).join('');

        return '<table class="positions-table"><thead><tr>'
             + '<th>Symbol</th><th>Total P&L</th><th>Trades</th><th>Win Rate</th>'
             + '<th>Avg P&L per Trade</th>'
             + `</tr></thead><tbody>${rows}</tbody></table>`;
    }

    /** The heat map: box area carries magnitude, colour carries direction. */
    renderHeatmap(stats) {
        if (stats.length === 0) return '<p>No closed positions</p>';

        const maxAbs = Math.max(...stats.map(s => Math.abs(s.total_pnl))) || 1;

        const boxes = stats.map(stat => {
            const pnl = stat.total_pnl;
            const absPnl = Math.abs(pnl);

            // Square root so a box twice the P&L is not four times the area
            const sizeFactor = Math.sqrt(absPnl / maxAbs);
            const size = HEATMAP.minSize + sizeFactor * (HEATMAP.maxSize - HEATMAP.minSize);

            const symbolSize = Math.max(0.6, size / 100);
            const pnlSize = Math.max(0.7, size / 90);
            const detailSize = Math.max(0.5, size / 140);

            let backgroundColor;
            if (pnl > 0) {
                const channel = Math.floor(80 + Math.min(absPnl / maxAbs, 1) * 120);
                backgroundColor = `rgb(34, ${channel}, 34)`;
            } else if (pnl < 0) {
                const channel = Math.floor(80 + Math.min(absPnl / maxAbs, 1) * 120);
                backgroundColor = `rgb(${channel}, 34, 34)`;
            } else {
                backgroundColor = '#888';
            }

            const roomForWinRate = size > HEATMAP.winRateMinSize
                                && stat.num_trades >= HEATMAP.winRateMinTrades;
            const sign = pnl >= 0 ? '+' : '';

            return `
            <div class="heatmap-box" style="
                width: ${size}px;
                height: ${size}px;
                background-color: ${backgroundColor};
                color: white;
            " onclick="showSymbolTrades('${escapeAttr(stat.symbol)}')">
                <div class="heatmap-symbol" style="font-size: ${symbolSize}em;">${escapeHtml2(stat.symbol)}</div>
                <div class="heatmap-pnl" style="font-size: ${pnlSize}em;">${sign}$${pnl.toFixed(0)}</div>
                ${roomForWinRate ? `<div class="heatmap-trades" style="font-size: ${detailSize}em;">${stat.num_trades} trades</div>` : ''}
                ${roomForWinRate ? `<div class="heatmap-winrate" style="font-size: ${detailSize}em;">${this.winRate(stat).toFixed(0)}% WR</div>` : ''}
            </div>
        `;
        }).join('');

        return `<div class="heatmap-container">${boxes}</div>`;
    }

    /** Orders for one symbol, oldest first. */
    symbolOrders(symbol, data) {
        const { ordersFrom, orderSymbolField, orderDateField } = this.settings;
        const orders = (data || {})[ordersFrom] || [];

        return orders
            .filter(order => order[orderSymbolField] === symbol)
            .sort((a, b) => new Date(a[orderDateField]) - new Date(b[orderDateField]));
    }

    /** Closed trades for one symbol. */
    symbolClosed(symbol, data) {
        const { symbolField } = this.settings;
        return this.closedTrades(data).filter(trade => trade[symbolField] === symbol);
    }

    /** The per-symbol detail modal body. */
    renderSymbolDetail(symbol, data) {
        const { pnlField, quantityField, unitLabel } = this.settings;

        const orders = this.symbolOrders(symbol, data);
        const closed = this.symbolClosed(symbol, data);

        const totalPnl = closed.reduce((sum, trade) => sum + (Number(trade[pnlField]) || 0), 0);
        const traded = orders.reduce((sum, order) => sum + (Number(order[quantityField]) || 0), 0);
        const pnls = closed.map(trade => Number(trade[pnlField]) || 0);
        const largestWin = pnls.length ? Math.max(...pnls) : 0;
        const largestLoss = pnls.length ? Math.min(...pnls) : 0;

        let html = `
        <div style="margin-bottom: 20px; padding: 10px; background: #f5f5f5; border-radius: 4px;">
            <strong>Symbol Summary:</strong> ${traded} ${escapeHtml2(unitLabel)} traded
            <br>
            <strong>Realized P&L:</strong>
            <span class="${pnlClass2(totalPnl)}">
                ${money2(totalPnl)}
            </span>
    `;

        if (closed.length > 0) {
            html += `
            <br>
            <strong>Largest Win:</strong>
            <span class="${pnlClass2(largestWin)}">
                ${money2(largestWin)}
            </span>
            &nbsp;&nbsp;
            <strong>Largest Loss:</strong>
            <span class="${pnlClass2(largestLoss)}">
                ${money2(largestLoss)}
            </span>
        `;
        }

        html += '</div>';

        if (closed.length > 0) {
            html += this._scrollingTable(
                `Closed Positions (${closed.length})`,
                closed,
                this.settings.closedColumns
            ) + '<br>';
        }

        html += this._scrollingTable(
            `All Orders (${orders.length})`,
            orders,
            this.settings.orderColumns
        );

        return html;
    }

    /**
     * A heading plus a table that scrolls rather than pushing the modal open.
     * @private
     */
    _scrollingTable(heading, rows, columns) {
        const head = columns.map(c => `<th>${escapeHtml2(c.label)}</th>`).join('');
        const body = rows.map(row =>
            `<tr>${columns.map(column => this._cell(row, column)).join('')}</tr>`
        ).join('');

        return `
            <h3>${escapeHtml2(heading)}</h3>
            <div style="max-height: 300px; overflow-y: auto; border: 1px solid #ddd; border-radius: 4px;">
                <table class="position-details-table">
                    <thead><tr>${head}</tr></thead>
                    <tbody>${body}</tbody>
                </table>
            </div>
        `;
    }

    /** @private */
    _cell(row, column) {
        const raw = row[column.key];

        switch (column.format) {
            case 'currency':
                return `<td>$${Number(raw || 0).toFixed(2)}</td>`;
            case 'signedPnl':
                return `<td class="${pnlClass2(raw)}">${money2(raw)}</td>`;
            case 'side':
                return `<td class="${raw === 'buy' ? 'buy' : 'sell'}">${escapeHtml2(String(raw || '').toUpperCase())}</td>`;
            case 'date':
                return `<td>${raw ? escapeHtml2(new Date(raw).toLocaleDateString()) : ''}</td>`;
            default:
                return `<td>${escapeHtml2(raw)}</td>`;
        }
    }

    /** Render both views into their containers. */
    render(data, { tableEl, heatmapEl } = {}) {
        this.data = data;
        const stats = this.groupBySymbol(data);

        const table = tableEl || document.getElementById('table');
        const heatmap = heatmapEl || document.getElementById('heatmap');

        if (table) table.innerHTML = this.renderTable(stats);
        if (heatmap) heatmap.innerHTML = this.renderHeatmap(stats);

        return stats;
    }

    /** Open the detail modal for one symbol. */
    showSymbol(symbol, data = null) {
        const payload = data || this.data;
        if (!payload) return;

        const title = document.getElementById('symbolModalTitle');
        const body = document.getElementById('symbolModalTrades');
        const modal = document.getElementById('symbolModal');
        if (!title || !body || !modal) return;

        title.textContent = `Trading Summary - ${symbol}`;
        body.innerHTML = this.renderSymbolDetail(symbol, payload);
        modal.style.display = 'block';
    }
}

/**
 * Wire the sub-tabs and the modal close, so every dashboard gets the same
 * behaviour without repeating the handlers.
 */
BySymbolView.setupUi = function () {
    document.querySelectorAll('.sub-tab').forEach(tab => {
        tab.addEventListener('click', () => BySymbolView.switchSubTab(tab.dataset.subtab));
    });

    const close = document.getElementById('symbolModalClose');
    if (close) {
        close.addEventListener('click', () => {
            document.getElementById('symbolModal').style.display = 'none';
        });
    }

    window.addEventListener('click', (event) => {
        const modal = document.getElementById('symbolModal');
        if (modal && event.target === modal) {
            modal.style.display = 'none';
        }
    });
};

BySymbolView.switchSubTab = function (name) {
    document.querySelectorAll('.sub-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.sub-tab-content').forEach(c => c.classList.remove('active'));

    const tab = document.querySelector(`[data-subtab="${name}"]`);
    const content = document.getElementById(name);
    if (tab) tab.classList.add('active');
    if (content) content.classList.add('active');
};

window.BySymbolView = BySymbolView;

// The table rows and heat-map boxes call this from their onclick
window.showSymbolTrades = function (symbol) {
    if (window.bySymbolView) {
        window.bySymbolView.showSymbol(symbol);
    }
};
