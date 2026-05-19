import requests
import schedule
import time
import os
import json
import threading
import random
import sys
from flask import Flask

app = Flask(__name__)

# Credentials from environment variables
EXNESS_LOGIN = os.environ.get("MT5_LOGIN", "")
EXNESS_PASSWORD = os.environ.get("MT5_PASSWORD", "")
EXNESS_SERVER = os.environ.get("MT5_SERVER", "")
CLAUDE_API_KEY = os.environ.get("CLAUDE_API_KEY", "")

SYMBOL = "XAUUSD"
LOT = 0.01

# Log capture so we can see output in browser
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
            .buy {{ color:#00e676; }}
            .sell {{ color:#ff1744; }}
            .hold {{ color:#ffd600; }}
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
            headers={"User-Agent": "Mozilla/5.0"}
        )
        data = response.json()
        current = data["items"][0]["xauPrice"]
        print(f"Live gold price fetched: ${current}")
        prices = [current + random.uniform(-8, 8) for _ in range(30)]
        prices[-1] = current
        return prices
    except Exception as e:
        print(f"Price fetch error (primary): {e}")
        try:
            r = requests.get(
                "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/XAU/USD",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            d = r.json()
            price = d[0]["spreadProfilePrices"][0]["ask"]
            print(f"Live gold price fetched (fallback): ${price}")
            prices = [price + random.uniform(-8, 8) for _ in range(30)]
            prices[-1] = price
            return prices
        except Exception as e2:
            print(f"Price fetch error (fallback): {e2}")
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
    return round
