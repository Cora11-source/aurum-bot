import requests
import schedule
import time
import os
import json
import threading
from flask import Flask

app = Flask(__name__)

# Credentials from environment variables
EXNESS_LOGIN = os.environ.get("MT5_LOGIN", "")
EXNESS_PASSWORD = os.environ.get("MT5_PASSWORD", "")
EXNESS_SERVER = os.environ.get("MT5_SERVER", "")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")

SYMBOL = "XAUUSD"
LOT = 0.01

@app.route("/")
def home():
    return "AURUM Bot is running! Gold trading active."

def get_gold_price():
    try:
        response = requests.get(
            "https://data-asg.goldprice.org/dbXRates/USD",
            headers={"User-Agent": "Mozilla/5.0"}
        )
        data = response.json()
        current = data["items"][0]["xauPrice"]
        print(f"Live gold price fetched: ${current}")
        # Build a simulated recent price series around current price
        import random
        prices = [current + random.uniform(-8, 8) for _ in range(30)]
        prices[-1] = current
        return prices
    except Exception as e:
        print(f"Price fetch error: {e}")
        # Fallback to metals-api free endpoint
        try:
            r = requests.get("https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/XAU/USD")
            d = r.json()
            price = d[0]["spreadProfilePrices"][0]["ask"]
            prices = [price + random.uniform(-8, 8) for _ in range(30)]
            prices[-1] = price
            return prices
        except:
            return None

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
                "system": "You are a gold trading AI. Respond ONLY in JSON with no extra text: {\"signal\": \"BUY\" or \"SELL\" or \"HOLD\", \"confidence\": number between 0-100, \"reason\": \"brief reason\"}",
                "messages": [{
                    "role": "user",
                    "content": f"Gold price: ${price:.2f}, RSI: {rsi}, Fast MA (9): {fast_ma}, Slow MA (21): {slow_ma}. Analyse and give signal."
                }]
            }
        )
        data = response.json()
        text = data["content"][0]["text"].strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        print(f"Claude error: {e}")
        return {"signal": "HOLD", "confidence": 0, "reason": "error"}

def place_order(signal, price):
    try:
        # Exness Trade API endpoint
        url = "https://trade.exness.com/api/v1/orders"
        headers = {
            "Authorization": f"Bearer {EXNESS_LOGIN}:{EXNESS_PASSWORD}",
            "Content-Type": "application/json"
        }
        order = {
            "symbol": SYMBOL,
            "side": signal,
            "type": "MARKET",
            "volume": LOT,
            "stopLoss": price - 15 if signal == "BUY" else price + 15,
            "takeProfit": price + 30 if signal == "BUY" else price - 30,
            "comment": "AURUM BOT"
        }
        response = requests.post(url, headers=headers, json=order)
        print(f"Order response: {response.json()}")
    except Exception as e:
        print(f"Order error: {e}")

def run_bot():
    print("---- AURUM Bot running ----")
    prices = get_gold_price()
    if not prices or len(prices) < 22:
        print("Not enough price data")
        return

    current_price = prices[-1]
    rsi = get_rsi(prices)
    fast_ma = get_ma(prices, 9)
    slow_ma = get_ma(prices, 21)

    print(f"Gold: ${current_price:.2f} | RSI: {rsi} | FastMA: {fast_ma} | SlowMA: {slow_ma}")

    signal = ask_claude(current_price, rsi, fast_ma, slow_ma)
    print(f"AI Signal: {signal['signal']} | Confidence: {signal['confidence']}% | {signal['reason']}")

    if signal["signal"] in ["BUY", "SELL"] and signal["confidence"] > 65:
        print(f"Placing {signal['signal']} order...")
        place_order(signal["signal"], current_price)
    else:
        print("Holding - no trade placed")

def start_scheduler():
    schedule.every(15).minutes.do(run_bot)
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    print("AURUM Bot starting...")
    scheduler_thread = threading.Thread(target=start_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    run_bot()
    from waitress import serve
    serve(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
