import websocket
import json
from datetime import datetime
import threading
import time
import ssl
import collections


class BinanceOrderBook:
    def __init__(self, symbol="btcusdt"):
        self.symbol = symbol
        self.bids = {}
        self.asks = {}
        self.ws = None
        self.data = []
        self.running = False

        # CVD Calculation
        self.cvd_history = collections.deque(maxlen=20)  # Store last 20 CVD values
        self.current_cvd = 0
        self.smoothed_cvd = 0

    def on_message(self, ws, message):
        try:
            data = json.loads(message)

            if 'b' in data and 'a' in data:
                self.bids = {float(price): float(qty) for price, qty in data['b']}
                self.asks = {float(price): float(qty) for price, qty in data['a']}

                # Calculate volumes
                bid_volume = sum(self.bids.values())
                ask_volume = sum(self.asks.values())

                # CALCULATE CVD (Cumulative Volume Delta)
                volume_delta = bid_volume - ask_volume
                self.current_cvd += volume_delta

                # SMOOTH CVD WITH MOVING AVERAGE
                self.cvd_history.append(self.current_cvd)
                self.smoothed_cvd = sum(self.cvd_history) / len(self.cvd_history)

                snapshot = {
                    'timestamp': datetime.now(),
                    'bid_volume': bid_volume,
                    'ask_volume': ask_volume,
                    'best_bid': max(self.bids.keys()) if self.bids else 0,
                    'best_ask': min(self.asks.keys()) if self.asks else 0,
                    # CVD Data
                    'cvd': self.current_cvd,
                    'smoothed_cvd': self.smoothed_cvd,
                    'volume_delta': volume_delta
                }

                self.data.append(snapshot)

        except Exception as e:
            print(f"Error: {e}")

    def on_error(self, ws, error):
        print(f"WebSocket error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print("WebSocket closed")
        self.running = False

    def on_open(self, ws):
        print(f"✅ Connected to {self.symbol.upper()}")
        self.running = True

    def start(self):
        websocket_url = f"wss://stream.binance.com:9443/ws/{self.symbol}@depth"

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