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
    return "✅ Meme Coin Scanner Bot Running"

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
            "order": "market_cap_asc",
            "per_page": per_page,
            "page": page,
            "sparkline": "false",
            "price_change_percentage": "1h,24h"
        }
        try:
            response = requests.get(url, params=params, timeout=20)
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
    market_cap = c.get("market_cap", 0)
    price_1h = c.get("price_change_percentage_1h_in_currency", 0)
    price_24h = c.get("price_change_percentage_24h_in_currency", 0)
    cg_link = f"https://www.coingecko.com/en/coins/{coin_id}"

    msg = (
        f"🚀 {name} ({symbol})\n"
        f"Volume: ${volume:,}\n"
        f"Market Cap: ${market_cap:,}\n"
        f"1h Gain: {price_1h:.2f}% | 24h Gain: {price_24h:.2f}%\n"
        f"{cg_link}\n\n"
        f"⚠️ Disclaimer: This is for informational purposes only. DYOR before investing."
    )

    await client.send_message(CHANNEL_ID, msg)
    POSTED_COINS.append(coin_id)
    if len(POSTED_COINS) > 100:  # keep history
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
        market_cap = c.get("market_cap", 0)
        price_1h = c.get("price_change_percentage_1h_in_currency", 0)
        price_24h = c.get("price_change_percentage_24h_in_currency", 0)

        # Volume 100k–200k
        if not (100_000 <= volume <= 200_000):
            continue
        if c["id"] in POSTED_COINS:
            continue
        # Momentum: 24h ≥5% OR 1h ≥2%
        if (price_24h < 5) and (price_1h < 2):
            continue
        # Small market cap
        if market_cap > 5_000_000:
            continue

        candidates.append(c)

    # Sort by 24h gain descending
    candidates.sort(key=lambda x: x.get("price_change_percentage_24h_in_currency", 0), reverse=True)

    posted = 0
    for coin in candidates:
        if posted >= 7:
            break
        await post_signal(coin)
        posted += 1

    if posted == 0:
        await client.send_message(CHANNEL_ID, "❌ No new meme coins found with volume $100k–$200k and positive momentum.")

# -----------------------------
# TELEGRAM /signal COMMAND
# -----------------------------
@client.on(events.NewMessage(pattern="/signal"))
async def manual_trigger(event):
    await event.reply("⏳ Manual scan started — looking for up to 7 new coin(s). This may take a few minutes...")
    await scan_and_post()
    await event.reply("✅ Manual scan completed.")

# -----------------------------
# AUTOMATIC SCAN LOOPS
# -----------------------------
async def auto_scan_loop(interval_seconds=600):
    """Fast scan every 10 minutes"""
    while True:
        try:
            print(f"[{datetime.utcnow()}] ⏱️ Running fast automatic scan...")
            await scan_and_post()
        except Exception as e:
            print(f"[{datetime.utcnow()}] ❌ Error in fast scan: {e}")
        await asyncio.sleep(interval_seconds)

async def hourly_scan_loop():
    """Hourly backup scan"""
    while True:
        try:
            print(f"[{datetime.utcnow()}] ⏱️ Running hourly scan...")
            await scan_and_post()
        except Exception as e:
            print(f"[{datetime.utcnow()}] ❌ Error in hourly scan: {e}")
        await asyncio.sleep(3600)  # 1 hour

# -----------------------------
# MAIN
# -----------------------------
async def main():
    await client.start(bot_token=BOT_TOKEN)
    print("✅ Meme Coin Scanner Bot is live")

    # Start fast and hourly scans
    asyncio.create_task(auto_scan_loop())
    asyncio.create_task(hourly_scan_loop())

    await client.run_until_disconnected()

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    asyncio.run(main())
