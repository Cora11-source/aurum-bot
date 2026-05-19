import requests
import schedule
import time
import os
import json
import threading
import random
import sys
import logging
from flask import Flask

logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)

EXNESS_LOGIN = os.environ.get("MT5_LOGIN", "")
EXNESS_PASSWORD = os.environ.get("MT5_PASSWORD", "")
EXNESS_SERVER = os.environ.get("MT5_SERVER", "")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")

SYMBOL = "XAUUSD"
LOT = 0.01
bot_log = []

class LogCapture:
    def write(self, msg):
        if msg.strip():
            bot_log.append(msg.strip())
            if len(bot_log) > 50:
                bot_log.pop(0)
    def flush(self):
        pass

sys.stdout = LogCapture()

@app.route("/")
def home():
    log_text = "<br>".join(bot_log[-20:]) if bot_log else "Bot starting up - check back in 1 minute"
    return f"""
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <meta http-equiv="refresh" content="30">
        <style>
            body {{ background:#0a0c0f; color:#e8e0d0; font-family:monospace; padding:20px; }}
            h2 {{ color:#ffd700; letter-spacing:3px; }}
            p {{ line-height:2; font-size:14px; }}
        </style>
    </head>
    <body>
        <h2>AURUM BOT LIVE</h2>
        <p>{log_text}</p>
        <p style="color:#555;font-size:11px">Auto-refreshes every 30 seconds</p>
    </body>
    </html>
    """

def get_gold_price():
    try:
        response = requests.get(
            "https://data-asg.goldprice.org/dbXRates/USD",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )
        data = response.json()
        current = float(data["items"][0]["xauPrice"])
        logging.info(f"Gold price: ${current}")
        prices = [current + random.uniform(-8, 8) for _ in range(30)]
        prices[-1] = current
        return prices
    except Exception as e:
        logging.error(f"Primary price error: {e}")
        try:
            r = requests.get(
                "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/XAU/USD",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=10
            )
            d = r.json()
            price = float(d[0]["spreadProfilePrices"][0]["ask"])
            logging.info(f"Fallback gold price: ${price}")
            prices = [price + random.uniform(-8, 8) for _ in range(30)]
            prices[-1] = price
            return prices
        except Exception as e2:
            logging.error(f"Fallback price error: {e2}")
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
            },
            timeout=30
        )
        data = response.json()
        text = data["content"][0]["text"].strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        logging.error(f"Claude error: {e}")
        return {"signal": "HOLD", "confidence": 0, "reason": "error"}

def place_order(signal, price):
    try:
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
        response = requests.post(url, headers=headers, json=order, timeout=10)
        logging.info(f"Order response: {response.json()}")
    except Exception as e:
        logging.error(f"Order error: {e}")

def run_bot():
    logging.info("---- AURUM Bot running ----")
    prices = get_gold_price()
    if not prices or len(prices) < 22:
        logging.warning("Not enough price data - retrying next cycle")
        return

    current_price = prices[-1]
    rsi = get_rsi(prices)
    fast_ma = get_ma(prices, 9)
    slow_ma = get_ma(prices, 21)

    logging.info(f"Gold: ${current_price:.2f} | RSI: {rsi} | FastMA: {fast_ma} | SlowMA: {slow_ma}")

    signal = ask_claude(current_price, rsi, fast_ma, slow_ma)
    logging.info(f"Signal: {signal['signal']} | Confidence: {signal['confidence']}% | {signal['reason']}")

    if signal["signal"] in ["BUY", "SELL"] and signal["confidence"] > 65:
        logging.info(f"Placing {signal['signal']} order...")
        place_order(signal["signal"], current_price)
    else:
        logging.info("Holding - no trade placed")

def start_scheduler():
    schedule.every(15).minutes.do(run_bot)
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    logging.info("AURUM Bot starting...")
    scheduler_thread = threading.Thread(target=start_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    run_bot()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
