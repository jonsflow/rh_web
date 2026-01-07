import json
import traceback
from flask import Flask, render_template, jsonify, request, url_for, send_from_directory, redirect
from futures.data_fetcher import FuturesDataFetcher

# Initialize Flask app
app = Flask(__name__, static_url_path='/static', static_folder='static', template_folder='templates')

# Initialize the futures data fetcher
data_fetcher = FuturesDataFetcher()

# Add route to serve static files
@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

def fetch_and_process_futures_orders():
    """Fetch and process futures orders"""
    try:
        # Use the data fetcher to get processed data
        result = data_fetcher.get_processed_data()

        # If there's an error, return it
        if 'error' in result:
            return result

        # Format the data for frontend
        formatted_result = {
            'open_positions': result['open_positions'],
            'closed_positions': result['closed_positions'],
            'all_orders': result['all_orders'],
            'summary': result['summary']  # P&L summary from robin_stocks
        }

        return formatted_result

    except Exception as e:
        print(f"Error getting processed data: {str(e)}")
        print(traceback.format_exc())

        return {
            'error': True,
            'message': 'An internal error occurred while processing futures data'
        }

@app.route('/')
def index():
    """Render the main page"""
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handle login for Robinhood"""
    error = None

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        try:
            # Update database with initial data after login
            result = data_fetcher.update_data(username, password)

            if 'error' in result:
                error = f"Login failed: {result['error']}"
            else:
                return redirect(url_for('index'))

        except Exception as e:
            error = f"Login failed: {str(e)}"

    return render_template('login.html', error=error)

@app.route('/api/update', methods=['POST'])
def update_data():
    """API endpoint to update data from Robinhood"""
    try:
        force_refresh = request.json.get('force_refresh', False) if request.json else False
        result = data_fetcher.update_data(force_full_refresh=force_refresh)

        if 'error' in result:
            return jsonify({
                'error': result['error'],
                'details': result.get('traceback', '')
            }), 500

        return jsonify({
            'success': True,
            'message': 'Data updated successfully',
            'data': result
        })

    except Exception as e:
        print(f"Update API Error: {str(e)}")
        print(traceback.format_exc())

        return jsonify({
            "error": "An internal error occurred while updating data"
        }), 500

@app.route('/api/futures')
def get_futures():
    """API endpoint to get futures orders as JSON"""
    try:
        result = fetch_and_process_futures_orders()

        # Check if there's an error
        if result and 'error' in result and result['error']:
            return jsonify({
                'error': result['message'],
                'details': result.get('traceback', '')
            }), 500

        return jsonify(result)

    except Exception as e:
        # Print the full error traceback to the console
        print(f"API Error: {str(e)}")
        print(traceback.format_exc())

        return jsonify({
            "error": "An internal error occurred while fetching futures data"
        }), 500

@app.route('/api/daily-pnl')
def get_daily_pnl():
    """API endpoint for calendar daily PnL data"""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        # Use the simplified database method that sums realized_pnl by trade_date
        daily_pnl = data_fetcher.db.get_daily_pnl(start_date, end_date)

        return jsonify({
            'success': True,
            'daily_pnl': daily_pnl
        })

    except Exception as e:
        print(f"Daily PnL API Error: {str(e)}")
        print(traceback.format_exc())

        return jsonify({
            'error': 'Failed to fetch daily PnL data'
        }), 500

@app.route('/api/positions/date/<date>')
def get_positions_by_date(date):
    """Get all orders for a specific trade date"""
    try:
        # Use the database method to get orders by trade date
        orders_on_date = data_fetcher.db.get_orders_by_trade_date(date)

        return jsonify({
            'success': True,
            'date': date,
            'orders': orders_on_date
        })

    except Exception as e:
        print(f"Orders by Date API Error: {str(e)}")
        print(traceback.format_exc())

        return jsonify({
            'error': f'Failed to fetch orders for date {date}'
        }), 500


if __name__ == '__main__':
    # Trigger authentication on startup
    print("Starting Robinhood Futures Dashboard...")
    try:
        # This will prompt for credentials if needed
        data_fetcher.login_robinhood()
        print("Authentication successful!")

        # Fetch initial data after authentication
        print("Fetching initial futures data...")
        result = data_fetcher.fetch_futures_orders()
        if result['success']:
            print(f"✓ {result['message']}")
        else:
            print(f"⚠ Data fetch warning: {result['error']}")

    except Exception as e:
        print(f"Authentication failed: {e}")
        print("You can try again when the server starts by refreshing the page.")

    app.run(debug=True, host='0.0.0.0', port=3001)
