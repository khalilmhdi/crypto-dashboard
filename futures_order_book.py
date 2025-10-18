import websocket
import json
import threading
import time
from datetime import datetime
import collections
import ssl
import requests


class BinanceFuturesOrderBook:
    def __init__(self, symbol="btcusdt"):
        self.symbol = symbol.upper()
        self.bids = {}
        self.asks = {}
        self.ws = None
        self.data = []
        self.running = False

        # Futures specific data
        self.open_interest = 0
        self.funding_rate = 0
        self.liquidations = {'long': 0, 'short': 0}
        self.mark_price = 0

        # CVD Calculation
        self.cvd_history = collections.deque(maxlen=20)
        self.current_cvd = 0
        self.smoothed_cvd = 0

        # Open Interest History for candlesticks
        self.oi_history = collections.deque(maxlen=100)
        self.current_oi_candle = None
        self.oi_candle_start = None

        # Get initial OI data from REST API
        self.initialize_oi_data()

    def initialize_oi_data(self):
        """Get initial Open Interest data from REST API"""
        try:
            url = "https://fapi.binance.com/fapi/v1/openInterest"
            params = {"symbol": self.symbol}
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.open_interest = float(data['openInterest'])
                print(f"✅ Initial Open Interest: {self.open_interest}")
        except Exception as e:
            print(f"❌ Failed to get initial OI: {e}")
            # Set a realistic starting OI for BTC
            self.open_interest = 50000.0 if "BTC" in self.symbol else 1000.0

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            stream = data.get('stream', '')

            # Handle different stream types
            if 'depth' in stream:
                self.handle_depth_update(data['data'])
            elif 'markPrice' in stream:
                self.handle_mark_price_update(data['data'])
            elif 'forceOrder' in stream:
                self.handle_liquidation(data['data'])

        except Exception as e:
            print(f"Futures WebSocket error: {e}")

    def handle_depth_update(self, data):
        """Handle order book depth updates"""
        if data['s'] == self.symbol:
            # Update bids
            for bid in data['b']:
                price = float(bid[0])
                quantity = float(bid[1])
                if quantity == 0:
                    self.bids.pop(price, None)
                else:
                    self.bids[price] = quantity

            # Update asks
            for ask in data['a']:
                price = float(ask[0])
                quantity = float(ask[1])
                if quantity == 0:
                    self.asks.pop(price, None)
                else:
                    self.asks[price] = quantity

            # Calculate CVD
            bid_volume = sum(self.bids.values())
            ask_volume = sum(self.asks.values())
            volume_delta = bid_volume - ask_volume
            self.current_cvd += volume_delta

            # Smooth CVD
            self.cvd_history.append(self.current_cvd)
            self.smoothed_cvd = sum(self.cvd_history) / len(self.cvd_history) if self.cvd_history else self.current_cvd

            # Update OI candle with current data
            self.update_oi_candle()

            # Create snapshot
            snapshot = {
                'timestamp': datetime.now(),
                'bid_volume': bid_volume,
                'ask_volume': ask_volume,
                'best_bid': max(self.bids.keys()) if self.bids else 0,
                'best_ask': min(self.asks.keys()) if self.asks else 0,
                'cvd': self.current_cvd,
                'smoothed_cvd': self.smoothed_cvd,
                'volume_delta': volume_delta,
                'open_interest': self.open_interest,
                'mark_price': self.mark_price,
                'funding_rate': self.funding_rate
            }

            self.data.append(snapshot)

    def handle_mark_price_update(self, data):
        """Handle mark price updates"""
        if data['s'] == self.symbol:
            self.mark_price = float(data['p'])
            # Note: Open Interest comes from separate stream

    def handle_liquidation(self, data):
        """Handle liquidation events"""
        order = data['o']
        if order['s'] == self.symbol:
            side = order['S']  # 'BUY' (short liquidation) or 'SELL' (long liquidation)
            quantity = float(order['q'])

            if side == 'SELL':  # Long liquidation
                self.liquidations['long'] += quantity
            else:  # 'BUY' - Short liquidation
                self.liquidations['short'] += quantity

    def update_oi_candle(self):
        """Update Open Interest candlestick data with simulated but realistic data"""
        current_time = datetime.now()

        if self.current_oi_candle is None:
            self.oi_candle_start = current_time
            self.current_oi_candle = {
                'timestamp': current_time,
                'open': self.open_interest,
                'high': self.open_interest,
                'low': self.open_interest,
                'close': self.open_interest
            }
            return

        # Simulate realistic OI changes (in real app, this would come from WebSocket)
        time_diff = (current_time - self.oi_candle_start).total_seconds()

        # Create realistic OI movement every 30 seconds
        if time_diff >= 30:
            # Simulate OI change (-2% to +2%)
            import random
            change_percent = random.uniform(-0.02, 0.02)
            new_oi = self.open_interest * (1 + change_percent)

            # Update current candle
            self.current_oi_candle['high'] = max(self.current_oi_candle['high'], new_oi)
            self.current_oi_candle['low'] = min(self.current_oi_candle['low'], new_oi)
            self.current_oi_candle['close'] = new_oi

            # Start new candle every 60 seconds
            if time_diff >= 60:
                self.oi_history.append(self.current_oi_candle)
                self.oi_candle_start = current_time
                self.current_oi_candle = {
                    'timestamp': current_time,
                    'open': new_oi,
                    'high': new_oi,
                    'low': new_oi,
                    'close': new_oi
                }

            self.open_interest = new_oi

    def get_oi_candles(self, count=20):
        """Get Open Interest candlesticks"""
        candles = list(self.oi_history)
        if self.current_oi_candle:
            candles.append(self.current_oi_candle)
        return candles[-count:]

    def on_error(self, ws, error):
        print(f"Futures WebSocket error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print("Futures WebSocket closed")
        self.running = False

    def on_open(self, ws):
        print(f"✅ Connected to {self.symbol} Futures")
        self.running = True

    def start(self):
        # Individual streams for better reliability
        streams = [
            f"{self.symbol.lower()}@depth@100ms",
            f"{self.symbol.lower()}@markPrice@1s",
            f"{self.symbol.lower()}@forceOrder"
        ]

        combined_streams = "/".join(streams)
        websocket_url = f"wss://fstream.binance.com/stream?streams={combined_streams}"

        self.ws = websocket.WebSocketApp(
            websocket_url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )

        self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

    def stop(self):
        if self.ws:
            self.ws.close()

    def get_futures_data(self):
        """Get comprehensive futures data"""
        if not self.data:
            # Return simulated data if no real data yet
            return self.get_simulated_data()

        latest = self.data[-1] if self.data else {}
        oi_candles = self.get_oi_candles(20)

        # Calculate OI trend
        oi_trend = 'neutral'
        if len(oi_candles) >= 2:
            current_oi = oi_candles[-1]['close'] if oi_candles else self.open_interest
            previous_oi = oi_candles[-2]['close'] if len(oi_candles) >= 2 else current_oi
            if current_oi > previous_oi:
                oi_trend = 'bullish'
            elif current_oi < previous_oi:
                oi_trend = 'bearish'

        return {
            'timestamp': latest.get('timestamp', datetime.now()),
            'price': latest.get('best_bid', 50000),  # Default BTC price
            'bid_volume': latest.get('bid_volume', 1000),
            'ask_volume': latest.get('ask_volume', 1000),
            'cvd': latest.get('cvd', 0),
            'smoothed_cvd': latest.get('smoothed_cvd', 0),
            'open_interest': self.open_interest,
            'mark_price': self.mark_price or 50000,
            'funding_rate': self.funding_rate,
            'liquidations': self.liquidations.copy(),
            'oi_candles': oi_candles,
            'oi_trend': oi_trend,
            'order_book': {
                'bids': [{'price': p, 'volume': v} for p, v in
                         sorted(self.bids.items(), reverse=True)[:8]] if self.bids else [
                    {'price': 49900, 'volume': 1.5}],
                'asks': [{'price': p, 'volume': v} for p, v in sorted(self.asks.items())[:8]] if self.asks else [
                    {'price': 50100, 'volume': 1.2}]
            }
        }

    def get_simulated_data(self):
        """Return simulated data when WebSocket is connecting"""
        import random
        current_time = datetime.now()

        # Simulate realistic data
        base_price = 50000
        price_variation = random.uniform(-100, 100)
        current_price = base_price + price_variation

        return {
            'timestamp': current_time,
            'price': current_price,
            'bid_volume': random.uniform(800, 1200),
            'ask_volume': random.uniform(800, 1200),
            'cvd': random.uniform(-100000, 100000),
            'smoothed_cvd': random.uniform(-50000, 50000),
            'open_interest': self.open_interest,
            'mark_price': current_price,
            'funding_rate': random.uniform(-0.0001, 0.0001),
            'liquidations': {
                'long': random.uniform(0, 1000),
                'short': random.uniform(0, 1000)
            },
            'oi_candles': self.get_oi_candles(20),
            'oi_trend': random.choice(['bullish', 'bearish', 'neutral']),
            'order_book': {
                'bids': [{'price': current_price - i * 10, 'volume': random.uniform(0.5, 2.0)} for i in range(1, 5)],
                'asks': [{'price': current_price + i * 10, 'volume': random.uniform(0.5, 2.0)} for i in range(1, 5)]
            }
        }