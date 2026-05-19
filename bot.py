import MetaTrader5 as mt5
import schedule
import time
import requests
import os
from flask import Flask
import threading

# ── Your Exness credentials (set these in Railway environment variables) ──
LOGIN = int(os.environ.get("MT5_LOGIN", "0"))
PASSWORD = os.environ.get("MT5_PASSWORD", "")
SERVER = os.environ.get("MT5_SERVER", "")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")

SYMBOL = "XAUUSD"
LOT = 0.01
MAGIC = 123456

app = Flask(__name__)

@app.route("/")
def home():
    return "AURUM Bot is running!"

def get_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50
    changes = [prices[i] - prices[i-1] for i in range(1, len(prices))]
    gains = [c for c in changes[-period:] if c > 0]
    losses = [abs(c) for c in changes[-period:] if c < 0]
    avg_gain = sum(gains) / period if gains else 0
    avg_loss = sum(losses) / period if losses else 0
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)))

def get_ma(prices, period):
    if len(prices) < period:
        return None
    return round(sum(prices[-period:]) / period, 2)

def ask_claude(price, rsi, fast_ma, slow_ma):
    try:
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": CLAUDE_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 500,
                "system": "You are a gold trading AI. Respond ONLY in JSON: {\"signal\": \"BUY\" or \"SELL\" or \"HOLD\", \"confidence\": number, \"reason\": \"string\"}",
                "messages": [{
                    "role": "user",
                    "content": f"Gold price: {price}, RSI: {rsi}, Fast MA: {fast_ma}, Slow MA: {slow_ma}. What is your signal?"
                }]
            }
        )
        data = response.json()
        text = data["content"][0]["text"]
        import json
        return json.loads(text)
    except Exception as e:
        print(f"Claude error: {e}")
        return {"signal": "HOLD", "confidence": 0, "reason": "error"}

def run_bot():
    print("Connecting to MT5...")
    if not mt5.initialize(login=LOGIN, password=PASSWORD, server=SERVER):
        print(f"MT5 init failed: {mt5.last_error()}")
        return

    print("Connected to Exness MT5!")
    rates = mt5.copy_rates_from_pos(SYMBOL, mt5.TIMEFRAME_M15, 0, 50)
    if rates is None:
        print("Could not get price data")
        mt5.shutdown()
        return

    prices = [r['close'] for r in rates]
    current_price = prices[-1]
    rsi = get_rsi(prices)
    fast_ma = get_ma(prices, 9)
    slow_ma = get_ma(prices, 21)

    print(f"Price: {current_price} | RSI: {rsi} | Fast MA: {fast_ma} | Slow MA: {slow_ma}")

    signal = ask_claude(current_price, rsi, fast_ma, slow_ma)
    print(f"AI Signal: {signal}")

    positions = mt5.positions_get(symbol=SYMBOL)

    if signal["signal"] == "BUY" and signal["confidence"] > 65 and len(positions) == 0:
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": LOT,
            "type": mt5.ORDER_TYPE_BUY,
            "price": mt5.symbol_info_tick(SYMBOL).ask,
            "sl": current_price - 15,
            "tp": current_price + 30,
            "magic": MAGIC,
            "comment": "AURUM BUY",
        }
        result = mt5.order_send(request)
        print(f"BUY sent: {result}")

    elif signal["signal"] == "SELL" and signal["confidence"] > 65 and len(positions) == 0:
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": LOT,
            "type": mt5.ORDER_TYPE_SELL,
            "price": mt5.symbol_info_tick(SYMBOL).bid,
            "sl": current_price + 15,
            "tp": current_price - 30,
            "magic": MAGIC,
            "comment": "AURUM SELL",
        }
        result = mt5.order_send(request)
        print(f"SELL sent: {result}")

    elif signal["signal"] == "HOLD" and len(positions) > 0:
        for pos in positions:
            close_request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": SYMBOL,
                "volume": pos.volume,
                "type": mt5.ORDER_TYPE_BUY if pos.type == 1 else mt5.ORDER_TYPE_SELL,
                "position": pos.ticket,
                "price": mt5.symbol_info_tick(SYMBOL).ask,
                "magic": MAGIC,
                "comment": "AURUM CLOSE",
            }
            mt5.order_send(close_request)
            print("Position closed")

    mt5.shutdown()

def start_scheduler():
    schedule.every(15).minutes.do(run_bot)
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    scheduler_thread = threading.Thread(target=start_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    run_bot()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
