from flask import Flask, render_template, jsonify
import threading
import time
import json
from datetime import datetime
from order_book import BinanceOrderBook
import numpy as np  # For moving average calculation

app = Flask(__name__)

# Enhanced data storage for multiple symbols
trading_data = {
    'btcusdt': {
        'timestamps': [], 'bid_volumes': [], 'ask_volumes': [], 'imbalances': [],
        'prices': [], 'spreads': [], 'latest_update': None, 'latest_bid_volume': 0,
        'latest_ask_volume': 0, 'latest_imbalance': 0, 'latest_price': 0, 'latest_spread': 0,
        'total_volume': 0, 'buy_ratio': 0, 'signals': [], 'order_book': {'bids': [], 'asks': []},
        'big_orders': {'big_buys': [], 'big_sells': []},
        'massive_orders': {'massive_buys': [], 'massive_sells': []},
        'cvd_data': {'cvd': [], 'cvd_ma': [], 'timestamps': []},
        # NEW: Smart Money vs Retail analysis
        'smart_money_flow': [],  # Green line - large order accumulation
        'retail_flow': [],  # Yellow line - small order flow
        'smart_money_ma': [],  # Smart Money moving average
        'retail_ma': []  # Retail moving average
    },
    'tutusdt': {
        'timestamps': [], 'bid_volumes': [], 'ask_volumes': [], 'imbalances': [],
        'prices': [], 'spreads': [], 'latest_update': None, 'latest_bid_volume': 0,
        'latest_ask_volume': 0, 'latest_imbalance': 0, 'latest_price': 0, 'latest_spread': 0,
        'total_volume': 0, 'buy_ratio': 0, 'signals': [], 'order_book': {'bids': [], 'asks': []},
        'big_orders': {'big_buys': [], 'big_sells': []},
        'massive_orders': {'massive_buys': [], 'massive_sells': []},
        'cvd_data': {'cvd': [], 'cvd_ma': [], 'timestamps': []},
        # NEW: Smart Money vs Retail analysis
        'smart_money_flow': [],  # Green line - large order accumulation
        'retail_flow': [],  # Yellow line - small order flow
        'smart_money_ma': [],  # Smart Money moving average
        'retail_ma': []  # Retail moving average
    }
}

order_books = {}
is_running = False


class AdvancedCandleGenerator:
    def __init__(self):
        self.candles = []
        self.current_candle = None

    def add_tick(self, timestamp, bid_volume, ask_volume, best_bid, best_ask):
        mid_price = (best_bid + best_ask) / 2
        imbalance = bid_volume - ask_volume
        spread = best_ask - best_bid

        current_minute = timestamp.replace(second=0, microsecond=0)

        if self.current_candle is None or self.current_candle['minute'] != current_minute:
            if self.current_candle is not None:
                self.candles.append(self.current_candle)

            self.current_candle = {
                'minute': current_minute,
                'open': mid_price,
                'high': mid_price,
                'low': mid_price,
                'close': mid_price,
                'buy_volume': bid_volume,
                'sell_volume': ask_volume,
                'total_volume': bid_volume + ask_volume,
                'imbalance': imbalance,
                'spread': spread,
                'ticks': 1,
                'signal': None
            }
        else:
            self.current_candle['high'] = max(self.current_candle['high'], mid_price)
            self.current_candle['low'] = min(self.current_candle['low'], mid_price)
            self.current_candle['close'] = mid_price
            self.current_candle['buy_volume'] += bid_volume
            self.current_candle['sell_volume'] += ask_volume
            self.current_candle['total_volume'] += (bid_volume + ask_volume)
            self.current_candle['imbalance'] += imbalance
            self.current_candle['ticks'] += 1

            self.detect_signals()

    def detect_signals(self):
        if self.current_candle['total_volume'] > 1000:
            self.current_candle['signal'] = 'HIGH_VOLUME'
        elif abs(self.current_candle['imbalance']) > 500:
            self.current_candle['signal'] = 'STRONG_IMBALANCE'
        elif self.current_candle['spread'] < 0.01:
            self.current_candle['signal'] = 'TIGHT_SPREAD'

    def get_candles(self):
        candles = self.candles.copy()
        if self.current_candle:
            candles.append(self.current_candle)
        return candles


candle_generators = {
    'btcusdt': AdvancedCandleGenerator(),
    'tutusdt': AdvancedCandleGenerator()
}


def calculate_smart_money_retail(symbol, bid_volume, ask_volume, order_book_data):
    """Calculate Smart Money vs Retail flow based on order sizes"""
    # Define thresholds for Smart Money (large orders) vs Retail (small orders)
    if symbol == 'btcusdt':
        smart_money_threshold = 5.0  # BTC
        retail_threshold = 1.0  # BTC
    else:
        smart_money_threshold = 500.0  # TUT
        retail_threshold = 100.0  # TUT

    # Analyze order book for large vs small orders
    smart_money_buy = 0
    smart_money_sell = 0
    retail_buy = 0
    retail_sell = 0

    # Analyze bids (buy orders)
    if order_book_data.get('bids'):
        for price, volume in order_book_data['bids']:
            if volume >= smart_money_threshold:
                smart_money_buy += volume
            elif volume <= retail_threshold:
                retail_buy += volume

    # Analyze asks (sell orders)
    if order_book_data.get('asks'):
        for price, volume in order_book_data['asks']:
            if volume >= smart_money_threshold:
                smart_money_sell += volume
            elif volume <= retail_threshold:
                retail_sell += volume

    # Calculate net flows
    smart_money_net = smart_money_buy - smart_money_sell
    retail_net = retail_buy - retail_sell

    return smart_money_net, retail_net


def calculate_cvd(symbol, bid_volume, ask_volume, timestamp, order_book_data):
    """Calculate Cumulative Volume Delta (CVD) and its moving average"""
    cvd_data = trading_data[symbol]['cvd_data']

    # Calculate current delta (buy volume - sell volume)
    current_delta = bid_volume - ask_volume

    # Update CVD (cumulative sum of deltas)
    if cvd_data['cvd']:
        current_cvd = cvd_data['cvd'][-1] + current_delta
    else:
        current_cvd = current_delta

    # Add to CVD data
    cvd_data['cvd'].append(current_cvd)
    cvd_data['timestamps'].append(timestamp.strftime('%H:%M:%S'))

    # Calculate 20-period moving average of CVD
    if len(cvd_data['cvd']) >= 20:
        cvd_ma = np.mean(cvd_data['cvd'][-20:])
    else:
        cvd_ma = current_cvd

    cvd_data['cvd_ma'].append(cvd_ma)

    # NEW: Calculate Smart Money vs Retail flow
    smart_money_net, retail_net = calculate_smart_money_retail(symbol, bid_volume, ask_volume, order_book_data)

    # Update Smart Money and Retail data
    trading_data[symbol]['smart_money_flow'].append(smart_money_net)
    trading_data[symbol]['retail_flow'].append(retail_net)

    # Calculate moving averages for Smart Money and Retail
    if len(trading_data[symbol]['smart_money_flow']) >= 10:
        smart_ma = np.mean(trading_data[symbol]['smart_money_flow'][-10:])
        retail_ma = np.mean(trading_data[symbol]['retail_flow'][-10:])
    else:
        smart_ma = smart_money_net
        retail_ma = retail_net

    trading_data[symbol]['smart_money_ma'].append(smart_ma)
    trading_data[symbol]['retail_ma'].append(retail_ma)

    # Keep only last 100 data points
    for key in ['cvd', 'cvd_ma', 'timestamps']:
        if len(cvd_data[key]) > 100:
            cvd_data[key] = cvd_data[key][-100:]

    # Keep Smart Money and Retail data manageable
    for key in ['smart_money_flow', 'retail_flow', 'smart_money_ma', 'retail_ma']:
        if len(trading_data[symbol][key]) > 100:
            trading_data[symbol][key] = trading_data[symbol][key][-100:]

    return current_cvd, cvd_ma, smart_money_net, retail_net, smart_ma, retail_ma


def find_big_orders(order_book_data, current_price, symbol):
    """Find the biggest limit orders in the order book (near current price)"""
    big_buys = []
    big_sells = []

    if symbol == 'btcusdt':
        big_order_threshold = 10.0
        price_range = 2.0
    else:  # tutusdt
        big_order_threshold = 1000.0
        price_range = 5.0

    if order_book_data.get('bids'):
        for price, volume in order_book_data['bids']:
            price_diff_percent = ((current_price - price) / current_price) * 100
            if price_diff_percent <= price_range and volume >= big_order_threshold:
                big_buys.append({
                    'price': price,
                    'volume': volume,
                    'distance_percent': price_diff_percent,
                    'type': 'BUY_LIMIT'
                })

    if order_book_data.get('asks'):
        for price, volume in order_book_data['asks']:
            price_diff_percent = ((price - current_price) / current_price) * 100
            if price_diff_percent <= price_range and volume >= big_order_threshold:
                big_sells.append({
                    'price': price,
                    'volume': volume,
                    'distance_percent': price_diff_percent,
                    'type': 'SELL_LIMIT'
                })

    big_buys.sort(key=lambda x: x['volume'], reverse=True)
    big_sells.sort(key=lambda x: x['volume'], reverse=True)

    return {
        'big_buys': big_buys[:3],
        'big_sells': big_sells[:3]
    }


def find_massive_orders(order_book_data, current_price, symbol):
    """Find MASSIVE orders at ALL price levels - the biggest in entire order book"""
    massive_buys = []
    massive_sells = []

    if symbol == 'btcusdt':
        massive_threshold = 50.0
        top_n_orders = 5
    else:  # tutusdt
        massive_threshold = 5000.0
        top_n_orders = 5

    if order_book_data.get('bids'):
        for price, volume in order_book_data['bids']:
            if volume >= massive_threshold:
                price_diff_percent = ((current_price - price) / current_price) * 100
                massive_buys.append({
                    'price': price,
                    'volume': volume,
                    'distance_percent': price_diff_percent,
                    'distance_absolute': current_price - price,
                    'type': 'MASSIVE_BUY'
                })

    if order_book_data.get('asks'):
        for price, volume in order_book_data['asks']:
            if volume >= massive_threshold:
                price_diff_percent = ((price - current_price) / current_price) * 100
                massive_sells.append({
                    'price': price,
                    'volume': volume,
                    'distance_percent': price_diff_percent,
                    'distance_absolute': price - current_price,
                    'type': 'MASSIVE_SELL'
                })

    massive_buys.sort(key=lambda x: x['volume'], reverse=True)
    massive_sells.sort(key=lambda x: x['volume'], reverse=True)

    return {
        'massive_buys': massive_buys[:top_n_orders],
        'massive_sells': massive_sells[:top_n_orders]
    }


def data_collection_thread():
    global order_books, is_running, trading_data

    order_books['btcusdt'] = BinanceOrderBook("btcusdt")
    order_books['tutusdt'] = BinanceOrderBook("tutusdt")

    for symbol, order_book in order_books.items():
        ws_thread = threading.Thread(target=order_book.start, daemon=True)
        ws_thread.start()
        print(f"🚀 Starting data collection for {symbol.upper()}...")

    is_running = True
    time.sleep(3)

    data_count = 0
    while is_running:
        for symbol, order_book in order_books.items():
            if order_book.data:
                latest = order_book.data[-1]
                data_count += 1

                current_price = (latest['best_bid'] + latest['best_ask']) / 2
                total_vol = latest['bid_volume'] + latest['ask_volume']
                buy_ratio = latest['bid_volume'] / total_vol if total_vol > 0 else 0
                spread = latest['best_ask'] - latest['best_bid']

                # Update trading data
                trading_data[symbol]['timestamps'].append(latest['timestamp'].strftime('%H:%M:%S'))
                trading_data[symbol]['bid_volumes'].append(latest['bid_volume'])
                trading_data[symbol]['ask_volumes'].append(latest['ask_volume'])
                trading_data[symbol]['imbalances'].append(latest['bid_volume'] - latest['ask_volume'])
                trading_data[symbol]['prices'].append(current_price)
                trading_data[symbol]['spreads'].append(spread)

                # Update order book first (needed for Smart Money calculation)
                if hasattr(order_book, 'bids') and order_book.bids:
                    trading_data[symbol]['order_book']['bids'] = sorted(order_book.bids.items(), reverse=True)[:50]
                    trading_data[symbol]['order_book']['asks'] = sorted(order_book.asks.items())[:50]

                # NEW: Calculate CVD and Smart Money/Retail with order book data
                current_cvd, cvd_ma, smart_money_net, retail_net, smart_ma, retail_ma = calculate_cvd(
                    symbol,
                    latest['bid_volume'],
                    latest['ask_volume'],
                    latest['timestamp'],
                    trading_data[symbol]['order_book']
                )

                # Update latest values
                trading_data[symbol]['latest_update'] = latest['timestamp'].strftime('%H:%M:%S')
                trading_data[symbol]['latest_bid_volume'] = latest['bid_volume']
                trading_data[symbol]['latest_ask_volume'] = latest['ask_volume']
                trading_data[symbol]['latest_imbalance'] = latest['bid_volume'] - latest['ask_volume']
                trading_data[symbol]['latest_price'] = current_price
                trading_data[symbol]['latest_spread'] = spread
                trading_data[symbol]['total_volume'] = total_vol
                trading_data[symbol]['buy_ratio'] = buy_ratio
                trading_data[symbol]['latest_cvd'] = current_cvd
                trading_data[symbol]['latest_cvd_ma'] = cvd_ma
                # NEW: Smart Money and Retail data
                trading_data[symbol]['latest_smart_money'] = smart_money_net
                trading_data[symbol]['latest_retail'] = retail_net
                trading_data[symbol]['latest_smart_ma'] = smart_ma
                trading_data[symbol]['latest_retail_ma'] = retail_ma

                # Update order analysis
                trading_data[symbol]['big_orders'] = find_big_orders(
                    trading_data[symbol]['order_book'],
                    current_price,
                    symbol
                )

                trading_data[symbol]['massive_orders'] = find_massive_orders(
                    trading_data[symbol]['order_book'],
                    current_price,
                    symbol
                )

                detect_trading_signals(symbol, latest)

                candle_generators[symbol].add_tick(
                    latest['timestamp'],
                    latest['bid_volume'],
                    latest['ask_volume'],
                    latest['best_bid'],
                    latest['best_ask']
                )

                if data_count % 20 == 0:
                    print(
                        f"📊 {symbol.upper()}: Bid {latest['bid_volume']:.1f} | Ask {latest['ask_volume']:.1f} | CVD: {current_cvd:+.0f} | Smart: {smart_money_net:+.0f} | Retail: {retail_net:+.0f}")

                for key in ['timestamps', 'bid_volumes', 'ask_volumes', 'imbalances', 'prices', 'spreads']:
                    if len(trading_data[symbol][key]) > 50:
                        trading_data[symbol][key] = trading_data[symbol][key][-50:]

        time.sleep(0.5)


def detect_trading_signals(symbol, latest_data):
    bid_volume = latest_data['bid_volume']
    ask_volume = latest_data['ask_volume']
    imbalance = bid_volume - ask_volume

    signals = []

    threshold = 1000 if symbol == 'btcusdt' else 100

    if bid_volume > threshold:
        signals.append(f"🔥 BIG BUY: {bid_volume:.0f}")
    if ask_volume > threshold:
        signals.append(f"💧 BIG SELL: {ask_volume:.0f}")

    imbalance_threshold = 500 if symbol == 'btcusdt' else 50
    if imbalance > imbalance_threshold:
        signals.append("📈 STRONG BUYING")
    elif imbalance < -imbalance_threshold:
        signals.append("📉 STRONG SELLING")

    # CVD-based signals
    cvd_data = trading_data[symbol]['cvd_data']
    if len(cvd_data['cvd']) >= 2:
        current_cvd = cvd_data['cvd'][-1]
        prev_cvd = cvd_data['cvd'][-2]
        cvd_change = current_cvd - prev_cvd

        if cvd_change > 1000:
            signals.append(f"📊 CVD SPIKE: +{cvd_change:.0f}")
        elif cvd_change < -1000:
            signals.append(f"📊 CVD DROP: {cvd_change:.0f}")

    # Smart Money vs Retail signals
    smart_money = trading_data[symbol]['latest_smart_money']
    retail = trading_data[symbol]['latest_retail']

    if smart_money > 500 and retail < -200:
        signals.append("💎 SMART MONEY ACCUMULATION + RETAIL SELLING")
    elif smart_money < -500 and retail > 200:
        signals.append("🚨 SMART MONEY DISTRIBUTION + RETAIL BUYING")
    elif smart_money > 300:
        signals.append("📈 SMART MONEY BUYING")
    elif smart_money < -300:
        signals.append("📉 SMART MONEY SELLING")

    big_orders = trading_data[symbol]['big_orders']
    for big_buy in big_orders.get('big_buys', []):
        signals.append(
            f"🏔️ BUY WALL: {big_buy['volume']:.0f} @ {big_buy['price']:.4f} ({big_buy['distance_percent']:.1f}%)")

    for big_sell in big_orders.get('big_sells', []):
        signals.append(
            f"🧱 SELL WALL: {big_sell['volume']:.0f} @ {big_sell['price']:.4f} ({big_sell['distance_percent']:.1f}%)")

    massive_orders = trading_data[symbol]['massive_orders']
    for massive_buy in massive_orders.get('massive_buys', []):
        signals.append(
            f"💎 MASSIVE BUY: {massive_buy['volume']:.0f} @ {massive_buy['price']:.4f} ({massive_buy['distance_percent']:.1f}% below)")

    for massive_sell in massive_orders.get('massive_sells', []):
        signals.append(
            f"🚨 MASSIVE SELL: {massive_sell['volume']:.0f} @ {massive_sell['price']:.4f} ({massive_sell['distance_percent']:.1f}% above)")

    trading_data[symbol]['signals'] = signals[-10:] if signals else ["No strong signals"]


@app.route('/')
def index():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Advanced Order Flow Dashboard</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            :root {
                --primary: #667eea;
                --success: #4CAF50;
                --danger: #f44336;
                --warning: #ff9800;
                --info: #2196F3;
                --purple: #9C27B0;
                --dark: #2d3748;
                --black: #000000;
                --yellow: #FFEB3B;
                --smart-green: #00ff88;
                --retail-yellow: #ffcc00;
            }

            body { 
                font-family: 'Segoe UI', system-ui, sans-serif; 
                margin: 0; 
                padding: 20px; 
                background: linear-gradient(135deg, var(--primary) 0%, #764ba2 100%);
                color: white;
                min-height: 100vh;
            }

            .container { max-width: 1600px; margin: 0 auto; }

            .header { text-align: center; margin-bottom: 30px; }
            .header h1 { font-size: 2.8em; margin-bottom: 10px; text-shadow: 2px 2px 4px rgba(0,0,0,0.3); }

            .control-panel {
                display: flex;
                gap: 15px;
                margin-bottom: 20px;
                justify-content: center;
                flex-wrap: wrap;
            }

            .control-btn {
                padding: 10px 20px;
                background: rgba(255,255,255,0.2);
                border: none;
                border-radius: 8px;
                color: white;
                cursor: pointer;
                font-weight: bold;
                transition: all 0.3s ease;
            }

            .control-btn:hover {
                background: rgba(255,255,255,0.3);
                transform: translateY(-2px);
            }

            .control-btn.active {
                background: rgba(255,255,255,0.4);
                box-shadow: 0 4px 8px rgba(0,0,0,0.2);
            }

            .fullscreen-btn {
                position: absolute;
                top: 10px;
                right: 10px;
                background: rgba(255,255,255,0.2);
                border: none;
                border-radius: 5px;
                color: white;
                padding: 5px 10px;
                cursor: pointer;
                z-index: 1000;
            }

            .symbol-tabs { display: flex; gap: 10px; margin-bottom: 20px; justify-content: center; }
            .tab { padding: 10px 20px; background: rgba(255,255,255,0.1); border-radius: 8px; cursor: pointer; }
            .tab.active { background: rgba(255,255,255,0.3); font-weight: bold; }

            .dashboard-grid { 
                display: grid; 
                grid-template-columns: 1fr 1fr;
                gap: 20px; 
                margin-bottom: 20px; 
            }

            .cvd-chart-container {
                grid-column: 1 / -1;
                background: var(--black);
                padding: 25px;
                border-radius: 15px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.3);
                border: 2px solid var(--yellow);
                display: none;
                position: relative;
            }

            .cvd-chart-container.fullscreen {
                position: fixed;
                top: 0;
                left: 0;
                width: 100vw;
                height: 100vh;
                z-index: 9999;
                border-radius: 0;
                padding: 60px 20px 20px 20px;
            }

            .cvd-chart-container.active {
                display: block;
            }

            .smart-money-chart-container {
                grid-column: 1 / -1;
                background: var(--black);
                padding: 25px;
                border-radius: 15px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.3);
                border: 2px solid var(--smart-green);
                display: none;
                position: relative;
            }

            .smart-money-chart-container.fullscreen {
                position: fixed;
                top: 0;
                left: 0;
                width: 100vw;
                height: 100vh;
                z-index: 9999;
                border-radius: 0;
                padding: 60px 20px 20px 20px;
            }

            .smart-money-chart-container.active {
                display: block;
            }

            .orders-grid {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 20px;
                margin-bottom: 20px;
            }

            .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 25px; }

            .card {
                background: rgba(255, 255, 255, 0.1);
                padding: 25px;
                border-radius: 15px;
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255, 255, 255, 0.2);
            }

            .stat-card { text-align: center; }
            .stat-label { font-size: 0.9em; opacity: 0.8; margin-bottom: 8px; }
            .stat-value { font-size: 24px; font-weight: bold; margin: 10px 0; }

            .chart-container {
                background: white;
                padding: 25px;
                border-radius: 15px;
                box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            }

            .chart-container h3 {
                color: var(--dark);
                margin-top: 0;
                text-align: center;
                font-size: 1.3em;
            }

            .signals-container { grid-column: 1 / -1; }

            .signal {
                padding: 10px 15px;
                margin: 5px 0;
                border-radius: 8px;
                background: rgba(255, 255, 255, 0.1);
                border-left: 4px solid var(--warning);
            }

            .signal.buy { border-left-color: var(--success); }
            .signal.sell { border-left-color: var(--danger); }
            .signal.wall { border-left-color: var(--info); }
            .signal.massive { border-left-color: var(--purple); font-weight: bold; }
            .signal.cvd { border-left-color: var(--yellow); }
            .signal.smart { border-left-color: var(--smart-green); }
            .signal.retail { border-left-color: var(--retail-yellow); }

            .positive { color: var(--success); }
            .negative { color: var(--danger); }
            .neutral { color: var(--warning); }
            .cvd-color { color: var(--yellow); }
            .smart-color { color: var(--smart-green); }
            .retail-color { color: var(--retail-yellow); }

            .status-bar {
                text-align: center;
                padding: 15px;
                background: rgba(255, 255, 255, 0.1);
                border-radius: 10px;
                margin-bottom: 20px;
                backdrop-filter: blur(10px);
            }

            .order-book {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
                margin-top: 15px;
            }

            .bids { color: var(--success); }
            .asks { color: var(--danger); }

            .symbol-badge {
                background: var(--info);
                padding: 2px 8px;
                border-radius: 12px;
                font-size: 0.8em;
                margin-left: 10px;
            }

            .big-orders, .massive-orders {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
                margin-top: 15px;
            }

            .big-buy, .massive-buy { 
                background: rgba(76, 175, 80, 0.2);
                padding: 15px;
                border-radius: 10px;
                border-left: 4px solid var(--success);
            }

            .big-sell, .massive-sell { 
                background: rgba(244, 67, 54, 0.2);
                padding: 15px;
                border-radius: 10px;
                border-left: 4px solid var(--danger);
            }

            .massive-buy { border-left-color: var(--purple); background: rgba(156, 39, 176, 0.2); }
            .massive-sell { border-left-color: var(--purple); background: rgba(156, 39, 176, 0.2); }

            .order-item {
                padding: 8px;
                margin: 5px 0;
                background: rgba(255,255,255,0.1);
                border-radius: 5px;
            }

            .massive-item {
                padding: 10px;
                margin: 8px 0;
                background: rgba(255,255,255,0.15);
                border-radius: 8px;
                border: 1px solid var(--purple);
            }

            .section-title {
                text-align: center;
                margin: 20px 0 10px 0;
                font-size: 1.4em;
                color: var(--warning);
            }

            .cvd-stats, .smart-money-stats {
                display: grid;
                grid-template-columns: 1fr 1fr 1fr;
                gap: 15px;
                margin-top: 15px;
            }

            .cvd-stat, .smart-stat {
                text-align: center;
                padding: 10px;
                background: rgba(255,255,255,0.1);
                border-radius: 8px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚀 Advanced Order Flow Dashboard</h1>
                <p>Real-time Market Analysis with CVD, Smart Money & Retail Flow</p>
            </div>

            <!-- Control Panel -->
            <div class="control-panel">
                <button class="control-btn active" onclick="toggleChart('volume')">📊 Volume Chart</button>
                <button class="control-btn active" onclick="toggleChart('momentum')">⚖️ Momentum Chart</button>
                <button class="control-btn" onclick="toggleChart('cvd')" id="cvdToggle">📈 Show CVD Chart</button>
                <button class="control-btn" onclick="toggleChart('smartMoney')" id="smartMoneyToggle">💎 Show Smart Money vs Retail</button>
            </div>

            <div class="symbol-tabs">
                <div class="tab active" onclick="switchSymbol('btcusdt')">BTC/USDT</div>
                <div class="tab" onclick="switchSymbol('tutusdt')">TUT/USDT</div>
            </div>

            <div class="status-bar" id="status">
                🔄 Connecting to live data feed...
            </div>

            <!-- CVD Chart -->
            <div class="cvd-chart-container" id="cvdChartContainer">
                <button class="fullscreen-btn" onclick="toggleFullscreen('cvdChartContainer')">⛶ Fullscreen</button>
                <h3 style="color: var(--yellow);">📈 Cumulative Volume Delta (CVD) with 20-Period Moving Average</h3>
                <div class="cvd-stats">
                    <div class="cvd-stat">
                        <div>Current CVD</div>
                        <div class="stat-value cvd-color" id="currentCVD">0</div>
                    </div>
                    <div class="cvd-stat">
                        <div>CVD Moving Average</div>
                        <div class="stat-value cvd-color" id="currentCVDMA">0</div>
                    </div>
                    <div class="cvd-stat">
                        <div>CVD Trend</div>
                        <div class="stat-value" id="cvdTrend">NEUTRAL</div>
                    </div>
                </div>
                <canvas id="cvdChart" width="800" height="300"></canvas>
            </div>

            <!-- Smart Money vs Retail Chart -->
            <div class="smart-money-chart-container" id="smartMoneyChartContainer">
                <button class="fullscreen-btn" onclick="toggleFullscreen('smartMoneyChartContainer')">⛶ Fullscreen</button>
                <h3 style="color: var(--smart-green);">💎 Smart Money vs Retail Flow Analysis</h3>
                <div class="smart-money-stats">
                    <div class="smart-stat">
                        <div>Smart Money Flow</div>
                        <div class="stat-value smart-color" id="currentSmartMoney">0</div>
                    </div>
                    <div class="smart-stat">
                        <div>Retail Flow</div>
                        <div class="stat-value retail-color" id="currentRetail">0</div>
                    </div>
                    <div class="smart-stat">
                        <div>Market Sentiment</div>
                        <div class="stat-value" id="marketSentiment">NEUTRAL</div>
                    </div>
                </div>
                <canvas id="smartMoneyChart" width="800" height="300"></canvas>
            </div>

            <!-- Key Statistics -->
            <div class="stats-grid">
                <div class="card stat-card">
                    <div class="stat-label">Current Price</div>
                    <div class="stat-value" id="currentPrice">0.00</div>
                    <div id="currentSymbol">BTC/USDT</div>
                </div>
                <div class="card stat-card">
                    <div class="stat-label">Bid Volume</div>
                    <div class="stat-value" id="bidVolume">0</div>
                    <div>Buy Pressure</div>
                </div>
                <div class="card stat-card">
                    <div class="stat-label">Ask Volume</div>
                    <div class="stat-value" id="askVolume">0</div>
                    <div>Sell Pressure</div>
                </div>
                <div class="card stat-card">
                    <div class="stat-label">Order Imbalance</div>
                    <div class="stat-value" id="imbalance">0</div>
                    <div>Market Sentiment</div>
                </div>
                <div class="card stat-card">
                    <div class="stat-label">Spread</div>
                    <div class="stat-value" id="spread">0.00</div>
                    <div>Liquidity</div>
                </div>
                <div class="card stat-card">
                    <div class="stat-label">Buy Ratio</div>
                    <div class="stat-value" id="buyRatio">0%</div>
                    <div>Market Bias</div>
                </div>
            </div>

            <!-- Charts -->
            <div class="dashboard-grid">
                <div class="chart-container" id="volumeChartContainer">
                    <h3>📊 Volume Analysis</h3>
                    <canvas id="volumeChart" width="400" height="300"></canvas>
                </div>
                <div class="chart-container" id="momentumChartContainer">
                    <h3>⚖️ Order Flow Momentum</h3>
                    <canvas id="momentumChart" width="400" height="300"></canvas>
                </div>
            </div>

            <!-- Massive Orders Section -->
            <div class="section-title">💎 MASSIVE ORDER WALLS (All Price Levels)</div>
            <div class="orders-grid">
                <div class="card">
                    <h3>🏔️ Massive Buy Walls</h3>
                    <div class="massive-orders">
                        <div id="massiveBuysList">
                            <div class="massive-item">Scanning for massive buy orders...</div>
                        </div>
                    </div>
                </div>
                <div class="card">
                    <h3>🧱 Massive Sell Walls</h3>
                    <div class="massive-orders">
                        <div id="massiveSellsList">
                            <div class="massive-item">Scanning for massive sell orders...</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Regular Big Orders Section -->
            <div class="section-title">📈 Near Price Order Walls</div>
            <div class="orders-grid">
                <div class="card">
                    <h3>💚 Big Buy Walls (Near Current Price)</h3>
                    <div class="big-orders">
                        <div id="bigBuysList">
                            <div class="order-item">No big buy walls detected near current price</div>
                        </div>
                    </div>
                </div>
                <div class="card">
                    <h3>❤️ Big Sell Walls (Near Current Price)</h3>
                    <div class="big-orders">
                        <div id="bigSellsList">
                            <div class="order-item">No big sell walls detected near current price</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Trading Signals -->
            <div class="card signals-container">
                <h3>🎯 Live Trading Signals <span class="symbol-badge" id="signalSymbol">BTC/USDT</span></h3>
                <div id="signalsList">
                    <div class="signal neutral">Waiting for signals...</div>
                </div>
            </div>
        </div>

        <script>
            let volumeChart, momentumChart, cvdChart, smartMoneyChart;
            let updateCount = 0;
            let currentSymbol = 'btcusdt';
            let chartsVisible = {
                volume: true,
                momentum: true,
                cvd: false,
                smartMoney: false
            };

            function toggleFullscreen(containerId) {
                const container = document.getElementById(containerId);
                container.classList.toggle('fullscreen');

                // Update charts after fullscreen toggle
                setTimeout(() => {
                    if (containerId === 'cvdChartContainer' && chartsVisible.cvd) {
                        updateCVDChart(lastCVDData);
                    } else if (containerId === 'smartMoneyChartContainer' && chartsVisible.smartMoney) {
                        updateSmartMoneyChart(lastSmartMoneyData);
                    }
                }, 100);
            }

            function toggleChart(chartType) {
                const btn = event.target;
                const container = document.getElementById(chartType + 'ChartContainer');

                if (chartsVisible[chartType]) {
                    // Hide chart
                    if (container) {
                        container.style.display = 'none';
                        container.classList.remove('fullscreen');
                    }
                    btn.classList.remove('active');
                    if (chartType === 'cvd') {
                        btn.textContent = '📈 Show CVD Chart';
                    } else if (chartType === 'smartMoney') {
                        btn.textContent = '💎 Show Smart Money vs Retail';
                    }
                } else {
                    // Show chart
                    if (container) container.style.display = 'block';
                    if (chartType === 'cvd') {
                        container.classList.add('active');
                        btn.textContent = '📈 Hide CVD Chart';
                    } else if (chartType === 'smartMoney') {
                        container.classList.add('active');
                        btn.textContent = '💎 Hide Smart Money vs Retail';
                    } else {
                        btn.classList.add('active');
                    }
                }

                chartsVisible[chartType] = !chartsVisible[chartType];
                updateDashboard();
            }

            function switchSymbol(symbol) {
                currentSymbol = symbol;
                document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
                event.target.classList.add('active');

                const symbolName = symbol === 'btcusdt' ? 'BTC/USDT' : 'TUT/USDT';
                document.getElementById('currentSymbol').textContent = symbolName;
                document.getElementById('signalSymbol').textContent = symbolName;

                updateDashboard();
            }

            let lastCVDData = null;
            let lastSmartMoneyData = null;

            function updateDashboard() {
                fetch('/data?symbol=' + currentSymbol)
                    .then(response => response.json())
                    .then(data => {
                        updateCount++;
                        lastCVDData = data;
                        lastSmartMoneyData = data;

                        document.getElementById('status').innerHTML = 
                            `<span style="color: #4CAF50;">✅ ${currentSymbol.toUpperCase()} - Updates: ${updateCount} | Last: ${data.latest_update || '--:--:--'}</span>`;

                        // Update statistics
                        document.getElementById('currentPrice').textContent = data.latest_price?.toFixed(6) || '0.000000';
                        document.getElementById('bidVolume').textContent = data.latest_bid_volume?.toFixed(1) || '0';
                        document.getElementById('askVolume').textContent = data.latest_ask_volume?.toFixed(1) || '0';

                        const imbalance = data.latest_imbalance || 0;
                        const imbalanceElem = document.getElementById('imbalance');
                        imbalanceElem.textContent = imbalance.toFixed(1);
                        imbalanceElem.className = 'stat-value ' + (imbalance > 0 ? 'positive' : 'negative');

                        document.getElementById('spread').textContent = data.latest_spread?.toFixed(6) || '0.000000';
                        document.getElementById('buyRatio').textContent = ((data.buy_ratio || 0) * 100).toFixed(1) + '%';

                        // Update CVD stats
                        document.getElementById('currentCVD').textContent = data.latest_cvd?.toFixed(0) || '0';
                        document.getElementById('currentCVDMA').textContent = data.latest_cvd_ma?.toFixed(0) || '0';

                        // Update CVD trend
                        const cvdTrend = data.latest_cvd > data.latest_cvd_ma ? 'BULLISH' : 
                                       data.latest_cvd < data.latest_cvd_ma ? 'BEARISH' : 'NEUTRAL';
                        document.getElementById('cvdTrend').textContent = cvdTrend;
                        document.getElementById('cvdTrend').className = 'stat-value ' + 
                            (cvdTrend === 'BULLISH' ? 'positive' : cvdTrend === 'BEARISH' ? 'negative' : 'neutral');

                        // Update Smart Money stats
                        document.getElementById('currentSmartMoney').textContent = data.latest_smart_money?.toFixed(0) || '0';
                        document.getElementById('currentRetail').textContent = data.latest_retail?.toFixed(0) || '0';

                        // Update market sentiment
                        const smartMoney = data.latest_smart_money || 0;
                        const retail = data.latest_retail || 0;
                        let sentiment = 'NEUTRAL';
                        if (smartMoney > 300 && retail < -100) sentiment = 'STRONG BULLISH';
                        else if (smartMoney > 200) sentiment = 'BULLISH';
                        else if (smartMoney < -300 && retail > 100) sentiment = 'STRONG BEARISH';
                        else if (smartMoney < -200) sentiment = 'BEARISH';

                        document.getElementById('marketSentiment').textContent = sentiment;
                        document.getElementById('marketSentiment').className = 'stat-value ' + 
                            (sentiment.includes('BULLISH') ? 'positive' : sentiment.includes('BEARISH') ? 'negative' : 'neutral');

                        // Update signals
                        updateSignals(data.signals || []);

                        // Update order walls
                        updateBigOrders(data.big_orders);
                        updateMassiveOrders(data.massive_orders);

                        // Update charts
                        if (data.timestamps && data.timestamps.length > 0) {
                            if (chartsVisible.volume) updateVolumeChart(data);
                            if (chartsVisible.momentum) updateMomentumChart(data);
                            if (chartsVisible.cvd) updateCVDChart(data);
                            if (chartsVisible.smartMoney) updateSmartMoneyChart(data);
                        }
                    })
                    .catch(error => {
                        console.error('Error:', error);
                        document.getElementById('status').innerHTML = 
                            '<span style="color: #f44336;">❌ Connection Error</span>';
                    });
            }

            function updateSignals(signals) {
                const container = document.getElementById('signalsList');
                if (signals.length === 0) {
                    container.innerHTML = '<div class="signal neutral">No strong signals detected</div>';
                    return;
                }

                container.innerHTML = signals.map(signal => {
                    const isBuy = signal.includes('BUY') || signal.includes('BUYING');
                    const isSell = signal.includes('SELL') || signal.includes('SELLING');
                    const isWall = signal.includes('WALL');
                    const isMassive = signal.includes('MASSIVE');
                    const isCVD = signal.includes('CVD');
                    const isSmart = signal.includes('SMART');
                    const isRetail = signal.includes('RETAIL');
                    let cls = 'neutral';
                    if (isMassive) cls = 'massive';
                    else if (isBuy) cls = 'buy';
                    else if (isSell) cls = 'sell';
                    else if (isWall) cls = 'wall';
                    else if (isCVD) cls = 'cvd';
                    else if (isSmart) cls = 'smart';
                    else if (isRetail) cls = 'retail';

                    return `<div class="signal ${cls}">${signal}</div>`;
                }).join('');
            }

            function updateBigOrders(bigOrders) {
                const buysContainer = document.getElementById('bigBuysList');
                const sellsContainer = document.getElementById('bigSellsList');

                if (bigOrders && bigOrders.big_buys && bigOrders.big_buys.length > 0) {
                    buysContainer.innerHTML = bigOrders.big_buys.map(order => 
                        `<div class="order-item">
                            <strong>${order.volume.toFixed(0)}</strong> @ ${order.price.toFixed(4)}<br>
                            <small>${order.distance_percent.toFixed(1)}% below current price</small>
                        </div>`
                    ).join('');
                } else {
                    buysContainer.innerHTML = '<div class="order-item">No big buy walls near current price</div>';
                }

                if (bigOrders && bigOrders.big_sells && bigOrders.big_sells.length > 0) {
                    sellsContainer.innerHTML = bigOrders.big_sells.map(order => 
                        `<div class="order-item">
                            <strong>${order.volume.toFixed(0)}</strong> @ ${order.price.toFixed(4)}<br>
                            <small>${order.distance_percent.toFixed(1)}% above current price</small>
                        </div>`
                    ).join('');
                } else {
                    sellsContainer.innerHTML = '<div class="order-item">No big sell walls near current price</div>';
                }
            }

            function updateMassiveOrders(massiveOrders) {
                const buysContainer = document.getElementById('massiveBuysList');
                const sellsContainer = document.getElementById('massiveSellsList');

                if (massiveOrders && massiveOrders.massive_buys && massiveOrders.massive_buys.length > 0) {
                    buysContainer.innerHTML = massiveOrders.massive_buys.map(order => 
                        `<div class="massive-item">
                            <strong>💎 ${order.volume.toFixed(0)}</strong> @ ${order.price.toFixed(4)}<br>
                            <small>${order.distance_percent.toFixed(1)}% below current price</small><br>
                            <small>Distance: ${order.distance_absolute?.toFixed(2) || '0'} points</small>
                        </div>`
                    ).join('');
                } else {
                    buysContainer.innerHTML = '<div class="massive-item">No MASSIVE buy walls detected</div>';
                }

                if (massiveOrders && massiveOrders.massive_sells && massiveOrders.massive_sells.length > 0) {
                    sellsContainer.innerHTML = massiveOrders.massive_sells.map(order => 
                        `<div class="massive-item">
                            <strong>🚨 ${order.volume.toFixed(0)}</strong> @ ${order.price.toFixed(4)}<br>
                            <small>${order.distance_percent.toFixed(1)}% above current price</small><br>
                            <small>Distance: ${order.distance_absolute?.toFixed(2) || '0'} points</small>
                        </div>`
                    ).join('');
                } else {
                    sellsContainer.innerHTML = '<div class="massive-item">No MASSIVE sell walls detected</div>';
                }
            }

            function updateVolumeChart(data) {
                const ctx = document.getElementById('volumeChart').getContext('2d');
                if (volumeChart) volumeChart.destroy();

                volumeChart = new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: data.timestamps || [],
                        datasets: [
                            {
                                label: 'Bid Volume',
                                data: data.bid_volumes || [],
                                backgroundColor: 'rgba(76, 175, 80, 0.7)',
                                borderColor: 'rgba(76, 175, 80, 1)',
                                borderWidth: 1
                            },
                            {
                                label: 'Ask Volume',
                                data: data.ask_volumes || [],
                                backgroundColor: 'rgba(244, 67, 54, 0.7)',
                                borderColor: 'rgba(244, 67, 54, 1)',
                                borderWidth: 1
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        plugins: { title: { display: true, text: 'Bid vs Ask Volume' } },
                        scales: { x: { display: false }, y: { beginAtZero: true } }
                    }
                });
            }

            function updateMomentumChart(data) {
                const ctx = document.getElementById('momentumChart').getContext('2d');
                if (momentumChart) momentumChart.destroy();

                const colors = (data.imbalances || []).map(imb => 
                    imb > 0 ? 'rgba(76, 175, 80, 0.8)' : 'rgba(244, 67, 54, 0.8)'
                );

                momentumChart = new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: data.timestamps || [],
                        datasets: [{
                            label: 'Order Imbalance',
                            data: data.imbalances || [],
                            backgroundColor: colors,
                            borderColor: colors,
                            borderWidth: 1
                        }]
                    },
                    options: {
                        responsive: true,
                        plugins: { title: { display: true, text: 'Order Flow Imbalance' } },
                        scales: {
                            x: { display: false },
                            y: { 
                                beginAtZero: true,
                                ticks: { callback: function(value) { return value > 0 ? '+' + value : value; } }
                            }
                        }
                    }
                });
            }

            function updateCVDChart(data) {
                const ctx = document.getElementById('cvdChart').getContext('2d');
                if (cvdChart) cvdChart.destroy();

                const cvdData = data.cvd_data || {};
                const timestamps = cvdData.timestamps || [];
                const cvdValues = cvdData.cvd || [];
                const cvdMAValues = cvdData.cvd_ma || [];

                if (timestamps.length === 0) return;

                cvdChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: timestamps,
                        datasets: [
                            {
                                label: 'Cumulative Volume Delta (CVD)',
                                data: cvdValues,
                                borderColor: '#FFEB3B',
                                backgroundColor: 'rgba(255, 235, 59, 0.1)',
                                borderWidth: 3,
                                tension: 0.4,
                                fill: true
                            },
                            {
                                label: 'CVD Moving Average (20)',
                                data: cvdMAValues,
                                borderColor: '#FF9800',
                                backgroundColor: 'rgba(255, 152, 0, 0.1)',
                                borderWidth: 2,
                                borderDash: [5, 5],
                                tension: 0.4,
                                fill: false
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            title: { 
                                display: true, 
                                text: 'Cumulative Volume Delta (CVD) - Buy vs Sell Pressure Over Time',
                                color: '#FFEB3B',
                                font: { size: 16 }
                            },
                            legend: {
                                labels: { color: '#FFEB3B' }
                            }
                        },
                        scales: {
                            x: {
                                ticks: { color: '#FFEB3B' },
                                grid: { color: 'rgba(255,255,255,0.1)' }
                            },
                            y: {
                                ticks: { 
                                    color: '#FFEB3B',
                                    callback: function(value) {
                                        return value > 0 ? '+' + value : value;
                                    }
                                },
                                grid: { color: 'rgba(255,255,255,0.1)' }
                            }
                        }
                    }
                });
            }

            // NEW: Smart Money vs Retail Chart
            function updateSmartMoneyChart(data) {
                const ctx = document.getElementById('smartMoneyChart').getContext('2d');
                if (smartMoneyChart) smartMoneyChart.destroy();

                const timestamps = data.timestamps || [];
                const smartMoneyFlow = data.smart_money_flow || [];
                const retailFlow = data.retail_flow || [];
                const smartMoneyMA = data.smart_money_ma || [];
                const retailMA = data.retail_ma || [];

                if (timestamps.length === 0) return;

                smartMoneyChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: timestamps,
                        datasets: [
                            {
                                label: 'Smart Money Flow (Large Orders)',
                                data: smartMoneyFlow,
                                borderColor: '#00ff88',
                                backgroundColor: 'rgba(0, 255, 136, 0.1)',
                                borderWidth: 3,
                                tension: 0.4,
                                fill: true
                            },
                            {
                                label: 'Smart Money MA (10)',
                                data: smartMoneyMA,
                                borderColor: '#00cc6a',
                                backgroundColor: 'rgba(0, 204, 106, 0.1)',
                                borderWidth: 2,
                                borderDash: [5, 5],
                                tension: 0.4,
                                fill: false
                            },
                            {
                                label: 'Retail Flow (Small Orders)',
                                data: retailFlow,
                                borderColor: '#ffcc00',
                                backgroundColor: 'rgba(255, 204, 0, 0.1)',
                                borderWidth: 3,
                                tension: 0.4,
                                fill: true
                            },
                            {
                                label: 'Retail MA (10)',
                                data: retailMA,
                                borderColor: '#cc9900',
                                backgroundColor: 'rgba(204, 153, 0, 0.1)',
                                borderWidth: 2,
                                borderDash: [5, 5],
                                tension: 0.4,
                                fill: false
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            title: { 
                                display: true, 
                                text: 'Smart Money vs Retail Flow Analysis - Market Participant Behavior',
                                color: '#00ff88',
                                font: { size: 16 }
                            },
                            legend: {
                                labels: { color: '#ffffff' }
                            }
                        },
                        scales: {
                            x: {
                                ticks: { color: '#ffffff' },
                                grid: { color: 'rgba(255,255,255,0.1)' }
                            },
                            y: {
                                ticks: { 
                                    color: '#ffffff',
                                    callback: function(value) {
                                        return value > 0 ? '+' + value : value;
                                    }
                                },
                                grid: { color: 'rgba(255,255,255,0.1)' }
                            }
                        }
                    }
                });
            }

            setInterval(updateDashboard, 1500);
            updateDashboard();
        </script>
    </body>
    </html>
    """


@app.route('/data')
def get_data():
    from flask import request
    symbol = request.args.get('symbol', 'btcusdt')
    return jsonify(trading_data.get(symbol, {}))


if __name__ == '__main__':
    data_thread = threading.Thread(target=data_collection_thread, daemon=True)
    data_thread.start()

    print("🚀 Starting ADVANCED Order Flow Dashboard...")
    print("📊 Tracking: BTC/USDT & TUT/USDT")
    print("📈 NEW: Cumulative Volume Delta (CVD) with Moving Average")
    print("💎 NEW: Smart Money vs Retail Flow Analysis")
    print("⛶ NEW: Fullscreen charts for CVD and Smart Money")
    print("🎛️ NEW: Toggle-able charts for better space management")
    print("🌐 Open: http://localhost:5000")
    print("⏳ Waiting for data...")

    time.sleep(5)
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)