import os
import time
import requests
from datetime import datetime
from flask import Flask
import threading
from telegram import Bot

# ------------------- ENV VARIABLES -------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("TELEGRAM_CHAT")  # @YourChannel
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", 20))
LOWCAP_THRESHOLD = int(os.getenv("LOWCAP_THRESHOLD_MC", 5000))
KEEP_ALIVE_MSG = os.getenv("KEEP_ALIVE_MSG", "✅ Pump.fun watcher running")

bot = Bot(token=BOT_TOKEN)

# ------------------- FLASK KEEP ALIVE -------------------
app = Flask(__name__)

@app.route('/')
def home():
    return KEEP_ALIVE_MSG

def run_web():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web, daemon=True).start()

# ------------------- TRACKER LOGIC -------------------
last_seen = set()

def get_new_coins():
    try:
        url = "https://pump.fun/api/trending/1?sort=created"
        data = requests.get(url, timeout=10).json()
        return data
    except Exception as e:
        print("Error fetching pump.fun:", e)
        return []

def format_alert(coin):
    name = coin.get("name", "Unknown")
    mint = coin.get("mint", "")
    mc = round(coin.get("marketCap", 0))

    link = f"https://pump.fun/coin/{mint}"
    
    message = (
        f"🚨 **New Meme Coin Launched!**\n\n"
        f"🪙 **{name}**\n"
        f"💰 Marketcap: **${mc}**\n"
        f"🔗 Pump.fun: {link}\n\n"
        f"⚠️ DYOR — new coin detected!"
    )
    return message

def post_alert(coin):
    msg = format_alert(coin)
    bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown")

def run_tracker():
    print("✅ Pump.fun tracker started")

    while True:
        coins = get_new_coins()

        for coin in coins:
            mint = coin.get("mint")
            mc = coin.get("marketCap", 0)

            if mint in last_seen:
                continue

            # Only alert low market cap coins
            if mc <= LOWCAP_THRESHOLD:
                post_alert(coin)

            last_seen.add(mint)

        time.sleep(POLL_INTERVAL)

# ------------------- START -------------------
if __name__ == "__main__":
    run_tracker()
