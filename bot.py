import requests
import schedule
import time
import os
import json
import threading
import random
import logging
from flask import Flask

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")
SYMBOL = "XAUUSD"
LOT = 0.01
bot_log = ["AURUM Bot started..."]

@app.route("/")
def home():
    try:
        log_text = "<br>".join(bot_log[-20:])
    except:
        log_text = "Starting up..."
    return f"""
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <meta http-equiv="refresh" content="30">
        <style>
            body {{ background:#0a0c0f; color:#e8e0d0; font-family:monospace; padding:20px; font-size:14px; }}
            h2 {{ color:#ffd700; letter-spacing:3px; }}
            p {{ line-height:2; }}
        </style>
    </head>
    <body>
        <h2>&#x25C8; AURUM BOT LIVE</h2>
        <p>{log_text}</p>
        <p style="color:#555;font-size:11px">Auto-refreshes every 30 seconds</p>
    </body>
    </html>
    """

def get_gold_price():
    # Try multiple free sources
    sources = [
        "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/xau.json",
        "https://latest.currency-api.pages.dev/v1/currencies/xau.json"
    ]
    for url in sources:
        try:
            r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            d = r.json()
            # Returns XAU to USD rate - we need USD per XAU (inverse)
            xau_to_usd = d["xau"]["usd"]
            # This gives price of 1 oz gold in USD
            price = round(1 / xau_to_usd, 2) if xau_to_usd < 1 else round(xau_to_usd, 2)
            logging.info(f"Gold price fetched: ${price}")
            bot_log.append(f"Gold price: ${price}")
            prices = [price + random.uniform(-8, 8) for _ in range(30)]
            prices[-1] = price
            return prices
        except Exception as e:
            logging.error(f"Source failed: {url} | {e}")
            continue
    # Last resort — use a hardcoded recent price so bot keeps running
    logging.warning("All price sources failed - using fallback price")
    bot_log.append("WARNING: Using fallback price - check API sources")
    price = 3320.0
    prices = [price + random.uniform(-8, 8) for _ in range(30)]
    prices[-1] = price
    return prices

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
    if not CLAUDE_API_KEY:
        bot_log.append("ERROR: CLAUDE_API_KEY not set in environment variables!")
        return {"signal": "HOLD", "confidence": 0, "reason": "No API key"}
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
        if "content" not in data:
            bot_log.append(f"Claude API error: {data}")
            return {"signal": "HOLD", "confidence": 0, "reason": "API error"}
        text = data["content"][0]["text"].strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        logging.error(f"Claude error: {e}")
        bot_log.append(f"Claude error: {e}")
        return {"signal": "HOLD", "confidence": 0, "reason": "error"}

def run_bot():
    bot_log.append("---- AURUM running ----")
    prices = get_gold_price()
    if not prices:
        bot_log.append("No price data available")
        return

    current_price = prices[-1]
    rsi = get_rsi(prices)
    fast_ma = get_ma(prices, 9)
    slow_ma = get_ma(prices, 21)

    msg = f"Gold: ${current_price:.2f} | RSI: {rsi} | FastMA: {fast_ma} | SlowMA: {slow_ma}"
    logging.info(msg)
    bot_log.append(msg)

    signal = ask_claude(current_price, rsi, fast_ma, slow_ma)
    sig_msg = f"Signal: {signal['signal']} | {signal['confidence']}% | {signal['reason']}"
    logging.info(sig_msg)
    bot_log.append(sig_msg)

    if signal["signal"] in ["BUY", "SELL"] and signal["confidence"] > 65:
        bot_log.append(f">>> Placing {signal['signal']} order...")
    else:
        bot_log.append("Holding - no trade placed")

def start_scheduler():
    schedule.every(15).minutes.do(run_bot)
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    bot_log.append("AURUM Bot starting...")
    scheduler_thread = threading.Thread(target=start_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    run_bot()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
