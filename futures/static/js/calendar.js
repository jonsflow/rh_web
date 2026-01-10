// Calendar View Manager for Daily P&L Display
class CalendarManager {
    constructor() {
        this.calendar = null;
        this.dailyPnlData = {};
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
            const response = await fetch(`/api/daily-pnl?start_date=${startDate}&end_date=${endDate}`);
            const data = await response.json();
            
            if (data.success) {
                this.dailyPnlData = data.daily_pnl;
            } else {
                console.error('Failed to load daily P&L data:', data.error);
            }
        } catch (error) {
            console.error('Error fetching daily P&L data:', error);
        }
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
                monthlyTotal += dayData.pnl_no_fees || 0;
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
            const pnlClass = monthlyTotal >= 0 ? 'profit' : 'loss';
            const pnlSign = monthlyTotal >= 0 ? '+' : '';
            titleElement.innerHTML = `
                ${monthYear}
                <div class="monthly-pnl ${pnlClass}" style="font-size: 0.8em; font-weight: normal; margin-top: 4px;">
                    Monthly P&L: ${pnlSign}$${monthlyTotal.toFixed(2)} (${tradeDays} days)
                </div>
            `;
        }
    }

    async loadCalendarEvents(info, successCallback, failureCallback) {
        try {
            // Load data for the current date range first
            await this.loadPnlData(info.startStr, info.endStr);
            
            // Convert daily P&L data to FullCalendar events
            const events = [];
            
            for (const [date, dayData] of Object.entries(this.dailyPnlData)) {
                const pnl = dayData.pnl_no_fees || 0;
                const count = dayData.count;

                events.push({
                    id: date,
                    title: `$${pnl.toFixed(2)}`,
                    date: date,
                    extendedProps: {
                        pnl: pnl,
                        count: count,
                        details: dayData.details
                    },
                    backgroundColor: pnl >= 0 ? '#28a745' : '#dc3545',
                    borderColor: pnl >= 0 ? '#28a745' : '#dc3545',
                    textColor: 'white'
                });
            }
            
            // Update the monthly summary after loading events
            this.updateMonthlyPnlSummary(info);
            
            successCallback(events);
        } catch (error) {
            console.error('Error loading calendar events:', error);
            failureCallback(error);
        }
    }

    renderEventContent(eventInfo) {
        const pnl = eventInfo.event.extendedProps.pnl;
        const count = eventInfo.event.extendedProps.count;
        
        return {
            html: `
                <div class="pnl-event">
                    <div class="pnl-amount">$${pnl.toFixed(2)}</div>
                    <div class="pnl-count">${count} trades</div>
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
        const pnl = eventInfo.event.extendedProps.pnl;
        const count = eventInfo.event.extendedProps.count;
        
        await this.showPositionDetails(date, pnl, count);
    }

    async showPositionDetails(date, pnl, count) {
        try {
            // Fetch both summary and detailed orders
            const [summaryResponse, ordersResponse] = await Promise.all([
                fetch(`/api/daily-summary/${date}`),
                fetch(`/api/positions/date/${date}`)
            ]);

            const summaryData = await summaryResponse.json();
            const ordersData = await ordersResponse.json();

            if (!summaryData.success || !ordersData.success) {
                alert('Failed to load order details');
                return;
            }

            const modal = document.getElementById('positionModal');
            const title = document.getElementById('modalTitle');
            const body = document.getElementById('modalPositions');

            title.textContent = `Trading Summary - ${date}`;

            // Format dates to be more readable (in Eastern time to match market hours)
            const formatDate = (dateStr) => {
                if (!dateStr) return '';
                const date = new Date(dateStr);
                return date.toLocaleString('en-US', {
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                    timeZone: 'America/New_York'
                });
            };

            const summary = summaryData.summary;

            // Build summary table (Purchase and Sale Summary format)
            let html = `
                <h3>Purchase and Sale Summary</h3>
                <table class="position-details-table">
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Total Qty Long</th>
                            <th>Total Qty Short</th>
                            <th>Gross P&L</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            summary.contracts.forEach(contract => {
                const pnlClass = contract.gross_pnl >= 0 ? 'profit' : 'loss';
                const pnlSign = contract.gross_pnl >= 0 ? '+' : '';

                html += `
                    <tr>
                        <td>${contract.symbol}</td>
                        <td>${contract.total_qty_long}</td>
                        <td>${contract.total_qty_short}</td>
                        <td class="${pnlClass}">${pnlSign}$${contract.gross_pnl.toFixed(2)}</td>
                    </tr>
                `;
            });

            // Totals row
            const totalPnlClass = summary.totals.gross_pnl >= 0 ? 'profit' : 'loss';
            const totalPnlSign = summary.totals.gross_pnl >= 0 ? '+' : '';
            html += `
                    <tr style="font-weight: bold; border-top: 2px solid #666;">
                        <td>TOTALS</td>
                        <td>${summary.totals.total_qty_long}</td>
                        <td>${summary.totals.total_qty_short}</td>
                        <td class="${totalPnlClass}">${totalPnlSign}$${summary.totals.gross_pnl.toFixed(2)}</td>
                    </tr>
            `;

            html += `
                    </tbody>
                </table>
                <br>
                <h3>Detailed Orders (${count} total)</h3>
                <table class="position-details-table">
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Time</th>
                            <th>Side</th>
                            <th>Quantity</th>
                            <th>Price</th>
                            <th>Realized P&L</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            ordersData.orders.forEach(order => {
                const orderPnl = order.realized_pnl || 0;
                const pnlClass = orderPnl >= 0 ? 'profit' : 'loss';
                const pnlSign = orderPnl >= 0 ? '+' : '';

                html += `
                    <tr>
                        <td>${order.symbol || order.contract_id}</td>
                        <td>${formatDate(order.execution_time)}</td>
                        <td>${order.order_side || ''}</td>
                        <td>${order.filled_quantity || order.quantity || ''}</td>
                        <td>$${(order.average_price || 0).toFixed(2)}</td>
                        <td class="${pnlClass}">${pnlSign}$${orderPnl.toFixed(2)}</td>
                    </tr>
                `;
            });

            html += '</tbody></table>';
            body.innerHTML = html;

            modal.style.display = 'block';

        } catch (error) {
            console.error('Error loading order details:', error);
            alert('Error loading order details');
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