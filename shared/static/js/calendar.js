/**
 * Calendar view of daily P&L, shared by every asset.
 *
 * One renderer replaces three that had drifted apart. What differs per asset is
 * configuration, not code: which P&L field the day shows, whether a day with
 * only opened positions gets its own colour, and what the day-detail modal puts
 * in its tables. All of that lives in the asset's `calendar` block in
 * asset-config.js.
 *
 * Requests go through ApiService, so the calendar follows the selected asset and
 * account without knowing either.
 */

const DAY_COLORS = {
    profit: '#28a745',
    loss: '#dc3545',
    opened: '#007bff'
};

/** Money with two decimals, e.g. $12.34 -- negatives read $-12.34, as before. */
function money(value) {
    return `$${Number(value || 0).toFixed(2)}`;
}

/** Money with an explicit + on gains, e.g. +$12.34. */
function signedMoney(value) {
    const amount = Number(value || 0);
    return `${amount >= 0 ? '+' : ''}$${amount.toFixed(2)}`;
}

function pnlClass(value) {
    return Number(value || 0) >= 0 ? 'profit' : 'loss';
}

/** Market-hours timestamp: Eastern, so it matches the trading day. */
function marketTime(value) {
    if (!value) return '';
    return new Date(value).toLocaleString('en-US', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        timeZone: 'America/New_York'
    });
}

function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

/** Read a dotted path, e.g. pick(payload, 'summary.totals'). */
function pick(source, path) {
    if (!path) return source;
    return path.split('.').reduce(
        (value, key) => (value === null || value === undefined ? undefined : value[key]),
        source
    );
}

/** Render one cell according to its column's format. */
function renderCell(row, column) {
    const raw = column.key ? pick(row, column.key) : undefined;

    switch (column.format) {
        case 'strong':
            return `<td><strong>${escapeHtml(raw)}</strong></td>`;
        case 'currency':
            return `<td>${money(raw)}</td>`;
        case 'pnl':
            return `<td class="${pnlClass(raw)}">${money(raw)}</td>`;
        case 'signedPnl':
            return `<td class="${pnlClass(raw)}">${signedMoney(raw)}</td>`;
        case 'datetime':
            return `<td>${escapeHtml(marketTime(raw))}</td>`;
        case 'side':
            return `<td class="${raw === 'buy' ? 'buy' : 'sell'}">${escapeHtml(String(raw || '').toUpperCase())}</td>`;
        case 'number':
            return `<td>${raw === null || raw === undefined ? '' : escapeHtml(raw)}</td>`;
        case 'fallback':
            // first key that has a value, e.g. symbol then contract_id
            for (const key of column.keys) {
                const value = pick(row, key);
                if (value !== null && value !== undefined && value !== '') {
                    return `<td>${escapeHtml(value)}</td>`;
                }
            }
            return '<td></td>';
        default:
            return `<td>${escapeHtml(raw === null || raw === undefined ? column.empty || '' : raw)}</td>`;
    }
}

function renderTable(rows, columns, totalsRow = null) {
    const head = columns.map(c => `<th>${escapeHtml(c.label)}</th>`).join('');
    const body = rows.map(row =>
        `<tr>${columns.map(column => renderCell(row, column)).join('')}</tr>`
    ).join('');

    let totals = '';
    if (totalsRow) {
        const cells = totalsRow.columns.map(column => (
            column.literal !== undefined
                ? `<td>${escapeHtml(column.literal)}</td>`
                : renderCell(totalsRow.data, column)
        )).join('');
        totals = `<tr style="font-weight: bold; border-top: 2px solid #666;">${cells}</tr>`;
    }

    return `<table class="position-details-table"><thead><tr>${head}</tr></thead>`
         + `<tbody>${body}${totals}</tbody></table>`;
}


class CalendarManager {
    /**
     * @param {Object} [options]
     * @param {string} [options.assetType] - defaults to the current selection
     * @param {Object} [options.config] - AssetConfig, for tests
     * @param {Object} [options.api] - ApiService, for tests
     */
    constructor(options = {}) {
        this.calendar = null;
        this.dailyPnlData = {};
        this.daySummaries = {};
        this.assetType = options.assetType || null;
        this._config = options.config || null;
        this._api = options.api || null;
    }

    get config() {
        return this._config || window.AssetConfig;
    }

    get api() {
        return this._api || window.ApiService;
    }

    /** This asset's calendar settings. */
    get settings() {
        return this.config.get(this.assetType).calendar;
    }

    async initCalendar() {
        const calendarEl = document.getElementById('calendarView');

        if (!calendarEl) {
            console.error('Calendar element not found');
            return;
        }

        this.calendar = new FullCalendar.Calendar(calendarEl, {
            initialView: 'dayGridMonth',
            headerToolbar: {
                left: 'prev,next today',
                center: 'title',
                right: 'dayGridMonth,dayGridWeek'
            },
            height: 'auto',
            events: this.loadCalendarEvents.bind(this),
            eventClick: this.handleEventClick.bind(this),
            eventContent: this.renderEventContent.bind(this),
            eventDidMount: this.styleEventElement.bind(this),
            datesSet: this.onDatesSet.bind(this)
        });

        this.calendar.render();
        this.setupModal();
    }

    async onDatesSet(dateInfo) {
        // Load data when the calendar view changes (month navigation)
        await this.loadPnlData(dateInfo.startStr, dateInfo.endStr);
        // Note: updateMonthlyPnlSummary will be called in loadCalendarEvents
    }

    async loadPnlData(startDate, endDate) {
        try {
            const data = await this.api.fetchDailyPnl(startDate, endDate, {
                assetType: this.assetType
            });
            this.dailyPnlData = data.daily_pnl || {};
        } catch (error) {
            console.error('Error fetching daily P&L data:', error);
        }
    }

    /** The figure this asset puts on the day. */
    dayPnl(dayData) {
        return Number((dayData || {})[this.settings.pnlField] || 0);
    }

    /**
     * Per-day position counts, for assets that colour days by activity.
     *
     * Costs one request per trading date, which is why only the assets that
     * need it ask: the day states are what distinguish a day that only opened
     * positions from one with no activity at all.
     */
    async loadDaySummaries(startDate, endDate) {
        const summaries = {};
        try {
            const dates = (await this.api.fetchAllTradingDates({ assetType: this.assetType })).dates || [];

            for (const date of dates) {
                if (date < startDate || date > endDate) continue;

                try {
                    const data = await this.api.fetchDailySummary(date, { assetType: this.assetType });
                    const totals = (data.summary || {}).totals;
                    if (totals && (totals.positions_closed > 0 || totals.positions_opened > 0)) {
                        summaries[date] = {
                            positions_closed: totals.positions_closed,
                            positions_opened: totals.positions_opened
                        };
                    }
                } catch (error) {
                    console.error(`Error loading summary for ${date}:`, error);
                }
            }
        } catch (error) {
            console.error('Failed to load trading dates:', error);
        }
        return summaries;
    }

    updateMonthlyPnlSummary(dateInfo) {
        // Get the actual month/year being displayed (center of the view)
        const viewStart = new Date(dateInfo.start);
        const viewEnd = new Date(dateInfo.end);
        const middleDate = new Date((viewStart.getTime() + viewEnd.getTime()) / 2);

        const targetMonth = middleDate.getMonth();
        const targetYear = middleDate.getFullYear();

        // Calculate total P&L only for days in the target month
        let monthlyTotal = 0;
        let tradeDays = 0;

        for (const [date, dayData] of Object.entries(this.dailyPnlData)) {
            const dayDate = new Date(date);
            // Only include days that are in the target month/year
            if (dayDate.getMonth() === targetMonth && dayDate.getFullYear() === targetYear) {
                monthlyTotal += this.dayPnl(dayData);
                tradeDays++;
            }
        }

        const monthYear = middleDate.toLocaleDateString('en-US', {
            month: 'long',
            year: 'numeric'
        });

        // Update the calendar title to include monthly P&L
        const titleElement = document.querySelector('.fc-toolbar-title');
        if (titleElement) {
            const cssClass = monthlyTotal >= 0 ? 'profit' : 'loss';
            const sign = monthlyTotal >= 0 ? '+' : '';
            titleElement.innerHTML = `
                ${monthYear}
                <div class="monthly-pnl ${cssClass}" style="font-size: 0.8em; font-weight: normal; margin-top: 4px;">
                    Monthly P&L: ${sign}$${monthlyTotal.toFixed(2)} (${tradeDays} days)
                </div>
            `;
        }
    }

    /**
     * Build the month's events.
     *
     * Days come from the P&L data. Where an asset tracks day states, days that
     * only opened positions are included too and shown in their own colour.
     */
    async buildEvents(startStr, endStr) {
        await this.loadPnlData(startStr, endStr);

        const tracksDayStates = Boolean(this.settings.dayStates);
        this.daySummaries = tracksDayStates
            ? await this.loadDaySummaries(startStr, endStr)
            : {};

        const dates = tracksDayStates
            ? new Set([...Object.keys(this.dailyPnlData), ...Object.keys(this.daySummaries)])
            : new Set(Object.keys(this.dailyPnlData));

        const events = [];

        for (const date of dates) {
            const dayData = this.dailyPnlData[date] || {};
            const pnl = this.dayPnl(dayData);
            const count = dayData.count || 0;

            let color = pnl >= 0 ? DAY_COLORS.profit : DAY_COLORS.loss;
            const extendedProps = { pnl, count, details: dayData.details };

            if (tracksDayStates) {
                const summary = this.daySummaries[date] || { positions_closed: 0, positions_opened: 0 };
                extendedProps.positions_closed = summary.positions_closed;
                extendedProps.positions_opened = summary.positions_opened;

                if (summary.positions_closed > 0) {
                    color = pnl >= 0 ? DAY_COLORS.profit : DAY_COLORS.loss;
                } else if (summary.positions_opened > 0) {
                    // Opened but nothing realized, so no gain or loss to colour
                    color = DAY_COLORS.opened;
                } else {
                    continue;  // no activity
                }
            }

            events.push({
                id: date,
                title: money(pnl),
                date: date,
                extendedProps,
                backgroundColor: color,
                borderColor: color,
                textColor: 'white'
            });
        }

        return events;
    }

    async loadCalendarEvents(info, successCallback, failureCallback) {
        try {
            const events = await this.buildEvents(info.startStr, info.endStr);

            // Update the monthly summary after loading events
            this.updateMonthlyPnlSummary(info);

            successCallback(events);
        } catch (error) {
            console.error('Error loading calendar events:', error);
            failureCallback(error);
        }
    }

    /** The line under the amount on a day. */
    dayLabel(props) {
        if (this.settings.dayStates) {
            const closed = props.positions_closed || 0;
            const opened = props.positions_opened || 0;
            if (closed > 0 && opened > 0) return `${closed} closed, ${opened} opened`;
            if (closed > 0) return `${closed} closed`;
            if (opened > 0) return `${opened} opened`;
            return '';
        }
        return `${props.count || 0} trades`;
    }

    renderEventContent(eventInfo) {
        const props = eventInfo.event.extendedProps;

        return {
            html: `
                <div class="pnl-event">
                    <div class="pnl-amount">${money(props.pnl)}</div>
                    <div class="pnl-count">${this.dayLabel(props)}</div>
                </div>
            `
        };
    }

    styleEventElement(eventInfo) {
        const element = eventInfo.el;
        element.style.cursor = 'pointer';
        element.style.fontSize = '11px';
        element.style.padding = '2px';
    }

    async handleEventClick(eventInfo) {
        const date = eventInfo.event.id;
        const props = eventInfo.event.extendedProps;

        await this.showDayDetails(date, props.pnl, props.count);
    }

    /**
     * Fetch whatever the day-detail modal needs for this asset.
     * @returns {Promise<Object>} payload keyed by source name
     */
    async fetchDetailSources(date) {
        const detail = this.settings.detail;
        const options = { assetType: this.assetType };

        const fetchers = {
            positionsByDate: () => this.api.fetchPositionsByDate(date, options),
            dailySummary: () => this.api.fetchDailySummary(date, options)
        };

        const names = detail.sources;
        const payloads = await Promise.all(names.map(name => fetchers[name]()));

        const result = {};
        names.forEach((name, index) => { result[name] = payloads[index]; });
        return result;
    }

    /**
     * Rows for one section, from the source it names.
     * @private
     */
    _sectionRows(section, sources) {
        const rows = pick(sources[section.source], section.from);
        return Array.isArray(rows) ? rows : [];
    }

    /** Build the modal body from this asset's section specs. */
    renderDetailBody(date, pnl, count, sources) {
        const detail = this.settings.detail;
        let html = '';

        if (detail.header) {
            html += this._renderHeader(detail.header, sources);
        }

        for (const section of detail.sections) {
            const rows = this._sectionRows(section, sources);
            if (rows.length === 0 && section.omitWhenEmpty) continue;

            const heading = (section.heading || '').replace('{count}', rows.length);
            if (heading) html += `<h3>${escapeHtml(heading)}</h3>`;

            let totalsRow = null;
            if (section.totals) {
                const data = pick(sources[section.source], section.totals.from);
                if (data) totalsRow = { data, columns: section.totals.columns };
            }

            html += renderTable(rows, section.columns, totalsRow);
            if (section.spacerAfter) html += '<br>';
        }

        return html;
    }

    /** The stats block some assets show above the tables. */
    _renderHeader(header, sources) {
        const totals = pick(sources[header.source], header.from) || {};
        const orders = pick(sources[header.countSource || 'positionsByDate'], header.countFrom || 'orders') || [];
        const traded = header.sumField
            ? orders.reduce((sum, row) => sum + (Number(row[header.sumField]) || 0), 0)
            : 0;

        const pnl = Number(totals[header.pnlField] || 0);

        return `
                <div style="margin-bottom: 20px; padding: 10px; background: #f5f5f5; border-radius: 4px;">
                    <strong>Daily Summary:</strong>
                    ${totals.positions_closed} position(s) closed,
                    ${totals.positions_opened} position(s) opened,
                    ${traded} ${escapeHtml(header.sumLabel || 'units')} traded
                    <br>
                    <strong>Realized P&L:</strong>
                    <span class="${pnlClass(pnl)}">
                        ${signedMoney(pnl)}
                    </span>
                </div>
            `;
    }

    async showDayDetails(date, pnl, count) {
        try {
            const sources = await this.fetchDetailSources(date);

            const failed = Object.values(sources).some(payload => payload && payload.success === false);
            if (failed) {
                alert('Failed to load details for this day');
                return;
            }

            const modal = document.getElementById('positionModal');
            const title = document.getElementById('modalTitle');
            const body = document.getElementById('modalPositions');

            title.textContent = this.settings.detail.title
                .replace('{date}', date)
                .replace('{pnl}', money(pnl))
                .replace('{count}', count);

            body.innerHTML = this.renderDetailBody(date, pnl, count, sources);
            modal.style.display = 'block';
        } catch (error) {
            console.error('Error loading day details:', error);
            alert('Error loading day details');
        }
    }

    setupModal() {
        const modal = document.getElementById('positionModal');
        const closeBtn = modal.querySelector('.close');

        closeBtn.addEventListener('click', () => {
            modal.style.display = 'none';
        });

        window.addEventListener('click', (event) => {
            if (event.target === modal) {
                modal.style.display = 'none';
            }
        });
    }

    async refreshCalendar() {
        if (this.calendar) {
            await this.calendar.refetchEvents();
        }
    }

    destroy() {
        if (this.calendar) {
            this.calendar.destroy();
            this.calendar = null;
        }
    }
}

// Global calendar manager instance
let calendarManager = null;

// Initialize calendar when the calendar tab is shown
function initCalendar() {
    if (!calendarManager) {
        calendarManager = new CalendarManager();
    }
    calendarManager.initCalendar();
}

// Clean up calendar when switching away
function destroyCalendar() {
    if (calendarManager) {
        calendarManager.destroy();
        calendarManager = null;
    }
}

// Refresh calendar data
async function refreshCalendar() {
    if (calendarManager) {
        await calendarManager.refreshCalendar();
    }
}

window.CalendarManager = CalendarManager;
window.initCalendar = initCalendar;
window.destroyCalendar = destroyCalendar;
window.refreshCalendar = refreshCalendar;
