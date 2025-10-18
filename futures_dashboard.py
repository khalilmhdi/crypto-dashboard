from flask import Flask, render_template, jsonify, request, redirect, url_for, session
import threading
import time
import random
import hashlib
import os
import json
from datetime import datetime
import base64

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# File-based storage
USERS_FILE = 'users.json'
USER_DATA_DIR = 'user_data'

os.makedirs(USER_DATA_DIR, exist_ok=True)


def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def get_user_data_file(username):
    return os.path.join(USER_DATA_DIR, f'{username}.json')


def load_user_data(username):
    user_file = get_user_data_file(username)
    if os.path.exists(user_file):
        with open(user_file, 'r') as f:
            return json.load(f)

    return {
        'calculator': {
            'entry_price': '', 'exit_price': '', 'position_size': '100', 'leverage': '10'
        },
        'trading_notes': '',
        'chart_settings': {
            'chart1': {'symbol': 'BTCUSDT.P', 'interval': '5'},
            'chart2': {'symbol': 'BTCUSDT.P', 'interval': '15'},
            'chart3': {'symbol': 'BTCUSDT.P', 'interval': '1'},
            'chart4': {'symbol': 'BTCUSDT.P', 'interval': '240'}
        },
        'chart_states': {  # NEW: Store complete chart states
            'chart1': {},
            'chart2': {},
            'chart3': {},
            'chart4': {}
        },
        'trade_journal': [],
        'preferences': {'theme': 'dark'},
        'layout_saves': {},
        'created_at': datetime.now().isoformat()
    }


def save_user_data(username, data):
    user_file = get_user_data_file(username)
    data['last_updated'] = datetime.now().isoformat()
    with open(user_file, 'w') as f:
        json.dump(data, f, indent=2)


market_data = {
    'btcusdt': {'price': 68250.42, 'change': 0, 'change_percent': 0},
    'tutusdt': {'price': 0.02759, 'change': 0, 'change_percent': 0},
    'ethusdt': {'price': 3512.67, 'change': 0, 'change_percent': 0},
    'adausdt': {'price': 0.4821, 'change': 0, 'change_percent': 0}
}


def price_updater():
    while True:
        for symbol in market_data:
            change = random.uniform(-0.02, 0.02)
            market_data[symbol]['price'] *= (1 + change)
            market_data[symbol]['change'] = market_data[symbol]['price'] * change
            market_data[symbol]['change_percent'] = change * 100
        time.sleep(2)


# Authentication routes (same as before)
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        users = load_users()

        if username in users:
            return auth_page('register', 'Username already exists!')
        if password != confirm_password:
            return auth_page('register', 'Passwords do not match!')
        if len(password) < 4:
            return auth_page('register', 'Password must be at least 4 characters!')

        users[username] = {'password': hash_password(password), 'created_at': datetime.now().isoformat()}
        save_users(users)

        user_data = load_user_data(username)
        save_user_data(username, user_data)

        session['username'] = username
        return redirect(url_for('dashboard'))

    return auth_page('register')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        users = load_users()

        if username not in users or users[username]['password'] != hash_password(password):
            return auth_page('login', 'Invalid username or password!')

        user_data = load_user_data(username)
        user_data['last_login'] = datetime.now().isoformat()
        save_user_data(username, user_data)

        session['username'] = username
        return redirect(url_for('dashboard'))

    return auth_page('login')


@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))


@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


# NEW: Save complete chart state including indicators
@app.route('/save_chart_state', methods=['POST'])
def save_chart_state():
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    username = session['username']
    data = request.json
    chart_id = data.get('chart_id')
    chart_state = data.get('chart_state', {})

    if not chart_id:
        return jsonify({'error': 'Missing chart_id'}), 400

    user_data = load_user_data(username)

    # Initialize chart_states if it doesn't exist
    if 'chart_states' not in user_data:
        user_data['chart_states'] = {}

    # Save the complete chart state
    user_data['chart_states'][chart_id] = chart_state
    save_user_data(username, user_data)

    return jsonify({'status': 'success'})


# NEW: Load complete chart state
@app.route('/load_chart_state', methods=['POST'])
def load_chart_state():
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    username = session['username']
    data = request.json
    chart_id = data.get('chart_id')

    if not chart_id:
        return jsonify({'error': 'Missing chart_id'}), 400

    user_data = load_user_data(username)

    if 'chart_states' not in user_data or chart_id not in user_data['chart_states']:
        return jsonify({'error': 'No saved state found'}), 404

    chart_state = user_data['chart_states'][chart_id]
    return jsonify({'status': 'success', 'chart_state': chart_state})


# Enhanced layout saving with chart states
@app.route('/save_layout', methods=['POST'])
def save_layout():
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    username = session['username']
    data = request.json
    layout_name = data.get('layout_name', 'Default Layout')
    chart_settings = data.get('chart_settings', {})
    chart_states = data.get('chart_states', {})  # NEW: Include chart states

    user_data = load_user_data(username)
    if 'layout_saves' not in user_data:
        user_data['layout_saves'] = {}

    user_data['layout_saves'][layout_name] = {
        'chart_settings': chart_settings,
        'chart_states': chart_states,  # NEW: Save chart states with layout
        'chart_symbols': data.get('chart_symbols', {}),
        'saved_at': datetime.now().isoformat()
    }

    # Also update current settings and states
    user_data['chart_settings'] = chart_settings
    user_data['chart_states'] = chart_states

    save_user_data(username, user_data)
    return jsonify({'status': 'success', 'message': f'Layout "{layout_name}" saved!'})


# Enhanced layout loading with chart states
@app.route('/load_layout', methods=['POST'])
def load_layout():
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    username = session['username']
    data = request.json
    layout_name = data.get('layout_name', 'Default Layout')

    user_data = load_user_data(username)
    if 'layout_saves' not in user_data or layout_name not in user_data['layout_saves']:
        return jsonify({'error': f'Layout "{layout_name}" not found'}), 404

    layout_data = user_data['layout_saves'][layout_name]
    return jsonify({
        'status': 'success',
        'chart_settings': layout_data.get('chart_settings', {}),
        'chart_symbols': layout_data.get('chart_symbols', {}),
        'chart_states': layout_data.get('chart_states', {})  # NEW: Return chart states
    })


# Keep existing endpoints for backward compatibility
@app.route('/save_calculator_data', methods=['POST'])
def save_calculator_data():
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    username = session['username']
    data = request.json
    user_data = load_user_data(username)
    user_data['calculator'] = data
    save_user_data(username, user_data)
    return jsonify({'status': 'success'})


@app.route('/save_trading_notes', methods=['POST'])
def save_trading_notes():
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    username = session['username']
    notes = request.json.get('notes', '')
    user_data = load_user_data(username)
    user_data['trading_notes'] = notes
    save_user_data(username, user_data)
    return jsonify({'status': 'success'})


@app.route('/save_chart_settings', methods=['POST'])
def save_chart_settings():
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    username = session['username']
    chart_settings = request.json
    user_data = load_user_data(username)
    user_data['chart_settings'] = chart_settings
    save_user_data(username, user_data)
    return jsonify({'status': 'success'})


@app.route('/save_chart_symbol', methods=['POST'])
def save_chart_symbol():
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    username = session['username']
    data = request.json
    chart_id = data.get('chart_id')
    symbol = data.get('symbol')

    if not chart_id or not symbol:
        return jsonify({'error': 'Missing chart_id or symbol'}), 400

    user_data = load_user_data(username)
    if 'chart_settings' not in user_data:
        user_data['chart_settings'] = {}
    if chart_id not in user_data['chart_settings']:
        user_data['chart_settings'][chart_id] = {}

    user_data['chart_settings'][chart_id]['symbol'] = symbol
    save_user_data(username, user_data)
    return jsonify({'status': 'success'})


@app.route('/get_saved_layouts', methods=['GET'])
def get_saved_layouts():
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    username = session['username']
    user_data = load_user_data(username)
    layouts = user_data.get('layout_saves', {})
    layout_list = [{'name': name, 'saved_at': data.get('saved_at', '')} for name, data in layouts.items()]
    return jsonify({'layouts': layout_list})


@app.route('/add_trade_journal', methods=['POST'])
def add_trade_journal():
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    username = session['username']
    trade_data = request.json
    user_data = load_user_data(username)
    trade_entry = {
        'id': len(user_data['trade_journal']) + 1,
        'timestamp': datetime.now().isoformat(),
        'symbol': trade_data.get('symbol', ''),
        'entry_price': trade_data.get('entry_price', 0),
        'exit_price': trade_data.get('exit_price', 0),
        'position_size': trade_data.get('position_size', 0),
        'leverage': trade_data.get('leverage', 1),
        'profit_loss': trade_data.get('profit_loss', 0),
        'roi': trade_data.get('roi', 0),
        'notes': trade_data.get('notes', '')
    }
    user_data['trade_journal'].append(trade_entry)
    save_user_data(username, user_data)
    return jsonify({'status': 'success', 'trade_id': trade_entry['id']})


@app.route('/get_user_data')
def get_user_data():
    if 'username' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    username = session['username']
    user_data = load_user_data(username)
    return jsonify({
        'calculator': user_data.get('calculator', {}),
        'trading_notes': user_data.get('trading_notes', ''),
        'chart_settings': user_data.get('chart_settings', {}),
        'chart_states': user_data.get('chart_states', {}),  # NEW: Include chart states
        'trade_journal': user_data.get('trade_journal', []),
        'preferences': user_data.get('preferences', {}),
        'layout_saves': user_data.get('layout_saves', {})
    })


@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))

    username = session.get('username', 'Guest')
    user_data = load_user_data(username)

    calculator_data = user_data.get('calculator', {})
    trading_notes = user_data.get('trading_notes', '')
    chart_settings = user_data.get('chart_settings', {})
    chart_states = user_data.get('chart_states', {})  # NEW: Load chart states

    chart1_symbol = chart_settings.get('chart1', {}).get('symbol', 'BTCUSDT.P')
    chart2_symbol = chart_settings.get('chart2', {}).get('symbol', 'BTCUSDT.P')
    chart3_symbol = chart_settings.get('chart3', {}).get('symbol', 'BTCUSDT.P')
    chart4_symbol = chart_settings.get('chart4', {}).get('symbol', 'BTCUSDT.P')

    calc_entry = calculator_data.get('entry_price', '')
    calc_exit = calculator_data.get('exit_price', '')
    calc_position = calculator_data.get('position_size', '100')
    calc_leverage = calculator_data.get('leverage', '10')

    safe_user_data = {
        'calculator': calculator_data,
        'trading_notes': trading_notes,
        'chart_settings': chart_settings,
        'chart_states': chart_states,  # NEW: Include chart states
        'trade_journal': user_data.get('trade_journal', []),
        'preferences': user_data.get('preferences', {}),
        'layout_saves': user_data.get('layout_saves', {})
    }

    # Return the dashboard HTML with enhanced JavaScript
    return f'''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Professional Trading Dashboard</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0a0a0a; color: #ffffff; line-height: 1.6; }}
            .container {{ max-width: 1800px; margin: 0 auto; padding: 20px; }}
            .header {{ text-align: center; margin-bottom: 20px; position: relative; }}
            .header h1 {{ font-size: 2.2em; font-weight: 300; color: #00d4aa; margin-bottom: 5px; }}
            .user-info {{ position: absolute; right: 0; top: 0; display: flex; align-items: center; gap: 15px; }}
            .layout-controls {{ display: flex; align-items: center; gap: 10px; }}
            .layout-input {{ background: #222; border: 1px solid #333; border-radius: 4px; color: white; padding: 6px 10px; font-size: 0.8em; width: 150px; }}
            .layout-btn {{ padding: 6px 12px; background: #222; border: 1px solid #333; border-radius: 4px; color: #ccc; cursor: pointer; font-size: 0.8em; transition: all 0.3s; }}
            .layout-btn:hover {{ background: #333; border-color: #00d4aa; color: #00d4aa; }}
            .layout-btn-primary {{ background: #00d4aa; border-color: #00d4aa; color: #000; font-weight: 600; }}
            .layout-btn-primary:hover {{ background: #00b894; border-color: #00b894; }}
            .welcome-text {{ color: #00d4aa; font-size: 0.9em; }}
            .logout-btn {{ background: #ff4d4d; border: none; border-radius: 4px; color: white; padding: 8px 16px; cursor: pointer; font-size: 0.8em; transition: all 0.3s; }}
            .logout-btn:hover {{ background: #ff3333; transform: translateY(-1px); }}
            .search-nav {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; padding: 10px 0; border-bottom: 1px solid #333; }}
            .ad-free-version {{ font-size: 0.9em; color: #888; }}
            .nav-links {{ display: flex; gap: 25px; }}
            .nav-links a {{ color: #ccc; text-decoration: none; font-size: 0.85em; transition: color 0.3s; }}
            .nav-links a:hover {{ color: #00d4aa; }}
            .modal {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0, 0, 0, 0.8); z-index: 2000; justify-content: center; align-items: center; }}
            .modal-content {{ background: #111; border: 1px solid #333; border-radius: 10px; padding: 20px; width: 90%; max-width: 400px; }}
            .modal-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; border-bottom: 1px solid #333; padding-bottom: 10px; }}
            .modal-title {{ color: #00d4aa; font-size: 1.2em; font-weight: 600; }}
            .close-modal {{ background: none; border: none; color: #ccc; font-size: 1.5em; cursor: pointer; }}
            .close-modal:hover {{ color: #ff4d4d; }}
            .layout-list {{ max-height: 300px; overflow-y: auto; margin-bottom: 15px; }}
            .layout-item {{ padding: 10px; background: #222; border: 1px solid #333; border-radius: 4px; margin-bottom: 8px; cursor: pointer; transition: all 0.3s; }}
            .layout-item:hover {{ border-color: #00d4aa; background: #2a2a2a; }}
            .layout-item.active {{ border-color: #00d4aa; background: rgba(0, 212, 170, 0.1); }}
            .layout-name {{ font-weight: 600; color: #00d4aa; }}
            .layout-date {{ font-size: 0.8em; color: #888; }}
            .main-grid {{ display: grid; grid-template-columns: 1fr 350px; gap: 15px; height: calc(100vh - 180px); }}
            .charts-container {{ display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; gap: 15px; }}
            .chart-section {{ background: #111; border-radius: 10px; border: 1px solid #333; display: flex; flex-direction: column; position: relative; overflow: hidden; }}
            .chart-section.fullscreen {{ position: fixed; top: 20px; left: 20px; right: 20px; bottom: 20px; z-index: 1000; }}
            .chart-header {{ display: flex; justify-content: space-between; align-items: center; padding: 12px 15px; border-bottom: 1px solid #333; background: #151515; }}
            .chart-title {{ font-size: 1em; font-weight: 600; color: #00d4aa; }}
            .chart-controls {{ display: flex; gap: 8px; align-items: center; }}
            .symbol-selector {{ background: #222; border: 1px solid #333; border-radius: 4px; color: white; padding: 4px 8px; font-size: 0.75em; cursor: pointer; }}
            .control-btn {{ padding: 4px 8px; background: #222; border: 1px solid #333; border-radius: 4px; color: #ccc; cursor: pointer; font-size: 0.75em; transition: all 0.3s; }}
            .control-btn:hover {{ background: #333; border-color: #00d4aa; color: #00d4aa; }}
            .chart-content {{ flex: 1; position: relative; background: #000; display: flex; }}
            .tradingview-widget-container {{ flex: 1; height: 100%; }}
            .exit-fullscreen-btn {{ position: fixed; top: 30px; right: 30px; z-index: 1001; background: #00d4aa; border: none; border-radius: 6px; color: #000; padding: 10px 16px; font-weight: 600; cursor: pointer; display: none; }}
            .sidebar {{ display: flex; flex-direction: column; gap: 15px; }}
            .stats-panel {{ background: #111; border-radius: 10px; border: 1px solid #333; padding: 15px; }}
            .panel-title {{ font-size: 1em; font-weight: 600; color: #00d4aa; margin-bottom: 12px; text-align: center; }}
            .visibility-controls {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 10px; }}
            .visibility-btn {{ padding: 8px; background: #222; border: 1px solid #333; border-radius: 4px; color: #ccc; cursor: pointer; font-size: 0.8em; text-align: center; transition: all 0.3s; }}
            .visibility-btn:hover {{ background: #333; border-color: #00d4aa; color: #00d4aa; }}
            .fullscreen-controls {{ display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 8px; margin-bottom: 15px; }}
            .fullscreen-btn {{ padding: 10px; background: #222; border: 1px solid #333; border-radius: 4px; color: #ccc; cursor: pointer; font-size: 0.9em; text-align: center; transition: all 0.3s; font-weight: 600; }}
            .fullscreen-btn:hover {{ background: #333; border-color: #00d4aa; color: #00d4aa; }}
            .calculator-input {{ width: 100%; padding: 8px; margin: 5px 0; background: #222; border: 1px solid #333; border-radius: 4px; color: white; font-size: 0.85em; }}
            .calculator-results {{ background: #151515; padding: 12px; border-radius: 6px; margin-top: 12px; border: 1px solid #333; }}
            .result-row {{ display: flex; justify-content: space-between; margin: 6px 0; font-size: 0.85em; }}
            .result-label {{ color: #888; }}
            .result-value {{ font-weight: 600; }}
            .result-positive {{ color: #00d4aa; }}
            .result-negative {{ color: #ff4d4d; }}
            .notebook-container {{ flex: 1; display: flex; flex-direction: column; }}
            .notebook-textarea {{ width: 100%; flex: 1; background: #151515; border: 1px solid #333; border-radius: 6px; color: white; padding: 12px; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; font-size: 0.9em; resize: none; }}
            .notebook-controls {{ display: flex; gap: 8px; margin-top: 10px; }}
            .notebook-btn {{ padding: 6px 12px; background: #222; border: 1px solid #333; border-radius: 4px; color: #ccc; cursor: pointer; font-size: 0.8em; }}
            .notebook-btn:hover {{ background: #333; border-color: #00d4aa; color: #00d4aa; }}
            .notebook-btn-primary {{ background: #00d4aa; border-color: #00d4aa; color: #000; font-weight: 600; }}
            .calc-buttons {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px; margin-top: 10px; }}
            .calc-btn {{ padding: 8px; background: #222; border: 1px solid #333; border-radius: 4px; color: #ccc; cursor: pointer; font-size: 0.8em; text-align: center; }}
            .calc-btn:hover {{ background: #333; border-color: #00d4aa; color: #00d4aa; }}
            .save-indicator {{ position: fixed; bottom: 20px; right: 20px; background: #00d4aa; color: #000; padding: 10px 15px; border-radius: 5px; font-size: 0.8em; font-weight: 600; z-index: 1000; opacity: 0; transition: opacity 0.3s; }}
            .save-indicator.show {{ opacity: 1; }}
        </style>
    </head>
    <body>
        <button class="exit-fullscreen-btn" id="exitFullscreenBtn" onclick="exitAllFullscreen()">✕ Exit Fullscreen</button>
        <div class="save-indicator" id="saveIndicator">💾 Data Saved</div>

        <div class="modal" id="layoutModal">
            <div class="modal-content">
                <div class="modal-header">
                    <div class="modal-title">💾 Saved Layouts</div>
                    <button class="close-modal" onclick="closeLayoutModal()">×</button>
                </div>
                <div class="layout-list" id="layoutList"></div>
                <div style="display: flex; gap: 10px;">
                    <button class="layout-btn layout-btn-primary" onclick="loadSelectedLayout()">📁 Load Selected</button>
                    <button class="layout-btn" onclick="closeLayoutModal()">Cancel</button>
                </div>
            </div>
        </div>

        <div class="container">
            <div class="header">
                <h1>Professional Trading Dashboard</h1>
                <p>Advanced Charting Tools • Position Calculator • Trading Notebook</p>
                <div class="user-info">
                    <div class="layout-controls">
                        <input type="text" class="layout-input" id="layoutName" placeholder="Layout Name" value="My Layout">
                        <button class="layout-btn layout-btn-primary" onclick="saveCurrentLayout()">💾 Save Layout</button>
                        <button class="layout-btn" onclick="openLayoutModal()">📁 Load Layout</button>
                    </div>
                    <span class="welcome-text">Welcome, {username}!</span>
                    <button class="logout-btn" onclick="location.href='/logout'">Logout</button>
                </div>
            </div>

            <div class="search-nav">
                <div class="ad-free-version">Multi-Chart Trading Dashboard</div>
                <div class="nav-links">
                    <a href="#">Dashboard</a>
                    <a href="#">Charts</a>
                    <a href="#">Analysis</a>
                    <a href="#">Tools</a>
                </div>
            </div>

            <div class="main-grid">
                <div class="charts-container">
                    <div class="chart-section" id="chart1">
                        <div class="chart-header">
                            <div class="chart-title" id="chart1Title">BTC/USDT - Advanced Chart</div>
                            <div class="chart-controls">
                                <select class="symbol-selector" onchange="changeChartSymbol('chart1', this.value)">
                                    <option value="BTCUSDT.P" {"selected" if chart1_symbol == "BTCUSDT.P" else ""}>BTC/USDT</option>
                                    <option value="TUTUSDT" {"selected" if chart1_symbol == "TUTUSDT" else ""}>TUT/USDT</option>
                                    <option value="ETHUSDT.P" {"selected" if chart1_symbol == "ETHUSDT.P" else ""}>ETH/USDT</option>
                                    <option value="ADAUSDT.P" {"selected" if chart1_symbol == "ADAUSDT.P" else ""}>ADA/USDT</option>
                                </select>
                                <button class="control-btn" onclick="toggleChart('chart1')">Hide</button>
                                <button class="control-btn" onclick="toggleFullscreen('chart1')">⛶</button>
                            </div>
                        </div>
                        <div class="chart-content">
                            <div class="tradingview-widget-container">
                                <div id="tradingview_chart1" style="width: 100%; height: 100%;"></div>
                            </div>
                        </div>
                    </div>

                    <div class="chart-section" id="chart2">
                        <div class="chart-header">
                            <div class="chart-title" id="chart2Title">BTC/USDT - Technical Analysis</div>
                            <div class="chart-controls">
                                <select class="symbol-selector" onchange="changeChartSymbol('chart2', this.value)">
                                    <option value="BTCUSDT.P" {"selected" if chart2_symbol == "BTCUSDT.P" else ""}>BTC/USDT</option>
                                    <option value="TUTUSDT" {"selected" if chart2_symbol == "TUTUSDT" else ""}>TUT/USDT</option>
                                    <option value="ETHUSDT.P" {"selected" if chart2_symbol == "ETHUSDT.P" else ""}>ETH/USDT</option>
                                    <option value="ADAUSDT.P" {"selected" if chart2_symbol == "ADAUSDT.P" else ""}>ADA/USDT</option>
                                </select>
                                <button class="control-btn" onclick="toggleChart('chart2')">Hide</button>
                                <button class="control-btn" onclick="toggleFullscreen('chart2')">⛶</button>
                            </div>
                        </div>
                        <div class="chart-content">
                            <div class="tradingview-widget-container">
                                <div id="tradingview_chart2" style="width: 100%; height: 100%;"></div>
                            </div>
                        </div>
                    </div>

                    <div class="chart-section" id="chart3">
                        <div class="chart-header">
                            <div class="chart-title" id="chart3Title">BTC/USDT - Market Depth</div>
                            <div class="chart-controls">
                                <select class="symbol-selector" onchange="changeChartSymbol('chart3', this.value)">
                                    <option value="BTCUSDT.P" {"selected" if chart3_symbol == "BTCUSDT.P" else ""}>BTC/USDT</option>
                                    <option value="TUTUSDT" {"selected" if chart3_symbol == "TUTUSDT" else ""}>TUT/USDT</option>
                                    <option value="ETHUSDT.P" {"selected" if chart3_symbol == "ETHUSDT.P" else ""}>ETH/USDT</option>
                                    <option value="ADAUSDT.P" {"selected" if chart3_symbol == "ADAUSDT.P" else ""}>ADA/USDT</option>
                                </select>
                                <button class="control-btn" onclick="toggleChart('chart3')">Hide</button>
                                <button class="control-btn" onclick="toggleFullscreen('chart3')">⛶</button>
                            </div>
                        </div>
                        <div class="chart-content">
                            <div class="tradingview-widget-container">
                                <div id="tradingview_chart3" style="width: 100%; height: 100%;"></div>
                            </div>
                        </div>
                    </div>

                    <div class="chart-section" id="chart4">
                        <div class="chart-header">
                            <div class="chart-title" id="chart4Title">BTC/USDT - Multi-timeframe</div>
                            <div class="chart-controls">
                                <select class="symbol-selector" onchange="changeChartSymbol('chart4', this.value)">
                                    <option value="BTCUSDT.P" {"selected" if chart4_symbol == "BTCUSDT.P" else ""}>BTC/USDT</option>
                                    <option value="TUTUSDT" {"selected" if chart4_symbol == "TUTUSDT" else ""}>TUT/USDT</option>
                                    <option value="ETHUSDT.P" {"selected" if chart4_symbol == "ETHUSDT.P" else ""}>ETH/USDT</option>
                                    <option value="ADAUSDT.P" {"selected" if chart4_symbol == "ADAUSDT.P" else ""}>ADA/USDT</option>
                                </select>
                                <button class="control-btn" onclick="toggleChart('chart4')">Hide</button>
                                <button class="control-btn" onclick="toggleFullscreen('chart4')">⛶</button>
                            </div>
                        </div>
                        <div class="chart-content">
                            <div class="tradingview-widget-container">
                                <div id="tradingview_chart4" style="width: 100%; height: 100%;"></div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="sidebar">
                    <div class="stats-panel">
                        <div class="panel-title">📊 Chart Controls</div>
                        <div class="fullscreen-controls">
                            <div class="fullscreen-btn" id="fullscreenBtn1" onclick="toggleFullscreen('chart1')">1</div>
                            <div class="fullscreen-btn" id="fullscreenBtn2" onclick="toggleFullscreen('chart2')">2</div>
                            <div class="fullscreen-btn" id="fullscreenBtn3" onclick="toggleFullscreen('chart3')">3</div>
                            <div class="fullscreen-btn" id="fullscreenBtn4" onclick="toggleFullscreen('chart4')">4</div>
                        </div>
                        <div class="visibility-controls">
                            <div class="visibility-btn" onclick="toggleChart('chart1')"><span id="chart1Toggle">Hide 1</span></div>
                            <div class="visibility-btn" onclick="toggleChart('chart2')"><span id="chart2Toggle">Hide 2</span></div>
                            <div class="visibility-btn" onclick="toggleChart('chart3')"><span id="chart3Toggle">Hide 3</span></div>
                            <div class="visibility-btn" onclick="toggleChart('chart4')"><span id="chart4Toggle">Hide 4</span></div>
                        </div>
                        <div class="visibility-controls">
                            <div class="visibility-btn" onclick="showAllCharts()">Show All</div>
                            <div class="visibility-btn" onclick="hideAllCharts()">Hide All</div>
                        </div>
                    </div>

                    <div class="stats-panel">
                        <div class="panel-title">🧮 Advanced Position Calculator</div>
                        <input type="number" class="calculator-input" id="calcEntry" placeholder="Entry Price" step="0.000001" value="{calc_entry}">
                        <input type="number" class="calculator-input" id="calcExit" placeholder="Exit Price" step="0.000001" value="{calc_exit}">
                        <input type="number" class="calculator-input" id="calcPosition" placeholder="Position Size ($)" value="{calc_position}">
                        <input type="number" class="calculator-input" id="calcLeverage" placeholder="Leverage" value="{calc_leverage}">
                        <div class="calc-buttons">
                            <div class="calc-btn" onclick="setCurrentPriceAsEntry()">📥 Set Entry</div>
                            <div class="calc-btn" onclick="setCurrentPriceAsExit()">📤 Set Exit</div>
                            <div class="calc-btn" onclick="saveTradeToJournal()">💾 Save Trade</div>
                        </div>
                        <div class="calculator-results" id="calcResults">
                            <div class="result-row"><span class="result-label">Margin Required:</span><span class="result-value" id="marginRequired">$0.00</span></div>
                            <div class="result-row"><span class="result-label">Position Size:</span><span class="result-value" id="positionSize">$0.00</span></div>
                            <div class="result-row"><span class="result-label">Profit/Loss:</span><span class="result-value" id="profitLoss">$0.00</span></div>
                            <div class="result-row"><span class="result-label">ROI:</span><span class="result-value" id="roiPercent">0.00%</span></div>
                            <div class="result-row"><span class="result-label">Liquidation Price:</span><span class="result-value" id="liquidationPrice">$0.00</span></div>
                        </div>
                    </div>

                    <div class="stats-panel notebook-container">
                        <div class="panel-title">📝 Trading Notebook</div>
                        <textarea class="notebook-textarea" id="tradingNotes" placeholder="Write your trading ideas, analysis, and notes here...">{trading_notes}</textarea>
                        <div class="notebook-controls">
                            <button class="notebook-btn notebook-btn-primary" onclick="saveNotes()">💾 Save Notes</button>
                            <button class="notebook-btn" onclick="clearNotes()">🗑️ Clear</button>
                            <button class="notebook-btn" onclick="loadSampleNotes()">📋 Sample</button>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
        <script>
            let tradingViewWidgets = {{}};
            let userData = {json.dumps(safe_user_data)};
            let chartSymbols = {{
                'chart1': '{chart1_symbol}',
                'chart2': '{chart2_symbol}', 
                'chart3': '{chart3_symbol}',
                'chart4': '{chart4_symbol}'
            }};
            let chartVisibility = {{'chart1': true, 'chart2': true, 'chart3': true, 'chart4': true}};
            let fullscreenStates = {{'chart1': false, 'chart2': false, 'chart3': false, 'chart4': false}};
            let selectedLayout = null;
            let chartStates = userData.chart_states || {{}}; // NEW: Store chart states

            const getWidgetConfig = (containerId, interval, symbol, savedState = null) => ({{
                "autosize": true, "symbol": `BINANCE:${{symbol}}`, "interval": interval, "timezone": "Etc/UTC",
                "theme": "dark", "style": "1", "locale": "en", "enable_publishing": false, "allow_symbol_change": true,
                "container_id": containerId, "studies": ["Volume@tv-basicstudies", "RSI@tv-basicstudies", "MACD@tv-basicstudies"],
                "height": "100%", "width": "100%", "drawing_tools": {{"enabled": true}},
                "studies_overrides": {{
                    "volume.volume.color.0": "rgba(255, 77, 77, 0.5)",
                    "volume.volume.color.1": "rgba(0, 212, 170, 0.5)",
                    "volume.volume.transparency": 70
                }},
                "overrides": {{
                    "mainSeriesProperties.showCountdown": true, "paneProperties.background": "#000000",
                    "paneProperties.vertGridProperties.color": "#1a1a1a", "paneProperties.horzGridProperties.color": "#1a1a1a",
                    "mainSeriesProperties.candleStyle.upColor": "#00d4aa", "mainSeriesProperties.candleStyle.downColor": "#ff4d4d"
                }},
                "saved_data": savedState // NEW: Pass saved state to widget
            }});

            function showSaveIndicator(message = '💾 Data Saved') {{
                const indicator = document.getElementById('saveIndicator');
                indicator.textContent = message;
                indicator.classList.add('show');
                setTimeout(() => indicator.classList.remove('show'), 2000);
            }}

            // NEW: Save complete chart state
            function saveChartState(chartId) {{
                const widget = tradingViewWidgets[chartId];
                if (widget) {{
                    try {{
                        // Get the chart instance
                        const chart = widget.chart();
                        if (chart) {{
                            // Get all studies (indicators)
                            const studies = chart.getAllStudies();
                            const studyStates = studies.map(study => ({{
                                id: study.id,
                                name: study.name,
                                properties: study.getProperties()
                            }}));

                            // Get drawings
                            const drawings = chart.getAllShapes();
                            const drawingStates = drawings.map(drawing => ({{
                                id: drawing.id,
                                name: drawing.name,
                                points: drawing.points,
                                properties: drawing.getProperties()
                            }}));

                            // Get chart properties
                            const chartProperties = chart.getStyle();

                            const chartState = {{
                                studies: studyStates,
                                drawings: drawingStates,
                                properties: chartProperties,
                                symbol: chartSymbols[chartId],
                                timestamp: new Date().toISOString()
                            }};

                            // Save to server
                            fetch('/save_chart_state', {{
                                method: 'POST', 
                                headers: {{'Content-Type': 'application/json'}},
                                body: JSON.stringify({{
                                    chart_id: chartId,
                                    chart_state: chartState
                                }})
                            }}).then(r => r.json()).then(data => {{
                                console.log('Chart state saved:', chartId);
                                chartStates[chartId] = chartState;
                            }}).catch(err => console.error('Error saving chart state:', err));
                        }}
                    }} catch (error) {{
                        console.log('Chart not ready for state saving:', chartId, error);
                    }}
                }}
            }}

            // NEW: Enhanced layout saving with chart states
            function saveCurrentLayout() {{
                const layoutName = document.getElementById('layoutName').value || 'My Layout';

                // Save all chart states first
                Object.keys(tradingViewWidgets).forEach(chartId => {{
                    saveChartState(chartId);
                }});

                // Wait a bit for states to save, then save layout
                setTimeout(() => {{
                    const allChartSettings = {{}};
                    Object.keys(chartSymbols).forEach(chartId => {{
                        allChartSettings[chartId] = {{
                            'symbol': chartSymbols[chartId],
                            'interval': chartId === 'chart1' ? '5' : chartId === 'chart2' ? '15' : chartId === 'chart3' ? '1' : '240'
                        }};
                    }});

                    fetch('/save_layout', {{
                        method: 'POST', 
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{
                            layout_name: layoutName, 
                            chart_settings: allChartSettings, 
                            chart_symbols: chartSymbols,
                            chart_states: chartStates // NEW: Include chart states
                        }})
                    }}).then(r => r.json()).then(data => showSaveIndicator(`💾 Layout "${{layoutName}}" Saved!`))
                    .catch(err => {{ console.error('Error saving layout:', err); showSaveIndicator('❌ Error saving layout'); }});
                }}, 1000);
            }}

            function openLayoutModal() {{
                fetch('/get_saved_layouts').then(r => r.json()).then(data => {{
                    const layoutList = document.getElementById('layoutList');
                    layoutList.innerHTML = '';
                    if (data.layouts && data.layouts.length > 0) {{
                        data.layouts.forEach(layout => {{
                            const layoutItem = document.createElement('div');
                            layoutItem.className = 'layout-item';
                            layoutItem.innerHTML = `<div class="layout-name">${{layout.name}}</div><div class="layout-date">${{new Date(layout.saved_at).toLocaleString()}}</div>`;
                            layoutItem.onclick = () => selectLayout(layout.name, layoutItem);
                            layoutList.appendChild(layoutItem);
                        }});
                    }} else {{
                        layoutList.innerHTML = '<div style="text-align: center; color: #888; padding: 20px;">No saved layouts found</div>';
                    }}
                    document.getElementById('layoutModal').style.display = 'flex';
                    selectedLayout = null;
                }}).catch(err => {{ console.error('Error loading layouts:', err); showSaveIndicator('❌ Error loading layouts'); }});
            }}

            function closeLayoutModal() {{ document.getElementById('layoutModal').style.display = 'none'; selectedLayout = null; }}

            function selectLayout(layoutName, element) {{
                document.querySelectorAll('.layout-item').forEach(item => item.classList.remove('active'));
                element.classList.add('active');
                selectedLayout = layoutName;
            }}

            // NEW: Enhanced layout loading with chart states
            function loadSelectedLayout() {{
                if (!selectedLayout) {{ alert('Please select a layout to load'); return; }}
                fetch('/load_layout', {{
                    method: 'POST', 
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{layout_name: selectedLayout}})
                }}).then(r => r.json()).then(data => {{
                    if (data.status === 'success') {{
                        // Update symbols and settings
                        Object.keys(data.chart_symbols).forEach(chartId => {{
                            const symbol = data.chart_symbols[chartId];
                            chartSymbols[chartId] = symbol;
                            const selector = document.querySelector(`#${{chartId}} .symbol-selector`);
                            if (selector) selector.value = symbol;
                        }});

                        // Store chart states for later use
                        chartStates = data.chart_states || {{}};

                        // Reload all charts with their saved states
                        Object.keys(chartSymbols).forEach(chartId => {{
                            const savedState = chartStates[chartId];
                            reloadChartWithSymbolAndState(chartId, chartSymbols[chartId], savedState);
                        }});

                        showSaveIndicator(`📁 Layout "${{selectedLayout}}" Loaded!`);
                        closeLayoutModal();
                    }} else {{
                        showSaveIndicator('❌ Error loading layout');
                    }}
                }}).catch(err => {{ console.error('Error loading layout:', err); showSaveIndicator('❌ Error loading layout'); }});
            }}

            // NEW: Enhanced chart reloading with state
            function reloadChartWithSymbolAndState(chartId, symbol, savedState = null) {{
                if (tradingViewWidgets[chartId]) tradingViewWidgets[chartId].remove();
                const intervals = {{'chart1': '5', 'chart2': '15', 'chart3': '1', 'chart4': '240'}};

                setTimeout(() => {{
                    const widgetConfig = getWidgetConfig('tradingview_' + chartId, intervals[chartId], symbol, savedState);
                    tradingViewWidgets[chartId] = new TradingView.widget(widgetConfig);

                    // NEW: Apply saved state after widget is created
                    if (savedState) {{
                        setTimeout(() => {{
                            try {{
                                const widget = tradingViewWidgets[chartId];
                                if (widget && widget.chart) {{
                                    const chart = widget.chart();
                                    if (chart && savedState.studies) {{
                                        // Re-apply studies
                                        savedState.studies.forEach(study => {{
                                            chart.createStudy(study.name, false, false, study.properties);
                                        }});
                                    }}
                                }}
                            }} catch (error) {{
                                console.log('Could not restore chart state:', chartId, error);
                            }}
                        }}, 2000);
                    }}

                    updateChartTitle(chartId, symbol);
                }}, 500);
            }}

            function reloadChartWithSymbol(chartId, symbol) {{
                reloadChartWithSymbolAndState(chartId, symbol, chartStates[chartId]);
            }}

            function saveChartSymbol(chartId, symbol) {{
                fetch('/save_chart_symbol', {{
                    method: 'POST', 
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{chart_id: chartId, symbol: symbol}})
                }}).then(r => r.json()).then(data => showSaveIndicator('📊 Chart Saved'))
                .catch(err => console.error('Error saving chart symbol:', err));
            }}

            function changeChartSymbol(chartId, symbol) {{
                const wasFullscreen = fullscreenStates[chartId];
                chartSymbols[chartId] = symbol;
                saveChartSymbol(chartId, symbol);

                // Save current state before changing symbol
                saveChartState(chartId);

                reloadChartWithSymbol(chartId, symbol);

                if (wasFullscreen) setTimeout(() => toggleFullscreen(chartId), 1000);
            }}

            function updateChartTitle(chartId, symbol) {{
                const titleElement = document.getElementById(chartId + 'Title');
                const symbolName = symbol.replace('.P', '').replace('USDT', '/USDT');
                const titles = {{
                    'chart1': `${{symbolName}} - Advanced Chart`, 
                    'chart2': `${{symbolName}} - Technical Analysis`,
                    'chart3': `${{symbolName}} - Market Depth`, 
                    'chart4': `${{symbolName}} - Multi-timeframe`
                }};
                if (titleElement) titleElement.textContent = titles[chartId];
            }}

            // NEW: Auto-save chart states periodically
            function startAutoSave() {{
                setInterval(() => {{
                    Object.keys(tradingViewWidgets).forEach(chartId => {{
                        if (tradingViewWidgets[chartId]) {{
                            saveChartState(chartId);
                        }}
                    }});
                }}, 30000); // Save every 30 seconds
            }}

            // Initialize charts with saved states
            function initializeTradingView() {{
                if (typeof TradingView === 'undefined') {{ setTimeout(initializeTradingView, 100); return; }}

                const chartConfigs = [
                    {{ id: 'tradingview_chart1', interval: '5' }}, 
                    {{ id: 'tradingview_chart2', interval: '15' }},
                    {{ id: 'tradingview_chart3', interval: '1' }}, 
                    {{ id: 'tradingview_chart4', interval: '240' }}
                ];

                chartConfigs.forEach(config => {{
                    const chartId = config.id.replace('tradingview_', '');
                    const symbol = chartSymbols[chartId];
                    const savedState = chartStates[chartId]; // Get saved state

                    const widgetConfig = getWidgetConfig(config.id, config.interval, symbol, savedState);
                    tradingViewWidgets[config.id] = new TradingView.widget(widgetConfig);
                    updateChartTitle(chartId, symbol);

                    // Apply saved state after a delay
                    if (savedState) {{
                        setTimeout(() => {{
                            try {{
                                const widget = tradingViewWidgets[config.id];
                                if (widget && widget.chart) {{
                                    const chart = widget.chart();
                                    if (chart && savedState.studies) {{
                                        // Re-apply studies
                                        savedState.studies.forEach(study => {{
                                            chart.createStudy(study.name, false, false, study.properties);
                                        }});
                                    }}
                                }}
                            }} catch (error) {{
                                console.log('Could not restore initial chart state:', chartId, error);
                            }}
                        }}, 3000);
                    }}
                }});

                // Start auto-save
                startAutoSave();
            }}

            // Keep the rest of your existing functions (toggleFullscreen, toggleChart, calculator, etc.)
            function toggleFullscreen(chartId) {{
                const chart = document.getElementById(chartId);
                const fullscreenBtn = document.getElementById('fullscreenBtn' + chartId.slice(-1));
                const exitBtn = document.getElementById('exitFullscreenBtn');
                const isFullscreen = chart.classList.contains('fullscreen');

                Object.keys(fullscreenStates).forEach(otherChartId => {{
                    if (otherChartId !== chartId && fullscreenStates[otherChartId]) {{
                        document.getElementById(otherChartId).classList.remove('fullscreen');
                        fullscreenStates[otherChartId] = false;
                        document.getElementById('fullscreenBtn' + otherChartId.slice(-1)).classList.remove('active');
                    }}
                }});

                if (isFullscreen) {{
                    chart.classList.remove('fullscreen');
                    fullscreenStates[chartId] = false;
                    fullscreenBtn.classList.remove('active');
                    exitBtn.style.display = 'none';
                }} else {{
                    chart.classList.add('fullscreen');
                    fullscreenStates[chartId] = true;
                    fullscreenBtn.classList.add('active');
                    exitBtn.style.display = 'block';
                }}
            }}

            function exitAllFullscreen() {{
                const exitBtn = document.getElementById('exitFullscreenBtn');
                Object.keys(fullscreenStates).forEach(chartId => {{
                    document.getElementById(chartId).classList.remove('fullscreen');
                    fullscreenStates[chartId] = false;
                    document.getElementById('fullscreenBtn' + chartId.slice(-1)).classList.remove('active');
                }});
                exitBtn.style.display = 'none';
            }}

            function toggleChart(chartId) {{
                const chart = document.getElementById(chartId);
                chartVisibility[chartId] = !chartVisibility[chartId];
                if (chartVisibility[chartId]) {{
                    chart.style.display = 'flex';
                    document.getElementById(chartId + 'Toggle').textContent = 'Hide ' + chartId.slice(-1);
                }} else {{
                    chart.style.display = 'none';
                    document.getElementById(chartId + 'Toggle').textContent = 'Show ' + chartId.slice(-1);
                }}
            }}

            function showAllCharts() {{
                Object.keys(chartVisibility).forEach(chartId => {{
                    chartVisibility[chartId] = true;
                    document.getElementById(chartId).style.display = 'flex';
                    document.getElementById(chartId + 'Toggle').textContent = 'Hide ' + chartId.slice(-1);
                }});
            }}

            function hideAllCharts() {{
                Object.keys(chartVisibility).forEach(chartId => {{
                    chartVisibility[chartId] = false;
                    document.getElementById(chartId).style.display = 'none';
                    document.getElementById(chartId + 'Toggle').textContent = 'Show ' + chartId.slice(-1);
                }});
            }}

            function updateAdvancedCalculator() {{
                const entry = parseFloat(document.getElementById('calcEntry').value) || 0;
                const exit = parseFloat(document.getElementById('calcExit').value) || 0;
                const positionSize = parseFloat(document.getElementById('calcPosition').value) || 0;
                const leverage = parseFloat(document.getElementById('calcLeverage').value) || 1;

                if (entry > 0 && positionSize > 0 && leverage > 0) {{
                    const marginRequired = positionSize / leverage;
                    const leveragedPosition = positionSize * leverage;
                    const priceChange = exit - entry;
                    const profitLoss = (priceChange / entry) * leveragedPosition;
                    const roiPercent = (profitLoss / marginRequired) * 100;
                    const liquidationLong = entry * (1 - (1 / leverage) * 0.9);
                    const liquidationShort = entry * (1 + (1 / leverage) * 0.9);
                    const liquidationPrice = profitLoss >= 0 ? liquidationLong : liquidationShort;

                    document.getElementById('marginRequired').textContent = '$' + marginRequired.toFixed(2);
                    document.getElementById('positionSize').textContent = '$' + leveragedPosition.toFixed(2);
                    document.getElementById('profitLoss').textContent = (profitLoss >= 0 ? '+$' : '$') + profitLoss.toFixed(2);
                    document.getElementById('roiPercent').textContent = (roiPercent >= 0 ? '+' : '') + roiPercent.toFixed(2) + '%';
                    document.getElementById('liquidationPrice').textContent = '$' + liquidationPrice.toFixed(6);

                    document.getElementById('profitLoss').className = 'result-value ' + (profitLoss >= 0 ? 'result-positive' : 'result-negative');
                    document.getElementById('roiPercent').className = 'result-value ' + (roiPercent >= 0 ? 'result-positive' : 'result-negative');
                }} else {{
                    document.getElementById('marginRequired').textContent = '$0.00';
                    document.getElementById('positionSize').textContent = '$0.00';
                    document.getElementById('profitLoss').textContent = '$0.00';
                    document.getElementById('roiPercent').textContent = '0.00%';
                    document.getElementById('liquidationPrice').textContent = '$0.00';
                    document.getElementById('profitLoss').className = 'result-value';
                    document.getElementById('roiPercent').className = 'result-value';
                }}
            }}

            function setCurrentPriceAsEntry() {{
                document.getElementById('calcEntry').value = 68250.42;
                updateAdvancedCalculator();
            }}

            function setCurrentPriceAsExit() {{
                document.getElementById('calcExit').value = 68250.42;
                updateAdvancedCalculator();
            }}

            function saveNotes() {{
                const notes = document.getElementById('tradingNotes').value;
                fetch('/save_trading_notes', {{
                    method: 'POST', 
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{notes: notes}})
                }}).then(r => r.json()).then(data => showSaveIndicator())
                .catch(err => console.error('Error saving notes:', err));
            }}

            function clearNotes() {{
                if (confirm('Are you sure you want to clear all notes?')) {{
                    document.getElementById('tradingNotes').value = '';
                }}
            }}

            function loadSampleNotes() {{
                const sampleNotes = `Trading Journal - ${{new Date().toLocaleDateString()}}\\n\\nCurrent Setup:\\n• BTC showing bullish divergence\\n• Key levels...`;
                document.getElementById('tradingNotes').value = sampleNotes;
            }}

            function saveTradeToJournal() {{
                const entry = parseFloat(document.getElementById('calcEntry').value) || 0;
                const exit = parseFloat(document.getElementById('calcExit').value) || 0;
                const positionSize = parseFloat(document.getElementById('calcPosition').value) || 0;
                const leverage = parseFloat(document.getElementById('calcLeverage').value) || 1;

                if (entry === 0 || exit === 0) {{
                    alert('Please enter both entry and exit prices');
                    return;
                }}

                const priceChange = exit - entry;
                const leveragedPosition = positionSize * leverage;
                const profitLoss = (priceChange / entry) * leveragedPosition;
                const roiPercent = (profitLoss / (positionSize / leverage)) * 100;

                const tradeData = {{
                    symbol: 'BTCUSDT',
                    entry_price: entry,
                    exit_price: exit,
                    position_size: positionSize,
                    leverage: leverage,
                    profit_loss: profitLoss,
                    roi: roiPercent,
                    notes: 'Saved from calculator'
                }};

                fetch('/add_trade_journal', {{
                    method: 'POST', 
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify(tradeData)
                }}).then(r => r.json()).then(data => {{
                    showSaveIndicator();
                    alert('Trade saved to journal!');
                }}).catch(err => console.error('Error saving trade:', err));
            }}

            // Event listeners
            document.getElementById('calcEntry').addEventListener('input', updateAdvancedCalculator);
            document.getElementById('calcExit').addEventListener('input', updateAdvancedCalculator);
            document.getElementById('calcPosition').addEventListener('input', updateAdvancedCalculator);
            document.getElementById('calcLeverage').addEventListener('input', updateAdvancedCalculator);

            // Auto-save notes
            let notesTimeout;
            document.getElementById('tradingNotes').addEventListener('input', function() {{
                clearTimeout(notesTimeout);
                notesTimeout = setTimeout(saveNotes, 1000);
            }});

            window.addEventListener('load', function() {{
                initializeTradingView();
                updateAdvancedCalculator();
            }});

            // Save chart states before unload
            window.addEventListener('beforeunload', function() {{
                Object.keys(tradingViewWidgets).forEach(chartId => {{
                    saveChartState(chartId);
                }});
            }});
        </script>
    </body>
    </html>
    '''


def auth_page(mode='login', error=''):
    is_register = mode == 'register'
    return f'''
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{"Register" if is_register else "Login"} - Trading Dashboard</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 50%, #16213e 100%); color: #ffffff; display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 20px; }}
            .auth-container {{ background: rgba(17, 17, 17, 0.95); border: 1px solid #333; border-radius: 15px; padding: 40px; width: 100%; max-width: 400px; }}
            .auth-header {{ text-align: center; margin-bottom: 30px; }}
            .auth-header h1 {{ font-size: 2.5em; font-weight: 300; color: #00d4aa; margin-bottom: 10px; }}
            .auth-form {{ display: flex; flex-direction: column; gap: 20px; }}
            .form-group {{ display: flex; flex-direction: column; gap: 8px; }}
            .form-label {{ color: #00d4aa; font-size: 0.9em; font-weight: 600; }}
            .form-input {{ padding: 12px 16px; background: #222; border: 1px solid #333; border-radius: 8px; color: white; font-size: 1em; }}
            .auth-button {{ padding: 14px; background: #00d4aa; border: none; border-radius: 8px; color: #000; font-size: 1.1em; font-weight: 600; cursor: pointer; margin-top: 10px; }}
            .auth-button:hover {{ background: #00b894; }}
            .error-message {{ background: rgba(255, 77, 77, 0.1); border: 1px solid #ff4d4d; border-radius: 6px; padding: 12px; color: #ff4d4d; text-align: center; margin-bottom: 20px; }}
        </style>
    </head>
    <body>
        <div class="auth-container">
            <div class="auth-header">
                <h1>{"Create Account" if is_register else "Welcome Back"}</h1>
            </div>
            {f'<div class="error-message">{error}</div>' if error else ''}
            <form class="auth-form" method="POST" action="/{"register" if is_register else "login"}">
                <div class="form-group">
                    <label class="form-label" for="username">Username</label>
                    <input class="form-input" type="text" id="username" name="username" required placeholder="Enter your username">
                </div>
                <div class="form-group">
                    <label class="form-label" for="password">Password</label>
                    <input class="form-input" type="password" id="password" name="password" required placeholder="Enter your password">
                </div>
                {"<div class=\"form-group\"><label class=\"form-label\" for=\"confirm_password\">Confirm Password</label><input class=\"form-input\" type=\"password\" id=\"confirm_password\" name=\"confirm_password\" required placeholder=\"Confirm your password\"></div>" if is_register else ""}
                <button type="submit" class="auth-button">{"Create Account" if is_register else "Sign In"}</button>
            </form>
            <div style="text-align: center; margin-top: 20px; color: #888;">
                {"Already have an account? <a href=\"/login\" style=\"color: #00d4aa;\">Sign In</a>" if is_register else "Don't have an account? <a href=\"/register\" style=\"color: #00d4aa;\">Create Account</a>"}
            </div>
        </div>
    </body>
    </html>
    '''


@app.route('/market_data')
def get_market_data():
    return jsonify(market_data)


if __name__ == '__main__':
    price_thread = threading.Thread(target=price_updater, daemon=True)
    price_thread.start()
    print("🚀 PROFESSIONAL TRADING DASHBOARD STARTED")
    print("✅ COMPLETE CHART STATE SAVING ADDED!")
    print("📊 Indicators, drawings, and settings are now preserved!")
    print("🌐 Visit: http://localhost:5000")
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)