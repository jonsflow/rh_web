import json
import traceback
from flask import Flask, render_template, jsonify, request, url_for, send_from_directory, redirect
from stocks.data_fetcher import StocksDataFetcher

# Initialize Flask app
app = Flask(__name__, static_url_path='/static', static_folder='static', template_folder='templates')

# Initialize the stocks data fetcher
data_fetcher = StocksDataFetcher()

# Add route to serve static files
@app.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)

@app.route('/')
def index():
    """Render the main page"""
    return render_template('index.html')

@app.route('/api/stocks')
def get_stocks():
    """API endpoint to get stocks data as JSON"""
    try:
        result = data_fetcher.get_processed_data()

        # Check if there's an error
        if result and 'error' in result and result['error']:
            return jsonify({
                'error': result['message'],
                'details': result.get('traceback', '')
            }), 500

        return jsonify(result)

    except Exception as e:
        print(f"API Error: {str(e)}")
        print(traceback.format_exc())

        return jsonify({
            "error": "An internal error occurred while fetching stocks data"
        }), 500

@app.route('/api/update', methods=['POST'])
def update_data():
    """API endpoint to update data from Robinhood"""
    try:
        result = data_fetcher.update_data()

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

@app.route('/api/daily-pnl')
def get_daily_pnl():
    """API endpoint for calendar daily PnL data"""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

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

@app.route('/api/daily-summary/<date>')
def get_daily_summary(date):
    """Get daily trading summary"""
    try:
        summary = data_fetcher.db.get_daily_summary(date)

        return jsonify({
            'success': True,
            'summary': summary
        })

    except Exception as e:
        print(f"Daily Summary API Error: {str(e)}")
        print(traceback.format_exc())

        return jsonify({
            'error': f'Failed to fetch summary for date {date}'
        }), 500

@app.route('/api/open-positions')
def get_open_positions_api():
    """Get current open positions from Robinhood"""
    try:
        # Login if needed
        if not data_fetcher.login_robinhood():
            return jsonify({
                'error': 'Failed to login to Robinhood'
            }), 401

        positions = data_fetcher.get_open_positions()

        return jsonify({
            'success': True,
            'open_positions': positions
        })

    except Exception as e:
        print(f"Open Positions API Error: {str(e)}")
        print(traceback.format_exc())

        return jsonify({
            'error': 'Failed to fetch open positions'
        }), 500

@app.route('/api/closed-positions')
def get_closed_positions_api():
    """Get closed positions with FIFO P&L"""
    try:
        closed_positions = data_fetcher.db.get_closed_positions()

        return jsonify({
            'success': True,
            'closed_positions': closed_positions
        })

    except Exception as e:
        print(f"Closed Positions API Error: {str(e)}")
        print(traceback.format_exc())

        return jsonify({
            'error': 'Failed to fetch closed positions'
        }), 500

@app.route('/api/all-trading-dates')
def get_all_trading_dates():
    """Get all unique trading dates from orders"""
    try:
        dates = data_fetcher.db.get_all_trading_dates()

        return jsonify({
            'success': True,
            'dates': dates
        })

    except Exception as e:
        print(f"All Trading Dates API Error: {str(e)}")
        print(traceback.format_exc())

        return jsonify({
            'error': 'Failed to fetch trading dates'
        }), 500


if __name__ == '__main__':
    # Start server
    print("Starting Robinhood Stocks Dashboard...")

    import os

    # Check if database has orders, if not, auto-fetch
    try:
        result = data_fetcher.get_processed_data(include_open_positions=False)
        if result.get('all_orders') is not None and len(result['all_orders']) == 0:
            print("No orders found in database, fetching from Robinhood...")
            data_fetcher.update_data()
            print("Initial data fetch complete.")
        else:
            print(f"Loaded {len(result.get('all_orders', []))} existing orders from database.")
    except Exception as e:
        print(f"Could not auto-fetch data: {e}")
        print("You can manually refresh data using the 'Refresh Data' button.")

    app.run(debug=True, host='0.0.0.0', port=3002)
