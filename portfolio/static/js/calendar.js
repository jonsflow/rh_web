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
                monthlyTotal += dayData.pnl || 0;
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
                const pnl = dayData.pnl;
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
            const response = await fetch(`/api/positions/date/${date}`);
            const data = await response.json();
            
            if (!data.success) {
                alert('Failed to load position details');
                return;
            }
            
            const modal = document.getElementById('positionModal');
            const title = document.getElementById('modalTitle');
            const body = document.getElementById('modalPositions');
            
            title.textContent = `Positions for ${date} - $${pnl.toFixed(2)} (${count} trades)`;
            
            // Build position details table
            let html = `
                <table class="position-details-table">
                    <thead>
                        <tr>
                            <th>Symbol</th>
                            <th>Strategy</th>
                            <th>Strike</th>
                            <th>Type</th>
                            <th>Quantity</th>
                            <th>Open Price</th>
                            <th>Close Price</th>
                            <th>P&L</th>
                        </tr>
                    </thead>
                    <tbody>
            `;
            
            data.positions.forEach(position => {
                const pnlClass = position.net_credit >= 0 ? 'profit' : 'loss';
                html += `
                    <tr>
                        <td>${position.symbol}</td>
                        <td>${position.strategy || '-'}</td>
                        <td>${position.strike_price}</td>
                        <td>${position.option_type}</td>
                        <td>${position.quantity}</td>
                        <td>$${(position.open_price || 0).toFixed(2)}</td>
                        <td>$${(position.close_price || 0).toFixed(2)}</td>
                        <td class="${pnlClass}">$${(position.net_credit || 0).toFixed(2)}</td>
                    </tr>
                `;
            });
            
            html += '</tbody></table>';
            body.innerHTML = html;
            
            modal.style.display = 'block';
            
        } catch (error) {
            console.error('Error loading position details:', error);
            alert('Error loading position details');
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