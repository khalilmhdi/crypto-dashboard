import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import numpy as np


class AdvancedOrderFlowCandles:
    def __init__(self, timeframe_minutes=1):
        self.timeframe = timeframe_minutes
        self.candles = []
        self.current_candle = None
        self.candle_start = None
        self.ticks_data = []  # Store individual ticks for detailed analysis

    def add_tick(self, timestamp, bid_volume, ask_volume, best_bid, best_ask):
        """Add order book data with detailed tick information"""
        mid_price = (best_bid + best_ask) / 2
        imbalance = bid_volume - ask_volume

        # Store tick data for detailed candle construction
        tick_data = {
            'timestamp': timestamp,
            'bid_volume': bid_volume,
            'ask_volume': ask_volume,
            'best_bid': best_bid,
            'best_ask': best_ask,
            'mid_price': mid_price,
            'imbalance': imbalance
        }
        self.ticks_data.append(tick_data)

        # Start new candle
        if self.current_candle is None:
            self.start_new_candle(timestamp, mid_price, bid_volume, ask_volume, imbalance)
        elif timestamp >= self.candle_start + timedelta(minutes=self.timeframe):
            # Finalize current candle with all tick data
            self.finalize_candle()
            self.candles.append(self.current_candle)
            self.start_new_candle(timestamp, mid_price, bid_volume, ask_volume, imbalance)
        else:
            # Update current candle
            self.current_candle['high'] = max(self.current_candle['high'], mid_price)
            self.current_candle['low'] = min(self.current_candle['low'], mid_price)
            self.current_candle['close'] = mid_price
            self.current_candle['buy_volume'] += bid_volume
            self.current_candle['sell_volume'] += ask_volume
            self.current_candle['total_volume'] += (bid_volume + ask_volume)
            self.current_candle['imbalance'] += imbalance
            self.current_candle['ticks'] += 1

            # Track volume at price levels
            price_level = round(mid_price, 2)
            if price_level not in self.current_candle['volume_profile']:
                self.current_candle['volume_profile'][price_level] = {'buy': 0, 'sell': 0}

            self.current_candle['volume_profile'][price_level]['buy'] += bid_volume
            self.current_candle['volume_profile'][price_level]['sell'] += ask_volume

    def start_new_candle(self, timestamp, price, bid_vol, ask_vol, imbalance):
        """Start a new candle with volume profile"""
        self.candle_start = timestamp.replace(second=0, microsecond=0)
        self.current_candle = {
            'timestamp': self.candle_start,
            'open': price,
            'high': price,
            'low': price,
            'close': price,
            'buy_volume': bid_vol,
            'sell_volume': ask_vol,
            'total_volume': bid_vol + ask_vol,
            'imbalance': imbalance,
            'volume_profile': {},  # Price level -> volume data
            'ticks': 1,
            'max_buy_spike': bid_vol,
            'max_sell_spike': ask_vol,
            'big_orders': []  # Track individual big orders
        }

        # Initialize volume profile
        price_level = round(price, 2)
        self.current_candle['volume_profile'][price_level] = {'buy': bid_vol, 'sell': ask_vol}

    def finalize_candle(self):
        """Finalize candle before moving to next"""
        if self.current_candle:
            # Calculate volume profile statistics
            vol_profile = self.current_candle['volume_profile']
            if vol_profile:
                # Find Point of Control (POC) - price with highest volume
                max_volume = 0
                poc_price = self.current_candle['close']
                for price, volumes in vol_profile.items():
                    total_vol = volumes['buy'] + volumes['sell']
                    if total_vol > max_volume:
                        max_volume = total_vol
                        poc_price = price
                self.current_candle['poc_price'] = poc_price
                self.current_candle['poc_volume'] = max_volume

    def get_candles(self):
        """Get all complete candles"""
        candles = self.candles.copy()
        if self.current_candle and self.current_candle['ticks'] > 10:  # Only add if meaningful
            self.finalize_candle()
            candles.append(self.current_candle)
        return candles


def create_professional_trading_chart(candles):
    """Create professional trading chart with order flow inside candles"""
    if len(candles) < 2:
        print("Need more candles for professional chart")
        return

    # Create professional layout
    fig = plt.figure(figsize=(16, 12))
    gs = plt.GridSpec(3, 2, figure=fig, width_ratios=[3, 1], height_ratios=[2, 1, 1])

    # Main price chart with order flow
    ax_price = fig.add_subplot(gs[0, 0])
    ax_volume = fig.add_subplot(gs[1, 0], sharex=ax_price)
    ax_imbalance = fig.add_subplot(gs[2, 0], sharex=ax_price)
    ax_volume_profile = fig.add_subplot(gs[0, 1])
    ax_stats = fig.add_subplot(gs[1, 1])
    ax_signals = fig.add_subplot(gs[2, 1])

    # Prepare data
    timestamps = [c['timestamp'] for c in candles]
    opens = [c['open'] for c in candles]
    highs = [c['high'] for c in candles]
    lows = [c['low'] for c in candles]
    closes = [c['close'] for c in candles]
    buy_volumes = [c['buy_volume'] for c in candles]
    sell_volumes = [c['sell_volume'] for c in candles]
    imbalances = [c['imbalance'] for c in candles]

    # 1. MAIN PRICE CHART WITH ORDER FLOW CANDLES
    for i, (ts, open_val, high, low, close, buy_vol, sell_vol) in enumerate(zip(
            timestamps, opens, highs, lows, closes, buy_volumes, sell_volumes)):

        # Calculate candle body properties
        body_height = abs(close - open_val)
        body_bottom = min(open_val, close)

        # Create order flow candle - width based on total volume
        total_vol = buy_vol + sell_vol
        max_vol = max(buy_volumes + sell_volumes)
        candle_width = 0.0001 + (total_vol / max_vol) * 0.0003

        # Candle color based on order flow imbalance
        imbalance_ratio = (buy_vol - sell_vol) / total_vol if total_vol > 0 else 0

        if imbalance_ratio > 0.1:  # Strong buy pressure
            color = 'limegreen'
            edge_color = 'darkgreen'
        elif imbalance_ratio > 0:  # Mild buy pressure
            color = 'green'
            edge_color = 'darkgreen'
        elif imbalance_ratio < -0.1:  # Strong sell pressure
            color = 'red'
            edge_color = 'darkred'
        else:  # Mild sell pressure
            color = 'lightcoral'
            edge_color = 'darkred'

        # Draw candle wick
        ax_price.plot([ts, ts], [low, high], color='black', linewidth=1, alpha=0.7)

        # Draw candle body with order flow information
        if body_height > 0:
            rect = plt.Rectangle((ts - timedelta(minutes=0.0005), body_bottom),
                                 timedelta(minutes=0.001), body_height,
                                 facecolor=color, edgecolor=edge_color, linewidth=2,
                                 alpha=0.8)
            ax_price.add_patch(rect)

        # Add volume text inside large candles
        if total_vol > max_vol * 0.3:  # Large volume candle
            ax_price.text(ts, (high + low) / 2, f'{total_vol:.0f}',
                          ha='center', va='center', fontsize=8, fontweight='bold',
                          bbox=dict(boxstyle="round,pad=0.3", facecolor='white', alpha=0.8))

        # Highlight very large orders
        if total_vol > max_vol * 0.5:
            ax_price.plot(ts, high, marker='*', markersize=12, color='gold',
                          markeredgecolor='black', markeredgewidth=1)

    ax_price.set_title('ORDER FLOW CANDLES - Size shows Volume, Color shows Buy/Sell Pressure',
                       fontweight='bold', fontsize=14, pad=20)
    ax_price.set_ylabel('Price', fontweight='bold')
    ax_price.grid(True, alpha=0.3)

    # 2. VOLUME BARS WITH BUY/SELL SPLIT
    for i, (ts, buy_vol, sell_vol) in enumerate(zip(timestamps, buy_volumes, sell_volumes)):
        ax_volume.bar(ts, buy_vol, color='green', alpha=0.7, width=0.0003, label='BUY' if i == 0 else "")
        ax_volume.bar(ts, sell_vol, color='red', alpha=0.7, width=0.0003, bottom=buy_vol,
                      label='SELL' if i == 0 else "")

    ax_volume.set_ylabel('Volume', fontweight='bold')
    ax_volume.set_title('BUY/SELL VOLUME BREAKDOWN', fontweight='bold')
    ax_volume.legend()
    ax_volume.grid(True, alpha=0.3)

    # 3. ORDER IMBALANCE
    bars = ax_imbalance.bar(timestamps, imbalances, alpha=0.8, width=0.0003)
    for bar, imb in zip(bars, imbalances):
        if imb > 0:
            bar.set_color('green')
        else:
            bar.set_color('red')

    ax_imbalance.axhline(y=0, color='black', linewidth=1)
    ax_imbalance.set_ylabel('Imbalance', fontweight='bold')
    ax_imbalance.set_xlabel('Time', fontweight='bold')
    ax_imbalance.set_title('ORDER IMBALANCE (Bid - Ask)', fontweight='bold')
    ax_imbalance.grid(True, alpha=0.3)

    # 4. VOLUME PROFILE (Right side - shows current candle volume distribution)
    if candles:
        current_candle = candles[-1]
        if 'volume_profile' in current_candle:
            prices = list(current_candle['volume_profile'].keys())
            buy_vols = [current_candle['volume_profile'][p]['buy'] for p in prices]
            sell_vols = [current_candle['volume_profile'][p]['sell'] for p in prices]

            # Sort by price
            sorted_data = sorted(zip(prices, buy_vols, sell_vols))
            prices, buy_vols, sell_vols = zip(*sorted_data)

            ax_volume_profile.barh(prices, buy_vols, color='green', alpha=0.7, label='BUY')
            ax_volume_profile.barh(prices, sell_vols, color='red', alpha=0.7, left=buy_vols, label='SELL')

            # Highlight POC if available
            if 'poc_price' in current_candle:
                ax_volume_profile.axhline(y=current_candle['poc_price'], color='blue',
                                          linestyle='--', alpha=0.7, label='POC')

    ax_volume_profile.set_title('VOLUME PROFILE\n(Current Candle)', fontweight='bold')
    ax_volume_profile.set_xlabel('Volume')
    ax_volume_profile.legend()
    ax_volume_profile.grid(True, alpha=0.3)

    # 5. TRADING STATISTICS
    stats_text = f"""
TRADING STATISTICS:
------------------
Total Candles: {len(candles)}
Avg Buy Volume: {np.mean(buy_volumes):.0f}
Avg Sell Volume: {np.mean(sell_volumes):.0f}
Max Imbalance: {max(imbalances):+.0f}
Min Imbalance: {min(imbalances):+.0f}
Buy Dominance: {(sum(buy_volumes) / sum(buy_volumes + sell_volumes) * 100):.1f}%
"""
    ax_stats.text(0.1, 0.9, stats_text, transform=ax_stats.transAxes, fontfamily='monospace',
                  verticalalignment='top', fontsize=10, bbox=dict(boxstyle="round", facecolor='lightblue'))
    ax_stats.axis('off')

    # 6. TRADING SIGNALS
    signals = analyze_trading_signals(candles)
    signals_text = "TRADING SIGNALS:\n----------------\n"
    if signals:
        for signal in signals[-3:]:  # Show last 3 signals
            signals_text += f"{signal['time'].strftime('%H:%M')} - {signal['type']}\n"
            signals_text += f"Reason: {signal['reason']}\n\n"
    else:
        signals_text += "No strong signals detected"

    ax_signals.text(0.1, 0.9, signals_text, transform=ax_signals.transAxes, fontfamily='monospace',
                    verticalalignment='top', fontsize=9, bbox=dict(boxstyle="round", facecolor='lightyellow'))
    ax_signals.axis('off')

    # Format x-axis
    for ax in [ax_price, ax_volume, ax_imbalance]:
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=1))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)

    plt.tight_layout()

    # Save and show
    filename = f'professional_order_flow_{datetime.now().strftime("%H%M%S")}.png'
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    print(f"💾 Professional chart saved: {filename}")
    plt.show()


def analyze_trading_signals(candles):
    """Analyze for professional trading signals"""
    if len(candles) < 3:
        return []

    signals = []
    for i in range(2, len(candles)):
        current = candles[i]
        prev1 = candles[i - 1]
        prev2 = candles[i - 2]

        # Strong buy signal: Increasing buy volume + price confirmation
        if (current['buy_volume'] > prev1['buy_volume'] > prev2['buy_volume'] and
                current['imbalance'] > 500 and current['close'] > current['open']):
            signals.append({
                'time': current['timestamp'],
                'type': 'STRONG BUY 📈',
                'reason': 'Increasing buy volume + positive imbalance'
            })

        # Strong sell signal: Increasing sell volume + price confirmation
        elif (current['sell_volume'] > prev1['sell_volume'] > prev2['sell_volume'] and
              current['imbalance'] < -500 and current['close'] < current['open']):
            signals.append({
                'time': current['timestamp'],
                'type': 'STRONG SELL 📉',
                'reason': 'Increasing sell volume + negative imbalance'
            })

        # Volume spike signal
        elif current['total_volume'] > 1.5 * np.mean([c['total_volume'] for c in candles[max(0, i - 3):i]]):
            direction = "BUY" if current['imbalance'] > 0 else "SELL"
            signals.append({
                'time': current['timestamp'],
                'type': f'VOLUME SPIKE {direction}',
                'reason': f'Volume spike with {direction} pressure'
            })

    return signals