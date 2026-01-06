// Global variables
let optionsData = {
    open_positions: [],
    closed_positions: [],
    expired_positions: [],
    all_orders: []
};

document.addEventListener('DOMContentLoaded', function() {
    // Core elements
    const tabButtons = document.querySelectorAll('.tab');
    const tabContents = document.querySelectorAll('.tab-content');
    const loadingIndicator = document.getElementById('loadingIndicator');
    const dashboardContent = document.getElementById('dashboardContent');
    const errorMessage = document.getElementById('errorMessage');
    
    // Tab switching
    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const previousActiveTab = document.querySelector('.tab.active')?.getAttribute('data-tab');
            const newTabId = button.getAttribute('data-tab');
            
            // Clean up previous tab
            if (previousActiveTab === 'calendar') {
                destroyCalendar();
            }
            
            tabButtons.forEach(btn => btn.classList.remove('active'));
            tabContents.forEach(content => content.classList.remove('active'));
            
            button.classList.add('active');
            document.getElementById(newTabId).classList.add('active');
            
            // Initialize new tab
            if (newTabId === 'calendar') {
                initCalendar();
            }
        });
    });
    
    // Fetch data from API using new ApiService (with fallback)
    function fetchOptionsData() {
        loadingIndicator.style.display = 'block';
        dashboardContent.style.display = 'none';
        errorMessage.style.display = 'none';
        
        // Use new ApiService if available, otherwise fallback to direct fetch
        const apiCall = (typeof window.ApiService !== 'undefined') 
            ? window.ApiService.fetchOptionsData()
            : fetch('/api/options').then(response => {
                if (response.status === 401) {
                    window.location.href = '/login';
                    throw new Error('Login required');
                }
                if (!response.ok) {
                    return response.json().then(errData => {
                        throw new Error(errData.error || 'Server error');
                    });
                }
                return response.json();
            });
        
        apiCall
            .then(data => {
                if (data && data.error) {
                    throw new Error(data.error);
                }
                
                optionsData = {
                    open_positions: data.open_positions || [],
                    closed_positions: data.closed_positions || [],
                    expired_positions: data.expired_positions || [],
                    all_orders: data.all_orders || []
                };
                
                renderDashboard();
                
                loadingIndicator.style.display = 'none';
                dashboardContent.style.display = 'block';
                
                const now = new Date();
                document.getElementById('lastUpdated').textContent = 
                    `Last updated: ${now.toLocaleTimeString()}`;
            })
            .catch(error => {
                console.error('Error fetching data:', error);
                loadingIndicator.style.display = 'none';
                errorMessage.innerHTML = `Error loading data: ${error.message}<br>
                    <small>Check the console for more details</small>`;
                errorMessage.style.display = 'block';
            });
    }
    
    // Initialize dashboard
    function renderDashboard() {
        renderSummary();
        renderOpenPositions();
        renderClosedPositions();
        renderExpiredPositions();
        renderAllOrders();
        populateFilters();
        setupSortListeners(); // New sorting functionality
    }
    
    // Initial data fetch
    fetchOptionsData();
    
    // Event listener for refresh button
    document.getElementById('refreshData').addEventListener('click', async () => {
        const refreshButton = document.getElementById('refreshData');
        const originalText = refreshButton.textContent;
        
        try {
            refreshButton.textContent = 'Updating from Robinhood...';
            refreshButton.disabled = true;
            
            // First update data from Robinhood
            const response = await fetch('/api/update', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ force_refresh: true })
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || 'Failed to update data');
            }
            
            // Then fetch the updated data for display
            await fetchOptionsData();
            
            // Also refresh calendar if it's active
            const activeTab = document.querySelector('.tab.active')?.getAttribute('data-tab');
            if (activeTab === 'calendar') {
                await refreshCalendar();
            }
            
        } catch (error) {
            console.error('Error during refresh:', error);
            alert(`Failed to refresh data: ${error.message}`);
        } finally {
            refreshButton.textContent = originalText;
            refreshButton.disabled = false;
        }
    });
});