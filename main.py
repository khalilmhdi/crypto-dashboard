from order_book import BinanceOrderBook
from advanced_order_flow import AdvancedOrderFlowCandles, create_professional_trading_chart
import threading
import time


def main():
    print("🚀 PROFESSIONAL ORDER FLOW TRADING ANALYZER")
    print("=" * 70)
    print("📊 Building SMART CANDLES that show order flow inside price action...")
    print("⏰ Collecting 5 minutes of data for professional chart")
    print("🎯 Candles show: Volume size + Buy/Sell color + Big order stars")
    print("=" * 70)

    order_book = BinanceOrderBook("btcusdt")
    candle_gen = AdvancedOrderFlowCandles(timeframe_minutes=1)

    try:
        ws_thread = threading.Thread(target=order_book.start)
        ws_thread.daemon = True
        ws_thread.start()

        time.sleep(3)
        print("✅ Connected - Building smart candles...")

        start_time = time.time()
        collection_time = 5 * 60

        while time.time() - start_time < collection_time:
            if order_book.data:
                latest = order_book.data[-1]
                candle_gen.add_tick(
                    latest['timestamp'],
                    latest['bid_volume'],
                    latest['ask_volume'],
                    latest['best_bid'],
                    latest['best_ask']
                )

            time.sleep(0.1)

        # Generate professional chart
        candles = candle_gen.get_candles()

        if len(candles) >= 2:
            print(f"\n✅ Collected {len(candles)} smart candles")
            print("📈 Generating PROFESSIONAL ORDER FLOW CHART...")
            create_professional_trading_chart(candles)
        else:
            print("❌ Not enough data for professional chart")

    except KeyboardInterrupt:
        print("\n🛑 Stopped by user")
    finally:
        order_book.stop()


if __name__ == "__main__":
    main()