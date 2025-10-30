#!/usr/bin/env python3
"""
Pump.fun test bot — posts EVERY new coin (for testing)
Deploy notes:
- Set env vars (see below)
- Add UptimeRobot to https://<your-render-url>/health (5 min)
- After testing, we will add filters/heuristics
"""

import os
import asyncio
import aiohttp
import json
import time
from telethon import TelegramClient
from keep_alive import start as start_keepalive
from flask import Flask, jsonify

# -----------------------
# Configuration (env)
# -----------------------
API_ID = int(os.getenv("API_ID", "0"))            # your Telegram API ID
API_HASH = os.getenv("API_HASH", "")              # your Telegram API HASH
BOT_TOKEN = os.getenv("BOT_TOKEN", "")            # BotFather token
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT", "@PumpFunMemeCoinAlert")  # channel username or -100... id
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "15"))   # seconds between polls
SEEN_STORE = os.getenv("SEEN_STORE", "/tmp/seen_pump.json")
KEEP_ALIVE_MSG = os.getenv("KEEP_ALIVE_MSG", "Pump.fun test bot alive ✅")

# Safety: require BOT_TOKEN
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN env var is required")

# -----------------------
# Telethon client
# -----------------------
client = TelegramClient("pumpfun", API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# -----------------------
# Simple persistent seen-cache
# -----------------------
def load_seen():
    try:
        if os.path.exists(SEEN_STORE):
            with open(SEEN_STORE, "r") as f:
                data = json.load(f)
                return set(data)
    except Exception as e:
        print("load_seen error:", e)
    return set()

def save_seen(seen):
    try:
        with open(SEEN_STORE, "w") as f:
            json.dump(list(seen), f)
    except Exception as e:
        print("save_seen error:", e)

seen = load_seen()

# -----------------------
# PumpPortal fetcher
# -----------------------
PUMP_PORTAL_URL = "https://pumpportal.fun/api/data/all_coins"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; PumpFunBot/1.0)",
    "Accept": "application/json",
    "Referer": "https://pump.fun"
}

async def fetch_pumpportal():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(PUMP_PORTAL_URL, headers=DEFAULT_HEADERS, timeout=15) as resp:
                if resp.status != 200:
                    print("PumpPortal status:", resp.status)
                    return []
                data = await resp.json()
                # data is usually a list of coin objects
                return data or []
    except Exception as e:
        print("fetch_pumpportal error:", e)
        return []

# -----------------------
# Posting helper
# -----------------------
async def post_coin_to_channel(coin):
    """
    coin: dict from pumpportal feed. We keep message compact for channel.
    """
    try:
        mint = coin.get("mint") or coin.get("mintAddress") or coin.get("address") or ""
        symbol = coin.get("symbol") or coin.get("name") or "UNKNOWN"
        name = coin.get("name") or symbol
        # market cap placeholder if missing
        mc = coin.get("usd_market_cap") or coin.get("marketCap") or 0

        text = (
            f"🔥 <b>NEW Pump.fun Coin (TEST)</b>\n\n"
            f"💠 <b>Token:</b> {name} ({symbol})\n"
            f"🧬 <b>Mint:</b> <code>{mint}</code>\n"
            f"💰 <b>MC (est):</b> ${int(mc):,}\n"
            f"🔗 <b>Pump.fun:</b> https://pump.fun/{mint}\n\n"
            f"_Posted for testing — each coin is posted once._"
        )
        await client.send_message(TELEGRAM_CHAT, text, parse_mode="html")
        print("✅ Posted:", symbol, mint)
    except Exception as e:
        print("post_coin_to_channel error:", e)

# -----------------------
# Single-scan function (used by monitor and forcecheck)
# -----------------------
async def scan_once():
    print("⏳ Scanning pumpportal (single-run)...")
    data = await fetch_pumpportal()
    if not data:
        print("⚠️ No data returned from PumpPortal")
        return 0

    posted = 0
    # ensure data is list-like -> iterate safe
    for coin in data:
        try:
            mint = coin.get("mint") or coin.get("mintAddress") or coin.get("address") or None
            if not mint:
                continue
            if mint in seen:
                continue
            # Post (for test we post every new coin)
            await post_coin_to_channel(coin)
            seen.add(mint)
            posted += 1
            # small delay between posts to avoid flooding
            await asyncio.sleep(1.2)
        except Exception as e:
            print("scan_once loop error:", e)
    save_seen(seen)
    print(f"🔁 scan_once finished — posted {posted} new coins")
    return posted

# -----------------------
# Monitor loop (polling)
# -----------------------
async def monitor_loop():
    print("▶️ Monitor started — polling every", POLL_INTERVAL, "seconds")
    while True:
        try:
            await scan_once()
        except Exception as e:
            print("monitor_loop error:", e)
        await asyncio.sleep(POLL_INTERVAL)

# -----------------------
# Flask / forcecheck route wiring
# -----------------------
# We attach a small route to the keep-alive flask app to trigger scan_once from the web.
# keep_alive.start() runs threaded Flask; we can import the app object if needed.
from keep_alive import app as keep_app

@keep_app.route("/forcecheck", methods=["GET"])
def http_forcecheck():
    """
    Trigger a single scan run asynchronously and return immediately.
    Use via GET: https://your-render-url/forcecheck
    """
    try:
        # schedule scan_once on Telethon/event loop
        asyncio.run_coroutine_threadsafe(scan_once(), client.loop)
        return {"status": "scheduled"}, 200
    except Exception as e:
        return {"error": str(e)}, 500

# -----------------------
# Startup
# -----------------------
if __name__ == "__main__":
    # start keep-alive Flask server in separate thread
    start_keepalive()
    time.sleep(0.5)
    print("✅ Keep-alive started; starting monitor...")

    # Start the Telethon client loop and run monitor
    with client:
        client.loop.run_until_complete(monitor_loop())
