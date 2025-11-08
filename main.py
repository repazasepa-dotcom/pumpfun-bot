#!/usr/bin/env python3
import os
import asyncio
import requests
from telethon import TelegramClient, events
from flask import Flask
import threading
import json
from datetime import datetime

# -----------------------------
# ENVIRONMENT VARIABLES
# -----------------------------
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL_ID = -1003219642022  # your public channel
POSTED_FILE = "posted_coins.json"

# Load posted coins
if os.path.exists(POSTED_FILE):
    with open(POSTED_FILE, "r") as f:
        POSTED_COINS = json.load(f)
else:
    POSTED_COINS = []

# -----------------------------
# TELEGRAM CLIENT
# -----------------------------
client = TelegramClient("pre_pump_session", API_ID, API_HASH)

# -----------------------------
# FLASK KEEP-ALIVE (Render)
# -----------------------------
app = Flask(__name__)
@app.route("/")
def home():
    return "✅ Pre-Pump Scanner Bot Running"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, threaded=True)

# -----------------------------
# HELPER FUNCTIONS
# -----------------------------
async def fetch_new_coins(per_page=50, total_pages=3, spacing=2):
    coins = []
    for page in range(1, total_pages+1):
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": per_page,
            "page": page,
            "sparkline": "false"
        }
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            coins.extend(response.json())
        except Exception as e:
            print(f"[{datetime.utcnow()}] ❌ Fetch error page {page}: {e}")
        await asyncio.sleep(spacing)
    return coins

async def post_signal(c):
    global POSTED_COINS
    coin_id = c["id"]
    if coin_id in POSTED_COINS:
        return
    name = c["name"]
    symbol = c["symbol"].upper()
    volume = c.get("total_volume", 0)
    cg_link = f"https://www.coingecko.com/en/coins/{coin_id}"
    msg = f"🚀 {name} ({symbol})\nVolume: ${volume:,}\n{cg_link}"
    await client.send_message(CHANNEL_ID, msg)
    POSTED_COINS.append(coin_id)
    if len(POSTED_COINS) > 50:  # keep history
        POSTED_COINS.pop(0)
    with open(POSTED_FILE, "w") as f:
        json.dump(POSTED_COINS, f)

# -----------------------------
# SCAN AND POST NEW COINS
# -----------------------------
async def scan_and_post():
    coins = await fetch_new_coins()
    candidates = []

    for c in coins:
        volume = c.get("total_volume", 0)
        # Only new coins with volume >=100k AND <=200k
        if not (100_000 <= volume <= 200_000):
            continue
        if c["id"] in POSTED_COINS:
            continue
        # Optional: momentum filter based on 24h price change
        if c.get("price_change_percentage_24h") is None or c["price_change_percentage_24h"] < 5:
            continue
        candidates.append(c)

    # Sort by 24h gain descending (momentum)
    candidates.sort(key=lambda x: x.get("price_change_percentage_24h", 0), reverse=True)

    # Post up to 7 coins
    posted = 0
    for coin in candidates:
        if posted >= 7:
            break
        await post_signal(coin)
        posted += 1

    if posted == 0:
        await client.send_message(CHANNEL_ID, "❌ No new coins found with volume $100k–$200k and positive momentum.")

# -----------------------------
# TELEGRAM /signal COMMAND
# -----------------------------
@client.on(events.NewMessage(pattern="/signal"))
async def manual_trigger(event):
    user_id = event.sender_id
    await event.reply("⏳ Manual scan started — looking for up to 7 new coin(s). This may take a few minutes...")
    await scan_and_post()
    await event.reply("✅ Manual scan completed.")

# -----------------------------
# MAIN
# -----------------------------
async def main():
    await client.start(bot_token=BOT_TOKEN)
    print("✅ Pre-Pump Scanner Bot is live")
    await client.run_until_disconnected()

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    asyncio.run(main())
